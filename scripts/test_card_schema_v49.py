# -*- coding: utf-8 -*-
"""批 46e:scripts/wt_qvf_prototype_v49.py 的零 API / 零 LLM 回归测试。

三层断言(见 results/opt_batch46e_verdict.md 的完整根因与判决):
  1. 正例——已知"好"店(批 33-A 派生店 results/wt_cards_v45k,machine 生成于
     scripts/b33A_backfill_slot_class.py)必须整店通过 schema 检查。
  2. 反例——已知"坏"店(冻结建卡器 scripts/wt_qvf_prototype.py 在
     QVF_CARD_KEYS 默认 0 下建出的 results/wt_cards_v45)必须**两个字段
     0% 覆盖**,即 schema 检查必须能把它判失败。这条把本批的根因判决
     (v43 起建卡器丢字段)固化进可执行代码,不只是写在文档里。
  3. 核心回归——scripts/wt_qvf_prototype_v49.py 的 backfill_store()(干跑
     模式,零 API)对 v45 重新派生 slot_class/owner 到新目录
     results/wt_cards_v45k2,必须(a)整店通过 schema 检查,且(b)与 1) 的
     v45k 逐条 (uid, record_id) 对齐后 slot_class/owner 完全一致,零差异。

不发起任何网络/LLM 调用——backfill_store() 是纯本地 JSON 读写 + 确定性
字符串匹配(与 b33A 派生脚本同逻辑)。

用法:
  PYTHONUTF8=1 python scripts/test_card_schema_v49.py             # 独立运行,print 汇总,非零退出码=失败
  PYTHONUTF8=1 python -m pytest scripts/test_card_schema_v49.py -q  # 或用 pytest(test_* 函数可被发现)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.complex_query_arm import SLOT_ALIASES  # noqa: E402
from scripts.wt_qvf_prototype_v49 import backfill_store  # noqa: E402

# 与 SLOT_ALIASES 的 7 个闭集类目同表(动态导入,不手写副本、不会与
# complex_query_arm.py 的表脱钩)。
ALLOWED_SLOT_CLASSES = set(SLOT_ALIASES.keys())


def _is_allowed_slot_class(v) -> bool:
    """slot_class 的合法取值:SLOT_ALIASES 的某个闭集类目,或
    "other:<归一名>" 开放前缀(与 classify_slot() 的返回值域逐一对应)。
    """
    return isinstance(v, str) and bool(v) and (
        v in ALLOWED_SLOT_CLASSES or v.startswith("other:"))


def _is_allowed_owner(v) -> bool:
    """owner 的合法取值:必须存在且是字符串——它是抽取器 entity 字段的
    原文抄写(不做 self/other 二值化,见 wt_qvf_prototype_v49._apply_card_
    keys 的文档字符串)。"" / "user" 是概念上的 self,任何其他字符串
    (第三方姓名/关系词,如 "cousin_rachel")是概念上的 other——两者都
    合法,唯一硬约束是类型必须是 str(不能整键缺失、不能是 None/数字)。
    """
    return isinstance(v, str)


def load_store(store_dir: Path) -> List[Tuple[str, dict]]:
    """展平一个店目录为 [(uid, record_dict), ...]。"""
    out: List[Tuple[str, dict]] = []
    for f in sorted(store_dir.glob("*.json")):
        obj = json.loads(f.read_text(encoding="utf-8"))
        uid = obj.get("uid", f.stem)
        for r in obj.get("records", []):
            out.append((uid, r))
    return out


def check_store_schema(store_dir: Path) -> dict:
    """核验一个店目录里每条记录都带 slot_class/owner 且取值合法。"""
    recs = load_store(store_dir)
    n_missing_slot_class = n_bad_slot_class = 0
    n_missing_owner = n_bad_owner = 0
    violations: List[Tuple[str, str, str]] = []

    for uid, r in recs:
        rid = r.get("record_id", "?")
        if "slot_class" not in r:
            n_missing_slot_class += 1
            if len(violations) < 20:
                violations.append((uid, rid, "missing slot_class"))
        elif not _is_allowed_slot_class(r["slot_class"]):
            n_bad_slot_class += 1
            if len(violations) < 20:
                violations.append((uid, rid, f"bad slot_class={r['slot_class']!r}"))
        if "owner" not in r:
            n_missing_owner += 1
            if len(violations) < 20:
                violations.append((uid, rid, "missing owner"))
        elif not _is_allowed_owner(r["owner"]):
            n_bad_owner += 1
            if len(violations) < 20:
                violations.append((uid, rid, f"bad owner={r['owner']!r}"))

    return {
        "store": str(store_dir),
        "n_records": len(recs),
        "n_missing_slot_class": n_missing_slot_class,
        "n_bad_slot_class": n_bad_slot_class,
        "n_missing_owner": n_missing_owner,
        "n_bad_owner": n_bad_owner,
        "n_violations_total": (n_missing_slot_class + n_bad_slot_class
                                + n_missing_owner + n_bad_owner),
        "violations_sample": violations,
    }


def diff_slot_owner(store_a: Path, store_b: Path) -> dict:
    """按 (uid, record_id) 对齐两个店,逐条比较 slot_class/owner 是否相同。"""
    def index(store: Path) -> dict:
        idx = {}
        for uid, r in load_store(store):
            idx[(uid, r.get("record_id"))] = (r.get("slot_class"), r.get("owner"))
        return idx

    a, b = index(store_a), index(store_b)
    keys_a, keys_b = set(a), set(b)
    common = keys_a & keys_b
    mismatches = [(k, a[k], b[k]) for k in sorted(common) if a[k] != b[k]]
    return {
        "store_a": str(store_a), "store_b": str(store_b),
        "n_a": len(keys_a), "n_b": len(keys_b), "n_common": len(common),
        "n_only_a": len(keys_a - keys_b), "n_only_b": len(keys_b - keys_a),
        "n_mismatches": len(mismatches),
        "mismatches_sample": mismatches[:20],
    }


# ─────────────────────────── test_* (pytest 可发现) ────────────────────────
V45 = ROOT / "results/wt_cards_v45"       # 冻结建卡器建出,已知两字段 0% 覆盖
V45K = ROOT / "results/wt_cards_v45k"     # 批 33-A 派生店(已知修复,machine-made)
V45K2 = ROOT / "results/wt_cards_v45k2"   # 本测试用 v49 backfill_store() 现场重建


def test_known_good_store_v45k_passes_schema():
    stats = check_store_schema(V45K)
    assert stats["n_records"] > 0, f"store empty or missing: {V45K}"
    assert stats["n_violations_total"] == 0, stats["violations_sample"]


def test_known_bad_store_v45_fails_schema():
    """反例:冻结建卡器(QVF_CARD_KEYS 默认 0)建的 v45 必须两个字段全无。
    这条断言把本批的根因判决(v43 起建卡器丢字段)固化进可执行代码。"""
    stats = check_store_schema(V45)
    assert stats["n_records"] > 0, f"store empty or missing: {V45}"
    assert stats["n_missing_slot_class"] == stats["n_records"], stats
    assert stats["n_missing_owner"] == stats["n_records"], stats


def test_v49_dry_run_reproduces_v45k():
    """核心回归:v49 backfill_store()(零 API)在 v45 上重新派生
    slot_class/owner,产物必须通过 schema 检查,且与 v45k 逐条 diff 为零。
    """
    if V45K2.exists():
        shutil.rmtree(V45K2)
    stats = backfill_store(V45, V45K2)
    assert stats["n_records"] > 0
    assert stats["n_records"] == check_store_schema(V45)["n_records"], (
        "backfill 前后记录数应不变(只加键、不删/不并记录)")

    schema_stats = check_store_schema(V45K2)
    assert schema_stats["n_violations_total"] == 0, schema_stats["violations_sample"]

    diff = diff_slot_owner(V45K2, V45K)
    assert diff["n_only_a"] == 0 and diff["n_only_b"] == 0, diff
    assert diff["n_mismatches"] == 0, diff["mismatches_sample"]


def _run_all() -> bool:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    ok = True
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            ok = False
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    return ok


if __name__ == "__main__":
    passed = _run_all()
    print("ALL TESTS PASSED" if passed else "SOME TESTS FAILED")
    sys.exit(0 if passed else 1)
