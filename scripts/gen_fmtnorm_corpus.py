# -*- coding: utf-8 -*-
"""批 28:语料格式归一(裸轮 → 与干扰轮同款 dict 串)。确定性零 LLM。
用法: python scripts/gen_fmtnorm_corpus.py
"""
import json
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
src = json.loads((ROOT / "data/wikistate_full_ALL.json").read_text(
    encoding="utf-8"))
n_wrap = n_bare = 0
anchor_ok = anchor_broken = 0
broken = []
for e in src:
    spans = [r.get("state_span") or "" for r in e.get("chain", [])]
    for s in e.get("sessions", []):
        new = []
        for t in s.get("turns", []):
            txt = str(t)
            if txt.startswith("{'role'"):
                n_wrap += 1
                new.append(txt)
            else:
                n_bare += 1
                new.append(str({"role": "user", "content": txt}))
        s["turns"] = new
    # 锚点逐字核验(对归一后轮文本)
    all_txt = "\n".join(str(t) for s in e.get("sessions", [])
                        for t in s.get("turns", []))
    for sp in spans:
        if not sp:
            continue
        if sp in all_txt:
            anchor_ok += 1
        else:
            anchor_broken += 1
            broken.append((e["uid"], sp[:60]))
out = ROOT / "data/wikistate_full_ALL_fmtnorm.json"
out.write_text(json.dumps(src, ensure_ascii=False), encoding="utf-8")
# 归一后裸轮闸
bare_after = sum(1 for e in src for s in e["sessions"]
                 for t in s["turns"] if not str(t).startswith("{'role'"))
print(f"wrapped {n_wrap} | 原裸轮 {n_bare} 已包 | 归一后裸轮 {bare_after}")
print(f"锚点核验: OK {anchor_ok} / 断 {anchor_broken}")
for b in broken[:8]:
    print("  broken:", b)
assert bare_after == 0
