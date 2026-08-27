# -*- coding: utf-8 -*-
"""外部考场建卡驱动:冻结 write_phase 原样调用,仅重定向卡店目录与店子集。

统一店文件须含每店占位 "chain":[{"date":...,"value":""}] 与
"probing_queries":{"_placeholder":{"q":"","gold":""}}(load_stale_chain 的
结构要求;占位题不参与任何评测,建卡只消费 memories)。

用法:
  python scripts/ext_build_cards.py --data data/external/<arena>_unified.json \
      --cards-dir results/ext_cards_<arena> --uids-file <采样uid清单>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import wt_qvf_prototype as W  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--cards-dir", required=True)
    ap.add_argument("--uids-file", default="")
    a = ap.parse_args()
    W.CARDS_DIR = Path(a.cards_dir)
    uids = None
    if a.uids_file:
        uids = [l.strip() for l in open(a.uids_file, encoding="utf-8")
                if l.strip()]
        print(f"building cards for {len(uids)} sampled stores", flush=True)
    W.write_phase(a.data, uids=uids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
