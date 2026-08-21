# -*- coding: utf-8 -*-
"""ChronoScope 原卷 × QVF 作用域外置试点。
预注册:results/chrono_qvf_pilot_prereg.md(先于本文件运行提交)。

子命令:
  sample   确定性抽样 60 链 → data/chronoscope/pilot60.jsonl
  run      跑一个臂:--arm a0|a1|a2|a3 → results/chrono_pilot_{arm}.jsonl
  analyze  四臂配对分析(判据 C1-C4)

判分:逐行移植 ChronoScope repo hf_scope_benchmark.py 的 relaxed 匹配
(论文 sbatch 实证口径);Drift = 判错且命中 present_day_answer。
"""
from __future__ import annotations

import argparse
import json
import re
import string
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
DATA = ROOT / "data/chronoscope/merged_scope_benchmark.jsonl"
PILOT = ROOT / "data/chronoscope/pilot60.jsonl"
FAMS = ["carryover", "carryover_then", "scope_switch",
        "cross_entity_then", "multi_turn_chain"]
PER_FAM = 12
READER_MODEL = "claude-haiku-4-5"
SYS = ("You answer factual questions. Reply with ONLY the answer "
       "(a name), nothing else.")
YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")

# ── 判分:逐行移植自 ChronoScope source/hf_scope_benchmark.py ──
_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"\u201c": '"', "\u201d": '"',
                         "\u2019": "'", "\u2018": "'"})


def normalize_text(s):
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    s = s.translate(_QUOTES)
    s = s.strip().lower()
    s = _WS.sub(" ", s)
    return s


def postprocess_pred(s):
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    s = s.strip()
    if "\n" in s:
        s = s.split("\n", 1)[0].strip()
    low = s.lower().strip()
    prefixes = ["assistant:", "answer:", "final answer:",
                "the answer is", "it is", "it's"]
    for p in prefixes:
        if low.startswith(p):
            s = s[len(p):].strip(" :\t")
            break
    s = s.strip().strip(string.punctuation + " ")
    return s


def normalize_for_match(s):
    s = postprocess_pred(s)
    s = normalize_text(s)
    s = re.sub(r"[^\w\s]", "", s)
    s = _WS.sub(" ", s).strip()
    return s


def extract_candidate_answers(pred):
    if pred is None:
        return []
    s = str(pred).strip()
    if "\n" in s:
        s = s.split("\n", 1)[0].strip()
    m = re.search(r"(?i)\banswer\s*:\s*(.+)$", s)
    if m:
        s = m.group(1).strip()
    s = s.strip().strip('"\'' + string.punctuation + " ")
    cands = [s]
    if "(" in s and ")" in s:
        no_paren = re.sub(r"\s*\([^)]*\)", "", s).strip()
        if no_paren and no_paren != s:
            cands.append(no_paren)
    if "," in s:
        first = s.split(",", 1)[0].strip()
        if first and first != s:
            cands.append(first)
    out, seen = [], set()
    for x in cands:
        nx = normalize_for_match(x)
        if nx and nx not in seen:
            out.append(x)
            seen.add(nx)
    return out


def match_relaxed(pred, gold):
    p = normalize_for_match(pred)
    g = normalize_for_match(gold)
    if not p or not g:
        return False
    if p == g:
        return True
    if g in p or p in g:
        return True
    raw = postprocess_pred(pred)
    for sep in [",", ";", "/", "|"]:
        if sep in raw:
            parts = [normalize_for_match(x) for x in raw.split(sep)]
            if g in parts:
                return True
    return False


def is_match(pred, gold):
    """make_is_match(relaxed, semantic=None) 的展开(论文运行未启用语义)。"""
    cands = extract_candidate_answers(pred) or [pred]
    return any(match_relaxed(c, gold) for c in cands)


def gold_present_value(chain_present, pid=None):
    if chain_present is None:
        return None
    if isinstance(chain_present, str):
        return chain_present
    if isinstance(chain_present, dict):
        if pid and pid in chain_present and isinstance(chain_present[pid], str):
            return chain_present[pid]
    return None


# ── 抽样(确定性:族内 chain_id 排序等距,无随机数)──────────
def cmd_sample():
    index = {f: [] for f in FAMS}
    off = 0
    with open(DATA, "rb") as fh:
        for raw in fh:
            ln = len(raw)
            try:
                r = json.loads(raw)
                fam = r.get("family")
                if fam in FAMS and r.get("is_drift_candidate"):
                    index[fam].append((r["chain_id"], off))
            except Exception:  # noqa: BLE001
                pass
            off += ln
    picked_offsets = []
    for f in FAMS:
        rows = sorted(index[f])
        n = len(rows)
        idxs = sorted({i * n // PER_FAM for i in range(PER_FAM)})
        picked_offsets += [rows[i][1] for i in idxs]
        print(f"{f}: eligible {n}, picked {len(idxs)}")
    with open(DATA, "rb") as fh, open(PILOT, "w", encoding="utf-8") as out:
        for o in picked_offsets:
            fh.seek(o)
            out.write(fh.readline().decode("utf-8").strip() + "\n")
    print(f"wrote {len(picked_offsets)} chains -> {PILOT}")


# ── 跑臂 ─────────────────────────────────────────────────────
def _call(client, messages):
    for attempt in range(4):
        try:
            r = client.messages.create(
                model=READER_MODEL, max_tokens=32, temperature=0.0,
                system=SYS, messages=messages)
            txt = "".join(b.text for b in r.content if b.type == "text")
            return txt, r.usage.input_tokens, r.usage.output_tokens
        except Exception as e:  # noqa: BLE001
            print(f"retry {attempt}: {type(e).__name__}: {str(e)[:80]}",
                  flush=True)
            time.sleep(4)
    return "", 0, 0


def cmd_run(arm):
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import anthropic
    client = anthropic.Anthropic()

    chains = [json.loads(l) for l in open(PILOT, encoding="utf-8")]
    out_p = ROOT / f"results/chrono_pilot_{arm}.jsonl"
    done = set()
    if out_p.exists():
        done = {(json.loads(l)["chain_id"], json.loads(l)["turn_index"])
                for l in open(out_p, encoding="utf-8")}
    fh = open(out_p, "a", encoding="utf-8")
    for c in chains:
        turns = [dict(t, turn_index=t.get("turn_index", i))
                 for i, t in enumerate(c["turns"])]
        turns.sort(key=lambda t: t["turn_index"])
        register = None
        hist = []      # a1: [(q, gold)];a3: [(q, self_pred)]
        ledger = []    # a2 账目行(与 a1 历史同信息:此前问题+金答案)
        for t in turns:
            q = t["question"]
            m = YEAR_RE.search(q)
            if m:
                register = m.group(1)
            t_q = register
            key = (c["chain_id"], t["turn_index"])
            if key in done:
                # 历史仍需推进(a3 无法恢复自身旧答,整链跳过靠外层)
                hist.append((q, t["answer"]))
                if t_q:
                    ledger.append(f"[as of {t_q}] {q} -> {t['answer']}")
                else:
                    ledger.append(f"{q} -> {t['answer']}")
                continue
            if arm == "a0":
                messages = [{"role": "user", "content": q}]
            elif arm in ("a1", "a3"):
                messages = []
                for hq, ha in hist:
                    messages.append({"role": "user", "content": hq})
                    messages.append({"role": "assistant", "content": ha})
                messages.append({"role": "user", "content": q})
            elif arm == "a2":
                parts = []
                if ledger:
                    parts.append("FACTS ESTABLISHED EARLIER IN THIS "
                                 "CONVERSATION:\n" + "\n".join(ledger))
                parts.append("QUESTION: " + q)
                if t_q:
                    parts.append(f"Answer as of {t_q}.")
                messages = [{"role": "user", "content": "\n\n".join(parts)}]
            t0 = time.time()
            pred, ti, to = _call(client, messages)
            gold = t["answer"]
            correct = is_match(pred, gold)
            pres = gold_present_value(c.get("present_day_answer"), t.get("pid"))
            drift = bool((not correct) and pres and is_match(pred, pres))
            fh.write(json.dumps({
                "chain_id": c["chain_id"], "family": c["family"],
                "turn_index": t["turn_index"], "question": q, "gold": gold,
                "present": pres, "pred": pred.strip(), "correct": correct,
                "drift": drift, "t_q": t_q,
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "latency_s": round(time.time() - t0, 2)},
                ensure_ascii=False) + "\n")
            fh.flush()
            # 历史推进
            if arm == "a3":
                hist.append((q, pred.strip() or "(no answer)"))
            else:
                hist.append((q, gold))
            if t_q:
                ledger.append(f"[as of {t_q}] {q} -> {gold}")
            else:
                ledger.append(f"{q} -> {gold}")
        print(f"[{c['chain_id'][:8]}] {c['family']} done", flush=True)
    rows = [json.loads(l) for l in open(out_p, encoding="utf-8")]
    acc = sum(r["correct"] for r in rows) / len(rows) * 100
    print(f"\n{arm}: overall {acc:.1f}% (n={len(rows)})")


# ── 分析(判据 C1-C4)────────────────────────────────────────
def _mcnemar(b, cnt):
    from math import comb
    n = b + cnt
    if n == 0:
        return 1.0
    k = min(b, cnt)
    p = sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n * 2
    return min(1.0, p)


def cmd_analyze():
    arms = {}
    for a in ("a0", "a1", "a2", "a3"):
        p = ROOT / f"results/chrono_pilot_{a}.jsonl"
        if p.exists():
            arms[a] = {(r["chain_id"], r["turn_index"]): r
                       for r in (json.loads(l) for l in open(p, encoding="utf-8"))}
    for a, d in arms.items():
        t0 = [r for r in d.values() if r["turn_index"] == 0]
        fu = [r for r in d.values() if r["turn_index"] >= 1]
        fu_p = [r for r in fu if r["present"]]
        print(f"{a}: turn0 acc {sum(r['correct'] for r in t0)/len(t0)*100:.1f}"
              f"  followup acc {sum(r['correct'] for r in fu)/len(fu)*100:.1f}"
              f"  followup drift {sum(r['drift'] for r in fu_p)/max(1,len(fu_p))*100:.1f}%"
              f" (n_fu={len(fu)}, n_pres={len(fu_p)})")
    if "a1" in arms and "a2" in arms:
        keys = [k for k in arms["a1"] if k in arms["a2"] and k[1] >= 1]
        for metric in ("drift", "correct"):
            b = sum(1 for k in keys
                    if arms["a2"][k][metric] and not arms["a1"][k][metric])
            cnt = sum(1 for k in keys
                      if not arms["a2"][k][metric] and arms["a1"][k][metric])
            print(f"A2 vs A1 followup {metric}: a2-only={b} a1-only={cnt} "
                  f"p={_mcnemar(b, cnt):.4g}")
        print("\nper-family followup (A1 acc/drift -> A2 acc/drift):")
        fams = sorted({arms["a1"][k]["family"] for k in keys})
        for f in fams:
            ks = [k for k in keys if arms["a1"][k]["family"] == f]
            def s(a, m):
                return sum(arms[a][k][m] for k in ks) / len(ks) * 100
            print(f"  {f:18s} n={len(ks):3d}  A1 {s('a1','correct'):5.1f}/"
                  f"{s('a1','drift'):5.1f}  ->  A2 {s('a2','correct'):5.1f}/"
                  f"{s('a2','drift'):5.1f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sample", "run", "analyze"])
    ap.add_argument("--arm", choices=["a0", "a1", "a2", "a3"])
    a = ap.parse_args()
    if a.cmd == "sample":
        cmd_sample()
    elif a.cmd == "run":
        if not a.arm:
            sys.exit("--arm required")
        cmd_run(a.arm)
    else:
        cmd_analyze()


if __name__ == "__main__":
    main()
