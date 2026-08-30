# -*- coding: utf-8 -*-
"""判官机械一致性核对(可复现版,08-30 审计 B3 修复)。

范围:v2 考场 9 臂 × 数值金标计数题(change_count 144 + count_before 144)
= 2,592 行。机械提取规则 v2(定死,勿改;改动即换版本号重报):
  1) 预处理:剥离日期(YYYY-MM-DD、Month DD, YYYY)、序数(18th 等)、
     独立 1800-2100 年份;
  2) 候选 = 剩余独立整数 + 词数字(one..twenty、once=1、twice=2);
  3) 机械答案 = 第一个候选(计数题答案习惯开头给出);无候选 = 不计入;
  4) 机械判定 = (机械答案 == 金标);一致率 = mean(judge==机械),逐行入档。
  规则 v1(取末候选、无词数字)总一致 92.20%,分歧抽样 8/8 为提取错误
  (句尾年份/届数被误抓)而非判官错误,故升 v2;v1 产物不入档。

用法: python scripts/mech_consistency_check.py
产物: results/mech_consistency_20260830.jsonl + 汇总打印。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARMS = ["wsc_v2_direct", "wsc_v2_filter", "wsc_v2_usability",
        "wsc_v2_compile", "wsc_v2_smw", "wsc_v2_smoc", "wsc_v2_smoc_v43",
        "wsc_v2_smoc_slot", "wsc_v2_smoc_v43_slot"]
QTYPES = {"change_count", "count_before"}
MONTHS = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")
DATE = re.compile(r"\d{4}-\d{2}(-\d{2})?|(?:%s)\s+\d{1,2}(?:,\s*\d{4})?"
                  % MONTHS)
ORD = re.compile(r"\b\d+(?:st|nd|rd|th)\b")
INT = re.compile(r"(?<![\d.])(\d+)(?![\d.])")
WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen "
    "twenty".split())}
WORDS.update(once=1, twice=2)
WORDRE = re.compile(r"\b(%s)\b" % "|".join(WORDS), re.I)


def mech_extract(text: str):
    text = ORD.sub(" ", DATE.sub(" ", text or ""))
    cands = []
    for m in re.finditer(r"%s|%s" % (INT.pattern, WORDRE.pattern), text,
                         re.I):
        tok = m.group(0)
        if tok.isdigit():
            if not 1800 <= int(tok) <= 2100:
                cands.append((m.start(), int(tok)))
        else:
            cands.append((m.start(), WORDS[tok.lower()]))
    return min(cands)[1] if cands else None


def main() -> int:
    out = open(ROOT / "results/mech_consistency_20260830.jsonl", "w",
               encoding="utf-8")
    tot = agree = noext = 0
    per = {}
    for arm in ARMS:
        rows = [json.loads(l) for l in
                open(ROOT / f"results/{arm}.jsonl", encoding="utf-8")]
        a = n = 0
        for r in rows:
            if r.get("question_type") not in QTYPES:
                continue
            try:
                gold = int(str(r["gold_answer"]).strip())
            except ValueError:
                continue
            mech = mech_extract(r.get("answer", ""))
            if mech is None:
                noext += 1
                continue
            ok = (mech == gold) == bool(r["judge_correct"])
            out.write(json.dumps({
                "arm": arm, "question_id": r["question_id"], "gold": gold,
                "mech": mech, "mech_correct": mech == gold,
                "judge_correct": bool(r["judge_correct"]),
                "agree": ok}, ensure_ascii=False) + "\n")
            n += 1
            a += ok
        per[arm] = (a, n)
        tot += n
        agree += a
    for arm, (a, n) in per.items():
        print(f"{arm:24s} {a}/{n} = {a / max(1, n) * 100:.2f}%")
    print(f"TOTAL {agree}/{tot} = {agree / tot * 100:.2f}%  "
          f"(无法提取 {noext} 行,不计入)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
