# -*- coding: utf-8 -*-
"""scripts/gen_replchain_twin.py — 替换型孪生题集生成器(实验 C 修订版,替换侧)。

为什么存在:Fable-5 审阅发现 ③ —— 原计划以 chain-212/confirm-228 作替换侧,
但其 dim2 是预设陷阱题,而集合侧 dim2 是计数题,问法类型混进唯一自变量。
本文件与 `scripts/gen_setchain.py` **逐项镜像**,使四类问法一一对应:

| | 本文件(替换) | gen_setchain(集合) |
|---|---|---|
| dim1_current | 现在的值(gold=末值) | 现在的全部(gold=全集) |
| **dim2_count** | **换过几次(gold=len−1)** | **有几个(gold=len)** |
| dim4_point_in_time | 某日的值(gold=区间覆盖值) | 截至某日的全集 |
| dim5_trajectory | 变化历程 | 累积历程 |

对称控制:同 seed、同模型、同 `build_haystack` 干扰池、同状态数分布 [3,3,4,4,5]、
同逐字锚点/日期递增/值两两不同校验。语言约束互为镜像:
集合侧黑名单禁替换词;**本侧黑名单禁累积短语**(见 `_FORBIDDEN_ACCUM`)。

固有混淆(如实声明):主题与语义天然绑定(phone model 只能替换、hobby 只能累积),
「主题」无法与「值语义」解耦 —— 这是该操纵的本性,缓解手段即上述全部对称控制。

用法:
    python scripts/gen_replchain_twin.py --n 50 --out data/replchain_50.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

# 与集合侧共用同一干扰会话构造与同一批替换型主题
from scripts.gen_stale_chain import TOPICS, build_haystack  # noqa: E402


class ReplState(BaseModel):
    value: str = Field(description="The slot value at this stage, short.")
    date: str = Field(description="Session date YYYY-MM-DD; strictly later than the previous state.")
    session_turns: list[str] = Field(
        description="3-5 casual first-person user messages forming this session. "
        "EXACTLY ONE turn must state that the user REPLACED the previous value "
        "with this new one (change language, explicit or oblique: 'we moved', "
        "'switched to', 'signing the lease tomorrow'). The old value is NO "
        "LONGER true afterwards. NEVER use accumulation language (no 'also "
        "picked up', 'on top of that', 'still doing X and now Y', 'added "
        "another'). No other state values mentioned."
    )
    state_span: str = Field(
        description="VERBATIM contiguous substring of one session turn that "
        "states this value (will be checked mechanically)."
    )


class ReplItem(BaseModel):
    slot: str
    chain: list[ReplState] = Field(description="3 to 5 states, chronological.")
    q_current: str = Field(description="Natural question asking the CURRENT value.")
    q_count: str = Field(
        description="Natural question asking HOW MANY TIMES the user changed "
        "this attribute in total."
    )
    q_point_in_time: str = Field(
        description="Question asking the value AT a specific past date that "
        "falls strictly between two changes (name the date explicitly)."
    )
    point_date: str = Field(description="That date, YYYY-MM-DD.")
    point_gold_index: int = Field(
        description="Index of the state valid at point_date (the last state "
        "whose date is on or before point_date)."
    )
    q_trajectory: str = Field(description="Question asking how the value changed over time.")


GEN_PROMPT = """You create ONE benchmark item for a long-term-memory assistant
evaluation. A single user attribute (slot) is REPLACED through {n_states}
successive values over time — each new value REPLACES the previous one, which
is no longer true afterwards. Write natural, varied, casual user messages —
no meta language.

CRITICAL — this is a REPLACEMENT item, not an accumulation item:
- Exactly ONE value is true at any moment; the newest replaces the old.
- Use change language, explicit or oblique: "we moved", "switched to",
  "starting at <new employer> Monday", "signing the lease tomorrow".
- FORBIDDEN phrases in the state turns: "also picked up", "on top of that",
  "still doing", "added another", "to the rotation", "as well as my",
  "in addition to".

Other constraints:
- Values pairwise distinct and unambiguous.
- Dates strictly increasing, spread over 6-18 months, all in 2025.
- point_in_time date must fall strictly BETWEEN two consecutive change dates.
- point_gold_index = index of the state valid at point_date.
Topic/slot: {topic}
Variation key: {vkey} — make this item clearly distinct from any other item on
the same topic (different names, places, brands, values, writing style).
"""

#: 累积语言黑名单(与集合侧的替换黑名单互为镜像;机械校验,不靠人眼)
#: 2026-08-20 泄漏审计修复(results/twin_leak_audit_20260820.md):旧短语表漏放
#: 词干级线索(also/another/still…),实测 21/127 后续状态残留;升级为词干正则,
#: 覆盖度与集合侧词表配平。旧短语表保留在正则内(短语含其词干)。
import re as _re
_FORBIDDEN_ACCUM_RE = _re.compile(
    r"\b(also|another|as well|plus|and now|on top of|in addition)\b|\bstill\b",
    _re.I)


def _xvalue_errors(ch) -> list[str]:
    """跨状态值提及机械禁令(泄漏审计 (b):单会话提及 ≥2 个链值 → 计数/当前值
    题可单会话直答)。任一状态的会话文本提及其他状态的值即不合格。"""
    vals = [s.value.strip().lower() for s in ch]
    errs = []
    for i, s in enumerate(ch):
        blob = " ".join(s.session_turns).lower()
        others = [v for j, v in enumerate(vals) if j != i and v and v in blob]
        if others:
            errs.append(f"cross-state value mention in state {i}: {others[:2]}")
    return errs


def validate(item: ReplItem) -> list[str]:
    """与 gen_setchain.validate 同构:同样的链长/去重/日期/逐字锚点检查,
    黑名单方向相反(禁累积短语)。"""
    errs = []
    ch = item.chain
    if not (3 <= len(ch) <= 5):
        errs.append("chain length")
    if len({s.value.strip().lower() for s in ch}) != len(ch):
        errs.append("values not distinct")
    dates = [s.date for s in ch]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        errs.append("dates not strictly increasing")
    for i, s in enumerate(ch):
        if not any(s.state_span in t for t in s.session_turns):
            errs.append(f"span missing in state {i}")
        if s.value.lower() not in s.state_span.lower():
            errs.append(f"value not inside span {i}")
        if i > 0:
            blob = " ".join(s.session_turns).lower()
            hit = _FORBIDDEN_ACCUM_RE.findall(blob)
            if hit:
                errs.append(f"accumulation language in state {i}: "
                            f"{[h for h in hit if h][:3]}")
    errs += _xvalue_errors(ch)
    gi = item.point_gold_index
    if not (0 <= gi < len(ch)):
        errs.append("point gold index range")
    else:
        pd = item.point_date
        if not (ch[gi].date <= pd and (gi + 1 >= len(ch) or pd < ch[gi + 1].date)):
            errs.append("point date/gold mismatch")
        if pd in dates:
            errs.append("point date equals a change date")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20260819)   # 与集合侧同 seed
    ap.add_argument("--out", default="data/replchain_50.json")
    ap.add_argument("--model", default="claude-opus-5")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    stale_items = json.load(open("data/stale_T1_T2_400_FULL.json", encoding="utf-8"))
    client = anthropic.Anthropic()
    out = []
    topics = [TOPICS[i % len(TOPICS)] for i in range(a.n)]
    rng.shuffle(topics)
    n_in = n_out = 0
    for i, topic in enumerate(topics):
        n_states = rng.choice([3, 3, 4, 4, 5])   # 与集合侧同分布
        item = None
        for attempt in range(3):
            resp = client.messages.parse(
                model=a.model, max_tokens=16000,
                messages=[{"role": "user", "content": GEN_PROMPT.format(
                    n_states=n_states, topic=topic, vkey=f"{a.seed}-{i}")}],
                output_format=ReplItem,
            )
            n_in += resp.usage.input_tokens
            n_out += resp.usage.output_tokens
            item = resp.parsed_output
            if item is None:
                continue
            errs = validate(item)
            if not errs:
                break
            print(f"[{topic}] attempt {attempt}: {errs}", file=sys.stderr)
            item = None
        if item is None:
            print(f"[{topic}] FAILED validation 3x, skipped", file=sys.stderr)
            continue
        sessions = build_haystack(rng, stale_items, item.chain)
        uid = f"replchain{i:03d}-{rng.randrange(16**8):08x}"
        vals = [s.value for s in item.chain]
        gi = item.point_gold_index
        out.append({
            "uid": uid,
            "type": "REPLCHAIN",
            "slot": item.slot,
            "chain": [s.model_dump() for s in item.chain],
            "sessions": sessions,
            "probing_queries": {
                "dim1_current": {"q": item.q_current, "gold": vals[-1]},
                "dim2_count": {"q": item.q_count, "gold": str(len(vals) - 1)},
                "dim4_point_in_time": {"q": item.q_point_in_time,
                                       "gold": vals[gi],
                                       "date": item.point_date},
                "dim5_trajectory": {"q": item.q_trajectory,
                                    "gold": " -> ".join(vals)},
            },
            "attribution": "Derivative of STALE (arXiv 2605.06527, CC BY 4.0): "
                           "distractor sessions remixed from the original haystacks. "
                           "Replacement-type twin of scripts/gen_setchain.py; "
                           "same haystack pool, same state-count distribution, "
                           "same verbatim-anchor validators, mirrored language "
                           "blacklists.",
        })
        print(f"[{topic}] ok: {len(item.chain)} states, {len(sessions)} sessions",
              file=sys.stderr)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    cost = n_in / 1e6 * 5 + n_out / 1e6 * 25
    print(f"wrote {len(out)}/{a.n} items -> {a.out}")
    print(f"generation cost: in={n_in:,} out={n_out:,} ≈ ${cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
