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
        sys.path.insert(0, r"C:/Users/25243/AppData/Local/Temp/claude/"
                           r"D--ZZL-cluade/2b238d36-0e89-4591-ac1c-f5ffd6578795/"
                           r"scratchpad/A-mem")
        from agentic_memory.memory_system import AgenticMemorySystem
        self._cls = AgenticMemorySystem
        self.stores: dict = {}

    def ingest(self, uid, sessions):
        m = self._cls(model_name="all-MiniLM-L6-v2",
                      llm_backend="openai", llm_model="gpt-4o-mini")
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

    def ingest(self, uid, sessions):
        c = self._c

        async def go():
            for s in sessions:
                await c.add(sess_text(s), dataset_name=uid)
            await c.cognify(datasets=[uid])
        self._run(go())

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["txtai", "lgstore", "amem", "bm25", "mstrata", "cognee"],
                    required=True)
    ap.add_argument("--limit-stores", type=int, default=0,
                    help="只跑前 N 库(抽样先行)")
    ap.add_argument("--questions-file", default="",
                    help="题源 jsonl(uid/qid/qtype/question/gold);仍限 15 库抽样交集")
    ap.add_argument("--out-suffix", default="", help="输出文件后缀")
    a = ap.parse_args()
    sysm = {"txtai": TxtaiSystem, "lgstore": LgStoreSystem,
            "amem": AmemSystem, "bm25": Bm25System,
            "mstrata": MemStrataSystem, "cognee": CogneeSystem}[a.system]()
    out_p = ROOT / f"results/wsc_s5_{sysm.name}{a.out_suffix}.jsonl"
    done = set()
    if out_p.exists():
        done = {json.loads(l)["question_id"] for l in open(out_p, encoding="utf-8")}
    entries = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    picked, by_uid = sample_stores()
    if a.questions_file:
        by_uid = {}
        for q in (json.loads(l) for l in open(ROOT / a.questions_file, encoding="utf-8")):
            by_uid.setdefault(q["uid"], []).append(q)
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
                "latency_s": round(time.time() - t1, 2)},
                ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] ingested {len(sessions)} in {ingest_s:.0f}s, "
              f"answered {len(qs)}", flush=True)
    rows = [json.loads(l) for l in open(out_p, encoding="utf-8")]
    acc = sum(1 for r in rows if r.get("judge_correct")) / len(rows) * 100
    print(f"\n{sysm.name}: {acc:.2f}% (n={len(rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
