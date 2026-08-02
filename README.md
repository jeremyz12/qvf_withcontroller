# QVF v5 — 查询条件化的记忆有效性守卫(零训练)

本仓库是 QVF 的当前版本(2026-08)。旧版符号引擎保留在 `legacy_engine/` 作为语义参考实现与契约校验器;v5 的发布配置用约 30 行可读规则替代了它(held-out 上反而高 4.3 个百分点),并新增了查询时间范围门控。更早版本的完整代码与文档见 git 历史(提交 441103c 及之前)。

## 它解决什么问题

长期记忆助手的一类特定失败:**把旧状态当现状说出来**(用户 3 月说住达尔文、6 月说搬去墨尔本,9 月问"我现在住哪"时答达尔文)。QVF 是检索后、生成前的守卫:陷阱场景把弱读者从 22.9% 拉到 55.7%,其余场景近似直通。

## 流水线

```
查询 + 记忆库
  → 稠密检索 top-10(nomic-embed-text,本地)
  → LLM 跨度锚定抽取(claude-haiku,每题一次调用)
      产出:查询焦点(实体/槽位/是否问现在/时间范围)
           + 逐条记录(逐字原文出处、值、替代关系标签)
      规范:仅显式改变语言才算替代;拿不准标 unresolved
  → 范围门控:past_or_change 查询 → 完整上下文直通(历史是证据不是噪声)
  → 轻规则裁决(~30 行,零 LLM):
      有替代 → 保新删旧(物理移出上下文)
      竞争值无显式语言 → 都保留 + 冲突提示词
      无冲突 → 放行;无记录 → 回退全文
  → 有效性触发补检索(问现在但没找到新状态时,一次,最多补 5 轮)
  → 本地弱读者作答(qwen3:4b,含空答案三级重试)
```

设计原则:**LLM 只做符号够不着的语义解析;所有决策程序是可读代码**。每个被删的记忆轮都能回溯到"哪条记录、哪个规则";证据只删不改写(零幻觉风险);改策略=改一行代码。

## 主要结果(读者 qwen3:4b,判官 claude-opus,判分经人工盲审 100 条 kappa 0.979)

| 基准 | 基线(稠密直读) | QVF | 配对 |
|---|---|---|---|
| STALE held-out(陷阱场景,n=210) | 22.9% | **55.7%**(v4 规则版,opus 抽取) | 75胜6负,CI [+25.2, +40.5] |
| LongMemEval 知识更新 | 78.2% | **84.6%**(v5+haiku) | 8胜3负 |
| MemConflict(分层 150) | 52.7% | 54.7%(v5+haiku) | 8胜5负(三分层全部非负) |
| LME 时间推理 / LoCoMo temporal | 55.6% / 66.0% | 统计中性(门控按设计直通) | — |

去混淆对照:偏新提示基线仅 +3.3%(不显著);引擎消融(本仓库旧引擎)比轻规则低 4.3pp;聚类 bootstrap CI 与读者跨运行噪声地板(≈3%)均已实测。新鲜切片复现与 opus/haiku 抽取器保留率对照进行中,以最终报告为准。

## 运行

```bash
pip install -r requirements.txt
# 本地模型(Ollama):
ollama pull qwen3:4b && ollama pull nomic-embed-text
# 环境变量:ANTHROPIC_API_KEY 必需;可选 QVF_ADAPTER_MODEL(默认 claude-opus-5,
# 发布配置用 claude-haiku-4-5)、QVF_JUDGE_MODEL、QVF_ENGINE_SRC

# 陷阱场景 held-out(STALE items 35-104):
python scripts/run_decisive_stale.py --benchmark stale --items 70 --item-offset 35 \
  --conditions dense_direct,minimal_rules_v5 --reader local:qwen3:4b \
  --out results/heldout.jsonl --resume

# 聚类 bootstrap 置信区间:
python scripts/bootstrap_ci.py

# 检索可达性微基准(免费预检):
python scripts/bench_retrieval.py

# 判分人工审计网页(盲审式):
python scripts/judge_audit_server.py   # → http://127.0.0.1:8765
```

## 数据

数据不随仓库分发,请自行获取:STALE(HuggingFace STALEproj/STALE,CC BY 4.0)、LongMemEval(cleaned 版)、LoCoMo、MemConflict(GitHub TaoZhen1110/MemConflict,**无公开许可证,仅评测使用**)。加载器在 `eval/`。

## 目录

- `qvf/engine_bridge.py` — 抽取契约(Pydantic schema + 提示词)、范围门控 schema、旧引擎桥接、本地读者(含重试梯子)、补检索
- `qvf/retrieval.py` — BM25 与 Ollama 稠密检索(带缓存)
- `qvf/judge.py` — LLM 判官(含降级回退标记)
- `scripts/run_decisive_stale.py` — 全部实验条件的运行器(direct/dense_direct/dense_recency/minimal_rules/minimal_rules_v5/extraction_only/oracle 等)
- `scripts/rejudge_fallback.py` — 降级判分的重判工具
- `scripts/judge_audit_server.py` + `judge_audit.html` — 人工判分盲审网页
- `legacy_engine/` — 旧版确定性有效性引擎(参考实现;engine_bridge 自动发现,或用 QVF_ENGINE_SRC 指定)

研究代码,冻结于 2026-08-02 战役;逐行结果带 extractor/reader 模型 ID 以保证复现链。
