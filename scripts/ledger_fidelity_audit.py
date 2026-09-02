# -*- coding: utf-8 -*-
"""scripts/ledger_fidelity_audit.py — 账目保真度分层审计($0,纯归档复算)。

动因:MASTER 增补勘误第 3 条把"gpt-5-mini 读账目 < 其全文"归因为"F.1 协议
不适配推理读者";但去掉协议(裸账目 82.12)仍低于全文(85.07),归因未识别。
本脚本对全部 542 条金链锚行做机核:账目渲染里该行的 value 是否在场、日期
粒度是否比金标更粗,据此把 576 题分成 DATE-FAITHFUL / DATE-DEGRADED 两层,
在层内做同题配对 McNemar。

用法:python scripts/ledger_fidelity_audit.py
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from repro_batch3 import render_card_ledger  # noqa: E402

CARDS = str(ROOT / "results/wt_cards_v43_20260828")
ARMS = {
    "bare-ledger": "results/wsc_v2_ledgerplain_gpt5mini.jsonl",
    "smoc(F.1)": "results/wsc_v2_smoc_v43_gpt5mini.jsonl",
    "fulltext": "results/b28_fullplain_gpt5mini_fmt.jsonl",
    "haiku-ledger": "results/wsc_v2_ledgerplain_haiku.jsonl",
}
DATE_TOK = re.compile(r"\[entry \d+\]\s+(\S+)\s*\|")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _gran(d):
    y, m, dd = d.split("-")
    return 1 if m == "00" else (2 if dd == "00" else 3)


def _mcnemar(pairs):
    b = sum(1 for x, y in pairs if x and not y)
    c = sum(1 for x, y in pairs if y and not x)
    n = b + c
    if not n:
        return b, c, 1.0
    p = 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return b, c, min(p, 1.0)


def main():
    entries = {e["uid"]: e for e in json.loads(
        (ROOT / "data/wikistate_full_ALL.json").read_text(encoding="utf-8"))}
    qs = {q["qid"]: q for q in (json.loads(l) for l in
          (ROOT / "data/wsc_s5_v2.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
    arms = {k: {json.loads(l)["question_id"]: json.loads(l) for l in
                (ROOT / v).read_text(encoding="utf-8").splitlines() if l.strip()}
            for k, v in ARMS.items()}

    stats = {}
    tot = miss = coarse = 0
    for e in entries.values():
        lines = render_card_ledger(e["uid"], e, CARDS).split("\n")
        cm = cc = 0
        for c in e["chain"]:
            tot += 1
            v = _norm(c["value"])
            hit = [ln for ln in lines if v in _norm(ln)]
            if not hit:
                cm += 1
                continue
            m = DATE_TOK.match(hit[0])
            lg = len(m.group(1).split("-")) if m else 0
            if lg < _gran(c["date"]):
                cc += 1
        miss += cm
        coarse += cc
        stats[e["uid"]] = (cm, cc)
    print(f"gold anchor rows={tot} | value absent={miss} ({100*miss/tot:.1f}%) | "
          f"ledger date coarser than gold={coarse} ({100*coarse/tot:.1f}%)")
    clean = {u for u, (cm, cc) in stats.items() if cm == 0 and cc == 0}
    print(f"chains fully faithful: {len(clean)}/{len(entries)}")

    for lab, want in (("DATE-FAITHFUL", True), ("DATE-DEGRADED", False)):
        K = [k for k, q in qs.items() if (q["uid"] in clean) is want]
        acc = {a: 100 * sum(1 for k in K if arms[a][k]["judge_correct"]) / len(K)
               for a in arms}
        b, c, p = _mcnemar([(arms["bare-ledger"][k]["judge_correct"],
                             arms["fulltext"][k]["judge_correct"]) for k in K])
        print(f"{lab:<15} n={len(K):3d} | " +
              " | ".join(f"{a} {acc[a]:5.1f}" for a in arms) +
              f" | ledger-vs-full D{acc['bare-ledger']-acc['fulltext']:+5.1f} "
              f"b={b}/c={c} p={p:.4f}")
        by = defaultdict(lambda: [0, 0, 0])
        for k in K:
            t = qs[k]["qtype"]
            by[t][0] += bool(arms["bare-ledger"][k]["judge_correct"])
            by[t][1] += bool(arms["fulltext"][k]["judge_correct"])
            by[t][2] += 1
        for t, (x, y, n) in sorted(by.items()):
            print(f"    {t:<16} ledger {100*x/n:5.1f}  full {100*y/n:5.1f}  n={n}")


if __name__ == "__main__":
    main()
