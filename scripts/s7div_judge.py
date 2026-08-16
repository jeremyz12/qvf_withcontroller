# -*- coding: utf-8 -*-
"""S7-div 可溯性评审器 —— wsc_s7_judge.py 的 recall 口径改造版。

复用 wsc_s7_judge.py 的①主张抽取(haiku)②精确率机械核对(会话原文+标签卡
grounding)逐字不改;唯一改动是召回口径:S7-div 每行自带机器推导的
`gold.items`(见 data/wsc_s7div.meta.json/scripts/s7div_gen.py,与建卡/读取
侧代码零重叠的独立种子词典机械施加得到),不是原 S7 那种"该 tag 下库里有
几张卡"的自指标签库统计。召回 = gold.items 里被回答文本提及的比例,复用
wsc_s7_judge._mentioned_in_answer 的同一文本覆盖判定(不比对 tag 库)。

原因:原 wsc_s7_judge._tagged() 恒定用精确字符串相等去数分母,这对格闭包臂
是不公平的量尺(格闭包存在的意义就是绕开精确字符串相等去找语义相关记录;
用精确字符串相等去定义"应该召回几条"会系统性低估格闭包臂的真实召回)。
S7-div 的 gold.items 是与三条读取路径(精确匹配/嵌入/格闭包)完全独立机械
推导的,是本题集唯一站得住的召回分母。

用法:
  python scripts/s7div_judge.py --arm-out results/complex_s7div_test_exact.jsonl \
      --questions data/wsc_s7div.jsonl --data data/stale_chain_full.json \
      data/stale_chain_confirm.json --cards-dir results/wt_cards_opentags \
      --out results/s7div_judged_exact.jsonl [--resume]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402

from scripts.wsc_s7_judge import (  # noqa: E402
    extract_claims, _load_entries, _mem_dates, _session_sources,
    _card_sources, _ground_claim, _norm_text, _hit_tokens,
    _mentioned_in_answer, _load_cards,
)


def score_row(client, arm_row: dict, gold_items: List[dict], entry: dict,
              recs: List[dict]) -> dict:
    t0 = time.time()
    mem_dates = _mem_dates(entry) if entry else {}
    srcs = _session_sources(entry) + _card_sources(recs, mem_dates)

    claims, tin, tout, ok = extract_claims(
        client, arm_row.get("question", ""), arm_row.get("answer", ""))

    details: List[dict] = []
    hallucinated: List[dict] = []
    grounded_n = 0
    for c in claims:
        item = str(c.get("item", ""))
        dstr = str(c.get("date_or_period") or "")
        g, via, reason = _ground_claim(item, dstr, srcs)
        details.append({"item": item, "date_or_period": dstr or None,
                        "grounded": g, "via": via or None,
                        "reason": reason or None})
        if g:
            grounded_n += 1
        else:
            hallucinated.append({"item": item,
                                 "date_or_period": dstr or None,
                                 "reason": reason})
    claims_n = len(claims)
    precision = round(grounded_n / claims_n, 4) if claims_n else None

    # 召回:gold.items(机器推导,独立于三条读取路径)里被回答提及的比例。
    ans_norm = _norm_text(arm_row.get("answer", ""))
    ans_toks = _hit_tokens(str(arm_row.get("answer", "")))
    missed: List[dict] = []
    mentioned_n = 0
    for it in gold_items:
        pseudo = {"value": it.get("value", ""), "source_span": ""}
        if _mentioned_in_answer(pseudo, ans_norm, ans_toks):
            mentioned_n += 1
        else:
            missed.append(it)
    recall = round(mentioned_n / len(gold_items), 4) if gold_items else None

    return {
        "question_id": arm_row.get("question_id"), "uid": arm_row.get("uid"),
        "question_type": arm_row.get("question_type"),
        "tag": (arm_row.get("plan") or {}).get("tag"),
        "extract_ok": ok, "claims_n": claims_n, "grounded_n": grounded_n,
        "precision": precision, "claims": details,
        "hallucinated": hallucinated,
        "gold_n": len(gold_items), "mentioned_n": mentioned_n,
        "recall": recall, "missed": missed,
        "usage_input_tokens": tin, "usage_output_tokens": tout,
        "judge_model": extract_claims.__globals__["MODEL"],
        "latency_s": round(time.time() - t0, 2),
    }


def run(arm_out_path: str, questions_path: str, data_paths: List[str],
        cards_dir: str, out_path: str, resume: bool):
    entries = _load_entries(data_paths)
    gold_by_qid = {}
    for l in open(questions_path, encoding="utf-8"):
        s = l.strip()
        if not s:
            continue
        r = json.loads(s)
        gold_by_qid[r["qid"]] = (r.get("gold") or {}).get("items") or []
    arm_rows = [json.loads(l) for l in open(arm_out_path, encoding="utf-8")
                if l.strip()]
    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if resume and outp.exists():
        for l in open(outp, encoding="utf-8"):
            try:
                done.add(json.loads(l)["question_id"])
            except Exception:  # noqa: BLE001
                pass
    fout = open(outp, "a" if resume else "w", encoding="utf-8")
    client = anthropic.Anthropic()
    t_start = time.time()
    scored: List[dict] = []
    tin_sum = tout_sum = 0
    cards_cache: dict = {}
    for row in arm_rows:
        qid = row.get("question_id")
        if qid in done:
            continue
        uid = row.get("uid", "")
        if uid not in cards_cache:
            cards_cache[uid] = _load_cards(cards_dir, uid)
        out = score_row(client, row, gold_by_qid.get(qid, []),
                        entries.get(uid, {}), cards_cache[uid])
        fout.write(json.dumps(out, ensure_ascii=False) + "\n")
        fout.flush()
        scored.append(out)
        tin_sum += out["usage_input_tokens"]
        tout_sum += out["usage_output_tokens"]
        print(f"[{qid}] tag={out['tag']} claims={out['claims_n']} "
              f"grounded={out['grounded_n']} P={out['precision']} "
              f"gold_n={out['gold_n']} R={out['recall']} "
              f"({out['latency_s']}s)", flush=True)
    fout.close()
    ps = [r["precision"] for r in scored if r["precision"] is not None]
    rs = [r["recall"] for r in scored if r["recall"] is not None]
    mp = f"{sum(ps) / len(ps):.4f} (n={len(ps)})" if ps else "n/a"
    mr = f"{sum(rs) / len(rs):.4f} (n={len(rs)})" if rs else "n/a"
    print(f"S7DIV JUDGE DONE: scored {len(scored)} rows ({len(done)} done "
          f"skipped); mean precision {mp}; mean recall {mr}; "
          f"tokens in/out {tin_sum}/{tout_sum}; "
          f"elapsed {time.time() - t_start:.1f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm-out", required=True,
                    help="complex_query_arm.py 输出 jsonl(答案来源)")
    ap.add_argument("--questions", required=True,
                    help="data/wsc_s7div.jsonl(取 qid -> gold.items)")
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--cards-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    run(a.arm_out, a.questions, a.data, a.cards_dir, a.out, a.resume)


if __name__ == "__main__":
    main()
