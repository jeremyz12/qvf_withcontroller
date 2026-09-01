# -*- coding: utf-8 -*-
"""批 31-B 第二刀:清扫注入状态的"回声"(v2.1 → v2.2)。

动因:v2.1 只删了用户的断言句,但同一会话里助手的回应仍在复述该状态
("Congratulations on your role as Senior Software Engineer!"、"As a senior
account manager, you'll need to..."),读者读全文时状态照样在场。

工艺:对每处 v2.1 删除,从"被删句 + 确认值"提取特征短语(≥2 词、≥8 字符、
非停用词短语),在**同一会话**内清扫所有轮次中含该短语的句子。跨会话不动,
避免过度删除。
用法: python scripts/scrub_echoes_v22.py [--dry]
产物: data/wikistate_full_ALL_v22.json + results/corpus_v22_echo_edits.jsonl
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

STOP = {"the", "and", "for", "with", "that", "this", "have", "been", "your",
        "you", "role", "job", "work", "new", "team", "company", "about",
        "from", "some", "more", "just", "very", "really", "like"}


def phrases(removed: str, value: str) -> list:
    """特征短语:优先用确认值的分段,退回被删句里的大写多词短语。"""
    out = []
    for seg in re.split(r"[(),;]|\bat\b|\bin\b", value or ""):
        seg = seg.strip(" .")
        words = [w for w in re.findall(r"[A-Za-z][\w'-]*", seg)]
        if len(words) >= 2 and len(seg) >= 8 and \
                any(w.lower() not in STOP for w in words):
            out.append(seg)
    for m in re.finditer(r"\b([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){1,4})\b",
                         removed or ""):
        seg = m.group(1)
        if len(seg) >= 8:
            out.append(seg)
    # 去重、长者优先(更具体)
    seen, res = set(), []
    for p in sorted(out, key=len, reverse=True):
        k = p.lower()
        if k in seen or any(k in s for s in seen):
            continue
        seen.add(k)
        res.append(p)
    return res[:4]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    conf = json.loads((ROOT / "results/contamination_confirmed_20260901.json")
                      .read_text(encoding="utf-8"))
    val_of = {}
    for c in conf:
        val_of.setdefault(c["uid"], []).append(c.get("value") or "")
    edits = [json.loads(l) for l in
             open(ROOT / "results/corpus_v21_edits.jsonl", encoding="utf-8")]
    by_key = {}
    for e in edits:
        by_key.setdefault((e["uid"], e["session"]), []).append(e)
    data = json.loads((ROOT / "data/wikistate_full_ALL_v21.json")
                      .read_text(encoding="utf-8"))
    log = open(ROOT / "results/corpus_v22_echo_edits.jsonl",
               "w", encoding="utf-8")
    n_scrub = 0
    for entry in data:
        uid = entry["uid"]
        for s in entry.get("sessions", []):
            key = (uid, s.get("date"))
            if key not in by_key:
                continue
            pats = []
            for e in by_key[key]:
                for v in val_of.get(uid, []):
                    pats += phrases(e["removed"], v)
            pats = list(dict.fromkeys(pats))
            if not pats:
                continue
            turns = s.get("turns", [])
            i = 0
            while i < len(turns):
                role, body, rebuild = unwrap(turns[i])
                if not isinstance(body, str) or not body.strip():
                    i += 1
                    continue
                newbody, removed_bits = body, []
                for p in pats:
                    while True:
                        m = re.search(re.escape(p), newbody, re.IGNORECASE)
                        if not m:
                            break
                        x, y = expand_sentence(newbody, m.start(), m.end())
                        removed_bits.append(newbody[x:y].strip())
                        newbody = (newbody[:x] + newbody[y:]).strip()
                if not removed_bits:
                    i += 1
                    continue
                newbody = re.sub(r"  +", " ", newbody)
                n_scrub += len(removed_bits)
                log.write(json.dumps({
                    "uid": uid, "session": s.get("date"), "role": role,
                    "patterns": pats, "removed": removed_bits},
                    ensure_ascii=False) + "\n")
                if a.dry:
                    i += 1
                    continue
                if newbody:
                    turns[i] = rebuild(newbody)
                    i += 1
                else:
                    turns.pop(i)
            continue
    # 闸:链锚必须仍在
    bad = 0
    for e in data:
        blob = re.sub(r"\s+", " ", json.dumps(e.get("sessions", []),
                                              ensure_ascii=False)).lower()
        for c in e["chain"]:
            if re.sub(r"\s+", " ", c["state_span"]).lower() not in blob:
                print(f"闸违例 锚丢失: {e['uid']} :: {c['state_span'][:50]}")
                bad += 1
    print(f"回声清扫 {n_scrub} 句;锚闸违例 {bad}")
    if a.dry:
        print("(dry run,未写出)")
        return 0
    if bad:
        print("ABORT:锚闸违例,不写出 v2.2")
        return 1
    (ROOT / "data/wikistate_full_ALL_v22.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print("v2.2 写出 data/wikistate_full_ALL_v22.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
