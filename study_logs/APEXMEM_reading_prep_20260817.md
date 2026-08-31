# APEX-MEM 伴读材料(Jeremy 亲读用)

**日期**:2026-08-17
**性质**:伴读材料。不是分析报告——是你边读边对的东西。
**读哪一版**:优先 `aclanthology.org/2026.acl-long.749.pdf`(camera-ready,pp. 16470–16489)。已核实:**camera-ready 与 arXiv v1 的节号、附录字母完全一致**,所以本材料的所有节号/表号在两个版本上都能用,不需要再花 30 秒对表题。
**本材料的三个来源**:① 08-17 已有的全文级七镜报告(`QVF_groupmeeting_papers_20260817.md` §3.1);② 本轮 camera-ready 逐格加深(13 表 + 附录 A–I);③ 本轮对核实档五.3 分界句的原文核实。
**溯源标记**:全文用【已有】=08-17 报告已有的结论;【新增】=本轮新查出;【更正】=本轮推翻或修正了已有结论。**凡标【更正】的地方,你在组会上说旧版会被当场翻书查到。**

---

## 〇、开卷五分钟须知

这篇是 Amazon 的五人组(Banerjee, Moshtaghi, Subramanian, Misra, Chadha),**ACL 2026 主会长文**,pp. 16470–16489,20 页,13 张表、4 张图、附录 A–I。做的事:把长期对话抽成属性图上带时间的事实断言,**只增不改**地存全部版本,读取时由一个 ReAct 多工具代理(SchemaViewer / EntityLookUp / GraphSQL / Search)**临场写出只读 SQL**,交给 SQLite **确定性执行**,冲突留到取回后由代理"选最新"来消解。它对 QVF 最危险的原因只有一句:**它已经占了"确定性结构化执行 + 写入侧保留全部版本 + 端到端 token 成本报告"这三块地,与 QVF 只差"闭集算子按路由编译"vs"LLM 临场生成 SQL"这一线**;而它自报的 SQL 执行成功率 93.4–97.6% 加失败自恢复 87%,已经把 QVF 原本要立的那条动机("LLM 临场生成查询不可靠")打掉了大半。所以你读它的目标**不是**评价它好不好,而是三件事:**(1) 确认它到底占走了什么,把 QVF intro/related work 里已经不能原样写的句子逐句划掉;(2) 找出它没测而 QVF 能测的缝(目前最干净的一条是"语法成功率 ≠ 语义正确率");(3) 学它的成本分解与工具调用统计的报法——这两项是同类论文里少见的高质量工程证据,也是 QVF 的成本口径纪律该抄的样板。**读完你必须能填出本材料第二节末尾那两栏,填不出就是没读进去。

---

## 一、阅读路线与时间预算(90 分钟)

**不按论文顺序读。** 论文顺序会让你先花 20 分钟读 §3 的本体形式化(最长、最像方法、最有技术感),而 §3 对应的贡献 1 **全篇零受控实验**。先读消融表,再读 §3,你才会带着正确的问题。

开读前 2 分钟准备三样:
1. 一张纸,左上角**逐字抄下** §1 末段 "Our contributions are threefold" 的三条(1 属性图+本体 / 2 仅追加存储 / 3 多工具代理)。这是全程记分卡,每读一节回来给某条打一个「有受控证据 / 只有跨系统对照 / 零证据」。**逐字抄,不要总结——后面两处攻击点全靠原文措辞。**
2. 计算器(练习里要做三轮减法)。
3. 一句话记住骨架:**三条贡献,一张消融表。** 读这篇的全部技巧就是把三条贡献逐条连到证据上,看哪条连不上。

| # | 读什么 | 分钟 | 为什么在这个位置 |
|---|---|---|---|
| 0 | 摘要 + §1 末段贡献三条 | 5 | 抄下三条。⚠️ 注意摘要与 §1 措辞不同(见警觉句 ②) |
| 1 | **Table 3(APEX-MEM Ablations)** | 8 | 全篇唯一的受控实验,只有三行。骨架从这三行最快看清:可信内核 =「四个工具累加」 |
| 2 | §4.1–§4.4(四个工具) | 12 | 现在你知道 Table 3 换的是哪四个东西了。重点读 §4.3 GraphSQL 执行前校验那句 |
| 3 | **Table 1(LOCOMO 分类别主表)** | 10 | 头条数字唯一出处 + 全部基线。**逐行抄底座名**,这是主表隐藏的自变量。注意它有 **7 个结果列**,末列是 `w/o Adv.` |
| 4 | §3.1–§3.3(本体 / 实体属性消解 / 事实抽取) | 12 | 贡献 1 的机制在这里。带着一个问题读:「这一节描述的任何设计选择,在 Table 3 里被换过吗?」 |
| 5 | **附录 F + Table 12** | 5 | 贡献 2 的**全部**证据就这一张表。你会发现 5 分钟太多(见练习 C) |
| 6 | Table 4(LongMemEval)+ Table 5(SealQA) | 8 | Table 4 是这篇真正立得住的地方,Table 5 是最脆的地方 |
| 7 | 附录 C + Table 9 + Table 10 | 10 | 成本。慢读,一段话里有两个 total |
| 8 | 附录 B / Figure 2(调用数-准确率)+ 附录 D / Table 11(SQL 成功率) | 10 | 同类论文里少见的工程证据。质量真高——也真能被反用 |
| 9 | §2 Related Work + §7 + Limitations | 10 | 最后读。此时你已有判断,不会被它的自我定位牵走 |

**明确跳过**(不影响任何判断):
- **附录 A**(Comparative Analysis)——定性叙述。唯一有信息量的是 "3.3x more tool calls" 那句,而它算错了(见警觉句 ⑤)。扫一眼就走。
- **附录 E**——**唯一例外**:只找一句。附录 E "Case 1: Temporal Contradiction Resolution"(**p.16485**)逐字 "At retrieval time, a GraphSQL temporal query returns both facts ordered by timestamp; the agent selects the most recent valid entry ('Sakura Sushi')."。这句是 QVF 分界句 (iii) 的关键引文,坐标已核准。找到、抄下、走。30 秒。
- **附录 G / H / I**、**Figure 3 / 4**、**Table 13**(text-to-graph 示例)——说明性插图。
- **§6.1 Datasets**——三个基准你已熟。但**回来抄一句**:adversarial 类的定义是 "adversarial (**unanswerable**)"(见 B1 更正,这句改了 QVF 一条分界句)。
- **Table 2**(Construction Metrics)——先跳过,读到警觉句 ① 时回来看 30 秒。

---

## 二、伴读手册

### 2.1 承重表清单

#### 承重(拿掉,主张就塌)

**Table 3 — APEX-MEM Ablations**(唯一受控实验)
- **证明什么**:贡献 3(多工具检索框架)。三行:`SchemaViewer, EntityLookUp` 77.19% → `+ GraphSQL` 79.45% → `+ Search` 87.00%。
- **分母**:LOCOMO 全题,**单底座 Claude 4.5 Haiku**,累加式(不是 leave-one-out)。
- **被攻的地方**:① **累加次序耦合**——无 LOO、无反序、无对称检验,全文无一句解释为何这个次序;② **Temporal 列在最后一步回退** 82.29 → 79.17;③ **Overall 87.00% 与 Table 1 同行的 84.92% 冲突**(见练习 A)。

**Table 1 — LOCOMO Category Type Evaluation**(头条数字唯一出处)
- **证明什么**:SOTA。APEX-MEM(GPT5)Overall 88.88%。
- **分母**:LOCOMO;**每行底座不同**;基线行 Adversarial 一律 N/A 而 Overall 含 Adversarial;**末列 `w/o Adv.` 给出了可比口径**【更正:已有报告漏读了这一列】。
- **被攻的地方**:**同底座比较是反的**——APEX-MEM(GPT4o)86.35% < Full Context QA Agent(GPT4o)87.52%;`w/o Adv.` 列同底座亦为反向(86.75% < 87.52%,−0.77pp)。表里**没有** Full Context + GPT5 行,所以 88.88 vs 87.52 的 +1.36pp 是换底座换来的,在它自报 std < ±1 下不足称显著。
- **它同时是送给 QVF 的礼物**:Full Context(GPT4o)行 open-domain **92.70%** vs temporal **71.88%**,同模型、同一份完整证据,落差 **20.82pp**。这一行替 QVF 做了「检索覆盖 vs 时序算术」的分离,用的是别人家的数据。

**Table 4 — LongMemEval**(这篇唯一真正立住的地方)
- APEX-MEM Online + Claude 4.5 Sonnet **86.2%**;最强 baseline Nemori 74.6%(**作者正确指名了最强 baseline**,+11.6pp)。
- 【更正,已关闭待核项】`Full-Context + Claude 4.5 Sonnet 62.2%` **确认存在且为同底座**,+24.0pp;另有 `Full-Context + GPT4o 60.2%`、`Full-Context + Chain-of-Note + Sonnet 4.5 63.9%`、`SimpleSearch top-5+expanded + Sonnet 4.5 72.5%`(+13.7pp,同底座)。**这是全文唯一一组干净的同底座正向证据,必须公允报出。**(伴读手册原先要你亲自去核这一行——已核毕,你只需扫一眼确认。)
- **被攻的地方**:**无分类别拆解**——knowledge-update 类缺席,而那一类正是检验「仅追加」最直接的靶;此表依赖在线构图 + Θ_rel > 0.2 门控(见警觉句 ⑧)。

**Figure 2(附录 B)— Tool Calls vs. Accuracy**
- 证明 40 步预算足够。**同时是「没有路由」的自证**:多数题约 10 次调用到 84–86%,约 20 次到顶,硬上限 40 且对所有题型一律平摊。附录 B.5 逐字:"most agents reaching their performance ceiling at approximately 20 tool calls"、"Reduces average tool calls from 20-30 to 10-15"。
- 【新增,且是必须自我降调的一条】**B.5 里作者已把「按 question type 预测最优工具序列 + 学会何时停止检索」列为 future work。** QVF 的四臂路由不能再讲成"没人想到",只能讲成"我们做了他们列为 future work 的事,并给出前沿曲线"。

**Table 11(附录 D)— GraphSQL Execution Statistics**
- Sonnet 4.5 3,659 次执行 / 97.6%;GPT-5 2,163 / 93.4%;Haiku 4,277 / 95.4%;Sonnet GraphSQL-only 66,580 / 98.8%;失败自恢复 87%(其中 45% 走 SchemaViewer 重看 schema)。
- **被攻的地方**:**success = 执行不报错,不是算对该算的**。一条语法合法但时间窗写错的 SQL 会静默给出错答案并计入 97.6%。【新增】附录 D 明说 GPT-5 的错误 "primarily due to SQLite syntax differences"——**作者自己把失败归因于语法层,这正好证明语义层从未被测。**

#### 装饰(拿掉,主张不塌)

| 表/图 | 为什么是装饰 |
|---|---|
| **Table 2**(Construction Metrics) | 抽取 97.3% / schema coverage 91.1% / 属性消解 98.2%——测的是**抽取模型**(Sonnet vs Haiku vs Qwen),不是本体设计,故不能支持贡献 1。【更正:协议已核实】脚注逐字 "We measure these metrics with 500 Random turns from LoCoMo and LongMemEval. GPT5 is used as the judge." → n=500 轮、**LLM 判官、零人工校验、零标注者一致性**;"schema coverage" 的判定标准仍未操作化 |
| **Table 12**(附录 F) | 看起来是消融,实际不是。见练习 C——全篇最值得你亲手抓一次的地方 |
| **Table 8**(Sample SQL)/ **Table 13** | 说明性。Table 8 值得看 30 秒:`julianday()` 做日差、`WHERE entity_name LIKE '%Anthony%' COLLATE NOCASE`、`ORDER BY f.created_at DESC LIMIT 1`。⚠️ 里面的 `LIMIT` 是模型自己写的,**不是工具强制的** |
| **Figure 3 / 4** | 可视化。全篇 4 张图,承重的只有 Figure 2 |
| **附录 A** | 定性叙述 |

#### 半承重(主张靠它,但它本身有问题)

- **Table 5(SealQA-Hard)**:APEX-MEM+GPT5 40.1%(正文写 40.15%)/ Sonnet 4.5 35.2% / Claude 4 Sonnet 28.9% / GPT4o 19.0%;Baselines w/ Web-Search:**GPT5 38.6%**、O3 34.6%、DeepSeek-R1 15.4%、GPT4o 15%、O4-Mini-HIGH 12%、QWEN3-235B 11.4%。正文逐字只列了 "O3 at 34.6%, DeepSeek-R1 15.4%, GPT4o at 15%, and O4-Mini-HIGH at 12%"——**同表里更强的 GPT5 38.6% 被跳过,而作者恰好列出了四个更弱的**。同底座真实增益 40.1 − 38.6 = **1.5pp**。可判定的事实错误,无辩解空间。
- **Table 6(Tool Call Distribution)**:"3.3x" 那句的来源,而那句是把单列的比说成总量的比。
- **Table 9 / Table 10(成本)**:两表口径互不相容(30,000 vs 81,604)。**但本轮更正了指控形式**,见第五节。
- **Table 7(SQL Query Categories)**:对论文自身是装饰,**对 QVF 是资产**——别人家数千条真实生成 SQL 的算子分布,可把 QVF「六原语完备基」改写为「相对某问题分布的覆盖性主张」。**两个坑**:① SELECT / JOIN / AGGREGATE / TEMPORAL **四类不互斥**,一条查询可计入多类,所以「TEMPORAL 占 62%」是**标签占比不是查询占比**,引用必须带这个限定;② 列头按底座与工具配置切分(Haiku / Haiku:Entity / Haiku:GraphSQL / Sonnet),**别跨列相加**。核准值:Sonnet 列 TEMPORAL 2,235 / 该列合计 3,584 = 62.4%。

### 2.2 三个边读边做的练习(含答案)

> 目的不是考你,是让你**自己**撞到落差。撞到的东西你才敢在组会上说。

#### 练习 A · 两个 Overall(读完 Table 3 与 Table 1 后做,5 分钟)

**题面**:抄出 Table 3 **末行**五个分类数字,再去 Table 1 找 `APEX-MEM (Claude 4.5 Haiku)` 行的五个分类数字,逐位对比;然后对比两行的 Overall。

**答案**:
- 五个分类数字**完全相同**:85.46 / 84.74 / 79.17 / 89.18 / 87.22。
- Overall 一为 **87.00%**(Table 3),Table 1 同行给 **Overall 84.92% / w/o Adv. 84.25%**。论文对此无任何说明。
- 【更正,朝更不利于作者的方向】已有报告猜"micro vs macro";本轮把三种良性解释**全部排除**:macro(5 类)= 85.15,macro(4 类)= 84.64,Table 1 两列 = 84.92 / 84.25,**没有一个等于 87.00**。同一份五类数字给出两个 Overall,**任何加权方案不可能同时产出 84.92 与 87.00**。从"推断"升级为**"已排除良性解释的硬矛盾"**。
- **后果**:正文 "+Search 带来 7.55 point improvement" 用的是 87.00 口径;换成 84.92 口径只剩 **+5.47pp**。这篇最大的单项增益,数值取决于一个没被定义、且已被证明不自洽的聚合口径。
- 组会上你只能说"两个 Overall,论文未定义,且已排除加权解释",**不能**说 "micro/macro"——论文里没这句话。

#### 练习 B · 五类里被漏掉的那一类(读 Table 3 Temporal 列时做,5 分钟)

**题面**:抄下三行的 **Temporal** 列;找到正文那句 "…a 7.55 point improvement, with substantial gains across all categories including single-hop (…), multi-hop (…), open-domain (…), and adversarial (…)",把被点名的类别打勾。

**答案**:
- Temporal:72.92 → **82.29** → **79.17**。最后一步 **−3.12pp**。
- 正文点名 single-hop / multi-hop / open-domain / adversarial——**五类里唯一没被点名的,正是回退的那一类**。而 **Temporal Reasoning 写在论文标题里**。
- 【新增,同向的第二处省略】正文那句 "including single-hop (**80.78%** to 85.46%)" 的起点用的是**第二行 80.78,不是第一行 80.85**——即绕过了 GraphSQL 那一步在 single-hop 上的 **−0.07**。两处省略同向。

**【更正】本轮做完这张表的完整逐类别 delta,结论比已有报告重要得多:**

| 类别 | 起点 | +GraphSQL | | +Search | |
|---|---|---|---|---|---|
| single-hop | 80.85 | **−0.07** | 80.78 | +4.68 | 85.46 |
| multi-hop | 76.64 | +3.11 | 79.75 | +4.99 | 84.74 |
| **temporal** | 72.92 | **+9.37** | **82.29** | **−3.12** | 79.17 |
| **open-domain** | 76.34 | +1.66 | 78.00 | **+11.18** | 89.18 |
| adversarial | 77.80 | +3.36 | 81.16 | +6.06 | 87.22 |
| Overall | 77.19 | **+2.26** | 79.45 | **+7.55** | 87.00 |

- **GraphSQL 的 +9.37pp(temporal)是整张消融表里最大的单类别增益**,比 Search 在 temporal 上好 12.49pp;而它在 single-hop 上 −0.07、open-domain 上仅 +1.66。**结构化执行的收益高度集中在它本该管的那一类,被 Overall 的平均彻底稀释成 +2.26pp。**
- Search 的 +7.55pp 主要来自 **open-domain +11.18pp**,一个与结构化无关的类别。
- **换序会不会变结论?会,方向可预判**:附录 B 自己说 GraphSQL-only "must first discover the graph structure through SchemaViewer and EntityLookup operations before constructing effective SQL queries",而 EntityLookup-only "plateaus at approximately 77%"。即 GraphSQL 的效力条件性地依赖实体锚定,而 Search 不依赖 GraphSQL。若先加 Search,GraphSQL 的边际会被压得更小,Search 的边际会大幅缩水。**"3.3 倍差距"(7.55/2.26)是次序的产物,不是重要性的度量。**

#### 练习 C · 附录 F 里到底有几个实验(读附录 F 时做,5 分钟)

**题面**:Table 12 列了四个系统的 temporal 表现。把四个数字逐个回到 **Table 1 的 Temporal 列**去找。找完再答一个问题:**表里有没有一行是「APEX-MEM,但冲突时覆盖旧值」?**

**答案**:
- 四个数(APEX-MEM 90.63 / Mem0 75.71 / MIRIX 65.62 / Zep 76.60)在 Table 1 Temporal 列**一字不差地存在**。
- Table 12 相对 Table 1 唯一新增的是一列 `Append-Only?` Yes/No 标注。
- **表里不存在 APEX-MEM 的 eager-update 变体。** 支撑贡献 2 的**整个附录没有跑任何新实验**——它是把 Table 1 已有的一列重新贴了标签。而"仅追加优于覆盖式更新"现在依赖"四个不同系统的差",那个差里同时变了抽取模型、本体、检索工具、底座至少四个变量。那个缺失的变体在工程上极便宜(同抽取、同本体、同四工具、同底座,只改写入时冲突处理),**拒跑它不是资源问题。**
- 【更正,朝有利于作者的方向,必须照样说】附录 F 开头逐字:"**Table 12 provides indirect evidence** supporting APEX-MEM's append-only design",结论句用 "**strongly suggests**" 而非 demonstrates。**作者自己把这条证据标注为"间接",并用了对冲动词。** 所以"夸大/掩盖"的指控**不成立**;能成立的是"缺同架构变体"。
- 【新增,替代上一条被软化的攻击,更硬】附录 F 声称 "APEX-MEM's **+14 to +25 point advantage** on temporal queries"。该区间用的是 APEX-MEM 的**最好** temporal(90.63%,Sonnet 4.5 / GPT5)对三个 baseline。**若换成同一篇论文 Table 1 的 Haiku 配置(temporal 79.17%),优势区间塌为 +2.57(vs Zep 76.60)到 +13.55(vs MIRIX 65.62)。** 而 append-only 是**架构属性、与 QnA 底座无关**。**若它是那 14–25pp 的成因,它不该随底座从 +2.6 变到 +25。** 这条既硬又公允,且不需要作者跑新实验就能判定。

#### 加时赛(可选,5 分钟)· 一段话里的两个分母

> ⚠️【更正】伴读手册原先给的加时赛题面("`GC Amort.` + `Mem Calls` + `QnA` 加起来对比 Total")**算术前提是错的**,已作废。正确的题面如下。

**题面**:把 Table 9 的表头 7 列抄全,注意 `GC Calls` 列的单位。对每一行验算 `Amort. GC/Q + QnA Tok/Q` 是否等于 `Total Tok/Q`。然后回到附录 C,找 "Graph construction accounts for only 16.6% of APEX-MEM's total cost" 这句,亲手算 16.6% 的分母是哪张表的数。

**答案**:
- 表头 7 列:`GC Tok/Conv | GC Calls | Amort. GC/Q | Mem Tok/Q | QnA Tok/Q | Total Tok/Q | Acc (w/o Adv)`。**3,717 是 GC Calls(调用次数),不是 token**——已有报告把它当 token 加进去了,那条算术无效。
- `Total = Amort.GC/Q + QnA Tok/Q` 在**全部 7 行一致成立**(Zep 60,900 + 3,900 = 64,800 精确相等;APEX 13,557 + 16,000 = 29,557 → 打印 30,000)。**`Mem Tok/Q` 对所有行一律不计入 Total**,附录 C 逐字披露了这个两成分口径。**所以"Table 9 选择性排除自家 tool framing 与 agent loop overhead"这个指控不成立——口径是统一且公开的。**
- **矛盾在别处,而且更窄更硬**:13,557 / **81,604** = 16.61%(Table 10 的分母);若用它自己刚介绍的 Table 9 的 Total(30,000),这个比例是 **45.19%**。**一段话里两个互不相容的 total**——可判定的编辑错误。同段还写着 "the majority is spent on tool access and agentic reasoning loops",即作者在文字上承认了这部分开销,只是没让它进跨系统那一列。
- 公允必须补的一条:APEX-MEM 是表里**唯一的 agentic 多工具 ReAct 系统**,agent loop overhead(16,174)+ tool framing(22,274)= 38,448 tok/Q = **47.1%** 是只有它才有的开销种类,非 agentic 的 baseline 不存在这个隐藏列。**所以问题不是"它藏了自己的账",而是"这张表的两成分口径对 agentic 架构在结构上不适用"。**

### 2.3 读到这几句要警觉

> 判据:**读起来像结论,实际是设置。**

**① 摘要末句**:"…demonstrating that **structured property graphs enable** more temporally coherent long-term conversational reasoning"
- 全篇最强的因果声称,而 innovation 1(属性图 + 本体)**零受控消融**。
- 去哪验:Table 3 换的是**读取侧的工具**,不是**写入侧的图结构**。属性图从头到尾只有一种,35 类本体的类数无敏感性分析;Table 2 测的是抽取模型不是本体设计。**这句话在论文里没有对应实验。**

**② §1 贡献 2**:"append-only event storage … enabling retrieval-time resolution based on temporal validity rather than **premature commitment to a single current state**"
- 全篇最漂亮的一句,也是 QVF 最该引的一句(它逐字说出了 QVF 写入侧的设计理由)。但它是**动机**不是**结果**。去哪验:附录 F / Table 12(练习 C)。
- 【更正,会被当场翻书查到】这句在 **§1 引言贡献列表第 2 条(p.16470 左栏)**,**不在摘要里**。camera-ready 摘要第 2 点重写为 "append-only storage that preserves the full temporal evolution of information",**不含这一短语**。组会稿有三处要改:§5 弱点表 ③ 行、A-Mem 节 B 数据段、**4.2 讲稿那句口播"APEX-MEM 摘要的第 2 点逐字批评的就是这件事"**——全部改为「§1 引言贡献列表第 2 条」。

**③ §6.3**:"a 7.55 point improvement, with **substantial gains across all categories** including…" —— "all categories" 后的枚举只有四类。去哪验:练习 B。

**④ Table 5 附近**:"this **5.55 percentage point improvement over the strongest baseline**" —— "the strongest baseline" 是作者指定的,不是表里最强的。去哪验:同表 GPT5+Web-Search 38.6% > O3 34.6%,同底座真实增益 **1.5pp**。
- 【新增,公允必须同时说】LongMemEval 上作者**正确指名了最强 baseline**(Nemori 74.6%),**说明 SealQA 这处误指是孤例,不是模式。**

**⑤ 附录 A / §6.3**:"**3.3x more tool calls** (27,282 vs 8,260)"
- 读起来像总调用量的比,用来说明「纯结构化路线代价高」。**27,282 与 8,260 都只是 Table 6 GRAPHSQL 一行。**
- Table 6 按原样加总:41,466 / 29,624 = **1.40×**。【新增】但 **Table 6 的 GRAPHSQL 行恰为 Table 7 各列合计的 2.0000 倍(三列全中)**,而 **Table 11 的执行数印证 Table 7 而非 Table 6**(Sonnet 3,659≈3,584;Haiku 4,277≈4,130)。若采信 Table 7/11 的量级,则 27,825 / 25,494 = **1.09×**。论文那句"query categories are not mutually exclusive"只能解释 Table 7 ≥ Table 6,**方向与实际相反,不能解释 2 倍**。
- **正确引用值:总工具调用量比在 1.09×–1.40× 之间,取决于采信 Table 6 还是 Table 7/11;3.3× 只成立于 GraphSQL 单列。**
- **纪律提醒**:这条更正**对 QVF 不利**(说明纯结构化路线的开销代价被论文夸大了 2.4–3 倍)。必须照样如实引用。

**⑥ 附录 C**:"Graph construction accounts for **only 16.6%** of APEX-MEM's total cost" —— "only" 相对一个特定分母,而这篇有两个。去哪验:加时赛。

**⑦ Table 11 附近**:"execution **success** rate 97.6%" / "87% successful recovery"
- success = SQL 跑起来没报错,**不是**算的是问题真正要求的东西。去哪验:Table 8 的示例 SQL——时间窗写错、`julianday()` 日差算错的查询照样"成功"。
- **这条对 QVF 最重要**:QVF 原打算写的动机「LLM 临场生成的查询不可靠」**被 97.6% / 93.4% / 95.4% + 自恢复 87% 基本打掉了**。但语义正确率**全篇没人测**,且附录 D 作者自己把 GPT-5 的失败归因于 SQLite 语法差异。这道缝是 QVF 可以占的位置——**前提是做成正式实验,不是嘴上说一句。**

**⑧ §5 + §6.2**:在线构图与 "Θ_rel > 0.2"
- 读起来像实现细节,实际是**头条 86.2% 的前置条件**。LongMemEval 与 SealQA 用在线构图,即**构图按查询条件化**,门控用相似度。两条后果:(a) 若答案所在会话与问题措辞无词法/语义交集,门控把它筛掉,**图里压根没有那些事实**;(b) 在线模式下构图无法在多次查询间摊销,**Table 9 的 GC Amort. 口径对 86.2% 不适用**。
- 对照:LOCOMO **没有**用在线构图。所以这篇最细的 temporal 证据(90.63%)恰恰**不覆盖**这条依赖,而头条 86.2% 恰恰来自这个模式。

**⑨ Table 1 每一行的底座名**:GPT5 / Claude 4.5 Sonnet / Claude 3.5 Sonnet / Claude 4.5 Haiku / GPT4o;Full Context QA Agent 是 **GPT4o**。底座名排在方法名后面像脚注,实际是主表第二个自变量。**逐行抄底座,只在同底座行之间做减法。**

**⑩ §6.2**:"All Tools are used with a max limit of **40** for ReACT tool invocations"
- 读起来像超参,实际是 QVF 分界句里最关键的一处事实。**它有硬上限**(附录 B 复述 "with tool calls capped at 40",且已核实为**每题跨全部工具的全局上限**,非按工具各 40)。所以核实档「循环步数无保证上限」这句**不能说**。
- 同理 §4.3 逐字:"The tool first validates the statement, enforcing a single read-only statement and forbidding Updates, or DDL then executes it against the GraphDB…" 白名单七表 `events, facts, evidence, entities, event_participants, properties, turns`——**它有生成前校验**,只是那是安全/作用域校验,不是**封闭算子词表的语义合法性校验**。这个区别要写清。
- ⚠️ 陷阱:§3.3 确有 "schema-constrained generation",但那是**事实抽取**的,**不是 SQL 生成**的——不可混引。

**⑪ §6.3 RQ4**:"the system maintains consistently high performance across different question types with **less than 5 percentage points variation**"
- 【更正,证据变锋利】原文**无任何底座限定语**。逐行实测极差:Sonnet 4.5 **4.53** ✓、Sonnet 3.5 **4.20** ✓、GPT4o **4.98** ✓、**GPT5 5.39 ✗**、**Haiku 10.01 ✗**。**头条那一行(GPT5)自己就违反了这句声明**,Haiku 行超了一倍。

### 2.4 读完要能自己答的七问及合格判据

> 不给答案,给「什么样的回答算合格」。**答不出来 = 那一节没读到位,回去重读。**

**A · 它究竟要解决什么问题?**
合格判据:必须是**一个具体的失败模式**,不是领域名;且能给出一个**系统内落差**数字(同一系统内两类问题的差),不是跨系统差。
- 不合格:「解决长期对话记忆问题」「提升时序推理」。
- 合格的形状:「作者真正害怕的是 ___,证据是 ___ 系统的 ___ 类 __% vs 同系统 ___ 类 __%,落差 __pp」。
- 【本轮加固,引用更安全】§6.3 RQ4 作者**自己**框定了对手的系统内落差:"MIRIX (20% drop in temporal accuracy 65.62% temporal) and Mem0 (10% drop in single-hop and 18% drop in multi-hop)"。你可以直接引作者的话,不必自己重算。

**B · 它有哪些隐含前提?**
合格判据:至少两条是**论文没写但结果依赖**的,且每条能说出「翻掉它之后**哪个具体数字**失效」。只列它 Limitations 里自认的不算。
- 自检:每条前提能不能配一个数字?配不上的是感想,不是前提。

**C · 真实创新点是什么?**
合格判据:必须落到「**改了哪个环节**」,并给出一句**可判定的分界句**——对着某个具体对手系统问一个 yes/no 问题。
- 不合格:「它用了 SQL」「它是 agentic 的」。
- 合格的形状:「vs ___:问 ___ 这类问题时,___ 库里已无该行,它有」。
- 附加判据:把创新分到 概念 / 技术 / 工程 三档,说出哪一档最弱、为什么。

**D · 实验支持度如何?**
合格判据:三条贡献逐条对齐「直接支持什么 / 缺什么」,然后答一个总问题:**哪一条贡献的证据强度与它在摘要里的位置最不匹配?**
- 自检 1:若你的答案是「实验很充分」,回头数三条贡献里有几条被受控消融过,数完再答。
- 自检 2:**你要能同时说出这篇实验的公允之处。若只列问题,说明你在挑刺不是在评审。**(现成的两条:LongMemEval 的 +24.0pp 与 +13.7pp 均为 Sonnet 4.5 同底座;附录 F 自标 indirect evidence。)

**E · 反例(能翻掉它的场景)**
合格判据:每条必须是**可构造的**——你能写出一道具体题目或一段具体对话。「可能不够鲁棒」不算。至少一条必须指向**它自报的某个数字**。
- 合格的形状:「构造:问 ___,而相关会话只出现 ___。此时 ___ 机制失效,因为 ___。它自报的 __% 说明这种情况约占 __%」。

**F · 审稿人会问什么?**
合格判据:每条主要质疑配**作者最可能的回应**,并判定该回应**成立/不成立**。
- 自检 1:**若三条主要质疑作者都能一句话答掉,说明你挑的是次要问题,回去重挑。**
- 自检 2:要有至少一条是「我让」——作者回应成立、你收回质疑。一条都没有,说明你审的是立场不是论文。(本轮就有一条真实的"我让":附录 F 自标 indirect,"夸大"的指控须撤回。)

**G · 扩展方向**
合格判据:每个方向说出**用什么现成资产做**(它的哪张表 / 哪批 SQL / 哪个基准),以及**第一个可测量的输出是什么**。
- 不合格:「改进本体」「扩展到多模态」。
- 合格的形状:「取它 Table 11 那批 SQL 的子集,标注语义是否实现问题意图,输出是语法成功率与语义正确率的差值」。
- **前提检查(已核实)**:全文**无 GitHub 链接、无 artifact 声明**(Ethical Considerations 只谈许可审查与去标识化)。所以任何依赖「拿到或重建其实现」的方向,第一步是可行性核实,不是实验设计;且构图 prompt 与 few-shot 未给,**保真度风险最高一档**。

### 2.5 与 QVF 对照:填这两栏

> 读完 90 分钟后填。**填表纪律:每一条必须写一个出处(表号或节号)+ 一个数字。写不出出处的,不许写进 related work。**

| 它占走了我什么 | 它留下什么空位 |
|---|---|
| | |
| | |
| | |
| | |

**填「占走」时问自己(4 条)**
1. **我在 intro 里打算写的哪一句,读完之后不能原样写了?** 具体是哪个词失效了——「首创」「唯一」「首次」「最小」?写下那个词,和它的哪张表/哪一节使它失效。
2. **我最想立的动机是「LLM 临场生成的结构化查询不可靠」。Table 11 是否已经把它打掉?** 若是,新动机是哪几条,**每一条各有什么可测量的证据**?(候选:编译期语义合法性校验 / 答前 premise_check / 按题型可判定的步数上界 / 成本可预测。四条里哪几条现在拿得出数字?)
3. **我在哪个数字上被它压住?** 它 LongMemEval 86.2%,QVF 的 LME-KU 卡片臂 64.1%。这个压住是**口径问题**(在线构图 vs 离线、判官不同、类别构成不同)还是**能力问题**?你要能说出至少一条口径差异,也要承认剩下的是能力差。
4. **我的「结构化机制净 +4.21pp」放在它的结构化臂 +2.26pp 旁边,是往前推了还是原地?**
   ⚠️【本轮更正,这一问的答案变了】见第三节 D 结论 1 与下文"最该改的一句话"的第 2 候选:**+2.26pp 是类别稀释后的平均,不是"结构化增益本来就小"的先例。** 这一问要重新答。

**填「空位」时问自己(5 条)**
1. **它整篇有没有任何一处按问题类型分派预算?** 若没有(§4 无问题分类、40 步平摊、Figure 2 显示多数题 10 次到顶),QVF 四臂路由能不能从「设计偏好」升级成「**可测量的成本-精度前沿**」?**我需要它的哪两张表/图才能画出那条前沿?**
   ⚠️ 但先读附录 B.5:**作者已把这件事列为 future work**。所以这个空位是"未做",不是"未想到"。措辞必须相应降调。
2. **「执行成功率 97.6%」与「语义正确率」之间那道缝,我手上有什么现成资产能量它?** 注意:「语义正确」必须可操作化——与人工参考查询的**结果集**比对,不是比对查询文本。想不清这一点,这个空位就占不住。
3. **它有没有做过组合泛化划分?** 若没有,QVF 的 S8 未见组合结果(朴素直读 70.1% vs 平面臂 52.2%,闭集**输** 18pp)是一个负结果——**在「这个子领域没人测过」的前提下,这个负结果本身能不能算贡献?** 如果能,它的贡献形式是「测量」还是「反例」?
4. **它有没有做过「必需证据完整率」的分层?** QVF 有 71.1% / 完整层 +26.3pp 的分解;它在线模式下从未测过召回失败(而头条 86.2% 正来自在线模式)。**这个方法论位是不是无人占据?** 前提:你的 71.1% 标注协议要能报多标注者一致性,报不出就还占不住。**(它 Table 2 的 91.1% 也报不出——见 E4,双方都欠这一项。)**
5. **QVF 的 c₂ = 46.2% 说明墙在编译/执行/渲染层,不在写入侧。它有没有任何一处测过这一层?** 若没有——这是它的空位,还是**整个子领域的空位**?两者写法完全不同,想清楚再写。

**填完之后的最后一步**:两栏各挑一条最硬的,合成一句读给自己听:

> 「读完 APEX-MEM,QVF 少了 ___(一句声称),多了 ___(一个可做的实验)。」

**如果「少了」是空的,你没读进去。如果「多了」是空的,你只读出了立场。**

---

## 三、七镜精读(加深版,供读后对照)

**本轮阅读层级**:从 arXiv v1 HTML **升级到 ACL Anthology camera-ready 全文**,13 张表 + 附录 A–I 按坐标逐格重建(非 HTML 摘要转述),全部数字经独立算术复核。文本提取物在 `C:\Users\25243\AppData\Local\Temp\claude\D--ZZL-cluade\afef460d-0054-423f-bfc3-93697664299e\scratchpad\apexmem_cr.txt`。

**版本对照(先关掉最基础的一条风险)**:节号与附录字母 camera-ready 与 arXiv v1 **完全一致**(§1 Intro / §2 Related Work / §3 Graph Construction / §4 Graph Agents / §5 Online Construction / §6 Experiments / §7 Conclusion / Limitations / Ethical Considerations;附录 A–I)。**三处小更正**:表总数 **13 张不是 12 张**(Table 13 = text-to-graph 示例,附录 G);**Table 1 有 7 个结果列,末列 `w/o Adv.`**(已有报告漏读);引用页码可直接用 16470–16489,节号表号不需要人工再对。

### 3.1 十条未核实项的结局(全部关闭,6 条需改结论)

| # | 原项 | 结局 | 关键定位 | 结论是否需改 |
|---|---|---|---|---|
| 1 | Table 2 评测协议 | **关闭** | 脚注逐字 "500 Random turns … GPT5 is used as the judge" | **补限定**:n=500 轮、LLM 判官、零人工校验、零一致性;"schema coverage" 判定标准仍未操作化。91.1% 只能写成"GPT5 在 500 轮抽样上判定的",不能写成测得的漏抽率 |
| 2 | Table 1 / Table 3 Overall 差 2.08pp | **关闭,结论加强** | Table 1 Haiku 行 Overall 84.92 / w/o Adv. 84.25;Table 3 末行 87.00 | **须改,朝更不利于作者**:micro/macro/含不含 adversarial 三种解释**全部排除**,从"推断"升级为**"已排除良性解释的硬矛盾"** |
| 3 | Table 9 的 ~30,000 排除了什么 | **关闭,已有算术有误** | 表头 7 列;附录 C 逐字定义两成分 | **须改**:3,717 是 **GC Calls 不是 token**;`Total = Amort.GC/Q + QnA` 七行一致;**"选择性排除自家开销"的指控不成立**,改为更窄更硬的一条(见 3.3) |
| 4 | Table 11 / 6 / 7 三者不符 | **关闭,变成可判定的发现** | Table 11 caption "'Sonnet (SQL)' denotes the GraphSQL-only ablation." | **须改**:不再是三方矛盾。Table 6 GRAPHSQL 行 = Table 7 各列合计的 **2.0000 倍(三列全中)**,而 Table 11 印证 Table 7;66,580 是 Sonnet 底座的 GraphSQL-only,与 Haiku 列不同底座,属**未解释**而非矛盾 |
| 5 | baseline 判官与引文编号 | **关闭** | §6.2 "For all other benchmarks we used reported numbers from (Salama et al., 2025; Pham et al., 2025; Wang and Chen, 2025)" | **须改一处口径错**:已有报告写"判官 GPT-5"。实际 **GPT5 只被指名为 Table 2 构图指标的判官**;LOCOMO 是 "Following Chhikara et al. (2025), we use LLM-as-a-Judge",LongMemEval/SealQA 是 "the recommended LLM-as-a-Judge",**三个基准的判官模型全文均未指名**。作者此处透明(明说是引用数字),不构成隐瞒 |
| 6 | "<5pp 波动"的适用范围 | **关闭,证据变锋利** | §6.3 RQ4,**无底座限定语** | **不改判断**:极差 Sonnet4.5 4.53 ✓ / Sonnet3.5 4.20 ✓ / GPT4o 4.98 ✓ / **GPT5 5.39 ✗** / **Haiku 10.01 ✗**。头条行自破 |
| 7 | 是否开源 | **关闭** | 全文无 GitHub / 无 artifact 声明 | **不改**:确认无代码/数据发布。G1/G2/G4 须按"从零重建"估工作量,构图 prompt 与 few-shot 未给,保真度风险最高一档 |
| 8 | camera-ready 是否重排 | **关闭** | 见上"版本对照" | **须改三处小事**:13 表非 12;Table 1 有 `w/o Adv.` 列;节号附录字母无需人工复核 |
| 9 | 消解规则的确切出处 | **关闭** | **附录 E "Case 1: Temporal Contradiction Resolution",p.16485** | **不改**:关键引文现在有精确坐标,可直接进相关工作 |
| 10 | 执行前校验是否更强 | **关闭** | §4.3 逐字 + 七表白名单 | **不改,反而可略放宽反方向**:**无 LIMIT 强制、无超时、无行数上限**;`S_sql` 定义为 "safe SQLite SELECT (**or WITH … SELECT**)",**CTE 被允许**,表达面比原估计更宽。Table 8 里的 `LIMIT` 是模型自己写的。C5 分界句「仅安全/作用域级校验」**不需要收紧,反而更站得住** |

### 3.2 A 问题意识

- **A1**【更正,会被当场翻书查到】"premature commitment to a single current state" **不在摘要里**,在 **§1 引言贡献段(p.16470 左栏)**。组会稿三处口径须改(见警觉句 ②)。
- **A2 落差**:五条全部维持;**落差二加固**(GraphSQL 步在 single-hop 上也是 −0.07,且正文起点绕过该负值,两处省略同向);**落差三从"推断"升级为"已排除良性解释"**;**落差五按 3.4 重写**。
- **A4**【新增】作者在 §6.3 RQ4 里**自己**框定了对手的系统内落差(MIRIX 20% drop / Mem0 10% & 18% drop)。**A4 的四条落差数字现在是作者自陈,不是我们重算的,引用更安全。**
- **A5** 维持。

### 3.3 B 隐含前提

- **B1**【更正,并改了 QVF 一条分界句】§6.1 逐字把 LOCOMO 的 adversarial 定义为 **"adversarial (unanswerable)"**。已有报告 B1(c) 写"问题都有答案…不含假前提问题"——**这句要收紧**:不可答类是存在的,APEX-MEM 在它上面拿到 86.10–87.22%。**对 QVF 的后果**:「答前 premise_check 无对手」不能再按"它没有不可答题"来讲,必须改成——它有不可答类且分数不低,但 **(i) 弃答是代理涌现行为,不是生成前的可判定拦截;(ii) 全文不报弃答的 precision/recall,只报该类总准确率,因此"该弃而弃"与"该答而误弃"无法分离。** 第 (ii) 条是新增的、更具实验可操作性的分界点。
- **B2** 维持,加一条:`S_sql` 允许 `WITH … SELECT`(CTE),表达面比原估计宽。
- **B4**【更正】"判官 GPT-5" 只对 Table 2 成立,三个基准判官未指名。"temperature 0 / 3 次均值 / std<±1" 维持,逐字:"we set the temperature to 0 wherever applicable. For each LLM-as-a-Judge, we report mean of 3 trials, with < ±1 standard deviation."
- **B3 / B5** 维持。

### 3.4 C 真实创新点 —— **判决维持:中**

C1–C4 维持;C5 三条对手分界句维持。vs QVF 的四条更正**经 camera-ready 复核全部成立,可定稿**(见第四节)。

【新增,一条可选强化,取代原 (iii) 里被削弱的成本论证】:

> (iii) 其执行阶段虽由 SQLite 完成,但**查询由模型在循环内临场写出,且成功率只在语法层被度量**(附录 D:Sonnet 4.5 97.6%、GPT-5 93.4%、Haiku 95.4%、GraphSQL-only Sonnet 98.8%;失败自恢复 87%,其中 45% 走 SchemaViewer 重看 schema);而 TEMPORAL 占其 SQL 标签的 62%(Table 7 Sonnet 列 2,235/3,584),Table 8 示例用 `julianday()` 做日差。**语法成功率与语义正确率之间的缝隙,论文未测量。**

原 (iii) 里"agent loop overhead 与 tool framing 合计 47.1%"**仍可用**(Table 10 实测),但**不要写成"论文隐藏成本"**——附录 C 文字承认了 "the majority is spent on tool access and agentic reasoning loops"。

### 3.5 D 实验支持度 —— **判决维持:部分**(三处需改)

| 结论 | 变动 | 内容 |
|---|---|---|
| 1 消融次序 | **加强** | 次序无交代、无 LOO、无反序全部确认;**新增"+2.26 是类别稀释后的平均"这一诊断** |
| 2 temporal 回退 | **加强** | 除 temporal 回退外,新增 GraphSQL 步在 single-hop 上 −0.07 且正文起点绕过该负值 |
| 3 附录 F | **须软化,朝有利于作者** | 见 F 主要 2 |
| 4 Table 2 | 维持 | 现有 500 轮 / GPT5 判官协议可引 |
| 5 同底座反向 | 维持 | 86.35% < 87.52%;`w/o Adv.` 同底座亦反向 86.75% < 87.52%(−0.77pp) |
| 6 LongMemEval | **须加强,朝有利于作者** | +24.0pp 与 +13.7pp **均为 Claude 4.5 Sonnet 同底座**,已逐格确认,是全文唯一一组干净的同底座正向证据;且作者在此**正确指名了最强 baseline**(Nemori 74.6%),说明 SealQA 误指是孤例。**必须公允写出** |
| 7 SealQA | 维持,证据更锋利 | 同表 GPT5 38.6% 被跳过而恰好列出四个更弱的;同底座真实增益 **1.5pp**。这比"误指"更难辩解 |
| 8 <5pp 声明 | 维持,头条行自破 | GPT5 极差 5.39;3/5 底座满足、2/5 违反 |
| 9 成本 | **须按 3.7 重写** | 指控形式变更 |

### 3.6 E 反例 —— 七条全部维持,两条改措辞

- **E4 加强**:91.1% 现有协议来源(500 轮 / GPT5 判官),但须注明是 **LLM 判定,非人工测得的漏抽率**。
- **E7**【更正】原依据"GPT-5 as judge",但三基准判官未指名。**E7 改为「判官模型全文未指名 + 无人工一致性研究」,本条更弱,仍是最弱的一条**;**不可再声称判官是 GPT-5。**
- **E8**【新增,可选替代 E7 作第七条】依赖 `w/o Adv.` 与 `Overall` 两列口径可互换;而 Table 3 的 87.00 与 Table 1 的 84.92 / 84.25 在同一份五类数字上不可同时成立,**任何引用其 Overall 的下游工作会继承一个 2.08–2.75pp 的口径不确定性。**

### 3.7 F 审稿人视角 —— **判决维持:弱接受**

- **主要 1 调整**:结论不变(两处头条在同底座下退化到 1.4–1.5pp 或反向),但"作者会回应"一栏**比原来有力**——LongMemEval 两条对照都是 Sonnet 4.5 同底座。故"能否成立"改为:**对总命题成立且证据干净;对 LOCOMO 头条数字与 SealQA 的 5.55pp 不成立。** 已有报告那句"最珍贵的分类别 temporal 证据全部只在 LOCOMO 上,即只在那个不需要记忆系统的基准上"**维持,这仍是最有力的一击**(Table 12 与逐类别 temporal 90.63% 确实只有 LOCOMO)。
- **主要 2 须实质软化 + 新增一条更硬的**:附录 F 自标 "**indirect evidence**"、结论用 "**strongly suggests**",故"夸大/掩盖"的指控**不成立**,须改为**部分成立——缺同架构变体的批评完全站得住,但作者已披露证据等级**。【新增更硬的一条】"+14 to +25 point advantage" 是**底座选择的产物**:换 Haiku(temporal 79.17%)后区间塌为 **+2.57 到 +13.55**,而 append-only 是架构属性、与底座无关。**若 append-only 是那 14–25pp 的成因,它不该随 QnA 底座从 +2.6 变到 +25。**
- **主要 3 须改一半**:"Overall 差异是聚合方式不同,camera-ready 会统一"这个可信辩解**被 camera-ready 本身否掉了**——已出版、三个值互不相等、加权解释已排除。**"可修"变成"未修",略加重。** temporal 回退部分维持,并加上 single-hop 的 −0.07。
- **次要 1 须重写并升级**:改为"Table 9 的两成分口径对唯一的 agentic 系统在结构上不适用,而附录 C 同一段引用的 16.6% 用的是 Table 10 的 81,604 作分母(用 Table 9 的 30,000 会得到 45.19%)"。**"弱成立"升为"成立"**——一段话里两个 total 是可判定的编辑错误。
- **次要 2 / 3 维持**(次要 3 措辞按 E7 改:判官模型未指名)。

### 3.8 G 扩展方向 —— 五条维持,两条更新前提

- **G1**:难点改为"**确认无代码/数据发布**,重建是唯一路径,构图 prompt 与 few-shot 未给,保真度最高风险"。【新增一个更省的入口】主要 2 新发现的"+14~+25 随底座塌到 +2.6"意味着**只需在 Haiku/Sonnet 两个底座上跑三档写入策略,就能把"写入策略效应"与"底座效应"分离**——比原设计便宜得多,且直接判定作者的核心推断。
- **G2**:维持,加一条已量化的靶心:**Search 步在 open-domain +11.18pp、temporal −3.12pp,同一组件在两类上符号相反**,是注意力竞争假说最干净的显影。
- **G3**:维持,并用 3.9 的新证据立动机(Full Context 实测 23,653 tok/Q 完整入窗仍 temporal 71.88%)。
- **G4**:**前提加强**。Table 11 已完整;附录 D 明说 GPT-5 的错误 "primarily due to SQLite syntax differences"——**作者自己把失败归因于语法层,正好证明语义层从未被测。** 语法≠语义这条缝现在有作者自己的归因句作反面证据。
- **G5**:维持,数据基础改为核实值(总调用 29,624,Haiku 全系统;B.5 的 20 次到顶 / 20-30 降到 10-15)。【必须自我降调】**作者在 B.5 已把"按 question type 预测最优工具序列 + 学会何时停止检索"列为 future work**——G5 的问题意识与作者重合,QVF 的路由不能讲成"没人想到",只能讲成"我们做了他们列为 future work 的事,并给出前沿曲线"。

### 3.9 一处专门加深:Table 1 Full-Context 行(QVF 的关键外部证据)

**结论:站得住,但站得住的理由不是原来那条。**

**坏消息**:论文**从未描述 Full-Context 的构造方式**。全文含附录无一句说明塞进上下文的是什么、多长、GPT4o 是哪个快照、是否截断。"Full Context" 只作为 Table 1 与 Table 9 的一行出现,§6.1/§6.2 均无对应段落。按纪律 1,本该判"未核实"停在这里。

**但 Table 9 从侧面把它钉住了**——本轮最有价值的一处交叉:Full Context 行 `GC Tok/Conv = 0`、`GC Calls = 0`、`Amort. GC/Q = 0`(确认它不建任何记忆)、**`Mem Tok/Q = 23,653`**、`QnA = 25,000`、`Total = 25,000`、`Acc(w/o Adv) = 87.52%`。GPT4o 窗口 128k。**因此:整段 LOCOMO 对话以约 2.4 万 token 一次性完整入窗,无截断、无检索、无摘要——证据是真完整的。** 这正是 QVF 想引的那个条件,而且有实测数字支撑,比"论文说它是 full context"强得多。

**正确写法**:

> APEX-MEM(ACL 2026)Table 1 的 Full Context 行:GPT4o 在整段对话完整入窗(Table 9 实测 23,653 token/query,远低于其 128k 窗口)的条件下,open-domain 达 **92.70%**(全表最高,高于 APEX-MEM 自己最好的 91.68%),而 temporal 只有 **71.88%**,**同模型、同一份未经裁剪的证据,落差 20.82pp**。

**必须同时披露的四条残余缺口**(否则审稿人会拆掉):① **temporal 子集题数全文未给**,20.82pp 无 n、无 CI、无显著性;要报 n 必须回引 LOCOMO 原论文(Maharana et al., 2024),**不能引本文**;② GPT4o 快照未指名;③ 判官模型未指名;④ Full Context 行 Adversarial 为 N/A,其 87.52% 是四类口径,与 APEX-MEM 五类 Overall 不同口径(但 `w/o Adv.` 列已给出可比值:Full Context 87.52% vs APEX-MEM+GPT4o 86.75%)。

**两条新增加固**:
- 这个"open-domain 高 / temporal 低"**不是 Full Context 独有,是全表通例**:SimpleSearch+GPT5 83.95% vs 72.92%;SimpleSearch+Sonnet 4.5 81.33% vs 73.96%;SimpleSearch+GPT4 73.60% vs 37.50%。**"证据/检索到位而时序算术不到位"在五种配置上重复出现**,不是一行的偶然。
- LongMemEval 上那组同底座对照已确认(见 D 结论 6),必须公允报出。

### 3.10 本轮后的三条判决

| 镜 | 上一轮 | 本轮 | 理由 |
|---|---|---|---|
| **C 新意** | 中 | **中(维持)** | 无一处需上调或下调;四条 vs QVF 更正经 camera-ready 全部确认 |
| **D 实验支持** | 部分 | **部分(维持)** | 一处显著加强(类别稀释 + Overall 矛盾排除良性解释)、一处显著软化(Table 12 自标 indirect)、一处翻向作者(LongMemEval 两条同底座 + 正确指名最强 baseline)。净额抵消 |
| **F 审稿** | 弱接受 | **弱接受(维持)** | 主要 2 软化被"+14~+25 随底座塌到 +2.6"新证抵偿;主要 3 因 camera-ready 已出版而由"可修"变"未修",略加重;次要 1 由"弱成立"升为"成立"。仍在弱接受区间 |

---

## 四、⚠️ 必须执行的档案更正

> **这一节是本文档最有行动价值的部分。** 待更正对象:`D:\ZZL_cluade\study_logs\QVF_related_work_verified_20260814.md` 五.3 的 APEX-MEM 分界句草稿。**本文档只读不改档案**,更正文本在此备好,由你决定何时落档。

### 4.1 四条断言的逐条核实结果

| # | 核实档五.3 原断言 | 原文定位与逐字引用 | **判定** |
|---|---|---|---|
| 1 | **"无生成前合法性校验"** | §4.3:"The tool first validates the statement, enforcing a single read-only statement and forbidding Updates, or DDL then executes it against the GraphDB and returns sql outputs wrapped as markdown." / 白名单七表:`events, facts, evidence, entities, event_participants, properties, turns` / 形式定义:"𝒮sql is the set of safe SQLite SELECT (or WITH … SELECT) statements over the whitelisted tables" | **不精确**(须改措辞,不删) |
| 2 | **"循环步数无保证上限"** | §6.2:"All Tools are used with a max limit of 40 for ReACT tool invocations." / 附录 B:"with tool calls capped at 40" / 已确认为**每题跨全部工具的全局上限**,非按工具各 40 | **错,须删** |
| 3 | **"论文未报告端到端 token 成本"** | 附录 C Table 9(跨系统 Total Tok/Q)+ Table 10 "APEX-MEM token decomposition per query":graph construction 13,557(16.6%)/ memory retrieval 21,745(26.6%)/ agent loop overhead 16,174(19.8%)/ tool framing 22,274(27.3%)/ **Total (mean) 81,604** | **错,须删** |
| 4 | **"单时态戳(非严格双时态 ingestion/event 分离)"** | §3.1:"f=(s,p,v,δ,[t_from,t_to],c,ℰ)";事件 "ε=(type,T,L,P,F,ℰ_ε) where T represents the event timestamp";§3.3 "t_anchor the anchor timestamp";§4.3 "temporal expressions are normalized to ISO 8601 format relative to t_anchor";**但物理表另有 `created_at`**:Table 8 TEMPORAL 示例 SQL 逐字 `ORDER BY f.created_at DESC LIMIT 1` | **不精确,且方向反了** ← **本轮最重要的发现** |

**第 1 条详情**:校验存在,但**仅覆盖安全与作用域**。两次独立取证均为 ABSENT:无 LIMIT 强制、无超时、无行数上限、无生成期语法约束(无受限解码/模板/许可函数表),**校验失败后的处置未述**。⚠️ 陷阱:§3.3 确有 "schema-constrained generation",但那是**事实抽取**的,不是 SQL 生成的,**不可混引**。

**第 2 条详情**:只剩「**预算统一、无按题型分配**」。反向增援:Limitations 逐字自认 "The current graph agent also requires multiple tool invocations to converge on solutions, which can impact response latency in interactive settings",并把减少调用次数列为 future work。但 40 是**实验设定常数**(截断式),不是机制级终止证明——**这条差异真实但比原措辞弱**。

**第 3 条详情**:只剩「**两表口径不一致且全文无解释,baseline 四行标 (est.) 且估法未述**」。⚠️【本轮更正指控形式】口径不一致的**性质变了**:Table 9 的两成分口径是**统一且公开披露**的(附录 C 逐字定义 GC + QnA 两成分,`Mem Tok/Q` 对所有行一律不入 Total),所以"选择性排除自家开销"**不成立**;真正的矛盾是**附录 C 一段话里两个 total**(16.6% 用 81,604 作分母,用 Table 9 的 30,000 会得 45.19%)。

**第 4 条详情(单独展开,最要紧)**:原断言把 APEX-MEM 记为"单时态"。原文事实是**两条轴都在库里**——
- **断言/入库轴**:`facts.created_at`(行插入序)+ `events.anchor_datetime`(话被说出的会话时刻)
- **有效期轴**:§3.1 声明的 `[t_from, t_to]`

所以"它是单时态、QVF 是双时态"**说不出口**。但真正守得住的缝在另一处:**两条轴并非都可操作。** 有效期区间是本体层声明,① 闭合边界的赋值规则全文未述(且 append-only + 只读 SQL 意味着 agent 无法回填 `t_to`),② 没有任何示例查询用到它——`t_from`/`t_to` **只作为 §3.1 数学记号出现,从未作为列名出现在任何示例 SQL 中**;全文无 CREATE TABLE、无列清单、无 SchemaViewer 输出样例;全文无 "bi-temporal / valid time / transaction time" 任何术语。而论文自己演示的冲突消解**塌回断言轴**——附录 E Case 1 逐字 "the agent selects the most recent valid entry",实现即 `ORDER BY f.created_at DESC LIMIT 1`。

**结论**:**APEX-MEM 分不开"在 X 时刻为真"与"到 X 时刻已被断言"。** QVF 能主张的只是**查询侧可寻址性**(ASOF 把 as-of 时刻作为算子实参,两轴在查询期均可指定),**不是存储侧双时态**。且这条主张受 QVF 自身牵制:逐字锚点契约违约 WikiState 11.0% / LongMemEval 28.26%,建卡路径零校验——**QVF 的时间溯源自己就有洞,这条只能算软差异。**

### 4.2 更正后的分界句全文(可直接替换核实档五.3 草稿)

> 同期机制最接近的会议论文是 APEX-MEM(ACL 2026 主会长文,pp. 16470–16489):它把对话抽成属性图上带时间的事实断言,以只增存储保留全部版本,再由多工具检索代理(SchemaViewer / EntityLookUp / GraphSQL / Search)在 ReAct 循环中临场生成只读 SQL,由 SQLite 确定性执行,支持 JOIN、聚合与时序计算。**该文已占据的位置须如实交出**:确定性结构化执行、写入侧保留全部版本并在读取时消解、端到端 token 成本的自家分解报告(附录 C / Table 10)、以及"LLM 生成查询不可靠"这条动机的大部分(强底座上执行成功率 93.4–97.6%,失败自恢复 87%)。
>
> QVF 与其的分野收缩到以下四处,且**仅在以下四处**:
>
> (i)**查询的来源不同**。APEX-MEM 的 SQL 由语言模型在循环中临场写出,执行前的校验只覆盖安全与作用域(§4.3 逐字:单语句只读、禁 UPDATE 与 DDL、七张表白名单;`𝒮sql` 定义容许 `WITH … SELECT`,即 CTE);不存在算子清单,无生成期语法约束,亦无语义合法性校验,且无 LIMIT 强制、无超时、无行数上限。QVF 先经问题类型路由,再从封闭算子词表编译出计划,合法性在编译期而非执行期判定。
>
> (ii)**步数的确定方式不同**。APEX-MEM 有硬上限(§6.2 逐字 "a max limit of 40 for ReACT tool invocations",为每题跨全部工具的全局上限),但该预算是对全部题型统一的截断式设定,论文自身 Limitations 亦承认收敛所需调用次数偏多、影响延迟,且附录 B.5 把"按 question type 预测最优工具序列、学会何时停止检索"列为 future work;QVF 的执行步数在编译期随题型确定。**注意:原档"无保证上限"是错的,不可再用;且此处不能讲成"无人想到",只能讲成"作者列为 future work 而未做"。**
>
> (iii)**消解发生的时点与对象不同**。APEX-MEM 的规则是模型在取回的多版本间"选最新"(附录 E Case 1,p.16485,逐字 "the agent selects the most recent valid entry",实现为 `ORDER BY f.created_at DESC LIMIT 1`),只处理版本冲突。其 LOCOMO 评测确有不可答类(§6.1 逐字 "adversarial (unanswerable)")且该类准确率 86.10–87.22%,但 **(a) 弃答是 ReAct 代理的涌现行为,不存在生成前的可判定拦截;(b) 全文只报该类总准确率,不报弃答的 precision/recall,故"该弃而弃"与"该答而误弃"无法分离**。QVF 由确定性替换边在答前判定版本,假前提经 premise_check 前置于生成拦截,并可分别报出弃答的两类错误。**注意:原档不可再按"它没有不可答题"来讲。**
>
> (iv)**时间轴的可寻址性不同**(弱主张)。APEX-MEM 本体声明了有效期区间 `[t_from, t_to]`,但其闭合边界的赋值机制未述,该记号从未作为列名出现在任何示例查询中,且示例查询与消解实现均落在断言轴(`facts.created_at`、`events.anchor_datetime`),因此无法区分"在某时刻为真"与"到某时刻已被断言";QVF 在查询期可就两轴分别指定。**该文并非单时态存储,原档措辞须撤回。**
>
> 引用其成本数据时以自家分解口径 **81,604 tok/Q**(Table 10 均值)为准;其跨系统表(Table 9)记 30,000 tok/Q,该表采用统一披露的两成分口径(构图摊销 + QnA,不含 memory 列),而附录 C 同一段落中的 "graph construction accounts for only 16.6%" 用的是 81,604 作分母(若用 30,000 则为 45.19%),两个 total 不相容。其 "3.3× more tool calls" 仅成立于 Table 6 的 GraphSQL 单列;按总量计,该比在 **1.09×–1.40×** 之间(取决于采信 Table 6 或 Table 7/11,后者与 Table 11 的执行数一致)——**该更正方向对 QVF 不利,同样如实引用。**

### 4.3 QVF 残余守得住的差异清单(标硬/软)

| # | 残余差异 | 硬/软 | 证据强度与要害 |
|---|---|---|---|
| 1 | **管线级路由:按问题类型分派臂与步数预算** | **硬**(但须降调) | §4 无任何问题分类、无按题型分支;§6.2 单一 40 上限;Limitations 自认调用次数待优化;附录 B 多数题 ~10 次即到 84–86%。⚠️ 两处收紧:(a) 确有**数据集级**模式切换(LongMemEval/SealQA 用 Online + Θ_rel > 0.2,LOCOMO 用全量建图),只能说"无按**问题类型**的路由",不能说"无任何配置差异";(b)【本轮新增】**附录 B.5 已把这件事列为 future work**,只能主张"我们做了并给出前沿曲线",不能主张原创问题意识 |
| 2 | **答前 premise_check / 假前提与不可答** | **硬**(须换论证方式) | 消解规则逐字只覆盖多版本择新;Limitations 通篇未提假前提。⚠️【本轮更正】**它有不可答类(86.10–87.22%)**,故不能按"无不可答题"讲;守得住的是「答前可判定拦截」+「**弃答的 precision/recall 无人报**」,后者更具实验可操作性 |
| 3 | **语法成功率 ≠ 语义正确率这道缝** | **硬**(作为未占领的测量空位) | Table 11 计的是 "SQL Errors",success = 执行不报错;**Limitations 全文未承认"语法合法但语义错的静默错答"风险**;【本轮加固】附录 D 作者自己把 GPT-5 的失败归因于 "SQLite syntax differences"——**作者的归因句正是语义层从未被测的反面证据**。该空位无人占 |
| 4 | **闭集算子词表本身** | **机制硬 / 收益软** | 机制:确认无算子清单、无语义校验。收益:97.6% 已打掉大部分动机——**但有一处反向增援**:Limitations 逐字 "With GPT4o as the QnA agent, we observed critically high error rates in graph query generation and tool selection, resulting in 86.35% overall accuracy … We had to add explicit query generation error examples to the GPT4o prompt to achieve this level." 即**查询生成可靠性强烈依赖底座,且需靠提示词补丁救**。闭集的收益只能在**弱/廉价底座**或**语义正确率**维度上论证,不能泛泛主张 |
| 5 | **执行阶段的 LLM 介入程度** | **软** | 不是"有无确定性执行"之别(它的 SQLite 执行同样确定),只是**交错程度**之别:agent loop overhead 19.8% + tool framing 27.3% = 47.1%。须按"程度差异"写,**不可写成范式差异**;且不可写成"论文隐藏成本"(附录 C 文字已承认) |
| 6 | **双时态 / 时间轴可寻址性** | **软(已从硬降级)** | 存储级差异点**不成立**(它有 created_at + anchor_datetime)。只剩查询侧可寻址性,且被 QVF 自身锚点违约 11.0% / 28.26% 牵制 |
| 7 | **成本口径的内部一致性与可预测性** | **软** | "未报告成本"已死。只剩"其附录 C 一段话内两个 total 不相容"+"QVF 步数编译期可定故成本可预测"。**后者尚待 QVF 自证** |
| 8 | **按题型条件化上报净增益的口径主张**【本轮新增】 | **软→可硬化** | 见下文"最该改的一句话"第 2 候选。这是本轮唯一**新长出来**的可主张位:APEX-MEM 的 GraphSQL 步 temporal +9.37 / single-hop −0.07 / Overall +2.26,自证了"按题型分工的机制在总平均上必然显得微小"。若 QVF 把它做成正式的上报口径主张(而非辩解),这条可硬化 |

### 4.4 必须同时记入的两处风险

1. **QVF 侧未经核实。** 本轮只核了 APEX-MEM 一侧。分界句 (i) 断言 QVF"存在编译期语义合法性校验"、(ii) 断言"步数编译期确定"——**这两条没有在 QVF 代码里验过**。且 QVF 自审的 **c₂ = 46.2%**(两链全对时组合题仍只 46.2%)指向墙就在编译/执行/渲染层,与"编译期校验强"是**张力关系**。**建议:把这两条当作 QVF 侧待证项,先验再写进论文。**
2. **节号/表号的置信度已升级。** 线二核实基于 arXiv v1 HTML,当时标注"位置只有中等置信度"(Table 8 曾被标为 A.1.3 与 A.1.4、EntityLookup 那句曾被标为 §3.2 与 §4.2)。**本轮 camera-ready 逐格核实已关闭这条风险**:节号与附录字母两版一致,附录 E Case 1 的坐标为 p.16485。逐字引文一直可靠。**但表总数是 13 不是 12,Table 1 是 7 列不是 6 列——这两处原记录是错的。**

---

## 五、成本口径纪律

**APEX-MEM 自己的成本数字有自相矛盾处。引用时用哪个值,以下为定论。**

### 5.1 Table 9 完整重建(单位 token,`GC Calls` 列除外)

| Method | GC Tok/Conv | GC Calls | Amort. GC/Q | Mem Tok/Q | QnA Tok/Q | **Total Tok/Q** | Acc (w/o Adv) |
|---|---|---|---|---|---|---|---|
| MIRIX (est.) | 15.2M | 4,704 | 98,750 | 4,500 | 13,500 | **112,000** | 85.38% |
| Zep/Graphiti | 9.4M | 5,292 | 60,900 | 2,247 | 3,900 | **64,800** | 75.14% |
| Mem0g (est.) | 4.9M | 2,352 | 31,882 | 3,616 | 5,300 | **37,200** | 68.44% |
| **APEX-MEM** | 2.69M | **3,717** | 13,557 | 8,000 | 16,000 | **30,000** | 84–89% |
| Full Context | 0 | 0 | 0 | **23,653** | 25,000 | **25,000** | 87.52% |
| Mem0 (est.) | 1.9M | 882 | 12,409 | 1,764 | 3,500 | **15,900** | 68.44% |
| Nemori (est.) | 1.0M | 765 | 6,422 | 2,745 | 4,500 | **10,900** | 79.40% |

`Total = Amort.GC/Q + QnA Tok/Q`,**七行一致成立**;`Mem Tok/Q` 一律不入 Total,附录 C 已披露此两成分口径。**3,717 是调用次数,不是 token。**

### 5.2 引用时该用哪个值(逐条)

| 场景 | 用什么 | 不用什么 |
|---|---|---|
| APEX-MEM 的 per-query 总成本 | **81,604 tok/Q**(Table 10 自家实测均值) | 不用 30,000 |
| 其成本构成 | graph construction 13,557(16.6%)/ memory retrieval 21,745(26.6%)/ agent loop overhead 16,174(19.8%)/ tool framing 22,274(27.3%) | — |
| 与 MIRIX 比 | **不给倍数**。写"跨系统成本表口径不同,不可直接相除;APEX-MEM 自报的全口径 per-query 成本为 81,604 token" | 不写 81,604 vs 112,000 = 1.37×,更不写 30,000 vs 112,000 = 3.73× |
| 引用任何跨系统倍数(若不得不给) | 必须同时声明:**7 行中 4 行标 "(est.)"(MIRIX / Mem0g / Mem0 / Nemori),估法全文未述** | — |
| 工具调用总量比(结构化-only vs 全系统) | **区间 1.09×–1.40×**,并注明取决于采信 Table 6 或 Table 7/11 | 不给点值,不用 3.3× |
| "3.3×" 这个数 | 只能写成"仅成立于 Table 6 的 GraphSQL 单列" | 不能写成总调用量比 |
| Table 9 的 8,000(Mem Tok/Q) | 引用时须注脚注 "† Tunable via top-k retrieval budget",即这个有利数字建立在一个**未做精度验证的低 k 设置**上 | — |
| 附录 C 的 16.6% | 引用时必须同时给出 45.19%,并指明这是同一段话内两个不相容的 total | 不能单引 16.6% |
| LongMemEval / SealQA 的成本 | **不能用 Table 9 的 GC Amort. 口径**——这两个基准用在线构图,构图无法在多次查询间摊销 | — |

### 5.3 对称纪律(这一条比上面任何数字都重要)

**对我方有利方向的更正,也要如实引用。** 本轮出现了两条方向相反的更正,必须成对出现:

- **对 APEX-MEM 不利、对 QVF 有利** → 成本用 **81,604** 而非 30,000(2.7 倍差);附录 C 一段话两个 total。**要引。**
- **对 APEX-MEM 有利、对 QVF 不利** → "3.3× more tool calls" 被夸大了 2.4–3 倍,真实总量比 **1.09×–1.40×**;Table 9 的两成分口径是**统一披露**的,"选择性排除自家开销"的指控**不成立**;附录 F 自标 "indirect evidence" 故"夸大"的指控**不成立**;LongMemEval 的 +24.0pp / +13.7pp 是**干净的同底座正向证据**;LongMemEval 上作者**正确指名了最强 baseline**;附录 B.5 已把按题型路由列为 **future work**。**同样要引,而且要主动引。**

**不对称引用是审稿人一眼能看出的东西。** 一篇 related work 里如果所有更正都朝一个方向,读者会默认剩下的判断也不可信。**本轮六条对我方不利的更正,是这一节存在的全部理由。**

---

## 六、未核实清单(一条不省)

### 6.1 APEX-MEM 侧残余(原 10 条已全部关闭,本轮新留 3 条)

1. **Table 9 中 4 行 "(est.)" 的估算方法**(MIRIX / Mem0g / Mem0 / Nemori)全文未述。**引用任何跨系统成本倍数时必须声明。**
2. **LOCOMO 各类别题数全文未给。** 20.82pp、10.01pp、1.5pp 等落差均无 n、无 CI、无显著性检验。要报 n 须回引 Maharana et al., 2024,**不得引本文**。
3. **Table 6 GRAPHSQL 行与 Table 7/11 的 2.0000 倍差异,作者未作任何说明。** 哪一张为真无法从论文内部判定(Table 11 的证据倾向 Table 7)。引用工具调用量时给区间 1.09×–1.40×,不给点值。

### 6.2 论文内不可核实(已确认为"论文未给出",非我方未查)

4. **Full-Context 行的构造方式**:塞进上下文的是什么、多长、是否截断——全文含附录零描述。只能靠 Table 9 的 23,653 tok/Q 侧面钉住。
5. **GPT4o 快照未指名。**
6. **三个基准的判官模型全文未指名**(仅 Table 2 的构图指标指名 GPT5)。**无人工一致性研究、无标注者一致性。**
7. **Table 2 "schema coverage(plausible properties covered)" 的判定标准未操作化。**
8. **`t_to` 在事实被取代时如何赋值,全文未述**;全文无 CREATE TABLE、无列清单、无 SchemaViewer 输出样例。
9. **§4.3 校验失败后的处置未述**(除附录 D 的 87% 自恢复统计外,无机制描述)。
10. **无代码/数据发布**(全文无 GitHub、无 artifact 声明;Ethical Considerations 只谈许可审查与去标识化)。→ 任何重建路径的保真度风险为最高一档,构图 prompt 与 few-shot 未给。

### 6.3 QVF 侧待证(**本轮未核,不得先写进论文**)

11. **QVF"存在编译期语义合法性校验"** —— 分界句 (i) 的断言,**未在 QVF 代码里验过**。
12. **QVF"执行步数在编译期随题型确定"** —— 分界句 (ii) 的断言,**未在 QVF 代码里验过**。且与 **c₂ = 46.2%** 呈张力:两链全对时组合题仍只 46.2%,说明墙在编译/执行/渲染层。
13. **QVF 的 71.1% 必需证据完整率的标注协议能否报多标注者一致性** —— 若报不出,"必需证据完整率分层"这个方法论位还占不住(注:APEX-MEM 的 91.1% 同样报不出,双方都欠这一项)。
14. **QVF 成本可预测性** —— 分界句末段"步数编译期可定故成本可预测",尚无实测曲线自证。
15. **QVF 的 LME-KU 卡片臂 64.1% vs 其 LongMemEval 86.2%** —— 需拆出口径差异(在线构图 vs 离线、判官不同、类别构成不同)与能力差各占多少,**未拆**。

---

## 附:读完这篇,最该改 QVF 的哪一句话

**第 1 候选(主答案)——QVF intro 的动机句。**

现在写的是(大意):

> 「LLM 临场生成的结构化查询不可靠,因此需要闭集算子按路由编译。」

**这句在 APEX-MEM 之后不能原样写。** 它自报 SQL 执行成功率 Sonnet 4.5 **97.6%** / GPT-5 93.4% / Haiku 95.4% / GraphSQL-only 98.8%,失败自恢复 **87%**(附录 D / Table 11)。审稿人只要读过这篇,你的动机第一句就死在第一段。

**该改成**:

> 「LLM 临场生成的结构化查询,其可靠性只在**语法层**被度量过——APEX-MEM(ACL 2026)报出 93.4–97.6% 的执行成功率,而该指标的定义是**执行不报错**(附录 D 将 GPT-5 的失败归因于 "SQLite syntax differences");**语法合法但语义偏离问题意图的静默错答,该文未测量,其 Limitations 亦未承认这一风险。** 闭集算子按路由编译的价值,应在这个未被测量的维度上论证,而非在执行成功率上。」

**为什么是这一句而不是别的**:(a) 它是 intro 的承重句,整篇的方法动机挂在它上面;(b) 它现在是**可被一张表当场打掉**的;(c) 它的替换句同时**是一个可做的实验**(取参考查询,比对结果集,报语法成功率与语义正确率的差值),而 QVF 目前正缺一个能立住的方法创新位——三条候选技术创新已全部零成本证否。改这一句等于把 QVF 从"被打掉动机"改成"占住一个无人测的测量位"。

**第 2 候选(强烈建议一并改,朝有利方向)——组会稿 §5 弱点表第 ③ 行。**

现在写的是:

> 「APEX-MEM 结构化臂只值 +2.26pp,给了'结构化净增益本来就小'的先例——但这削弱而非补强我们的辩解空间。」

**这条判断要撤回。** 本轮拿到完整逐类别 delta 后可判定:APEX-MEM 的 GraphSQL 步在 **temporal 上 +9.37pp(整张消融表最大的单类别增益)**、在 single-hop 上 **−0.07**、在 open-domain 上仅 +1.66。**它并没有建立"结构化增益本来就小"的先例,它建立的是"结构化增益是类别集中的,会被 Overall 平均稀释"。**

**该改成**:

> 「净增益必须按题型条件化上报,否则任何按题型分工的机制在总平均上都必然显得微小——APEX-MEM 的 GraphSQL 步即是示例:temporal +9.37pp、single-hop −0.07pp、Overall 被稀释为 +2.26pp。」

**为什么值得一并改**:这把 QVF 的应对从「辩解 +4.21pp 为什么小」变成一个**方法论主张**,而且**用别人家的数据做示范**。这是本轮唯一新长出来的可主张位(残余差异清单第 8 条),也是唯一一处 QVF 因读这篇而**多**了东西的地方。

**第 3 候选(硬性事实错误,必须删)——核实档五.3「循环步数无保证上限」。** §6.2 逐字 "a max limit of 40 for ReACT tool invocations"。这句是**错的**,不是不精确。留着它,组会上任何读过 §6.2 的人翻一页就能当场推翻,而一处硬错会让在场的人对整份分界句都打折。**优先级上它其实排第一——因为改它是零成本的,而前两条要写新句子。**
