# -*- coding: utf-8 -*-
"""P6: 建卡 n 轮驱动脚本 —— 对拍 B6,唯一差异是 QVF_CARD_TEMP0=1。
只读调用 scripts/wt_qvf_prototype.py 的 write_phase(), 不改动其逐字节行为
(旗标关时);本脚本只是按 uid 所属源文件分发调用,复现 B6 的分文件建卡方式。
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QVF_EMBED_BACKEND", "openai")

import scripts.wt_qvf_prototype as wt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    ROOT / "data/wikistate_full_P108.json",
    ROOT / "data/wikistate_full_P108_ext.json",
    ROOT / "data/wikistate_full_P54.json",
    ROOT / "data/wikistate_full_P54_ext.json",
]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", required=True, help="path to b6_fixed_subset50.json")
    ap.add_argument("--cards-dir", required=True)
    args = ap.parse_args()

    subset = json.loads(Path(args.subset).read_text(encoding="utf-8"))["uids"]
    subset_set = set(subset)

    wt.CARDS_DIR = Path(args.cards_dir)
    wt.CARDS_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    for f in FILES:
        data = json.loads(f.read_text(encoding="utf-8"))
        uids_here = [e["uid"] for e in data if e["uid"] in subset_set]
        if not uids_here:
            continue
        print(f"=== {f.name}: {len(uids_here)} uids ===", flush=True)
        wt.write_phase(str(f), 0, uids_here)

    made = list(wt.CARDS_DIR.glob("*.json"))
    print(f"TOTAL cards written: {len(made)} / expected {len(subset)} "
          f"({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
