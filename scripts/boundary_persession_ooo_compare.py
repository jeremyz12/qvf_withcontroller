# -*- coding: utf-8 -*-
"""scripts/boundary_persession_ooo_compare.py — 阶段二判据①主裁决。

零 LLM。对新路径(QVF_WRITE_PERSESSION=1)在 data/_ooo_seq.json / _ooo_shuf.json
上分别建出的卡片集,逐 uid 用 write_persession.canonical_json() 稳定序列化后
逐字节比较。record_id 已是内容派生哈希(见 write_persession._record_id),不
含任何输入顺序信息,因此无需像冻结路径基线那样剥离 record_id —— 若装配层
与抽取层真的对顺序不变,seq/shuf 两份 canonical_json() 应逐字节相同,包括
record_id 与 relation_target_record_ids。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.write_persession import canonical_json  # noqa: E402


def _diff_records(recs_a, recs_b):
    """按 record_id 对齐后逐条列出差异,便于归因。"""
    by_a = {r["record_id"]: r for r in recs_a}
    by_b = {r["record_id"]: r for r in recs_b}
    ids_a, ids_b = set(by_a), set(by_b)
    only_a = ids_a - ids_b
    only_b = ids_b - ids_a
    common = ids_a & ids_b
    field_diffs = []
    for rid in sorted(common):
        ra, rb = by_a[rid], by_b[rid]
        for k in sorted(set(ra) | set(rb)):
            if ra.get(k) != rb.get(k):
                field_diffs.append({"record_id": rid, "field": k,
                                     "seq": ra.get(k), "shuf": rb.get(k)})
    return sorted(only_a), sorted(only_b), field_diffs


def main():
    seq_dir = ROOT / "results" / "wt_cards_persession_ooo_seq"
    shuf_dir = ROOT / "results" / "wt_cards_persession_ooo_shuf"
    uids = sorted(p.stem for p in seq_dir.glob("*.json"))
    n_same = n_diff = 0
    rows = []
    for uid in uids:
        ps, pu = seq_dir / f"{uid}.json", shuf_dir / f"{uid}.json"
        if not ps.exists() or not pu.exists():
            print(f"[{uid}] MISSING (seq={ps.exists()} shuf={pu.exists()})")
            continue
        ds = json.loads(ps.read_text(encoding="utf-8"))
        du = json.loads(pu.read_text(encoding="utf-8"))
        recs_s, recs_u = ds.get("records", []), du.get("records", [])
        js, ju = canonical_json(recs_s), canonical_json(recs_u)
        same = (js == ju)
        n_same += int(same)
        n_diff += int(not same)
        row = {"uid": uid, "byte_identical": same,
               "n_cards_seq": len(recs_s), "n_cards_shuf": len(recs_u),
               "n_raw_seq": ds.get("n_raw_records"), "n_raw_shuf": du.get("n_raw_records"),
               "usage_in_seq": ds.get("usage_in"), "usage_out_seq": ds.get("usage_out"),
               "usage_in_shuf": du.get("usage_in"), "usage_out_shuf": du.get("usage_out")}
        if not same:
            only_a, only_b, field_diffs = _diff_records(recs_s, recs_u)
            row["only_in_seq"] = only_a
            row["only_in_shuf"] = only_b
            row["field_diffs"] = field_diffs
        rows.append(row)
        print(f"[{uid}] {'SAME' if same else 'DIFF'} "
              f"(n_seq={len(recs_s)}, n_shuf={len(recs_u)})")
        if not same:
            print(f"    only_in_seq={row['only_in_seq']}")
            print(f"    only_in_shuf={row['only_in_shuf']}")
            for fd in row["field_diffs"][:10]:
                print(f"    field_diff record_id={fd['record_id']} field={fd['field']} "
                      f"seq={fd['seq']!r} shuf={fd['shuf']!r}")

    n = len(rows)
    print(f"\nPERSESSION PATH judgment ①: {n_diff}/{n} chains differ "
          f"({(n_diff/n*100) if n else 0:.1f}%), {n_same}/{n} byte-identical")

    tot_in = sum((r.get("usage_in_seq") or 0) + (r.get("usage_in_shuf") or 0) for r in rows)
    tot_out = sum((r.get("usage_out_seq") or 0) + (r.get("usage_out_shuf") or 0) for r in rows)
    cost = tot_in * 1.0 / 1e6 + tot_out * 5.0 / 1e6
    print(f"total tokens: in={tot_in} out={tot_out}  est. cost (Haiku 4.5 $1/$5 per MTok) = ${cost:.3f}")

    out = ROOT / "results" / "p2_persession_ooo_compare.json"
    out.write_text(json.dumps({"rows": rows, "n_total": n, "n_diff": n_diff,
                                "n_same": n_same, "tot_in": tot_in, "tot_out": tot_out,
                                "est_cost_usd": cost}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
