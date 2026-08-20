# Top3 排序(去重后)

候选池 19 条,去重 2 处(When Facts Change 与 ScienceMeter 各出现两次),实际 17 篇。复核情况:ChronoScope 与 Memory-R1 的 Anthology 页面今日已由我独立再抓取确认;OpenReview(含 API)今日被 Cloudflare 验证墙拦截,ICLR 两篇无法独立复验,只能依赖候选池中记录的 API 核实证据。

---

## 1. ChronoScope — Evaluating Temporal Consistency in Multi-Turn Language Models(ACL 2026 主会长文)

- **链接**:https://aclanthology.org/2026.acl-long.2133/ (作者 Atri, Johnson, Hartvigsen;今日独立复核通过)
- **推荐理由**:三项打分全满。接收硬度最高档(ACL 主会长文,Anthology 页独立复核两次通过);轴相关性是全池唯一的"命中问题本身"——对话早前建立的时间作用域在后续省略时间指涉的追问中还算不算数,即查询条件化有效性判定的行为学测量;且基准由 Wikidata 确定性生成的百万级问题链构成,与用户 wikistate(P54/P108/P551)管线方法论同源,组会听众可以零成本对上。内容量上,四类子设定、oracle context 消融(证明失败在推理不在检索)、交互长度递增分析、多模型横评、代码数据公开,20 分钟讲不完只能删。
- **风险**:与用户自己的工作**太**同源——组会最可能被问的是"这和你的 wikistate 有什么区别",必须提前把分界讲清;另外百万题链是模板确定性生成,题目同质性高,"100万"的规模数字含金量有限,汇报时别把规模当卖点。接收证据无忧。
- **与 QVF 的分界句**:"ChronoScope 证明的是即使证据摆在眼前,模型也会把早前确立的时间作用域漂回'现在时'默认——它诊断了这个失败并测量了它;QVF 做的是不指望模型自己扛住这件事,在取用层前置一个显式的查询条件化有效性判定,把时序作用域从模型的隐式推理负担变成系统的显式路由决策。"

---

## 2. Memory-R1 — RL for Memory Management and Utilization(ACL 2026 主会长文)

- **链接**:https://aclanthology.org/2026.acl-long.583/ (pp. 12805–12825;今日独立复核通过)
- **推荐理由**:接收硬度同为最高档且已独立复核。轴相关性正面命中"过期/取代"子轴:用 RL 学出 ADD/UPDATE/DELETE/NOOP 的结构化记忆操作,即让系统学会判定旧记录是被更新、作废还是继续有效;Answer Agent 再对检索条目做查询条件化筛选,恰好覆盖轴的两端(写入侧取代 + 读取侧判定)。内容量足:双 agent 架构、PPO/GRPO 对比、152 条训练样本即泛化、LoCoMo/MSC/LongMemEval 三基准、3B–14B 多尺度——且 LoCoMo 与 LongMemEval 都是用户已在跑或已精读的基准,对比成本极低。
- **风险**:论文重心是"RL 能学会记忆操作"这个训练故事,而非有效性判定的机制分析——判定质量本身(UPDATE/DELETE 打得准不准、错在哪类时序关系上)未必有细粒度剖析,20 分钟里"与轴强相关的部分"可能只占论文一半;152 样本泛化的说法也容易被组会质疑外部效度。
- **与 QVF 的分界句**:"Memory-R1 在写入时刻就用学出来的 DELETE/UPDATE 把记忆库改成'当前正确'的样子,判定错误会永久销毁历史;QVF 保留全部原始记录,把有效性判定推迟到查询时刻、以当前问题为条件裁决——写入侧不可逆改库 vs 读取侧可回溯判定,是两条路线的根本分界,也是我们能做时序回溯题而它不能的原因。"

---

## 3. Memory-T1 — RL for Temporal Reasoning in Multi-session Agents(ICLR 2026 Poster)

- **链接**:https://openreview.net/forum?id=vQf2YR2Kpd
- **推荐理由**:全池轴相关性最高的一篇——它就是"查询条件化时序有效性判定"的可学习实现:coarse-to-fine 剪枝后由 RL 策略精选证据,奖励函数里显式内建 session 级与 utterance 级的时间一致性对齐,等于把 QVF 想用规则/路由做的事整个交给策略学。7B 超 14B 基线 10.2%、时间一致性奖励贡献 15.0% 的消融、128k 噪声鲁棒性分析,方法/实验/消融三块齐,20 分钟够。作为与 QVF 的"可学习 vs 显式判定"对照,是三篇里最能引出讨论的。
- **风险**:三项里最实的一条风险在接收证据——候选池记录了经 OpenReview API 按 ICLR.cc/2026/Conference group 核实 venue="ICLR 2026 Poster",但今日我复核时 OpenReview 网页与 API 均被验证墙拦截,**无法独立再证**,汇报前建议自己再开一次页面确认;其次 poster 档低于 ACL 主会长文;再次主实验落在 Time-Dialog 这一个(疑似自建)基准上,外部效度弱于前两篇。
- **与 QVF 的分界句**:"Memory-T1 把时序有效性判定折进端到端 RL 策略的权重里,判定存在但不可读——错了只能重训;QVF 把同一判定做成显式、可审计的符号步骤(时序代数、闭区间约定),每个判定错误都能定位到具体一步——可学习黑盒与可检验白盒的取舍,是我们与它的分界,也是组会上值得辩的问题。"

---

## 落选说明(最接近的几篇差在哪)

- **ICF-Bench(ICLR)**:"记忆强≠遗忘强"的发现与导师"时序感知不敏感"叙事最合拍,但同受 OpenReview 不可复核问题,且纯评测、无方法,内容厚度逊于 Memory-T1。
- **Unable to Forget(COLM)**:机制级最漂亮(PI 范式、log-linear 定律),可解释用户长链 wt 题脆弱性;差在 COLM 证据是接收列表 HTML 而非论文页(硬度略低一档),且它讲的是模型内在工作记忆极限,离"对话记忆系统"应用层隔一步。
- **Locomo-Plus(ACL 主会)**:与用户在跑的 LoCoMo 直接衔接,但轴命中的是隐式约束生效面,离"时序/取代"核心稍偏,作为 Top3 之外的第一替补。
- 候选池中无 NAACL 2026 论文;PAMU 内容偏薄,LOKA/ScienceMeter/When Facts Change 属参数记忆侧,汇报需自行搭桥,均不进前三。

---

# 附:完整候选池(17 篇,接收证据均经亲核)

## Evaluating Temporal Consistency in Multi-Turn Language Models (ChronoScope)
- 链接:https://aclanthology.org/2026.acl-long.2133/ | arXiv: https://arxiv.org/abs/2604.23051
- 接收证据:已亲自打开 https://aclanthology.org/2026.acl-long.2133/ 核实:Anthology ID 2026.acl-long.2133,Volume 显示 Proceedings of the 64th Annual Meeting of the ACL (Volume 1: Long Papers),Year 2026,San Diego——ACL 2026 
- 轴相关:轴心命中:研究'时序作用域稳定性'——对话早前建立的时间范围假设,在后续省略时间指涉的追问里还算不算数(implicit carryover / 显式换域 / 跨实体迁移 / 长轨迹),发现模型系统性漂移回'现在时'默认。这正是查询条件化的记忆有效性判定;且基准由 Wikidata 确定性生成的百万级问题链构成,与用户 wikistate(P54/P108/P551)状态链管线方法论同源
- 内容量:100 万+确定性生成问题链、四类子设定各自独立测量、oracle context 消融证明失败不在检索而在推理、交互长度递增分析、多个 SOTA 模型横评,代码数据公开(github.com/yashkumaratri/ChronoScope)——机制+失败模式+消融俱全,20 分钟绰绰有余

## Memory-R1: Enhancing Large Language Model Agents to Manage and Utilize Memories via Reinfo
- 链接:https://aclanthology.org/2026.acl-long.583/ | arXiv: https://arxiv.org/abs/2508.19828
- 接收证据:已亲自打开 https://aclanthology.org/2026.acl-long.583/ 核实:Anthology ID 2026.acl-long.583,Volume 为 Proceedings of the 64th ACL (Volume 1: Long Papers) 2026,页码 12805–12825,DOI 10.18653/v1/2026.acl-long.583
- 轴相关:轴心命中'记忆过期/取代':用 RL 学出 Memory Manager 的 ADD/UPDATE/DELETE/NOOP 结构化操作——即让模型自己学会判定旧记录是被更新、被作废还是继续有效,而非启发式规则;Answer Agent 再学对检索条目做筛选推理(查询条件化的取用)。直接对标用户 QVF 的记忆有效性判定臂
- 内容量:双 agent 架构、PPO 与 GRPO 两种训练对比、仅 152 个训练 QA 即泛化、LoCoMo/MSC/LongMemEval 三基准、3B–14B 多尺度,操作级 ablation 可讲——方法+实验体量足够 20 分钟

## Locomo-Plus: Beyond-Factual Cognitive Memory Evaluation Framework for LLM Agents
- 链接:https://aclanthology.org/2026.acl-long.1150/ | arXiv: https://arxiv.org/abs/2602.10715
- 接收证据:已亲自打开 https://aclanthology.org/2026.acl-long.1150/ 核实:Anthology ID 2026.acl-long.1150,Volume 为 Proceedings of the 64th ACL (Volume 1: Long Papers) 2026,页码 25085–25100,DOI 10.18653/v1/2026.acl-long.115
- 轴相关:轴心命中'旧记录对当前问题算不算数'的隐式面:cue–trigger 语义断连设定下,早期埋下的用户状态/目标/约束在后续查询未显式提及时是否仍应生效并约束回答;并论证 string-matching 指标在此失真,提出约束一致性评测框架。用户已在跑 LoCoMo(locomo_chain_spotcheck),此文是其直接升级,对比成本极低
- 内容量:新基准构建方法 + 指标失真分析 + 约束一致性统一评测框架 + 跨骨干模型/检索方法/记忆系统的三层实验矩阵,代码公开(github.com/xjtuleeyf/Locomo-Plus)——benchmark 论文标准三段式,20 分钟正好讲透

## Inside Out: Evolving User-Centric Core Memory Trees for Long-Term Personalized Dialogue Sy
- 链接:https://aclanthology.org/2026.acl-long.614/ | arXiv: https://arxiv.org/abs/2601.05171
- 接收证据:已亲自打开 https://aclanthology.org/2026.acl-long.614/ 核实:Anthology ID 2026.acl-long.614,Volume 为 Proceedings of the 64th Annual Meeting of the ACL (Volume 1: Long Papers),Year 2026,San Diego——ACL 2026 主会长
- 轴相关:轴心命中'状态链+知识更新'在对话侧的实现:PersonaTree 以 schema 约束的树承载用户长期画像,RL 训练的轻量 MemListener 产出可执行的 ADD/UPDATE/DELETE/NO_OP 操作驱动画像动态演化——即用户属性状态链(类比用户 wikistate 的 P551 居住地/P108 雇主链)的取代与过期管理,附带过程奖励的操作正确性监督
- 内容量:树结构设计 + process-based reward 的 RL 训练 + 双模式生成(低延迟直取 vs agentic 按需展开)+ 对全文拼接与多记忆系统的对比 + 小模型操作决策对标 DeepSeek-R1/Gemini-3-Pro——机制层次多,20 分钟可讲出取舍

## When Facts Change: Temporal Knowledge Conflict Resolution in LLMs
- 链接:https://aclanthology.org/2026.findings-acl.103/
- 接收证据:https://aclanthology.org/2026.findings-acl.103/ — 亲自打开核实:venue 字符串为 Findings of the Association for Computational Linguistics: ACL 2026,作者 Jonas Wallat, Wolfgang Nejdl, Sandipan Sikdar,页码 2154–2184
- 轴相关:正面命中知识更新轴:研究训练截止后事实已变时,LLM 如何在过期参数记忆与检索到的新上下文之间裁决(temporal misalignment 下的 context–memory conflict),并提出新基准 WIKIRECENTCHANGES(稳定事实 vs 近期更新事实对照),考察'事实可变性 mutability'能否作为判定旧知识是否还算数的信号——这正是'旧记录对当前问题算不算数'在参数记忆侧的镜像问题,可直接对照用户在对话记忆侧的 stale/supersede 判定机制
- 内容量:31 页(2154–2184):自建时序对照基准 + 多模型冲突裁决实验 + mutability 信号分析,机制假设-基准构造-验证链条完整,够撑 20 分钟并能引出与自研 QVF 时序判定的逐点对比

## TiMem: Temporal-Hierarchical Memory Consolidation for Long-Horizon Conversational Agents
- 链接:https://aclanthology.org/2026.findings-acl.1091/
- 接收证据:https://aclanthology.org/2026.findings-acl.1091/ — 亲自打开核实:venue 字符串为 Findings of the Association for Computational Linguistics: ACL 2026,页码 21700–21720,代码库 github.com/TiMEM-AI/timem
- 轴相关:长程对话记忆的时序组织机制:提出 Temporal Memory Tree,把原始对话观察按时间层级逐级固结为抽象画像表示,直指现有记忆框架'时序结构支持不足→记忆碎片化、长程人格化不稳定'的问题——即用时序层级决定哪一层记忆对当前查询有效,与用户的状态链/时序感知记忆检索直接同轴
- 内容量:21 页 + 开源代码:TMT 结构设计、逐级固结算法、LoCoMo 75.30% / LongMemEval-S 76.88% 双基准 SOTA、召回记忆长度大幅缩减的效率分析——方法+双基准+效率三块材料,20 分钟内容充足

## ACR: Adaptive Context Refactoring via Context Refactoring Operators for Multi-Turn Dialogu
- 链接:https://aclanthology.org/2026.findings-acl.155/
- 接收证据:https://aclanthology.org/2026.findings-acl.155/ — 亲自打开核实:venue 字符串为 Findings of the Association for Computational Linguistics: ACL 2026,作者 Jiawei Shen 等 12 人
- 轴相关:多轮对话中的状态漂移(state drift)与上下文惰性(contextual inertia)问题:模型难以与早先确立的信息保持一致、跨多轮追踪依赖、随交互变长漂入错误事实——正是'状态链维护失败'的机制刻画;其方案是用重构算子库动态监控并重写交互历史,把上下文管理与推理解耦,可与用户的记忆有效性判定(判定后重写 vs 判定后过滤)做机制对比
- 内容量:算子库设计 + teacher-guided 自进化训练范式(学 when to intervene / how to refactor)+ 多轮对话实验 + token 消耗下降的成本分析,方法-训练-实验-成本四段结构,够 20 分钟

## Task Matters: Knowledge Requirements Shape LLM Responses to Context–Memory Conflict
- 链接:https://aclanthology.org/2026.findings-acl.202/
- 接收证据:https://aclanthology.org/2026.findings-acl.202/ — 亲自打开核实:venue 字符串为 Findings of the Association for Computational Linguistics: ACL 2026,作者 Kaiser Sun, Fan Bai, Mark Dredze,页码 4154–4176
- 轴相关:知识更新轴的条件化视角:上下文与参数记忆冲突时模型信谁,取决于任务对知识的依赖类型与程度——性能退化与任务知识依赖相关而非冲突本身;解释性 rationale 会推高对上下文的依赖,对有的任务是修复、对另一些是伤害。这与用户'查询条件化'的核心命题同构:同一条(旧)信息是否该被采信,答案依查询/任务而变,不存在全局判定。注意:载体是参数记忆 vs 上下文,不是对话记忆,汇报时需自己搭桥
- 内容量:23 页(4154–4176):诊断框架 + 跨任务系统实验 + rationale 干预实验 + 对 model-based evaluation 偏差的连带发现,三条主发现层层递进,20 分钟够用

## Memory-T1: Reinforcement Learning for Temporal Reasoning in Multi-session Agents
- 链接:https://openreview.net/forum?id=vQf2YR2Kpd
- 接收证据:https://openreview.net/forum?id=vQf2YR2Kpd — OpenReview 官方记录 venue="ICLR 2026 Poster"、venueid=ICLR.cc/2026/Conference(经 api2.openreview.net/notes/search 按 ICLR.cc/2026/Conference group 检索原始 JSON 亲自核实,
- 轴相关:正中轴心:用 RL 学一个 time-aware memory selection policy,决定多会话对话史里哪些旧记录对当前问题在时间上有效。机制是 coarse-to-fine——先用时间过滤器+检索器剪出候选集,再由 RL agent 精选证据;奖励函数三层(答案准确、证据落地、时间一致性),其中时间一致性奖励在 session 级(时间范围邻近)和 utterance 级(证据密度)双层对齐,专门解决时序歧义。这就是'查询条件化记忆有效性判定'的可学习版本,可直接对照用户的 QVF 路由/判定思路。
- 内容量:够 20 分钟:完整方法(剪枝管线+RL 策略+多层奖励设计)、Time-Dialog 基准上 7B 模型 67.0% 超 14B 基线 10.2%、消融(时间一致性+证据落地奖励合计贡献 15.0%)、128k token 噪声鲁棒性分析(基线崩溃而它不崩)。方法/实验/消融三块齐全。

## Do LLMs Forget What They Should? Evaluating In-Context Forgetting in Large Language Models
- 链接:https://openreview.net/forum?id=hcJywRYc3n
- 接收证据:https://openreview.net/forum?id=hcJywRYc3n — OpenReview 官方记录 venue="ICLR 2026 Poster"、venueid=ICLR.cc/2026/Conference(经 api2.openreview.net/notes/search 原始 JSON 亲自核实)
- 轴相关:正中'记忆过期/取代'子轴:定义 In-Context Forgetting——不改参数、纯上下文内选择性作废干扰/失效信息同时保留有用知识,即'旧记录对当前问题不算数'的判定能力本身。ICF-Bench 用 2k 条带标注的多轮对话测这件事。三个发现里最有分享价值的是:记忆能力强不等于遗忘/作废能力强(两者不对称)——直接支持'有效性判定是独立于检索记忆的另一种能力'这一叙事,和用户'时序感知不敏感'的框架呼应。
- 内容量:够 20 分钟:基准构建方法(多场景、2k 多轮对话、标注体系)、多个前沿 LLM 的系统实验、三条主发现(干扰存在时性能骤降;记忆-遗忘不对称;上下文长度对 ICF 的场景依赖效应),外加隐私/适应性讨论。代码数据开源(anonymous.4open.science/r/ICF-Bench-B1C7)。

## Beyond a Million Tokens: Benchmarking and Enhancing Long-Term Memory in LLMs
- 链接:https://openreview.net/forum?id=y59hf5lrMn
- 接收证据:https://openreview.net/forum?id=y59hf5lrMn — OpenReview 官方记录 venue="ICLR 2026 Poster"、venueid=ICLR.cc/2026/Conference(经 api2.openreview.net/notes/search 原始 JSON 亲自核实)
- 轴相关:轴相关(评测+方法双面):BEAM 基准自动生成最长 10M token 的连贯多话题长对话,探测问题覆盖广谱记忆能力(超越单纯 recall,含随对话演进的信息追踪),核心发现是 1M 上下文窗口模型(含 RAG)随对话变长照样失效——即长对话里'哪些旧信息对当前问题仍算数'不是上下文长度能解决的。配套方法 LIGHT 用三重记忆(情景长期记忆+工作记忆+要点 scratchpad)提升 3.5%–12.69%,其记忆分层设计可与用户的 QVF 臂结构对照。
- 内容量:够 20 分钟:对话自动生成框架、BEAM(100 对话/2000 验证过的问题)、LIGHT 三组件方法、跨多个 backbone 的主实验、逐组件消融。基准构建+机制设计+失效分析三条线都能讲。

## Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions
- 链接:https://openreview.net/forum?id=DT7JyQC3MR
- 接收证据:https://openreview.net/forum?id=DT7JyQC3MR — OpenReview 官方记录 venue="ICLR 2026 Poster"、venueid=ICLR.cc/2026/Conference(经 api2.openreview.net/notes/search 原始 JSON 亲自核实)
- 轴相关:轴相关(评测框架):MemoryAgentBench 把记忆代理的核心能力拆成四项——精确检索、test-time learning、长程理解、selective forgetting;后两项直接对应用户轴——selective forgetting 测被更新/取代信息的作废处理,增量多轮注入的设定(信息逐轮累积而非一次性给长上下文)正是长期对话记忆的真实形态,查询必须以'当前状态'为条件作答。结论:现有方法(长上下文/RAG/外置记忆模块/工具集成代理)没有一家四项全能。
- 内容量:够 20 分钟:四能力框架的动机(记忆科学/认知科学)、既有长上下文数据集的多轮化改造+新建数据集、对从简单 RAG 到带外置记忆模块的多类记忆代理的横向评测、按能力维度的失效分析。适合作为'评测这条轴该怎么设计'的方法论分享。

## Unable to Forget: Proactive Interference Reveals Working Memory Limits in LLMs Beyond Cont
- 链接:https://arxiv.org/abs/2506.08184 | arXiv: 2506.08184
- 接收证据:COLM 2026 主会 accepted papers 列表 https://colmweb.org/AcceptedPapers.html — 我下载了原始 HTML 亲自核实:页面 <title> 为 "COLM 2026: Accepted Papers",标题逐字命中,作者 Chupei Wang, Jiaqiu Vince Sun 与 arXiv 2506.08184 一致;并用 CO
- 轴相关:与轴的机制级对应最直接:PI-LLM 范式按顺序流入同键的 key-value 更新,只问最终值——即"旧记录被取代后对当前问题不再算数"的最小化实验。发现检索准确率随干扰量 log-linear 跌向零,错误恰是取回已被覆盖的旧值;提示工程(叫模型忽略先前输入)基本无效。这正是查询条件化有效性判定失败的模型侧根因:状态链越长,当前值检索越不可靠——可直接解释用户 QVF 项目中乱序/长链条件下 wt 类题的脆弱性,并为"为什么需要外部有效性判定而非指望模型自己压制过期记忆"提供论据
- 内容量:够 20 分钟:认知科学 PI 范式迁移设计、受控干扰量操纵、跨多模型的 log-linear 定律、错误类型分析(取回被覆盖值)、多种 prompt 缓解尝试及其失败、与 context length 解耦的论证;可延伸讨论对记忆系统设计的含义

## ScienceMeter: Tracking Scientific Knowledge Updates in Language Models
- 链接:https://arxiv.org/abs/2505.24302 | arXiv: 2505.24302
- 接收证据:COLM 2026 主会 accepted papers 列表 https://colmweb.org/AcceptedPapers.html — 原始 HTML 中标题逐字命中,作者 Yike Wang, Shangbin Feng, Yulia Tsvetkov, Hannaneh Hajishirzi 与 arXiv 2505.24302 一致;页面标题为 COLM 2026 且经旧年份论文
- 轴相关:知识更新轴的系统性评测框架:把"更新后旧知识算不算数"拆成三个可测度——knowledge preservation(旧知识保留 85.9% 上限)、acquisition(新知识习得仅 71.7%)、projection(向未来相关命题泛化仅 37.7%),对五类更新方法(含训练式与检索式)统一度量。与用户"记忆过期/取代"问题同构:更新操作后新旧知识的共存与冲突正是查询条件化有效性的知识编辑侧镜像
- 内容量:够 20 分钟:三指标框架定义、十个科学领域的数据集构建、claim judgment + generation 两类任务、五种代表性更新方法的横向对比、preservation/acquisition/projection 的 trade-off 分析

## Back to Basics: Let Conversational Agents Remember with Just Retrieval and Generation
- 链接:https://arxiv.org/abs/2604.11628 | arXiv: 2604.11628
- 接收证据:COLM 2026 主会 accepted papers 列表 https://colmweb.org/AcceptedPapers.html — 原始 HTML 中标题逐字命中,作者 Yuqian Wu, Wei Chen 等与 arXiv 2604.11628 一致;页面标题为 COLM 2026 且经旧年份论文缺席检验
- 轴相关:用户的确切应用场景(长期对话记忆)+ 查询条件化选证:诊断出 Decisive Evidence Sparsity(会话越长,决定性证据越孤立,聚合/摘要式记忆系统骤降)与 Dual-Level Redundancy(跨会话干扰 + 会话内废话),然后用 Turn Isolation Retrieval(turn 级 max-activation 取代全局聚合)+ Query-Driven Pruning(按当前 query 剪掉冗余会话与 filler)构建紧凑证据集——即"哪些旧记录对当前问题算数"的检索侧实现,并论证复杂分层摘要记忆架构可能是伪需求
- 内容量:够 20 分钟:两个受控实验诊断现象、极简方法(TIR+QDP)设计、多长对话记忆基准的横向对比、token/延迟效率报告(契合用户成本汇报习惯)、对"记忆架构 vs 信号稀疏"的立场之争可引发讨论

## PM-Bench: Evaluating Prospective Memory of LLM Agents
- 链接:https://arxiv.org/abs/2607.12385 | arXiv: 2607.12385
- 接收证据:COLM 2026 主会 accepted papers 列表 https://colmweb.org/AcceptedPapers.html — 原始 HTML 中标题逐字命中(列表作 "of LLM Agents",arXiv v1 作 "in LLM Agents",同一论文),作者 Genglin Liu, Saadia Gabriel 与 arXiv 2607.12385 一致;页面标题
- 轴相关:时序状态追踪轴的前瞻侧:prospective memory 是"存下的意图何时变为有效/到期"——记忆有效性由未来时点或环境状态条件触发,与用户"旧记录对当前问题算不算数"互为镜像(当前问题对未来记录何时算数)。基于认知科学 Virtual Week 范式的七天模拟中,agent 须在持续任务干扰下追踪潜在环境变化并判断延迟任务是否到期——本质是跨时间的状态链维护与到期判定
- 内容量:够 20 分钟:Virtual Week 范式设计、维持意图/延迟执行/潜在环境变化监测三种能力拆解、8 个 SOTA 模型 x 8 种 agent 配置的矩阵实验、最佳配置仅 65.1% F1 的失败分析、无单一策略跨模型占优的发现

## When Facts Change: Temporal Knowledge Conflict Resolution in LLMs (Wallat, Nejdl, Sikdar)
- 链接:https://aclanthology.org/2026.findings-acl.103/
- 接收证据:https://aclanthology.org/2026.findings-acl.103/ — 亲自打开核实,页面标注 Findings of the Association for Computational Linguistics: ACL 2026
- 轴相关:正面回答'旧记录对当前问题算不算数':RAG 场景下检索内容比参数化记忆更新,冲突源头是时间错位(事实在 cutoff 后变了)。构建 WIKIRECENTCHANGES 基准(Wikidata 稳定事实 vs 近期变更事实),核心发现是可变性判定与最终预测脱节——模型会对已变更事实自发产生时序推理,但该判断几乎不传导到答案;规模依赖:小模型察觉不到冲突,大模型察觉了却不据此行动。这就是查询条件化有效性判定的失效机制分析。
- 内容量:够 20 分钟:基准构建方法(稳定/变更事实对照)、多模型多规模对比、显式提示可变性的干预实验(引用时序变化增多但准确率不升)、verbalized reasoning 与 prediction 行为脱节的分析,可与用户自己的 wikistate/时序状态追踪实验直接对照。

## LOKA: Conflict-Aware LLM Knowledge Update with Adaptive Knowledge Memory (Zhang, Chen, Zhe
- 链接:https://aclanthology.org/2026.acl-long.760/
- 接收证据:https://aclanthology.org/2026.acl-long.760/ — 亲自打开核实,页面标注 Proceedings of the 64th Annual Meeting of the ACL (Volume 1: Long Papers), July 2026,即 ACL 2026 主会长文
- 轴相关:把知识更新框定为'删旧+增新'必须同时做且互相冲突的问题(与记忆过期/取代轴同构)。机制:训练期把更新知识分配到多个自适应记忆单元,推理期检索最相关单元与原模型融合,并用学习型 router 按查询决定是否激活知识记忆——即按 query 条件化地判定'更新后的知识对这个问题是否生效',与用户的路由式 QVF 架构有直接可比性。
- 内容量:主会长文,含框架设计(记忆单元分配+路由激活)、理论分析、冲突感知更新的实证实验;机制、消融、对比齐全,撑 20 分钟没问题。

## ScienceMeter: Tracking Scientific Knowledge Updates in Language Models (Wang, Feng, Tsvetk
- 链接:https://arxiv.org/abs/2505.24302 | arXiv: 2505.24302
- 接收证据:https://colmweb.org/AcceptedPapers.html — 亲自打开核实,该页为 COLM 2026 接收论文列表(colmweb.org 首页确认站点为 COLM 2026,2026-10-06~09 旧金山),列表中含此标题
- 轴相关:知识更新有效性的量化评测框架:沿过去/现在/未来三轴定义 knowledge preservation(旧知识保留)、acquisition(新知识习得)、projection(未来知识外推)三指标——精确刻画'更新后旧记录还算不算数、新记录是否真生效'的权衡。最佳更新方法也只能保留 85.9% 旧知识、习得 71.7% 新知识、外推 37.7%,证明更新机制普遍不可靠。
- 内容量:框架+三指标定义+跨多种更新方法(含续训/微调/检索式)与专业科学 LLM 的大规模实验,有具体数字可讨论;是参数化知识更新而非会话记忆,分享时可作为轴的'参数侧'对照。

## Preference-Aware Memory Update for Long-Term LLM Agents (Sun, Zhang, Zeng)
- 链接:https://aclanthology.org/2026.findings-acl.38/ | arXiv: 2510.09720
- 接收证据:https://aclanthology.org/2026.findings-acl.38/ — 亲自打开核实,页面标注 Findings of the Association for Computational Linguistics: ACL 2026, pp. 783–793
- 轴相关:直指长期代理记忆系统'重存取、轻更新'的缺口:提出 PAMU,用滑动窗口均值+指数移动平均融合出偏好表征,检测偏好漂移并据此刷新记忆——旧偏好记录随时间衰减/被取代,即偏好维度上的记忆过期判定。与用户轴的'状态链/取代'吻合,但对象是偏好而非事实状态。
- 内容量:11 页 Findings:机制(SW+EMA 融合)+ LoCoMo 上 5 任务场景 × 5 基线;够撑 20 分钟但四篇中体量最薄,机制偏统计启发式,适合作为备选而非首选。
