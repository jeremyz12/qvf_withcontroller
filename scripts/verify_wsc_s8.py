# -*- coding: utf-8 -*-
"""S8 独立复核校验器(与 gen_wsc_s8.py 分离编写,不导入其组合逻辑)。

对 data/wsc_s8.jsonl 每一行,从原始源文件重新加载链、重新用 params 里记录
的锚点/窗口坐标,按各 combo 类型独立重写的定义重新推导 gold,与落盘 gold
逐行比对。只共用最基础的日期解析工具(parse_partial_date),组合判定逻辑
全部独立重写,以捕获生成器里可能存在的索引/序列化/复用变量类 bug。

用法:
  python scripts/verify_wsc_s8.py
退出码 0 = 全量一致;非 0 = 存在不一致,详情打印到 stdout。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.gen_wikistate_complex import parse_partial_date

ROWS = ROOT / "data" / "wsc_s8.jsonl"

SINGLE_FILES = ["data/wikistate_full_P108.json", "data/wikistate_full_P54.json",
                "data/wikistate_full_P551.json"]
MULTI_FILES = ["data/wikistate_full_multi_big.json",
               "data/wikistate_full_multi_P108_P551.json"]


def _parse_chain(chain) -> Tuple[List[date], List[str]]:
    parsed, values = [], []
    for step in chain:
        dt, _ = parse_partial_date(step["date"])
        parsed.append(dt)
        values.append(str(step["value"]))
    return parsed, values


def _load_single_index() -> Dict[Tuple[str, str], dict]:
    """(uid, source) -> {parsed, values} for single-chain entries."""
    idx: Dict[Tuple[str, str], dict] = {}
    for f in SINGLE_FILES:
        for e in json.loads((ROOT / f).read_text(encoding="utf-8")):
            chain = e.get("chain") or []
            if len(chain) < 3:
                continue
            parsed, values = _parse_chain(chain)
            idx[(e["uid"], f)] = {"parsed": parsed, "values": values,
                                   "slot": e["slot"]}
    return idx


def _load_cross_index(
        multi_files: Optional[List[str]] = None) -> Dict[Tuple[str, str], dict]:
    """(uid, source) -> {"a": {...}, "b": {...}} for dual-chain worlds.

    Keyed by every (uid, file) pair found, independent of any noise/monotonic
    filtering — each row already names the exact source file it was built
    from (rows land on whichever file the generator's per-uid fallback
    picked), so verification just needs to load that same raw chain, not
    re-derive the fallback choice itself.

    multi_files: 覆盖 MULTI_FILES 的来源列表(v2 复核追加渲染的新文件用;
    不传时行为与 v1 逐字节一致)。
    """
    idx: Dict[Tuple[str, str], dict] = {}
    for f in (multi_files if multi_files is not None else MULTI_FILES):
        for e in json.loads((ROOT / f).read_text(encoding="utf-8")):
            c2 = e.get("chain2") or {}
            ca, cb = e.get("chain") or [], c2.get("chain") or []
            if not ca or not cb:
                continue
            key = (e["uid"], f)
            if key in idx:
                continue  # duplicate uid within same file: keep first
            pa, va = _parse_chain(ca)
            pb, vb = _parse_chain(cb)
            idx[key] = {
                "a": {"parsed": pa, "values": va, "slot": e["slot"]},
                "b": {"parsed": pb, "values": vb, "slot": c2["slot"]},
            }
    return idx


def _side(world: dict, wk: str) -> dict:
    return world[wk]


def _other(wk: str) -> str:
    return "b" if wk == "a" else "a"


def check_row(row: dict, singles: dict, crosses: dict) -> str | None:
    """Return None if row's gold matches independent recomputation, else a
    mismatch description string."""
    combo = row["combo"]
    p = row["params"]
    src = row["source"]
    uid = row["uid"]

    if combo == "WINDOW∘COUNT":
        if p["kind"] == "date_window":
            ent = singles.get((uid, src))
            if ent is None:
                return f"single entry not found for {uid}/{src}"
            parsed = ent["parsed"]
            d1 = date.fromisoformat(p["d1"])
            d2 = date.fromisoformat(p["d2"])
            g1, g2 = p["g1"], p["g2"]
            if not (parsed[g1] < d1 < parsed[g1 + 1]):
                return f"d1 not strictly inside gap g1: {d1} vs " \
                       f"({parsed[g1]}, {parsed[g1+1]})"
            if not (parsed[g2] < d2 < parsed[g2 + 1]):
                return f"d2 not strictly inside gap g2: {d2} vs " \
                       f"({parsed[g2]}, {parsed[g2+1]})"
            recomputed = sum(1 for t in parsed[1:] if d1 < t < d2)
            if recomputed != row["gold"]:
                return f"date_window recompute={recomputed} != gold={row['gold']}"
            return None
        elif p["kind"] == "value_window":
            world = crosses.get((uid, src))
            if world is None:
                return f"cross world not found for {uid}/{src}"
            W = _side(world, p["w_side"])
            C = _side(world, _other(p["w_side"]))
            i = p["w_index"]
            if W["values"][i] != p["w_value"]:
                return f"w_value mismatch: {W['values'][i]} != {p['w_value']}"
            s = W["parsed"][i]
            e = W["parsed"][i + 1] if i + 1 < len(W["parsed"]) else None
            recomputed = sum(1 for t in C["parsed"][1:]
                              if t > s and (e is None or t < e))
            if recomputed != row["gold"]:
                return f"value_window recompute={recomputed} != gold={row['gold']}"
            return None
        return f"unknown WINDOW∘COUNT kind {p['kind']}"

    if combo == "NTH∘CMP_DUR":
        ent = singles.get((uid, src))
        if ent is None:
            return f"single entry not found for {uid}/{src}"
        parsed, values = ent["parsed"], ent["values"]
        i, j = p["i"], p["j"]
        di = (parsed[i + 1] - parsed[i]).days
        dj = (parsed[j + 1] - parsed[j]).days
        if di == dj:
            return f"durations equal ({di}), should have been filtered"
        expect = values[i] if di > dj else values[j]
        if expect != row["gold"]:
            return f"cmp_dur expect={expect} != gold={row['gold']} (di={di} dj={dj})"
        return None

    if combo == "WINDOW∘AGG":
        ent = singles.get((uid, src))
        if ent is None:
            return f"single entry not found for {uid}/{src}"
        parsed, values = ent["parsed"], ent["values"]
        g = p["g"]
        d = date.fromisoformat(p["d"])
        if not (parsed[g] < d < parsed[g + 1]):
            return f"cutoff d not strictly inside gap g: {d} vs " \
                   f"({parsed[g]}, {parsed[g+1]})"
        dur_a: Dict[str, int] = {}
        for k in range(g):
            dur_a[values[k]] = dur_a.get(values[k], 0) + \
                (parsed[k + 1] - parsed[k]).days
        dur_a[values[g]] = dur_a.get(values[g], 0) + (d - parsed[g]).days
        dur_b: Dict[str, int] = {}
        for k in range(g):
            dur_b[values[k]] = dur_b.get(values[k], 0) + \
                (parsed[k + 1] - parsed[k]).days
        wa_ = sorted(dur_a.items(), key=lambda kv: -kv[1])
        wb_ = sorted(dur_b.items(), key=lambda kv: -kv[1])
        if len(wa_) < 2 or wa_[0][1] == wa_[1][1]:
            return "reading A winner not unique"
        if len(wb_) > 1 and wb_[0][1] == wb_[1][1]:
            return "reading B winner not unique"
        if wa_[0][0] != wb_[0][0]:
            return f"reading disagreement: A={wa_[0][0]} B={wb_[0][0]}"
        if wa_[0][0] != row["gold"]:
            return f"window_agg expect={wa_[0][0]} != gold={row['gold']}"
        return None

    if combo == "WINDOW_2ANCHOR∘COUNT":
        if p["kind"] == "same_chain":
            ent = singles.get((uid, src))
            if ent is None:
                return f"single entry not found for {uid}/{src}"
            parsed, values = ent["parsed"], ent["values"]
            i, j = p["i"], p["j"]
            if values[i] != p["vi"] or values[j] != p["vj"]:
                return "vi/vj mismatch with chain values"
            recomputed = max(j - i - 1, 0)
            if recomputed != row["gold"]:
                return f"same_chain recompute={recomputed} != gold={row['gold']}"
            return None
        elif p["kind"] == "cross":
            world = crosses.get((uid, src))
            if world is None:
                return f"cross world not found for {uid}/{src}"
            W = _side(world, p["w_side"])
            C = _side(world, _other(p["w_side"]))
            i, j = p["i"], p["j"]
            if W["values"][i] != p["vi"] or W["values"][j] != p["vj"]:
                return "vi/vj mismatch with chain values"
            ti, tj = W["parsed"][i], W["parsed"][j]
            recomputed = sum(1 for t in C["parsed"][1:] if ti < t < tj)
            if recomputed != row["gold"]:
                return f"cross w2 recompute={recomputed} != gold={row['gold']}"
            return None
        return f"unknown WINDOW_2ANCHOR∘COUNT kind {p['kind']}"

    if combo == "NTH∘JOIN_T":
        world = crosses.get((uid, src))
        if world is None:
            return f"cross world not found for {uid}/{src}"
        W = _side(world, p["w_side"])
        O = _side(world, _other(p["w_side"]))
        n = p["n"]
        T = W["parsed"][n]
        candidates = [k for k, t in enumerate(O["parsed"]) if t < T]
        if not candidates:
            return "no O interval starts before anchor T"
        j = max(candidates)
        if any(t == T for t in O["parsed"]):
            return "T coincides with an O boundary, should have been skipped"
        expect = O["values"][j]
        if expect != row["gold"]:
            return f"nth_join expect={expect} != gold={row['gold']}"
        return None

    if combo == "JOIN_T∘WINDOW":
        world = crosses.get((uid, src))
        if world is None:
            return f"cross world not found for {uid}/{src}"
        W = _side(world, p["w_side"])
        C = _side(world, _other(p["w_side"]))
        if len(set(W["values"])) != len(W["values"]):
            return "W values not unique, should have been skipped"
        c_tr = C["parsed"][1:]
        if any(t in W["parsed"] for t in c_tr):
            return "boundary coincidence, should have been skipped"
        counts = []
        for k in range(len(W["parsed"])):
            s = W["parsed"][k]
            e = W["parsed"][k + 1] if k + 1 < len(W["parsed"]) else None
            counts.append(sum(1 for t in c_tr if t > s and (e is None or t < e)))
        ge2 = [k for k, c in enumerate(counts) if c >= 2]
        if len(ge2) == 1:
            mode = "unique_ge2"
            win = ge2[0]
        else:
            mx = max(counts) if counts else 0
            if mx < 2 or counts.count(mx) != 1:
                return f"no unique winner under either mode, counts={counts}"
            mode = "unique_argmax"
            win = counts.index(mx)
        if mode != p["mode"] or win != p["win_index"]:
            return f"mode/win_index mismatch: recomputed ({mode},{win}) " \
                   f"!= stored ({p['mode']},{p['win_index']})"
        expect = W["values"][win]
        if expect != row["gold"]:
            return f"join_window expect={expect} != gold={row['gold']}"
        return None

    return f"unknown combo {combo}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", default=str(ROWS), help="待复核的 jsonl 路径")
    ap.add_argument("--extra-multi", nargs="*", default=[],
                    help="追加到 MULTI_FILES 的跨槽位来源文件(需与生成时"
                         "一致;不传时 v1 行为逐字节不变)")
    args = ap.parse_args()
    rows_path = Path(args.rows)
    multi_files = MULTI_FILES + list(args.extra_multi)

    rows = [json.loads(l) for l in rows_path.read_text(encoding="utf-8")
            .splitlines() if l.strip()]
    singles = _load_single_index()
    crosses = _load_cross_index(multi_files)

    mismatches = []
    by_combo_n: Dict[str, int] = {}
    by_combo_ok: Dict[str, int] = {}
    for row in rows:
        by_combo_n[row["combo"]] = by_combo_n.get(row["combo"], 0) + 1
        err = check_row(row, singles, crosses)
        if err is None:
            by_combo_ok[row["combo"]] = by_combo_ok.get(row["combo"], 0) + 1
        else:
            mismatches.append((row["qid"], row["combo"], err))

    print(f"total rows: {len(rows)}")
    for combo in by_combo_n:
        ok = by_combo_ok.get(combo, 0)
        print(f"  {combo:24s} {ok}/{by_combo_n[combo]} independently "
              f"reproduced")
    if mismatches:
        print(f"\n{len(mismatches)} MISMATCHES:")
        for qid, combo, err in mismatches:
            print(f"  [{combo}] {qid}: {err}")
        return 1
    print("\nALL ROWS independently reproduced (100% match).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
