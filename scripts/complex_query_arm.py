# -*- coding: utf-8 -*-
"""复杂查询编译臂(S1-S7 独立跑批器;完全不触碰冻结路由 qvf_router)。

逐题四步:
  ① COMPILE:一次 haiku 调用(模型走 qvf.config,temperature 0)把问题编译
     为小计划 —— 严格 JSON:{"op", "slot", "date", "tag", "presupposed"};
  ② EXECUTE:纯代码在键控(+标签)卡片库上执行计划。卡片解析与 qvf_router
     同口径:QVF_CARDS_KEYED 覆盖目录按 uid 先查,缺则回落 results/wt_cards;
     记录按 (owner, slot_class) 分组,聚焦槽位经 SLOT_ALIASES 归一,无键/无类
     命中回退 slot 词重叠;产出证据包(带日期条目行,上限 12 条)+ 计算结论;
  ③ READ:一次 haiku 调用,日常助手口吻(逐字节复用 framing_arm 修正框定
     基线提示词),用户内容 = 证据包条目行 + TODAY'S DATE + 问题,temperature 0;
  ④ JUDGE:qvf.judge.ClaudeJudge 与各臂同口径;gold 为 null(S7)时跳过判官,
     judge_correct=null(S7 另行按 judge_rubric 评审)。

gold 只进判官,绝不进两次 LLM 调用。

用法:
  python scripts/complex_query_arm.py --data data/wikistate_full.json [...] \
      --questions results/wsc_s5.jsonl --out results/complex_s5.jsonl --resume
  python scripts/complex_query_arm.py --data data/stale_chain_full.json \
      --out results/complex_probing.jsonl        # 缺省用条目自带 probing_queries
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Literal, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from qvf import config  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from scripts.gen_wikistate_complex import parse_partial_date  # noqa: E402
from scripts.wt_qvf_prototype import _norm, _slot_match  # noqa: E402

# 两次 LLM 调用同款小模型;qvf.config 驱动(QVF_ADAPTER_MODEL,默认 haiku-4-5,
# 与 wt_qvf_prototype / qvf_router 的 MODEL 同值)。
MODEL = config.DEFAULT_ADAPTER_MODEL
CARDS = Path(r"results/wt_cards")
# 与 qvf_router 同名同义:键控卡片覆盖目录(按 uid 先查这里,缺则回落 CARDS)。
_CARDS_KEYED = os.environ.get("QVF_CARDS_KEYED", "")

# 与 scripts/qvf_router.py 的 SLOT_ALIASES 逐字一致(复制而非导入:qvf_router
# 模块级即创建 anthropic 客户端并读聚焦缓存,独立跑批器不背这些副作用)。
SLOT_ALIASES = {
    "position": ["position", "职位", "job", "role", "chairman", "member",
                 "committee", "议员", "委员", "职务", "任职", "mayor",
                 "minister", "office"],
    "employer": ["employer", "雇主", "company", "工作", "单位", "university",
                 "institute", "works for", "employed"],
    "team": ["team", "球队", "队", "club"],
    "residence": ["residence", "住", "居住", "address", "city", "live",
                  "hometown"],
    "device": ["device", "phone", "laptop", "tablet", "camera", "手机",
               "电脑", "设备"],
    "location": ["location", "位置", "地点", "place", "where"],
    "relationship": ["relationship", "partner", "spouse", "wife", "husband",
                     "girlfriend", "boyfriend", "married", "婚", "恋", "关系"],
}

_FP_RE = re.compile(r"\b(i|me|my|mine)\b", re.IGNORECASE)
_TODAY_RE = re.compile(r"\(Today is ([0-9][0-9-]*)\.?\)")

EVIDENCE_CAP = 12    # 证据包条目行上限
_SPAN_CAP = 240      # 单条 source_span 引文长度上限(防超长行灌爆读者)

OPS = ("current", "point_in_time", "trajectory", "premise_check",
       "count_changes", "longest", "count_before", "first_last",
       "tag_filter", "tag_trend")


# ── ① COMPILE:问题 → 严格 JSON 小计划 ────────────────────────
class CompiledPlan(BaseModel):
    op: Literal["current", "point_in_time", "trajectory", "premise_check",
                "count_changes", "longest", "count_before", "first_last",
                "tag_filter", "tag_trend"] = Field(
        description="The single query operation this question compiles to.")
    slot: Optional[str] = Field(
        default=None,
        description="Concrete state attribute the question depends on "
        "(e.g. 'position', 'employer', 'residence city', 'phone model'); "
        "null for tag_filter/tag_trend.")
    date: Optional[str] = Field(
        default=None,
        description="The asked date (YYYY-MM-DD) for point_in_time / "
        "count_before; null otherwise.")
    tag: Optional[str] = Field(
        default=None,
        description="Tag label EXACTLY as the question names it (e.g. 饮食, "
        "高糖) for tag_filter/tag_trend; null otherwise.")
    presupposed: Optional[str] = Field(
        default=None,
        description="Value the question asserts/presupposes for the "
        "attribute (premise_check); null otherwise.")


COMPILE_PROMPT = """\
You compile a user's question about their own personal history into ONE
small query plan for a dated personal-state record store. Output STRICT
JSON only, exactly this object and nothing else:
{"op": "<one of: current | point_in_time | trajectory | premise_check |
count_changes | longest | count_before | first_last | tag_filter |
tag_trend>", "slot": <str|null>, "date": <str|null>, "tag": <str|null>,
"presupposed": <str|null>}

op semantics:
- current: the state now.
- point_in_time: the state at a specific past date (fill date, YYYY-MM-DD).
- trajectory: how the state changed over time (full ordered history).
- premise_check: a help request premised on some state value (fill
  presupposed with that value).
- count_changes: how many times the state changed.
- longest: which value of the state was held the longest.
- count_before: how many different values the state had before a date
  (fill date).
- first_last: the first value and the most recent value.
- tag_filter: list everything mentioned that matches a semantic tag
  (fill tag).
- tag_trend: what was mentioned under a tag category and whether it
  changed over time (fill tag).

Field rules: slot is a short concrete attribute noun phrase, never an
abstraction like 'history' or 'timeline'; tag is copied verbatim from the
question; unused fields are null.

Examples:
Q: (Today is 2007-01-22.) How many times did I change my position?
A: {"op": "count_changes", "slot": "position", "date": null, "tag": null, "presupposed": null}
Q: How many different employer values did I have before 2001-05-14?
A: {"op": "count_before", "slot": "employer", "date": "2001-05-14", "tag": null, "presupposed": null}
Q: Looking across everything I've told you, what have I mentioned in the 饮食 (diet/food) category, and has anything about my eating changed over time?
A: {"op": "tag_trend", "slot": null, "date": null, "tag": "饮食", "presupposed": null}
Q: Have I mentioned anything 高糖 (high-sugar)? List what and when.
A: {"op": "tag_filter", "slot": null, "date": null, "tag": "高糖", "presupposed": null}
"""


# ── ③ READ:日常助手读者(逐字节复用 framing_arm 修正框定基线) ──
READER_SYSTEM = (
    "You are the user's personal AI assistant. You will be shown excerpts "
    "from your past conversations with this user (retrieved from memory, "
    "each dated), followed by the user's new message. Reply to the new "
    "message naturally and helpfully in 1-3 sentences, as you would in an "
    "everyday chat."
)


def _client():
    return anthropic.Anthropic()


def compile_plan(client, question: str):
    """一次 haiku 编译调用(重试 3 次);返回 (plan_dict, in_tok, out_tok, ok)。
    全部失败时回落 op=current 的空计划(ok=False),流程不中断。"""
    tin = tout = 0
    for _ in range(3):
        try:
            resp = client.messages.parse(
                model=MODEL, max_tokens=400, temperature=0.0,
                system=[{"type": "text", "text": COMPILE_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": question}],
                output_format=CompiledPlan,
            )
            tin += resp.usage.input_tokens
            tout += resp.usage.output_tokens
            p = resp.parsed_output
            if p:
                return p.model_dump(), tin, tout, True
        except Exception:  # noqa: BLE001
            continue
    return ({"op": "current", "slot": None, "date": None, "tag": None,
             "presupposed": None}, tin, tout, False)


# ── ② EXECUTE:纯代码执行计划 ────────────────────────────────
def _card_file(uid: str) -> Path:
    """与 qvf_router._card_file 同口径:覆盖目录优先,回落 CARDS。"""
    if _CARDS_KEYED:
        p = Path(_CARDS_KEYED) / f"{uid}.json"
        if p.exists():
            return p
    return CARDS / f"{uid}.json"


def _load_records(uid: str) -> List[dict]:
    f = _card_file(uid)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("records", [])
    except Exception:  # noqa: BLE001
        return []


def _rec_date(rec: dict, mem_dates: dict) -> str:
    return rec.get("stated_date") or mem_dates.get(
        rec.get("source_memory_id", ""), "")


def _pdate(s: str):
    """部分日期解析(与 S5 gold 生成器同一规约函数);失败返回 None。"""
    try:
        return parse_partial_date(str(s))[0]
    except Exception:  # noqa: BLE001
        return None


def _select_pool(recs: List[dict], slot: str, mem_dates: dict,
                 question: str = "") -> List[dict]:
    """槽位记录池:键控优先((owner, slot_class) 分组 + SLOT_ALIASES 归一,
    取带日期不同值数最多的组 —— 与路由键控链深同精神);无键卡片/无类命中
    回退 slot 词重叠(_slot_match)。一人称问题且卡片带 owner 时限定
    owner∈{"", "user"}(与 qvf_router._keyed_depth 同规则)。"""
    fs = _norm(slot or "")
    matched = [c for c, al in SLOT_ALIASES.items() if any(a in fs for a in al)]
    keyed = [r for r in recs if r.get("slot_class")]
    first_person = (not question or _FP_RE.search(question)
                    or "我" in question)
    if keyed and matched:
        kp = keyed
        if first_person and any(r.get("owner") for r in keyed):
            kp = [r for r in keyed if (r.get("owner") or "") in ("", "user")]
        groups: dict = {}
        for r in kp:
            cls = r.get("slot_class", "")
            if cls in matched and _norm(r.get("value", "")):
                groups.setdefault(((r.get("owner") or ""), cls), []).append(r)
        if groups:
            def depth(g):
                return len({_norm(r.get("value", "")) for r in g
                            if _rec_date(r, mem_dates)})
            pool = max(groups.values(), key=depth)
            return sorted(pool, key=lambda r: _rec_date(r, mem_dates))
    pool = [r for r in recs if _slot_match(r.get("slot", ""), slot or "")]
    return sorted(pool, key=lambda r: _rec_date(r, mem_dates))


def _chain(pool: List[dict], mem_dates: dict) -> List[dict]:
    """带日期、相邻去重的有序状态链(相邻同值 = 同一状态延续,合并;
    非相邻重现视为再次变更 —— 与 S5 gold 的逐转移计数口径一致)。"""
    out: List[dict] = []
    for r in pool:
        d = _rec_date(r, mem_dates)
        v = _norm(r.get("value", ""))
        if not d or not v:
            continue
        if out and _norm(out[-1].get("value", "")) == v:
            continue
        out.append(r)
    return out


def _label(rec: dict) -> str:
    return rec.get("slot_class") or rec.get("slot", "") or "state"


def _line(rec: dict, mem_dates: dict) -> str:
    span = str(rec.get("source_span", ""))
    if len(span) > _SPAN_CAP:
        span = span[:_SPAN_CAP] + " ...[truncated]"
    return (f"[{_rec_date(rec, mem_dates) or 'undated'}] "
            f"{_label(rec)}: {rec.get('value', '')} — \"{span}\"")


def _tagged(recs: List[dict], tag: str) -> List[dict]:
    t = (tag or "").strip()
    return [r for r in recs
            if any((x or "").strip() == t for x in (r.get("value_tags") or []))]


_COUNT_OPS = {"count_changes", "count_before", "first_last", "longest"}
_DATEPHRASE_RE = re.compile(
    r"\b\d+\s+(months?|weeks?|years?|days?)\b|\b(before|after|ago)\b",
    re.IGNORECASE)


def _hygiene_pool(pool: List[dict]) -> List[dict]:
    """计数类算子的池清洗(dev 迭代 1):
    ①值为日期短语的碎卡剔除(如 '6 months before 1980-02-12'——同一宣告句
    被拆出的时间描述,不是状态值);②同一来源会话只保留一张卡(一句话至多
    宣告一个状态;优先带日期、其次值更长的那张)。点查/轨迹算子不经此路,
    保持原语义。"""
    kept = [r for r in pool
            if not _DATEPHRASE_RE.search(str(r.get("value", "")))]
    by_mem: dict = {}
    order: List[str] = []
    for r in kept:
        m = str(r.get("source_memory_id", "")) or f"_r{id(r)}"
        if m not in by_mem:
            by_mem[m] = r
            order.append(m)
        else:
            cur = by_mem[m]
            better = ((bool(r.get("stated_date")), len(str(r.get("value", ""))))
                      > (bool(cur.get("stated_date")),
                         len(str(cur.get("value", "")))))
            if better:
                by_mem[m] = r
    return [by_mem[m] for m in order]


def execute_plan(plan: dict, recs: List[dict], mem_dates: dict,
                 question: str = ""):
    """执行小计划;返回 (证据行 ≤EVIDENCE_CAP, 计算结论行)。零 LLM。"""
    op = plan.get("op") or "current"
    slot = plan.get("slot") or ""
    ev: List[str] = []
    derived: List[str] = []

    if op in ("tag_filter", "tag_trend"):
        tag = plan.get("tag") or ""
        hits = sorted(_tagged(recs, tag),
                      key=lambda r: _rec_date(r, mem_dates))
        ev = [_line(r, mem_dates) for r in hits]
        if not hits:
            derived.append(f"No stored item carries the tag {tag}.")
        elif op == "tag_filter":
            derived.append(
                f"{len(hits)} stored item(s) carry the tag {tag}; every one "
                f"is listed above with its date.")
        else:  # tag_trend:按年分组的演变
            by_year: dict = {}
            for r in hits:
                y = (_rec_date(r, mem_dates) or "undated")[:4]
                by_year.setdefault(y, []).append(str(r.get("value", "")))
            seq = "; ".join(f"{y}: " + ", ".join(vs)
                            for y, vs in sorted(by_year.items()))
            derived.append(
                f"Items tagged {tag} by year — {seq}. Describe what was "
                f"mentioned and how it evolved, citing only these items "
                f"with their dates.")
        return ev[:EVIDENCE_CAP], derived

    pool = _select_pool(recs, slot, mem_dates, question)
    if op in _COUNT_OPS:
        pool = _hygiene_pool(pool)
    chain = _chain(pool, mem_dates)
    ev = [_line(r, mem_dates) for r in chain]
    if not chain:
        derived.append("No dated record found for "
                       f"{slot or 'the asked attribute'} in memory.")
        return ev[:EVIDENCE_CAP], derived
    label = _label(chain[-1])
    dates = [_rec_date(r, mem_dates) for r in chain]
    values = [str(r.get("value", "")) for r in chain]

    if op in ("current", "premise_check"):
        derived.append(f"The user's current {label} is {values[-1]} "
                       f"(since {dates[-1]}).")
        pv = _norm(plan.get("presupposed") or "")
        if op == "premise_check" and pv:
            stale = next(
                (r for r in chain[:-1]
                 if pv in _norm(r.get("value", ""))
                 or _norm(r.get("value", "")) in pv), None)
            if stale is not None:
                derived.append(
                    f"IMPORTANT: the message presupposes "
                    f"{stale.get('value', '')}, which is OUTDATED — the "
                    f"user's current {label} is {values[-1]}. Correct this "
                    f"premise before helping.")
    elif op == "point_in_time":
        qd = _pdate(plan.get("date") or "")
        parsed = [_pdate(d) for d in dates]
        gi = None
        for i, pd in enumerate(parsed):
            if pd is not None and qd is not None and pd <= qd:
                gi = i
        if qd is None or gi is None:
            derived.append(
                f"The asked date predates every known state of {label}; the "
                f"earliest known state is {values[0]} from {dates[0]}.")
        else:
            until = (f", unchanged until {dates[gi + 1]}"
                     if gi + 1 < len(chain) else "")
            derived.append(
                f"On {plan.get('date')}, the user's {label} was {values[gi]} "
                f"(recorded {dates[gi]}{until}). This IS the answer.")
    elif op == "trajectory":
        seq = " -> ".join(f"{v} (from {d})" for v, d in zip(values, dates))
        derived.append(f"Full evolution of the user's {label}: {seq}. "
                       f"Give the complete ordered history.")
    elif op == "count_changes":
        n = len(chain) - 1
        derived.append(
            f"The user's {label} changed {n} time(s) — {len(chain)} "
            f"successive states: " + " -> ".join(values) + ".")
    elif op == "longest":
        # 与 gen_wikistate_complex S5a 同口径:仅闭区间,同值多段按值累加。
        per_value: dict = {}
        parsed = [_pdate(d) for d in dates]
        for i in range(len(chain) - 1):
            if parsed[i] is not None and parsed[i + 1] is not None:
                per_value[values[i]] = (per_value.get(values[i], 0)
                                        + (parsed[i + 1] - parsed[i]).days)
        if per_value:
            best = max(per_value.values())
            winners = [v for v, d in per_value.items() if d == best]
            derived.append(
                f"Held longest (closed intervals only): {winners[0]} "
                f"({best} days). Closed days per value: "
                + json.dumps(per_value, ensure_ascii=False) + ".")
        else:
            derived.append(
                f"Only one dated state of {label} is known "
                f"({values[-1]} since {dates[-1]}); no closed interval to "
                f"compare.")
    elif op == "count_before":
        qd = _pdate(plan.get("date") or "")
        before = [v for v, d in zip(values, dates)
                  if qd is not None and _pdate(d) is not None
                  and _pdate(d) < qd]
        distinct = sorted(set(before), key=before.index)
        derived.append(
            f"Before {plan.get('date')}, the user had {len(distinct)} "
            f"different {label} value(s): " + (", ".join(distinct) or "none")
            + ".")
    elif op == "first_last":
        derived.append(
            f"First {label}: {values[0]} (from {dates[0]}); most recent: "
            f"{values[-1]} (since {dates[-1]}).")
    return ev[:EVIDENCE_CAP], derived


# ── ③ READ:证据包 → 日常口吻回答 ────────────────────────────
def reader_content(ev: List[str], derived: List[str], qdate: str,
                   question: str) -> str:
    lines = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]
    lines += ev or ["(no matching records found in memory)"]
    for d in derived:
        lines.append(f"[memory summary] {d}")
    lines.append("")
    if qdate:
        lines.append(f"TODAY'S DATE: {qdate}")
        lines.append("")
    lines.append(f"USER'S NEW MESSAGE: {question}")
    return "\n".join(lines)


# ── 题目装配 ─────────────────────────────────────────────────
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


def _query_date(entry: dict, question: str) -> str:
    """TODAY'S DATE:问题自带 (Today is X.) 前缀则用 X(S5/wiki 卷);否则
    末链日期 +1 月(与 eval.stale_chain_dataset.load_stale_chain 同算式)。"""
    m = _TODAY_RE.search(question or "")
    if m:
        return m.group(1)
    try:
        last = str(entry["chain"][-1]["date"])
        y, mo, d = (int(x) for x in last.split("-"))
        mo += 1
        if mo > 12:
            y, mo = y + 1, 1
        return f"{y}-{mo:02d}-{d:02d}"
    except Exception:  # noqa: BLE001
        return ""


def _questions_from_jsonl(path: str) -> List[dict]:
    """gen_wikistate_complex 输出行:uid/qid/qtype/question/gold
    (S7 额外带 judge_rubric,gold=null)。"""
    out = []
    for l in open(path, encoding="utf-8"):
        s = l.strip()
        if s:
            out.append(json.loads(s))
    return out


def _questions_from_probing(entries: dict) -> List[dict]:
    """缺省题源:条目自带 probing_queries(dim1/2/4/5 四维混合)。"""
    out = []
    for uid, e in entries.items():
        for dim, q in (e.get("probing_queries") or {}).items():
            out.append({"uid": uid, "qid": f"{uid}_{dim}",
                        "qtype": f"chain-{dim}", "question": q["q"],
                        "gold": q.get("gold")})
    return out


# ── 主流程 ───────────────────────────────────────────────────
def run(data_paths: List[str], questions_path: Optional[str], out_path: str,
        uids: Optional[List[str]], resume: bool):
    entries = _load_entries(data_paths)
    qs = (_questions_from_jsonl(questions_path) if questions_path
          else _questions_from_probing(entries))
    if uids:
        keep = set(uids)
        qs = [q for q in qs if q["uid"] in keep]
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
    client = _client()
    judge = ClaudeJudge()
    md_cache: dict = {}
    n_run = n_ok = n_null = 0
    for q in qs:
        qid, uid = q["qid"], q["uid"]
        if qid in done:
            continue
        t0 = time.time()
        entry = entries.get(uid, {})
        if uid not in md_cache:
            md_cache[uid] = _mem_dates(entry)
        mem_dates = md_cache[uid]

        # ① 编译(只见问题)
        plan, c_in, c_out, ok = compile_plan(client, q["question"])
        # ② 纯代码执行
        ev, derived = execute_plan(plan, _load_records(uid), mem_dates,
                                   q["question"])
        # ③ 读者(只见证据包 + 日期 + 问题)
        qdate = _query_date(entry, q["question"])
        rr = client.messages.create(
            model=MODEL, max_tokens=1000, temperature=0.0,
            system=[{"type": "text", "text": READER_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": reader_content(ev, derived, qdate,
                                                 q["question"])}],
        )
        answer = "".join(b.text for b in rr.content if b.type == "text")

        # ④ 判官(gold 仅在此出现;S7 gold=null 跳过,另行评审)
        gold = q.get("gold")
        if gold is None:
            jc, jr = None, "gold=null (S7): judged separately via rubric"
            n_null += 1
        else:
            v = judge.judge(q["question"], str(gold), answer, q.get("qtype"))
            jc, jr = v.correct, v.reason
            n_ok += bool(jc)

        row = {
            "question_id": qid, "mode": "complex_arm", "uid": uid,
            "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": gold, "answer": answer,
            "plan": plan, "compile_ok": ok, "evidence_n": len(ev),
            "usage_input_tokens": c_in + rr.usage.input_tokens,
            "usage_output_tokens": c_out + rr.usage.output_tokens,
            "judge_correct": jc, "judge_reason": jr,
            "reader_model": MODEL, "latency_s": round(time.time() - t0, 2),
        }
        if q.get("judge_rubric"):
            row["judge_rubric"] = q["judge_rubric"]
        fout.write(json.dumps(row, ensure_ascii=False) + "\n")
        fout.flush()
        n_run += 1
        print(f"[{qid}] op={plan.get('op')} ev={len(ev)} "
              f"judge={jc} ({time.time() - t0:.1f}s)", flush=True)
    fout.close()
    n_judged = n_run - n_null
    acc = f"{n_ok}/{n_judged} = {n_ok / n_judged * 100:.1f}%" if n_judged \
        else "n/a"
    print(f"COMPLEX ARM DONE: ran {n_run} (skipped {len(done)} done); "
          f"judged {n_judged}, correct {acc}; gold=null {n_null}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True,
                    help="一个或多个 chain 架构数据 json(供会话日期/缺省题源)")
    ap.add_argument("--questions", default=None,
                    help="gen_wikistate_complex 输出 jsonl;缺省用条目自带 "
                    "probing_queries")
    ap.add_argument("--out", required=True, help="输出 jsonl 路径")
    ap.add_argument("--uids", default=None,
                    help="逗号分隔 uid 列表,只跑这些条目(默认全量)")
    ap.add_argument("--resume", action="store_true",
                    help="跳过输出文件里已有 question_id 的题,追加写")
    a = ap.parse_args()
    uid_list = [u for u in (a.uids or "").split(",") if u] or None
    run(a.data, a.questions, a.out, uid_list, a.resume)


if __name__ == "__main__":
    main()
