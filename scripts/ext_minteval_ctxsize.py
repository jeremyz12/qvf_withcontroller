# -*- coding: utf-8 -*-
"""批 33-G4:实测每个 MINTEval 店的"整库直塞"读者输入 token 数。

用途:证明/证伪 haiku-4.5 全文臂(200K 上下文窗)在本考场是否可跑。
渲染与 scripts/ext_direct_arm.py 的 QVF_FULL_CONTEXT=1 路径逐字同款
(READER_SYSTEM + reader_content(问题, 全部记忆, TODAY'S DATE)),
计数用 Anthropic count_tokens(免费,不产生生成费用)。

用法: PYTHONUTF8=1 python scripts/ext_minteval_ctxsize.py
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402

import ext_direct_arm as D  # noqa: E402

LIMIT = 200_000  # claude-haiku-4-5 context window


def main() -> int:
    src = Path(r"D:\ZZL_cluade\data\external\minteval_cardable.json")
    entries = json.loads(src.read_text(encoding="utf-8"))
    probe = [json.loads(l) for l in
             open(r"D:\ZZL_cluade\data\external\minteval_probe.jsonl",
                  encoding="utf-8") if l.strip()]
    q_by_uid = {}
    for r in probe:
        q_by_uid.setdefault(r["uid"], r["question"])
    client = anthropic.Anthropic()
    out, n_fit = [], 0
    for e in entries:
        uid = e["uid"]
        q = q_by_uid.get(uid)
        if q is None:
            continue
        mems = D._memories(e)
        content = D.reader_content(q, mems, D._query_date(e, q))
        r = client.messages.count_tokens(
            model="claude-haiku-4-5",
            system=[{"type": "text", "text": D.READER_SYSTEM}],
            messages=[{"role": "user", "content": content}])
        n = r.input_tokens
        fit = n <= LIMIT
        n_fit += fit
        out.append({"uid": uid, "orig_id": e.get("orig_id"),
                    "n_memories": len(mems), "input_tokens": n, "fits": fit})
        print("%s  mems=%-5d tokens=%-8d %s" % (uid, len(mems), n,
                                                "FITS" if fit else "OVER"),
              flush=True)
    p = Path(r"D:\ZZL_cluade\results\ext_minteval_ctxsize.json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    ts = sorted(x["input_tokens"] for x in out)
    print("\nusers=%d  fit<=200K: %d  min=%d med=%d max=%d  -> %s"
          % (len(ts), n_fit, ts[0], ts[len(ts) // 2], ts[-1], p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
