"""Mem0 OSS write-time consolidation baseline on STALE-Chain.

Referee-requested baseline: Mem0 (pip mem0ai) consolidates memory at WRITE
time — its add() uses an LLM to extract facts and UPDATE/DELETE older ones.
QVF instead adjudicates validity at READ time. Prediction under test: write-
time consolidation destroys the history needed for point-in-time (dim4) and
trajectory (dim5) questions, while remaining fine on current-state (dim1).

Protocol per ITEM (not per question):
  1. Fresh Mem0 user_id = item uid; sessions ingested chronologically via
     m.add(session_turns, user_id=uid, metadata={"date": session_date}).
     (mem0ai 2.0.16 OSS: the `timestamp` kwarg raises — platform-only — so
     the session date travels in metadata, and search results carry it back.)
  2. Per question: m.search(question, filters={"user_id": uid}, top_k=10);
     each returned memory is wrapped as a qvf MemoryItem with
     metadata={"session_date": <date>} and answered by OUR reader
     (BaselineGenerator, claude-haiku-4-5, temp 0) — same reader as the
     dense_direct arm in scripts/run_decisive_stale.py.
  3. Judged by qvf.judge.ClaudeJudge (default judge model, same as all arms).

Usage:
    python scripts/run_mem0_baseline.py --items 2 --out results/mem0_smoke.jsonl
    python scripts/run_mem0_baseline.py --items 20 --out results/mem0_chain_pilot.jsonl
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("MEM0_TELEMETRY", "False")

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from tqdm import tqdm

from eval.stale_chain_dataset import load_stale_chain
from qvf.generator import BaselineGenerator
from qvf.judge import ClaudeJudge
from qvf.retrieval import MemoryItem

READER_MODEL = "claude-haiku-4-5"
TOP_K = 10


# ---------------------------------------------------------------------------
# Mem0 configuration
# ---------------------------------------------------------------------------

def _mem0_config(llm_choice: str, store_dir: Path) -> dict:
    """Build a Memory.from_config dict. llm_choice: 'anthropic' | 'openai'."""
    if llm_choice == "anthropic":
        llm = {
            "provider": "anthropic",
            "config": {
                "model": "claude-haiku-4-5",
                "temperature": 0.0,
                "max_tokens": 4000,
            },
        }
    else:
        llm = {
            "provider": "openai",
            "config": {"model": "gpt-5-mini"},
        }
    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "mem0_stale_chain",
                "embedding_model_dims": 1536,
                "path": str(store_dir / "qdrant"),
                "on_disk": False,
            },
        },
        "llm": llm,
        "embedder": {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "embedding_dims": 1536,
            },
        },
        "history_db_path": str(store_dir / "history.db"),
    }


class UsageCounter:
    """Accumulates mem0-internal LLM token usage by wrapping the provider
    client (mem0 OSS does not expose usage itself)."""

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self._lock = threading.Lock()

    def add(self, tin: int, tout: int):
        with self._lock:
            self.input_tokens += int(tin or 0)
            self.output_tokens += int(tout or 0)
            self.calls += 1

    def snapshot(self):
        with self._lock:
            return (self.input_tokens, self.output_tokens, self.calls)


def _instrument_llm(memory, counter: UsageCounter) -> bool:
    """Wrap the mem0 LLM client's create() to count tokens. Best-effort."""
    try:
        client = memory.llm.client
        if hasattr(client, "messages"):  # anthropic
            orig = client.messages.create

            def wrapped(**kw):
                resp = orig(**kw)
                try:
                    counter.add(resp.usage.input_tokens, resp.usage.output_tokens)
                except Exception:  # noqa: BLE001
                    pass
                return resp

            client.messages.create = wrapped
            return True
        if hasattr(client, "chat"):  # openai
            orig = client.chat.completions.create

            def wrapped(**kw):
                resp = orig(**kw)
                try:
                    counter.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
                except Exception:  # noqa: BLE001
                    pass
                return resp

            client.chat.completions.create = wrapped
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _make_memory(llm_choice: str, store_dir: Path, counter: UsageCounter):
    from mem0 import Memory

    store_dir.mkdir(parents=True, exist_ok=True)
    m = Memory.from_config(_mem0_config(llm_choice, store_dir))
    _instrument_llm(m, counter)
    return m


def _probe_llm(base_dir: Path, requested: str) -> str:
    """Try one real add() with the requested provider; fall back to openai
    gpt-5-mini if the anthropic provider is broken in this mem0 version."""
    if requested != "anthropic":
        return requested
    counter = UsageCounter()
    try:
        m = _make_memory("anthropic", base_dir / "_probe", counter)
        res = m.add(
            [{"role": "user", "content":
              "I moved to Lisbon last month and started a pottery class."}],
            user_id="probe-user",
        )
        n = len((res or {}).get("results", []))
        sr = m.search("Where does the user live?",
                      filters={"user_id": "probe-user"}, top_k=3)
        print(f"[probe] anthropic provider OK: add extracted {n} memories, "
              f"search returned {len(sr.get('results', []))}; "
              f"mem0 LLM tokens {counter.snapshot()}")
        if sr.get("results"):
            keys = sorted(sr["results"][0].keys())
            print(f"[probe] search result keys: {keys}")
        return "anthropic"
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        print("[probe] anthropic provider FAILED — falling back to "
              "openai gpt-5-mini (must be flagged in the report)")
        return "openai"


# ---------------------------------------------------------------------------
# Dataset handling
# ---------------------------------------------------------------------------

def _parse_turn(turn_text: str) -> dict:
    """STALE-Chain turns are stored as str(turn); distractor sessions hold
    dict-reprs {'role': ..., 'content': ...}, chain sessions plain strings.
    Recover role/content when possible so Mem0 sees a real conversation."""
    s = str(turn_text).strip()
    if s.startswith("{"):
        try:
            d = ast.literal_eval(s)
            if isinstance(d, dict) and "content" in d:
                role = str(d.get("role", "user"))
                if role not in ("user", "assistant"):
                    role = "user"
                return {"role": role, "content": str(d["content"])}
        except (ValueError, SyntaxError):
            pass
    return {"role": "user", "content": s}


def _group_items(instances):
    """Group QAInstances by item. All instances of one item share the SAME
    memories list object (see load_stale_chain), so group by its id()."""
    items = []
    by_mem = {}
    for inst in instances:
        key = id(inst.memories)
        if key not in by_mem:
            uid = inst.memories[0].memory_id.split("/")[0]
            entry = {"uid": uid, "memories": inst.memories, "instances": []}
            by_mem[key] = entry
            items.append(entry)
        by_mem[key]["instances"].append(inst)
    return items


def _sessions_of(memories):
    """Rebuild (session_id, date, [turn dicts]) in chronological (file) order
    from the flat memory list."""
    sessions = []
    seen = {}
    for m in memories:
        sid = m.metadata.get("session_id")
        if sid not in seen:
            seen[sid] = {"session_id": sid,
                         "date": m.metadata.get("session_date", ""),
                         "turns": []}
            sessions.append(seen[sid])
        seen[sid]["turns"].append(_parse_turn(m.content))
    return sessions


# ---------------------------------------------------------------------------
# Per-item pipeline
# ---------------------------------------------------------------------------

def run_item(item, llm_choice: str, store_root: Path, generator, judge,
             top_k: int) -> list[dict]:
    uid = item["uid"]
    counter = UsageCounter()
    rows = []
    ingest_t0 = time.time()
    session_errors = 0
    mem = None
    try:
        mem = _make_memory(llm_choice, store_root / uid, counter)
        try:
            mem.delete_all(user_id=uid)  # belt-and-braces on reruns
        except Exception:  # noqa: BLE001
            pass
        sessions = _sessions_of(item["memories"])
        for sess in sessions:
            try:
                mem.add(
                    sess["turns"],
                    user_id=uid,
                    metadata={"date": sess["date"]},
                    infer=True,
                )
            except Exception:  # noqa: BLE001
                session_errors += 1
                sys.stderr.write(
                    f"[{uid}] add() failed for {sess['session_id']}:\n"
                    + traceback.format_exc(limit=2))
    except Exception:  # noqa: BLE001
        # Item-level ingestion failure: record and fall through — questions
        # are still emitted as error rows so the pilot accounting stays whole.
        item_error = traceback.format_exc(limit=3)
        for inst in item["instances"]:
            rows.append({
                "question_id": inst.question_id,
                "question_type": inst.question_type,
                "mode": "mem0",
                "error": item_error,
            })
        return rows
    ingest_latency = round(time.time() - ingest_t0, 2)
    iin, iout, icalls = counter.snapshot()

    # How many memories did write-time consolidation retain?
    try:
        kept = mem.get_all(filters={"user_id": uid}, top_k=2000)
        kept_memories = kept.get("results", [])
    except Exception:  # noqa: BLE001
        kept_memories = []
    mem0_count = len(kept_memories)
    raw_rounds = len(item["memories"])
    n_sessions = len({m.metadata.get("session_id") for m in item["memories"]})

    for inst in item["instances"]:
        t0 = time.time()
        row = {
            "question_id": inst.question_id,
            "question_type": inst.question_type,
            "mode": "mem0",
            "question": inst.question,
            "gold_answer": inst.gold_answer,
            "mem0_llm": llm_choice,
            "mem0_memory_count": mem0_count,
            "raw_round_count": raw_rounds,
            "session_count": n_sessions,
            "session_add_errors": session_errors,
            "item_ingest_latency_s": ingest_latency,
            "mem0_ingest_input_tokens": iin,
            "mem0_ingest_output_tokens": iout,
            "mem0_ingest_llm_calls": icalls,
        }
        try:
            ts = time.time()
            found = mem.search(inst.question, filters={"user_id": uid},
                               top_k=top_k)
            results = found.get("results", [])
            row["search_latency_s"] = round(time.time() - ts, 2)
            retrieved = []
            row_evidence = []
            for i, r in enumerate(results):
                meta = r.get("metadata") or {}
                date = str(meta.get("date") or "")
                retrieved.append(MemoryItem(
                    memory_id=f"mem0#{i}",
                    content=str(r.get("memory") or ""),
                    metadata={"session_date": date},
                ))
                row_evidence.append({
                    "memory": str(r.get("memory") or ""),
                    "date": date,
                    "score": r.get("score"),
                })
            row["mem0_retrieved_count"] = len(retrieved)
            row["mem0_retrieved"] = row_evidence

            tg = time.time()
            gen = generator.generate(inst.question, retrieved,
                                     inst.question_date)
            row["gen_latency_s"] = round(time.time() - tg, 2)
            row["answer"] = gen.answer
            row["usage_input_tokens"] = gen.usage_input_tokens
            row["usage_output_tokens"] = gen.usage_output_tokens
            row["latency_s"] = round(time.time() - t0, 2)

            if judge is not None:
                try:
                    verdict = judge.judge(
                        inst.question, inst.gold_answer, gen.answer,
                        inst.question_type, False,
                    )
                    row["judge_correct"] = verdict.correct
                    row["judge_reason"] = verdict.reason
                except Exception:  # noqa: BLE001
                    row["judge_correct"] = None
                    row["judge_error"] = traceback.format_exc(limit=2)
        except Exception:  # noqa: BLE001
            row["error"] = traceback.format_exc(limit=3)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data/stale_chain_full.json")
    ap.add_argument("--items", type=int, default=2)
    ap.add_argument("--item-offset", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top-k", type=int, default=TOP_K)
    ap.add_argument("--workers", type=int, default=3,
                    help="item-level parallelism; each worker item gets its "
                         "own Mem0 store directory")
    ap.add_argument("--llm", choices=["anthropic", "openai"],
                    default="anthropic")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--append", action="store_true",
                    help="append to --out instead of overwriting (use with "
                         "--item-offset to resume)")
    ap.add_argument("--store-root", default=None,
                    help="Mem0 store directory (default: results/mem0_stores/"
                         "<out stem>)")
    args = ap.parse_args()

    instances = load_stale_chain(args.data, limit_items=args.items,
                                 item_offset=args.item_offset)
    items = _group_items(instances)
    print(f"Loaded {len(items)} items / {len(instances)} questions "
          f"from {args.data} (offset {args.item_offset})")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    store_root = Path(args.store_root) if args.store_root else (
        Path("results") / "mem0_stores" / out_path.stem)
    store_root.mkdir(parents=True, exist_ok=True)

    llm_choice = _probe_llm(store_root, args.llm)
    if args.llm == "anthropic" and llm_choice != "anthropic":
        print("*** NOTE: running with OPENAI gpt-5-mini as the Mem0 "
              "consolidation LLM (anthropic provider failed the probe). ***")

    generator = BaselineGenerator(model=READER_MODEL)
    generator.temperature = 0.0  # matches run_decisive_stale.py haiku readers
    judge = None if args.no_judge else ClaudeJudge()

    write_lock = threading.Lock()
    open_mode = "a" if args.append else "w"
    fout = out_path.open(open_mode, encoding="utf-8")
    all_rows = []

    def _emit(rows):
        with write_lock:
            for r in rows:
                fout.write(json.dumps(r, ensure_ascii=False) + "\n")
            fout.flush()
            all_rows.extend(rows)

    if args.workers > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {
                ex.submit(run_item, item, llm_choice, store_root, generator,
                          judge, args.top_k): item["uid"]
                for item in items
            }
            for fut in tqdm(as_completed(futs), total=len(futs),
                            desc="items"):
                _emit(fut.result())
    else:
        for item in tqdm(items, desc="items"):
            _emit(run_item(item, llm_choice, store_root, generator, judge,
                           args.top_k))
    fout.close()

    # Aggregates
    from collections import defaultdict

    agg = defaultdict(lambda: {"n": 0, "correct": 0})
    n_err = 0
    kept, raw = [], []
    for r in all_rows:
        if "error" in r:
            n_err += 1
            continue
        a = agg[r["question_type"]]
        a["n"] += 1
        a["correct"] += 1 if r.get("judge_correct") else 0
        kept.append(r.get("mem0_memory_count", 0))
        raw.append(r.get("raw_round_count", 0))
    print()
    tot_n = tot_c = 0
    for qt in sorted(agg):
        a = agg[qt]
        tot_n += a["n"]
        tot_c += a["correct"]
        print(f"mem0      {qt:22s} n={a['n']:>3} "
              f"acc={a['correct'] / max(a['n'], 1):.3f}")
    print(f"mem0      {'OVERALL':22s} n={tot_n:>3} "
          f"acc={tot_c / max(tot_n, 1):.3f}  errors={n_err}")
    if kept:
        print(f"Mem0 memories kept per item: mean "
              f"{sum(kept) / len(kept):.1f} (raw rounds mean "
              f"{sum(raw) / len(raw):.1f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
