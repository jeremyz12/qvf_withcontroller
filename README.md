# QVF — Query-conditioned Validity Filter

QVF 是一个位于**外部记忆检索之后、答案生成之前**的语义有效性过滤模块。其核心组件
**Semantic Adapter** 将（用户查询 + 原始检索记忆 + 记忆真实元数据）转换为结构化的
**Query-Conditioned Validity Map（查询条件化有效性图）**：

- 原子声明抽取（带记忆 ID 引用与支持片段）
- 声明间语义关系（EQUIVALENT / SUPPORTS / COMPLEMENTS / COEXISTS /
  CONDITIONALLY_COMPATIBLE / CONTRADICTS / SUPERSEDES / UNRELATED / UNKNOWN）
- 查询条件化适用性（APPLICABLE / PARTIALLY_APPLICABLE / NOT_APPLICABLE / UNKNOWN）
- 查询条件化时间标签（CURRENT_FOR_QUERY / HISTORICAL_FOR_QUERY /
  SUPERSEDED_FOR_QUERY / FUTURE_OR_NOT_YET_VALID / TIME_INSENSITIVE / UNKNOWN）
- 记忆角色（DIRECT_SUPPORT / CORROBORATION / UPDATE / CONTRAST / QUALIFIER /
  BACKGROUND / DISTRACTOR / UNRESOLVED）
- 证据充分性（SUFFICIENT / INSUFFICIENT / AMBIGUOUS）与风险标志

核心研究假设：**有效性是查询条件化的** —— 旧记忆并非全局失效（历史问题恰恰需要它），
更新的时间戳本身也不构成取代（supersession 需要同一状态变量上的显式更新或互斥后继状态）。

## 目录结构

```
qvf/                 核心库
  schema.py          Validity Map 的 Pydantic schema（同时作为 API 结构化输出契约）
  prompts.py         Semantic Adapter 系统提示词（研究对象本体）+ 生成器提示词
  adapter.py         Semantic Adapter（Claude API 结构化输出；含 mock 后端）
  retrieval.py       MemoryItem + BM25 检索（各实验条件间保持不变）
  generator.py       BaselineGenerator（普通 RAG）与 QVFGenerator（有效性图条件化）
  judge.py           Claude LLM-as-judge 判分
  pipeline.py        端到端 pipeline（baseline / qvf 两种条件）
  config.py          模型与运行配置（环境变量驱动）
eval/
  datasets.py        LongMemEval 与 LoCoMo 加载器（统一为内部格式）
  download_data.py   数据下载（HuggingFace + GitHub）
  run_eval.py        实验主脚本（跑 pipeline + 判分 + 按题型聚合）
  metrics.py         token-F1 / EM / 聚合
scripts/
  smoke_test.py      合成"知识更新"场景的端到端冒烟测试
docs/
  research_proposal.md   研究方案
  related_work.md        相关工作与定位简报
  paper_outline.md       论文大纲
data/                下载的基准数据（不入库）
results/             实验输出 JSONL
```

## 快速开始

```bash
pip install -r requirements.txt

# 1) 无 API 冒烟测试（验证全流程管线）
QVF_MOCK=1 python scripts/smoke_test.py

# 2) 下载基准数据
python eval/download_data.py

# 3) 真实实验（需要 ANTHROPIC_API_KEY）
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/smoke_test.py                       # 先看合成场景上的真实行为
python eval/run_eval.py --benchmark longmemeval --data data/longmemeval_oracle.json \
    --mode both --limit 20                         # oracle 小规模对比
python eval/run_eval.py --benchmark locomo --data data/locomo10.json \
    --mode both --limit 20
# 主实验用官方推荐的清洗版：data/longmemeval_s_cleaned.json
# 消融加 filter-only 条件：--mode all
```

Windows PowerShell 下设置环境变量用 `$env:QVF_MOCK='1'`、`$env:ANTHROPIC_API_KEY='...'`。

## 实验设计要点

- **对照条件**：baseline（检索→生成）与 qvf（检索→Semantic Adapter→条件化生成）
  共享同一检索器（BM25, top-k）与同一生成模型/解码设置，唯一差异是有效性图的有无。
- **模型**：默认 `claude-opus-5`（适配器/生成器/judge 可分别用
  `QVF_ADAPTER_MODEL` 等环境变量覆盖，便于消融）。
- **判分**：统一 Claude judge（注意：LongMemEval 官方用 GPT-4o judge，绝对数字
  不可与他文直接对表；论文主张以文内对照为准）。LoCoMo 额外报告 token-F1。
- **预期敏感题型**：LongMemEval 的 knowledge-update / temporal-reasoning /
  abstention；LoCoMo 的 temporal / adversarial —— 这些正是查询条件化有效性
  应当起作用的地方。

## 成本提示

LongMemEval-S 每题约 40-60 轮检索上下文；用 `--limit` 控制规模，先在
`longmemeval_oracle`（仅证据会话）上验证行为，再扩到 `_s`。切换
`QVF_ADAPTER_MODEL=claude-sonnet-5` 或 `claude-haiku-4-5` 可做低成本消融。
