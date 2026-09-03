# -*- coding: utf-8 -*-
"""批 41 步骤 2:derived 店 results/wt_cards_v47skf2 —— 对
results/wt_cards_v47sk 的 3 条缺锚点链(wikiP39037-Q3525068、
wikiP39006-Q5220520、wikiP39017-Q24568849)联集本批新抽取的第二遍卡片
（results/wt_cards_v47s_pass2，scripts/wt_qvf_prototype_b38.py 原样命令，
只换目标目录），再对联集结果应用与批 38-E 逐字相同的断言类型过滤器；其余
33 条链从 results/wt_cards_v47skf 原样字节复制。

去重键：(slot_class 或 slot 缺省, value 规范化, stated_date, source_span)。
v47sk 卡片带 slot_class；pass2 卡片是原版 wt_qvf_prototype_b38.py 输出、
没有 slot_class 字段，键第一段退化用 slot。

用法: PYTHONUTF8=1 python scripts/b41_build_v47skf2.py
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
SK = ROOT / "results/wt_cards_v47sk"          # 只读
SKF = ROOT / "results/wt_cards_v47skf"        # 只读(其余 33 链原样复制源)
PASS2 = ROOT / "results/wt_cards_v47s_pass2"  # 只读(本批新抽,3 链)
DST = ROOT / "results/wt_cards_v47skf2"
UIDS_FILE = ROOT / "results/b35_sample_uids.txt"
CORPUS = ROOT / "data/wikistate_full_ALL_v24.json"
OUT_LOG = ROOT / "results/b41_filter_log.json"

TARGET_UIDS = ["wikiP39037-Q3525068", "wikiP39006-Q5220520",
               "wikiP39017-Q24568849"]

# ------------------------------------------------------------------ assertion_type
# 逐字复制自 scripts/b38e_build_v47skf.py（未改一个子串/一条正则）。
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


def dedup_key(card):
    slot = card.get("slot_class") or card.get("slot") or ""
    return (nv(slot), nv(card.get("value")), (card.get("stated_date") or ""),
            (card.get("source_span") or "").strip().lower())


def main():
    uids = [x.strip() for x in UIDS_FILE.read_text(encoding="utf-8").splitlines()
            if x.strip()]
    assert len(uids) == 36, f"expected 36 uids, got {len(uids)}"
    assert all(u in uids for u in TARGET_UIDS)

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    ents = {e["uid"]: e for e in corpus}

    sk_fp_before = dir_fingerprint(SK)
    skf_fp_before = dir_fingerprint(SKF)
    pass2_fp = dir_fingerprint(PASS2)

    DST.mkdir(parents=True, exist_ok=True)
    for f in DST.glob("*.json"):
        f.unlink()

    union_report = {}   # uid -> {sk_n, pass2_n, union_n, new_from_pass2, ...}
    census = Counter()
    dropped_cards = []

    for uid in uids:
        if uid in TARGET_UIDS:
            sk_obj = json.loads((SK / f"{uid}.json").read_text(encoding="utf-8"))
            sk_recs = sk_obj["records"]
            p2_obj = json.loads((PASS2 / f"{uid}.json").read_text(encoding="utf-8"))
            p2_recs = p2_obj["records"]

            seen = {}
            union_recs = []
            for r in sk_recs:
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
                "v47sk_n": len(sk_recs), "pass2_n": len(p2_recs),
                "union_n": len(union_recs), "new_from_pass2": new_from_pass2,
            }

            kept_recs, drop_recs = [], []
            for r in union_recs:
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

            new_obj = dict(sk_obj)  # 顶层其它字段沿用 v47sk 的(usage_in 等
                                     # 对联集店只是历史记账参考,不重算)
            new_obj["records"] = kept_recs
            new_obj["b41_union_pass2_new_cards"] = new_from_pass2
            (DST / f"{uid}.json").write_text(
                json.dumps(new_obj, ensure_ascii=False, indent=1),
                encoding="utf-8")
        else:
            # 其余 33 链:从 v47skf 原样字节复制
            src = SKF / f"{uid}.json"
            (DST / f"{uid}.json").write_bytes(src.read_bytes())
            obj = json.loads(src.read_text(encoding="utf-8"))
            for r in obj["records"]:
                census[assertion_type(r)] += 1

    # ---------------------------------------------------------------- 硬约束核验
    # 金标锚点命中索引集合:v47sk(before) vs v47skf2(after) 不能出现
    # "命中→未命中"翻转（与批 38-D/38-E 同一方法；这里额外核验一次也不能
    # 相对 v47skf 翻转，因为 v47skf2 对 33 条未动链应逐字等价于 v47skf）。
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
    n_lost_vs_sk = 0
    lost_detail_vs_sk = []
    n_lost_vs_skf = 0
    lost_detail_vs_skf = []
    n_new_hits = []
    for uid in uids:
        e = ents[uid]
        before_sk = hit_set(uid, e, SK)
        before_skf = hit_set(uid, e, SKF)
        after = hit_set(uid, e, DST)
        n_gold_total += len(e.get("chain") or [])
        for gi in before_sk:
            if gi not in after:
                n_lost_vs_sk += 1
                lost_detail_vs_sk.append({"uid": uid, "gold_idx": gi,
                                          "gold": e["chain"][gi]})
        for gi in before_skf:
            if gi not in after:
                n_lost_vs_skf += 1
                lost_detail_vs_skf.append({"uid": uid, "gold_idx": gi,
                                           "gold": e["chain"][gi]})
        if uid in TARGET_UIDS:
            newly = [gi for gi in after if gi not in before_skf]
            if newly:
                n_new_hits.append({"uid": uid, "newly_hit_gold_idx": newly,
                                    "gold": [e["chain"][gi] for gi in newly]})

    hard_constraint_a = {
        "method": "exact+date_off hit-index set, v47sk(before)/v47skf(before) "
                  "vs v47skf2(after), per gold-chain hit->miss transition "
                  "count",
        "gold_rows_total_36_chains": n_gold_total,
        "lost_vs_v47sk": n_lost_vs_sk, "lost_detail_vs_v47sk": lost_detail_vs_sk,
        "lost_vs_v47skf": n_lost_vs_skf,
        "lost_detail_vs_v47skf": lost_detail_vs_skf,
        "newly_hit_vs_v47skf": n_new_hits,
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
    sk_fp_after = dir_fingerprint(SK)
    skf_fp_after = dir_fingerprint(SKF)

    # 非目标 33 链 byte-identical 校验
    non_target_identical = True
    for uid in uids:
        if uid in TARGET_UIDS:
            continue
        a = (DST / f"{uid}.json").read_bytes()
        b = (SKF / f"{uid}.json").read_bytes()
        if a != b:
            non_target_identical = False
            print(f"MISMATCH non-target uid={uid}")

    log = {
        "store_sk": "results/wt_cards_v47sk", "store_skf": "results/wt_cards_v47skf",
        "store_pass2": "results/wt_cards_v47s_pass2",
        "store_dst": "results/wt_cards_v47skf2",
        "target_uids": TARGET_UIDS,
        "union_report": union_report,
        "census_all_records_36_chains": dict(census),
        "dropped_total": len(dropped_cards),
        "dropped_cards": dropped_cards,
        "hard_constraint_gold_anchor_check_a_index": hard_constraint_a,
        "hard_constraint_gold_anchor_check_b_span_text": hard_constraint_b,
        "non_target_33_chains_byte_identical_to_v47skf": non_target_identical,
        "sk_dir_fingerprint_before": {"n_files": sk_fp_before[0],
                                      "n_records": sk_fp_before[1],
                                      "sha256": sk_fp_before[2]},
        "sk_dir_fingerprint_after": {"n_files": sk_fp_after[0],
                                     "n_records": sk_fp_after[1],
                                     "sha256": sk_fp_after[2]},
        "sk_untouched": sk_fp_before == sk_fp_after,
        "skf_dir_fingerprint_before": {"n_files": skf_fp_before[0],
                                       "n_records": skf_fp_before[1],
                                       "sha256": skf_fp_before[2]},
        "skf_dir_fingerprint_after": {"n_files": skf_fp_after[0],
                                      "n_records": skf_fp_after[1],
                                      "sha256": skf_fp_after[2]},
        "skf_untouched": skf_fp_before == skf_fp_after,
        "pass2_dir_fingerprint": {"n_files": pass2_fp[0], "n_records": pass2_fp[1],
                                  "sha256": pass2_fp[2]},
        "dst_dir_fingerprint": {"n_files": dst_fp[0], "n_records": dst_fp[1],
                                "sha256": dst_fp[2]},
    }
    OUT_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    print(f"union_report: {json.dumps(union_report, ensure_ascii=False, indent=1)}")
    print(f"census (36 chains, all records): {dict(census)}")
    print(f"dropped={len(dropped_cards)}")
    print(f"sk untouched: {log['sk_untouched']} | skf untouched: {log['skf_untouched']}")
    print(f"non-target 33 chains byte-identical to v47skf: {non_target_identical}")
    print(f"dst store: {dst_fp[0]} files / {dst_fp[1]} records / sha256={dst_fp[2]}")
    print(f"hard constraint (a) gold rows lost vs v47sk: {n_lost_vs_sk} / {n_gold_total}")
    print(f"hard constraint (a) gold rows lost vs v47skf: {n_lost_vs_skf} / {n_gold_total}")
    print(f"newly hit gold rows (vs v47skf, target uids): {n_new_hits}")
    print(f"hard constraint (b) span-text flagged drops: {len(span_hits)}")
    print(f"wrote {OUT_LOG}")


if __name__ == "__main__":
    main()
