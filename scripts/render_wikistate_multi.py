# -*- coding: utf-8 -*-
"""WikiState S6 跨槽位 join·步骤2:双链候选 → 记忆化渲染(chain 架构 + chain2)。

输入:scrape_wikistate_multi --fetch 产物(如 data/wikistate_multi_candidates_
P108_P551.json,候选记录 {uid wikiM###-Q…, props [PA,PB],
chains {P: [{position,start,end}]}},值为裸 QID)。

输出:与 data/wikistate_full*.json 同构的条目数组,全管线(eval.
stale_chain_dataset / complex_query_arm / wsc_direct_arm / gen_wikistate_
complex)直接可读,新增 chain2 字段:
  uid/type/slot/chain/chain2/sessions/probing_queries/attribution
  - uid               沿用候选 uid(wikiM###-Q…);type = WIKISTATE_MULTI;
  - slot / chain      = 主属性(props[0])槽位名与状态链(原布局
                        {value,date,state_span});
  - chain2            = {"slot": 副属性槽位名, "chain": [...同布局]};
  - sessions          = 两条链的宣告会话 + STALE 噪声会话按日期归并排序;
                        主链宣告 chain_index=k,副链宣告 chain_index=None
                        且 chain2_index=k,噪声 chain_index=None(既有
                        代码均不读 chain_index,新键零风险);
  - probing_queries   = {}(S6 题由 gen_wikistate_complex --s6 生成);
  - attribution       同原线措辞,属性对并列。

渲染方式承 wikistate_render.py,但宣告句改"确定性模板优先":
  state_span = 每槽位固定模板句(值逐字嵌入,锚点由构造保证),LLM
  (opus,messages.parse,同原线调用模式)只写宣告句周围 2-3 条闲聊
  (禁止提及任何职位/雇主/球队/居住等同族转变语言与两链任何取值;
  校验失败重试 3 次,仍失败回落罐头闲聊并记录)。闲聊禁语表与
  gen_wikistate_complex.noise_interference 的家族/转变正则同精神,
  保证渲染件不因自家闲聊被 S5/S6 干扰筛误杀。

标签解析承 wikistate_build.resolve_labels 同款(wbgetentities,同 UA);
链清洗:非日期 start 剔除(Wikidata unknown-value genid URL 会以
"http://www" 形式混进 start/end)、裸 QID 标签剔除、标签去重保首见、
start 严格递增,清洗后两链均
>= MIN_CHAIN(=3,与 scrape 线一致)才保留条目。原线的参数可答(LEAK)
过滤不在此步(候选已按 sitelinks<=5 低知名度筛过,是主要缓解)。

STALE 噪声混入与 wikistate_render 同款:rng.sample(stale,12) 每项取前 5
会话 × 前 5 轮、截 400 字符,洗牌取 --noise-per-entry(默认 30)条,
日期均匀铺在两链年份并集范围。

用法:
  python scripts/render_wikistate_multi.py \
      --candidates data/wikistate_multi_candidates_P108_P551.json \
      --out data/wikistate_full_multi_P108_P551.json \
      [--limit N] [--noise-per-entry 30]
  python scripts/render_wikistate_multi.py --smoke   # 零网络零 API 自检
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 与既有线一致的常量 ───────────────────────────────────────
UA = {"User-Agent": "QVF-research/0.1 (academic; zenglin0813@gmail.com)"}
API = "https://www.wikidata.org/w/api.php"
# S8 补齐 (2026-08-17): 闲聊只是禁语筛过的平庸日常填充,不需要 opus 的
# 生成质量;改用 haiku-4-5(同 build_tag_lattice.py 的记账口径)把这条
# 渲染线的边际成本压到可忽略,为"多渲染候选换更多干净跨槽位世界"腾预算。
# 不再断言与 wikistate_render.MODEL 一致(该脚本仍用 opus,互不影响)。
MODEL = os.environ.get("QVF_S8_RENDER_MODEL", "claude-haiku-4-5")
MIN_CHAIN = 3                    # 同 scrape 线口径
STALE_FILE = ROOT / "data" / "stale_T1_T2_400_FULL.json"
NOUN = {"P39": "position", "P54": "team", "P108": "employer",
        "P551": "residence"}

# 成本记账(list price,未计缓存折扣;仅用于跑批后如实报告实测,不影响
# 任何渲染/生成逻辑)。Haiku 4.5 公开单价(每百万 token,美元)。
_PRICE_HAIKU_IN = 1.00
_PRICE_HAIKU_OUT = 5.00
USAGE = {"chatter_in": 0, "chatter_out": 0, "chatter_calls": 0}


def usage_cost_usd() -> float:
    return (USAGE["chatter_in"] / 1e6 * _PRICE_HAIKU_IN
            + USAGE["chatter_out"] / 1e6 * _PRICE_HAIKU_OUT)

# 确定性宣告模板(state_span;值逐字嵌入)。措辞刻意避开其它槽位家族的
# 触发词(见 gen_wikistate_complex._FAMILY_TERMS),宣告句本身经 span
# 前缀匹配豁免,不会触发干扰筛。
ANNOUNCE = {
    "position": "I officially started as {title} today.",
    "employer": "I officially started working at {title} today.",
    "team": "I officially joined {title} today.",
    "residence": "I officially moved to {title} today.",
}

_QID_RE = re.compile(r"Q\d+")
_UID_RE = re.compile(r"wikiM\d{3}-Q\d+")

# 闲聊禁语:gen_wikistate_complex 的四族触发词 + 转变动词的并集(超集,
# 宁严勿漏 —— 闲聊被拒就重试/回落,不影响宣告句)。
_BAN_RE = re.compile(
    r"\b(job|role|position|promot\w*|career|compan(y|ies)|employer|firm|"
    r"startup|team|club|squad|moved|moving|relocat\w+|"
    r"new (apartment|house|place|city|job)|hired|quit|elected|appointed|"
    r"start(ed|ing)? (as|at|work)|join(ed|ing)?)\b", re.IGNORECASE)

FALLBACK_CHATTER = [
    "Quick check-in — I finally sorted through that stack of paperwork "
    "on my desk this morning.",
    "Also, remind me to water the plants and reply to two letters this "
    "evening.",
]

CHATTER_PROMPT = """You write filler chatter for a personal-assistant memory log.
The user is {name}. Write 2-3 short casual first-person messages (from the
user to their AI assistant) dated {date}. Only mundane everyday details
(weather, errands, meals, chores, small plans). STRICT BANS: do not mention
or hint at any job, role, career, employer, company, team, club, home,
moving, relocation, or any other life change — a separate sentence handles
that and it is not your job. Vary tone (style hint #{k}).
"""


# ── 标签解析(承 wikistate_build.resolve_labels,懒导入 requests)──
def resolve_labels(qids):
    import requests  # 懒导入:--smoke / py_compile 全程不需要网络栈
    labels = {}
    qids = list(qids)
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        r = requests.get(API, params={
            "action": "wbgetentities", "ids": "|".join(batch),
            "props": "labels", "languages": "en", "format": "json"},
            headers=UA, timeout=30)
        for qid, ent in r.json().get("entities", {}).items():
            labels[qid] = ent.get("labels", {}).get("en", {}).get("value", qid)
        time.sleep(0.2)
    return labels


# ── 链清洗:非日期 start 剔除、QID → 标签、去重保首见、start 严格递增 ──
def prep_chain(steps, labels):
    out, seen = [], set()
    for s in steps:
        if not str(s.get("start", ""))[:4].isdigit():
            continue                    # 非日期 start(Wikidata unknown-value
            #                             genid URL 等)剔除,防污染递增筛
        lb = str(labels.get(s["position"], s["position"]))
        if _QID_RE.fullmatch(lb):
            continue                    # 无英文标签(裸 QID)剔除
        if lb in seen:
            continue                    # 同标签去重保首见
        if out and str(s["start"]) <= str(out[-1]["start"]):
            continue                    # start 严格递增(同日并列剔除)
        seen.add(lb)
        out.append({"position": s["position"], "start": str(s["start"])[:10],
                    "end": s.get("end"), "label": lb})
    return out


# ── 闲聊校验 + 重试/回落 ─────────────────────────────────────
def chatter_errors(turns, banned_labels) -> list:
    errs = []
    if not (2 <= len(turns) <= 4):
        errs.append(f"need 2-4 turns, got {len(turns)}")
    joined = " ".join(str(t) for t in turns)
    low = joined.lower()
    for lb in banned_labels:
        if lb and lb.lower() in low:
            errs.append(f"mentions chain value: {lb[:30]}")
    m = _BAN_RE.search(joined)
    if m:
        errs.append(f"banned family/transition term: {m.group(0)!r}")
    return errs


def chatter_with_retry(propose, name, date, k, banned_labels):
    """propose(name,date,k) -> list[str]|None(一次 LLM 调用或桩件)。
    校验通过返回 (turns, False);3 次仍失败回落罐头 (fallback, True)。"""
    for attempt in range(3):
        turns = propose(name, date, k)
        if turns is None:
            continue
        errs = chatter_errors(turns, banned_labels)
        if not errs:
            return [str(t) for t in turns], False
        print(f"chatter attempt {attempt} rejected: {errs[:2]}", flush=True)
    print(f"chatter FALLBACK for {name} @ {date}", flush=True)
    return list(FALLBACK_CHATTER), True


def make_llm_propose(client):
    """真 LLM propose:opus messages.parse,同 wikistate_render 调用模式。"""
    from pydantic import BaseModel, Field

    class ChatterTurns(BaseModel):
        turns: list[str] = Field(
            description="2-3 casual mundane first-person messages from the "
            "user to their assistant; MUST NOT mention any job/employer/"
            "team/residence value or change.")

    def propose(name, date, k):
        try:
            resp = client.messages.parse(
                model=MODEL, max_tokens=800,
                messages=[{"role": "user", "content": CHATTER_PROMPT.format(
                    name=name, date=date, k=k)}],
                output_format=ChatterTurns,
            )
            try:
                USAGE["chatter_in"] += int(resp.usage.input_tokens)
                USAGE["chatter_out"] += int(resp.usage.output_tokens)
                USAGE["chatter_calls"] += 1
            except Exception:  # noqa: BLE001
                pass
            cand = resp.parsed_output
            return [str(t) for t in cand.turns] if cand else None
        except Exception as e:  # noqa: BLE001
            print(f"chatter LLM error: {type(e).__name__}", flush=True)
            return None
    return propose


# ── 单候选 → chain 架构条目(纯函数;propose 可注入桩件)────────
def render_entry(cand, labels, propose, rng, stale, noise_n=30):
    pa, pb = cand["props"]
    noun_a, noun_b = NOUN[pa], NOUN[pb]
    ca = prep_chain(cand["chains"][pa], labels)
    cb = prep_chain(cand["chains"][pb], labels)
    if len(ca) < MIN_CHAIN or len(cb) < MIN_CHAIN:
        return None
    banned = [c["label"] for c in ca + cb]
    name = cand.get("label", cand["qid"])

    sessions = []

    def build(chain, noun, secondary):
        rendered = []
        for k, c in enumerate(chain):
            span = ANNOUNCE[noun].format(title=c["label"])
            others = [b for b in banned if b != c["label"]]
            turns, _fb = chatter_with_retry(propose, name, c["start"], k,
                                            others)
            turns = [turns[0], span] + list(turns[1:])
            # 与 wikistate_render.validate_state 同精神的锚点校验
            # (模板构造保证,断言兜底)。
            assert any(span in t for t in turns), "span not verbatim in turns"
            assert c["label"] in span, "title missing in span"
            sess = {"date": c["start"], "turns": turns, "chain_index": None}
            if secondary:
                sess["chain2_index"] = k
            else:
                sess["chain_index"] = k
            sessions.append(sess)
            rendered.append({"value": c["label"], "date": c["start"],
                             "state_span": span})
        return rendered

    chain_a = build(ca, noun_a, secondary=False)
    chain_b = build(cb, noun_b, secondary=True)

    # STALE 噪声(同 wikistate_render:前5会话×前5轮,截400,洗牌)。
    # B2 fix (2026-08-17): 自家宣告句与 LLM 闲聊都已过禁语筛(_BAN_RE /
    # chatter_errors),但原逻辑对混入的真实 STALE 语料本身未筛——这是
    # dual-family 干扰筛低通过率的主因(wsc_s8.meta 记录的 4/13 清洁世界,
    # 复核后确认噪声泄漏几乎全部来自这里而非自家生成内容)。改为:候选池
    # 先用 _BAN_RE(取 content 字段判定,避免 B1 同款 role/content 结构键
    # 误伤)+ 两条链值字面剔除,洗牌来源顺序后逐项累积,直到候选量充分
    # 富余或源池耗尽,再洗牌截取 noise_n 条。
    def _distractor_text(turn) -> str:
        if isinstance(turn, dict):
            return str(turn.get("content", turn))
        return str(turn)

    pool = []
    stale_shuffled = list(stale)
    rng.shuffle(stale_shuffled)
    for s_it in stale_shuffled:
        for sess in (s_it.get("haystack_session") or [])[:5]:
            turns = (sess if isinstance(sess, list) else [str(sess)])[:5]
            content = " ".join(_distractor_text(t) for t in turns)
            if _BAN_RE.search(content):
                continue
            if any(lb and lb.lower() in content.lower() for lb in banned):
                continue
            pool.append([str(t)[:400] for t in turns])
        if len(pool) >= max(noise_n * 3, 60):
            break
    rng.shuffle(pool)
    distractors = pool[:noise_n]
    y0 = min(int(ca[0]["start"][:4]), int(cb[0]["start"][:4]))
    y1 = max(y0 + 1, int(ca[-1]["start"][:4]), int(cb[-1]["start"][:4]))
    for j, turns in enumerate(distractors):
        y = y0 + (j % (y1 - y0 + 1))
        m = 1 + (j * 5) % 12
        d = 1 + (j * 7) % 27
        sessions.append({"date": f"{y}-{m:02d}-{d:02d}", "turns": turns,
                         "chain_index": None})
    sessions.sort(key=lambda s: s["date"])

    return {
        "uid": cand["uid"],
        "type": "WIKISTATE_MULTI",
        "slot": noun_a,
        "chain": chain_a,
        "chain2": {"slot": noun_b, "chain": chain_b},
        "sessions": sessions,
        # 占位 dim1(机械 gold):写入侧按实例迭代,空 probing_queries 会导致
        # 建卡阶段零实例零建库(S6 首测实雷),故至少给一个真问题。
        "probing_queries": {"dim1_current": {
            "q": f"(Today is {chain_a[-1]['date']}.) What's my current "
                 f"{noun_a} these days?",
            "gold": str(chain_a[-1]["value"])}},
        "attribution": (f"States derived from Wikidata {cand['qid']} "
                        f"{pa}+{pb} qualifiers (CC0); distractor sessions "
                        f"remixed from STALE (CC BY 4.0)."),
    }


# ── 主流程(网络 + LLM;--smoke 不走这里)──────────────────────
def run_render(candidates_path, out_path, limit, noise_n):
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import anthropic

    cands = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    if limit:
        cands = cands[:limit]
    qids = {s["position"] for c in cands
            for p in c["props"] for s in c["chains"][p]}
    print(f"resolving {len(qids)} value labels...", flush=True)
    labels = resolve_labels(qids)
    stale = json.loads(STALE_FILE.read_text(encoding="utf-8"))
    propose = make_llm_propose(anthropic.Anthropic())
    rng = random.Random(20260807)

    out = []
    for cand in cands:
        entry = render_entry(cand, labels, propose, rng, stale, noise_n)
        if entry is None:
            print(f"[{cand['uid']}] SKIP (chain < {MIN_CHAIN} after label "
                  f"cleaning)", flush=True)
            continue
        out.append(entry)
        print(f"[{len(out)}] {cand['uid']} {cand.get('label', '')}: "
              f"{len(entry['chain'])}+{len(entry['chain2']['chain'])} states, "
              f"{len(entry['sessions'])} sessions", flush=True)
        time.sleep(0.3)
    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"RENDERED {len(out)}/{len(cands)} entries -> {outp}")
    print(f"USAGE model={MODEL} calls={USAGE['chatter_calls']} "
          f"in={USAGE['chatter_in']} out={USAGE['chatter_out']} "
          f"cost_usd={usage_cost_usd():.4f} (list price, no cache discount)")


# ── --smoke:零网络零 API 自检(渲染器 + S6 生成器)────────────
FIX_LABELS = {"Q1": "Acme Labs", "Q2": "Beta Corp", "Q3": "Gamma Institute",
              "Q60": "Oslo", "Q64": "Bergen", "Q84": "Tromso",
              "Q64b": "Bergen", "Q4": "Delta Group"}
FIX_CAND = {
    "uid": "wikiM000-Q900002", "qid": "Q900002", "label": "Bea Example",
    "sitelinks": 4, "props": ["P108", "P551"],
    "chains": {
        "P108": [
            {"position": "Q1", "start": "2001-01-01", "end": "2002-01-01"},
            {"position": "Q2", "start": "2002-01-01", "end": "2003-01-01"},
            # 非日期 start(unknown-value genid URL,真实抓取件同款):必须
            # 被剔除且不得污染递增筛(否则 'http…' > '2003…' 会连带丢掉
            # 后续真实步)—— 下方 chain 断言 3 步齐全即为证。
            {"position": "Q4", "start": "http://www", "end": None},
            {"position": "Q3", "start": "2003-01-01", "end": None},
        ],
        "P551": [
            {"position": "Q60", "start": "2000-06-01", "end": None},
            {"position": "Q64", "start": "2005-06-01", "end": None},
            {"position": "Q84", "start": "2010-06-01", "end": None},
        ],
    },
}
# 淘汰件:P551 一步无标签(裸 QID)+ 一步标签重复 → 清洗后 2 < MIN_CHAIN
FIX_CAND_DROP = {
    "uid": "wikiM001-Q900009", "qid": "Q900009", "label": "Drop Case",
    "sitelinks": 0, "props": ["P108", "P551"],
    "chains": {
        "P108": FIX_CAND["chains"]["P108"],
        "P551": [
            {"position": "Q60", "start": "2000-06-01", "end": None},
            {"position": "Q99", "start": "2005-06-01", "end": None},   # 无标签
            {"position": "Q64b", "start": "2007-06-01", "end": None},
            {"position": "Q64", "start": "2010-06-01", "end": None},   # 重复
        ],
    },
}
FIX_STALE = [
    {"haystack_session": [["The soup recipe turned out well yesterday.",
                           "I should write to my aunt this weekend."],
                          ["Rainy afternoon, staying in with a book."]]},
    {"haystack_session": [["Picked up groceries and fresh bread today."],
                          ["The garden needs weeding again."]]},
]


def _stub_propose(name, date, k):
    return ["Nice quiet morning here, just tidying up my notes.",
            "Planning a walk after lunch if the rain holds off."]


def run_smoke():
    sys.path.insert(0, str(ROOT))
    import scripts.gen_wikistate_complex as G

    # ① 闲聊校验:标签提及 / 家族转变语 / 轮数越界均拒,干净件通过。
    assert chatter_errors(["I visited Beta Corp downtown.", "ok day"],
                          ["Beta Corp"]), "label mention not caught"
    assert chatter_errors(["I started a new job today!", "x"], []), \
        "transition language not caught"
    assert chatter_errors(["only one turn"], []), "turn count not caught"
    assert not chatter_errors(list(FALLBACK_CHATTER), ["Beta Corp"]), \
        "fallback chatter must self-pass"
    assert not chatter_errors(_stub_propose("n", "d", 0), ["Beta Corp"])

    # ② 重试/回落:坏→好取好件不回落;三连坏回落罐头。
    seq = [["My company sent me to a new city."], _stub_propose("n", "d", 0)]
    turns, fb = chatter_with_retry(lambda *a: seq.pop(0), "n", "d", 0, [])
    assert turns == _stub_propose("n", "d", 0) and fb is False, "retry broken"
    turns, fb = chatter_with_retry(
        lambda *a: ["I got hired at a startup."], "n", "d", 0, [])
    assert fb is True and turns == FALLBACK_CHATTER, "fallback broken"

    # ③ 渲染器:双链候选 → 合法 chain+chain2 条目。
    rng = random.Random(7)
    e = render_entry(FIX_CAND, FIX_LABELS, _stub_propose, rng, FIX_STALE,
                     noise_n=4)
    assert e is not None
    assert list(e.keys()) == ["uid", "type", "slot", "chain", "chain2",
                              "sessions", "probing_queries", "attribution"]
    assert _UID_RE.fullmatch(e["uid"]) and e["uid"] == FIX_CAND["uid"]
    assert e["type"] == "WIKISTATE_MULTI"
    assert e["slot"] == "employer" and e["chain2"]["slot"] == "residence"
    assert [list(s.keys()) for s in e["chain"]] == \
        [["value", "date", "state_span"]] * 3
    assert [s["value"] for s in e["chain"]] == \
        ["Acme Labs", "Beta Corp", "Gamma Institute"]
    assert [s["value"] for s in e["chain2"]["chain"]] == \
        ["Oslo", "Bergen", "Tromso"]
    pq = e["probing_queries"]
    assert set(pq) == {"dim1_current"}, "应有且仅有占位 dim1(防零建卡)"
    assert pq["dim1_current"]["gold"] == str(e["chain"][-1]["value"])
    assert e["chain"][-1]["date"] in pq["dim1_current"]["q"]
    assert "Q900002" in e["attribution"] and "P108+P551" in e["attribution"]
    dates = [s["date"] for s in e["sessions"]]
    assert dates == sorted(dates), "sessions not date-sorted"
    ann_a = [s for s in e["sessions"] if s.get("chain_index") is not None]
    ann_b = [s for s in e["sessions"] if "chain2_index" in s]
    noise = [s for s in e["sessions"]
             if s.get("chain_index") is None and "chain2_index" not in s]
    assert len(ann_a) == 3 and len(ann_b) == 3 and len(noise) == 4
    for s in ann_b:
        assert s["chain_index"] is None, "secondary must keep chain_index=None"
    for chain, ann in ((e["chain"], ann_a), (e["chain2"]["chain"], ann_b)):
        for step in chain:
            sess = [s for s in ann if s["date"] == step["date"]]
            assert len(sess) == 1, f"announcement session missing {step}"
            assert step["state_span"] in sess[0]["turns"], "span not a turn"
            assert step["value"] in step["state_span"], "value not in span"
    y_ok = {int(d[:4]) for d in (s["date"] for s in noise)}
    assert y_ok <= set(range(2000, 2011)), f"noise years out of range: {y_ok}"

    # 淘汰件:副链清洗后 2 步 → 条目剔除。
    assert render_entry(FIX_CAND_DROP, FIX_LABELS, _stub_propose,
                        random.Random(7), FIX_STALE, 4) is None

    # ④ S6 生成器:手工双链 fixture → 手核 gold + 歧义跳过。
    def _ann_sess(chain_key):
        return [{"date": s["date"], "turns":
                 ["Morning note, nothing much planned.", s["state_span"]],
                 "chain_index": None} for s in chain_key]
    fx = {
        "uid": "wikiM100-Q800001", "type": "WIKISTATE_MULTI",
        "slot": "employer",
        "chain": [
            {"value": "Acme Labs", "date": "1999-01-01",
             "state_span": "I officially started working at Acme Labs today."},
            {"value": "Beta Corp", "date": "2000-01-01",
             "state_span": "I officially started working at Beta Corp today."},
            {"value": "Gamma Institute", "date": "2003-06-01", "state_span":
             "I officially started working at Gamma Institute today."},
            {"value": "Delta University", "date": "2010-01-01", "state_span":
             "I officially started working at Delta University today."},
        ],
        "chain2": {"slot": "residence", "chain": [
            {"value": "Oslo", "date": "2000-06-01",
             "state_span": "I officially moved to Oslo today."},
            {"value": "Bergen", "date": "2003-06-01",
             "state_span": "I officially moved to Bergen today."},
            {"value": "Tromso", "date": "2005-01-01",
             "state_span": "I officially moved to Tromso today."},
        ]},
        "probing_queries": {},
    }
    fx["sessions"] = (_ann_sess(fx["chain"]) + _ann_sess(fx["chain2"]["chain"])
                      + [{"date": "2004-04-04", "turns":
                          ["Lovely weather for a walk by the harbor."],
                          "chain_index": None}])
    rows = G.gen_s6(fx)
    # a 向:i=1 T=2000-01-01 早于副链首步(跳);i=2 T=2003-06-01 恰在副链
    # 边界(歧义,跳);i=3 T=2010-01-01 ∈ [2005-01-01, open) → Tromso。
    # b 向:i=1 T=2003-06-01 恰在主链边界(跳);i=2 T=2005-01-01 ∈
    # [2003-06-01, 2010-01-01) → Gamma Institute。
    assert [r["qid"] for r in rows] == \
        ["wikiM100-Q800001_s6a3", "wikiM100-Q800001_s6b2"], \
        f"qids: {[r['qid'] for r in rows]}"
    a3, b2 = rows
    assert a3["gold"] == "Tromso" and b2["gold"] == "Gamma Institute"
    assert a3["question"] == ("(Today is 2010-01-01.) When I started at "
                              "Delta University, where was I living at "
                              "that time?"), a3["question"]
    assert b2["question"] == ("(Today is 2010-01-01.) When I moved to "
                              "Tromso, what was my employer at that "
                              "time?"), b2["question"]
    assert a3["slot"] == "residence" and a3["anchor_slot"] == "employer"
    assert b2["slot"] == "employer" and b2["anchor_slot"] == "residence"
    assert "[2005-01-01, open)" in a3["basis"], a3["basis"]
    assert "[2003-06-01, 2010-01-01)" in b2["basis"], b2["basis"]
    assert all(r["qtype"] == "s6_cross_slot" for r in rows)

    # ⑤ 双家族干扰筛:任一家族的噪声转变语言 → 整条目零题。
    import copy
    bad_emp = copy.deepcopy(fx)
    bad_emp["sessions"].append({"date": "2006-01-01", "turns":
                                ["I started a new job last week, nervous!"],
                                "chain_index": None})
    assert G.gen_s6(bad_emp) == [], "employer-family noise not screened"
    bad_res = copy.deepcopy(fx)
    bad_res["sessions"].append({"date": "2006-01-01", "turns":
                                ["We are moving to a new apartment soon."],
                                "chain_index": None})
    assert G.gen_s6(bad_res) == [], "residence-family noise not screened"
    # 宣告句自身豁免:干净 fixture 未被筛(上面 rows 非空已证)。

    # ⑥ 单链条目(无 chain2)→ 零题;渲染件端到端可直接喂 S6。
    assert G.gen_s6({"uid": "x", "slot": "employer", "chain": fx["chain"],
                     "sessions": []}) == []
    e_rows = G.gen_s6(e)
    # 渲染 fixture:a 向 T=2002/2003-01-01 均 ∈ [2000-06-01, 2005-06-01)
    # → Oslo×2;b 向 T=2005/2010-06-01 均落 Gamma Institute 段(末段 open)。
    assert [r["qid"][-4:] for r in e_rows] == ["s6a1", "s6a2", "s6b1", "s6b2"]
    assert [r["gold"] for r in e_rows] == \
        ["Oslo", "Oslo", "Gamma Institute", "Gamma Institute"]

    print("SMOKE OK: chatter screen/retry/fallback + renderer schema "
          "(chain+chain2, sessions merged+sorted, noise mixed) + S6 golds "
          f"hand-checked (2 ambiguous skips) + e2e rows={len(e_rows)}")


# ── CLI ──────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", default=None,
                    help="scrape_wikistate_multi --fetch 产物 json")
    ap.add_argument("--out", default=None, help="输出 json 路径")
    ap.add_argument("--limit", type=int, default=0,
                    help="仅渲染前 N 个候选;0 = 不限")
    ap.add_argument("--noise-per-entry", type=int, default=30,
                    help="每条目 STALE 噪声会话数(默认 30,同原线)")
    ap.add_argument("--smoke", action="store_true",
                    help="零网络零 API 自检(渲染器 + S6 生成器)")
    args = ap.parse_args()

    if args.smoke:
        run_smoke()
        return
    if not args.candidates or not args.out:
        ap.error("--candidates 与 --out 为渲染模式必填(或用 --smoke)")
    run_render(args.candidates, args.out, args.limit, args.noise_per_entry)


if __name__ == "__main__":
    main()
