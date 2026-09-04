# -*- coding: utf-8 -*-
"""批 37:检索侧 RAG 基线家族(同题集 / 同读者 / 同判官,只换"选哪些记忆")。

动机:此前的对照只有 dense top-10 一条直读臂,读者被问"QVF 相对**其他 RAG
方法**如何"时无从作答。本脚本把检索侧的常见做法各做成一条臂,读者渲染与
判官口径**逐字冻结**为批 33-A/35 的 direct 臂,使唯一自由度是"选中集合"。

冻结件(import 而非复制):
  - 记忆装配 / 渲染 / TODAY 日期:ext_direct_arm._memories / reader_content /
    _query_date / READER_SYSTEM / _retriever_cls
  - 读者调用:lb_reader_arm.call_reader(anthropic 分支 = max_tokens 800、
    temperature 0、system 直传)——与 results/b33A_direct.jsonl 同一函数
  - 判官:qvf.judge.ClaudeJudge()(默认 QVF_JUDGE_MODEL)
  - 稠密底座:qvf.retrieval.OpenAIDenseRetriever(text-embedding-3-small),
    嵌入落盘缓存后各臂共用同一份向量,消除"换了嵌入器"的混淆。

臂(--variant):
  direct / dense_top10       dense top-10(归档直读基线同 k 同序;两名同义)
  dense_top30 / dense_top50 / dense_top100
                             同检索器、更深的 k(预算匹配对照)
  session_top5   以**整个会话**(日期+全部轮次拼接)为索引单元,取 top-5 会话,
                 渲染这些会话的全部轮次
  hybrid_rrf     BM25 top-30 与 dense top-30 按 RRF(k=60)融合,保留 top-10
  mmr            OllamaDenseRetriever.retrieve_mmr(lam=0.7, pool=50)top-10
  recency        dense top-30 后按 sim * exp(-age/tau) 重排,tau=5 年,age 相对
                 问题的 Today;保留 top-10
  asof_filter    先丢弃晚于问题 Today 的记忆(月/日为 00 视作年初),再 dense top-10
  rewrite        haiku 把问题改写成检索查询(点名槽位与时间约束),用改写句 dense top-10
  rerank         dense top-30 → haiku 一次调用给 30 条打 0-10 分 → 取 top-10
  dry_verify     零读者零判官:复算 dense top-10 并用 count_tokens 与 b33A_direct
                 的 usage_input_tokens 逐题比对(证明本脚本渲染与旧臂一致)

选中集合一律按记忆流原序(时序)呈现给读者 —— 与 OllamaDenseRetriever.retrieve
的 `sorted(top)` 口径一致,保证与 direct 臂唯一的差别是"选了哪些"。

用法:
  QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/b37_rag_variants.py \
      --variant build_cache
  QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/b37_rag_variants.py \
      --variant dense_top30 --out results/b37_dense_top30.jsonl

批 39(规模轴 L2,30 店 / 120 题)——换语料时**必须**换缓存文件:
  QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/b37_rag_variants.py \
      --variant build_cache --data data/wikistate_long_L2_b33.json \
      --questions data/wsc_long_L1_questions.jsonl \
      --emb-cache results/b39_emb_L2_turns.npz --emb-cache-sess ""
  QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/b37_rag_variants.py \
      --variant dense_top50 --data data/wikistate_long_L2_b33.json \
      --questions data/wsc_long_L1_questions.jsonl \
      --emb-cache results/b39_emb_L2_turns.npz --emb-cache-sess "" \
      --out results/b39_dense_top50_L2.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

import numpy as np  # noqa: E402

from qvf.judge import ClaudeJudge  # noqa: E402
from qvf.retrieval import (BM25Retriever, MemoryItem,  # noqa: E402
                           OpenAIDenseRetriever, _tokenize)
from ext_direct_arm import (READER_SYSTEM, _memories, _query_date,  # noqa: E402
                            _retriever_cls, reader_content)
# 批 40:改从 lb_reader_arm_b36b 取 call_reader(原 lb_reader_arm.call_reader
# 的严格超集——加了 max_tokens 参数与"仅 haiku 发 temperature"的显式判断;
# 对 haiku 走同一 anthropic 分支、同样不传 max_tokens 之外的任何新参数,
# 批 37/39 的默认行为逐字节不变)。
from lb_reader_arm_b36b import call_reader  # noqa: E402

READER = "anthropic:claude-haiku-4-5"          # 默认值不变;--reader 可覆盖
READER_MAX_TOKENS = 800                          # 默认值不变;--max-tokens 可覆盖
EMB_MODEL = "text-embedding-3-small"

# 读者侧现价($/百万 token),与 scripts/b36_plain_fullctx.py 同表(批 40 起
# 打印真实读者花费,不再写死 haiku 单价)。
PRICES = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5": (2.0, 10.0)}
DEFAULT_PRICE = (3.0, 15.0)


def price_of(model: str):
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    return DEFAULT_PRICE
DATA = "data/wikistate_full_ALL_v24.json"
QUESTIONS = "results/b35_questions_sample36.jsonl"
CACHE_TURN = ROOT / "results" / "b37_emb_turns.npz"
CACHE_SESS = ROOT / "results" / "b37_emb_sessions.npz"

RRF_K = 60                      # RRF 常数(Cormack 2009 缺省)
TAU_DAYS = 5 * 365.25           # recency 臂的"半衰期"(按 spec 用 exp(-age/tau))
_TODAY_RE = re.compile(r"\(Today is ([0-9][0-9-]*)\.?\)")

_print_lock = threading.Lock()
_write_lock = threading.Lock()
_retr_lock = threading.RLock()
_USAGE = {"reader_in": 0, "reader_out": 0, "retr_in": 0, "retr_out": 0,
          "judge_in": 0, "judge_out": 0}


def _log(msg: str):
    with _print_lock:
        print(msg, flush=True)


# ── 日期工具 ────────────────────────────────────────────────────
def parse_date(s: str) -> date:
    """月/日为 00 视作年初(语料里 120 个会话日期形如 1774-00-00)。"""
    y, m, d = (str(s).split("-") + ["0", "0"])[:3]
    return date(int(y), max(1, int(m or 0)), max(1, int(d or 0)))


def retrieval_today(entry: dict, question: str) -> date:
    """检索侧的 Today:问题自带 (Today is X.) 用之;否则用**最晚会话日期**
    (spec 口径)。注意这与渲染给读者的 TODAY'S DATE 行(ext_direct_arm.
    _query_date,缺省是末链日期 +1 月)是两回事,渲染保持逐字冻结。"""
    m = _TODAY_RE.search(question or "")
    if m:
        return parse_date(m.group(1))
    ds = [s.get("date", "") for s in entry.get("sessions", []) if s.get("date")]
    return parse_date(max(ds)) if ds else date(9999, 12, 31)


# ── 记忆装配 ────────────────────────────────────────────────────
def session_memories(entry: dict) -> List[MemoryItem]:
    """会话级索引单元:日期 + 该会话全部轮次拼接(session_top5 臂用)。"""
    uid = entry.get("uid", "")
    out: List[MemoryItem] = []
    for si, sess in enumerate(entry.get("sessions", [])):
        d = sess.get("date", "")
        body = "\n".join(str(t) for t in sess.get("turns", []))
        out.append(MemoryItem(memory_id=f"{uid}/s{si}",
                              content=f"[{d}]\n{body}",
                              metadata={"session_id": f"s{si}",
                                        "session_date": d,
                                        "sess_index": si}))
    return out


def expand_sessions(entry: dict, sess_items: List[MemoryItem]) -> List[MemoryItem]:
    """把选中的会话展开成轮次级条目(id 与 direct 臂同构),按时序。"""
    want = {(m.metadata or {}).get("session_id") for m in sess_items}
    return [m for m in _memories(entry)
            if (m.metadata or {}).get("session_id") in want]


# ── 嵌入缓存(各臂共用同一份向量) ──────────────────────────────
def _cache_key(mems: List[MemoryItem]) -> Tuple:
    return (EMB_MODEL, mems[0].memory_id if mems else "", len(mems))


def load_emb_cache():
    """把落盘 npz 灌进 OpenAIDenseRetriever 的类级缓存(**未归一化**,与
    构造函数写入缓存的值同源),此后构造检索器零 API 调用。"""
    n = 0
    for path, builder in ((CACHE_TURN, _memories), (CACHE_SESS, session_memories)):
        if not path or not path.exists():
            continue
        z = np.load(path)
        entries = load_entries()
        for uid in z.files:
            e = entries.get(uid)
            if e is None:
                continue
            mems = builder(e)
            arr = np.asarray(z[uid], dtype="float32")
            if arr.shape[0] != len(mems):
                continue
            OpenAIDenseRetriever._cache[_cache_key(mems)] = arr
            n += 1
    return n


def build_cache(uids: List[str], entries: dict, workers: int = 4):
    for path, builder in ((CACHE_TURN, _memories), (CACHE_SESS, session_memories)):
        if not path:            # --emb-cache-sess "" :只建轮次级(批 39 无会话臂)
            continue
        got: Dict[str, np.ndarray] = {}
        if path.exists():
            z = np.load(path)
            got = {k: np.asarray(z[k]) for k in z.files}
        todo = [u for u in uids if u not in got]
        _log(f"[cache] {path.name}: have {len(got)}, need {len(todo)}")

        def one(uid):
            mems = builder(entries[uid])
            OpenAIDenseRetriever(mems)          # 走类自身的 _embed
            return uid, OpenAIDenseRetriever._cache[_cache_key(mems)]

        if todo:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for uid, arr in ex.map(one, todo):
                    got[uid] = arr
                    _log(f"[cache] {path.name} {uid} {arr.shape}")
            np.savez(path, **got)
    _log("[cache] done")


# ── 打分原语(复用检索器自身的嵌入/BM25,不另造轮子) ────────────
def dense_scores(retr, query: str) -> np.ndarray:
    q = retr._embed([query])[0]
    qn = q / (np.linalg.norm(q) or 1.0)
    return retr._embs @ qn          # retr._embs 已在构造时归一化


def bm25_scores(br: BM25Retriever, query: str) -> np.ndarray:
    if br._bm25 is None:
        return np.zeros(len(br.memories), dtype="float32")
    return np.asarray(br._bm25.get_scores(_tokenize(query)), dtype="float32")


def chrono(mems: List[MemoryItem], idx) -> List[MemoryItem]:
    return [mems[i] for i in sorted(idx)]


# ── 检索侧的 LLM 小步骤 ────────────────────────────────────────
REWRITE_PROMPT = (
    "Rewrite the user's question into a short retrieval query for searching "
    "their past chat logs. The query must name the attribute/slot being asked "
    "about (e.g. employer, position held, place of residence, spouse) and the "
    "time constraint if there is one. Output ONLY the query, no quotes, no "
    "explanation.\n\nQuestion: {q}\n\nQuery:")


def do_rewrite(question: str) -> Tuple[str, int, int]:
    import anthropic
    cli = do_rewrite._c = getattr(do_rewrite, "_c", None) or anthropic.Anthropic()
    r = cli.messages.create(model="claude-haiku-4-5", max_tokens=100,
                            temperature=0.0,
                            messages=[{"role": "user",
                                       "content": REWRITE_PROMPT.format(q=question)}])
    txt = "".join(b.text for b in r.content if b.type == "text").strip()
    return (txt or question), r.usage.input_tokens, r.usage.output_tokens


RERANK_PROMPT = (
    "You are a retrieval reranker. Below are {n} numbered excerpts from a "
    "user's past conversations, each with its date. Score how relevant each "
    "excerpt is for answering the user's question, from 0 (irrelevant) to 10 "
    "(directly contains the needed information).\n\n"
    "QUESTION: {q}\n\nEXCERPTS:\n{cands}\n\n"
    "Output ONLY a JSON object of the form "
    '{{"scores": [{{"i": 1, "s": 0}}, ...]}} with one entry for every '
    "excerpt number, and nothing else.")


def do_rerank(question: str, cands: List[MemoryItem]) -> Tuple[List[float], int, int]:
    import anthropic
    cli = do_rerank._c = getattr(do_rerank, "_c", None) or anthropic.Anthropic()
    body = "\n".join(
        f"[{i + 1}] ({(m.metadata or {}).get('session_date') or 'undated'}) "
        f"{m.content}" for i, m in enumerate(cands))
    r = cli.messages.create(
        model="claude-haiku-4-5", max_tokens=1500, temperature=0.0,
        messages=[{"role": "user",
                   "content": RERANK_PROMPT.format(n=len(cands), q=question,
                                                   cands=body)}])
    txt = "".join(b.text for b in r.content if b.type == "text")
    scores = [0.0] * len(cands)
    try:
        m = re.search(r"\{.*\}", txt, re.S)
        obj = json.loads(m.group(0)) if m else {}
        for it in obj.get("scores", []):
            i = int(it.get("i", 0)) - 1
            if 0 <= i < len(cands):
                scores[i] = float(it.get("s", 0))
    except Exception as e:                                   # noqa: BLE001
        _log(f"  rerank parse failed ({type(e).__name__}); falling back to "
             f"dense order")
        scores = [float(len(cands) - i) for i in range(len(cands))]
    return scores, r.usage.input_tokens, r.usage.output_tokens


# ── 每题检索 ────────────────────────────────────────────────────
class Store:
    """按 uid 惰性构建的检索器集合(轮次级 dense / BM25、会话级 dense)。"""

    def __init__(self, entries: dict, cls):
        self.entries, self.cls = entries, cls
        self.turn_mem: Dict[str, List[MemoryItem]] = {}
        self.dense: Dict[str, object] = {}
        self.bm25: Dict[str, BM25Retriever] = {}
        self.sess_mem: Dict[str, List[MemoryItem]] = {}
        self.sess_dense: Dict[str, object] = {}

    def turns(self, uid):
        with _retr_lock:
            if uid not in self.turn_mem:
                self.turn_mem[uid] = _memories(self.entries[uid])
            return self.turn_mem[uid]

    def dense_r(self, uid):
        with _retr_lock:
            if uid not in self.dense:
                self.dense[uid] = self.cls(self.turns(uid))
            return self.dense[uid]

    def bm25_r(self, uid):
        with _retr_lock:
            if uid not in self.bm25:
                self.bm25[uid] = BM25Retriever(self.turns(uid))
            return self.bm25[uid]

    def sessions(self, uid):
        with _retr_lock:
            if uid not in self.sess_mem:
                self.sess_mem[uid] = session_memories(self.entries[uid])
            return self.sess_mem[uid]

    def sess_dense_r(self, uid):
        with _retr_lock:
            if uid not in self.sess_dense:
                self.sess_dense[uid] = self.cls(self.sessions(uid))
            return self.sess_dense[uid]


def retrieve(variant: str, store: Store, q: dict) -> Tuple[List[MemoryItem], dict]:
    """返回 (按时序排列的 MemoryItem 列表, 附加字段 dict)。"""
    uid, question = q["uid"], q["question"]
    entry = store.entries[uid]
    mems = store.turns(uid)
    extra = {"retrieval_input_tokens": 0, "retrieval_output_tokens": 0}

    if variant in ("dense_top30", "dense_top50", "dense_top10", "dense_top100",
                   "direct"):
        # `direct` = dense top-10,与归档 direct 臂同 k 同序(批 39 起用这个
        # 别名,使 L2 上的产物名 b39_direct_L2.jsonl 与"直读基线"对齐)。
        k = {"direct": 10, "dense_top10": 10, "dense_top30": 30,
             "dense_top50": 50, "dense_top100": 100}[variant]
        return store.dense_r(uid).retrieve(question, top_k=k), extra

    if variant == "session_top5":
        got = store.sess_dense_r(uid).retrieve(question, top_k=5)
        extra["retrieved_session_ids"] = [m.memory_id for m in got]
        return expand_sessions(entry, got), extra

    if variant == "mmr":
        return store.dense_r(uid).retrieve_mmr(question, top_k=10, lam=0.7,
                                               pool=50), extra

    if variant == "hybrid_rrf":
        ds = dense_scores(store.dense_r(uid), question)
        bs = bm25_scores(store.bm25_r(uid), question)
        d_rank = sorted(range(len(mems)), key=lambda i: -float(ds[i]))[:30]
        b_rank = sorted(range(len(mems)), key=lambda i: -float(bs[i]))[:30]
        fused: Dict[int, float] = {}
        for lst in (d_rank, b_rank):
            for r, i in enumerate(lst):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
        top = sorted(fused, key=lambda i: -fused[i])[:10]
        extra["n_bm25_only"] = len(set(b_rank) - set(d_rank))
        return chrono(mems, top), extra

    if variant == "recency":
        ds = dense_scores(store.dense_r(uid), question)
        pool = sorted(range(len(mems)), key=lambda i: -float(ds[i]))[:30]
        t0 = retrieval_today(entry, question)
        def sc(i):
            d = parse_date((mems[i].metadata or {}).get("session_date") or "9999-01-01")
            age = max(0.0, (t0 - d).days)
            return float(ds[i]) * math.exp(-age / TAU_DAYS)
        top = sorted(pool, key=lambda i: -sc(i))[:10]
        extra["retrieval_today"] = t0.isoformat()
        return chrono(mems, top), extra

    if variant == "asof_filter":
        # 先按 Today 掩掉"未来"记忆,再在剩余集合上取 dense top-10。
        # 用同一份缓存向量打分 + 掩码,与"对子集另建检索器"逐位等价
        # (余弦分是逐条独立的),但不产生额外嵌入调用。
        t0 = retrieval_today(entry, question)
        keep = [i for i, m in enumerate(mems)
                if parse_date((m.metadata or {}).get("session_date")
                              or "9999-01-01") <= t0]
        extra["retrieval_today"] = t0.isoformat()
        extra["n_dropped_future"] = len(mems) - len(keep)
        if not keep:
            return [], extra
        ds = dense_scores(store.dense_r(uid), question)
        top = sorted(keep, key=lambda i: -float(ds[i]))[:10]
        return chrono(mems, top), extra

    if variant == "rewrite":
        rq, ti, to = do_rewrite(question)
        extra.update(retrieval_input_tokens=ti, retrieval_output_tokens=to,
                     rewritten_query=rq)
        return store.dense_r(uid).retrieve(rq, top_k=10), extra

    if variant == "rerank":
        ds = dense_scores(store.dense_r(uid), question)
        pool = sorted(range(len(mems)), key=lambda i: -float(ds[i]))[:30]
        cands = [mems[i] for i in pool]
        scores, ti, to = do_rerank(question, cands)
        order = sorted(range(len(pool)), key=lambda j: (-scores[j], j))[:10]
        extra.update(retrieval_input_tokens=ti, retrieval_output_tokens=to,
                     rerank_scores=[scores[j] for j in order])
        return chrono(mems, [pool[j] for j in order]), extra

    raise ValueError(variant)


# ── 题集 / 语料 ─────────────────────────────────────────────────
_ENTRIES: dict = {}


def load_entries() -> dict:
    global _ENTRIES
    if not _ENTRIES:
        _ENTRIES = {e["uid"]: e for e in
                    json.loads((ROOT / DATA).read_text(encoding="utf-8"))}
    return _ENTRIES


def load_questions(path: str) -> List[dict]:
    return [json.loads(l) for l in open(ROOT / path, encoding="utf-8") if l.strip()]


# ── dry_verify:证明本脚本的渲染与 b33A_direct 逐题同 token ───────
def dry_verify(store: Store, qs: List[dict], n: int):
    import anthropic
    cli = anthropic.Anthropic()
    ref = {}
    for l in open(ROOT / "results/b33A_direct.jsonl", encoding="utf-8"):
        r = json.loads(l)
        ref.setdefault(r["question_id"], r)
    same = diff = 0
    for q in qs[:n]:
        got = store.dense_r(q["uid"]).retrieve(q["question"], top_k=10)
        user = reader_content(q["question"], got,
                              _query_date(store.entries[q["uid"]], q["question"]))
        c = cli.messages.count_tokens(
            model="claude-haiku-4-5", system=READER_SYSTEM,
            messages=[{"role": "user", "content": user}])
        want = ref[q["qid"]]["usage_input_tokens"]
        ok = c.input_tokens == want
        same += ok
        diff += (not ok)
        _log(f"[verify] {q['qid']} count={c.input_tokens} b33A={want} "
             f"{'MATCH' if ok else 'DIFF'}")
    _log(f"DRY VERIFY: {same} match / {diff} differ (of {same + diff})")


# ── 主流程 ──────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--questions", default=QUESTIONS)
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    # 批 39:换语料(L2,30 店 x ~1350 轮)时向量缓存必须另存一份,否则
    # _cache_key 只按 (模型, 首条 id, 条数) 判同,不同语料会互相污染。
    ap.add_argument("--emb-cache", default=str(CACHE_TURN),
                    help="轮次级嵌入缓存 npz 路径")
    ap.add_argument("--emb-cache-sess", default=str(CACHE_SESS),
                    help="会话级嵌入缓存 npz 路径;传空串则不建/不加载")
    ap.add_argument("--reader", default=READER,
                    help="anthropic:<model>;默认 claude-haiku-4-5(原行为不变)")
    ap.add_argument("--max-tokens", type=int, default=READER_MAX_TOKENS,
                    help="读者 max_tokens;默认 800(原行为不变)。sonnet-5 "
                         "默认开思考,同一预算同时封顶思考与可见文本,批 40 "
                         "起对 sonnet-5 一律传 4000")
    a = ap.parse_args()
    globals()["READER"] = a.reader
    reader_model = a.reader.split(":", 1)[1]

    backend = os.environ.get("QVF_EMBED_BACKEND", "")
    if backend != "openai":
        raise SystemExit("set QVF_EMBED_BACKEND=openai exactly (same dense "
                         "stack / model as the archived direct arm)")
    globals()["DATA"] = a.data
    globals()["CACHE_TURN"] = Path(a.emb_cache) if a.emb_cache else None
    globals()["CACHE_SESS"] = Path(a.emb_cache_sess) if a.emb_cache_sess else None
    entries = load_entries()
    qs = load_questions(a.questions)
    if a.limit:
        qs = qs[:a.limit]
    uids = sorted({q["uid"] for q in qs})
    missing = [u for u in uids if u not in entries]
    if missing:
        raise SystemExit(f"uids missing from {a.data}: {missing[:5]}")

    if a.variant == "build_cache":
        build_cache(uids, entries, a.workers)
        return 0

    n_cached = load_emb_cache()
    _log(f"[emb] preloaded {n_cached} cached embedding blocks")
    store = Store(entries, _retriever_cls())

    if a.variant == "dry_verify":
        dry_verify(store, qs, a.limit or 8)
        return 0

    outp = ROOT / (a.out or f"results/b37_{a.variant}.jsonl")
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if outp.exists():
        for l in open(outp, encoding="utf-8"):
            try:
                done.add(json.loads(l)["question_id"])
            except Exception:                                # noqa: BLE001
                pass
    todo = [q for q in qs if q["qid"] not in done]
    _log(f"[{a.variant}] {len(todo)} to run ({len(done)} already done)")
    fh = open(outp, "a", encoding="utf-8")
    judge = ClaudeJudge()
    t_start = time.time()
    counter = {"n": 0, "ok": 0}

    def work(q):
        qid, uid = q["qid"], q["uid"]
        tr0 = time.time()
        try:
            got, extra = retrieve(a.variant, store, q)
        except Exception as e:                               # noqa: BLE001
            _log(f"[{qid}] RETRIEVAL FAIL {type(e).__name__}: {str(e)[:120]}")
            return
        t_retr = time.time() - tr0
        user = reader_content(q["question"], got,
                              _query_date(entries[uid], q["question"]))
        raw, ti, to, lat, stop = "", 0, 0, 0.0, ""
        for attempt in range(3):
            try:
                raw, ti, to, lat, stop = call_reader(READER, READER_SYSTEM,
                                                      user, a.max_tokens)
                break
            except Exception as e:                           # noqa: BLE001
                _log(f"[{qid}] reader retry {attempt}: {type(e).__name__}: "
                     f"{str(e)[:90]}")
                time.sleep(4)
        else:
            _log(f"[{qid}] READER FAILED 3x — row skipped")
            return
        v = judge.judge(q["question"], str(q["gold"]), raw, q.get("qtype"))
        row = {
            "question_id": qid, "mode": f"{a.variant}:{READER}", "uid": uid,
            "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": q["gold"], "answer": raw[:2000],
            "protocol_deviation": False,
            "usage_input_tokens": ti, "usage_output_tokens": to,
            "judge_correct": v.correct, "judge_reason": v.reason,
            "judge_input_tokens": v.usage_input_tokens,
            "judge_output_tokens": v.usage_output_tokens,
            "latency_s": round(lat, 2),
            "variant": a.variant,
            "n_retrieved": len(got),
            "retrieved_memory_ids": [m.memory_id for m in got],
            "retrieval_latency_s": round(t_retr, 2),
            "reader_model": reader_model,
            "reader_max_tokens": a.max_tokens,
            "stop_reason": stop,
        }
        row.update(extra)
        with _write_lock:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            counter["n"] += 1
            counter["ok"] += bool(v.correct)
            _USAGE["reader_in"] += ti or 0
            _USAGE["reader_out"] += to or 0
            _USAGE["retr_in"] += extra.get("retrieval_input_tokens") or 0
            _USAGE["retr_out"] += extra.get("retrieval_output_tokens") or 0
            _USAGE["judge_in"] += v.usage_input_tokens or 0
            _USAGE["judge_out"] += v.usage_output_tokens or 0
        _log(f"[{qid}] {a.variant} k={len(got)} {v.correct} "
             f"({lat:.1f}s r/{t_retr:.1f}s)")

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(work, todo))
    fh.close()
    n, ok = counter["n"], counter["ok"]
    pin, pout = price_of(reader_model)
    reader_cost = (_USAGE["reader_in"] + _USAGE["retr_in"]) / 1e6 * pin + \
                  (_USAGE["reader_out"] + _USAGE["retr_out"]) / 1e6 * pout
    _log(f"B37 {a.variant} DONE: {ok}/{n} = {ok / max(1, n) * 100:.1f}% | "
         f"reader in {_USAGE['reader_in']} out {_USAGE['reader_out']} | "
         f"retrieval in {_USAGE['retr_in']} out {_USAGE['retr_out']} | "
         f"judge in {_USAGE['judge_in']} out {_USAGE['judge_out']} | "
         f"reader-side({reader_model}) $ {reader_cost:.3f} | "
         f"wall {time.time() - t_start:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
