# -*- coding: utf-8 -*-
"""scripts/write_persession.py — 建卡两层拆分:逐会话独立抽取 + 纯代码装配。

动机(实测,B4/B6,见任务纪律文档):现行 wt_qvf_prototype.write_phase 把整库
所有会话打包成一次 LLM 调用,模型看得见会话呈现顺序,顺序信息因此可能泄漏进
抽取输出(同链顺序建卡/乱序建卡产出不同槽位标签,或整条漏抽)。B6 同契约重
建 3 次精确匹配率方差 ±20pp(78.0/68.0/64.0%)。

架构:
  抽取层(LLM,逐会话独立,本文件 extract_session):每个会话单独一次调用,
    彼此不可见;只回答"这个会话说了什么个人状态",产出【未连边】记录
    (无 record_id、无 relation_target_record_ids)。冻结契约(wt_qvf_prototype.
    CATALOG_PROMPT_V4)基础上删去两条依赖全局视野的规则:
      - 原 Rule 2 "Use consistent slot names across records"(单会话看不到
        其它会话,无法保证一致);
      - 原 Rule 3 的 "Fill relation_target_record_ids accordingly"(单会话
        不知道其它会话产出的 record_id)。
    其余规则(source_span 逐字子串、temporal_relation 分类、stated_date、
    跳过闲聊、owner、slot_class)逐字保留(见 PERSESSION_PROMPT 内联对照)。
    新增一条:slot_cardinality 在 schema 层收紧为 {single,set} 两值(去掉
    "unknown" 逃逸项),强制模型每条记录都给出明确判断 —— 该字段旧 schema
    (qvf/engine_bridge.ExtractedRecord)本就存在但读取侧从不消费(08-16 讲
    解发现);本任务先把它填准,消费与否留后续。

  装配层(纯代码,零 LLM,assemble()):按 (owner, slot_class) 分组 → 组内
    按日期排序 → 推导 temporal_relation 的 relation_target_record_ids(链式:
    每条记录的目标是同组按日期排序的前一条,仅当该记录自身 temporal_relation
    ∈ {replacement, correction, cessation, contradiction} 时才连边;
    slot_cardinality=set 的组不连边,视为并存集合)→ 槽位名归一(组内出现
    频次最高的原始大小写文本,频次并列按归一化字符串字典序决胜;归一化/排序
    /计数全部对输入列表顺序不敏感,保证判据④装配确定性)。record_id 由内容
    派生的稳定哈希(owner+slot_class+entity+slot+value+stated_date+
    source_memory_id+source_span+condition 的 sha256 前 16 位),不含任何
    输入顺序信息;内容完全相同的重复记录自然合并去重。

纪律:
  - 冻结代码只读:scripts/wt_qvf_prototype.py(write_phase/CATALOG_PROMPT 系
    列)、scripts/complex_query_arm.py、scripts/qvf_router.py、qvf/
    engine_bridge.py 本文件一字不改、不 import 其可变状态。
  - 新路径需显式开启环境变量 QVF_WRITE_PERSESSION=1 才允许运行(未设置时
    main() 直接拒绝退出)——旗标只作用于本文件自身,不触碰
    wt_qvf_prototype.py 的执行路径,后者在旗标关/开两种状态下字节不变
    (可用 git diff 验证,见任务阶段一步骤4)。

用法:
  QVF_WRITE_PERSESSION=1 python scripts/write_persession.py \
      --data data/wikistate_full_P551.json --uids wikiP551002-Q107297 \
      --cards-dir results/wt_cards_persession
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QVF_EMBED_BACKEND", "openai")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from typing import Literal  # noqa: E402

from eval.stale_chain_dataset import load_stale_chain  # noqa: E402

MODEL = "claude-haiku-4-5"
CARDS_DIR_DEFAULT = Path("results/wt_cards_persession")

_WRITE_PERSESSION = int(os.environ.get("QVF_WRITE_PERSESSION", "0") or 0)


# ── 抽取层 schema(逐会话,未连边)───────────────────────────
class SessionRecord(BaseModel):
    entity: str = Field(description="Entity of the fact, e.g. 'user'.")
    slot: str = Field(description="Slot name for this attribute (free text; "
                       "canonicalized later by the assembly layer — no need "
                       "to match other sessions' wording).")
    value: str = Field(description="The slot value stated by this span.")
    claim: str = Field(description="One-sentence normalized statement of the fact.")
    slot_cardinality: Literal["single", "set"] = Field(
        description="'single' if this slot can hold only ONE value at a time "
        "for this entity (e.g. home city, employer, team — a new value "
        "replaces the old one); 'set' if multiple values normally coexist "
        "(e.g. hobbies, skills, devices owned). Always pick one — do not "
        "leave this ambiguous; use domain knowledge about the attribute."
    )
    temporal_relation: Literal[
        "replacement", "correction", "equivalent", "additive", "unresolved",
        "contradiction", "cessation"
    ] = Field(
        description="Relation of this record to the entity's PRIOR state for "
        "the same slot, judged from THIS session's text alone: 'replacement' "
        "only if this memory explicitly establishes a NEW state replacing an "
        "older one (moving/switching/upgrading language); 'cessation' if it "
        "explicitly ENDS the state without a new value (quit, canceled, no "
        "longer, stopped); 'contradiction' if the text asserts a value that "
        "conflicts with common sense/earlier framing with NO change language; "
        "'unresolved' when in doubt. A later timestamp alone is NOT "
        "replacement. You will NOT be shown other sessions or their record "
        "ids — just classify this session's own language; the assembly step "
        "resolves which prior record(s) this points to."
    )
    condition: str = Field(
        default="",
        description="If this value applies only under an explicit condition "
        "or context (at work, on weekends, when traveling ...), state it "
        "briefly; empty string otherwise.",
    )
    implies_stale_slots: List[str] = Field(
        default_factory=list,
        description="Slot names of OTHER attributes this update makes stale "
        "via a common-sense dependency. Empty if none.",
    )
    stated_date: str = Field(
        default="",
        description="When the TEXT ITSELF states when this state began or "
        "held (a year, month or date in the span or its sentence), copy it "
        "as YYYY, YYYY-MM or YYYY-MM-DD. For ranges use the START. Empty if "
        "the text states no date.",
    )
    source_span: str = Field(
        description="VERBATIM contiguous substring of this session's text "
        "stating the fact. Copy exactly — any paraphrase invalidates the "
        "record."
    )
    owner: str = Field(
        default="",
        description="Who this state belongs to: 'user' when the text speaks "
        "in the first person (diary/chat voice), otherwise the person's name "
        "exactly as the text names them. Empty only if genuinely unclear.",
    )
    slot_class: str = Field(
        default="",
        description="Normalized attribute category, EXACTLY one of: "
        "position | employer | team | residence | device | location | "
        "relationship | other:<short-noun> (e.g. other:diet).",
    )


class SessionExtraction(BaseModel):
    records: List[SessionRecord] = Field(
        description="Every personal-state fact found in THIS memory round. "
        "Empty list if none."
    )


# PERSESSION_PROMPT — 对照 wt_qvf_prototype.CATALOG_PROMPT_V4 的逐条注记:
#   header: "ALL memory rounds ... history" -> "ONE memory round (session)"
#           (单会话调用,不再整库打包)
#   Rule 1 (source_span 逐字子串)         — 逐字保留,原 Rule 1
#   Rule 2 (consistent slot names)         — 删除(依赖全局视野)
#   Rule 3 (temporal_relation 分类)        — 保留分类语言;删除末句
#           "Fill relation_target_record_ids accordingly."(装配层代做)
#   Rule 4 (stated_date)                   — 逐字保留,原 Rule 4
#   Rule 5 (跳过闲聊/不编造)               — 逐字保留,原 Rule 5
#   Rule 6 (owner)                         — 逐字保留,原 V4 Rule 6
#   Rule 7 (slot_class)                    — 逐字保留,原 V4 Rule 7(末句
#           "Records about the same real-world attribute must share the same
#           slot_class" 删除——单会话看不到同实体的其它记录,无法自证一致;
#           slot_class 本身的取值口径不变)
#   Rule 8 (slot_cardinality 明确化)       — 新增(见模块 docstring)
PERSESSION_PROMPT = """\
You are a memory cataloger for a personal AI assistant. You will be given ONE
memory round (session) of one user's history (memory_id, date, text). Catalog
EVERY personal-state fact (residence, job, devices, plans, memberships, habits,
providers, ...) as records.

Rules:
1. source_span must be a VERBATIM contiguous substring of that memory's text.
2. temporal_relation: 'replacement' ONLY when the text explicitly establishes a
   NEW state replacing an older record (moving/switching/upgrading language);
   'cessation' for explicit endings; 'contradiction' for incompatible values
   with no change language; else 'unresolved'. A later date alone is NOT
   replacement.
3. stated_date: copy the date the TEXT states for the fact (YYYY[-MM[-DD]]),
   else empty. The round's own date is provided in metadata — do not copy it
   into stated_date.
4. Skip small talk with no state content. Do not invent facts.
5. owner: who the state belongs to — 'user' when the memory speaks in the
   first person (diary/chat voice), otherwise the person's name exactly as
   the text names them. Empty only if genuinely unclear.
6. slot_class: the normalized attribute category, EXACTLY one of:
   position | employer | team | residence | device | location |
   relationship | other:<short-noun> (e.g. other:diet).
7. slot_cardinality: state explicitly whether this attribute is single-valued
   (single) or multi-valued (set) for this entity — never leave it unclear.
"""


def _client():
    return anthropic.Anthropic()


def extract_session(client: "anthropic.Anthropic", memory_id: str, date: str,
                     text: str) -> Tuple[List[dict], int, int]:
    """单会话抽取一次调用。返回 (未连边记录列表, input_tokens, output_tokens)。
    source_memory_id 由代码注入(单会话内无歧义,不必让模型猜),省一份 token。
    """
    payload = {"memory_id": memory_id, "date": date, "text": text}
    resp = client.messages.parse(
        model=MODEL, max_tokens=4000,
        system=[{"type": "text", "text": PERSESSION_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content":
                   "MEMORY ROUND (JSON):\n" + json.dumps(payload, ensure_ascii=False)}],
        output_format=SessionExtraction,
    )
    ext = resp.parsed_output
    u = resp.usage
    recs = []
    for r in (ext.records if ext else []):
        d = r.model_dump()
        d["source_memory_id"] = memory_id
        d["_session_date"] = date  # 代码侧留痕,装配层日期回退用;非模型字段
        recs.append(d)
    return recs, u.input_tokens, u.output_tokens


# ── 装配层(纯代码,零 LLM)────────────────────────────────
def _record_id(rec: dict) -> str:
    """内容派生的稳定哈希:仅取内容字段,不含记录在列表中的位置/输入顺序。"""
    basis = "\x1f".join([
        rec.get("owner", "") or "",
        rec.get("slot_class", "") or "",
        rec.get("entity", "") or "",
        rec.get("slot", "") or "",
        rec.get("value", "") or "",
        rec.get("stated_date", "") or "",
        rec.get("source_memory_id", "") or "",
        rec.get("source_span", "") or "",
        rec.get("condition", "") or "",
    ])
    h = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return f"r_{h}"


def _norm_slot_text(s: str) -> str:
    return " ".join(str(s).lower().replace("_", " ").replace("-", " ").split())


def _canonical_slot(members: List[dict]) -> str:
    """组内出现频次最高的原始文本;频次并列按归一化字符串字典序决胜。
    Counter/sorted 均对输入顺序不敏感 —— 与判据④(装配确定性)要求一致。"""
    norm_counts: Counter = Counter()
    reps: Dict[str, str] = {}
    for r in members:
        s = (r.get("slot") or "").strip()
        if not s:
            continue
        n = _norm_slot_text(s)
        norm_counts[n] += 1
        if n not in reps or s < reps[n]:
            reps[n] = s
    if not norm_counts:
        return ""
    best_norm = sorted(norm_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return reps[best_norm]


def _date_key(d: str) -> Tuple[int, str]:
    """(has_date, padded YYYY-MM-DD) 排序键;空日期排最后。全部纯字符串运算,
    对输入顺序不敏感。"""
    if not d:
        return (1, "9999-99-99")
    parts = str(d).split("-")
    y = (parts[0] or "0000").zfill(4)
    m = (parts[1].zfill(2) if len(parts) > 1 and parts[1] else "01")
    day = (parts[2].zfill(2) if len(parts) > 2 and parts[2] else "01")
    return (0, f"{y}-{m}-{day}")


def _cardinality_for_group(members: List[dict]) -> str:
    c = Counter(r.get("slot_cardinality", "single") for r in members)
    n_single = c.get("single", 0)
    n_set = c.get("set", 0)
    return "single" if n_single >= n_set else "set"


def assemble(records: List[dict]) -> List[dict]:
    """未连边记录 -> 装配后卡片列表。纯代码,零 LLM,对输入列表顺序不敏感
    (判据④:打乱输入 >=1000 次输出逐字节相同)。

    步骤:
      1. 逐条计算内容派生 record_id;完全同内容的重复记录去重(取一份)。
      2. 按 (owner, slot_class) 分组。
      3. 组内槽位名归一(见 _canonical_slot),覆盖写回 slot 字段(保留原文
         于 slot_raw,便于审计)。
      4. 组内按日期排序(_date_key,并列按 record_id 决胜)。
      5. 组的 slot_cardinality 取多数票;set 组不连边(值并存);single/多数
         组内链式连边:每条记录(排除组内第一条)若自身 temporal_relation
         属于 {replacement, correction, cessation, contradiction},则
         relation_target_record_ids = [同组按日期排序的前一条的 record_id]。
      6. 全表按 (owner, slot_class, date_key, record_id) 排序输出,保证列表
         级别的呈现顺序同样是内容的确定性函数。
    """
    seen: Dict[str, dict] = {}
    for r in records:
        rid = _record_id(r)
        if rid not in seen:
            rr = dict(r)
            rr["record_id"] = rid
            rr["slot_raw"] = r.get("slot", "")
            rr.pop("_session_date", None)
            # 日期回退:stated_date 优先,否则会话日期(代码侧已在抽取层附着)
            if not rr.get("stated_date"):
                rr["stated_date_effective"] = r.get("_session_date", "")
            else:
                rr["stated_date_effective"] = rr["stated_date"]
            rr["relation_target_record_ids"] = []
            seen[rid] = rr
    all_recs = list(seen.values())

    groups: Dict[Tuple[str, str], List[dict]] = {}
    for r in all_recs:
        key = ((r.get("owner") or "").strip(), (r.get("slot_class") or "").strip())
        groups.setdefault(key, []).append(r)

    out: List[dict] = []
    for key in sorted(groups.keys()):
        members = groups[key]
        canon_slot = _canonical_slot(members)
        for r in members:
            r["slot"] = canon_slot or r.get("slot", "")
        ordered = sorted(
            members,
            key=lambda r: (_date_key(r.get("stated_date_effective", "")), r["record_id"]),
        )
        cardinality = _cardinality_for_group(members)
        if cardinality != "set":
            prev_id = None
            for i, r in enumerate(ordered):
                if i > 0 and r.get("temporal_relation") in (
                    "replacement", "correction", "cessation", "contradiction"
                ):
                    r["relation_target_record_ids"] = [prev_id]
                prev_id = r["record_id"]
        out.extend(ordered)

    out.sort(key=lambda r: (
        (r.get("owner") or "").strip(),
        (r.get("slot_class") or "").strip(),
        _date_key(r.get("stated_date_effective", "")),
        r["record_id"],
    ))
    return out


def canonical_json(cards: List[dict]) -> str:
    """判据④用的稳定序列化:key 排序 + 无 ensure_ascii,列表顺序本身已由
    assemble() 保证是内容的确定性函数,这里只需保证同一 dict 的 key 顺序
    不受 dict 构造顺序影响。"""
    return json.dumps(cards, ensure_ascii=False, sort_keys=True, indent=None)


# ── 建卡入口(逐库逐 uid)──────────────────────────────────
def write_phase(data_path: str, uids: Optional[List[str]] = None,
                 cards_dir: Optional[Path] = None,
                 limit_items: int = 0, max_sessions: int = 0):
    cards_dir = cards_dir or CARDS_DIR_DEFAULT
    cards_dir.mkdir(parents=True, exist_ok=True)
    instances = load_stale_chain(data_path)
    by_uid = {}
    for inst in instances:
        uid = inst.memories[0].memory_id.split("/", 1)[0] if inst.memories else None
        if uid and uid not in by_uid:
            by_uid[uid] = inst
    items = list(by_uid.items())
    if uids:
        keep = set(uids)
        items = [x for x in items if x[0] in keep]
    if limit_items:
        items = items[:limit_items]
    client = _client()
    tot_in = tot_out = 0
    for uid, inst in items:
        out_f = cards_dir / f"{uid}.json"
        if out_f.exists():
            print(f"[{uid}] SKIP (exists)")
            continue
        sessions = [{"memory_id": m.memory_id,
                     "date": (m.metadata or {}).get("session_date", ""),
                     "text": m.content} for m in inst.memories]
        if max_sessions:
            sessions = sessions[:max_sessions]
        t0 = time.time()
        raw_records: List[dict] = []
        item_in = item_out = 0
        for si, s in enumerate(sessions):
            try:
                recs, i_in, i_out = extract_session(client, s["memory_id"], s["date"], s["text"])
            except Exception as e:  # noqa: BLE001
                print(f"  session {si} ({s['memory_id']}) FAILED: "
                      f"{type(e).__name__}: {e}", flush=True)
                recs, i_in, i_out = [], 0, 0
            raw_records.extend(recs)
            item_in += i_in
            item_out += i_out
            if (si + 1) % 20 == 0:
                print(f"  ...{si+1}/{len(sessions)} sessions, "
                      f"{len(raw_records)} raw records so far", flush=True)
        cards = assemble(raw_records)
        tot_in += item_in
        tot_out += item_out
        out_f.write_text(json.dumps(
            {"uid": uid, "records": cards, "n_sessions": len(sessions),
             "n_raw_records": len(raw_records),
             "usage_in": item_in, "usage_out": item_out,
             "schema": "persession_v1"},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{uid}] {len(sessions)} sessions -> {len(raw_records)} raw "
              f"-> {len(cards)} cards, in={item_in} out={item_out} "
              f"({time.time()-t0:.0f}s)", flush=True)
    print(f"WRITE PHASE (persession) TOTAL: in={tot_in} out={tot_out}")


def main():
    if not _WRITE_PERSESSION:
        print("REFUSED: set QVF_WRITE_PERSESSION=1 to run this module "
              "(discipline gate — see module docstring).", file=sys.stderr)
        sys.exit(1)
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--uids", default=None,
                     help="逗号分隔 uid 列表;不传则跑该 --data 全部 uid")
    ap.add_argument("--cards-dir", default=str(CARDS_DIR_DEFAULT), dest="cards_dir")
    ap.add_argument("--items", type=int, default=0)
    ap.add_argument("--max-sessions", type=int, default=0, dest="max_sessions",
                     help="调试/冒烟用:每个 uid 只处理前 N 个会话(0=不限)")
    args = ap.parse_args()
    uids = args.uids.split(",") if args.uids else None
    write_phase(args.data, uids=uids, cards_dir=Path(args.cards_dir),
                limit_items=args.items, max_sessions=args.max_sessions)


if __name__ == "__main__":
    main()
