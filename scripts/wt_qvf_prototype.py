# -*- coding: utf-8 -*-
"""W3 原型:写入时抽取(write-time extraction)+ 读取时纯代码裁决。

动机(评审反馈):按查询全量抽取在多 gold / 建库场景下开销不可接受。
架构:抽取成本按【记忆】一次性摊销(建库),读取时仅一次微型查询聚焦调用
(~百 token)+ 确定性裁决 + 读者 —— 单查询 LLM 开销降至直读量级。
额外红利:卡片库覆盖全店,链组装直查同槽位卡片,补全扫描(及其开销)整体取消。

用法:
  python scripts/wt_qvf_prototype.py --phase write [--data ...]   # 建库(每条目 1 次抽取调用)
  python scripts/wt_qvf_prototype.py --phase read  [--data ...] --out results/wtqvf_chain_h45.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QVF_EMBED_BACKEND", "openai")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from eval.stale_chain_dataset import load_stale_chain  # noqa: E402
from qvf.engine_bridge import ExtractedRecord  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402

MODEL = "claude-haiku-4-5"
CARDS_DIR = Path("results/wt_cards")

# QVF_CARD_KEYS=1:建卡改用 V4 目录提示词,卡片额外带 owner/slot_class 规范键
# (ExtractedRecord 的对应可选字段由同名旗标在 qvf/engine_bridge.py 门控)。
# 默认 0 = 冻结行为,提示词与载荷逐字节不变。
_CARD_KEYS = int(os.environ.get("QVF_CARD_KEYS", "0") or 0)

# QVF_CARD_TAGS=1:建卡提示词追加唯一一条 value_tags 语义标签规则(闭集类目
# + 食品/健康自由子标签;ExtractedRecord 的对应可选字段由同名旗标在
# qvf/engine_bridge.py 门控)。与 QVF_CARD_KEYS 可叠加(基底自动选 V4)。
# 默认 0 = 冻结行为,提示词与载荷逐字节不变。
_CARD_TAGS = int(os.environ.get("QVF_CARD_TAGS", "0") or 0)


# ── 写入时:目录化抽取(查询无关) ──────────────────────────
class CatalogExtraction(BaseModel):
    records: List[ExtractedRecord] = Field(
        description="Every personal-state fact found in the memories."
    )


CATALOG_PROMPT = """\
You are a memory cataloger for a personal AI assistant. You will be given ALL
memory rounds of one user's history (each with memory_id, date, text). Catalog
EVERY personal-state fact (residence, job, devices, plans, memberships, habits,
providers, ...) as records.

Rules:
1. source_span must be a VERBATIM contiguous substring of that memory's text.
2. Use consistent slot names across records for the same attribute.
3. temporal_relation: 'replacement' ONLY when the text explicitly establishes a
   NEW state replacing an older record (moving/switching/upgrading language);
   'cessation' for explicit endings; 'contradiction' for incompatible values
   with no change language; else 'unresolved'. A later date alone is NOT
   replacement. Fill relation_target_record_ids accordingly.
4. stated_date: copy the date the TEXT states for the fact (YYYY[-MM[-DD]]),
   else empty. The round's own date is provided in metadata — do not copy it
   into stated_date.
5. Skip small talk with no state content. Do not invent facts.
"""


# V4(QVF_CARD_KEYS=1 时启用):在原提示词之上追加 owner/slot_class 两条
# 规范键指令;规则 1-5(含 source_span 逐字子串契约)逐字不动。
CATALOG_PROMPT_V4 = CATALOG_PROMPT + """\
6. owner: who the state belongs to — 'user' when the memory speaks in the
   first person (diary/chat voice), otherwise the person's name exactly as
   the text names them. Empty only if genuinely unclear.
7. slot_class: the normalized attribute category, EXACTLY one of:
   position | employer | team | residence | device | location |
   relationship | other:<short-noun> (e.g. other:diet). Records about the
   same real-world attribute must share the same slot_class.
"""


# TAGS 规则(QVF_CARD_TAGS=1 时启用):在所选基底提示词(有 KEYS 则 V4,
# 否则原版)之上仅追加这一条 value_tags 规则;其余指令与 source_span 逐字
# 子串契约逐字不动。编号顺延基底(原版 1-5 → 6;V4 1-7 → 8)。
_CATALOG_TAGS_RULE = """\
{n}. value_tags: for each record also output value_tags — 0-3 labels from this
   CLOSED SET (or an empty list if none apply): 饮食, 健康运动, 消费购物,
   出行旅行, 居家生活, 工作学习, 社交关系, 娱乐爱好, 财务, 宠物 — PLUS
   free-form food/health sub-tags like 高糖, 高油, 素食, 咖啡因 when the
   value is food/drink related.
"""


def _catalog_prompt() -> str:
    """当前生效的建卡提示词。两旗标全关时返回 CATALOG_PROMPT 本体(逐字节
    不变);KEYS/TAGS 各自独立门控,可叠加。"""
    base = CATALOG_PROMPT_V4 if _CARD_KEYS else CATALOG_PROMPT
    if _CARD_TAGS:
        return base + _CATALOG_TAGS_RULE.format(n=8 if _CARD_KEYS else 6)
    return base


def _client():
    return anthropic.Anthropic()


def write_phase(data_path: str, limit_items: int = 0,
                uids: Optional[List[str]] = None):
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    instances = load_stale_chain(data_path)
    by_uid = {}
    for inst in instances:  # 4 问共享同一记忆库,按条目去重
        uid = inst.memories[0].memory_id.split("/", 1)[0] if inst.memories else None
        if uid and uid not in by_uid:
            by_uid[uid] = inst
    items = list(by_uid.items())
    if uids:  # --uids 子集重建(与环境变量无关;默认 None = 全量)
        keep = set(uids)
        items = [x for x in items if x[0] in keep]
    if limit_items:
        items = items[:limit_items]
    client = _client()
    tot_in = tot_out = 0
    for uid, inst in items:
        out_f = CARDS_DIR / f"{uid}.json"
        if out_f.exists():
            continue
        payload = [{"memory_id": m.memory_id,
                    "date": (m.metadata or {}).get("session_date", ""),
                    "text": m.content} for m in inst.memories]
        # 超长条目分批建卡(≈写入时逐会话入库的真实形态):按字符预算切块,
        # 各批独立抽取后合并卡片;memory_id 全局唯一,关系边指向不受影响。
        # 卡片密度极高的内容(如逐行事实库)可用环境变量调小批预算。
        import os as _os
        CH_BUDGET = int(_os.environ.get("QVF_CATALOG_BUDGET", "320000"))
        batches, cur, cur_len = [], [], 0
        for p in payload:
            plen = len(p["text"]) + 60
            if cur and cur_len + plen > CH_BUDGET:
                batches.append(cur)
                cur, cur_len = [], 0
            cur.append(p)
            cur_len += plen
        if cur:
            batches.append(cur)
        t0 = time.time()

        def _catalog(batch, depth=0):
            """建卡一批;输出截断/解析失败时对半分批递归(卡片密度自适应)。"""
            try:
                resp = client.messages.parse(
                    model=MODEL, max_tokens=16000,
                    system=[{"type": "text",
                             "text": _catalog_prompt(),
                             "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content":
                               "MEMORY ROUNDS (JSON):\n" + json.dumps(batch, ensure_ascii=False)}],
                    output_format=CatalogExtraction,
                )
                cat = resp.parsed_output
                u = resp.usage
                recs_out = [r.model_dump() for r in (cat.records if cat else [])]
                # 大批量返回空记录=静默投降,按失败处理触发对半分批
                if not recs_out and len(batch) > 8:
                    raise ValueError("empty catalog on large batch")
                return recs_out, u.input_tokens, u.output_tokens
            except Exception as e:  # noqa: BLE001
                if len(batch) <= 1 or depth >= 4:
                    print(f"  catalog batch FAILED ({type(e).__name__}), "
                          f"{len(batch)} rounds skipped", flush=True)
                    return [], 0, 0
                mid = len(batch) // 2
                r1, i1, o1 = _catalog(batch[:mid], depth + 1)
                r2, i2, o2 = _catalog(batch[mid:], depth + 1)
                return r1 + r2, i1 + i2, o1 + o2

        recs, item_in, item_out = [], 0, 0
        for bi, batch in enumerate(batches):
            br, bi_in, bi_out = _catalog(batch)
            item_in += bi_in
            item_out += bi_out
            recs.extend(br)
        tot_in += item_in
        tot_out += item_out
        out_f.write_text(json.dumps(
            {"uid": uid, "records": recs,
             "usage_in": item_in, "usage_out": item_out},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{uid}] {len(recs)} cards ({len(batches)} batch), "
              f"in={item_in} out={item_out} ({time.time()-t0:.0f}s)", flush=True)
    print(f"WRITE PHASE TOTAL: in={tot_in} out={tot_out}")


# ── 读取时:微型聚焦 + 纯代码裁决 + 修正框定读者 ──────────────
class QueryFocusMini(BaseModel):
    entity: str = Field(description="Entity the question asks about, usually 'user'.")
    slot: str = Field(
        description="The UNDERLYING user-state attribute the question depends "
        "on, as a short CONCRETE noun phrase naming the thing whose value "
        "changes (e.g. 'phone model', 'project name', 'diet plan', "
        "'position/job', 'residence city'). NEVER an abstraction over time "
        "such as 'career progression', 'history', 'timeline', 'evolution' — "
        "for such questions name the attribute itself (e.g. 'position'). For "
        "help requests premised on some state, this is the premised "
        "attribute — NOT the topic of the requested help.")
    scope: str = Field(description="'current' | 'point_in_time' | 'trajectory' | 'unclear'")
    point_date: str = Field(default="", description="If scope=point_in_time, the asked date YYYY-MM-DD; else empty.")
    presupposed_value: str = Field(
        default="",
        description="If the question ASSERTS/presupposes a specific value for "
        "that attribute (e.g. 'Since I'm on the Xperia...' presupposes phone "
        "model = Xperia), copy that value; else empty.")


FOCUS_PROMPT = (
    "Analyze this question about a user's personal state. Identify the "
    "UNDERLYING state attribute it depends on (for help requests like 'since "
    "I'm on X, recommend...' the attribute is what X is a value of, e.g. "
    "phone model / project name / diet plan), any presupposed value, and the "
    "temporal scope: 'current' if it concerns the state now (including "
    "premised help requests); 'point_in_time' if it asks the state at a "
    "specific past date; 'trajectory' if it asks how the state changed over "
    "time; else 'unclear'."
)

READER_SYSTEM = (
    "You are the user's personal AI assistant. You will be shown excerpts "
    "from your past conversations with this user (retrieved from memory, "
    "each dated), followed by the user's new message. These excerpts have "
    "been pre-validated by an upstream memory module: they reflect the "
    "user's CURRENT, up-to-date state relevant to this message (outdated "
    "information has already been removed), and any bracketed analysis notes "
    "among them are authoritative conclusions you should follow. Reply to "
    "the new message naturally and helpfully in 1-3 sentences. Treat the "
    "excerpts as reliable facts about the user; do not say you lack the "
    "information when an excerpt or note states it."
)


def _norm(s: str) -> str:
    return " ".join(str(s).lower().replace("_", " ").replace("-", " ").split())


def _slot_match(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    aw, bw = set(a.split()), set(b.split())
    return len(aw & bw) >= max(1, min(len(aw), len(bw)) - 1) and bool(aw & bw)


def _rec_date(rec: dict, mem_dates: dict) -> str:
    return rec.get("stated_date") or mem_dates.get(rec.get("source_memory_id", ""), "")


def read_phase(data_path: str, out_path: str, limit_items: int = 0,
               item_offset: int = 0):
    from scripts.run_decisive_stale import _dense_retriever_cls  # noqa: E402

    instances = load_stale_chain(data_path)
    if limit_items or item_offset:
        keep_uids = []
        for inst in instances:
            uid = inst.memories[0].memory_id.split("/", 1)[0]
            if uid not in keep_uids:
                keep_uids.append(uid)
        end = item_offset + limit_items if limit_items else len(keep_uids)
        keep = set(keep_uids[item_offset:end])
        instances = [i for i in instances
                     if i.memories[0].memory_id.split("/", 1)[0] in keep]
    client = _client()
    judge = ClaudeJudge()
    RET = _dense_retriever_cls()
    outp = Path(out_path)
    done = set()
    if outp.exists():
        for l in open(outp, encoding="utf-8"):
            try:
                done.add(json.loads(l)["question_id"])
            except Exception:
                pass
    fout = open(outp, "a", encoding="utf-8")
    for inst in instances:
        if inst.question_id in done:
            continue
        t0 = time.time()
        uid = inst.memories[0].memory_id.split("/", 1)[0]
        cards_f = CARDS_DIR / f"{uid}.json"
        cards = json.loads(cards_f.read_text(encoding="utf-8"))["records"] if cards_f.exists() else []
        mem_by_id = {m.memory_id: m for m in inst.memories}
        mem_dates = {m.memory_id: (m.metadata or {}).get("session_date", "")
                     for m in inst.memories}

        # 1) 检索(与主协议一致)
        retriever = RET(inst.memories)
        retrieved = retriever.retrieve(inst.question, top_k=10)

        # 2) 微型查询聚焦(唯一的读取时 LLM 前置调用)
        fr = client.messages.parse(
            model=MODEL, max_tokens=500,
            system=[{"type": "text", "text": FOCUS_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"QUESTION: {inst.question}"}],
            output_format=QueryFocusMini,
        )
        qf = fr.parsed_output
        f_in, f_out = fr.usage.input_tokens, fr.usage.output_tokens

        # 3) 纯代码裁决(零 LLM)
        notes: List[str] = []
        drop_ids: set = set()
        extra_ids: List[str] = []
        # 抗污染 v3:关系链连通分量。真实状态链的卡片被抽取器用
        # replacement/cessation 关系互相链接;污染卡与链无关系边。
        # 图:节点=全库卡片;边=关系链接 ∪ 槽位模糊匹配。
        # 组件得分 = 2×内部关系边数 + 匹配查询槽位的卡数;取最高分组件。
        by_rid = {r.get("record_id"): r for r in cards if r.get("record_id")}
        parent = {}

        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        ids = [r.get("record_id") or f"idx{i}" for i, r in enumerate(cards)]
        for i, r in enumerate(cards):
            parent.setdefault(ids[i], ids[i])
        rel_edges = set()
        for i, r in enumerate(cards):
            for tgt in (r.get("relation_target_record_ids") or []):
                if tgt in by_rid:
                    union(ids[i], tgt)
                    rel_edges.add((ids[i], tgt))
        for i, r in enumerate(cards):
            for j in range(i + 1, len(cards)):
                if _slot_match(cards[i].get("slot", ""), cards[j].get("slot", "")):
                    union(ids[i], ids[j])
        comps = {}
        for i, r in enumerate(cards):
            comps.setdefault(find(ids[i]), []).append((ids[i], r))
        qslot = qf.slot if qf else ""

        def comp_score(members):
            # 槽位匹配主导(真实链靠语义归属);关系边仅作决胜
            # (累加型状态链不产生 replacement 边,反而污染闲聊常有)。
            mids = {m[0] for m in members}
            rel = sum(1 for a, b in rel_edges if a in mids and b in mids)
            slot_hits = sum(1 for _, r in members
                            if _slot_match(r.get("slot", ""), qslot))
            return 4 * slot_hits + min(rel, 3)

        cand = []
        if comps and qslot:
            best_members = max(comps.values(), key=comp_score)
            if comp_score(best_members) > 0:
                cand = [r for _, r in best_members]
        if not cand and qf and qf.presupposed_value:
            # 回退:按预设值反查卡片,借该卡的槽位重聚
            pv = _norm(qf.presupposed_value)
            pv_words = {w for w in pv.split() if len(w) > 3}
            anchor = next((r for r in cards
                           if pv and (pv in _norm(r.get("value", ""))
                                      or _norm(r.get("value", "")) in pv
                                      or (pv_words & set(_norm(r.get("value", "")).split())))),
                          None)
            if anchor:
                cand = [r for r in cards if _slot_match(r.get("slot", ""), anchor["slot"])]
        chain = sorted(cand, key=lambda r: _rec_date(r, mem_dates))
        chain = [r for r in chain if _rec_date(r, mem_dates)]
        seen_vals = []
        dedup = []
        for r in chain:
            v = _norm(r.get("value", ""))
            if v and v not in seen_vals:
                seen_vals.append(v)
                dedup.append(r)
        chain = dedup
        scope = qf.scope if qf else "unclear"
        if chain:
            latest = chain[-1]
            if scope == "point_in_time" and qf.point_date:
                valid = [r for r in chain if _rec_date(r, mem_dates) <= qf.point_date]
                if valid:
                    g = valid[-1]
                    nxt = chain[chain.index(g) + 1] if chain.index(g) + 1 < len(chain) else None
                    until = f", unchanged until {_rec_date(nxt, mem_dates)}" if nxt else ""
                    notes.append(
                        f"On {qf.point_date}, the user's {g['slot']} was "
                        f"{g['value']} (recorded {_rec_date(g, mem_dates)}{until}). "
                        f"This IS the answer; do not claim there is no information "
                        f"for that date.")
                    extra_ids.append(g.get("source_memory_id", ""))
                else:
                    notes.append(
                        f"The asked date {qf.point_date} predates every known "
                        f"state of {qf.slot}; the earliest known state is "
                        f"{chain[0]['value']} from {_rec_date(chain[0], mem_dates)}.")
            elif scope == "trajectory":
                seq = " -> ".join(
                    f"{r['value']} (from {_rec_date(r, mem_dates)})" for r in chain)
                notes.append(
                    f"Full evolution of the user's {latest['slot']}: {seq}. "
                    f"Give the complete ordered history.")
                extra_ids.extend(r.get("source_memory_id", "") for r in chain)
            else:  # current / unclear → 当前态手术
                notes.append(
                    f"The user's current {latest['slot']} is {latest['value']} "
                    f"(since {_rec_date(latest, mem_dates)}).")
                extra_ids.append(latest.get("source_memory_id", ""))
                qn = _norm(inst.question)
                qn_words = set(qn.split())
                pv = _norm(qf.presupposed_value) if qf else ""
                for r in chain[:-1]:
                    if _rec_date(r, mem_dates) < _rec_date(latest, mem_dates):
                        drop_ids.add(r.get("source_memory_id", ""))
                        v = _norm(r.get("value", ""))
                        v_words = {w for w in v.split() if len(w) > 3}
                        hit = v and (v in qn or (v_words and v_words & qn_words)
                                     or (pv and (pv in v or v in pv)))
                        if hit:
                            notes.append(
                                f"IMPORTANT: the message presupposes "
                                f"{r['value']}, which is OUTDATED — the user's "
                                f"current {latest['slot']} is {latest['value']}. "
                                f"Correct this premise before helping; do not "
                                f"give advice tailored to {r['value']}.")

        kept = [m for m in retrieved if m.memory_id not in drop_ids]
        for mid in extra_ids:
            if mid and mid in mem_by_id and all(m.memory_id != mid for m in kept):
                kept.append(mem_by_id[mid])

        # 4) 修正框定读者
        lines = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]
        for m in kept:
            d = (m.metadata or {}).get("session_date") or "undated"
            lines.append(f"[{d}] {m.content}")
        for nt in notes:
            lines.append(f"[memory-module note] {nt}")
        lines.append("")
        if inst.question_date:
            lines.append(f"TODAY'S DATE: {inst.question_date}")
            lines.append("")
        lines.append(f"USER'S NEW MESSAGE: {inst.question}")
        rr = client.messages.create(
            model=MODEL, max_tokens=1000, temperature=0.0,
            system=[{"type": "text", "text": READER_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
        answer = "".join(b.text for b in rr.content if b.type == "text")
        r_in, r_out = rr.usage.input_tokens, rr.usage.output_tokens

        v = judge.judge(inst.question, inst.gold_answer, answer,
                        inst.question_type, inst.is_abstention)
        row = {
            "question_id": inst.question_id, "mode": "wt_qvf",
            "question_type": inst.question_type, "question": inst.question,
            "gold_answer": inst.gold_answer, "answer": answer,
            "judge_correct": v.correct, "judge_reason": v.reason,
            "usage_input_tokens": f_in + r_in, "usage_output_tokens": f_out + r_out,
            "focus_tokens": f_in + f_out, "notes_n": len(notes),
            "dropped_n": len(drop_ids), "latency_s": round(time.time() - t0, 2),
            "reader_model": MODEL, "extractor_model": "write-time-cache",
        }
        fout.write(json.dumps(row, ensure_ascii=False) + "\n")
        fout.flush()
    fout.close()
    print("READ PHASE DONE")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["write", "read"], required=True)
    ap.add_argument("--data", default=r"D:\ZZL_cluade\data\stale_chain_full.json")
    ap.add_argument("--out", default=r"results\wtqvf_chain_h45.jsonl")
    ap.add_argument("--items", type=int, default=0)
    ap.add_argument("--item-offset", type=int, default=0, dest="item_offset")
    ap.add_argument("--uids", default=None,
                    help="--phase write 时:逗号分隔 uid 列表,只建这些条目的卡片")
    ap.add_argument("--cards-dir", default=None, dest="cards_dir",
                    help="覆盖卡片库目录(默认 results/wt_cards;A/B 重建时指到新目录)")
    a = ap.parse_args()
    if a.cards_dir:
        global CARDS_DIR
        CARDS_DIR = Path(a.cards_dir)
    if a.phase == "write":
        uid_list = [u for u in (a.uids or "").split(",") if u] or None
        write_phase(a.data, a.items, uid_list)
    else:
        read_phase(a.data, a.out, a.items, a.item_offset)


if __name__ == "__main__":
    main()
