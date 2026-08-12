# -*- coding: utf-8 -*-
"""Post-Retrieval Assembly(arXiv:2606.01435)三原语管线的忠实重写 × WikiState。

原语逐条对应原文:①事实级 BM25 检索 k=10;②LLM 把检回证据抽成候选表
{value, date};③确定性 freshness picking = 取最新日期候选为答案。
读者/判官与本项目全部臂一致(haiku 抽取 + opus 判官),标注 faithful
reimplementation(原文用 gpt-4o-mini + 序号;我们域内以日期为版本信号)。"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from rank_bm25 import BM25Okapi  # noqa: E402
from qvf.judge import ClaudeJudge  # noqa: E402
from qvf.retrieval import MemoryItem  # noqa: E402

USE_DENSE = "--dense" in sys.argv
if USE_DENSE:
    sys.argv.remove("--dense")
    import os
    os.environ.setdefault("QVF_EMBED_BACKEND", "openai")
    from scripts.run_decisive_stale import _dense_retriever_cls
    DENSE_CLS = _dense_retriever_cls()

MODEL = "claude-haiku-4-5"


class Candidate(BaseModel):
    value: str = Field(description="A candidate answer value stated in the excerpts.")
    date: str = Field(default="", description="The date of the excerpt stating it (as given).")


class CandidateList(BaseModel):
    candidates: list[Candidate]


EXTRACT_PROMPT = (
    "You are given dated excerpts retrieved from a user's conversation history, "
    "and a question. Extract EVERY candidate value that the excerpts state for "
    "what the question asks about, each with the date of the excerpt it came "
    "from. Only extract values actually stated in the excerpts; if none match, "
    "return an empty list. Do not decide which is correct — list all candidates."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    items = json.loads(Path(a.data).read_text(encoding="utf-8"))
    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    out_f = Path(a.out)
    done = set()
    if out_f.exists():
        for l in open(out_f, encoding="utf-8"):
            done.add(json.loads(l)["question_id"])
    fh = open(out_f, "a", encoding="utf-8")
    for it in items:
        uid = it["uid"]
        docs, dates = [], []
        for s in it.get("sessions", []):
            for t in s.get("turns", []):
                docs.append(str(t))
                dates.append(s.get("date", "undated"))
        if USE_DENSE:
            mems = [MemoryItem(memory_id=f"{uid}/m{i}", content=docs[i],
                               metadata={"session_date": dates[i]})
                    for i in range(len(docs))]
            retriever = DENSE_CLS(mems)
        else:
            bm25 = BM25Okapi([d.lower().split() for d in docs])
        for dim, q in it.get("probing_queries", {}).items():
            qid = f"{uid}_{dim}_query"
            if qid in done:
                continue
            if USE_DENSE:
                got = retriever.retrieve(str(q["q"]), top_k=10)
                excerpts = "\n".join(
                    f"[{(m.metadata or {}).get('session_date','undated')}] {m.content[:400]}"
                    for m in got)
            else:
                scores = bm25.get_scores(str(q["q"]).lower().split())
                top = sorted(range(len(docs)), key=lambda i: -scores[i])[:10]
                excerpts = "\n".join(f"[{dates[i]}] {docs[i][:400]}" for i in top)
            cands = []
            t0 = time.time()
            for attempt in range(3):
                try:
                    resp = client.messages.parse(
                        model=MODEL, max_tokens=1200, system=EXTRACT_PROMPT,
                        messages=[{"role": "user", "content":
                                   f"EXCERPTS:\n{excerpts}\n\nQUESTION: {q['q']}"}],
                        output_format=CandidateList)
                    if resp.parsed_output:
                        cands = resp.parsed_output.candidates
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(2)
            # 原语③:确定性取最新(日期字符串排序,与其取最大序号同构)
            if cands:
                best = max(cands, key=lambda c: c.date or "")
                ans = f"{best.value}" + (f" (as of {best.date})" if best.date else "")
            else:
                ans = "I don't have that information."
            v = judge.judge(q["q"], str(q["gold"]), ans, qid)
            fh.write(json.dumps({
                "question_id": qid, "mode": "pra_newest",
                "question": q["q"], "gold_answer": str(q["gold"]),
                "answer": ans, "candidates_n": len(cands),
                "judge_correct": v.correct, "judge_reason": v.reason,
                "latency_s": round(time.time() - t0, 1),
            }, ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] answered {len(it.get('probing_queries', {}))} questions", flush=True)
    print("DONE")


if __name__ == "__main__":
    main()
