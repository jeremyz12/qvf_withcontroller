# -*- coding: utf-8 -*-
"""LoCoMo 链抽取重试轮(预注册许可的一次修正):observation 辅助候选增广。
机械校验与首轮完全相同;产物并入后按 (conv,speaker,slot) 归一合并。"""
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

PROMPT = """You are annotating STATE CHAINS in a real multi-session conversation.
You get: session dates, per-session OBSERVATION notes (facts the dataset ships),
and the full turn list of sessions mentioned. Build chains of one speaker's own
attribute changing over time (job, home, pet, relationship, vehicle, hobby gear,
business...). PREFER chains with 2+ states.

Rules: state_span MUST be an exact verbatim substring of the referenced turn's
text; date = that session's date (YYYY-MM-DD); self-declared states only.

Return ONLY JSON:
{"chains":[{"speaker":"...","slot":"...","elements":[
 {"value":"...","date":"YYYY-MM-DD","state_span":"...","turn_id":"session_k#i"}]}]}

SESSION DATES:
{dates}

OBSERVATIONS (hints, not ground truth):
{obs}

TURNS:
{turns}"""


def main() -> int:
    raw = json.loads((ROOT / "data/locomo10.json").read_text(encoding="utf-8"))
    client = anthropic.Anthropic()
    out_all = []
    for e in raw:
        conv = e["conversation"]
        dates, turns = [], []
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
                spk = t.get("speaker", "?") if isinstance(t, dict) else "?"
                turns.append(f"[{tid}] {spk}: {txt[:220]}")
        obs = json.dumps(e.get("observation", {}), ensure_ascii=False)[:6000]
        msg = PROMPT.replace("{dates}", "\n".join(dates)) \
                    .replace("{obs}", obs) \
                    .replace("{turns}", "\n".join(turns)[:60000])
        txt = ""
        for attempt in range(4):
            try:
                r = client.messages.create(model="claude-opus-5", max_tokens=4000,
                                           messages=[{"role": "user",
                                                      "content": msg}])
                txt = "".join(b.text for b in r.content if b.type == "text")
                break
            except Exception as err:  # noqa: BLE001
                print(f"[{e.get('sample_id')}] attempt {attempt}: "
                      f"{type(err).__name__}", flush=True)
                import time as _t
                _t.sleep(5 * (attempt + 1))
        if not txt:
            continue
        try:
            j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        except Exception:
            print(f"[{e.get('sample_id')}] parse fail", flush=True)
            continue
        kept = 0
        for ch in j.get("chains", []):
            elems = []
            for el in ch.get("elements", []):
                span = str(el.get("state_span") or "")
                tid = str(el.get("turn_id") or "")
                src = turn_text.get(tid, "")
                d = str(el.get("date") or "")
                if span and src and span in src and \
                   re.match(r"\d{4}-\d{2}-\d{2}$", d) and el.get("value"):
                    elems.append({"value": el["value"], "date": d,
                                  "state_span": span, "turn_id": tid})
            ds = [x["date"] for x in elems]
            if elems and ds == sorted(ds):
                out_all.append({"conv": e.get("sample_id"),
                                "speaker": str(ch.get("speaker")).lower(),
                                "slot": ch.get("slot"), "elements": elems})
                kept += 1
        print(f"[{e.get('sample_id')}] chains={kept}", flush=True)
    json.dump(out_all, open(ROOT / "data/locomo_chains_r2.json", "w",
                            encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"r2 链 {len(out_all)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
