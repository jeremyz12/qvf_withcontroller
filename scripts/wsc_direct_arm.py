# -*- coding: utf-8 -*-
"""WSC 稠密直读基线臂(dense_direct 同口径,自定义题集跑批器;对照 complex_query_arm)。

逐题三步:
  ① RETRIEVE:条目会话流按 eval.stale_chain_dataset.load_stale_chain 同口径
     装配记忆条(memory_id=uid/s{si}#r{ri},content=str(turn),metadata 带
     session_id/session_date),用 run_decisive_stale 的 dense_direct 同款
     稠密检索器对问题原文取 top-10(QVF_EMBED_BACKEND 驱动:缺省 ollama
     nomic-embed-text,openai[:model] 切纯 API 栈);
  ② READ:一次 haiku 调用,日常助手口吻(READER_SYSTEM 逐字节 = framing_arm
     猴补的修正框定基线提示词),用户内容 = framing_arm _fmt 同款带日期誊录
     行 + TODAY'S DATE + 问题,temperature 0,max_tokens 与 complex_query_arm
     的 READ 步同值;
  ③ JUDGE:qvf.judge.ClaudeJudge 与各臂同口径;gold 为 null 时跳过判官。

gold 只进判官,绝不进读者调用。

复制而非导入的三小件(scripts/smoke_wsc_direct_arm.py 按 AST 提取原件逐一
断言等价,零 API 零网络):
  - _retriever_cls  ← run_decisive_stale._dense_retriever_cls(该模块级联
    导入 qvf.engine_bridge → 旧引擎 qvf_validity_admission 等重依赖);
  - reader_content  ← framing_arm._fmt(framing_arm 模块级即执行 argparse
    并整卷跑批,不可导入);
  - _query_date     ← complex_query_arm._query_date(其模块级导入
    wt_qvf_prototype,后者 import 时 setdefault QVF_EMBED_BACKEND=openai,
    会悄改本臂检索后端缺省值)。

用法:
  QVF_EMBED_BACKEND=openai python scripts/wsc_direct_arm.py \
      --data data/wikistate_full_P108_w2.json data/wikistate_full_P54_w2.json \
             data/wikistate_full_P551.json \
      --questions results/wsc_s5_all.jsonl \
      --out results/wsc_direct_s5_all.jsonl --resume
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402

from qvf import config  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from qvf.retrieval import MemoryItem  # noqa: E402

# 读者与 complex_query_arm 的 READ 步同款:qvf.config 驱动的小模型
# (QVF_ADAPTER_MODEL,默认 haiku-4-5),max_tokens/temperature 同值。
MODEL = config.DEFAULT_ADAPTER_MODEL
READER_MAX_TOKENS = 1000
TOP_K = 10  # 与 run_decisive_stale.TOP_K 同值

_TODAY_RE = re.compile(r"\(Today is ([0-9][0-9-]*)\.?\)")

# 逐字节复用 framing_arm 猴补的修正框定基线提示词(= complex_query_arm 的
# READER_SYSTEM;冒烟按 AST 对两处原件断言字节相等)。
READER_SYSTEM = (
    "You are the user's personal AI assistant. You will be shown excerpts "
    "from your past conversations with this user (retrieved from memory, "
    "each dated), followed by the user's new message. Reply to the new "
    "message naturally and helpfully in 1-3 sentences, as you would in an "
    "everyday chat."
)


def _client():
    return anthropic.Anthropic()


# ── ① RETRIEVE:记忆装配 + dense_direct 同款检索器 ─────────────
def _retriever_cls():
    """与 run_decisive_stale._dense_retriever_cls 逐字同逻辑(复制而非导入,
    理由见模块头;冒烟断言四种 QVF_EMBED_BACKEND 取值下选类一致)。"""
    backend = os.environ.get("QVF_EMBED_BACKEND", "ollama")
    if backend.startswith("openai"):
        from functools import partial

        from qvf.retrieval import OpenAIDenseRetriever

        if ":" in backend:
            return partial(OpenAIDenseRetriever, model=backend.split(":", 1)[1])
        return OpenAIDenseRetriever
    from qvf.retrieval import OllamaDenseRetriever

    return OllamaDenseRetriever


def _memories(entry: dict) -> List[MemoryItem]:
    """与 eval.stale_chain_dataset.load_stale_chain 的记忆装配逐位一致
    (只取记忆流,不建问题;冒烟对合成条目断言逐字段相等)。"""
    uid = entry.get("uid", "")
    out: List[MemoryItem] = []
    for si, sess in enumerate(entry.get("sessions", [])):
        for ri, turn in enumerate(sess.get("turns", [])):
            out.append(MemoryItem(
                memory_id=f"{uid}/s{si}#r{ri}",
                content=str(turn),
                metadata={"session_id": f"s{si}",
                          "session_date": sess.get("date", "")},
            ))
    return out


# ── ② READ:带日期誊录渲染(framing_arm._fmt 同款) ─────────────
def reader_content(query, memories, query_date=None) -> str:
    """与 scripts/framing_arm.py 的 _fmt 逐位一致(冒烟按 AST 提取原件断言
    输出逐字节相等)。"""
    lines = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]
    for m in memories:
        d = (m.metadata or {}).get("session_date") or "undated"
        lines.append(f"[{d}] {m.content}")
    lines.append("")
    if query_date:
        lines.append(f"TODAY'S DATE: {query_date}")
        lines.append("")
    lines.append(f"USER'S NEW MESSAGE: {query}")
    return "\n".join(lines)


def _query_date(entry: dict, question: str) -> str:
    """TODAY'S DATE:问题自带 (Today is X.) 前缀则用 X(S5/wiki 卷);否则
    末链日期 +1 月(与 eval.stale_chain_dataset.load_stale_chain 同算式;
    与 complex_query_arm._query_date 逐位一致,冒烟断言)。"""
    m = _TODAY_RE.search(question or "")
    if m:
        return m.group(1)
    try:
        last = str(entry["chain"][-1]["date"])
        y, mo, d = (int(x) for x in last.split("-"))
        mo += 1
        if mo > 12:
            y, mo = y + 1, 1
        return f"{y}-{mo:02d}-{d:02d}"
    except Exception:  # noqa: BLE001
        return ""


# ── 题目装配(与 complex_query_arm 同款读法) ─────────────────
def _load_entries(paths: List[str]) -> dict:
    """合并多份 chain 架构数据,按 uid 去重(同 gen_wikistate_complex)。"""
    by_uid: dict = {}
    for f in paths:
        for e in json.loads(Path(f).read_text(encoding="utf-8")):
            by_uid.setdefault(e["uid"], e)
    return by_uid


def _questions_from_jsonl(path: str) -> List[dict]:
    """gen_wikistate_complex 输出行:uid/qid/qtype/question/gold/basis。"""
    out = []
    for l in open(path, encoding="utf-8"):
        s = l.strip()
        if s:
            out.append(json.loads(s))
    return out


# ── 主流程 ───────────────────────────────────────────────────
def run(data_paths: List[str], questions_path: str, out_path: str,
        uids: Optional[List[str]], resume: bool):
    entries = _load_entries(data_paths)
    qs = _questions_from_jsonl(questions_path)
    if uids:
        keep = set(uids)
        qs = [q for q in qs if q["uid"] in keep]
    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if resume and outp.exists():
        for l in open(outp, encoding="utf-8"):
            try:
                done.add(json.loads(l)["question_id"])
            except Exception:  # noqa: BLE001
                pass
    fout = open(outp, "a" if resume else "w", encoding="utf-8")
    client = _client()
    judge = ClaudeJudge()
    retr_cls = _retriever_cls()
    retr_cache: dict = {}
    n_run = n_ok = n_null = 0
    for q in qs:
        qid, uid = q["qid"], q["uid"]
        if qid in done:
            continue
        t0 = time.time()
        entry = entries.get(uid, {})

        # ① 稠密检索(问题原文,top-10;检索器按 uid 缓存,嵌入只算一次)
        if uid not in retr_cache:
            mems = _memories(entry)
            retr_cache[uid] = retr_cls(mems) if mems else None
        retr = retr_cache[uid]
        retrieved = retr.retrieve(q["question"], top_k=TOP_K) if retr else []

        # ② 读者(只见带日期誊录 + 日期 + 问题;gold 绝不进此调用)
        qdate = _query_date(entry, q["question"])
        rr = client.messages.create(
            model=MODEL, max_tokens=READER_MAX_TOKENS, temperature=0.0,
            system=[{"type": "text", "text": READER_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": reader_content(q["question"], retrieved,
                                                 qdate)}],
        )
        answer = "".join(b.text for b in rr.content if b.type == "text")

        # ③ 判官(gold 仅在此出现;gold=null 跳过,另行评审)
        gold = q.get("gold")
        if gold is None:
            jc, jr = None, "gold=null: judged separately via rubric"
            n_null += 1
        else:
            v = judge.judge(q["question"], str(gold), answer, q.get("qtype"))
            jc, jr = v.correct, v.reason
            n_ok += bool(jc)

        row = {
            "question_id": qid, "mode": "wsc_direct", "uid": uid,
            "question_type": q.get("qtype"), "question": q["question"],
            "gold_answer": gold, "answer": answer,
            "retrieved_memory_ids": [m.memory_id for m in retrieved],
            "usage_input_tokens": rr.usage.input_tokens,
            "usage_output_tokens": rr.usage.output_tokens,
            "judge_correct": jc, "judge_reason": jr,
            "reader_model": MODEL, "latency_s": round(time.time() - t0, 2),
        }
        fout.write(json.dumps(row, ensure_ascii=False) + "\n")
        fout.flush()
        n_run += 1
        print(f"[{qid}] k={len(retrieved)} judge={jc} "
              f"({time.time() - t0:.1f}s)", flush=True)
    fout.close()
    n_judged = n_run - n_null
    acc = f"{n_ok}/{n_judged} = {n_ok / n_judged * 100:.1f}%" if n_judged \
        else "n/a"
    print(f"WSC DIRECT DONE: ran {n_run} (skipped {len(done)} done); "
          f"judged {n_judged}, correct {acc}; gold=null {n_null}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True,
                    help="一个或多个 chain 架构数据 json(供记忆流/会话日期)")
    ap.add_argument("--questions", required=True,
                    help="gen_wikistate_complex 输出 jsonl "
                    "(uid/qid/qtype/question/gold/basis)")
    ap.add_argument("--out", required=True, help="输出 jsonl 路径")
    ap.add_argument("--uids", default=None,
                    help="逗号分隔 uid 列表,只跑这些条目(默认全量)")
    ap.add_argument("--resume", action="store_true",
                    help="跳过输出文件里已有 question_id 的题,追加写")
    a = ap.parse_args()
    uid_list = [u for u in (a.uids or "").split(",") if u] or None
    run(a.data, a.questions, a.out, uid_list, a.resume)


if __name__ == "__main__":
    main()
