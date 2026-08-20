# -*- coding: utf-8 -*-
"""scripts/locomo_chain_extract.py — LoCoMo 链标注试点:opus 辅助抽取 + 机械校验。

预注册:results/locomo_chain_pilot_prereg.md(提交 768497a,先于本文件运行)。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade")
from dotenv import load_dotenv
load_dotenv(r"D:\ZZL_cluade\.env")
import anthropic

ROOT = Path(r"D:\ZZL_cluade")
PAT = re.compile(r"\b(moved to|moving to|new (job|place|apartment|house|car|phone)|"
                 r"start(ed|ing) (a|my|at)|switch(ed|ing)|quit|got (a|my) (new|first)|"
                 r"adopt(ed)?|bought|just joined|promoted|broke up|engaged|married|"
                 r"no longer|used to (live|work))\b", re.I)

PROMPT = """You are annotating STATE CHAINS in a real multi-session conversation
between two people. A state chain tracks one attribute (slot) of ONE speaker
changing over time (job, home city, pet, relationship, vehicle, hobby item...).

Below: the session date table, then candidate turns (with neighbors) that may
declare state changes.

For every state you can ground, emit one chain element. Group elements into
chains by (speaker, slot). Rules:
- state_span MUST be an exact verbatim substring of the quoted turn text;
- date = the session's date (YYYY-MM-DD);
- only states the speaker declares about THEMSELVES;
- include single-element chains (one known state) too.

Return ONLY JSON:
{"chains":[{"speaker":"...","slot":"...","elements":[
   {"value":"...","date":"YYYY-MM-DD","state_span":"...","turn_id":"..."}]}]}

SESSION DATES:
{dates}

CANDIDATE TURNS:
{turns}"""


def main() -> int:
    raw = json.loads((ROOT / "data/locomo10.json").read_text(encoding="utf-8"))
    client = anthropic.Anthropic()
    out_all, report = [], []
    for e in raw:
        conv = e["conversation"]
        dates, cand = [], []
        turn_text = {}
        for k, v in conv.items():
            if k.endswith("date_time"):
                dates.append(f"{k[:-10]}: {v}")
        for k, v in conv.items():
            if not isinstance(v, list):
                continue
            for i, t in enumerate(v):
                txt = t.get("text", "") if isinstance(t, dict) else str(t)
                tid = f"{k}#{i}"
                turn_text[tid] = txt
                if PAT.search(txt):
                    spk = t.get("speaker", "?") if isinstance(t, dict) else "?"
                    ctx = ""
                    if i > 0:
                        prev = v[i-1]
                        ctx = (prev.get("text", "") if isinstance(prev, dict)
                               else str(prev))[:120]
                    cand.append(f'[{tid}] ({k}) {spk}: "{txt}"'
                                + (f'\n    (prev: "{ctx}")' if ctx else ""))
        msg = PROMPT.replace("{dates}", "\n".join(dates)).replace(
            "{turns}", "\n".join(cand[:40]))
        r = client.messages.create(model="claude-opus-5", max_tokens=4000,
                                   messages=[{"role": "user", "content": msg}])
        txt = "".join(b.text for b in r.content if b.type == "text")
        try:
            j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        except Exception:
            report.append({"conv": e.get("sample_id"), "error": "parse"})
            continue
        kept = dropped = 0
        for ch in j.get("chains", []):
            elems = []
            for el in ch.get("elements", []):
                span = str(el.get("state_span") or "")
                tid = str(el.get("turn_id") or "")
                src = turn_text.get(tid, "")
                d = str(el.get("date") or "")
                okdate = bool(re.match(r"\d{4}-\d{2}-\d{2}$", d))
                if span and src and span in src and okdate and el.get("value"):
                    elems.append({"value": el["value"], "date": d,
                                  "state_span": span, "turn_id": tid})
                else:
                    dropped += 1
            # 链内日期非降
            ds = [x["date"] for x in elems]
            if elems and ds == sorted(ds):
                out_all.append({"conv": e.get("sample_id"),
                                "speaker": ch.get("speaker"),
                                "slot": ch.get("slot"), "elements": elems})
                kept += 1
            elif elems:
                dropped += len(elems)
        report.append({"conv": e.get("sample_id"), "chains_kept": kept,
                       "elems_dropped": dropped})
        print(f"[{e.get('sample_id')}] chains={kept} dropped_elems={dropped}",
              flush=True)
    multi = sum(1 for c in out_all if len(c["elements"]) >= 2)
    summary = {"chains": len(out_all), "multi_value_chains": multi,
               "per_conv": report}
    json.dump({"summary": summary, "chains": out_all},
              open(ROOT / "data/locomo_chains_pilot.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n合计:链 {len(out_all)} 条,其中 ≥2 值 {multi} 条 "
          f"(判据:≥50 段 且 ≥2值链 ≥15)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
