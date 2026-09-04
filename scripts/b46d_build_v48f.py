# -*- coding: utf-8 -*-
"""批 46d 步骤 C:derived 店 results/wt_cards_v48f —— 144 链全量版本。

- 触发链(见 results/b46d_pass2_triggers.json,gold-free 判据):
  results/wt_cards_v48(pass1)现有卡片 ∪ results/wt_cards_v48_pass2(pass2)
  新抽卡片,去重键 = (slot_class 或 slot 缺省, value 规范化, stated_date,
  source_span)(与 scripts/b41_build_v47skf2.py 逐字相同),联集后套用断言
  类型过滤器。
- 未触发链:results/wt_cards_v48 原样字节读入,直接套用同一断言类型过滤器
  (不联集,无 pass2)。

断言类型过滤规则(assertion_type()/keep()/DROP_CLASSES)逐字复制自
scripts/b38e_build_v47skf.py / scripts/b41_build_v47skf2.py,未改一个子串/
一条正则。

用法: PYTHONUTF8=1 python scripts/b46d_build_v48f.py
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
V48 = ROOT / "results/wt_cards_v48"              # 只读(pass1, 144 链)
PASS2 = ROOT / "results/wt_cards_v48_pass2"      # 只读(pass2,触发链子集)
DST = ROOT / "results/wt_cards_v48f"
UIDS_FILE = ROOT / "results/b46d_all144_uids.txt"
TRIGGERS_FILE = ROOT / "results/b46d_pass2_triggers.json"
CORPUS = ROOT / "data/wikistate_full_ALL_v24.json"
OUT_LOG = ROOT / "results/b46d_filter_log.json"

# ------------------------------------------------------------------ assertion_type
# 逐字复制自 scripts/b38e_build_v47skf.py / scripts/b41_build_v47skf2.py。
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


# ------------------------------------------------------------------ value match
# (与 scripts/b38b_score.py 的 nv/val_match 逐字相同,仅用于硬约束核验)
_ART = re.compile(r"^(the|a|an|le|la|les|l')\s+", re.I)
_PUNCT = re.compile(r"[^\w\s]", re.U)


def nv(s):
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


def dedup_key(card):
    slot = card.get("slot_class") or card.get("slot") or ""
    return (nv(slot), nv(card.get("value")), (card.get("stated_date") or ""),
            (card.get("source_span") or "").strip().lower())


def main():
    uids = [x.strip() for x in UIDS_FILE.read_text(encoding="utf-8").splitlines()
            if x.strip()]
    assert len(uids) == 144, f"expected 144 uids, got {len(uids)}"

    trig = json.loads(TRIGGERS_FILE.read_text(encoding="utf-8"))
    target_uids = [d["uid"] for d in trig["triggered"]]
    assert all(u in uids for u in target_uids)
    print(f"triggered (gold-free) uids: {len(target_uids)} / {len(uids)}")

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    ents = {e["uid"]: e for e in corpus}

    v48_fp_before = dir_fingerprint(V48)
    pass2_fp = dir_fingerprint(PASS2) if PASS2.exists() else (0, 0, "")

    DST.mkdir(parents=True, exist_ok=True)
    for f in DST.glob("*.json"):
        f.unlink()

    union_report = {}
    census = Counter()
    dropped_cards = []

    for uid in uids:
        v48_obj = json.loads((V48 / f"{uid}.json").read_text(encoding="utf-8"))
        v48_recs = v48_obj["records"]

        if uid in target_uids:
            p2_path = PASS2 / f"{uid}.json"
            if not p2_path.exists():
                raise SystemExit(f"missing pass2 file for triggered uid {uid}")
            p2_obj = json.loads(p2_path.read_text(encoding="utf-8"))
            p2_recs = p2_obj["records"]

            seen = {}
            union_recs = []
            for r in v48_recs:
                k = dedup_key(r)
                if k not in seen:
                    seen[k] = True
                    union_recs.append(r)
            new_from_pass2 = 0
            for r in p2_recs:
                k = dedup_key(r)
                if k not in seen:
                    seen[k] = True
                    union_recs.append(r)
                    new_from_pass2 += 1

            union_report[uid] = {
                "v48_n": len(v48_recs), "pass2_n": len(p2_recs),
                "union_n": len(union_recs), "new_from_pass2": new_from_pass2,
            }
            src_recs = union_recs
            base_obj = dict(v48_obj)
            base_obj["b46d_union_pass2_new_cards"] = new_from_pass2
        else:
            src_recs = v48_recs
            base_obj = dict(v48_obj)

        kept_recs, drop_recs = [], []
        for r in src_recs:
            t = assertion_type(r)
            census[t] += 1
            if t in ("start", "unknown"):
                kept_recs.append(r)
            else:
                drop_recs.append((t, r))
        for t, r in drop_recs:
            dropped_cards.append({
                "uid": uid, "date": r.get("stated_date") or "",
                "slot": r.get("slot") or r.get("slot_class") or "",
                "value": r.get("value") or "",
                "span": (r.get("source_span") or "")[:120], "class": t,
            })

        base_obj["records"] = kept_recs
        (DST / f"{uid}.json").write_text(
            json.dumps(base_obj, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------------------------------------------------------- 硬约束核验
    def ledger_rows(uid, cards_dir):
        p = cards_dir / f"{uid}.json"
        recs = json.loads(p.read_text(encoding="utf-8"))["records"]
        out = [((r.get("stated_date") or ""), r) for r in recs]
        out.sort(key=lambda x: x[0] or "9999")
        return out

    def hit_set(uid, entry, cards_dir):
        gold = entry.get("chain") or []
        rows = ledger_rows(uid, cards_dir)
        used = set()
        hits = {}
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
    n_lost_vs_v48 = 0
    lost_detail = []
    n_new_hits = []
    for uid in uids:
        e = ents[uid]
        before = hit_set(uid, e, V48)
        after = hit_set(uid, e, DST)
        n_gold_total += len(e.get("chain") or [])
        for gi in before:
            if gi not in after:
                n_lost_vs_v48 += 1
                lost_detail.append({"uid": uid, "gold_idx": gi,
                                    "gold": e["chain"][gi]})
        if uid in target_uids:
            newly = [gi for gi in after if gi not in before]
            if newly:
                n_new_hits.append({"uid": uid, "newly_hit_gold_idx": newly})

    hard_constraint_a = {
        "method": "exact+date_off hit-index set, v48(before) vs v48f(after), "
                  "per gold-chain hit->miss transition count (gold used ONLY "
                  "for this post-hoc verification, never for the pass2 "
                  "trigger decision itself)",
        "gold_rows_total_144_chains": n_gold_total,
        "lost_vs_v48": n_lost_vs_v48, "lost_detail_vs_v48": lost_detail,
        "newly_hit_vs_v48_target_uids": n_new_hits,
    }

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
    v48_fp_after = dir_fingerprint(V48)

    log = {
        "store_v48": "results/wt_cards_v48", "store_pass2": "results/wt_cards_v48_pass2",
        "store_dst": "results/wt_cards_v48f",
        "target_uids_n": len(target_uids), "target_uids": target_uids,
        "union_report": union_report,
        "census_all_records_144_chains": dict(census),
        "dropped_total": len(dropped_cards),
        "hard_constraint_gold_anchor_check_a_index": hard_constraint_a,
        "hard_constraint_gold_anchor_check_b_span_text": hard_constraint_b,
        "v48_dir_fingerprint_before": {"n_files": v48_fp_before[0],
                                       "n_records": v48_fp_before[1],
                                       "sha256": v48_fp_before[2]},
        "v48_dir_fingerprint_after": {"n_files": v48_fp_after[0],
                                      "n_records": v48_fp_after[1],
                                      "sha256": v48_fp_after[2]},
        "v48_untouched": v48_fp_before == v48_fp_after,
        "pass2_dir_fingerprint": {"n_files": pass2_fp[0], "n_records": pass2_fp[1],
                                  "sha256": pass2_fp[2]},
        "dst_dir_fingerprint": {"n_files": dst_fp[0], "n_records": dst_fp[1],
                                "sha256": dst_fp[2]},
    }
    OUT_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    print(f"census (144 chains, all records post-union): {dict(census)}")
    print(f"dropped={len(dropped_cards)}")
    print(f"v48 untouched: {log['v48_untouched']}")
    print(f"dst store: {dst_fp[0]} files / {dst_fp[1]} records / sha256={dst_fp[2]}")
    print(f"hard constraint (a) gold rows lost vs v48: {n_lost_vs_v48} / {n_gold_total}")
    print(f"hard constraint (b) span-text flagged drops: {len(span_hits)}")
    print(f"wrote {OUT_LOG}")


if __name__ == "__main__":
    main()
