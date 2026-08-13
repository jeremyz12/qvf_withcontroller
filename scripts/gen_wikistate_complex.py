# -*- coding: utf-8 -*-
"""WikiState-Complex 题集生成器:S5 聚合/计数题(机械 gold)+ S7 语义标签演示题。

纯代码、零 API、确定性输出。

S5(默认):对 len(chain)>=3 的条目,从 chain 结构机械推导 gold:
  (a) longest_tenure  最长任期(仅闭区间口径;末段开区间在 Today=末链日期
      时长为 0,不可能超过任何闭区间,故排除 —— 口径记入 basis);
  (b) change_count    变更次数,gold = len(chain)-1;
  (c) count_before    某日期(两链日期的中点,严格居间无歧义)之前有过多少
      个不同取值;
  (d) first_vs_last   最初取值 + 最新取值。

S7(--s7):每条目 2 道闭集标签卷积演示题(类目题 + 子标签题),gold=null,
改以 judge_rubric 字段约束评审(只能引用会话中确实出现的条目并带日期)。

S6(--s6):跨槽位 join 题,只对双链条目(render_wikistate_multi 产物,
含 chain2)生成:对主链每个转移日期 T(跳过首步)发问
  "(Today is <末链日期>.) When I <转移短语,如 started at V>, <副槽位问
  法> at that time?",gold = 副链上 [start_j, start_{j+1}) 区间覆盖 T 的
取值(代码机械推导);T 早于副链首个 start、或恰落在副链任一边界上
(新旧值同日皆可辩)则该题跳过;对称方向(副链锚定、主链取值)同规则。
噪声干扰筛对两个槽位家族都生效(两链宣告句均豁免),任一命中整条目
跳过。qid = uid_s6a{i}(主锚)/ uid_s6b{i}(副锚),i 为链内步序。

S6 隐式序数孪生题(s6_cross_slot_implicit):每道显式题额外配一道同
i 同 gold 的孪生 —— 问句不点名锚值,改用序数短语("my second
employer" / "my third residence";序数词 first..tenth,取转移新值在锚
链中的 1-based 位置;该值在锚链中重复出现则歧义跳过 —— 与显式 repeat
筛同条件;位置超出 tenth 仅跳孪生)。qid = uid_s6ia{i} / uid_s6ib{i},
basis 写明序数映射。跳题规则与显式完全一致(before-first-start /
boundary / repeat)。设计动机:显式题把锚值逐字写进问句,稠密检索凭
词面即可命中;序数锚不含 needle,必须对锚链做有序记账。

用法:
  python scripts/gen_wikistate_complex.py --data data/wikistate_full.json \
      [更多数据文件 ...] --out results/wsc_s5.jsonl [--uids ...] [--limit N]
  python scripts/gen_wikistate_complex.py --s7 --data data/stale_chain_full.json \
      --limit 10 --out results/wsc_s7.jsonl
  python scripts/gen_wikistate_complex.py --s6 \
      --data data/wikistate_full_multi_P108_P551.json --out results/wsc_s6.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import zlib
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple


# ── 日期解析(部分日期规约) ──────────────────────────────────
def parse_partial_date(raw: str) -> Tuple[date, Optional[str]]:
    """解析链日期,含 YYYY-00-00 / YYYY-MM-00 / YYYY-MM / YYYY 部分日期。

    00 月/日与缺失月/日一律规约为 1(年首/月首),规约动作以
    'raw→normalized' 记号返回,供写入 basis。完整日期返回 (date, None)。
    """
    parts = str(raw).strip().split("-")
    y = int(parts[0])
    mo = int(parts[1]) if len(parts) > 1 else 0
    d = int(parts[2]) if len(parts) > 2 else 0
    normalized = mo == 0 or d == 0 or len(parts) < 3
    mo = mo or 1
    d = d or 1
    out = date(y, mo, d)
    note = f"{raw}→{out.isoformat()}" if normalized else None
    return out, note


def _q_slot(slot: str) -> str:
    """槽位名转问句用名词(沿用既有 probing_queries 风格:
    'position held' 在问句中写作 'position')。"""
    return slot[:-5] if slot.endswith(" held") else slot


# ── 噪声干扰筛(dev 迭代 1)─────────────────────────────────────
# 计数/首末类问题的机械 gold 只在"世界内唯一可判"时才公平:若公告句之外的
# 噪声闲聊里出现与本槽位同族的转变语言(如噪声人格自己的 started my new
# job),这些题型对该条目不生成;点查/轨迹/最长任期不受此限。
_FAMILY_TERMS = {
    "position": r"\b(job|role|position|promot\w*|career)\b",
    "employer": r"\b(compan(y|ies)|employer|firm|startup|new job)\b",
    "team": r"\b(team|club|squad)\b",
    "residence": r"\b(moved|moving|relocat\w+|new (apartment|house|place|city))\b",
}
_TRANSITION_RE = re.compile(
    r"\b(start(ed|ing)?|join(ed|ing)?|promot(ed|ion)|became|becoming|"
    r"switch(ed|ing)?|left|quit|hired|new)\b", re.IGNORECASE)
CONTESTED = {"n": 0}


def _slot_family(slot: str) -> str:
    s = slot.lower()
    for fam in ("employer", "team", "residence"):
        if fam in s:
            return fam
    return "position"


def noise_interference(entry: dict) -> bool:
    spans = [str(step.get("state_span", ""))
             for step in entry.get("chain", [])]
    fam = _slot_family(str(entry.get("slot", "")))
    fam_re = re.compile(_FAMILY_TERMS[fam], re.IGNORECASE)
    for sess in entry.get("sessions", []):
        for turn in sess.get("turns", []):
            t = str(turn)
            if any(sp and sp[:60] in t for sp in spans):
                continue
            for sent in re.split(r"[.!?\n]", t):
                if fam_re.search(sent) and (fam == "residence"
                                            or _TRANSITION_RE.search(sent)):
                    return True
    return False


# ── S5:机械 gold 生成 ────────────────────────────────────────
def gen_s5(entry: dict) -> List[dict]:
    chain = entry.get("chain") or []
    if len(chain) < 3:
        return []
    uid = entry["uid"]
    slot = entry["slot"]
    qslot = _q_slot(slot)
    today = str(chain[-1]["date"])  # Today 前缀沿用原始日期串(含 -00-00)

    parsed: List[date] = []
    notes: List[str] = []
    for step in chain:
        dt, note = parse_partial_date(step["date"])
        parsed.append(dt)
        if note:
            notes.append(note)
    if any(b < a for a, b in zip(parsed, parsed[1:])):
        return []  # 链日期非单调,数据异常,整条目跳过
    date_basis = ("partial dates normalized to period start: "
                  + ", ".join(notes)) if notes else "all chain dates complete"
    values = [str(step["value"]) for step in chain]
    rows: List[dict] = []

    # dev 迭代 3:干扰筛前置覆盖全部 S5 题型 —— 噪声里的同族转变提及经
    # 会话日期回填后会伪造闭区间,连"最长任期"的机械 gold 也不再唯一。
    if noise_interference(entry):
        CONTESTED["n"] += 1
        return rows

    # (a) longest_tenure —— 仅闭区间;同值多段闭区间时长按值累加;并列最长
    # 则 gold 有歧义,跳过该题。
    closed = [(values[i], (parsed[i + 1] - parsed[i]).days)
              for i in range(len(chain) - 1)]
    if len(closed) >= 2:
        per_value: dict = {}
        for v, days in closed:
            per_value[v] = per_value.get(v, 0) + days
        best = max(per_value.values())
        winners = [v for v, d in per_value.items() if d == best]
        if len(winners) == 1:
            rows.append({
                "uid": uid, "qid": f"{uid}_s5a", "qtype": "longest_tenure",
                "slot": slot,
                "question": f"(Today is {today}.) Which {qslot} did I hold "
                            "the longest?",
                "gold": winners[0],
                "basis": ("CLOSED intervals only: tenure_i = start_(i+1) - "
                          "start_i; the last tenure is open and, as of Today "
                          "= the last chain date, has length 0, so it cannot "
                          "exceed any closed interval. Closed days per value: "
                          + json.dumps(per_value, ensure_ascii=False)
                          + "; " + date_basis),
            })

    # (b) change_count —— 每次链转移记一次变更。
    rows.append({
        "uid": uid, "qid": f"{uid}_s5b", "qtype": "change_count",
        "slot": slot,
        "question": f"(Today is {today}.) How many times did I change my "
                    f"{qslot}?",
        "gold": len(chain) - 1,
        "basis": f"one change per chain transition: gold = len(chain)-1 = "
                 f"{len(chain) - 1}",
    })

    # (c) count_before —— 取最居中且间隔 >=2 天的转移,问日期为两链日期的
    # 严格中点(不与任何链日期重合,故无歧义);此前不同取值数由代码计出。
    n_tr = len(chain) - 1
    order = sorted(range(n_tr), key=lambda i: (abs(i - (n_tr - 1) / 2), i))
    for i in order:
        gap = (parsed[i + 1] - parsed[i]).days
        if gap < 2:
            continue
        mid = parsed[i] + timedelta(days=gap // 2)
        if not (parsed[i] < mid < parsed[i + 1]):
            continue
        gold_c = len(set(values[:i + 1]))
        rows.append({
            "uid": uid, "qid": f"{uid}_s5c", "qtype": "count_before",
            "slot": slot,
            "question": f"How many different {qslot} values did I have "
                        f"before {mid.isoformat()}?",
            "gold": gold_c,
            "basis": (f"date = midpoint of chain[{i}].start "
                      f"({parsed[i].isoformat()}) and chain[{i + 1}].start "
                      f"({parsed[i + 1].isoformat()}), strictly between both; "
                      f"gold = distinct values among steps 0..{i} (each began "
                      f"strictly before that date) = {gold_c}; " + date_basis),
        })
        break

    # (d) first_vs_last —— 首末取值直读。
    rows.append({
        "uid": uid, "qid": f"{uid}_s5d", "qtype": "first_vs_last",
        "slot": slot,
        "question": f"(Today is {today}.) What was my first {qslot}, and "
                    "what is my most recent one?",
        "gold": f"first: {values[0]}; most recent: {values[-1]}",
        "basis": "gold = chain[0].value + chain[-1].value",
    })
    return rows


# ── S6:跨槽位 join(双链条目,机械 gold) ────────────────────
_S6_PHRASE = {"position": "became {v}", "employer": "started at {v}",
              "team": "joined {v}", "residence": "moved to {v}"}

# 隐式序数孪生题的序数词(1-based;超出 tenth 的位置仅跳孪生,不影响显式题)
_ORDINALS = ("first", "second", "third", "fourth", "fifth",
             "sixth", "seventh", "eighth", "ninth", "tenth")


def _s6_ask(slot: str) -> str:
    if _slot_family(slot) == "residence":
        return "where was I living"
    return f"what was my {_q_slot(slot)}"


def gen_s6(entry: dict) -> List[dict]:
    c2 = entry.get("chain2") or {}
    chain_a = entry.get("chain") or []
    chain_b = c2.get("chain") or []
    slot_a = str(entry.get("slot", ""))
    slot_b = str(c2.get("slot", ""))
    if not chain_a or not chain_b or not slot_a or not slot_b:
        return []
    uid = entry["uid"]

    # 双家族干扰筛(S6 版):跨槽位 join 的 gold 只有在两个家族的世界内
    # 状态都唯一可判时才公平 —— 两链宣告句(state_span)均豁免,两个槽位
    # 家族任一在噪声里命中转变语言,整条目跳过。
    probe_chain = list(chain_a) + list(chain_b)
    for fam_slot in (slot_a, slot_b):
        if noise_interference({"slot": fam_slot, "chain": probe_chain,
                               "sessions": entry.get("sessions", [])}):
            CONTESTED["n"] += 1
            return []

    notes: List[str] = []

    def _parse_chain(chain):
        out = []
        for step in chain:
            dt, note = parse_partial_date(step["date"])
            out.append(dt)
            if note:
                notes.append(note)
        return out
    try:
        pa, pb = _parse_chain(chain_a), _parse_chain(chain_b)
    except Exception:  # noqa: BLE001 —— 日期不可解析,数据异常,整条目跳过
        return []
    if any(b <= a for a, b in zip(pa, pa[1:])) or \
            any(b <= a for a, b in zip(pb, pb[1:])):
        return []  # 链日期非严格递增,区间语义失效,整条目跳过
    date_basis = ("partial dates normalized to period start: "
                  + ", ".join(notes)) if notes else "all chain dates complete"
    today = (str(chain_a[-1]["date"]) if pa[-1] >= pb[-1]
             else str(chain_b[-1]["date"]))

    rows: List[dict] = []

    def _direction(tag: str, anc_chain, anc_parsed, anc_slot,
                   oth_chain, oth_parsed, oth_slot):
        anc_vals = [str(s["value"]) for s in anc_chain]
        oth_vals = [str(s["value"]) for s in oth_chain]
        phrase_t = _S6_PHRASE[_slot_family(anc_slot)]
        for i in range(1, len(anc_chain)):   # 首步是初态,不是转移
            T, v = anc_parsed[i], anc_vals[i]
            if anc_vals.count(v) > 1:
                continue  # 锚值在链内重复出现,"When I ..." 指代歧义
            if T < oth_parsed[0]:
                continue  # T 早于副链首个已知状态,无区间可判
            if any(T == s for s in oth_parsed):
                continue  # T 恰在副链边界:新旧值同日皆可辩,歧义
            j = max(k for k, s in enumerate(oth_parsed) if s < T)
            hi = (oth_parsed[j + 1].isoformat()
                  if j + 1 < len(oth_parsed) else "open")
            rows.append({
                "uid": uid, "qid": f"{uid}_s6{tag}{i}",
                "qtype": "s6_cross_slot",
                "slot": oth_slot, "anchor_slot": anc_slot,
                "question": (f"(Today is {today}.) When I "
                             f"{phrase_t.format(v=v)}, {_s6_ask(oth_slot)} "
                             f"at that time?"),
                "gold": oth_vals[j],
                "basis": (f"T = {anc_slot} transition to {v} at "
                          f"{T.isoformat()} ({anc_slot} chain[{i}].start); "
                          f"{oth_slot} interval [{oth_parsed[j].isoformat()}, "
                          f"{hi}) covers T -> gold = {oth_vals[j]}; T before "
                          f"the first {oth_slot} start or exactly on a "
                          f"{oth_slot} boundary is skipped as ambiguous; "
                          + date_basis),
            })
            # 隐式序数孪生:同 i 同 gold/区间逻辑,问句不点名锚值,改用
            # 序数短语("my second employer")—— 问句中无逐字 needle,
            # 必须对锚链做有序记账。锚值唯一(repeat 筛已过),其链内
            # 1-based 位置即 i+1;位置超出 tenth 仅跳孪生。
            p = i + 1
            if p <= len(_ORDINALS):
                word = _ORDINALS[p - 1]
                noun = _q_slot(anc_slot)
                rows.append({
                    "uid": uid, "qid": f"{uid}_s6i{tag}{i}",
                    "qtype": "s6_cross_slot_implicit",
                    "slot": oth_slot, "anchor_slot": anc_slot,
                    "anchor_ordinal": p,
                    "question": (f"(Today is {today}.) When I "
                                 f"{phrase_t.format(v=f'my {word} {noun}')}, "
                                 f"{_s6_ask(oth_slot)} at that time?"),
                    "gold": oth_vals[j],
                    "basis": (f"ordinal mapping: 'my {word} {noun}' = "
                              f"{anc_slot} chain position {p} (1-based) = "
                              f"{v} (value unique in chain); T = {anc_slot} "
                              f"transition to {v} at {T.isoformat()} "
                              f"({anc_slot} chain[{i}].start); {oth_slot} "
                              f"interval [{oth_parsed[j].isoformat()}, {hi}) "
                              f"covers T -> gold = {oth_vals[j]}; skips "
                              f"identical to explicit s6 (before-first-start"
                              f" / boundary / repeat); " + date_basis),
                })

    _direction("a", chain_a, pa, slot_a, chain_b, pb, slot_b)
    _direction("b", chain_b, pb, slot_b, chain_a, pa, slot_a)
    return rows


# ── S7:闭集标签卷积演示题(judge 评,非机械 gold) ─────────────
CLOSED_TAGS = ["饮食", "健康运动", "消费购物", "出行旅行", "居家生活",
               "工作学习", "社交关系", "娱乐爱好", "财务", "宠物"]

_TAG_AREA = {
    "饮食": ("diet/food", "my eating"),
    "健康运动": ("health & exercise", "my health or exercise habits"),
    "消费购物": ("spending & shopping", "my spending or shopping habits"),
    "出行旅行": ("transport & travel", "how I get around or travel"),
    "居家生活": ("home & household", "my home life"),
    "工作学习": ("work & study", "my work or studies"),
    "社交关系": ("social relationships", "my relationships"),
    "娱乐爱好": ("entertainment & hobbies", "my hobbies or entertainment"),
    "财务": ("finances", "my finances"),
    "宠物": ("pets", "my pets"),
}

SUB_TAGS = [("高糖", "high-sugar"), ("高油", "high-fat/oily"),
            ("素食", "vegetarian"), ("咖啡因", "caffeine")]

S7_RUBRIC = ("answer must cite only items actually present in sessions, "
             "with dates")


def gen_s7(entry: dict) -> List[dict]:
    uid = entry["uid"]
    h = zlib.crc32(uid.encode("utf-8"))  # 按 uid 确定性选标签,子集稳定
    tag = CLOSED_TAGS[h % len(CLOSED_TAGS)]
    gloss, area = _TAG_AREA[tag]
    sub, sub_gloss = SUB_TAGS[h % len(SUB_TAGS)]
    return [
        {
            "uid": uid, "qid": f"{uid}_s7a", "qtype": "s7_category",
            "tag": tag,
            "question": (f"Looking across everything I've told you, what "
                         f"have I mentioned in the {tag} ({gloss}) category, "
                         f"and has anything about {area} changed over time?"),
            "gold": None,
            "judge_rubric": S7_RUBRIC,
        },
        {
            "uid": uid, "qid": f"{uid}_s7b", "qtype": "s7_subtag",
            "tag": sub,
            "question": (f"Have I mentioned anything {sub} ({sub_gloss})? "
                         "List what and when."),
            "gold": None,
            "judge_rubric": S7_RUBRIC,
        },
    ]


# ── CLI ──────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", nargs="+", required=True,
                    help="一个或多个 wikistate/chain 架构数据 json")
    ap.add_argument("--out", required=True, help="输出 jsonl 路径")
    ap.add_argument("--uids", nargs="*", default=None,
                    help="仅生成这些 uid(默认全量)")
    ap.add_argument("--limit", type=int, default=0,
                    help="仅取(合并去重后的)前 N 个条目;0 = 不限")
    ap.add_argument("--s7", action="store_true",
                    help="生成 S7 演示题(judge 评)而非 S5 机械 gold 题")
    ap.add_argument("--s6", action="store_true",
                    help="生成 S6 跨槽位 join 题(需 render_wikistate_multi "
                         "产物的 chain2 双链条目)")
    args = ap.parse_args()
    if args.s6 and args.s7:
        ap.error("--s6 与 --s7 互斥")

    entries, seen = [], set()
    for f in args.data:
        for e in json.loads(Path(f).read_text(encoding="utf-8")):
            if e["uid"] not in seen:
                seen.add(e["uid"])
                entries.append(e)
    if args.uids:
        keep = set(args.uids)
        entries = [e for e in entries if e["uid"] in keep]
    if args.limit:
        entries = entries[:args.limit]

    gen = gen_s6 if args.s6 else (gen_s7 if args.s7 else gen_s5)
    rows, skipped = [], 0
    for e in entries:
        r = gen(e)
        if not r:
            skipped += 1
        rows.extend(r)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_type: dict = {}
    for row in rows:
        by_type[row["qtype"]] = by_type.get(row["qtype"], 0) + 1
    print(f"entries={len(entries)} skipped={skipped} "
          f"contested_bcd={CONTESTED['n']} questions={len(rows)} "
          f"by_type={json.dumps(by_type, ensure_ascii=False)} -> {out}")


if __name__ == "__main__":
    main()
