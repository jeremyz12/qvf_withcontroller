# -*- coding: utf-8 -*-
"""批 33-H1 事后诊断:HippoRAG 2 的 top-10 是否召回了"链会话"。

不重建索引(force_index_from_scratch=False),直接加载 scripts/hipporag2_baseline.py
留下的 per-item 店,重跑同样的 60 个 query,统计:
  * 每题 top-10 里命中"链会话"(即该实体状态变更所在会话)的条数;
  * 命中的链状态占该链全部状态的比例(chain-state recall@10)。
链会话的判定:entry["chain"] 里每个状态的 date,与被检索段落首行
"(session date: YYYY-MM-DD)" 的日期逐字相等。

用法: .venv_hipporag/Scripts/python.exe scripts/hipporag2_retrieval_diag.py
"""
from __future__ import annotations

import json
import re
import sys
import types
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

_v = types.ModuleType("vllm")
_v.SamplingParams = object
_v.LLM = object
sys.modules.setdefault("vllm", _v)

import multiprocessing as _mp  # noqa: E402


class _LocalManager:
    def dict(self, *a, **k):
        return dict(*a, **k)

    def list(self, *a, **k):
        return list(*a, **k)


_orig = _mp.Manager
_mp.Manager = lambda *a, **k: _LocalManager()

from hipporag import HippoRAG  # noqa: E402
from hipporag.utils.config_utils import BaseConfig  # noqa: E402
from repro_batch2 import VOLS, sample_stores  # noqa: E402

_mp.Manager = _orig

DATE_RE = re.compile(r"\(session date: (\d{4}-\d{2}-\d{2})\)")


def main() -> int:
    entries = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    picked, by_uid = sample_stores()
    out = []
    for uid in picked:
        store = ROOT / "results/hipporag_stores" / uid
        if not store.exists():
            print(f"[{uid}] no store, skip", flush=True)
            continue
        chain_dates = {str(c.get("date"))[:10] for c in entries[uid].get("chain", [])}
        cfg = BaseConfig()
        cfg.save_dir = str(store)
        cfg.llm_name = "gpt-4o-mini"
        cfg.embedding_model_name = "text-embedding-3-small"
        cfg.openie_mode = "online"
        cfg.retrieval_top_k = 10
        cfg.force_index_from_scratch = False
        cfg.force_openie_from_scratch = False
        hr = HippoRAG(global_config=cfg)
        for q in by_uid[uid]:
            sol = hr.retrieve(queries=[q["question"]], num_to_retrieve=10)[0]
            dates = [m.group(1) for d in sol.docs for m in [DATE_RE.search(d)] if m]
            hit = sorted(set(dates) & chain_dates)
            out.append({"qid": q["qid"], "uid": uid, "qtype": q["qtype"],
                        "n_chain_states": len(chain_dates),
                        "n_chain_in_top10": len(hit),
                        "chain_recall": len(hit) / max(len(chain_dates), 1),
                        "retrieved_dates": dates, "chain_dates": sorted(chain_dates)})
            print(f"[{q['qid']}] chain {len(hit)}/{len(chain_dates)}", flush=True)
    p = ROOT / "results/b33_H1_hipporag2_retrieval_diag.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    n = len(out)
    if n:
        full = sum(1 for r in out if r["chain_recall"] >= 1.0)
        print(f"\nn={n}  mean chain-state recall@10 = "
              f"{sum(r['chain_recall'] for r in out) / n:.3f}; "
              f"完全召回全链的题 {full}/{n} = {full / n * 100:.1f}%")
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
