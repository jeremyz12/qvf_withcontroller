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

# 成本记账(list price,未计缓存折扣;仅用于"记录成本与时间"纪律的
# calibrate/build 侧自报,不影响任何建格逻辑)。Haiku 4.5 与
# text-embedding-3-small 的公开单价(每百万 token,美元)。
_PRICE_HAIKU_IN = 1.00
_PRICE_HAIKU_OUT = 5.00
_PRICE_EMBED = 0.02
USAGE = {"haiku_in": 0, "haiku_out": 0, "haiku_calls": 0, "embed_tokens": 0}


def usage_cost_usd() -> float:
    return (USAGE["haiku_in"] / 1e6 * _PRICE_HAIKU_IN +
            USAGE["haiku_out"] / 1e6 * _PRICE_HAIKU_OUT +
            USAGE["embed_tokens"] / 1e6 * _PRICE_EMBED)


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
        try:
            USAGE["embed_tokens"] += int(r.usage.total_tokens)
        except Exception:  # noqa: BLE001
            pass
        for lab, d in zip(batch, r.data):
            v = d.embedding
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out[lab] = [x / n for x in v]
    return out


def cos(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _record_usage(resp) -> None:
    try:
        USAGE["haiku_in"] += int(resp.usage.input_tokens)
        USAGE["haiku_out"] += int(resp.usage.output_tokens)
        USAGE["haiku_calls"] += 1
    except Exception:  # noqa: BLE001
        pass


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
        _record_usage(resp)
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
        _record_usage(resp)
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
        _record_usage(resp)
        p = resp.parsed_output
        return bool(p and p.holds)
    except Exception:  # noqa: BLE001
        return False


# ── 主构建流程 ───────────────────────────────────────────────
def build(labels: List[str], vecs: Dict[str, List[float]],
         tau_syn: float, topk: int, client,
         use_entailment: bool = True,
         use_merge_attach: bool = True) -> Tuple[dict, List[dict]]:
    """use_entailment=False / use_merge_attach=False 是阶段 A 消融专用旁路,
    默认均 True = 与本函数此前行为逐字节一致(两条调和不变量生效)。
    - use_merge_attach=False:跳过同义合并与挂载判定,每个标签各自直接挂根
      (is_a -> __root__),不产生 has_property 边——用于测出"没有格结构、
      只剩精确字符串匹配"这条基线相对全量格的 P/R 差值。
    - use_entailment=False:has_property 边跳过逐条文本蕴含复核,LLM 判定
      has_property 即直接采信——用于测出蕴含复核对精确率的保护量。
    """
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
        if not use_merge_attach:
            # 消融:直接挂根,不合并、不判父、不产生 has_property。
            nid = new_node_id()
            nodes[nid] = {"label": label, "type": "concept", "aliases": [],
                          "members": [lv], "centroid": lv}
            is_a.append((nid, ROOT_ID))
            audit.append({"label": label, "action": "flat_no_merge_attach"})
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
            # ③ property 边逐条文本蕴含复核(消融 use_entailment=False 时跳过)
            ok = True if not use_entailment else check_entailment(
                client, nodes[parent_nid]["label"], label)
            if ok:
                nodes[nid] = {"label": label, "type": "property",
                              "aliases": [], "members": [lv], "centroid": lv}
                has_property.append((parent_nid, nid))
                audit.append({"label": label, "action": "attach_property",
                              "parent": nodes[parent_nid]["label"],
                              "reason": verdict.reason,
                              "entailment": "SKIPPED" if not use_entailment
                                            else "PASS"})
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
    print(f"usage: haiku_calls={USAGE['haiku_calls']} "
          f"haiku_in={USAGE['haiku_in']} haiku_out={USAGE['haiku_out']} "
          f"embed_tokens={USAGE['embed_tokens']} "
          f"cost_usd~{usage_cost_usd():.4f}")


# ── calibrate 子命令(阶段 A):dev 100 题上扫 (tau_syn, 读取侧回退阈值
# QVF_TAG_LATTICE_TAU) 联合网格,选"精确率>=--target-precision 前提下召回
# 最大"的工作点;并在选中的 tau_syn 上做两条调和不变量的开/关消融。
# 纯离线评估,不改动任何冻结路径;检索模拟直接 import scripts/tag_lattice.py
# 里对外唯一入口 TagLattice.satisfies() + embed_similar(),与读取侧
# complex_query_arm.py(QVF_TAG_LATTICE=1)用的是同一份格闭包判定代码。
# ──────────────────────────────────────────────────────────────

_STOPWORDS = {
    "the", "and", "with", "for", "from", "this", "that", "was", "were",
    "have", "has", "had", "during", "after", "before", "using", "into",
    "onto", "about", "their", "they", "them", "his", "her", "she", "him",
    "you", "your", "not", "but", "are", "been", "will", "who", "what",
    "when", "where", "which",
}


def _words(s: str) -> set:
    import re as _re
    return {w for w in _re.findall(r"[a-z0-9]+", str(s).lower())
            if len(w) >= 3 and w not in _STOPWORDS}


def _value_match(a: str, b: str, thresh: float) -> bool:
    """gold.item.value 与新建卡片 record.value 的近似同源判定(阶段 A 已知
    局限:gold 的 record_id 出自旧版无标签卡片 results/wt_cards/{uid}.json
    的抽取顺序,与本阶段 QVF_CARD_TAGS=2 重建的卡片是不同一次 LLM 抽取,
    record_id 不能跨版本对齐,故退化用词集 Jaccard 重叠度近似"同一事实"——
    这是 calibrate 的已知简化,在 results/tag_lattice_calib.json 的
    "caveats" 字段里如实注明,不作为阶段二判官裁决的替代)。"""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    inter = len(wa & wb)
    union = len(wa | wb)
    return union > 0 and (inter / union) >= thresh


def _load_dev_rows(questions_path: Path, split: str,
                   pop_uids: set) -> List[dict]:
    rows = []
    with questions_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("split") == split and r["uid"] in pop_uids:
                rows.append(r)
    return rows


def _gold_items(row: dict) -> List[dict]:
    if row["qtype"] == "s7div_onset":
        g = row["gold"]
        return [{"value": g.get("value", ""), "date": g.get("date", "")}]
    return [{"value": it.get("value", ""), "date": it.get("date", "")}
            for it in row.get("gold", {}).get("items", [])]


def _load_cards_dir(cards_dir: Path) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for f in sorted(cards_dir.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        out[f.stem] = d.get("records", [])
    return out


def _prewarm_embed_fallback_cache(cards_by_uid: Dict[str, List[dict]],
                                  dev_rows: List[dict]) -> None:
    """embed_similar() 逐对(2 条文本)单独探测缓存/退 API,网格扫描里对
    同一批标签反复调用会退化成一堆 2 条一批的小网络请求,极慢。这里在扫描
    前用 tag_lattice._embed() 一次性大批量(内部按 256 分片)把本次评估会
    用到的全部卡片标签 + 全部 query 的 gloss 都灌进磁盘缓存,之后
    embed_similar() 全部命中缓存,网格扫描阶段零新增网络调用。"""
    import scripts.tag_lattice as tl  # noqa: PLC0415
    texts = set()
    for recs in cards_by_uid.values():
        for rec in recs:
            for t in (rec.get("value_tags") or []):
                texts.add(tl._norm(t))
    for row in dev_rows:
        texts.add(tl._norm(row["attribute_gloss"]))
    texts.discard("")
    tl._embed(sorted(texts))


def _retrieve(records: List[dict], query_tag: str, lattice,
             use_embed_fallback: bool, tau: float) -> List[dict]:
    import scripts.tag_lattice as tl  # noqa: PLC0415 (延迟 import,与读取侧一致)
    hit = []
    for rec in records:
        for tag in (rec.get("value_tags") or []):
            if lattice.satisfies(tag, query_tag):
                hit.append(rec)
                break
            if use_embed_fallback and tl.embed_similar(tag, query_tag, tau):
                hit.append(rec)
                break
    return hit


def _score(cards_by_uid: Dict[str, List[dict]], dev_rows: List[dict],
          lattice, use_embed_fallback: bool, tau: float,
          match_thresh: float) -> dict:
    tp = fp = fn = 0
    n_rows = 0
    for row in dev_rows:
        records = cards_by_uid.get(row["uid"])
        if records is None:
            continue
        n_rows += 1
        retrieved = _retrieve(records, row["attribute_gloss"],
                              lattice, use_embed_fallback, tau)
        gold = _gold_items(row)
        gold_used = [False] * len(gold)
        row_tp = 0
        for rec in retrieved:
            matched = False
            for gi, g in enumerate(gold):
                if gold_used[gi]:
                    continue
                if _value_match(g["value"], rec.get("value", ""),
                                match_thresh):
                    gold_used[gi] = True
                    matched = True
                    row_tp += 1
                    break
            if not matched:
                fp += 1
        tp += row_tp
        fn += gold_used.count(False)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {"n_dev_rows": n_rows, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4), "recall": round(recall, 4)}


def calibrate_main() -> None:
    ap = argparse.ArgumentParser(
        description="阶段 A: dev 上扫 (tau_syn, QVF_TAG_LATTICE_TAU) 联合"
                     "网格,选精确率达标前提下召回最大的工作点;并做两条"
                     "调和不变量的开/关消融。")
    ap.add_argument("--cards-dir", default="results/wt_cards_opentags")
    ap.add_argument("--questions", default="data/wsc_s7div.jsonl")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--out", default="results/tag_lattice_calib.json")
    ap.add_argument("--lattice-out", default="results/tag_lattice.json",
                    help="选中 tau_syn(全量不变量)的格落盘到这里,"
                         "供阶段二/complex_query_arm.py 读取")
    ap.add_argument("--tau-syn-grid", default="0.80,0.86")
    ap.add_argument("--read-tau-grid",
                    default="0.30,0.40,0.50,0.60,0.70,0.80,0.90")
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--target-precision", type=float, default=0.95)
    ap.add_argument("--match-thresh", type=float, default=0.30,
                    help="gold vs 卡片 value 词集 Jaccard 判同阈值(见 "
                         "_value_match 的已知局限说明)")
    ap.add_argument("--max-labels", type=int, default=0,
                    help="预算控制:tau_syn 网格里每个候选(=生产格 + "
                         "no_entailment 消融复用同一子集)只处理前 N 个去重"
                         "标签(0=不限)。no_merge_or_attach 消融不受此限——"
                         "该分支跳过全部 haiku 调用(见 build() 里的旁路),"
                         "近乎零成本,永远在全量标签上跑,给出全量覆盖的"
                         "'无格结构基线'对照。")
    args = ap.parse_args()

    cards_dir = Path(args.cards_dir)
    cards_by_uid = _load_cards_dir(cards_dir)
    pop_uids = set(cards_by_uid.keys())
    dev_rows = _load_dev_rows(Path(args.questions), args.split, pop_uids)
    print(f"card population: {len(pop_uids)} uids; "
          f"dev rows in population: {len(dev_rows)}", flush=True)

    all_labels = collect_labels(cards_dir, None)
    labels = all_labels[:args.max_labels] if args.max_labels else all_labels
    print(f"unique raw labels: total={len(all_labels)} "
          f"capped_for_haiku_builds={len(labels)}", flush=True)
    t0 = time.time()
    vecs = embed_all(all_labels)  # 全量嵌入很便宜,给 no_merge_attach 消融用
    print(f"embedded {len(all_labels)} labels in {time.time()-t0:.1f}s",
          flush=True)
    t0 = time.time()
    _prewarm_embed_fallback_cache(cards_by_uid, dev_rows)
    print(f"prewarmed embed-fallback cache in {time.time()-t0:.1f}s",
          flush=True)
    client = anthropic.Anthropic()

    tau_syn_grid = [float(x) for x in args.tau_syn_grid.split(",") if x]
    read_tau_grid = [float(x) for x in args.read_tau_grid.split(",") if x]

    curve = []
    lattices_by_tau_syn = {}
    for tau_syn in tau_syn_grid:
        print(f"-- building lattice tau_syn={tau_syn} "
              f"(n_labels={len(labels)}) --", flush=True)
        lattice_dict, audit = build(labels, vecs, tau_syn, args.topk, client)
        lattices_by_tau_syn[tau_syn] = (lattice_dict, audit)
        tmp_p = Path(f"results/_calib_lattice_{tau_syn}.json")
        tmp_p.write_text(json.dumps(lattice_dict, ensure_ascii=False),
                         encoding="utf-8")
        import scripts.tag_lattice as tl  # noqa: PLC0415
        lat_obj = tl.TagLattice(tmp_p)
        for read_tau in read_tau_grid:
            sc = _score(cards_by_uid, dev_rows, lat_obj, True, read_tau,
                       args.match_thresh)
            sc.update({"tau_syn": tau_syn, "read_tau": read_tau})
            curve.append(sc)
            print(f"   read_tau={read_tau} P={sc['precision']} "
                  f"R={sc['recall']} tp={sc['tp']} fp={sc['fp']} "
                  f"fn={sc['fn']}", flush=True)
        # 该 tau_syn 下也报纯格闭包(不退嵌入回退)的 P/R,供审计对比
        sc_no_fb = _score(cards_by_uid, dev_rows, lat_obj, False, 0.0,
                          args.match_thresh)
        sc_no_fb.update({"tau_syn": tau_syn, "read_tau": None,
                         "note": "no_embed_fallback"})
        curve.append(sc_no_fb)

    # 选点:精确率 >= target 里挑召回最大;若无一达标,退而挑精确率最高者
    # (如实标注 target_met=false,不得假装达标)。
    qualifying = [c for c in curve if c.get("read_tau") is not None
                 and c["precision"] >= args.target_precision]
    if qualifying:
        best = max(qualifying, key=lambda c: (c["recall"], c["precision"]))
        target_met = True
    else:
        scored = [c for c in curve if c.get("read_tau") is not None]
        best = max(scored, key=lambda c: (c["precision"], c["recall"]))
        target_met = False
    print(f"chosen point: tau_syn={best['tau_syn']} "
          f"read_tau={best['read_tau']} P={best['precision']} "
          f"R={best['recall']} target_met={target_met}", flush=True)

    # 最终格(全量两条不变量)落盘到 --lattice-out,供阶段二读取侧使用
    best_lattice, best_audit = lattices_by_tau_syn[best["tau_syn"]]
    n_nodes = len(best_lattice["nodes"]) - 1
    n_isa = len(best_lattice["is_a"])
    n_prop = len(best_lattice["has_property"])
    n_merged = sum(1 for a in best_audit if a["action"] == "merge")
    n_prop_rejected = sum(1 for a in best_audit
                          if a["action"] == "property_rejected")
    connected = ({c for c, _ in best_lattice["is_a"]} |
                {p for _, p in best_lattice["has_property"]})
    for nid in best_lattice["nodes"]:
        if nid == ROOT_ID:
            continue
        assert nid in connected, f"isolated node detected: {nid}"
    lat_out = Path(args.lattice_out)
    lat_out.parent.mkdir(parents=True, exist_ok=True)
    lat_out.write_text(json.dumps(best_lattice, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    audit_out = lat_out.parent / (lat_out.stem + "_audit.jsonl")
    with audit_out.open("w", encoding="utf-8") as f:
        for a in best_audit:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"production lattice -> {lat_out} (tau_syn={best['tau_syn']}) "
          f"nodes={n_nodes} is_a={n_isa} has_property={n_prop} "
          f"merged={n_merged} property_rejected={n_prop_rejected}")

    # ── 消融:两条不变量各自开/关,固定在选中的 tau_syn / read_tau ──
    print("-- ablations at chosen tau_syn --", flush=True)
    lat_no_ent_dict, _ = build(labels, vecs, best["tau_syn"], args.topk,
                               client, use_entailment=False)
    tmp_ne = Path("results/_calib_lattice_no_entailment.json")
    tmp_ne.write_text(json.dumps(lat_no_ent_dict, ensure_ascii=False),
                      encoding="utf-8")
    import scripts.tag_lattice as tl  # noqa: PLC0415
    sc_no_ent = _score(cards_by_uid, dev_rows, tl.TagLattice(tmp_ne), True,
                       best["read_tau"], args.match_thresh)

    # no_merge_attach 分支在 build() 里对每个标签零 haiku 调用(直接挂根),
    # 近乎零成本 —— 在全量 all_labels(不受 --max-labels 限制)上跑,给出
    # 覆盖全量标签的"无格结构"基线,而不仅是与生产格同一子集。
    lat_no_ma_dict, _ = build(all_labels, vecs, best["tau_syn"], args.topk,
                              client, use_merge_attach=False)
    tmp_nm = Path("results/_calib_lattice_no_merge_attach.json")
    tmp_nm.write_text(json.dumps(lat_no_ma_dict, ensure_ascii=False),
                      encoding="utf-8")
    sc_no_ma = _score(cards_by_uid, dev_rows, tl.TagLattice(tmp_nm), True,
                      best["read_tau"], args.match_thresh)

    sc_full = next(c for c in curve if c.get("read_tau") == best["read_tau"]
                   and c["tau_syn"] == best["tau_syn"])
    print(f"full(both invariants on): P={sc_full['precision']} "
          f"R={sc_full['recall']}")
    print(f"no_entailment_check:      P={sc_no_ent['precision']} "
          f"R={sc_no_ent['recall']}  dP={sc_no_ent['precision']-sc_full['precision']:+.4f}"
          f" dR={sc_no_ent['recall']-sc_full['recall']:+.4f}")
    print(f"no_merge_or_attach:       P={sc_no_ma['precision']} "
          f"R={sc_no_ma['recall']}  dP={sc_no_ma['precision']-sc_full['precision']:+.4f}"
          f" dR={sc_no_ma['recall']-sc_full['recall']:+.4f}")

    out = {
        "generated": "calibrate subcommand, scripts/build_tag_lattice.py",
        "cards_dir": str(cards_dir),
        "population_uids": sorted(pop_uids),
        "n_population_uids": len(pop_uids),
        "dev_rows_evaluated": len(dev_rows),
        "n_unique_labels_total": len(all_labels),
        "n_unique_labels_capped_for_haiku_builds": len(labels),
        "max_labels_cap": args.max_labels,
        "target_precision": args.target_precision,
        "match_thresh_jaccard": args.match_thresh,
        "pr_curve": curve,
        "chosen": {"tau_syn": best["tau_syn"],
                   "QVF_TAG_LATTICE_TAU": best["read_tau"],
                   "precision": best["precision"],
                   "recall": best["recall"],
                   "target_precision_met": target_met},
        "production_lattice": {
            "path": str(lat_out), "nodes": n_nodes, "is_a_edges": n_isa,
            "has_property_edges": n_prop, "merged": n_merged,
            "property_rejected": n_prop_rejected,
        },
        "ablation_at_chosen_point": {
            "full_both_invariants_on": {
                **sc_full, "n_labels_processed": len(labels)},
            "no_entailment_check": {
                **sc_no_ent, "n_labels_processed": len(labels),
                "note": "same capped label subset as production build"},
            "no_merge_or_attach": {
                **sc_no_ma, "n_labels_processed": len(all_labels),
                "note": "zero haiku calls in this mode, ran on FULL "
                        "uncapped vocabulary"},
        },
        "usage": dict(USAGE),
        "usage_cost_usd_estimate": round(usage_cost_usd(), 4),
        "caveats": [
            "gold.record_id 出自旧版无标签 results/wt_cards/ 卡片的抽取"
            "顺序,与本阶段 QVF_CARD_TAGS=2 重建卡片是不同一次 LLM 抽取,"
            "record_id 不可跨版本对齐;本 calibrate 改用 gold.value 与卡片"
            "record.value 的词集 Jaccard 重叠(阈值 match-thresh)做近似"
            "同一事实判定,非阶段二判官(qvf/judge.py)的语义裁决,数字仅供"
            "阈值选点参考,不是最终 P1/P2 主判据的替代。",
            "query_tag 取 attribute_gloss 原字段直接探测格,未经过"
            "complex_query_arm.py 真实查询编译器产出 plan.tag——阶段二"
            "接入编译器后的真实 P/R 可能与本表不同,需要复测。",
            f"仅覆盖 {len(pop_uids)}/71 个 dev uid(受限于本阶段只建了 30 "
            "张卡);dev 100 题里落在这 30 uid 内的子集才被评估,非全量 "
            "dev 100 题。",
            f"预算发现:30 张卡实测去重 value_tags 词表达 {len(all_labels)} "
            "条(远超 8-uid 冒烟阶段 772 条的量级),按实测 haiku 单价"
            "(~$0.0008/标签)全量跑一次生产格已接近 $1.5+,tau_syn 网格"
            "(2 候选)+ no_entailment 消融再各乘一次,远超本阶段 ≤$3 预算"
            "上限。故实际执行做了两处降级(如实记录,非隐瞒):① tau_syn 只"
            "取单点(生产格未做 tau_syn 网格搜索,--tau-syn-grid 传入的仍是"
            "冻结默认 0.86,与 8-uid 冒烟阶段验证过的值一致);② 生产格 / "
            "no_entailment 消融只处理前 --max-labels 个去重标签(见 "
            "n_unique_labels_capped_for_haiku_builds vs n_unique_labels_"
            "total),未覆盖的标签在读取侧仍可命中嵌入回退(embed_similar 不"
            "要求标签是格节点),故检索并非对未入格标签完全失效,但格闭包"
            "(is_a/has_property)带来的增益只在入格的这部分标签上被验证。"
            "no_merge_or_attach 消融例外:该分支零 haiku 调用,在全量标签"
            "上运行,是唯一的全覆盖测量。",
        ],
    }
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"-> {outp}")
    print(f"usage: haiku_calls={USAGE['haiku_calls']} "
          f"haiku_in={USAGE['haiku_in']} haiku_out={USAGE['haiku_out']} "
          f"embed_tokens={USAGE['embed_tokens']} "
          f"cost_usd~{usage_cost_usd():.4f}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        sys.argv.pop(1)
        calibrate_main()
    else:
        main()
