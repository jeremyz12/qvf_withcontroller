# S7-div 预注册裁决 — 阻塞报告(2026-08-16)

## 结论先行

**本次无法产出阶段四裁决。原因:上游未把"对决结果"数据传入本次调用 —— 收到的任务文本里该字段字面是未被替换的模板占位符 `${JSON.stringify(run).slice(0,5000)}`,而非真实 JSON。我独立核查了文件系统,确认这不是传输丢失,而是对决(阶段三:格闭包臂读取 S7-div 题集 + qvf/judge.py 评分)从未被执行过。** 在没有真实跑数的情况下裁决主判据/护栏/消融,等同于编造数字,直接违反本任务反复强调的"如实"纪律与预注册精神(判据必须先于跑数确定,数据必须先于判决存在)——所以这里选择如实报告阻塞,而不是编一份看似完整的裁决。

## 独立核查证据(诊断,非裁决)

流水线目前实际进度,按文件 mtime 重建时间线:

| 时间 | 产物 | 状态 |
|---|---|---|
| 15:16–15:17 | `scripts/s7div_gen.py` / `s7div_verify.py`,`data/wsc_s7div.jsonl`(139 题,dev 100/test 39)、`data/s7div_seed_ontology.json` | **阶段一完成**。`data/wsc_s7div.meta.json` 记录 assert1(零字面泄漏)/assert2(金答可独立复现)/assert3(冻结代码零 grep 命中)三项均 PASS。 |
| 15:28–15:39 | `scripts/tag_lattice.py`(闭包查询工具,`QVF_TAG_LATTICE` 旗标延迟 import)、`scripts/build_tag_lattice.py`(格构建器) | **机制代码写好**,旗标默认关。 |
| 15:29–15:32 | `scratchpad_lattice_verify/replay_baseline.jsonl` vs `replay_flagoff.jsonl`(S7 原 220 题) | 逐行 `diff` **exit 0,零差异** —— 旗标关时 `complex_query_arm.py` 输出逐字节不变,冻结代码只读纪律满足。 |
| 15:39–15:44 | `results/wt_cards_opentags_smoke/`(8 张卡)→ `results/tag_lattice_smoke.json` + `tag_lattice_smoke_audit.jsonl`(80 条 LLM 建边决策) | 这只是**冒烟建格**(8 张卡、通用领域概念如"outdoor recreation/cooking/employment",与 S7-div 的 110-uid 人口、饮食/活动属性词典**不是同一批**)。 |
| 15:44 之后 | (无) | `find . -newer results/tag_lattice_embed_cache.json` 返回空 —— 此后没有任何文件被创建或修改,说明流水线在此处停止,直到本次调用发起。 |

尚不存在、因而无法裁决的东西:
- `results/tag_lattice.json`(覆盖 S7-div 110-uid 人口的**生产版**标签格)—— 只有 8 卡冒烟版,不存在。
- S7-div test 集(39 题)、dev 集(100 题,仅用于阈值/门槛整定,不可用于裁决)经格闭包臂读取产生的答案文件 —— 不存在。
- S7 原 220 题在 `QVF_TAG_LATTICE=1` 下的护栏回归结果 —— 不存在(现有的 220 题对拍是**旗标关**的字节级 parity,证明的是"不开旗标不影响老行为",不是护栏本身)。
- 消融(去蕴含复核 / 去 merge-or-attach)两组结果 —— 不存在。
- `qvf/judge.py` 的评分产物与 `total_usage` token/美元落盘 —— 不存在,因为判官从未被调用。

## 三个预注册问题的裁决状态

1. **主判据(test 上格闭包臂召回 ≥60% 且精确率 ≥90%)**:无法裁决,无跑数。
2. **护栏(S7 原 220 题,精确率 ≥96.6−1pp、召回 ≥90.5−1pp)**:无法裁决;现有证据只覆盖"旗标关=冻结行为"这一更弱的前提条件,不是护栏本身要求的"旗标开"回归。
3. **消融(去蕴含复核/去 merge-or-attach 各自贡献)**:无法裁决,两组消融跑数均不存在。

## 回答导师原始问题:"三杯鸡 → 高糖"现在能不能做到?

**机制层面**:能力已经写好但未经验证——`tag_lattice.py` 实现了 is-a 传递闭包(三杯鸡 → 台式炖菜 → 肉类主菜)+ has-property 限一跳(三杯鸡 → 高糖)+ 嵌入余弦回退,理论上覆盖导师描述的场景。
**经验层面**:**不能给出任何成功或失败的具体例子**——因为生产版标签格从未在真实的 110-uid S7-div 人口上构建过,格闭包臂也从未真正读取过一条 S7-div 问题。冒烟建格用的是另一批 8 张卡,其中没有出现"三杯鸡"这类食物节点,不能作为例证挪用。任何在此报告中给出的"三杯鸡→高糖 命中/未命中"例子都会是编造的,故不给。

## 对"S7 自考闭环"指控的处置效果

**设计层面的隔离主张成立,有 grep 证据支持**(`data/wsc_s7div.meta.json` 的 assertions 字段,assert3 = PASS):种子属性词典 `data/s7div_seed_ontology.json` 只被 `scripts/s7div_gen.py`(出题侧)和 `scripts/s7div_verify.py`(独立复现校验)导入,对 `qvf_router.py` / `wt_qvf_prototype.py` / `complex_query_arm.py` / `qvf_algebra.py` 四个冻结文件的 grep 命中为零。金答案的推导路径(词典机械施加于已建卡片的 value 字段)与建卡侧的 `_CATALOG_TAGS_RULE`、读取侧的 `_tagged()` 精确字符串匹配完全不共享代码或词表,查询词也经代码断言校验不逐字出现在卡片值/标签里。

**但"S7-div 的成绩是否可作为非自考的证据"——现在还不能回答,因为还没有成绩。** 设计隔离(反自考)是一个关于*题集构造方式*的静态命题,已经用 grep 独立核验为真;但它本身不产生任何关于格闭包臂*能力*的经验证据。要让"非自考"的论证闭环,还需要阶段三的真实跑数——如果格闭包臂在这批与建卡/读取代码零重叠的题目上仍能拿到有意义的召回/精确率,那才是"提升不是抄考纲抄出来的"的实证支持。目前这一步缺失。

## 判官侧实测 token 与美元

未产生 —— `qvf/judge.py` 在本次流水线中从未被调用,没有 usage 记录可读。

## 建议的下一步(不属于本次裁决,仅为诊断的自然推论)

1. 用 `scripts/build_tag_lattice.py` 对覆盖 S7-div 110-uid 人口的完整卡片集(而非 8 卡冒烟子集)建生产版 `results/tag_lattice.json`。
2. 在 dev 集(100 题)上跑 `QVF_TAG_LATTICE_TAU` 校准(≤3 轮,如导言纪律所定),封笔后只跑一次 test(39 题)。
3. 同时跑 S7 原 220 题在 `QVF_TAG_LATTICE=1` 下的护栏回归,以及两组消融。
4. 全部经 `qvf/judge.py` 评分,读出 `total_usage`,把真实 token/美元数字和裁决结果重新写入本报告(建议保留本文件的阻塞记录作为附录,而不是覆盖删除,以保持"负结果如实"的可追溯性)。
