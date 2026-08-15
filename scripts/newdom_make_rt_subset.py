# -*- coding: utf-8 -*-
"""按最终路由决策生成 rt 臂子集数据文件(数据侧过滤,不改任何臂脚本):
data/newdom_rt_subset_{dom}.json = 原 *_full.json 条目,probing_queries 只保留
路由到 rt 的题。framing_qvf_arm 直接 --data 之,产出行的 question_id 与全量
文件一致(uid_dim_query)。同理生成 prompt 子集的 qid 文件(framing_tlcot_arm
自带 --qid-file)。"""
import json
from pathlib import Path

for dom in ["P26", "P69", "P1303"]:
    routes = [json.loads(l) for l in
              open(f"results/newdom_routes_{dom}.jsonl", encoding="utf-8")]
    rt = {(r["uid"], r["dim"]) for r in routes if r["route"] == "rt"}
    prompt_qids = [f"{r['uid']}_{r['dim']}_query" for r in routes
                   if r["route"] == "prompt"]
    entries = json.loads(Path(f"data/newdom_{dom}_full.json")
                         .read_text(encoding="utf-8"))
    out = []
    nq = 0
    for e in entries:
        pq = {dim: q for dim, q in (e.get("probing_queries") or {}).items()
              if (e["uid"], dim) in rt}
        if pq:
            e2 = dict(e)
            e2["probing_queries"] = pq
            out.append(e2)
            nq += len(pq)
    Path(f"data/newdom_rt_subset_{dom}.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    Path(f"data/newdom_prompt_qids_{dom}.txt").write_text(
        "\n".join(prompt_qids) + ("\n" if prompt_qids else ""),
        encoding="utf-8")
    print(f"{dom}: rt {nq} 题 / {len(out)} 库 -> rt_subset; "
          f"prompt {len(prompt_qids)} 题 -> qid 文件")
