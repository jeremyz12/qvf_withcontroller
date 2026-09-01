# -*- coding: utf-8 -*-
"""第二轮评审题目生成器:从 v2.3 净化语料直接生成,含 5 道全新对照题。

选题:61 条被清洗的链(验证修复)+ 19 条未触及链(对照)+ 5 道植入错误对照题。
三人同一套题(全重叠)→ κ 可算。产物 data/round2_payload.json,再灌入 rate.db。
"""
import json, re, ast, html as H, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_corpus_v21 import unwrap

STYLE = open(ROOT / "scripts/build_labelstudio_html.py", encoding="utf-8").read()
STYLE = re.search(r'STYLE = """(.*?)"""', STYLE, re.S).group(1)
STYLE = "<style>" + STYLE.split("<style>", 1)[1]

CONV = ("dates use the session date on which the state was declared; "
        "00 means the day/month was not stated.")


def chain_table(rows):
    tr = "".join(f"<tr><td>{H.escape(r['date'])}</td><td>{H.escape(r['value'])}</td>"
                 f"<td>&ldquo;{H.escape(r['state_span'])}&rdquo;</td></tr>" for r in rows)
    return (STYLE + "<table><thead><tr><th>DATE</th><th>VALUE</th>"
            "<th>SOURCE SENTENCE (verbatim anchor)</th></tr></thead>"
            f"<tbody>{tr}</tbody></table><div class='conv'>CONVENTION: {CONV}</div>")


def raw_box(entry, rows):
    spans = [r["state_span"] for r in rows]
    parts = [STYLE, "<div class='scrollbox'>",
             "<div class='hd'>RAW MEMORY — the persona's full session log "
             "(scroll inside this box)</div>",
             f"<div class='intro'>All {len(entry['sessions'])} sessions "
             f"({entry['sessions'][0]['date']} … {entry['sessions'][-1]['date']}), "
             "every user message quoted verbatim; assistant replies omitted. "
             "Anchor sentences are <mark>highlighted</mark>.</div>"]
    for si, s in enumerate(entry["sessions"], 1):
        hit = [i + 1 for i, sp in enumerate(spans)
               if any(sp in (unwrap(t)[1] or "") for t in s["turns"])]
        badge = (f"<span class='anch'>anchor {', '.join('#' + str(k) for k in hit)}"
                 "</span>") if hit else ""
        parts.append(f"<div class='sess'>Session {si} · {H.escape(s['date'])}{badge}</div>")
        for t in s["turns"]:
            role, body, _ = unwrap(t)
            if role != "user" or not isinstance(body, str) or not body.strip():
                continue
            esc = H.escape(body).replace("\n", "<br>")
            for sp in spans:
                if sp in body:
                    esc = esc.replace(H.escape(sp), f"<mark>{H.escape(sp)}</mark>")
            parts.append(f"<p>{esc}</p>")
    parts.append("</div>")
    return "".join(parts)


def inject(rows, kind, rng):
    """植入一处错误,返回(新链, 描述)。"""
    rows = [dict(r) for r in rows]
    if kind == "value_swap" and len(rows) >= 2:
        i = rng.randrange(len(rows) - 1)
        rows[i]["value"], rows[i + 1]["value"] = rows[i + 1]["value"], rows[i]["value"]
        return rows, f"value_swap: rows #{i+1}/#{i+2} values swapped"
    if kind == "date_shift":
        i = rng.randrange(len(rows))
        y = re.match(r"(\d{4})", rows[i]["date"])
        if y:
            rows[i]["date"] = str(int(y.group(1)) + 3) + rows[i]["date"][4:]
            return rows, f"date_shift: row #{i+1} year +3"
    if kind == "delete_row" and len(rows) >= 3:
        i = rng.randrange(1, len(rows))
        d = rows.pop(i)
        return rows, f"delete_row: row for '{d['value']}' ({d['date']}) deleted"
    if kind == "fabricate_anchor":
        i = rng.randrange(len(rows))
        rows[i]["value"] = "Northgate Analytics"
        rows[i]["state_span"] = ("I can officially confirm the switch to "
                                 "Northgate Analytics as of today")
        return rows, f"fabricate_anchor: row #{i+1} replaced with fabricated value"
    if kind == "add_row":
        i = rng.randrange(len(rows))
        y = re.match(r"(\d{4})", rows[i]["date"])
        yy = str(int(y.group(1)) + 1) if y else "1999"
        rows.insert(i + 1, {"date": yy + "-00-00", "value": "interim coordinator",
                            "state_span": "I have taken on the interim coordinator "
                                          "role starting today"})
        return rows, f"add_row: fabricated row inserted after #{i+1}"
    return rows, "none"


def main():
    data = {e["uid"]: e for e in json.loads(
        (ROOT / "data/wikistate_full_ALL_v23.json").read_text(encoding="utf-8"))}
    cleaned = sorted(set(open(ROOT / "data/b31_dirty_uids.txt").read().split(",")))
    rest = sorted(u for u in data if u not in set(cleaned))
    rng = random.Random(2026)
    control = rng.sample(rest, 19)
    catch_pool = rng.sample(rest, 5)
    kinds = ["value_swap", "date_shift", "delete_row", "fabricate_anchor", "add_row"]
    items, keymap = [], {}
    for n, uid in enumerate(cleaned + control, 1):
        e = data[uid]
        iid = f"r2-{n:03d}"
        items.append({"id": iid, "slot": e["slot"],
                      "chain_html": chain_table(e["chain"]),
                      "raw_html": raw_box(e, e["chain"])})
        keymap[iid] = {"uid": uid, "catch": False, "injection": None,
                       "group": "cleaned" if uid in set(cleaned) else "control"}
    for k, (uid, kind) in enumerate(zip(catch_pool, kinds), 1):
        e = data[uid]
        rows, desc = inject(e["chain"], kind, rng)
        iid = f"r2-c{k:02d}"
        items.append({"id": iid, "slot": e["slot"],
                      "chain_html": chain_table(rows),
                      "raw_html": raw_box(e, e["chain"])})
        keymap[iid] = {"uid": uid, "catch": True, "injection": desc, "group": "catch"}
    order = [i["id"] for i in items]
    rng.shuffle(order)
    raters = [{"token": "r2" + "".join(rng.choice(
        "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(14)),
        "name": nm, "items": order} for nm in ("author-r2", "senior1-r2", "senior2-r2")]
    (ROOT / "data/round2_payload.json").write_text(json.dumps(
        {"items": items, "raters": raters}, ensure_ascii=False), encoding="utf-8")
    (ROOT / "data/round2_keymap.json").write_text(json.dumps(keymap, ensure_ascii=False,
                                                             indent=1), encoding="utf-8")
    print(f"题目 {len(items)}(清洗 {len(cleaned)} / 对照 {len(control)} / 植入 5)")
    for r in raters:
        print(f"  {r['name']}: /r/{r['token']}")


if __name__ == "__main__":
    main()
