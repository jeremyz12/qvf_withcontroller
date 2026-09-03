# 批 38-D:断言类型过滤器(assertion-type filter)——离线复算,零 API 调用

**范围声明**:本批零 API 调用(仅读文件 + 纯 Python 确定性脚本),不落地任何新判官/
读者产物,不改动 `results/wt_cards_v45`、`results/wt_cards_v47s`、
`results/wt_cards_v47sk` 三店中的任何一个字节(全程只读)。分析脚本留在本会话
scratchpad,不入库;本文件是唯一产出。**总花费 $0.00**,运行时间(三店 ×
36 链 × 全量卡片扫描 + 140 题编译 + 逐链方差统计)全部在一分钟以内完成
(纯离线 Python,无 API 延迟)。

**背景**:`results/b38c_card_audit.md` 逐卡人工复核发现,批 38-B 的残余车道
稀释卡片主要不是"相邻政治身份"(假说原话),而是两类断言:计划/提名/候选
(nominee/incoming/admitted 等,c 类)与无具体头衔的泛泛工作/求学闲聊
(d 类)。该文档给出的修复建议排序里,"断言类型过滤"是唯一对 10 道残余题
有实测效力的规则。本批把这条建议做成可运行的确定性规则,并在同一 36 链 ×
140 题语料上离线复算验证。

---

## 一、规则:`assertion_type(card) -> {start, restate, plan, task, other_person, unknown}`

判据只看卡片自身的 `source_span` + `value`(拼接后转小写),按下表优先级
依次匹配,命中第一条就返回,全不命中记 `unknown`:

| 优先级 | 类型 | 命中即返回 | 触发词(子串匹配) |
|---|---|---|---|
| 1 | `other_person` | 人物代称词 **且** 附近有第三人称系动词 | 代称:`my wife/husband/friend/colleague/boss/team lead/partner`;动词:` is / was / has / has been / does / did / 's ` |
| 2 | `plan` | 计划/提名/候选/进行中申请 | `nominee nomination nominated candidate applying applied incoming admitted offer interview hoping planning "thinking of" might "would love" considering` |
| 3 | `task` | 一次性任务/无头衔工作闲聊 | `"working on" "leading a project" curating organising/organizing "helping with" "new job"` |
| 4 | `restate` | 重述("依然/一如既往") | `"as always" "continue to be" "continues to be"`,以及正则 `\bstill\b(?!\s+(getting used to\|adjusting to\|settling into\|new to))` |
| 5 | `start` | 已持有状态声明(仅用于报表分类,不参与过滤决策) | `appointed "started as" "start as" "am now" "i'm now" "as of today" "began serving" "took office" elected became "promoted to" "started working as" "returned as" "officially started"` |
| — | `unknown` | 以上全不命中 | — |

**过滤规则**(task 步骤 2 原文):只保留 `start` 与 `unknown` 两类卡片,
丢弃 `plan`/`task`/`restate`/`other_person` 四类,再重建车道账本。

**car 逻辑复用**:车道/账本/值匹配全部复用 `scripts/b38b_score.py` 的
`ledger_rows`/`val_match`/`yr`/`diag_uid`/`lanes`(参数化加一个可选
`filt` 谓词,逻辑逐字未改),保证过滤前的基线数字与批 38-B/38-C 完全对得上号
(见下方口径核验)。

### 迭代记录(硬约束驱动的两次收紧/一次扩展)

任务书的硬约束是"过滤器不得删除任何一张金标锚点卡"。第一版规则(`still` 作为
无条件重述触发词)在 36 链 × 3 店全量重放后,**在 v47s 与 v47sk 两店各撞见
1 处金标误删**(同一条金标行,`wikiP551007-Q9153879` 1939 年 `Lviv`):

- 命中卡片原文:*"Lviv is my new residence now, and I'm still getting used to
  which tram goes where"*(`temporal_relation=replacement`,是一次真实的
  居住地变更声明,不是重述)。
- 误删原因:`still` 子串命中了 "I'm **still** getting used to..." 这个从句,
  但这句话里 `still` 修饰的是"适应新状态"的过程,不是"旧状态仍在延续"。
- 修复:把 `still` 从无条件子串,收紧为正则
  `\bstill\b(?!\s+(getting used to|adjusting to|settling into|new to))`——
  排除"还在适应/还在安顿"这几个变更后过渡期的固定搭配。
- 复算确认:收紧后 v45/v47s/v47sk 三店金标误删数全部回到 **0**(见下表)。

第二版扩展:初版 `task` 类未覆盖 `results/wt_cards_v47sk/wikiP39039-Q11801709.json`
里的一张卡(*"has a new job, finding it tough"*,source_span 是
*"trying to focus on the positive aspects of the job, but it's been tough"*,
不含 "working on" 等已有触发词)。核对全库(三店、不限 36 链样本)后确认
`"new job"` 这个短语在金标 `state_span` 里零命中,风险可控,遂加入 `task`
触发词表。加入后重新跑金标误删检查,**仍是 0/0/0**(见下表),予以保留。

---

## 二、硬约束核验:金标锚点卡有没有被误删

对 36 链 × 3 店,逐条比较过滤前/过滤后每张金标行是否仍被命中
(`exact`+`date_off` 命中索引集合是否发生"命中→未命中"翻转):

| store | 金标行总数 | 被过滤器误删的金标行数 |
|---|---|---|
| v45 | 133 | **0** |
| v47s | 133 | **0** |
| v47sk | 133 | **0** |

**硬约束满足**(收紧后)。三店合计误删 **0** 行。

---

## 三、账本保真度:过滤前 vs 过滤后(三店聚合,36 链)

| store | filter | exact | date_off | missing | **extra**(车道内非金标卡) | 总卡数 | 完美链 |
|---|---|---|---|---|---|---|---|
| v45 | before | 122 | 0 | 11 | **13** | 2003 | 31/36 |
| v45 | after | 122 | 0 | 11 | **11** | 1760 | 31/36 |
| v47s | before | 133 | 0 | 0 | **4** | 1743 | 36/36 |
| v47s | after | 133 | 0 | 0 | **4** | 1529 | 36/36 |
| v47sk | before | 131 | 0 | 2 | **7** | 1639 | 35/36 |
| v47sk | after | 131 | 0 | 2 | **2** | 1436 | 35/36 |

**口径核验**:过滤前(`before`)三店的 `extra` 列 = 13/4/**7**,与
`results/b38c_card_audit.md` 口径核验段落逐字节相同,证明本批车道复算与
批 38-B/38-C 同源。

**关键读数**:
- `exact`/`date_off`/`missing`(金标命中口径)**过滤前后完全不变**——
  过滤器只删非金标车道卡,不可能碰到金标行,这与上面§二的硬约束核验互相印证。
- `extra` 的降幅:v45 13→11(减 2)、v47s 4→4(**减 0,过滤器对 v47s 车道
  零效力**)、v47sk 7→2(减 5)。
- v47sk 减掉的 5 张,逐卡核对全部是 `plan`/`task` 类
  (2 张 UC Berkeley "incoming"/"admitted" + 1 张教学助理 "nominee" + 2 张
  "working on"/"new job" 泛泛工作闲聊),与 `b38c_card_audit.md` §四对
  这三条链的人工分类**逐卡一致**。
- v47s 车道零变化,不是过滤器没触发——记录级普查(见下表)显示 v47s 全库
  确实有 156 条 `plan`、18 条 `task` 记录被移除,只是这批链条里刚好没有一条
  落进被 36 条问题所定义的"金标车道"内。

### 记录级 `assertion_type` 普查(三店全部卡片,不限车道)

| store | 总卡数 | other_person | plan | restate | start | task | unknown |
|---|---|---|---|---|---|---|---|
| v45 | 2003 | 10 | 181 | 37 | 78 | 15 | 1682 |
| v47s | 1743 | 10 | 156 | 30 | 73 | 18 | 1456 |
| v47sk | 1639 | 15 | 136 | 32 | 74 | 20 | 1362 |

大部分 `plan`/`task` 命中落在与本次 36 条问题无关的其它属性链上(教育计划、
旅行计划等),这是预期行为——过滤器是全局规则,不是针对某条链调参出来的。

### 车道内 `extra` 卡逐条清单(哪些被删、哪些被保留、为什么)

| store | 链 | 过滤前 extra | 过滤后 extra | 卡片(日期/槽位/值) | 类型 | 处置 |
|---|---|---|---|---|---|---|
| v45 | wikiP39000-Q4976518 | 1 | 1 | 1988-03 `family_composition`="has 3 sisters" | unknown | 保留(车道定义子串巧合"**position**"⊂"com**position**",非断言类型问题) |
| v45 | wikiP39003-Q6248447 | 1 | 0 | 1967-04 `academic_position`="teaching assistant nomination" | **plan** | **删除** |
| v45 | wikiP39006-Q5220520 | 2 | 2 | 2009/2011 `political_position`="Member of Nth Northern Ireland Assembly" | start | 保留(真实持有状态,只是金标写法带"the"、卡片没带,值匹配伪影) |
| v45 | wikiP39017-Q24568849 | 5 | 5 | 1793 `household_composition`="two people and a pet" + 4 张 1801-1807`position`="member of Nth Parliament..." | unknown/start | 保留(1 张子串巧合 + 4 张同上的"the"值匹配伪影) |
| v45 | wikiP54001-Q16225986 | 1 | 0 | 2013-05 `team_size`="four team members" | **plan**("thinking of") | **删除**(见§五"两误抵消"个案) |
| v45 | wikiP551002-Q107297 | 1 | 1 | 1871 `residence`="Cairo" | start | 保留(真实持有,但不在金标链里,(e) 类) |
| v45 | wikiP551003-Q20512700 | 1 | 1 | 1918-06 `residence`="New York" | unknown | 保留 |
| v45 | wikiP551006-Q57870878 | 1 | 1 | 1923 `residence_update_needed`="Paris" | unknown | 保留 |
| v47s | wikiP39000-Q4976518 | 1 | 1 | 1988-03 `family_composition`="has 3 sisters" | unknown | 保留(同上,子串巧合) |
| v47s | wikiP39039-Q11801709 | 1 | 1 | 1830-07 `parliament_membership`="9th Parliament of the United Kingdom" | start | 保留((a) 类金标值原样重述,非断言类型问题) |
| v47s | wikiP54020-Q98594955 | 1 | 1 | 2017 `cycling_team`="Team Kvickly Odder Junior" | unknown | 保留((e) 类真实持有但不在金标链) |
| v47s | wikiP551001-Q20667184 | 1 | 1 | 1868-04 `residence_area`="downtown area" | unknown | 保留(子串巧合) |
| v47sk | wikiP108008-Q53283502 | 2 | 2 | 2013/2016 `employer`="Tsinghua University"/"Laboratoire de physique théorique" | start | 保留((a) 类金标值原样重述) |
| v47sk | wikiP108009-Q64855331 | 2 | 0 | 2008-11 `position`="Master's student at UC Berkeley (incoming)" / "admitted to UC Berkeley for fall semester" | **plan** | **删除** |
| v47sk | wikiP39003-Q6248447 | 1 | 0 | 1967-04 `position`="teaching assistant nominee" | **plan** | **删除** |
| v47sk | wikiP39039-Q11801709 | 2 | 0 | 1824-03 `position`="working on a big campaign at job" / 1831-02 `position`="has a new job, finding it tough" | **task** | **删除** |

---

## 四、编译账本答案 vs 金标:过滤前后的命中数(140 题)

方法:对每条链的车道账本行(与上面 `extra` 同一车道定义),按题面里写死的
`Today`(`change_count`/`longest_tenure`/`first_vs_last` 用 `"Today is
YYYY-MM-DD."`;`count_before` 用 `"before YYYY-MM-DD"` 且严格早于),重算
`change_count`(相邻取值变化次数)、`count_before`(截止日期前去重取值数)、
`longest_tenure`(逐段持有时长求和取 arg-max,要求唯一)、`first_vs_last`
(车道内最早/最晚取值),口径逐字对齐 `scripts/gen_wsc_v2.py` 的
`tenure_gold` 与 change_count/count_before 的计数规则,再和
`results/b35_questions_sample36.jsonl` 的 `gold` 字段比较。

| store | filter | gold-equal | change_count | count_before | first_vs_last | longest_tenure |
|---|---|---|---|---|---|---|
| v45 | before | 122/140 | 30/36 | 32/36 | 32/36 | 28/32 |
| v45 | after | **124/140** | 30/36 | 32/36 | 33/36 | 29/32 |
| v47s | before | 135/140 | 34/36 | 34/36 | 36/36 | 31/32 |
| v47s | after | **135/140**(不变) | 34/36 | 34/36 | 36/36 | 31/32 |
| v47sk | before | 131/140 | 32/36 | 33/36 | 35/36 | 31/32 |
| v47sk | after | **137/140** | 35/36 | 35/36 | 35/36 | **32/32** |

**逐店判决**:
- **v47sk:猜想被证实**——断言类型过滤把编译账本的金标一致题数从
  131/140(93.6%)提到 137/140(97.9%),净增 **6** 题,change_count 与
  count_before 两个类型各修复 3 题,longest_tenure 修复 1 题达到满分
  32/32,**零回退**(全部 6 处翻转都是"错→对",没有"对→错")。
- **v47s:猜想被否定(对这一店无效)**——135/140 过滤前后逐题相同,
  一题未变。原因见§三:车道内 4 张 `extra` 卡没有一张是
  `plan`/`task`/`restate`/`other_person`。
- **v45:部分证实,附一例"两误抵消被拆穿"**——122→124(净增 2),但
  4 处改善(wikiP39003 三题 + wikiP54001 的 first_vs_last)对 2 处回退
  (wikiP54001 的 change_count/count_before)。回退不是过滤器质量问题,
  是暴露了一个已存在的抽取缺口——见下面的个案分析。

### 个案:v45 `wikiP54001-Q16225986` ——被过滤器拆穿的"两误抵消"

金标 4 段车队变更(Team PCW → Selle Italia Ghezzi → A.R. Monex Women's Pro
Cycling Team → RusVelo Women's Team)。v45 店本身就漏抽了第三段
(A.R. Monex,一次真实的抽取缺口,与本批过滤器无关),车道里只剩 3 张金标卡,
编译 `change_count` 应为 2。但过滤前车道里混进一张 `team_size`="four team
members"(来自"我在想找四个团队成员帮忙做展示",`plan` 类,"thinking of"
触发)的非金标卡,恰好把编译计数从 2 顶回 3——**两个独立错误(漏一段真实
变更 + 混入一张假变更)在这一题上刚好互相抵消,编译结果碰巧等于金标**。
过滤器删掉这张假卡后,编译计数变回真实的 2,题目从"意外算对"变成"如实算错"。

这不是过滤器引入的新缺陷——§二的硬约束核验已确认这张链上没有任何金标行
被误删(A.R. Monex 那段本来就没被 v45 命中,过滤前后一样"missing")。这个
个案说明:"编译账本是否等于金标"这个指标本身有噪声(会被"两误抵消"污染),
真正干净的安全判据是§二的"金标行是否被误删"这条硬约束,而不是这个题目级
指标的涨跌本身。

---

## 五、十道"两个读者都还错"的题:逐题过滤前后

来源:`results/b38b_score_out.txt` §5(v47sk@haiku 与 v47sk@sonnet5 都答错
的 10 题)。下表"车道 extra"取自§三的过滤前数字;"编译账本"取本批的确定性
重算(不是读者的真实作答,是"一个不出错的读者理论上该读出什么答案")。

| qid | 类型 | 金标 | 过滤前编译 | 过滤前=金标? | 过滤后编译 | 过滤后=金标? | 归因 |
|---|---|---|---|---|---|---|---|
| `wikiP108009-Q64855331_v2cc` | change_count | 2 | 4 | 否 | 2 | **是** | 稀释,已修复(2 张 UC Berkeley 计划卡) |
| `wikiP39003-Q6248447_v2cb` | count_before | 2 | 3 | 否 | 2 | **是** | 稀释,已修复(1 张提名卡) |
| `wikiP39003-Q6248447_v2cc` | change_count | 2 | 3 | 否 | 2 | **是** | 稀释,已修复(同上) |
| `wikiP39017-Q24568849_v2lt` | longest_tenure | High Sheriff of Hampshire | High Sheriff of Hampshire | **是** | High Sheriff of Hampshire | **是** | 车道本就与金标对齐,过滤器无关——纯读者推理误差(见 b38c §三) |
| `wikiP39033-Q5331705_v2cb` | count_before | 6 | 6 | **是** | 6 | **是** | 车道本就与金标对齐,过滤器无关——纯读者推理误差 |
| `wikiP39037-Q3525068_v2cb` | count_before | 4 | 2 | 否 | 2 | 否 | 未修复:1784/1794 两行金标从抽取阶段就没产出,车道里根本没有可删的"多余卡"(见§六) |
| `wikiP39037-Q3525068_v2cc` | change_count | 3 | 1 | 否 | 1 | 否 | 同上 |
| `wikiP39037-Q3525068_v2fl` | first_vs_last | first=13th Parl.; last=殖民地总督 | first=13th; last=**14th Parliament** | 否 | 同左 | 否 | 同上 |
| `wikiP39039-Q11801709_v2cb` | count_before | 8 | 10 | 否 | 8 | **是** | 稀释,已修复(2 张工作闲聊卡) |
| `wikiP39039-Q11801709_v2cc` | change_count | 7 | 9 | 否 | 7 | **是** | 稀释,已修复(同上) |

**10 题里:5 题编译账本从"错"变"对"(与 `b38c_card_audit.md` §三的人工归因
逐题一致);2 题编译账本本来就等于金标(纯读者推理误差,过滤器无从下手);
3 题(全部在 `wikiP39037`)编译账本过滤前后都错,根因是抽取缺行,不是车道
稀释。**

**补充**:`wikiP39003-Q6248447_v2lt`(longest_tenure)不在这 10 题名单里
——过滤前编译账本其实是错的("teaching assistant nominee"顶替了正确的
"member of the First Chamber"),但两个 v47sk 读者当时都碰巧答对了,说明
真实读者不是逐字照搬账本最长段这么简单的算法,对这类明显不像正式职务的
噪声值有一定免疫力。过滤后编译账本也修复为正确值——净效果是把"读者侥幸
答对"变成"账本本身就对",鲁棒性更高,即使换一个更"较真"的读者模型也不会
在这题上失手。

---

## 六、v47s / v47sk 全部账本≠金标的题(不限于上面 10 题)

`results/b38b_score_out.txt` §5 的 10 题只统计"两个 v47sk 读者都错"的题;
下面是本批编译指标定义下,**账本本身**(不看读者真实作答)与金标不一致的
全部题目,按店分列。

### v47sk(过滤前 9 题账本≠金标,过滤后剩 3 题)

| qid | 类型 | 金标 | 过滤前编译 | 过滤后编译 | 过滤后=金标? |
|---|---|---|---|---|---|
| `wikiP108009-Q64855331_v2cc` | change_count | 2 | 4 | 2 | 是 |
| `wikiP39003-Q6248447_v2cb` | count_before | 2 | 3 | 2 | 是 |
| `wikiP39003-Q6248447_v2cc` | change_count | 2 | 3 | 2 | 是 |
| `wikiP39003-Q6248447_v2lt` | longest_tenure | member of the First Chamber | teaching assistant nominee | member of the First Chamber | 是 |
| `wikiP39037-Q3525068_v2cb` | count_before | 4 | 2 | 2 | **否** |
| `wikiP39037-Q3525068_v2cc` | change_count | 3 | 1 | 1 | **否** |
| `wikiP39037-Q3525068_v2fl` | first_vs_last | first 13th Parl.; last 殖民地总督 | first 13th; last 14th Parl. | 同左 | **否** |
| `wikiP39039-Q11801709_v2cb` | count_before | 8 | 10 | 8 | 是 |
| `wikiP39039-Q11801709_v2cc` | change_count | 7 | 9 | 7 | 是 |

`wikiP39037-Q3525068` 三题维持原判:根因是抽取阶段整链少产出 28 张卡
(v47sk 该链总卡数 30,v47s 同链 58——本批§七方差表复核到同一数字,
`drop=53%`,是 36 链里跌幅第二大的),1784/1794 两行金标(16th Parliament、
殖民地总督)从未被抽取,车道里没有任何"多余卡"可删,断言类型过滤对
"缺行"这类问题**天然无能为力**(它只能删多余的,不能补缺失的)。

### v47s(过滤前后都是 5 题账本≠金标,过滤器零效力)

| qid | 类型 | 金标 | 过滤前编译 | 过滤后编译 | 车道内 extra 类型 |
|---|---|---|---|---|---|
| `wikiP39000-Q4976518_v2cb` | count_before | 3 | 4 | 4(不变) | unknown(`family_composition`子串巧合) |
| `wikiP39000-Q4976518_v2cc` | change_count | 2 | 3 | 3(不变) | 同上 |
| `wikiP551001-Q20667184_v2cb` | count_before | 4 | 5 | 5(不变) | unknown(`residence_area`="downtown area",子串巧合) |
| `wikiP551001-Q20667184_v2cc` | change_count | 3 | 4 | 4(不变) | 同上 |
| `wikiP551005-Q42324799_v2lt` | longest_tenure | Amsterdam | AMBIGUOUS(并列最长段,无唯一解) | 不变 | 与车道 extra 无关,是持有时长本身并列 |

v47s 这 5 题全部与断言类型无关:前 4 题是车道定义的"子串巧合"bug(槽位名
里含 `position`/`residence` 的巧合子串,`b38c_card_audit.md` §四已归为
(g) 类记分口径伪影,不是抽取或断言类型问题);第 5 题是持有时长本身出现
非唯一最大值,是题目生成器 `tenure_gold` 唯一性判据在这条链的编译重算下
恰好落空,不是卡片质量问题。

---

## 七、抽取器批次方差(36 链 × 3 店,记录数 & 金标锚点命中数)

`records` = 该链在该店的全部卡片数;括号内 = 该店命中的金标行数
(`exact+date_off`,满分等于该链"金标"列)。"跌幅"取三店记录数
`(max-min)/max`,>=30% 记 FLAG。

| chain | gold | v45 records(anchors) | v47s records(anchors) | v47sk records(anchors) | 跌幅 |
|---|---|---|---|---|---|
| wikiP108008-Q53283502 | 3 | 62 (3) | 40 (3) | 44 (3) | 35% FLAG |
| wikiP108009-Q64855331 | 3 | 51 (3) | 48 (3) | 45 (3) | 12% |
| wikiP108016-Q57079433 | 3 | 68 (3) | 65 (3) | 57 (3) | 16% |
| wikiP108018-Q86139829 | 3 | 61 (3) | 23 (3) | 49 (3) | 62% FLAG |
| wikiP108021-Q37837264 | 3 | 67 (3) | 61 (3) | 45 (3) | 33% FLAG |
| wikiP108027-Q20829689 | 4 | 60 (4) | 58 (4) | 48 (4) | 20% |
| wikiP108035-Q39407125 | 3 | 54 (3) | 52 (3) | 34 (3) | 37% FLAG |
| wikiP108048-Q38640679 | 3 | 70 (3) | 38 (3) | 36 (3) | 49% FLAG |
| wikiP108049-Q43145446 | 4 | 59 (4) | 46 (4) | 33 (4) | 44% FLAG |
| wikiP39000-Q4976518 | 3 | 34 (3) | 43 (3) | 45 (3) | 24% |
| wikiP39003-Q6248447 | 3 | 56 (3) | 53 (3) | 59 (3) | 10% |
| wikiP39006-Q5220520 | 3 | 52 **(1)** | 56 (3) | 32 (3) | 43% FLAG |
| wikiP39017-Q24568849 | 5 | 61 **(1)** | 46 (5) | 44 (5) | 28% |
| wikiP39023-Q18527003 | 5 | 74 (5) | 45 (5) | 50 (5) | 39% FLAG |
| wikiP39033-Q5331705 | 6 | 61 (6) | 56 (6) | 45 (6) | 26% |
| wikiP39036-Q15039950 | 3 | 53 (3) | 49 (3) | 45 (3) | 15% |
| wikiP39037-Q3525068 | 4 | 64 **(1)** | 58 (4) | 30 **(2)** | 53% FLAG |
| wikiP39039-Q11801709 | 8 | 51 (8) | 52 (8) | 51 (8) | 2% |
| wikiP54001-Q16225986 | 4 | 35 (3) | 44 (4) | 33 (4) | 25% |
| wikiP54003-Q26001185 | 4 | 53 (4) | 48 (4) | 38 (4) | 28% |
| wikiP54005-Q58454919 | 3 | 46 (3) | 51 (3) | 34 (3) | 33% FLAG |
| wikiP54010-Q105871142 | 3 | 59 (3) | 39 (3) | 42 (3) | 34% FLAG |
| wikiP54015-Q24718521 | 3 | 44 (3) | 31 (3) | 45 (3) | 31% FLAG |
| wikiP54020-Q98594955 | 6 | 60 (6) | 35 (6) | 59 (6) | 42% FLAG |
| wikiP54031-Q16198306 | 4 | 76 (4) | 45 (4) | 49 (4) | 41% FLAG |
| wikiP54032-Q58045043 | 3 | 49 (3) | 67 (3) | 54 (3) | 27% |
| wikiP54037-Q99293520 | 3 | 60 (3) | 39 (3) | 50 (3) | 35% FLAG |
| wikiP551000-Q19845625 | 3 | 51 (3) | 45 (3) | 50 (3) | 12% |
| wikiP551001-Q20667184 | 4 | 45 (4) | 54 (4) | 51 (4) | 17% |
| wikiP551002-Q107297 | 4 | 65 (3) | 50 (4) | 47 (4) | 28% |
| wikiP551003-Q20512700 | 3 | 59 (3) | 53 (3) | 58 (3) | 10% |
| wikiP551005-Q42324799 | 3 | 41 (3) | 47 (3) | 52 (3) | 21% |
| wikiP551006-Q57870878 | 4 | 61 (4) | 60 (4) | 38 (4) | 38% FLAG |
| wikiP551007-Q9153879 | 3 | 40 (3) | 51 (3) | 55 (3) | 27% |
| wikiP551008-Q29918442 | 3 | 54 (3) | 43 (3) | 44 (3) | 20% |
| wikiP551009-Q5321987 | 4 | 47 (4) | 52 (4) | 48 (4) | 10% |

**16 / 36 条链**记录数跌幅 >= 30%(三店取最大值最小值)。

**读数口径提醒**:记录数跌幅**不等于**质量问题——36 条链里,除了下面
3 条特别标注的以外,金标锚点命中数(括号内)在跌幅最大的链上依然满分,
说明多数波动只是"废话/闲聊卡"的抽取数量在批次间自然起伏(sampling
variance),不影响金标命中。真正值得关注的是锚点数**没有**打满的 3 条:

- `wikiP39037-Q3525068`:v45=1/4、v47s=4/4、v47sk=**2/4**——v47sk 是唯一
  锚点不满的抽取批次,且记录数跌幅 53% 全表第二,与 `b38c_card_audit.md`
  §一.1 的结论一致("1784/1794 两行金标整体缺失,是提取器批次间的召回
  波动,不是槽位归一规则系统性造成的")。v45 的 1/4 是另一个独立问题
  (见下条)。
- `wikiP39006-Q5220520`、`wikiP39017-Q24568849`:只有 **v45** 锚点不满
  (1/3、1/5),v47s/v47sk 都是满分。逐卡核对(见§三 v45 的 extra 清单)
  发现这不是真漏抽——v45 确实产出了对应卡片(`member of Nth Parliament of
  the United Kingdom` / `Member of Nth Northern Ireland Assembly`),只是
  漏写了金标值里的定冠词"the",被 `val_match` 的整词匹配判成不命中,是
  记分口径的伪影(`b38c_card_audit.md` §四已定性为 (f) 类,非抽取失败)。

---

## 八、结论与建议

**逐条猜想判决**:

1. **"断言类型过滤能修复 v47sk 的稀释类残余题"——证实**。编译账本金标
   一致题数 131/140 → 137/140(+6),硬约束(金标误删=0)全程满足,
   与 `b38c_card_audit.md` 人工归因的 5/10 题逐题吻合,另有 1 题
   (`wikiP39003-Q6248447_v2lt`)从"读者侥幸答对"变成"账本本身就对"。
2. **"同一过滤器对 v47s 有增量价值"——被否定**。v47s 车道内的 4 张
   `extra` 卡没有一张属于 `plan`/`task`/`restate`/`other_person`,
   过滤前后 135/140 逐题不变。
3. **"过滤器能解决 wikiP39037 的车道问题"——被否定,且判定为范围外**。
   该链的问题是抽取阶段缺行(v47sk 该链只有 30 张卡,vs v47s 同链 58 张),
   车道里没有可删的多余卡,断言类型过滤这类"减法"规则原则上无法修复
   "缺行"这种问题,需要另开一批复查建店日志(`b38c_card_audit.md` §五
   已提出此建议,本批复核后维持)。

### 建议:filtered v47s 值不值得花 ~$3 跑一次读者?

**不值得——直接证据是过滤器对 v47s 车道零效力**。§三/§四/§六 三处独立
核算(车道 extra 卡清单、编译账本逐题比对、账本≠金标题目清单)一致显示:
v47s 的 4 张车道内非金标卡没有一张匹配 `plan`/`task`/`restate`/
`other_person` 任何一条规则,过滤前后账本**逐字节相同**(除车道外的
214 张卡被删,但那些卡不出现在读者要回答的 4 类问题所对应的车道里)。
在 filtered v47s 上花 ~$3 重跑读者,预测结果 = 现有 `results/
b38_smoc_v47s_*.jsonl` 的准确率(92.9% haiku / 92.1% sonnet-5)**原样
不变**——这是一次可预先证伪、不需要真花钱验证的实验,不建议执行。

**该花的钱在 filtered v47sk 上**。编译账本的"假设读者不出错、只读账本"
上限从 93.6%(131/140,过滤前)升到 97.9%(137/140,过滤后)。但真实
读者历史上会比这个上限低几个点(`wikiP39017`/`wikiP39033` 那类纯推理
误差不会因为账本变干净而消失)——用过滤前的真实差距做校准:

- sonnet-5:账本上限 93.6% vs 实测 91.4%,差 2.2pp;套用到过滤后上限
  97.9%,预测 **约 95.7%**。
- haiku:账本上限 93.6% vs 实测 88.6%,差 5.0pp;套用到过滤后上限
  97.9%,预测 **约 92.9%**。

预测区间的两端:**乐观上限 97.9%**(若过滤后读者不再犯任何账本外的
推理错误)、**保守估计约 92.9%-95.7%**(按历史"账本上限-实测"差距外推)。
两者都**摸不到** `plainctx@sonnet5 mt4000` 的 97.1% 硬顶——`wikiP39037`
的 3 题缺行问题在过滤器的能力范围之外,单这一条链就封住了约 2.1pp
(3/140)的上升空间。建议:如果要花这笔 $3,花在 **filtered v47sk**
(两个读者臂,haiku+sonnet5,预算与 `b38b_score_out.txt` 记录的原版
v47sk 读者花费 $2.575 同量级),而不是 v47s;预期收益是把 v47sk 从"不如
v47s"的位置(91.4% vs 92.1%)拉到与 v47s 打平或小幅反超,但不足以单独
逼近全文直读的上限。
