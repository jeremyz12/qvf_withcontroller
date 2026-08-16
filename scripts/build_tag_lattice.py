# -*- coding: utf-8 -*-
"""阶段二·离线开放标签本体归纳(新文件,不改动任何冻结路径)。

输入:一批用 QVF_CARD_TAGS=2(开放标签,见 scripts/wt_qvf_prototype.py)重建
的卡片目录(每条 record 带自由 value_tags)。
输出:results/tag_lattice.json —— 供 scripts/tag_lattice.py /
complex_query_arm.py(QVF_TAG_LATTICE=1)读取侧格闭包查询使用的标签格。

流程:
  ① 收集全部卡片的 value_tags 原始标签词汇表(去重,保留首次出现顺序)。
  ② 嵌入(复用 QVF_EMBED_BACKEND=openai 同款 text-embedding-3-small)。
  ③ 逐标签增量入格,调和不变量【merge-or-attach,禁止孤立节点】:
     - 与既有节点嵌入余弦 >= --tau-syn 的最相似节点,经 haiku 复核确认
       同义 -> 合并(记为该节点别名,质心重算);
     - 否则挂到既有节点下:haiku 从候选父节点(嵌入 top-K)中选一个,
       判定边类型 is_a(概念层级)或 has_property(属性描述),并给出该
       父节点选择的理由;has_property 边额外过【逐条文本蕴含复核】——
       "X 通常/合理地具有属性 Y 吗?"haiku yes/no 复核,拒绝则降级为
       挂在根节点下的 is_a 边(不丢弃、不孤立,但不放行未经验证的属性
       断言,防"寿司→高糖"类幻觉边击穿精确率);
     - 唯一允许的"无父"节点是引导根节点 __root__(代码写死,非语义
       类目,不出现在字符串匹配里,只作图连通锚点,与 CLOSED_TAGS/
       SUB_TAGS 无任何字面重叠)。
  ④ 落盘 results/tag_lattice.json + 建格审计日志(每条合并/挂载决策的
     理由,供人工抽查)。

用法:
  python scripts/build_tag_lattice.py --cards-dir results/wt_cards_opentags_smoke \
      --out results/tag_lattice.json --tau-syn 0.86
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

ROOT_ID = "__root__"
MODEL = os.environ.get("QVF_TAG_LATTICE_BUILD_MODEL", "claude-haiku-4-5")
EMBED_MODEL = os.environ.get("QVF_TAG_LATTICE_EMBED_MODEL",
                             "text-embedding-3-small")


# ── 标签词汇表收集 ───────────────────────────────────────────
def collect_labels(cards_dir: Path, uids: Optional[List[str]]) -> List[str]:
    files = sorted(cards_dir.glob("*.json"))
    if uids:
        keep = set(uids)
        files = [f for f in files if f.stem in keep]
    seen: Dict[str, str] = {}   # normalized -> first-seen original casing
    order: List[str] = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for r in d.get("records", []):
            for t in (r.get("value_tags") or []):
                t = (t or "").strip()
                if not t:
                    continue
                key = t.lower()
                if key not in seen:
                    seen[key] = t
                    order.append(key)
    return [seen[k] for k in order]


# ── 嵌入 ─────────────────────────────────────────────────────
def embed_all(labels: List[str]) -> Dict[str, List[float]]:
    from openai import OpenAI
    client = OpenAI()
    out: Dict[str, List[float]] = {}
    for i in range(0, len(labels), 256):
        batch = labels[i:i + 256]
        r = client.embeddings.create(model=EMBED_MODEL, input=batch)
        for lab, d in zip(batch, r.data):
            v = d.embedding
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out[lab] = [x / n for x in v]
    return out


def cos(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ── haiku 复核:同义合并判定 ─────────────────────────────────
class SynonymVerdict(BaseModel):
    same_concept: bool = Field(
        description="True if the two labels denote the SAME underlying "
        "concept/category (near-synonyms, one a paraphrase of the other), "
        "not merely related.")


def confirm_synonym(client, label_a: str, label_b: str) -> bool:
    try:
        resp = client.messages.parse(
            model=MODEL, max_tokens=100, temperature=0.0,
            system=[{"type": "text", "text":
                     "You judge whether two short tag labels denote the "
                     "SAME concept (synonyms/near-duplicates), not just "
                     "related concepts. Be strict: 'coffee' and 'espresso' "
                     "are NOT the same (species vs genus); 'coffee' and "
                     "'caffeinated drink' overlap but are not the same "
                     "either. Only true near-synonyms count."}],
            messages=[{"role": "user", "content":
                       f"Label A: {label_a!r}\nLabel B: {label_b!r}"}],
            output_format=SynonymVerdict,
        )
        p = resp.parsed_output
        return bool(p and p.same_concept)
    except Exception:  # noqa: BLE001
        return False


# ── haiku:挂载判定(边类型 + 父节点 + 理由) ────────────────────
class AttachVerdict(BaseModel):
    edge_type: str = Field(
        description="'is_a' if the label is a more specific instance/"
        "subtype of the chosen parent concept; 'has_property' if the "
        "label instead describes an ATTRIBUTE/PROPERTY that things of "
        "the parent's kind may or may not have (e.g. a nutrition or "
        "intensity descriptor).")
    parent_label: str = Field(
        description="Exactly one of the candidate parent labels given, "
        "or 'NONE' if none of them is a sensible parent.")
    reason: str = Field(description="One short sentence justification.")


def choose_attachment(client, label: str,
                      candidates: List[str]) -> Optional[AttachVerdict]:
    if not candidates:
        return None
    try:
        resp = client.messages.parse(
            model=MODEL, max_tokens=200, temperature=0.0,
            system=[{"type": "text", "text":
                     "You are building a concept lattice for personal-memory "
                     "tags. Given a NEW label and a shortlist of EXISTING "
                     "candidate parent labels, decide how the new label "
                     "relates to the single best candidate: is_a (new label "
                     "is a more specific kind/instance of the candidate) or "
                     "has_property (new label is instead an attribute/"
                     "descriptor that things like the candidate may carry, "
                     "e.g. a nutrition or intensity trait). If no candidate "
                     "fits either relation, say parent_label='NONE'."}],
            messages=[{"role": "user", "content":
                       f"NEW LABEL: {label!r}\nCANDIDATE PARENTS: "
                       f"{json.dumps(candidates, ensure_ascii=False)}"}],
            output_format=AttachVerdict,
        )
        return resp.parsed_output
    except Exception:  # noqa: BLE001
        return None


# ── haiku:has_property 边逐条文本蕴含复核 ───────────────────
class EntailmentVerdict(BaseModel):
    holds: bool = Field(
        description="True if it is reasonable/commonly true that things "
        "denoted by the concept label carry the property label; False if "
        "this would be a stretch, an overgeneralization, or false for the "
        "typical case.")


def check_entailment(client, concept_label: str, property_label: str) -> bool:
    try:
        resp = client.messages.parse(
            model=MODEL, max_tokens=100, temperature=0.0,
            system=[{"type": "text", "text":
                     "You fact-check a proposed property assertion for a "
                     "concept lattice. Answer holds=True only if it is "
                     "reasonable to say the concept commonly/typically "
                     "carries the property; be conservative — reject "
                     "overgeneralizations and unlikely stretches (e.g. "
                     "'sushi' does NOT commonly entail 'high-sugar')."}],
            messages=[{"role": "user", "content":
                       f"Concept: {concept_label!r}\nProperty: "
                       f"{property_label!r}\nDoes the concept commonly "
                       f"carry this property?"}],
            output_format=EntailmentVerdict,
        )
        p = resp.parsed_output
        return bool(p and p.holds)
    except Exception:  # noqa: BLE001
        return False


# ── 主构建流程 ───────────────────────────────────────────────
def build(labels: List[str], vecs: Dict[str, List[float]],
         tau_syn: float, topk: int, client) -> Tuple[dict, List[dict]]:
    nodes: Dict[str, dict] = {
        ROOT_ID: {"label": ROOT_ID, "type": "root", "aliases": [],
                  "members": [], "centroid": None},
    }
    is_a: List[Tuple[str, str]] = []
    has_property: List[Tuple[str, str]] = []
    audit: List[dict] = []
    next_id = [0]

    def new_node_id() -> str:
        next_id[0] += 1
        return f"n{next_id[0]}"

    def real_nodes() -> List[str]:
        return [nid for nid in nodes if nid != ROOT_ID]

    for li, label in enumerate(labels):
        if li % 10 == 0:
            print(f"  [{li}/{len(labels)}] {label!r}", flush=True)
        lv = vecs.get(label)
        if lv is None:
            continue
        cand_scored = []
        for nid in real_nodes():
            c = nodes[nid]["centroid"]
            if c is not None:
                cand_scored.append((nid, cos(lv, c)))
        cand_scored.sort(key=lambda x: -x[1])

        # ① 与最相似既有节点合并?
        merged = False
        if cand_scored:
            best_nid, best_sim = cand_scored[0]
            if best_sim >= tau_syn:
                if confirm_synonym(client, label, nodes[best_nid]["label"]):
                    nodes[best_nid]["aliases"].append(label)
                    nodes[best_nid]["members"].append(lv)
                    ms = nodes[best_nid]["members"]
                    nodes[best_nid]["centroid"] = [
                        sum(m[i] for m in ms) / len(ms) for i in range(len(lv))]
                    audit.append({"label": label, "action": "merge",
                                  "into": nodes[best_nid]["label"],
                                  "sim": round(best_sim, 3)})
                    merged = True
        if merged:
            continue

        # 首个真实标签:直接挂根,建立首节点
        if not cand_scored:
            nid = new_node_id()
            nodes[nid] = {"label": label, "type": "concept", "aliases": [],
                          "members": [lv], "centroid": lv}
            is_a.append((nid, ROOT_ID))
            audit.append({"label": label, "action": "seed_root_child"})
            continue

        # ② 挂载:候选父节点取 top-K 嵌入近邻
        shortlist = [nodes[nid]["label"] for nid, _ in cand_scored[:topk]]
        verdict = choose_attachment(client, label, shortlist)
        nid = new_node_id()
        if verdict is None or verdict.parent_label == "NONE":
            nodes[nid] = {"label": label, "type": "concept", "aliases": [],
                          "members": [lv], "centroid": lv}
            is_a.append((nid, ROOT_ID))
            audit.append({"label": label, "action": "attach_root_fallback",
                          "reason": "no LLM parent verdict"})
            continue
        parent_nid = next((n for n in real_nodes()
                           if nodes[n]["label"] == verdict.parent_label), None)
        if parent_nid is None:
            nodes[nid] = {"label": label, "type": "concept", "aliases": [],
                          "members": [lv], "centroid": lv}
            is_a.append((nid, ROOT_ID))
            audit.append({"label": label, "action": "attach_root_fallback",
                          "reason": "parent_label not in shortlist"})
            continue

        if verdict.edge_type == "has_property":
            # ③ property 边逐条文本蕴含复核
            ok = check_entailment(client, nodes[parent_nid]["label"], label)
            if ok:
                nodes[nid] = {"label": label, "type": "property",
                              "aliases": [], "members": [lv], "centroid": lv}
                has_property.append((parent_nid, nid))
                audit.append({"label": label, "action": "attach_property",
                              "parent": nodes[parent_nid]["label"],
                              "reason": verdict.reason, "entailment": "PASS"})
            else:
                # 蕴含复核未过:不丢弃、不放行未验证属性边——降级挂根
                # is_a(仍非孤立节点,但不产生可能击穿精确率的幻觉属性边)
                nodes[nid] = {"label": label, "type": "concept", "aliases": [],
                              "members": [lv], "centroid": lv}
                is_a.append((nid, ROOT_ID))
                audit.append({"label": label, "action": "property_rejected",
                              "would_be_parent": nodes[parent_nid]["label"],
                              "reason": verdict.reason,
                              "entailment": "FAIL(downgraded to root is_a)"})
        else:  # is_a
            nodes[nid] = {"label": label, "type": "concept", "aliases": [],
                          "members": [lv], "centroid": lv}
            is_a.append((nid, parent_nid))
            audit.append({"label": label, "action": "attach_is_a",
                          "parent": nodes[parent_nid]["label"],
                          "reason": verdict.reason})

    out_nodes = {nid: {"label": n["label"], "type": n["type"],
                       "aliases": n["aliases"]}
                for nid, n in nodes.items() if nid != ROOT_ID}
    out_nodes[ROOT_ID] = {"label": ROOT_ID, "type": "root", "aliases": []}
    lattice = {
        "nodes": out_nodes,
        "is_a": [list(e) for e in is_a],
        "has_property": [list(e) for e in has_property],
    }
    return lattice, audit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cards-dir", required=True)
    ap.add_argument("--uids", nargs="*", default=None)
    ap.add_argument("--out", default="results/tag_lattice.json")
    ap.add_argument("--audit-out", default=None,
                    help="默认 = <out 同目录>/tag_lattice_audit.jsonl")
    ap.add_argument("--tau-syn", type=float, default=0.86)
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--max-labels", type=int, default=0,
                    help="冒烟/预算控制:只处理前 N 个去重标签(0=不限)。"
                         "每标签最多触发 haiku 3 次调用(同义复核/挂载判定/"
                         "蕴含复核),标签量大时序列调用耗时线性增长。")
    args = ap.parse_args()

    labels = collect_labels(Path(args.cards_dir), args.uids)
    print(f"unique raw labels: {len(labels)}", flush=True)
    if args.max_labels:
        labels = labels[:args.max_labels]
        print(f"capped to {len(labels)} (--max-labels)", flush=True)
    if not labels:
        print("no labels found — nothing to build")
        return
    t0 = time.time()
    vecs = embed_all(labels)
    print(f"embedded in {time.time()-t0:.1f}s")

    client = anthropic.Anthropic()
    lattice, audit = build(labels, vecs, args.tau_syn, args.topk, client)

    n_nodes = len(lattice["nodes"]) - 1  # 不计根
    n_isa = len(lattice["is_a"])
    n_prop = len(lattice["has_property"])
    n_merged = sum(1 for a in audit if a["action"] == "merge")
    print(f"nodes={n_nodes} is_a_edges={n_isa} "
          f"has_property_edges={n_prop} merged={n_merged} "
          f"total_raw_labels={len(labels)}")

    # 不变量自检:除根外每个节点必须有 >=1 条"挂载边"——is_a 的子端,或
    # has_property 的属性端(property 节点本身不重复挂 is_a,一条
    # has_property 边即为其唯一连接)——代码层面 build() 已保证,这里做
    # 落盘前断言。合并进既有节点的别名不单独成节点,天然不在此检查范围。
    connected = ({c for c, _ in lattice["is_a"]} |
                {p for _, p in lattice["has_property"]})
    for nid in lattice["nodes"]:
        if nid == ROOT_ID:
            continue
        assert nid in connected, f"isolated node detected: {nid}"
    print("invariant check: no isolated nodes — PASS")

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(lattice, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    audit_p = Path(args.audit_out or
                   (outp.parent / (outp.stem + "_audit.jsonl")))
    with audit_p.open("w", encoding="utf-8") as f:
        for a in audit:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"-> {outp}\n-> {audit_p}")


if __name__ == "__main__":
    main()
