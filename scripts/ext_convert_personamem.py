# -*- coding: utf-8 -*-
"""把 PersonaMem-v2(HF bowen-upenn/PersonaMem-v2,CC-BY-4.0)转成本仓外场
统一店格式,并按批 33-G1 预注册做分层抽样。

输入(HF 直下,不入库):
  benchmark/text/benchmark.csv                 5000 题 / 200 persona
  data/chat_history_32k/*.json                 每 persona 一份 32k 上下文
  data/raw_data/*.json                         每 persona 一份原始档(用于**切会话**)

输出(全部落 data/external/personamem/,不得提交):
  personamem_unified.json    统一店(uid=persona-<id>,sessions/questions)
  personamem_cardable.json   同上 + load_stale_chain 需要的占位 chain/probing_queries
  personamem_probe.jsonl     600 题探针(uid/qid/qtype/question/gold/cutoff/meta)
  personamem_uids.txt        采样 uid 清单(建卡分片用)

三条须披露的构造决定(全部写进终判):
  ① **分层退化**:v2 text benchmark 里 `updated=True`(1047 行)⊂
     `pref_type=='ask_to_forget'`(1048 行),交集 1047 —— 预注册的
     "updated 200 / ask_to_forget 200"在本发布上是同一个层。故按预注册
     "fallback to what exists"改为三层:ask_to_forget(=updated) /
     who=others / self_standard(其余 who=self 且非 ask_to_forget)。
  ② **日期是派生的**:chat_history_32k 与 raw_data 都**不带任何时间戳**
     (metadata 只有 total_messages/final_token_count/persona_id)。按令
     "derive from session order with a fixed 7-day step and DISCLOSE":
     会话序 j(0 起,含 persona 档案伪会话)→ START_DATE + 7j 天。
  ③ **会话边界由 raw_data 反推**:chat_history 是 raw_data 各 scenario
     conversation block 的**连续拼接子集**(实测 persona521:64 块严丝合缝
     覆盖全部 188 条消息)。逐块在 chat_history 里定位起点并校验连续,
     一块 = 一会话。定位不上的块(未进 32k 窗口)丢弃。
     系统消息(persona 档案 JSON)= 会话 0,官方 32k 上下文含之,原样保留。

题面 = 官方四选一协议(README:"append the user_query to the end of its
chat history";correct_answer + 3 个 incorrect_answers)。选项按
seed=33 的确定性洗牌贴标 A-D;gold = "<字母> — <正确选项原文>"。

用法:
  python scripts/ext_convert_personamem.py --personas 100 --per-stratum 2
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "external" / "personamem"
HFDIR = OUT / "v2"
REPO_ID = "bowen-upenn/PersonaMem-v2"
SEED = 33
START_DATE = date(2024, 1, 1)   # 派生日期起点(见模块头 ②)
STEP_DAYS = 7

STRATA = ("ask_to_forget", "who_other", "self_standard")


def stratum_of(row) -> str:
    if row["pref_type"] == "ask_to_forget":
        return "ask_to_forget"
    if row["who"] == "others":
        return "who_other"
    return "self_standard"


def _dl(rel: str) -> Path:
    from huggingface_hub import hf_hub_download
    return Path(hf_hub_download(REPO_ID, rel, repo_type="dataset",
                                local_dir=str(HFDIR)))


def _content(cell) -> str:
    """user_query 列是 str(dict);取 content,失败则原样。"""
    try:
        v = ast.literal_eval(cell)
        if isinstance(v, dict):
            return str(v.get("content", cell))
    except Exception:  # noqa: BLE001
        pass
    return str(cell)


def segment_sessions(chat_history, raw_persona):
    """用 raw_data 的 conversation block 反推会话边界。
    返回 [[msg, ...], ...](按 chat_history 出现序),以及诊断计数。"""
    def key(m):
        c = m.get("content")
        # multimodal 块的 content 是 list(不可哈希);text 卷里不会出现,
        # 但 raw_data 含 multimodal scenario,统一序列化成字符串再比对。
        return (m.get("role"), c if isinstance(c, str)
                else json.dumps(c, ensure_ascii=False, sort_keys=True))

    idx = defaultdict(list)
    for i, m in enumerate(chat_history):
        idx[key(m)].append(i)
    spans, n_block, n_miss = [], 0, 0
    for _scen, lst in (raw_persona.get("conversations") or {}).items():
        for b in lst:
            n_block += 1
            msgs = b.get("conversations") or []
            if not msgs:
                n_miss += 1
                continue
            pos = [idx.get(key(m), []) for m in msgs]
            if not all(pos):
                n_miss += 1
                continue
            placed = False
            for s in pos[0]:
                if all((s + j) in pos[j] for j in range(len(msgs))):
                    spans.append((s, len(msgs)))
                    placed = True
                    break
            if not placed:
                n_miss += 1
    spans.sort()
    # 去重(同一段被两块匹配到时保留一次)
    seen, clean = set(), []
    for s, ln in spans:
        if s in seen:
            continue
        seen.add(s)
        clean.append((s, ln))
    return clean, n_block, n_miss


def build_store(pid: int, ch_path: Path, raw_path: Path):
    ch_obj = json.loads(ch_path.read_text(encoding="utf-8"))
    chat = ch_obj["chat_history"]
    raw_obj = json.loads(raw_path.read_text(encoding="utf-8"))
    raw = raw_obj[str(pid)] if str(pid) in raw_obj else list(raw_obj.values())[0]
    spans, n_block, n_miss = segment_sessions(chat, raw)

    sessions = []
    covered = set()
    # 会话 0:persona 档案(官方 32k 上下文的 system 消息,原样保留)
    if chat and chat[0].get("role") == "system":
        sessions.append(["system: " + chat[0]["content"]])
        covered.add(0)
    for s, ln in spans:
        turns = []
        for j in range(s, s + ln):
            m = chat[j]
            turns.append(f"{m.get('role', '?')}: {m.get('content', '')}")
            covered.add(j)
        sessions.append(turns)
    # 未被任何块覆盖的残留消息(实测通常为 0):按单条兜底会话追加,不丢数据
    leftovers = sorted(set(range(len(chat))) - covered)
    for j in leftovers:
        m = chat[j]
        sessions.append([f"{m.get('role', '?')}: {m.get('content', '')}"])

    dated = [{"date": (START_DATE + timedelta(days=STEP_DAYS * k)).isoformat(),
              "turns": t} for k, t in enumerate(sessions)]
    diag = {"n_msgs": len(chat), "n_sessions": len(dated),
            "n_raw_blocks": n_block, "n_blocks_unmatched": n_miss,
            "n_leftover_msgs": len(leftovers),
            "final_token_count": ch_obj.get("metadata", {}).get(
                "final_token_count")}
    return dated, diag


def make_question(rng, row, pid, qi):
    opts = [str(row["correct_answer"])] + list(ast.literal_eval(
        row["incorrect_answers"]))
    order = list(range(4))
    rng.shuffle(order)
    letters = "ABCD"
    lines, gold_letter = [], None
    for slot, oi in enumerate(order):
        lines.append(f"({letters[slot]}) {opts[oi]}")
        if oi == 0:
            gold_letter = letters[slot]
    qtext = (_content(row["user_query"]).strip()
             + "\n\nWhich of these four candidate replies is the best, most "
               "personalized response for me? Answer with the single letter "
               "(A, B, C, or D) of the best option.\n\n"
             + "\n\n".join(lines))
    gold = f"{gold_letter} — {opts[0]}"
    return {
        "uid": f"personamem-{pid:04d}",
        "qid": f"personamem-{pid:04d}-q{qi:02d}",
        "qtype": stratum_of(row),
        "question": qtext,
        "gold": gold,
        "cutoff": "",
        "meta": {
            "persona_id": int(pid),
            "gold_letter": gold_letter,
            "option_order": order,
            "preference": str(row["preference"]),
            "prev_pref": None if row["prev_pref"] != row["prev_pref"]
            else str(row["prev_pref"]),
            "pref_type": str(row["pref_type"]),
            "who": str(row["who"]),
            "updated": bool(row["updated"]),
            "conversation_scenario": str(row["conversation_scenario"]),
            "topic_query": str(row["topic_query"]),
            "distance_to_ref_tokens_32k": int(
                row["distance_from_related_snippet_to_query_32k"]),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--personas", type=int, default=100)
    ap.add_argument("--per-stratum", type=int, default=2)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    import pandas as pd
    bench = HFDIR / "benchmark" / "text" / "benchmark.csv"
    if not bench.exists():
        _dl("benchmark/text/benchmark.csv")
    df = pd.read_csv(bench)
    df["stratum"] = df.apply(stratum_of, axis=1)
    print("full benchmark strata:", dict(df.stratum.value_counts()))
    print("degenerate-check: updated&ask_to_forget=%d updated=%d atf=%d"
          % (((df.updated) & (df.pref_type == "ask_to_forget")).sum(),
             (df.updated).sum(), (df.pref_type == "ask_to_forget").sum()))

    ct = df.pivot_table(index="persona_id", columns="stratum",
                        values="user_query", aggfunc="count").fillna(0)
    for s in STRATA:
        if s not in ct:
            ct[s] = 0
    elig = sorted(ct[(ct[list(STRATA)] >= a.per_stratum).all(axis=1)].index)
    print(f"eligible personas (>= {a.per_stratum} in each stratum): {len(elig)}")
    rng = random.Random(SEED)
    picked = sorted(rng.sample(elig, min(a.personas, len(elig))))
    print(f"sampled personas: {len(picked)}")

    # ── 下载所需两份文件(并行 <=4) ──────────────────────
    sub = df[df.persona_id.isin(picked)]
    need = {}
    for pid, g in sub.groupby("persona_id"):
        need[int(pid)] = (g.iloc[0]["chat_history_32k_link"],
                          g.iloc[0]["raw_persona_file"])
    todo = []
    for pid, (ch, raw) in need.items():
        for rel in (ch, raw):
            if not (HFDIR / rel).exists():
                todo.append(rel)
    print(f"downloading {len(todo)} files from HF ...", flush=True)
    if todo:
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(_dl, todo))

    # ── 建店 + 抽题 ────────────────────────────────────
    stores, rows, diags = [], [], []
    for pid in picked:
        ch_rel, raw_rel = need[pid]
        sessions, diag = build_store(pid, HFDIR / ch_rel, HFDIR / raw_rel)
        diag["persona_id"] = pid
        diags.append(diag)
        g = sub[sub.persona_id == pid]
        qs, qi = [], 0
        for s in STRATA:
            pool = g[g.stratum == s]
            take = rng.sample(list(pool.index), a.per_stratum)
            for ridx in take:
                qs.append(make_question(rng, df.loc[ridx], pid, qi))
                qi += 1
        stores.append({"uid": f"personamem-{pid:04d}", "sessions": sessions,
                       "questions": qs})
        rows.extend(qs)

    (OUT / "personamem_unified.json").write_text(
        json.dumps(stores, ensure_ascii=False), encoding="utf-8")
    for st in stores:
        st["chain"] = [{"date": st["sessions"][-1]["date"], "value": ""}]
        st["probing_queries"] = {"_placeholder": {"q": "placeholder", "gold": ""}}
    (OUT / "personamem_cardable.json").write_text(
        json.dumps(stores, ensure_ascii=False), encoding="utf-8")
    with open(OUT / "personamem_probe.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "personamem_uids.txt").write_text(
        "\n".join(st["uid"] for st in stores) + "\n", encoding="utf-8")
    (OUT / "personamem_build_diag.json").write_text(
        json.dumps(diags, ensure_ascii=False, indent=1), encoding="utf-8")

    chars = sum(len(t) for st in stores for s in st["sessions"]
                for t in s["turns"])
    sess = [len(st["sessions"]) for st in stores]
    print(f"stores {len(stores)}; questions {len(rows)}; strata "
          f"{dict(Counter(r['qtype'] for r in rows))}")
    print(f"card-build chars {chars:,} (mean {chars // len(stores):,}/store); "
          f"sessions/store mean {sum(sess) / len(sess):.1f} "
          f"min {min(sess)} max {max(sess)}")
    print("unmatched raw blocks total:",
          sum(d["n_blocks_unmatched"] for d in diags),
          "leftover msgs total:", sum(d["n_leftover_msgs"] for d in diags))
    print("gold letter balance:",
          dict(Counter(r["meta"]["gold_letter"] for r in rows)))
    print("wrote ->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
