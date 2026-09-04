# -*- coding: utf-8 -*-
"""批 44 — render-matched 控制臂(版式对齐 vs 编译机制拆分)读者跑批器。

预注册:results/opt_batch44_prereg.md(先于本文件运行提交)。对 arXiv
2607.16019《Presentation, Not Mechanism》的质疑构造两条与 smoc 账目**同
版式**的对照臂:

  (A) --arm renderonly — 卡片账目,按题面槽位选中(owner/slot 三层选择,
      见 prereg §2),不做近邻同值合并、不做转变计数、不追加任何计算摘要
      行。数据源 --cards-dir(与 smoc 同一张卡片店)。
  (B) --arm renderraw  — 原始会话里"提到槽位关键词"的 user 轮次原文,
      不经任何卡片抽取。数据源 --data(语料 json 本身)。

两臂都逐字复用 `scripts/repro_batch3.py` 的 `SMW_PROMPT`(F.1 协议提示词)
与 `parse_answer`,行版式 `[entry N] DATE | LABEL: "TEXT"` 与 smoc 默认
视图的行文法对齐。读者/判官调用式复制自 `scripts/lb_reader_arm_b36b.py`
(该文件本身声明是原件 `lb_reader_arm.py` 的只读副本),本文件是同一惯例
下的批 44 副本,不改动任何既有臂的行为——smoc/direct/fullplain 等既有
`--arm` 分支本批完全不碰,只新增 renderonly/renderraw 两个分支。

用法:
  PYTHONUTF8=1 python scripts/lb_reader_arm_b44.py \
      --arm renderonly --cards-dir results/wt_cards_v45 \
      --data data/wikistate_full_ALL_v24.json \
      --questions data/wsc_s5_v25.jsonl \
      --out results/b44_renderonly.jsonl --workers 4

  PYTHONUTF8=1 python scripts/lb_reader_arm_b44.py \
      --arm renderraw \
      --data data/wikistate_full_ALL_v24.json \
      --questions data/wsc_s5_v25.jsonl \
      --out results/b44_renderraw.jsonl --workers 4
"""
from __future__ import annotations

import argparse
import ast
import collections
import json
import queue
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from qvf.judge import ClaudeJudge  # noqa: E402
from repro_batch3 import SMW_PROMPT, parse_answer  # noqa: E402 逐字复用,零改写
from complex_query_arm import _mem_dates, SLOT_ALIASES  # noqa: E402

# ── 读者调用(逐字照抄 lb_reader_arm_b36b.py 的 anthropic 分支;本批只用
#    claude-haiku-4-5,故只保留 anthropic 分支,其余 kind 不支持) ──────
PRICES = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5": (2.0, 10.0)}
DEFAULT_PRICE = (3.0, 15.0)


def price_of(model: str):
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    return DEFAULT_PRICE


def cost_of(model: str, tin, tout) -> float:
    pin, pout = price_of(model)
    return (tin or 0) / 1e6 * pin + (tout or 0) / 1e6 * pout


def prior_spend(pattern: str = "results/b44_*.jsonl") -> float:
    tot = 0.0
    for p in sorted(ROOT.glob(pattern)):
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            tot += cost_of(d.get("reader_model", ""),
                           d.get("usage_input_tokens"),
                           d.get("usage_output_tokens"))
    return tot


def call_reader(reader: str, system: str, user: str, max_tokens: int = 800):
    kind, model = reader.split(":", 1)
    t0 = time.time()
    if kind == "anthropic":
        import anthropic
        with call_reader._lock:
            cli = call_reader._ant = getattr(call_reader, "_ant", None) or \
                anthropic.Anthropic()
        kw = dict(model=model, max_tokens=max_tokens,
                  messages=[{"role": "user", "content": user}])
        if system:
            kw["system"] = system
        if model.startswith("claude-haiku"):  # 与冻结逐字同值:sonnet-5 拒收 temperature
            kw["temperature"] = 0.0
        r = cli.messages.create(**kw)
        txt = "".join(b.text for b in r.content if b.type == "text")
        return txt, r.usage.input_tokens, r.usage.output_tokens, \
            time.time() - t0, r.stop_reason
    raise ValueError("本批只跑 anthropic 读者: %r" % kind)


call_reader._lock = threading.Lock()


# ── (A) renderonly:owner/slot 三层选择,行版式与 smoc 默认视图逐字节同 ──

def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _alias_keywords(slot: str) -> set:
    slot = _norm(slot)
    base = slot.replace("_", " ").strip()
    tokens = [t for t in re.split(r"[_\s]+", slot) if len(t) >= 4]
    ali = []
    for k, vs in SLOT_ALIASES.items():
        if k in slot or slot in k:
            ali.extend(vs)
    kws = set([base] + tokens + [w.lower() for w in ali])
    kws.discard("")
    return kws


def select_render_only_rows(uid: str, entry: dict, cards_dir: str):
    """owner/slot 三层选择(见 prereg §2)。返回 (rows, tier, n_total_recs)。
    rows 为 (date, record) 列表,tier in
    {'chain-crosswalk','literal-slot','alias-kw','fallback-full'}。"""
    cards_p = Path(cards_dir) / f"{uid}.json"
    all_recs = json.loads(cards_p.read_text(encoding="utf-8")).get("records", [])
    recs = [r for r in all_recs if r.get("entity") == "user"]  # owner 闸
    md = _mem_dates(entry)

    def dated(rs):
        out = []
        for r in rs:
            d = r.get("stated_date") or md.get(r.get("source_memory_id", ""), "")
            out.append((d or "9999", r))
        return out

    slot = entry.get("slot") or ""
    s = _norm(slot)

    # Tier 1: chain-crosswalk — 用语料自带黄金链只做"标签对照表",不直接
    # 用链条的 date/value 选行或拼正文(避免 oracle 泄漏进正文)。
    chain_pairs = {(c.get("date", ""), _norm(c.get("value", "")))
                    for c in entry.get("chain", [])}
    label_hits = collections.Counter()
    for r in recs:
        rv = _norm(r.get("value", ""))
        rd = r.get("stated_date", "")
        if not rv:
            continue
        for cd, cv in chain_pairs:
            if rd == cd and cv and (cv in rv or rv in cv):
                label_hits[r.get("slot", "")] += 1
    label = label_hits.most_common(1)[0][0] if label_hits else None

    def hit_label(r, lab):
        rl = _norm(r.get("slot", ""))
        lab = _norm(lab)
        return bool(lab) and (lab in rl or rl in lab)

    picked, tier = [], None
    if label:
        picked = [r for r in recs if hit_label(r, label)]
        if picked:
            tier = "chain-crosswalk"

    # Tier 2: literal-slot — 与 render_card_ledger 现有 hit() 逐字同逻辑。
    if len(picked) < 2:
        picked2 = [r for r in recs if s and (s in _norm(r.get("slot", ""))
                                             or _norm(r.get("slot", "")) in s)]
        if len(picked2) > len(picked):
            picked, tier = picked2, "literal-slot"

    # Tier 3: alias-kw — SLOT_ALIASES 展开的关键词集对卡片 slot 字段做包含判定。
    if len(picked) < 2:
        kws = _alias_keywords(slot)
        picked3 = [r for r in recs if any(kw in _norm(r.get("slot", "")) for kw in kws)]
        if len(picked3) > len(picked):
            picked, tier = picked3, "alias-kw"

    # 兜底:命中不足两行,退回该店整本账目(与 render_card_ledger 自身
    # slot-view 的既有兜底惯例同构),不新增任何计算内容。
    if len(picked) < 2:
        picked, tier = recs, "fallback-full"

    return sorted(dated(picked), key=lambda x: x[0]), tier, len(all_recs)


def render_render_only(uid: str, entry: dict, cards_dir: str):
    rows, tier, n_total = select_render_only_rows(uid, entry, cards_dir)
    lines = []
    for n, (d, r) in enumerate(rows, 1):
        date = d if d != "9999" else "undated"
        span = (r.get("source_span") or "")[:120]
        lines.append('[entry %d] %s | %s: %s — "%s"'
                     % (n, date, r.get("slot", "?"), r.get("value", "?"), span))
    return "\n".join(lines), len(rows), tier, n_total


# ── (B) renderraw:原始 user 轮次,关键词命中,无卡片抽取 ─────────────

_ROLE_RE = re.compile(r"^\{'role':\s*'(user|assistant)',\s*'content':\s*(['\"])")


def _parse_turn(t) -> tuple:
    """鲁棒角色解析(prereg §2/§7.5)。原始 turn 序列化不统一:多数是
    `str({'role':.., 'content':..})`,但超长回复在 400 字符处被截断导致
    字典字面量不闭合,ast.literal_eval 会失败;另有整轮就是裸字符串
    (无 role 包装)的情况,实测均为第一人称用户自述。三级解析:
    1) ast.literal_eval 成功且含 role 键 -> 直接用;
    2) 正则匹配字典前缀(容忍未闭合)-> 按前缀取 role,content 取剩余原文;
    3) 都不匹配 -> 判 role='user',content=原文。
    绝不用裸 `eval()`(那是 render_transcript 的既有写法,失败时静默保留
    原文、不判角色,会把这类轮次整体排除出"user 轮"统计——本臂需要精确
    的角色标签,故弃用该写法,另写此函数)。"""
    txt = str(t)
    try:
        d = ast.literal_eval(txt)
        if isinstance(d, dict) and "role" in d:
            return d.get("role", ""), str(d.get("content", ""))
    except Exception:  # noqa: BLE001
        pass
    m = _ROLE_RE.match(txt)
    if m:
        role = m.group(1)
        content = txt[m.end():]
        content = content.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"')
        return role, content
    return "user", txt


_STOP = {"the", "and", "for", "with", "from", "this", "that", "have", "been",
         "were", "was", "are", "has", "had", "into", "over", "under", "than",
         "then", "also", "just", "about", "after", "before", "their", "they",
         "them", "your", "you", "not", "now", "today", "recently"}


def _value_tokens(chain) -> set:
    toks = set()
    for c in chain:
        v = str(c.get("value") or "")
        vl = v.lower().strip()
        if vl:
            toks.add(vl)
        for w in re.split(r"[^a-zA-Z0-9]+", vl):
            if len(w) >= 4 and w not in _STOP:
                toks.add(w)
    return toks


def render_render_raw(uid: str, entry: dict):
    slot = entry.get("slot") or ""
    kws = _alias_keywords(slot) | _value_tokens(entry.get("chain", []))
    rows = []  # (date, content)
    for sess in entry.get("sessions", []):
        date = sess.get("date", "undated")
        for t in sess.get("turns", []):
            role, content = _parse_turn(t)
            if role != "user":
                continue
            low = content.lower()
            if any(kw in low for kw in kws):
                rows.append((date, content))
    tier = "keyword-hit"
    if len(rows) < 2:  # 离线预演零触发(prereg §2),留兜底以防未预演到的店
        tier = "fallback-all-user"
        rows = []
        for sess in entry.get("sessions", []):
            date = sess.get("date", "undated")
            for t in sess.get("turns", []):
                role, content = _parse_turn(t)
                if role == "user":
                    rows.append((date, content))
    rows.sort(key=lambda x: x[0])
    lines = []
    for n, (d, txt) in enumerate(rows, 1):
        span = txt.replace("\n", " ").replace("\r", " ")[:400]
        lines.append('[entry %d] %s | %s: "%s"' % (n, d, slot or "?", span))
    return "\n".join(lines), len(rows), tier


def build_prompt(arm: str, q: dict, entries: dict, led: dict, cards_dir: str):
    uid = q["uid"]
    entry = entries[uid]
    if arm == "renderonly":
        transcript, n_rows, tier, n_total = render_render_only(uid, entry, cards_dir)
    else:
        transcript, n_rows, tier = render_render_raw(uid, entry)
    user = SMW_PROMPT.format(question=q["question"], transcript=transcript)
    return "", user, n_rows, tier, len(transcript)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", default="anthropic:claude-haiku-4-5")
    ap.add_argument("--arm", choices=["renderonly", "renderraw"], required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--cards-dir", default="results/wt_cards_v45",
                    help="renderonly 专用;renderraw 不读卡片店")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=800)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget", type=float, default=4.0,
                    help="results/b44_*.jsonl 累计读者花费上限($),默认对齐环境准则")
    a = ap.parse_args()
    model = a.reader.split(":", 1)[1]

    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8") if l.strip()]
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")
            if l.strip()} if outp.exists() else set()
    todo = [q for q in qs if q["qid"] not in done and q["uid"] in entries]
    print("[plan] %d questions, %d already done, %d to run | arm=%s reader=%s "
          "max_tokens=%d" % (len(qs), len(done), len(todo), a.arm, a.reader,
                             a.max_tokens), flush=True)
    if not todo:
        print("nothing to do")
        return 0

    spend0 = prior_spend()
    print("[budget] prior b44 reader spend = $%.3f; cap $%.2f"
          % (spend0, a.budget), flush=True)

    judge = ClaudeJudge()
    lock = threading.Lock()
    fh = open(outp, "a", encoding="utf-8")
    state = {"spend": spend0, "n": 0, "ok": 0, "stop": False, "skipped": 0,
             "tiers": collections.Counter(), "rows": []}
    qq: "queue.Queue" = queue.Queue()
    for q in todo:
        qq.put(q)

    def worker():
        while True:
            try:
                q = qq.get_nowait()
            except queue.Empty:
                return
            sys_p, user, n_rows, tier, n_chars = build_prompt(
                a.arm, q, entries, {}, a.cards_dir)
            with lock:
                if state["stop"]:
                    state["skipped"] += 1
                    qq.task_done()
                    continue
                est = cost_of(model, len(user) / 3.4, a.max_tokens)
                if state["spend"] + est > a.budget:
                    state["stop"] = True
                    state["skipped"] += 1
                    print("[budget] STOP: $%.2f + est $%.3f > $%.2f"
                          % (state["spend"], est, a.budget), flush=True)
                    qq.task_done()
                    continue
            raw, ti, to, lat, stop = "", 0, 0, 0.0, ""
            err = ""
            for attempt in range(3):
                try:
                    raw, ti, to, lat, stop = call_reader(
                        a.reader, sys_p, user, a.max_tokens)
                    err = ""
                    break
                except Exception as e:  # noqa: BLE001
                    err = "%s: %s" % (type(e).__name__, str(e)[:160])
                    print("retry %d [%s]: %s" % (attempt, q["qid"], err),
                          flush=True)
                    time.sleep(4)
            pred, dev = parse_answer(raw)
            v = judge.judge(q["question"], str(q["gold"]), pred, q.get("qtype"))
            row = {
                "question_id": q["qid"], "mode": "%s:%s" % (a.arm, a.reader),
                "uid": q["uid"], "question_type": q.get("qtype"),
                "question": q["question"], "gold_answer": q["gold"],
                "answer": pred[:2000], "protocol_deviation": dev,
                "usage_input_tokens": ti, "usage_output_tokens": to,
                "judge_correct": v.correct, "judge_reason": v.reason,
                "latency_s": round(lat, 2),
                "reader_model": model, "reader_max_tokens": a.max_tokens,
                "stop_reason": stop, "reader_error": err,
                "judge_input_tokens": v.usage_input_tokens,
                "judge_output_tokens": v.usage_output_tokens,
                "cards_dir": (a.cards_dir if a.arm == "renderonly" else ""),
                "rendered_rows": n_rows, "rendered_chars": n_chars,
                "selection_tier": tier}
            with lock:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                state["spend"] += cost_of(model, ti, to)
                state["n"] += 1
                state["ok"] += bool(v.correct)
                state["tiers"][tier] += 1
                state["rows"].append(n_rows)
                print("[%s] %s rows=%d tier=%s in=%s out=%s (%.1fs) $%.2f"
                      % (q["qid"], v.correct, n_rows, tier, ti, to, lat,
                         state["spend"]), flush=True)
            qq.task_done()

    ths = [threading.Thread(target=worker, daemon=True)
           for _ in range(max(1, a.workers))]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    fh.close()
    n, ok = state["n"], state["ok"]
    mean_rows = (sum(state["rows"]) / len(state["rows"])) if state["rows"] else 0.0
    print("B44 ARM DONE %s/%s: %d/%d = %.1f%% | skipped(budget)=%d | "
          "reader spend $%.3f | mean_rendered_rows=%.2f | tiers=%s | judge %s"
          % (a.reader, a.arm, ok, n, ok / max(1, n) * 100, state["skipped"],
             state["spend"], mean_rows, dict(state["tiers"]), judge.total_usage))
    return 0


if __name__ == "__main__":
    sys.exit(main())
