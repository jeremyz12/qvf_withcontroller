# -*- coding: utf-8 -*-
"""scripts/repro_batch4.py — 考生批 8:txtai / langgraph InMemoryStore ×
WikiState 聚合题(A-MEM/cognee 另行适配)。
预注册:results/repro_batch4_prereg.md。协议镜像 repro_batch2:同 15 库 60 题、
同读者同判官;k=10。
用法: python repro_batch4.py --system txtai|lgstore
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
sys.path.insert(0, r"D:\ZZL_cluade\scripts")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")

import anthropic
from qvf.judge import ClaudeJudge
from repro_batch2 import sample_stores, VOLS, ROOT, READER_MODEL, READER_SYS


def sess_text(s):
    turns = s.get("turns", [])[:6]
    return f"(session date: {s.get('date','undated')})\n" + \
        "\n".join(str(t)[:400] for t in turns)


class TxtaiSystem:
    """本地嵌入 flat-RAG 锚:零 LLM 摄入,sentence-transformers 检索。"""
    name = "txtai"

    def __init__(self):
        from txtai import Embeddings
        self._E = Embeddings
        self.stores: dict = {}

    def ingest(self, uid, sessions):
        emb = self._E(content=True)
        emb.index([(i, sess_text(s), None) for i, s in enumerate(sessions)])
        self.stores[uid] = emb

    def search(self, uid, query):
        emb = self.stores.get(uid)
        if emb is None:
            return []
        return [f"- {r['text'][:400]}" for r in emb.search(query, limit=10)]


class LgStoreSystem:
    """langgraph InMemoryStore:官方记忆基建,openai 嵌入语义索引。"""
    name = "lgstore"

    def __init__(self):
        from langgraph.store.memory import InMemoryStore
        from langchain_openai import OpenAIEmbeddings
        self.store = InMemoryStore(index={
            "embed": OpenAIEmbeddings(model="text-embedding-3-small"),
            "dims": 1536})

    def ingest(self, uid, sessions):
        for i, s in enumerate(sessions):
            self.store.put((uid, "sessions"), f"s{i}", {"text": sess_text(s)})

    def search(self, uid, query):
        hits = self.store.search((uid, "sessions"), query=query, limit=10)
        return [f"- {h.value['text'][:400]}" for h in hits]


class Bm25System:
    """词面检索锚:rank_bm25,零 LLM 摄入。"""
    name = "bm25"

    def __init__(self):
        from rank_bm25 import BM25Okapi
        self._cls = BM25Okapi
        self.stores: dict = {}

    def ingest(self, uid, sessions):
        docs = [sess_text(s) for s in sessions]
        toks = [d.lower().split() for d in docs]
        self.stores[uid] = (self._cls(toks), docs)

    def search(self, uid, query):
        st = self.stores.get(uid)
        if st is None:
            return []
        bm, docs = st
        import numpy as np
        scores = bm.get_scores(query.lower().split())
        idx = np.argsort(scores)[::-1][:10]
        return [f"- {docs[i][:400]}" for i in idx]


class AmemSystem:
    """A-MEM(agiresearch):Zettelkasten 演化笔记;llm_backend=openai
    gpt-4o-mini(其原生支持面),嵌入本地 MiniLM。每 add_note 触发 LLM
    笔记构造+链接演化——抽样先行。"""
    name = "amem"

    def __init__(self):
        # b35c 接线:源码路径可由 --amem-repo / 环境变量 AMEM_REPO 指定;默认仍为旧路径
        repo = os.environ.get("AMEM_REPO") or (
            r"C:/Users/25243/AppData/Local/Temp/claude/"
            r"D--ZZL-cluade/2b238d36-0e89-4591-ac1c-f5ffd6578795/"
            r"scratchpad/A-mem")
        sys.path.insert(0, repo)
        from agentic_memory.memory_system import AgenticMemorySystem
        self._cls = AgenticMemorySystem
        self.stores: dict = {}
        try:
            import subprocess
            commit = subprocess.check_output(
                ["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
        except Exception:  # noqa: BLE001
            commit = "unknown"
        self.row_extra = {"amem_repo": repo, "amem_commit": commit}
        self.store_extra: dict = {}  # uid -> 摄入期 gpt-4o-mini 用量(只计量)

    def ingest(self, uid, sessions):
        m = self._cls(model_name="all-MiniLM-L6-v2",
                      llm_backend="openai", llm_model="gpt-4o-mini")
        usage = {"amem_ingest_llm_in": 0, "amem_ingest_llm_out": 0,
                 "amem_ingest_llm_calls": 0}
        try:  # 计量包装:透传全部参数,只读 response.usage,不改 A-MEM 的调用
            _cc = m.llm_controller.llm.client.chat.completions
            _orig = _cc.create

            def _counted(*args, **kw):
                r = _orig(*args, **kw)
                u = getattr(r, "usage", None)
                usage["amem_ingest_llm_calls"] += 1
                usage["amem_ingest_llm_in"] += getattr(u, "prompt_tokens", 0) or 0
                usage["amem_ingest_llm_out"] += getattr(u, "completion_tokens", 0) or 0
                return r
            _cc.create = _counted
        except Exception:  # noqa: BLE001
            pass
        self.store_extra[uid] = usage
        for s in sessions:
            for attempt in range(3):
                try:
                    m.add_note(sess_text(s), time=s.get("date", ""))
                    break
                except TypeError:
                    try:
                        m.add_note(sess_text(s))
                        break
                    except Exception:  # noqa: BLE001
                        time.sleep(3)
                except Exception as e:  # noqa: BLE001
                    print(f"[{uid}] add retry {attempt}: "
                          f"{type(e).__name__}: {str(e)[:80]}", flush=True)
                    time.sleep(3)
        self.stores[uid] = m

    def search(self, uid, query):
        m = self.stores.get(uid)
        if m is None:
            return []
        try:
            hits = m.search_agentic(query, k=10)
            out = []
            for h in hits:
                txt = h.get("content", h) if isinstance(h, dict) else str(h)
                out.append(f"- {str(txt)[:400]}")
            return out
        except Exception as e:  # noqa: BLE001
            print(f"[{uid}] search fail: {type(e).__name__}", flush=True)
            return []


class MemStrataSystem:
    """MemStrata 式确定性 (s,r,o) 双时序台账(按论文方法节复刻,提示词自写,
    对外标注"MemStrata 式")。写入:每会话一次 haiku 三元组抽取 → (s,r) 键
    查活跃断言:异 object 取代(旧行关闭)、同 object 强化、无键新存。
    读取:仅活跃行(superseded 丢弃,照论文默认)+ openai 嵌入 top-10。
    预注册预测:当前值类强、聚合类塌——valid:S×Q 天花板的实测形态。"""
    name = "mstrata"

    def __init__(self):
        import anthropic as _a
        self.client = _a.Anthropic()
        from qvf.retrieval import OpenAIDenseRetriever
        self._retr_cls = OpenAIDenseRetriever
        self.stores: dict = {}

    def _extract(self, text, date):
        prompt = (
            "Extract user-state facts from this chat session as JSON array of "
            "triples: [{\"s\": subject, \"r\": relation, \"o\": object}]. "
            "Rules: subject is 'user' for first-person statements; relation is "
            "a short normalized attribute name (e.g. employer, team, "
            "residence, diet); two sentences that differ only in the value "
            "MUST produce the same s and r; o is the value only, never "
            "embedded in s or r. Output ONLY the JSON array.\n\n" + text)
        for attempt in range(3):
            try:
                r = self.client.messages.create(
                    model=READER_MODEL, max_tokens=500, temperature=0.0,
                    messages=[{"role": "user", "content": prompt}])
                raw = "".join(b.text for b in r.content if b.type == "text")
                i, j = raw.find("["), raw.rfind("]")
                return json.loads(raw[i:j + 1]) if i >= 0 else []
            except Exception:  # noqa: BLE001
                time.sleep(3)
        return []

    def ingest(self, uid, sessions):
        ledger = []  # rows: {s,r,o,valid_from,valid_to,superseded}
        active = {}  # (s_norm, r_norm) -> row
        for s in sessions:
            date = s.get("date", "")
            for t in self._extract(sess_text(s), date):
                try:
                    key = (str(t["s"]).strip().lower(),
                           str(t["r"]).strip().lower())
                    o = str(t["o"]).strip()
                except Exception:  # noqa: BLE001
                    continue
                if not o:
                    continue
                cur = active.get(key)
                if cur is not None and cur["o"].lower() == o.lower():
                    continue  # 强化,无操作
                if cur is not None:  # 取代:旧行关闭
                    cur["valid_to"] = date
                    cur["superseded"] = True
                row = {"s": key[0], "r": key[1], "o": o,
                       "valid_from": date, "valid_to": None,
                       "superseded": False}
                ledger.append(row)
                active[key] = row
        rows = [r for r in ledger if not r["superseded"]]  # 论文默认读路径

        class _M:
            def __init__(self, c, d):
                self.content, self.metadata = c, {"session_date": d}
                self.memory_id = d
        mems = [_M(f"[since {r['valid_from']}] {r['s']} {r['r']}: {r['o']}",
                   r["valid_from"]) for r in rows]
        self.stores[uid] = (self._retr_cls(mems) if mems else None,
                            len(ledger), len(rows))

    def search(self, uid, query):
        retr, tot, act = self.stores.get(uid, (None, 0, 0))
        if retr is None:
            return []
        try:
            hits = retr.retrieve(query, top_k=10)
            return [f"- {h.content[:300]}" for h in hits]
        except Exception:  # noqa: BLE001
            return []


class CogneeSystem:
    """cognee:LLM 知识图谱抽取路线。add→cognify 建图,search 取 CHUNKS
    (只要素材不要它自答,喂我方同款读者保持同台)。全嵌入式默认存储。"""
    name = "cognee"

    def __init__(self):
        import asyncio
        import os
        os.environ.setdefault("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")
        os.environ.setdefault("EMBEDDING_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        import cognee
        self._c = cognee
        self._run = asyncio.run
        # b35c 用量埋点:被动 litellm success 回调,只累计 usage,不改任何调用
        self._root = None
        self.usage = {"llm_in": 0, "llm_out": 0, "llm_calls": 0,
                      "emb_tok": 0, "emb_calls": 0}
        try:
            import litellm

            def _cb(kwargs, resp, t0, t1, _u=self.usage):
                u = getattr(resp, "usage", None)
                if u is None:
                    return
                pt = getattr(u, "prompt_tokens", 0) or 0
                ct = getattr(u, "completion_tokens", 0) or 0
                if "embedding" in str(kwargs.get("call_type", "")):
                    _u["emb_tok"] += pt
                    _u["emb_calls"] += 1
                else:
                    _u["llm_in"] += pt
                    _u["llm_out"] += ct
                    _u["llm_calls"] += 1
            litellm.success_callback.append(_cb)
        except Exception:  # noqa: BLE001
            pass

    def set_store_root(self, root):
        """b35c:把 cognee 的 system/data 根改到隔离目录(不写其全局根)。"""
        import atexit
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._c.config.system_root_directory(str(self._root / "system"))
        self._c.config.data_root_directory(str(self._root / "data"))
        atexit.register(lambda: (self._root / "usage_total.json").write_text(
            json.dumps(self.usage), encoding="utf-8"))

    def ingest(self, uid, sessions):
        c = self._c
        u0, t0 = dict(self.usage), time.time()

        async def go():
            for s in sessions:
                await c.add(sess_text(s), dataset_name=uid)
            await c.cognify(datasets=[uid])
        self._run(go())
        if self._root is not None:  # 每库建库用量 sidecar(店根内)
            with open(self._root / "usage_build.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"uid": uid, "n_sessions": len(sessions),
                                    "build_s": round(time.time() - t0, 1),
                                    **{k: self.usage[k] - u0[k] for k in u0}}) + "\n")

    def search(self, uid, query):
        c = self._c
        from cognee import SearchType

        async def go():
            return await c.search(query_text=query,
                                  query_type=SearchType.CHUNKS,
                                  datasets=[uid], top_k=10)
        try:
            res = self._run(go())
            out = []
            for r in res:  # 1.5.x:每 dataset 一个 dict,chunks 在 search_result
                items = r.get("search_result", [r]) if isinstance(r, dict) else [r]
                for it in items:
                    t = it.get("text") or it.get("content") or str(it)                         if isinstance(it, dict) else str(it)
                    out.append(f"- {str(t)[:400]}")
            return out[:10]
        except Exception as e:  # noqa: BLE001
            print(f"[{uid}] search fail: {type(e).__name__}: {str(e)[:80]}",
                  flush=True)
            return []


class GraphitiSystem:
    """Graphiti(getzep):时序知识图谱,FalkorDB 后端(docker 单容器),
    LLM=haiku 抽取,嵌入=openai。add_episode 每集多次 LLM 调用——抽样先行。"""
    name = "graphiti"

    def __init__(self):
        import asyncio
        self._loop = asyncio.new_event_loop()
        from graphiti_core import Graphiti
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        from graphiti_core.llm_client.anthropic_client import AnthropicClient
        from graphiti_core.llm_client.config import LLMConfig
        driver = FalkorDriver(host="localhost", port=6379)
        self.g = Graphiti(graph_driver=driver,
                          llm_client=AnthropicClient(config=LLMConfig(
                              model="claude-haiku-4-5",
                              small_model="claude-haiku-4-5")))
        self._loop.run_until_complete(self.g.build_indices_and_constraints())

    def ingest(self, uid, sessions):
        from graphiti_core.nodes import EpisodeType
        from datetime import datetime, timezone

        async def go():
            for i, s in enumerate(sessions):
                d = (s.get("date") or "2000-01-01")[:10].replace("-00", "-01")
                try:
                    rt = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
                except ValueError:
                    rt = datetime(2000, 1, 1, tzinfo=timezone.utc)
                for attempt in range(3):
                    try:
                        await self.g.add_episode(
                            name=f"{uid}-s{i}", episode_body=sess_text(s),
                            source_description="chat session",
                            reference_time=rt, source=EpisodeType.message,
                            group_id=uid)
                        break
                    except Exception as e:  # noqa: BLE001
                        print(f"[{uid}] ep{i} retry {attempt}: "
                              f"{type(e).__name__}: {str(e)[:80]}", flush=True)
                        time.sleep(3)
        self._loop.run_until_complete(go())

    def search(self, uid, query):
        async def go():
            return await self.g.search(query, group_ids=[uid], num_results=10)
        try:
            edges = self._loop.run_until_complete(go())
            out = []
            for e in edges:
                fact = getattr(e, "fact", None) or str(e)
                va = getattr(e, "valid_at", None)
                out.append(f"- {fact}" + (f" (valid_at: {va})" if va else ""))
            return out[:10]
        except Exception as e:  # noqa: BLE001
            print(f"[{uid}] search fail: {type(e).__name__}: {str(e)[:80]}",
                  flush=True)
            return []


class LightRagSystem:
    """LightRAG(HKU):graph-RAG 家族;gpt-4o-mini 建图,openai 嵌入;
    only_need_context=True 只取素材喂我方读者(同台)。抽样先行。"""
    name = "lightrag"

    def __init__(self):
        import asyncio
        self._loop = asyncio.new_event_loop()
        self.stores: dict = {}

    def ingest(self, uid, sessions):
        import os
        from lightrag import LightRAG
        from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed
        wd = str(ROOT / "scratchpad" / "lightrag" / uid)
        os.makedirs(wd, exist_ok=True)

        async def go():
            rag = LightRAG(working_dir=wd,
                           llm_model_func=gpt_4o_mini_complete,
                           embedding_func=openai_embed)
            await rag.initialize_storages()
            try:
                from lightrag.kg.shared_storage import initialize_pipeline_status
                await initialize_pipeline_status()
            except Exception:  # noqa: BLE001
                pass
            await rag.ainsert([sess_text(s) for s in sessions])
            return rag
        self.stores[uid] = self._loop.run_until_complete(go())

    def search(self, uid, query):
        from lightrag import QueryParam
        rag = self.stores.get(uid)
        if rag is None:
            return []

        async def go():
            return await rag.aquery(query, param=QueryParam(
                mode="hybrid", only_need_context=True, top_k=10))
        try:
            ctx = self._loop.run_until_complete(go())
            txt = str(ctx or "").strip()
            # 其原生证据形态 = 完整结构化上下文包(实体/关系/原文块),
            # 整包交付,上限 8000 字符(截断伪影教训:只取前10行=表头)
            return [txt[:8000]] if txt else []
        except Exception as e:  # noqa: BLE001
            print(f"[{uid}] search fail: {type(e).__name__}: {str(e)[:80]}",
                  flush=True)
            return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["txtai", "lgstore", "amem", "bm25", "mstrata", "cognee", "graphiti", "lightrag"],
                    required=True)
    ap.add_argument("--limit-stores", type=int, default=0,
                    help="只跑前 N 库(抽样先行)")
    ap.add_argument("--questions-file", default="",
                    help="题源 jsonl(uid/qid/qtype/question/gold);仍限 15 库抽样交集")
    ap.add_argument("--out-suffix", default="", help="输出文件后缀")
    # b35c 接线(仅装载段,协议常量不动):自定义语料 / uid 清单 / 输出路径
    ap.add_argument("--vols", default="",
                    help="逗号分隔语料 json;默认保持 VOLS")
    ap.add_argument("--uids-file", default="",
                    help="uid 清单(每行一个);给出时替代 sample_stores() 的 picked,保持文件顺序")
    ap.add_argument("--out", default="",
                    help="结果 jsonl 完整路径;默认 results/wsc_s5_<name>{suffix}.jsonl")
    ap.add_argument("--store-root", default="",
                    help="需落盘系统的店根目录(cognee:system/data 根);默认保持各系统原值")
    ap.add_argument("--amem-repo", default="",
                    help="A-MEM 源码目录(相对 ROOT;设为环境变量 AMEM_REPO)")
    a = ap.parse_args()
    if a.amem_repo:
        os.environ["AMEM_REPO"] = str(ROOT / a.amem_repo)
    sysm = {"txtai": TxtaiSystem, "lgstore": LgStoreSystem,
            "amem": AmemSystem, "bm25": Bm25System,
            "mstrata": MemStrataSystem, "cognee": CogneeSystem,
            "graphiti": GraphitiSystem, "lightrag": LightRagSystem}[a.system]()
    if a.store_root and hasattr(sysm, "set_store_root"):
        sysm.set_store_root(ROOT / a.store_root)
    out_p = ROOT / a.out if a.out else ROOT / f"results/wsc_s5_{sysm.name}{a.out_suffix}.jsonl"
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"] for l in open(out_p, encoding="utf-8")}
    vols = a.vols.split(",") if a.vols else VOLS
    entries = {}
    for v in vols:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    picked, by_uid = sample_stores()
    if a.questions_file:
        by_uid = {}
        for q in (json.loads(l) for l in open(ROOT / a.questions_file, encoding="utf-8") if l.strip()):
            by_uid.setdefault(q["uid"], []).append(q)
    if a.uids_file:
        picked = [u.strip() for u in open(ROOT / a.uids_file, encoding="utf-8") if u.strip()]
    picked = [u for u in picked if u in by_uid]
    if a.limit_stores:
        picked = picked[:a.limit_stores]
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    fh = open(out_p, "a", encoding="utf-8")
    for uid in picked:
        qs = [q for q in by_uid[uid] if q["qid"] not in done]
        if not qs or uid not in entries:
            continue
        t0 = time.time()
        sessions = sorted(entries[uid].get("sessions", []),
                          key=lambda s: s.get("date", ""))
        sysm.ingest(uid, sessions)
        ingest_s = time.time() - t0
        for q in qs:
            t1 = time.time()
            mems = sysm.search(uid, q["question"])
            memtext = "\n".join(mems) if mems else "(no memories retrieved)"
            ans, ti, to = "", 0, 0
            for attempt in range(3):
                try:
                    r = client.messages.create(
                        model=READER_MODEL, max_tokens=300, temperature=0.0,
                        system=READER_SYS,
                        messages=[{"role": "user", "content":
                                   f"MEMORIES:\n{memtext}\n\n"
                                   f"USER'S NEW MESSAGE: {q['question']}"}])
                    ans = "".join(b.text for b in r.content if b.type == "text")
                    ti, to = r.usage.input_tokens, r.usage.output_tokens
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"retry {attempt}: {type(e).__name__}", flush=True)
                    time.sleep(3)
            v = judge.judge(q["question"], str(q["gold"]), ans, q["qtype"])
            fh.write(json.dumps({
                "question_id": q["qid"], "mode": sysm.name, "uid": uid,
                "question_type": q["qtype"], "question": q["question"],
                "gold_answer": q["gold"], "answer": ans, "memories_n": len(mems),
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "ingest_seconds": round(ingest_s, 1),
                "build_s": round(ingest_s, 1),
                "latency_s": round(time.time() - t1, 2),
                **getattr(sysm, "row_extra", {}),
                **getattr(sysm, "store_extra", {}).get(uid, {})},
                ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] ingested {len(sessions)} in {ingest_s:.0f}s, "
              f"answered {len(qs)}", flush=True)
    rows = [json.loads(l) for l in open(out_p, encoding="utf-8")]
    acc = sum(1 for r in rows if r.get("judge_correct")) / len(rows) * 100
    print(f"\n{sysm.name}: {acc:.2f}% (n={len(rows)})")
    print(f"judge total_usage (this process): {judge.total_usage}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
