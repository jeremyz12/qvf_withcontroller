# -*- coding: utf-8 -*-
"""v2.4:按填充池严判结果做定向清洗(v2.3 → v2.4)。

来源:results/pool_verdicts.json(70 条 CONFIRMED,每条标注 kind)。
传播规则:只从"槽位相关"的链里删——kind=employer/position 互相关联(职衔隐含
雇主),residence/team 各自独立。链会话(chain_index 有值)一律不动。
双闸:542 链锚完好 + 确认句在相关链中零残留。
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_corpus_v21 import expand_sentence, unwrap

KIND2SLOT = {"employer": {"employer", "position"}, "position": {"position", "employer"},
             "residence": {"residence"}, "team": {"team"}}


def norm(s): return re.sub(r"\s+", " ", s or "").strip().lower()


def main():
    dry = "--dry" in sys.argv
    v = json.loads((ROOT / "results/pool_verdicts.json").read_text(encoding="utf-8"))
    conf = [x for x in v if x["verdict"] == "CONFIRMED" and x.get("quote")]
    data = json.loads((ROOT / "data/wikistate_full_ALL_v23.json").read_text(encoding="utf-8"))
    log = open(ROOT / "results/corpus_v24_edits.jsonl", "w", encoding="utf-8")
    n_cut, touched = 0, set()
    # 批31-C 按链严判确认的残留:该轮有完整链上下文,直接按 uid 定向删除
    perchain = {}
    for x in json.loads((ROOT / "results/v23_residual_verdicts.json").read_text(encoding="utf-8")):
        if x["verdict"] == "CONFIRMED":
            perchain.setdefault(x["uid"], []).append({"quote": x["quote_head"]})
    for e in data:
        pats = [c for c in conf if e["slot"] in KIND2SLOT.get(c.get("kind") or "", set())]
        pats = pats + perchain.get(e["uid"], [])
        if not pats: continue
        for s in e.get("sessions", []):
            if s.get("chain_index") is not None: continue
            turns = s.get("turns", []); i = 0
            while i < len(turns):
                role, body, rebuild = unwrap(turns[i])
                if not isinstance(body, str) or not body.strip():
                    i += 1; continue
                cuts, newbody = [], body
                for c in pats:
                    q = c["quote"].strip()
                    if len(q) < 15: continue
                    pat = r"\s+".join(re.escape(w) for w in q[:120].split())
                    m = re.search(pat, newbody, re.I)
                    if not m: continue
                    x, y = expand_sentence(newbody, m.start(), m.end())
                    seg = newbody[x:y].strip()
                    if not seg: continue
                    cuts.append(seg); newbody = (newbody[:x] + newbody[y:]).strip()
                if not cuts:
                    i += 1; continue
                newbody = re.sub(r"  +", " ", newbody)
                n_cut += len(cuts); touched.add(e["uid"])
                log.write(json.dumps({"uid": e["uid"], "slot": e["slot"],
                                      "session": s.get("date"), "role": role,
                                      "cuts": cuts}, ensure_ascii=False) + "\n")
                if dry: i += 1; continue
                if newbody: turns[i] = rebuild(newbody); i += 1
                else: turns.pop(i)
    bad = 0
    for e in data:
        blob = norm(json.dumps(e.get("sessions", []), ensure_ascii=False))
        for c in e["chain"]:
            if norm(c["state_span"]) not in blob:
                print(f"闸1违例 锚丢失: {e['uid']}"); bad += 1
    print(f"v2.4:删除 {n_cut} 句,涉及 {len(touched)} 链;锚闸违例 {bad}")
    if dry: print("(dry run)"); return
    if bad: print("ABORT"); return
    (ROOT / "data/wikistate_full_ALL_v24.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data/b31_v24_touched.txt").write_text(",".join(sorted(touched)), encoding="utf-8")
    print("v2.4 写出")


main()
