# -*- coding: utf-8 -*-
"""scripts/write_persession_batch.py -- P3 quality-guardrail run driver.

Reuses scripts.write_persession.extract_session / assemble / canonical_json
UNCHANGED (no edits to that module -- it already carries the phase-1/phase-2
verified determinism property for assemble()). This file only adds
thread-pool concurrency across the per-session extraction calls within each
uid, purely to fit within wall-clock/session budget; it does not change what
is sent to the model or how records are assembled.

Because assemble() is order-invariant (judged criterion 4, verified with
1500+3000 shuffles in phase 1/2), running extract_session() concurrently and
feeding results to assemble() in whatever order they complete is equivalent
in expectation to the sequential write_persession.write_phase() -- same
per-session calls, same prompt, just concurrent instead of serial.

Usage:
  QVF_WRITE_PERSESSION=1 python scripts/write_persession_batch.py \
      --data data/wikistate_full_P108.json \
      --uids wikiP108003-Q63411963,wikiP108008-Q22278468 \
      --cards-dir results/wt_cards_p3_subset --workers 6
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.write_persession import (  # noqa: E402
    _WRITE_PERSESSION, _client, assemble, extract_session,
)
from eval.stale_chain_dataset import load_stale_chain  # noqa: E402

CARDS_DIR_DEFAULT = Path("results/wt_cards_p3_subset")


def write_phase_parallel(data_path: str, uids: Optional[List[str]] = None,
                          cards_dir: Optional[Path] = None, workers: int = 6):
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
        t0 = time.time()
        raw_records: List[dict] = []
        item_in = item_out = 0
        n_fail = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(extract_session, client, s["memory_id"], s["date"],
                               s["text"]): s for s in sessions}
            for fut in as_completed(futs):
                s = futs[fut]
                try:
                    recs, i_in, i_out = fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"  session ({s['memory_id']}) FAILED: {type(e).__name__}: {e}",
                          flush=True)
                    recs, i_in, i_out = [], 0, 0
                    n_fail += 1
                raw_records.extend(recs)
                item_in += i_in
                item_out += i_out
        cards = assemble(raw_records)
        tot_in += item_in
        tot_out += item_out
        out_f.write_text(json.dumps(
            {"uid": uid, "records": cards, "n_sessions": len(sessions),
             "n_raw_records": len(raw_records),
             "usage_in": item_in, "usage_out": item_out, "n_fail": n_fail,
             "schema": "persession_v1_batch"},
            ensure_ascii=False, indent=1), encoding="utf-8")
        cost = item_in * 1.0 / 1e6 + item_out * 5.0 / 1e6
        print(f"[{uid}] {len(sessions)} sessions -> {len(raw_records)} raw "
              f"-> {len(cards)} cards, in={item_in} out={item_out} "
              f"(${cost:.4f}) fails={n_fail} ({time.time()-t0:.0f}s)", flush=True)
    tot_cost = tot_in * 1.0 / 1e6 + tot_out * 5.0 / 1e6
    print(f"BATCH TOTAL: in={tot_in} out={tot_out} est_cost=${tot_cost:.4f}")


def main():
    if not _WRITE_PERSESSION:
        print("REFUSED: set QVF_WRITE_PERSESSION=1 (same gate as write_persession.py).",
              file=sys.stderr)
        sys.exit(1)
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--uids", default=None)
    ap.add_argument("--cards-dir", default=str(CARDS_DIR_DEFAULT), dest="cards_dir")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    uids = args.uids.split(",") if args.uids else None
    write_phase_parallel(args.data, uids=uids, cards_dir=Path(args.cards_dir),
                          workers=args.workers)


if __name__ == "__main__":
    main()
