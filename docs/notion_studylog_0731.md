# QVF Study Log — 2026-07-31：五篇论文与启发

## 1. MemChain: Learning Interpretable Memory Traces for Memory-Augmented LLM Agents

**内容**：位于检索后、回答前的可训练记忆策略。给定 query 与封闭候选集，策略一次生成 evidence plan、候选 ID-grounded trace、memory actions（KEEP/DROP/MERGE/REFINE/ADD）与 active evidence；冻结回答模型只看 active evidence，不看完整候选。训练为 SFT（Qwen3-4B LoRA）+ TMPO 组内优化，奖励含结构门与正确性/稳定性/引用精度。

**关键结果**：LoCoMo 69.80（SFT+TMPO）、LongMemEval-S 78.20；消融显示 trace 影响最大（去 trace 55.84、prompt-only 49.35）；answer-facing context 约 143 tokens。

**对 QVF 的启发**："post-retrieval 位置"本身不构成新颖性。真正重要的是控制器有没有能力**改变最终进入 Reader 的证据**，以及这种改变能否被追溯验证——只要 Reader 还能看到全部 raw memory，再完整的分析也只是附加提示。由此形成的设想：先 plan 后抽取；逐 span grounding 扩展为候选集合覆盖审计；MemChain 的 ADD 在 QVF 中应转译为受约束的补检索请求而非凭空补写；高权限必须伴随 grounding、覆盖审计与安全回退（DEFER、raw archive）。

## 2. DRAGged into CONFLICTS: Detecting and Addressing Conflicting Sources in Search-Augmented LLMs

**内容**：冲突是**集合级关系**（等价、互补、意见相左、过期、失实），逐条相关性无法区分；类别直接绑定回答行为（无冲突直答、互补合并、意见中性呈现、过期取新、失实排除）。CONFLICTS 数据 458 例，模型不微调，比较 Pipeline / Taxonomy-Aware / Oracle 三种用法。

**关键结果**：冲突类型分类最高仅 65.3%；给 gold type 平均提升约 24 个 behavior points（预测 type 约 9），收益集中在意见冲突，个别类别反而略降。

**对 QVF 的启发**：最相关的不是 misinformation，而是 outdated、complementary 与 conditional coexistence 的区分——个人记忆的新旧记录不一定是冲突：旧记录可能仍适用于过去时间点，两条记录可能分别适用于不同条件。QVF 不能按"新旧"选赢家，要先判断 query 所问的时间与条件，再决定合并、替代、保留历史还是暂缓。DEFER 更适合表示裁决不确定性。

## 3. Beyond Similarity: MemGate——记忆接纳控制

**内容**：相似性 ≠ 接纳性（admissibility）：相似记忆仍可能跨域、诱导附和或污染工具调用。在向量检索与 prompt 之间插入约 9M 参数的门控 MLP，对 query–memory 对输出 mask 与分数并重排 top-k；DPO 训练于合成偏好对。各 pair 独立处理，无集合级关系。

**关键结果**：cross-domain failure 27.0→3.5、jailbreak ASR 16.8→4.4、LoCoMo 38.9→40.8；sycophancy 改善有限；存在过度过滤风险。

**对 QVF 的启发**：重视 **false rejection**——不能为了显得安全就把 QVF 做成激进过滤器。在普通、无冲突问题上不伤害原有能力，比多拦几条可疑记忆更重要。只有来源、时间与关系证据充分时才真正隐藏候选；证据不完整时优先 DEFER、保留 raw archive 或回退 direct。

## 4. Presentation, Not Mechanism（ESR / RevisionLedger）

**内容**：追问 deprecation-aware memory 的提升来自状态机制还是字段/排序/提示的呈现差异。用渲染匹配对照分离两者：保留 ledger 布局与 ID、只关闭 supersedes/contradicts/unresolved 关系。

**关键结果**：primary slice 总差 +.184 中 render 项占 +.159；exact-layout-matched 的机制残差仅 +.025（CI 含零附近）。fine-ledger 的表面收益大部分来自 presentation。

**对 QVF 的启发**：改变了对早期 STALE 大幅提升的解释——那个结果应表述为 structured adapter、render 与 Reader 共同的**联合上限**，而非机制独立贡献。QVF 实验必须按 `retrieval→extraction→adjudication→render/transport→Reader use` 分解，加 extraction-only 与 render-only 对照、固定候选与渲染，否则差值不能归给 validity engine。

## 5. MemTrace：final accuracy 之前的失败定位

**内容**：以知识点为单位的诊断基准：20 users、835 KP、8 checkpoints、15,422 rows；按 Current/Historical/Trajectory 与 present/missing/false-premise 分层，记录 Gist/Verbatim 完整度与响应类型。

**关键结果**：检索可达（R=1）不保证 gold span 进入 Reader；透明 RAG 中 reached-unsolved 220 例远多于 solved 59；Trajectory 维度暴露 winner-selection 边界（HippoRAG-v2 仅 13.4）；Mem0 boundary abstention 99.3% 但 conflict Gist 仅 14.6——选赢家或拒答都不充分。

**对 QVF 的启发**：最关心的仍是 Current，但只找"最新一条"不够：query 问过去时旧状态应继续可用，问变化过程时系统要看到状态演化。QVF 应优先解决 current-state error，同时**不把历史信息当无效噪声删除**——这是它与普通 relevance filter 的重要区别。评测要把 reach、extract、adjudicate、use 分开定位失败。

## 综合：对 QVF 的定位修正

1. 已不能宣称的新颖性："第一个检索后模块"、"第一个处理完整候选集合"、"结构化 action 本身"、"LLM+规则组合本身"均有先例。
2. 仍可能成立的贡献：query-conditioned、span-grounded 的有效性记录；严格可执行的抽取契约与可审计失败模式；deterministic adjudication 的**独立**贡献（需 extraction-only 对照才能证明）；contract coverage 与 downstream utility 的联合分析；面向 validity risk 的低权限选择性控制。
3. 核心研究问题收敛为：固定候选并匹配渲染的条件下，通用 LLM 能否以足够覆盖率与关系准确度生成来源可验证的同槽位状态记录，使冻结的确定性引擎减少过期/冲突错误，同时不损害无冲突问答。
