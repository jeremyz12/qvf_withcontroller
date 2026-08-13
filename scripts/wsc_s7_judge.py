# -*- coding: utf-8 -*-
"""S7 标签汇总题接地性评审器(gold=null 行专用;与判官臂完全解耦)。

results/wsc_s7_demo.jsonl 里的 S7 行 gold_answer 恒为 null,只带 judge_rubric
("answer must cite only items actually present in sessions, with dates")。
本评审器把该 rubric 机械化,逐行两步:

  ① 主张抽取:一次 haiku 调用(messages.parse,pydantic 列表模式,与
     complex_query_arm.compile_plan 同款重试/缓存写法)把回答拆成主张条目
     [{item, date_or_period}];只见问题与回答,不见会话/卡片。
  ② 机械核对:纯代码、零 LLM。每条主张对照两路来源:
     (a) 该 uid 的会话逐场文本(--data,场内全部 turns 拼接,配会话日期);
     (b) 标签卡片库(--cards-dir,value+value_tags+source_span,日期取
         stated_date 或经 source_memory_id 回落会话日期)。
     文本判接地:规范化子串命中,或词重叠(主张词被来源覆盖比例 >= 0.5;
     词集用 engine_bridge 同款 _hit_tokens —— 英文词 + CJK 单字/双字组,
     无需分词器)。日期判接地:主张所述日期须在其自身粒度内与来源日期一致
     (只说年 → 年相等;说到月 → 年月相等;说到日 → 年月日相等)。
     任一来源同时过文本与日期两关即为接地。

行级产出:claims_n / grounded_n / precision / hallucinated(未接地清单,
含 not_found 与 date_mismatch 归因);另有库侧召回:该题所问标签下的卡片
未被回答提及者计失,recall = 提及数/标签卡数。汇总行给均值。

复制而非导入(qvf/engine_bridge 连带 rank_bm25 与遗留引擎路径,
scripts/complex_query_arm 连带 wt_qvf_prototype 全链;评审器不背这些依赖):
_hit_tokens/_HIT_STOP 逐字取自 qvf/engine_bridge.py,_load_entries/_mem_dates/
_rec_date/_tagged 逐字取自 scripts/complex_query_arm.py;--smoke 里逐一断言
与原件行为等价(同 complex_query_arm 对 SLOT_ALIASES 的处理精神)。

用法:
  python scripts/wsc_s7_judge.py --rows results/wsc_s7_demo.jsonl \
      --data data/stale_chain_full.json --cards-dir results/wt_cards_tagged \
      --out results/wsc_s7_judged.jsonl [--resume]
  python scripts/wsc_s7_judge.py --smoke     # 离线冒烟:桩客户端,零 API
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from qvf import config  # noqa: E402

# 抽取调用与各臂同款小模型(QVF_ADAPTER_MODEL,默认 haiku-4-5)。
MODEL = config.DEFAULT_ADAPTER_MODEL

OVERLAP_MIN = 0.5    # 主张词被来源覆盖的最低比例(含 CJK 双字组)

# ── 复制片段(--smoke 断言与原件等价) ────────────────────────
# 与 qvf/engine_bridge.py 的 _HIT_STOP/_hit_tokens 逐字一致。
_HIT_STOP = frozenset(
    "the a an and or of to in on at is are was were be been am do does did "
    "i you he she it we they my your his her its our their me him them us "
    "this that these those for with about from as by not no yes so if but "
    "what when where which who whom why how".split())


def _hit_tokens(_s):
    # Lowercase word tokens (stopwords dropped); single chars + character
    # bigrams for non-ASCII runs so overlap scoring also works on CJK text
    # without a tokenizer.
    _s = _s.lower()
    toks = set(re.findall(r"[a-z0-9]+", _s)) - _HIT_STOP
    run = [c for c in _s if ord(c) > 127 and not c.isspace()]
    toks.update(run)
    toks.update(a + b for a, b in zip(run, run[1:]))
    return toks


# 与 scripts/complex_query_arm.py 的同名函数逐字一致。
def _load_entries(paths: List[str]) -> dict:
    """合并多份 chain 架构数据,按 uid 去重(同 gen_wikistate_complex)。"""
    by_uid: dict = {}
    for f in paths:
        for e in json.loads(Path(f).read_text(encoding="utf-8")):
            by_uid.setdefault(e["uid"], e)
    return by_uid


def _mem_dates(entry: dict) -> dict:
    md = {}
    for si, sess in enumerate(entry.get("sessions", [])):
        for ri, _ in enumerate(sess.get("turns", [])):
            md[f"{entry['uid']}/s{si}#r{ri}"] = sess.get("date", "")
    return md


def _rec_date(rec: dict, mem_dates: dict) -> str:
    return rec.get("stated_date") or mem_dates.get(
        rec.get("source_memory_id", ""), "")


def _tagged(recs: List[dict], tag: str) -> List[dict]:
    t = (tag or "").strip()
    return [r for r in recs
            if any((x or "").strip() == t for x in (r.get("value_tags") or []))]


# ── ① 主张抽取:回答 → [{item, date_or_period}] ──────────────
class ClaimedItem(BaseModel):
    item: str = Field(
        description="One concrete thing the answer claims the user "
        "mentioned/did/had/experienced, as a short phrase reusing the "
        "answer's own content words.")
    date_or_period: Optional[str] = Field(
        default=None,
        description="The date or period the ANSWER attaches to this item, "
        "copied verbatim (e.g. 'January 4th, 2025', 'March 2025', '2024', "
        "'throughout 2025'); null if the answer attaches none.")


class ClaimExtraction(BaseModel):
    claims: List[ClaimedItem] = Field(
        description="Every claimed item found in the answer.")


EXTRACT_PROMPT = """\
You will be given a QUESTION a user asked their personal AI assistant about
their own history, and the ASSISTANT'S ANSWER. Extract every concrete claimed
item: a specific thing the answer asserts the user mentioned, did, had, or
experienced. Output STRICT JSON only, exactly this object and nothing else:
{"claims": [{"item": "<short phrase>", "date_or_period": <str|null>}]}

Rules:
1. One claim per distinct item/event/state; split conjunctions ("X and Y" ->
   two claims when X and Y are separate items).
2. item reuses the answer's own content words; never paraphrase into new
   facts and never add anything the answer does not say.
3. date_or_period is copied verbatim as the answer states it ("January 4th,
   2025", "March 2025", "2024", "throughout 2025"); null if the answer
   attaches no date to that item.
4. Skip sentences that add no item: openers, category names, meta remarks
   ("that's the one item we have stored"), and trend commentary without a
   concrete item ("your circle expanded").
5. Empty answer or pure refusal -> {"claims": []}.
"""


def extract_claims(client, question: str, answer: str):
    """一次 haiku 抽取调用(重试 3 次);返回 (claims, in_tok, out_tok, ok)。
    全部失败时返回空清单(ok=False),该行 precision 记 null,不进均值。"""
    tin = tout = 0
    content = f"QUESTION: {question}\n\nASSISTANT'S ANSWER: {answer}"
    for _ in range(3):
        try:
            resp = client.messages.parse(
                model=MODEL, max_tokens=1000, temperature=0.0,
                system=[{"type": "text", "text": EXTRACT_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
                output_format=ClaimExtraction,
            )
            tin += resp.usage.input_tokens
            tout += resp.usage.output_tokens
            p = resp.parsed_output
            if p is not None:
                return [c.model_dump() for c in p.claims], tin, tout, True
        except Exception:  # noqa: BLE001
            continue
    return [], tin, tout, False


# ── ② 机械核对:纯代码 ───────────────────────────────────────
def _norm_text(s) -> str:
    return re.sub(r"\s+", " ", str(s).lower()).strip()


def _text_match(claim_item: str, src_norm: str, src_toks: set) -> bool:
    """文本接地:规范化子串命中,或主张词被来源覆盖 >= OVERLAP_MIN。"""
    ci = _norm_text(claim_item)
    if ci and ci in src_norm:
        return True
    ct = _hit_tokens(claim_item)
    return bool(ct) and len(ct & src_toks) / len(ct) >= OVERLAP_MIN


# 主张侧日期解析:ISO(2025-01-04 / 2025-01)、英文月名(January 4th, 2025 /
# March 2025)、中文(2025年1月4日);裸年份仅在未被上述精细写法占用的位置
# 计入(否则 "January 4th, 2025" 会额外派生年粒度候选,月/日门形同虚设)。
_MONTH_MAP = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}
_ISO_RE = re.compile(r"\b(\d{4})-(\d{1,2})(?:-(\d{1,2}))?\b")
_MDY_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|"
    r"nov|dec)\.?\s+(?:(\d{1,2})(?:st|nd|rd|th)?\s*,?\s+)?(\d{4})\b",
    re.IGNORECASE)
_CJK_DATE_RE = re.compile(r"(\d{4})年(?:(\d{1,2})月)?(?:(\d{1,2})日)?")
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _parse_claim_dates(s: str) -> List[tuple]:
    """返回候选 (year, month|None, day|None) 列表;空列表 = 主张未带日期。"""
    s = str(s or "")
    cands: List[tuple] = []
    spans: List[tuple] = []
    for m in _ISO_RE.finditer(s):
        cands.append((int(m.group(1)), int(m.group(2)),
                      int(m.group(3)) if m.group(3) else None))
        spans.append(m.span())
    for m in _MDY_RE.finditer(s):
        cands.append((int(m.group(3)), _MONTH_MAP[m.group(1)[:3].lower()],
                      int(m.group(2)) if m.group(2) else None))
        spans.append(m.span())
    for m in _CJK_DATE_RE.finditer(s):
        cands.append((int(m.group(1)),
                      int(m.group(2)) if m.group(2) else None,
                      int(m.group(3)) if m.group(3) else None))
        spans.append(m.span())
    for m in _YEAR_RE.finditer(s):
        if any(a <= m.start() < b for a, b in spans):
            continue
        cands.append((int(m.group(1)), None, None))
    return cands


def _src_ymd(d) -> Optional[tuple]:
    m = re.match(r"^\s*(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", str(d or ""))
    if not m:
        return None
    return (int(m.group(1)),
            int(m.group(2)) if m.group(2) else None,
            int(m.group(3)) if m.group(3) else None)


def _date_ok(cands: List[tuple], src_date: str) -> bool:
    """按主张粒度核对:只说年 → 年相等;说到月 → 年月;说到日 → 年月日。
    主张无日期 → 不设日期关;主张带日期而来源无日期 → 无法核实,判不过。
    来源自身缺月/日的分量(部分日期卡)以来源粒度为限,不作要求。"""
    if not cands:
        return True
    s = _src_ymd(src_date)
    if s is None:
        return False
    sy, sm, sd = s
    for y, mo, d in cands:
        if y != sy:
            continue
        if mo is not None and sm is not None and mo != sm:
            continue
        if d is not None and sd is not None and d != sd:
            continue
        return True
    return False


def _session_sources(entry: dict) -> List[tuple]:
    """(kind, date, norm_text, toks) —— 每场会话一条,全 turns 拼接。"""
    out = []
    for si, sess in enumerate(entry.get("sessions", [])):
        txt = "\n".join(str(t) for t in sess.get("turns", []))
        out.append((f"session:s{si}", sess.get("date", ""),
                    _norm_text(txt), _hit_tokens(txt)))
    return out


def _card_sources(recs: List[dict], mem_dates: dict) -> List[tuple]:
    """(kind, date, norm_text, toks) —— 每卡一条:value+value_tags+source_span。"""
    out = []
    for r in recs:
        txt = " ".join([str(r.get("value", "")),
                        " ".join(r.get("value_tags") or []),
                        str(r.get("source_span", ""))])
        out.append((f"card:{r.get('record_id', '')}",
                    _rec_date(r, mem_dates), _norm_text(txt),
                    _hit_tokens(txt)))
    return out


def _ground_claim(item: str, date_str: str, srcs: List[tuple]):
    """逐来源核对一条主张;返回 (grounded, via, reason)。
    文本命中但日期全不合 → date_mismatch(列出命中来源的日期);
    文本无一命中 → not_found。"""
    cands = _parse_claim_dates(date_str)
    miss_dates: List[str] = []
    for kind, d, n, t in srcs:
        if not _text_match(item, n, t):
            continue
        if _date_ok(cands, d):
            return True, f"{kind}[{d or 'undated'}]", ""
        miss_dates.append(d or "undated")
    if miss_dates:
        return False, "", (f"date_mismatch: claimed {date_str!r}, matching "
                           "sources dated " + ", ".join(sorted(set(miss_dates))))
    return False, "", "not_found"


def _mentioned_in_answer(rec: dict, ans_norm: str, ans_toks: set) -> bool:
    """库侧召回的提及判定:卡 value 或 source_span 任一被回答覆盖即算提及。"""
    for txt in (str(rec.get("value", "")), str(rec.get("source_span", ""))):
        n = _norm_text(txt)
        if not n:
            continue
        if n in ans_norm:
            return True
        t = _hit_tokens(txt)
        if t and len(t & ans_toks) / len(t) >= OVERLAP_MIN:
            return True
    return False


def score_row(client, row: dict, entry: dict, recs: List[dict]) -> dict:
    """一行 S7 的完整打分:①抽取(一次调用)→ ②机械核对(零 LLM)。"""
    t0 = time.time()
    mem_dates = _mem_dates(entry) if entry else {}
    srcs = _session_sources(entry) + _card_sources(recs, mem_dates)

    claims, tin, tout, ok = extract_claims(
        client, row.get("question", ""), row.get("answer", ""))

    details: List[dict] = []
    hallucinated: List[dict] = []
    grounded_n = 0
    for c in claims:
        item = str(c.get("item", ""))
        dstr = str(c.get("date_or_period") or "")
        g, via, reason = _ground_claim(item, dstr, srcs)
        details.append({"item": item, "date_or_period": dstr or None,
                        "grounded": g, "via": via or None,
                        "reason": reason or None})
        if g:
            grounded_n += 1
        else:
            hallucinated.append({"item": item,
                                 "date_or_period": dstr or None,
                                 "reason": reason})
    claims_n = len(claims)
    precision = round(grounded_n / claims_n, 4) if claims_n else None

    # 库侧召回:该题所问标签下的卡片,未被回答提及者计失。
    tag = (row.get("plan") or {}).get("tag")
    ans_norm = _norm_text(row.get("answer", ""))
    ans_toks = _hit_tokens(str(row.get("answer", "")))
    tagged = _tagged(recs, tag) if tag else []
    missed: List[dict] = []
    mentioned_n = 0
    for r in tagged:
        if _mentioned_in_answer(r, ans_norm, ans_toks):
            mentioned_n += 1
        else:
            missed.append({"record_id": r.get("record_id", ""),
                           "value": r.get("value", ""),
                           "date": _rec_date(r, mem_dates)})
    recall = round(mentioned_n / len(tagged), 4) if tagged else None

    return {
        "question_id": row.get("question_id"), "uid": row.get("uid"),
        "question_type": row.get("question_type"), "tag": tag,
        "extract_ok": ok, "claims_n": claims_n, "grounded_n": grounded_n,
        "precision": precision, "claims": details,
        "hallucinated": hallucinated,
        "store_tagged_n": len(tagged), "mentioned_n": mentioned_n,
        "recall": recall, "missed": missed,
        "usage_input_tokens": tin, "usage_output_tokens": tout,
        "judge_model": MODEL, "latency_s": round(time.time() - t0, 2),
    }


# ── 主流程 ───────────────────────────────────────────────────
def _load_cards(cards_dir: str, uid: str) -> List[dict]:
    f = Path(cards_dir) / f"{uid}.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("records", [])
    except Exception:  # noqa: BLE001
        return []


def run(rows_path: str, data_paths: List[str], cards_dir: str, out_path: str,
        resume: bool):
    entries = _load_entries(data_paths)
    rows = [json.loads(l) for l in open(rows_path, encoding="utf-8")
            if l.strip()]
    s7 = [r for r in rows
          if r.get("gold_answer") is None and r.get("judge_rubric")]
    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if resume and outp.exists():
        for l in open(outp, encoding="utf-8"):
            try:
                done.add(json.loads(l)["question_id"])
            except Exception:  # noqa: BLE001
                pass
    fout = open(outp, "a" if resume else "w", encoding="utf-8")
    client = anthropic.Anthropic()
    t_start = time.time()
    scored: List[dict] = []
    tin_sum = tout_sum = 0
    for row in s7:
        qid = row.get("question_id")
        if qid in done:
            continue
        out = score_row(client, row, entries.get(row.get("uid"), {}),
                        _load_cards(cards_dir, row.get("uid", "")))
        fout.write(json.dumps(out, ensure_ascii=False) + "\n")
        fout.flush()
        scored.append(out)
        tin_sum += out["usage_input_tokens"]
        tout_sum += out["usage_output_tokens"]
        print(f"[{qid}] tag={out['tag']} claims={out['claims_n']} "
              f"grounded={out['grounded_n']} P={out['precision']} "
              f"R={out['recall']} ({out['latency_s']}s)", flush=True)
    fout.close()
    ps = [r["precision"] for r in scored if r["precision"] is not None]
    rs = [r["recall"] for r in scored if r["recall"] is not None]
    mp = f"{sum(ps) / len(ps):.4f} (n={len(ps)})" if ps else "n/a"
    mr = f"{sum(rs) / len(rs):.4f} (n={len(rs)})" if rs else "n/a"
    print(f"S7 JUDGE DONE: scored {len(scored)} rows "
          f"(skipped {len(rows) - len(s7)} non-S7, {len(done)} done); "
          f"mean precision {mp}; mean recall {mr}; "
          f"tokens in/out {tin_sum}/{tout_sum}; "
          f"elapsed {time.time() - t_start:.1f}s")


# ── 离线冒烟:桩客户端,零 API ───────────────────────────────
class _StubClient:
    """messages.parse 桩:固定返回预置主张清单,usage 记零。"""

    def __init__(self, claims: List[ClaimedItem]):
        parent = self

        class _Messages:
            def parse(self, **_kw):
                class _Usage:
                    input_tokens = 0
                    output_tokens = 0

                class _Resp:
                    parsed_output = ClaimExtraction(claims=parent._claims)
                    usage = _Usage()
                return _Resp()

        self._claims = claims
        self.messages = _Messages()


def _smoke() -> int:
    # ① 复制片段与原件逐字等价断言(等价失守即冒烟失败)。
    from qvf.engine_bridge import _hit_tokens as _eb_hit  # noqa: E402
    for s in ("I've been using a Nokia G22 for about a year.",
              "我最近在吃素食,还上了纯素烹饪课。",
              "Mixed 中英 text with a date 2025-01-04 and CJK 标签"):
        assert _hit_tokens(s) == _eb_hit(s), f"_hit_tokens 与原件不等价: {s!r}"
    from scripts.complex_query_arm import _load_entries as _cq_le  # noqa: E402
    from scripts.complex_query_arm import _mem_dates as _cq_md  # noqa: E402
    from scripts.complex_query_arm import _rec_date as _cq_rd  # noqa: E402
    from scripts.complex_query_arm import _tagged as _cq_tg  # noqa: E402

    entry = {
        "uid": "smoke-uid",
        "sessions": [{
            "date": "2025-01-04",
            "turns": [
                "{'role': 'user', 'content': \"I've been trying to eat more "
                "plant-based lately, and I recently attended a class on "
                "vegan cuisine that got me really inspired.\"}",
                "{'role': 'assistant', 'content': 'That sounds great!'}",
            ],
        }],
    }
    recs = [
        {"record_id": "r1", "source_memory_id": "smoke-uid/s0#r0",
         "source_span": "I've been trying to eat more plant-based lately",
         "value": "plant-based/vegan", "stated_date": "",
         "value_tags": ["饮食", "素食"]},
        {"record_id": "r2", "source_memory_id": "smoke-uid/s0#r1",
         "source_span": "I joined a vegetarian cooking club",
         "value": "vegetarian cooking club membership", "stated_date": "",
         "value_tags": ["素食"]},
    ]
    md = _mem_dates(entry)
    assert md == _cq_md(entry), "_mem_dates 与原件不等价"
    for r in recs:
        assert _rec_date(r, md) == _cq_rd(r, md), "_rec_date 与原件不等价"
    assert _tagged(recs, "素食") == _cq_tg(recs, "素食"), "_tagged 与原件不等价"
    assert _load_entries.__code__.co_code == _cq_le.__code__.co_code, \
        "_load_entries 与原件字节码不一致"

    # ② 日期粒度语义单元断言。
    assert _date_ok(_parse_claim_dates("January 4th, 2025"), "2025-01-04")
    assert not _date_ok(_parse_claim_dates("January 4th, 2025"), "2025-05-06")
    assert _date_ok(_parse_claim_dates("March 2025"), "2025-03-22")
    assert not _date_ok(_parse_claim_dates("March 2025"), "2025-04-02")
    assert _date_ok(_parse_claim_dates("throughout 2025"), "2025-09-12")
    assert _date_ok(_parse_claim_dates("2025年1月4日"), "2025-01-04")
    assert _date_ok(_parse_claim_dates(""), "2025-01-04")   # 无日期主张不设关
    assert not _date_ok(_parse_claim_dates("2024"), "")     # 来源无日期判不过

    # 文本命中但年份不合 → date_mismatch 归因。
    srcs = _session_sources(entry) + _card_sources(recs, md)
    g, _via, reason = _ground_claim(
        "attended a class on vegan cuisine", "2024", srcs)
    assert not g and reason.startswith("date_mismatch"), reason

    # ③ 整行打分:一真(会话可证)一假(全库无据)→ precision 0.5;
    #    标签 素食 两卡一提及一漏 → recall 0.5。
    row = {
        "question_id": "smoke_s7b", "uid": "smoke-uid",
        "question_type": "s7_subtag", "gold_answer": None,
        "question": "Have I mentioned anything 素食 (vegetarian)? "
                    "List what and when.",
        "answer": "Yes — on January 4th, 2025 you said you were eating more "
                  "plant-based and attended a vegan cuisine class. And in "
                  "March 2023 you climbed Mount Everest.",
        "plan": {"op": "tag_filter", "slot": None, "date": None,
                 "tag": "素食", "presupposed": None},
        "judge_rubric": "answer must cite only items actually present in "
                        "sessions, with dates",
    }
    stub = _StubClient([
        ClaimedItem(item="attended a class on vegan cuisine",
                    date_or_period="January 4th, 2025"),
        ClaimedItem(item="climbed Mount Everest",
                    date_or_period="March 2023"),
    ])
    out = score_row(stub, row, entry, recs)
    assert out["extract_ok"] and out["claims_n"] == 2, out
    assert out["grounded_n"] == 1 and out["precision"] == 0.5, out
    assert [h["item"] for h in out["hallucinated"]] == \
        ["climbed Mount Everest"], out["hallucinated"]
    assert out["hallucinated"][0]["reason"] == "not_found", out["hallucinated"]
    assert out["store_tagged_n"] == 2 and out["mentioned_n"] == 1, out
    assert out["recall"] == 0.5, out
    assert [m["record_id"] for m in out["missed"]] == ["r2"], out["missed"]

    print("SMOKE OK: 复制片段等价 x4;日期粒度断言 x8;"
          "一真一假整行 precision=0.5,recall=0.5,幻觉归因 not_found。")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default=None,
                    help="complex_query_arm 输出 jsonl(只取 gold_answer=null "
                    "且带 judge_rubric 的 S7 行)")
    ap.add_argument("--data", nargs="+", default=None,
                    help="一个或多个 chain 架构数据 json(供会话文本与日期)")
    ap.add_argument("--cards-dir", default=None,
                    help="标签卡片库目录(每 uid 一个 json,如 "
                    "results/wt_cards_tagged)")
    ap.add_argument("--out", default=None, help="输出 jsonl 路径")
    ap.add_argument("--resume", action="store_true",
                    help="跳过输出文件里已有 question_id 的行,追加写")
    ap.add_argument("--smoke", action="store_true",
                    help="离线冒烟(桩客户端,零 API 调用)后退出")
    a = ap.parse_args()
    if a.smoke:
        sys.exit(_smoke())
    if not (a.rows and a.data and a.cards_dir and a.out):
        ap.error("--rows/--data/--cards-dir/--out 为必填(除非 --smoke)")
    run(a.rows, a.data, a.cards_dir, a.out, a.resume)


if __name__ == "__main__":
    main()
