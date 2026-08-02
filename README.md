# QVF v5 — 查询条件化的记忆有效性守卫(零训练)

本仓库是 QVF 的当前版本(2026-08)。旧版符号引擎保留在 `legacy_engine/` 作为语义参考实现与契约校验器;v5 用约 30 行可读规则替代了它,并新增了查询时间范围门控。更早版本的完整代码与文档见 git 历史(提交 441103c 及之前)。

## 它解决什么问题

长期记忆助手的一类特定失败:**把旧状态当现状说出来**(用户 3 月说住达尔文、6 月说搬去墨尔本,9 月问"我现在住哪"时答达尔文)。QVF 是检索后、生成前的守卫:识别查询意图,把已被取代的旧状态从上下文中物理移出,其余场景近似直通。

## 流水线

```
查询 + 记忆库
  → 稠密检索 top-10(nomic-embed-text,本地)
  → LLM 跨度锚定抽取(claude-haiku-4-5,每题一次调用)
      产出:查询焦点(实体/槽位/是否问现在/时间范围)
           + 逐条记录(逐字原文出处、值、替代关系标签)
      规范:仅显式改变语言才算替代;拿不准标 unresolved
  → 范围门控:past_or_change 查询 → 完整上下文直通(历史是证据不是噪声)
  → 轻规则裁决(~30 行,零 LLM):
      有替代 → 保新删旧(物理移出上下文)
      竞争值无显式语言 → 都保留 + 冲突提示词
      无冲突 → 放行;无记录 → 回退全文
  → 有效性触发补检索(问现在但没找到新状态时,一次,最多补 5 轮)
  → 读者作答(claude-haiku-4-5;--reader 可换任意 Anthropic 型号)
```

设计原则:**LLM 只做符号够不着的语义解析;所有决策程序是可读代码**。每个被删的记忆轮都能回溯到"哪条记录、哪个规则";证据只删不改写(零幻觉风险);改策略=改一行代码。

## 当前结果(pilot)

协议:STALE 取从未使用过的条目 225-274(50 个 case × 3 种问法 = 150 问,保留条目结构);其余基准各随机抽 50 题(seed 20260802,固定可复现)。配对两臂:直读 vs +QVF,读者与抽取器同档,判官统一 claude-opus(判分经人工盲审 100 条,kappa 0.979);抽取与 haiku 读者 temperature=0。两张表答的是**同一批题**,可逐题对照。

### 表一:claude-haiku-4-5(读者 + 抽取器)

| 数据集 | 直读 | +QVF | 配对 | token 比 | $/题 | 秒/题 |
|---|---|---|---|---|---|---|
| STALE 陷阱(150) | 12.0% | **18.0%** | **12胜3负**135平(p≈0.035) | ×3.3 | 0.006→0.021 | 9.9→15.8 |
| LongMemEval 知识更新(50) | 80% | 74% | 2胜5负43平 | ×2.3 | 0.007→0.016 | 14.0→**9.4** |
| LongMemEval 时间推理(50) | 56% | 58% | 1胜0负49平 | ×2.3 | 0.007→0.016 | 14.0→**8.4** |
| LoCoMo temporal(50) | 64% | 68% | 3胜1负46平 | ×3.1 | 0.002→0.007 | 6.3→7.3 |
| MemConflict(50) | 56% | 54% | 0胜1负49平 | ×3.6 | 0.002→0.009 | **51.8→10.1** |

### 表二:gpt-5-mini(读者 + 抽取器,判官不变)

| 数据集 | 直读 | +QVF | 配对 | token 比 | $/题 | 秒/题 |
|---|---|---|---|---|---|---|
| STALE 陷阱(150) | 13.3% | **23.3%** | **19胜4负**127平(p≈0.003) | ×3.6 | 0.003→0.016 | 18.0→74.1 |
| LongMemEval 知识更新(50) | 84% | 86% | 3胜2负45平 | ×2.7 | 0.002→0.011 | 17.2→48.6 |
| LongMemEval 时间推理(50) | 64% | 64% | 1胜1负48平 | ×2.6 | 0.002→0.010 | 17.9→40.5 |
| LoCoMo temporal(50) | 70% | 70% | 1胜1负48平 | ×3.2 | 0.001→0.006 | 9.9→29.0 |
| MemConflict(50) | 54% | 52% | 2胜3负45平 | ×4.6 | 0.001→0.010 | 56.2→55.3 |

判读:

- **陷阱场景的增益在两个提供商上同时统计显著**(haiku +6.0pp,gpt-5-mini +10.0pp,符号检验均 p<0.05)——机制跨提供商、跨读者架构(非推理/推理)成立;
- **四个泛化基准全部统计中性**;haiku 的知识更新 2胜5负与聚合类问题误手术的已知规则缺口一致,修复在验证队列;
- **成本与延迟不跨提供商**:输入 token 两家一致 ×2.3~3.6(抽取要重读检索上下文);输出端推理模型的思考 token 计入计费,gpt 的 +QVF 输出是 haiku 的 8 倍。延迟上,非推理读者常因交付上下文变短而**变快**(MemConflict 52→10 秒),推理读者则 ×2~4 变慢——部署建议因此分叉:非推理读者可常开,推理读者应配条件化调用;
- 早期 n=20 pilot 的数字(git 历史 316025f)已被本轮取代:小样本曾双向误导(高估 haiku 增益、误判 gpt 无效),本仓库结论以 n≥50 为准。

vNext(均需未使用切片冻结验证):聚合类问题(how many/total/since)直通;门控前置微型分类省决策税;抽取契约召回修复(逐条 memory 强制判定);repair 增量抽取;条件化调用全案。

## 运行

```bash
pip install -r requirements.txt
# 本地嵌入(Ollama,用于稠密检索):
ollama pull nomic-embed-text
# 环境变量:ANTHROPIC_API_KEY 必需;QVF_ADAPTER_MODEL=claude-haiku-4-5(抽取器);
# 可选 QVF_JUDGE_MODEL、QVF_ENGINE_SRC

# STALE 50 case × 3 问(两臂配对):
QVF_ADAPTER_MODEL=claude-haiku-4-5 python scripts/run_decisive_stale.py \
  --benchmark stale --items 50 --item-offset 225 \
  --conditions dense_direct,minimal_rules_v5 --reader claude-haiku-4-5 \
  --out results/stale_n50.jsonl --resume

# gpt-5-mini 版(需 OPENAI_API_KEY;判官仍为 claude-opus):
# QVF_ADAPTER_MODEL=openai:gpt-5-mini ... --reader openai:gpt-5-mini
# 其余基准:--benchmark longmemeval|locomo|memconflict 配 --qtype 与 --sample-n 50
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

- `qvf/engine_bridge.py` — 抽取契约(Pydantic schema + 提示词)、范围门控 schema、旧引擎桥接、本地读者支持、补检索
- `qvf/retrieval.py` — BM25 与 Ollama 稠密检索(带缓存)
- `qvf/judge.py` — LLM 判官(含降级回退标记)
- `scripts/run_decisive_stale.py` — 全部实验条件的运行器(dense_direct/minimal_rules_v5/extraction_only/oracle 等;--sample-n 随机抽样)
- `scripts/rejudge_fallback.py` — 降级判分的重判工具
- `scripts/judge_audit_server.py` + `judge_audit.html` — 人工判分盲审网页
- `legacy_engine/` — 旧版确定性有效性引擎(参考实现;engine_bridge 自动发现,或用 QVF_ENGINE_SRC 指定)

研究代码;逐行结果带 extractor/reader 模型 ID 与 token/延迟字段以保证复现链与成本核算。
