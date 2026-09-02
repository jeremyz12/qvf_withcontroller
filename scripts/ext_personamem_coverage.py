# -*- coding: utf-8 -*-
"""批 33-G1 写侧覆盖诊断(零 API):每题的目标偏好(以及 ask_to_forget 题的
被撤销值 prev_pref)在**卡店账目**里是否留下痕迹,对照它在**原文会话流**里
的痕迹。口径沿用批 29 的"内容词命中 ≥50%"。

这是判读 smoc 输赢归因的关键分流:
  原文有 & 账目有 → 写侧保住了,输赢归读侧;
  原文有 & 账目无 → **写侧丢失**(账目压缩把该状态压没了);
  原文无          → 题本身不在 32k 窗口内(采样/切窗问题)。

用法:
  python scripts/ext_personamem_coverage.py
"""
from __future__ import annotations

import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parent.parent
PROBE = REPO / "data/external/personamem/personamem_probe.jsonl"
UNIFIED = REPO / "data/external/personamem/personamem_unified.json"
CARDS = REPO / "results/ext_cards_personamem"

STOP = set("""the a an and or of to in on at for with from that this those these
is are was were be been being it its as by not no do does did done have has had
your you my me i we they he she his her their our about into over under more
most some any all can could would should will just like remember memory""".split())


def words(s: str):
    return [w for w in re.findall(r"[a-z']+", (s or "").lower())
            if len(w) > 3 and w not in STOP]


def hit_frac(target: str, hay_lc: str) -> float:
    ws = words(target)
    if not ws:
        return 0.0
    return sum(1 for w in ws if w in hay_lc) / len(ws)


def main() -> int:
    probe = [json.loads(l) for l in open(PROBE, encoding="utf-8") if l.strip()]
    uni = {e["uid"]: e for e in json.loads(UNIFIED.read_text(encoding="utf-8"))}
    ledger_txt, src_txt = {}, {}
    for uid, e in uni.items():
        f = CARDS / f"{uid}.json"
        if not f.exists():
            continue
        recs = json.loads(f.read_text(encoding="utf-8")).get("records", [])
        ledger_txt[uid] = json.dumps(recs, ensure_ascii=False).lower()
        src_txt[uid] = "\n".join(t for s in e["sessions"]
                                 for t in s["turns"]).lower()
    print(f"stores with cards: {len(ledger_txt)}/{len(uni)}")

    tab = defaultdict(Counter)
    for q in probe:
        uid = q["uid"]
        if uid not in ledger_txt:
            continue
        s = q["qtype"]
        tgt = q["meta"].get("prev_pref") or q["meta"]["preference"]
        in_src = hit_frac(tgt, src_txt[uid]) >= 0.5
        in_led = hit_frac(tgt, ledger_txt[uid]) >= 0.5
        tab[s]["n"] += 1
        tab[s]["src"] += in_src
        tab[s]["led"] += in_led
        tab[s]["src_not_led"] += (in_src and not in_led)
        if s == "ask_to_forget":
            # 撤销事件本身("forget"/"don't remember"…)是否留在账目里
            neg = q["meta"]["preference"]           # "Do not remember 'X' in memory"
            tab[s]["forget_marked"] += hit_frac(neg, ledger_txt[uid]) >= 0.5
    print(f"{'stratum':16s} {'n':>4s} {'in source':>10s} {'in ledger':>10s} "
          f"{'src&!ledger':>12s}")
    for s, c in tab.items():
        print(f"{s:16s} {c['n']:>4d} {c['src'] / c['n'] * 100:>9.1f}% "
              f"{c['led'] / c['n'] * 100:>9.1f}% "
              f"{c['src_not_led'] / c['n'] * 100:>11.1f}%")
    if "ask_to_forget" in tab:
        c = tab["ask_to_forget"]
        print(f"ask_to_forget: retraction phrasing itself present in ledger "
              f"{c['forget_marked']}/{c['n']} "
              f"({c['forget_marked'] / c['n'] * 100:.1f}%)")
    # 账目规模
    sizes = [len(json.loads((CARDS / f"{u}.json").read_text(encoding="utf-8"))
                 ["records"]) for u in ledger_txt]
    turns = [sum(len(s["turns"]) for s in uni[u]["sessions"]) for u in ledger_txt]
    print(f"cards/store mean {sum(sizes) / len(sizes):.1f} "
          f"(min {min(sizes)} max {max(sizes)}); turns/store mean "
          f"{sum(turns) / len(turns):.1f}; compression "
          f"{sum(sizes) / sum(turns):.3f} cards/turn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
