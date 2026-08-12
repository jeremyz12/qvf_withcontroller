# QVF Study Log — 2026-08-01：五篇论文与启发

检索主题：post-retrieval context filtering、context compression、selective augmentation、corrective retrieval、evidence sufficiency。纳入标准：干预发生在 retrieval 后、Reader 前，或能约束 QVF 的补检索动作。

## 1. FILCO: Learning to Filter Context for Retrieval-Augmented Generation

**内容**：在检索 passages 与 Generator 之间生成句子级过滤后 context，Generator 只看过滤结果。silver-label 构造中 STRINC/CXMI 依赖训练集 canonical output，LEXICAL 在 QA/对话任务上同样对照 canonical output、在 FEVER 上因输出只是一元标签而改用 query 计算重叠（2026-08-02 校对更正）；filter 与 Generator 联合训练。

**关键结果**：Top-1 六任务平均 +2.8~+3.0 points；Top-5 上 NQ 47.6→61.8 等；Generator 输入长度减少 44%–64%。

**对 QVF 的启发**：细粒度 context surgery 有现实正向先例——"物理改变 Reader 可见证据"这个方向不是凭空设想。但其收益建立在 filter 与 Generator 联合训练之上，对未训练、面对固定黑盒 Reader 的 QVF 必须单独验证（固定 Reader 做 filter-only 消融）。QVF 应采用 candidate-ID/source-span 可追溯的 extractive view 并保留 raw archive；不能把 gold-answer 依赖的标签构造搬进目标基准。

## 2. RECOMP: Improving Retrieval-Augmented LMs with Context Compression and Selective Augmentation

**内容**：固定 retriever，压缩器输出短 context 给黑盒 Reader；extractive 选句、abstractive 摘要，允许输出空串（等价"不注入检索"）。训练依赖 gold target 与目标 Reader utility。

**关键结果**：context 压至约 4.7%–11.0%，代价约 2.35–4.60 EM——主要是效率-准确率权衡而非普遍提分。gold 不在证据中时，Reader 错误复制率从 81% 降到 33%/39%（过滤可降低错误服从）。abstractive faithfulness 有限（HotpotQA faithful+comprehensive 仅 40%）。

**对 QVF 的启发**：`PASS / SELECT / EMPTY` 是合理的最小动作集；空 context 必须配 abstain/defer 或安全回退。QVF 适合 source-preserving 的 extractive surgery，不应把自由摘要当作权威记忆。评测须同时记录 false deletion、evidence recall、双侧 token、延迟与最终准确率——controller 的开销和 Reader 的节省要放进同一份账本。

## 3. ECoRAG: Evidentiality-guided Compression for Long Context RAG

**内容**：在 retriever 已提供的 top-100 内，按 evidentiality 排序分句，sufficiency evaluator 判断当前证据集是否足够，不足则从同一预取池逐步加句（"adaptive retrieval"实为 EXPAND_WITHIN_POOL，非外部重检索）。

**关键结果**：大幅缩短 context 且 TQA/WQ 明显提分（TQA 56.21→65.34 EM），但相对最强压缩基线增益仅 +0.4~+1.4；去掉 sufficiency evaluator 降 0.77/1.80 points；跨 Reader 不普遍优于 closed-book。

**对 QVF 的启发**：控制器不应只有一次性 keep/drop——"现有证据无效"与"现有证据不充分"是两个问题，后者应先在固定池内渐进扩展（EXPAND_WITHIN_POOL），确认池内确实没有再请求外部补检索，避免 QVF 膨胀成完整 RAG。sufficiency 必须与 truth/temporal validity 分开：证据足以构造答案 ≠ 答案最新或可信。

## 4. CRAG: Corrective Retrieval Augmented Generation

**内容**：轻量 evaluator 给检索质量打分，controller 按 Correct/Incorrect/Ambiguous 三路由行动：保留并 strip-过滤重组、丢弃改用 web 检索、或合并两者。是 `USE / RETRIEVE / COMBINE` 的现实先例；但 evaluator 用 gold 标题构造训练、阈值按基准调。

**关键结果**：四个基准上 CRAG 相对 vanilla RAG 均提高（如 PopQA 50.5→54.9）；消融显示 refinement、query rewriting、web selection 各有贡献；单纯给 RAG 加同批 web 内容弱于完整 CRAG。

**对 QVF 的启发**：动作显式分为 `USE / RETRIEVE_MORE / COMBINE / DEFER` 比只输出标注更有执行力。**原候选 validity 与 candidate coverage 必须分开归因**——补检索的收益单独报告，不能都记给裁决。补检索应从"一次、可审计"开始：说明为什么需要、缺哪类证据、查询由哪些已有记录推导、新记忆最后起了什么作用；先验证一次结构化补检索，再考虑循环。

## 5. How Does Knowledge Selection Help Retrieval Augmented Generation?

**内容**：不提出 selector，而是在有 gold/distractor 标注的固定候选池中随机操纵证据组成，系统研究 knowledge precision/recall、Reader 强弱与 answer F1 的关系。

**关键结果**：GPT-4o-mini/HotpotQA 的 full→gold gap 仅 .048（强 Reader 下 selector 空间很小）；Mistral/HotpotQA 的 full context 反而低于 no-knowledge（弱 Reader 被 distractor 严重破坏，过滤空间大）。强 Reader 主要随 recall 变化；即使表面 100% precision 的 selector 也可能因 false negative 输给 full context。"更短"本身不等于"更准"。

**对 QVF 的启发**：三个边界必须先报告——`no memory / full raw memory / gold-within-pool`，full–gold gap 才是 selection 的理论空间。recall/coverage failure 的优先级高于 precision；Reader 强弱应作预注册分层——若 context surgery 只帮助弱 Reader，这可以是清晰的适用边界，不应伪装成普遍提升。强 Reader 场景下 QVF 的价值更可能在 validity-specific harm 的降低、可审计性与证据不足时的定向补检索，而非更激进的删除。

## 综合：五篇共同划定的边界

**支持**：在 retrieval 与 generation 之间实际改变 evidence view 有现实依据；过滤不是越强越好，需要 precision–recall–false deletion–成本的完整曲线；"证据无效"与"证据不充分"要分开处理（隔离/降级 vs 池内扩展/补检索）；过滤收益依赖 Reader 能力与任务形态。

**不支持**：联合训练结果不能解读为固定 Reader 下的独立 filter 贡献；gold-answer 依赖的监督不能搬进目标基准；更短 prompt 不直接等于端到端更便宜或更准。

**对 QVF vNext 的落点**：动作集 `PASS / SELECT(ids/spans) / EMPTY_OR_DEFER / EXPAND_WITHIN_POOL / RETRIEVE_MORE(结构化请求)`；先冻结完成现有 filtered 结果，再把补检索拆成通用措辞与结构化请求两个可审计臂；增加 coverage report；把 observed_at 与 effective_from 分开。
