# QVF 组会选文报告(2026-08-17)

**用途**:为 Jeremy Zhong 在组会上分享论文选题,并同时为 QVF 论文找定位。
**依据**:打分结果(20 篇候选)+ 四篇精读七镜报告。venue/编号/已核实数字以 `study_logs/QVF_related_work_verified_20260814.md` 为唯一依据,本报告对其中 **APEX-MEM 分界句草稿的 3 处断言** 与 **TimelineQA 引用措辞的 2 处** 提出更正(见第五节与各篇 takes_from_qvf)。
**阅读层级标注**:APEX-MEM(arXiv v1 HTML 全文级)、Prog-TQA(ACL Anthology 官方 PDF 全文级)、TimelineQA(ACL Anthology 官方 PDF 全文级)、**A-Mem(未取到全文,本报告该篇为结构性草案,所有事实性陈述均标"待核",不得对外引用具体数字)**。

---

## 一、推荐与理由

### 1.1 四篇是什么

| 槽位 | 论文 | venue |
|---|---|---|
| 最危险近邻(钩**定位**) | **APEX-MEM** | ACL 2026 主会长文 |
| 范式先例(钩**方法来源**) | **Prog-TQA** | LREC-COLING 2024 长文 |
| 诊断基准(钩**机制归因证据**) | **TimelineQA** | Findings of ACL 2023(Meta) |
| 相反赌注(钩**设计前提**) | **A-Mem** | NeurIPS 2025 |

### 1.2 为什么是这四篇,而不是 total 前四名

打分表里 total 前四是 APEX-MEM(15)、A-Mem(14)、TimelineQA(14)、LongMemEval(13)/TempReason(13)。本组合**主动放弃了 LongMemEval 与 TempReason,换进了 total 只有 12 的 Prog-TQA**,理由是三条,每一条都可复核:

1. **四篇必须钩住 QVF 四个不同的承压点,而不是四篇同类综述。** LongMemEval 与 TimelineQA 都是基准,TempReason 与 TimelineQA、Prog-TQA 都是时序 QA;若按 total 取前四,四篇里会出现三篇时序 QA + 两篇基准,组合退化成同类堆叠,组会听下来是"这个方向有很多论文",而不是"QVF 站在哪个坐标上"。
2. **Prog-TQA 是自审第 23 行点名的"范式层占先方"。** QVF 的方法叙事就是"编译成算子闭集计划 → 纯代码执行";这件事 2024 年 LREC-COLING 已经做过(LLM 编译 KoPL 程序 + 12 个时序算子 + 符号执行)。**不讲它,QVF 的方法叙事是虚的;讲清它,QVF 才立得住"不是新发明而是域迁移(给定 KG → 对话在线抽取)"。** venue 低不是理由——占先事实与 venue 无关。
3. **补洞覆盖是决定性权重。** 六条真实弱点里,这四篇覆盖四条(见第五节):TimelineQA 给①的实验模板,APEX-MEM + A-Mem 给④的正面实验与机理解释,Prog-TQA 的 KoPL 12 算子是解除⑥循环性所需的"独立方算子清单"。而 LongMemEval 钩住的⑤(LME-KU 靶心)补法是**在 v4.2 口径下重跑那 78 题**,不是在组会上讲一遍自己已经在用的基准;TempReason 只提供 L1/L2/L3 引用框架,不产生定位压力也不补洞。

被刷掉的其余高分候选:MAGMA(ACL 2026 主会,venue 最诱人)会与 APEX-MEM 抢同一个"近邻"槽位却给不出新反例(核实档五.3 已判其时序图仅线性时间戳链、聚合靠 LLM 心算、无 premise_check、无路由);HippoRAG 可讲性满分但属检回环节,对 QVF 任何一句声称都不构成约束,是最典型的"讲得漂亮但白讲";TReMu 与 Prog-TQA 同域更近,但分野在核实档已量化定稿、边际信息少,且 KoPL 那份第三方算子清单是 Prog-TQA 独有的补洞资产;DocETL(PVLDB 顶刊)是唯一通往 DB 社区的一篇,建议留作下一轮。

### 1.3 讲下来是一条线

开场把坐标轴画出来:横轴是"记忆的结构从哪来"(预先枚举的固定契约 ←→ LLM 涌现的自组织),纵轴是"读取时谁做算术"(模型心算 ←→ 确定性代码)。

- **Prog-TQA** 落在(固定契约 + 代码执行)——但库是给定的,写入侧空白;
- **APEX-MEM** 落在(半结构化本体 + 代码执行)——但查询由 LLM 临场写,无路由无 premise_check;
- **A-Mem** 落在(涌现结构 + 模型心算)——是 QVF 的对角线,整个赌注方向相反;
- **TimelineQA** 不是系统,是那把尺子——它证明了这条纵轴上"模型心算"那一端在证据数变大时会崩到 4.3%,而且它自己算金标用的正是"代码执行"那一端,却从未把它当系统评测过。

QVF 落在(固定契约 + 代码执行 + 写入侧从对话在线抽取 + 路由 + premise_check)。**四篇讲完,QVF 的位置是被四个点框出来的,不是自己声称的。**

### 1.4 如果只讲一篇:讲 **APEX-MEM**

**四条理由,按分量排序:**

1. **它直接决定 QVF 能不能说出那句分界句。** 核实档明判其为最危险近邻:属性图 + 只读 GraphSQL(SELECT/JOIN/AGGREGATE/TEMPORAL),执行同为确定性代码,与 QVF 只差"LLM 临场生成 SQL"vs"闭集算子按路由编译"一线。而七镜自审第 985-988 行已写明"当前三支柱没有一条是冲着 APEX-MEM 写的"。讲这一篇 = 把 QVF 最大的定位风险摆到桌面上。
2. **读它当场产出三条必须改的档案更正**(见 3.1 的 C5 表):"无生成前合法性校验"不精确、"循环步数无保证上限"错、"论文未报告端到端 token 成本"错。这三条不改,QVF 相关工作一节会被审稿人当场打掉可信度。**没有任何其他一篇能一次性带来这样的直接收益。**
3. **它同时提供一份反向礼物**,是四篇里唯一的:它的 Table 1 Full-Context 行(同一模型、同一份完整证据,open-domain 92.70% vs temporal 71.88%,落差 20.82pp)**独立地、用别人家的数据**证明了"证据齐全而算术仍不行"——这正是 QVF 头条 +35.4pp 里那约 9pp 检索覆盖混因之外、纯净的那一半,比 QVF 自己的完整层/截断层分层更容易被审稿人接受。
4. **可讲性满分。** ReAct 循环 + 只读 SQL 是全场听众都能跟的具象机制,GraphSQL schema 图即核心图;而它的 Table 3 是一张能同时讲"结构化只值 +2.26pp"和"标题里的能力反而回退 −3.12pp"的表,一张表撑 40 分钟绰绰有余。

**次优单篇是 Prog-TQA**,但它的价值是"必须讲"而非"最好讲":它补的是最痛但最不体面的洞(支柱二的所有权)。如果组会气氛适合自我批评,讲 Prog-TQA 收益更高;如果需要先立住 QVF 的坐标,讲 APEX-MEM。

---

## 二、横向表(可单独取用)

> 后两列是为 QVF 找定位时全表最有用的部分。
> A-Mem 行的所有内容标 **[待核]**,因未取到全文。

| 论文 | venue | A5 一句话真实问题意识 | C 判决 | D 判决 | F 倾向 | **它占走了 QVF 什么** | **它留下什么空位** |
|---|---|---|---|---|---|---|---|
| **APEX-MEM** | ACL 2026 主会长文(2026.acl-long.749, pp.16470–16489) | 作者真正害怕的不是检索不准,而是**写入时对"当前状态"的一次不可撤回的提前承诺,会永久销毁回答一个尚未被提出的问题所需的证据** | **中** | **部分** | **弱接受** | ① "把对话记忆落到确定性结构化执行"不能再称首创/唯一(3,584 条只读 SQL 由 SQLite 执行);② **"LLM 生成的查询不可靠"这条动机基本被打掉**(SQL 执行成功率 Sonnet 97.6% / GPT-5 93.4% / Haiku 95.4%,失败自恢复 87%);③ "写入侧保留全部版本、读取时按有效期消解"是它摘要第 2 点,逐字 "avoid premature commitment to a single current state";④ LongMemEval 高地被占(86.2%),而 QVF LME-KU 卡片臂只有 64.1%;⑤ "结构化机制净增益小"有了先例(其结构化臂只值 +2.26pp,混合检索值 +7.55pp) | ① **管线级路由完全空缺**(§4 无任何问题分类,40 步预算对所有题型平摊,而附录 B 显示多数题 ~10 次调用就到 84–86%)——QVF 四臂路由因此是可测量的成本-精度前沿而非设计偏好;② **答前 premise_check 无对手**(消解规则逐字 "the agent selects the most recent valid entry",只处理多版本,不处理假前提);③ **反向礼物**:Table 1 Full-Context 行替 QVF 做了"检索覆盖 vs 算术能力"的分离(92.70% vs 71.88%);④ **语法成功率 ≠ 语义正确率**这道缝没人补(97.6% 是执行不报错率,TEMPORAL 占其 SQL 62% 且用 `julianday()` 做日差);⑤ 两条头条贡献零受控消融,**ablation 纪律本身是差异化资产**;⑥ LongMemEval 无分类别拆解(knowledge-update 类缺席);⑦ 无组合泛化测试;Qwen3-14B 从未作为 QnA agent 测过 |
| **Prog-TQA** | LREC-COLING 2024 长文(2024.lrec-main.1270, pp.14579–14594) | 作者真正害怕的失败模式是:**组合时间约束("before"+"last")一旦被压进单个时间感知向量的相似度分数里,答案对了说不清为什么对、错了定位不到哪一步错** | **中** | **部分支持** | **弱接受**(投 ACL 主会应为弱拒) | ① **"编译-执行范式"不能作为新意的任何一部分**——2024 年长文已做同一件事,带 12 个时序算子 + 符号执行器 + 消融 + SOTA;② **"六原语完备基"这根支柱被压到接近于零**:它一号贡献原文即"systematically analyze time constraints and design the corresponding temporal operators",唯一差别是它老实写 "these operators can be flexibly extended"(明确开集);③ **具体算子的所有权要交出去**:FilterFirst/FilterLast、FilterBefore/After、FilterByTimePoint、GetYear/Month/Date、FilterByDuration/**GetDuration**、QueryEventQualifier 全部同名同义已存在——"时长计算"不可再称独有;④ "11 算子闭集 vs 12 算子"不可作平行对比(它的 12 个是**增量**,基础 KoPL 函数仍在词表且论文未列举数量);⑤ 自训练/自举也别碰(此文 + Huang et al. 2023 已占) | ① **写入侧完全空白**(库是给定四元组 TKG;CronQuestions 更直接用数据集自带金标实体/关系标注),而它证明了给定库这侧天花板已很高(0.797/0.937),反衬瓶颈在库的来源;② 无管线级路由(每题走同一固定管线 draft→link→execute);③ **检索覆盖度的分解无人做过**(依赖 top-5 事实检索却从不报 recall@5 或覆盖度)——QVF 自审那套分解是没人做过的测量贡献;④ **LLM 直读臂的缺席给 QVF 的负结果撑腰**(五个基线全是前 LLM 时代方法,最强 0.293);⑤ 假前提与不可答完全缺位(判对判据是 `r ∩ gold ≠ ∅`);⑥ 计数类空位需精确表述(基础 KoPL 有 Count,只能主张"沿取代链的 count_changes"是空位);⑦ 成本与延迟零测量,而 Table 7(7B/13B/33B 仅差 1.4pp)可为 QVF 小模型路线背书 |
| **TimelineQA** | Findings of ACL 2023(2023.findings-acl.6, pp.77–91) | 作者真正害怕的是:**整个领域会在"短上下文、少证据"的题上宣布个人记忆问答已被解决,却永远看不见同一批系统在答案需要跨千条记录聚合的那一刻掉到个位数**——所以他们造了一台能无限量生产"金标只能由符号计算得到"的题的生成器 | **中(偏弱)** | **部分支持** | **弱接受**(主会应为弱拒) | ① **"首次指出个人时间线聚合是难点"不能说**(2023 年中已定义 atomic/multi-hop/aggregate/temporal 分类学并在 128M 条量级上测出);② **"符号执行路线用于时间线聚合"不能声称为 QVF 创新**——它自己的金标管线就是 "logical representation → SQL queries → 答案",QVF 的"11 算子 JSON 计划 → 纯 Python 执行"在架构上就是它已经当作 oracle 在用的那一步;③ **它拿走了"没有基准在这个量级上测过这件事"这一步棋**,并让"自建基准循环性"这条攻击变锋利(600k atomic + 4,284 multi-hop + 120 留出 log + 128M 条记录 + Meta 开源,比 WikiState/WSC 的 5,061 unique qid 大两个量级);④ 对 QVF 写入侧是一记警告:其 atomic 抽取式 82.6% EM 被作者亲手归为构造产物("answers are always a valid span in the input")——QVF"逐字锚点"若语料答案本身是原文 span,抽取准确率是以同样方式被抬高的 | ① **完全没有有效性/取代语义——最干净的空位**:单调追加,一致性只靠互斥约束,42 条复杂模板里没有一条问"现在",零道假前提题;后果是 **staleness 处理率 0% 的系统与 100% 的系统在该基准上得分完全相同**;② **没有写入侧,且是作者亲口划出界外的**(§3 "after the inference of episodes has been done";§7 明说抽取与 episode 推断需另作研究);③ 没有 schema/IE 鲁棒性测量(§5.3 "beyond our current scope");④ **时序关系推理被声称为设计目标却未被测量**(§3.2 "therefore we design our benchmark to evaluate these challenges",但 Table 6 题型桶只有 average/count/argmax/list,四桶 n 加总 = 4,284 = 测试集全量);⑤ 没有 plan-and-execute baseline,也没有任何成本口径(全文唯一资源数字是 25.4 A100 GPU 小时);⑥ 没有路由(尽管它自己的分类学就是最显然的路由信号);⑦ density 旋钮从未作为结果轴使用 |
| **A-Mem** **[全篇待核]** | NeurIPS 2025 **[venue 取自打分结果,未复核原文]** | **[待核]** 作者真正害怕的是:**任何预先枚举的固定 schema 都会在设计者没想到的那类问题上失效,而设计者永远想不全**——所以把结构的产生权整体交给 LLM,让笔记之间的链接与组织在使用中涌现 | **[待核]** 倾向 **中**(方向性赌注清晰,但"涌现"缺可判定的机制隔离) | **[待核]** 倾向 **部分** | **[待核]** 倾向 **弱接受** | **[待核]** ① 它不与 QVF 抢同一句声称(打分表相关性给 4 而非 5,属对照而非竞位),**因此"占走"最少**;② 但它占走了一句 QVF 容易顺口说出的话:"结构化记忆优于无结构记忆"——A-Mem 的整个下注方向是"不预设结构",而 QVF 在 S8 未见组合上恰恰输给不做任何结构化的直读 18-21pp(直读 70.1% vs 平面臂 52.2%),**这句话在 QVF 自己的数据上就不成立**;③ **[待核]** 若 A-Mem 的 memory evolution 确实会改写/更新旧笔记,则它与 QVF"保时间线 + 替换边"是同一维上的相反选择,QVF 不能把"更新旧记忆"简单当作对手的缺陷来讲——那是对方的设计,不是疏忽 | **[待核]** ① 无双时态有效期与显式取代链(结构由涌现产生,不承诺可判定的 `valid` 谓词);② 读取侧无可执行算子、无确定性算术;③ 无 premise_check;④ 无管线级路由;⑤ 无成本/延迟三项口径;⑥ **最重要的空位是一个实验位而非机制位**:"涌现结构 vs 固定契约"在**未见组合**上的优劣从未被受控测量过,而这正是 QVF S8 反超现象的机理解释入口 |

---

## 三、逐篇七镜全文

### 3.1 APEX-MEM

> **APEX-MEM: Agentic Semi-Structured Memory with Temporal Reasoning for Long-Term Conversational AI**
> Banerjee, Moshtaghi, Subramanian, Misra, Chadha(全体 Amazon)
> arXiv:2604.14362 / ACL Anthology 2026.acl-long.749, pp. 16470–16489 | **ACL 2026 主会长文**(档案 + Anthology 页双证)
> 阅读层级:**全文级**(arXiv v1 HTML,含 §1–§7 + 附录 A–I + Table 1–12)。**未开 camera-ready PDF**,所有节号/表号按 arXiv v1 编号。

#### A 究竟要解决什么问题

**A1 作者声称**(intro 末段 "Our contributions are threefold",逐字):
1. **混合实体-事件本体**:"a hybrid entity-event ontology … represents conversational events as first-class citizens enabling fine-grained temporal reasoning while maintaining entity coherence"。
2. **仅追加事实存储**:"append-only event storage where facts are anchored to temporally grounded events … preserves the full evolution of information including contradictions and revisions enabling retrieval-time resolution based on temporal validity rather than **premature commitment to a single current state**"。
3. **多工具检索框架**:EntityLookup + GraphSql + Search + SchemaViewer。
摘要头条:LOCOMO 88.88%、LongMemEval 86.2%。

**A2 实际做成的**:
- **贡献 3 有真实受控证据**。Table 3(Claude 4.5 Haiku,累加消融):SchemaViewer+EntityLookup 77.19% → +GraphSQL 79.45% → +Search 87.00%。附录 A/B 另有 GraphSQL-only 变体(79.45%,GraphSQL 调用 27,282 次 vs 全系统 8,260 次);附录 D Table 11 给 SQL 执行成功率(Sonnet 4.5 97.6%、GPT-5 93.4%、Haiku 95.4%);附录 B 给工具调用数-准确率曲线(~10 次达 84–86%,~20 次到顶,上限 40)。**这一块比同类系统论文扎实。**
- **贡献 1(本体)全文零受控消融**。没有扁平本体 / 纯实体本体 / 去 event-as-first-class 任一变体,35 类的类数也无敏感性。Table 2 报的是不同抽取模型的构图质量(Sonnet 4.5 事实抽取 97.3% / schema coverage 91.1% / 实体属性消解 98.2%),测的是**抽取模型**,不是本体设计。
- **贡献 2(仅追加)只有跨系统对照,不是消融**。附录 F Table 12:APEX-MEM 90.63% vs Mem0 75.71%(Δ−14.92)/ MIRIX 65.62%(Δ−25.01)/ Zep 76.60%(Δ−14.03)。**四行是四个不同系统。**

**A1–A2 落差(五条)**:
1. **结构性,最重**:三条头条贡献里两条没有受控实验。唯一被消融的是工程性最强的那条。做一个"APEX-MEM + 冲突时覆盖旧值"的同架构变体在工程上极便宜(同抽取、同本体、同工具,只改写入策略),论文没做,于是 Δ−25.01 完全不可归因。
2. **可逐字取证,最锋利**:标题写 "Temporal Reasoning",而唯一的消融表显示最后加入的 Search 让 temporal 掉了 **−3.12pp(82.29% → 79.17%)**,正文却写 "substantial gains across **all categories** including single-hop (80.78→85.46), multi-hop (79.75→84.74), open-domain (78.00→89.18), and adversarial (81.16→87.22)" —— **五类里唯一没被点名的就是回退的那一类**;且全系统 Haiku 的 temporal 79.17% **低于**只加到 GraphSQL 那一级的 82.29%。
3. **Overall 口径自相矛盾**:Table 3 末行五个分类数字(85.46/84.74/79.17/89.18/87.22)与 Table 1 "APEX-MEM + Claude 4.5 Haiku" 行**完全相同**,而 Overall 一写 **87.00%**、一写 **84.92%**,相差 2.08pp,论文无任何说明。"Search 带来 +7.55pp"换成 Table 1 口径会变小。
4. **两处"超过最强 baseline"都不是同底座,且 SealQA 处误指对手**:
   - LOCOMO 头条 APEX-MEM+**GPT5** 88.88% vs Full Context+**GPT4o** 87.52%(仅 +1.36pp,换了底座),表里**根本没有 Full Context + GPT5 行**;同底座比较是反的——**APEX-MEM+GPT4o 86.35% < Full Context+GPT4o 87.52%**(−1.17pp)。
   - SealQA-Hard 原文 "This **5.55 percentage point improvement over the strongest baseline**",对照 O3 34.6%;但**同一张 Table 5 里 GPT5+Web-Search 是 38.6%**,同底座真实增益 40.1 − 38.6 = **1.5pp**。
5. **成本表口径有利**:Table 9(唯一跨系统 token 对照)记 APEX-MEM Total ~30,000 tok/Q,而 Table 10(自家分解)给 **81,604 tok/Q**;差的 2.7 倍正是 Table 9 没计的 **tool framing 27.3%(22,274)+ agent loop overhead 19.8%(16,174)= 47.1%**。铁证:附录 C 那句 "Graph construction accounts for only 16.6% of APEX-MEM's total cost" 用的正是 81,604 作分母(13,557/81,604 = 16.6%)。**全文无一句解释这 2.7 倍差异**,且所有 baseline token 数都标 "(est.)"、估法未述。

**A3 领域位置**:**换方法,不是开辟新问题**。问题与基准全部继承上游(LOCOMO ACL 2024、LongMemEval ICLR 2025),对手是 Mem0/Zep/MIRIX/Nemori。最有后果的一步是把 **text-to-SQL 的"只读 SQL 执行面"搬进 agent memory**。场景小幅扩张:纳入 SealQA-Hard(30 篇含冲突噪声文档)。下游是 Amazon 生产型助手记忆。

**A4 若无此文,已有方法卡在哪**(按其 Table 1 / Table 12):
- **MIRIX(eager state merge)** LOCOMO temporal 65.62%,同系统 single-hop 85.11%,**系统内落差 19.49pp**。根因:写入时把旧值合并成单一当前状态,"改之前是什么/持续多久/什么时候变的"在库里已无可读旧行。
- **Mem0(consolidation)** multi-hop 47.19%,同系统 single-hop 65.71%,落差 18.52pp。根因:事实压成扁平条目,实体间 join 路径被压掉。
- **Zep(partial temporal KG)** temporal 76.60%,~64,800 tok/Q。根因:保住时间线但检索不以问题的时序算子为条件,取回文本后的计数/时长/排序仍交模型。
- **最关键一条:Full Context + GPT4o 把整段对话塞进上下文,open-domain 92.70%,而 temporal 只有 71.88% —— 同一模型、同一份完整证据下 20.82pp 的落差。** 根因:在几十条散落的带日期提及上做计数/时长/排序,是模型在上下文里不可靠执行的算术任务,与检索覆盖度无关。**这一行把"检索不全"与"算术不行"两个混因分开了,是本文对领域最干净的贡献,也是 QVF 最该引用的一行。**

**A5 一句话真实问题意识**:作者真正害怕的不是"检索得不准",而是**写入时对"当前状态"的一次不可撤回的提前承诺,会把回答一个尚未被提出的问题所需的证据永久销毁**——append-only、事件作一等公民、读取时消解、四工具并行,全是为"我在写入时做的决定事后无法反悔"这一失败模式买的保险。

#### B 隐含前提

**B1 数据** — 明说:LOCOMO / LongMemEval / SealQA-Hard;后两者用在线构图,相关性阈值 Θ_rel > 0.2;数据去标识化。**未明说但实际依赖**:(a) 基准答案恰好可被 35 类本体表达(schema coverage 91.1% 已暗示约 9% 覆盖不到,而 Table 2 的评测协议全文未述);(b) LOCOMO 是 persona 驱动生成的,日期干净自洽,§3.3 的 "ISO 8601 relative to t_anchor" 只在此前提下正确;(c) 问题都有答案(或以 adversarial 显式给出),**不含假前提问题**。**高风险**:真实对话里"上次聊的时候""搬家之前"无法归一,或说话人记错日期,则 [t_from, t_to] 错;而 **TEMPORAL 类 SQL 占 Sonnet 全部 SQL 的 2,235/3,584 ≈ 62%**,Table 8 显示用 `julianday()` 做日差算术——区间错则**自信地算出错的时长,无弃答机制**。这一条翻掉,90.63% 直接失效。

**B2 方法** — 明说:GraphSQL 是只读 SQL,执行前校验(单条只读语句、禁 UPDATE/DDL、七表白名单);构图用 Sonnet 4.5(抽取)+ Haiku 4.5(消解);ReAct 上限 40。**未明说但实际依赖**:(a) schema 小到能塞进提示词(SQL 失败恢复里 45% 走 SchemaViewer 重看 schema,而 Limitations 自认本体可能需扩展——本体一扩,这条主恢复路径同步退化,是**级联依赖**);(b) top-k 检索预算可下调而不掉分(Table 9 的 QnA 8,000 带脚注 "‡Tunable via top-k retrieval budget",而 Table 10 实测 memory retrieval 是 21,745——**有利的成本数字建立在一个未做过精度验证的低 k 设置上**);(c) 前沿模型会写 SQLite(Qwen3-14B 只用于构图质量评测,**从未作为 QnA agent**);(d) "取回的多版本证据是完整的",因为消解规则就是附录 E 那句 "a GraphSQL temporal query returns both facts ordered by timestamp; the agent selects the most recent valid entry"。**高风险**:若最新版本压根没被抽取出来,agent 会**自信地选中"取回集合里最新的那条陈旧事实"**;既无答前前提校验也无答后一致性审计,9% 的抽取漏就转化为确定性的自信错答。

**B3 任务** — 未明说但实际依赖:**"记忆有效性可由时间戳单调序判定"**(即 `valid : S → {0,1}`,不以问题为条件),比 QVF 的 `valid : S × Q → {0,1}` **更弱**。它在"某时点是什么"类问题上靠 SQL 的 WHERE 时间窗补救,但补救逻辑由模型每次临场写出。**高风险**:一旦问题要求的不是"最新"而是"某历史时点/某段区间/取值变了几次",且模型没写对时间窗,append-only 保下来的旧行**存在但不被读到**——这正是它用来打 Mem0/MIRIX 的那个故障的读取侧同构版本。

**B4 实验** — 明说:temperature 0;3 次试验取均值,标准差 < ±1;判官 GPT-5;LOCOMO baseline 由作者重跑,其余用原文报告数字。**未明说但实际依赖**:(a) Overall 聚合口径(已证不一致);(b) 消融的**累加次序**(GraphSQL 第二、Search 第三,边际贡献与次序强耦合,**无 leave-one-out**;若 Search 先加,+2.26/+7.55 这个 3.3 倍差距很可能变形);(c) baseline 方差未知——88.88 vs MIRIX 85.38 的 3.5pp 在 std<±1 下大概站得住,但 88.88 vs Full Context 87.52 的 1.36pp 与 SealQA 的 1.5pp **不足以宣称显著**;全文无任何显著性检验或置信区间。**高风险**:"3.3x more tool calls (27,282 vs 8,260)" 读起来像总调用数,但按 Table 6 加总,全系统 Haiku 总调用 = 5,160+8,900+3,346+3,958+8,260 = **29,624**,GraphSQL-only 变体 = 5,546+0+5,016+3,622+27,282 = **41,466**,真实总量比是 **1.40×,不是 3.3×**(3.3× 只成立于 GraphSQL 这一列)。**这条是对 QVF 有利方向的更正:结构化-only 路线的开销代价被论文夸大了。**

**B5 应用** — 明说:文本-only;构图算力开销大。**未明说但实际依赖**:构图可离线一次、开销在多次查询上摊销(Table 9 的 "GC Amort. Tok/Conv 3,717" 全靠这个)。但 §5 + §6.2 说 LongMemEval 与 SealQA 用**在线构图,且以 Θ_rel>0.2 门控**——即构图是**按查询条件化**的,**头条 86.2% 来自在线模式,而在线模式下构图无法在查询间摊销**,Table 9 的摊销口径不适用于它。**高风险**:在线模式下若答案所在会话与问题无语义/词法交集,门控就把它筛掉,图里压根没有这些事实,86.2% 塌方。**这与 QVF 自审"必需证据完整仅 71.1%"是同一个洞,只是它没测。**

#### C 真实创新点

- **C1 改了哪个环节**:**写入侧的承诺时机 + 读取侧的执行面**,两处同时改。写入侧:事实挂在带时间戳的事件上而非直接挂实体,冲突不覆盖(f=(s,p,v,δ,[t_from,t_to],c,ℰ),ε=(type,T,L,P,F,ℰ_ε));读取侧:把只读 SQL 接口暴露给 ReAct 代理,JOIN/AGGREGATE/TEMPORAL 由 SQLite 确定性执行。
- **C2 引入什么新东西**:建模——35 类类 YAGO 本体 + 实体对话角色 ρ ∈ {Speaker, Listener, Agent, Mentioned} + 属性类型系统 δ;无训练(全 prompting + schema-constrained generation + 手工 few-shot)。数据处理——在线构图的查询条件化门控(Θ_rel>0.2),把"构图"本身变成检索的一部分。评估——两项新颖度不低的分析:附录 B 的工具调用数-准确率曲线、附录 D 的 SQL 执行成功率与失败恢复路径分解(恢复 87%,其中 SchemaViewer 45% / EntityLookup 28% / Search 14%)。
- **C3 机制(不是"实验涨了")**:**机制一(写入)**——覆盖式更新是信息论上的有损操作,而问题分布在写入时未知;保留全部版本把"选哪个版本"从写入时的无信息决策推迟到读取时的有信息决策。**机制二(读取)**——计数/时长/排序在自然语言上下文里对 LLM 是高错误率操作(其 Full-Context 行:证据齐全下 temporal 仍只 71.88%),把这类算子下沉到 SQLite 消除了这一类错误源;Table 3 的 GraphSQL 一步 temporal +9.37pp(72.92→82.29)是机制二的直接显影。**但机制二在完整系统里被机制外的东西吃掉了**:加 Search 后 temporal 回落到 79.17%,论文未诊断。
- **C4 概念/技术/工程**:**工程为主,技术为辅,概念最弱**。append-only + 读取时消解在 Zep、Semantic XPath 已有;event-as-first-class 在时序 KGQA(ExaQT/TempoQR)有先例;ReAct 多工具是标准范式;只读 SQL 沙箱是 text-to-SQL 既有工件。真正属于本文的是**这套组合在生产级系统跑通,并给出工具级归因、SQL 成功率、调用数曲线三项工程证据**。
- **C5 分界句**:vs **MIRIX**——问"改之前的值是什么"时,MIRIX 库中已无该行(temporal 塌到 65.62%),APEX-MEM 有。vs **Zep**——是否存在一个执行阶段由代码而非模型完成的算术。vs **Mem0**——multi-hop 时是否存在可 JOIN 的 evidence/event 关系表。

**vs QVF —— 档案分界句草稿必须更正 3 处**:

| 档案草稿断言 | 全文核对 | 判定 |
|---|---|---|
| "无生成前合法性校验" | §4.3:"The tool **first validates the statement**, enforcing a single read-only statement and forbidding Updates, or DDL then executes it… over the whitelisted tables" | **不精确,须改**。有执行前校验,但是**安全/作用域校验**(单语句只读 + 表白名单),不是**封闭算子词表的语义合法性校验** |
| "循环步数无保证上限" | §6.2:"All Tools are used with a max limit of **40** for ReACT tool invocations";附录 B:~20 次到顶 | **错,须删**。有硬上限 40。可保留的只是"预算对全部题型统一,无按类型的步数分配" |
| "论文未报告端到端 token 成本" | 附录 C Table 9 + Table 10(81,604) | **错,须删**。可保留的只是"跨系统表口径与自家分解不一致(~30,000 vs 81,604)且未说明" |
| "无管线级路由,全部查询走同一多工具循环" | §4 全文无问题分类/类型分派 | **成立,保留** |
| "冲突消解由模型在多版本证据间自行择取,无答前 premise_check" | 附录 E:"…the agent selects the most recent valid entry" | **成立,保留**,且现在有逐字出处 |

**更正后可用的分界句(建议替换档案五.3 草稿)**:
> 同期最接近的会议论文是 APEX-MEM(ACL 2026 主会):其多工具检索代理在 ReAct 循环(硬上限 40 步)中调用只读 SQL 接口,能生成含 JOIN/AGGREGATE/TEMPORAL 的结构化查询并由 SQLite 确定性执行,执行前也做了单语句只读与表白名单校验,论文亦报告了 token 成本。**QVF 的分野在三处且仅在三处**:(i) 查询不是由语言模型临场写出,而是先经问题类型路由再从封闭算子词表编译,故存在生成前的**语义**合法性校验与编译期可判定的执行步数,而非全类型共用一个 40 步预算;(ii) 冲突消解不是由模型在取回的多版本间"选最新",而是由确定性替换边在答前判定,且假前提问题经 premise_check 在生成前拦截;(iii) 执行阶段零 LLM 介入,而 APEX-MEM 自家分解显示其 per-query token 中 agent loop overhead 与 tool framing 合计占 47.1%。

> **判决 C:新意 中。** 无一组件概念首创,机制主张亦未隔离;但"把只读 SQL 执行面搬进对话记忆 + 写入侧拒绝提前承诺"是设计空间里一个真实的新点,并在所有对手集体塌方的 temporal 类上拿到 90.63%,加上三项少见的工程证据。够中,不够强,不至弱。

#### D 实验支持度

| # | 结论 | 直接支持 | 缺什么 |
|---|---|---|---|
| 1 | 多工具组合优于单工具 | **有**。Table 3 累加消融 77.19→79.45→87.00;附录 A GraphSQL-only 79.45%;Table 11 SQL 成功率 | 无 leave-one-out;次序耦合;Overall 口径与 Table 1 冲突 |
| 2 | 结构化 SQL 提升时序推理 | **有,但局部**。+GraphSQL 使 temporal 72.92→82.29(+9.37pp) | **加 Search 后回落至 79.17%,论文未诊断也未在正文承认** |
| 3 | append-only 优于 eager 更新 | **无受控证据**(仅 Table 12 跨系统) | 缺"APEX-MEM + eager 覆盖"同架构变体;Δ 不可归因 |
| 4 | 混合实体-事件本体带来细粒度时序推理 | **无任何证据**(Table 2 是抽取模型对比) | 缺扁平/纯实体本体对照,缺 35 类的类数敏感性 |
| 5 | SOTA:LOCOMO 88.88% | 数字为真 | **同底座反向**(86.35% < 87.52%);无 Full Context+GPT5 行;1.36pp 不足称显著 |
| 6 | SOTA:LongMemEval 86.2% | **较强**。Full-Context+Sonnet 4.5 仅 62.2%,差 24pp,记忆系统的价值真实 | Nemori/Zep 为引用数字,底座与判官是否一致未述;**无分类别拆解**(knowledge-update 类缺席) |
| 7 | SealQA-Hard +5.55pp over strongest baseline | **不成立**(同表 GPT5+Web-Search 38.6% 更强,真实同底座增益 1.5pp) | — |
| 8 | 跨题型泛化(<5pp 波动) | Table 1 分类数字部分支持 | Haiku 行 temporal 79.17% vs open-domain 89.18% 是 10.01pp,已超声明 |
| 9 | 成本显著低于 MIRIX | **口径有利**(Table 9 记 ~30,000 而自报 81,604) | baseline 全为 "(est.)";在线模式下构图无法摊销,而 86.2% 来自在线模式 |

**偏向选择**:头条 LOCOMO 用 GPT5 底座而唯一 Full Context 对照留在 GPT4o;SealQA 的"最强 baseline"绕过同表更强的同底座项;跨系统成本表排除自家最大两项开销——**三处都朝同一方向**。
**公允之处(必须报)**:temperature 0、3 次均值、std<±1、判官明示、LOCOMO baseline 亲自重跑以对齐模型代际、Adversarial 类纳入 Overall(许多对手直接 N/A)、Limitations 诚实承认成本/本体/模型依赖——都在同类系统论文的中位数之上。

> **判决 D:实验支持 部分。** 贡献 3 被受控消融真实支持,LongMemEval 24pp 差把核心价值立住;但两条头条贡献零受控证据,两处头条比较在同底座下退化到不显著或反向,Overall 口径自相矛盾,唯一跨系统成本表排除自家 47.1% 开销。不够"充分",远未到"不足"。

#### E 反例(7 条)

**E1** 依赖在线构图的 Θ_rel>0.2 能召回答案所在会话;在"问题措辞与证据措辞无词法/语义交集"时不成立(门控用的正是相似度)。构造:问"我关于那次旅行改了几次主意",而相关会话只出现"订了机票""退了""又订了另一家"。**LOCOMO 没有用在线构图,所以最细的 temporal 证据(90.63%)恰恰不覆盖这条依赖,而头条 86.2% 恰恰来自这个模式。**
**E2** 依赖 QnA 底座能写对 SQLite。Limitations 原文:GPT4o "critically high error rates in graph query generation and tool selection";SealQA 上 GPT4o 只 19.0% vs GPT5 40.1%(**掉 21.1pp**)。Qwen3-14B 从未作为 QnA agent 测过——而"端侧长期记忆"这个最现实的部署场景正是小模型。
**E3** 依赖每条事实能拿到形状良好的 [t_from, t_to];相对/模糊/记错时间下不成立(归一化锚在单一 t_anchor)。TEMPORAL 是最大类(62%),用 `julianday()` 做日差;区间错则**算出自信的错时长**,全文无弃答/置信阈值机制(事实带 c∈[0,1] 但从未用于阈值决策)。
**E4** 依赖"取回集合包含真正最新的那条";而自报 schema coverage 只 91.1%。消解规则逐字 "the agent selects the most recent valid entry" —— 若最新版本未被抽取,agent 就选中"取回集合里最新的陈旧事实",**约 9% 的抽取漏稳定转化为高置信错答**,而非可检出的弃答。
**E5** 依赖 35 类类 YAGO 本体覆盖领域;企业/编码助手/临床场景不成立(实体是代码符号、工单、配置键)。且本体一扩 schema 塞不进提示词,而 SQL 失败恢复的 45% 主路径正是"重看 schema"——**级联依赖**。
**E6** 依赖 40 步预算相对题目难度宽裕;实体名高度歧义的大库中不成立(Table 8 的 SELECT 示例逐字 `WHERE entity_name LIKE '%Anthony%' COLLATE NOCASE`)。**因为没有管线级路由,40 步对所有题型一律平摊**:单跳题浪费,重组合题被截断。**这条同时是 QVF 路由设计最直接的卖点。**
**E7** 依赖 GPT-5 as judge 与人工判定一致,在 adversarial(不可答)类上尤其可疑,而这一类恰是它唯一有分而多数对手 N/A 的类。全文无人工-判官一致性研究。(公允说明:两个基准的推荐判官本就如此,这是社区惯例,故本条是最弱的一条。)

#### F 审稿人视角

| 项 | 判 |
|---|---|
| 问题重要性 | **高**,ACL 主会合适 |
| 创新性 | **中**,组件皆有先例,组合与工程证据是真贡献 |
| 方法清楚 | **清楚**,§3 形式化、§4 四工具接口、§5 门控、超参齐全,可复述 |
| 实验充分 | **不足**,三条贡献两条无受控消融;无 leave-one-out;无显著性检验;LongMemEval 无分类别拆解 |
| baseline 公平 | **不公平处明确**(见 D 节偏向选择三条) |
| 结论夸大 | **有,可逐字取证**:"gains across all categories" 而 temporal 回退;"5.55pp over the strongest baseline";"3.3x more tool calls" 实为总量 1.40× |
| 可复现 | **中偏好**。模型版本/温度/步数/阈值均给;构图 prompt 与 few-shot、Table 2 协议、Overall 定义缺失 |
| 逻辑跳跃 | 两处:由 Table 12 跨系统差推"append-only 优于 eager";由累加边际推工具重要性排序而次序未做对称检验 |

**主要 1:LOCOMO 同底座比较是反的,SealQA"最强 baseline"被误指,两处头条优势在同底座下退化到 1.4–1.5pp 且不显著。**
*作者会回应*:LOCOMO 对话本就塞得进上下文,记忆系统的价值在规模化,看 LongMemEval——Full-Context+Sonnet 4.5 只 62.2% 而我们 86.2%,差 24pp。
*能否成立*:**对总命题成立,对头条数字不成立。** LongMemEval 的 24pp 确实把"记忆系统有必要"立住了,必须公允承认。但救不回两件事:(i) 88.88% 是全文被引最多的数字,却来自一个系统并不必要的基准,且同底座下输给纯上下文;(ii) 论文最珍贵的分类别 temporal 证据(90.63%、Table 12 全部 Δ)**全部只在 LOCOMO 上,即只在那个不需要记忆系统的基准上**。SealQA 的误指没有任何辩解空间,是必须改的事实错误。

**主要 2:三条头条贡献里两条零受控消融;Table 12 是四个不同系统,故 90.63% 无法归因于 append-only。**
*作者会回应*:append-only 与 eager 是架构级承诺,不是可插拔开关;竞争系统本身体现了另一种选择。
*能否成立*:**不成立,这是最致命的一条。** 该变体工程上极便宜(同抽取、同本体、同四工具,只在写入时覆盖而非追加)。拒跑它,意味着 90.63% 可归因于至少四个同时不同的变量。而 append-only 是摘要三点里的第 2 点、是标题里 "Temporal Reasoning" 的主要依托。**贡献 2 作为一个 claim 未被支持。**

**主要 3:唯一的工具消融显示时序推理在完整配置下反而下降,而正文用 "gains across all categories" 掩过;同时 Overall 口径矛盾,头条 +7.55pp 依赖于口径。**
*作者会回应*:Overall 差异是聚合方式不同(题级 micro vs 类别 macro),camera-ready 会统一;temporal 的省略是笔误。
*能否成立*:**聚合解释可信且可修,但必须披露,因为它改变头条增益的大小;temporal 的省略不能以笔误结案。** 时序推理写在标题里,而唯一的消融表显示最后一个组件让它退步、退步后的完整系统在该类上不如中间配置——这是需要**机制诊断**的现象(很可能是混合检索注入的无日期文本片段与 SQL 结果争夺注意力),不是排版问题。列举五类时恰好只漏掉唯一回退的那一类,概率上难以支持"无意"。

**次要 1**:跨系统 token 表记 ~30,000 而自家分解 81,604,被排除的 47.1% 恰是 agentic 架构的固有开销,全文无一句解释。*回应*:baseline 都是 est.,Total 列是近似量级。*能否成立*:**弱成立**——标 est. 的估计可以粗,但**自家那一行不该用比自家分解宽松的口径**,尤其当附录 C 的 16.6% 正是用 81,604 作分母算出。至少须改为 81,604 并把"显著低于 MIRIX"降级。
**次要 2**:LongMemEval 无分类别拆解,而 knowledge-update 类是检验 append-only 最直接的靶。*回应*:篇幅。*能否成立*:**不成立**——一张六格小表,是全文对贡献 2 最有诊断力也最便宜的证据,且还能顺带验证 Θ_rel 门控在哪类问题上召回失败。
**次要 3**:GPT-5 as judge 无人工一致性研究。*回应*:两基准都用其推荐判官以保持可比。*能否成立*:**成立,本条我让**——记为"领域共同欠账",不算本文失分项。

> **判决 F:倾向 弱接受。** 问题重要、方法清楚、三基准两处真实 SOTA、LongMemEval 24pp 立住核心命题、工程证据质量高于同类、Limitations 诚实;但两条头条贡献无受控证据、两处"超过最强 baseline"在同底座下退化到不显著或反向(SealQA 一处属可判定的事实错误)、Overall 列自相矛盾、唯一消融里标题所指能力反而回退且被措辞掩过。这些属可在 rebuttal/camera-ready 内修补的表述与补实验问题,不是方法失效,故不到弱拒;但足以取消"接受"。

#### G 五个扩展方向

**G1 写入策略的受控消融**(来源:D 结论 3 + F 主要 2)。问题:抽取/本体/工具/底座全部固定时,写入时提交单一当前状态究竟造成多少不可恢复损失,损失如何随问题类型分布变化?做法:三档写入策略(全追加 / 冲突即覆盖 / 覆盖但保留 K 个最近版本),其余固定,在 LOCOMO + LongMemEval 上按题型拆解,**新增"历史值查询"题型切片**(问改变前的值、改变次数、持续时长),3 seed 报 CI。难点:是否开源未核实;重建则构图 prompt 与 few-shot 未给,保真度是主要风险。
**G2 诊断"混合检索为何伤害时序推理"**(来源:A2 落差二 + Table 3 的 82.29→79.17)。问题:当 SQL 返回的确定性聚合结果与语义检索返回的无日期文本片段同时进入提示词,模型在何种条件下弃用前者?**这是一个逆直觉的、已被数据显影但无人解释的现象,且直接决定"确定性执行"这一范式在混合系统里能不能兑现。** 做法:控制注入片段数量与时间相关性;记录最终答案与 SQL 结果的一致率;做位置/顺序交换;用"抹掉 SQL 结果看答案是否变"测依赖度。若确认是注意力竞争,则给出"执行结果必须独占/必须带来源优先级标注"的设计律。
**G3 把"证据完整性"从"算术正确性"里分离的统一诊断协议**(来源:A4 Full-Context 行 + E1 + QVF 自审 71.1%)。做法:每题标注"必需证据集";记录被测系统实际取回集;coverage = |取回∩必需|/|必需|;准确率按 coverage 分层(完整层/截断层);再以 oracle-evidence 臂给算术上限。至少三个系统对照(结构化 / 时序 KG / 纯 RAG)。难点:标注昂贵且有主观性(须报多标注者一致性);oracle 臂易泄漏答案措辞。
**G4 "LLM 临场写 SQL"vs"封闭算子词表编译"的直接对撞**(来源:B2 + C5 + Table 11)。**关键洞察:Table 11 报的是执行成功率(不报错),不是语义正确率(算对该算的);一条语法合法但时间窗写错的 SQL 会静默给出错答案并计入 97.6% 的"成功"。这个区分是可发表的。** 做法:取其生成的 SQL 全集(Sonnet 3,584 条),对子集人工标注"语义是否实现问题意图",给出语法成功率与语义正确率的差;再用闭集算子编译执行同批问题。难点:"语义正确"须可操作化(与人工参考 SQL 的**结果集**比对,而非比对 SQL 文本);闭集表达力须先证明覆盖这批问题。
**G5 按问题类型分配步数与工具预算的路由层,及其成本-精度前沿**(来源:E6 + B4 + 附录 B 曲线)。它全类型共用 40 步、~29,624 次调用,而多数题 ~10 次就到 84–86%——**存在一个尚未被任何人画出的成本-精度前沿**。做法:先用其调用轨迹做离线分析,按题型统计到达平台期所需调用数;写规则或小分类器分派预算(单跳 3 / 聚合 8 / 时序 12 / 组合 30);报 Pareto 前沿(准确率 vs token vs 延迟)。**纪律:必须同时报告分类器本身的 token 成本,否则重犯"用一段提示词换分"的错——QVF 自审已查出整合系统增益里 +5.64pp 来自一段提示词、结构化机制净 +4.21pp,路由层的收益必须以同样的净口径报。**

#### 三条判决(APEX-MEM)

- **C 新意**:**中**
- **D 实验支持**:**部分**
- **F 审稿倾向**:**弱接受**

---

### 3.2 Prog-TQA

> **Self-Improvement Programming for Temporal Knowledge Graph Question Answering**
> Zhuo Chen, Zhao Zhang, Zixuan Li, Fei Wang, Yutao Zeng, Xiaolong Jin, Yongjun Xu(ICT-CAS / UCAS)
> arXiv 2404.01720 = ACL Anthology 2024.lrec-main.1270 | **LREC-COLING 2024 长文, pp. 14579–14594**
> 阅读层级:**全文级**(官方 PDF 16 页文本完整提取,含 Table 1–10、Algorithm 1、Appendix A.1–A.6、Figure 7/8 提示词原文)。Figure 1–6 为位图,图内逐点数值未核实。

#### A 究竟要解决什么问题

**A1 作者声称**(§1 末贡献列表,逐字三条):
1. "We systematically analyze time constraints in TKGQA and design the corresponding temporal operators to extend KoPL to handle temporal questions."
2. "we propose a two-stage framework … Prog-TQA, which leverages the ICL ability to perform few-shot program generation. Besides, we incorporate an effective self-improvement strategy…"
3. "It achieves up to 50.4% improvement overall at Hits@1 on MultiTQ and 3.5% for complex questions at Hits@1 on CronQuestions."
摘要落点:"especially in the **Hits@1** metric"。

**A2 实际做成的**:
- MultiTQ 上多约束题从相似度打分换成算子程序执行,Hits@1 Overall 0.293(MultiQA)→ **0.797**,Multiple 0.159 → **0.750**(Table 2)。54,584 题上 50pp 级差距不可能是噪声。
- 少逻辑形式标注下生成可执行程序:每类 20 个人工标注示例 + gold answer 弱监督迭代自举(§3.3.1、Algorithm 1)。SI 净值 **+21.4pp** overall / **+37.1pp** multiple(0.583→0.797 / 0.379→0.750,Table 4)。
- linking 模块(骨架抽取 → miniLM 句向量 → cosine 选 top-5 事实 → 模糊匹配)相对 MultiQA 的 linking 值 **+13.2pp** Hits@1 / +4.3pp Hits@10。
- **只声称未证实**:贡献一"系统分析时序约束并设计对应算子"**一次都没被消融**。Table 4 的四个设置是 SI / linking / post-processing / 示例数,没有任何一行是"去掉设计的时序算子"或"用原生 KoPL / SPARQL 表达同一约束"。全文唯一支撑是 Figure 1 的定性对照。
- **只声称未证实**:CronQuestions 上"程序化优于嵌入"这一层。§4.1 明写 "we directly utilize the entity and relation annotations given in the CronQuestions" —— 该数据集上 **linking 被金标实体/关系标注绕过**,0.937 是在给定链接前提下拿到的。

**A1–A2 落差(三条)**:
1. **一号贡献零消融。** 排第一的贡献是全文唯一没有对应实验的贡献。读者无法从任何表判断 12 个时序算子买了多少 pp。
2. **增益归因未分解,摘要选择性披露。** 增益高度集中在"答案是时间"的题:MultiTQ 上 time-answer Hits@1 EmbedKGQA = **0.001**、Hits@10 = **0.001**(嵌入法在实体候选集上打分,时间戳不在其输出空间),MultiQA 0.157 → Prog-TQA **0.815**(+65.8pp);entity-answer 0.349 → 0.790(+44.1pp)。CronQuestions 上 entity-answer **反而输**给 TempoQR(Hits@1 0.914 vs 0.926;Hits@10 0.968 vs 0.980),Hits@10 Overall 也输(0.973 vs 0.978)。摘要只说 "especially in the Hits@1 metric"。且 Table 8 只按题型切分不按答案类型切分,**读者无法把 +50.4pp 分解为"时间格式输出能力"与"时序推理能力"**。
3. **"few-shot / few annotations" 是措辞层的位移。** §4.1 明写 "2 rounds of iteration on **100k** fine-tuning data for MultiTQ and 1 round on **50k** for CronQuestions",Figure 5 还显示 10k 时因多约束类正确标注不足而明显更低。"少"指的只是**逻辑形式**标注少(20/类),(question, gold answer) 标签仍消耗 10 万条。**系统级不是 few-shot。**

**A3 领域位置**:**换方法**(附带一个小的**换表示**贡献)。上游:KoPL/KQA Pro(Cao 2022)提供语言与执行器;KB-BINDER(Li 2023)提供"LLM ICL 生成逻辑形式、少标注"路线;Huang et al. 2023 提供 LLM self-improvement 框架(作者 §2 自陈沿用,差别是"the iterative process is highlighted")。下游:把算子-执行范式搬到别的时序库。任务与两个数据集都已存在,换的是求解范式(嵌入打分 → 程序生成+符号执行)。

**A4 若无此文,已有方法卡在哪**:
1. **多约束题**:MultiQA(彼时 MultiTQ SOTA)Hits@1 Multiple = **0.159**,CronKGQA 0.134,EmbedKGQA 0.134,BERT 0.061。根因:把组合约束("before"+"last")压进单个时间感知向量的匹配分里,没有"先定位参照时间点 → 再按 before 筛 → 再按 last 排序"这三个可分解的计算步,因此约束既不可组合也不可定位。
2. **答案为时间的题**:EmbedKGQA Hits@1 = **0.001**、Hits@10 = **0.001**。根因:嵌入方法在实体候选集上打分,时间戳根本不在输出空间。
3. **传统语义解析路线**:TEQUILA / SF-TQA 要么依赖大量逻辑形式标注,要么受 SPARQL 表达力所限——单个时序操作需要多个查询子句,"not concise enough for automated generation"(§1 逐字),不适合 LLM 自动生成。

**A5 一句话真实问题意识**:作者真正害怕的失败模式是:**组合时间约束被隐式嵌入吞掉之后,答案对了说不清为什么对、错了定位不到哪一步错**——即时序约束一旦不可分解为显式计算步,就既不可组合也不可诊断。

#### B 隐含前提

**数据** — 明说:MultiTQ(时间点、单+多约束)、CronQuestions(区间、**仅单约束**);统计见 Table 8(MultiTQ 386,787/57,979/54,584;CronQuestions 350,000/30,000/30,000);每类 20 个人工标注示例;100k/50k 微调数据。**未明说但实际依赖**:(a) 每题在 TKG 内可答且有非空 gold answer(否则 Algorithm 1 line 22 的 `r ∩ gold_answer ≠ ∅` 无意义);(b) **题目自带可用的 category 标签**用于同类示例检索(§3.3.1 "samples N examples of the same category as the query question"),真实提问不带这个标签;(c) CronQuestions 的实体/关系标注是**金标**;(d) 人工标注总量论文从未给出;(e) 训练/测试同分布。**高风险**:(b) 翻了则示例检索退化,D(1) 消融给出的下界是 **−25.3pp**(0.583→0.330);(c) 翻了则 0.937 不成立,参照 MultiTQ 换 linking 即 −13.2pp,无标注的真实库更差;(a) 翻了则整条自举监督链失效。

**方法** — 明说:两阶段(ICL 生成草稿 → linking → 执行);Table 1 的 12 个时序算子;gold answer 弱监督迭代自举;LoRA rank 8。**未明说但实际依赖**:(a) **非空交集即判对**,配合 post-processing 过量生成候选,是最宽松的正确性判据——返回 {A,B,C} 而金标 {A} 也计对,**这直接就是 spurious program 的来源**;(b) **Table 1 的 12 个算子不是实际实现的算子**:A.1 明写 FilterFirst/FilterLast 各被拆成 Time/Event 两版即实际 14 个,而 Table 9/10 标注程序里用的正是 FilterFirstTime/FilterFirstEvent/FilterLastTime/FilterLastEvent——**这四个名字未出现在 Table 1**;§3.2 正文只点名 11 个(GetDuration 只在 Table 1 出现)。**三处口径不一致(正文 11 / 表 12 / 实现 14)**;(c) 基础 KoPL 函数(Find / Relate / QueryRelationQualifier / What)才是程序词表主体,时序算子只是增量,论文从未列举基础函数数量;(d) Algorithm 1 line 5 的 `while |F^t_i| ≥ C **or** i < Max` 与 §3.3.4 正文逻辑相反,且 C 与 Max 的取值从未给出。

**任务** — 未明说但实际依赖:(a) 输出是**答案集合按 Hits@k 排序**,不需要生成自然语言、不需要唯一答案——因此过量生成是"免费的召回红利";(b) 不存在假前提题、不存在不可答题;(c) 库是静态的、**无取代/失效语义**,FilterLast 取的是"时间最晚的 fact",不是"最晚生效的值"。**高风险**:(a) 翻了(要求唯一答案)则 post-processing 从 Hits@10 +8.0pp 的红利变成 Hits@1 −4.6pp 的纯损失——作者自陈 Equal Multi 类已因此垮:"the selected r relations in the linking module generate redundant answers, thereby reducing the performance on Hits@1"(§4.2 逐字);(c) 翻了则 FilterLast 语义与"当前有效值"分离。

**实验** — 明说:三类五个基线;vicuna-13B;2×RTX3090;MultiTQ 6 例/CronQuestions 8 例、每题 1 份草稿;MultiTQ **不开** PP、CronQuestions **开** PP。**未明说但实际依赖**:(a) Table 2 的 Prog-TQA 行与 Table 6 的 **Llama-13B** 行**逐位相同**(0.797/0.750/0.817/0.934/0.910/0.944),而 Vicuna-13B 行是 0.793/0.748/0.811/0.930/0.912/0.937——主表很可能用的是 Llama-13B,与 §4.1 不符;(b) Table 2 **缺 TempoQR 与 TMA**,两者在 §4.1 被列为基线却只出现在 Table 3,论文未解释;(c) **无 LLM 直读 / CoT 基线,无闭源 LLM 基线**(§1 以 ChatGPT 举例却从不跑);(d) 无任何方差/CI/检验,Table 7 明确对 5 个 2000 题子集取平均**却不报 std**;(e) **零成本测量**——无延迟、无 LLM 调用次数、无 token 量;"cost" 只作为限制自己实验的理由出现两次。

**应用** — 未明说但实际依赖:部署方已拥有干净规范化的四元组 TKG;能提供约 10 万条带答案的同分布训练题;用户容忍 top-10 候选;有 GPU 做 LoRA。**高风险**:前两条同时翻掉才是"对话记忆"这类场景的真实条件——**这正是 QVF 的地盘**。

#### C 真实创新点

- **C1**:求解范式整体替换——从"问题/答案嵌入相似度打分"改为"LLM 生成算子程序 → 对齐到库 → 符号执行"。
- **C2**:(i) 12 个时序算子扩 KoPL(比较 before/after、序数 first/last、粒度 GetYear/Month/Date、粗粒度 FilterRange、格式 FilterByTimePoint/FilterByDuration、GetDuration、QueryEventQualifier);(ii) linking 的**骨架抽取 + 句向量选 top-k 事实缩小链接候选**,并把三元组拆成两个实体-关系二元组以免"另一个实体的语义干扰单实体问题的检索"(§3.3.2);(iii) gold answer 弱监督的**迭代**自举,失败题池 F^f 被下一轮模型重试;(iv) 简化 KoPL 序列化格式(`<i>` 文本参数 / `<d>` 函数依赖索引,Figure 7)。
- **C3 机制**:组合时间约束一旦被写成算子序列,"定位参照时间点 → 按 before 过滤 → 按 last 排序"变成三个独立可执行步,不再互相干扰;且时间戳成为一等输出对象,绕过嵌入法输出空间里没有时间戳这个结构性缺陷(EmbedKGQA time Hits@1 = 0.001 是这一机制的反面证据)。自举有效的机制是:执行器提供了一个**免费的、可自动判定的**正确性代理(结果∩金标),把"没有逻辑形式标注"转化成"有大量弱标注"。
- **C4**:**技术为主,工程为辅,概念含量低**。算子设计是无形式化内容的题型学表格,且作者明写 "these operators can be flexibly extended according to future requirements"(§3.2)——**显式声明是开集,不声称完备或最小**。
- **C5 分界句**:vs **KB-BINDER**——分界不在"用 ICL 生成逻辑形式"(那是 KB-BINDER 的),而在(i)为时序约束新增算子、(ii)用执行结果∩金标做弱监督**反过来微调**生成器。vs **Huang et al. 2023**——监督信号从 self-consistency 换成 gold answer,且强调**迭代**重试失败题池(作者 §2 自己这么划的)。vs **SF-TQA / TEQUILA**——不用预定义结构模板、不依赖大量逻辑形式标注。

> **判决 C:新意 中。** 首个把 TKGQA 做成"LLM 生成算子程序 + 符号执行 + 自训练闭环"的工作,linking 模块与迭代自举是实质的机制级构造;但四个组件各有前例,算子设计本身零形式化内容且自认开集,新意在于组合与到时序域的落地,而非任何单点。

#### D 实验支持度

| 核心结论 | 支持等级 | 依据 / 缺口 |
|---|---|---|
| MultiTQ 上程序化范式大幅优于嵌入范式 | **直接支持** | Table 2,54,584 题,+50.4pp overall / +59.1pp multiple |
| 自举策略有效 | **直接支持** | Table 4:+21.4pp overall、+37.1pp multiple;Figure 4 逐轮曲线(图内数值未核实) |
| linking 模块有效 | **直接支持** | Table 4:+13.2pp Hits@1 / +4.3pp Hits@10(对照是真实对手实现) |
| 示例数量重要 | **直接支持** | Table 4 D(1):−25.3pp |
| post-processing 换召回损精度 | **直接支持(诚实的负结果)** | Hits@1 −4.6pp、Hits@10 +8.0pp;作者据此只把 PP 用在自举的候选过量生成里 |
| LLM 参数量不是决定因素 | **间接支持** | Table 7(w/o SI + w/ PP,5×2000 题子集平均):7B 0.516 / 13B 0.529 / 33B 0.530;13B→33B 的 Multiple 反降 0.346→0.331。但换的是 scale 不是 architecture |
| 设计的时序算子有效 | **缺关键消融** | 无任何一行消融算子集,唯一支撑 Figure 1 定性对照 |
| 增益来自"程序化"而非"引入了 LLM" | **缺关键 baseline** | 五个基线全是 2019–2023 嵌入/LM 方法(最强 0.293),无 LLM 直读、无 CoT、无闭源模型 |
| 自举降低 spurious program 率 | **不足支持** | Table 5:7.5%→4.0%,每轮**仅 200 个人工判样**。我方 Wilson 95% CI 分别 [4.6%,12.0%] 与 [2.0%,7.7%],**重叠**;两比例 z = 1.50(p≈0.13),不显著。论文却写 "attests to the effectiveness of our proposed self-improvement strategy" |

**指标口径的有利选择**:MultiTQ 三个头条数(50.4/47.0)是**绝对百分点**却写成 "%",而 CronQuestions 的 "2.1% relative improvement" 是**真相对值**(0.019/0.918 = 2.07%)——同一篇论文两套口径,绝对口径给出的数字大一个量级。内部算术亦不自洽:文本 "60.9% improvement on multiple-constraint" 与表内 **59.1pp**(0.750−0.159)不符;贡献列表的 "3.5%" 与绝对 3.4pp / 相对 3.9% 都不精确吻合。

> **判决 D:部分支持。** MultiTQ 的 +50.4pp 在 5.5 万题上不可能是噪声,且消融把 SI/linking/示例数/PP 四项都测了并诚实报告 PP 的负结果与自举分布塌陷;但一号贡献零消融、无任何 LLM 直读基线、增益未按答案类型分解、CronQuestions 绕过 linking、Table 5/7 无方差——核心机制归因的关键对照均缺位。

#### E 反例(8 条)

1. **依赖 top-5 事实检索命中**。骨架抽取会删掉疑问词、停用词和时间词,"Who visited China in the same month as X" 剩下的语义极短;实体名同形、关系近义的库上 cosine top-5 会崩。论文**从未报告 linking recall@5 或检索覆盖度**,退化幅度不可知——而 QVF 在 S8 上已实测同类问题(必需证据完整仅 297/418 = 71.1%)。
2. **依赖每题存在非空 gold answer 且 `r ∩ GA ≠ ∅` 可判对**。假前提题的金标是"前提不成立":任何返回非空结果的程序被判错,返回空的程序也无法被判对——**自举的监督信号在该题型上归零**,而 SI 正是 +21.4pp 的来源。
3. **依赖 12(实际 14)个算子对目标题型充分,且题目自带 category 标签**。算子集是按 MultiTQ 6 题型 + CronQuestions 4 题型倒推设计的。开放提问场景里既没有可分类别(§3.3.1 的同类示例检索直接失去标签、退化为随机示例),也没有对应算子;而 D(1) 显示示例质量值 **25.3pp**。
4. **依赖约 10 万条带 gold answer 的同分布训练题**。每个用户的对话记忆库是私有且一次性的,不存在这样的训练集;去掉 SI 后 multiple 类从 0.750 掉到 0.379(**−37.1pp**)。
5. **依赖库为给定且实体/关系已规范化,无版本演化**。Prog-TQA 无取代边概念,FilterLast 取"时间最晚的 fact";而对话记忆中"最晚陈述"≠"最晚生效"(用户追溯修正时二者分离),该算子会系统性给出错误的当前值。
6. **依赖过量生成 + Hits@k 排序指标**。候选膨胀在 Hits@10 下是红利,在必须输出唯一答案的部署下是纯错误(作者自陈 Equal Multi 类因此垮,w/ PP 使 Hits@1 −4.6pp)。任何需要"说人话给一个答案"的应用吃不到 Hits@10 的 0.934。
7. **依赖自举中难易题分布不塌陷**。作者自陈 CronQuestions 后续轮次不再提升,因为 "the proportion of simple questions is too large for Prog-TQA to learn about the reasoning of complex ones"(§4.4)。长尾复杂题占比更低的真实分布下,增加轮数会进一步稀释复杂题信号,自举反而有害。
8. **依赖执行器与库 schema 完全一致**。CronQuestions 需要 QueryEventQualifier 这个"dataset-specific operator";换 schema 就要重新设计算子并重新标注 20/类示例,迁移成本未被测量。

#### F 审稿人视角

| 查项 | 结论 |
|---|---|
| 问题重要性 | 强。多约束题的 0.159 天花板是真实卡点 |
| 创新性 | 中。组合式创新,单点均有前例 |
| 方法清楚 | 基本清楚,但两处自相矛盾 + 两个未给的超参(C、Max) |
| 实验充分 | 消融覆盖四项且报负结果,但缺一号贡献消融与 LLM 直读基线 |
| baseline 公平 | 数据上公平,但**代际不公平**(全是前 LLM 时代方法);§4.1 列的 TempoQR/TMA 未进 Table 2 |
| 结论夸大 | 有。绝对 pp 写成 "%";摘要只提 Hits@1 不提 CronQuestions 的 Hits@10 净负;"few-shot" 掩盖 100k 弱标注 |
| 可复现 | 中偏低。无代码链接;主表基座模型与 Implementation Details 不符;C/Max 缺失 |
| 逻辑跳跃 | Table 5 从 n=200 的 7.5%→4.0% 直接断言自举有效 |

**主要 1:一号贡献从未被消融。** *作者回应*:Figure 1 已定性说明 SPARQL 需多子句;且没有这些算子程序根本不可执行,消融不可构造。*能否成立*:**部分成立但不足**。至少两个可构造对照:(a) 让同一 LLM 直接生成原生 KoPL 或 SPARQL 并执行,报执行通过率与 Hits@1;(b) 逐类算子留一——去掉 FilterFirst/FilterLast,只用 FilterBefore/FilterAfter 组合表达序数约束,看 First/Last、Before Last、After First 三类崩多少。二者都在其算力内(2×3090 已跑完全量测试集),"不可构造"不成立。

**主要 2:无任何 LLM 直读基线,无法区分增益来自"程序"还是"引入了 LLM"。** *作者回应*:领域惯例基线就是这些;且 Table 7 显示 7B/13B/33B 差异极小,说明不是 LLM 在起作用。*能否成立*:**在关键处不成立**。Table 7 变的是 **scale 而非 architecture**,三档全都仍在 Prog-TQA 管线内跑——它只证明"不是更大的 LLM 在起作用",不能证明"不是 LLM 本身在起作用"。缺的那一臂复用现成检索与现成模型,构造成本近乎为零。**这是本文最硬的伤。**

**主要 3:增益的答案类型结构未被披露。** *作者回应*:时间答案题本就是 TKGQA 的正当组成部分;Hits@1 更严,Hits@10 小幅落后可接受。*能否成立*:**前半成立,后半在披露层面不成立**。问题不是优势不正当,而是**归因未分解 + 摘要选择性披露**;补一张按答案类型切分的题量表与分解表几乎零成本。

**次要 1**:Table 4 caption("'w/' means removing the module and 'w/o' means adding the module")与 §4.3 正文恰好相反,caption 自身也与 "Prog-TQA w/ SI" 不一致。*回应*:笔误。→ **成立**(camera-ready 可修),但增加复现成本,审稿时会被当作校对不严的信号。
**次要 2**:主表所用基座模型与 Implementation Details 不符(见 B 实验 (a))。*回应*:差异仅 0.4pp,不影响结论。→ **"结论不受影响"成立,但"Implementation Details 写错了主表用的模型"不可辩护**。
**次要 3**:统计量全缺。*回应*:主表差距 +50.4pp,显著性不言自明。→ **对主表成立,对 Table 5 与 Table 7 不成立**:前者是支撑"自举有效"的核心证据之一而 n 仅 200,后者的 5 次重复已跑完、报 std 零成本。

> **判决 F:弱接受。** 问题真实、机制清楚、主结果幅度巨大且消融相对完整,对 PP 的精度-召回权衡与自举的分布塌陷都诚实披露,足以进 LREC-COLING 这一档;但缺 LLM 直读基线与算子消融是硬伤——**若投 ACL 主会,同样的稿子应为弱拒**。

#### G 五个扩展方向

**G1 算子集的最小充分性:把题型学表格变成结果。** 问题:一个时序算子集需要多大才够?能否证明某个**闭集**对给定题型学是充分的?值得做的理由:Prog-TQA 把"可按需扩展"当优点写,等于承认没有闭集论证;整条 TKGQA 语义解析线至今没人给过"算子数 vs 可解题型覆盖率"曲线。做法:在 MultiTQ 6 题型 + CronQuestions 4 题型 + TempReason L1/L2/L3 + TimeQA 上做 leave-one-operator-out 与最小覆盖搜索,给出每题型的最小算子子集,画覆盖率曲线。难点:需每题金标程序或可判定的执行等价性;子集组合爆炸;**Prog-TQA 无代码,须自实现 KoPL 时序扩展**。
**G2 符号执行 vs LLM 直读的判定边界。** 问题:在什么条件下"编译成算子计划再执行"胜过"把检索到的事实直接给 LLM 读"?值得做的理由:F 主要 2 指出这一臂在整条线上缺失,而 QVF 在 S8 上恰恰被直读反超(直读 70.1% vs 平面臂 52.2%)——这条曲线是"何时该用符号执行"的判定依据。做法:固定同一模型与同一 top-k 检索证据,构造三臂(直读 / CoT 直读 / 程序执行),沿三轴扫:证据条数、需聚合的事实数、组合约束深度,找交叉点。数据:MultiTQ 多约束子集 + TimelineQA(其崩塌曲线现成)+ QVF 的 S8。难点:两臂检索证据必须完全一致才可比;**直读臂的提示词强度是混淆变量(QVF 自审已量化到 +5.64pp,须一并控制)**。
**G3 弱监督判据的严格程度 → spurious 率 → 泛化。** 把 CheckProg 换成集合相等 / Jaccard 阈值 / 执行轨迹一致性三档,各跑 2 轮自举,报 spurious 率(人工判 ≥500 样本、给二项 CI)与留出未见约束组合的泛化。难点:严格判据会使 F^t 骤减、可能不足以微调,须与数据规模做交叉设计。
**G4 防止自举被简单题淹没。** 在 F^t 上做难度分层重采样 / 只保留上一轮失败题的新解 / 按题型逆频率加权,对比朴素自举在 MultiTQ multiple 类与 CronQuestions complex 类上的逐轮曲线。难点:C 与 Max 论文未给,须自定并报敏感性;难度标签只能用题型或"首轮失败"做代理,后者有选择偏差。
**G5 把算子-执行范式接到在线抽取且带取代边的库上。** 问题:性能损失来自抽取噪声还是算子语义不匹配?做法:用 QVF 写入侧从 LoCoMo / LongMemEval 抽卡片,整形为四元组喂 Prog-TQA 的执行器,与 QVF 自己的执行器对比;再做两个隔离对照:(i) 金标卡片(隔离抽取噪声),(ii) 给 Prog-TQA 加 supersession-aware 的 FilterLast 变体(隔离算子语义)。**这是把档案里那句分界句("库来源 given vs 对话在线抽取")从措辞变成实验的最直接做法。** 难点:无代码;"时间最晚事实"与"最晚生效值"的对齐需重定义评测金标。

#### 三条判决(Prog-TQA)

- **C 新意**:**中**
- **D 实验支持**:**部分支持**
- **F 审稿倾向**:**弱接受**(投 ACL 主会应为**弱拒**)

---

### 3.3 TimelineQA

> **TimelineQA: A Benchmark for Question Answering over Timelines**
> Tan, Dwivedi-Yu, Li, Mathias, Saeidi, Yan, Halevy(Meta + Cornell)
> arXiv:2306.01069 / ACL Anthology 2023.findings-acl.6 | **Findings of ACL 2023, pp. 77–91**
> 阅读层级:**全文级**(官方 PDF `pdftotext -layout` 抽出 917 行,含 §1–§7、附录 A(Table 8/9)、附录 B(全部超参)、附录 C(Table 10)、ACL 2023 Responsible NLP Checklist;Table 6 两侧分桶各自加总 = 4,284 = 测试集全量,校验通过)。

#### A 究竟要解决什么问题

**A1 作者声称**。lifelog 对它做问答"超出了当前问答技术的水平(beyond the current state of the art)",最突出的原因是"lifelog 把自由文本与某种程度的结构(时间与地理信息)结合在一起"(摘要)。贡献声称异常克朴,只有一句:**"Our main contribution is a benchmark for QA systems over lifelog data of different sizes."**(§1)另有三条辅助声称:
- §3.2:希望基准推动"结构与语言在问答中交互的极限",并能变动"问题的复杂度、lifelog 的大小与内容、lifelog 中的数据类型";
- §3.2 关于时序(**最关键**):"Reasoning about such temporal relations is an area of weakness for QA algorithms today. This aspect of query answering is critical to lifelogs and **therefore we design our benchmark to evaluate these challenges.**"
- §1:当前 SOTA 远达不到足够性能;"somewhat surprisingly,即使在微调之后,生成式 RAG 仍落后于抽取式";最优系统 Tapex 只有 59.0%,"且假定计算答案所需的 episode 子集是已知的"。

**A2 实际做成的**:
1. 参数化 lifelog 生成器:persona(18–75 岁、性别、教育与职业史、家庭、偏好)→ 按 lifetime/annual/monthly/weekly/daily 五个时标生成 episode(Table 1)→ super-episode 嵌套 sub-episode → 互斥约束保证一致性(旅行期间不生成年度牙检)。产出 3,000 个 lifelog / **128,023,476** 条记录 / 平均 **8.40** token/条(Table 2),覆盖 25 类事件(Table 9)。
2. 金标由**符号计算**产生:"the process of creating begins by creating a logical representation of the episodes"(§4.1.1),复杂题"The answers are computed by applying external algorithms (e.g., **SQL queries**) over the timeline"。
3. 问题分类学(§3.1):atomic / complex-multi-hop / complex-aggregate,加一条横切的 temporal;基于 7 人众包约 600 题、归并为 13 个主题(Table 8)。
4. 两组基准实验:
   - **Atomic QA(Table 4,DPR+FAISS top-5,reader = roberta-base-squad2)**:Extractive FT **82.6** EM / 93.8 F1;Extractive OR 83.3/94.8;Extractive ZS 24.1/47.3;RAG FT **40.3**/57.5;RAG OR 73.7/84.4;RAG ZS 8.4/32.9。
   - **Multi-hop QA(Table 5,denotation accuracy)**:Tapex-large(400M)OR-retriever 微调后 **59.0**,ZS reader 6.5;FT-retriever 32.7;ZS-retriever 33.0。Tapex-base(140M)57.7/30.8/30.7。Bart-base OR 54.4,**Bart-large OR 47.0**。附录 C:InstructGPT 175B 在 100 题抽样上 OR 33.0 / FT 25.0 / ZS 18.0。
   - **误差分析(Table 6,Tapex-large 微调 + oracle retriever)**:按题型 average **11.1**(n=360)/ count **75.9**(n=1,776)/ argmax **47.2**(n=1,668)/ list **62.7**(n=480);**按证据集规模 [0,10] 85.1(n=1,949)→(10,100] 52.5(n=1,275)→(100,1000] 19.2(n=689)→ >1000 4.3(n=371)**。

**声称了但没被测的**:
- **时序关系推理**。§3.2 明说 "therefore we design our benchmark to evaluate these challenges",§3.1/§4.1.1 举了 "Did I go to Spain before Italy?"、"How long was my break between leaving my last job and starting my current job?" 等模板。但 Table 6 的题型分桶只有 average/count/argmax/list 四类,**四类 n 加总 = 360+1776+1668+480 = 4,284 = 测试集全量**——即 before/after 序关系、区间 join(intro 招牌例子"where did I take my mom when she visited Seattle")、跨 episode 时长差,**在 multi-hop 测试集里根本没有生成**。公平起见:first/last 类可能被 argmax 桶吸收(47.2%),所以"时序完全没测"是过头话;**准确说法是只有"时间维取极值"这一族被测了,序关系与区间 join 两族被声称为设计目标却缺席**。
- **密度作为实验轴**。§3.2 把"lifelog 的大小与内容"列为可变动变量,Table 2 整个围绕 sparse/medium/dense 三分构建,测试集也是"每种密度均匀采样 40 个 log"(§5.1)——但 **Table 4/5/6 没有任何一行按密度拆分**,120 个 log 的结果全部池化。**设计好的旋钮从未被拧。**
- **"结构与语言的交互"**。§3.2 提出词汇错配挑战(用户问"和朋友喝酒",日志写"晚饭前去了酒吧"),随即自我豁免:"this is not a focal point of our benchmark"。

**A1–A2 落差(三条)**:这篇的摘要与"main contribution"一句话是同类基准论文里最诚实的之一(头条数字自带最重的限定词),落差集中在 §3.2:
1. **§3.2 声称"因此我们设计基准来评测时序关系挑战"vs Table 6 四个题型桶中没有序关系与区间 join。** 这是最实的一条,因为时序性是全文的立论前提。
2. **§3.2 声称基准可变动 lifelog 大小与内容 vs 全文零条按密度拆分的结果。**
3. **§1 把"RAG 落后于抽取式"称为 "somewhat surprisingly",§5.2 同一现象改口为 "which is to be expected, given the benchmark construction, where the answers are always a valid span in the input for atomic queries"。** 同一篇论文里 intro 当成发现、方法节当成构造产物。**后者才是对的**——这条"发现"是基准的人工制品,不是关于抽取式/生成式问答的科学结论。
另有一条**未在摘要中披露的双重 oracle**(见 B2 与 F 主要 1)。

**A3 领域位置**:**开辟新问题**。上游:Memex(Bush 1945)/ MyLifeBits(Gemmell 2006)的 lifelog 愿景;CLEVR(Johnson 2017)提供"设计可控问题空间 + 合成数据 + 已知金标"方法论(作者明确承认 "The design of our benchmark was inspired by the Clevr benchmark",§2);Neural Databases(Thorne 2021)是最近邻,作者分界句为 "it does not address the temporal aspects that are critical to queries over lifelogs"(§2)。下游:LoCoMo(ACL 2024)、LongMemEval(ICLR 2025)、2026 年的双时态记忆库一族,但**继承的是"个人时间线聚合很难"这个论断,而不是这个基准本身**——它的下游用途是"被当作难度的引证",而不是被当作 leaderboard 刷分(要用它必须跑生成器、微调 2023 年代的 1024-token reader,门槛与收益不匹配)。零方法创新(所有 reader 与 retriever 都是现成 checkpoint)。

**A4 若无此文,已有方法卡在哪**(不能写"效果不够好"):**卡点的根因是标注经济学,不是模型能力。** 人工标注一道题的金标,成本随该题所需证据条数增长;因此所有人工标注的问答基准都被**隐式地钉死在小证据集区间**——没有众包工人能标出"过去若干年里我平均每天和朋友聊了多少分钟",而这道题在 Table 7 第一行需要聚合 **74k 条记录**(金标 84.05,Tapex 预测 83.94)。后果是:整个领域报告的数字都采样自 ≤10 条证据的区间,而同一个系统在该区间的成绩是 **85.1%**。**失效模式在 ~100 条证据之后才出现,而它在结构上不可观测。** 代表性前人状态:Neural Databases 能做文本聚合但没有时间维;TempQuestions(WWW 2018)只有 1,271 道纯时序题且全是维基世界知识;两条线都无法生成一道"需要跨千条记录求均值"的题并知道答案。TimelineQA 用符号金标切断了"题目难度 ∝ 标注成本"这条耦合,于是把悬崖测出来了:**一个 400M 参数、已微调、且配备完美检索器的 table-QA reader,随金标证据集从 ≤10 条增长到 >1000 条,准确率从 85.1% 退化到 4.3%;根因是序列化后的证据超出 reader 的 1024-token 输入窗(§5.1 报告测试集整体 20.40% 输入被截断),叠加算术能力本身的薄弱(average 题型全局仅 11.1%)。**

**A5 一句话真实问题意识**:作者真正害怕的失败模式是:**整个领域会在"短上下文、少证据"的题上宣布个人记忆问答已被解决,却永远看不见同一批系统在答案需要跨千条记录聚合的那一刻掉到个位数——所以他们造了一台能无限量生产"金标只能由符号计算得到"的题的生成器,目的是让这道悬崖无法被回避。** 这也解释了为什么他们把最重的限定词写进摘要而不是藏进附录:他们要的是这个负结果站得住,不是要一个高分。

#### B 隐含前提

**B1 数据** — 明说:合成、虚构、无真人信息(§7);模板化描述缺乏语言多样性;多样性只覆盖 "age, gender, locations, professions" 且 "do not claim that they represent a diversity in any social sense"(§4);episode 是推理后的产物,从原始数据抽 episode 明确出界(§3 "Our work concerns question answering after the inference of episodes has been done");"far from representing the full range of human experiences"(§7)。**未明说但实际依赖**:(a) episode 到达过程是手设的、平稳的概率流程——density 旋钮只按比例放大 daily/weekly/monthly 的生成概率,它缩放速率,**不产生突发性**;真实时间线是丛聚的(三周旅行,然后半年空白),而这里证据集规模分布由构造而平滑,**Table 6 右列那条漂亮的单调曲线,一部分来自这个平稳性**;(b) 分类学的经验基础是 7 个人对着"自己**潜在的** lifelog"写题(§3.1 逐字 "their **potential** lifelogs"),他们并不拥有一份真实的 20 年日志;(c) 单一类目支配语料——chat 占 40.76M / 128.02M ≈ **32%**(Table 9);(d) 复杂题的问题空间只有 **42 个模板**("we created **42 complex questions** in our benchmark for the subset of categories we have implemented",§4.1.1),每个 lifelog 实例化 35 道,**训练集 8,586 题与测试集 4,284 题共享这 42 个模板,只换 lifelog**;(e) 写读对齐是构造性完美的(atomic 答案永远是输入中的合法 span);(f) **单调追加,没有任何事实会失效**——一致性只靠互斥约束,没有 supersession,没有一个模板问"现在",没有一道假前提题。
**高风险**:**(f) 是全篇最高风险的一条。** 它不影响任何一道现有题的正确性,但把结论的适用对象从"个人记忆问答"悄悄换成"**追加式、内部自洽的日志上的问答**"——后者严格更容易。直接后果:**一个永远用过期值回答的系统,与一个完美处理过期的系统,在 TimelineQA 上得分完全相同。** **(d) 次高风险**:若把 42 个模板做留出划分,59.0% 极可能向 6.5%(零样本)方向大幅回落;这**不会**推翻负结论(59% 本就不及格),但会推翻**比较性正结论**("Tapex generally outperforms BART, which indicates the importance of understanding structured data",§5.3)——而这恰是后来者会引用的那句。

**B2 方法(= 生成器 + 评测仪器)** — 明说:金标由 logical representation 上的 SQL 计算;table QA 的表由信息抽取管线构建,"**By exploiting the topics (e.g., medical care, chat, exercise) which are known to the generation pipeline**, we define a fixed schema for each topic",自评 "This simple pipeline works very well (**near perfect**)",紧接着承认 "For real-life lifelog data, additional challenges such as episode construction, topic/attribute discovery, and schema reconciliation, are **beyond our current scope**"(§5.3,皆逐字);最大输入 1024 token,**20.40% 测试输入被截断**(§5.1)。**未明说但实际依赖**:(a) denotation accuracy + 精确匹配,默认了生成器的 SQL 语义是自然语言聚合的唯一正确算子化——一个把 0 分钟 chat 条目从"平均聊天时长"里合理排除的系统得 0 分,**59.0% 里混着"算错"与"语义口径不同",无任何消融分离**;(b) multi-hop 的"零样本检索器"根本不是检索模型:"A zero-shot retriever uses a set of **user-defined patterns** such as 'I talked to X for Y minutes'"(§5.3),即规则匹配,而 FT-retriever 是微调的 SentenceTransformers——**因此 ZS-retriever 33.0 vs FT-retriever 32.7 是"规则 vs 嵌入"的比较,不是同一检索器两种设置的比较**,而作者在此基础上写下 "fine-tuning the retriever generally does not improve the QA performance";(c) **全文从未报告任何 retriever 的 recall@k**,于是 §5.3 的归因是断言不是展示;(d) atomic QA 固定 top-5,该超参从未扫过;(e) 微调检索器的负例是"跨 episode 类目随机采样",标注为 "guaranteed hard negatives",但**跨类目负例对 count 类题恰恰是易负例**——count 题真正的混淆项是同类目内的邻近条目。
**高风险**:**(a)**。若金标语义可争议,那么 59.0% 混合了计算失败与口径失配,而真实数据上并不存在这样一份 SQL 金标——**评测仪器本身不可迁移**。

**B3 任务** — 未明说但实际依赖:(a) 每道题都恰有一个可从日志计算出的正确答案,没有不可答题、欠指定题、假前提题;(b) 提问者与日志的词汇一致;(c) 不存在"提问时间"这个变量;(d) 属主无歧义(episode 可以属于家人,"who was involved" 是一个属性,但**没有一道题测"把某事实归错到某人"**);(e) 无澄清轮。**高风险**:**(a)**。在 TimelineQA 上最优的系统没有任何激励去说"我不知道"或"你的前提不对"——而这恰是助理记忆在真实世界里的主导失效模式。**部署一个 TimelineQA-最优的系统,等于最大化自信的错答。**

**B4 实验** — 明说:超参全在附录 B;25.4 A100 GPU 小时;三种检索器条件。**未明说但实际依赖**:(a) **每格单次运行,无随机种子,无置信区间**,却据此下了比较性结论(Tapex-large 59.0 vs Tapex-base 57.7 相差 **1.3pp**;"Tapex > BART" 的最强同规模对照是 57.7 vs 54.4,+3.3pp);(b) 默认 reader 规模轴单调,而数据反着走——**Bart-large 47.0 < Bart-base 54.4**(差 7.4pp),全文**零字评论**,这条反向缩放直接削弱"理解结构化数据很重要"这个由规模/预训练差异支撑的叙事;(c) 测试集按密度均匀采样 40×3 却池化报告;(d) **Responsible NLP Checklist C3 项(描述统计/误差棒)填 "Section 5",而 §5 中不存在任何误差棒或方差**;(e) 附录 D(人类标注者)整节 "Left blank / No response",而 §3.1 明确使用了 7 位人类贡献者写题、附录 C 由作者 "manually checking" 人工判分。**高风险**:**(a)+(c)**。若密度与系统存在较大交互,池化会把它藏起来,那么 Table 6 那条头条曲线可能是三条形状颇不相同的曲线的平均——而全领域引用的正是这条平均曲线。

**B5 应用** — 明说(异常自觉):"should not be used to train models for making key decisions that will impact people's lives (e.g., job matching, insurance approvals or building personal assistants)";预期用途仅为 "reveal potential limitations of QA systems"(§7)。**未明说但实际依赖**:(a) 8.4 token 的模板化条目上的结论可迁移到真实多模态、冗长、歧义的 episode 文本;(b) **固定窗口 reader 是正确的分析单位**——全篇难度轴是相对 1024 token 定义的,结论被索引到 2023 年的一种架构上,**而论文没有这样框定它,论文把它报告为任务的性质**;(c) 无需与用户交互。**高风险**:**(b)**,这是真正随时间老化的那一条:**悬崖在 x 轴上的位置是 reader 上下文窗口的函数,而论文把它当作任务的属性来汇报。**

#### C 真实创新点

- **C1**:改的是**评测对象与难度轴的定义**,不是表示/检索/训练目标/推理流程(这四项一个都没动)。具体两处:(i) 把"**证据集基数**"提升为一等难度轴(此前问答难度按 hop 数、推理类型、上下文长度切);(ii) 把金标生成从人工标注换成符号执行,解除"题目难度 ∝ 标注成本"的耦合,使前一条轴在 10³ 量级上可测。
- **C2**:零建模、零训练创新。数据处理与评估侧:参数化 lifelog 生成器(persona → 五时标 → super/sub 嵌套 → 互斥约束一致性,duration 与 density 两个旋钮,25 类事件,128M 条);金标由 logical DB + SQL 计算,复杂题 42 条模板;**三档检索器条件(OR/FT/ZS)作为统一评测协议**,把"检索失败"与"阅读失败"分开——这个协议本身是可复用的方法学贡献,且被用得比多数论文严格(oracle 行让 Table 6 的悬崖成为纯 reader 侧证据)。
- **C3 机制**:不是"实验涨了"——这篇论文没有任何数字上涨。机制是:**人工标注的边际成本随证据条数超线性增长,而符号执行的边际成本随证据条数近似恒定。** 因此把金标产生从人搬到 SQL,唯一改变的是"可被生产的题目分布"的支撑集扩张到了大证据集区间。在旧支撑集上同一系统得 85.1%,在新支撑集尾部得 4.3%——这个 80.8pp 的差是被**标注经济学**而非模型能力遮住的。
- **C4**:概念层小而真("证据集基数是个人时间线问答的主导难度变量"成立);技术层无;工程层中等偏实(生成器 + 128M 条 + 600k atomic / 4,284 multi-hop 测试题 + 开源 `github.com/facebookresearch/TimelineQA` + 25.4 GPU 小时全披露);方法论层是**借来的**(作者自承来自 CLEVR)。
- **C5 分界句**:vs **Neural Databases**——作者自己给了("does not address the temporal aspects"),可判定:Neural DB 的查询里没有时间轴与区间语义,TimelineQA 每条 episode 强制带 start/end time 与 start/end location。vs **CLEVR**——方法论同源,分野在难度轴:CLEVR 的难度轴是**组合深度**且提供了 CoGenT 组合泛化划分,TimelineQA 的难度轴是**证据集基数**且**没有**提供任何模板留出划分。vs **TimeQA / TempQuestions**——前者是维基/Freebase 上的第三人称世界知识时序问答、量级 10³ 题,证据集几乎恒为个位数条,**不可能观测到基数悬崖**。vs **Memento 2.0 / LSC**——真实 lifelog、图像模态、任务是**检索**;TimelineQA 是合成、文本、任务是**问答与聚合**(被引但未用于校准生成器统计量)。

> **判决 C:新意 中(偏弱)。** 概念上确有一条成立且此前不可观测的新命题,并给出了使其可观测的机制;但方法论范式借自 CLEVR、聚合-over-文本借自 Neural Databases、时序问答借自 TempQuestions 一族,建模与训练侧创新为零;且**最有分量的那条设计——logical DB + SQL 算金标——只被当作 oracle 使用,从未被当作系统评测**,即作者手里握着最有意思的那个方法却没有把它做成贡献。判"中偏弱"不是贬低:这是一篇资源+诊断论文,它的价值在别处,而它在自己声称的位置上是诚实的。

#### D 实验支持度

**直接支持**:C1(atomic 抽取式远优于 RAG)← Table 4 差 42.3pp,量级远超任何合理噪声,**作为关于本基准的事实支持充分**;C3(基数悬崖)← Table 6 右列四桶 n 分别 1,949/1,275/689/371,单调,跨度 80.8pp,且是在 **oracle retriever** 下测的(§5.4 "with a perfect retriever"),**排除了检索侧解释**;C5(算术最弱)← average 11.1 / argmax 47.2 显著低于 count 75.9 / list 62.7;C4 前半 ← Extractive ZS 24.1 → FT 82.6,+58.5pp。

**只能间接支持**:C2("最优来自 table QA")——同规模对照只有 +3.3pp,Tapex-large vs base 只有 **+1.3pp**,且 **Bart 的规模轴反向**(47.0 < 54.4,差 7.4pp),无方差、单次运行,**机制归因被自家反向缩放数据削弱**;C4 后半("微调检索器无用")——ZS 行是**规则匹配**不是嵌入检索器,且全文无 recall@k;C6(微调小模型优于零样本 175B)——n=100 抽样、作者本人非盲人工判分、无一致性统计、自陈 "the numbers are not directly comparable",**最弱的一条却仍被用来推出方向性结论**。

**缺关键 baseline(最大缺口)**:**最该比而没比的,是论文自己用来算金标的那条路线。** §4.1.1 明说复杂题金标由 SQL 计算,§5.3 又构建了近乎完美的 per-topic 表——那么"LLM/语义解析器产生一个查询或计划 → 确定性执行器在这些表上执行"是显而易见的 baseline,而**它完全缺席**:没有 text-to-SQL,没有语义解析,没有任何符号执行臂。后果:论文报告的"当时的天花板 59.0%"是**一族 reader 的天花板,不是任务的天花板**;一条把 count 题化为"数检回来的行数"的朴素 Python baseline 很可能在 >1000 桶上远超 4.3%。其余缺失:BM25 等稀疏检索对照;长上下文 reader 对照(1024 上限从未被放松过一次)。

**缺消融**:按密度拆分(近乎零成本却缺席);**截断消融(512/1024/2048/无截断)——这是分离"装不下"与"算不出"的唯一手段**;模板留出划分(42 条在训练与测试间完全共享,零组合泛化划分);schema/IE oracle 消融(注入 1/5/10/20% NER 噪声);retriever recall@k;时序关系题型。

**最重的一条偏向:C3 的悬崖与输入截断混淆,论文未做分离。** §5.1 报告 20.40% 输入被截断;>1000 证据桶的题平均 1,169.8 条 × 8.4 token/条 ≈ **10k token**,即该桶几乎每一道题都有约 **90% 的证据在 reader 看到之前就被丢掉了**。对 count/average 而言,答案在输入里根本不可计算。论文把这个下降归因为 "the hardness of dealing with large input tables",**没有把"装不下"与"算不出"分开**。作为对固定窗口架构的诊断这是公平的;**作为关于"聚合推理能力"的论断则不成立**。另:**双重 oracle**——摘要只披露"金标 episode 集已知",§5.3 披露的第二个 oracle(偷看生成器 topic 标签的近乎完美 schema/IE)不在摘要里,且**贯穿 Table 5 的所有行**。

**提升是否显著**:这篇论文**没有提升要证明**。退化曲线的**存在性**无可争议(80.8pp、四桶 n 均 ≥371),但**归因**未被实验分离,且尾桶 4.3% × n=371 ≈ 16 道题正确、无 CI。上限 59.0% 作为负结果幅度足够且被双 oracle 加强。**比较性结论(Tapex > BART、规模有益)在 1.3–3.3pp 量级、单次运行、且 BART 规模轴反向,这一档不显著,论文却据此写下机制归因。**

> **判决 D:部分支持。** 两条负结论幅度足够、oracle retriever 的设计干净排除了检索侧解释,这部分立得住;但三处关键缺口未填:(i) 悬崖的**归因**与 1024-token 截断混淆,而分离它只需一次极廉价的截断消融;(ii) 最该比的 baseline——论文自己算金标用的符号执行路线——完全缺席;(iii) 数据集自身的核心设计变量(密度)从未作为结果轴出现。

#### E 反例(8 条)

**E1 换架构**:长上下文 reader / 代码执行 agent 会让头条悬崖大幅蒸发。依赖:整条曲线的 x 轴刻度是相对 **1024 token** 定义的。此时 count/list 类退化为机械操作。**净结论:该反例削弱"聚合能力"解读,不削弱"固定窗口架构在大证据集上失效"这个 2023 年诊断。**(域外对照:QO-Bench 报告长上下文 oracle 在集合交集上仅 3.9%,说明装得下也未必算得对——但交集比计数难,不能推断计数也会崩。)
**E2 换问法**:模板留出或改写会让 59.0% 向 6.5% 回落。依赖:42 个复杂模板在训练/测试间完全共享,零组合泛化划分;ZS 6.5% → FT 59.0% 的 52.5pp 跃升最简约的解释是模板拟合。**这条不推翻负结论,但推翻其正结论**("Tapex 优于 BART,说明理解结构化数据很重要")——那才是下游会引用的句子。
**E3 撤掉第二个 oracle**:真实数据上 59.0% 不可达。依赖:table QA 的表由"偷看生成器 topic"建成。此时需要 schema 发现与属性对齐,误差在 >1k 行上乘性复合。后果:**"table QA 是最优技术"这个结论在真实数据上不可检验**,而不只是数值会降。
**E4 换文本**:非模板化 episode 会翻转 atomic 题的抽取式/生成式排序。依赖:答案永远是输入中的合法 span(作者 §5.2 自承)。**82.6 vs 40.3 这个 42.3pp 的差是构造产物**,intro 称之为 "somewhat surprisingly" 是误导,§5.2 的自我更正才是对的。
**E5 引入过期**:基准对"用陈旧事实回答"完全不敏感。依赖:单调追加,无 supersession,42 个模板中**没有一个问"现在"**,零假前提题。后果:**staleness 处理率 0% 的系统与 100% 的系统得分完全相同**;在此基准上最优化,等价于最大化自信错答。(**与 QVF 命题正交且互补。**)
**E6 金标语义的唯一性不成立**:真实数据上"平均每天和朋友聊多久"存在真实歧义(哪些 episode 算"和朋友聊"?0 分钟条目算不算?跨天的算哪天?),而真实数据上也不存在这样一份 SQL 金标。后果:**评测仪器不可迁移**。
**E7 换到达过程**:突发性时间线会改变难度剖面,而 density 旋钮模拟不出来(只缩放平稳速率)。真实用户的时间线是丛聚的;突发性同时改变检索的时间局部性与聚合的桶大小方差。后果:Table 6 那条漂亮单调的曲线可能在突发性数据上变形;更糟的是**论文从未按密度拆分结果**,所以连"密度是否改变系统排序"这个更弱的问题都没有答案。
**E8 单一类目支配**:chat 占 32%。25 类事件的手设频率分布未对任何真实 lifelog 语料校准(引了 LSC 却没用于校准)。后果:>1000 证据桶里的题很可能大比例是 chat 聚合题——若如此,4.3% 描述的是"在一个类目上聚合"而非"在个人时间线上聚合"。(该桶的类目构成论文未报,此为推断。)

#### F 审稿人视角

| 维度 | 评价 |
|---|---|
| 问题重要性 | 高。2023 年中即把个人时间线问答定义为可测对象,早于 agent-memory 基准爆发 |
| 创新性 | 中偏弱。资源 + 诊断;方法论借自 CLEVR;零建模创新 |
| 方法是否清楚 | 生成器 §4 描述相当清楚,超参全在附录 B,代码数据开源。**但** logical representation 无形式化定义;42 个复杂模板未枚举(只给 4 例);约束语言未规范;per-topic schema 未列全 |
| 实验是否充分 | 薄。4 个 reader + 1 个 LLM,3 档检索器,单次运行,无 CI,无按密度拆分,无截断消融,无模板留出,无 recall@k |
| baseline 是否公平 | 以一种罕见的方式不公平:table QA 独享一条"偷看生成器"的近乎完美 IE 管线,而其他臂没有;同时**最自然的 baseline(text-to-SQL / 符号执行)完全缺席** |
| 结论是否夸大 | 摘要与"main contribution"一句话**异常诚实**。夸大集中在三处小地方:§3.2 时序声称未兑现;§1 的 "somewhat surprisingly" 被 §5.2 自我否定;摘要漏披露第二个 oracle;Checklist C3 声称 §5 有描述统计而实际无 |
| 可复现性 | 良。开源仓库、完整超参、GPU 小时、checkpoint URL 均给出,明显强于同期同类 |
| 逻辑跳跃 | 两处:(i) "fine-tuning the retriever generally does not improve … This can be due to the hard requirement of retrieving the exact evidence set"——归因未测,且 ZS 行是规则匹配;(ii) Bart 反向缩放与规模叙事冲突,全文零字 |

**主要 1(M1):未在摘要披露的双重 oracle,使 59.0% 这个"天花板"的真实位置未知。** *作者回应*:§5.3 已明确披露,并写明真实数据的 IE 挑战 "beyond our current scope";上限带更多 oracle 仍是有效上限——事实上是**更强的负结果**("即使给两个 oracle 也只有 59%")。*能否成立*:**基本成立,且实际上对作者有利。** 剩余损伤仅在摘要的完整性。降级为写作/框定问题。**这条不是硬伤。**
**主要 2(M2):85.1%→4.3% 与输入截断混淆,因此它不构成关于聚合推理的证据。** *作者回应*:截断**就是**那个难点——固定窗口 LM 下"装不下"是操作性失效模式,而暴露它正是基准的目的;并可指向 Table 7 第一行(74k 条记录,金标 84.05,预测 83.94)作为"reader 有时能从截断样本外推"的反证。*能否成立*:**只在 2023 年成立。** 作为对固定窗口架构的诊断是公平的,Table 7 第一行也是个漂亮的反点;但作为关于聚合能力的持久论断不成立:混淆可被一次极廉价的消融分离,论文没做。**这条存活,是三条里最硬的一条。**
**主要 3(M3):无模板留出划分,头条微调数字测的是同分布模板拟合。** *作者回应*:基准目的是暴露局限,59% 已是不及格,模板泄漏只让负结果更难看;atomic 侧有 600k 题跨更多模板;且 CLEVR 也有固定问题语法却成为经典。*能否成立*:**部分成立。** "只会加强负结果"对**上限论断**有效,但救不了**比较性正结论**,而那恰是下游引用的句子;CLEVR 类比也不完全成立——**CLEVR 配套发布了 CoGenT 组合泛化划分,TimelineQA 没有**。

**次要 1(m1)**:论文自己的设计变量(sparse/medium/dense)从未作为结果轴出现。*回应*:证据集规模是更直接的操作化代理。*能否成立*:**部分成立但勉强**——逐密度数字的生产成本近乎为零,而它能回答"这条头条曲线是否三条不同曲线的平均"这个直接影响可信度的问题。
**次要 2(m2)**:无方差/CI,单次运行,而比较性结论建立在 1.3–3.3pp 上;Bart 规模轴反向未获解释;Checklist C3 声称描述统计在 §5 而 §5 中不存在。*回应*:基准论文,baseline 仅为示例性。*能否成立*:**不成立**——论文从这些数字推出了机制归因,一旦下了归因就需要方差;而 BART 的反向缩放是自家表格里的直接反证,零字处理。
**次要 3(m3)**:附录 C 的 InstructGPT 结果由作者本人非盲人工判分,n=100,无一致性统计,自陈"不可直接比较",却仍据此推出方向性结论。*回应*:附录旁注,且已声明不可比。*能否成立*:**成立,确属次要**——但既然自陈不可比,"suggests a potential direction of leveraging fine-tuned LLMs" 这句就该删或改写。
*(另记两条程序性瑕疵:附录 D 人类参与者整节留空而 §3.1 使用了 7 位贡献者、附录 C 由作者人工判分;全文从未报告任何 retriever 的 recall@k,导致 §5.3 的核心归因悬空。)*

> **判决 F:倾向 弱接受。** 作为 Findings 论文——它实际去的地方——应当接受:范围界定清楚、限定词写在摘要里而非藏在附录里、代码数据与超参全开,并贡献了一条事后被证明为真的概念命题。它最大的问题不是不诚实,而是**实验薄**:三处近乎零成本的消融(截断分离、逐密度拆分、模板留出)缺席,而其中第一处直接决定头条数字的含义;同时最该跑的 baseline(它自己算金标用的符号执行路线)完全缺席,使"天花板"论断只在一族 reader 内成立。**若投主会长文,我会给弱拒**(实验充分性与 baseline 公平性两项达不到主会标准);Findings 是这篇论文正确的位置,这也说明当年的审稿判断是准的。

#### G 五个扩展方向

**G1 把"装不下"与"算不出"分开:头条悬崖的保质期测量。** 问题:当证据装得下时,85.1%→4.3% 这条曲线还剩多少?值得做的理由:这个数字如今被广泛引作"基于阅读的聚合会失败"的证据,而它的 x 轴刻度是 1024 token 的函数;**对本项目而言,它直接决定 QVF 的机制论断是否必须加"1024-token reader"这个限定词——不加,审稿人会当场拆掉这条引证**。做法:用开源生成器重建 120 个 log 的测试集与 oracle 证据集,固定证据集不变,换三臂:(a) Tapex-1024 复现(校准基线),(b) 128k 上下文模型接收完整序列化表,(c) LLM 写 Python、解释器执行;按四个证据桶报准确率**与** token/$ 成本。难点:尾部题目会需要 10k–620k token(Table 7 第一行 74k 条记录 ≈ 620k token),长上下文臂在真正尾部照样撞上限——这本身是发现,但成本失控风险高,需先做分层抽样。
**G2 TimelineQA-CoGenT:模板留出的组合泛化划分。** 问题:微调后的 table QA 能泛化到未见的聚合模板与改写问法吗?值得做的理由:59.0% 这个上限的**含义**取决于此;CLEVR 自己发布了 CoGenT,TimelineQA 没有。做法:把 42 个模板划成 seen/unseen;另用 LLM 改写测试题并人工校验答案保持;报三格。难点:**42 个模板太少,留出后统计功效不足**——必须先扩充模板库,而这就改变了基准本身,需论证扩充后分布可比。
**G3 给生成器加上失效语义与假前提(TimelineQA-Stale)。** 问题:能通过 TimelineQA 聚合题的系统,能在同一条时间线上回答"现在"类问题、并拒绝假前提问题吗?值得做的理由:这是原作最大的结构性盲区。**关键的独有价值:一个带属性有效区间的生成器可以在 128M 条量级上免费产出 `valid(S,Q)` 的金标——没有任何其他资源能做到这件事,人工标注永远做不到**(这正是原作用符号金标解除标注成本耦合那个机制的第二次应用)。做法:扩展 logical DB,给雇主、城市、牙医、伴侣等属性加有效区间与 supersession 关系(Table 1 的 lifetime 时标已含 "jobs & relocation",可作区间种子);新增模板("我现在在哪工作 / 截至 DATE"、"我住在 Y 的那段时间去了几次 X"、以从未成立的属性值为锚的假前提变体);金标由区间 SQL 计算;把"用过期事实作答的比率"作为一等指标。难点:(i) "现在"的参照时刻必须显式化;(ii) **最大的陷阱是合成的 supersession 可能被"取最新值"这条浅层启发式一键通关**——生成器必须刻意包含"最新值不是答案"的情形(本项目已隔离测量到查询盲的"永远取最新"策略在时序题上仅 32.0%,正是这类反例的存在性证据);假前提题也必须做得可信而非词面荒谬。
**G4 补上缺失的 baseline:符号执行臂,并逐步撤掉 schema oracle。** 问题:"LLM 产出查询/计划 → 确定性执行器执行"与 table QA reader 如何比较?当 IE/schema oracle 被逐级削弱时如何退化?值得做的理由:原作用 SQL 算金标却从未把这条路线当系统评测,**这是三年来最有信息量的缺席对照,也是 QVF / Prog-TQA / TReMu 共同占据的架构**;做这个实验能把 M1 从一条抱怨变成一次测量,并且是回答"为什么不在 TimelineQA 上评测 QVF"这个必然被追问的问题的正面做法。做法:三臂——(a) text-to-SQL + 生成器 schema(oracle 开),(b) 同上但 schema 由 LLM 从原始 episode 自行发现,(c) 端到端 plan-and-execute;再对 IE 注入 1/5/10/20% NER 噪声做敏感性扫描,报"准确率 vs IE 错误率"曲线。难点(两个反向风险):(i) 臂 (c) 要在 78M 条的 log 上跑,必须先有索引/过滤级,检索问题原路返回——这是诚实的发现而非失败;(ii) 相反的风险是在模板化文本上 text-to-SQL 可能轻易接近 100%,使该轴失去信息量,除非先按 §4 所述用 LLM 改写 episode 文本。
**G5 真实校准的突发性到达过程。** 问题:当 episode 到达是突发的、重尾的而非平稳概率,系统的难度排序会变吗?值得做的理由:若排序不变,合成简化就被验证了,这本身是有价值的正结果;若排序翻转,所有从 TimelineQA 得出的结论都要加限定词;顺手可以把 m1(逐密度结果)一并补掉。做法:用公开真实 lifelog 语料(NTCIR-Lifelog / LSC)或公开 quantified-self 数据拟合到达过程;用 Hawkes 型丛聚到达重新参数化生成器;重跑 Table 5/6 网格并按密度拆分。难点:真实语料小且受限;可校准的目标可能只覆盖照片/位置模态而不覆盖占 32% 的 chat 类;**最大风险是只对上了边际速率而没对上联合时间结构,导致结果不可 falsify——必须预先声明校准的是哪些统计量**。

#### 三条判决(TimelineQA)

- **C 新意**:**中(偏弱)**
- **D 实验支持**:**部分支持**
- **F 审稿倾向**:**弱接受**(投主会长文应为**弱拒**)

---

### 3.4 A-Mem 【本节为结构性草案,未取到全文,全部事实性陈述标"待核"】

> **A-Mem: Agentic Memory for LLM Agents**(题名与作者列表**待核**)
> **NeurIPS 2025**(venue 取自打分结果,**本次未复核原文/会议页**)
> 阅读层级:**未取到全文。** 本节依据为:(i) 打分结果中的定位理由;(ii) 核实档 `study_logs/QVF_related_work_verified_20260814.md` 对该篇的定位("与 QVF 固定契约相反的设计赌注":自组织笔记、结构由 LLM 涌现而非预先枚举)。
> **纪律声明:本节不给出任何具体数值,不引用任何逐字原文。凡涉及其内部机制的陈述均标【待核】,组会前必须补一次全文级精读,否则不得对外宣讲本节 C/D/F 判决。** 已并入第六节未核实清单。

#### A 究竟要解决什么问题

**A1 作者声称【待核】**:核实档记录的定位是"自组织笔记、结构由 LLM 涌现而非预先枚举",Zettelkasten(卡片盒笔记法)是其明面上的灵感来源。据此可推断其声称大致落在三点:(i) 现有 agent 记忆系统依赖预先定义的固定 schema / 固定工作流,在设计者未预见的场景上失效;(ii) 提出让记忆条目自行生成结构化属性并在条目之间建立链接,组织在使用中涌现;(iii) 新记忆的加入会反过来更新旧记忆(memory evolution)。**以上三点均为【待核】。**

**A2 实际做成的【待核,必须补读】**:未取到全文,无法判断哪些声称有受控消融支持。**必须在补读时重点回答的三个问题**:
1. **"结构由涌现产生优于预先枚举"这一命题有没有受控消融?** 具体地:是否存在"去掉链接生成""去掉 memory evolution""用固定 schema 替换 LLM 生成属性"的同架构变体?这是本篇对 QVF 唯一真正重要的一条——若它也像 APEX-MEM 与 Prog-TQA 一样把核心概念贡献留在无消融状态,那么"涌现 vs 固定契约"这场争论在文献里**根本没有任何一方给过受控证据**,而这本身就是 QVF 可以占的位置。
2. **memory evolution 是否会改写/覆盖旧笔记?** 若是,则它与 QVF"保时间线 + 替换边"是同一维上的相反选择,**QVF 不能把"更新旧记忆"当作对手的疏忽来讲——那是对方的设计**;若否(只增不改),则 A-Mem 与 QVF 在写入侧的分野比想象中小,QVF 的分界必须挪到"是否承诺可判定的 `valid` 谓词"上。
3. **有没有任何未见组合 / 分布外的泛化测量?** 这决定它能否真的为 QVF 的 S8 反超现象(直读 70.1% vs 平面臂 52.2%)提供机理证据,还是只能作为一个方向性的对照叙事。

**A1–A2 落差**:**无法判定,待补读。**

**A3 领域位置【待核】**:与 APEX-MEM / Zep / Mem0 / MemoryOS 同属 agent 记忆系统一线,但**赌注方向相反**——后者都在把结构做得更明确(本体、时序 KG、事实条目、容量分层),A-Mem 把结构的产生权交给 LLM。属**换设计前提**,不是换方法也不是开辟新问题。

**A4 若无此文,已有方法卡在哪【待核,须在补读时落到具体数字】**:可预期的论证形式是"固定 schema 的记忆系统在设计者未枚举的关系上无法建立联系,因此跨条目的关联型问题失败"。**必须补上具体的系统内落差数字**(如 APEX-MEM 那样的 "MIRIX single-hop 85.11% vs temporal 65.62%,落差 19.49pp"),否则 A4 只是一句同义反复。

**A5 一句话真实问题意识【待核,但方向性判断可用】**:作者真正害怕的是:**任何预先枚举的固定 schema 都会在设计者没想到的那类问题上失效,而设计者永远想不全**——所以把结构的产生权整体交给 LLM,让笔记之间的链接与组织在使用中涌现。**这句话是 QVF 必须正面回答的那个反问("为什么还要固定契约"),而 QVF 自己的 S8 数据站在提问者一边。**

#### B 隐含前提【全部待核】

即使不读全文,这一类设计的隐含前提可以先列出来作为补读时的检查表:
- **数据**:依赖 LLM 生成的属性/链接质量足够高;依赖对话语料里的关联是语义可察的(而非需要外部知识才能连上)。**高风险**:若链接由语义相似度驱动,则"措辞不相似但事实相关"的条目连不上——这与 APEX-MEM 的 Θ_rel 门控(E1)是同一个洞。
- **方法**:依赖"涌现的结构在读取时可被有效利用",即检索侧能沿链接走对;依赖 memory evolution 的更新是单调改善的(**没有灾难性改写**)。**高风险**:LLM 改写旧笔记是一个不可逆的有损操作,与 APEX-MEM 摘要第 2 点("premature commitment")的批评正面冲突——**A-Mem 与 APEX-MEM 在这一点上互为反例,这是组会上最有戏的对撞。**
- **任务**:依赖问题不要求确定性算术(计数/时长/排序),因为读取侧无可执行算子;依赖不存在假前提题。
- **实验**:**待核**——是否有多 backbone、是否报方差、是否报成本三项。
- **应用**:依赖每次写入都可以调用 LLM(成本随记忆条数增长的方式必须核实)。

#### C 真实创新点【倾向判决,待核】

- **C1**:改的是**结构的来源**——从设计者预先枚举,改为 LLM 在写入与使用中生成。
- **C2/C3【待核】**:关键要核实的是"链接生成 + memory evolution"两个机制是否被隔离测量。若未隔离,则 C 判决应压到"中"。
- **C4**:**概念层的赌注清晰(这是它最强处),技术层与工程层待核。** Zettelkasten 的类比本身不是技术创新,但作为设计哲学的表述极有力,这也是它可讲性满分的原因。
- **C5 与 QVF 的分界句(可先写,数字待补)**:
  > A-Mem(NeurIPS 2025)代表相反的设计赌注:记忆条目的结构化属性与条目间链接由语言模型在写入与使用中生成,组织形态涌现而非预先枚举。**QVF 的分野在于它对结构做了三项可判定的承诺**:(i) 六字段卡片契约在写入期固定,故每一条记忆的属主、有效期与逐字锚点是可机械校验的,而非模型每次生成时的自由产物;(ii) 记忆有效性被建模为 `valid : S × Q → {0,1}`,即以问题为条件的二元谓词,而涌现结构不承诺任何可判定的有效性语义;(iii) 读取侧由封闭算子集编译执行,计数/时长/排序由代码完成,而涌现结构下的读取仍是模型在取回的笔记上推理。**代价必须同时写出:在我们自己构造的未见组合切片上,不做任何结构化的直读臂反超了平面卡片臂(70.1% vs 52.2%),这与 A-Mem 的赌注方向一致,QVF 尚未给出反驳。**

> **判决 C【待核,倾向】:中。** 方向性赌注清晰且与整条线相反,概念层有真实价值;但"涌现"作为机制难以隔离,若无受控消融则新意封顶在中。**此判决在补读前不得对外宣讲。**

#### D 实验支持度【待核,倾向】

> **判决 D【待核,倾向】:部分。** 依据是同一子领域(APEX-MEM、Prog-TQA、TimelineQA)三篇的共同规律:**概念性最强的那条贡献最少被受控消融**。A-Mem 的核心贡献恰恰是最难消融的一条(结构涌现),因此先验上大概率是"部分"。**必须补读验证,不得据此宣讲。**

#### E 反例【待核,可先列构造方向】

**E1** 依赖 LLM 生成的链接能连上"措辞不相似但事实相关"的条目;在同义改写/隐含指代场景下不成立。
**E2** 依赖 memory evolution 的改写是单调改善的;在"新信息本身是错的/是用户口误"的场景下,一次改写会污染旧笔记且不可回滚——**这正是 APEX-MEM 摘要第 2 点批评的失败模式,只是发生在笔记层而非事实层。**
**E3** 依赖问题不要求确定性算术;计数/时长/跨条目排序题上无可执行算子。
**E4** 依赖不存在假前提题;涌现结构下没有 premise_check 的挂载点。
**E5** 依赖每条记忆的写入可以负担 LLM 调用;记忆库增长后链接生成的组合成本如何缩放**待核**。

#### F 审稿人视角【待核,倾向 弱接受】

**补读时必须回答的三条主要质疑候选**:
1. "结构涌现优于固定 schema"是否有同架构受控消融,还是只有跨系统对照?(与 APEX-MEM 主要 2 同型)
2. memory evolution 的改写是否有回滚/审计?若无,如何论证它不是一次有损承诺?
3. 是否报告了成本三项(token/$/延迟)与方差?

> **判决 F【待核,倾向】:弱接受。**

#### G 五个扩展方向

**G1 "涌现结构 vs 固定契约"在未见组合上的受控对撞(最高优先,直接补 QVF 弱点④)。** 问题:在同一份对话语料、同一底座、同一检索预算下,LLM 涌现的笔记链接与预先枚举的固定契约,在**训练/开发时未见的约束组合**上谁更强?**为什么值得做:QVF 的 S8 数据显示不做任何结构化的直读反超平面卡片臂 18-21pp,而 A-Mem 的整个赌注就是"不预设结构在分布外占优"——这个命题至今没有任何一方给过受控证据。** 做法:四臂(直读 / 固定契约卡片 / A-Mem 式涌现笔记 / 二者叠加),在 S5–S8 上按"组合是否见过"分层报告。**若结果确认闭集在组合外是负资产,这个发现本身就能写成贡献**(诚实的负结果 + 机理解释,而不是藏起来)。
**G2 涌现链接的召回诊断**:借 G3(TimelineQA)与 G3(APEX-MEM)的同一套 coverage 分层协议,测涌现链接在"措辞不相似但事实相关"的条目对上的召回率,与固定契约的替换边召回率对照。
**G3 memory evolution 的可逆性与污染率**:构造"新信息是错的"注入实验,测一次改写造成的不可逆污染比例;对照 append-only + supersession 的同场景表现。**这条同时是 A-Mem 与 APEX-MEM 的正面对撞。**
**G4 涌现结构上挂 premise_check**:研究能否在无固定 schema 的记忆上做答前前提校验;若不能,则这是固定契约的一项不可替代收益,是 QVF 支柱的正当来源。
**G5 成本缩放曲线**:链接生成的 LLM 调用数随记忆条数的缩放形式(线性?二次?),与 QVF 写入期一次性抽卡的成本对照,按项目纪律报 token/$/延迟三项。

#### 三条判决(A-Mem)

- **C 新意**:**中【待核,未取全文,不得对外宣讲】**
- **D 实验支持**:**部分【待核,未取全文,不得对外宣讲】**
- **F 审稿倾向**:**弱接受【待核,未取全文,不得对外宣讲】**

---

## 四、组会讲稿骨架(每篇一份,按 40–60 分钟一场设计)

> 共同纪律(四份都适用):
> - 措辞按项目纪律:不用"战役/哨兵"等比喻,实验阶段说"轮",机制说功能名。
> - 报数字时**先判决后数字**("这个猜想被否定了:同底座下它反而低 1.17pp"),不要先铺陈。
> - 凡引用 QVF 自己的数字,一律用**去重后**口径(5,061 unique qid;59.55→70.16),不用 5,511/未去重口径。
> - 讲成本必带 token/$/延迟三项;凡引用对方成本,必须说明是哪张表的口径。

---

### 4.1 APEX-MEM 讲稿(推荐:如果只讲一篇,讲这篇)

**开场三句**
1. "这是 ACL 2026 主会、Amazon 的长文,也是目前离我们的系统最近的一篇:它把一个**只读 SQL 接口**交给 ReAct 代理,让 JOIN、聚合、时间窗由 SQLite 确定性执行——我们的读取侧做的是同一件事。"
2. "所以今天不是来介绍一篇相关工作,是来回答一个问题:**在它已经发表之后,我们还剩哪句话可以说。** 我读完的答案是只剩三句,我会把这三句念给大家听,请当场挑战。"
3. "另外它送了我们一份反向的礼物:它自己的表里有一行,用**别人家的数据**证明了我们最想证明的那件事——证据完全齐全的时候,模型的时序算术依然不行。"

**分段时间表(总 50 分钟)**

| 段 | 时长 | 内容 |
|---|---|---|
| 问题 | 6 min | 它真正害怕的失败模式:**写入时对"当前状态"的一次不可撤回的提前承诺,会永久销毁回答一个尚未被提出的问题所需的证据**。用 MIRIX 的系统内落差举例(single-hop 85.11% vs temporal 65.62%,落差 19.49pp)——不是"效果差",是**旧行在库里已被合并掉了** |
| 方法 | 10 min | 三件事:append-only 事实挂事件(f 与 ε 的元组)、35 类本体、四工具 ReAct(EntityLookup / GraphSql / Search / SchemaViewer,硬上限 40 步)。**白板画 GraphSQL 的七张白名单表** |
| 实验 | 14 min | 头条(LOCOMO 88.88% / LongMemEval 86.2%)→ 立刻转 Table 3 消融 → 立刻转两处同底座反转 |
| 局限 | 12 min | 三条主要质疑逐条讲,每条都给作者的最佳回应与我的裁定(尤其:LongMemEval 的 24pp 差**救回了**它的核心论证,必须公允说出来) |
| 与我们的关系 | 8 min | 三句还能说的话 + 三条必须改的档案断言 + 一个立刻可做的实验(G4:语法成功率 vs 语义正确率) |

**必放的一张表:Table 3(唯一的工具消融,Claude 4.5 Haiku)**
77.19% → +GraphSQL 79.45% → +Search 87.00%。
**为什么是它**:一张表同时承载三件事,别的图做不到——(i) 它是全文**唯一**的受控消融,因此是全文唯一能做归因的地方;(ii) 它显示**结构化 SQL 只值 +2.26pp,而普通混合检索值 +7.55pp**,结构化机制的净贡献远小于检索改善,这与我们自审"+35.4pp 里约 9pp 来自检索覆盖度"同向,**所以我们必须先引这张表再讲自己的分解,否则显得是重新发现别人已发表的东西**;(iii) 它显示标题里的 temporal 在完整配置下从 82.29% **掉到 79.17%(−3.12pp)**,而正文写 "substantial gains across **all categories** including single-hop…multi-hop…open-domain…and adversarial"——五类里唯一没被点名的就是回退的那一类。

**预判的 3 个提问 + 准备好的回答**

**Q1(最可能来自导师):"他们让 LLM 临场写 SQL,执行成功率 97.6%。你为什么还要 11 算子闭集?"**
A:"这个问题问到了要害,而且**我们原来的动机已经死了**——'模型写不对查询'不能再作为理由:Sonnet 4.5 97.6%(3,574/3,659)、GPT-5 93.4%、Haiku 95.4%,失败还能自恢复 87%。我的回答是把动机换成一个可实测的区分:**Table 11 报的是执行不报错率,不是语义正确率。** 一条语法合法但时间窗写错的 TEMPORAL SQL 会静默返回错结果,并照样计入那 97.6% 的'成功';而 TEMPORAL 占它 SQL 的 62%,靠 `julianday()` 做日差算术。所以闭集的价值转到四条:编译期**语义**校验、答前 premise_check、按题型可判定的步数上界、成本可预测。而且这个差值可以量出来——我把它列成了下一轮的正式实验。"

**Q2:"88.88% 是 SOTA,你怎么说它不如把对话直接塞进上下文?"**
A:"这个猜想被否定了,而且是被它自己的表否定的。Table 1:APEX-MEM + GPT4o = 86.35%,Full Context + GPT4o = **87.52%**,同底座下它低 1.17pp。头条 88.88% 用的是 GPT5 底座,而表里**没有 Full Context + GPT5 这一行**,那 +1.36pp 是换底座换来的,且在它自报的 std<±1 下不足称显著。SealQA 上同一模式再演一次:原文说 '5.55 percentage point improvement over the strongest baseline' 并对照 O3 34.6%,但同一张 Table 5 里 GPT5+Web-Search 是 38.6%,同底座真实增益只有 1.5pp。**但公允地说,这不是全盘否定**:LongMemEval 上 Full-Context+Sonnet 4.5 只有 62.2% 而它 86.2%,差 24pp——记忆系统真正有必要的地方是上下文塞不下的时候。真正的问题是,**它最珍贵的分类别 temporal 证据全部只在 LOCOMO 上,即只在那个不需要记忆系统的基准上。**"

**Q3:"我们跟它比,成本上有优势吗?"**
A:"目前不能这么说,而且这里有一条我们必须对称适用的纪律。它的跨系统 token 表(Table 9)把自己记为 ~30,000 tok/Q,而自家分解(Table 10)明写 **81,604**;差的 2.7 倍正是 Table 9 没计的 tool framing 27.3% + agent loop overhead 19.8% = **47.1%**,也就是 agentic 架构的固有开销。铁证是附录 C 那句 '16.6%'——16.6% = 13,557/81,604,写跨系统对照时 81,604 就在手上。**但我要同时认一处对我们有利的更正**:它那句 '3.3x more tool calls (27,282 vs 8,260)' 只成立于 GraphSQL 单列;按 Table 6 加总,结构化-only 变体总调用 41,466 vs 全系统 29,624,真实比是 **1.40×**——结构化路线的开销代价被它夸大了,我们引用时必须用 1.40×。我们自己刚被内部审判否过一次成本口径,所以标准要对称:**不能因为顶会论文这么写就跟着写。**"

**收尾一句**
"这篇论文告诉我们:**'结构化执行'这句话在 2026 年已经不属于任何人了,还没被占走的是三样东西——按题型分派预算的路由、答前的前提校验、以及把归因做干净的纪律。我们的三支柱现在没有一条是冲着它写的,这是今天散会后要改的第一件事。**"

---

### 4.2 Prog-TQA 讲稿

**开场三句**
1. "这是 LREC-COLING 2024 的长文,venue 是今天四篇里最低的,但它是唯一一篇我**不敢不讲**的:我们方法叙事的那句话——'把问题编译成算子计划,再由代码执行'——2024 年这篇已经做了,带 12 个时序算子、符号执行器、完整消融和 SOTA。"
2. "所以这一场我讲的不是别人的论文,是**我们支柱二的所有权问题**。我会先把它的一号贡献原文念出来,大家听听像不像我们的第二根支柱。"
3. "好消息是它同时留了两样东西给我们,而且都很实在:一份**第三方的算子清单**,和一个它没跑而我们跑了、还跑输了的对照臂。"

**分段时间表(总 45 分钟)**

| 段 | 时长 | 内容 |
|---|---|---|
| 问题 | 6 min | 它真正害怕的:**组合时间约束("before"+"last")一旦被压进单个时间感知向量的相似度分数里,答对了说不清为什么对、答错了定位不到哪一步错**。用彼时 SOTA 的多约束题 Hits@1 = 0.159 立卡点,并说明根因是"没有三个可分解的计算步" |
| 方法 | 10 min | 两阶段(ICL 生成 KoPL 草稿 → linking → 符号执行)+ 12 个时序算子 + gold-answer 弱监督迭代自举(Algorithm 1)。**白板上把 Table 1 的算子名一个一个写出来**,让大家自己看出与我们的重叠 |
| 实验 | 12 min | Table 2 头条(0.293 → 0.797)→ Table 4 消融四项 → Table 7 的规模实验 |
| 局限 | 10 min | 三条主要质疑(算子零消融、无 LLM 直读臂、增益结构未披露)+ 口径纪律的反面教材 |
| 与我们的关系 | 7 min | 支柱二的两条出路;我们的算子级独有项收缩到哪三项;G1 与 G2 两个实验 |

**必放的一张表:Table 4(消融表)**
自举微调 **+21.4pp**、linking 模块 **+13.2pp**、示例数从 6 降到 1 **−25.3pp**、post-processing **Hits@1 −4.6pp / Hits@10 +8.0pp**。
**为什么是它**:**四个被测的组件加起来解释了几乎全部的 +50.4pp,而排第一位的贡献"系统分析时序约束并设计 12 个时序算子"一次都没被消融。** 这张表用"它测了什么"反衬出"它没测什么",是整篇最大的声称-证实落差;而这个落差与我们支柱二的处境完全同型——讲这张表,等于同时讲完他们的问题和我们的问题。

**预判的 3 个提问 + 准备好的回答**

**Q1:"那我们的十一个算子跟他们的十二个,到底差在哪?能不能说我们更精简?"**
A:"不能这么比,这是个陷阱。**他们的 12 个是增量**——基础 KoPL 函数(Find / Relate / QueryRelationQualifier / What 等)仍然在词表里,论文从未列举基础函数的数量。所以'11 vs 12'不是同口径比较,拿它讲'我们更精简'会被一句话戳破。而且算子级的重叠比想象中大:FilterFirst/FilterLast、FilterBefore/After、FilterByTimePoint、GetYear/Month/Date、FilterByDuration、**GetDuration**、QueryEventQualifier 全部同名同义已存在——**'时长计算'我们不能再称独有**。收缩之后,我们真正独有的只剩三项:沿取代链的 count_changes、premise_check、tag_filter/tag_trend,再加一条'算子作用于在线抽取而非给定的库'。顺带说一句他们自己的口径也乱:正文点名 11 个、表里 12 个、附录 A.1 说 FilterFirst/FilterLast 各拆成 Time/Event 两版即实际 14 个,而 Table 9/10 用的正是那四个**没出现在 Table 1** 的名字。"

**Q2:"他们 +50.4pp,你们才 +4.21pp 净增益,差距这么大?"**
A:"这个比较不成立,原因在**基线代际**,不在机制强弱。他们的五个基线全是 2019–2023 的嵌入/LM 方法,最强 0.293,连'同一个 13B + 同样 top-5 检索事实、不生成程序直接作答'这一臂都没跑;intro 拿 ChatGPT 举例却从不跑闭源模型。所以无法区分那 +50.4pp 来自'程序化符号执行'还是来自'引入了一个 LLM'。他们可能拿 Table 7 的规模实验挡——7B/13B/33B 是 0.516/0.529/0.530,只差 1.4pp——**但那三档全都仍在 Prog-TQA 管线内跑,只证明'不是更大的 LLM 在起作用',不能证明'不是 LLM 本身在起作用'。** 而这一臂我们跑了,还跑输了:S8 未见组合上直读 70.1% vs 平面臂 52.2%,LongMemEval-KU 上卡片臂 64.1% < 直读 78.2% < 提示词臂 92.3%。**我们的标准比这篇长文更严,这些负结果要留在论文里,不是要藏。**"

**Q3:"那还怎么讲我们的第二根支柱?"**
A:"两条路,我倾向第一条。**第一条:把'完备/最小'换成可做的实验。** 自审第 323 行说解除循环性的办法是'由独立方列出算子清单,再看我们的覆盖率'——**KoPL 的 12 个时序算子就是那份现成的独立清单**,读这篇等于把最大的质疑变成一个可执行实验:做 leave-one-operator-out,给出'算子数 vs 可解题型覆盖率'曲线,顺便把 TempReason L1/L2/L3 与 TimeQA 也纳进来。**第二条:把支柱二降级成题型学表格,不再声称完备。** 注意他们比我们诚实——原文写 'these operators can be flexibly extended according to future requirements',**明确声明是开集**。当前状态下,我们的支柱二 ≈ 他们的 Table 1 + 一个更强的词。不能维持现状。"

**收尾一句**
"这一篇的意义不是'又一个相关工作',而是**它把我们最弱那根支柱的天花板画出来了:范式已经被占先,我们能立的只有'域迁移 + 三项可判定的承诺';而它同时把解除循环性的那份第三方算子清单送到了我们手上——如果两周内不做这个实验,支柱二就该改口。**"

---

### 4.3 TimelineQA 讲稿

**开场三句**
1. "这一篇不是系统,是一把尺子,Meta 和 Halevy 组做的,Findings of ACL 2023。它做了一件我们做不到的事:造了一台生成器,能**无限量生产那种'金标只能由 SQL 算出来'的题**。"
2. "为什么这很重要:因为人工标注一道题的成本随所需证据条数增长,所以整个领域的数字**都采样自 10 条证据以内的区间**——而在那个区间里,系统的成绩是 85.1%。他们把成本耦合切断之后,同一个系统在千条证据上是 **4.3%**。"
3. "我今天要用这一篇回答一个我们必然被问到的问题:**为什么我们的头条增益里,有一部分不是算术能力,而是检索覆盖度?** 他们三年前就给了分离这两者的实验模板,而且用的是给不给金标事件集这个最朴素的开关。"

**分段时间表(总 45 分钟)**

| 段 | 时长 | 内容 |
|---|---|---|
| 问题 | 8 min | 标注经济学这条机制(不是"模型不够好"):人工标注成本随证据条数超线性增长 → 所有基准被隐式钉死在小证据区间 → **失效模式在结构上不可观测**。举 Table 7 第一行(74k 条记录的均值题)说明为什么众包做不到 |
| 方法 | 8 min | 生成器:persona → 五时标 episode → super/sub 嵌套 → 互斥约束;duration 与 density 两个旋钮;25 类事件、128M 条;**金标由 logical representation + SQL 计算**;三档检索器条件(OR/FT/ZS)这个协议本身 |
| 实验 | 13 min | 基数悬崖(白板四个数)+ 题型分桶(average 11.1 最弱)+ 59.0% 的双重 oracle |
| 局限 | 10 min | 三条:双 oracle 未在摘要披露、悬崖与 1024-token 截断混淆、无模板留出;并说明第一条其实**对作者有利** |
| 与我们的关系 | 6 min | 我们必须改的两处引用措辞;它留下的最干净的空位(有效性/取代语义);"为什么不在它上面评测我们"的正面答案 |

**必放的一张图/表:Table 6 右列——直接画在白板上的四个数**
[0,10] → **85.1%**(n=1,949)、(10,100] → **52.5%**(n=1,275)、(100,1000] → **19.2%**(n=689)、>1000 → **4.3%**(n=371)。
**为什么是它**:(i) 一列四个数就是整篇论文,听完一周还记得;(ii) **关键是这是在 oracle retriever 下测的**(§5.4 原文 "with a perfect retriever"),所以检索侧解释被干净排除,这一点决定了它能不能被我们引用;(iii) 它同时是我们要更正档案措辞的地方——**必须同时写出 1024-token 上限与 20.40% 截断率**,否则这条引证会被一个持 128k 上下文的审稿人一句话作废。

**预判的 3 个提问 + 准备好的回答**

**Q1:"你引的 85.1%→4.3%,那是检索失败还是上下文窗口失败?"**
A:"这个问题我自己先查过,而且我们档案里的措辞是错的,要改两处。**第一,它不是检索失败**——那个分桶是在 oracle retriever 下测的,§5.4 原文 'with a perfect retriever',所以叫'检索式 QA 崩塌'会被当场纠正,它是 reader 侧失败。**第二,不能不提 1024-token 上限**:§5.1 报告测试集 20.40% 的输入被截断,而 >1000 桶平均 1,169.8 条 × 8.4 token ≈ 10k token,约 **90% 的证据在 reader 看到之前就被丢掉了**。所以正确的引用措辞是:'在完美证据检索器下,一个输入上限 1024 token 的 table-QA reader 随金标证据集从 ≤10 条(85.1%)增长到 >1000 条(4.3%)而崩塌;论文同时报告 20.40% 的测试输入被截断,故尾部崩塌相当程度上是输入容量失效。' **论文自己没有把'装不下'与'算不出'分开,而分离它只需要一次 512/1024/2048 的截断消融——这也是我列的第一个扩展方向。**"

**Q2:"这个基准是公开的、Meta 发布的、题型正是你们的目标题型。为什么不在它上面评测你们的系统?"**
A:"这是四篇里最难回答的一个问题,我不打算绕。诚实的答案有两层。**第一层是它测不到我们的核心命题**:它的 episode 集是单调追加的,一致性只靠互斥约束,42 条复杂模板里**没有一条问'现在'**,零道假前提题——后果是**一个陈旧值处理率 0% 的系统与 100% 的系统在它上面得分完全相同**,它对 `valid : S × Q → {0,1}` 这条轴是全盲的。**第二层是我不该用第一层当挡箭牌**:它完全能测我们的算子与聚合论断。所以正确的做法不是解释为什么不跑,而是**把它作为算子/聚合论断的域外效度臂真的跑一遍**,同时说明它测不到有效性那一维。这件事我列进了扩展方向 G4,而且它顺带补上了这篇论文三年来最有信息量的缺席对照。"

**Q3:"它的天花板 59.0%,是不是说明符号执行也救不了?"**
A:"恰恰相反,而这是**这篇论文里最有意思的一处空缺**:59.0% 是一族 **reader** 的天花板,不是任务的天花板。因为**它自己算金标用的就是符号执行**——§4.1.1 原文 'The answers are computed by applying external algorithms (e.g., **SQL queries**) over the timeline'。它把符号执行 over 结构化库用作 **oracle**,从来没当作 **baseline** 跑过一次;§5.3 还建了一套近乎完美的 per-topic 表,而那套表的'近乎完美'原因是 'exploiting the topics ... which are known to the **generation pipeline**'——**它偷看了数据生成器,这是摘要里没披露的第二个 oracle。** 一条把 count 题化为'数检回来的行数'的朴素 Python baseline 很可能在 >1000 桶上远超 4.3%。但这也有反面:**我们不能把'符号执行有助于聚合'当作 QVF 的创新来讲——那句话属于 2023 年的这篇论文。**"

**收尾一句**
"这一篇给我们的不是一个对手,是**两样东西:一把量'检索覆盖 vs 算术能力'的尺子(我们头条里那 9pp 就该用它的方式量),和一个它亲口划出界外、三年没人补的空位——它明说自己的工作从 episode 已被推断出来之后才开始,而'从对话原文推断出带有效期的事实'正是我们写入侧做的事。**"

---

### 4.4 A-Mem 讲稿【须在补读全文后才可宣讲;本骨架不含具体数字】

**开场三句**
1. "前三篇都在把记忆的结构做得更明确——本体、时序图、算子清单。这一篇是 NeurIPS 2025,赌的是**完全相反的方向**:结构不预先枚举,让它在使用中涌现。"
2. "我讲它不是为了完整性,是因为它是**我们最痛的那个洞的对立面**:在我们自己构造的未见组合切片上,不做任何结构化的直读臂反超了平面卡片臂 18 个点。**A-Mem 的整个下注方向就是'不预设结构在分布外占优'。**"
3. "所以今天最值得吵的一句话是:**既然如此,为什么还要固定契约?** 我准备了我的答案,但我先说清楚——我们自己的数据现在站在提问者那一边。"

**分段时间表(总 40 分钟;若补读后发现实验丰富,把实验段扩到 15 min、总 50 min)**

| 段 | 时长 | 内容 |
|---|---|---|
| 问题 | 8 min | 它真正害怕的:**任何预先枚举的固定 schema 都会在设计者没想到的那类问题上失效,而设计者永远想不全**。用 Zettelkasten 的故事讲(不需要任何时序 QA 背景,非本行听众也能参与) |
| 方法 | 8 min | 笔记生成结构化属性 → 条目间链接 → 新记忆反过来更新旧记忆【补读时确认第三步是否会改写旧笔记】 |
| 实验 | 8 min | **【待补读】重点核实:三条声称各有无受控消融;有无未见组合/分布外测量;有无成本三项** |
| 局限 | 8 min | 与 APEX-MEM 的正面对撞:LLM 改写旧笔记是不可逆的有损操作,而 APEX-MEM 摘要第 2 点批评的正是 "premature commitment to a single current state"——**两篇在这一点上互为反例** |
| 与我们的关系 | 8 min | 固定契约的三项可判定承诺;S8 反超作为对方的正面证据;G1 对撞实验 |

**必放的一张图:它的笔记互链示意图(核心机制图)**
**为什么是它**:这一场的价值不在数字而在**设计哲学的对撞**,而互链图是唯一能让全场(包括没有时序 QA 背景的人)在三十秒内理解"结构从哪来"这个问题的载体。把它和上一场 APEX-MEM 的 GraphSQL schema 图**并排放在同一张幻灯片上**——左边是预先枚举的七张表,右边是涌现的笔记网络,QVF 的坐标就在这两张图之间。

**预判的 3 个提问 + 准备好的回答**

**Q1(最关键,必被问到):"如果不预设结构在分布外更好,你们为什么还要固定契约?你们自己的 S8 数据不是站在他们那边吗?"**
A:"是,站在他们那边,我不辩解:S8 未见组合上直读 70.1% vs 平面臂 52.2%。我的回答分三步。**第一步,承认这是一个真实的发现而不是一个 bug**——如果闭集在组合外确实是负资产,**这个发现本身就能写成贡献**,前提是我们把它量清楚而不是藏起来。**第二步,固定契约买的不是分布外的准确率,是三样只有它能给的东西**:可机械校验的属主/有效期/逐字锚点、以问题为条件的 `valid` 谓词、以及答前的前提校验——这三样在涌现结构上都没有挂载点。**第三步,这场争论至今没有任何一方给过受控证据。** 它没有(待核实),我们也只有一个切片。所以我把'涌现 vs 固定契约在未见组合上的四臂对撞'列成了下一轮的第一优先实验。"

**Q2:"他们的 memory evolution 会改写旧记忆,这不正是你们批评 Mem0 覆盖旧值的那件事吗?"**
A:"这是今天最有戏的一处对撞,但我要小心用词:**那是他们的设计,不是他们的疏忽。** 更有意思的是,APEX-MEM 摘要的第 2 点逐字批评的就是这件事——'avoid premature commitment to a single current state'。所以**同一子领域里两篇顶会论文在'该不该改写已有记忆'上是正面对立的,而两边都没有做同架构的受控消融。** 这就是我列的 G3:构造'新信息本身是错的'注入实验,测一次改写造成的不可逆污染比例,对照 append-only + 替换边。**这个实验没人做过,而它同时是两篇论文的裁判。**"

**Q3:"这篇跟你们的系统其实不冲突,为什么要花一场讲它?"**
A:"对,它不与我们抢同一句声称——这也是我给它相关性 4 而不是 5 的原因,它是**对照而不是竞位**。但正因如此它最有用:前三篇都在告诉我们'这句话不能说了',只有这一篇在问'你为什么要这样设计'。**一个只回答'我和别人不同在哪'的论文是站不住的,还得回答'为什么这个不同是对的'——这一篇就是那个提问者。**"

**收尾一句**
"这一场没有数字上的结论,只有一个坐标:**我们把结构的产生权握在写入期,换来的是三项可判定的承诺;A-Mem 把它交给模型,换来的是在设计者没想到的地方仍然能连上。到目前为止,在我们自己的未见组合切片上,他们的赌注赢了——这件事我们要写进论文,不是写进抽屉。**"

---

## 五、给 QVF 的直接启示

### 5.1 六条真实弱点 × 四篇的补洞覆盖

| # | 弱点 | APEX-MEM | Prog-TQA | TimelineQA | A-Mem | 净判定 |
|---|---|---|---|---|---|---|
| ① | 头条 +35.4pp 里约 9pp 来自**检索覆盖度**而非算术能力(必需证据完整仅 297/418 = 71.1%;完整层 Δ=+26.3pp,截断层 Δ=+57.9pp) | **强补**:Table 1 Full-Context 行(同模型、同完整证据,open-domain 92.70% vs temporal 71.88%,落差 20.82pp)是**别人家数据**做的同一分离,比自家分层更易被接受 | 反证式补:它依赖 top-5 检索却**从不报 recall@5 或覆盖度**,说明这个测量在近邻里没人做过 | **强补**:"给不给金标事件集"就是覆盖度受控条件的现成设计,对应待办 G1b 全上下文臂;三档检索器协议(OR/FT/ZS)可直接搬 | — | **已被覆盖**。做法明确:先引 APEX-MEM Full-Context 行立动机,再用 TimelineQA 的 oracle/非 oracle 三档协议做自家分层,把 9pp 从"自审发现"升级为"标准协议下的测量" |
| ② | 整合系统 5,511 题**实为 5,061 unique qid**(450 重复);去重后 59.55→70.16 | — | — | — | — | **四篇都补不了**。这是自家实验纪律问题,读任何论文都无解。唯一的处理是:全文一律用去重口径,并在方法节显式记录去重规则与重复来源 |
| ③ | 整合系统增益里 **+5.64pp 来自一段提示词**,结构化机制净 **+4.21pp**(簇 CI[+1.39,+7.16]) | 部分:它的结构化臂也只值 +2.26pp,给了"结构化净增益本来就小"的先例——**但这削弱而非补强我们的辩解空间** | 部分:同型口径问题(绝对 pp 写成 "%")是反面教材 | — | — | **四篇都补不了(且 APEX-MEM 让它更难说)**。审稿人会说:APEX-MEM 结构化臂只值 +2.26pp,你的 +4.21pp 并未把这条线往前推。唯一出路是把净口径做成方法论贡献(见 5.2) |
| ④ | 组合泛化上被朴素直读反超(S8 未见组合 直读 70.1% vs 平面臂 52.2%) | **补(正面实验)**:自审 987 行的最小实验就是在 S5/S8 上做"开放生成 vs 闭集词表"臂;它无任何组合泛化测试,这是我们的测量贡献 | 部分:它同样零组合泛化划分(自举训练/测试同分布) | 部分:它的 42 个模板训练/测试完全共享、零 CoGenT 划分,说明"组合泛化划分缺席"是全线通病 | **补(机理解释)**:"不预设结构在分布外占优"就是它的整个下注方向 | **已被覆盖(两面都有)**。APEX-MEM 给实验设计,A-Mem 给机理。**关键判断:若结果确认闭集在组合外是负资产,这个发现本身就能写成贡献** |
| ⑤ | LongMemEval-KU 靶心上卡片臂 **64.1%** < 直读 78.2% < 提示词臂 92.3%(自审判 M2"基本不成立") | **反向:它抢走了这块高地**(LongMemEval Online + Sonnet 4.5 = 86.2%),使 64.1% 更难看,不能靠"我们不比 SOTA"回避。**唯一的礼物是空位六**:它只报 overall、**knowledge-update 类缺席**,所以逐类别报(包括输的 KU)在信息量上严格更强 | — | — | — | **只补到叙事框架,不补解法**。真正的补法是**在 v4.2 当前口径下重跑那 78 题**,并把逐类别负结果主动列出——这正是"预注册自我证伪审计协议"这一支柱的用武之地(把对手的沉默变成对照) |
| ⑥ | 三支柱中"六原语完备基"数学含量低,"最小"性从未证明 | 部分:Table 7 给出 4,130 条真实生成 SQL 的算子分布(TEMPORAL 2,317 + AGGREGATE 1,417 = 90.4%),是**别人家的独立经验证据**,支持把"完备"改写为**相对某问题分布的覆盖性主张** | **强补**:KoPL 的 12 个时序算子是解除循环性所需的"独立方算子清单"(自审 323 行),读它等于把最大质疑变成可执行实验(leave-one-operator-out + 覆盖率曲线) | 部分:它的 42 模板 + 四题型桶是另一份独立题型学 | — | **已被覆盖,且有两条并行出路**:(a) 证覆盖不证最小,引 APEX-MEM Table 7 的真实算子分布;(b) 做 Prog-TQA 独立清单的覆盖率实验。**注意 Prog-TQA 明写算子"可按需扩展"即自认开集——它比我们诚实,这一点必须公允写出** |

### 5.2 合看四篇之后,QVF 必须改的动作(按优先级)

1. **重写"为什么要闭集"这一段(最紧急)。** "LLM 生成的查询不可靠"这条动机已被 APEX-MEM 的 SQL 成功率(97.6%/93.4%/95.4% + 自恢复 87%)打掉。新动机只能是四条:编译期**语义**合法性校验、答前 premise_check、按题型可判定的步数上界、成本可预测。并把"语法成功率 ≠ 语义正确率"做成正式实验(APEX-MEM G4)。
2. **修档案三处硬错**(APEX-MEM 分界句草稿)+ **两处引用措辞**(TimelineQA 的 85.1%→4.3% 与 59.0%)。不修,相关工作一节会被当场打掉可信度。
3. **支柱二二选一**:补 leave-one-operator-out + 覆盖率曲线(用 Prog-TQA 的 12 算子作独立清单、APEX-MEM Table 7 作外部分布),或把它降级为题型学表格并明确声明开集。**不能维持现状。**
4. **支柱一改写口径**:从"我们的系统很强"改为"**我们给出了编译-执行类系统的增益分解方法,并对自己执行了它**"。四篇里没有一篇做过覆盖度分解(APEX-MEM 未测在线模式的召回失败、Prog-TQA 从不报 recall@5、TimelineQA 无 recall@k),**这是真正无人占据的方法论贡献位**——前提是我们一处不虚。
5. **把归因纪律本身写进 intro。** 三篇里概念性最强的贡献都零受控消融(APEX-MEM 的本体与 append-only、Prog-TQA 的算子集、TimelineQA 的密度轴);而我们已有簇 bootstrap CI[+1.39,+7.16]、去重后 59.55→70.16 的诚实重算、以及主动报出的三处负结果。**在这个子领域,把归因做干净本身就是可以点名的方法论贡献。**
6. **负结果全部保留并主动前置**:S8 反超、LME-KU 64.1%、LoCoMo 66.2% < 直读 69.4%。四篇里没有一篇报过这种自我否证的对照臂(Prog-TQA 连 LLM 直读基线都没有),**这是我们高于这条线标准的地方,不是要藏的弱点**。
7. **成本口径对称适用**:引用 APEX-MEM 时用 81,604 而非 ~30,000,用 1.40× 而非 3.3×(后者是对我们有利方向的更正,同样要如实引用);自家一律带 token/$/延迟三项。

### 5.3 哪条弱点是这四篇都补不了的

**②(去重口径)与 ③(提示词 +5.64pp / 结构化净 +4.21pp)。** 这两条是自家实验纪律问题,读任何论文都补不了——它们只能靠**在方法节公开口径 + 在结果表里同时给出净口径与含提示词口径 + 预注册后续实验**来处理。

需要额外标注的是 **⑤(LME-KU 靶心)属于"半补不了"**:四篇给了它一个更好的叙事框架(APEX-MEM 只报 LongMemEval overall、knowledge-update 类缺席,所以我们逐类别报在信息量上严格更强),但**没有任何一篇能替我们把 64.1% 抬起来**。这条的补法是在 v4.2 口径下重跑那 78 题并逐类别公开,不是靠讲论文。

---

## 六、未核实清单(四篇合并,一条不省)

### 6.1 APEX-MEM(10 条)

1. **Table 2 的评测协议完全未定位** —— 事实抽取 97.3% / schema coverage 91.1% / 实体属性消解 98.2% 三组数字的样本量、评判者(人工还是 LLM)、判定标准,在取到的全文中未找到描述。B1/E4 中"约 9% 抽取漏"的推断建立在 91.1% 上,故该推断为**待核**。
2. **Table 1 与 Table 3 的 Overall 聚合定义差异是推断,不是原文陈述。** 已核实的硬事实是:两表五个分类别数字完全相同(85.46/84.74/79.17/89.18/87.22)而 Overall 一为 87.00%、一为 84.92%。"题级 micro 与类别 macro 之别"是猜测,**论文对此无任何说明**。
3. **Table 9 的 ~30,000 究竟排除了哪些项,是从算术与上下文反推的**(3,717 + 13,557 + 8,000 ≈ 25,274;附录 C 的 16.6% 用 81,604 作分母)。**论文没有任何一句陈述 Table 9 的口径,也没有陈述 baseline "(est.)" 的估法**,故"排除 tool framing 与 agent loop overhead"是推断而非引文。
4. **Table 11 的 "Sonnet (SQL)" 列 66,580 次 SQL 执行,与 Table 6 GraphSQL-only 列 27,282 次、Table 7 GraphSQL-only 列分类合计 13,641 三者互不相符。** 部分原因可能是底座不同(Sonnet vs Haiku)与抽样分类,**三者关系未核实,未据此下任何判断**。
5. **LongMemEval baseline(Nemori 74.6%、Zep 71.2%)与 SealQA baseline 是否使用同一 GPT-5 判官、同一底座,未核实。** 只核到 "For all other benchmarks we used reported numbers from [14, 12, 17]",**引文编号 [14][12][17] 具体对应哪三篇未核实**。
6. **"跨题型泛化波动 <5 percentage points" 这一声明的适用范围未核实。** GPT5 行波动约 5.4pp 勉强,而 Haiku 行 temporal 79.17% vs open-domain 89.18% 是 10.01pp;**论文是否把该声明限定在特定底座上,取到的文本中未见限定语**。
7. **是否开源代码/数据未核实。** 全文取到的部分未见 GitHub 链接或 artifact 声明,Ethics 节只谈 AI 辅助写作与去标识化。G1/G2/G4 三个扩展方向都依赖能否拿到或重建其实现,**这一前提待查**。
8. **未开 ACL Anthology camera-ready PDF。** venue/作者/标题/页码 16470–16489/头条数字已从 Anthology 页核实与 arXiv 一致,但**本报告全部节号(§3.3、§4.3、§5、§6.2、§6.3)与表号(Table 1–12)、附录字母(A–I)均按 arXiv v1 HTML 编号;camera-ready 是否重排未核实**。引用页码时需人工复核对应关系。
9. **附录 E 那句消解规则("a GraphSQL temporal query returns both facts ordered by timestamp; the agent selects the most recent valid entry")的确切出处小节未定位**,仅确认在附录 E "Qualitative Case Studies" 范围内。该句是 C5/B3/E4 与"无 premise_check"分界句的关键引文,**建议原文再定位一次精确位置**。
10. **GraphSQL 的执行前校验是否还包含表白名单之外的其他检查(如 LIMIT 强制、超时、行数上限)未核实**,只核到 "single read-only statement"、"forbidding Updates, or DDL"、七张白名单表。若存在更强校验,C5 分界句中"仅安全/作用域级校验"的措辞需再收紧。

### 6.2 Prog-TQA(12 条)

1. **基础 KoPL 函数总数未核实**。论文从未列举 KoPL 原生函数(Find / Relate / QueryRelationQualifier / What 等)有多少个。因此"QVF 11 算子闭集 vs Prog-TQA 12 算子"**不是同口径比较,对外不可这样讲**。
2. **人工标注程序总量未核实**。论文只写 "provide 20 exemplary programs annotated for each category" 与按答案类型(entity/time)再细分,从未给总数。按 20/类 × 题型数 × 2 推得约 240/160,**乘法为推算**,类别是否真按答案类型翻倍也未明确。
3. **测试集中 time-answer / entity-answer 的题目占比未核实**。Table 8 只按题型切分不按答案类型。因此"增益集中在时间答案题"只能看方向,**不能给出加权贡献量**。
4. **文本 60.9% 与 Table 2 自身数字不符,差值来源未核实**。0.750 − 0.159 = **59.1pp**,而 §4.2 文本写 "60.9% improvement";另两个数(50.4、47.0)与表格精确一致。1.8pp 的差可能是笔误,也可能用了未列于 Table 2 的基线,无法判定。
5. **贡献列表 3.5% 的口径未核实**。CronQuestions complex 绝对 3.4pp / 相对 3.94%,均不精确等于 3.5%;而同篇 §4.2 的 "2.1% relative improvement" 确实是相对值。3.5% 用的是哪种口径未说明。
6. **Table 5 的置信区间为我方计算**。论文只给 7.5%/4.0%,n=200/轮,不报任何区间或检验。Wilson 95% CI [4.6%,12.0%] 与 [2.0%,7.7%]、两比例 z=1.50(p≈0.13)**均为我方计算**。
7. **Figure 1–6 图内数值未核实**(位图)。具体未核实项:Figure 3 各题型 Hits@1 逐点值、Figure 4 各轮次逐点值(只知"MultiTQ 第 2 轮最优、CronQuestions 第 1 轮最优")、Figure 5 的 10k/50k/100k 具体数值(只知"随规模稳定上升、10k 明显更低")。
8. **TempoQR 与 TMA 为何缺席 Table 2 未核实**。二者在 §4.1 被列为基线却只出现在 Table 3;**也未核实 MultiQA 原论文(Chen et al. ACL 2023)是否报过 TempoQR on MultiTQ**,故不能断言是刻意省略。
9. **代码/数据是否发布未核实**。论文正文与 arXiv abs 页均无代码链接;**未另行搜索 GitHub**。"无代码"仅指"论文未给出"。
10. **自举超参 C 与 Max 的取值论文从未给出**。只知 MultiTQ 跑 2 轮 / CronQuestions 跑 1 轮;且 Algorithm 1 line 5 的 `while |F^t_i| ≥ C or i < Max` 与 §3.3.4 正文逻辑相反,**哪个是作者本意未核实**。
11. **LREC-COLING 2024 当年是否要求 Limitations 章节未核实**。本文确实**没有 Limitations 也没有 Ethics 节**(全文结构:1 Intro / 2 Related Work / 3 Methodology / 4 Experiments / 5 Conclusion / 6 Acknowledgements / 7–8 References / A Appendix A.1–A.6),但投稿要求未核实,故不能据此判定违规。本报告中所有"作者自陈的限制"均来自 §4.2、§4.4 正文。
12. **主表基座模型的判定是推断**。Table 2 的 Prog-TQA 行与 Table 6 的 Llama-13B 行逐位相同,§4.1 却写 vicuna-13B。"主表很可能用的是 Llama-13B"是**基于数字重合的推断**,作者未明确说明。

### 6.3 TimelineQA(16 条)

1. 开源仓库 `github.com/facebookresearch/TimelineQA` 是否仍包含生成器与**确切的 120-log 测试划分**——未访问核实。G1/G2/G4 的可执行性依赖于此。
2. **42 条复杂查询模板的完整清单**——论文只给了 4 条示例模板(§4.1.1),未枚举。G2 的划分设计依赖于此。
3. **42 条模板与 Table 6 四个题型桶(average/count/argmax/list)的映射关系**;特别是 "Did I go to X before I went to Y?" 这条 §4.1.1 明确列出的模板是否被生成进测试集。推断依据是四桶 n 加总恰为 4,284(= 测试集全量),暗示 before/after 题未被生成——**这是推断,不是原文陈述**。
4. **"argmax"桶(47.2%, n=1,668)是否包含 "When was the first/last time I X?" 这类时间维取极值题,还是只含数值 argmax**。这直接决定"时序关系落差"的宽度,本报告已按较保守(对作者较有利)的读法陈述。
5. **>1000 证据桶内部的实际截断率**。§5.1 只给测试集整体 20.40%;"约 90% 证据被丢弃"是用 1,169.8 条 × 8.4 token vs 1024 上限**推算**的,论文未报。M2 的量级依赖于此。
6. **>1000 证据桶(n=371)的事件类目构成**。E8 中"该桶很可能大比例是 chat 聚合题"是推测,论文未报。
7. **任何 retriever 的 recall@k**——论文全篇从未报告。§5.3 关于"微调检索器为何无用"的归因因此无法验证。
8. **逐密度(sparse/medium/dense)结果**。"论文中不存在"已核实(Table 4/5/6 逐行检查);但其数值未知。
9. **Tapex-large 59.0 vs Tapex-base 57.7 的 1.3pp 是否在运行间方差之内**——论文无方差报告;"不可区分"是断言而非测量。
10. **InstructGPT 的确切 checkpoint/快照**(text-davinci-00X 之类)——论文只引 Ouyang et al. 2022,正文与附录 C 均未给版本号。
11. **本文被引情况,以及 85.1%→4.3% 在下游被如何使用**(是否普遍被去掉了 oracle-retriever 与 1024-token 两个限定词)——未检索。
12. **QVF 读取侧能否实际跑在 TimelineQA 上**(六字段卡与 "time-and-space boxed episode" 的 schema 兼容性)——G4 与讲稿 Q2 中的这条属未测试的工程论断。
13. **生成器是否把"雇主/城市"存为可用作有效区间金标的区间**。Table 1 的 lifetime 时标列出 "jobs & relocation",但未核实生成器内部是否保有 start/end 使 G3 可直接构造 `valid(S,Q)` 金标。**G3 的可行性依赖于此。**
14. **对比中引用的 STALE / LongMemEval / QO-Bench / Prog-TQA / TReMu 的数字与定位**,取自项目核实档 `study_logs/QVF_related_work_verified_20260814.md`,本次**未重新核实原文**(按任务指示直接采信)。
15. **CLEVR-CoGenT 的存在与内容**(用于 M3 中削弱作者的 CLEVR 类比)取自既有知识,本次未核实原文。
16. §5.3 原文有一处笔误 "This simple pipeline works very well (near perfect) **for by** exploiting the generation pipeline" —— 已按字面转录,**未核实是否为出版版勘误**。

### 6.4 A-Mem(整篇未核实,7 条 + 1 条总纲)

> **总纲(最重要的一条):本报告 3.4 节全篇未取到全文。** 其 A–G 七镜内容为**结构性草案**,依据仅为打分结果中的定位理由与核实档的一句定位("与 QVF 固定契约相反的设计赌注:自组织笔记、结构由 LLM 涌现而非预先枚举")。**其 C/D/F 三条判决为倾向性判断,组会前必须补一次全文级精读方可宣讲;在补读前不得对外引用本报告中关于 A-Mem 的任何机制性陈述。**

1. **题名的完整形式、作者列表与所属机构未核实。**
2. **venue 未复核**:"NeurIPS 2025" 取自打分结果,未查 NeurIPS 2025 会议页或 OpenReview,**是否 main track、poster/spotlight/oral 均未核实**。
3. **贡献列表的逐字原文未取到**,故 A1 三条声称是**从定位反推的推断**,不是引文。
4. **memory evolution 是否会改写/覆盖旧笔记未核实**。这是本篇与 QVF 分界句的关键事实,也是与 APEX-MEM 正面对撞那段论述的前提;**若为"只增不改",3.4 节的 C5 分界句与讲稿 Q2 必须重写。**
5. **实验设置全部未核实**:评测基准(是否 LoCoMo)、backbone 数量、baseline 集合、是否报方差/CI、是否报成本三项(token/$/延迟)——一概未知。**因此 D 判决"部分"是基于同子领域三篇共同规律的先验推断,不是证据。**
6. **是否存在受控消融(去掉链接生成 / 去掉 memory evolution / 用固定 schema 替换 LLM 生成属性)未核实。** 这一条直接决定 C 判决是"中"还是可以更高。
7. **是否有任何未见组合 / 分布外泛化测量未核实。** 这一条决定它能否真的为 QVF 的 S8 反超提供机理证据,还是只能作为方向性对照叙事;**G1 对撞实验的设计需据此调整。**

### 6.5 跨篇的方法论未核实项(2 条)

1. **本报告所有 pp 差值均为对表内 verbatim 数字做减法**(已复算),但**原论文本身对同一差值的表述可能与之不符**(已知不符处:Prog-TQA 的 60.9 vs 59.1pp;APEX-MEM 的 3.3× vs 1.40×)。引用时一律以"我方复算值"标注,不以原文措辞为准。
2. **四篇的实际影响力与在下游被引用的方式均未检索**(仅 TimelineQA 一条已列入 6.3 第 11 项)。这影响"占走了什么"的现实强度判断——一篇发表但无人引用的论文对 QVF 的定位压力小于被广泛引用的论文,**本报告未做这一层加权**。

---

**报告完。**

