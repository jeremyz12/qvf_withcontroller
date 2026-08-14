# -*- coding: utf-8 -*-
"""本地小模型编译能力评测线(阶段 0:能力下限测量,零 API LLM 成本)。

对拍对象:参考计划集(haiku 编译 + 判官判对的历史行,只取最新跑、qid 去重)。
被测:本地 ollama 模型,system+user 结构逐字节复用冻结臂 COMPILE_PROMPT
(import 自 scripts/complex_query_arm,不复制不改写)。

三层指标:
  ① 严格 JSON 合法率:第一次请求的原始输出能直接 json.loads 成 dict;
  ② 计划一致率:op 精确相等 + 该 op 相关槽位经 SLOT_ALIASES/_norm 归一后匹配;
  ③ 执行等价率:同 recs/mem_dates 下 execute_plan(本地计划) 与
     execute_plan(参考计划) 的 (证据行, 结论行) 完全相等(纯代码零 LLM)。
     编译三试全败的题记 False。

与 haiku 线的一致与差异(如实入档):
  - 提示词字节相同(import COMPILE_PROMPT);temperature 0;重试 ≤3 同口径;
  - haiku 走 messages.parse 结构化,本地走 ollama format="json" + pydantic
    CompiledPlan 验证 —— 解析层差异,非提示词差异;
  - qwen3 系默认 thinking,统一 "think": false(推理参数,三档一致)。

用法(cwd 必须是仓库根 D:\\ZZL_cluade):
  python scripts/eval_local_compiler.py --model qwen3:4b \
      --out results/local_compile_qwen3_4b_20260815.jsonl [--resume]
  python scripts/eval_local_compiler.py --build-ref-only   # 只装配参考集并打印统计
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# 键控卡片覆盖目录:必须在 import 冻结模块之前设好(模块级读取)。
os.environ.setdefault("QVF_CARDS_KEYED", "results/wt_cards_v42")

from scripts.complex_query_arm import (  # noqa: E402  冻结模块,只 import 不改
    COMPILE_PROMPT, CompiledPlan, OPS, SLOT_ALIASES,
    _load_entries, _load_records, _mem_dates, execute_plan)
from scripts.gen_wikistate_complex import parse_partial_date  # noqa: E402
from scripts.wt_qvf_prototype import _norm  # noqa: E402

OLLAMA = "http://localhost:11434/api/chat"
RETRIES = 3          # 与 haiku 线 compile_plan 的 for _ in range(3) 同口径
NUM_PREDICT = 512

# ── 参考集装配 ───────────────────────────────────────────────
REF_S5 = "results/wsc_s5_test_v42.jsonl"
REF_S6 = ["results/complex_s6_v2.jsonl", "results/wsc_s6_big_arm.jsonl"]
REF_S7_ARM = "results/wsc_s7_arm_full2.jsonl"
REF_S7_JUDGE = "results/wsc_s7_judged_full2.jsonl"
DATA_FILES = [
    "data/wikistate_full_P108.json", "data/wikistate_full_P54.json",
    "data/wikistate_full_P551.json", "data/wikistate_full_multi_big.json",
    "data/stale_chain_full.json", "data/stale_chain_confirm.json",
]


def _rows(path: str):
    for l in open(path, encoding="utf-8"):
        s = l.strip()
        if s:
            yield json.loads(s)


def build_reference():
    """(问题, 参考计划) 对;qid 去重、只取最新跑、只留判对+compile_ok 行。
    S7 用严格档:precision=1 且 recall=1 且零幻觉(rubric 判官标签,不进
    被测模型输入)。"""
    ref = {}
    # S5:judge_correct=true 且 compile_ok
    for r in _rows(REF_S5):
        if r.get("judge_correct") is True and r.get("compile_ok"):
            ref[r["question_id"]] = r
    # S6:v2 优先,big_arm 补缺(qid 重叠,净 21)
    for p in REF_S6:
        for r in _rows(p):
            if (r.get("judge_correct") is True and r.get("compile_ok")
                    and r["question_id"] not in ref):
                ref[r["question_id"]] = r
    # S7:rubric 严格档过滤
    s7j = {}
    for j in _rows(REF_S7_JUDGE):
        s7j[j["question_id"]] = j
    for r in _rows(REF_S7_ARM):
        j = s7j.get(r["question_id"])
        if not j or not r.get("compile_ok"):
            continue
        hall = j.get("hallucinated")
        n_hall = len(hall) if isinstance(hall, list) else (hall or 0)
        if j.get("precision") == 1 and j.get("recall") == 1 and n_hall == 0:
            if r["question_id"] not in ref:
                ref[r["question_id"]] = r
    out = []
    for qid, r in ref.items():
        out.append({"question_id": qid, "uid": r["uid"],
                    "question_type": r.get("question_type"),
                    "question": r["question"], "ref_plan": r["plan"]})
    out.sort(key=lambda x: x["question_id"])
    return out


# ── 归一化与计划一致判定 ─────────────────────────────────────
def _slot_key(s):
    """SLOT_ALIASES 归一(与 _select_pool 的类匹配同口径):命中类集合;
    无命中回退 _norm 字符串。"""
    fs = _norm(s or "")
    if not fs:
        return ("",)
    m = tuple(sorted(c for c, al in SLOT_ALIASES.items()
                     if any(a in fs for a in al)))
    return m if m else (fs,)


def _date_key(d):
    if not d:
        return None
    try:
        return parse_partial_date(str(d))[0].isoformat()
    except Exception:  # noqa: BLE001
        return _norm(str(d))


def _pv_match(a, b):
    """presupposed:_norm 双向包含(与 _exec_join 锚匹配同口径)。"""
    na, nb = _norm(a or ""), _norm(b or "")
    if not na and not nb:
        return True
    return bool(na and nb and (na in nb or nb in na))


# 每 op 参与一致判定的字段(execute_plan 实际读取的字段)
OP_FIELDS = {
    "current": ("slot",), "trajectory": ("slot",), "first_last": ("slot",),
    "count_changes": ("slot",), "longest": ("slot",),
    "point_in_time": ("slot", "date"), "count_before": ("slot", "date"),
    "premise_check": ("slot", "presupposed"),
    "tag_filter": ("tag",), "tag_trend": ("tag",),
    "join_at_change": ("slot", "slot2", "presupposed", "anchor_index"),
}


def plans_agree(local: dict, ref: dict):
    """op 精确 + 归一化 args;返回 (是否一致, 首个不匹配字段名或 None)。"""
    if (local.get("op") or "") != (ref.get("op") or ""):
        return False, "op"
    for f in OP_FIELDS.get(ref.get("op"), ()):
        lv, rv = local.get(f), ref.get(f)
        if f in ("slot", "slot2"):
            if _slot_key(lv) != _slot_key(rv):
                return False, f
        elif f == "date":
            if _date_key(lv) != _date_key(rv):
                return False, f
        elif f == "tag":
            if (str(lv or "").strip()) != (str(rv or "").strip()):
                return False, f
        elif f == "presupposed":
            if not _pv_match(lv, rv):
                return False, f
        elif f == "anchor_index":
            if (lv or None) != (rv or None):
                return False, f
    return True, None


# ── 本地推理 ─────────────────────────────────────────────────
def _post(body: dict, timeout=600) -> dict:
    req = urllib.request.Request(
        OLLAMA, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def compile_local(model: str, question: str):
    """与 haiku 线 compile_plan 同结构:system=COMPILE_PROMPT(逐字节)、
    user=原始问题、temperature 0、重试 ≤3。返回逐题记录字典。"""
    attempts = []
    plan = None
    first_strict = None
    t_total = 0.0
    for i in range(RETRIES):
        t0 = time.time()
        try:
            resp = _post({
                "model": model, "stream": False, "think": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": COMPILE_PROMPT},
                    {"role": "user", "content": question}],
                "options": {"temperature": 0.0, "num_predict": NUM_PREDICT},
                "keep_alive": "15m",
            })
            raw = resp.get("message", {}).get("content", "")
        except Exception as e:  # noqa: BLE001
            raw = f"__HTTP_ERROR__ {e}"
        dt = time.time() - t0
        t_total += dt
        strict = False
        parsed = None
        try:
            parsed = json.loads(raw)
            strict = isinstance(parsed, dict)
        except Exception:  # noqa: BLE001
            # 剥 JSON 兜底(非严格):取首个 {...} 片段
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except Exception:  # noqa: BLE001
                    parsed = None
        if first_strict is None:
            first_strict = strict
        attempts.append({"strict_json": strict, "latency_s": round(dt, 2),
                         "raw": raw if not strict else None})
        if isinstance(parsed, dict):
            try:
                plan = CompiledPlan.model_validate(parsed).model_dump()
                break
            except Exception:  # noqa: BLE001
                plan = None
        # 失败 → 重试
    return {"plan": plan, "compile_ok": plan is not None,
            "json_valid_first": bool(first_strict),
            "attempts_n": len(attempts), "attempts": attempts,
            "latency_s": round(t_total, 2)}


# ── 显存采样 ─────────────────────────────────────────────────
class VramSampler(threading.Thread):
    def __init__(self, interval=5.0):
        super().__init__(daemon=True)
        self.interval = interval
        self.max_mib = 0
        self.samples = []
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10).stdout
                v = int(out.strip().splitlines()[0])
                self.samples.append(v)
                self.max_mib = max(self.max_mib, v)
            except Exception:  # noqa: BLE001
                pass
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()


def _ollama_ps():
    try:
        return subprocess.run(["ollama", "ps"], capture_output=True,
                              text=True, timeout=15).stdout
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


# ── 主流程 ───────────────────────────────────────────────────
def run(model: str, out_path: str, resume: bool):
    ref = build_reference()
    entries = _load_entries(DATA_FILES)
    md_cache = {}
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

    sampler = VramSampler()
    sampler.start()
    baseline = None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        baseline = int(out.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        pass

    t_run0 = time.time()
    n = n_strict = n_ok = n_agree = n_exec = 0
    for q in ref:
        qid = q["question_id"]
        if qid in done:
            continue
        uid = q["uid"]
        if uid not in md_cache:
            md_cache[uid] = _mem_dates(entries.get(uid, {}))
        mem_dates = md_cache[uid]
        recs = _load_records(uid)

        c = compile_local(model, q["question"])
        agree, mis = (False, "compile_fail")
        exec_eq = False
        ref_out = local_out = None
        if c["plan"] is not None:
            agree, mis = plans_agree(c["plan"], q["ref_plan"])
            # 执行等价对拍(纯代码零 LLM;一致题也执行以核验)
            try:
                ref_out = execute_plan(dict(q["ref_plan"]), recs, mem_dates,
                                       q["question"])
                local_out = execute_plan(dict(c["plan"]), recs, mem_dates,
                                         q["question"])
                exec_eq = (ref_out == local_out)
            except Exception as e:  # noqa: BLE001
                exec_eq = False
                local_out = ["__EXEC_ERROR__", str(e)]
        row = {
            "question_id": qid, "uid": uid, "model": model,
            "question_type": q["question_type"], "question": q["question"],
            "ref_plan": q["ref_plan"], "local_plan": c["plan"],
            "json_valid_first": c["json_valid_first"],
            "compile_ok": c["compile_ok"], "attempts_n": c["attempts_n"],
            "attempts": c["attempts"],
            "plan_agree": agree, "mismatch_field": mis if not agree else None,
            "exec_equal": exec_eq,
            "cards_n": len(recs), "latency_s": c["latency_s"],
        }
        if not exec_eq and c["plan"] is not None:
            row["ref_exec"] = ref_out
            row["local_exec"] = local_out
        fout.write(json.dumps(row, ensure_ascii=False) + "\n")
        fout.flush()
        n += 1
        n_strict += row["json_valid_first"]
        n_ok += row["compile_ok"]
        n_agree += agree
        n_exec += exec_eq
        if n % 25 == 0 or n == 1:
            print(f"[{n}] {qid} op_ref={q['ref_plan'].get('op')} "
                  f"agree={agree} exec={exec_eq} ({c['latency_s']}s)",
                  flush=True)
    wall = time.time() - t_run0
    sampler.stop()
    fout.close()
    ps = _ollama_ps()
    meta = {
        "question_id": "__META__", "model": model, "n_run": n,
        "wall_s": round(wall, 1), "vram_baseline_mib": baseline,
        "vram_max_mib": sampler.max_mib,
        "vram_samples_n": len(sampler.samples),
        "ollama_ps": ps,
        "json_valid_first": n_strict, "compile_ok": n_ok,
        "plan_agree": n_agree, "exec_equal": n_exec,
    }
    with open(outp.with_suffix(".meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"DONE {model}: n={n} strict_json={n_strict} compile_ok={n_ok} "
          f"agree={n_agree} exec_eq={n_exec} wall={wall:.0f}s "
          f"vram_max={sampler.max_mib}MiB", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--out")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--build-ref-only", action="store_true")
    a = ap.parse_args()
    if a.build_ref_only:
        ref = build_reference()
        by_op = {}
        for r in ref:
            by_op[r["ref_plan"]["op"]] = by_op.get(r["ref_plan"]["op"], 0) + 1
        print(f"reference n={len(ref)}")
        for op in OPS:
            if op in by_op:
                print(f"  {op}: {by_op[op]}")
        return
    if not a.model or not a.out:
        ap.error("--model and --out required")
    run(a.model, a.out, a.resume)


if __name__ == "__main__":
    main()
