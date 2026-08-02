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

每个数据集随机抽 20 题(seed 20260802,固定可复现),配对两臂:直读 vs +QVF。读者与抽取器均为 claude-haiku-4-5(最便宜 API 档),判官 claude-opus。

| 数据集 | 直读 | +QVF | 配对 | token 比 | $/题 | 秒/题 |
|---|---|---|---|---|---|---|
| STALE 陷阱场景 | 35% | **45%** | 3胜1负16平 | ×2.9 | 0.006→0.019 | 16.0→15.0 |
| LongMemEval 知识更新 | 75% | 65% | 1胜3负16平 | ×2.2 | 0.006→0.015 | 14.0→8.3 |
| LongMemEval 时间推理 | 50% | 45% | 1胜2负17平 | ×2.4 | 0.007→0.016 | 14.1→8.4 |
| LoCoMo temporal | 55% | 50% | 0胜1负19平 | ×3.2 | 0.002→0.007 | 9.1→7.4 |
| MemConflict | 57% | 57% | 1胜1负18平 | ×3.0 | 0.002→0.008 | **49.1→10.2** |

判读(n=20 为方向性 pilot,扩样验证中):

- **陷阱场景 +10pp**(3胜1负),与既往切片方向一致;
- **泛化基准净中性**:败例解剖显示多数为 API 默认 temperature=1 的采样噪声(两例上下文与直读逐字节相同),一例为聚合类问题被误手术(已定位为规则缺口,见 vNext);
- **token ×2.5,但端到端延迟平均降约 40%**——手术缩短了交付给读者的上下文(MemConflict 49→10 秒/题),延迟是部署侧的真实收益维度;
- LoCoMo 20/20 走门控直通(全部为问历史的题):无伤害符合设计,但为"不干预"付出的抽取开销是决策税,见 vNext 门控前置。

vNext(均需未使用切片冻结验证):冲突路改执行 latest-wins 删除;admit 路单值疑罪直通;聚合类问题(how many/total/since)直通;门控前置微型分类省决策税;API 读者 temperature=0;历史题时间线摘要。

## 运行

```bash
pip install -r requirements.txt
# 本地嵌入(Ollama,用于稠密检索):
ollama pull nomic-embed-text
# 环境变量:ANTHROPIC_API_KEY 必需;QVF_ADAPTER_MODEL=claude-haiku-4-5(抽取器);
# 可选 QVF_JUDGE_MODEL、QVF_ENGINE_SRC

# pilot(每数据集随机 20 题,两臂配对):
QVF_ADAPTER_MODEL=claude-haiku-4-5 python scripts/run_decisive_stale.py \
  --benchmark stale --items 55 --item-offset 145 --sample-n 20 \
  --conditions dense_direct,minimal_rules_v5 --reader claude-haiku-4-5 \
  --out results/pilot_stale.jsonl --resume

# 其余基准:--benchmark longmemeval|locomo|memconflict(配 --qtype,见 --help)
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
