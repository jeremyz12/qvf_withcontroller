# QVF：检索后长期记忆有效性控制器

QVF 位于**初始记忆检索之后、答案生成之前**。它不重新实现向量数据库，也不写入用户长期记忆；它检查已经检索到的 memories 是否与当前 query 的实体、属性、时间、条件和证据要求一致，然后向下游输出：

- memory role：`current evidence`、`history`、`stale contrast`、`condition-bound evidence`；
- model-facing sidecar：允许当前使用、仅允许历史使用或必须阻断的证据；
- controller action：`answer`、`correct stale premise`、`retrieve` 或 `clarify`。

## 目录

- `01_核心代码`：当前 QVF 工程候选版的最小运行闭包、一个示例和一个 smoke test。
- `02_结果证据`：仅保留聚合结果与证据边界，不包含 API 原始响应或逐 case benchmark 内容。
- `03_说明文档`：系统流程、代码模块、本周改进、相关工作和已知限制。

## 核心流程

```text
query + externally retrieved memories
                |
                v
raw-input / structured-input contract
                |
                v
provenance + temporal + semantic relation validation
                |
                v
query-conditioned admission and evidence sufficiency
                |
                v
sidecar + answer / correct / retrieve / clarify
                |
                v
external answer model
```

## 当前结果概览

| 证据线 | Direct | QVF | 观察 | 边界 |
|---|---:|---:|---|---|
| MemConflict100 | 58/100 | 67/100 | 9 wins / 0 losses | 历史 strict-contract local main 结果；当前精确代码树未重新绑定该分数 |
| LongMemEval-S500 | 195/500 | 195/500 | 0 losses | 历史 official full non-degradation gate |
| LoCoMo79 | 40/79 | 43/79 | 3 wins / 0 losses | supporting pilot only；受 adapter coverage 限制 |
| STALE400 | 177/1200 | 1088/1200 | 14.75% vs 90.67% | 非同期描述；adapter 已提供 exact old/new pair，不能归因为 pure-core QVF |

STALE400 中更可归因的组件消融是：固定 adapter 后，full QVF 为 `1088/1200`，annotation-only 和 no-stale-blocking 均为 `1054/1200`，完整 validity policy 的净增量为 `34/1200 = 2.83pp`。

跨模型 frozen-BM25 结果没有支持“普适精度插件”结论：Claude Haiku 4.5 为 `73 -> 69`，Gemini 3.1 Flash-Lite 为 `61 -> 61`。这说明接口可组合已经实现，但当前 packet/action policy 对不同 reader 的稳健性仍是主要研究问题。

## 运行

```powershell
cd 01_核心代码
$env:PYTHONPATH = "src"
python -B examples/run_raw_input_example.py
python -B -m pytest tests/test_core_smoke.py -q
```

## 版本说明

本仓库保留的是精简研究进度版，而不是完整实验工作区。当前代码快照标记为 engineering candidate；聚合结果均保留原始 evidence label，历史已保护结果不会自动被表述为当前代码的重新测分。
