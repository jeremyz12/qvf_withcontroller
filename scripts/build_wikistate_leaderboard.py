# -*- coding: utf-8 -*-
"""WikiState 全系统榜单汇编:从存档逐行文件计算 准确度 / in-out token /
延迟中位 / 建库耗时,生成 results/wikistate_leaderboard_20260828.md。
缺指标的行标注"缺,须跑"。用法: python scripts/build_wikistate_leaderboard.py
"""
import json
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")

SECTIONS = [
    ("v2 主考场(576 题,haiku 读者;店版本标注)", [
        ("直读 top-10 检索", "results/wsc_v2_direct.jsonl", ""),
        ("filter(纯选择)", "results/wsc_v2_filter.jsonl", ""),
        ("usability(+认证)", "results/wsc_v2_usability.jsonl", ""),
        ("编译臂(代码执行)", "results/wsc_v2_compile.jsonl", "v42 店"),
        ("smw(引用协议+原文全文)", "results/wsc_v2_smw.jsonl", ""),
        ("smoc(账目读法)", "results/wsc_v2_smoc.jsonl", "v42 店"),
        ("smoc", "results/wsc_v2_smoc_v43.jsonl", "v43 店"),
        ("smoc 槽位投影(经济档)", "results/wsc_v2_smoc_slot.jsonl", "v42 店"),
        ("smoc 投影去锚(判负档)", "results/wsc_v2_smoc_slim.jsonl", "v42 店"),
        ("smoc 槽位投影(经济档)", "results/wsc_v2_smoc_v43_slot.jsonl", "v43 店;回退 21.5%"),
    ]),
    ("v1 头条考场(418 题,haiku 读者)", [
        ("smoc run1", "results/wsc_s5_smoc.jsonl", "v42 店"),
        ("smoc run2(复核)", "results/wsc_smoc418_rerun_20260826.jsonl", "v42 店"),
        ("smoc", "results/wsc_s5_smoc_v43.jsonl", "v43 店(中性带,头条仍 88.4)"),
        ("smw(协议+原文)", "results/wsc_s5_smw.jsonl", ""),
        ("smw 对照(通用协议)", "results/wsc_s5_smwctrl.jsonl", ""),
        ("原文裸读", "results/wsc_s5_smwplain.jsonl", ""),
        ("filter-only", "results/wsc_s5_filter_only.jsonl", ""),
        ("sonnet-5 读 smoc 账目", "results/wsc_s5_smoc_sonnet5.jsonl", "批16,v42 店"),
    ]),
    ("16 系统同台(60 题标定场,v1;各系统自带建库)", [
        ("Mem0", "results/wsc_s5_mem0.jsonl", ""),
        ("LangMem", "results/wsc_s5_langmem.jsonl", ""),
        ("A-MEM", "results/wsc_s5_amem.jsonl", ""),
        ("cognee", "results/wsc_s5_cognee.jsonl", ""),
        ("LightRAG", "results/wsc_s5_lightrag.jsonl", "† 集成问题不入对比"),
        ("Graphiti", "results/wsc_s5_graphiti.jsonl", "† 同上"),
        ("txtai(本地嵌入RAG)", "results/wsc_s5_txtai.jsonl", ""),
        ("lgstore", "results/wsc_s5_lgstore.jsonl", ""),
        ("timeline(时间线组织)", "results/wsc_s5_timeline.jsonl", ""),
        ("BM25", "results/wsc_s5_bm25.jsonl", ""),
        ("obs-RAG", "results/wsc_s5_obsrag.jsonl", ""),
        ("摘要 RAG", "results/wiki_summarymem_h45.jsonl", ""),
        ("写入盖章台账(MemStrata式)", "results/wsc_s5_mstrata.jsonl", "机制天花板"),
    ]),
    ("跨读者矩阵(v2 576;同一检索/账目,只换读者)", [
        ("haiku-4.5 · 直读", "results/wsc_v2_direct.jsonl", ""),
        ("sonnet-5 · 直读", "results/wsc_v2_direct_sonnet5.jsonl", ""),
        ("gpt-5-mini · 直读", "results/wsc_v2_direct_gpt5mini.jsonl", ""),
        ("haiku-4.5 · smoc", "results/wsc_v2_smoc_v43.jsonl", "v43 店"),
        ("sonnet-5 · smoc", "results/wsc_v2_smoc_v43_sonnet5.jsonl", "v43 店;截断 29/576=5.0%"),
        ("gpt-5-mini · smoc", "results/wsc_v2_smoc_v43_gpt5mini.jsonl", "v43 店;空答 23/576=4.0%(推理截断)"),
        ("qwen3:14b(开源本地)· smoc", "results/lb_qwen14b_smoc.jsonl", "60 题抽样,v43 店"),
    ]),
]


def stats(p):
    f = ROOT / p
    if not f.exists():
        return None
    rows = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    rows = [r for r in rows if "question_id" in r or "qid" in r]
    if not rows:
        return None
    ok = sum(1 for r in rows if r.get("judge_correct") or r.get("correct"))
    n = len(rows)
    ti = [r.get("usage_input_tokens") for r in rows
          if r.get("usage_input_tokens") is not None]
    to = [r.get("usage_output_tokens") for r in rows
          if r.get("usage_output_tokens") is not None]
    lat = sorted(r.get("latency_s") for r in rows
                 if r.get("latency_s") is not None)
    ing = [r.get("ingest_seconds") for r in rows
           if r.get("ingest_seconds") is not None]
    return dict(
        n=n, acc=ok / n * 100,
        tin=sum(ti) / len(ti) if ti else None,
        tout=sum(to) / len(to) if to else None,
        lat=lat[len(lat) // 2] if lat else None,
        ingest=sum(ing) / len(ing) if ing else None)


out = ["# WikiState 全系统榜单(2026-08-28 汇编)",
       "",
       "> 每行:n / 准确度 / 平均入·出 token/题 / 延迟中位(秒)/ 建库耗时。",
       "> 判官统一 ClaudeJudge;60 题行为标定场抽样,不得与全量直比;",
       "> † 行不入对比性主张(集成问题不可分)。缺项标注后本批补跑。", ""]
for title, rows in SECTIONS:
    out.append(f"## {title}\n")
    out.append("| 系统/臂 | n | acc | in-tok | out-tok | 延迟中位 | 建库 | 注 |")
    out.append("|---|---|---|---|---|---|---|---|")
    for name, path, note in rows:
        s = stats(path)
        if s is None:
            out.append(f"| {name} | — | **缺,须跑** | — | — | — | — | {note} |")
            continue
        fmt = lambda v, d="—": (f"{v:.0f}" if v is not None else d)
        ing = f"{s['ingest']:.1f}s/题" if s['ingest'] else "—"
        out.append(
            f"| {name} | {s['n']} | **{s['acc']:.2f}** | {fmt(s['tin'])} | "
            f"{fmt(s['tout'])} | {s['lat'] if s['lat'] is not None else '—'}s "
            f"| {ing} | {note} |")
    out.append("")
(ROOT / "results/wikistate_leaderboard_20260828.md").write_text(
    "\n".join(out), encoding="utf-8")
print("written results/wikistate_leaderboard_20260828.md")
for title, rows in SECTIONS:
    for name, path, note in rows:
        if stats(path) is None:
            print("GAP:", name, "->", path)
