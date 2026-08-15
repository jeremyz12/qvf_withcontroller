# -*- coding: utf-8 -*-
"""新域三属性遥测与汇总(纯离线,零 LLM):
① 卡片遥测:slot_class 分布(other:* 占比)、owner 分布、逐字锚点合法率、
   SLOT_ALIASES 命中率(聚焦槽位侧,取自 routes 文件);
② 路由分布与相对旧域(router_routes_v42_final 的 wiki-* 子集)漂移;
③ S1-S4 各臂与路由组合正确率(逐域逐题型);
④ S5:编译 ok 率 / op 分布 / 空证据率、臂 vs 直读;
⑤ token 记账。
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DOMS = ["P26", "P69", "P1303"]
DATA = {d: f"data/newdom_{d}_full.json" for d in DOMS}

SLOT_ALIASES = {
    "position": ["position", "职位", "job", "role", "chairman", "member",
                 "committee", "议员", "委员", "职务", "任职", "mayor",
                 "minister", "office"],
    "employer": ["employer", "雇主", "company", "工作", "单位", "university",
                 "institute", "works for", "employed"],
    "team": ["team", "球队", "队", "club"],
    "residence": ["residence", "住", "居住", "address", "city", "live",
                  "hometown"],
    "device": ["device", "phone", "laptop", "tablet", "camera", "手机",
               "电脑", "设备"],
    "location": ["location", "位置", "地点", "place", "where"],
    "relationship": ["relationship", "partner", "spouse", "wife", "husband",
                     "girlfriend", "boyfriend", "married", "婚", "恋", "关系"],
}


def _norm(s):
    return " ".join(str(s).lower().replace("_", " ").replace("-", " ").split())


def rows(p):
    out = []
    if Path(p).exists():
        for l in open(p, encoding="utf-8"):
            s = l.strip()
            if s:
                out.append(json.loads(s))
    return out


def card_telemetry():
    print("=" * 70)
    print("① 卡片遥测(results/wt_cards_newdom)")
    for dom in DOMS:
        data = {e["uid"]: e for e in
                json.loads(Path(DATA[dom]).read_text(encoding="utf-8"))}
        cls = Counter()
        own = Counter()
        a_ok = a_bad = n = 0
        for uid, e in data.items():
            f = Path("results/wt_cards_newdom") / f"{uid}.json"
            if not f.exists():
                continue
            c = json.loads(f.read_text(encoding="utf-8"))
            mem = {}
            for si, s in enumerate(e["sessions"]):
                for ri, t in enumerate(s["turns"]):
                    mem[f"{uid}/s{si}#r{ri}"] = str(t)
            for r in c["records"]:
                n += 1
                cls[r.get("slot_class") or "<none>"] += 1
                own[r.get("owner") or "<empty>"] += 1
                sp = r.get("source_span", "")
                if sp and sp in mem.get(r.get("source_memory_id", ""), ""):
                    a_ok += 1
                else:
                    a_bad += 1
        other = sum(v for k, v in cls.items() if k.startswith("other:"))
        none = cls.get("<none>", 0)
        closed = n - other - none
        print(f"\n[{dom}] cards={n} 闭集 {closed} ({closed/n*100:.1f}%) "
              f"other:* {other} ({other/n*100:.1f}%) 无类 {none}")
        print("  top slot_class:", cls.most_common(8))
        print(f"  owner: {dict(own.most_common(3))}")
        print(f"  逐字锚点合法率 {a_ok}/{n} = {a_ok/n*100:.1f}%")


def route_telemetry():
    print("=" * 70)
    print("② 路由分布与漂移")
    old = [json.loads(l) for l in
           open("results/router_routes_v42_final.jsonl", encoding="utf-8")]
    oldw = [r for r in old if r["bench"].startswith("wiki-")]
    oc = Counter(r["route"] for r in oldw)
    on = len(oldw)
    print(f"旧域 wiki-* 基线 n={on}: "
          + " ".join(f"{k} {v/on*100:.1f}%" for k, v in oc.most_common()))
    allc = Counter()
    alln = 0
    for dom in DOMS:
        rs = rows(f"results/newdom_routes_{dom}.jsonl")
        if not rs:
            continue
        c = Counter(r["route"] for r in rs)
        n = len(rs)
        allc += c
        alln += n
        # SLOT_ALIASES 命中率(聚焦槽位)
        hit = sum(1 for r in rs if any(
            a in _norm(r.get("focus_slot", "")) for al in SLOT_ALIASES.values()
            for a in al))
        kd_none = sum(1 for r in rs if r.get("keyed_depth") is None)
        print(f"[{dom}] n={n}: "
              + " ".join(f"{k} {v} ({v/n*100:.1f}%)" for k, v in c.most_common())
              + f" | 聚焦槽位别名命中 {hit}/{n}={hit/n*100:.1f}%"
              + f" | keyed_depth=None(direct/含算术直通) {kd_none}")
        d = defaultdict(Counter)
        for r in rs:
            d[r["dim"]][r["route"]] += 1
        for k, v in sorted(d.items()):
            print(f"    {k}: {dict(v)}")
    if alln:
        print(f"新域合计 n={alln}: "
              + " ".join(f"{k} {v/alln*100:.1f}%" for k, v in allc.most_common())
              + "  漂移(vs 旧域wiki): "
              + " ".join(f"{k} {allc.get(k,0)/alln*100 - oc.get(k,0)/on*100:+.1f}pp"
                         for k in set(list(allc) + list(oc))))


def arm_table():
    print("=" * 70)
    print("③ S1-S4 各臂与路由组合(逐域逐题型)")
    from scripts.qvf_router import normkey
    for dom in DOMS:
        arms = {
            "direct": rows(f"results/newdom_direct_{dom}.jsonl"),
            "rt": rows(f"results/newdom_rt_{dom}.jsonl"),
            "wt": rows(f"results/newdom_wt_{dom}.jsonl"),
            "prompt": rows(f"results/newdom_prompt_{dom}.jsonl"),
        }
        comb = rows(f"results/newdom_router_{dom}.jsonl")
        print(f"\n[{dom}]")
        dims = sorted({r["question_type"] for a in arms.values() for r in a})
        for dim in dims:
            line = f"  {dim:26s}"
            for a, rs in arms.items():
                sub = [r for r in rs if r["question_type"] == dim]
                if sub:
                    c = sum(1 for r in sub if r.get("judge_correct"))
                    line += f" {a} {c}/{len(sub)}={c/len(sub)*100:5.1f}%"
            print(line)
        if comb:
            cd = defaultdict(lambda: [0, 0])
            for r in comb:
                cd[r["dim"]][0] += bool(r["result"])
                cd[r["dim"]][1] += 1
            for k, (c, t) in sorted(cd.items()):
                print(f"  ROUTER {k}: {c}/{t}={c/t*100:.1f}%")
            tot = sum(v[0] for v in cd.values())
            n = sum(v[1] for v in cd.values())
            print(f"  ROUTER TOTAL {tot}/{n}={tot/n*100:.1f}%")


def s5_table():
    print("=" * 70)
    print("④ S5 编译臂 vs 直读(逐域逐题型)+ 编译遥测")
    for dom in DOMS:
        arm = rows(f"results/newdom_s5_arm_{dom}.jsonl")
        dr = rows(f"results/newdom_s5_direct_{dom}.jsonl")
        if not arm and not dr:
            continue
        print(f"\n[{dom}] arm n={len(arm)} direct n={len(dr)}")
        ops = Counter(r.get("plan", {}).get("op") for r in arm)
        okn = sum(1 for r in arm if r.get("compile_ok"))
        ev0 = sum(1 for r in arm if r.get("evidence_n") == 0)
        if arm:
            print(f"  compile_ok {okn}/{len(arm)}={okn/len(arm)*100:.1f}%  "
                  f"空证据行 {ev0}/{len(arm)}={ev0/len(arm)*100:.1f}%  "
                  f"op分布 {dict(ops.most_common())}")
        qts = sorted({r["question_type"] for r in arm + dr})
        for qt in qts:
            line = f"  {qt:16s}"
            for name, rs in (("arm", arm), ("direct", dr)):
                sub = [r for r in rs if r["question_type"] == qt]
                if sub:
                    c = sum(1 for r in sub if r.get("judge_correct"))
                    line += f" {name} {c}/{len(sub)}={c/len(sub)*100:5.1f}%"
            print(line)


def tokens():
    print("=" * 70)
    print("⑤ token 记账(haiku $1/$5 /M;判官 opus-5 另计)")
    tot_in = tot_out = 0
    for pat, label in [
        ("results/newdom_build_*.log", None),  # builds handled separately
    ]:
        pass
    # build logs
    b_in = b_out = 0
    import glob as _g
    for lgp in _g.glob("results/newdom_build_*.log"):
        m = re.search(r"WRITE PHASE TOTAL: in=(\d+) out=(\d+)",
                      Path(lgp).read_text(encoding="utf-8"))
        if m:
            b_in += int(m.group(1))
            b_out += int(m.group(2))
    # 冒烟 5 库(单独调用,控制台记录)
    b_in += 107768
    b_out += 31765
    print(f"建卡(不含冒烟5库): in={b_in} out={b_out} "
          f"≈ ${b_in/1e6*1+b_out/1e6*5:.2f}")
    grand_in, grand_out = b_in, b_out
    for pat in ["newdom_direct_{d}", "newdom_rt_{d}", "newdom_wt_{d}",
                "newdom_prompt_{d}", "newdom_s5_arm_{d}",
                "newdom_s5_direct_{d}"]:
        p_in = p_out = n = 0
        for dom in DOMS:
            for r in rows("results/" + pat.format(d=dom) + ".jsonl"):
                p_in += int(r.get("usage_input_tokens") or 0)
                p_out += int(r.get("usage_output_tokens") or 0)
                n += 1
        if n:
            print(f"{pat.format(d='*'):28s} n={n:4d} in={p_in} out={p_out} "
                  f"≈ ${p_in/1e6*1+p_out/1e6*5:.2f}")
            grand_in += p_in
            grand_out += p_out
    print(f"合计(haiku 侧): in={grand_in} out={grand_out} "
          f"≈ ${grand_in/1e6*1+grand_out/1e6*5:.2f}")


if __name__ == "__main__":
    card_telemetry()
    route_telemetry()
    arm_table()
    s5_table()
    tokens()
