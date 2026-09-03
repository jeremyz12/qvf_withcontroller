# -*- coding: utf-8 -*-
"""批 38-E 步骤 1:derived 店 results/wt_cards_v47skf ——对 results/wt_cards_v47sk
的 36 条链(results/b35_sample_uids.txt)逐卡应用批 38-D 的断言类型过滤器,
丢弃 plan/task/other_person/restate 四类,保留 start + unknown。

`assertion_type()` / `keep()` 规则是本会话 scratchpad 模块
`b38d_filter.py` 的**逐字复制**(未改一个子串/一条正则),不做 import ——
这个店要长期留存,不应依赖会话专属的临时 scratchpad 路径。规则出处见
`results/opt_batch38d_verdict.md` §一。

输出:
  - results/wt_cards_v47skf/<uid>.json  ×36(json.dumps(indent=1,
    ensure_ascii=False),与 wt_cards_v47sk 源文件的序列化参数逐字相同;
    除 records 被过滤外,uid / usage_in / usage_out /
    slot_canon_n / slot_canon_by_slot_class / slot_canon_by_b33a_alias /
    date_refined_n 六个顶层字段原样保留,byte-identical)。
  - results/b38e_filter_log.json —— 每张被丢弃卡片的
    {uid, date, slot, value, span(前120字符), class},加上按店/按类的
    汇总计数、硬约束核验结果、目录 sha256。

用法: PYTHONUTF8=1 python scripts/b38e_build_v47skf.py
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
SRC = ROOT / "results/wt_cards_v47sk"
DST = ROOT / "results/wt_cards_v47skf"
UIDS_FILE = ROOT / "results/b35_sample_uids.txt"
CORPUS = ROOT / "data/wikistate_full_ALL_v24.json"
OUT_LOG = ROOT / "results/b38e_filter_log.json"

# ------------------------------------------------------------------ assertion_type
# 逐字复制自会话 scratchpad b38d_filter.py（同一份规则，results/opt_batch38d_
# verdict.md §一收紧后的最终版：PLAN/TASK/PERSON/RESTATE_STILL 正则、
# START_CUES 均未改动）。
PLAN_CUES = [
    "nominee", "nomination", "nominated", "candidate", "applying", "applied",
    "incoming", "admitted", "offer", "interview", "hoping", "planning",
    "thinking of", "might", "would love", "considering",
]
TASK_CUES = [
    "working on", "leading a project", "curating", "organising", "organizing",
    "helping with", "new job",
]
PERSON_CUES = [
    "my wife", "my husband", "my friend", "my colleague", "my boss",
    "my team lead", "my partner",
]
PERSON_VERB_CUES = [
    " is ", " was ", " has ", " has been ", " does ", " did ", "'s ",
]
RESTATE_CUES = ["as always", "continue to be", "continues to be"]
RESTATE_STILL_RE = re.compile(
    r"\bstill\b(?!\s+(getting used to|adjusting to|settling into|new to))")
START_CUES = [
    "appointed", "started as", "start as", "am now", "i'm now", "as of today",
    "began serving", "took office", "elected", "became", "promoted to",
    "started working as", "returned as", "officially started",
]


def assertion_type(card):
    span = (card.get("source_span") or "").lower()
    value = (card.get("value") or "").lower()
    text = span + " . " + value

    if any(p in text for p in PERSON_CUES) and any(v in text for v in PERSON_VERB_CUES):
        return "other_person"
    if any(c in text for c in PLAN_CUES):
        return "plan"
    if any(c in text for c in TASK_CUES):
        return "task"
    if any(c in text for c in RESTATE_CUES) or RESTATE_STILL_RE.search(text):
        return "restate"
    if any(c in text for c in START_CUES):
        return "start"
    return "unknown"


def keep(card):
    return assertion_type(card) in ("start", "unknown")


DROP_CLASSES = ("plan", "task", "restate", "other_person")

# ------------------------------------------------------------------ value match
# (仅用于硬约束核验，与 scripts/b38b_score.py 的 nv/val_match 逐字相同)
_ART = re.compile(r"^(the|a|an|le|la|les|l')\s+", re.I)
_PUNCT = re.compile(r"[^\w\s]", re.U)


def nv(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _PUNCT.sub(" ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    s = _ART.sub("", s).strip()
    return s


def val_match(gold_v, card_v):
    g, c = nv(gold_v), nv(card_v)
    if not g or not c:
        return False
    if g == c:
        return True
    if len(g) >= 4 and re.search(r"\b" + re.escape(g) + r"\b", c):
        return True
    if len(c) >= 4 and re.search(r"\b" + re.escape(c) + r"\b", g):
        return True
    return False


def yr(d):
    m = re.match(r"(\d{4})", str(d or ""))
    return m.group(1) if m else ""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def dir_fingerprint(d: Path):
    fs = sorted(d.glob("*.json"))
    cat = hashlib.sha256()
    nrec = 0
    for f in fs:
        cat.update(f.name.encode())
        b = f.read_bytes()
        cat.update(b)
        nrec += len(json.loads(b)["records"])
    return len(fs), nrec, cat.hexdigest()


def main():
    uids = [x.strip() for x in UIDS_FILE.read_text(encoding="utf-8").splitlines()
            if x.strip()]
    assert len(uids) == 36, f"expected 36 uids, got {len(uids)}"

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    ents = {e["uid"]: e for e in corpus}

    src_fp_before = dir_fingerprint(SRC)

    DST.mkdir(parents=True, exist_ok=True)
    # derived 店必须从空目录重建，不允许残留旧文件掺进本批
    for f in DST.glob("*.json"):
        f.unlink()

    dropped_cards = []          # 全量丢弃清单
    census = Counter()          # 逐类计数（36 链全量卡片）
    per_uid_kept = {}
    per_uid_dropped = {}

    for uid in uids:
        sp = SRC / f"{uid}.json"
        obj = json.loads(sp.read_text(encoding="utf-8"))
        recs = obj["records"]
        kept_recs, drop_recs = [], []
        for r in recs:
            t = assertion_type(r)
            census[t] += 1
            if t in ("start", "unknown"):
                kept_recs.append(r)
            else:
                drop_recs.append((t, r))
        per_uid_kept[uid] = len(kept_recs)
        per_uid_dropped[uid] = len(drop_recs)
        for t, r in drop_recs:
            dropped_cards.append({
                "uid": uid,
                "date": r.get("stated_date") or "",
                "slot": r.get("slot") or "",
                "value": r.get("value") or "",
                "span": (r.get("source_span") or "")[:120],
                "class": t,
            })

        new_obj = dict(obj)   # 顶层其它字段（uid/usage_in/usage_out/
                                # slot_canon_*/date_refined_n）原样保留
        new_obj["records"] = kept_recs
        dp = DST / f"{uid}.json"
        dp.write_text(json.dumps(new_obj, ensure_ascii=False, indent=1),
                       encoding="utf-8")

    # ---------------------------------------------------------------- 硬约束核验
    # (a) 主判据：v47sk（过滤前）vs v47skf（过滤后）的金标命中索引集合，
    #     不能出现"命中→未命中"翻转（逐字复用 results/opt_batch38d_verdict.md
    #     §二 的方法：exact+date_off 命中的 gold 行必须在过滤后依然被同一条
    #     或另一条卡片命中）。
    def ledger_rows(uid, entry, cards_dir):
        p = cards_dir / f"{uid}.json"
        recs = json.loads(p.read_text(encoding="utf-8"))["records"]
        # stated_date 是唯一日期来源（不依赖 complex_query_arm._mem_dates，
        # 避免给这个独立核验脚本引入项目内部依赖；stated_date 缺失时退化为
        # 空串，与 b38b_score.ledger_rows 的兜底路径只在 stated_date 为空
        # 时才会用到 session date，这里的核验只关心「是否命中」，兜底缺失
        # 顶多让某条非金标行排序略有出入，不影响 exact/date_off 判定）。
        out = [((r.get("stated_date") or ""), r) for r in recs]
        out.sort(key=lambda x: x[0] or "9999")
        return out

    def hit_set(uid, entry, cards_dir):
        gold = entry.get("chain") or []
        rows = ledger_rows(uid, entry, cards_dir)
        used = set()
        hits = {}  # gold index -> (exact_bool)
        for gi, g in enumerate(gold):
            best = None
            for i, (d, r) in enumerate(rows):
                if i in used or not val_match(g.get("value"), r.get("value")):
                    continue
                same_yr = yr(d) == yr(g.get("date"))
                if best is None or (same_yr and not best[1]):
                    best = (i, same_yr)
                if same_yr:
                    break
            if best is None:
                continue
            used.add(best[0])
            hits[gi] = best[1]
        return hits

    n_gold_total = 0
    n_lost = 0
    lost_detail = []
    for uid in uids:
        e = ents[uid]
        before = hit_set(uid, e, SRC)
        after = hit_set(uid, e, DST)
        n_gold_total += len(e.get("chain") or [])
        for gi in before:
            if gi not in after:
                n_lost += 1
                lost_detail.append({"uid": uid, "gold_idx": gi,
                                     "gold": e["chain"][gi]})
    hard_constraint_a = {
        "method": "exact+date_off hit-index set, v47sk(before) vs "
                  "v47skf(after), per gold-chain hit->miss transition count",
        "gold_rows_total_36_chains": n_gold_total,
        "lost": n_lost,
        "lost_detail": lost_detail,
    }

    # (b) 字面核验：每张被丢弃卡片的 source_span，是否与本链任一条金标行的
    #     state_span 逐字相同或互为子串（大小写不敏感）——比 (a) 更严格的
    #     文本级二次核验，覆盖"值匹配巧合但其实是同一句金标原文被误删"的
    #     边界情况。
    span_hits = []
    for d in dropped_cards:
        uid = d["uid"]
        e = ents[uid]
        card_span = (d["span"] or "").strip().lower()
        if not card_span:
            continue
        for gi, g in enumerate(e.get("chain") or []):
            gs = (g.get("state_span") or "").strip().lower()
            if not gs:
                continue
            if card_span in gs or gs in card_span or card_span == gs:
                span_hits.append({**d, "gold_idx": gi,
                                   "gold_state_span": g.get("state_span"),
                                   "gold_value": g.get("value"),
                                   "gold_date": g.get("date")})
    hard_constraint_b = {
        "method": "dropped card source_span[:120] vs every gold chain[*]."
                  "state_span in the same uid, case-insensitive substring "
                  "match either direction",
        "flagged": span_hits,
    }

    dst_fp = dir_fingerprint(DST)
    src_fp_after = dir_fingerprint(SRC)

    log = {
        "store_src": "results/wt_cards_v47sk",
        "store_dst": "results/wt_cards_v47skf",
        "uids_n": len(uids),
        "census_all_records_36_chains": dict(census),
        "dropped_total": len(dropped_cards),
        "kept_total": sum(per_uid_kept.values()),
        "per_uid_kept": per_uid_kept,
        "per_uid_dropped": per_uid_dropped,
        "dropped_cards": dropped_cards,
        "hard_constraint_gold_anchor_check_a_index": hard_constraint_a,
        "hard_constraint_gold_anchor_check_b_span_text": hard_constraint_b,
        "src_dir_fingerprint_before": {
            "n_files": src_fp_before[0], "n_records": src_fp_before[1],
            "sha256": src_fp_before[2]},
        "src_dir_fingerprint_after": {
            "n_files": src_fp_after[0], "n_records": src_fp_after[1],
            "sha256": src_fp_after[2]},
        "src_untouched": src_fp_before == src_fp_after,
        "dst_dir_fingerprint": {
            "n_files": dst_fp[0], "n_records": dst_fp[1], "sha256": dst_fp[2]},
    }
    OUT_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    print(f"census (36 chains, all records): {dict(census)}")
    print(f"dropped={len(dropped_cards)} kept={sum(per_uid_kept.values())} "
          f"(src total={sum(census.values())})")
    print(f"src untouched: {log['src_untouched']}")
    print(f"dst store: {dst_fp[0]} files / {dst_fp[1]} records / "
          f"sha256={dst_fp[2]}")
    print(f"hard constraint (a) gold rows lost: {n_lost} / {n_gold_total}")
    print(f"hard constraint (b) span-text flagged drops: {len(span_hits)}")
    print(f"wrote {OUT_LOG}")


if __name__ == "__main__":
    main()
