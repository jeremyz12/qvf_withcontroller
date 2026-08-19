# -*- coding: utf-8 -*-
"""scripts/chain_membership_filter.py — 装配层链成员资格过滤器。

对每库目标槽位的选池(与执行器同一 `_select_pool`)做一次 LLM 语义角色判断
(K=1,temperature 0),再由**确定性代码授权**;授权失败一律 fail-closed 判非成员。
设计来源与判据见 results/membership_filter_prereg.md(先于本文件运行提交)。

三条来自方法节精读的硬约束,全部在代码里而不只在文档里:
1. 问句是**语义角色**("是不是槽位 X 的一次状态宣告"),不是"是否被上下文支持"
   —— 后者对同主题污染零区分度(ConsistencyGate 的问句在我们的失败模式上失效)。
2. never-infer 负约束进提示词,且输出强制带 evidence 引文(Schema-Grounded)。
3. 授权 = 引文必须是该卡逐字锚点的子串、锚点必须在库原文中(StateAuditor VTA:
   模型只提议,代码授权;钉不上就不算成员)。

用法:
    python scripts/chain_membership_filter.py \
        --data data/replchain_50.json --cards results/wt_cards_twinC_repl \
        --out-cards results/wt_cards_twinC_repl_mf --report results/mf_repl.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-haiku-4-5"

PROMPT = """You are auditing a memory store. The target attribute (slot) is:

    {slot}

Below are candidate memory cards that a lexical selector swept into this slot's
history chain. Some are TRUE STATE DECLARATIONS of this slot (the user stating,
explicitly or across turns, that this attribute took a new value). Others are
ADJACENT-TOPIC attributes that merely share the theme (e.g. a drink order swept
into a "favorite coffee shop" chain, a dashcam swept into a "car model" chain).

For EACH card, decide: is its value a state OF THE SLOT ITSELF?

Rules:
- member=true ONLY if the card's quoted text declares the slot taking this value.
- A declaration may be oblique or span context ("signing the lease tomorrow"),
  but the VALUE must be a value of the slot, not of a related attribute.
- NEVER infer membership from topical closeness. If the quote shows an adjacent
  attribute (an accessory, an order, a frequency, a location detail, an amenity),
  answer member=false.
- For every member=true, copy the exact substring of that card's quote that
  declares the state (verbatim, no paraphrase) into `evidence`.

Cards:
{cards}

Answer as JSON: {{"decisions": [{{"record_id": "...", "member": true/false,
"evidence": "verbatim substring or empty"}}]}}"""


def content_words(s: str):
    import re
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2]


def authorize(decision: dict, card: dict, store_blob: str) -> bool:
    """确定性授权:模型只提议,这里说了算。任何一步失败 → 非成员(fail-closed)。"""
    if not decision.get("member"):
        return False
    ev = (decision.get("evidence") or "").strip()
    span = str(card.get("source_span") or "")
    if not ev or not span:
        return False
    # 引文钉回该卡自己的锚点(子串,或 ≥80% 内容词落入)
    if ev not in span:
        cw = content_words(ev)
        if not cw or sum(1 for w in cw if w in span.lower()) / len(cw) < 0.8:
            return False
    # 锚点本身必须在库原文中(伪造锚点不算)
    if span not in store_blob:
        return False
    return True


def run(data_path: str, cards_dir: str, out_dir: str, report_path: str) -> int:
    os.environ.setdefault("QVF_CARDS_KEYED", cards_dir)
    for m in list(sys.modules):
        if m.startswith("scripts.complex_query_arm"):
            del sys.modules[m]
    os.environ["QVF_CARDS_KEYED"] = cards_dir
    import scripts.complex_query_arm as A

    entries = {e["uid"]: e for e in json.loads(
        (ROOT / data_path).read_text(encoding="utf-8"))}
    client = anthropic.Anthropic()
    (ROOT / out_dir).mkdir(parents=True, exist_ok=True)

    tot_in = tot_out = 0
    report = []
    for uid, e in entries.items():
        src = ROOT / cards_dir / f"{uid}.json"
        if not src.exists():
            continue
        lib = json.loads(src.read_text(encoding="utf-8"))
        recs = lib.get("records", [])
        md = A._mem_dates(e)
        slot = (e.get("slot") or "").strip()
        pool = A._select_pool(recs, slot, md, "")
        pool_ids = {id(r) for r in pool}
        blob = "\n".join(str(t) for s in e.get("sessions", [])
                         for t in s.get("turns", []))
        if not pool:
            (ROOT / out_dir / f"{uid}.json").write_text(
                json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf-8")
            report.append({"uid": uid, "pool": 0, "kept": 0, "removed": 0})
            continue
        cards_txt = "\n".join(
            f'- record_id={r.get("record_id")} value="{r.get("value")}" '
            f'date="{r.get("stated_date") or md.get(r.get("source_memory_id", ""), "")}" '
            f'quote="{r.get("source_span")}"' for r in pool)
        resp = client.messages.create(
            model=MODEL, max_tokens=2000, temperature=0.0,
            messages=[{"role": "user",
                       "content": PROMPT.format(slot=slot, cards=cards_txt)}])
        tot_in += resp.usage.input_tokens
        tot_out += resp.usage.output_tokens
        txt = "".join(b.text for b in resp.content if b.type == "text")
        try:
            j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
            dec = {d.get("record_id"): d for d in j.get("decisions", [])}
        except Exception:
            dec = {}   # 解析失败 → 全部 fail-closed(整池判非成员)
        by_id = {r.get("record_id"): r for r in pool}
        keep_ids = {rid for rid, d in dec.items()
                    if rid in by_id and authorize(d, by_id[rid], blob)}
        new_recs = [r for r in recs
                    if id(r) not in pool_ids or r.get("record_id") in keep_ids]
        out = dict(lib)
        out["records"] = new_recs
        out["membership_filtered"] = {"slot": slot, "pool": len(pool),
                                      "kept": len(keep_ids),
                                      "removed": len(pool) - len(keep_ids)}
        (ROOT / out_dir / f"{uid}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        report.append({"uid": uid, "pool": len(pool), "kept": len(keep_ids),
                       "removed": len(pool) - len(keep_ids)})
        print(f"[{uid[:28]}] pool={len(pool)} kept={len(keep_ids)}", flush=True)
    cost = tot_in / 1e6 * 1 + tot_out / 1e6 * 5
    summary = {"stores": len(report), "tok_in": tot_in, "tok_out": tot_out,
               "cost_usd": round(cost, 4), "rows": report}
    (ROOT / report_path).write_text(json.dumps(summary, ensure_ascii=False,
                                               indent=1), encoding="utf-8")
    print(f"DONE {len(report)} stores  in={tot_in:,} out={tot_out:,} ≈ ${cost:.3f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--cards", required=True)
    ap.add_argument("--out-cards", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args()
    return run(a.data, a.cards, a.out_cards, a.report)


if __name__ == "__main__":
    sys.exit(main())
