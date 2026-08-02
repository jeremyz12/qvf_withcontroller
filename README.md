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

## 当前结果

协议:配对两臂(直读 vs +QVF),读者与抽取器同档,判官统一 claude-opus(判分经人工盲审 100 条,kappa 0.979);抽取与 haiku 读者 temperature=0。STALE 按题型分层报告——**T1=显式更新语言的陷阱(条目 0-199),T2=隐晦更新的陷阱(条目 200-399)**,数据文件按类型排序,跨类型混报会误导。两个提供商答的是**同一批题**,可逐题对照。

### 主表:STALE 陷阱场景,提供商 × 题型

| 配置 | 题型 | 直读 | +QVF | 配对(符号检验) |
|---|---|---|---|---|
| haiku-4-5 | T1(165 问,条目 145-199) | 30.9% | **39.4%** | **24胜10负,p≈0.024** |
| haiku-4-5 | T2(300 问,两切片合并) | 12-22% | 18-21% | 23胜16负,p≈0.34 **不稳定** |
| gpt-5-mini | T1(同 165 问) | 29.1% | **45.5%** | **32胜5负,p<0.0001** |
| gpt-5-mini | T2(同 300 问) | 13-17% | **23%** | **34胜10负,p<0.001** |

T2 = 条目 225-274 全量(150 问)+ 条目 275-399 随机 50 条目(150 问,seed 20260803)。

### 泛化基准(各随机 50 题,seed 20260802;目标=不伤害)

| 数据集 | haiku:直读→+QVF(配对) | gpt-5-mini:直读→+QVF(配对) |
|---|---|---|
| LongMemEval 知识更新 | 80%→74%(2胜5负) | 84%→86%(3胜2负) |
| LongMemEval 时间推理 | 56%→58%(1胜0负) | 64%→64%(1胜1负) |
| LoCoMo temporal | 64%→68%(3胜1负) | 70%→70%(1胜1负) |
| MemConflict | 56%→54%(0胜1负) | 54%→52%(2胜3负) |

### 成本与延迟(每题,T2 150 问测量)

| 配置 | $:直读→+QVF | 秒:直读→+QVF | 备注 |
|---|---|---|---|
| haiku-4-5 | 0.006→0.021 | 9.9→15.8 | 上下文臃肿的基准反而变快(MemConflict 52→10 秒) |
| gpt-5-mini | 0.003→0.016 | 18→74 | 推理 token 计入输出计费,延迟 ×2-4 |

判读:

- **四格里三格统计显著**。两个改写认知的发现:(1)推理读者在陷阱上并不比弱读者强(直读 29% vs 31%——照样掉坑),但**利用 QVF 交付证据的能力**强得多(+16.4pp vs +8.5pp)——增益 = 交付证据质量 × 读者利用能力,不是单调的"读者越强越无用";(2)T2 上分层:弱读者只能吃手术路(隐晦措辞很少触发→不稳定),推理读者连"保留双方+冲突提示"路也能吃(T2 仍显著);
- **泛化基准双提供商统计中性**(|净胜负|≤3),不伤害目标达成;
- **已证伪并放弃的扩展**(全部在新鲜切片预注册验证):v6 规则扩展(净负)、聚合守卫(无净益)、v7 召回契约(7胜8负——强制枚举改不动抽取召回,缺口是模型能力);30 行规则确认处于局部最优,后续提升在抽取档位与条件化调用;
- 早期 n=20 pilot 与"连续段=随机样本"的假设都曾误导(git 历史可溯),现行结论全部基于 n≥150、随机/全量抽样、题型分层。

vNext:门控前置(离线验证中)、repair 增量抽取(成本 -60% 候选)、疑难查询定向升级抽取器、条件化调用全案。

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
