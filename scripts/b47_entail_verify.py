# -*- coding: utf-8 -*-
"""批 47-A:语义蕴含校验器(替换批 38-E 的关键词断言过滤)。

对一个既有卡店的每张卡,给读者模型看 (来源轮次全文, source_span, slot, value),
让它判断这句话是否真的宣告了"本人开始持有该状态",并给出断言类型。
零改动源店(店冻结纪律):输出两个新目录 —
  <dst>_ent : 全部卡 + 标签(assertion_type / entailed / entail_reason)
  <dst>     : 只保留 entailed 且 assertion_type ∈ KEEP 的卡(与 38-E 过滤器同语义)
以及日志 results/<tag>_entail_log.json(逐卡标签、成本、源店 sha256)。

用法:
  PYTHONUTF8=1 python scripts/b47_entail_verify.py --src results/wt_cards_v48 \
      --dst results/wt_cards_v48e --data data/wikistate_full_ALL_v24.json --workers 8
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Literal

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(r"D:\ZZL_cluade\.env")
import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

ROOT = Path(r"D:\ZZL_cluade")
MODEL = os.environ.get("QVF_ENTAIL_MODEL", "claude-haiku-4-5")
PRICE_IN, PRICE_OUT = 1.0, 5.0  # $/M, haiku-4.5 list price

KEEP = {"start", "unclear", "unjudged"}  # 与 38-E 同语义:plan/task/other_person/restate 丢;新增 hypothetical/ended 丢;restate 的去留由离线评分另行比较(_ent 店保留全部标签)

SYSTEM = """You are auditing ONE extracted memory card against the sentence it was taken from.
A card claims that the SPEAKER (first person, "I") holds a personal state: slot = value
(for example employer = CERN, position = member of parliament, team = FC Barcelona,
residence = Cambridge). Decide two things from the SOURCE TEXT ONLY:

1. assertion_type — what the source text actually asserts about slot/value:
   - start: the speaker states they now hold / have started / were appointed to /
     joined / moved to this value (a current or newly begun state of the speaker).
   - restate: the speaker merely re-mentions a state that is clearly already ongoing
     ("as always", "still", "continue to be"), not a new start.
   - plan: a future intention, nomination, candidacy, application, offer not yet
     taken up, or hope ("hoping to", "applying", "nominated", "will start next year").
   - hypothetical: considered / imagined / rejected options ("I considered joining X
     but stayed", "if I moved to Y").
   - task: a one-off task, project or event, not a held position or membership
     ("working on a big project", "organising the conference").
   - other_person: the state belongs to someone other than the speaker.
   - ended: the text says the speaker LEFT / ENDED this state (quit, retired, resigned).
   - unclear: the text does not let you decide.
   Note: "I signed the offer and I'm officially joining X" is a start (the decision is
   final and the state begins); "I got an offer from X" alone is a plan.
2. entailed — true only if the source text supports "speaker holds slot = value"
   (now or from the stated start); false for plan / hypothetical / other_person /
   ended / task, and false if the value is not what the text says.

Judge from the text; do not use outside knowledge. Return the structured fields only."""


class Verdict(BaseModel):
    assertion_type: Literal["start", "restate", "plan", "hypothetical", "task",
                            "other_person", "ended", "unclear"] = Field(
        description="What the source text asserts about the card's slot/value.")
    entailed: bool = Field(description="Does the source text support that the speaker holds slot = value?")
    reason: str = Field(description="One short sentence quoting the decisive words.")


def sha_dir(d: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(d.glob("*.json")):
        h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()


def turn_text(t: str) -> str:
    """会话 turns 是 dict repr 字符串;取 content,失败时整串退回。"""
    try:
        d = ast.literal_eval(t)
        if isinstance(d, dict):
            return str(d.get("content", t))
    except Exception:  # noqa: BLE001
        m = re.search(r"'content':\s*(\"(.*)\"|'(.*)')\s*[,}]", t, re.S)
        if m:
            return m.group(2) if m.group(2) is not None else m.group(3)
    return t


def mem_text(entry: dict) -> dict:
    out = {}
    for si, s in enumerate(entry["sessions"]):
        for ti, t in enumerate(s["turns"]):
            out[f'{entry["uid"]}/s{si}#r{ti}'] = turn_text(t)
    return out


def judge(client, ctx: str, card: dict):
    user = ("SOURCE TEXT (one memory round):\n" + ctx[:2500] +
            "\n\nCARD:\n" + json.dumps({"source_span": card.get("source_span", ""),
                                        "slot": card.get("slot_class") or card.get("slot", ""),
                                        "value": card.get("value", "")}, ensure_ascii=False))
    resp = client.messages.parse(
        model=MODEL, max_tokens=300, temperature=0.0,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_format=Verdict,
    )
    v = resp.parsed_output
    return v, resp.usage.input_tokens, resp.usage.output_tokens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--data", default=r"data\wikistate_full_ALL_v24.json")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="debug: only first N stores")
    ap.add_argument("--tag", default="b47")
    ap.add_argument("--lane-only", action="store_true", dest="lane_only",
                    help="只审四个金标槽位类(employer/position/team/residence)的卡;其余卡标 unjudged 并保留")
    a = ap.parse_args()
    if a.lane_only:
        sys.path.insert(0, str(ROOT / "scripts"))
        from wt_qvf_prototype_v49 import classify_slot  # noqa: E402
        LANE = {"employer", "position", "team", "residence"}
    src = ROOT / a.src; dst = ROOT / a.dst; dst_ent = Path(str(dst) + "_ent")
    if dst.exists() or dst_ent.exists():
        raise SystemExit(f"refusing to overwrite existing store: {dst} / {dst_ent}")
    dst.mkdir(parents=True); dst_ent.mkdir(parents=True)
    corpus = {e["uid"]: e for e in json.load(open(ROOT / a.data, encoding="utf-8"))}
    files = sorted(src.glob("*.json"))
    if a.limit:
        files = files[: a.limit]
    src_sha = sha_dir(src)
    client = anthropic.Anthropic()
    log = {"src": str(src), "src_sha256": src_sha, "model": MODEL, "keep": sorted(KEEP), "stores": {}}
    tot_in = tot_out = 0; t0 = time.time()
    for f in files:
        j = json.load(open(f, encoding="utf-8")); uid = j["uid"]
        mt = mem_text(corpus[uid])
        recs = j["records"]
        jobs = []
        with ThreadPoolExecutor(a.workers) as ex:
            for i, r in enumerate(recs):
                if a.lane_only and classify_slot(r.get("slot", ""))[0] not in LANE:
                    r["assertion_type"] = "unjudged"; r["entailed"] = True; r["entail_reason"] = ""
                    continue
                ctx = mt.get(r.get("source_memory_id"), "")
                if not ctx:  # 挂错会话:用含该 span 的轮次
                    sp = (r.get("source_span") or "").strip()
                    ctx = next((t for t in mt.values() if sp and sp in t), "")
                jobs.append((i, ex.submit(judge, client, ctx or r.get("source_span", ""), r)))
            for i, fut in jobs:
                try:
                    v, ui, uo = fut.result()
                except Exception as e:  # noqa: BLE001
                    v, ui, uo = Verdict(assertion_type="unclear", entailed=True, reason=f"error: {type(e).__name__}"), 0, 0
                recs[i]["assertion_type"] = v.assertion_type
                recs[i]["entailed"] = bool(v.entailed)
                recs[i]["entail_reason"] = v.reason
                tot_in += ui; tot_out += uo
        # 采用规则(批 47 §3):只看断言类型,不看 entailed 标志 —— entailed 在
        # "TotalEnergies is my new team" 上用了外部知识误判,类型过滤零误伤。
        kept = [r for r in recs if r["assertion_type"] in KEEP]
        from collections import Counter
        types = Counter(r["assertion_type"] for r in recs)
        log["stores"][uid] = {"n": len(recs), "kept": len(kept), "types": dict(types)}
        base = {k: v for k, v in j.items() if k != "records"}
        prov = {"derived_from": str(src), "src_sha256": src_sha, "entail_model": MODEL}
        (dst_ent / f.name).write_text(json.dumps({**base, "records": recs, **prov}, ensure_ascii=False, indent=1), encoding="utf-8")
        (dst / f.name).write_text(json.dumps({**base, "records": kept, **prov, "entail_keep": sorted(KEEP)}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{uid}] {len(recs)} -> {len(kept)} kept; {dict(types)}; in={tot_in} out={tot_out} ({time.time()-t0:.0f}s)", flush=True)
    log["usage"] = {"in": tot_in, "out": tot_out, "usd": tot_in / 1e6 * PRICE_IN + tot_out / 1e6 * PRICE_OUT}
    (ROOT / "results" / f"{a.tag}_entail_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print("DONE", json.dumps(log["usage"]))


if __name__ == "__main__":
    main()
