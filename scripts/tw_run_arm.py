# -*- coding: utf-8 -*-
"""33-G3 臂驱动器:**不改冻结臂脚本一个字节**,只在进程内给
qvf.judge.ClaudeJudge.judge 挂一层记账猴补,把判官侧 usage token 落到
sidecar,然后原样调用臂脚本的 main()。

动机:硬规则要求"cost from usage tokens";而三支冻结臂的输出行只记读者侧
usage,判官侧 token 从不落盘(JudgeResult 自 08-16 起带 usage 字段,但没人
写出去)。改臂脚本会碰到批 33 其他并行轨,故走猴补。

用法(argv 透传给臂脚本):
  python scripts/tw_run_arm.py --arm smoc --judge-log results/tw_judge_smoc.jsonl \
      -- --data ... --questions ... --cards-dir ... --out ... --resume
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def main() -> int:
    argv = sys.argv[1:]
    arm = argv[argv.index("--arm") + 1]
    jlog = argv[argv.index("--judge-log") + 1]
    passthru = argv[argv.index("--") + 1:]

    import qvf.judge as J
    _orig = J.ClaudeJudge.judge
    Path(jlog).parent.mkdir(parents=True, exist_ok=True)
    fh = open(jlog, "a", encoding="utf-8")

    def _patched(self, question, gold_answer, response, question_type=None,
                 is_abstention=False):
        t0 = time.time()
        r = _orig(self, question, gold_answer, response, question_type,
                  is_abstention)
        fh.write(json.dumps({
            "arm": arm, "judge_model": self.model,
            "judge_in": r.usage_input_tokens, "judge_out": r.usage_output_tokens,
            "judge_latency_s": round(time.time() - t0, 2),
            "correct": r.correct}, ensure_ascii=False) + "\n")
        fh.flush()
        return r

    J.ClaudeJudge.judge = _patched

    mods = {"smoc": "ext_smoc_arm", "direct": "ext_direct_arm"}
    modname = mods.get(arm, "lb_reader_arm")
    mod = __import__(modname)
    sys.argv = [modname] + passthru
    rc = mod.main()
    fh.close()
    return rc or 0


if __name__ == "__main__":
    raise SystemExit(main())
