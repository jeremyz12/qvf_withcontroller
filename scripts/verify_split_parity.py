#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""去耦合验证:数据层 split 字段 vs 原硬编码裁题分支,题集逐 qid 对拍。

背景(耦合审计 08-15,risk=high):qvf_router.py 原有一行
    if name == "wiki-P39":  # dev-5 隔离
        qs = [x for x in qs if x[1] in arms["wt"]]
用"哪些行恰好存在于 wt 结果文件里"反推测试集。切分本身正当(P39 dev-5 /
test-52),但以结果文件定义测试集形式上等同 cherry-picking,是审计里
"最像 cherry-picking 的一行"。08-16 改为数据层 it["split"] 显式声明。

本脚本证明:两种实现产生的题集**逐 qid 完全相同**,即这是纯重构,
不改变任何已归档数字。零 LLM 调用。

用法: python scripts/verify_split_parity.py
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-for-import")
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

_spec = importlib.util.spec_from_file_location("qr", "scripts/qvf_router.py")
qr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qr)


def qids_of(items, normkey):
    """复现主流程的题目枚举(uid, qid)。"""
    out = []
    for it in items:
        for dim in it.get("probing_queries", {}):
            out.append((it["uid"], normkey(f"{it['uid']}_{dim}")))
    return out


def old_filter(name, qs, arms):
    """原硬编码分支。"""
    if name == "wiki-P39":
        return [x for x in qs if x[1] in arms["wt"]]
    return qs


def new_filter(items, qs):
    """数据层 split 字段。"""
    split = {it["uid"]: it.get("split", "test") for it in items}
    if any(v != "test" for v in split.values()):
        return [x for x in qs if split.get(x[0], "test") == "test"]
    return qs


def main():
    fails = []
    print(f"{'bench':16s} {'全卷':>5s} {'旧口径':>6s} {'新口径':>6s}  判决")
    for name, data_f, d_spec, r_spec, w_spec in qr.BENCHES:
        if not Path(data_f).exists():
            print(f"{name:16s} {'-':>5s} {'-':>6s} {'-':>6s}  跳过(数据文件不存在)")
            continue
        items = json.loads(Path(data_f).read_text(encoding="utf-8"))
        qs_all = qids_of(items, qr.normkey)
        arms = {"wt": qr.load_arm(*w_spec) if w_spec else {},
                "direct": qr.load_arm(*d_spec) if d_spec else {}}
        # 主流程在裁题前先按 direct 在场过滤,此处同步复现以保证可比
        qs = [x for x in qs_all if x[1] in arms["direct"]]
        old = sorted(q for _, q in old_filter(name, qs, arms))
        new = sorted(q for _, q in new_filter(items, qs))
        ok = old == new
        if not ok:
            fails.append((name, sorted(set(old) ^ set(new))))
        print(f"{name:16s} {len(qs_all):5d} {len(old):6d} {len(new):6d}  "
              f"{'✅ 逐 qid 相同' if ok else '❌ 不一致'}")

    print()
    if fails:
        print("对拍失败:")
        for name, diff in fails:
            print(f"  {name}: 差集 {len(diff)} 个 → {diff[:10]}")
        sys.exit(1)
    print("全部基准逐 qid 相同 —— 数据层 split 为纯重构,已归档数字不受影响。")


if __name__ == "__main__":
    main()
