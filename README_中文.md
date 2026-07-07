# QVF 核心控制器研究进展包

本目录整理的是当前 QVF controller 版本的最小可读材料：核心代码、主要实验结果、结构说明和后续讨论点。重点不是完整复现整个仓库，而是展示 QVF 当前作为“检索之后、生成之前的记忆有效性控制器”的系统设计和阶段性证据。

## 目录结构

| 目录 | 内容 |
|---|---|
| `01_核心代码/` | 当前 controller 相关核心源码、必要兼容封装与关键测试。 |
| `02_结果证据/` | 四类主要实验结果的 summary/report/cases 文件。 |
| `03_说明文档/` | 中文结构说明、结果摘要和后续讨论点。 |

## 当前核心结论

QVF 当前不是一个新的向量数据库、记忆写入系统或完整 RAG 替代方案，而是插在初始检索之后、答案生成之前的 validity controller。它根据 query 与检索到的 memory 之间的关系，决定是否让原始记忆直接进入生成，或是否需要进入 QVF 的有效性控制路径。

当前 controller 的主要作用包括：

1. 判断记忆是 current、archive/history、stale/blocked、uncertain，避免把过期记忆当作当前事实使用。
2. 在 stale/current 冲突、条件范围、时间顺序、source-history 证据不足等场景中构造更明确的 evidence packet。
3. 对普通长期记忆回忆尽量保持 direct-equivalent，避免 QVF 过度干预。
4. 对 source-history 场景增加 temporal focus、causal focus 和 answer-anchor preservation，但只有 source-history 具备可审计时间边界时才提升为独立 QVF 路由。

说明：`public_dataset_adapters.py` 中用于公开数据集长对话抽取的 mutable-state 词表，只是 query expansion / history selection 的透明辅助规则，用来提高相关 history turn 的覆盖率。它不是 QVF controller 的路由逻辑，也不应被表述为核心贡献。

## 最新结果摘要

| 数据集 / 切片 | Direct / Control | QVF controller | 结果含义 |
|---|---:|---:|---|
| MemConflict100 | 57/100 | 71/100 | stale/current 与 conflict 场景显著增益，QVF wins 14 / losses 0。 |
| STALE400 | annotation-only 1054/1200；no-stale-blocking 1054/1200 | full QVF 1088/1200 | full QVF 高于控制组，说明不只是“加标签”，stale blocking 有贡献。 |
| LongMemEval500 | 200/500 | 203/500 | 普通长期记忆非退化，QVF wins 3 / losses 0。 |
| LoCoMo79 | 41/79 | 46/79 | 支持性 pilot 证据，QVF wins 6 / losses 1。 |

## 最新结构改动

本轮最后冲刺新增并验证了一个 source-history route 的细化机制：

- `source_history_focus_context`：从已选 source-history 中抽取通用 focus，而不是把某个具体短语当作触发条件。当前主要包括两类：一类是相对时间窗口，例如“本周/上周末/最近几个月”这类 deictic 或 rolling time expression；另一类是通用因果或动机表达，例如 `because...`、`due to...`、`as a result of...`、`prompted/motivated/led someone to...`、`gave someone motivation/reason/confidence...`。这些 focus 只有在 selected source-history 带有可观察时间边界并与 query 有词项重叠时才会进入 QVF packet。
- `source_history_answer_anchor_context`：从可见 source span 中保留具体活动、地点、方式等 answer anchor，减少长期记忆回答中关键细节被压缩掉的问题。
- `timestamp boundary promotion gate`：只有 selected source-history turn 带有 `timestamp` 或 `observed_at`，这些 source-history packet 才会触发独立 QVF 生成；否则保持 direct-equivalent，避免 LongMemEval 普通回忆被过度干预。

这个 gate 很关键：未加 gate 时，LongMemEval500 上 QVF 为 194/500，低于 Direct 196/500；加 gate 后，LongMemEval500 为 Direct 200/500、QVF 203/500，且 pairwise losses 为 0。

## 结果边界

这些结果应按 evidence label 区分：

- MemConflict100 是 API-backed full 100-case answer eval。
- STALE400 是 sharded full benchmark aggregation，并包含 annotation-only 和 no-stale-blocking 控制。
- LongMemEval500 是当前 500-case full LongMemEval-S answer eval。
- LoCoMo79 是当前可用 QVF-ready 79-case pilot/slice evidence，不应表述为完整 LoCoMo benchmark。

## 测试状态

当前核心测试已通过：

```powershell
python -m unittest discover -s tests
```

最近一次精简包内测试结果：372 tests OK。
