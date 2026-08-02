# QVF 核心控制器

本目录是 QVF 当前工程候选版的最小运行闭包。它接收用户查询和外部检索器返回的 memories，在答案生成之前执行来源校验、时间有效性分析、语义关系判断、证据充分性判断和控制动作生成。

QVF 不负责写入长期记忆，也不替代 BM25、dense、hybrid 或公开 memory retriever。外部系统仍负责初始检索；QVF 只审查已经检索到的证据能否作为 current evidence、history、stale contrast 或 condition-bound evidence 使用。

## 两种输入路径

1. `run_raw_memory_validity_controller`：推荐集成入口。输入原始 query 和 retrieved memories，经可插拔 extractor 形成结构化候选；QVF 逐字段验证 source span 和 provenance，不允许补造时间或置信度。
2. `run_memory_validity_controller`：结构化 fast path。适合上游已经提供规范 entity、slot、value、时间与来源字段的系统。

## 最小运行

```powershell
$env:PYTHONPATH = "src"
python -B examples/run_raw_input_example.py
python -B -m pytest tests/test_core_smoke.py -q
```

Linux/macOS 可将第一行替换为：

```bash
export PYTHONPATH=src
```

运行过程不调用外部 API。示例使用内嵌结构化记录，展示 provenance 验证和 stale/current 控制；真实部署可将任意语义 extractor 作为参数传入。

## 当前完成度

- 已完成：raw-input contract、精确 source-span provenance、双时间语义、future-plan/revocation fail-closed、关系与基数 contract、read-time admission、sidecar 和 answer/retrieve/clarify 动作。
- 当前基线：`query_risk_router.py` 是可审计的确定性 Router，使用通用时间、变化、冲突、条件和证据充分性线索；其 confidence 是启发式优先级分数，不是校准概率。
- 尚未晋升：自适应或 learned Router。已有候选未达到独立跨域 macro-F1、false-safe 和 calibration 门槛，因此不在此核心发布包中。
- 版本边界：本目录是 2026-07-16 的工程候选快照；历史 benchmark 分数不能自动视为该精确 working tree 的重新测分结果。
