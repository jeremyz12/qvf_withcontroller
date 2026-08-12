# QVF：Query-conditioned Validity Filter 研究方案

版本：v0.1（2026-07-31）
状态：方法与系统实现完成；基准数据接入完成；实验待跑

---

## 1. 问题定义

记忆增强的 LLM 代理（memory-augmented agents）在长期多会话交互中积累外部记忆。
回答用户问题时的标准流程是：**检索 → 拼接 → 生成**。这条流程存在一个被普遍忽略的
结构性缺陷：**检索器回答的是"什么相关（relevance）"，而生成器需要知道的是
"什么对这个查询有效（validity）"**。两者的错位造成一类特征性错误：

1. **时间性错误**：用户 2023 年说"在 Google 工作"，2024 年说"跳槽到 Anthropic"。
   两条记忆都会被"工作"类查询检索到。问"现在在哪工作"时旧记忆是干扰项；
   问"2023 年在哪工作"时旧记忆恰恰是正确证据——**有效性取决于查询**，
   而现有系统要么全部拼接（让生成器自己猜），要么按新近性硬性覆盖（历史问题答错）。
2. **伪冲突/真冲突不分**：措辞不同、条件不同、时间域不重叠的记忆被当作矛盾；
   或真正互斥的记忆未被识别，生成器随机择一。
3. **条件限定丢失**："通常骑车上班，下雨除外"在拼接-生成过程中退化为"骑车上班"。
4. **该弃权不弃权**：证据不足或冲突未解决时，生成器仍给出流畅但无据的答案。

**研究问题**：能否在检索与生成之间插入一个显式的、结构化的
**查询条件化有效性判定层**，将上述判定从生成器的隐式负担中剥离出来，
从而在不改动检索器与生成器的前提下系统性减少这类错误？

## 2. 方法：QVF 与 Semantic Adapter

### 2.1 架构位置

```
查询 q ──┐
         ├─→ 检索器 R ─→ 记忆集 M = {(id, content, meta)} ─┐
记忆库 ──┘                                                ├─→ Semantic Adapter A
                                                          │      ↓
                                                q ────────┘  Validity Map V(q, M)
                                                                 ↓
                                          生成器 G(q, M, V) ─→ 答案 / 弃权
```

QVF 不是检索器（不改变召回），不是生成器（不产生答案），而是两者之间的
**语义适配层**。其输出 Validity Map 是一个结构化对象，生成器在其上条件化。

### 2.2 Validity Map 的形式化

给定查询 q（含可选查询时间 t_q）与封闭证据集 M：

- **查询接地** QA(q)：目标实体 E、目标属性 A、时间域
  τ ∈ {CURRENT, HISTORICAL, AT_TIME, CHANGE_OVER_TIME, TIME_INSENSITIVE, UNKNOWN}、
  显式条件 C、是否需要比较。
- **原子声明集** K = {k_i}：每条 k_i = (memory_id, span, 规范化陈述,
  subject, attribute, value, condition, event_time, creation_time, is_inference)。
  关键约束：封闭证据边界（不得引入 M 之外的事实）、事件时间与记忆创建时间分离、
  条件限定词不可丢弃、显式事实与语义推断区分。
- **关系图** R ⊆ K×K，标签 ∈ {EQUIVALENT, SUPPORTS, COMPLEMENTS, COEXISTS,
  CONDITIONALLY_COMPATIBLE, CONTRADICTS, SUPERSEDES, UNRELATED, UNKNOWN}。
  关键规则：仅时间戳更新不构成 SUPERSEDES（需同一状态变量上的显式更新或互斥后继）；
  时间域不重叠不得标 CONTRADICTS；一般声明与条件例外标 CONDITIONALLY_COMPATIBLE。
- **查询条件化标注**：对每条 k_i 给出
  applicability(k_i | q) ∈ {APPLICABLE, PARTIALLY_APPLICABLE, NOT_APPLICABLE, UNKNOWN}
  与 temporal(k_i | q) ∈ {CURRENT_FOR_QUERY, HISTORICAL_FOR_QUERY,
  SUPERSEDED_FOR_QUERY, FUTURE_OR_NOT_YET_VALID, TIME_INSENSITIVE, UNKNOWN}，
  以及角色 roles(k_i | q) ⊆ {DIRECT_SUPPORT, CORROBORATION, UPDATE, CONTRAST,
  QUALIFIER, BACKGROUND, DISTRACTOR, UNRESOLVED}。
  **同一条声明在不同查询下的标注可以不同**——这是与"全局记忆失效/衰减"类方法的
  本质区别。
- **充分性与风险**：sufficiency ∈ {SUFFICIENT, INSUFFICIENT, AMBIGUOUS} +
  风险标志集（时间歧义、未解决冲突、实体归属不确定、条件丢失风险、
  缺当前/历史状态、证据不足、元数据缺失、疑似提示注入）。
  这为生成器的**弃权决策**提供显式信号。

### 2.3 实现

- Semantic Adapter 由 LLM（默认 claude-opus-5）驱动，系统提示词即研究规范本体
  （qvf/prompts.py），输出经 **API 层结构化输出校验**（Pydantic schema =
  qvf/schema.py），保证 JSON 契约机械可执行而非仅靠提示词约束。
- 封闭证据边界的引用完整性（每条声明必须引用供给的 memory_id）在客户端二次校验，
  违规记为 warning 并纳入分析。
- 生成器两种条件共享同一模型与提示词骨架，唯一差异是有无 Validity Map 及其使用
  规则（历史问题用匹配时间标签的声明；INSUFFICIENT/未解决冲突时弃权；保留条件限定）。

## 3. 实验设计

### 3.1 基准与理由

| 基准 | 角色 | 与 QVF 的契合点 |
|---|---|---|
| LongMemEval（ICLR'25） | 主实验 | 题型直接覆盖 QVF 目标现象：knowledge-update（取代）、temporal-reasoning（时间域匹配）、abstention（充分性）、multi-session（跨会话聚合）、single-session-preference（条件保留） |
| LoCoMo（ACL'24） | 泛化验证 | 超长多会话对话；temporal 与 adversarial（不可回答）类别对应时间标注与弃权 |

### 3.2 条件与对照

主对照（检索器、生成模型、top-k、解码全部持恒）：

1. **baseline**：检索 → 拼接 → 生成（普通 RAG）
2. **prompt-only**：检索 → 自由文本分析（同样两次调用、同一模型、指令涵盖
   QVF 全部关注点，但**无封闭词汇表、无 schema、无机械校验**）→ 生成。
   这是"只是提示词工程"假设做成的基线：完整 QVF 若不能显著优于它，
   则结构化 schema 的贡献被证伪（见 §7 止损线）。
3. **qvf**：检索 → Semantic Adapter → Validity Map 条件化生成

计划消融（结构化梯度）：
- **自由文本 → 仅适用性标签 → +时间标签 → +关系图 → 完整 schema**：
  画出"结构化程度-性能"曲线，无论涨跌都是科学发现
- **filter-only**：只用 Validity Map 过滤记忆（丢弃 NOT_APPLICABLE），
  不把图交给生成器（"过滤 vs 解释"之辨）
- **能力解耦矩阵**：裁决器 × 生成器 = {opus, sonnet, haiku}²——
  强裁决×弱生成能否在同等成本下逼近强模型全程？若能，则证明有效性判定
  是**可分离、可传递的能力**（QVF 独有的科学问题，纯提示词方案无法做此实验）
- **oracle-retrieval**：在 longmemeval_oracle 上重复主对照，剥离检索误差
  （试点已证明 oracle 对 opus-5 存在天花板效应，仅作检索误差剥离用）

### 3.3 指标

**端到端层**（可比性）：
- LLM-judge 正确率（judge 提示词已对齐官方分题型规则：knowledge-update 含更新
  答案即对、temporal off-by-one 容忍、preference 按 rubric、abstention 必须弃权），
  按题型分解；数据用官方推荐的 **cleaned 版**（longmemeval_s_cleaned.json）。
- LoCoMo 附 token-F1；**完整评测含 category 5（adversarial）**——调研显示已发表
  工作从未评过该类别，首次正式评测本身即是贡献点。
- 协议钉死：数据版本 / judge 模型与提示 / 检索预算 / 类别映射 / 置信区间
  全部显式报告（调研发现现有 LongMemEval 数字多为厂商自报、协议混乱）。

**中间层**（QVF 特有的新指标——论文核心卖点，现有基准论文均无此维度）：
1. **引用忠实性**：原子声明的 memory_id 引用对照真值证据
   （LoCoMo `evidence`、LongMemEval `answer_session_ids`/`has_answer`）算
   citation P/R/F1。
2. **有效性标签弱监督准确率**：在 knowledge-update（78 题）与
   temporal-reasoning（133 题）上，由更新链 + question_date + haystack_dates
   程序化推导 SUPERSEDED/CURRENT/HISTORICAL_FOR_QUERY 真值，评适配器标签。
3. **误差分解**：错题归因 = 检索错（证据未进候选）vs 有效性判断错
   （在候选但误标）vs 阅读错（图谱正确但生成器答错）。
4. **充分性校准**：INSUFFICIENT 预测对 `_abs` 与 category-5 的弃权
   precision/recall + 选择性准确率曲线。
5. **干扰项识别**：DISTRACTOR/NOT_APPLICABLE 标签对 filler/干扰会话的识别率。
6. **陈旧内容泄漏率**：最终答案任何位置出现被取代信息的比率（QVF 相对
   无过滤基线的核心收益量化）。
7. **新近度偏差抵抗**：同一目标构造"当前意图 vs 历史意图"查询对，检验
   "更晚时间戳≠取代"论点。

**成本层**：适配器 token 开销、延迟 p50/p95、每题成本——正面回应确定性阵营
（MemStrata 等）的开销批评。

### 3.4 预期结果与可证伪性

- 预期 QVF 的收益集中于 knowledge-update / temporal-reasoning / abstention /
  adversarial 题型；single-hop 简单题型上应大致持平（QVF 不应伤害简单情形——
  若显著下降则假设部分证伪）。
- filter-only 若与完整 QVF 相当，则"结构化解释"的贡献存疑，需修正主张为
  "查询条件化过滤"；若完整 QVF 更优，支持"生成器需要标注而不只是过滤"。

## 4. 预期贡献（依据 2026-07 调研修订的可辩护表述）

调研结论（详见 docs/related_work.md §3-4）：问题空间在 2025-2026 已活跃，
"查询条件化适用性"的**概念表述**已被 MemConflict 基准占用；但**没有任何现有
系统产出 QVF 的目标产物**——把原子声明+引用、9 元关系分类学、逐查询适用性/
时间标签、记忆角色、充分性与风险合并在一起的结构化图谱。据此贡献表述为：

1. **方法**：对 MemConflict 所诊断问题的**首个结构化输出的方法侧回答**——
   Semantic Adapter，一个免训练、模型/检索器/生成器无关的读取时裁决层，
   输出机械可校验（API 层 schema 强制）、可审计的 Validity Map。
   区别于：MemChain（训练型压缩策略，丢弃而非标注）、ConvMemory v3
   （目标条件化过滤，非完整查询条件化标注）、MemStrata/Zep（写入时全局取代
   判定，无法服务历史意图查询的按查询重裁决）。
2. **分类学**：比已发表工作更细的 9 元关系集（CONDITIONALLY_COMPATIBLE、
   SUPERSEDES-vs-CONTRADICTS 之辨等），论文附与知识冲突文献的分类学对齐表。
3. **评测**：一组现有基准论文均未报告的中间层指标（引用忠实性、有效性标签
   弱监督准确率、误差三分解、充分性校准、陈旧泄漏率、新近度偏差抵抗），
   以及 LoCoMo category-5 的首次正式评测与协议卫生实践。
4. **资源**：开源实现 + 实验产出的 Validity Map 语料（可审计中间产物）。

## 5. 风险与应对

| 风险 | 应对 |
|---|---|
| 适配器自身出错（错标 SUPERSEDES 等）反而伤害下游 | 误差三分解单列适配器归因；消融 adapter 模型规模；弱监督标签准确率直接量化 |
| 判分器偏置（Claude 判 Claude） | 全条件同一 judge + 官方分题型规则；附 F1；抽样人工复核；敏感性分析 |
| **MemChain / ConvMemory v3 重合**（同插槽同基准） | 正面区分表 + 把二者思想的提示化近似纳入基线（"目标条件化 vs 查询条件化"、"压缩动作 vs 有效性标签"消融） |
| **确定性阵营反击**（MemStrata：读取路径加 LLM 调用不必要且慢） | 纳入确定性取代规则基线；构造规则欠定案例集（历史查询/条件事实/佐证 vs 更新）；引用 MemStrata 自己的嵌入 AUROC 0.59 与散文取代可靠性 44% 论证语义裁决必要；如实报告成本层指标 |
| **概念首创权**（MemConflict 已占"query-conditioned fitness-for-use"表述） | 不宣称概念首创；定位为"诊断 → 方法"承接关系并引用 |
| 评测可信度（现有数字厂商自报、协议混乱、LoCoMo 金标 6.4% 错误） | 协议全钉死 + 发布假设文件与图谱产物；用 locomo-audit 修正标签做敏感性分析 |
| 成本过高 | oracle 分片先行、--limit 分批、低成本模型消融 |

## 6. 贡献重心迁移与防御性设计（2026-07-31 增补）

针对"只是提示词工程"的预期攻击，贡献重心从"方法赢"迁移到四个免训练但
非提示词的支柱：

1. **可测量的任务层（最高优先）**：用 LongMemEval 结构（更新链 +
   question_date + answer_session_ids + has_answer）程序化推导声明级
   SUPERSEDED/CURRENT/HISTORICAL 弱监督真值，**人工校验数百条**形成
   评测层——"查询条件化有效性判定"由此成为有真值的预测任务，任何系统
   （含 MemChain 类）都可在此层被评。提示词只是"首个基线"的实现细节。
2. **prompt-only 杀手级对照**（已实现，见 §3.2 条件 2）：把攻击者的假设
   做成被检验的基线。
3. **符号一致性校验器**：Validity Map 的内在逻辑约束（SUPERSEDES 与
   CURRENT 标签互斥、DISTRACTOR 与 DIRECT_SUPPORT 互斥、CONTRADICTS
   要求时间域重叠等）用纯代码校验；违规率成为指标，违规触发修复或降级
   弃权——schema 之上的符号推理层，提示词工程无对应物。
4. **诊断对集**：最小对（同记忆的当前/历史意图查询对；仅时间戳 vs 显式
   更新的取代对；复述 vs 真矛盾对），数百对、人工可控，直接检验
   "有效性随查询翻转"与"晚时间戳≠取代"两个核心主张，随论文发布。

**止损线**：若 prompt-only 追平完整 QVF 且弱监督标签准确率不高，则
"结构化裁决层"论题证伪，转向纯评测/诊断论文（任务定义 + 评测层 +
对现有系统的诊断）——该出口不依赖方法赢。

## 7. 时间线（建议）

1. 第 1 周：小规模真实实验（oracle 分片 50 题 × 2 条件），行为定性分析与提示词迭代
2. 第 2-3 周：LongMemEval-S 主实验 + 消融
3. 第 4 周：LoCoMo 泛化 + 诊断分析
4. 第 5-6 周：论文撰写（大纲见 docs/paper_outline.md）
