# -*- coding: utf-8 -*-
"""批 42 冻结保留集 2·步骤3:记忆化渲染 + 干净填充装配 → data/wikistate_holdout2_v1.json

逐字复用 scripts/holdout_render_v1.py 的渲染器(claude-opus-5、同提示词、同
逐字锚点校验、同日期铺法、同 probing_queries 公式)与填充装配规范(v2.3 已审
填充池、池层面剔除 CONFIRMED、装配后复扫残余须为零)。三处改动:
  (1) SEED 换新(20260904,记入预注册与本文件头,与 v1 的 20260902 不同);
  (2) uid 前缀改 hold2<PROP>(与既有 40 链保留集 v1 的 hold<PROP> 视觉区分,
      QID 本身已保证零交集,前缀只是双重防呆);
  (3) 输入输出路径改为 holdout2_*(itempool/selection/part/最终产物)。

用法:python scripts/b42_holdout_render_v1.py            # 全部四槽位按配额
产物:data/wikistate_holdout2_v1.json(经 QVF_HOLDOUT_OUT 覆盖时先落分片)
"""
from __future__ import annotations

import collections
import hashlib
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

MODEL = "claude-opus-5"
SEED = 20260904   # 批 42 新种子(v1 为 20260902),预注册记录
QUOTA = {"P108": 10, "P39": 10, "P54": 10, "P551": 10}
import os as _os
if _os.environ.get("QVF_HOLDOUT_QUOTA"):
    QUOTA = json.loads(_os.environ["QVF_HOLDOUT_QUOTA"])
OUT_PATH = _os.environ.get("QVF_HOLDOUT_OUT", "data/wikistate_holdout2_v1.json")
SEL_PATH = _os.environ.get("QVF_HOLDOUT_SEL", "data/holdout2_selection_v1.json")
NOUNS = {"P39": "position", "P54": "team", "P108": "employer",
         "P551": "residence"}
PRE = re.compile(r"^\{'role': '[a-z]+', 'content': (\"|')")


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


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def turn_content(t: str) -> str:
    m = PRE.match(t)
    s = t[m.end():] if m else t
    return re.sub(r"(\"|')\}$", "", s)


def pool_hash(turns) -> str:
    return hashlib.md5("\n".join(turn_content(t) for t in turns)
                       .encode("utf-8")).hexdigest()[:10]


def build_filler_bank():
    """同 v1:1,100 个审计过的填充会话 → 剔除 CONFIRMED → 复扫 → 干净池。
    池本身是共享既审资源(与 v1 同一份),批 42 不重新审计——沿用同一构造
    规范,只是抽样种子换新(见下方 rng = random.Random(SEED + md5(qid)))。"""
    pool = json.loads((ROOT / "data/filler_pool_v23.json")
                      .read_text(encoding="utf-8"))
    verdicts = json.loads((ROOT / "results/pool_verdicts.json")
                          .read_text(encoding="utf-8"))
    bad_h = {x["h"] for x in verdicts if x["verdict"] == "CONFIRMED"}
    quotes = [x["quote"] for x in verdicts
              if x["verdict"] == "CONFIRMED" and x.get("quote")]
    resid = json.loads((ROOT / "results/v23_residual_verdicts.json")
                       .read_text(encoding="utf-8"))
    quotes += [x["quote_head"] for x in resid if x["verdict"] == "CONFIRMED"]
    src = json.loads((ROOT / "data/wikistate_full_ALL_v23.json")
                     .read_text(encoding="utf-8"))
    by_h = {}
    for e in src:
        for s in e.get("sessions", []):
            if s.get("chain_index") is not None:
                continue
            h = pool_hash(s["turns"])
            if h in pool and h not in by_h:
                by_h[h] = s["turns"]
    bank, resid_n = [], 0
    for h, t in sorted(by_h.items()):
        if h in bad_h:
            continue
        blob = norm(json.dumps(t, ensure_ascii=False))
        if any(len(norm(q)[:60]) >= 20 and norm(q)[:60] in blob for q in quotes):
            resid_n += 1
            continue
        bank.append((h, t))
    print(f"filler pool={len(pool)} recovered={len(by_h)} "
          f"dropped_CONFIRMED={len(bad_h)} dropped_rescan={resid_n} "
          f"bank={len(bank)}", flush=True)
    return bank, quotes


def midpoint(a, b):
    from datetime import date as _d

    def p(s):
        y, m, d = (s + "-01-01")[:10].split("-")
        return _d(int(y), max(1, int(m)), max(1, int(d)))
    da, db = p(a), p(b)
    return (da + (db - da) / 2).isoformat()


def main():
    selp = ROOT / SEL_PATH
    SEL = json.loads(selp.read_text(encoding="utf-8")) if selp.exists() else None
    if SEL:
        print(f"selection pinned: {sum(len(v) for v in SEL['selection'].values())}"
              f" chains, hist={SEL['achieved_hist']}", flush=True)
    bank, quotes = build_filler_bank()
    client = anthropic.Anthropic()
    outp = ROOT / OUT_PATH
    out = json.loads(outp.read_text(encoding="utf-8")) if outp.exists() else []
    done_q = {e["uid"].split("-", 1)[1] for e in out}
    if done_q:
        print(f"resume: {len(out)} chains already in {OUT_PATH}", flush=True)
    used_qids = set(done_q)
    for PROP, quota in QUOTA.items():
        NOUN = NOUNS[PROP]
        f = ROOT / f"data/holdout2_itempool_{PROP}.json"
        if not f.exists():
            print(f"!! missing {f}", flush=True)
            continue
        pool = json.loads(f.read_text(encoding="utf-8"))
        items = pool
        if SEL:
            want = SEL["selection"].get(PROP, [])
            by_qid = {e["qid"]: e for e in pool}
            items = [by_qid[q] for q in want if q in by_qid]
            quota = len(items)
            chosen = set(want)
            spare = collections.defaultdict(list)
            for e in pool:
                if e["qid"] not in chosen:
                    spare[min(8, len(e["chain"]))].append(e)
            items = items + [x for L in sorted(spare) for x in spare[L]]
        need_len = collections.Counter(min(8, len(e["chain"]))
                                       for e in items[:quota]) if SEL else None
        kept = sum(1 for e in out if e["uid"].startswith(f"hold2{PROP}"))
        if need_len is not None:
            for e in out:
                if e["uid"].startswith(f"hold2{PROP}"):
                    need_len[min(8, len(e["chain"]))] -= 1
        for i, it in enumerate(items):
            if kept >= quota:
                break
            if it["qid"] in used_qids:
                continue
            L = min(8, len(it["chain"]))
            if need_len is not None and need_len[L] <= 0:
                continue
            chain = it["chain"][:8]

            def _render_state(k_c):
                k, c = k_c
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
                        print(f"[{it['qid']}] s{k} attempt {attempt}: "
                              f"{type(e).__name__}: {str(e)[:70]}", flush=True)
                        time.sleep(4)
                        continue
                    if cand and not validate_state(cand, c):
                        return k, cand
                    if cand:
                        print(f"[{it['qid']}] s{k} attempt {attempt}: "
                              f"{validate_state(cand, c)[:2]}", flush=True)
                return k, None

            with ThreadPoolExecutor(max_workers=4) as ex:
                got = dict(ex.map(_render_state, list(enumerate(chain))))
            states = [got[k] for k in range(len(chain))]
            ok_item = all(st is not None for st in states)
            if not ok_item:
                print(f"[{it['qid']}] FAILED render, skipped", flush=True)
                continue

            rng = random.Random(SEED + int(
                hashlib.md5(it["qid"].encode()).hexdigest()[:8], 16))
            distractors = [t for _, t in rng.sample(bank, 30)]
            y0 = int(chain[0]["start"][:4])
            y1 = max(y0 + 1, int(chain[-1]["start"][:4]))
            sessions = [{"date": st.date, "turns": st.session_turns,
                         "chain_index": ci} for ci, st in enumerate(states)]
            for j, turns in enumerate(distractors):
                y = y0 + (j % (y1 - y0 + 1))
                m = 1 + (j * 5) % 12
                d = 1 + (j * 7) % 27
                sessions.append({"date": f"{y}-{m:02d}-{d:02d}",
                                 "turns": turns, "chain_index": None})
            sessions.sort(key=lambda s: s["date"])

            last, mid = chain[-1], chain[len(chain) // 2]
            pt = chain[0] if chain[0] is not mid else chain[1]
            today = last["start"][:10]
            point_date = midpoint(pt["start"], pt["end"])
            name = it["name"]
            uid = f"hold2{PROP}{kept:03d}-{it['qid']}"
            out.append({
                "uid": uid,
                "type": "WIKISTATE",
                "slot": NOUN,
                "chain": [{"value": c["label"], "date": c["start"],
                           "state_span": st.state_span}
                          for c, st in zip(chain, states)],
                "sessions": sessions,
                "probing_queries": {
                    "dim1_current": {
                        "q": f"(Today is {today}.) What's my current {NOUN} "
                             f"these days?", "gold": last["label"]},
                    "dim2_premise_mid": {
                        "q": f"(Today is {today}.) Since my {NOUN} is "
                             f"{mid['label']}, what would typically be "
                             f"relevant to know about it?",
                        "gold": (f"The premise is outdated: as of {today} "
                                 f"{name}'s current {NOUN} is {last['label']} "
                                 f"(the {mid['label']} tenure ended "
                                 f"{mid['end']}). A correct answer must correct "
                                 f"the premise; it must not answer as if "
                                 f"{mid['label']} were current."),
                        "presupposed": mid["label"]},
                    "dim4_point_in_time": {
                        "q": f"What {NOUN} did I have on {point_date}?",
                        "gold": pt["label"], "date": point_date},
                    "dim5_trajectory": {
                        "q": f"How has my {NOUN} changed over time — which "
                             "values, in order?",
                        "gold": " -> ".join(c["label"] for c in chain)},
                },
                "attribution": f"States derived from Wikidata {it['qid']} "
                               f"{PROP} qualifiers (CC0); filler sessions drawn "
                               "from the audited v2.3 filler pool (remixed from "
                               "STALE, CC BY 4.0).",
            })
            outp.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                             encoding="utf-8")
            kept += 1
            if need_len is not None:
                need_len[L] -= 1
            used_qids.add(it["qid"])
            print(f"[{PROP} {kept}/{quota}] {name}: {len(states)} states",
                  flush=True)
            time.sleep(0.2)
        print(f"== {PROP}: {kept}/{quota} rendered", flush=True)

    bad_anchor = bad_quote = 0
    for e in out:
        blob = norm(json.dumps(e["sessions"], ensure_ascii=False))
        for c in e["chain"]:
            if norm(c["state_span"]) not in blob:
                print(f"闸1违例 锚丢失: {e['uid']}")
                bad_anchor += 1
        fill = norm(json.dumps([s for s in e["sessions"]
                                if s["chain_index"] is None],
                               ensure_ascii=False))
        for q in quotes:
            qq = norm(q)[:60]
            if len(qq) >= 20 and qq in fill:
                print(f"闸2违例 污染残留: {e['uid']} :: {q[:60]}")
                bad_quote += 1
    print(f"chains={len(out)} 锚闸违例={bad_anchor} 污染残留={bad_quote}")
    if bad_anchor or bad_quote:
        print("ABORT — not written")
        return
    (ROOT / OUT_PATH).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"WROTE {OUT_PATH} ({len(out)} chains)")


if __name__ == "__main__":
    main()
