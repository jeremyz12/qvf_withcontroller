# -*- coding: utf-8 -*-
"""改写题集编译重测(模板膨胀量测量)。

输入 results/paraphrase_set_20260815.jsonl(1107 条,369 题 x3 改写),
参考计划按 question_id 连回原 369 参考集(改写不变量保证参考计划不变)。
被测三方:qwen3:8b / qwen3:4b(ollama 本地,与阶段 0 完全同参数)、
haiku 原编译线(import complex_query_arm.compile_plan,不复制不改写)。

执行等价对拍口径与阶段 0 相同:同 recs/mem_dates 双执行、纯代码零 LLM;
双方都以改写句为 question 文本执行(唯一变量是计划本身)。

用法(cwd 仓库根):
  python scripts/eval_paraphrase.py --model qwen3:8b \
      --out results/para_compile_qwen3_8b_20260815.jsonl [--resume]
  python scripts/eval_paraphrase.py --model haiku --limit 20 \
      --out results/para_compile_haiku_smoke.jsonl        # 冒烟
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# eval_local_compiler 在 import 时设 QVF_CARDS_KEYED 并 os.chdir(ROOT)
from scripts.eval_local_compiler import (  # noqa: E402
    DATA_FILES, build_reference, compile_local, plans_agree)
from scripts.complex_query_arm import (  # noqa: E402  冻结模块,只 import
    _client, _load_entries, _load_records, _mem_dates, compile_plan,
    execute_plan)

PARA_SET = "results/paraphrase_set_20260815.jsonl"


def _rows(path):
    for l in open(path, encoding="utf-8"):
        s = l.strip()
        if s:
            yield json.loads(s)


def compile_haiku(client, question: str):
    """haiku 原编译线包装:与阶段 0 本地记录同形。ok=False(三试全败的
    回落空计划)按阶段 0 口径记 plan=None。"""
    t0 = time.time()
    plan, tin, tout, ok = compile_plan(client, question)
    dt = time.time() - t0
    if not ok:
        plan = None
    return {"plan": plan, "compile_ok": ok, "json_valid_first": ok,
            "attempts_n": None, "attempts": None,
            "tokens_in": tin, "tokens_out": tout,
            "latency_s": round(dt, 2)}


def run(model: str, out_path: str, resume: bool, limit: int | None):
    ref = {r["question_id"]: r for r in build_reference()}
    paras = list(_rows(PARA_SET))
    if limit:
        paras = paras[:limit]
    entries = _load_entries(DATA_FILES)
    md_cache = {}
    rec_cache = {}

    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if resume and outp.exists():
        for r in _rows(outp):
            done.add((r.get("question_id"), r.get("para_idx")))
    fout = open(outp, "a" if resume else "w", encoding="utf-8")

    is_haiku = model.startswith("haiku") or model.startswith("claude")
    client = _client() if is_haiku else None

    t_run0 = time.time()
    n = n_ok = n_agree = n_exec = 0
    tin_sum = tout_sum = 0
    for p in paras:
        qid, pidx = p["question_id"], p["para_idx"]
        if (qid, pidx) in done:
            continue
        q = ref.get(qid)
        if q is None:
            raise SystemExit(f"paraphrase qid not in reference set: {qid}")
        uid = q["uid"]
        if uid not in md_cache:
            md_cache[uid] = _mem_dates(entries.get(uid, {}))
            rec_cache[uid] = _load_records(uid)
        mem_dates, recs = md_cache[uid], rec_cache[uid]
        qtext = p["question_para"]

        c = (compile_haiku(client, qtext) if is_haiku
             else compile_local(model, qtext))
        agree, mis = (False, "compile_fail")
        exec_eq = False
        ref_out = local_out = None
        if c["plan"] is not None:
            agree, mis = plans_agree(c["plan"], q["ref_plan"])
            try:
                ref_out = execute_plan(dict(q["ref_plan"]), recs, mem_dates,
                                       qtext)
                local_out = execute_plan(dict(c["plan"]), recs, mem_dates,
                                         qtext)
                exec_eq = (ref_out == local_out)
            except Exception as e:  # noqa: BLE001
                exec_eq = False
                local_out = ["__EXEC_ERROR__", str(e)]
        row = {
            "question_id": qid, "para_idx": pidx, "uid": uid, "model": model,
            "question_type": q["question_type"],
            "question_orig": q["question"], "question_para": qtext,
            "ref_plan": q["ref_plan"], "test_plan": c["plan"],
            "compile_ok": c["compile_ok"],
            "plan_agree": agree, "mismatch_field": mis if not agree else None,
            "exec_equal": exec_eq, "latency_s": c["latency_s"],
        }
        if is_haiku:
            row["tokens_in"] = c["tokens_in"]
            row["tokens_out"] = c["tokens_out"]
            tin_sum += c["tokens_in"]
            tout_sum += c["tokens_out"]
        else:
            row["json_valid_first"] = c["json_valid_first"]
            row["attempts_n"] = c["attempts_n"]
        if not exec_eq and c["plan"] is not None:
            row["ref_exec"] = ref_out
            row["local_exec"] = local_out
        fout.write(json.dumps(row, ensure_ascii=False) + "\n")
        fout.flush()
        n += 1
        n_ok += bool(c["compile_ok"])
        n_agree += agree
        n_exec += exec_eq
        if n % 50 == 0 or n == 1:
            print(f"[{n}] {qid}#p{pidx} op={q['ref_plan'].get('op')} "
                  f"agree={agree} exec={exec_eq} ({c['latency_s']}s)",
                  flush=True)
    wall = time.time() - t_run0
    fout.close()
    meta = {"question_id": "__META__", "model": model, "n_run": n,
            "wall_s": round(wall, 1), "compile_ok": n_ok,
            "plan_agree": n_agree, "exec_equal": n_exec}
    if is_haiku:
        meta["tokens_in"] = tin_sum
        meta["tokens_out"] = tout_sum
    with open(outp.with_suffix(".meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"DONE {model}: n={n} compile_ok={n_ok} agree={n_agree} "
          f"exec_eq={n_exec} wall={wall:.0f}s "
          f"tok_in={tin_sum} tok_out={tout_sum}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    run(a.model, a.out, a.resume, a.limit)


if __name__ == "__main__":
    main()
