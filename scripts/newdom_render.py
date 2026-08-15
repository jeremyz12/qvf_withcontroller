# -*- coding: utf-8 -*-
"""新域建材·步骤2:链 JSON → 记忆化渲染(零 LLM,多会话第一人称对话)。

输入:scripts/newdom_scrape.py --fetch 产物(data/newdom_{PROP}.json,
布局与旧域候选件同构:人级 {qid,label,sitelinks,chain},链步
{position,start,end},值为裸 QID)。

输出:与 data/wikistate_full*.json 逐字同构的条目数组:
  uid/type/slot/chain/sessions/probing_queries/attribution
  - uid             = wiki{PROP}{i:03d}-{qid}(沿旧域命名族);
  - type            = WIKISTATE;slot = 属性槽位名(P69 → school,
                      七类闭集之外,预期 slot_class 落 other:* ——
                      这正是测试目的,不为它加任何别名);
  - chain           = [{value,date,state_span}](事实真实:值与日期来自
                      Wikidata 限定符;state_span 逐字含值);
  - sessions        = 宣告会话(chain_index=k)+ STALE 噪声会话
                      (chain_index=None)按日期归并排序;
  - probing_queries = {}(占位空表 —— 题面由下一阶段独立盲写员生成,
                      不看 COMPILE_PROMPT;见审计 §三。注意:S6 首测
                      教训 —— 空表喂建卡阶段会零实例零建库,建卡前
                      必须先由盲写阶段回填);
  - attribution     同旧域措辞。

渲染方式(与旧域的口径差异全部记录于 meta):
  - 宣告句 = 确定性模板(承 render_wikistate_multi 的"模板优先"路线;
    值逐字嵌入,锚点由构造保证 + 断言兜底):
      school: "I officially enrolled at {title} today."
    措辞避开旧四族触发词(start/join/move 等)与教育家族筛的误杀面
    (宣告句本身在 noise_interference 类筛中按 span 前缀豁免)。
  - 闲聊 = 零 LLM 组合式模板池(载体合成:天气/家务/饮食/跑腿/小计划,
    槽位词表 × 句式,rng 抽 2-3 句);每句经禁语筛(旧四族 _BAN_RE 超集
    + 教育家族扩展词表)与链值提及筛双重校验,违者构造期即断言失败。
    (旧单属性线为 opus 整会话渲染、S6 线为 opus 闲聊;新域走零 LLM,
    省预算且完全可复现 —— 口径差异记录在案。)
  - STALE 噪声与旧线同款:rng.sample(stale,12) 每项取前 5 会话 × 前 5
    轮、截 400 字符,洗牌取 --noise-per-entry(默认 30)条,日期均匀铺
    在链年份范围;不做家族筛(旧域渲染亦不筛,同口径 —— 筛选属下游
    出题阶段);教育家族命中数作为遥测计数入 meta,供下游筛用。

家族词表扩展(记录在案,供下游 noise_interference 扩展用,本阶段仅
遥测与闲聊自筛,不改任何冻结文件):
  school 家族词 = EDU_FAMILY_RE;instrument 家族词 = INSTRUMENT_FAMILY_RE
  (P1303 线扩展);转变动词沿用 gen_wikistate_complex 的 _TRANSITION_RE
  精神(本文件复制常量,不导入)。

同日并列(仅 instrument 槽位,ALLOW_SAME_DAY_NOUNS 门控;P69/P26 路径
行为与输出逐字不变):乐器域天然集值 —— 一条乐队成员陈述常以同一
P580 列多件乐器(newdom_scrape_P1303.py 的 same_day_kept 计数;强制
唯一日期会把 52 人坍缩到 ~11 人且丢真实事实)。渲染侧把同日步骤并入
同一宣告会话:每值一条模板宣告句(各自 state_span 逐字在场),
chain_index = 该日首步序号,同日 >1 步时新增 chain_indices 键列全部
序号(既有代码均不读 chain_index,新键零风险;P69/P26 输出不含该键)。
非门控槽位同日步骤仍在 prep_chain 剔除(原行为)。

用法:
  python scripts/newdom_render.py --candidates data/newdom_P69.json \
      --out data/newdom_P69_full.json [--limit N] [--noise-per-entry 30]
  python scripts/newdom_render.py --smoke   # 零网络自检
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 与既有线一致的常量 ───────────────────────────────────────
UA = {"User-Agent": "QVF-research/0.1 (academic; zenglin0813@gmail.com)"}
API = "https://www.wikidata.org/w/api.php"
STALE_FILE = ROOT / "data" / "stale_T1_T2_400_FULL.json"
MIN_CHAIN_NEW = 2               # 同 newdom_scrape 口径
MAX_CHAIN = 8                   # 超长链截 8 段,同旧渲染线
SEED = 20260815                 # 新域渲染种子(旧线 20260807,记录在案)

NOUN = {"P69": "school", "P1303": "instrument", "P26": "spouse"}

# 确定性宣告模板(值逐字嵌入)。措辞避开旧四族触发词
# (render_wikistate_multi._BAN_RE / gen_wikistate_complex._FAMILY_TERMS)。
ANNOUNCE = {
    "school": "I officially enrolled at {title} today.",
    "instrument": "I officially took up the {title} today.",
    "spouse": "I officially married {title} today.",
}

# 旧四族禁语(与 render_wikistate_multi._BAN_RE 逐字同构,复制而非导入)
_BAN_RE_OLD = re.compile(
    r"\b(job|role|position|promot\w*|career|compan(y|ies)|employer|firm|"
    r"startup|team|club|squad|moved|moving|relocat\w+|"
    r"new (apartment|house|place|city|job)|hired|quit|elected|appointed|"
    r"start(ed|ing)? (as|at|work)|join(ed|ing)?)\b", re.IGNORECASE)

# 教育家族扩展词表(本次扩展内容;供下游 noise_interference 增设
# "school" 家族时复用,格式同 _FAMILY_TERMS 的值)。
EDU_FAMILY_PATTERN = (
    r"\b(school|universit(y|ies)|college|campus|degree|diploma|thesis|"
    r"semester|enrol\w*|graduat\w*|admitted|admission|matriculat\w*|"
    r"student|studies|studying|studied|freshman|sophomore|exam(s)?|"
    r"class(es)?|lecture(s)?|course(s|work)?|alma mater|dorm\w*|tuition)\b")
EDU_FAMILY_RE = re.compile(EDU_FAMILY_PATTERN, re.IGNORECASE)

# 转变动词(gen_wikistate_complex._TRANSITION_RE 逐字同构,复制而非导入)
_TRANSITION_RE = re.compile(
    r"\b(start(ed|ing)?|join(ed|ing)?|promot(ed|ion)|became|becoming|"
    r"switch(ed|ing)?|left|quit|hired|new)\b", re.IGNORECASE)

# 乐器家族扩展词表(P1303 线扩展内容;格式同 _FAMILY_TERMS 的值,供
# 下游 noise_interference 增设 "instrument" 家族时复用)。
INSTRUMENT_FAMILY_PATTERN = (
    r"\b(instrument(s)?|guitar(s)?|piano|violin|viola|cello|drum(s|mer)?|"
    r"drum kit|bass|flute|sax(ophone)?|trumpet|trombone|clarinet|oboe|"
    r"harp|banjo|mandolin|accordion|keyboard(s)?|organ|synth\w*|"
    r"percussion|vocal(s|ist)?|singing|sang|choir|band|orchestra|"
    r"ensemble|concert|gig(s)?|rehears\w*|recital|music\w*|melod\w*|"
    r"song(s)?|album(s)?|riff(s)?|chord(s)?)\b")
INSTRUMENT_FAMILY_RE = re.compile(INSTRUMENT_FAMILY_PATTERN, re.IGNORECASE)

# 配偶家族扩展词表(P26 线扩展内容;格式同 _FAMILY_TERMS 的值,供下游
# noise_interference 增设 "relationship" 家族时复用。注意 qvf_router.
# SLOT_ALIASES 已有 relationship 类 —— P26 是闭集内阳性对照,本表只管
# 渲染件噪声卫生,不动任何冻结文件)。
SPOUSE_FAMILY_PATTERN = (
    r"\b(marr(y|ies|ied|iage|ying)|wedding|wed(ded)?|wife|husband|"
    r"spouse|fianc\w*|engag(ed|ement)s?|divorc\w*|widow\w*|bride|groom|"
    r"honeymoon|anniversary|partner|boyfriend|girlfriend|dating|"
    r"in-laws?)\b")
SPOUSE_FAMILY_RE = re.compile(SPOUSE_FAMILY_PATTERN, re.IGNORECASE)

# 同日并列门控(集值域;见文件头)。
ALLOW_SAME_DAY_NOUNS = {"instrument"}

_UID_RE = re.compile(r"wikiP\d+\d{3}-Q\d+")


# ── 零 LLM 闲聊池(载体合成)────────────────────────────────
# 句式 × 槽位词表;全部句子构造期过双筛(旧四族 + 教育家族)。
_CHATTER_TEMPLATES = [
    "The {weather} this morning caught me off guard on my walk.",
    "I finally fixed the squeaky hinge on the kitchen cupboard.",
    "Remind me to pick up {grocery} when I'm out later.",
    "Dinner tonight will probably be {meal}.",
    "The plants on the windowsill need watering again.",
    "I spent a while sorting old letters into boxes this afternoon.",
    "My bicycle tyre is flat again; I'll pump it up before the weekend.",
    "The neighbour's cat keeps napping on our doorstep, funny thing.",
    "I mended the loose button on my coat while listening to the radio.",
    "Planning a slow evening: tea, a crossword, and an early night.",
    "The market had good {fruit} today, so I bought a small bag.",
    "I need to drop off a parcel at the post office before Friday.",
    "The kettle took ages to boil; might be time to descale it.",
    "Jotting down a reminder to call the plumber about the slow drain.",
    "It rained on and off all afternoon, so I stayed in and tidied drawers.",
    "I tried a different route on my morning walk and found a nice bakery.",
    "The radio kept cutting out during breakfast; the aerial needs adjusting.",
    "Made a big pot of vegetable stew; it should last a couple of days.",
    "I patched the garden hose and swept the back steps.",
    "Note to self: buy stamps and drop the letters in the postbox.",
]
_SLOT_WORDS = {
    "weather": ["drizzle", "fog", "wind chill", "heat", "frost"],
    "grocery": ["eggs and flour", "fresh bread", "coffee beans",
                "laundry detergent", "olive oil"],
    "meal": ["leftover soup", "a simple stir-fry", "baked potatoes",
             "pasta with whatever's in the fridge", "grilled vegetables"],
    "fruit": ["plums", "apricots", "pears", "cherries", "figs"],
}
_SLOT_RE = re.compile(r"\{(\w+)\}")


def synth_chatter(rng: random.Random, n: int) -> list:
    """rng 抽 n 句不重复句式,槽位随机填词。纯函数于 rng 状态。"""
    out = []
    for tpl in rng.sample(_CHATTER_TEMPLATES, n):
        def _fill(m):
            return rng.choice(_SLOT_WORDS[m.group(1)])
        out.append(_SLOT_RE.sub(_fill, tpl))
    return out


def chatter_errors(turns, banned_labels) -> list:
    """禁语双筛:旧四族 + 教育家族 + 链值提及。宁严勿漏。"""
    errs = []
    joined = " ".join(str(t) for t in turns)
    low = joined.lower()
    for lb in banned_labels:
        if lb and lb.lower() in low:
            errs.append(f"mentions chain value: {str(lb)[:30]}")
    m = _BAN_RE_OLD.search(joined)
    if m:
        errs.append(f"old-family banned term: {m.group(0)!r}")
    m = EDU_FAMILY_RE.search(joined)
    if m:
        errs.append(f"edu-family banned term: {m.group(0)!r}")
    m = INSTRUMENT_FAMILY_RE.search(joined)
    if m:
        errs.append(f"instrument-family banned term: {m.group(0)!r}")
    m = SPOUSE_FAMILY_RE.search(joined)
    if m:
        errs.append(f"spouse-family banned term: {m.group(0)!r}")
    return errs


# ── 标签解析(承 wikistate_build.resolve_labels)─────────────
def resolve_labels(qids):
    import requests  # 懒导入:--smoke / py_compile 不需要网络栈
    labels = {}
    qids = list(qids)
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        for attempt in range(4):   # 瞬时 429/错误体防线:entities 缺失即
            r = requests.get(API, params={   # 退避重试,不再静默空标签
                "action": "wbgetentities", "ids": "|".join(batch),
                "props": "labels", "languages": "en", "format": "json"},
                headers=UA, timeout=30)
            ents = r.json().get("entities")
            if ents:
                for qid, ent in ents.items():
                    labels[qid] = ent.get("labels", {}).get(
                        "en", {}).get("value", qid)
                break
            print(f"wbgetentities empty/error (attempt {attempt + 1}/4), "
                  f"backoff", flush=True)
            time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError(f"wbgetentities failed for batch {batch[:3]}…")
        time.sleep(0.2)
    return labels


# ── 链准备(防御性复检,承 render_wikistate_multi.prep_chain)──
_QID_RE = re.compile(r"Q\d+")


def prep_chain(steps, labels, allow_same_date=False):
    """allow_same_date(仅 instrument 集值域):同日不同标签保留,仅剔
    严格倒序;默认 False = 原行为逐字不变(同日并列剔除)。"""
    out, seen = [], set()
    for s in steps:
        if not str(s.get("start", ""))[:4].isdigit():
            continue
        lb = str(labels.get(s["position"], s["position"]))
        if _QID_RE.fullmatch(lb):
            continue
        if lb in seen:
            continue
        if out and str(s["start"]) <= str(out[-1]["start"]):
            if not (allow_same_date
                    and str(s["start"]) == str(out[-1]["start"])):
                continue
        seen.add(lb)
        out.append({"position": s["position"], "start": str(s["start"])[:10],
                    "end": s.get("end"), "label": lb})
    return out


# ── 单候选 → 条目(纯函数)──────────────────────────────────
def render_entry(cand, uid, noun, labels, rng, stale, noise_n=30,
                 telemetry=None):
    ca = prep_chain(cand["chain"], labels,
                    allow_same_date=noun in ALLOW_SAME_DAY_NOUNS)[:MAX_CHAIN]
    if len(ca) < MIN_CHAIN_NEW:
        return None
    banned = [c["label"] for c in ca]

    # 按日期分组(P69/P26 日期全唯一 → 全为单步组,rng 消耗与分组前
    # 逐字一致;instrument 同日多值 → 一组一宣告会话,每值一条 span)。
    groups = []
    for k, c in enumerate(ca):
        if groups and c["start"] == groups[-1][0][1]["start"]:
            groups[-1].append((k, c))
        else:
            groups.append([(k, c)])

    sessions, chain_out = [], []
    for group in groups:
        k0, c0 = group[0]
        spans = [ANNOUNCE[noun].format(title=c["label"]) for _, c in group]
        group_labels = {c["label"] for _, c in group}
        others = [b for b in banned if b not in group_labels]
        chatter = synth_chatter(rng, rng.choice([2, 3]))
        errs = chatter_errors(chatter, others)
        assert not errs, f"chatter pool violates screen: {errs}"
        turns = [chatter[0]] + spans + list(chatter[1:])
        sess = {"date": c0["start"], "turns": turns, "chain_index": k0}
        if len(group) > 1:
            sess["chain_indices"] = [k for k, _ in group]
        sessions.append(sess)
        for (k, c), span in zip(group, spans):
            # 与 wikistate_render.validate_state 同精神的锚点校验
            assert any(span in t for t in turns), "span not verbatim in turns"
            assert c["label"] in span, "title missing in span"
            chain_out.append({"value": c["label"], "date": c["start"],
                              "state_span": span})

    # STALE 噪声(同旧线:12 项×前5会话×前5轮,截400,洗牌,均匀铺年)
    pool = []
    for s_it in rng.sample(stale, min(12, len(stale))):
        for sess in (s_it.get("haystack_session") or [])[:5]:
            turns = sess if isinstance(sess, list) else [str(sess)]
            pool.append([str(t)[:400] for t in turns[:5]])
    rng.shuffle(pool)
    distractors = pool[:noise_n]
    y0 = int(ca[0]["start"][:4])
    y1 = max(y0 + 1, int(ca[-1]["start"][:4]))
    for j, turns in enumerate(distractors):
        y = y0 + (j % (y1 - y0 + 1))
        m = 1 + (j * 5) % 12
        d = 1 + (j * 7) % 27
        sessions.append({"date": f"{y}-{m:02d}-{d:02d}", "turns": turns,
                         "chain_index": None})
        if telemetry is not None:
            # 遥测:噪声会话家族语言命中(句级家族词+转变动词,同
            # noise_interference 精神;另计乐器家族裸提及 —— 集值域下
            # 无转变动词的乐器闲谈也可能干扰集合类 gold。不剔除,供
            # 下游盲写/筛选用)
            edu_hit, inst_hit, inst_mention = False, False, False
            sp_hit, sp_mention = False, False
            for t in turns:
                for sent in re.split(r"[.!?\n]", str(t)):
                    trans = _TRANSITION_RE.search(sent)
                    if not edu_hit and trans and EDU_FAMILY_RE.search(sent):
                        edu_hit = True
                    if INSTRUMENT_FAMILY_RE.search(sent):
                        inst_mention = True
                        if trans:
                            inst_hit = True
                    if SPOUSE_FAMILY_RE.search(sent):
                        # 配偶家族:裸提及也计("my husband cooked" 无转变
                        # 动词仍可干扰 current-spouse 类 gold)
                        sp_mention = True
                        if trans:
                            sp_hit = True
            telemetry["noise_sessions_total"] += 1
            if edu_hit:
                telemetry["noise_sessions_edu_transition_hit"] += 1
            if inst_hit:
                telemetry["noise_sessions_instrument_transition_hit"] += 1
            if inst_mention:
                telemetry["noise_sessions_instrument_mention"] += 1
            if sp_hit:
                telemetry["noise_sessions_spouse_transition_hit"] += 1
            if sp_mention:
                telemetry["noise_sessions_spouse_mention"] += 1
    sessions.sort(key=lambda s: s["date"])

    return {
        "uid": uid,
        "type": "WIKISTATE",
        "slot": noun,
        "chain": chain_out,
        "sessions": sessions,
        "probing_queries": {},   # 占位空表:题面由盲写阶段回填(见文件头)
        "attribution": (f"States derived from Wikidata {cand['qid']} "
                        f"{cand.get('_prop', 'P69')} qualifiers (CC0); "
                        f"distractor sessions remixed from STALE (CC BY 4.0)."),
    }


def new_telemetry() -> dict:
    return {"noise_sessions_total": 0,
            "noise_sessions_edu_transition_hit": 0,
            "noise_sessions_instrument_transition_hit": 0,
            "noise_sessions_instrument_mention": 0,
            "noise_sessions_spouse_transition_hit": 0,
            "noise_sessions_spouse_mention": 0}


# ── 主流程(仅标签解析走网络;零 LLM)────────────────────────
def run_render(candidates_path, out_path, prop, limit, noise_n):
    noun = NOUN[prop]
    cands = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    if limit:
        cands = cands[:limit]
    qids = {s["position"] for c in cands for s in c["chain"]}
    print(f"resolving {len(qids)} value labels...", flush=True)
    labels = resolve_labels(qids)
    stale = json.loads(STALE_FILE.read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    telemetry = new_telemetry()

    out, dropped = [], 0
    for i, cand in enumerate(cands):
        uid = f"wiki{prop}{i:03d}-{cand['qid']}"
        cand = {**cand, "_prop": prop}
        entry = render_entry(cand, uid, noun, labels, rng, stale, noise_n,
                             telemetry)
        if entry is None:
            dropped += 1
            print(f"[{uid}] SKIP (chain < {MIN_CHAIN_NEW} after label "
                  f"cleaning)", flush=True)
            continue
        out.append(entry)
        print(f"[{len(out)}] {uid} {cand.get('label', '')}: "
              f"{len(entry['chain'])} states, {len(entry['sessions'])} "
              f"sessions", flush=True)
    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")

    # meta:统计 + 口径差异记录
    from collections import Counter
    depth = Counter(len(e["chain"]) for e in out)
    n_sess = [len(e["sessions"]) for e in out]
    n_turns = [sum(len(s["turns"]) for s in e["sessions"]) for e in out]
    meta = {
        "prop": prop, "slot": noun,
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "command": " ".join(sys.argv), "seed": SEED,
        "renderer": "zero-LLM(模板宣告 + 组合式闲聊池 + STALE 噪声)",
        "entries": len(out), "dropped": dropped,
        "chain_depth_dist": {str(k): v for k, v in sorted(depth.items())},
        "sessions_total": sum(n_sess),
        "sessions_per_entry": (round(sum(n_sess) / len(out), 2) if out else 0),
        "turns_total": sum(n_turns),
        "noise_per_entry": noise_n,
        "noise_telemetry": telemetry,
        "announce_template": ANNOUNCE[noun],
        "edu_family_pattern_extension": EDU_FAMILY_PATTERN,
        "instrument_family_pattern_extension": INSTRUMENT_FAMILY_PATTERN,
        "spouse_family_pattern_extension": SPOUSE_FAMILY_PATTERN,
        "same_day_policy": (
            "same-day different-value steps grouped into one announcement "
            "session (one span per value; chain_indices lists step indices; "
            "set-valued domain, see newdom_scrape_P1303 meta)"
            if noun in ALLOW_SAME_DAY_NOUNS
            else "unique dates enforced (same-day steps dropped in "
                 "prep_chain, original behaviour)"),
        "caliber_diffs_vs_old_domain": [
            "闲聊为零 LLM 组合式模板池(旧单属性线 opus 整会话渲染、"
            "S6 线 opus 闲聊+确定性宣告;本线承后者但闲聊亦模板化)",
            "宣告句为单一确定性模板(旧单属性线宣告措辞由 opus 变化)",
            "MIN_CHAIN=2(旧线 3);链深≥2 优先为新域预注册口径",
            "probing_queries 为占位空表,题面由盲写阶段回填(旧线渲染期"
            "即生成四问)",
            f"渲染种子 {SEED}(旧线 20260807)",
            "STALE 噪声注入参数与旧线逐字一致(12 项×5 会话×5 轮×400 "
            "字符,30 条/条目,铺链年份范围);不做家族筛,教育家族命中"
            "仅遥测",
        ],
    }
    outp.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"RENDERED {len(out)}/{len(cands)} entries -> {outp}")
    print(f"sessions/entry={meta['sessions_per_entry']} "
          f"noise_telemetry={telemetry}")


# ── --smoke:零网络自检 ──────────────────────────────────────
FIX_LABELS = {"Q100": "Northfield Grammar", "Q102": "Eastvale Academy",
              "Q107": "Harbor Polytechnic", "Q301": "Q301"}
FIX_CAND = {
    "qid": "Q910001", "label": "Al Fixture", "sitelinks": 1,
    "chain": [
        {"position": "Q100", "start": "1991-09-01", "end": None},
        {"position": "Q301", "start": "1993-09-01", "end": None},  # 裸 QID
        {"position": "Q102", "start": "1995-09-01", "end": None},
        {"position": "Q107", "start": "2005-00-00", "end": None},  # 部分日期
    ],
}
FIX_CAND_DROP = {
    "qid": "Q910009", "label": "Drop Case", "sitelinks": 0,
    "chain": [
        {"position": "Q100", "start": "1991-09-01", "end": None},
        {"position": "Q301", "start": "1993-09-01", "end": None},
    ],
}
FIX_STALE = [
    {"haystack_session": [["The soup recipe turned out well yesterday.",
                           "I should write to my aunt this weekend."],
                          ["Rainy afternoon, staying in with a book."]]},
    {"haystack_session": [["Picked up groceries and fresh bread today."],
                          ["I just enrolled in a pottery class at the "
                           "community college, starting next week!"]]},
]


def run_smoke():
    # ① 闲聊池构造期全量自筛:每句(含全部槽位组合)过双筛。
    for tpl in _CHATTER_TEMPLATES:
        slots = _SLOT_RE.findall(tpl)
        if not slots:
            variants = [tpl]
        else:
            variants = []
            for w in _SLOT_WORDS[slots[0]]:
                variants.append(tpl.replace("{" + slots[0] + "}", w))
        for v in variants:
            errs = chatter_errors([v], [])
            assert not errs, f"chatter template dirty: {tpl!r} -> {errs}"
    # 禁语筛本身有效:旧族 / 教育族 / 链值提及均被抓。
    assert chatter_errors(["I started a new job today."], [])
    assert chatter_errors(["My thesis defense went well."], [])
    assert chatter_errors(["Lunch near Eastvale Academy."],
                          ["Eastvale Academy"])

    # ② 宣告模板均不触旧四族禁语(教育家族词天然在宣告里,属预期豁免面)。
    for noun, tpl in ANNOUNCE.items():
        span = tpl.format(title="Placeholder Name")
        assert not _BAN_RE_OLD.search(span), f"announce hits old ban: {noun}"

    # ③ 渲染器:条目 schema 与旧域全件逐字同构。
    rng = random.Random(7)
    telemetry = new_telemetry()
    e = render_entry({**FIX_CAND, "_prop": "P69"}, "wikiP69000-Q910001",
                     "school", FIX_LABELS, rng, FIX_STALE, noise_n=4,
                     telemetry=telemetry)
    assert e is not None
    assert list(e.keys()) == ["uid", "type", "slot", "chain", "sessions",
                              "probing_queries", "attribution"]
    assert _UID_RE.fullmatch(e["uid"])
    assert e["type"] == "WIKISTATE" and e["slot"] == "school"
    assert [list(s.keys()) for s in e["chain"]] == \
        [["value", "date", "state_span"]] * 3
    assert [s["value"] for s in e["chain"]] == \
        ["Northfield Grammar", "Eastvale Academy", "Harbor Polytechnic"]
    assert e["chain"][2]["date"] == "2005-00-00", "部分日期原样保留"
    assert e["probing_queries"] == {}, "占位空表"
    assert "Q910001" in e["attribution"] and "P69" in e["attribution"]
    dates = [s["date"] for s in e["sessions"]]
    assert dates == sorted(dates), "sessions not date-sorted"
    ann = [s for s in e["sessions"] if s.get("chain_index") is not None]
    noise = [s for s in e["sessions"] if s.get("chain_index") is None]
    assert len(ann) == 3 and len(noise) == 4
    assert [s["chain_index"] for s in sorted(ann, key=lambda x: x["date"])] \
        == [0, 1, 2]
    for step, s in zip(e["chain"], sorted(ann, key=lambda x: x["date"])):
        assert step["state_span"] in s["turns"], "span not a turn"
        assert step["value"] in step["state_span"], "value not in span"
        assert s["turns"].index(step["state_span"]) == 1, "span at turn[1]"
        assert 3 <= len(s["turns"]) <= 4, "3-4 turns per announce session"
        others = [t for t in s["turns"] if t != step["state_span"]]
        assert not chatter_errors(others, [b["value"] for b in e["chain"]
                                           if b["value"] != step["value"]])
    y_ok = {int(d[:4]) for d in (s["date"] for s in noise)}
    assert y_ok <= set(range(1991, 2006)), f"noise years out of range: {y_ok}"
    # 遥测:FIX_STALE 有一条教育家族+转变动词句("enrolled ... starting")
    assert telemetry["noise_sessions_total"] == 4
    assert telemetry["noise_sessions_edu_transition_hit"] >= 1, telemetry

    # ④ 淘汰件:标签清洗后 1 < MIN_CHAIN_NEW → None。
    assert render_entry({**FIX_CAND_DROP, "_prop": "P69"},
                        "wikiP69001-Q910009", "school", FIX_LABELS,
                        random.Random(7), FIX_STALE, 4) is None

    # ⑤ 与旧域全件的 schema 逐字对齐(存在才查,离线安全)。
    ref = ROOT / "data" / "wikistate_full_P108.json"
    if ref.exists():
        r0 = json.loads(ref.read_text(encoding="utf-8"))[0]
        assert list(r0.keys()) == list(e.keys()), "entry keys drifted"
        assert list(r0["chain"][0].keys()) == ["value", "date", "state_span"]
        assert set(r0["sessions"][0].keys()) == {"date", "turns",
                                                 "chain_index"}
        assert set(e["sessions"][0].keys()) == {"date", "turns",
                                                "chain_index"}

    # ⑥ 确定性:同种子两次渲染逐字节一致。
    e2 = render_entry({**FIX_CAND, "_prop": "P69"}, "wikiP69000-Q910001",
                      "school", FIX_LABELS, random.Random(7), FIX_STALE, 4,
                      new_telemetry())
    assert json.dumps(e, sort_keys=True) == json.dumps(e2, sort_keys=True), \
        "renderer not deterministic"

    # ⑦ P1303 同日并列(集值域门控):分组宣告会话 + chain_indices;
    #    非门控槽位(school)同日并列仍剔除 → 原行为不变。
    fix_labels_1303 = {"Q6607": "guitar", "Q1339": "keyboard",
                       "Q8338": "bass guitar"}
    fix_cand_1303 = {
        "qid": "Q920001", "label": "Cass Sameday", "sitelinks": 0,
        "_prop": "P1303",
        "chain": [
            {"position": "Q6607", "start": "1990-03-01", "end": None},
            {"position": "Q1339", "start": "2001-09-01", "end": None},
            {"position": "Q8338", "start": "2001-09-01", "end": None},
        ],
    }
    t3 = new_telemetry()
    e3 = render_entry(fix_cand_1303, "wikiP1303007-Q920001", "instrument",
                      fix_labels_1303, random.Random(11), FIX_STALE, 4, t3)
    assert e3 is not None and _UID_RE.fullmatch(e3["uid"])
    assert e3["slot"] == "instrument" and "P1303" in e3["attribution"]
    assert [s["value"] for s in e3["chain"]] == \
        ["guitar", "keyboard", "bass guitar"]
    assert [s["date"] for s in e3["chain"]] == \
        ["1990-03-01", "2001-09-01", "2001-09-01"], "same-day steps kept"
    ann3 = sorted((s for s in e3["sessions"]
                   if s.get("chain_index") is not None),
                  key=lambda s: s["date"])
    assert len(ann3) == 2, "same-day pair must share one session"
    assert ann3[0]["chain_index"] == 0 and "chain_indices" not in ann3[0]
    assert ann3[1]["chain_index"] == 1 and ann3[1]["chain_indices"] == [1, 2]
    assert "I officially took up the keyboard today." in ann3[1]["turns"]
    assert "I officially took up the bass guitar today." in ann3[1]["turns"]
    assert e3["chain"][1]["state_span"] in ann3[1]["turns"]
    assert e3["chain"][2]["state_span"] in ann3[1]["turns"]
    assert ann3[1]["turns"].index(e3["chain"][1]["state_span"]) == 1, \
        "spans start at turn[1]"
    # 同种子确定性(P1303 路径)。
    e3b = render_entry(fix_cand_1303, "wikiP1303007-Q920001", "instrument",
                       fix_labels_1303, random.Random(11), FIX_STALE, 4,
                       new_telemetry())
    assert json.dumps(e3, sort_keys=True) == json.dumps(e3b, sort_keys=True)
    # 非门控槽位:同日并列剔除后 1 < MIN_CHAIN_NEW → None(原行为)。
    same_day_p69 = {"qid": "Q920002", "label": "Nope", "sitelinks": 0,
                    "_prop": "P69",
                    "chain": [
                        {"position": "Q100", "start": "1990-01-01",
                         "end": None},
                        {"position": "Q102", "start": "1990-01-01",
                         "end": None}]}
    assert render_entry(same_day_p69, "wikiP69002-Q920002", "school",
                        FIX_LABELS, random.Random(11), FIX_STALE, 4,
                        new_telemetry()) is None
    # 乐器家族闲聊筛 + 遥测正则:
    assert chatter_errors(["I picked up the guitar again."], []), \
        "instrument family not caught in chatter screen"
    assert INSTRUMENT_FAMILY_RE.search("new drummer joined the band")

    # ⑧ 配偶家族(P26 线扩展):闲聊筛 + 遥测正则 + P26 渲染路径端到端
    #    (宣告句 "married" 属预期豁免面 —— 宣告不进闲聊筛)。
    assert chatter_errors(["We celebrated our wedding anniversary."], []), \
        "spouse family not caught in chatter screen"
    assert SPOUSE_FAMILY_RE.search("my husband cooked dinner")
    fix_labels_p26 = {"Q800011": "Miriam Voss", "Q800012": "Petra Lindqvist"}
    fix_cand_p26 = {"qid": "Q930001", "label": "Ada Casefold",
                    "sitelinks": 0, "_prop": "P26",
                    "chain": [
                        {"position": "Q800011", "start": "1980-05-10",
                         "end": "1994-01-01"},
                        {"position": "Q800012", "start": "1995-06-01",
                         "end": None}]}
    t4 = new_telemetry()
    e4 = render_entry(fix_cand_p26, "wikiP26000-Q930001", "spouse",
                      fix_labels_p26, random.Random(13), FIX_STALE, 4, t4)
    assert e4 is not None and e4["slot"] == "spouse"
    assert e4["uid"] == "wikiP26000-Q930001" and "P26" in e4["attribution"]
    assert [s["value"] for s in e4["chain"]] == \
        ["Miriam Voss", "Petra Lindqvist"]
    assert e4["chain"][0]["state_span"] == \
        "I officially married Miriam Voss today."
    ann4 = [s for s in e4["sessions"] if s.get("chain_index") is not None]
    assert len(ann4) == 2 and all("chain_indices" not in s for s in ann4)
    assert set(t4) == set(new_telemetry()), "spouse telemetry keys in place"
    e4b = render_entry(fix_cand_p26, "wikiP26000-Q930001", "spouse",
                       fix_labels_p26, random.Random(13), FIX_STALE, 4,
                       new_telemetry())
    assert json.dumps(e4, sort_keys=True) == json.dumps(e4b, sort_keys=True), \
        "P26 path not deterministic"

    print("SMOKE OK: chatter pool fully self-screened, announce templates "
          "clean, entry schema aligned with wikistate_full, telemetry "
          "counts edu-transition noise, deterministic under seed, P1303 "
          "same-day grouping (chain_indices) + non-gated drop verified")


# ── CLI ──────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", default=None,
                    help="newdom_scrape --fetch 产物 json")
    ap.add_argument("--out", default=None, help="输出 json 路径")
    ap.add_argument("--prop", default="P69",
                    help="属性(默认 P69;决定 slot 名与宣告模板)")
    ap.add_argument("--limit", type=int, default=0,
                    help="仅渲染前 N 个候选(冒烟用);0 = 不限")
    ap.add_argument("--noise-per-entry", type=int, default=30,
                    help="每条目 STALE 噪声会话数(默认 30,同旧线)")
    ap.add_argument("--smoke", action="store_true",
                    help="零网络自检")
    args = ap.parse_args()

    if args.smoke:
        run_smoke()
        return
    if not args.candidates or not args.out:
        ap.error("--candidates 与 --out 为渲染模式必填(或用 --smoke)")
    if args.prop not in NOUN:
        ap.error(f"--prop 取值限 {sorted(NOUN)}")
    run_render(args.candidates, args.out, args.prop, args.limit,
               args.noise_per_entry)


if __name__ == "__main__":
    main()
