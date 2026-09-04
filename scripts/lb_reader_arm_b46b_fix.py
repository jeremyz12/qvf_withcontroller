# -*- coding: utf-8 -*-
"""批 46b — render-only / render-raw 复刻批 44,换到 L2(104K-token)规模。

预注册:results/opt_batch46b_prereg.md。这是 scripts/lb_reader_arm_b44.py 的
L2 适配副本。与原件的差异,逐条列出(其余代码逐字节照抄,不重写选择/渲染
逻辑本身):

  1. renderraw 分支新增一层防御性配额闸(prereg §4):若某题渲染文本估算
     input token(len(text)/3.4)超过 40,000,按"同题 render-only 渲染行数"
     截断到该行数(保留最早的 N 行),并记录
     `renderraw_rows_before_cap`/`renderraw_rows_dropped` 两个新字段。
     干跑核验(scratchpad/b46b/dry_run_diag.py)显示本批 120 题最大估算
     18K token,远低于 40,000,预期不触发——但代码按预注册的规则实现,
     不因为预期不触发就省略。
  2. 为了让 renderraw 也能算出"同题 render-only 会渲染几行"这个截断参照,
     renderraw 分支现在也需要 --cards-dir(原件 renderraw 不读卡片店);
     本文件的 renderraw 仍然**不用卡片店的内容渲染正文**,只用它计算截断
     参照行数这一件事,行内容依旧 100% 来自原始 user 轮次原文(与原件
     prereg 的"不做卡片抽取"承诺不变)。
  3. main() 增加对两个 --arm 都要求 --cards-dir 的校验;其余参数、断点续
     跑(已完成 question_id 跳过)、花费闸、行 schema 均与原件相同,只新增
     两个字段。

用法:
  PYTHONUTF8=1 python scripts/lb_reader_arm_b46b.py \
      --arm renderonly --cards-dir results/wt_cards_b33_L2 \
      --data data/wikistate_long_L2_b33.json \
      --questions data/wsc_long_L1_questions.jsonl \
      --out results/b46b_renderonly_L2.jsonl --workers 4
  # 同上,--cards-dir results/wt_cards_b27_L2,同一 --out(追加)

  PYTHONUTF8=1 python scripts/lb_reader_arm_b46b.py \
      --arm renderraw --cards-dir results/wt_cards_b33_L2 \
      --data data/wikistate_long_L2_b33.json \
      --questions data/wsc_long_L1_questions.jsonl \
      --out results/b46b_renderraw_L2.jsonl --workers 4
  # 同上,--cards-dir results/wt_cards_b27_L2,同一 --out(追加)
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

# ── 读者调用(逐字照抄 lb_reader_arm_b44.py) ─────────────────────────
PRICES = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5": (2.0, 10.0)}
DEFAULT_PRICE = (3.0, 15.0)
SANE_BUDGET_INTOK = 40000  # prereg §4:超过此估算 input token 触发截断


def price_of(model: str):
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    return DEFAULT_PRICE


def cost_of(model: str, tin, tout) -> float:
    pin, pout = price_of(model)
    return (tin or 0) / 1e6 * pin + (tout or 0) / 1e6 * pout


def prior_spend(pattern: str = "results/b46b_*.jsonl") -> float:
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


# ── (A) renderonly:owner/slot 三层选择,逐字照抄 b44 ──────────────────

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

    # Tier 3: alias-kw — SLOT_ALIASES 展开的关键词集对卡片 slot 字段做判定。
    # 批 46b 追加修复(见 results/opt_batch46b_verdict.md 追加节):原判据是
    # "kw in card_slot" 子串包含,导致像 "job" 这样的泛化别名(来自
    # SLOT_ALIASES["position"])把毫不相关的 job_title 卡片当命中(job 是
    # job_title 的子串)。改成整词/整槽位名精确匹配("kw == card_slot"),
    # 不再做子串包含判定——只有卡片 slot 字段与某个别名关键词逐字相同才算
    # 命中,消除这一类短词碰撞。命中不足两行时仍走既有的 fallback-full
    # 兜底(与未修复前同构,只是现在更容易触发,行为更保守)。
    if len(picked) < 2:
        kws = _alias_keywords(slot)
        picked3 = [r for r in recs if _norm(r.get("slot", "")) in kws]
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
    """鲁棒角色解析(prereg §2/§7.5,逐字照抄 b44)。"""
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


def _render_raw_rows(uid: str, entry: dict):
    """返回 (rows, tier);rows = [(date, content), ...] 已按日期排序,
    未做任何截断——截断在 render_render_raw() 里、拿到 render-only 的
    参照行数之后再做(prereg §4)。"""
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
    if len(rows) < 2:  # 兜底,与 b44 同构
        tier = "fallback-all-user"
        rows = []
        for sess in entry.get("sessions", []):
            date = sess.get("date", "undated")
            for t in sess.get("turns", []):
                role, content = _parse_turn(t)
                if role == "user":
                    rows.append((date, content))
    rows.sort(key=lambda x: x[0])
    return rows, tier


def _render_rows_to_text(slot, rows):
    lines = []
    for n, (d, txt) in enumerate(rows, 1):
        span = txt.replace("\n", " ").replace("\r", " ")[:400]
        lines.append('[entry %d] %s | %s: "%s"' % (n, d, slot or "?", span))
    return "\n".join(lines)


def render_render_raw(uid: str, entry: dict, cards_dir: str):
    """新增(prereg §4):渲染后估算 input token 若 > SANE_BUDGET_INTOK,
    按同题 render-only 渲染行数截断(保留最早的 N 行)。返回
    (text, n_rows_final, tier, n_rows_before_cap, n_rows_dropped)。"""
    slot = entry.get("slot") or ""
    rows, tier = _render_raw_rows(uid, entry)
    text = _render_rows_to_text(slot, rows)
    n_before = len(rows)
    approx_tok = len(text) / 3.4
    dropped = 0
    if approx_tok > SANE_BUDGET_INTOK:
        try:
            ro_rows, _, _ = select_render_only_rows(uid, entry, cards_dir)
            cap_n = max(2, len(ro_rows))
        except Exception:  # noqa: BLE001 卡片店缺失等异常兜底
            cap_n = max(2, n_before // 8)  # 与干跑观测的 rr/ro 比值量级一致的兜底
        if cap_n < n_before:
            rows = rows[:cap_n]
            text = _render_rows_to_text(slot, rows)
            dropped = n_before - cap_n
            tier = tier + "+capped"
    return text, len(rows), tier, n_before, dropped


def build_prompt(arm: str, q: dict, entries: dict, cards_dir: str):
    uid = q["uid"]
    entry = entries[uid]
    if arm == "renderonly":
        transcript, n_rows, tier, n_total = render_render_only(uid, entry, cards_dir)
        n_before, dropped = n_rows, 0
    else:
        transcript, n_rows, tier, n_before, dropped = render_render_raw(
            uid, entry, cards_dir)
    user = SMW_PROMPT.format(question=q["question"], transcript=transcript)
    return "", user, n_rows, tier, len(transcript), n_before, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", default="anthropic:claude-haiku-4-5")
    ap.add_argument("--arm", choices=["renderonly", "renderraw"], required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--cards-dir", required=True,
                    help="renderonly 用来渲染正文;renderraw 只用来算截断"
                         "参照行数(prereg §4),不用于渲染正文内容")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=800)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget", type=float, default=6.0,
                    help="results/b46b_*.jsonl 累计读者花费上限($),默认对齐"
                         "环境准则 Reader spend cap $6")
    a = ap.parse_args()
    model = a.reader.split(":", 1)[1]

    entries = {e["uid"]: e for e in
               json.loads(Path(a.data).read_text(encoding="utf-8"))}
    qs = [json.loads(l) for l in open(a.questions, encoding="utf-8") if l.strip()]
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["question_id"] for l in open(outp, encoding="utf-8")
            if l.strip()} if outp.exists() else set()
    # 只跑这次 --cards-dir 覆盖的 uid(与批 40 处理两卡片店目录同构)
    cdir_uids = {p.stem for p in Path(a.cards_dir).glob("*.json")}
    todo = [q for q in qs if q["qid"] not in done and q["uid"] in entries
            and q["uid"] in cdir_uids]
    print("[plan] %d questions, %d already done, %d to run (this cards-dir "
          "covers %d uid) | arm=%s reader=%s max_tokens=%d"
          % (len(qs), len(done), len(todo), len(cdir_uids), a.arm, a.reader,
             a.max_tokens), flush=True)
    if not todo:
        print("nothing to do")
        return 0

    spend0 = prior_spend()
    print("[budget] prior b46b reader spend = $%.3f; cap $%.2f"
          % (spend0, a.budget), flush=True)

    judge = ClaudeJudge()
    lock = threading.Lock()
    fh = open(outp, "a", encoding="utf-8")
    state = {"spend": spend0, "n": 0, "ok": 0, "stop": False, "skipped": 0,
             "tiers": collections.Counter(), "rows": [], "capped": 0}
    qq: "queue.Queue" = queue.Queue()
    for q in todo:
        qq.put(q)

    def worker():
        while True:
            try:
                q = qq.get_nowait()
            except queue.Empty:
                return
            sys_p, user, n_rows, tier, n_chars, n_before, dropped = build_prompt(
                a.arm, q, entries, a.cards_dir)
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
                "cards_dir": a.cards_dir,
                "rendered_rows": n_rows, "rendered_chars": n_chars,
                "selection_tier": tier,
                "renderraw_rows_before_cap": n_before,
                "renderraw_rows_dropped": dropped}
            with lock:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                state["spend"] += cost_of(model, ti, to)
                state["n"] += 1
                state["ok"] += bool(v.correct)
                state["tiers"][tier] += 1
                state["rows"].append(n_rows)
                state["capped"] += int(dropped > 0)
                print("[%s] %s rows=%d(before=%d,dropped=%d) tier=%s in=%s "
                      "out=%s (%.1fs) $%.2f"
                      % (q["qid"], v.correct, n_rows, n_before, dropped, tier,
                         ti, to, lat, state["spend"]), flush=True)
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
    print("B46b ARM DONE %s/%s: %d/%d = %.1f%% | skipped(budget)=%d | capped=%d | "
          "reader spend $%.3f | mean_rendered_rows=%.2f | tiers=%s | judge %s"
          % (a.reader, a.arm, ok, n, ok / max(1, n) * 100, state["skipped"],
             state["capped"], state["spend"], mean_rows, dict(state["tiers"]),
             judge.total_usage))
    return 0


if __name__ == "__main__":
    sys.exit(main())
