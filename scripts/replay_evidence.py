# -*- coding: utf-8 -*-
"""证据包重放器(零 LLM;dev 工具,新文件,不改任何冻结路径)。

从既有 complex_arm 结果行读取已存 plan,重跑 execute_plan(纯代码),输出
逐题证据包全文(reader_content 渲染串)。用途:
  ① 旗标全关 vs 冻结版:同 env 下前后两次重放输出逐字节对拍;
  ② 旗标开启 dev A/B:与基线重放对比,找出证据包变化的题(只对这些题
     增量重跑读者+判官,控预算)。
env(QVF_CARDS_KEYED / QVF_OPEN_SLOT / QVF_OPEN_KEYS ...)由调用方设置。

用法:
  python scripts/replay_evidence.py --rows results/wsc_s5_test_v42.jsonl \
      --data data/wikistate_full_P108.json data/wikistate_full_P54.json \
      --out <replay.jsonl>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.complex_query_arm import (_load_entries, _load_records,  # noqa: E402
                                       _mem_dates, _query_date,
                                       execute_plan, reader_content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", nargs="+", required=True,
                    help="含 plan 字段的 complex_arm 结果 jsonl(可多份,"
                    "按 question_id 先到先得去重)")
    ap.add_argument("--data", nargs="+", required=True,
                    help="chain 架构数据 json(供 mem_dates / 查询日期回退)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    for p in a.rows + a.data:
        assert "P69" not in Path(p).name, "P69 是测试床,重放器拒绝触碰"
    entries = _load_entries(a.data)
    md_cache: dict = {}
    seen: set = set()
    n = 0
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for rf in a.rows:
            for line in open(rf, encoding="utf-8"):
                s = line.strip()
                if not s:
                    continue
                r = json.loads(s)
                qid = r.get("question_id")
                if not qid or qid in seen or not isinstance(r.get("plan"), dict):
                    continue
                seen.add(qid)
                uid = r["uid"]
                if uid not in md_cache:
                    md_cache[uid] = _mem_dates(entries.get(uid, {}))
                ev, derived = execute_plan(r["plan"], _load_records(uid),
                                           md_cache[uid], r["question"])
                qd = _query_date(entries.get(uid, {}), r["question"])
                f.write(json.dumps({
                    "question_id": qid, "uid": uid,
                    "op": (r["plan"] or {}).get("op"),
                    "stored_evidence_n": r.get("evidence_n"),
                    "evidence_n": len(ev),
                    "reader_content": reader_content(ev, derived, qd,
                                                     r["question"]),
                }, ensure_ascii=False) + "\n")
                n += 1
    print(f"replayed {n} -> {a.out}")


if __name__ == "__main__":
    main()
