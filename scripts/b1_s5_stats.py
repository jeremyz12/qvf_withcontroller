# -*- coding: utf-8 -*-
"""B1 stats: report the three required S5 numbers (original-314 subset,
new-P39 subset, union) for both the complex-query arm and the direct arm,
plus paired same-question tests (naive sign test + cluster-robust sign test
+ cluster bootstrap CI), by importing (not modifying) scripts/bootstrap_ci.py's
existing functions on freshly-built union files.

New file (bootstrap_ci.py is not one of the four frozen scripts, but this
still avoids touching it — only imports its helpers).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.bootstrap_ci import (  # noqa: E402
    build_clusters, load_two_file_pairs, report, print_row, N_BOOT, SEED,
)

RESULTS = Path("results")


def acc(path: Path, mode: str) -> tuple[int, int]:
    """(correct, judged) for a given mode in a jsonl results file."""
    c = j = 0
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        if "error" in r or r.get("mode") != mode:
            continue
        if r.get("judge_correct") is None:
            continue
        j += 1
        c += int(bool(r["judge_correct"]))
    return c, j


def build_union(orig: str, new: str, out: str) -> None:
    seen = set()
    rows = []
    for f in (orig, new):
        p = RESULTS / f"{f}.jsonl"
        if not p.exists():
            continue
        for line in p.open(encoding="utf-8"):
            r = json.loads(line)
            qid = r.get("question_id")
            if qid in seen:
                continue
            seen.add(qid)
            rows.append(r)
    with (RESULTS / f"{out}.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def main():
    # Build union files: original 314 archived results + new P39 results.
    n_arm = build_union("wsc_s5_test_v42", "wsc_s5_p39_arm", "wsc_s5_test_v42b1_union")
    n_direct = build_union("wsc_direct_s5_all", "wsc_s5_p39_direct", "wsc_direct_s5_all_b1_union")
    print(f"union rows: complex_arm={n_arm} wsc_direct={n_direct}")

    print("\n=== ① original 314-question subset (consistency check vs 89.81%) ===")
    c, j = acc(RESULTS / "wsc_s5_test_v42.jsonl", "complex_arm")
    print(f"complex_arm  (orig 314): {c}/{j} = {c/j*100:.2f}%")
    c, j = acc(RESULTS / "wsc_direct_s5_all.jsonl", "wsc_direct")
    print(f"wsc_direct   (orig 314): {c}/{j} = {c/j*100:.2f}%")

    print("\n=== ② new P39 subset only ===")
    c, j = acc(RESULTS / "wsc_s5_p39_arm.jsonl", "complex_arm")
    print(f"complex_arm  (P39 new):  {c}/{j} = {c/j*100:.2f}%")
    c, j = acc(RESULTS / "wsc_s5_p39_direct.jsonl", "wsc_direct")
    print(f"wsc_direct   (P39 new):  {c}/{j} = {c/j*100:.2f}%")

    print("\n=== ③ union (314+P39) = corrected S5 final numbers ===")
    c, j = acc(RESULTS / "wsc_s5_test_v42b1_union.jsonl", "complex_arm")
    print(f"complex_arm  (union):    {c}/{j} = {c/j*100:.2f}%")
    c, j = acc(RESULTS / "wsc_direct_s5_all_b1_union.jsonl", "wsc_direct")
    print(f"wsc_direct   (union):    {c}/{j} = {c/j*100:.2f}%")

    print("\n=== paired same-question tests (complex_arm vs wsc_direct), cluster = wikistate uid ===")
    rng = random.Random(SEED)

    def paired(label, test_file, base_file):
        tp = RESULTS / f"{test_file}.jsonl"
        bp = RESULTS / f"{base_file}.jsonl"
        items, uid_map = load_two_file_pairs(tp, bp, "complex_arm", "wsc_direct", True)
        if not items:
            print(f"[skip] no overlapping question_ids for {label}")
            return
        clusters = build_clusters(items, "wikistate", uid_map)
        r = report(label, items, clusters, rng, N_BOOT)
        if r:
            print_row(r)

    paired("original 314 (re-derived, sanity check)", "wsc_s5_test_v42", "wsc_direct_s5_all")
    paired("P39 new (104)", "wsc_s5_p39_arm", "wsc_s5_p39_direct")
    paired("UNION (418) = corrected S5 final", "wsc_s5_test_v42b1_union", "wsc_direct_s5_all_b1_union")


if __name__ == "__main__":
    main()
