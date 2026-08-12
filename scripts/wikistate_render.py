# -*- coding: utf-8 -*-
"""WikiState 试点·步骤3:记忆化渲染 → stale-chain 同构 schema。

真实任职链(Wikidata 限定符)→ opus 渲染为第一人称会话(逐字锚点验证)
+ STALE 干扰干草堆 → data/wikistate_full.json(与 stale_chain_full 同构,
全部既有实验臂/判分工具直接复用)。问题为第一人称,金答案保持机械导出值。"""
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

MODEL = "claude-opus-5"

import sys as _sys
PROP = _sys.argv[1] if len(_sys.argv) > 1 else "P39"
NOUN = {"P39": "position", "P54": "team", "P108": "employer", "P551": "residence"}[PROP]
ITEMS_FILE = ("data/wikistate_items.json" if PROP == "P39"
              else f"data/wikistate_items_{PROP}.json")
FULL_FILE = ("data/wikistate_full.json" if PROP == "P39"
             else f"data/wikistate_full_{PROP}.json")
if len(_sys.argv) > 2:
    ITEMS_FILE = _sys.argv[2]
if len(_sys.argv) > 3:
    FULL_FILE = _sys.argv[3]



class RenderedState(BaseModel):
    date: str = Field(description="Session date, must EXACTLY equal the given start date.")
    session_turns: list[str] = Field(
        description="3-4 casual first-person messages from the user to their "
        "assistant, written on the day they started this position. EXACTLY ONE "
        "turn must state the new position naturally (sworn in / appointed / "
        "started as / elected ...). Do not mention other positions.")
    state_span: str = Field(
        description="VERBATIM contiguous substring of one turn stating the "
        "position; must contain the position title verbatim.")


PROMPT = """You render real life events as personal-assistant memory sessions.
The user is {name}. Write ONE session dated {date}: 3-4 casual first-person
user messages (talking to their AI assistant), exactly one of which naturally
states that "{title}" is now their new {noun} — the span must contain that
EXACT name verbatim. Include mundane life details; do not mention any other
{noun} values. Vary tone (style hint #{k}).
"""


def validate_state(st: RenderedState, c) -> list:
    errs = []
    if st.date != c["start"]:
        errs.append(f"date {st.date} != {c['start']}")
    if not any(st.state_span in t for t in st.session_turns):
        errs.append("span not verbatim in turns")
    if c["label"].lower() not in st.state_span.lower():
        errs.append(f"title missing in span: {c['label'][:30]}")
    return errs


def main():
    items = json.load(open(ITEMS_FILE, encoding="utf-8"))
    stale = json.load(open(r"data/stale_T1_T2_400_FULL.json", encoding="utf-8"))
    client = anthropic.Anthropic()
    rng = random.Random(20260807)
    out = []
    for i, it in enumerate(items):
        chain = it["chain"][:8]  # 超长链截到 8 段,控制条目体量
        states = []
        ok_item = True
        for k, c in enumerate(chain):
            st = None
            for attempt in range(3):
                try:
                    resp = client.messages.parse(
                        model=MODEL, max_tokens=1500,
                        messages=[{"role": "user", "content": PROMPT.format(
                            name=it["name"], date=c["start"],
                            title=c["label"], k=k, noun=NOUN)}],
                        output_format=RenderedState,
                    )
                    cand = resp.parsed_output
                except Exception as e:  # noqa: BLE001
                    print(f"[{it['qid']}] s{k} attempt {attempt}: {type(e).__name__}",
                          flush=True)
                    continue
                if cand and not validate_state(cand, c):
                    st = cand
                    break
                if cand:
                    print(f"[{it['qid']}] s{k} attempt {attempt}: "
                          f"{validate_state(cand, c)[:2]}", flush=True)
            if st is None:
                ok_item = False
                break
            states.append(st)
        if not ok_item:
            print(f"[{it['qid']}] FAILED render, skipped", flush=True)
            continue
        it = {**it, "chain": chain}

        class _RC:  # 适配后续代码的 rc.states 访问
            pass
        rc = _RC()
        rc.states = states
        # 干扰会话:复用 STALE 干草堆(CC BY),日期均匀铺在链的年代范围
        pool = []
        for s_it in rng.sample(stale, 12):
            for sess in (s_it.get("haystack_session") or [])[:5]:
                turns = sess if isinstance(sess, list) else [str(sess)]
                pool.append([str(t)[:400] for t in turns[:5]])
        rng.shuffle(pool)
        distractors = pool[:30]
        y0 = int(it["chain"][0]["start"][:4])
        y1 = max(y0 + 1, int(it["chain"][-1]["start"][:4]))
        sessions = []
        for ci, st in enumerate(rc.states):
            sessions.append({"date": st.date, "turns": st.session_turns,
                             "chain_index": ci})
        for j, turns in enumerate(distractors):
            y = y0 + (j % (y1 - y0 + 1))
            m = 1 + (j * 5) % 12
            d = 1 + (j * 7) % 27
            sessions.append({"date": f"{y}-{m:02d}-{d:02d}", "turns": turns,
                             "chain_index": None})
        sessions.sort(key=lambda s: s["date"])

        # 按(可能截断的)链重算四问与金答案,避免与 build 阶段全链版错位
        def midpoint(a, b):
            from datetime import date as _d
            def p(s):
                y, m, d = (s + "-01-01")[:10].split("-")
                return _d(int(y), max(1, int(m)), max(1, int(d)))
            da, db = p(a), p(b)
            return (da + (db - da) / 2).isoformat()

        last, mid = chain[-1], chain[len(chain) // 2]
        pt = chain[0] if chain[0] is not mid else chain[1]
        today = last["start"][:10]
        point_date = midpoint(pt["start"], pt["end"])
        name = it["name"]
        qs = {
            "dim1": {"gold": last["label"]},
            "dim2": {"presupposed": mid["label"],
                     "gold": (f"The premise is outdated: as of {today} {name}'s "
                              f"current {NOUN} is {last['label']} (the "
                              f"{mid['label']} tenure ended {mid['end']}). A "
                              f"correct answer must correct the premise; it must "
                              f"not answer as if {mid['label']} were current.")},
            "dim4": {"gold": pt["label"], "date": point_date},
            "dim5": {"gold": " -> ".join(c["label"] for c in chain)},
        }
        out.append({
            "uid": f"wiki{PROP}{i:03d}-{it['qid']}",
            "type": "WIKISTATE",
            "slot": NOUN,
            "chain": [{"value": c["label"], "date": c["start"],
                       "state_span": st.state_span}
                      for c, st in zip(it["chain"], rc.states)],
            "sessions": sessions,
            "probing_queries": {
                "dim1_current": {
                    "q": f"(Today is {today}.) What's my current {NOUN} these days?",
                    "gold": qs["dim1"]["gold"]},
                "dim2_premise_mid": {
                    "q": f"(Today is {today}.) Since my {NOUN} is "
                         f"{qs['dim2']['presupposed']}, what would typically "
                         f"be relevant to know about it?",
                    "gold": qs["dim2"]["gold"],
                    "presupposed": qs["dim2"]["presupposed"]},
                "dim4_point_in_time": {
                    "q": f"What {NOUN} did I have on {qs['dim4']['date']}?",
                    "gold": qs["dim4"]["gold"], "date": qs["dim4"]["date"]},
                "dim5_trajectory": {
                    "q": f"How has my {NOUN} changed over time — which "
                         "values, in order?",
                    "gold": qs["dim5"]["gold"]},
            },
            "attribution": f"States derived from Wikidata {it['qid']} P39 "
                           "qualifiers (CC0); distractor sessions remixed from "
                           "STALE (CC BY 4.0).",
        })
        print(f"[{len(out)}] {it['name']}: {len(rc.states)} states rendered",
              flush=True)
        time.sleep(0.3)
    Path(FULL_FILE).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"RENDERED {len(out)} items -> data/wikistate_full.json")


if __name__ == "__main__":
    main()
