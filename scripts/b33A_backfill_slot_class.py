# -*- coding: utf-8 -*-
"""批 33-A 派生店:results/wt_cards_v45 -> results/wt_cards_v45k,机械补 slot_class/owner。

背景:v45/v45g 建卡器不再写 `slot_class`/`owner`(v42 两字段 100% 覆盖),
而 complex_query_arm._select_pool 的键控路径以 (owner, slot_class) 分组,
`_select_pool` 的 OPEN_SLOT/OPEN_KEYS 救援也先要求 `slot_class` 存在,
故 filter/usability/compile 在 v45 上整段走无键回退。本脚本只补字段,
不改 record 的任何既有键值,产物写入**新目录**,v45 原店只读。

映射规则(确定性,零 LLM):
  slot_class = 与 complex_query_arm.SLOT_ALIASES 同表匹配 record 的 `slot`,
               命中多类时取**最长别名**者(最具体);未命中记 "other:<归一 slot>"
               —— 与 v42 的 other:* 一等公民写法一致。
  owner      = record["entity"];"user" 保持 "user",其余原样(v42 同形)。

用法: PYTHONUTF8=1 python scripts/b33A_backfill_slot_class.py
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"D:/ZZL_cluade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from complex_query_arm import SLOT_ALIASES, _norm  # noqa: E402

SRC = ROOT / "results/wt_cards_v45"
DST = ROOT / "results/wt_cards_v45k"


def classify(slot: str) -> tuple[str, str]:
    """返回 (slot_class, 命中的别名);未命中返回 ("other:<norm>", "")。"""
    fs = _norm(slot or "")
    best_cls, best_alias = "", ""
    for cls, aliases in SLOT_ALIASES.items():
        for a in aliases:
            if a in fs and len(a) > len(best_alias):
                best_cls, best_alias = cls, a
    if best_cls:
        return best_cls, best_alias
    return ("other:" + fs if fs else "other:state"), ""


def main() -> int:
    if not SRC.exists():
        print("SOURCE MISSING", SRC)
        return 1
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)

    files = sorted(SRC.glob("*.json"))
    n_rec = 0
    cls_ct: Counter = Counter()
    mapping: dict = {}
    unmapped = 0
    for f in files:
        obj = json.loads(f.read_text(encoding="utf-8"))
        for r in obj.get("records", []):
            n_rec += 1
            slot = r.get("slot", "")
            cls, alias = classify(slot)
            r["slot_class"] = cls
            ent = (r.get("entity") or "").strip()
            r["owner"] = ent
            cls_ct[cls] += 1
            if cls.startswith("other:"):
                unmapped += 1
            mapping.setdefault(slot, (cls, alias))
        (DST / f.name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")

    keyed = sum(v for k, v in cls_ct.items() if not k.startswith("other:"))
    print("files=%d records=%d" % (len(files), n_rec))
    print("mapped to a SLOT_ALIASES class: %d (%.1f%%)"
          % (keyed, keyed / n_rec * 100))
    print("left as other:*            : %d (%.1f%%)"
          % (unmapped, unmapped / n_rec * 100))
    print("\nclass histogram (closed classes):")
    for k, v in cls_ct.most_common():
        if not k.startswith("other:"):
            print("   %-14s %d" % (k, v))
    print("\ntop 20 slot -> class mappings actually used:")
    rows = sorted(mapping.items(), key=lambda kv: kv[0])
    shown = 0
    for slot, (cls, alias) in rows:
        if not cls.startswith("other:") and shown < 20:
            print("   %-24s -> %-12s (alias %r)" % (slot, cls, alias))
            shown += 1
    (ROOT / "results/b33A_v45k_mapping.json").write_text(
        json.dumps({"n_records": n_rec, "mapped": keyed, "other": unmapped,
                    "class_histogram": dict(cls_ct),
                    "slot_to_class": {k: v[0] for k, v in mapping.items()}},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nwrote %s and results/b33A_v45k_mapping.json" % DST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
