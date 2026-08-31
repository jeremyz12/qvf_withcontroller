# -*- coding: utf-8 -*-
"""渲染修复(QVF_RENDER_ANCHORS)持出集跑批入口。

纯粹是 scripts/complex_query_arm.py:run() 的一层薄封装 —— 不改动、不复制
该函数任何逻辑,只是换一种导入方式:直接执行 `python -m
scripts.complex_query_arm ...`(该文件以 __main__ 身份运行)在 QVF_ALGEBRA=1
时会触发 complex_query_arm <-> qvf_algebra 的循环 import(两边互相
`from scripts.X import ...`,__main__ 与 "scripts.complex_query_arm" 是
两个不同的模块对象,第二次以包名重新加载会在 qvf_algebra 模块还没定义完
时去取它的符号)。本文件以 __main__ 身份先把 "scripts.complex_query_arm"
当作一个普通包子模块导入(而不是自己就是它),sys.modules 只会有一份,
不会重复初始化,循环 import 就不会发生。complex_query_arm.py/qvf_algebra.py
零改动。

用法同 complex_query_arm.py 的 CLI:
  python -m scripts.s8_render_fix_run --data ... --questions ... --out ... [--uids ...] [--resume]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.complex_query_arm import run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--questions", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--uids", default=None)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    uid_list = [u for u in (a.uids or "").split(",") if u] or None
    run(a.data, a.questions, a.out, uid_list, a.resume)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
