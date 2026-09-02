# -*- coding: utf-8 -*-
"""批 33-G4 跑批壳:原样调用冻结的 ext_smoc_arm / ext_direct_arm,只额外落盘
**判官侧 token 用量**(冻结脚本不写这两个字段,而本轨要求成本全部由 usage
token 算出,不许估算)。

做法:import 冻结模块前先给 qvf.judge.ClaudeJudge.judge 打一层计数装饰器
(累加 JudgeResult.usage_input_tokens/usage_output_tokens),臂脚本本身
一个字节都不改,答题/判官行为逐字不变。

用法(分片并行,parallelism ≤ 4):
  PYTHONUTF8=1 python scripts/ext_minteval_run.py --arm smoc \
      --questions scratchpad/b33g_smoc_s0.jsonl \
      --out results/ext_minteval_smoc.s0.jsonl --resume
  QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/ext_minteval_run.py \
      --arm direct --questions ... --out ... --resume
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from qvf.judge import ClaudeJudge  # noqa: E402

DATA = r"D:\ZZL_cluade\data\external\minteval_cardable.json"
CARDS = r"D:\ZZL_cluade\results\ext_cards_minteval"

_USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "no_usage": 0}
_orig_judge = ClaudeJudge.judge


def _counting_judge(self, *a, **kw):
    r = _orig_judge(self, *a, **kw)
    _USAGE["calls"] += 1
    if r.usage_input_tokens is None:
        _USAGE["no_usage"] += 1      # 判官两次都失败走了兜底启发式
    else:
        _USAGE["input_tokens"] += r.usage_input_tokens
        _USAGE["output_tokens"] += r.usage_output_tokens or 0
    return r


ClaudeJudge.judge = _counting_judge


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["smoc", "direct"], required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--reader-max-tokens", type=int, default=0,
                    help="仅诊断子臂用:把读者 max_tokens 从冻结的 800 抬高。"
                         "默认 0 = 不改,冻结臂逐字节不变。")
    a = ap.parse_args()

    if a.arm == "smoc":
        import ext_smoc_arm as M
        if a.reader_max_tokens:
            # 诊断子臂:MINTEval 的 'N 个偏好变更事件之前' 题要求读者先在
            # 账目里逐条枚举偏好变更再倒数,冻结的 max_tokens=800 会把
            # 枚举截断在半路(试跑 8 题里多次出现)。本旗标只抬输出上限,
            # 提示词/温度/模型/判官全不动,用来把"账目里没有" 与
            # "输出预算不够写完" 两种失败分开。
            # 只包读者那一个 client:ext_smoc_arm 里 `client = anthropic.Anthropic()`
            # 与 qvf.judge 里 `anthropic.Anthropic()` 指向同一个类,所以代理
            # **必须对其余属性透传**(判官走的是 messages.parse)。第一版只暴露
            # messages.create,把 60 次判官调用全打进兜底启发式——已修。
            _bump = a.reader_max_tokens
            _real = M.anthropic.Anthropic

            class _Msgs:
                def __init__(self, inner):
                    self._inner = inner

                def create(self, **kw):
                    if kw.get("max_tokens") == 800:
                        kw["max_tokens"] = _bump
                    return self._inner.create(**kw)

                def __getattr__(self, k):
                    return getattr(self._inner, k)

            class _Proxy:
                def __init__(self, inner):
                    self._inner = inner
                    self.messages = _Msgs(inner.messages)

                def __getattr__(self, k):
                    return getattr(self._inner, k)

            M.anthropic.Anthropic = lambda *args, **kw: _Proxy(_real(*args, **kw))
            print("DIAGNOSTIC: reader max_tokens 800 -> %d" % _bump, flush=True)
        sys.argv = ["ext_smoc_arm.py", "--data", DATA,
                    "--questions", a.questions, "--cards-dir", CARDS,
                    "--out", a.out] + (["--resume"] if a.resume else [])
        rc = M.main()
    else:
        import ext_direct_arm as M
        sys.argv = ["ext_direct_arm.py", "--data", DATA,
                    "--questions", a.questions, "--out", a.out] \
            + (["--resume"] if a.resume else [])
        M.main()
        rc = 0

    p = Path(a.out).with_suffix(".judgeusage.json")
    p.write_text(json.dumps(_USAGE, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    print("judge usage ->", p, _USAGE, flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
