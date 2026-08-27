# -*- coding: utf-8 -*-
"""批 21 相对日期解析器(纯代码,卡店后处理——不触冻结建卡器)。

对卡店每张卡:source_span 若含批 21 短语集之一,按与生成器同一张日历
算术表把**卡片所在会话日期**回推为绝对日期,覆盖 stated_date;无命中
的卡原样。产物:--out 新卡店目录 + 修正计数。
用法: python scripts/rel_date_resolver.py --cards results/wt_cards_rel30 \
        --data data/wikistate_rel30.json --out results/wt_cards_rel30_resolved
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, r"D:\ZZL_cluade\scripts")
sys.path.insert(0, r"D:\ZZL_cluade")
from complex_query_arm import _mem_dates  # noqa: E402


def pd(s):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s))
    return date(*map(int, m.groups())) if m else None


def sub_months(d, n):
    m = d.month - 1 - n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, 28 if m == 2 else 30 if m in (4, 6, 9, 11)
                          else 31))


# 与 gen_relative_arena.PHRASES 严格互逆
BACK = [
    (re.compile(r"\btwo months ago\b", re.I), lambda d: sub_months(d, 2)),
    (re.compile(r"\bthree weeks ago\b", re.I),
     lambda d: d.fromordinal(d.toordinal() - 21)),
    (re.compile(r"\blast month\b", re.I), lambda d: sub_months(d, 1)),
    (re.compile(r"\ba year ago\b", re.I), lambda d: sub_months(d, 12)),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    n_cards = n_fix = 0
    for f in sorted(Path(a.cards).glob("*.json")):
        uid = f.stem
        doc = json.loads(f.read_text(encoding="utf-8"))
        md = _mem_dates(entries[uid]) if uid in entries else {}
        for r in doc.get("records", []):
            n_cards += 1
            span = r.get("source_span") or ""
            hit = next(((rx, back) for rx, back in BACK if rx.search(span)),
                       None)
            if hit is None:
                continue
            # 回推基准 = 会话日期(可靠全日期);stated_date 仅兜底——
            # 建卡器对相对短语自发做月级解析("2024-04"),天级信息只在
            # 会话日期里。
            sess_d = pd(md.get(r.get("source_memory_id", ""), "")) or \
                pd(r.get("stated_date") or "")
            if sess_d is None:
                continue
            r["stated_date"] = hit[1](sess_d).isoformat()
            n_fix += 1
        (outdir / f.name).write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print(f"resolver: {n_fix}/{n_cards} cards re-dated -> {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
