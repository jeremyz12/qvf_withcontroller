# -*- coding: utf-8 -*-
"""批 14 缓存排布核算(预注册 opt_batch14_prereg,确定性计算,无采纳门槛)。
把每臂提示拆成 [库内稳定段 P](账目/全文)+ [动态段 Q](题面+模板),按
Anthropic 缓存计价(写 1.25x,读 0.1x,5 分钟 TTL;同库 4 题连发满足窗口)
计算缓存排布变体的 $/题。注意:缓存排布变体把题面移到提示末尾,偏离 F.1
逐字顺序,故所有缓存列都标"排布变体";对外引用前须做顺序不变性确认跑。
用法: python scripts/cache_accounting.py [arm.jsonl ...](默认 smoc+smw)
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:\ZZL_cluade")
PRICE_IN, PRICE_OUT = 1.0, 5.0          # haiku-4.5 $/M(2026-08 牌价)
W, H = 1.25, 0.10                        # 缓存写/读倍率
QPU = 4                                  # 每库题数(v2:144x4)


def arm_stats(path):
    rows = [json.loads(l) for l in open(ROOT / path, encoding="utf-8")]
    rows = [r for r in rows if "usage_input_tokens" in r]
    by_uid = defaultdict(list)
    for r in rows:
        by_uid[r["uid"]].append(r)
    # P 估计:库内均值输入 - 题面动态部分估计(题字符/3.7);模板固定段并入 P
    # (模板同为跨题稳定前缀的一部分——排布变体里仅题面在末尾)。
    tot_in = sum(r["usage_input_tokens"] for r in rows) / len(rows)
    tot_out = sum(r["usage_output_tokens"] for r in rows) / len(rows)
    p_est, q_est, n_u = 0.0, 0.0, 0
    for uid, rs in by_uid.items():
        qtok = [len(r["question"]) / 3.7 for r in rs]
        m_in = sum(r["usage_input_tokens"] for r in rs) / len(rs)
        p_est += m_in - sum(qtok) / len(qtok)
        q_est += sum(qtok) / len(qtok)
        n_u += 1
    return dict(n=len(rows), uids=n_u, tin=tot_in, tout=tot_out,
                P=p_est / n_u, Q=q_est / n_u)


def dollars(s):
    nocache = (s["tin"] * PRICE_IN + s["tout"] * PRICE_OUT) / 1e6
    # 排布变体:P 段首题写缓存,后 QPU-1 题读缓存;Q 段全价
    p_amort = s["P"] * (W + (QPU - 1) * H) / QPU
    cached = ((p_amort + s["Q"]) * PRICE_IN + s["tout"] * PRICE_OUT) / 1e6
    return nocache, cached


ARMS = sys.argv[1:] or ["results/wsc_v2_smoc.jsonl", "results/wsc_v2_smw.jsonl"]
print(f"{'arm':34s} {'in/q':>7s} {'out/q':>6s} {'P(稳定)':>8s} {'Q(动态)':>8s} "
      f"{'$/q原':>9s} {'$/q缓存变体':>11s} {'省':>5s}")
base = {}
for a in ARMS:
    s = arm_stats(a)
    nc, ca = dollars(s)
    name = Path(a).stem
    base[name] = (nc, ca)
    print(f"{name:34s} {s['tin']:7.0f} {s['tout']:6.0f} {s['P']:8.0f} "
          f"{s['Q']:8.0f} {nc*100:8.3f}c {ca*100:10.3f}c "
          f"{(1-ca/nc)*100:4.0f}%")
if "wsc_v2_smoc" in base and "wsc_v2_smw" in base:
    for tag, i in (("原口径", 0), ("双方缓存变体", 1)):
        r = base["wsc_v2_smw"][i] / base["wsc_v2_smoc"][i]
        print(f"读取成本比 smw/smoc({tag}): {r:.2f}x")
