# -*- coding: utf-8 -*-
"""批 33-H1 诊断:HippoRAG 2 的 recognition-memory 事实闸(DSPyFilter)在这 60 题
上保留了几条事实;保留 0 条即触发官方 HippoRAG.py:415 的纯 DPR 回退。

复用 scripts/hipporag2_baseline.py 建好的 15 座店,不重建索引;重排 LLM 调用命中
llm_cache.sqlite,故重跑零新增 LLM 成本。改 hr.rerank_filter.model_name 可测别的
重排模型(诊断用,非 README 默认)。

用法: .venv_hipporag/Scripts/python.exe scripts/hipporag2_rerank_diag.py
输出: results/b33_H1_hipporag2_rerank_diag.jsonl
"""
import json, sys, types
from pathlib import Path
ROOT = Path(r"D:\ZZL_cluade")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
_v = types.ModuleType("vllm"); _v.SamplingParams = object; _v.LLM = object
sys.modules.setdefault("vllm", _v)
import multiprocessing as _mp
class _LM:
    def dict(self, *a, **k): return dict(*a, **k)
    def list(self, *a, **k): return list(*a, **k)
_o = _mp.Manager; _mp.Manager = lambda *a, **k: _LM()
from hipporag import HippoRAG
from hipporag.utils.config_utils import BaseConfig
from repro_batch2 import sample_stores
_mp.Manager = _o

picked, by_uid = sample_stores()
cur = {"n": 0, "facts": None}
orig = HippoRAG.rerank_facts
def patched(self, query, scores):
    idx, facts, log = orig(self, query, scores)
    cur["facts"] = len(facts)
    cur["cands"] = len(log.get("facts_before_rerank", []))
    return idx, facts, log
HippoRAG.rerank_facts = patched

out = []
for uid in picked:
    cfg = BaseConfig()
    cfg.save_dir = str(ROOT / "results/hipporag_stores" / uid)
    cfg.llm_name = "gpt-4o-mini"; cfg.embedding_model_name = "text-embedding-3-small"
    cfg.openie_mode = "online"; cfg.retrieval_top_k = 10
    cfg.force_index_from_scratch = False; cfg.force_openie_from_scratch = False
    hr = HippoRAG(global_config=cfg)
    for q in by_uid[uid]:
        cur["facts"] = None
        hr.retrieve(queries=[q["question"]], num_to_retrieve=10)
        out.append({"qid": q["qid"], "uid": uid, "qtype": q["qtype"],
                    "facts_kept": cur["facts"], "cands": cur.get("cands")})
p = ROOT / "results/b33_H1_hipporag2_rerank_diag.jsonl"
with open(p, "w", encoding="utf-8") as fh:
    for r in out: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print("wrote", p, len(out))
