# -*- coding: utf-8 -*-
"""wsc_direct_arm 离线冒烟:零 API、零网络,桩件替换 LLM/检索器/判官。

断言清单:
  A READER_SYSTEM 逐字节 = framing_arm 猴补的基线提示词,且 =
    complex_query_arm.READER_SYSTEM(两处原件均按 AST 提取,不导入);
  B reader_content 输出逐字节 = framing_arm._fmt(AST 提取执行);
  C _retriever_cls 在四种 QVF_EMBED_BACKEND 取值下选类与
    run_decisive_stale._dense_retriever_cls 一致(AST 提取执行);
  D _memories / _query_date 与 eval.stale_chain_dataset.load_stale_chain
    的记忆装配与查询日期逐字段一致;_query_date 与 complex_query_arm 原件
    行为一致(AST 提取执行);
  E gold 不出现在读者任何载荷(system+user)中;判官收到 str(gold);
  F 检索以问题原文调用,top_k=10;
  G --resume 跳过已完成 qid(第二轮仅跑新增题);gold=null 跳过判官;
  H 行字段齐全,mode='wsc_direct'。

用法:  python scripts/smoke_wsc_direct_arm.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import tempfile
from functools import partial
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.wsc_direct_arm as W  # noqa: E402
from eval.stale_chain_dataset import load_stale_chain  # noqa: E402
from qvf.retrieval import MemoryItem  # noqa: E402

GOLD_MARK = "GOLDSECRET"  # 冒烟金答案统一水印,读者载荷中绝不允许出现


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _extract_fn(tree: ast.Module, name: str, ns: dict):
    """按名提取顶层函数并在给定命名空间中编译执行,返回该函数。"""
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == name)
    mod = ast.Module(body=[fn], type_ignores=[])
    exec(compile(mod, f"<extracted {name}>", "exec"), ns)
    return ns[name]


# ── A:读者系统提示词字节相等 ────────────────────────────────
def check_reader_system():
    tree = ast.parse(_src("scripts/framing_arm.py"))
    framing = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Attribute)
                        and t.attr == "BASELINE_GENERATOR_SYSTEM_PROMPT"):
                    framing = ast.literal_eval(node.value)
    assert framing is not None, "framing_arm 猴补提示词未找到"
    assert W.READER_SYSTEM == framing, "READER_SYSTEM 与 framing_arm 不同字节"

    tree2 = ast.parse(_src("scripts/complex_query_arm.py"))
    complex_rs = None
    for node in tree2.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "READER_SYSTEM":
                    complex_rs = ast.literal_eval(node.value)
    assert W.READER_SYSTEM == complex_rs, "与 complex_query_arm 读者不同字节"
    print("A. READER_SYSTEM 逐字节 = framing_arm 猴补版 = complex_query_arm 版")


# ── B:誊录渲染与 framing_arm._fmt 等价 ──────────────────────
def check_fmt_equivalence():
    fmt = _extract_fn(ast.parse(_src("scripts/framing_arm.py")), "_fmt", {})
    mems = [
        MemoryItem("u/s0#r0", "{'role': 'user', 'content': 'hi'}",
                   {"session_id": "s0", "session_date": "1991-01-01"}),
        MemoryItem("u/s1#r0", "plain turn", {"session_id": "s1",
                                             "session_date": ""}),
    ]
    for qdate in ("1998-09-01", None, ""):
        ref = fmt("What now?", mems, qdate)
        got = W.reader_content("What now?", mems, qdate)
        assert got == ref, f"reader_content 与 _fmt 不一致 (qdate={qdate!r})"
    assert "[undated] plain turn" in W.reader_content("q", mems, None)
    assert fmt("q", [], "2020-01-01") == W.reader_content("q", [], "2020-01-01")
    print("B. reader_content 输出逐字节 = framing_arm._fmt(含 undated/空店)")


# ── C:检索器选类与 run_decisive_stale 等价 ──────────────────
def check_retriever_cls():
    orig = _extract_fn(ast.parse(_src("scripts/run_decisive_stale.py")),
                       "_dense_retriever_cls", {"os": os})
    saved = os.environ.get("QVF_EMBED_BACKEND")
    try:
        for backend in (None, "ollama", "openai",
                        "openai:text-embedding-3-large"):
            if backend is None:
                os.environ.pop("QVF_EMBED_BACKEND", None)
            else:
                os.environ["QVF_EMBED_BACKEND"] = backend
            a, b = W._retriever_cls(), orig()
            if isinstance(a, partial) or isinstance(b, partial):
                assert isinstance(a, partial) and isinstance(b, partial)
                assert a.func is b.func and a.keywords == b.keywords, backend
            else:
                assert a is b, f"选类不一致 backend={backend!r}: {a} vs {b}"
    finally:
        if saved is None:
            os.environ.pop("QVF_EMBED_BACKEND", None)
        else:
            os.environ["QVF_EMBED_BACKEND"] = saved
    print("C. _retriever_cls 四种后端取值选类 = run_decisive_stale 原件")


# ── D:记忆装配 / 查询日期与原件等价 ─────────────────────────
def check_memories_and_qdate(tmp: Path):
    entry = {
        "uid": "smoke000-Q1", "slot": "residence",
        "sessions": [
            {"date": "2020-01-05",
             "turns": [{"role": "user", "content": "I live in Oslo."},
                       "plain string turn"]},
            {"date": "", "turns": ["undated turn"]},
        ],
        "chain": [{"value": "Oslo", "date": "2020-01-05"},
                  {"value": "Bergen", "date": "2020-12-31"}],
        "probing_queries": {"dim1": {"q": "Where do I live now?",
                                     "gold": "Bergen"}},
    }
    f = tmp / "smoke_chain.json"
    f.write_text(json.dumps([entry]), encoding="utf-8")
    inst = load_stale_chain(f)[0]
    ours = W._memories(entry)
    assert len(ours) == len(inst.memories) == 3
    for a, b in zip(ours, inst.memories):
        assert (a.memory_id, a.content, a.metadata) == \
            (b.memory_id, b.content, b.metadata)
    assert W._query_date(entry, "Where do I live now?") == inst.question_date \
        == "2021-01-31"

    ns = {"re": re}
    tree = ast.parse(_src("scripts/complex_query_arm.py"))
    for node in tree.body:  # _TODAY_RE 常量是 _query_date 的自由变量
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_TODAY_RE"
                for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]),
                         "<_TODAY_RE>", "exec"), ns)
    orig_qd = _extract_fn(tree, "_query_date", ns)
    cases = [
        (entry, "(Today is 1998-09-01.) Which employer did I hold longest?"),
        (entry, "Where do I live now?"),
        ({}, "no chain no prefix"),
        ({"chain": [{"date": "2004-03-00"}]}, "partial chain date"),
    ]
    for e, q in cases:
        assert W._query_date(e, q) == orig_qd(e, q), (e, q)
    print("D. _memories/_query_date = load_stale_chain 与 complex_query_arm 原件")


# ── E/F/G/H:桩件跑批 ────────────────────────────────────────
class _StubClient:
    def __init__(self, log):
        self._log = log
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self._log.append(kw)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="[stub answer]")],
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        )


class _StubRetriever:
    calls = []
    made = []

    def __init__(self, memories):
        self.memories = memories
        _StubRetriever.made.append([m.memory_id for m in memories])

    def retrieve(self, query, top_k=10):
        _StubRetriever.calls.append((query, top_k))
        return self.memories[:top_k]


class _StubJudge:
    calls = []

    def judge(self, question, gold, answer, qtype=None, is_abstention=False):
        _StubJudge.calls.append((question, gold, answer, qtype))
        return SimpleNamespace(correct=True, reason="stub verdict")


def check_run_flow(tmp: Path):
    sessions = [
        {"date": "2020-01-05",
         "turns": [{"role": "user", "content": "I moved to Oslo."},
                   {"role": "user", "content": "I like tea."}]},
        {"date": "2020-12-31",
         "turns": [{"role": "user", "content": "Now living in Bergen."}]},
    ]
    data = [
        {"uid": "smokeA-Q1", "slot": "residence", "sessions": sessions,
         "chain": [{"value": "Oslo", "date": "2020-01-05"},
                   {"value": "Bergen", "date": "2020-12-31"}]},
        {"uid": "smokeB-Q2", "slot": "residence", "sessions": sessions,
         "chain": [{"value": "Oslo", "date": "2020-01-05"}]},
    ]
    dataf = tmp / "smoke_data.json"
    dataf.write_text(json.dumps(data), encoding="utf-8")

    q1 = {"uid": "smokeA-Q1", "qid": "smokeA-Q1_s5a", "qtype": "change_count",
          "question": "(Today is 1998-09-01.) How many times did I move?",
          "gold": f"{GOLD_MARK}_ALPHA", "basis": "smoke"}
    q2 = {"uid": "smokeA-Q1", "qid": "smokeA-Q1_s5b", "qtype": "first_vs_last",
          "question": "Where did I live first and where now?",
          "gold": f"{GOLD_MARK}_BETA", "basis": "smoke"}
    q3 = {"uid": "smokeB-Q2", "qid": "smokeB-Q2_s7a", "qtype": "tag_demo",
          "question": "What have I mentioned about where I live?",
          "gold": None, "basis": "smoke"}
    qf1 = tmp / "smoke_q12.jsonl"
    qf1.write_text("".join(json.dumps(q) + "\n" for q in (q1, q2)),
                   encoding="utf-8")
    qf2 = tmp / "smoke_q123.jsonl"
    qf2.write_text("".join(json.dumps(q) + "\n" for q in (q1, q2, q3)),
                   encoding="utf-8")
    outf = tmp / "smoke_out.jsonl"

    reader_log = []
    W._client = lambda: _StubClient(reader_log)
    W._retriever_cls = lambda: _StubRetriever
    W.ClaudeJudge = _StubJudge

    # 第一轮:q1+q2
    W.run([str(dataf)], str(qf1), str(outf), None, False)
    rows = [json.loads(l) for l in outf.read_text(encoding="utf-8")
            .splitlines() if l]
    assert [r["question_id"] for r in rows] == [q1["qid"], q2["qid"]]

    # F. 检索以问题原文调用,top_k=10;检索器只按 uid 建一次(嵌入缓存)
    assert _StubRetriever.calls == [(q1["question"], 10), (q2["question"], 10)]
    assert len(_StubRetriever.made) == 1 and \
        _StubRetriever.made[0][0] == "smokeA-Q1/s0#r0"
    print("F. 检索以问题原文调用 top_k=10;检索器按 uid 只建一次")

    # E. gold 绝不进读者载荷;判官收到 str(gold)
    assert len(reader_log) == 2
    for kw in reader_log:
        blob = json.dumps(kw, ensure_ascii=False, default=str)
        assert GOLD_MARK not in blob, "gold 泄入读者载荷!"
        assert kw["system"][0]["text"] == W.READER_SYSTEM
        assert kw["model"] == W.MODEL and kw["temperature"] == 0.0
        assert kw["max_tokens"] == W.READER_MAX_TOKENS
    assert [c[1] for c in _StubJudge.calls] == \
        [f"{GOLD_MARK}_ALPHA", f"{GOLD_MARK}_BETA"]
    print("E. gold 未出现在读者任何载荷;判官收到 str(gold)")

    # 载荷 = _fmt 同款渲染:誊录行 + TODAY'S DATE + 问题
    body1 = reader_log[0]["messages"][0]["content"]
    assert body1.startswith("EXCERPTS FROM YOUR PAST CONVERSATIONS")
    assert "[2020-01-05]" in body1 and "TODAY'S DATE: 1998-09-01" in body1
    assert body1.endswith(f"USER'S NEW MESSAGE: {q1['question']}")
    body2 = reader_log[1]["messages"][0]["content"]
    assert "TODAY'S DATE: 2021-01-31" in body2  # 末链日期 +1 月

    # 第二轮:--resume,题集扩为 q1..q3,只应跑 q3(gold=null 跳判官)
    W.run([str(dataf)], str(qf2), str(outf), None, True)
    rows2 = [json.loads(l) for l in outf.read_text(encoding="utf-8")
             .splitlines() if l]
    assert len(reader_log) == 3, "resume 未跳过已完成 qid"
    assert [r["question_id"] for r in rows2] == \
        [q1["qid"], q2["qid"], q3["qid"]]
    assert len(_StubJudge.calls) == 2 and rows2[2]["judge_correct"] is None
    print("G. --resume 只跑新增 q3;gold=null 跳过判官")

    # H. 行字段齐全
    need = {"question_id", "mode", "uid", "question_type", "question",
            "gold_answer", "answer", "retrieved_memory_ids",
            "usage_input_tokens", "usage_output_tokens", "judge_correct",
            "judge_reason", "reader_model", "latency_s"}
    for r in rows2:
        assert need <= set(r), need - set(r)
        assert r["mode"] == "wsc_direct" and r["reader_model"] == W.MODEL
    assert rows2[0]["usage_input_tokens"] == 11
    assert rows2[0]["usage_output_tokens"] == 7
    assert rows2[0]["question_type"] == "change_count"
    print("H. 行字段齐全,mode='wsc_direct'")


def main() -> int:
    check_reader_system()
    check_fmt_equivalence()
    check_retriever_cls()
    tmp = Path(tempfile.mkdtemp(prefix="wsc_direct_smoke_"))
    check_memories_and_qdate(tmp)
    check_run_flow(tmp)
    print("SMOKE OK: wsc_direct_arm 全部离线断言通过(零 API 调用)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
