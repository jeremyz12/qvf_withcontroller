# -*- coding: utf-8 -*-
"""Oracle 检索实验:强制把全部金证据轮注入 top-10,量"检索 100% 覆盖 gold"
时直读与 QVF 的表现上限。

注入策略:先做正常 dense top-10;缺失的金轮从尾部(最低分的非金轮)逐个
置换进来,已在场的金轮保持原位。除注入外,协议与冻结版完全一致。

用法:
  python oracle_arm.py --benchmark stale       --conditions dense_direct --out results/oracle_stale50_direct.jsonl
  python oracle_arm.py --benchmark stale_chain --conditions minimal_rules_species2 --out results/oracle_chain_qvf.jsonl
"""
import argparse
import json
import os
import sys

sys.path.insert(0, r"D:\ZZL_cluade")
os.environ.setdefault("QVF_EMBED_BACKEND", "openai")
from dotenv import load_dotenv  # noqa: E402
load_dotenv(r"D:\ZZL_cluade\.env")

import scripts.run_decisive_stale as rds  # noqa: E402

# ── 修正框定协议 v2 补丁(与 framing_arm 逐字一致)──
import qvf.generator as G  # noqa: E402
G.BASELINE_GENERATOR_SYSTEM_PROMPT = (
    "You are the user's personal AI assistant. You will be shown excerpts "
    "from your past conversations with this user (retrieved from memory, "
    "each dated), followed by the user's new message. Reply to the new "
    "message naturally and helpfully in 1-3 sentences, as you would in an "
    "everyday chat."
)

def _fr_fmt(query, memories, query_date=None):
    lines = ["EXCERPTS FROM YOUR PAST CONVERSATIONS WITH THE USER:"]
    for m in memories:
        d = (m.metadata or {}).get("session_date") or "undated"
        lines.append(f"[{d}] {m.content}")
    lines.append("")
    if query_date:
        lines.append(f"TODAY'S DATE: {query_date}")
        lines.append("")
    lines.append(f"USER'S NEW MESSAGE: {query}")
    return chr(10).join(lines)

G.format_baseline_generator_input = _fr_fmt



def _nq(q: str) -> str:
    return " ".join(str(q).split())


def _best_round(sess_mems, sent):
    """定位含金句的轮:先逐字,再词重叠回退(check 脚本验证 100/100 可定位)。"""
    for m in sess_mems:
        if sent in m.content:
            return m.memory_id
    sw = set(sent.lower().split())
    best, score = None, -1
    for m in sess_mems:
        s = len(sw & set(m.content.lower().split()))
        if s > score:
            best, score = m, s
    return best.memory_id if best is not None else None


def build_gold_map(benchmark: str):
    gold = {}
    if benchmark == "stale":
        data = json.load(open(r"D:\ZZL_cluade\data\stale_T1_T2_400_FULL.json",
                              encoding="utf-8"))
        by_uid = {it["uid"]: it for it in data}
        inst = rds.load_stale(r"D:\ZZL_cluade\data\stale_T1_T2_400_FULL.json",
                              limit_items=50)
        for i in inst:
            if not i.memories:
                continue
            uid_pfx = i.memories[0].memory_id.split("/", 1)[0]
            it = next((v for k, v in by_uid.items() if k.startswith(uid_pfx)), None)
            if it is None:
                continue
            ids = set()
            for key, si_key in (("M_old", "old_session_index"),
                                ("M_new", "new_session_index")):
                si = i.extra.get(si_key)
                if si is None:
                    continue
                sess = [m for m in i.memories if f"/s{si}#" in m.memory_id]
                mid = _best_round(sess, it[key])
                if mid:
                    ids.add(mid)
            if ids:
                gold[(uid_pfx, _nq(i.question))] = frozenset(ids)
    else:  # stale_chain
        from eval.stale_chain_dataset import load_stale_chain
        data = json.load(open(r"D:\ZZL_cluade\data\stale_chain_full.json",
                              encoding="utf-8"))
        by_uid = {it["uid"]: it for it in data}
        inst = load_stale_chain(r"D:\ZZL_cluade\data\stale_chain_full.json")
        for i in inst:
            if not i.memories:
                continue
            uid_pfx = i.memories[0].memory_id.split("/", 1)[0]
            it = next((v for k, v in by_uid.items()
                       if k.startswith(uid_pfx) or uid_pfx.startswith(k)), None)
            if it is None:
                continue
            ids = set()
            for st in it["chain"]:
                mid = next((m.memory_id for m in i.memories
                            if st["state_span"] in m.content), None)
                if mid:
                    ids.add(mid)
            if ids:
                gold[(uid_pfx, _nq(i.question))] = frozenset(ids)
    return gold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", choices=["stale", "stale_chain"], required=True)
    ap.add_argument("--conditions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tlcot", action="store_true",
                    help="warned_direct 臂使用 timeline-CoT 指令(替换默认警告)")
    args = ap.parse_args()

    if args.tlcot:
        rds._WARN_INSTRUCTION = (
            "\n\n[Instruction: Before answering, reconstruct (silently) a dated "
            "timeline of every attribute the question touches: list each state "
            "with its start date in chronological order, and note which states "
            "have been superseded by later ones. Then answer STRICTLY from that "
            "timeline: for current-state questions use the latest state; for "
            "questions about a specific past date use the state that was valid "
            "on that date; for history/trajectory questions give the full "
            "ordered evolution. If the question presupposes a state your "
            "timeline shows as superseded, correct the premise before helping.]"
        )

    GOLD = build_gold_map(args.benchmark)
    n_g = sum(len(v) for v in GOLD.values())
    print(f"gold map: {len(GOLD)} questions, {n_g} gold rounds")

    _REAL = rds._dense_retriever_cls()  # 补丁前捕获真实检索器

    class OracleRetriever:
        def __init__(self, memories):
            self.inner = _REAL(memories)
            self.by_id = {m.memory_id: m for m in memories}
            self.uid = (memories[0].memory_id.split("/", 1)[0]
                        if memories else "")

        def retrieve(self, question, top_k=10):
            base = list(self.inner.retrieve(question, top_k=top_k))
            g = GOLD.get((self.uid, _nq(question)))
            if not g:
                return base
            have = {m.memory_id for m in base}
            for mid in sorted(g - have):
                if mid not in self.by_id:
                    continue
                for i in range(len(base) - 1, -1, -1):
                    if base[i].memory_id not in g:
                        base.pop(i)
                        break
                base.append(self.by_id[mid])
            return base

    rds._dense_retriever_cls = lambda: OracleRetriever

    if args.benchmark == "stale":
        argv = ["oracle", "--data", r"D:\ZZL_cluade\data\stale_T1_T2_400_FULL.json",
                "--benchmark", "stale", "--items", "50"]
    else:
        argv = ["oracle", "--data", r"D:\ZZL_cluade\data\stale_chain_full.json",
                "--benchmark", "stale_chain", "--items", "0"]
    argv += ["--conditions", args.conditions, "--out", args.out,
             "--reader", "claude-haiku-4-5", "--resume"]
    sys.argv = argv
    return rds.main()


if __name__ == "__main__":
    sys.exit(main())
