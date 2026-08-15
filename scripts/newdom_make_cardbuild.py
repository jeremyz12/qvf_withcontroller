# -*- coding: utf-8 -*-
"""建卡专用数据文件生成:对没有 probing_queries 的条目补一个占位探针
(与 S6 管线同一处置:空 probing_queries → 占位 dim1),使 wt_qvf_prototype
write 阶段为全部条目建卡。占位探针只用于让 load_stale_chain 产生实例,
建卡提示词与载荷只取 sessions,卡片内容与占位无关;占位文件绝不用于读跑。
"""
import json
from pathlib import Path

for dom in ["P26", "P69", "P1303"]:
    src = Path(f"data/newdom_{dom}_full.json")
    entries = json.loads(src.read_text(encoding="utf-8"))
    n_pad = 0
    for e in entries:
        if not e.get("probing_queries"):
            e["probing_queries"] = {"dim1_placeholder": {
                "q": "placeholder (card-build only, never evaluated)",
                "gold": "placeholder"}}
            n_pad += 1
    out = Path(f"data/newdom_{dom}_cardbuild.json")
    out.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    print(f"{dom}: {len(entries)} entries, padded {n_pad} -> {out}")
