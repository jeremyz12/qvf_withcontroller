# 本地编译器评测 · 阶段 0(能力下限测量)

日期:2026-08-15;评测线:`scripts/eval_local_compiler.py`;参考集 369 题(qid 去重、判对且 compile_ok 的最新跑;S7 严格档 precision=1 & recall=1 & 零幻觉)。

提示词:与 haiku 线逐字节相同(import 冻结臂 COMPILE_PROMPT);temperature 0,num_predict 512,重试 ≤3,format=json + think=false 三档统一。零 API LLM 成本。

## 总表

| 模型 | n | 严格 JSON 合法率(首次) | 编译成功率(≤3 试) | 计划一致率 | 执行等价率 | 每题延迟中位 | 吞吐 | 模型驻留(ollama ps) | nvidia-smi 峰值(全卡) |
|---|---|---|---|---|---|---|---|---|---|
| qwen3:4b | 369 | 369/369 = 100.0% | 369/369 = 100.0% | 365/369 = 98.9% | 365/369 = 98.9% | 2.49s | 24.1 题/分 | 3.2 GB, 100% GPU | 15592 MiB(跑前基线 15410) |
| qwen3:8b | 369 | 369/369 = 100.0% | 369/369 = 100.0% | 369/369 = 100.0% | 369/369 = 100.0% | 2.49s | 24.0 题/分 | 5.6 GB, 100% GPU | 15617 MiB(跑前基线 11795) |
| qwen3:14b | 369 | 369/369 = 100.0% | 369/369 = 100.0% | 369/369 = 100.0% | 369/369 = 100.0% | 2.48s | 23.3 题/分 | 9.6 GB, 100% GPU | 11857 MiB(跑前基线 2144) |

显存注记:nvidia-smi 为全卡占用,评测期间桌面/其他应用共占(4b 跑时用户游戏在前台,基线 15.4GB;8b 跑时游戏中途退出);模型真实驻留以 ollama ps 列为准,三档均 100% GPU、未发生 CPU 卸载。

## 分算子(计划一致 / 执行等价)

| 算子 | n | qwen3:4b | qwen3:8b | qwen3:14b |
|---|---|---|---|---|
| count_before | 73 | 73/73 · exec 73/73 | 73/73 · exec 73/73 | 73/73 · exec 73/73 |
| count_changes | 66 | 66/66 · exec 66/66 | 66/66 · exec 66/66 | 66/66 · exec 66/66 |
| first_last | 74 | 74/74 · exec 74/74 | 74/74 · exec 74/74 | 74/74 · exec 74/74 |
| join_at_change | 21 | 17/21 · exec 17/21 | 21/21 · exec 21/21 | 21/21 · exec 21/21 |
| longest | 69 | 69/69 · exec 69/69 | 69/69 · exec 69/69 | 69/69 · exec 69/69 |
| tag_filter | 16 | 16/16 · exec 16/16 | 16/16 · exec 16/16 | 16/16 · exec 16/16 |
| tag_trend | 50 | 50/50 · exec 50/50 | 50/50 · exec 50/50 | 50/50 · exec 50/50 |

### 不一致主因(mismatch_field 计数)

- **qwen3:4b**:join_at_change.slot ×4
- **qwen3:8b**:无不一致
- **qwen3:14b**:无不一致

### qwen3:4b 全部 4 处失误的定性(唯一失败模式:join 锚反转)

4 题全部是 S6 "When I moved to X, what was my employer at that time?" 句式:
参考计划锚=residence(变更事件)、slot2=employer(被问属性),4b 一律反填
(锚=employer、slot2=residence),执行输出随之不同,exec 也判不等。
qid:wikiM003-Q106386024_s6b2、wikiM019-Q13205835_s6b2/s6b3/s6b4。
8b/14b 在同 4 题上全对。这是唯一失败模式,其余 6 算子三档全 100%。

## 判决

猜想被证实:本地小模型无需任何微调即可胜任该编译任务——三档全部越过
90% 绿灯线,且远超线。

- **qwen3:4b**:计划一致 98.9%,执行等价 98.9% → 绿灯(≥90%,可进阶段 1 蒸馏)
- **qwen3:8b**:计划一致 100.0%,执行等价 100.0% → 绿灯(≥90%,可进阶段 1 蒸馏)
- **qwen3:14b**:计划一致 100.0%,执行等价 100.0% → 绿灯(≥90%,可进阶段 1 蒸馏)

阶段 1 蒸馏的取舍:8b 已在全部 369 题与参考计划完全一致,14b 相对 8b
零增益(延迟同为 ~2.5s,驻留多 4GB)——若做蒸馏/部署,**目标应选 4b**
(唯一有可测差距的档,差距集中在 join_at_change 锚方向这一单点,4 例
即可构造针对性训练对);8b 可作为"零训练即达标"的直接部署候选。也就是
说,阶段 1 蒸馏对 8b/14b 无必要,对 4b 是低成本可选项而非必需。

## 口径与注记(如实入档)

1. **覆盖 7/11 算子**:current / point_in_time / trajectory / premise_check
   四个基础算子在 results/ 中无任何历史编译计划行(S1-S4 走冻结路由不产
   plan 字段),本轮未测,结论不外推到这 4 算子。
2. **S7 参考集取严格档**(precision=1 且 recall=1 且零幻觉,66 行);宽档
   (precision=1,93 行)未采用,避免把"召回不全的计划"当参考。
3. **解析层差异**:haiku 线用 messages.parse 结构化输出,本地线用 ollama
   `format:"json"` + pydantic CompiledPlan 校验(同一模型类,import 冻结
   模块);qwen3 系统一 `think:false`(推理参数,三档一致,不改提示词
   字节)。提示词 system/user 结构与字节均与 haiku 线相同。
4. **金答案与判官标签零泄漏**:被测模型输入只有 COMPILE_PROMPT + 原始
   问题;gold/judge 字段仅用于离线筛参考行。
5. **一致判定口径**:op 精确相等 + 该 op 相关字段归一化匹配(slot/slot2 经
   SLOT_ALIASES 类归一,date 经 parse_partial_date,presupposed 用 _norm
   双向包含,tag 去空格精确)。执行等价 = 同卡片库/同 mem_dates 下
   execute_plan(本地计划) 与 execute_plan(参考计划) 的(证据行, 结论行)
   完全相等,纯代码零 LLM。一致题也全部实际执行核验(365/369 与 369/369
   两列完全同值,说明"计划一致 ⇒ 执行等价"在本集上无一例外,且不存在
   "计划不同但执行殊途同归"的题——4 处锚反转执行输出确实不同)。
6. **延迟/吞吐环境**:三档中位延迟均 ~2.5s/题(瓶颈在 ~700 token 提示词
   的预填充,ollama 默认 ctx 4096),吞吐 ~24 题/分,单发串行、未并发。
   4b/8b 评测期间用户游戏共占 GPU(全卡峰值列受污染),但 ollama ps 确认
   三档全程 100% GPU 驻留、无 CPU 卸载,精度指标不受影响;14b 跑时游戏
   已退出,其全卡峰值 11.9GB(基线 2.1GB)干净可信。
7. **重试从未触发**:三档 369 题首次请求即产出严格合法 JSON(json_valid
   首次 = 100%),≤3 重试机制存在但零使用。

## 逐题文件

- `results/local_compile_qwen3_4b_20260815.jsonl`(+ `.meta.json`)
- `results/local_compile_qwen3_8b_20260815.jsonl`(+ `.meta.json`)
- `results/local_compile_qwen3_14b_20260815.jsonl`(+ `.meta.json`)
- 评测线:`scripts/eval_local_compiler.py`;汇总:`scripts/summarize_local_compiler.py`
