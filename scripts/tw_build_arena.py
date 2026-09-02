# -*- coding: utf-8 -*-
"""33-G3 外场 Temporal Wiki 建场器:把 Özer & Yıldız (arXiv 2506.07270) 的
TQA 仓库(github.com/atahanoezer/TQA,full_data_filtered/*.json)转成本项目
统一店格式 + 探针题集。

转换口径(逐条写死,勿改):
  * 一个 event 文件 = 一条实体链 = 一个店(uid = tw-####);
  * 每个 incident(按 q_year 键)= 一个**带日期轮次**,date = f"{q_year}-01-01",
    turn 文本 = "owner: ..." 前缀 + infobox 行 + 匹配段落;
    (底层 revision 多为 q_year+1 年初抓取的 map_year 快照;这里按提问所指
     年份落日期,使"as of 年份"与账目行日期对齐,四臂同一份文本。)
  * 题目原样取 incidents[y]["question"](自带 "in <year>" 的 as-of 年),
    gold = Wikidata 标准标签;
  * 入样条件(三重,arm-independent):
      ① 链内各 incident 的 revision url 互不相同(排除多个 q_year 共用同一
         快照的 112 条链——那类链不存在"逐年快照"这一前提);
      ② 只取单答案题(len(answer)==1)。冻结 ClaudeJudge 判据规定"多部分
         gold 只答其一即错",多答案题会把四臂一律判错、纯加噪;
      ③ 链内保留题 ≥2 且答案至少两取值(= 答案跨年份发生变化)。
  * 按 relation 比例分层抽 300 题:每关系配额 = 该关系可用题占比 × 300
    (最大余数法配满),关系内按种子打乱**整链**纳入,超配额时截尾。

用法:
  PYTHONUTF8=1 python scripts/tw_build_arena.py \
      --repo data/external/temporalwiki/repo/full_data_filtered \
      --out-data data/external/temporalwiki_unified.json \
      --out-probe data/external/temporalwiki_probe.jsonl \
      --n 300 --seed 33
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import urllib.parse
from pathlib import Path

# 关系码 → 人类可读槽名(只进元数据/报表,不进读者上下文)
REL_SLOT = {
    "P54": "member_of_sports_team",
    "P108": "employer",
    "P39": "position_held",
    "P102": "member_of_political_party",
    "P286": "head_coach",
    "P488": "chairperson",
    "P127": "owned_by",
    "P6": "head_of_government",
    "P69": "educated_at",
}

_CSS = re.compile(r"\.mw-parser-output[^\n]*?\{[^}]*\}")
_WS = re.compile(r"[ \t]+")
_STOP = {
    "the", "of", "and", "for", "club", "football", "de", "la", "el", "party",
    "national", "united", "city", "university", "company", "association",
    "sport", "sports", "team", "from", "with", "that", "this", "were", "have",
}
MAX_PARA = 1500
MAX_INFOBOX = 1400


def _title(url: str) -> str:
    m = re.search(r"title=(.*?)&oldid=", url or "")
    if not m:
        return ""
    return urllib.parse.unquote(m.group(1)).replace("_", " ").strip()


def _toks(s: str):
    return [t for t in re.findall(r"[A-Za-zÀ-ɏ]{4,}", (s or "").lower())
            if t not in _STOP]


def _paragraphs(body: str):
    body = _CSS.sub(" ", body or "")
    out = []
    for p in re.split(r"\n+", body):
        p = _WS.sub(" ", p).strip()
        if not p or p.startswith("Template:"):
            continue
        out.append(p)
    return out


def _matched_paragraph(body: str, answer_names) -> str:
    """匹配段落:与该快照**自身**年份 gold 标签词重叠最高的段落
    (重叠为 0 时退回前 5 段中最长的一段 = 导语)。
    这是 evidence-oracle 式选段,对四臂完全同一份文本,不构成臂间偏置;
    局限已在终判里明写。"""
    ps = _paragraphs(body)
    if not ps:
        return ""
    want = set()
    for n in answer_names:
        want |= set(_toks(n))
    best, bs = None, 0
    for p in ps:
        if len(p) < 80:
            continue
        s = sum(1 for w in want if w in p.lower())
        if s > bs or (s == bs and s > 0 and best is not None and len(p) > len(best)):
            bs, best = s, p
    if best is None:
        cand = [p for p in ps[:5] if len(p) >= 80] or ps[:1]
        best = max(cand, key=len)
    return best[:MAX_PARA]


def _infobox_lines(info: dict) -> str:
    if not info:
        return ""
    parts = []
    n = 0
    for k, v in info.items():
        k = _WS.sub(" ", str(k)).replace("\n", " ").strip()
        v = _WS.sub(" ", str(v)).replace("\n", " ").strip()
        if not k or not v:
            continue
        s = f"{k}: {v}"
        if n + len(s) > MAX_INFOBOX:
            break
        parts.append(s)
        n += len(s) + 2
    return "; ".join(parts)


def _turn_text(title: str, year: int, inc: dict, answer_names) -> str:
    info = _infobox_lines(inc["dump"].get("infobox") or {})
    para = _matched_paragraph(inc["dump"].get("body_par") or "", answer_names)
    lines = [f'owner: Wikipedia article "{title}" — snapshot for {year}.']
    if info:
        lines.append(f"Infobox: {info}")
    if para:
        lines.append(f"Article: {para}")
    return "\n".join(lines)


def load_eligible(repo: Path):
    """返回 [(event_id, relation, title, [(year, inc, gold_name, gold_qid)...])]。"""
    out = []
    for f in sorted(repo.glob("*.json"), key=lambda p: int(p.stem)):
        d = json.loads(f.read_text(encoding="utf-8"))
        q, inc = d["query"], d["incidents"]
        urls = [v["url"] for _, v in sorted(inc.items())]
        if len(set(urls)) != len(urls):        # 条件①
            continue
        keys = [k for k in q["query"]
                if len(q["answer"][k]) == 1 and str(q["date"][k]) in inc]  # 条件②
        if len(keys) < 2:
            continue
        vals = {q["answer"][k][0]["wikidata_id"] for k in keys}
        if len(vals) < 2:                      # 条件③
            continue
        rel = q["relation"][keys[0]]
        title = _title(urls[0]) or ""
        items = []
        for k in sorted(keys, key=lambda k: int(q["date"][k])):
            y = int(q["date"][k])
            a = q["answer"][k][0]
            items.append((y, inc[str(y)], a["name"], a["wikidata_id"], q["id"][k],
                          q["most_recent_answer"].get(k), q["most_frequent_answer"].get(k)))
        out.append({"event_id": d["event_id"], "relation": rel, "title": title,
                    "items": items, "incidents": inc, "query": q})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out-data", required=True)
    ap.add_argument("--out-probe", required=True)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=33)
    a = ap.parse_args()

    chains = load_eligible(Path(a.repo))
    by_rel = collections.defaultdict(list)
    for c in chains:
        by_rel[c["relation"]].append(c)
    qtot = {r: sum(len(c["items"]) for c in v) for r, v in by_rel.items()}
    grand = sum(qtot.values())

    # 最大余数法把 n 题按关系可用题量比例配满
    raw = {r: qtot[r] / grand * a.n for r in qtot}
    quota = {r: int(raw[r]) for r in raw}
    rest = a.n - sum(quota.values())
    for r in sorted(raw, key=lambda r: (-(raw[r] - int(raw[r])), r))[:rest]:
        quota[r] += 1

    # 抽的是**题**不是链:被选中的链一律把全部合格快照写进店(记忆完整性
    # 与抽题无关),只有 questions/probe 取配额内的子集。这样任何店都保有
    # ≥2 个不同年份的冲突快照,配额截尾不会削出"单快照店"。
    rng = random.Random(a.seed)
    picked = []
    for r in sorted(by_rel):
        pool = sorted(by_rel[r], key=lambda c: c["event_id"])
        rng.shuffle(pool)
        got = 0
        for c in pool:
            if got >= quota[r]:
                break
            take = c["items"][: quota[r] - got]     # 超配额时只截**题**
            picked.append((c, take))
            got += len(take)

    entries, probes = [], []
    for i, (c, ask) in enumerate(sorted(picked, key=lambda x: (x[0]["relation"],
                                                              x[0]["event_id"]))):
        uid = f"tw-{i:04d}"
        asked_years = {y for (y, *_r) in ask}
        sessions, questions = [], []
        for (y, inc, gname, gqid, wid, mra, mfa) in c["items"]:
            sessions.append({"date": f"{y}-01-01",
                             "turns": [_turn_text(c["title"], y, inc, [gname])]})
            if y not in asked_years:
                continue
            qtext = re.sub(r"^Question:\s*", "", inc["question"]).strip()
            qid = f"{uid}-{y}"
            questions.append({"qid": qid, "question": qtext, "gold": gname,
                              "year": y, "relation": c["relation"]})
            probes.append({
                "uid": uid, "qid": qid, "qtype": f"tw_{c['relation']}",
                "question": qtext, "gold": gname, "cutoff": "",
                "meta": {"relation": c["relation"],
                         "slot": REL_SLOT.get(c["relation"], c["relation"]),
                         "as_of_year": y, "wikidata_answer_id": gqid,
                         "wikidata_item_id": wid, "entity_title": c["title"],
                         "event_id": c["event_id"],
                         "snapshot_map_year": inc["map_year"],
                         "revision_url": inc["url"],
                         "most_recent_answer": (mra or {}).get("name"),
                         "most_frequent_answer": (mfa or {}).get("name")}})
        sessions.sort(key=lambda s: s["date"])
        entries.append({
            "uid": uid, "sessions": sessions, "questions": questions,
            "chain": [{"date": sessions[-1]["date"], "value": ""}],
            "probing_queries": {"_placeholder": {"q": "placeholder", "gold": ""}},
            "meta": {"event_id": c["event_id"], "relation": c["relation"],
                     "slot": REL_SLOT.get(c["relation"], c["relation"]),
                     "entity_title": c["title"]}})

    Path(a.out_data).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out_data).write_text(json.dumps(entries, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    with open(a.out_probe, "w", encoding="utf-8") as fh:
        for p in probes:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"eligible chains {len(chains)} / questions {grand}")
    print("quota:", {r: quota[r] for r in sorted(quota)})
    got = collections.Counter(p["meta"]["relation"] for p in probes)
    print("sampled:", dict(sorted(got.items())), "total", len(probes),
          f"in {len(entries)} stores")
    ch = collections.Counter(len(e["sessions"]) for e in entries)
    print("sessions per store:", dict(sorted(ch.items())))
    tl = [len(t) for e in entries for s in e["sessions"] for t in s["turns"]]
    print(f"turn chars: mean {sum(tl)/len(tl):.0f} max {max(tl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
