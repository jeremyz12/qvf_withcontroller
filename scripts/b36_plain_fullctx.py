# -*- coding: utf-8 -*-
"""批 36:"现实直读"基线臂(plainctx)——把**整库原始记忆**原样塞进提示,
普通一次调用,无检索、无协议、无"这是从记忆里检索到的摘录"框定、无长度上限。

与档案臂的唯一差别就是提示词框定:
  - b33A_smwplain = 同一 render_transcript 全文 + repro_batch3.PLAIN_PROMPT
    ("Answer the question based on the conversation transcript. Reply with
     only the answer.",系统提示为空);
  - b33A_smw      = 同一全文 + F.1 两段式状态追踪协议;
  - b33A_direct   = 稠密 top-10 检索 + ext_direct_arm.READER_SYSTEM
    ("excerpts ... retrieved from memory" + "1-3 sentences");
  - b33A_smoc_v45 = QVF 卡片账目 + F.1 协议;
  - 本臂 plainctx = 同一全文 + system "You are a helpful assistant." +
    "Below is the complete record of my past conversations with you,
     in chronological order." —— 没有任何任务框定或长度限制。

誊录渲染逐字复用 repro_batch3.render_transcript(与 b33A 的 smw/smwplain 同一
函数;已按 AST 断言 repro_batch3 与 repro_batch3_b33 两份实现字节等价),
因此**全文内容逐字节相同**,配对比较分离出来的只有提示词框定这一个变量。
render_transcript 会话按日期排序、会话前插 `--- session date: X ---` 行、
user 与 assistant 两种角色的**全部**轮次逐条渲染为 `[turn N] role: content`。

判官:qvf.judge.ClaudeJudge(),与 lb_reader_arm 同一默认模型与调用式。

用法:
  python scripts/b36_plain_fullctx.py --reader anthropic:claude-haiku-4-5 \
      --data data/wikistate_full_ALL_v24.json \
      --questions results/b35_questions_sample36.jsonl \
      --out results/b36_plainctx_haiku-4-5.jsonl --workers 4
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch3 import render_transcript  # noqa: E402

# ── 唯一的提示词(逐字;不得再加任何一句) ─────────────────────
PLAINCTX_SYSTEM = "You are a helpful assistant."
PLAINCTX_USER = ("Below is the complete record of my past conversations with "
                 "you, in chronological order.\n\n{transcript}\n\n"
                 "Question: {question}")

READER_MAX_TOKENS = 800  # 协调员口径;--max-tokens 只用于灵敏度复跑,不进主表

# 读者侧现价($/百万 token,in/out);预算闸用。
PRICES = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (2.0, 10.0),
}
DEFAULT_PRICE = (3.0, 15.0)


def price_of(model: str):
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    return DEFAULT_PRICE


def cost_of(model: str, tin: int, tout: int) -> float:
    pin, pout = price_of(model)
    return (tin or 0) / 1e6 * pin + (tout or 0) / 1e6 * pout


def prior_spend(pattern: str = "results/b36_plainctx_*.jsonl") -> float:
    """已落盘的全部 b36 读者花费(跨两次调用共享同一 $12 上限)。"""
    tot = 0.0
    for p in sorted(ROOT.glob(pattern)):
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            tot += cost_of(d.get("reader_model", ""),
                           d.get("usage_input_tokens") or 0,
                           d.get("usage_output_tokens") or 0)
    return tot


def call_reader(reader: str, system: str, user: str):
    """anthropic 专用;temperature 只在 haiku 上发送(sonnet-5 拒收该参数)。"""
    kind, model = reader.split(":", 1)
    if kind != "anthropic":
        raise ValueError(f"本臂只支持 anthropic:<model>,收到 {reader}")
    import anthropic
    cli = call_reader._ant = getattr(call_reader, "_ant", None) or \
        anthropic.Anthropic()
    kw = dict(model=model, max_tokens=call_reader.max_tokens, system=system,
              messages=[{"role": "user", "content": user}])
    if model.startswith("claude-haiku"):
        kw["temperature"] = 0.0
    t0 = time.time()
    r = cli.messages.create(**kw)
    txt = "".join(b.text for b in r.content if b.type == "text")
    return (txt, r.usage.input_tokens, r.usage.output_tokens, time.time() - t0,
            r.stop_reason)


call_reader.max_tokens = READER_MAX_TOKENS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", required=True,
                    help="anthropic:claude-haiku-4-5 | anthropic:claude-sonnet-5")
    ap.add_argument("--data", default="data/wikistate_full_ALL_v24.json")
    ap.add_argument("--questions", default="results/b35_questions_sample36.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget", type=float, default=12.0,
                    help="全部 b36 读者调用累计花费上限($);超出即停")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题(冒烟用)")
    ap.add_argument("--max-tokens", type=int, default=READER_MAX_TOKENS,
                    help="灵敏度复跑用;主表一律 800")
    ap.add_argument("--qids-file", default="",
                    help="只跑该文件里的 question_id(每行一个)")
    ap.add_argument("--dry-run", action="store_true",
                    help="只渲染誊录并打印长度统计,零 API 调用")
    a = ap.parse_args()
    model = a.reader.split(":", 1)[1]
    call_reader.max_tokens = a.max_tokens

    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8") if l.strip()]
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")
            if l.strip()} if outp.exists() else set()
    todo = [q for q in qs if q["qid"] not in done and q["uid"] in entries]
    if a.qids_file:
        keep = {l.strip() for l in open(a.qids_file, encoding="utf-8") if l.strip()}
        todo = [q for q in todo if q["qid"] in keep]
    if a.limit:
        todo = todo[:a.limit]

    # 誊录一次性预渲染(线程外),同时出长度统计。
    tx: dict = {}
    for uid in sorted({q["uid"] for q in todo} or {q["uid"] for q in qs}):
        if uid in entries:
            tx[uid] = render_transcript(entries[uid].get("sessions", []))
    if tx:
        lens = sorted(len(v) for v in tx.values())
        n = len(lens)
        print(f"[transcript] stores={n} chars min={lens[0]} "
              f"median={lens[n // 2]} mean={sum(lens) / n:.0f} max={lens[-1]} "
              f"| approx_tokens(mean/3.6)={sum(lens) / n / 3.6:.0f}", flush=True)
        any_uid = sorted(tx)[0]
        roles = {"user": 0, "assistant": 0, "other": 0}
        for line in tx[any_uid].splitlines():
            if line.startswith("[turn "):
                seg = line.split("] ", 1)[1] if "] " in line else ""
                r = seg.split(":", 1)[0].strip()
                roles[r if r in roles else "other"] += 1
        print(f"[transcript] role check on {any_uid}: {roles}", flush=True)
    if a.dry_run:
        return 0

    spend0 = prior_spend()
    print(f"[budget] prior b36 reader spend = ${spend0:.3f}; cap ${a.budget:.2f}",
          flush=True)

    judge = ClaudeJudge()
    lock = threading.Lock()
    fh = open(outp, "a", encoding="utf-8")
    state = {"spend": spend0, "n": 0, "ok": 0, "stop": False}
    qq: "queue.Queue" = queue.Queue()
    for q in todo:
        qq.put(q)

    def worker():
        while True:
            try:
                q = qq.get_nowait()
            except queue.Empty:
                return
            with lock:
                if state["stop"]:
                    qq.task_done()
                    continue
                # 预算闸:按本模型 in 价预估这题(誊录字符/3.6)后再放行。
                est = cost_of(model, len(tx.get(q["uid"], "")) / 3.6,
                              a.max_tokens)
                if state["spend"] + est > a.budget:
                    state["stop"] = True
                    print(f"[budget] STOP: ${state['spend']:.2f} + est "
                          f"${est:.3f} > ${a.budget:.2f}", flush=True)
                    qq.task_done()
                    continue
            user = PLAINCTX_USER.format(transcript=tx[q["uid"]],
                                        question=q["question"])
            raw, ti, to, lat, stop = "", 0, 0, 0.0, ""
            err = ""
            for attempt in range(3):
                try:
                    raw, ti, to, lat, stop = call_reader(
                        a.reader, PLAINCTX_SYSTEM, user)
                    err = ""
                    break
                except Exception as e:  # noqa: BLE001
                    err = f"{type(e).__name__}: {str(e)[:120]}"
                    print(f"retry {attempt} [{q['qid']}]: {err}", flush=True)
                    time.sleep(4)
            v = judge.judge(q["question"], str(q["gold"]), raw, q.get("qtype"))
            row = {
                "question_id": q["qid"], "mode": f"plainctx:{a.reader}",
                "uid": q["uid"], "question_type": q.get("qtype"),
                "question": q["question"], "gold_answer": q["gold"],
                "answer": raw[:2000], "protocol_deviation": False,
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "judge_input_tokens": v.usage_input_tokens,
                "judge_output_tokens": v.usage_output_tokens,
                "reader_model": model,
                "reader_max_tokens": a.max_tokens,
                "stop_reason": stop,
                "transcript_chars": len(tx[q["uid"]]),
                "reader_error": err,
                "latency_s": round(lat, 2)}
            with lock:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                state["spend"] += cost_of(model, ti, to)
                state["n"] += 1
                state["ok"] += bool(v.correct)
                print(f"[{q['qid']}] {v.correct} in={ti} out={to} "
                      f"({lat:.1f}s) ${state['spend']:.2f}", flush=True)
            qq.task_done()

    ths = [threading.Thread(target=worker, daemon=True)
           for _ in range(max(1, a.workers))]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    fh.close()
    n, ok = state["n"], state["ok"]
    print(f"B36 PLAINCTX DONE {a.reader}: {ok}/{n} = "
          f"{ok / max(1, n) * 100:.1f}% | reader spend ${state['spend']:.3f} "
          f"| judge tokens {judge.total_usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
