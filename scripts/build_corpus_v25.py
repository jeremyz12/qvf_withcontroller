# -*- coding: utf-8 -*-
"""v2.5 语料构建(批 34):在 v2.4 上 (1) 按裁决文件删除 CONFIRMED 句子(手术式,复用 v2.1 工具,双闸),
(2) 链内逐字节重复的填充会话去重(保留首次出现,只删 FILLER),(3) 题集移除 8 道近平局 longest_tenure 题(记录不改链)。
用法:python scripts/build_corpus_v25.py --verdicts results/b34_audit_verdicts.json [--dry]
产物:data/wikistate_full_ALL_v25.json、data/wsc_s5_v25.jsonl、results/b34_v25_changelog.json
"""
import argparse, json, re, sys
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_corpus_v21 import unwrap, expand_sentence, find_span  # noqa: E402


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def pd(s):
    y, m, d = (int(x) for x in s.split("-")); return date(y, max(m, 1), max(d, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdicts", required=True, help="JSON list of {uid, quote, verdict, suggested_fix}")
    ap.add_argument("--src", default="data/wikistate_full_ALL_v24.json")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    data = json.loads((ROOT / a.src).read_text(encoding="utf-8"))
    verdicts = [v for v in json.loads((ROOT / a.verdicts).read_text(encoding="utf-8")) if v.get("verdict") == "CONFIRMED"]
    by_uid = {}
    for v in verdicts:
        by_uid.setdefault(v["uid"], []).append(v)
    log = {"deleted": [], "dedup": [], "not_found": [], "anchor_check": None, "residue": None}
    anchors_before = sum(len(e["chain"]) for e in data)
    for e in data:
        # (2) dedupe identical filler sessions
        seen, keep = set(), []
        for si, s in enumerate(e["sessions"]):
            key = json.dumps(s["turns"], ensure_ascii=False)
            if key in seen and s.get("chain_index") is None:
                log["dedup"].append({"uid": e["uid"], "session": si + 1, "date": s["date"]}); continue
            seen.add(key); keep.append(s)
        e["sessions"] = keep
        # (1) surgical sentence deletion
        for v in by_uid.get(e["uid"], []):
            q = v["quote"]; hit = False
            for s in e["sessions"]:
                for ti, t in enumerate(s["turns"]):
                    role, body, rebuild = unwrap(t)
                    if not isinstance(body, str) or norm(q) not in norm(body):
                        continue
                    span = find_span(body, q) if callable(find_span) else None
                    if span is None:
                        # fallback: exact substring (whitespace-normalised search failed to map) -> try raw
                        i = body.find(q)
                        span = (i, i + len(q)) if i >= 0 else None
                    if span is None:
                        continue
                    a0, b0 = expand_sentence(body, span[0], span[1])  # 扩到整句边界(v2.1 同款)
                    new_body = (body[:a0] + body[b0:]).strip()
                    # 锚点保护:待删文本(整轮或该句)若含任何金标锚句,跳过并记录——不得动锚点
                    anchors = [r.get("state_span", "") for r in e["chain"] if r.get("state_span")]
                    doomed = body if (v.get("suggested_fix") == "delete_turn" or not new_body) else body[a0:b0]
                    if any(sp in doomed for sp in anchors):
                        log.setdefault("anchor_protected", []).append({"uid": e["uid"], "date": s["date"], "quote": q}); hit = True; break
                    if v.get("suggested_fix") == "delete_turn" or not new_body:
                        s["turns"].pop(ti)
                    else:
                        s["turns"][ti] = rebuild(new_body)
                    log["deleted"].append({"uid": e["uid"], "date": s["date"], "quote": q, "mode": "turn" if (v.get("suggested_fix") == "delete_turn" or not new_body) else "sentence"})
                    hit = True; break
                if hit: break
            if not hit:
                log["not_found"].append({"uid": e["uid"], "quote": q})
    # gates: anchors intact, residue zero
    bad = 0
    for e in data:
        for r in e["chain"]:
            sp = r.get("state_span", "")
            if not any(sp in (unwrap(t)[1] or "") for s in e["sessions"] if s.get("chain_index") is not None for t in s["turns"]):
                bad += 1
    residue = 0
    protected = {(x["uid"], x["quote"]) for x in log.get("anchor_protected", [])}
    for e in data:
        blob = norm(" ".join((unwrap(t)[1] or "") for s in e["sessions"] for t in s["turns"]))
        for v in by_uid.get(e["uid"], []):
            if (e["uid"], v["quote"]) in protected: continue  # 锚点保护项有意保留,不计残留
            if norm(v["quote"]) in blob: residue += 1
    log["anchor_check"] = f"{anchors_before - bad}/{anchors_before}"; log["residue"] = residue
    # (3) questions: drop near-tie longest_tenure
    qs = [json.loads(l) for l in open(ROOT / "data/wsc_s5_v2.jsonl", encoding="utf-8")]
    D = {e["uid"]: e for e in data}; dropped = []
    for q in qs:
        if q["qtype"] != "longest_tenure": continue
        rows = D[q["uid"]]["chain"]; today = pd(rows[-1]["date"]) + timedelta(days=400)
        ten = sorted((((pd(rows[i + 1]["date"]) if i + 1 < len(rows) else today) - pd(r["date"])).days for i, r in enumerate(rows)), reverse=True)
        if len(ten) > 1 and ten[0] > 0 and (ten[0] - ten[1]) / ten[0] <= 0.01: dropped.append(q["qid"])
    log["dropped_questions"] = dropped
    print(f"deleted {len(log['deleted'])} (turn {sum(1 for x in log['deleted'] if x['mode']=='turn')}), not_found {len(log['not_found'])}, dedup {len(log['dedup'])}, anchors {log['anchor_check']}, residue {residue}, dropped lt questions {len(dropped)}")
    if a.dry or bad or residue:
        print("DRY RUN or GATE FAILED — nothing written"); (ROOT / "results/b34_v25_changelog_dry.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8"); return
    (ROOT / "data/wikistate_full_ALL_v25.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with open(ROOT / "data/wsc_s5_v25.jsonl", "w", encoding="utf-8") as f:
        for q in qs:
            if q["qid"] not in set(dropped): f.write(json.dumps(q, ensure_ascii=False) + "\n")
    (ROOT / "results/b34_v25_changelog.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written data/wikistate_full_ALL_v25.json, data/wsc_s5_v25.jsonl, results/b34_v25_changelog.json")


if __name__ == "__main__":
    main()
