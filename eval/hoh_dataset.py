"""Loader for HoH-QAs (HuggingFace: russwest404/HoH-QAs, Apache-2.0).

HoH ("Hallucinations of History"?) pairs each Wikipedia-derived question with the
CURRENT evidence passage plus every OUTDATED version of that same passage, each
carrying its own edit timestamp. That makes it a natural query-conditioned
validity benchmark: retrieval will surface several mutually contradictory
passages that differ only in *when* they were true.

Actual parquet schema (file hoh_qas_240601_241201.parquet, 111,972 rows,
90,571 distinct documents, single 'train' split)::

    question            string
    answer              string          -- gold answer as of last_modified_time
    last_modified_time  timestamp[ns]   -- e.g. 2024-07-01 00:00:00
    evidence            string          -- the CURRENT passage
    outdated_infos      list<struct<
                            answer:             string
                            evidence:           string
                            last_modified_time: string   -- 'YYYY-MM-DD'
                        >>
    document            struct<id: string, title: string>

Timestamps: ALL versions carry real timestamps, so nothing is synthesized here.
The top-level `last_modified_time` is a datetime (midnight); the nested
`outdated_infos[*].last_modified_time` is a plain 'YYYY-MM-DD' string. Both are
normalized to 'YYYY-MM-DD'. Verified over the full file:
  * every outdated version has a non-empty timestamp (0 missing),
  * every outdated timestamp is strictly earlier than the current one,
  * `outdated_infos` is ordered oldest -> newest,
  * dates come from 6 monthly snapshots, 2024-06-01 .. 2024-12-01,
  * length of `outdated_infos` is 1 for 95% of rows, up to 6 at the tail.

Mapping to the internal format (one QAInstance per sampled row):
  * the current `evidence` -> one MemoryItem dated `last_modified_time`,
  * each outdated version -> its own MemoryItem dated with ITS timestamp,
  * `n_distractors` evidence passages sampled from OTHER documents, each dated
    with that row's own `last_modified_time`,
  * memories are shuffled deterministically so the gold passage is not always
    first,
  * `question_date` = one day after the newest timestamp among all memories
    (distractors included, since a distractor may be newer than the gold),
  * `gold_answer` = the current `answer`, `question_type` = 'hoh_current',
  * `extra['outdated_answers']` keeps the superseded answers so a
    stale-answer-rate metric can be computed later.

`MemoryItem.content` is the raw evidence passage; the document title lives in
metadata (`doc_title`) rather than being prepended, to keep retrieval text
faithful to the dataset.

Determinism: sampling of rows uses Random(seed); each instance's distractors use
Random("hoh-distractors:{seed}:{row_index}"), so an instance's distractor set is
stable regardless of `limit` or of which other rows were drawn.
"""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.datasets import QAInstance
from qvf.retrieval import MemoryItem

DEFAULT_FILENAME = "hoh_qas_240601_241201.parquet"


def _date_str(value: Any) -> str:
    """Normalize a HoH timestamp (datetime, date or string) to 'YYYY-MM-DD'."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _plus_one_day(day: str) -> str:
    try:
        return (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    except ValueError:
        return day


def _resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_dir():
        preferred = p / DEFAULT_FILENAME
        if preferred.exists():
            return preferred
        candidates = sorted(p.glob("*.parquet"))
        if not candidates:
            raise FileNotFoundError(f"no .parquet file under {p}")
        return candidates[0]
    if not p.exists():
        raise FileNotFoundError(f"HoH parquet not found: {p}")
    return p


def load_hoh(
    path: str | Path,
    limit: int = 0,
    seed: int = 0,
    n_distractors: int = 8,
    min_versions: int = 1,
) -> List[QAInstance]:
    """Load HoH-QAs into QAInstances.

    Args:
        path: the .parquet file, or a directory containing it (e.g. data/hoh).
        limit: number of QA rows to sample; 0 = all 111,972 rows (heavy).
        seed: RNG seed for row sampling and distractor selection.
        n_distractors: passages drawn from OTHER documents per instance.
        min_versions: keep only rows with at least this many OUTDATED
            versions (1 = all; 2 = the harder multi-version tail, ~5.4k rows).
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "load_hoh needs pyarrow (pip install pyarrow) to read the HoH parquet"
        ) from exc

    file_path = _resolve_path(path)
    table = pq.read_table(file_path)
    n_rows = table.num_rows

    # Columnar views used only for distractor lookup (avoids materializing the
    # nested outdated_infos column for all ~112k rows).
    all_evidence: Sequence[str] = table.column("evidence").to_pylist()
    all_doc = table.column("document").to_pylist()
    all_doc_ids = [d["id"] for d in all_doc]
    all_doc_titles = [d["title"] for d in all_doc]
    all_dates = [_date_str(t) for t in table.column("last_modified_time").to_pylist()]

    rng = random.Random(seed)
    if min_versions > 1:
        n_out = [len(v or []) for v in
                 table.column("outdated_infos").to_pylist()]
        pool = [i for i in range(n_rows) if n_out[i] >= min_versions]
    else:
        pool = list(range(n_rows))
    if limit and limit < len(pool):
        row_indices = sorted(rng.sample(pool, limit))
    else:
        row_indices = pool

    sub = table.take(row_indices).to_pylist()

    instances: List[QAInstance] = []
    for pos, row in enumerate(sub):
        row_idx = row_indices[pos]
        doc = row.get("document") or {}
        doc_id = doc.get("id", "?")
        doc_title = doc.get("title", "")
        qid = f"hoh_{doc_id}_{row_idx}"

        cur_date = _date_str(row.get("last_modified_time"))
        memories: List[MemoryItem] = [
            MemoryItem(
                memory_id=f"{qid}/v_cur",
                content=row.get("evidence") or "",
                metadata={
                    "session_id": f"{doc_id}@{cur_date}",
                    "session_date": cur_date,
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "version": "current",
                    "is_current": True,
                    "is_distractor": False,
                },
            )
        ]

        outdated = row.get("outdated_infos") or []
        outdated_answers: List[str] = []
        outdated_dates: List[str] = []
        for v_idx, old in enumerate(outdated):
            old_date = _date_str(old.get("last_modified_time"))
            outdated_answers.append(old.get("answer") or "")
            outdated_dates.append(old_date)
            memories.append(
                MemoryItem(
                    memory_id=f"{qid}/v{v_idx}",
                    content=old.get("evidence") or "",
                    metadata={
                        "session_id": f"{doc_id}@{old_date}",
                        "session_date": old_date,
                        "doc_id": doc_id,
                        "doc_title": doc_title,
                        "version": f"outdated_{v_idx}",
                        "is_current": False,
                        "is_distractor": False,
                    },
                )
            )

        # Distractors: evidence passages from OTHER documents.
        d_rng = random.Random(f"hoh-distractors:{seed}:{row_idx}")
        distractor_ids: List[str] = []
        seen: set[int] = set()
        attempts = 0
        max_attempts = max(50, n_distractors * 25)
        while len(distractor_ids) < n_distractors and attempts < max_attempts and n_rows > 1:
            attempts += 1
            cand = d_rng.randrange(n_rows)
            if cand in seen or all_doc_ids[cand] == doc_id:
                continue
            seen.add(cand)
            d_date = all_dates[cand]
            memories.append(
                MemoryItem(
                    memory_id=f"{qid}/d{len(distractor_ids)}",
                    content=all_evidence[cand] or "",
                    metadata={
                        "session_id": f"{all_doc_ids[cand]}@{d_date}",
                        "session_date": d_date,
                        "doc_id": all_doc_ids[cand],
                        "doc_title": all_doc_titles[cand],
                        "version": "distractor",
                        "is_current": False,
                        "is_distractor": True,
                    },
                )
            )
            distractor_ids.append(all_doc_ids[cand])

        d_rng.shuffle(memories)

        dates = [m.metadata.get("session_date") or "" for m in memories]
        newest = max([d for d in dates if d] or [cur_date])
        question_date = _plus_one_day(newest)

        extra: Dict[str, Any] = {
            "doc_id": doc_id,
            "doc_title": doc_title,
            "row_index": row_idx,
            "current_date": cur_date,
            "outdated_answers": outdated_answers,
            "outdated_dates": outdated_dates,
            "n_versions": 1 + len(outdated),
            "n_distractors": len(distractor_ids),
            "distractor_doc_ids": distractor_ids,
        }
        instances.append(
            QAInstance(
                question_id=qid,
                question=row.get("question") or "",
                gold_answer=row.get("answer") or "",
                memories=memories,
                question_date=question_date,
                question_type="hoh_current",
                is_abstention=False,
                extra=extra,
            )
        )
    return instances


if __name__ == "__main__":
    default_dir = Path(__file__).resolve().parent.parent / "data" / "hoh"
    src = sys.argv[1] if len(sys.argv) > 1 else default_dir
    insts = load_hoh(src, limit=5, seed=0, n_distractors=8)
    print(f"loaded {len(insts)} instances")
    for inst in insts:
        print("=" * 72)
        print("qid       :", inst.question_id, "|", inst.question_type)
        print("question  :", inst.question)
        print("gold      :", inst.gold_answer)
        print("q_date    :", inst.question_date)
        print("memories  :", len(inst.memories),
              f"(1 current + {inst.extra['n_versions'] - 1} outdated"
              f" + {inst.extra['n_distractors']} distractors)")
        print("mem dates :", [m.metadata["session_date"] for m in inst.memories])
        print("stale ans :", inst.extra["outdated_answers"],
              "@", inst.extra["outdated_dates"])
