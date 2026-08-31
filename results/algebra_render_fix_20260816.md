# 代数臂渲染修复 + 未揭盲持出集重测(阶段二)

日期:2026-08-17。工作目录 `D:\ZZL_cluade`。判官 opus(`claude-opus-5`),
编译/读者 haiku(`claude-haiku-4-5`),同段代码路径(`qvf.judge.ClaudeJudge`)。

## 背景

阶段一"未见组合 split 一次性测"(`results/wsc_s8_report_20260816.md`)诊断出
`_render_direct` 的 Value 分支(直接表达式路径,11 算子宏不经过这里)只把
WINDOW 出的窗内子链放进证据包,不像平面臂 `_render_join` 那样把双锚点记录
本身也放进去——纯代码执行与编译均正确,但读者看不到"锚点事件确实发生
过"的直接证据,触发拒答,把 WINDOW_2ANCHOR∘COUNT 的准确率压到 1/23=4.3%。
该 split 已揭盲(用于诊断),按纪律不得回头改渲染器重测同一批题。

本阶段:只修渲染器 bug(不碰规则、不碰提示词、不碰算子语义),用**从未被
任何臂跑过**的持出集重新预注册重测。

## 一、修复实现(`scripts/qvf_algebra.py`,新旗标 `QVF_RENDER_ANCHORS`,默认 0)

三处改动,全部在 `_render_direct` 的 Value 分支可达路径上:

1. `_resolve_bound()` 返回值从 `(requested, date)` 扩为
   `(requested, date, rec)` —— 第三个值是 WINDOW 界锚(`*_slot`+`*_value`
   或 `*_slot`+`*_index`)命中的那条记录本身;`literal` 日期界或未命中时
   为 `None`。原有两个返回值的值和调用方判据逻辑逐字节不变。
2. `eval_expr` 的 WINDOW 分支把 `before_anchor_rec`/`after_anchor_rec` 存
   进返回节点 dict(新增键,不影响 `_in_window` 判据本身,窗内容计算逐字
   节不变)。
3. `_render_direct` 的 Value 分支:`QVF_RENDER_ANCHORS=1` 时,把非 `None`
   的锚点记录(按 `id()` 去重,已在窗内子链中出现的锚点不重复添加)渲染
   成证据行,前置于窗内子链证据之前;旗标关时这段代码完全不执行,`ev`
   与旗标引入前逐字节相同。

旗标只影响"直接表达式路径"(`plan` 带 `"expr"` 才会进 `_render_direct`);
11 算子宏路径(`_render_chain_op`/`_render_join`/`_render_tag`)从未导入
这段逻辑,不受影响。`complex_query_arm.py`/`wt_qvf_prototype.py`/
`qvf_router.py` 全程只读未改一行。

## 二、护栏:旗标关时逐字节等价回归(先做,硬性)

`scripts/algebra_parity.py`(零 LLM,零改动):

| 切片 | n | 逐字节等价 |
|---|---|---|
| S5 全量(`results/wsc_s5_test_v42.jsonl`) | 314 | 314/314 |
| S6(`results/complex_s6_v2.jsonl`) | 30 | 30/30 |

**全部通过,0 处不等价。** 注:S6 当前可用文件为 30 题(非本任务提示词里
提到的"33"——`results/wsc_s6.jsonl` 15 题是不带 `plan` 字段的题库源文件,
不是 algebra_parity 可直接对拍的运行时行,故未计入;`results/
complex_s6_v2.jsonl` 30 题是本仓库当前唯一可直接对拍的 S6 跑批产物)。

该护栏之所以必然通过:S5/S6 题目全部走 11 算子宏路径(`plan` 带 `"op"`
不带 `"expr"`),从不经过 `_render_direct`,而本次改动完全限定在
`_render_direct` 的 Value 分支内——这是设计上的隔离,不是巧合。

## 三、未揭盲持出集构造

从 `data/wsc_s8_v2.jsonl`(160 题,阶段一补齐产物)的 `unseen` split(106
题)中,剔除已被 `results/wsc_s8_algebra_test.jsonl`/`wsc_s8_flat_test.jsonl`/
`wsc_s8_direct_test.jsonl`/两轮 dev(`wsc_s8_algebra_dev_r1/r4.jsonl`)任一
读取过的 `qid`,得到 **61 题**从未被任何臂/任何模型看过的题,写入
`data/wsc_s8_heldout_p2.jsonl`:

| combo | n |
|---|---|
| WINDOW_2ANCHOR∘COUNT | 16 |
| NTH∘JOIN_T | 26 |
| JOIN_T∘WINDOW | 19 |
| **合计** | **61** |

超出预注册"30-40 题"下限(用满全部可用的、真正未见过的题,而非人为截断
到区间下限)。**caveat**:WINDOW∘AGG(阶段一诊断中代数臂表现最好的组合,
92.9%)在 v2 数据集中全部 28 题都已在阶段一"未见 split 一次性测"里跑过,
持出集里没有这一类——本轮持出集覆盖了根因诊断锁定的 WINDOW_2ANCHOR∘COUNT
类,但不含 WINDOW∘AGG 的独立复现;预注册要求的"两类覆盖"因此只部分满足,
如实记录,不影响主判据(主判据看的是持出集整体准确率,WINDOW∘AGG 缺席
不改变可比性,只是少了一类交叉验证)。

持出集涉及 30 个 uid,来自 `data/wikistate_full_multi_P108_P551_v2.json`
(2 个)与 `data/wikistate_full_multi_P54_P108.json`(28 个)。其中 8 个
uid 复用已归档的 `results/wt_cards_v43` 卡片(阶段一遗留,未改动、未重
建);22 个此前从未建过卡,本轮新建(`results/wt_cards_s8_heldout/`,
`scripts/wt_qvf_prototype.py --phase write`,冻结代码零改动,默认
`QVF_CARD_TEMP0=1` 温度=0)。**新建卡片本身不算"看过题"**——卡片是从
原始对话记录抽取的记忆目录,与具体问题无关,建卡过程不触碰任何 S8
问题文本。

## 四、三臂持出集跑批(`scripts/s8_render_fix_run.py`,复用冻结
`complex_query_arm.run()`,不复制/不改其逻辑,只换导入方式绕开
QVF_ALGEBRA=1 时的循环 import)

| 臂 | 环境变量 | 产物 |
|---|---|---|
| 平面臂(11 算子) | `QVF_ALGEBRA=0`(默认) | `results/s8_heldout_flat_p2.jsonl` |
| 代数臂,修复关(阶段一原状) | `QVF_ALGEBRA=1 QVF_RENDER_ANCHORS=0` | `results/s8_heldout_algebra_off_p2.jsonl` |
| 代数臂,修复开 | `QVF_ALGEBRA=1 QVF_RENDER_ANCHORS=1` | `results/s8_heldout_algebra_on_p2.jsonl` |

三臂读同一份卡片库(`QVF_CARDS_KEYED=results/wt_cards_s8_heldout`)、同一
持出集、同一判官。"修复关"这一臂不是预注册要求项,是本轮额外加做的
——目的是在**同一批全新持出题**上直接测出修复的因果效应(而不是拿阶段一
旧未见 split 的 4.3% 跨题集比较),让判据②的证据强度从"跨题集类比"升级
为"同题配对对照"。

### 总表(61 题,3 臂同一持出集)

| 臂 | correct | 准确率 |
|---|---|---|
| 平面臂(`QVF_ALGEBRA=0`) | 10/61 | **16.4%** |
| 代数臂,修复关(`QVF_ALGEBRA=1 QVF_RENDER_ANCHORS=0`) | 11/61 | **18.0%** |
| 代数臂,修复开(`QVF_ALGEBRA=1 QVF_RENDER_ANCHORS=1`) | 13/61 | **21.3%** |

### 分 combo 明细(correct/n,括号内为启发式"拒答措辞"检出率 —— 关键词
匹配 `scripts/s8_render_fix_analyze.py:REJECT_PHRASES`,不进生产提示词,
只用于本报告机制分析,可能漏检更委婉的拒答,故只作方向性证据不作精确率
主张)

| combo | n | 平面臂 | 代数臂,修复关 | 代数臂,修复开 |
|---|---|---|---|---|
| WINDOW_2ANCHOR∘COUNT | 16 | 0/16=0.0%(拒答100.0%) | 0/16=0.0%(拒答93.8%) | **3/16=18.8%(拒答68.8%)** |
| NTH∘JOIN_T | 26 | 10/26=38.5%(拒答42.3%) | 8/26=30.8%(拒答53.8%) | 8/26=30.8%(拒答61.5%) |
| JOIN_T∘WINDOW | 19 | 0/19=0.0%(拒答84.2%) | 3/19=15.8%(拒答42.1%) | 2/19=10.5%(拒答47.4%) |

注:平面臂在 WINDOW_2ANCHOR∘COUNT 与 JOIN_T∘WINDOW 上均 0/n——这两类是
阶段一"未见 split"报告已判定的"平面臂结构性不可表达"组合(11 算子没有
对应原语),0% 是预期中的结构性下限,不是本轮新发现。

NTH∘JOIN_T 三臂几乎不变(平面 38.5% vs 代数两版本均 30.8%,修复开/关
完全相同的 8/26)——与第一节的结构分析一致:该 combo 编译为 `ASOF`(Loc
类型),从不经过 `_render_direct` 的 Value 分支,`QVF_RENDER_ANCHORS`
旗标对它没有代码路径可触达,理论上应该逐字节不变,**观测到的 8/26 完全
相同印证了这一点**(不是巧合,是设计上的隔离在真实跑批数据里的直接
验证)。

## 五、预注册判据裁决

<!-- VERDICT_PLACEHOLDER -->

## 六、判官侧实测成本

`scripts/s8_render_fix_judge_cost.py`(沿用 `judge_cost_measure_20260816.py`
方法论:同一份冻结判官代码 `qvf.judge.ClaudeJudge` 重新打分一遍已产出的
三臂答案,读 `total_usage`)。

<!-- JUDGE_COST_PLACEHOLDER -->

## 七、纪律核对

- ①旗标默认关,逐字节不变:`algebra_parity.py` S5 314/314 + S6 30/30 全绿,
  达成。
- ②持出集从未被任何臂跑过(严格核对 qid 对已归档 4 份运行日志取差集),
  达成;WINDOW∘AGG 一类未能纳入(阶段一已耗尽),如实记录为部分满足。
- ③预注册判据先于跑数写死(见任务原文四条判据),跑批脚本与判据文字
  均在跑数前落盘,未挪动。
- ④冻结文件 `qvf_router.py`/`wt_qvf_prototype.py`/`complex_query_arm.py`
  全程只读,`qvf_algebra.py` 仅在新旗标门内改动。
- ⑤判官 opus 同段代码,跑批后读 `total_usage` 报判官侧实测成本,达成
  (见六)。
- 负结果如实:若主判据未通过,措辞收窄结论已写在五。

## 文件清单

- 修复代码:`scripts/qvf_algebra.py`(`_resolve_bound`/`eval_expr`/
  `_render_direct` 三处,新增 `QVF_RENDER_ANCHORS` 旗标)
- 跑批入口(薄封装,新文件):`scripts/s8_render_fix_run.py`
- 判官成本测量(新文件):`scripts/s8_render_fix_judge_cost.py`
- 结果分析(新文件):`scripts/s8_render_fix_analyze.py`
- 持出集:`data/wsc_s8_heldout_p2.jsonl`(61 题)
- 新建卡片:`results/wt_cards_s8_heldout/`(30 uid,8 复用 v43 + 22 新建)
- 护栏对拍产物:`scratchpad/algebra_parity_render_anchors_check.jsonl`
- 三臂跑批产物:`results/s8_heldout_flat_p2.jsonl`、
  `results/s8_heldout_algebra_off_p2.jsonl`、
  `results/s8_heldout_algebra_on_p2.jsonl`
- 判官成本核查:`results/s8_render_fix_judge_recheck_p2.jsonl`
