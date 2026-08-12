# QVF 参考文献总表(2026-08-11 整理)

> 组织方式:按论文章节角色分组;每条 = 文献 · 出处 · **在我们论文中的角色**(基座/对比/背书/证伪/近亲)。标 ⚠ 的编号或年份需在写作时核对原文。方法借鉴细节(移植方式、行数、成本)见 literature_map_2026-08-05.md。

---

## 一、对话记忆基准(评测底座与对照考场)

| 文献 | 出处 | 角色 |
|---|---|---|
| **STALE** — Can LLM Agents Know When Their Memories Are No Longer Valid? | arXiv:2605.06527 | **基座**:记忆过时问题本体;我们的考场底座(干扰干草堆复用其 CC BY 素材);其二态结构"一律删旧可满分"是 STALE-Chain 扩展的立论 |
| **LongMemEval** | arXiv:2410.10813 ⚠ | **对照考场+判分协议来源**:TR/KU 子集为在题公开考场(rt +12pp gpt 显著);其 LLM 判官协议 = 我们判官实现的蓝本 |
| **LoCoMo** | arXiv:2402.17753 ⚠ | **无害性对照**:逐题审计 0-18% 在题;也是 Mem0 等竞品的主场(引其原表做问题含量对比) |
| **MemConflict** | arXiv:2605.20926 | **边界地图**:时序/错误信息/条件三分层;名义 60% 在题经 opus 复核站住 |
| **HoH**(维基编辑差分) | ACL 2025 ⚠ | 删除时间检查的消融证明考场(缺时间检查 100→74) |
| **BEAM / EverMemBench** | 2026,编号⚠ | related work:最新长程对话基准,时序版本化方向与我们同期;差异=合成状态链 vs 机械金答案 |

## 二、时序 QA 基准(WikiState 的近亲,必须差异化)

| 文献 | 出处 | 角色 |
|---|---|---|
| **TempReason** | arXiv:2306.08952(ACL 2023) | **最近的基准近亲**:同用 Wikidata 时序事实,其 L2 时点题与我们 dim4 同构——必须明确 credit;差异=文档/闭卷 QA vs 个人记忆形态(渲染会话+干扰干草堆+检索);也是我们的外部考场(rt +6.5pp) |
| **TimeQA** | arXiv:2108.06314 ⚠(NeurIPS 2021 D&B) | 时间限定符出题的开创者;同上差异化 |
| **UnSeenTimeQA** | ACL 2025 | 防记忆化动机与我们的参数泄漏过滤同源,方法不同(虚构 vs 过滤) |
| **PAT-Questions** | arXiv:2402.11034 | 现在锚定+自更新;与 dim1 的"(Today is…)"锚定同思想 |
| **TempLAMA / Time-Aware LM** | arXiv:2106.15110 ⚠(TACL 2022) | 参数时序知识背景;支撑"参数泄漏过滤必要性" |
| **FreshQA / FreshLLMs** | arXiv:2310.03214 ⚠ | 过时前提(false premise)问题的世界知识版;dim2 的近亲,域不同(世界知识+搜索 vs 个人记忆) |
| **SituatedQA** | arXiv:2109.06157 ⚠ | 时空条件化答案的先声 |

## 三、记忆系统(实测对照 + related work)

| 文献/系统 | 出处 | 角色 |
|---|---|---|
| **Mem0** | arXiv:2504.19413 | **实测竞品**:其 LoCoMo J 66.9(全文 72.9 更高;temporal 55.5 为其最弱类);我们实测其真实域 20-30%+时间线腐蚀机制——用其原表铺垫我们的发现 |
| **Zep / Graphiti** | arXiv:2501.13956 | **最近的系统近亲**(bi-temporal KG,作废不删除);我们实测其开源核默认栈在 WikiState 2.5%(抽取本体不含带日期状态,逐字探针证据);其主场 LoCoMo temporal 49.3(引自 Mem0 表)——"图记忆在联想考场能干活,状态链考场抽取本体不对口" |
| **MemGPT / Letta** | arXiv:2310.08560 ⚠ | related work:记忆 OS 范式 |
| **LangMem / OpenAI Memory / A-Mem** | Mem0 论文表转引 | 竞品谱系(temporal 21.7-49.9 集体塌陷=写入时整理范式证据) |
| **MemoryBank** | arXiv:2305.10250 ⚠ | 遗忘曲线/近因加权 = "一律取最新"谬误的系统化身,dim4/5 的反例 |
| 增量摘要记忆(ChatGPT 式画像) | 自实现基线 | 写入时整理第三代表,实测 54.4% |

## 四、知识冲突(问题定义的排除项来源 + 分型依据)

| 文献 | 出处 | 角色 |
|---|---|---|
| **CONFLICTS / DRAGged into Conflicts** | arXiv:2506.08500(Google 2025) | 冲突先分型再施策 → 四物种设计依据;458 专家标注可校准变更语言检测 |
| **ConflictBank** | NeurIPS 2024 D&B | 时序冲突≠错误信息 → 问题定义排除项的文献依据;不可变槽位先验 |
| **WikiContradict** | NeurIPS 2024 D&B | 真平局应并呈 → 矛盾阅读器行为背书 |
| **Adaptive Chameleon** | ICLR 2024 Spotlight | 流畅错误信息赢得信任 → "永不让阅读器裁决"的架构依据 |
| 知识冲突综述(Xu et al.) | arXiv:2403.08319 ⚠ | related work 总览引 |

## 五、方法构件的系谱(消融与设计依据;移植细节见映射文档)

- **Chain of Condition**(EMNLP 2024 Findings)— "LLM 抽取+代码求解"架构同构,裁决层设计依据
- **CRH 真值发现**(SIGMOD 2014)— 佐证计数系谱
- **ConditionalQA**(ACL 2022)/ **StarE**(EMNLP 2020)— 条件一等公民、(value, condition) 契约
- **ATOM**(EACL 2026 Findings ⚠)— 逐块并行抽取:目录覆盖率修复(v4)的方法来源
- **MMR**(SIGIR 1998)— 移植后被配对证伪(0胜4负)——"借鉴不照搬"的展品
- **doc2query / HyDE / IRCoT / FLARE** — 补全扫描的系谱(HyDE: ACL 2023;余编号⚠)
- **Context-faithful Prompting**(EMNLP 2023 Findings)/ **Chain-of-Note**(arXiv:2311.09210 ⚠)— 注记措辞设计与消融
- **Safety-Tuned LLaMAs**(ICLR 2024)— 全局警示过度泛化 = 注记式 14.6% 崩盘的机制解释
- **CoCoNot**(NeurIPS 2024 D&B)— 过度弃答治理(框定发现的邻域)

## 五.五、方法侧 2026 近邻(三轮查新 08-12,方法本体的 related work 核心)

| 文献 | 出处 | 与 QVF 的关系(全部已查透) |
|---|---|---|
| **Post-Retrieval Assembly**(Reddy & Challaram) | arXiv:2606.01435,COLM 2026 WS | **原则同侪(独立同期)**:"抽取与政策执行分离"同一架构洞察,其消融证明分离本身值 +10.8pp(佐证我们的设计)。**边界天壤**:政策仅"取最大序号"(显式版本号,非日期);仅现值题;其自测 LongMemEval 无显著优势并自认"结果限于带显式版本元数据的现值问题"。差异化=我们把政策推广为查询条件化四语义分路+真实日期区间算术+纠前提+历史永不删。必引必 credit |
| **MemStrata** | arXiv:2606.26511(单作者工业预印) | **"一律删旧"范式最强实例=完美 foil**:确定性 supersession(写入检测+读取过滤),非查询条件化,通用退休旧值;仅现值模板题;as-of 能力"建了未评";自由文本抽取 97→44% 塌方(我们 v3 抗污染正中此处)。引用位置=dim4/dim5 结构性失败的论证 |
| **temporal-rag**(GitHub 实践) | Emmimal/temporal-rag | 工程先行者:检索后有效性过滤+时间衰减;无查询条件化、无评测。作 practice 引 |
| **MemRouter / FluxMem / HyMem / MemR3 / RCR-Router** | arXiv:2605.00356 等 ⚠ | 路由近邻群:路由对象=检索动作/记忆结构/粒度(部分为学习型门控);**无一以时序有效性为路由目标、无一按库形态选抽取时机**。差异化=路由维度不同(抽取时机+裁决政策 vs 检索调度) |
| **Don't-ask-LLM 类деterministic 决策**(含 2606.01435) | — | "新鲜度判断不可托付 LLM"共识正在形成(2026 多篇)——我们 2025-08 冻结的代码裁决属最早一批,且唯一带查询条件化与真实域证据 |

## 六、2026 最新近邻(二轮查新 08-12,related work 必写)

| 文献 | 出处 | 关系 |
|---|---|---|
| **TOKI** — bitemporal 算子代数解记忆矛盾 | arXiv:2606.06240 | 双时态形式化与 wt 卡片库最接近的理论工作;差异=查询条件化分路裁决与真实域实证 |
| **Supersede** — supersession gap 命名者 | arXiv:2606.27472 | **已查透**:LME-KU 现成数据+GRPO 训练;仅二态、仅问现在值,无时点/轨迹/陷阱/污染过滤。必须主动 credit 其命名;引其"模板化合成 supersession 已饱和"支撑 WikiState 立论。与我们=同域 S1 的训练路线 vs 全 S1-S4 的架构路线 |
| PersonaMem / MemoryAgentBench / EvoMemBench / StreamMemBench / MemTrace | 2026,编号⚠ | 2026 合成侧基准潮:更新/冲突/流式类别齐全但全为合成用户行为、LLM 金答案——反衬"真实可验证链+机械金答案"空位 |
| KnowMe-Bench | arXiv:2601.04745 | 真实自传文本但考人格理解;非状态更替 |
| AlpsBench | arXiv:2603.26680 | 真实人机对话+人工核验记忆;考记忆管理/偏好,非时序选择 |
| MemoryDocDataSet | arXiv:2606.04442 | 人设时间事件图微世界;虚构+标注金答案 |
| **Always-On Agents 综述** | arXiv:2606.30306 | 引其"memory staleness 为最难开放问题"的定位背书 |
| **Control-Plane Placement 架构研究** | arXiv:2606.15903 | "控制面放置决定遗忘行为"与我们"抽取时机决定证据形态"同型论证 |

## 七、数据与许可

- **Wikidata**(CC0)— 状态链与金答案来源(P39/P54/P108/P551 + P580/P582 限定符)
- **STALE**(CC BY 4.0)— 干扰干草堆素材;衍生声明已内嵌每条目 attribution 字段

---

### 写作时使用指南

1. 引言引:STALE(问题真)、Always-On 综述(问题难)、Mem0 原表(现有方案时序集体塌陷);
2. 问题定义节引:ConflictBank/CONFLICTS(排除项依据)、TempReason/TimeQA(S2 同构 credit);
3. 基准节引:近亲四件套(TempReason/TimeQA/UnSeenTimeQA/PAT)逐一差异化 + LoCoMo/LME(问题含量);
4. 方法节引:Chain of Condition(架构)、映射文档全部构件系谱;
5. 实验节引:Mem0/Zep 论文数字与我们实测并列;
6. related work 收尾:TOKI/Supersede/Zep 三近邻正面比较(阅读任务已建芯片);
7. ⚠ 条目共 12 处,提交前逐一核对编号/年份/venue。
