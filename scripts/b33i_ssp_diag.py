# -*- coding: utf-8 -*-
"""33-I SSP 三臂弃答/长度诊断($0):smoc vs ledgerplain vs direct。"""
import json, re, statistics as st
PAT = re.compile(r"(cannot|can't|not enough|no (prior )?(information|record|"
                 r"documented|discussion|data)|does not (contain|provide)|"
                 r"contains no|unable to)", re.I)
def L(p): return [json.loads(l) for l in open(p, encoding="utf-8")]
arms = {
    "smoc(F.1协议)": "results/b33i_lme_ssp_smoc.jsonl",
    "ledgerplain(裸提示)": "results/b33i_lme_ssp_ledgerplain.jsonl",
    "direct(稠密top-10)": "results/b33i_lme_ssp_direct.jsonl",
}
print(f"{'arm':24s} {'n':>3} {'acc%':>6} {'弃答':>6} {'弃答对':>6} "
      f"{'非弃答acc':>10} {'答长中位':>9}")
rows = {}
for tag, p in arms.items():
    r = L(p); rows[tag] = r
    ref = [x for x in r if PAT.search(x["answer"])]
    non = [x for x in r if not PAT.search(x["answer"])]
    a = sum(1 for x in r if x["judge_correct"])
    print(f"{tag:24s} {len(r):>3} {100*a/len(r):>6.2f} "
          f"{len(ref):>3}/{len(r):<2} {sum(1 for x in ref if x['judge_correct']):>6} "
          f"{(100*sum(1 for x in non if x['judge_correct'])/max(len(non),1)):>9.1f}% "
          f"{int(st.median(len(x['answer']) for x in r)):>9}")
