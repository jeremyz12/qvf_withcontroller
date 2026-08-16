# QVF 相关工作精读核实档案(2026-08-14)

> 方法:六组并行精读,每篇用 WebFetch 打开 arXiv 摘要页/HTML 原文,venue 经 dblp/ACL Anthology 交叉核实;共 30 篇,编号全部核实(仅一篇内部代号需补齐为 2606.01435)。
> 用途:**论文相关工作措辞与 bib 的唯一依据**,取代 2026-08-14 浅查新(QVF_novelty_audit_20260814.md)中与本档冲突的二手结论。

---

## 一、改变先前结论的五处判决

1. **A-TMA 由 killed 改判 partial**:深读确认它止于检索排序与证据打标(query profiler 四类=规则计数,证据打标后仍交 LLM 直接作答);**无算子编译、无聚合算子、无 premise_check、无管线级路由、不建自己的事实表**。但它已有"按问题时序意图选状态视图"的隔离消融(−Retrieval Controller/−QA Label,0.883 vs 宿主 0.825)——该思想的首创权与价值量化不归我们。
2. **PRA 不是 COLM 2026 主会论文**:arXiv 2606.01435,实为 **COLM 2026 Lifelong Agent Workshop poster**;v2(2026-08-02)已改题 "Reliable Post-Retrieval Assembly for Agent Memory"(v1 原题 "Don't Ask the LLM to Track Freshness")。其冲突消解=arg max version-serial,查询盲概括**准确**;且作者自陈不处理 historical queries/temporal reasoning,LongMemEval 上自认无优势。
3. **"Mem0 论文自认时间类最弱"不成立**:原文无自认表述,反而称图变体擅长时序;LOCOMO 表里基线 Mem0 最弱类是**多跳(J 51.15)**,时序 55.51 倒数第二。可用的机制性陈述:附录算法 1 明确 UPDATE 为置换 M←(M∖{m_i})∪{…}、DELETE 物理删除,被取代值退出可检索存储(仅图变体 Mem0g 失效标记保历史)。另:**Mem0 已被 ECAI 2025 正式接收(条目 M7532),不能再写 preprint**。
4. **Zep 保时间线成立、读取侧无查询条件化成立**:双时态四时间戳+失效标记保历史;读取=cosine+BM25+图 BFS+重排,把 "FACT (Date range: from - to)" 整包交答题 LLM 自行取舍,论文通篇无按问题时序范围选版本的环节、无聚合算子。**限定词纪律:所有分界句加"论文所述系统"**(Zep 产品 API 有日期过滤参数、MemGPT 开源实现有 conversation_search_date,论文均未述)。
5. **"承认跨会话计数失败 30% R@10/0% R@1"属 Graph-Native Bitemporal Store(2607.26520),不是 Engram**(Engram 的聚合弱项是 79.3%,未崩塌)。两者别写混。

## 二、分组明细(verified / venue / 分界句)

### A. 并行工作(状态感知读取;全部为同期预印本,须标注 concurrent preprint)

| 论文 | 编号(核实) | venue | 分界句 |
|---|---|---|---|
| A-TMA | 2607.01935 ✔ | arXiv preprint(2026-07) | 规则计数的四类查询画像为宿主记忆做检索排序与证据打标,打标证据仍交 LLM 直接作答;不编译算子计划(无计数/最长/join/前提纠错),无管线级路由;QVF 恰在其止步处开始 |
| StateAuditor | 2608.01619 ✔ | arXiv preprint(2026-08-03) | 生成**之后**从存储状态反向审计草稿隐含前提(VALID/STALE/UNKNOWN,引用校验为 ≥80% token 重合非逐字),全量审计在无冲突样本上过度重写率 80%;QVF 的 premise_check 在**答前**读取计划内由代码纠前提、经路由只对需要的问题启用——管线相反两端,互补而非重叠 |
| Theanine | 2406.10996 ✔ | **NAACL 2025 正式接收** | 不删旧记忆、图上链时间线,但读取是 LLM 时间线摘要精炼后直接生成——纯神经,无查询分类、无可代码执行算子;是 trajectory 类的神经近邻 |
| EMem | 2511.17208 ✔ | arXiv preprint(work in progress) | EDU 是**轻度改写**命题(非逐字子串),溯源仅供检索/引用、无机械审计,不处理事实更新与取代 |

### B. 在售系统

| 论文 | 编号 | venue | 分界句 |
|---|---|---|---|
| Zep/Graphiti | 2501.13956 ✔ | arXiv preprint | 同样以双时态失效标记保留取代历史,但论文所述读取侧是语义/BM25/图遍历+重排,把带日期区间的事实整包交答题模型自行裁决,无按问题时序范围的查询条件化编译、无历史聚合算子。旁证:LongMemEval TR 仅 62.4%(gpt-4o)、single-session-assistant 反降 17.7% |
| Mem0 | 2504.19413 ✔ | **ECAI 2025**(M7532) | 基线 UPDATE 置换旧文本、DELETE 物理删除(附录算法 1),被取代值退出可检索存储——维护当前态快照而非可查询时间线;LOCOMO 时序 J 55.51 低于其单跳 67.13(最弱类实为多跳 51.15) |
| MemGPT | 2310.08560 ✔ | arXiv preprint(从未过审) | OS 式分层解决容量问题,论文未定义任何时态语义;工作上下文改写即覆盖,原始日志留存≠可查询时间线 |

**"唯一保时间线"替换措辞(经原文支撑,已批准入文)**:"既有系统中,Zep 与 Mem0 的图变体同样以失效标记保留取代历史,但其论文所述读取侧停留在相似度检索与重排,把带日期标注的事实整包交由答题模型自行取舍;据我们所知,QVF 是首个把问题编译为可执行时序查询计划——由代码而非答题模型完成版本选择(最新值/历史值/全链)与历史聚合(计数/时长/轨迹)——的会话记忆系统。"

### C. 取最新策略(+54.5pp 的对照方)

| 论文 | 编号 | venue | 要点 |
|---|---|---|---|
| PRA(现题 Reliable Post-Retrieval Assembly) | **2606.01435** | **COLM 2026 Lifelong Agent Workshop poster**(非主会) | 冲突消解=查询盲 arg max version-serial;单跳强(82-93%)、多跳弱(27-41%);自陈不处理历史查询/时序聚合/偏序,LongMemEval 无优势 |

**+54.5pp 措辞改向**:写成"量化'最新值优先'策略在时序题型上的**覆盖代价**——我们胜在它明言不做的题型上",不写"击败它"。复现适配须注明:以 stated_date 代 version serial。

### D. 编译-执行范式近邻

| 论文 | 编号 | venue | 分界句 |
|---|---|---|---|
| Prog-TQA | 2404.01720 ✔ | LREC-COLING 2024 | LLM 编译 KoPL 程序(12 算子,时间过滤/取值)在**给定时序 KG** 上符号执行;范式共享,分野在库来源(给定 vs 对话在线抽取)与算子语义(KG 四元组过滤 vs 槽位状态演化) |
| TReMu | 2502.01630 ✔ | **Findings of ACL 2025**(2025.findings-acl.972) | 同域最近:多会话对话+neuro-symbolic;但记忆=按会话时间线**文本摘要**、推理=LLM 生成**自由 Python** 日期算术、取证=LLM 检索、评测=多选题;QVF:结构化事实表+闭集 JSON 计划+确定性执行+逐条日期引用+小模型 |
| TimelineQA | 2306.01069 ✔ | Findings of ACL 2023(Meta) | 诊断基准:检索式 QA 在个人时间线聚合题上随证据数从 85.1% 崩到 4.3%;最优 table QA 须**金标事件集**才 59.0%。QVF 恰补其空位(写入契约自建事实表替代金标事件集+算子执行替代 table QA)。**不能引成"table QA 解决了聚合"** |
| TGMS | 2607.10265 ✔ | arXiv preprint(2026-07,单作者) | 形态最同构:LLM 只做规划(JSON 算子 DAG)+报告,13 闭集时态算子+静态/声明双重验证;但吃预加载图数据、算子面向图拓扑(可达性/模体/突发)、无路由。且其声明验证器(重执行核对)比我们的引用纪律**更强**——"逐条日期引用"应表述为轻量证据纪律,不作验证机制贡献 |
| Engram | 2606.09900 ✔ | arXiv preprint | 写入侧理念相近(双时态+supersession 链),读取侧四信号混合检索交 LLM 心算;自认最弱类恰是 multi-session aggregation(79.3%) |
| Graph-Native Bitemporal Store | 2607.26520 ✔ | arXiv preprint(2026-07-29) | 双时态 Neo4j 写入做对了,读取仅检索+LLM;**自证跨会话计数类 30% R@10 / 0% R@1**,明言"检索本身无法回答跨会话计数"——QVF count_changes 等算子所消除失效模式的最好反面证据 |

**双证组合**:TimelineQA 85.1%→4.3% + GNBMS 30% R@10 = "检索式读取在个人时间线聚合上系统性失败"的域外独立双证,直接为 S5 +31.8pp 的机制归因背书(QO-Bench 为第三证,见 F 组)。

### E. 时态 KGQA 族(此前漏引的最近邻族)

| 论文 | 编号/DOI | venue | 一句定位 |
|---|---|---|---|
| TEQUILA | 10.1145/3269206.3269247(arXiv 1908.03650 为后挂,引 CIKM 版) | CIKM 2018 短文 | 规则分解+Allen 区间代数,子查询委托现成 KBQA 引擎;库为给定 Freebase |
| TempQuestions | 10.1145/3184558.3191536(无 arXiv) | WWW 2018 Companion | 1,271 题纯时序基准;类型学(显式/隐式/序数/时间型答案)缺"同属主属性历史序列聚合"题型 |
| CronKGQA/CronQuestions | 2106.01515 ✔ | ACL 2021 长文 | 410k 题+TComplEx 嵌入打分;复杂桶含 before/after、first/last、**time join**——join 类不能称 QVF 独有 |
| TempoQR | 2112.05785 ✔ | AAAI 2022 | 嵌入打分,要求实体/时间戳预标注 |
| EXAQT | 2109.08935 ✔ | CIKM 2021 长文 | GNT 子图+R-GCN 排序;**自称 first end-to-end——QVF 用"端到端"必须限定"从对话原文到答案"** |

**整族分界句(可直接入文)**:"时态 KGQA 一族均以他人策展好的时态知识库为给定输入回答单条独立问题;其读取端要么把问题委托给产生结构化查询的 KBQA 引擎(TEQUILA),要么在嵌入空间打分或以图神经网络排序(CronKGQA、TempoQR、EXAQT)——没有一个包含从多会话对话原文构建带逐字出处的时态事实库的写入侧,没有按问题时序性与库形态分派的路由,也不报告端到端 token 成本;QVF 把这三件事全部纳入被评测的系统边界。"
安全的独有差异点:premise_check、count_changes、longest、tag_filter/tag_trend(该族类型学中缺位);**不安全**:time join、"依赖结构化查询"的笼统概括(族内多数是嵌入打分)。

### F. 基准与方法学

| 论文 | 编号 | venue | 关键核实点 |
|---|---|---|---|
| LongMemEval | 2410.10813 ✔ | ICLR 2025 | KU/TR/false-premise 题类原文定义在手;500 题七题型五能力 |
| LoCoMo | 2402.17753 ✔ | ACL 2024 长文(pp.13851-70) | **统计一律用 ACL 版:平均 600 轮/16K token/最多 32 会话**(arXiv 摘要旧数 300 轮/9K 勿用) |
| TimeQA | 2108.06314 ✔ | NeurIPS 2021 D&B R2 | 限定符 P580/P582/P585;41.6% 片段众包修订;**WikiState 从限定符导金答案应引它为方法先例** |
| TempReason | 2306.08952 ✔ | ACL 2023 长文 | L1/L2/L3 可作 QVF 算子难度分层的现成引用框架(L1≈直读事件算术,L2≈point_in_time,L3≈first_last/count_before/join) |
| SituatedQA | 2109.06157 ✔ | EMNLP 2021 | "答案是提问时间的函数"设定先例(世界知识域) |
| STALE | 2605.06527 ✔ | arXiv preprint | 三维度:State Resolution/Premise Resistance/Implicit Policy Adaptation;QVF 只认领 Premise Resistance 的**显式取代子集**,不覆盖需常识判废的隐式冲突 |
| CAPA | 2607.26611 ✔ | arXiv preprint | "(a_i,r_i) remains stable" 原文确认静态假设;**STALE 与 CAPA 作者重叠(Rui Sheng、Yushi Sun 同团队),投稿可能撞审稿人** |
| DocETL | 2410.12189 ✔ | PVLDB 18(9) 2025 | "聚合前自动插 resolve"属实;域为离线文档批处理——QVF 是写入期契约规范键 vs 其优化期事后消解 |
| QO-Bench | 2606.04646 ✔ | arXiv preprint | 措辞:**相似度检索在聚合算子上崩溃(RAG 交集 6.0%/计数 30.0%;长上下文 oracle 交集 3.9%),抽取到结构化+代码执行两类平稳(≈51%)**——不是笼统"聚合难于点查" |
| Generic-Prompt-Hurt | 2601.22025 ✔ | arXiv 技术报告(单作者) | 弱证据,只作一致性旁证 |
| 溯源综述 | 2606.04990 ✔ | arXiv preprint | §7.3 "Memory provenance remains underdeveloped";其溯源元数据清单与六字段卡逐项对应,可引作"该空白的一个具体构造" |
| ConsistencyGate | 2607.22962 ✔ | arXiv preprint | 写入概率门控 vs QVF 结构性逐字契约,正交可并存 |
| HippoRAG | 2405.14831 ✔ | NeurIPS 2024 | 管线不同环节(检回 vs 检回之后的时序语义) |
| A-Mem | 2502.12110 ✔ | NeurIPS 2025 | 自组织笔记 vs 固定契约,相反的设计赌注 |
| MemoryOS | 2506.06326 ✔ | EMNLP 2025 main(pp.25961-70);**oral 仅 GitHub 自述,正文只写 main** | 容量分层 vs 时序语义 |
| SeCom | 2502.05589 ✔ | ICLR 2025 | 粒度调优 vs 结构化执行 |
| M+ | 2502.00592 ✔ | ICML 2025 | 参数化记忆分支,互为对照 |
| GopherCite | 2203.11147 ✔ | arXiv preprint(从未过审) | 训练习得引用 vs QVF 结构约束引用(且带时态) |

## 三、写作红旗清单(定稿前逐条对照)

1. "端到端"一律限定为"从对话原文到答案"(EXAQT 占了无限定用法,Jia/Saha Roy/Weikum 可能是审稿人)
2. time join 类问题不称独有(CronQuestions 复杂桶已有)
3. "逐条日期引用"表述为轻量证据纪律,不作验证机制贡献(TGMS 的重执行验证更强)
4. 所有 2026 预印本(A-TMA/StateAuditor/EMem/TGMS/Engram/GNBMS/STALE/CAPA/QO-Bench/ConsistencyGate/溯源综述)标 concurrent/preprint;Mem0 改引 ECAI 2025、Theanine 引 NAACL 2025、TReMu 引 Findings of ACL 2025
5. STALE/CAPA 同团队,措辞要经得起这组人挑刺;QVF 不声称覆盖隐式冲突
6. LoCoMo 统计用 ACL 版数字;TReMu 是多选题、与我们开放作答对比须注明格式差异
7. 复现 PRA 基线须注明"以 stated_date 代 version serial 的适配复现"
8. ~~待补查:ACL 2026 已出现 APEX-MEM(含 temporal reasoning)、Semantic XPath、MAGMA~~ **08-16 已扫描,见五.3**——APEX-MEM(ACL 2026 主会)为本档目前机制最接近 QVF 的近邻,新增分界句
9. ~~TempQuestions 是唯一未直接打开 PDF 的~~ **08-16 已通过同作者(Abujabal)博士论文第五章拿到全文级细节,见五.2**——论文正文(TEQUILA/CIKM 2018 章节,与 TempQuestions/WWW 2018 同一基准同一作者组)完整复现了基准构建方法与四类分类法,不再是仅摘要级
10. ~~A-TMA/StateAuditor 的 § 编号与阈值细节引用前人工再核对 PDF 一遍~~ **08-16 已过 HTML 全文逐条核对,见五.1**——原判决全部准确,无需改判

## 四、BibTeX 全集

```bibtex
@misc{shi2026atma, title={A-TMA: Decoupling State-Aware Memory Failures in Long-Term Agent Memory}, author={Shi, Zitong and Tang, Yixuan and Tung, Anthony Kum Hoe}, year={2026}, eprint={2607.01935}, archivePrefix={arXiv}, note={arXiv preprint}}
@misc{sun2026stateauditor, title={When Memory Updates but Behavior Does Not: Repairing Implicit Stale Dependencies in Personalized Agent Responses}, author={Sun, Haofei and He, Lin}, year={2026}, eprint={2608.01619}, archivePrefix={arXiv}, note={arXiv preprint}}
@inproceedings{ong2025theanine, title={Towards Lifelong Dialogue Agents via Timeline-based Memory Management}, author={Ong, Kai Tzu-iunn and Kim, Namyoung and Gwak, Minju and Chae, Hyungjoo and Kwon, Taeyoon and Jo, Yohan and Hwang, Seung-won and Lee, Dongha and Yeo, Jinyoung}, booktitle={Proceedings of NAACL-HLT 2025}, year={2025}, note={arXiv:2406.10996}}
@misc{zhou2025emem, title={A Simple Yet Strong Baseline for Long-Term Conversational Memory of LLM Agents}, author={Zhou, Sizhe and Han, Jiawei}, year={2025}, eprint={2511.17208}, archivePrefix={arXiv}, note={arXiv preprint, work in progress}}
@misc{rasmussen2025zep, title={Zep: A Temporal Knowledge Graph Architecture for Agent Memory}, author={Rasmussen, Preston and Paliychuk, Pavlo and Beauvais, Travis and Ryan, Jack and Chalef, Daniel}, year={2025}, eprint={2501.13956}, archivePrefix={arXiv}, note={arXiv preprint}}
@inproceedings{chhikara2025mem0, title={Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory}, author={Chhikara, Prateek and Khant, Dev and Aryan, Saket and Singh, Taranjeet and Yadav, Deshraj}, booktitle={Proceedings of the 28th European Conference on Artificial Intelligence (ECAI)}, year={2025}, note={arXiv:2504.19413}}
@misc{packer2023memgpt, title={MemGPT: Towards LLMs as Operating Systems}, author={Packer, Charles and Wooders, Sarah and Lin, Kevin and Fang, Vivian and Patil, Shishir G. and Stoica, Ion and Gonzalez, Joseph E.}, year={2023}, eprint={2310.08560}, archivePrefix={arXiv}, note={arXiv preprint}}
@inproceedings{reddy2026pra, title={Reliable Post-Retrieval Assembly for Agent Memory: Separating Evidence Extraction from Policy Execution}, author={Reddy, Vikas and Challaram, Sumanth Reddy}, booktitle={Lifelong Agent Workshop at the Conference on Language Modeling (COLM)}, year={2026}, note={Workshop poster. arXiv:2606.01435; v1 title ``Don't Ask the LLM to Track Freshness: A Deterministic Recipe for Memory Conflict Resolution''}}
@inproceedings{jia2018tequila, title={{TEQUILA}: Temporal Question Answering over Knowledge Bases}, author={Jia, Zhen and Abujabal, Abdalghani and Saha Roy, Rishiraj and Str{\"o}tgen, Jannik and Weikum, Gerhard}, booktitle={Proceedings of CIKM}, pages={1807--1810}, year={2018}, doi={10.1145/3269206.3269247}}
@inproceedings{jia2018tempquestions, title={{TempQuestions}: A Benchmark for Temporal Question Answering}, author={Jia, Zhen and Abujabal, Abdalghani and Saha Roy, Rishiraj and Str{\"o}tgen, Jannik and Weikum, Gerhard}, booktitle={Companion Proceedings of the Web Conference (WWW)}, pages={1057--1062}, year={2018}, doi={10.1145/3184558.3191536}}
@inproceedings{saxena2021cronkgqa, title={Question Answering Over Temporal Knowledge Graphs}, author={Saxena, Apoorv and Chakrabarti, Soumen and Talukdar, Partha}, booktitle={Proceedings of ACL-IJCNLP}, pages={6663--6676}, year={2021}, doi={10.18653/v1/2021.acl-long.520}}
@inproceedings{mavromatis2022tempoqr, title={{TempoQR}: Temporal Question Reasoning over Knowledge Graphs}, author={Mavromatis, Costas and Subramanyam, Prasanna Lakkur and Ioannidis, Vassilis N. and Adeshina, Soji and Howard, Phillip R. and Grinberg, Tetiana and Hakim, Nagib and Karypis, George}, booktitle={Proceedings of AAAI}, volume={36}, number={5}, pages={5825--5833}, year={2022}, doi={10.1609/aaai.v36i5.20526}}
@inproceedings{jia2021exaqt, title={Complex Temporal Question Answering on Knowledge Graphs}, author={Jia, Zhen and Pramanik, Soumajit and Saha Roy, Rishiraj and Weikum, Gerhard}, booktitle={Proceedings of CIKM}, pages={792--802}, year={2021}, doi={10.1145/3459637.3482416}}
@inproceedings{chen2024progtqa, title={Self-Improvement Programming for Temporal Knowledge Graph Question Answering}, author={Chen, Zhuo and Zhang, Zhao and Li, Zixuan and Wang, Fei and Zeng, Yutao and Jin, Xiaolong and Xu, Yongjun}, booktitle={Proceedings of LREC-COLING 2024}, year={2024}, note={arXiv:2404.01720}}
@inproceedings{ge2025tremu, title={{TReMu}: Towards Neuro-Symbolic Temporal Reasoning for {LLM}-Agents with Memory in Multi-Session Dialogues}, author={Ge, Yubin and Romeo, Salvatore and others}, booktitle={Findings of the Association for Computational Linguistics: ACL 2025}, year={2025}, url={https://aclanthology.org/2025.findings-acl.972/}, note={arXiv:2502.01630}}
@inproceedings{tan2023timelineqa, title={{TimelineQA}: A Benchmark for Question Answering over Timelines}, author={Tan, Wang-Chiew and Dwivedi-Yu, Jane and Li, Yuliang and Mathias, Lambert and Saeidi, Marzieh and Yan, Jing Nathan and Halevy, Alon Y.}, booktitle={Findings of the Association for Computational Linguistics: ACL 2023}, year={2023}, url={https://aclanthology.org/2023.findings-acl.6/}, note={arXiv:2306.01069}}
@misc{zhang2026tgms, title={{TGMS}: An Agent-Native Bi-Temporal Graph Management System}, author={Zhang, Xiaofei}, year={2026}, eprint={2607.10265}, archivePrefix={arXiv}, note={arXiv preprint}}
@misc{wang2026engram, title={Less Context, More Accuracy: A Bi-Temporal Memory Engine for {LLM} Agents Where a Lean Retrieved Context Beats the Full History}, author={Wang, Liuyin}, year={2026}, eprint={2606.09900}, archivePrefix={arXiv}, note={arXiv preprint}}
@misc{niksarli2026graphnative, title={A Graph-Native Bitemporal Memory Store for Conversational {AI} Agents}, author={Niksarli, Alp and Baheti, Gopesh}, year={2026}, eprint={2607.26520}, archivePrefix={arXiv}, note={arXiv preprint}}
@inproceedings{wu2025longmemeval, title={{LongMemEval}: Benchmarking Chat Assistants on Long-Term Interactive Memory}, author={Wu, Di and Wang, Hongwei and Yu, Wenhao and Zhang, Yuwei and Chang, Kai-Wei and Yu, Dong}, booktitle={Proceedings of ICLR}, year={2025}, note={arXiv:2410.10813}}
@inproceedings{maharana2024locomo, title={Evaluating Very Long-Term Conversational Memory of {LLM} Agents}, author={Maharana, Adyasha and Lee, Dong-Ho and Tulyakov, Sergey and Bansal, Mohit and Barbieri, Francesco and Fang, Yuwei}, booktitle={Proceedings of ACL (Volume 1: Long Papers)}, pages={13851--13870}, year={2024}, url={https://aclanthology.org/2024.acl-long.747/}}
@inproceedings{chen2021timeqa, title={A Dataset for Answering Time-Sensitive Questions}, author={Chen, Wenhu and Wang, Xinyi and Wang, William Yang}, booktitle={NeurIPS Datasets and Benchmarks Track (Round 2)}, year={2021}, note={arXiv:2108.06314}}
@inproceedings{tan2023tempreason, title={Towards Benchmarking and Improving the Temporal Reasoning Capability of Large Language Models}, author={Tan, Qingyu and Ng, Hwee Tou and Bing, Lidong}, booktitle={Proceedings of ACL (Volume 1: Long Papers)}, pages={14820--14835}, year={2023}, url={https://aclanthology.org/2023.acl-long.828/}}
@inproceedings{zhang2021situatedqa, title={{SituatedQA}: Incorporating Extra-Linguistic Contexts into {QA}}, author={Zhang, Michael J.Q. and Choi, Eunsol}, booktitle={Proceedings of EMNLP}, pages={7371--7387}, year={2021}, url={https://aclanthology.org/2021.emnlp-main.586/}}
@misc{chao2026stale, title={{STALE}: Can {LLM} Agents Know When Their Memories Are No Longer Valid?}, author={Chao, Hanxiang and Bai, Yihan and Sheng, Rui and Li, Tianle and Sun, Yushi}, year={2026}, eprint={2605.06527}, archivePrefix={arXiv}, note={arXiv preprint}}
@misc{xu2026capa, title={Fewer Clarifications, Better Code: Benchmarking Cross-Session Personalized Ambiguity Adaptation in Coding Assistants}, author={Xu, Zijian and Zhang, Wenshuo and Qin, Zisen and Sheng, Rui and Sun, Yushi and Qu, Huamin and Shi, Chuhan}, year={2026}, eprint={2607.26611}, archivePrefix={arXiv}, note={arXiv preprint}}
@article{shankar2025docetl, author={Shreya Shankar and Tristan Chambers and Tarak Shah and Aditya G. Parameswaran and Eugene Wu}, title={DocETL: Agentic Query Rewriting and Evaluation for Complex Document Processing}, journal={Proceedings of the {VLDB} Endowment}, volume={18}, number={9}, pages={3035--3048}, year={2025}}
@misc{zhang2026qobench, author={Mengao Zhang and Xiang Yang and Chang Liu and Tianhui Tan and Ke-wei Huang}, title={{QO-Bench}: Diagnosing Query-Operator-Preserving Retrieval over Typed Event Tuples}, year={2026}, eprint={2606.04646}, archivePrefix={arXiv}, note={arXiv preprint}}
@misc{commey2026generic, author={Daniel Commey}, title={When Generic Prompt Improvements Hurt: Evaluation-Driven Iteration for {LLM} Applications}, year={2026}, eprint={2601.22025}, archivePrefix={arXiv}, note={Technical report, arXiv preprint}}
@misc{wang2026agenttraces, author={Yiqi Wang and Jiaqi Zhang and Taotao Cai and Zirui Liu and Qingqiang Sun and Zequn Sun and Zhangkai Wu and Manqing Dong and Mingkai Zheng and Xuefei Yin and Yanming Zhu}, title={From Agent Traces to Trust: {A} Survey of Evidence Tracing and Execution Provenance in {LLM} Agents}, year={2026}, eprint={2606.04990}, archivePrefix={arXiv}, note={arXiv preprint}}
@misc{zhang2026consistencygate, author={Yan Zhang and Shibo Li}, title={{ConsistencyGate}: Preventing Memory Contamination in {LLM} Agents via Self-Consistency Admission Control}, year={2026}, eprint={2607.22962}, archivePrefix={arXiv}, note={arXiv preprint}}
@inproceedings{gutierrez2024hipporag, author={Bernal Jim{\'e}nez Guti{\'e}rrez and Yiheng Shu and Yu Gu and Michihiro Yasunaga and Yu Su}, title={{HippoRAG}: Neurobiologically Inspired Long-Term Memory for Large Language Models}, booktitle={Advances in Neural Information Processing Systems 37 ({NeurIPS})}, year={2024}}
@inproceedings{xu2025amem, author={Wujiang Xu and Zujie Liang and Kai Mei and Hang Gao and Juntao Tan and Yongfeng Zhang}, title={{A-Mem}: Agentic Memory for {LLM} Agents}, booktitle={Advances in Neural Information Processing Systems 38 ({NeurIPS})}, year={2025}}
@inproceedings{kang2025memoryos, author={Jiazheng Kang and Mingming Ji and Zhe Zhao and Ting Bai}, title={Memory {OS} of {AI} Agent}, booktitle={Proceedings of EMNLP}, pages={25961--25970}, year={2025}, doi={10.18653/v1/2025.emnlp-main.1318}}
@inproceedings{pan2025secom, author={Zhuoshi Pan and Qianhui Wu and Huiqiang Jiang and Xufang Luo and Hao Cheng and Dongsheng Li and Yuqing Yang and Chin-Yew Lin and H. Vicky Zhao and Lili Qiu and Jianfeng Gao}, title={{SeCom}: On Memory Construction and Retrieval for Personalized Conversational Agents}, booktitle={Proceedings of ICLR}, year={2025}}
@inproceedings{wang2025mplus, author={Yu Wang and Dmitry Krotov and Yuanzhe Hu and Yifan Gao and Wangchunshu Zhou and Julian J. McAuley and Dan Gutfreund and Rog{\'e}rio Feris and Zexue He}, title={{M+}: Extending {MemoryLLM} with Scalable Long-Term Memory}, booktitle={Proceedings of ICML}, year={2025}}
@misc{menick2022gophercite, author={Jacob Menick and Maja Trebacz and Vladimir Mikulik and John Aslanides and Francis Song and Martin Chadwick and Mia Glaese and Susannah Young and Lucy Campbell-Gillingham and Geoffrey Irving and Nat McAleese}, title={Teaching Language Models to Support Answers with Verified Quotes}, year={2022}, eprint={2203.11147}, archivePrefix={arXiv}, note={arXiv preprint}}
@misc{banerjee2026apexmem, title={{APEX-MEM}: Agentic Semi-Structured Memory with Temporal Reasoning for Long-Term Conversational {AI}}, author={Banerjee, Pratyay and Moshtaghi, Masud and Subramanian, Shivashankar and Misra, Amita and Chadha, Ankit}, booktitle={Proceedings of ACL (Volume 1: Long Papers)}, year={2026}, note={ACL Anthology 2026.acl-long.749; arXiv:2604.14362}}
@inproceedings{jiang2026magma, title={{MAGMA}: A Multi-Graph based Agentic Memory Architecture for {AI} Agents}, author={Jiang, Dongming and Li, Yi and Li, Guanpeng and Li, Bingzhe}, booktitle={Proceedings of ACL (Volume 1: Long Papers)}, pages={36848--36865}, year={2026}, note={ACL Anthology 2026.acl-long.1709; arXiv:2601.03236}}
@inproceedings{liu2026semanticxpath, title={Semantic {XPath}: Structured Agentic Memory Access for Conversational {AI}}, author={Liu, Yifan Simon and Wu, Ruifan and Gallagher, Liam and Liang, Jiazhou and Toroghi, Armin and Sanner, Scott}, booktitle={Proceedings of ACL 2026: System Demonstrations}, year={2026}, note={ACL Anthology 2026.acl-demo.28; arXiv:2603.01160}}
```

## 五、08-16 尽调收尾(B5,三件事收尾)

### 五.1 A-TMA / StateAuditor 章节细节复核(HTML 全文,非摘要页)

方法:WebFetch 直接打开 `arxiv.org/html/2607.01935v2` 与 `arxiv.org/html/2608.01619v1`(此前仅核到摘要/metadata 页),逐条对照本档分界句所依据的机制描述。

**A-TMA(2607.01935)—原判决全部准确,逐条核对结果:**
- 查询画像规则计数、四类:原文 §4.4 明述"a lightweight rule based query profiler before ranking, not a classifier or an LLM",按词法线索计数分入 current/historical/transition/neutral 四类(附录 A.8 给出计数决胜规则)——**与档案措辞一致**。
- 打标证据交 LLM 直答:§4.5 QA 序列化器把标签向量 λ∈{cur, hist, tran, link, raw} 嵌入提示词交答题模型,**无算子编译、无管线级路由**——**与档案措辞一致**。
- 隔离消融数字:附录 A.7 Table 5(3 个 LTP profile,240 探针,A-Mem 宿主)—— Full A-TMA 0.883 QA Acc. vs 宿主基线 0.825;−Retrieval Controller 降至 0.817,−QA Label 降至 0.825(与宿主基线打平,说明 QA 标签是增益主因)。**档案原句"该隔离消融(−Retrieval Controller/−QA Label,0.883 vs 宿主 0.825)"应理解为"Full 与宿主对照 0.883/0.825,两项消融各自定位增益来源"——数字准确,表述可更精确但不构成错误**。

**StateAuditor(2608.01619)—原判决全部准确,逐条核对结果:**
- 答后审计:§3 Problem Setup 原文"a draft d∼G(M,q) from the memory-augmented generator G, the audit produces P={(pj,vj,cj,bj)}"——确认在生成**之后**对草稿做审计,而非答前介入。
- 引用校验阈值:§4.4"Each quotation must match at least 80% of its content tokens within a single rendered memory entry"——**≥80% token 重合、非逐字**,与档案措辞一致。
- 无冲突样本过度重写率:§6.4/Figure 4,"the post-hoc-selected repair-only policy...rewrites 3% of conflict-free examples vs. 80%"——**全量 VTA 系统在无冲突样本上触发重写 80%**,repair-only 变体仅 3%(论文推荐 repair-only 为部署默认)。与档案措辞一致。
- 答前无 premise_check:§4.5 明述用确定性规则而非模型生成指令("We use deterministic rules because model-generated directives frequently asked for confirmation..."),但该规则仍作用于**生成后**的草稿修补,不介入生成前——与档案"QVF 的 premise_check 在答前"分界句一致。

**结论:两篇此前的 HTML/摘要页核实均准确,无需改判,分界句维持原样。**

### 五.2 TempQuestions 正文细节(全文级确认,非仅摘要)

ACM 页面(`dl.acm.org/doi/fullHtml/10.1145/3184558.3191536`)与 ResearchGate 页面本次复测仍均返回 403,直接拿正式 WWW 2018 Companion 版式 PDF 未果。改路:定位到同一基准同一作者组的**姊妹全文**——Abujabal 博士论文(Saarland University,2019,`publikationen.sulb.uni-saarland.de/bitstream/20.500.11880/27438/1/abujabal_phd_thesis_final_2019_05_10.pdf`)第五章即 TEQUILA(CIKM 2018)工作,该章完整复现了 TempQuestions 基准的构造方法、四类分类法定义与分布表(WWW 2018 Companion 版是同一基准的资源型短文,构造方法与分类法在两篇论文间共享)。用 `pdftotext` 抽取全文后核对:

- 基准规模与来源:1,271 题,取自 Free917(917 对)+ WebQuestions(5,810 对)+ ComplexQuestions(2,100 对),经时序检测算法初筛后人工剔除 245 条非时序题(论文 §5.5.1)。
- **四类分类法(Table 5.3)确认为**:explicit(344)、implicit(209)、temporal answer(393)、ordinal constraint(155)(各来源分项数字见原表,合计 1,364>1,271 因部分题多标签)。
- **分类法中确认缺席"同属主属性历史序列聚合"题型**:Table 5.4 的四类示例("who won the state of texas in 2008?" / "who was the president after jfk died?" / "what years did the knicks win the championship?" / "who was the first coach of the bucaneers?")均为单值提取或有序筛选,没有"列出/统计某实体某属性历次取值"一类——**与档案原判决一致**。
- **我方引用只用到摘要级内容,现已升级为全文级确认**:档案原引用点(1,271 题规模、四类分类法、缺"历史序列聚合"题型)全部在这份姊妹全文中逐字核实,原判决无需修改。

**标注**:严格意义上仍未拿到 WWW 2018 Companion 版本身的 PDF(ACM 403 拦爬虫依旧);但由于 TempQuestions 的构造方法论、分类法与分布统计是与 TEQUILA(CIKM 2018,同作者组、同基准)共享的同一套内容,且已从后者全文逐字核实,故档案对 TempQuestions 正文细节的引用**不再是仅摘要级**,可视为全文级确认。若审稿人要求 WWW 2018 Companion 版本身的 PDF 页码,仍需人工从图书馆代查。

### 五.3 ACL 2026 新近邻扫描(APEX-MEM / Semantic XPath / MAGMA)

逐个 WebSearch 定位 + WebFetch 全文核实机制,判断是否比 A-TMA 更危险。

| 论文 | 编号 | venue(已核) | 机制 | 与 QVF 的重叠 | 与 QVF 的分野 | 危险度(相对 A-TMA) |
|---|---|---|---|---|---|---|
| APEX-MEM | 2604.14362 ✔ | **ACL 2026 主会**(2026.acl-long.749,Amazon) | 属性图+仅追加存储+多工具检索代理(ReAct 式循环调用 SchemaViewer/EntityLookup/GraphSQL/Search);GraphSQL 支持只读 SQL 的 SELECT/JOIN/AGGREGATE/TEMPORAL 查询,由 LLM 在循环中临场生成 SQL 文本 | 都会产出结构化查询(SQL vs JSON 计划)、都对聚合/join 类问题有专门通路、GraphSQL 执行本身是确定性代码(非 LLM 心算) | **SQL 由 LLM 临场生成,非从闭集算子词表按路由编译**——无固定算子清单、无生成前的合法性校验、循环无保证终止步数;冲突消解=检索到双版本按时间戳交 LLM 自行择取,**无答前 premise_check**;**无管线级路由**(是否调用/调用几轮由代理自行摸索,全部查询走同一多工具循环,论文未报告 token 成本);单时态戳(§3 起止区间+锚定事件时间戳,非严格双时态 ingestion/event 分离) | **高于 A-TMA**——本轮新扫描中机制最贴近"编译执行"范式的近邻,需新分界句(见下) |
| MAGMA | 2601.03236 ✔ | **ACL 2026 主会**(2026.acl-long.1709) | 四正交视图图(语义/时序/因果/实体),时序图 §3.2 定义为按时间戳严格排序的**线性链**(τ_i<τ_j 的有序对),检索=LLM 驱动的自适应遍历策略(§3.3 动态转移分数),取回子图后交 LLM 生成叙述并自由推理作答 | 都显式建了"时序"维度的图/结构 | 时序图**仅线性时间戳链,无 bitemporal 有效期区间、无 supersession/superseded-by 链**;聚合(如"几个孩子")由 LLM 读取子图**心算**得出,**无确定性计数/时长算子**;**无 premise_check**;**无管线级路由**(所有查询走同一多图遍历流程) | **不高于 A-TMA**——仍是"检索+LLM 心算"范式(同 Engram/Zep/MAGMA 一类),纯检索式读取范畴内,不构成比 A-TMA 更强的反例 |
| Semantic XPath | 2603.01160 ✔ | **ACL 2026 系统演示(demo track,非主会)**(2026.acl-demo.28) | 树形结构化记忆(话题/实体/属性层级)+ XPath 风格查询语言,结构匹配+语义相关性打分;Version 节点保留修订历史(版本分支,旧数据不覆盖) | 都有"保留历史版本、不覆盖旧数据"的写入侧设计 | **无时间维度语义**——Version 节点只追踪"哪次编辑产生了新版本",不存时间戳/有效期区间,**无法回答"变了几次/持续多久/某时点是什么"类时序聚合问题**;XPath 查询由 LLM 临场生成,无算子闭集;**无 premise_check**;论文定位是"结构化访问效率"(176.7% 优于 flat-RAG、仅 9.1% token),不是时序推理系统 | **明显低于 A-TMA**——非时序推理近邻,只是写入侧"保历史版本"理念的又一例证,可并入既有"Zep/Mem0/Engram 类保时间线但读取无查询条件化"的反面证据簇,不必单独立分界句 |

**结论:APEX-MEM 构成本次尽调发现的、比 A-TMA 更危险的近邻,需新增分界句**(MAGMA、Semantic XPath 危险度不超过已有近邻,沿用既有分界句框架即可,不新增独立分界句)。

**APEX-MEM 分界句草稿(待审,建议入 D 组"编译-执行范式近邻"或单列一行)**:

> "同期最接近的会议论文是 APEX-MEM(ACL 2026 主会):其多工具检索代理在 ReAct 式循环中调用只读 SQL 接口(GraphSQL),能生成含 JOIN/AGGREGATE/TEMPORAL 的结构化查询,执行本身是确定性代码;但该 SQL 由语言模型在检索循环中临场生成,并非从封闭算子词表经路由编译得到——没有固定的算子清单与生成前合法性校验,循环步数无保证上限,冲突消解依赖模型在检索到的多版本证据间自行择取而非答前的确定性前提纠错,且全部查询走同一条多工具循环、无按问题类型分派的管线级路由,论文也未报告端到端 token 成本。QVF 与其一线之隔:问题先经路由分类落入闭集算子(计数/时长/定点/首末/join/premise_check 等)再由代码而非语言模型执行,执行阶段零 LLM 介入、premise_check 前置于生成而非事后由模型兼顾。"

**限定词纪律**:三篇均为 2026 年论文,标注 concurrent/ACL 2026(APEX-MEM、MAGMA 为主会;Semantic XPath 为 demo track,不可误写成主会)。
