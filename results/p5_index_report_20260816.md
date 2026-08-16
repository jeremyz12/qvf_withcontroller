# P5 阶段三:乱序验证 + 预注册裁决(2026-08-16)

## 判决(先判决,后数字)

**预注册判据③(乱序主判据)按字面被证伪**:任务书假设的"wikiP108000 链
current+point_in_time 两处 execute_plan tie-break 分歧",经本轮独立复核
**不是** tie-break 实例(两库该键 4 条 employer 记录日期互不相同,零平局;
真实成因是乱序库把职位后缀并入雇主值的写入侧内容差异)——这与
`qvf/store_index.py` 内已有的 REPRO NOTE 结论一致,本轮做了独立复算确认。
索引路径开/关对这两题的输出**逐字节相同**(仍是错的),整体 seq==shuf
同答率**不因开索引而变化**(68.9% 对 68.9%,持平),预注册设想的"上限约
82.2%"未出现。

但本轮同时发现一个任务书未预料到的**真实**同日平局实例(wikiP551002 的
residence 键,乱序建库侧混入一条同日"1873"的干扰记录),索引的内容指纹
平局裁决在这一题上把系统自己的答案从错(与金标准不符)改判为对——
`seq_agree_gold` 从 25/45(55.6%)升到 26/45(57.8%),可归因、可复现;但
`seq==shuf` 这一题仍判 False,因为乱序库另有一处独立的写入侧格式差异
("Cairo" vs "Cairo, Egypt")叠加在同一题上,遮蔽了这处修复对头条指标的
可见度。净效果:判据③在"整体同答率"意义上是空的负结果,在"系统-金标准
准确率"这个更细的量尺上有一处真实、微小、可复现的正结果。

**顺带修复的脚本 bug(`scripts/boundary_ooo_run.py::extract_answer`)本身
就是一项重要更正**:`first_last_first`/`first_last_last` 两算子此前只抓
取正则里的 value 分组、丢弃 date 分组,而 gold 是 `(value, date)` 二元组
——`answers_agree` 因而拿字符串跟列表比较,恒假。这不仅让这 24/45 题此前
从未产生过可用的"系统 vs 独立金答案"数字(`seq_agree_gold`/
`shuf_agree_gold` 对这两个算子恒为 0,呈现为噪声而非信号),还**静默漏检
了 4 处 seq/shuf 分歧**(日期粒度不同,如 seq 记 "2022-00-00" 而 shuf 记
"2022")——因为旧代码在判 `seq_eq_shuf` 时同样只比较裸 value,两侧的
value 恰好相同、date 不同的分歧完全看不见。修复后,45 对题的真实分歧数
从 B4 原报的 10 处升到 14 处,`seq==shuf` 从原报的 77.8%(35/45)降到诚实
的 68.9%(31/45)——**这是脚本 bug 修复带来的诚实收窄,不是索引或卡片
质量变差**。

---

## 一、修复的脚本 bug 与首次可用的"系统 vs 独立金答案"数字

### 1.1 bug 定位

`scripts/boundary_ooo_run.py`(冻结文件只读导入,自身可编辑,阶段一/二未
触碰过)第 50-51 行:

```python
_RE_FL_FIRST = re.compile(r"^First .+?: (.+?) \(from ")
_RE_FL_LAST = re.compile(r"most recent: (.+?) \(since ")
```

只捕获 value 分组;`extract_answer` 对 `first_last_first`/`first_last_last`
只返回 `m.group(1)`(纯字符串),而 `data/wsc_ooo.jsonl` 里这两个算子的
gold 是 `[value, date]` 列表(与 `scripts/boundary_gold.py::op_first_last`
的 `(v, t)` 元组语义一致)。`answers_agree` 对 `(str, list)` 组合直接落到
`a == b`,恒假。derived 文本本身其实带日期(如
`"First employer: Princeton University (from 1998-10-01); most recent: ..."`),
只是正则没抓。

### 1.2 修复

补抓 date 分组,`extract_answer` 对这两个算子返回 `(value, date)` 二元
组;`answers_agree` 比照 `scripts/boundary_run.py` 里 `longest` 算子的
既有先例(value 走 `_norm_val` 规整、date 精确比较,tuple/list 先各自转
列表逐位比较,避免 `tuple != list` 的假阴性)新增一支判定逻辑。四个冻结
文件与 `boundary_gold.py`/`boundary_run.py` 均未改动,只改了这一个可编辑
脚本。

### 1.3 修复后:首次给出"系统 vs 独立金答案"的可用数字(45 对题,scan 路径)

| 分量 | n | seq==shuf | seq vs gold | shuf vs gold |
|---|---|---|---|---|
| 全量 | 45 | 31 (68.9%) | 25 (55.6%) | 22 (48.9%) |
| current | 12 | 7 (58%) | 10 (83%) | 8 (67%) |
| count_changes | 9 | 8 (89%) | 7 (78%) | 7 (78%) |
| count_before | 8 | 7 (88%) | **0 (0%)** | 0 (0%) |
| first_last_first | 7 | 4 (57%) | 3 (43%) | 2 (29%) |
| first_last_last | 5 | 3 (60%) | 2 (40%) | 2 (40%) |
| point_in_time | 4 | 2 (50%) | 3 (75%) | 3 (75%) |

**独立新发现(与 P5 本身正交,如实记录不掩盖)**:`count_before` 的
`seq vs gold`/`shuf vs gold` 是系统性 0/8——系统答案恒比 gold 大 1
(如系统给 2、gold 给 1)。这不是本轮改动引入的(修 bug 前用旧脚本跑同一
批题也是同样的 0/8,只是旧脚本从未把这个数字暴露出来给人看),指向
`complex_query_arm.py`(冻结)里 `count_before` 的语义与
`boundary_gold.py` 独立金标准定义之间存在系统性边界差异(是否把"边界日
当天生效的那个值"计入"之前出现过的不同值数")。这是**写入/算子语义层
问题,不是索引读取层问题**,P5 的索引不改变、也不能修正这个数字(已验证
scan 与 index 路径在这 8 题上逐字节相同)——如实标注为一项超出 P5 范围
的既有发现,交由后续任务处理,不计入 P5 判据。

---

## 二、判据③(乱序主判据)逐条裁决

### 2.1 复用 B4 卡片库,走 `QVF_STORE_INDEX` 旗标对拍

用 `scripts/store_index_run.py --mode ooo_duel`(阶段一/二已建好、本轮
未改动此文件)重跑 B4 的 45 对题:

- `QVF_STORE_INDEX=0`(scan,冻结 `execute_plan` 逐字节引用)→
  `results/p5_store_index_ooo_duel_flag0.jsonl`
- `QVF_STORE_INDEX=1`(index,`qvf/store_index(_ops).py`)→
  `results/p5_store_index_ooo_duel_flag1.jsonl`

两次都用本轮修好的 `extract_answer`/`answers_agree`(`store_index_run.py`
直接从 `boundary_ooo_run.py` import 这两个函数,同一套比较口径)。

| 旗标 | n | seq==shuf | seq vs gold | shuf vs gold |
|---|---|---|---|---|
| flag0 (scan) | 45 | 31 (68.9%) | 25 (55.6%) | 22 (48.9%) |
| flag1 (index) | 45 | 31 (68.9%) | **26 (57.8%)** | 22 (48.9%) |

`seq==shuf` **头条指标完全不因开索引而变化**(逐题级 True/False 集合
逐字节相同,14 处分歧的题目清单不变,详见下表)——预注册设想的"消除
wikiP108000 那 2 处后整体升到约 82.2%"**没有出现**。`seq vs gold` 有
+1 题(25→26),下面 2.3 节精确定位并解释这一题。

### 2.2 逐字段对拍:index 与 scan 到底哪里不同

对 flag0/flag1 两份输出逐字段(`seq_answer`/`shuf_answer`/`seq_derived`/
`shuf_derived`)比较,**全 45×2=90 行里只有 1 个 uid(wikiP551002-Q107297)
的 3 道题(_ooo0/_ooo1/_ooo2,对应 first_last/current/count_changes,
共用同一条 residence 链)输出有任何字节级差异**,其余 44 个 uid 的全部
题目在两条路径下逐字节相同(含 13 处仍然分歧、31 处仍然一致的题)。这本
身就是判据③"不引入新分歧"这半句的直接证据:**index 路径没有在任何一
个原本 seq==shuf 的题上引入新分歧**(d1−d0 = ∅),也没有在任何非
wikiP551002 的题上改变输出。

### 2.3 wikiP108000(任务书点名的"2 处 tie-break"):独立复核,证伪

`wikiP108000-Q59200022` 的 employer 键在 seq/shuf 两库里各自只有 4 条
记录,`stated_date` 互不相同:

```
1985-11-01 / 1989-06-01 / 1995-10-01 / 1998-09-01
```

两库都没有同日重复记录——**不存在任何平局**,`execute_plan` 的排序步骤
在这两题上根本不涉及平局裁决。真实分歧源头是两次建卡的 value 字段文本
本身不同:

```
seq : "California Institute of Technology"
shuf: "California Institute of Technology, research fellow"
```

（另一条同理，shuf 侧把 "lecturer" 职位后缀并入了 University of
Birmingham 的值）。这是写入侧 LLM 抽取的内容级差异,索引读取侧的任何
排序/去重规则都无法修正一个已经写错的字符串字段——flag0/flag1 在这两题
上逐字节相同(仍然都错),**直接验证了这一判断**。这与 `qvf/store_index.py`
文件内已有的 REPRO NOTE 结论完全一致(本轮做的是独立复算确认,不是重新
得出);任务书对这 2 处的"tie-break"归因需要更正为"写入侧内容差异",
与 B4 报的另外 8 处同属一类,只是被最初的自动分诊错误地单独归了类。

### 2.4 wikiP551002:真实存在、且真实被索引修复的平局实例

`wikiP551002-Q107297` 的 seq 建卡库里,residence 键出现一条此前未被
诊断到的干扰记录:

```
r60 | 1873 | slot=residence                         | value="Cairo"
r67 | 1873 | slot=residence_furniture_issues_cairo   | value="wobbly writing desk at residence"
```

两条**同日**(都是 "1873"),且该卡片库**完全无键控**
(`slot_class` 全部为 `None`——与 S5/S6/S7 用的 `wt_cards_v42` 库不同,
后者每条记录都带 `slot_class`)。当查询槽位是 "residence" 时,冻结实现
`_select_pool_frozen` 因为 `keyed=[]`(无一条记录带 `slot_class`),直接
落到无键回退分支:

```python
pool = [r for r in recs if _slot_match(r.get("slot", ""), slot or "")]
return sorted(pool, key=lambda r: _rec_date(r, mem_dates))
```

`_slot_match` 把 `residence_furniture_issues_cairo`(子串含
"residence")也判定命中,于是两条同日记录被并入同一个池子;Python
`sorted()` 是稳定排序,同日时按原始列表位置决定先后——r60 在 r67 之前
入表,"current"(取链尾/最新值)于是**报出 r67 的干扰值**
"wobbly writing desk at residence"。这正是任务书描述的那一类隐患
(平局由呈现位置决定,不看 stated_date 之外的任何内容),只是**发生在
wikiP551002 而不是 wikiP108000**。

索引路径(`qvf/store_index.py::sort_key`)的次级排序键是内容指纹
(sha256(slot_class, value, source_span, condition)),不看列表位置;
在这一对记录上,内容指纹恰好把 r60(Cairo)排在 r67(干扰值)之后,
"current" 于是正确报出 "Cairo",与 gold 一致——这就是 2.1 节
`seq_agree_gold` 25→26 那 +1 题的完整来源,**可复现、可归因、方向正确**
（系统自身答案由错变对，判据①允许的"tie-break 修正方向正确"例外条款
若适用于本场景，这里的方向确实是正确的）。

但 `seq==shuf` 这一题仍然是 False:shuf 建卡库里同一 residence 链没有
干扰记录(无平局问题),但把值写成了 "Cairo, Egypt" 而不是 "Cairo"——
一处独立的写入侧格式差异,恰好叠加在同一道题上,遮住了 tie-break 修复
对头条指标的可见度。

### 2.5 为什么 REPRO NOTE 此前说"零真实平局实例"——诊断工具的盲区

`qvf/store_index.py` 内已有的 REPRO NOTE(阶段一遗留,本轮之前写成)称
用 `scripts/store_index_equiv.py --scan-ties` 扫过全部 15×2 库、45 对题,
"零个真实同日多值平局实例"。复核该工具的实现(`scan_ties` 函数)发现:

```python
for r in recs:
    cls = r.get("slot_class")
    if not cls:
        continue          # 无键记录被直接跳过
    groups.setdefault((r.get("owner") or "", cls), []).append(r)
```

它只在 `(owner, slot_class)` 分组内找平局。B4 的 OOO 卡片库**全部记录
`slot_class` 都是 `None`**(与 S5/S6/S7 的 `wt_cards_v42` 完全不同),
所以这个工具在 OOO 库上永远不会形成任何分组,天然报 0——不是因为没有
平局,是这把尺子看不到无键回退池里的平局(wikiP551002 那一对就活在无键
回退池里)。这不影响判据①在 S5/S6/S3 上的结论(那三套语料库全部有键控,
且判据①是用双路径直接执行对拍验出来的,不依赖 `scan_ties`),但需要
更正 REPRO NOTE"vacuously inapplicable"这句的适用范围:判据③指认的
tie-break 机制在 B4 数据集上**是真实存在的**(1 处,wikiP551002),只是
不在任务书点名的 uid 上;`scan_ties` 工具本身有盲区,已如实记录,建议
后续若要在无键卡片库上复核平局需另补无键回退池扫描,本轮未去改
`scan_ties`(诊断工具,非四个冻结文件,但也不属于本次任务书要求项,故
只记录不改)。

### 2.6 判据③终裁

| 子判据 | 任务书原始预期 | 实测结果 | 裁决 |
|---|---|---|---|
| wikiP108000 current+PIT 的 tie-break 分歧被消除 | 2 处消除 | 0 处(根本不是 tie-break 实例,index 逐字节不变) | **证伪** |
| 不引入新分歧 | — | d1−d0=∅,44/45 uid 逐字节不变 | **通过** |
| 整体同答率变化 | 升到约上限 82.2% | 68.9%→68.9%,持平 | **未达成,且预期本身依据的诊断有误** |
| (追加发现)真实 tie-break 实例是否存在、能否被索引正确处理 | 未预料到此问题形态 | 1 处(wikiP551002),索引处理方向正确,系统-金标准准确率 +1 题 | 追加的窄口径正结果 |

**综合裁决:判据③按字面预注册口径不通过**——任务书对"2 处 tie-break"
的具体归因是错的,整体同答率不因索引而改变。但索引设计针对的那类问题
(平局由呈现位置决定)在本数据集上**确实存在过一例真实实例**,并且
索引的处理方式在这一例上是**正确的方向**(系统自身准确率提升、无回归)
——是一个规模很小但诚实、可复现的正面证据,不构成判据③要求的整体性
通过,但也不是纯粹的负结果,如实两面记录。

---

## 三、判据①②④:复用阶段二结果,本轮未改动相关代码,结论不变

阶段二已完成的三项(生产口径完整 `--data` 对拍、不变量压测、复杂度基准)
本轮未修改 `qvf/store_index.py`、`qvf/store_index_ops.py`,`git diff`
对四个冻结文件与这两个新模块均确认无变化(冻结文件本就应为空 diff;
两个新模块本轮零编辑),故复用阶段二数字,不重复计算成本:

- **判据①(等价性护栏)**:S5 全量 314/314(100%)清洁通过;S7 切片
  50/50(100%)清洁通过;S6 生产口径 29/33(87.9%),4 处分歧全部可追溯
  到同一张卡 wikiM003-Q106386024 上两条同日不同值的 residence 记录
  (写入侧问题,读取侧无法修正)——**按预注册字面口径未通过**(裁决
  维持阶段二结论)。
- **判据②(不变量)**:12,500 次插入即检验(250×50)+ 400 次插入顺序
  无关性对照,零失败——**通过**(裁决维持阶段二结论)。
- **判据④(复杂度)**:O(n²) 参照实现二次标度确认(逐倍比 3.90-4.04×);
  索引 `chain_depth`/`asof` 在 n=10³/10⁴/10⁵ 全部实测,p99<13ms;11 算子
  全量补测,`chain_depth`/`asof` 亚线性,其余 9 个"证据枚举类"算子天然
  O(链长)(基准设计的必然结果,非索引缺陷)——**通过**(裁决维持阶段二
  结论)。

---

## 四、四条预注册判据总裁决

| 判据 | 裁决 |
|---|---|
| ①等价性护栏(硬性) | **未通过**(S6 87.9%<100%,4 处同源写入侧问题,不在允许例外范围内) |
| ②不变量 | **通过**(12,500+400 次压测零失败) |
| ③乱序主判据 | **未通过**(字面预期证伪:任务书点名的 2 处不是 tie-break 实例,整体同答率不因索引变化;但发现 1 处真实 tie-break 实例,索引处理方向正确,narrow 意义上有 +1 题的可归因正结果) |
| ④复杂度 | **通过**(chain_depth/asof 达到亚线性,经验复杂度曲线完整) |

**四条中两条通过、两条未通过**,与阶段二的裁决格局一致(阶段二同样是
①③未通过、②④通过);本轮的增量贡献是:(a) 修复了一个真实存在、
此前从未被发现的脚本 bug,首次拿到 45 题的系统-金标准准确率数字;
(b) 把判据③的负结果从"任务书假设有误但未验证"精确为"任务书假设的
具体 uid 归因确认有误,但索引针对的那类问题在数据集里确实有一个真实
实例、且索引处理正确";(c) 发现并记录了阶段一 REPRO NOTE 所用诊断工具
(`scan_ties`)的一处结构性盲区(只扫有键分组,漏掉无键回退池)。

---

## 五、成本与只读纪律

零 LLM 成本——本轮全部工作是重跑既有纯代码脚本(`store_index_run.py`)
与一处正则/比较逻辑修复(`boundary_ooo_run.py`),已 grep 确认无
`anthropic`/`client.messages.create` 调用。四个冻结文件
(`qvf_router.py` / `wt_qvf_prototype.py` / `complex_query_arm.py` /
`qvf_algebra.py`)`git diff` 为空,全程只读导入。

## 六、§7.3 定理槽终裁文本(草稿,供写入 `study_logs/QVF_methods_formalization_20260814.md`,待批未自动写入)

> 以下文本用于替换该文件第 158 行 `### §7.3 P5:增量双时态索引的不变量
> (待批)` 及其后的命题槽占位段落。本轮未自动提交这处编辑——判据①③是
> 混合/部分负结果,是否以及如何合并进正式定理槽由用户裁定。

### §7.3 P5:增量双时态索引的不变量(**08-16 阶段三终裁,窄口径成立**)

> **命题 3(窄口径,成立)**:增量双时态索引 `StoreIndex`(定义见
> `qvf/store_index.py`)满足四条完整性不变量 I1(替换边无环)/ I2(任一
> 时刻每键至多一个活跃值)/ I3(链内日期单调,允许同日并列)/ I4(关系边
> 端点存在)在任意有限次 `insert_record` 调用序列下保持(按操作归纳,
> 含回溯拼接);`chain_depth` 与 `asof` 两个定位原语相对冻结实现的
> O(n)/O(n log n) 扫描,分别达到 O(1) 摊销查表与 O(log m)(m=链长)
> 二分查找。

**不在命题 3 范围内、字面预注册但未通过的两条(如实分离,不并入命题)**:

1. **"索引执行与扫描执行对 11 算子逐字节等价"不成立**,按预注册的
   S5 全量 314 + S6 33 + S7 切片 50 三段护栏实测:S5=314/314(100%)、
   S7=50/50(100%),但 **S6=29/33(87.9%)**——4 处分歧全部同源于一张卡
   (wikiM003-Q106386024)上两条同日不同值、且缺显式 `stated_date` 的
   residence 记录,根因在写入侧(建卡阶段对同日冲突记录的处理),索引
   读取侧的任何确定性平局规则都无法修正一个内容本身有歧义的输入——
   已排查确认不属于预注册允许的"tie-break 修正方向正确"例外。
2. **"平局由呈现位置决定"这一隐患类别的乱序实测(B4 45 对题复算)未
   验证出预注册设想的具体实例**:任务书点名的 wikiP108000 链
   current/point_in_time 两题经独立复核**不是**同日平局(4 条记录日期
   互不相同),真实成因是写入侧内容差异(职位后缀被并入雇主值),索引
   开/关对这两题逐字节相同。但复算过程中**确实发现了一处任务书未点名
   的真实同日平局**(wikiP551002 的 residence 键,一条无键卡片库里混入
   的同日干扰记录),索引的内容指纹次级排序键相对冻结实现的列表位置
   次级排序键,在这一例上把系统答案从错误改判为与独立金标准一致——
   方向正确、可复现,但只影响 45 题里的 1 题,整体 seq==shuf 同答率
   未因索引变化(68.9%→68.9%,预注册设想的~82.2%上限未出现)。

**测量纪律三条(仿 §7.2 先例,违反即被抓)**:
①只能说"chain_depth/asof 两个定位原语达到亚线性",不可说"11 算子整体
提速"——11 算子里另外 9 个"证据枚举类"算子(current/trajectory/
join_at_change 等)必须把答案支持链的每条记录吐成文本,天然 O(链长),
任何正确实现都绕不开这个下限,已实测其延迟随 n 近似线性增长(基准把
记录集中在约 12 个键上以便与 O(n²) 参照公平对照,真实部署场景键更多、
单键链更短,数字预计更低,但本命题不主张这一点);②只能说"S5/S7 两段
护栏 100% 通过",不可说"整体等价性护栏通过"——S6 的 87.9% 是预注册里
明写的三段之一,不可选择性引用;③只能说"发现一处真实平局并被索引
正确处理",不可说"验证了预注册假设的乱序隐患"——预注册假设的具体
uid 归因被证伪,替换为一个更窄、独立发现的正例。

**测量口径**:等价性 S5/S6/S7 见 `results/p5_index_equiv_stage2.jsonl`；
不变量压测见 `results/p5_index_stress_stage2.jsonl`(12,500 次插入 +
400 次顺序无关性对照,零失败)；复杂度见
`results/p5_index_bench_stage2.jsonl` + `p5_index_bench_ops_stage2.jsonl`；
乱序复算见 `results/p5_store_index_ooo_duel_flag0.jsonl` /
`_flag1.jsonl` 与 `results/p5_index_report_20260816.md`(阶段三,本轮)。

---

## 七、产出文件

- `scripts/boundary_ooo_run.py`(本轮唯一编辑:修复 first_last 二元组
  比较 bug)
- `results/p5_ooo_duel_flag0_fixed.jsonl`(修 bug 后、原脚本、scan 路径,
  45 对题)
- `results/p5_store_index_ooo_duel_flag0.jsonl`(`store_index_run.py`,
  `QVF_STORE_INDEX=0`)
- `results/p5_store_index_ooo_duel_flag1.jsonl`(`store_index_run.py`,
  `QVF_STORE_INDEX=1`)
- `results/p5_index_report_20260816.md`(本文件)
