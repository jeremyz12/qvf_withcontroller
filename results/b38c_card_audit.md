# 批 38-C 卡片级复核:批 38-B 机制假说是否成立?

**范围声明**:本批零 API 调用(仅读文件),不落地任何新判官/读者产物,不改动任何店。
产出仅本文件 + 会话临时脚本(不入库)。

**复核对象**:`results/opt_batch38b_verdict.md` §四/§五 留下的机制假说 ——
"槽位归一把非金标的相邻政治身份也拉进了同一车道、稀释了 change_count/
count_before 类问题的计数"(原文明示"未做逐卡人工复核,列为待验证的机制假说,
不作确证陈述")。本批做的就是这份逐卡人工复核。

**方法**:车道规则直接复用 `scripts/b38b_score.py` 的既有函数
(`ledger_rows`/`val_match`/`yr`,车道计算逻辑与 `diag_uid`/`lanes` 逐字一致,
未重新发明),保证"每店自己的车道规则"与批 38-B 诊断表的 extra/missing 计数
对得上号(见下方核验)。三条目标链:`wikiP39037-Q3525068`、
`wikiP39039-Q11801709`、`wikiP39003-Q6248447`。语料 36 链清单:
`results/b35_sample_uids.txt`。

**口径核验**:本批车道逻辑在 36 链 × 3 店上复算出的"车道内非金标卡数"
= v45 **13**、v47s **4**、v47sk **7** —— 与 `opt_batch38b_verdict.md` §四表格的
`extra` 列(13/4/7)逐字节相同,证明车道复算与批 38-B 诊断脚本同源。

---

## 一、三条目标链:金标 vs 车道卡片

### 1.1 `wikiP39037-Q3525068`(金标 4 行,gold slot = position)

| date | value |
|---|---|
| 1771-01-31 | member of the 13th Parliament of Great Britain |
| 1774-00-00 | member of the 14th Parliament of Great Britain |
| 1784-00-00 | member of the 16th Parliament of Great Britain |
| 1794-04-21 | colonial governor of Guadeloupe |

| store | 车道(own lane rule) | 车道卡数 | 命中金标 | 非金标 |
|---|---|---|---|---|
| v45 | `occupation` | 1 | 1 | **0** |
| v47s | `occupation, parliament_membership` | 4 | 4 | **0** |
| v47sk | `position` | 2 | 2 | **0** |

v47sk 车道卡片(全部是金标命中,逐字如下):

| date | slot | value | owner | source_span(前120字) |
|---|---|---|---|---|
| 1771-01-31 | position | 13th Parliament of Great Britain | user | I've been returned as a member of the 13th Parliament of Great Britain |
| 1774-00-00 | position | 14th Parliament of Great Britain | user | I'm now a member of the 14th Parliament of Great Britain |

**关键发现:这条链没有一张非金标车道卡** —— H2/H3 关心的"稀释"机制在这条链
上**完全没有发生**。真正的问题是 **1784(16th Parliament)与 1794(殖民地总督)
两行金标在 v47sk 店里整体缺失,不是被错误并道,是从提取阶段就没有产出这两张
卡**(逐字核验:对 v47sk 店 `wikiP39037-Q3525068.json` 的全部 30 条记录做
`"16th"`/`"governor"`/`"guadeloupe"` 关键词检索,**零命中**;同一检索对 v47s
店 58 条记录能命中两张对应卡)。

**规模核验(非车道层面,链级)**:v47sk 该链总卡数 **30**,v47s 该链总卡数
**58** —— 单链少了 28 张卡,是 36 链里跌幅最大的一条(第二名 `wikiP39006-
Q5220520` 少 24 张)。但把这条差值放进全部 36 链的分布里看,跌幅从 -28 到
+26 两端都有(`wikiP108018-Q86139829` 反而 +26),说明**这是 v47sk 从零重建
时提取器本身的批次间波动(sampling variance),不是槽位归一规则系统性造成的**
—— 归一规则只重写 `slot`/`owner` 字段,不删除记录;记录数量的增减只能来自
抽取阶段的那次独立 LLM 调用本身少写/多写了几条卡。

### 1.2 `wikiP39039-Q11801709`(金标 8 行,gold slot = position)

| date | value |
|---|---|
| 1802-00-00 | High Sheriff of Herefordshire |
| 1826-06-07 | member of the 8th Parliament of the United Kingdom |
| 1830-07-29 | member of the 9th Parliament of the United Kingdom |
| 1831-04-28 | member of the 10th Parliament of the United Kingdom |
| 1832-12-10 | member of the 11th Parliament of the United Kingdom |
| 1835-01-06 | member of the 12th Parliament of the United Kingdom |
| 1837-07-24 | member of the 13th Parliament of the United Kingdom |
| 1841-06-29 | member of the 14th Parliament of the United Kingdom |

| store | 车道 | 车道卡数 | 命中金标 | 非金标 |
|---|---|---|---|---|
| v45 | `parliament_membership, position` | 8 | 8 | **0** |
| v47s | `civic_office, parliament_membership` | 9 | 8 | **1** |
| v47sk | `position` | 10 | 8 | **2** |

非金标车道卡(逐字):

| store | date | slot | value | owner | source_span(前120字) | 分类 |
|---|---|---|---|---|---|---|
| v47s | 1830-07 | parliament_membership | 9th Parliament of the United Kingdom | user | as of today I'm officially a member of the 9th Parliament of the United Kingdom | (a) 金标值原样重述(与 1830-07-29 那行是同一事件的重复卡) |
| v47sk | 1824-03-20 | **position** | working on a big campaign at job | user | with this big campaign I'm working on | **(d)** 一次性任务/事件误判为职务("正在忙一个项目",不是被授予的头衔) |
| v47sk | 1831-02-15 | **position** | has a new job, finding it tough | user | trying to focus on the positive aspects of the job, but it's been tough | **(d)** 泛泛的"换了份新工作、有点难熬"的情绪吐槽,没有具体头衔,不是政治职务 |

**这条链是假说被证实的地方**:v47sk 把两张与"政治职务"毫无关系的、泛泛的
"工作/项目"闲聊句子归进了 `position` 车道 —— 且这两张卡在 v47s(槽位名还是
`civic_office`/`parliament_membership`)里**根本不存在于车道**(因为它们原本
的槽位名——大概率是 `work_task`/`job_update` 一类——既不匹配金标值,也不含
"position"/"civic_office"/"parliament_membership"子串,不会被车道规则收进来)。
是归一把 `slot_class` 判成 `position` 之后,才第一次把这两张卡拉进了政治职务
车道。

**十题映射预告**:`v2cb`(count_before,金标 8,两个读者都答 10 = +2)、
`v2cc`(change_count,金标 7,两个读者都答 9 = +2)—— 与"车道多了 2 张
非金标卡"精确对上,详见 §三。

### 1.3 `wikiP39003-Q6248447`(金标 3 行,gold slot = position)

| date | value |
|---|---|
| 1964-00-00 | member of the First Chamber |
| 1971-01-11 | member of the Swedish Riksdag |
| 1974-05-06 | Representative of the Parliamentary Assembly of the Council of Europe |

| store | 车道 | 车道卡数 | 命中金标 | 非金标 |
|---|---|---|---|---|
| v45 | `academic_position, political_position` | 4 | 3 | **1** |
| v47s | `political_position` | 3 | 3 | **0** |
| v47sk | `position` | 4 | 3 | **1** |

非金标车道卡(逐字):

| store | date | slot | value | owner | source_span(前120字) | 分类 |
|---|---|---|---|---|---|---|
| v45 | 1967-04-22 | academic_position | teaching assistant nomination | user | my recent teaching assistant nomination in the department | (c) 提名/候选,非已获得的在任状态 |
| v47sk | 1967-04-22 | **position** | teaching assistant nominee | user | my recent teaching assistant nomination in the department | **(c)** 同一事件,归一后换了措辞仍是提名,不是在任状态 |

**这条链部分证实假说,但不是"相邻政治身份",是"相邻职业身份"**:v45 里这张
教学助理提名卡的槽位名是 `academic_position`,由于车道规则的子串匹配
(`"position" in "academic_position"` 为真)本来就已经被 v45 自己的车道规则
收进车道 —— v47s 的车道恰好不含这张卡(v47s 抽取器没有产出这条记录,不是
归一把它挡在外面)。v47sk 归一后这张卡重新出现,且换了个措辞
("nomination"→"nominee"),被 `slot_class=position` 直接收编。**净效果与
v45 一样**(都是 1 张非金标卡混进车道),v47sk 相对 v47s 是"新增",相对 v45
是"复现"。

**十题映射预告**:`v2cb`(count_before,金标 2,两个读者都答 3 = +1)、
`v2cc`(change_count,金标 2,两个读者都答 3 = +1)—— 与"车道多 1 张非金标卡"
精确对上。

---

## 二、非金标车道卡分类(三链范围,step 3)

分类口径(七类,任务书原定义):
(a) 金标值原样重述(同值、晚会话) (b) 他人状态(owner≠user 或谈论的是别人)
(c) 计划/提名/候选/假设(非已持有状态) (d) 一次性任务/事件误判为角色
(e) 真实持有但不在金标链里的荣誉/成员身份 (f) 金标值的不同措辞(值归一问题)
(g) 其他

| store | (a) | (b) | (c) | (d) | (e) | (f) | (g) | 合计 |
|---|---|---|---|---|---|---|---|---|
| v45 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | **1** |
| v47s | 1 | 0 | 0 | 0 | 0 | 0 | 0 | **1** |
| v47sk | 0 | 0 | 2 | 2 | 0 | 0 | 0 | **4** |

三链范围内,**(b) 他人状态一次都没出现** —— 三条链本身都是单一叙述者
(entity 全为 `user`),owner 过滤器在这三条链上无的放矢。v47sk 相对 v47s
在这三条链上**净增 3 张非金标车道卡**(1 张 (c) 类的重复提名卡 + 2 张全新
的 (d) 类工作闲聊卡),(d) 类在这三条链的 v45/v47s 里**从未出现过**,是
v47sk 独有的新退化(与 §四判决呼应)。

---

## 三、十道"两个读者都还错"的题:逐题卡片级归因

来源:`results/b38b_score_out.txt` §5「Questions BOTH v47sk readers still get
wrong」,共 10 题。读者看到的账目 = `scripts/repro_batch3.render_card_ledger`
的**整本账目**(`QVF_LEDGER_VIEW` 默认空,批 38/38-B 均未设置该环境变量 ——
`scripts/wt_qvf_prototype_b38b.py:218` 与 `results/opt_batch38b_prereg.md:100`
均明确记录"默认关"),即读者看到的是**全部槽位按日期排序的整本账目**,不是
预先按车道过滤过的子集;下表的"车道卡"是账目里与该问题金标槽位同车道的那些
行,读者要在整本账目里自己认出哪些行属于同一属性。

| qid | 类型 | 金标 | 两读者的答案 | 车道内非金标卡 | 归因 |
|---|---|---|---|---|---|
| `wikiP39037-Q3525068_v2cb` | count_before | 4 | 2 | 0 | **缺行**:1784/1794 两行金标整体未被 v47sk 抽取出来(§一.1),车道只剩 2 张卡,不是被稀释,是被截断 |
| `wikiP39037-Q3525068_v2cc` | change_count | 3 | 1 | 0 | 同上,车道 2 张卡只能数出 1 次变化 |
| `wikiP39037-Q3525068_v2fl` | first_vs_last | first=13th Parl.; last=殖民地总督 | last 答成 14th Parliament | 0 | 同上,车道里最后一张卡就是 14th Parliament,因为真正的"最后一行"从未被抽取 |
| `wikiP39039-Q11801709_v2cb` | count_before | 8 | 10(+2) | **2**(d 类工作闲聊卡) | **稀释**:2 张非金标 `position` 卡精确解释 +2 的偏差 |
| `wikiP39039-Q11801709_v2cc` | change_count | 7 | 9(+2) | **2** | 同上,2 张卡插进日期序列各多算一次变化 |
| `wikiP39003-Q6248447_v2cb` | count_before | 2 | 3(+1) | **1**(c 类提名卡) | **稀释**:1 张非金标 `position` 卡精确解释 +1 |
| `wikiP39003-Q6248447_v2cc` | change_count | 2 | 3(+1) | **1** | 同上 |
| `wikiP108009-Q64855331_v2cc` | change_count | 2 | 3(+1) | **2**(c 类,见下) | **稀释+跨属性串店**:该链金标槽位是 `employer`,但 v47sk 把 3 张真金标 employer/postdoc 卡也判成了 `slot_class=position`,同车道还多了 2 张 UC Berkeley "incoming"/"admitted" 申请状态卡(均非已在职状态);净效果多算 1 次变化 |
| `wikiP39017-Q24568849_v2lt` | longest_tenure | High Sheriff of Hampshire | 答成 2nd Parliament | **0**(该链诊断本就 5/0/0/0,车道完美) | **非车道问题**:车道 5 张卡与金标逐字对齐、日期精确到年,读者仍算错任期最长的一段——纯推理错误,且 `plainctx@sonnet5`(全文直读)在这题上**同样答错**,说明与卡片/归一机制无关 |
| `wikiP39033-Q5331705_v2cb` | count_before | 6 | 5(-1) | **0**(v47s 与 v47sk 该链诊断数字逐字相同,均 6/0/0/0) | **非车道问题、非 v47sk 独有**:车道 6 张卡与金标 1:1 精确对齐,`v47s@sonnet5` 在这题上**同样答错**(仅 v47s@haiku 答对)——车道数据本身无缺陷,是读者计数推理的问题,且不是归一新引入的(v47s 已经错) |

**归因小结(10 题)**:
- **3 题(wikiP39037 全部)**:根因是 v47sk 建店时的抽取召回波动(整链少了
  28 张卡),与槽位归一/车道稀释机制**无关** —— 这直接推翻了假说对这条链的
  适用性。
- **5 题(wikiP39039×2、wikiP39003×2、wikiP108009×1)**:根因确认是车道稀释,
  但稀释物不是假说猜测的"相邻政治身份",而是**(c)提名/候选状态**与
  **(d)无具体头衔的工作闲聊/求学申请状态**,外加一种假说未预见到的**跨属性
  串道**(`employer`型金标链被整体误判为 `position` 类)。
- **2 题(wikiP39017、wikiP39033)**:车道账目与金标逐字对齐,错误发生在
  读者的计数/推理层面,与写入侧规范化完全无关(其中 1 题在全文直读臂和
  v47s 臂上同样答错,证明是题目本身难,不是本批引入的退化)。

---

## 四、语料全量(36 链 × 3 店)非金标车道卡分类分布(step 5)

按各链自己的金标槽位(不限定"position")计算车道,36 链清单见
`results/b35_sample_uids.txt`。非金标车道卡总数与 §口径核验一致:
v45=13、v47s=4、v47sk=7。

| store | (a)重述 | (b)他人 | (c)提名/候选 | (d)任务误判 | (e)非金标荣誉 | (f)值归一 | (g)其他 | 合计 |
|---|---|---|---|---|---|---|---|---|
| v45 | 2 | 0 | 1 | 1 | 0 | **6** | 3 | 13 |
| v47s | 2 | 0 | 0 | 1 | 0 | 0 | 1 | 4 |
| v47sk | 2 | 0 | **3** | **2** | 0 | 0 | 0 | 7 |

逐条清单(全部 24 条,非三目标链的补充证据):

**v45 的 6 条 (f) 类**——全部来自同一种模式:`wikiP39017-Q24568849` 的 4 张
`member of Nth Parliament of the United Kingdom` 卡与 `wikiP39006-Q5220520`
的 2 张 `Member of Nth Northern Ireland Assembly` 卡,值本身与金标语义完全
相同,但金标写的是"member of **the** Nth Parliament...",卡片漏了这个
"the",导致 `val_match` 的整词子串规则两边都不成立——**这是记分器/比对逻辑
的伪影,不是抽取错误、更不是车道稀释**:这些卡本来就该算对,只是"少一个
定冠词"把它们同时打成了"金标缺行"+"车道多余"两笔账。

**v45/v47s 共有的 (g) 类**——`wikiP39000-Q4976518` 的 `family_composition`
("有 3 个姐妹")与 `wikiP39017-Q24568849` 的 `household_composition`
("两口人和一只宠物")都是因为车道规则的子串匹配把 "position" 误认成了
"**com**position" 词根的一部分(`household_composition`/`family_composition`
两个词里都含有连续字符串 "position")——**这是车道规则本身的一个巧合性
bug,不是归一机制或读者会真正混淆的东西**(账目里这两行清清楚楚标着
`family_composition:`/`household_composition:`,读者不会把"我有 3 个姐妹"
当成政治职务)。`wikiP54001-Q16225986` 的 `team_size`("四个团队成员")同理,
是 "team" 这个词在"工作小组"和"自行车车队"两个语义域撞车,与政治身份无关。

**v47sk 的 5 条 (c)+(d)**——`wikiP39039` 的 2 条 (d)、`wikiP39003` 的 1 条
(c) 已在 §一/§二 详述;新增的是 `wikiP108008-Q53283502` 的 2 条 (a)(金标
Tsinghua/Laboratoire 值原样重述,不影响计数)与 `wikiP108009-Q64855331` 的
2 条 (c)(UC Berkeley "incoming"/"admitted" 状态,见 §三)。

**净判决**:**(f) 类(值归一/记分器伪影)只在 v45 出现,是这套车道诊断口径
自身的已知局限,不构成"归一引入新代价"的证据**;真正在 v47sk 净新增、且
v45/v47s 从未出现过的类别是 **(c) 提名/候选** 与 **(d) 任务误判**,合计从
v47s 的 1 条涨到 v47sk 的 5 条——**语料全量的分布与三目标链的分布方向一致**,
不是三链的巧合。**(b) 他人状态与 (e) 非金标荣誉在三家店、36 链范围内一次
都没出现** —— 假说列出的"多人身份混入"("committee 之类的荣誉头衔"）在这批
数据里完全没有实例。

---

## 五、结论

**猜想被部分证实,但机制被找错了名字**。批 38-B §四/§五 的原始猜想——
"槽位归一把非金标的相邻**政治身份**也拉进了同一车道、稀释了计数"——在
"稀释确实发生""被稀释的问题类型确实是 count_before/change_count"这两点上
成立;但在**稀释物是什么**这一点上被证据修正:

1. **不是"相邻政治身份"**。三条目标链 + 语料全量 36 链里,**没有一条
   非金标车道卡是"另一个真实存在、但不在金标链里的政治职务或团体身份"**
   ((e) 类计数 0/0/0)。真正混进 `position` 车道的是两种东西:
   - **(c) 提名/候选状态**("被提名为教学助理""获 UC Berkeley 录取"——
     这些是尚未真正持有的状态,不是已授予的头衔);
   - **(d) 没有具体头衔的泛泛工作/求学闲聊**("在忙一个大项目""换了份新
     工作、有点难熬"——这些原本大概率带着 `work_task`/`job_update` 一类
     与"position"毫不相关的槽位名,归一后被 `slot_class` 判进了 `position`)。
2. **v47sk 独有的新退化**:(c)+(d) 在 v47s 只有 0+1=1 条,v47sk 涨到 3+2=5
   条,且 §三 逐题核验里,这两类卡精确解释了 5/10 道"两个读者都还错"的题
   (wikiP39039×2、wikiP39003×2、wikiP108009×1)的偏差方向与偏差量
   (+1/+1/+2/+2/+1,与非金标卡数一一对应)。
3. **但另外 3/10 道题(全部在 `wikiP39037-Q3525068`)与车道稀释完全无关**——
   根因是这条链在 v47sk 重建时整体少抽了 28 张卡(含 2 行金标),是抽取器
   批次间的召回波动,不是 `slot_class` 判据把这两行金标"挤出"了车道(车道里
   根本找不到这两行的任何变体)。再有 2/10 道题(`wikiP39017`、`wikiP39033`)
   车道账目与金标逐字对齐、无任何非金标卡,错误是读者的计数/推理失误,且其中
   1 题在全文直读臂上同样答错——与写入侧规范化无关。**10 题里只有 5 题能
   归因到"稀释"机制,3 题是缺行,2 题是纯推理误差**。

**schema 修复建议排序**(目标:去掉最多的 10 题偏差,同时不动任何金标行):

| 规则 | 能修的题 | 判断依据 |
|---|---|---|
| **断言类型过滤(assertion-type filter)** —— 剔除措辞暗示"计划/候选/进行中/未完成"的记录(如 "nomination"/"nominee"/"incoming"/"admitted"/"working on"/现在进行时的求职求学状态),不让它们进入任何 slot_class 车道 | **5/10**(wikiP39039×2、wikiP39003×2、wikiP108009×1) | 这 5 题的全部非金标车道卡((c)+(d) 类)都符合"非既定持有状态"的语义特征,且没有一张是金标行——过滤不会误伤金标 |
| owner 过滤(排除 owner≠self 的记录) | **0/10** | 三链 + 36 链范围内 (b) 类恒为 0,这条规则在本次样本里无的放矢 |
| 重述合并(同值记录去重) | **0/10** 直接相关(会消掉 v47sk 的 2 条 (a) 类,但那 2 条本来就不影响 wikiP108008 链的任何一道题) | (a) 类卡片的值与某条金标完全相同,即使不合并,读者把两条相同值当一次状态处理的概率本来就高(§三 wikiP39039 的 v47s 重复卡没有导致任何一题出错) |
| 值归一(改进 `val_match`/`nv`,如识别缺省定冠词) | **0/10**,但能把 v45 诊断表里的 6 条 (f) 伪影从"missing+extra"各消 6 笔,让 v45 的账目保真度数字更真实 | (f) 类只出现在 v45,与本批的 10 题(全部来自 v47sk)无关,是诊断口径本身该修的债,不是本批 canonicalisation 的问题 |

**结论一句话**:断言类型过滤是四个候选里唯一对本批 10 道残余题有实测效力
的规则,且不会碰到任何一行金标(所有可疑记录都不是金标命中);owner 过滤
和重述合并在这批数据里没有作用面;值归一修的是记分口径的旧账,不是 v47sk
引入的新债。下一批建议:把"断言类型过滤"做成 `slot_class` 判据的一个必要
条件(而不是在现有四类闭集上加类目),并且优先在 `wikiP39037-Q3525068` 这条
链上单独复查一次 v47sk 的建店日志/原始 LLM 输出,确认 28 张卡的缺失是否
可复现(如可复现,说明抽取器本身在长会话链上有 truncation 倾向,这是一个
独立于本次假说、需要单开一批验证的新线索)。
