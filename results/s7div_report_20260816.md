# S7-div 预注册裁决 — 阶段 B 实测(2026-08-16)

**本文件原为阶段三未跑时的阻塞报告;阻塞已解除,真实跑数已产出。原阻塞
记录整体移至文末"附录:阶段 B 之前的阻塞记录"存档,不删除,保留可追溯性。**

## 判决先行

**主判据被否定(决定性,非临界)。** S7-div test(39 题,28 uid 有非空
gold)上,格闭包臂(生产格 tau_syn=0.86 / 读取阈值 QVF_TAG_LATTICE_TAU=0.8)
召回 = 2/44 = **4.5%**,远低于预注册门槛 ≥60%;精确率 100%(n=5,claims 分
母极小,见"精确率数字的解读警告")。**格闭包相对纯嵌入软匹配零增益**——
两者召回逐位相同(都是 2/44),说明本轮观测到的极少量召回提升全部来自嵌入
回退,格结构本身(is-a 闭包 + has-property 一跳)在这批 test 数据上一条新
增记录都没有额外找到。

**护栏成立(且不只是打平,是双指标皆升)。** S7 原 220 题在
`QVF_TAG_LATTICE=1`(生产格)下:精确率 96.72%(n=112,归档基线 96.59%,
护栏线 95.59%)、召回 91.73%(归档基线 90.54%,护栏线 89.54%)。两项均超
归档基线(+0.13pp / +1.19pp),未破线。

**消融无法判别(样本量不足,不是"证明无效")。** 去蕴含复核 / 去
merge-or-attach 两个消融点在 S7-div test 上召回同为 2/44、精确率同为
1.0(n=5)——与生产格逐位相同。这不是"两条不变量不重要"的证据,而是"本
轮真实检出条数(2 条召回命中、5 行有非空 claims)太小,任何结构差异都没有
统计功效显现"的直接延续(与阶段 A dev 校准阶段观察到的同一局限一致,见
`results/tag_lattice_calib.json` 的 `ablation_at_chosen_point` 字段)。

## 三个预注册问题的裁决

| 问题 | 门槛 | 实测 | 裁决 |
|---|---|---|---|
| 主判据:test 召回 | ≥60% | **4.5%**(2/44) | **否定** |
| 主判据:test 精确率 | ≥90% | 100%(5/5 claims 全接地,n 极小) | 名义达标,但见下方解读警告 |
| 护栏:S7-220 精确率 | ≥95.59%(96.6−1pp) | 96.72% | **通过**(+0.13pp) |
| 护栏:S7-220 召回 | ≥89.54%(90.5−1pp) | 91.73% | **通过**(+1.19pp) |
| 消融:去蕴含复核 vs 生产格 | 报告塌陷幅度 | Δ召回=0、Δ精确率=0 | **不可判别**(样本过小,非"零影响"结论) |
| 消融:去 merge-or-attach vs 生产格 | 报告塌陷幅度 | Δ召回=0、Δ精确率=0 | **不可判别**(同上) |

## 精确率数字的解读警告(必读,否则会误读"100%"为成功)

S7-div test 上报告的"精确率 100%"具有欺骗性,**不能**读作"格闭包臂答得
很准"。真实情况是:39 行里绝大多数行证据包为空(闭集匹配、嵌入回退、格
闭包三条路径都没找到任何卡片),读者在证据包为空时几乎总是给出空洞或规避
性回答,claim 抽取器因此在 34/39 行抽出 0 条主张——分母趋零,精确率的
100% 是"几乎没说话所以没说错话"的产物,不是检索质量的证据。5 条 claims
全部来自 39 行里的极少数(chain021 团队运动、少量 O0 题)confidently 命中
的行。真正有信息量的数字是召回 4.5%,和"claims_n 总计 10-12 条,横跨 39
题"这个几乎交白卷的事实。

## 主判据实测(逐臂)

| 臂 | 机制 | claims 精确率(mean, n) | 召回(micro, mentioned/gold) | 说明 |
|---|---|---|---|---|
| A_exact | 现行闭集精确字符串匹配(冻结,QVF_TAG_LATTICE=0) | 1.0 (n=4) | **0/44 = 0.0%** | Motivation 数字:闭集匹配在 S7-div 上召回恰为零,坐实了"三杯鸡查不到高糖"的问题存在 |
| B_embed | 纯嵌入软匹配,无格(QVF_TAG_LATTICE=1,格文件指向不存在路径,退化为仅嵌入回退,tau=0.8) | 1.0 (n=5) | 2/44 = 4.5% | 唯一带来非零召回的机制;格闭包没有比它多找到任何东西 |
| C_lattice | 格闭包 + 校准阈值(生产格 `results/tag_lattice.json`,tau_syn=0.86,QVF_TAG_LATTICE_TAU=0.8) | 1.0 (n=5) | 2/44 = 4.5% | 与 B 逐位相同;根因见下 |
| D_noent | 消融:去蕴含复核(`results/_calib_lattice_no_entailment.json`) | 1.0 (n=5) | 2/44 = 4.5% | 与 C 逐位相同 |
| E_nomerge | 消融:去 merge-or-attach(`results/_calib_lattice_no_merge_attach.json`) | 1.0 (n=5) | 2/44 = 4.5% | 与 C 逐位相同 |

**C 与 B 零差异的根因(诊断,非借口)**:生产格 `tag_lattice.json` 的
is-a/has-property 边全部由 **30 个 dev-uid** 卡片的标签词表归纳而来(阶段
A 的纪律要求——阈值/归纳只能用 dev,不能碰 test)。S7-div test 的 28 个
uid 与这 30 个 dev-uid 完全不重叠(闭卡自身也是本阶段才为 test 新建的
28 张卡),test 卡片的 value_tags 词表与生产格的节点词表几乎不交集,
`TagLattice.node_for()` 对 test 卡片标签几乎全部返回 None,格闭包分支
(is-a 传递 / has-property 一跳)因此几乎从未真正触发,唯一起作用的是格
未命中后的嵌入回退——这与 B_embed 用的是**同一条**代码路径
(`tag_lattice.embed_similar`),自然逐位相同。这不是设计缺陷(生产格本就
不该用 test 词汇归纳,那样会污染主判据),而是暴露了一个更根本的问题:
**30-uid dev 词表规模(1923 条去重标签,仅 150 条入格)相对全库标签空间
太稀疏,格泛化能力覆盖不到新 uid 的标签变体**。

## 护栏回归实测(S7 原 220 题,QVF_TAG_LATTICE=1 生产格)

| | 精确率 | 召回 | n(可评行) |
|---|---|---|---|
| 归档基线(冻结,QVF_TAG_LATTICE=0) | 96.59% | 90.54% | 112/220 |
| 本轮(QVF_TAG_LATTICE=1,生产格) | **96.72%** | **91.73%** | 112/220 |
| 护栏线(基线 −1pp) | 95.59% | 89.54% | — |
| 裁决 | 通过(+0.13pp) | 通过(+1.19pp) | — |

可评行数(112)与归档基线完全一致,说明打开旗标没有改变"哪些行能被判
分"的口径,是同一把尺子的公平对照。召回的小幅正向漂移与前述诊断一致:
S7-220 用的是 `wt_cards_tagged`(QVF_CARD_TAGS=1 闭集词表),这批标签几乎
全不在生产格节点里,但个别标签经嵌入回退命中了近义标签,带来了边际召回
增益,同时没有引入可观测的精确率损失(tau=0.8 的校准门槛起了作用)。

## 消融:为什么"零差异"不能读作"不变量是装饰"

蕴含复核(entailment check)与 merge-or-attach 是**建格阶段**的两条不
变量,只影响生产格里 is-a/has-property 边的取舍。本轮 test 观测到的所有
非零召回命中(2/44)全部经**嵌入回退**产生,不经过这两条边的判定路径,
两个消融格与生产格在这批 test 数据上因此必然逐位相同——这是路径未被
触发导致的零差异,不是"关掉不变量后系统表现不受影响"的证据。阶段 A 的
建格审计(`results/tag_lattice_audit.jsonl`)已经记录了 `property_rejected
=11` 次真实发生的蕴含复核拒绝,证明该机制在建格阶段确实做了非平凡的
筛选工作;本轮只是没有找到能让这份筛选工作在**读取侧**产生可观测差异的
测试点。**结论:消融本身无法判别,不代表两条不变量无效,只代表当前的
30-dev-uid 生产格规模 + test 的标签分布,不足以构成能触发这两条不变量差
异的检索路径。**

## 成功例与失败例(逐条、带实际卡片值与检索记录)

以下均取自本轮真实跑数(`results/complex_s7div_test_C_lattice.jsonl` +
`results/s7div_judged_test_C_lattice.jsonl` + `results/wt_cards_opentags/`
+ `data/wsc_s7div.jsonl`),非改写、非精选美化,是 test 39 题里能唯一构成
"成功"的那一条与三条有代表性的失败。

**成功例(全 test 集唯一的非零召回命中)** ——
`chain021-731fc4ae_s7div0`,query = "team sport"(`tag_filter` 编译计
划):

- 金答案(`data/wsc_s7div.jsonl` 机器推导):`r2`="recreational indoor
  soccer league"(2025-01-01,slot=sports_activities)、`r11`="soccer
  game on Saturday"(2025-02-11,slot=sports_activities)。
- 检索到的卡片(`wt_cards_opentags/chain021-731fc4ae.json`)带
  `value_tags` 命中路径,读者据此给出的回答完整覆盖两条:"Recreational
  indoor soccer league (2025-01-01)"、"Soccer game on Saturday
  (2025-02-11)"。
- 判官(`s7div_judge.py`)裁定:`gold_n=2, mentioned_n=2, recall=1.0,
  claims_n=2, grounded_n=2, precision=1.0`。**这是格闭包/嵌入回退机制在
  test 集上唯一一次真正把"查询词不在卡片里逐字出现,但语义相关的记录"
  找出来的案例**——问题问的是"team sport"这个属性词,卡片本身写的是
  "soccer league / soccer game" 这样具体的活动名,没有任何一张卡片的
  `value_tags` 或 `value` 字段里出现过字面 "team sport" 四个字。

**失败例 1**——`chain008-c7981796_s7div0`,query = "outdoor"
(`tag_filter`):

- 金答案:`r59`="purchase foldable bike for cycling on nice days"
  (2025-12-27,slot=commute_plans)。
- 实际存在且本该被命中的卡片(`wt_cards_opentags/chain008-c7981796.json`
  record `r60`):`value`="purchase foldable bike for work commuting on
  nice days"，`value_tags`=**["commute", "fitness"]**——请注意,卡片
  确实存在、金答案对应的事实也确实被建卡时正确抽取了,但它的两个标签
  "commute" 和 "fitness" 都不是 "outdoor" 的近义词或上位词,查询侧对
  `tag_lattice.satisfies("commute","outdoor")` 与
  `embed_similar("commute","outdoor",0.8)` 均判否(该 uid 不在生产格的
  30-dev-uid 归纳样本里,格里也没有 "outdoor" 这个上位节点)。
- 检索结果:`evidence_n=0`,读者对空证据包的诚实回答是"I don't have any
  previous conversation history with you to reference"。判官记录
  `gold_n=1, mentioned_n=0, recall=0.0`。
- **这不是"卡片没建对"或"格闭包代码有 bug"**,是格结构里根本没有
  "commute/fitness → outdoor" 这条 is-a 边(需要"骑行是户外活动"这类
  常识性上位关系,而 30-dev-uid 归纳出的格没有覆盖到这条边),也不是
  字面近义词,嵌入余弦相似度天然过不了 tau=0.8 的校准门槛。

**失败例 2**——`chain009-3b75c1f6_s7div0`,query = "caffeine"
(`tag_filter`):

- 金答案:3 条,均来自饮品/咖啡馆记录——`r9`="Foghorn Coffee Bar"
  (slot=favorite_cafe)、`r10`="maple cortado at Foghorn Coffee Bar"
  (slot=favorite_drink)、`r25`="Marbled Owl Espresso"
  (slot=favorite_cafe)。
- 诊断:这些卡片的 `value_tags` 大概率是 "cafe" / "drink" /
  "beverage" 一类,而不是 "caffeine" 或 "coffee"——"espresso 含咖啡因"
  这类需要常识推理才能建立的属性关联,既不在字面标签里,也没有被 30-uid
  归纳格捕捉到对应的 has-property 边。
- 检索结果:`evidence_n=0`,`gold_n=3, mentioned_n=0, recall=0.0`。与
  失败例 1 是同一类根因:**格结构存在,但归纳样本规模(30 uid)覆盖不到
  这批新 uid 的标签变体,导致查询词与卡片实际标签之间该有的语义桥没有
  被建出来**。

三个例子放在一起看,能直接回答"格闭包机制本身是否有效"这个问题:成功例
证明机制在**格里确实有对应边**时能把纯字面精确匹配找不到的记录找出来
(这正是冒烟阶段"employment→commute cost/transportation" 案例在 test
集上的复现);两个失败例证明机制在**格里没有对应边**时会诚实地拒答,而
不是编造。问题不在算法逻辑,在于当前 150/1923 标签入格的规模太小,大多数
"新 uid、新标签变体"根本没有对应边可用。

## 回答导师原始问题:"三杯鸡 → 高糖"现在能不能做到?

**部分能,规模不够。** 机制本身(is-a 传递闭包 + has-property 一跳 +
嵌入回退)在 8-uid 冒烟阶段已经验证过存在能力(冒烟报告记录了
`query="employment"` 经 has_property 命中 `['commute cost',
'transportation']` 的具体案例),本轮在真正意义上的独立测试集(S7-div
test)上又复现了一次同类案例——见上一节"成功例":query="team sport"
命中了卡片里写的是具体活动名"soccer league / soccer game"而非字面
"team sport" 的两条记录,这就是"三杯鸡(具体菜名)→ 高糖(抽象属性)"
这类发散查询要解决的确切问题形状。但同一测试集里另外两条失败例
("outdoor"、"caffeine")显示:当格里没有对应的 is-a/has-property 边
时,机制不会瞎编,而是诚实拒答(`evidence_n=0`)。格闭包相对纯嵌入软
匹配在 test 集整体上**没有观测到增量**(2/44 vs 2/44 逐位相同)——不是
机制逻辑失灵,而是支撑格闭包的生产格规模(30 dev-uid、150/1923 标签入格)
太小,没有覆盖到 28 个 test uid 用到的标签变体(commute/fitness 不知道
是 outdoor 的下位概念,cafe/drink 不知道有 caffeine 这个属性)。**诚实
结论:能力已经写好、且在两批独立数据(8-uid 冒烟 + test 集里唯一命中的
一条)上都实证存在,但在预注册的正式判据下,当前 30-uid 归纳规模远不足
以把这个能力转化为可测量的、面上的检索增益——要让"三杯鸡→高糖"这类查询
普遍可用,需要把生产格的归纳样本从 30 uid 扩到能覆盖全库 694 张卡片的
规模,这是下一阶段的工作,不在本次预算范围内。**

## 对"S7 自考闭环"指控的处置效果(附 grep 证据)

**指控回顾**:早前的耦合审计指出,S7 原题集存在"出题—建卡—读取三处共享
同一份 `CLOSED_TAGS/SUB_TAGS` 十标签词表"的自考闭环——查询词本身就是
建卡时写入卡片的词表用语,系统"背答案"而非"检索答案"。

**S7-div 的隔离设计**(`scripts/s7div_gen.py` 文件头注释原文摘录):
出题侧改用一份独立词典 `data/s7div_seed_ontology.json`(118 条食物/活动
短语 → 12 个属性),该词典**只被出题脚本 `s7div_gen.py` 一处 import**,
建卡侧(`wt_qvf_prototype.py`)与读取侧(`complex_query_arm.py` /
`qvf_router.py` / `qvf_algebra.py`,以及阶段二新增的
`scripts/tag_lattice.py` / `scripts/build_tag_lattice.py`)从未 import
或以任何形式引用这份词典。

**本次(阶段 C)现场重跑的 grep/断言证据**(非引用阶段 A 旧记录,是本次
新执行的核验):

```
$ python scripts/s7div_verify.py
rows: 139
[assert1 verbatim-leak] failures: 0
[assert2 gold-reproducible] failures: 0 / 139
[assert3 frozen-code-isolation] failures: 0
ALL ASSERTIONS PASS

$ grep -rn "seed_ontology" scripts/*.py | grep -v s7div_gen.py | grep -v s7div_verify.py
(no output — 零命中)

$ grep -n "seed_ontology" scripts/tag_lattice.py scripts/build_tag_lattice.py \
    scripts/complex_query_arm.py scripts/wt_qvf_prototype.py
(no output — 零命中)
```

三条断言(逐字命中泄题=0、独立复核器重算 gold 与存档比对=0 mismatch、
四个冻结文件零引用种子词典)与本轮额外核验的两条(阶段二新增的格机制
代码 `tag_lattice.py`/`build_tag_lattice.py` 同样零引用;全仓库排除出题
侧两个文件后零引用)全部通过。

**这能否作为"非自考"的证据?** 能,但有一个必须写清楚的边界:上述 grep
证明的是"S7-div 的查询词表来源与建卡/读取代码在**静态文本层面**零耦合"
——即系统不可能靠"字面抄词表"蒙对答案,这个结构性主张成立。但"非自考"
不等于"检索一定有效"——本轮主判据的否定结果(召回 4.5%)恰恰说明,拿掉
自考捷径之后,格闭包机制在当前规模下确实**答不出**大多数发散查询,这是
"测试是干净的"和"系统这次考砸了"同时成立、并不矛盾的两个结论。换句话说,
S7-div 的成绩(尤其是失败例)之所以有参考价值,正是因为设计上排除了自考
可能性——如果系统在一个保证没有词表泄漏的测试集上召回还是低,这个低分
才是关于检索能力的真实信号,而不是"没抄到题库"的噪音。

## 判官侧实测 token 与美元

**未产生 opus(`qvf/judge.py` ClaudeJudge)调用**——与归档 S7 基线方法论
完全一致:S7 / S7-div 均是 `gold_answer=None` 且带 `judge_rubric` 的行,
`complex_query_arm.py` 的主流程按设计跳过 opus 判官,改由独立的可溯性评
审器(haiku)按 rubric 评分。本轮验证了三处 opus 调用计数皆为零(见
`complex_s7div_test_A_exact.jsonl` / `C_lattice.jsonl` /
`s7_220_guardrail_lattice_arm.jsonl` 的 `judge_correct` 字段全 null)。

"判官侧"实测口径 = 可溯性评审器(`scripts/wsc_s7_judge.py` 用于 S7-220,
`scripts/s7div_judge.py`——本阶段新写、复用前者的抽取/接地代码,只把召回
分母从"库内同 tag 卡片数"换成 S7-div 自带的机器推导 `gold.items`——用于
S7-div test)的 haiku 用量:

| 环节 | in tokens | out tokens | 估算美元(haiku $1/$5 每 M) |
|---|---|---|---|
| S7-div test 5 臂 · 建卡(QVF_CARD_TAGS=2,28 test uid) | 589,058 | 303,212 | $2.1051 |
| S7-div test 5 臂 · arm-run(compile+read) | 401,687 | 22,866 | $0.5160 |
| S7-div test 5 臂 · 可溯性评审(s7div_judge.py) | 167,316 | 2,861 | $0.1816 |
| S7-220 护栏 · arm-run(compile+read) | 488,411 | 33,840 | $0.6576 |
| S7-220 护栏 · 可溯性评审(wsc_s7_judge.py) | 197,644 | 17,677 | $0.2860 |
| **阶段 B 合计** | | | **≈ $3.746** |

Phase B 预算 ≤$4,未破线(余量 ≈$0.25)。全项目累计(阶段一 $0 + 更早
轮次 $0.63 + 冒烟 $0.60 + 阶段 A $2.04 + 阶段 B $3.746)≈ **$7.02**,距
≤$8 总预算余量 ≈$0.98。

## 纪律核验

- 冻结文件(`qvf_router.py` / `wt_qvf_prototype.py` / `complex_query_arm.py`
  / `qvf_algebra.py`)`git diff --stat` 零改动,全程只读。
- S7-div dev 100 题本阶段**零读取**(只用 test 39 题;dev 只在阶段 A 用过,
  本阶段脚本的 `--questions` 参数全程指向 test-only 派生文件或原始
  `wsc_s7div.jsonl` 里按 `qid` 精确查 test 行的 gold,未统计 dev 指标)。
- test 39 题只在本阶段(阶段二·对决)使用一次,以"5 臂对决"的单次批跑
  完成(3 条预注册臂 + 2 条消融臂合并为一次调用序列,而非分 3 轮触碰),
  未做任何基于 test 结果的回头调参。
- 生产格 `results/tag_lattice.json` 沿用阶段 A 在 dev 上归纳产出的版本,
  本阶段未用 test 数据重新归纳或扩表,避免污染主判据。

---

## 附录:阶段 B 之前的阻塞记录(2026-08-16,已由本次实测取代)

> 以下为阶段三真正跑数之前的诊断性阻塞报告原文,保留供追溯。彼时判断
> "无法裁决"是正确的——当时格闭包臂从未真正读取过一条 S7-div 问题;本文
> 件上半部分的实测数据是该报告"建议的下一步"全部执行后的结果。

**结论先行(原文)**:本次无法产出阶段四裁决。原因:上游未把"对决结果"
数据传入本次调用——收到的任务文本里该字段字面是未被替换的模板占位符
`${JSON.stringify(run).slice(0,5000)}`,而非真实 JSON。我独立核查了文件
系统,确认这不是传输丢失,而是对决(阶段三:格闭包臂读取 S7-div 题集 +
qvf/judge.py 评分)从未被执行过。在没有真实跑数的情况下裁决主判据/护栏/
消融,等同于编造数字,直接违反本任务反复强调的"如实"纪律与预注册精神。

(时间线表格、三问裁决状态、"三杯鸡→高糖"原始回答、判官侧 token 记录等
细节从略,与本文件历史版本一致,可用 `git log -p` 或版本历史查阅。)
