# -*- coding: utf-8 -*-
"""T1 条件③ 第二步:最低质量轮(b6_rep3,64.0%)端到端小规模验证。

只对 B6/S5 重叠的 19 uid / 76 题跑真实的 READ(haiku)+JUDGE(opus);COMPILE
步骤复用 results/wsc_s5_test_v42b1_union.jsonl 里已经编译好的 plan(问题→计划
只取决于问题文本,不取决于卡片库,复用不引入方法学偏差,且省掉这部分 LLM 调用
的钱)。EXECUTE 步骤用 b6_rep3 库重新跑(纯代码,零 LLM,但结果因换库而变)。

冻结文件(complex_query_arm.py / qvf_router.py / qvf_algebra.py)全程只读、
不猴补 execute_plan 本身;只猴补 qvf.judge.ClaudeJudge.judge 用于读出判官侧
真实 token 用量(与 b1_run_p39.py 同一套路)。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qvf.judge as qjudge  # noqa: E402

_GLOBAL_USAGE = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
_orig_judge_method = qjudge.ClaudeJudge.judge


def _tracked_judge(self, *a, **kw):
    before = dict(self.total_usage)
    result = _orig_judge_method(self, *a, **kw)
    for k in _GLOBAL_USAGE:
        _GLOBAL_USAGE[k] += self.total_usage[k] - before[k]
    return result


qjudge.ClaudeJudge.judge = _tracked_judge

from scripts.complex_query_arm import (  # noqa: E402
    execute_plan, _mem_dates, _query_date, reader_content, MODEL,
    READER_SYSTEM, _client,
)

ROOT = Path(__file__).resolve().parent.parent
UNION = ROOT / "results/wsc_s5_test_v42b1_union.jsonl"
LIB_DIR = ROOT / "results/wt_cards_b6_rep3"   # 最低单轮质量 64.0%
DATA_FILES = [ROOT / "data/wikistate_full_P108.json",
              ROOT / "data/wikistate_full_P54.json"]
OUT = ROOT / "results/writeside_sensitivity_b6rep3_arm.jsonl"


def load_entries():
    by_uid = {}
    for f in DATA_FILES:
        for e in json.loads(f.read_text(encoding="utf-8")):
            by_uid.setdefault(e["uid"], e)
    return by_uid


def load_records(uid: str):
    p = LIB_DIR / f"{uid}.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("records", [])
    except Exception:
        return []


def main():
    entries = load_entries()
    rows = [json.loads(l) for l in open(UNION, encoding="utf-8")]
    b6_uids = set(p.stem for p in LIB_DIR.glob("*.json"))
    target = [r for r in rows if r["uid"] in b6_uids]
    if len(sys.argv) > 1 and sys.argv[1] == "smoke":
        target = target[:3]
    print(f"target questions: {len(target)} across "
          f"{len(set(r['uid'] for r in target))} uids "
          f"(card library = {LIB_DIR}, quality=64.0% single-round, lowest "
          f"of all available reconstruction rounds)")

    done = set()
    if OUT.exists():
        for l in open(OUT, encoding="utf-8"):
            try:
                done.add(json.loads(l)["question_id"])
            except Exception:
                pass
    fout = open(OUT, "a" if done else "w", encoding="utf-8")
    client = _client()
    judge = qjudge.ClaudeJudge()
    md_cache = {}
    n_ok = n_run = 0

    for r in target:
        qid = r["question_id"]
        if qid in done:
            continue
        uid = r["uid"]
        t0 = time.time()
        if uid not in md_cache:
            md_cache[uid] = _mem_dates(entries[uid])
        mem_dates = md_cache[uid]

        plan = r["plan"]  # 复用已编译计划(零 LLM,问题→计划与卡片库无关)
        recs = load_records(uid)
        ev, derived = execute_plan(plan, recs, mem_dates, r["question"])

        qdate = _query_date(entries[uid], r["question"])
        rr = client.messages.create(
            model=MODEL, max_tokens=1000, temperature=0.0,
            system=[{"type": "text", "text": READER_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user",
                       "content": reader_content(ev, derived, qdate,
                                                  r["question"])}],
        )
        answer = "".join(b.text for b in rr.content if b.type == "text")

        gold = r["gold_answer"]
        v = judge.judge(r["question"], str(gold), answer,
                         r.get("question_type"))
        jc, jr = v.correct, v.reason
        n_ok += bool(jc)
        n_run += 1

        out_row = {
            "question_id": qid, "mode": "complex_arm", "uid": uid,
            "question_type": r.get("question_type"), "question": r["question"],
            "gold_answer": gold, "answer": answer,
            "plan": plan, "evidence_n": len(ev),
            "card_library": "wt_cards_b6_rep3 (64.0% single-round quality, "
                             "lowest of all reconstruction rounds)",
            "usage_input_tokens": rr.usage.input_tokens,
            "usage_output_tokens": rr.usage.output_tokens,
            "judge_correct": jc, "judge_reason": jr,
            "reader_model": MODEL, "latency_s": round(time.time() - t0, 2),
        }
        fout.write(json.dumps(out_row, ensure_ascii=False) + "\n")
        fout.flush()
        print(f"[{qid}] op={plan.get('op')} ev={len(ev)} judge={jc} "
              f"({time.time()-t0:.1f}s)", flush=True)

    fout.close()
    print(f"\nDONE: ran {n_run} (skipped {len(done)} already-done); "
          f"correct {n_ok}/{n_run + len(done & set(r['question_id'] for r in target))}"
          if n_run else "\nDONE: nothing new to run")
    print("\n=== judge (opus) usage this process ===")
    print(json.dumps(_GLOBAL_USAGE, ensure_ascii=False))
    cost = (_GLOBAL_USAGE["input_tokens"] * 5
            + _GLOBAL_USAGE["output_tokens"] * 25) / 1_000_000
    print(f"judge cost estimate (claude-opus-5 $5/$25 per Mtok): ${cost:.4f}")


if __name__ == "__main__":
    main()
