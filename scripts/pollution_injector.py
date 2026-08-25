# -*- coding: utf-8 -*-
"""P② 污染注入器(预注册 opt_batch6_prereg):零 LLM 机械注入。
对 30 库子集每库注入 K=6 张"伪更替卡":从他库同 slot_class 记录克隆值,
日期确定性插在真链中段——制造假状态转移(conditional 型干扰)。
确定性:一切排序/配对用 SHA-256,无随机数。
用法: python pollution_injector.py --cards results/wt_cards_v42 \
        --out results/wt_cards_v42_inj30 --n-stores 30 --k 6
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")


def h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-stores", type=int, default=30)
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--data", nargs="*", default=[],
                    help="语料卷:补 stated_date 为空的卡的日期(会话日期映射,"
                         "与读取侧 _mem_dates 同口径)")
    ap.add_argument("--restrict", default="",
                    help="只从该文件(每行一个 uid)里选注入库")
    ap.add_argument("--primary-only", action="store_true",
                    help="只注入各库主槽位(语料卷 entry.slot 对应的 slot_class)"
                         "——过滤器只审主槽位池,题目也只问主槽位")
    a = ap.parse_args()
    mem_dates: dict = {}
    if a.data:
        import sys as _s
        _s.path.insert(0, str(ROOT / "scripts"))
        from complex_query_arm import _mem_dates
        for v in a.data:
            for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
                mem_dates.update(_mem_dates(e))
    src = ROOT / a.cards
    outd = ROOT / a.out
    outd.mkdir(parents=True, exist_ok=True)

    files = sorted(p.name for p in src.glob("*.json"))
    entry_slot: dict = {}
    if a.data:
        for v in a.data:
            for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
                entry_slot[e["uid"]] = e.get("slot", "")
    if a.restrict:
        allow = {l.strip() for l in open(ROOT / a.restrict, encoding="utf-8")
                 if l.strip()}
        files = [f for f in files if f[:-5] in allow]
    n = len(files)
    picked = sorted({files[i * n // a.n_stores] for i in range(a.n_stores)})
    stores = {f: json.loads((src / f).read_text(encoding="utf-8"))
              for f in files}

    # 值池:按 slot_class 汇总全体库的 (value, 来源uid)
    pool: dict = {}
    for f, d in stores.items():
        for r in d.get("records", []):
            cls = r.get("slot_class") or r.get("slot") or ""
            v = (r.get("value") or "").strip()
            if cls and v:
                pool.setdefault(cls, []).append((v, f))

    report = {"picked": picked, "per_store": {}}
    for f in picked:
        d = copy.deepcopy(stores[f])
        recs = d.get("records", [])
        # 该库各 slot_class 的带日期记录组(≥2 条才有"链中段"可插)
        groups: dict = {}
        for r in recs:
            cls = r.get("slot_class") or ""
            rd = (r.get("stated_date") or "").strip() or \
                mem_dates.get(r.get("source_memory_id", ""), "")
            if cls and rd:
                rr = dict(r)
                rr["_eff_date"] = rd
                groups.setdefault(cls, []).append(rr)
        # 也允许无 stated_date 的组:日期取自 source_memory_id 序号无从得,跳过
        cand_cls = sorted([c for c, g in groups.items() if len(g) >= 2],
                          key=lambda c: h(f + c))
        if a.primary_only:
            ps = (entry_slot.get(f[:-5]) or "").lower()
            cand_cls = [c for c in cand_cls
                        if ps and (ps in c.lower() or c.lower() in ps)]
        injected = 0
        inj_log = []
        for cls in cand_cls:
            if injected >= a.k:
                break
            g = sorted(groups[cls], key=lambda r: r.get("_eff_date", ""))
            own_vals = {(r.get("value") or "").strip().lower() for r in g}
            # 他库同类值,确定性挑第一个不在本库值集里的
            foreign = [(v, sf) for v, sf in pool.get(cls, [])
                       if sf != f and v.strip().lower() not in own_vals]
            if not foreign:
                continue
            foreign.sort(key=lambda t: h(f + cls + t[0]))
            # 去重外值,每类注满余量:不同外值 × 轮转链窗口
            seen_fv = set()
            uniq_foreign = []
            for fv, sf in foreign:
                k2 = fv.strip().lower()
                if k2 not in seen_fv:
                    seen_fv.add(k2)
                    uniq_foreign.append((fv, sf))
            from datetime import date as _date
            wi = 0
            for fv, sf in uniq_foreign:
                if injected >= a.k:
                    break
                # 轮转窗口:第 wi 与 wi+1 条真卡之间的中点
                win = wi % (len(g) - 1)
                wi += 1
                d1 = g[win].get("_eff_date")
                d2 = g[win + 1].get("_eff_date")
                try:
                    a1 = _date.fromisoformat(d1[:10])
                    a2 = _date.fromisoformat(d2[:10])
                    if (a2 - a1).days < 2:
                        continue
                    mid_s = (a1 + (a2 - a1) / 2).isoformat()
                except Exception:  # noqa: BLE001
                    continue
                base = g[win]
                fake = copy.deepcopy(
                    {k: v for k, v in base.items() if k != "_eff_date"})
                fake["record_id"] = f"inj{injected}_{h(f + cls + fv)[:8]}"
                fake["value"] = fv
                fake["stated_date"] = mid_s
                fake["claim"] = f"The user's {cls} changed to {fv}."
                fake["source_span"] = base.get("source_span", "")
                # 锚点袭用真卡:溯源信号全满分,只有语义角色判断能识破
                recs.append(fake)
                injected += 1
                inj_log.append({"cls": cls, "value": fv, "date": mid_s,
                                "from": sf})
        d["records"] = recs
        (outd / f).write_text(json.dumps(d, ensure_ascii=False),
                              encoding="utf-8")
        report["per_store"][f] = {"injected": injected, "log": inj_log}
    # 未选中的库原样拷贝(读取侧按 uid 找文件,保持完整目录)
    for f in files:
        if f not in picked:
            (outd / f).write_text(json.dumps(stores[f], ensure_ascii=False),
                                  encoding="utf-8")
    tot = sum(v["injected"] for v in report["per_store"].values())
    (ROOT / (a.out + "_report.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"picked {len(picked)} stores, injected {tot} fake cards "
          f"(mean {tot/len(picked):.1f}/store) -> {outd}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
