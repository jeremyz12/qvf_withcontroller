# QVF Research Study Log — 2026-08-01

## 1. 今日研究问题与检索协议

### 研究问题

在 7 月 31 日读完 MemChain 并确认低权限 sidecar 很容易被 Reader 绕过之后，今天的问题不是“再加一种提示是否能多答对几题”，而是：

1. 物理改变 Reader 可见证据的 context surgery 是否有现实论文依据？
2. 如何在 false deletion、证据不足与额外检索之间设计可审计的 controller action？
3. 哪些论文结果可以支持当前 `filtered`/`repaired` 路线，哪些结果因联合训练、gold-answer supervision、retrieval 改变或 Reader 差异而不能迁移？
4. 为什么过滤对弱 Reader 可能有用，对强 Reader 却可能几乎没有净收益？

### 检索范围与纳入规则

- 检索日期：2026-08-01。
- 一手来源：ACL Anthology、ICLR Proceedings/OpenReview 与 arXiv 原始论文 PDF。
- 主题组合：`post-retrieval context filtering`、`context compression`、`selective augmentation`、`corrective retrieval`、`evidence sufficiency`、`knowledge selection generator strength`。
- 纳入：干预发生在 retrieval 后、Reader 前，或能直接约束 QVF 的 `RETRIEVE_MORE` 动作；有完整方法、实证与可核查的限制。
- 排除：纯 retriever、memory writer、survey、只改向量索引/KV cache、回答生成后的修补，以及无法区分 post-retrieval 独立贡献的宣传性材料。

### 最终纳入的五篇

| 论文 | 选择理由 | 在今日证据链中的位置 |
|---|---|---|
| [FILCO](https://arxiv.org/abs/2311.08377) | 直接测试细粒度 filtered context 替代 full passage，并报告多任务正向结果 | `SELECT` / context surgery 的正向先例与联合训练混淆 |
| [RECOMP](https://proceedings.iclr.cc/paper_files/paper/2024/hash/bda88ed2892f5e61c9a9bf215c566913-Abstract-Conference.html) | 把短 extractive/abstractive context 送给黑盒 Reader，并允许 empty augmentation | `SELECT` / `EMPTY`、token–accuracy 权衡与 hallucinated summary 风险 |
| [ECoRAG](https://aclanthology.org/2025.findings-acl.1365/) | 在固定的大候选池中按 evidentiality 排序，并用 sufficiency evaluator 决定继续加入证据 | `EXPAND_WITHIN_POOL` 与 sufficiency gate |
| [CRAG](https://arxiv.org/abs/2401.15884) | 按检索质量采取 correct/incorrect/ambiguous 路由，必要时扩展到网络检索 | `RETRIEVE_MORE` 的先例与 retrieval-gain 归因边界 |
| [How Does Knowledge Selection Help RAG?](https://aclanthology.org/2025.findings-emnlp.218/) | 用可控 gold/distractor 混合研究 selector、recall、Reader 强弱与任务歧义 | 判断“何时值得过滤”及当前弱 Reader 实验的理论边界 |

另全文筛选了 Sufficient Context、Astute RAG、SELF-multi-RAG，以及 citation-grounding compression 工作；它们保留为补充文献，不与上述五篇混算。

## 2. Claude 当前方向与本地代码审计

### 2.1 三条实际路径

| 路径 | Reader 实际看到什么 | 权限与状态 |
|---|---|---|
| `prompted`（7/31 历史臂） | engine sidecar，但 sidecar 内仍嵌完整 raw BM25 top-10 | 低权限 advisory；105 题完成，Direct 与 Prompted 均为 18/105、3 wins/3 losses/99 ties |
| `filtered`（8/1 新臂） | engine 获准 evidence 对应的原始 memory rounds；无可靠映射、engine 失败或空集时回退 full raw | 高于 advisory 的 evidence delivery；正式运行中，本文不查看中途效果调参 |
| `repaired`（8/1 新臂） | 先抽取/裁决；失败条件触发一次实例内 BM25 补检索，最多加入 5 条，再抽取、裁决与过滤 | 代码和 mock plumbing 已接通，尚未正式运行 |

### 2.2 对当前叙事的必要修正

1. `filtered` 发生在 memory-round 粒度，不是 atomic span；同一 round 内未裁决的内容仍会一起进入 Reader。
2. `repaired` 当前没有消费 engine 输出的结构化 `suggested_retrieval_scope`。repair query 来自 LLM 抽取的 entity/slot 加一组固定 update terms，且只执行一次，不是三次闭环。
3. mock plumbing 只证明控制流与 BM25 可以跑通，不证明抽取、关系、裁决或过滤有语义效果。
4. record rejection 率只衡量 schema/span contract 是否通过，不等于 semantic extraction accuracy。
5. Global Oracle 同时改变 retrieval、distractor removal、gold pairing、relation、render 与 Reader context，不能把其高分归为“上下文更短”或 engine 独立贡献。
6. `filtered`/`repaired` 是在看过同一 35-item STALE cohort 的失败后形成的 development routes。即使得到正向结果，也必须冻结后在未见 holdout 或另一数据协议上验证。

### 2.3 与 7 月 31 日 MemChain 启发的对应关系

| MemChain 后形成的设想 | 当前进展 | 尚缺什么 |
|---|---|---|
| Active evidence 替代完整候选 | `filtered` 首次让获准 evidence 控制 Reader 可见上下文 | atomic span、coverage audit、false-deletion 评估与完整结果 |
| `ADD` 变为受约束补检索 | `repaired` 已有一次补检索骨架 | 结构化 RetrievalRequest、真实来源约束、独立 retrieval-gain 归因 |
| Plan + ID-grounded trace | 尚未实现 | query evidence plan、所有竞争候选的 keep/drop/unresolved 解释 |
| Benchmark-independent 训练 | 尚未实现 | 独立机制数据、SFT 监督与严格 holdout |
| 组件消融 | 尚未闭合 | matched render、extraction-only、engine-only、fixed-pool expand 与 external repair 分臂 |

## 3. Paper 1 — Learning to Filter Context for Retrieval-Augmented Generation（FILCO）

### 系统边界与方法

FILCO 位于 DPR top-1/top-5 passages 与 Generator 之间。`M_ctx` 根据 query 生成过滤后的句子级 context，`M_gen` 只看 filtered context，不再看完整 passage。这个权限结构与 8 月 1 日 `filtered` 分支相近：它改变 evidence delivery，而不是在 full context 旁边再附一段建议。

训练监督并不满足当前 QVF 的 Benchmark-independent 约束。STRINC、LEXICAL 与 CXMI 三种 silver-label 构造都使用训练集 canonical output；不同数据集还采用不同策略。论文同时训练 filter 与在 filtered-context 分布上回答的 Generator，因此结果不能解释为“固定 Reader 前插入 filter”的纯独立贡献。

### 实证与成本边界

- Top-1 主实验相对 FULL 的六任务平均提升：FLAN-T5 +2.8 points，LLaMA2 +3.0 points；论文未给置信区间或显著性检验。
- Top-5、FLAN-T5（Table 5）：NQ `47.6→61.8`、TQA `67.3→71.1`、HotpotQA `61.5→65.0`、ELI5 `72.7→73.9`、FEVER `88.0→91.4`、WoW `64.8→66.0`。
- filtered context 使 Generator 输入长度减少 44%–64%。论文的“至少 4.7×”只针对 generation model；系统仍要额外运行 3B/7B filter，没有端到端 latency/FLOPs 账本。
- Table 4/5 的部分 run 与 FEVER strategy 描述不完全一致，本文只按各表分别报告，不拼接成单一 run。

### 对 QVF 的可迁移结论

- 细粒度 context surgery 有现实正向先例，当前方向不是凭空想象。
- QVF 应优先采用 candidate-ID/source-span 可追溯的 extractive view，并保存 raw archive/fallback。
- 必须固定 Reader 做 filter-only 消融，否则收益可能来自 Generator 对 filtered-context 分布的联合适配。
- 不能把 gold-answer-dependent silver target 或数据集策略映射搬进 MemConflict、STALE、LongMemEval、LoCoMo 的评测规则。

FILCO 让我更确定，过滤本身是一个有现实依据的方向，真正的问题是怎样学会过滤。它的正向结果建立在 filter 和 Generator 都经过训练的条件下，因此对我现在这个未经专门训练、面对固定黑盒 Reader 的 QVF，仍然需要单独实验。我的下一步会把重点从设计更多 prompt 转向获得可靠的、与 Benchmark 独立的 selection supervision，并用固定 Reader 验证 context surgery 的贡献。

## 4. Paper 2 — RECOMP: Improving Retrieval-Augmented LMs with Context Compression and Selective Augmentation

### 系统边界与方法

RECOMP 明确固定 retriever，输入 query 与 top-5 documents，压缩器输出短 context，再 prepend 给黑盒 Reader。Extractive compressor 从候选句中选 1 句（HotpotQA 选 2 句）；Abstractive compressor 生成摘要，并允许输出空字符串，等价于“不注入 retrieval”。

其训练高度依赖 gold target 与目标 Reader utility：extractive 正例按某句对生成 gold answer 的帮助选择，abstractive target 也按是否改善 gold output 筛选；不同 QA 数据集分别训练 compressor。因此可借机制，不能照搬标签协议。

### 实证与成本边界

Table 2、Flan-UL2 20B：

| 数据集 | Full top-5 | Extractive | Abstractive |
|---|---:|---:|---:|
| NQ | 660 tokens / 39.39 EM | 37 / 36.57 | 36 / 37.04 |
| TriviaQA | 677 / 62.37 | 38 / 58.99 | 32 / 58.68 |
| HotpotQA | 684 / 32.80 | 75 / 30.40 | 64 / 28.20 |

最稳妥的结论是：相对 full top-5，RECOMP 将 Reader context 压到约 4.7%–11.0%，但损失约 2.35–4.60 EM；它主要提供效率–准确率权衡，不是普遍准确率提升。oracle 可同时明显提分与减 token，但它按 gold answer/Reader 表现选句，不能当作可部署 controller 结果。

当 gold answer 不在 evidence 中时，NQ 的 full top-5 Reader 仍从 evidence 复制答案的比例为 81%；learned extractive/abstractive 分别降到 33%/39%（Table 3）。这支持“过滤可降低错误服从”这一问题动机，但只是字符串复制启发式，不等于 temporal/conflict validity。

Abstractive faithfulness 也构成直接警告：每数据集仅 30 个非空摘要的人评中，fully faithful 为 NQ 80%、TQA 83%、HotpotQA 67%；HotpotQA 的 faithful+comprehensive 只有 40%。论文只报送入 Reader 的 context token，没有计入 110M/775M compressor 的端到端开销。

### 对 QVF 的可迁移结论

- `PASS / SELECT / EMPTY` 是合理的最小 action set；空 context 必须配合 abstain/defer 或安全 fallback。
- QVF 更适合 source-preserving extractive surgery，不应把自由摘要视为权威 memory。
- 必须同时记录 false deletion、evidence recall、Reader tokens、controller tokens、总 latency 和 downstream accuracy。

我可以接受在明确部署场景下，用很小的准确率损失换取显著的 token 和延迟下降，不过 QVF 的首要目标仍然是减少模型对过期、冲突或条件不匹配 memory 的错误使用，效率属于第二条价值线。如果答案质量和证据可追溯性保持稳定，同时 Reader context 明显缩短，这本身也可以构成有用的结果。报告时需要把 controller 的额外成本与 Reader 的节省放在同一份账本中比较。

## 5. Paper 3 — ECoRAG: Evidentiality-guided Compression for Long Context RAG

### 系统边界与方法

ECoRAG（Jeong et al., Findings of ACL 2025）假定 retriever 已经提供 top-100 documents，不改变 retriever。系统先把 query 与 documents 分句，用 dual encoder 按 evidentiality 排序；Flan-T5-large evaluator 从第一条证据开始判断当前集合是否足以回答，不足时每轮从同一个预取池再加入 4 句，最多 20 句，最后把 extractive evidence set 交给 Reader。论文所说的 adaptive retrieval 实际是 `EXPAND_WITHIN_POOL`，不是重新搜索外部语料。

训练依赖 gold answer 与特定 Reader。Flan-UL2 通过反事实问答结果把句子标为 strong evidence、weak evidence 或 distractor；dual encoder 学排序，evaluator 学 `<EVI>/<NOT>` 充分性分类。因此其训练方法不能直接用于 QVF 目标 Benchmark，但“先点式排序、再集合式 sufficiency gate”是可迁移机制。

### 实证、消融与边界

Table 1、GPT-4o-mini：

| 数据集 | Standard RAG | ECoRAG |
|---|---:|---:|
| NQ | 13,905 tokens / 36.09 EM / 50.18 F1 | 632 / 36.48 / 49.81 |
| TriviaQA | 14,167 / 56.21 / 64.22 | 441 / 65.34 / 75.37 |
| WebQuestions | 13,731 / 21.11 / 38.72 | 560 / 30.17 / 46.13 |

这组结果显示大幅缩短 Reader context，并在 TQA/WQ 明显提分；但 NQ 的 F1 `50.18→49.81` 略降。相对论文最强压缩 baseline CompAct，ECoRAG 的 EM 增益只有 NQ +0.77、TQA +1.38、WQ +0.40 points。不能把“优于未压缩 RAG”与“selector 的独立贡献”混为一谈。

Table 3 中去掉 evaluator，NQ/TQA EM 分别下降 0.77/1.80 points；这为 sufficiency gate 提供了小而直接的消融依据。Table 4 的 Flan-UL2/NQ 总时间是 Standard RAG 12.28 h、RECOMP 4.35 h、ECoRAG 4.96 h、CompAct 14.94 h；这是特定实验总时长，不等同于在线单请求 latency。跨 Reader 结果也不普遍优于 closed-book：Llama3 在 TQA/WQ 上 closed-book 为 60.89/21.79，ECoRAG 为 59.25/21.60。

### 对 QVF 的可迁移结论

- Controller 不应只输出一次性 keep/drop；还应有 `EXPAND_WITHIN_POOL`，在 evidence validity 尚可但 coverage 不足时逐步扩大 evidence view。
- sufficiency 必须与 truth/temporal validity 分开：一组 evidence 足以让 Reader 构造答案，不代表答案真实、最新或来源可信。
- QVF 应保留 sentence/record/source ID；ECoRAG 的 answer-derived evidentiality 只能由独立机制数据替代，不能用目标 Benchmark 答案挖标签。
- ECoRAG 不支持外部 `RETRIEVE_MORE` 的效果结论，也不处理替代、共存、条件限定与 observation/effective time。

我更愿意先在固定 top-k 内做渐进扩展。这样可以比较清楚地判断，收益究竟来自 evidence selection 和 sufficiency gate，还是来自新增检索覆盖。只有当系统能明确说明当前候选缺了什么，而且固定池内确实找不到时，我才希望它请求一次外部补检索。这个顺序也能避免 QVF 很快膨胀成一个完整 RAG 系统。

## 6. Paper 4 — Corrective Retrieval Augmented Generation（CRAG）

### 系统边界与方法

CRAG（Yan et al., arXiv:2401.15884v3）输入 query 与 Contriever top-10。T5-large 0.77B evaluator 先给每个 query–document pair 打分，controller 再执行三种高权限动作：

- `Correct`：保留初始来源，但切成 text strips、过滤并重组；
- `Incorrect`：丢弃原始 retrieval，改用 Google Search；
- `Ambiguous`：合并过滤后的原 retrieval 与 web search。

它是 `USE / RETRIEVE / COMBINE` 的现实先例，但并非通用无监督 controller。evaluator 用 PopQA gold subject Wikipedia title 构造正例，阈值又按 benchmark 设置：PopQA `(0.59,-0.99)`、PubHealth/ARC `(0.50,-0.91)`、Biography `(0.95,-0.91)`。Web query 由 GPT-3.5 改写为至多三个关键词，只执行一次 web branch，没有多轮 repair loop。

### 实证、消融与成本边界

Table 1：

| Reader / 方法 | PopQA | Biography | PubHealth | ARC |
|---|---:|---:|---:|---:|
| LLaMA2-hf RAG | 50.5 | 44.9 | 48.9 | 43.4 |
| LLaMA2-hf CRAG | 54.9 | 47.7 | 59.5 | 53.7 |
| SelfRAG-LLaMA RAG | 52.8 | 59.2 | 39.0 | 53.2 |
| SelfRAG-LLaMA CRAG | 59.8 | 74.1 | 75.6 | 68.6 |
| SelfRAG-LLaMA Self-RAG | 54.9 | 81.2 | 72.4 | 67.3 |
| SelfRAG-LLaMA Self-CRAG | 61.8 | 86.2 | 74.8 | 67.2 |

CRAG 相对 vanilla RAG 在表中四项均提高；但 Self-CRAG 相对 Self-RAG 的 ARC 是 `67.2 vs 67.3`，不能写成所有配置均提高。Table 3 中 CRAG 54.9；去 refinement 为 49.8、去 query rewriting 为 51.7、去 web selection 为 50.9。Table 5 又表明单纯给 RAG 加同一批 web 内容仍弱于完整 CRAG，所以收益不全是额外 retrieval coverage；但也不能从联合 pipeline 反推出 evaluator 或 filter 的独立贡献。

Table 6 报 CRAG 27.2 TFLOPs/token、0.512 秒/实例，RAG 为 26.5、0.363；该表明确排除 retrieval 与 data processing，没有计入 Google Search、页面抓取、query rewrite 和 strip filtering，不能当作完整系统开销。

### 对 QVF 的可迁移结论

- 将 action 明确分成 `USE / RETRIEVE_MORE / COMBINE / DEFER`，比只输出 annotation 更有执行力。
- 原候选 validity 与 candidate coverage 必须分开：补检索的收益单独报告，不能都归给 QVF adjudication。
- CRAG evaluator 只判断 query relevance，不判断时间有效性、替代/共存、来源权威或 memory role；QVF 不能照搬其 benchmark 阈值与 gold-title supervision。
- 当前 `repaired` 的 generic update terms 应作为 development baseline；正式版本应输出基于 grounded records 的结构化 RetrievalRequest，并记录 query、来源、added IDs 与触发理由。

现阶段我会先把外部动作限制为一次可审计的补检索。对我来说，重要的不是循环次数，而是系统能否说明为什么需要补检索、缺少哪一类证据、查询由哪些已有记录推导出来，以及新加入的 memory 最后起了什么作用。先验证一次结构化补检索能否稳定提高 coverage，再根据结果决定是否有必要增加循环，这样也更容易控制成本和解释收益来源。

## 7. Paper 5 — How Does Knowledge Selection Help Retrieval Augmented Generation?

### 研究设计与系统边界

Li 与 Ouyang（Findings of EMNLP 2025）没有提出可部署 selector，而是在有 gold/distractor 标注的固定候选池中，用 `p_gold` 与 `p_noise` 随机抽样 evidence subset，系统研究 knowledge precision、recall、Reader 能力与 answer F1 的关系。它不改 query、不重检索、不判时间关系；价值在于给“什么时候过滤值得做”提供受控机制证据。

数据是 WoW test-seen 前 100 段对话（452 个 wizard utterances）与 HotpotQA training 前 500 个 case；Readers 为 GPT-4o-mini-2024-07-18、Llama 3.1 8B Turbo、Mistral-7B-Instruct-v0.1。无 selector 训练，但实验依赖不可部署的 gold/distractor labels。

### 关键结果

| 数据集 / Reader | 无知识 F1 | 全候选 F1 | 仅 gold F1 |
|---|---:|---:|---:|
| HotpotQA / GPT-4o-mini | .437 | .780 | .828 |
| HotpotQA / Llama 3.1 8B | .298 | .545 | .671 |
| HotpotQA / Mistral 7B | .260 | .151 | .627 |
| WoW / GPT-4o-mini | .200 | .251 | .276 |
| WoW / Llama 3.1 8B | .216 | .248 | .278 |
| WoW / Mistral 7B | .203 | .233 | .268 |

这组边界非常重要：GPT-4o-mini/HotpotQA 的 full→gold gap 只有 `.048`，纯 selector 可争取空间很小；Mistral/HotpotQA 的 full context 反而低于 no-knowledge `.109`，弱 Reader 被 distractor 严重破坏，过滤空间很大。强 Reader 的 answer F1 主要随 knowledge recall 变化；弱 Reader 且 distractor 清晰时，knowledge F1 更关键。WoW 的“distractor”常能支持合理回答，过滤收益会非单调；当 recall 已低时继续提高 precision，甚至会进一步伤害答案。

论文还对 gold label 注入 false negative：即使表面为 100% precision 的 selector，也可能输给 full context。这直接要求 QVF 把 evidence recall 与 false deletion 作为一等指标。k=3 长度约束没有改变整体趋势，说明“更短”本身不等于“更准”。

### 因果与迁移边界

论文随机操纵证据组成，因而对固定 Reader/数据集下 precision–recall 改变具有较强机制证据；但 Reader 强弱比较跨模型，任务歧义主要跨 WoW/HotpotQA，并非完整因子随机化，不能外推为所有长期记忆任务的普遍定律。

对 QVF 的直接启发是：

1. 先报告 `no memory / full raw memory / gold-within-retrieved-pool` 三个边界；full–gold gap 才是 selection 理论空间。
2. `filtered` 应把 recall/coverage failure 置于 precision 之前，并保留 raw archive、`DEFER` 或 fallback。
3. Reader strength 必须预注册分层。若 context surgery 只帮助弱 Reader，这可以是清晰适用边界，不应伪装成普遍提升。
4. 强 Reader 的 full–gold gap 很小时，更值得研究 validity-specific harm、可审计性和在 evidence 不充分时保 recall 的定向补检索，而不是更激进删除。

如果强 Reader 已经能较好处理普通噪声，我不认为 QVF 必须在所有问题上继续追求 raw accuracy 提升。它更可能在高风险子集上体现价值，例如避免把旧状态当成当前状态、保留答案的来源与时间依据、在证据不足时选择 `DEFER`，以及减少不必要的上下文。相反，如果 QVF 只是在所有问题上重复一次分析，却没有降低错误使用率或成本，那么即使结构看起来完整，也很难说明它有实际价值。

## 8. 五篇论文共同支持什么、不支持什么

### 可以支持的研究命题

1. Reader 会被检索噪声或不受支持证据影响；在 retrieval 与 generation 之间实际改变 evidence view，具有现实研究依据。
2. 过滤不是越强越好。可部署 controller 必须在 precision、recall、false deletion、abstention、token 与 latency 之间给出 utility–risk–cost 曲线。
3. “现有 evidence 无效”和“现有 evidence 不充分”是两个不同问题：前者需要隔离/降级，后者需要扩大固定池或请求补检索。
4. 提升 selector precision 的收益依赖 Reader 能力、任务歧义和检索 recall；这能解释为何同一 QVF 在弱 Reader、强 Reader和不同 benchmark 上可能表现不同。
5. 外部补检索带来的新 evidence coverage 必须与固定候选上的 QVF mediation 分开归因。

### 现有证据的解释边界

- 论文中的 filter/compressor 正向结果说明这类机制具有可行性；当前 QVF 的实际效果仍由本项目的冻结对照确定。
- FILCO 报告的是 filter 与 Generator 联合训练结果；独立 controller 贡献需要在固定 Reader 下另做消融。
- RECOMP oracle、CRAG 网络检索和 gold-answer supervision 分别代表上限或扩展 pipeline；可部署 QVF 成绩采用不含这些信息的独立测试协议。
- 更短 prompt 只直接说明 Reader-side context 下降；端到端成本同时计算 controller、filter、补检索和二次抽取。
- relevance 与 sufficiency 各自作为辅助判断维度；真实性、时间有效性和 memory role 继续由独立证据与关系裁决负责。

## 9. 由文献收敛出的 QVF vNext

### 9.1 建议接口

```text
Query + RetrievedMemory[] + authentic metadata
    -> EvidencePlan
    -> grounded Record[] + CoverageReport
    -> Validity/Sufficiency adjudication
    -> ControllerAction
       PASS
       SELECT(memory_ids / spans)
       EMPTY_OR_DEFER(reason)
       EXPAND_WITHIN_POOL(scope)
       RETRIEVE_MORE(RetrievalRequest)
    -> Reader-visible EvidenceView + provenance + raw archive handle
```

`RetrievalRequest` 至少应包含 `entity`、`slot`、`temporal_need`、`missing_evidence`、`exclude_values`、`source_constraints` 与触发原因。它必须由已有 grounded records 和 coverage failure 产生；不能由未经验证的答案草稿、case ID、类别或残差措辞生成。

### 9.2 对当前代码的最小修正顺序

1. 先完成并冻结现有 `filtered` 结果，不看中途得分调规则；记录每题选中/删除 ID、fallback、tokens 与 latency。
2. 在正式运行 `repaired` 前，把手写 update expansion terms 与结构化 `RetrievalRequest` 分成两个可审计臂；固定一次 repair，暂不扩展三次循环。
3. 增加 coverage report：每个竞争候选均须解释为 kept、blocked、historical、irrelevant 或 unresolved；关键 pair 不完整时不得假装可答。
4. 把 `observed_at` 与 `effective_from` 分开；不能继续把 session date 自动当作状态生效时间。
5. 只有无 API 的 span/relation/coverage 质检通过后，才在独立 holdout 上运行 Reader/API；保留零或负结果。

## 10. 下一轮因果实验与验收

### 固定候选实验：只测 post-retrieval mediation

至少包括：Direct full context、matched-render full context、Extraction-Only neutral view、Extraction+Engine selected view、retrieval-fixed gold selection oracle。必须固定同一 top-k、Reader、回答 prompt skeleton；gold 不在 top-k 时记 retrieval failure，不允许注入。

### 补检索实验：单独测候选覆盖改善

至少包括：Direct fixed retrieval、generic repair query、structured RetrievalRequest、retrieval oracle。分别报告 repair trigger precision、added-evidence recall、无效额外检索、二次抽取失败、token/latency 与最终答案变化。

### 验收指标

- Answer：paired wins/losses/ties、cluster bootstrap CI、abstention-aware utility。
- Evidence：gold-span recall、false deletion、blocked-as-current precision、coverage completeness、provenance/source-ID preservation。
- Controller：PASS/SELECT/DEFER/EXPAND/RETRIEVE_MORE 的路由准确度与错误条件下 harm。
- Cost：controller 与 Reader input/output tokens、wall-clock latency、额外 retrieval 次数。
- Generalization：冻结后跨 MemConflict、STALE、LongMemEval、LoCoMo 协议分别报告，不把不同版本/Reader 的历史分数聚合成当前结果。

### Reader-strength 设计

弱 Reader 与强 Reader 应是预注册分层而非看到结果后的补救。若过滤只帮助弱 Reader，这仍可能是有价值的 deployment boundary；若强 Reader 对 full context 已很鲁棒，则 QVF 的价值可能主要体现在 validity risk、可审计证据和成本，而不是 raw accuracy。

## 11. 可用于下一次汇报的暂定一句话

> 7 月 31 日的文献审计表明，QVF 的研究价值取决于它是否真正控制 Reader 所使用的证据，以及各个组件能否被独立验证。8 月 1 日的工作已经把旧版低权限 annotation 推进为可执行的 evidence selection 与 failure-triggered retrieval repair。现有论文为这两类机制提供了依据；接下来将过滤、Reader 适配、检索覆盖和成本分开评估，并以冻结实验结果确定最终收益。

## 12. 我的当前判断

读完这五篇后，我更愿意把 QVF 定位成一个以 validity risk 为核心、同时记录 utility 和 cost 的 controller，而不是单纯的 efficiency module。它首先要回答的是：当前检索到的 memory 是否适用于这个 query、证据是否足够，以及 Reader 应该看到哪些内容；只有在这些判断可靠以后，token 节省才构成额外价值。

对于 false deletion，我目前倾向于保守。只要关键 evidence 的 coverage 不完整，系统就进入 `DEFER`、扩大固定候选池，或回退到带风险提示的 full context。具体误删率门槛将由独立标注集和 accuracy–coverage 曲线确定，而不是提前凭经验设定。

我也可以接受 QVF 的收益存在明确适用边界。例如，它可能主要帮助较弱的 Reader、较长且噪声较多的上下文，或者真正包含时间冲突的 case，而对强 Reader 和简单问题接近 pass-through。只要这个边界是预先定义并由独立数据验证的，它仍然可以构成有价值的研究结论，没有必要强求所有数据集都普遍提升。

下一次汇报时，我会先强调这两天形成的架构修正和因果诊断：QVF 已从低权限 annotation 转向实际控制 evidence view，并开始区分 evidence invalid 与 evidence insufficient；同时也明确了历史 adapter、Reader 适配和额外 retrieval 需要分别归因。后续重点是构造与 Benchmark 独立的 controller 训练数据，并用冻结 holdout 给出最终的效果判断。

---

## Evidence Matrix

### 0. 最终五篇与本地证据

| Paper | Status / venue | Local PDF | SHA-256 |
|---|---|---|---|
| [*Learning to Filter Context for Retrieval-Augmented Generation*](https://arxiv.org/abs/2311.08377) | arXiv:2311.08377 v1 preprint | `docs/papers/2026-08-01/FILCO_2311.08377.pdf` | `88C58A9D6F0A2F992097634790CAB5D3454943DE5DF2C07BB61FA6DF2A769E52` |
| [*RECOMP: Improving Retrieval-Augmented LMs with Context Compression and Selective Augmentation*](https://proceedings.iclr.cc/paper_files/paper/2024/hash/bda88ed2892f5e61c9a9bf215c566913-Abstract-Conference.html) | ICLR 2024；本地 PDF 为 arXiv v1，标题少 “Context” | `docs/papers/2026-08-01/RECOMP_2310.04408.pdf` | `9D8AA7881E786D6B3593FE6C60BC2E52944AEE82AB6CA577097618BAF8D21066` |
| [*ECoRAG: Evidentiality-guided Compression for Long Context RAG*](https://aclanthology.org/2025.findings-acl.1365/) | Findings of ACL 2025 | `docs/papers/2026-08-01/ECoRAG_2025.findings-acl.1365.pdf` | `BD8445E34E39429DE2F8508AD6D261049FB77AF288FAB8025EF72D4F35D5A7DE` |
| [*Corrective Retrieval Augmented Generation*](https://arxiv.org/abs/2401.15884) | arXiv:2401.15884 v3 preprint | `docs/papers/2026-08-01/CRAG_2401.15884.pdf` | `975AA1FD3C1B603126E93FF99D6504858B61301BF1D34C9DF88EBE53A0B026CB` |
| [*How Does Knowledge Selection Help Retrieval Augmented Generation?*](https://aclanthology.org/2025.findings-emnlp.218/) | Findings of EMNLP 2025 | `docs/papers/2026-08-01/Knowledge_Selection_RAG_2025.findings-emnlp.218.pdf` | `3024CFB478F8C334441BEB3DB351E374551B31E8304A4D98B2C5E5F8073612D8` |

### 1. FILCO

| Evidence item | Full-text finding | QVF boundary |
|---|---|---|
| Authors | Zhiruo Wang, Jun Araki, Zhengbao Jiang, Md Rizwan Parvez, Graham Neubig | 预印本，不写成正式 ACL 接收论文 |
| Stage | DPR top-1/top-5 后，生成式 `M_ctx` 用 filtered text 替代 full passage；另训练 `M_gen` | 与 `filtered` 权限相近，但不是固定黑盒 Reader 的纯插件实验 |
| Supervision | STRINC/LEXICAL/CXMI 均使用 canonical output；任务选择不同策略 | 不能从目标 Benchmark 答案/类别构造 QVF labels |
| Main results | Top-1 六任务平均：FLAN-T5 +2.8、LLaMA2 +3.0 points。Top-5 FLAN-T5：NQ 47.6→61.8、TQA 67.3→71.1、HotpotQA 61.5→65.0、FEVER 88.0→91.4 | context surgery 有正向先例；无 CI/显著性，且 filter+Generator 联合训练 |
| Cost | Generator 输入减少 44%–64%；“≥4.7×”只指 generation model | 未计 3B/7B filter，总 latency/FLOPs 未报告 |
| Internal inconsistency | §4.2、Table 4、Table 5 的 FEVER strategy/run 存在未解释差异 | 各表分别引用，不拼成同一 run |
| Transfer | ID-grounded extractive view、raw archive、matched Reader control | 不支持 temporal validity、replacement、coexistence 或 provenance guarantee |

### 2. RECOMP

| Evidence item | Full-text finding | QVF boundary |
|---|---|---|
| Authors | Fangyuan Xu, Weijia Shi, Eunsol Choi | ICLR 2024；本地 arXiv v1 标题略不同 |
| Stage/actions | 固定 retriever；extractive 选 1 句（Hotpot 2），abstractive 生成摘要，可输出 empty string | 支持 `SELECT/EMPTY`；abstractive 无 candidate-ID 约束 |
| Supervision | 用 gold target 与目标 Reader utility 选正例/摘要；各数据集单独训练 | 不满足目标 Benchmark 独立训练 |
| Main results | Full top-5→extractive：NQ 660 tok/39.39 EM→37/36.57；TQA 677/62.37→38/58.99；Hotpot 684/32.80→75/30.40 | 主要是 4.7%–11% context 与 2.40–3.38 EM 损失的 trade-off，不是普遍提分 |
| Wrong-copy signal | NQ gold 不在 evidence 时，从 evidence 复制答案：full 81%，extractive 33%，abstractive 39% | 支持“过滤可降低错误服从”，但只是字符串启发式 |
| Faithfulness | 每数据集 30 例人评；abstractive fully faithful：NQ 80%、TQA 83%、Hotpot 67% | 自由摘要不能作权威 memory；优先 extractive provenance |
| Cost | 只报 Reader context token | 未计 110M/775M compressor、总 latency/FLOPs |

### 3. ECoRAG

| Evidence item | Full-text finding | QVF boundary |
|---|---|---|
| Authors/venue | Jeong, Kim, Lee, Hwang；Findings ACL 2025，pp.26607–26628 | 正式同行评审论文 |
| Stage/actions | retriever 预取 top-100；句级 evidentiality 排序；sufficiency 不足时每次加 4 句，最多 20 | 是 `EXPAND_WITHIN_POOL`，不是外部 re-retrieval |
| Supervision | Flan-UL2+gold answer 反事实标 strong/weak/distractor；evaluator 学 `<EVI>/<NOT>` | Reader/答案依赖，不能用于目标 Benchmark label |
| Main results | GPT-4o-mini：NQ 13,905 tok/36.09/50.18→632/36.48/49.81；TQA 14,167/56.21/64.22→441/65.34/75.37；WQ 13,731/21.11/38.72→560/30.17/46.13 | TQA/WQ 正向，NQ F1 略负；相对最强压缩 baseline EM 只 +0.77/+1.38/+0.40 |
| Evaluator ablation | 去 evaluator，NQ/TQA EM 降 0.77/1.80 | sufficiency gate 有小而直接的独立证据 |
| Cross-reader | Llama3 TQA/WQ closed-book 60.89/21.79，ECoRAG 59.25/21.60 | 不能宣称普遍优于不使用 retrieval |
| Transfer | strong/weak/distractor + sufficiency + 动态 evidence amount | sufficiency≠truth/temporal validity；必须保 record/source ID |

### 4. CRAG

| Evidence item | Full-text finding | QVF boundary |
|---|---|---|
| Authors/status | Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling；arXiv v3 | 预印本，不写成正式 venue 论文 |
| Stage/actions | Contriever top-10→T5 evaluator→Correct/Incorrect/Ambiguous；分别内部 refine、Google Search 或合并 | 高权限 corrective RAG；会改变 corpus，不是纯 fixed-candidate QVF |
| Trigger | evaluator `[-1,1]`；benchmark-specific thresholds：PopQA `(0.59,-0.99)`、PubHealth/ARC `(0.50,-0.91)`、Biography `(0.95,-0.91)` | 阈值不能迁移为 QVF 规则；它判断 relevance 而非 validity |
| Supervision | PopQA gold subject Wikipedia title 构造 evaluator labels | 不符合 Benchmark-independent 要求 |
| Main results | LLaMA2-hf RAG→CRAG：PopQA 50.5→54.9、Biography 44.9→47.7、PubHealth 48.9→59.5、ARC 43.4→53.7；SelfRAG-LLaMA RAG→CRAG 52.8→59.8、59.2→74.1、39.0→75.6、53.2→68.6 | vanilla RAG 对比均正向；Self-CRAG vs Self-RAG 的 ARC 67.2 vs 67.3，并非全配置提高 |
| Ablation | CRAG 54.9；去 refinement 49.8、去 query rewrite 51.7、去 web selection 50.9 | filter/query rewrite/web selection 都有贡献，仍是联合 pipeline |
| Cost | 27.2 TFLOPs/token、0.512 s vs RAG 26.5、0.363 | 明确排除 retrieval/data processing，不能代表完整 web-repair 成本 |
| Transfer | `USE/RETRIEVE/COMBINE/DEFER` 与一次结构化 repair | 不支持长期 memory conflict、时间有效性或来源真实性 |

### 5. How Does Knowledge Selection Help RAG?

| Evidence item | Full-text finding | QVF boundary |
|---|---|---|
| Authors/venue | Xiangci Li, Jessica Ouyang；Findings EMNLP 2025，pp.4104–4121 | 实证分析，不是可部署 selector |
| Design | 固定 gold/distractor pool，用 `p_gold/p_noise` 随机抽样，操纵 evidence precision/recall | 对固定 Reader/数据集有较强机制证据；依赖部署不可得的 gold labels |
| Data/Readers | WoW 452 utterances；HotpotQA 500 cases；GPT-4o-mini、Llama3.1 8B、Mistral7B | 小子集、三种轻量 Reader；不含 temporal/conflict/provenance |
| Hotpot results | no/full/gold F1：GPT-4o-mini .437/.780/.828；Llama .298/.545/.671；Mistral .260/.151/.627 | 强 Reader full–gold gap 小；弱 Reader 会被 distractor 严重伤害 |
| WoW results | GPT-4o-mini .200/.251/.276；Llama .216/.248/.278；Mistral .203/.233/.268 | “distractor”可能支持合理回答，过滤收益非单调 |
| Mechanism | 强 Reader 主要受 recall 影响；弱 Reader+清晰噪声更依赖 knowledge F1；低 recall 时继续删证据可伤害 | QVF 必须优先 coverage/recall，并预注册 Reader-strength 分层 |
| Label-noise intervention | gold false negative 会使表面 100% precision selector 输给 full context | 必须报告 false deletion、raw fallback 与 `DEFER` |

### 6. 今日 Claude 分支的证据状态

| Branch | Code-level fact | Evidence status |
|---|---|---|
| `prompted` | sidecar 仍含完整 raw top-10 | 105/105 完成；Direct=18、Prompted=18，3W/3L/99T |
| `filtered` | engine evidence IDs 映射回 source-memory round；无裁决/失败/空集时 full fallback | 2026-08-01 02:08 正式运行中；54/105 infrastructure rows，0 duplicate/parse/explicit-failure；不据中途正确率调参 |
| `repaired` | 一次 BM25 repair；query=extracted entity+slot+fixed update terms；最多加5条 | 仅 3-case mock plumbing；没有正式语义效果证据 |

### 7. 主张边界与筛选记录

#### 共同可支持

- 真正改变 Reader-visible evidence 的 post-retrieval mediation 有现实方法与部分正向证据。
- validity 与 sufficiency 必须分开；固定池扩展与外部补检索也必须分开。
- selector 的收益取决于 evidence recall、Reader 能力与任务噪声结构。
- answer accuracy、evidence coverage/provenance、false deletion 与完整成本必须联合验收。

#### 共同不支持

- 不支持当前 QVF 已有正向收益。
- 不支持任何 gold-answer-derived labels、逐数据集阈值或关键词规则进入目标 Benchmark evaluation。
- 不支持把 relevance/evidentiality/sufficiency 当成真实性、时间有效性或 relation oracle。
- 不支持把 Reader input token 降幅直接写成端到端成本降幅。

#### 完整筛选但未纳入主五篇

| Paper | 不纳入主五篇的理由 |
|---|---|
| *Sufficient Context: A New Lens on RAG Systems*（ICLR 2025） | 很适合定义独立 sufficiency 维度，但其 controller 只做 ANSWER/ABSTAIN；ECoRAG 已覆盖更直接的“sufficiency→扩大 evidence”动作。保留为训练无 GT sufficiency detector 的补充依据。 |
| *Astute RAG*（ACL 2025） | 强调 source-aware consistency/conflict grouping，相关性高；但生成无来源的 internal knowledge，并把 controller 与 final answer 耦合。7/31 的 DRAGged 已覆盖 conflict taxonomy，故本日优先补齐 selection 因果边界。 |
| *Efficiency vs. Verifiability in Evidence-Aware RAG*（CustomNLP4U 2026） | 重要反证：answer 指标小降时 citation grounding 可大幅下降；但单一 Reader/数据集/压缩器，且没有清楚报告真实输入 token/latency。作为安全指标补充，不作正向方法证据。 |
| *SELF-multi-RAG*（Findings EMNLP 2024） | retrieve/rewrite tokens 与 conversational QA 相关，但与 CRAG 的 corrective route 重叠，且不直接研究 temporal memory validity。 |
