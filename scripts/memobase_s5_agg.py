# -*- coding: utf-8 -*-
"""scripts/memobase_s5_agg.py — Memobase(memodb-io/memobase, Apache-2.0)
× WikiState 60 题标定场(批 33-H5 对手位)。

!!! 状态:本文件从未成功执行过 !!!
Memobase 服务端只有 docker-compose 一条部署路径(Postgres+pgvector 与 Redis 为
硬依赖),本机 Docker Desktop 后端起不来,因此本脚本停在"写好待跑"。
判决见 results/opt_batch33_H5_memobase_verdict.md。恢复条件:任一机器上
`cd external/memobase/src/server && docker compose up -d` 起得来,填好
api/config.yaml 后设 MEMOBASE_URL / MEMOBASE_TOKEN 即可运行本脚本。

协议镜像 scripts/langmem_s5_agg.py(取库口径 / 摄入 / 读者 / 判官逐字同款),
只把记忆系统换成 Memobase:
  - 每条目一个全新 user(client.add_user → User);
  - 会话按日期升序逐个 insert 成 ChatBlob,日期挂在每条 message 的
    created_at 上(memobase_server/utils.py:get_message_timestamp 用的就是它);
  - 全部插完后 flush(sync=True) 触发写时抽取/合并(profile 槽位固化);
  - 每题读 profile(槽位卡)+ context(profile+event 打包串),拼成 MEMORIES
    喂同款 haiku 读者,同 ClaudeJudge 判。

用法(先起服务):
  cd external/memobase/src/server && docker compose up -d
  MEMOBASE_URL=http://localhost:8019 MEMOBASE_TOKEN=secret \
  .venv_memobase/Scripts/python.exe scripts/memobase_s5_agg.py \
      --out results/wsc_s5_memobase.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv

load_dotenv(r"D:\ZZL_cluade\.env")

import anthropic
from memobase import ChatBlob, MemoBaseClient
from qvf.judge import ClaudeJudge

ROOT = Path(r"D:\ZZL_cluade")
VOLS = ["data/wikistate_full_P108.json", "data/wikistate_full_P39_ext.json",
        "data/wikistate_full_P54.json", "data/wikistate_full_P551.json"]
READER_MODEL = "claude-haiku-4-5"
# 与 langmem_s5_agg.py / graphiti_baseline.py 同一句,逐字不动。
READER_SYS = (
    "You are the user's personal AI assistant. You will be shown MEMORIES "
    "retrieved from a memory system about this user (each may carry dates), "
    "followed by the user's new message. Reply to the new message naturally "
    "and helpfully in 1-3 sentences, as you would in an everyday chat.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-stores", type=int, default=15)
    ap.add_argument("--store-offset", type=int, default=0)
    ap.add_argument("--out", default="results/wsc_s5_memobase.jsonl")
    ap.add_argument("--profile-tokens", type=int, default=1000)
    ap.add_argument("--context-tokens", type=int, default=1000)
    a = ap.parse_args()

    entries = {}
    for v in VOLS:
        for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
            entries.setdefault(e["uid"], e)
    qrows = [json.loads(l) for l in open(ROOT / "results/wsc_s5_filter_only.jsonl",
                                         encoding="utf-8")]
    by_uid: dict = {}
    for r in qrows:
        by_uid.setdefault(r["uid"], []).append(
            {"qid": r["question_id"], "qtype": r["question_type"],
             "question": r["question"], "gold": r["gold_answer"]})
    uids = sorted(by_uid)
    n = len(uids)
    picked = [uids[(a.store_offset + i) * n // a.n_stores % n]
              for i in range(a.n_stores)] if a.store_offset == 0 else \
             [uids[(i * n // a.n_stores + a.store_offset) % n]
              for i in range(a.n_stores)]
    picked = list(dict.fromkeys(picked))
    print(f"抽中 {len(picked)} 库,共 {sum(len(by_uid[u]) for u in picked)} 题",
          flush=True)

    mb = MemoBaseClient(
        project_url=os.environ.get("MEMOBASE_URL", "http://localhost:8019"),
        api_key=os.environ.get("MEMOBASE_TOKEN", "secret"))
    assert mb.ping(), "Memobase 服务不可达"

    client = anthropic.Anthropic()
    judge = ClaudeJudge()
    outp = ROOT / a.out
    done = set()
    if outp.exists():
        done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")}
    fh = open(outp, "a", encoding="utf-8")
    for uid in picked:
        it = entries.get(uid)
        if not it:
            continue
        qs = [q for q in by_uid[uid] if q["qid"] not in done]
        if not qs:
            continue
        # 每条目一个全新 user(uid 只作日志,memobase 自己发 uuid)
        mb_uid = mb.add_user({"wikistate_uid": uid})
        u = mb.get_user(mb_uid)
        t0 = time.time()
        sessions = sorted(it.get("sessions", []), key=lambda s: s.get("date", ""))
        for si, sess in enumerate(sessions):
            date = sess.get("date", "") or ""
            msgs = []
            for t in sess.get("turns", [])[:6]:
                msgs.append({"role": "user", "content": str(t)[:400],
                             "created_at": date})
            if not msgs:
                continue
            for attempt in range(3):
                try:
                    u.insert(ChatBlob(messages=msgs))
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"[{uid}] s{si} attempt {attempt}: "
                          f"{type(e).__name__}: {str(e)[:120]}", flush=True)
                    time.sleep(2)
        try:
            u.flush(sync=True)          # 写时固化:抽取 → 合并 → 槽位落库
        except Exception as e:  # noqa: BLE001
            print(f"[{uid}] flush failed: {type(e).__name__}: {str(e)[:120]}",
                  flush=True)
        ingest_s = time.time() - t0

        try:
            profiles = u.profile(max_token_size=a.profile_tokens)
            prof_lines = [f"- {p.topic}::{p.sub_topic}: {p.content}"
                          for p in profiles]
        except Exception as e:  # noqa: BLE001
            print(f"[{uid}] profile failed: {type(e).__name__}", flush=True)
            profiles, prof_lines = [], []
        for q in qs:
            t1 = time.time()
            try:
                ctx = u.context(max_token_size=a.context_tokens,
                                chats=[{"role": "user", "content": q["question"]}])
            except Exception as e:  # noqa: BLE001
                print(f"[{q['qid']}] context failed: {type(e).__name__}",
                      flush=True)
                ctx = ""
            memtext = "\n".join(prof_lines) if prof_lines else ""
            if ctx:
                memtext = (memtext + "\n" + ctx).strip()
            memtext = memtext or "(no memories retrieved)"
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
                except Exception:  # noqa: BLE001
                    time.sleep(2)
            v = judge.judge(q["question"], str(q["gold"]), ans, q["qtype"])
            fh.write(json.dumps({
                "question_id": q["qid"], "mode": "memobase", "uid": uid,
                "memobase_user_id": mb_uid,
                "question_type": q["qtype"], "question": q["question"],
                "gold_answer": q["gold"], "answer": ans,
                "memories_n": len(prof_lines),
                "profile_slots": prof_lines,
                "context_chars": len(ctx),
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "ingest_seconds": round(ingest_s, 1),
                "latency_s": round(time.time() - t1, 2)},
                ensure_ascii=False) + "\n")
            fh.flush()
        print(f"[{uid}] ingested {len(sessions)} sessions in {ingest_s:.0f}s, "
              f"{len(prof_lines)} profile slots, answered {len(qs)}", flush=True)
    rows = [json.loads(l) for l in open(outp, encoding="utf-8")]
    acc = sum(1 for r in rows if r.get("judge_correct")) / len(rows) * 100
    print(f"\nMemobase 聚合题:{acc:.2f}% (n={len(rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
