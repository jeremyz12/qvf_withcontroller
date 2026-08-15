# S8 组合式时序代数 — dev + 未见组合 split 一次性测 报告

日期:2026-08-15/16。工作目录 `D:\ZZL_cluade`。判官 opus(`claude-opus-5`),
编译/读者 haiku(`claude-haiku-4-5`),同段代码路径(`qvf.judge.ClaudeJudge`)。

## 猜想被否定

**主判据(预注册,不得挪动):代数臂在未见组合 split 上准确率 ≥65% 且高于
平面臂 ≥20pp。两条均未达成 —— 猜想被否定。**

| 臂 | 未见 split 准确率 | vs 平面臂 |
|---|---|---|
| 代数臂(QVF_ALGEBRA=1) | 33/67 = **49.3%** | **-3.0pp**(不仅未高出 20pp,反而更低) |
| 平面臂(11 算子,被迫落最近算子) | 35/67 = 52.2% | — |
| 直读臂(haiku 稠密直读) | 47/67 = 70.1% | — |

护栏(11 算子宏形式与平面执行逐字节等价)全数通过,编译良构率 100%(见
下)——代数臂"调通"本身是成功的,但**未达到预注册的准确率门槛**。

## 一、dev(见过 split,3 轮,未见 split 全程未触碰直至锁定)

seen split = WINDOW∘COUNT(28)+ NTH∘CMP_DUR(26) = 54 题,与未见 split
(WINDOW∘AGG/WINDOW_2ANCHOR∘COUNT/NTH∘JOIN_T/JOIN_T∘WINDOW)组合类型**完全不
重叠**——dev 对代数原语的改进是否泛化到未见组合,是一次真实的零样本测试,
不是调参对齐评测集。

- **轮 1(基线)**:WINDOW 原语只有单侧 `before`(字面日期)。整体
  33/54=61.1%(WINDOW∘COUNT 11/28,NTH∘CMP_DUR 22/26)。现场诊断:
  WINDOW∘COUNT 里"since I moved to X"式值锚下界、"between d1 and d2"式双侧
  界,原语完全表达不了,编译器只能把 `before` 填成"今天"当无效上界,证据
  包退化为全链。**判决:原语集本身有结构性缺口,进入轮 2。**

- **轮 2(WINDOW 双侧界扩展 + 两处真实实现 bug)**:给 WINDOW 加
  `after`/`before_slot+before_value`/`before_slot+before_index`(对称
  `after_*`)三种可选界描述,新增 `AGG.fn="count_elements"`。护栏对拍
  (S5 全量 314 + S6 33 + S7 切片 50,含 synthetic 316)全程逐字节等价,
  旗标关时 `replay_evidence.py` 前后对拍逐字节相同。
  - **现场 bug①**:`messages.parse` 结构化输出在扩展后的 schema 上被
    bisection 复现地挂起(有时数分钟无响应)或显式 400 "Schema is too
    complex"——原始小 schema(1.4s)稳定,加到仅 1 个新增字段就开始不稳定。
    改走 `messages.create` 纯文本 + 手工 JSON/pydantic 校验(见
    `compile_plan_algebra`),10+ 次验证零复现,<2s 稳定返回。
  - **现场 bug②**:`before_index`/`after_index` 省略 `*_slot`(提示词文档
    的"默认同链")时,类型检查器和求值器都没实现这个默认,导致该类计划
    被误判非良构或界解析失败——修了 `check_expr` 放行条件与 `eval_expr`
    的自指默认。
  - 修完中途冒烟:整体一度跌到 9.3%(NTH∘CMP_DUR 完全崩溃,26 题 22 题
    空证据)——序数界的"排除锚点本身"语义被错误地套用到"直接比较两个
    序数位"场景(该场景需要**包含**两个位置,不是排除)。
  - **判决:实现 bug 修完后判据不达标,进入轮 3。**

- **轮 3(提示词澄清,最后一轮,不再改代数实现)**:补一条区分规则——
  只有问题里出现 between/since/during/before/after/while 等显式跨度词才
  用 WINDOW;单纯"我的第一个 vs 第二个 X"这类直接位置比较不开窗,退回
  轮 1 的全链 AGG。整体回升到 28/54=51.9%(WINDOW∘COUNT 10/28,好卡片
  子集 9/18=50%,坏卡片子集 1/10=10%;NTH∘CMP_DUR 回升到 18/26=69%,
  未回到轮 1 的 85%,但不影响未见 split——两个 dev 组合都不在未见
  split 里)。**dev 3 轮用尽,锁定实现,转未见 split 一次性测,测前无
  再改动。**

副产品(dev 中途发现,不算入 3 轮迭代计数,是数据基础设施修复而非算法
调参):`results/wt_cards_v42` 的 4 个跨属性世界 uid
(wikiM003/M004/M018/M019)卡片建自**旧版**
`wikistate_full_multi_big.json`/`_multi_P108_P551.json`(如今这两个源
文件已扩容,如 M003 从 66 场对话变成更长版本),卡片日期与当前源文件的
链日期**系统性不一致**(如某雇主记录卡片日期 2008-01-10 vs 当前源链
2011-09-01,偏差以年计)。这 4 个 uid 占未见 split 32/67(47.8%)——若不
修复,三臂的绝对准确率都会被这个共享混淆项拖累(不是代数臂特有的劣势,
三臂读同一份卡片库)。修复:从当前源文件重新建卡(`results/wt_cards_v43`,
小批量抽取提升召回),验证日期与源链完全对齐后作为 dev 收尾与一次性测
的统一卡片库。

## 二、护栏(零 LLM 重放,任一不等价即弃)

`results/wsc_s8_algebra_parity_r2_20260815.jsonl`:

| 切片 | n | 逐字节等价 |
|---|---|---|
| S5 全量 | 314 | 314/314 |
| S5 synthetic(+current/point_in_time/trajectory/premise_check) | 316 | 316/316 |
| S6(两份) | 15+18=33 | 33/33 |
| S7 切片 | 50 | 50/50 |

`scripts/replay_evidence.py` 对拍(旗标关,复合修改前后)逐字节相同 ——
`complex_query_arm.py` 的改动(try/except 接住 IllFormed、`compile_wellformed`
字段)全部挂在 `if _ALGEBRA:` 门内,不影响冻结路径。全部通过,**护栏未破
一次**。

## 三、未见组合 split 一次性测(三臂,67 题)

`results/wsc_s8_algebra_test.jsonl` / `wsc_s8_flat_test.jsonl` /
`wsc_s8_direct_test.jsonl`。

### 三臂总表(token 为 compile+read 合计,不含判官)

| 臂 | n | correct | 准确率 | tok_in/题 | tok_out/题 | 延迟 s/题 |
|---|---|---|---|---|---|---|
| 代数臂 | 67 | 33 | 49.3% | 1777.6 | 170.3 | 6.76 |
| 平面臂 | 67 | 35 | 52.2% | 2224.0 | 131.0 | 6.23 |
| 直读臂 | 67 | 47 | 70.1% | 798.3 | 90.2 | 11.95 |

### 分组合明细(correct/n)

| combo | n | 代数臂 | 平面臂 | 直读臂 | 平面臂结构性不可表达 |
|---|---|---|---|---|---|
| WINDOW∘AGG | 28 | **26/28=92.9%** | 22/28=78.6% | 20/28=71.4% | 否(闭区间读法 reading B 与代数 WINDOW+argmax_dur 处处一致,但平面臂自身 11 算子里 `longest` 无窗、不等价 gold,记不可表达) |
| WINDOW_2ANCHOR∘COUNT | 23 | **1/23=4.3%** | 7/23=30.4% | 21/23=91.3% | 是(无双锚窗原语) |
| NTH∘JOIN_T | 15 | 5/15=33.3% | 6/15=40.0% | 5/15=33.3% | 否(`join_at_change` 语义与 gold 处处一致,数据集已剔除边界重合歧义行) |
| JOIN_T∘WINDOW | 1 | 1/1 | 0/1 | 1/1 | 是(无逐段计数比较原语;n=1 不构成统计证据) |

平面臂结构性不可表达率(严格口径,按 combo 类型机械判定,非逐行 LLM
判断):**52/67 = 77.6%**(WINDOW_2ANCHOR∘COUNT 全 23 题 + WINDOW∘AGG
全 28 题 + JOIN_T∘WINDOW 1 题;NTH∘JOIN_T 15 题记可表达)。分类判据与
理由见 `scripts/wsc_s8_inexpressible.py`。

编译良构率(类型检查拒绝):未见 split **67/67 = 100%**(≥90% 门槛达
成)。dev 各轮:轮 1 53/54=98%,轮 2 中途(bug 复现时段)40/54=74%,
轮 2 终版/轮 3 均 54/54=100%——bug 修复后的"修复率"即为这一变化本身
(未额外实现"拒绝后自动重试重编译"的修复循环,IllFormed 直接降级为
空证据,不重试;这是本轮未做的工程项,如实记录)。

### 根因诊断(WINDOW_2ANCHOR∘COUNT 崩溃,非猜测,逐题验证)

抽查未见 split 里"好卡片"(非 4 个陈旧 uid)的 WINDOW_2ANCHOR∘COUNT 题
(如 `wikiP108036-Q39032964_s8w2`,"University of Oklahoma" 与
"University of Nebraska–Lincoln" 之间换了几次雇主),编译计划**完全正确**
(`before_value`/`after_value` 精确匹配卡片值,连长破折号字符都对齐;
`fn="count_elements"` 也用对了),纯代码执行结果**完全正确**(证据行
= 窗内那条 "Oklahoma State University" 记录,derived = "count_elements
over ... : 1. This IS the answer")。但读者最终答案是"我记忆里没有你
入职 University of Oklahoma 或 University of Nebraska–Lincoln 的记录"
——**读者拒答**,尽管计算全对。

原因:`_render_direct` 的 Value 分支只把"窗内子链"当证据展示给读者,
不像平面臂 `join_at_change` 的 `_render_join` 那样把两个**锚点记录本身**
也放进证据包。读者看不到"你确实入职过这两个地方"的直接证据,只看到窗内
一条孤零零的记录 + 一句"这就是答案"的断言,触发了拒绝无依据断言的训练
倾向,宁可说"没有记录"。这是**代数臂通用渲染器的证据完整性缺陷**——
不是编译错、不是执行错,是"证据包该放什么"的设计遗漏,系统性压低了
WINDOW_2ANCHOR∘COUNT(以及潜在的所有值/序数锚定 WINDOW 用法)的准确率。
一次性测已锁定,未回头改渲染器重测;记为本轮最重要的负结果与后续修复
线索。

## 四、纪律核对

- ①旗标默认关,逐字节不变:`replay_evidence.py` 复合前后对拍相同,
  达成。
- ②护栏(11 算子宏 vs 平面执行,S5 全量+S6+S7 切片逐字节等价):全绿,
  达成;编译良构率 100% ≥90%,达成。
- ③dev ≤3 轮,未见 split 一次性测、测前禁触:3 轮用尽后锁定,未见
  split 仅在锁定后跑过一次,达成。
- ④编译提示词 = 原语形式语义文档 + ≤2 组合示例,示例句式不取自 gen
  模板:达成(`ALGEBRA_COMPILE_PROMPT` 全程 2 个示例,新造句式)。
- ⑤S8 金答案纯代码从链导出:沿用既有 `gen_wsc_s8.py`/
  `verify_wsc_s8.py`(121/121 独立复核一致,未在本轮改动)。
- ⑥预算 ≤$8、冒烟先行:达成(见"成本"字段);判官 opus 同段代码:
  达成(`qvf.judge.ClaudeJudge`,三臂共用)。
- 负结果如实:本报告即负结果的完整呈现,未做任何事后美化或选择性
  汇报。

## 文件清单

- 数据/题集:`data/wsc_s8.jsonl`、`data/wsc_s8.meta.json`、
  `results/wsc_s8_seen.jsonl`、`results/wsc_s8_unseen.jsonl`
- 卡片:`results/wt_cards_v43`(4 个 uid 重建,其余 68 个复用
  `wt_cards_v42`)
- dev 轮次:`results/wsc_s8_algebra_dev_r1.jsonl`(轮1)、
  `_r2.jsonl`(轮2中途,含 bug 复现)、`_r4.jsonl`(轮2终版=轮3,锁定版)
- 一次性测:`results/wsc_s8_algebra_test.jsonl`、
  `results/wsc_s8_flat_test.jsonl`、`results/wsc_s8_direct_test.jsonl`
- 护栏:`results/wsc_s8_algebra_parity_r2_20260815.jsonl`
- 不可表达率分类器:`scripts/wsc_s8_inexpressible.py`
- 代数实现:`scripts/qvf_algebra.py`(本轮修改:WINDOW 双侧界扩展、
  `count_elements`、`compile_plan_algebra` 纯文本编译路径)
- 跑批器改动:`scripts/complex_query_arm.py`(IllFormed 接住 + 旗标内
  `compile_wellformed` 字段,旗标关时逐字节不变)
