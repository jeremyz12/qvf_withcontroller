# -*- coding: utf-8 -*-
"""批 31-D 第三刀:按槽位定向的机械清扫(v2.2 → v2.3)。

前两刀依赖 LLM 逐条找,批 31-C 证明会一直有残留(预设式"my students at the
language school"、另一措辞的助手回声、时长陈述)。本刀改为**机械规则**:
在填充会话(chain_index is None)中,凡出现与该条目 slot 相关的第一人称状态
措辞、或助手第二人称复述措辞的句子,一律删除。规则固定 → 可收敛、可复现。

不动链会话(chain_index 有值),故 542 条锚点天然安全。
用法: python scripts/build_corpus_v23.py [--dry]
产物: data/wikistate_full_ALL_v23.json + results/corpus_v23_edits.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_corpus_v21 import expand_sentence, unwrap  # noqa: E402

JOB = (r"engineer|manager|analyst|specialist|teacher|designer|developer"
       r"|consultant|scientist|entrepreneur")
WORK = (r"\bmy job\b|\bnew (job|role|position)\b|\b(got|was|been|were) (recently |just |finally |officially )?promoted\b"
        r"|\bi work (at|for|as)\b|\bi'm (a|an) [a-z ]{0,25}(" + JOB + r")\b"
        r"|\bi started (at|working|my new)\b|\bmy (current )?role as\b"
        r"|\bsince i started (my )?(new )?(job|role|work)\b")
FIRST = {
    "employer": WORK + r"|\bmy (students|boss|supervisor) (at|in)\b",
    "position": WORK + r"|\bmy (title|position) (at|in)\b",
    "residence": (r"\bi live in\b|\bi'm living in\b|\bi moved (to|into)\b"
                  r"|\bmy new (apartment|place|flat|home)\b"
                  r"|\bi'm based in\b|\bsince i moved\b"),
    "team": (r"\bmy team at\b|\bnew team\b|\bi joined\b"
             r"|\bleading (a|my) team\b|\bi (now )?lead a team\b"
             r"|\bmy (colleagues|teammates) at\b"),
}
# 助手侧第二人称复述:只认与职务/归属/搬迁绑定的复述,不认泛泛祝贺
SECOND = {
    "employer": (r"\byour (new )?(job|role|position|promotion)\b"
                 r"|\byour role as\b|\bsettling into your new\b"),
    "position": (r"\byour (new )?(job|role|position|promotion|title)\b"
                 r"|\byour role as\b|\bsettling into your new\b"),
    "residence": (r"\byour new (apartment|place|home|city)\b"
                  r"|\bsettling into your new\b|\byour move to\b"),
    "team": (r"\byour (new )?team\b|\bleading your team\b"
             r"|\bsettling into your new\b"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    data = json.loads((ROOT / "data/wikistate_full_ALL_v22.json")
                      .read_text(encoding="utf-8"))
    log = open(ROOT / "results/corpus_v23_edits.jsonl", "w", encoding="utf-8")
    n_cut = 0
    touched = set()
    for e in data:
        slot = e["slot"]
        if slot not in FIRST:
            continue
        p1 = re.compile(FIRST[slot], re.I)
        p2 = re.compile(SECOND[slot], re.I)
        for s in e.get("sessions", []):
            if s.get("chain_index") is not None:
                continue          # 链会话不动,锚点天然安全
            turns = s.get("turns", [])
            i = 0
            while i < len(turns):
                role, body, rebuild = unwrap(turns[i])
                if not isinstance(body, str) or not body.strip():
                    i += 1
                    continue
                pat = p2 if role == "assistant" else p1
                cuts, newbody = [], body
                while True:
                    m = pat.search(newbody)
                    if not m:
                        break
                    x, y = expand_sentence(newbody, m.start(), m.end())
                    seg = newbody[x:y].strip()
                    if not seg:
                        break
                    cuts.append(seg)
                    newbody = (newbody[:x] + newbody[y:]).strip()
                if not cuts:
                    i += 1
                    continue
                newbody = re.sub(r"  +", " ", newbody)
                n_cut += len(cuts)
                touched.add(e["uid"])
                log.write(json.dumps({
                    "uid": e["uid"], "slot": slot, "session": s.get("date"),
                    "role": role, "cuts": cuts}, ensure_ascii=False) + "\n")
                if a.dry:
                    i += 1
                    continue
                if newbody:
                    turns[i] = rebuild(newbody)
                    i += 1
                else:
                    turns.pop(i)
    bad = 0
    for e in data:
        blob = re.sub(r"\s+", " ", json.dumps(e.get("sessions", []),
                                              ensure_ascii=False)).lower()
        for c in e["chain"]:
            if re.sub(r"\s+", " ", c["state_span"]).lower() not in blob:
                print(f"闸1违例 锚丢失: {e['uid']} :: {c['state_span'][:50]}")
                bad += 1
    print(f"第三刀:删除 {n_cut} 句,涉及 {len(touched)} 链;锚闸违例 {bad}")
    if a.dry:
        print("(dry run,未写出)")
        return 0
    if bad:
        print("ABORT")
        return 1
    (ROOT / "data/wikistate_full_ALL_v23.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data/b31_v23_touched.txt").write_text(",".join(sorted(touched)),
                                                   encoding="utf-8")
    print("v2.3 写出 data/wikistate_full_ALL_v23.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
