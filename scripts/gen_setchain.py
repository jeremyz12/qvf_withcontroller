# -*- coding: utf-8 -*-
"""scripts/gen_setchain.py — 集合型孪生题集生成器(实验 C)。

与 `scripts/gen_stale_chain.py` **配对**:同一个生成模型、同一个干扰会话池
(`build_haystack` 直接导入复用,不复制)、同样的状态数分布(3–5)、同样的日期跨度、
同样的逐字锚点校验。**唯一的差别是值之间的语义关系**:

| | 替换型(gen_stale_chain) | **集合型(本文件)** |
|---|---|---|
| 值的关系 | 后值**取代**前值 | 后值**叠加**,前值仍然有效 |
| 措辞 | "we moved" / "switching to" | "also picked up" / "still doing X, now also Y" |
| dim1 金答案 | 链末值 | **全部值(集合)** |
| dim2 金答案 | 变更次数 = len−1 | **持有总数 = len** |
| dim4 金答案 | 区间覆盖该日的那个值 | **截至该日已有的全部值** |
| dim5 金答案 | 有序变化历程 | **有序累积历程** |

为什么必须配对:实验 A/B/B′/B″ 已证明跨语料相关(set 占比 r=−0.963)进不了卷内
(r=−0.055),即那些相关只能归因于与语料构造方式共变的因素。本生成器把
"值的语义关系"从语料属性中**单独拆出来变成唯一自变量**,是唯一的前瞻性因果检验。
判据见 `results/set_vs_replacement_prereg.md` 实验 C。

用法:
    python scripts/gen_setchain.py --n 50 --out data/setchain_50.json
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

# 复用替换型生成器的干扰会话构造 —— 保证两批条目的 haystack 同源同分布
from scripts.gen_stale_chain import build_haystack  # noqa: E402

#: 集合型主题:这些属性在真人身上**累积**而非替换。
#: 与 gen_stale_chain.TOPICS **零重叠**(已断言)—— 同一槽位出现在两批里会把
#: "槽位难度"混进唯一自变量,那样 C 就白做了。
TOPICS = [
    "hobby", "sport played", "musical instrument", "language being learned",
    "board game owned", "houseplant", "podcast subscribed", "cookbook owned",
    "volunteer cause", "collectible category", "streaming service subscribed",
    "hiking trail completed", "certification earned", "chess opening studied",
    "regular running route", "craft skill", "book club joined",
    "charity donated to", "recipe mastered", "photography subject",
]


class SetState(BaseModel):
    value: str = Field(description="The NEW item added at this stage, short.")
    date: str = Field(description="Session date YYYY-MM-DD; strictly later than the previous state.")
    session_turns: list[str] = Field(
        description="3-5 casual first-person user messages forming this session. "
        "EXACTLY ONE turn must state that the user ADDED this new item while "
        "KEEPING the earlier ones (accumulation language: 'also picked up', "
        "'on top of X I now', 'still doing X, and started Y'). "
        "NEVER use replacement language (no 'switched', 'moved', 'instead of', "
        "'gave up', 'quit', 'replaced'). No other item values mentioned."
    )
    state_span: str = Field(
        description="VERBATIM contiguous substring of one session turn that "
        "states this newly added item (will be checked mechanically)."
    )


class SetItem(BaseModel):
    slot: str
    chain: list[SetState] = Field(description="3 to 5 accumulated items, chronological.")
    q_current: str = Field(description="Natural question asking what the user has NOW (expects ALL items).")
    q_count: str = Field(description="Natural question asking HOW MANY the user has in total.")
    q_point_in_time: str = Field(
        description="Question asking what the user had AS OF a specific past date "
        "that falls strictly between two additions (name the date explicitly)."
    )
    point_date: str = Field(description="That date, YYYY-MM-DD.")
    point_gold_index: int = Field(
        description="Index of the LAST item added on or before point_date "
        "(so the gold set is chain[0..point_gold_index])."
    )
    q_trajectory: str = Field(description="Question asking how the collection grew over time.")


GEN_PROMPT = """You create ONE benchmark item for a long-term-memory assistant
evaluation. A single user attribute (slot) ACCUMULATES {n_states} items over
time — each new item is ADDED while all earlier ones REMAIN TRUE. Write
natural, varied, casual user messages — no meta language.

CRITICAL — this is an ACCUMULATION item, not a replacement item:
- The user NEVER drops, quits, switches away from, or replaces an earlier item.
- Every earlier item is still true at the end.
- Use accumulation language: "also picked up", "on top of that I started",
  "still doing X and now Y too", "added Z to the rotation".
- FORBIDDEN words in the state turns: switched, moved, instead, replaced,
  gave up, quit, dropped, no longer, used to.

Other constraints:
- Values pairwise distinct and unambiguous.
- Dates strictly increasing, spread over 6-18 months, all in 2025.
- point_in_time date must fall strictly BETWEEN two consecutive addition dates.
- point_gold_index = index of the last item added on or before point_date.
Topic/slot: {topic}
Variation key: {vkey} — make this item clearly distinct from any other item on
the same topic (different names, places, brands, values, writing style).
"""

#: 替换语言黑名单 —— 出现即判该条目不合格(机械校验,不靠人眼)
#: 2026-08-20 泄漏审计修复:升级为词干正则并与替换侧词表配平;
#: 新增跨状态值提及禁令(实测 18/47 条目单会话可直答计数题,+2.66pp 反超
#: 全部来自该子集——见 results/twin_leak_audit_20260820.md)。
import re as _re
_FORBIDDEN_RE = _re.compile(
    r"\b(switch(ed|ing)?|mov(ed|ing)|instead of|replac(e|ed|ing)|gave up|"
    r"quit|dropp(ed|ing)|no longer|used to|swap(ped|ping)?|done with)\b", _re.I)


def _xvalue_errors(ch) -> list[str]:
    """跨状态值提及机械禁令(与替换侧同一实现,镜像复制)。"""
    vals = [s.value.strip().lower() for s in ch]
    errs = []
    for i, s in enumerate(ch):
        blob = " ".join(s.session_turns).lower()
        others = [v for j, v in enumerate(vals) if j != i and v and v in blob]
        if others:
            errs.append(f"cross-state value mention in state {i}: {others[:2]}")
    return errs


def validate(item: SetItem) -> list[str]:
    """与替换型 validate() 同构的机械校验,外加累积语义的黑名单检查。"""
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
        # 累积语义:后续状态的会话里不得出现替换措辞
        if i > 0:
            blob = " ".join(s.session_turns).lower()
            hit = _FORBIDDEN_RE.findall(blob)
            if hit:
                errs.append(f"replacement language in state {i}: "
                            f"{[h[0] if isinstance(h, tuple) else h for h in hit][:3]}")
    errs += _xvalue_errors(ch)
    gi = item.point_gold_index
    if not (0 <= gi < len(ch)):
        errs.append("point gold index range")
    else:
        pd = item.point_date
        if not (ch[gi].date <= pd and (gi + 1 >= len(ch) or pd < ch[gi + 1].date)):
            errs.append("point date/gold mismatch")
        if pd in dates:
            errs.append("point date equals an addition date")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20260819)
    ap.add_argument("--out", default="data/setchain_50.json")
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
        n_states = rng.choice([3, 3, 4, 4, 5])   # 与替换型同分布
        item = None
        for attempt in range(3):
            resp = client.messages.parse(
                model=a.model, max_tokens=16000,
                messages=[{"role": "user", "content": GEN_PROMPT.format(
                    n_states=n_states, topic=topic, vkey=f"{a.seed}-{i}")}],
                output_format=SetItem,
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
        uid = f"setchain{i:03d}-{rng.randrange(16**8):08x}"
        vals = [s.value for s in item.chain]
        gi = item.point_gold_index
        out.append({
            "uid": uid,
            "type": "SETCHAIN",
            "slot": item.slot,
            "chain": [s.model_dump() for s in item.chain],
            "sessions": sessions,
            "probing_queries": {
                # 与替换型的 dim1/2/4/5 一一对应,但金答案按集合语义机械导出
                "dim1_current": {"q": item.q_current, "gold": "; ".join(vals)},
                "dim2_count": {"q": item.q_count, "gold": str(len(vals))},
                "dim4_point_in_time": {"q": item.q_point_in_time,
                                       "gold": "; ".join(vals[:gi + 1]),
                                       "date": item.point_date},
                "dim5_trajectory": {"q": item.q_trajectory,
                                    "gold": " -> ".join(vals)},
            },
            "attribution": "Derivative of STALE (arXiv 2605.06527, CC BY 4.0): "
                           "distractor sessions remixed from the original haystacks. "
                           "Set-type twin of STALE-Chain (scripts/gen_stale_chain.py); "
                           "same haystack pool, same state-count distribution, "
                           "same verbatim-anchor validators.",
        })
        print(f"[{topic}] ok: {len(item.chain)} items, {len(sessions)} sessions",
              file=sys.stderr)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    cost = n_in / 1e6 * 5 + n_out / 1e6 * 25   # opus-5
    print(f"wrote {len(out)}/{a.n} items -> {a.out}")
    print(f"generation cost: in={n_in:,} out={n_out:,} ≈ ${cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
