# Five-Paper QVF Evidence Matrix — 2026-07-31（周五）

## 0. 来源与核对范围

| 来源 | 本地文件 | SHA-256 |
|---|---|---|
| MemChain | `docs/papers/MemChain_2607.24097.pdf` | `416CFB28578318EF48EBEB68654F94D06DD8512443E2690EEF0A49AF0F2E815E` |
| DRAGged into CONFLICTS | `docs/papers/DRAGged_into_Conflicts_2506.08500.pdf` | `30E430F538B28A56626C249CCF644A841B9C010D44CEA01C5FF945711661AF68` |
| Beyond Similarity / MemGate | `docs/papers/Beyond_Similarity_MemGate_2606.06054.pdf` | `F237B0D908375FC3E95B6EF2A0247F5A1A2585C86852AD69BB340881E75898FE` |
| Presentation, Not Mechanism | `docs/papers/Presentation_Not_Mechanism_2607.16019.pdf` | `AC27AB30F056082D7336D189CCC5D0CAE919247F61C0E914754C7B904B446850` |
| MemTrace | `docs/papers/MemTrace_2606.17328.pdf` | `A1964184BAFD75B60599E8745CB429FF6301DDFF267C441B18324D9428CBFBD4` |

本地实现与研究边界另核对了 `docs/AGENT_BRIEFING.md`、`qvf/engine_bridge.py`、`docs/research_proposal.md`、`docs/related_work.md`、`docs/paper_outline.md`、`scripts/run_decisive_stale.py`、`eval/stale_dataset.py`、`results/` 下相关 JSONL，以及 `external/qvf_withcontroller/` 中的 legacy raw-input、validity engine、结果摘要和示例。

## 1. MemChain

**准确标题**：*MemChain: Learning Interpretable Memory Traces for Memory-Augmented LLM Agents*

| 证据项 | 核对结果 | 位置 |
|---|---|---|
| 研究问题 | 固定 memory store、Retriever 与 Answer Model 时，能否训练一个 post-retrieval policy，把封闭候选集转成问题充分、可追踪的主动证据，而不是把检索结果原样交给生成器。 | Sections 1、3–4 |
| 输入 | query `q` 与封闭候选集 `Cq`；系统不能从候选边界外补回漏检证据。 | Section 3；Section 7 |
| 输出 | 一次自回归产生 evidence plan `z`、grounded evidence trace `T`、memory actions `A` 和 active evidence `E`。 | Section 4；Eqs. (6)–(11) |
| Answer Model 可见内容 | 冻结 Answer Model 只接收 active evidence `E`，不再看到完整 raw candidates；`E` 是临时 answer-time 表示，不回写 memory store。 | Sections 3–4 |
| Evidence plan | 描述 intent、需要的 memory type、temporal scope（current/recent/historical/any）、evidence need 与 soft count。 | Section 4.2；Eq. (6) |
| Grounded trace | 以 candidate ID 绑定 role、statement 与 next relation；作用不只是自然语言解释，而是让后续动作可回溯到候选证据。 | Section 4.3；Eqs. (7)–(8) |
| Memory actions | `KEEP` 保留、`DROP` 删除、`MERGE` 合并、`REFINE` 细化、`ADD` 添加候选集合所支持的派生内容；`ADD` 不是开放式补知识。 | Section 4.4；Eqs. (9)–(11) |
| SFT | 由 teacher 产生结构化 packet，以 token-level cross-entropy 学习；5,882 个训练样本、310 个验证样本，候选最多 24 条。Qwen3-4B，LoRA rank 32、alpha 64、dropout 0.05、2 epochs、学习率 `8e-5`。 | Section 4.5；Eq. (12)；Appendix A.3、A.5 |
| TMPO | 同一问题成组采样 rollouts，使用组内相对标准化 advantage；以 mean-token log-ratio 构造 sequence-level policy ratio，再进行 clipping，并加入 KL regularisation 与 entropy。group size 3、KL `β=.006`、entropy `λ=.001`、学习率 `2e-7`。 | Section 4.5；Eq. (14)；Appendix B.3；Table 6 |
| Reward | 结构门 `m=.35×strict JSON + .25×schema + .20×candidate IDs + .20×trace validity`；总 reward 为 `m × (.65 answer correctness + .15 answer stability + .15 trace/cited-evidence precision-recall + .05 evidence support)`。未见独立 length reward。 | Appendix B；Eqs. (15)–(16) |
| 主要结果 | GPT-4.1-mini Reader 下，LoCoMo：SFT 67.42，SFT+TMPO 69.80；LongMemEval-S：GPT-4.1-mini 68.40、GPT-4.1 78.20。LoCoMo 的 Qwen3-4B policy 配置还报告 143.3 answer-facing tokens 与 0.83 s memory-side latency；后者包含 retrieval 与 post-retrieval composition、排除 answer generation，前者不是端到端总 token。 | Section 5.2；Tables 1–2、4 |
| 关键消融 | LoCoMo Full 69.80；去 plan 63.59（−6.21）；去 trace 55.84（−13.96）；prompt-only 49.35（−20.45）。多数报告分数已由 SFT 达到，TMPO 在该设置再增加 2.38 pp；因此不能把全部效果归给 RL。 | Table 5；SFT/TMPO 对照见 Table 1 |
| 明确限制 | 封闭候选边界无法恢复 retrieval omission；增加 memory-side inference；token 统计口径只覆盖 answer-facing `E`。 | Section 7 |
| 最强可支持结论 | 在论文自己的训练、候选集与 Reader 协议中，学习出的 plan–trace–action mediation 比其 prompt-only 变体更有效；grounded trace 是该消融中最关键的结构组件。 | Table 5 |
| 诱人但不受支持的结论 | “所有 post-retrieval controller 都应高权限改写证据”“RL 是主要收益来源”“MemChain 已解决个人记忆的时间真实性”均超出证据。 | 由系统边界与消融反证 |

**复现信息缺口**：PDF 给出了训练规模、目标与超参数，但 teacher 身份、teacher prompt 和训练样本构造细节不足以仅凭论文逐项复现；代码链接存在，但本任务没有把代码仓库当作论文正文证据。

## 2. DRAGged into CONFLICTS

**准确标题**：*DRAGged into CONFLICTS: Detecting and Addressing Conflicting Sources in Search-Augmented LLMs*

| 证据项 | 核对结果 | 位置 |
|---|---|---|
| 研究问题 | Search-Augmented LLM 能否先判断完整已选 source set 的关系类型，再按类型生成合适回答。 | Sections 1–2 |
| 输入与边界 | query 加完整的“已选检索结果集合”，平均 9.2 条；但每条不是完整网页，而是 URL、标题、snippet、可用发布日期和 TAS-B 选出的一个 512-token segment。论文不改 Retriever。 | Sections 3、5.1 |
| 输出 | 分类任务输出 conflict type；生成任务输出带 inline citations、符合 type-specific behavior 的回答。 | Section 4；Eqs. (1)–(2) |
| Taxonomy 与行为 | No conflict→直接回答；Complementary→合并共存信息而不制造争议；Conflicting opinions/research→中性呈现分歧；Freshness→优先最新值、可说明旧值；Misinformation→排除不准来源并依据可靠证据回答。 | Section 2；Table 1 |
| 方法 | 无微调。Pipeline 先分类后生成；Taxonomy-Aware 在单次 prompt 中分类、解释、生成；Oracle 直接提供 gold type。 | Section 5.1；Appendix B；Figures 2–3 |
| 数据 | 458 例，另有 18 个 no-relevant-source 被过滤；No conflict 161、Complementary 115、Opinions 115、Outdated 62、Misinformation 5。两位专家标注并协商，第三位复核。 | Section 3；Table 2；Appendix A Table 7 |
| 评测 | 分别评 expected-behavior adherence、answer recall（仅 228 个适用样本）和 grounding；LLM behavior judge 在 100 例人工核对中准确率 0.89。 | Section 4 |
| 主要结果 | 最高分类准确率 65.3%。Pipeline 平均约提升 9 个 behavior points，Taxonomy-Aware 约 5.5，Oracle 约 24。Table 6 的 Gemini 2.5 Flash Thinking+Pipeline 配置中，opinions 为 36.2→73.3，而 no-conflict 为 78.4→74.7；“收益集中于 opinions”只对这项分类别对照成立，不能概括全部模型。 | Tables 4–6 |
| 明确限制 | 定向筛题造成非自然类别分布；misinformation 仅 5 例；只含 safe queries；Google、网页状态和日期依赖采集时点；每源只看 512-token segment；多项指标依赖 LLM judge。 | Sections 3–6 |
| 最强可支持结论 | 在该 curated web-RAG 设置中，显式 conflict type 能改善与类别相匹配的回答行为，尤其是意见冲突。 | Tables 5–6 |
| 诱人但不受支持的结论 | 不能据此说模型已可靠检测任意真实 RAG/个人长期记忆冲突，也不能把网页发布日期直接当个人状态的 effective time。 | 分类准确率、数据边界 |

**文本不一致**：Table 3 的 *Prison Break* 示例一处写成 “April 7, 2020”，而同表回答及 Table 1 支持 “April 4, 2017”；PDF 与官方 HTML 都保留此问题，故不使用该错误日期作为论据。

## 3. Beyond Similarity / MemGate

**准确标题**：*Beyond Similarity: Trustworthy Memory Search for Personal AI Agents*

| 证据项 | 核对结果 | 位置 |
|---|---|---|
| 研究问题 | 相似 memory 不一定适合影响当前任务；如何在不改 LLM 和 memory database 的条件下，把 similarity retrieval 变成 task-conditioned admission。 | Sections 1–2；Eq. (3) |
| 插入位置 | vector Retriever 先给小候选集，MemGate 在 prompt construction/LLM 之前逐 query–memory pair 打分并重排。最终 Reader 仍看到入选 memory 的原始文本。 | Figure 1；Sections 4.1–4.2 |
| 输入输出 | 输入 query embedding `q` 和单条 memory embedding `v_m`；输出 384 维连续 mask 及 masked-memory cosine score，随后按分数取 top-k。 | Eqs. (4)–(7) |
| 是否建模集合关系 | Gate 本身逐 pair 独立；候选间只在 softmax 分母和 ranking 中相对竞争。没有 candidate attention，也没有 entity-slot、replacement、coexistence 或 target pairing。 | Eqs. (4)、(7) |
| 模型与训练 | all-MiniLM-L6-v2（384 维）；MLP `1152→2048→2048→1024→384`，约 9M 参数/35.1 MB。1,640 个 GPT-4o-mini 合成 preference pairs；DPO 对 ungated cosine reference，并以 L1 positive-preservation 约束。`τ=.1, β=.3, λ=.1`，AdamW `1.5e-4`、batch 256、20 epochs。 | Sections 4.1–5.1；Eqs. (4)–(8) |
| 威胁与效用 | PersistBench cross-domain/sycophancy、MemDrift tool drift、PS-Bench jailbreak；效用使用 LoCoMo、MemoryAgentBench、PreFEval、PersonaMem 和 beneficial-memory failure。 | Tables 1、4、6；Appendix C.1 |
| 主要结果 | GPT-4o-mini+OpenClaw：cross-domain FR 27.0→3.5，jailbreak ASR 16.8→4.4，LoCoMo 38.9→40.8，PreFEval 86.4→88.2，latency 1.47→1.59 s；sycophancy 33.5→31.5 改善有限。 | Table 7 |
| 失败/权衡 | 较小 `λ` 更激进，可能 false rejection；较大 `λ` 更接近 identity，风险 memory 保留更多。个别效用回退，如 Qwen+Mem0 LoCoMo Single-Hop 48.5→46.6、GPT-4o-mini+OpenClaw Open-Domain 22.8→16.9。 | Section 5.5；Figures 6–7；Table 4 |
| 明确限制/缺口 | 封闭候选集，不能恢复漏检；没有显式 reject-all 阈值；训练 pair 的风险类别分布未给；未报告置信区间/显著性，也无独立 Limitations section。 | Sections 4–5 |
| 最强可支持结论 | 在所测框架、backbone 与风险任务上，轻量 pairwise gating/reranking 能减少若干 memory-activation 风险，同时大体保留 aggregate utility。 | Tables 4、7 |
| 诱人但不受支持的结论 | 不能说 MemGate 判定了 memory 的真实性、当前有效性或多 memory temporal conflict，也不能说它是校准过的硬安全过滤器。 | 方法边界 |

**表述差异**：Figure 5 说明文字提到 query gate `g_q` 与 memory gate `g_m`，但 Section 4.1 和 Eqs. (5)–(6) 明确保持 query 不变、只 mask memory；PDF/HTML 均未解释该差异。

## 4. Presentation, Not Mechanism

**准确标题**：*Presentation, Not Mechanism: A Render Confound in Deprecation-Aware Memory Evaluation*

| 证据项 | 核对结果 | 位置 |
|---|---|---|
| 研究问题 | deprecation-aware memory 相对 flat retrieval 的表面提升，有多少来自关系/失效机制，有多少只来自排序、结构、字段和回答提示的呈现。 | Sections 1–2 |
| 输入输出 | 时间排序 evidence stream；冻结 extractor 得到 `(entity, attribute, value, polarity, time, source role)`，系统输出 current value、valid-since、support、deprecated atoms 和 conflict/abstain。 | Sections 2–3 |
| 三类系统 | GraphRAG+abstain 为 `d`-blind；Graphiti 风格 coarse-`d` 是 live/dead invalidation；RevisionLedger fine-`d` 还保存关系类型、支持/失效集合和 unresolved。 | Section 3 |
| 训练 | headline 系统没有端到端训练，使用 frozen extractor 与 rule scorer；约 110M BERT learned pair scorer 只用于 `refines` 恢复诊断。 | Appendix F；Table 10 |
| 数据 | ESR-Bench 2,907 QA：GitHub 1,698、MultiRepo 252、Wikipedia 848、DyKnow 109；包含 reversion、cross-source、refines 与 monotonic。 | Section 3；Table 1 |
| Render-matched control | 保持 RevisionLedger 的 layout、IDs 与字段，但把所有 co-key relation 设为 `same-state`，从而关闭 supersedes/contradicts/unresolved。 | Section 4.1；Appendix F |
| 主要结果 | primary reverted-revert slice 的 headline RevisionLedger−GraphRAG+abstain 为 +0.182，95% CI `[.134,.230]`。同一 slice 的 matched decomposition 总差 +.184：render +.159 `[.114,.207]`；exact-layout-matched fine mechanism residual +.025 `[-.005,.057]`。论文另报告 coarse-`d` 对 render-only control 的差 +.087 `[.046,.130]`，但没有同样明确交代字段、顺序和 token budget 全部精确匹配。 | Section 4.1；Table 2 |
| 失败/细节 | clean reversion 上 fine ledger 比 coarse Graphiti 低 .084。主 extractor 的 gold-relevant-event recall 为 GitHub .86、MultiRepo .84。 | Appendix B Table 5；Appendix F |
| Query sufficiency | Proposition 2b 只在“正确 partition 与 values 已知”的条件下说明 snapshot answer 不再需要 fine relation type；它不证明 relation scoring 无用，因为正确 partition 本身仍需判断 supersession。 | Appendix A，Propositions 2b–2c |
| 明确限制 | 每 key 假设单一 current value；没有人工 atom gold；noise sweeps 不穷尽真实误差；Proposition 5 是 post-hoc；外部 TempLAMA 接近 ceiling，未复现同一 render confound。 | Section 2；Appendices A、C、D、F |
| 最强可支持结论 | 在 ESR-Bench reverted-revert 设置中，fine RevisionLedger 的大部分表面收益来自 render；exact-layout-matched fine residual 与零不可区分。论文另报告正向 coarse-`d` contrast，但其匹配细节不如 fine control 完整，不能按同等强度作因果解释。 | Table 2 |
| 诱人但不受支持的结论 | 不能推广为“所有结构化 memory 收益都只是呈现”“validity mechanism 永远无用”或“fine relation 在任何 query 上都无用”。 | coarse-`d`、provenance 与 relation-query 结果 |

## 5. MemTrace

**准确标题**：*MemTrace: Probing What Final Accuracy Misses in Long-Term Memory*

| 证据项 | 核对结果 | 位置 |
|---|---|---|
| 研究问题 | pooled per-question accuracy 掩盖同一知识点在年龄、问法和证据条件上的不同失败；以 knowledge point 为单位做诊断。 | Sections 1、3 |
| 输入输出与边界 | 每个配置只能利用 checkpoint 前的 multi-session prefix：long-context 系统直接读 prefix，其他系统用 prefix 构建/更新 memory，再把 retrieved/stored evidence 交给共同的 gpt-4o-mini generator。输出答案后评分为 `(g, v, r)`：Gist、Verbatim completeness、response type。它是 benchmark，不是 controller。 | Sections 3.1–3.3；Section 4.1；Appendix B Table 8 |
| 规模 | 20 users、835 KP、5,677 base probes、15,422 question rows、200,453 answers、每用户 8 checkpoints；KP 包含 348 static、213 dynamic、74 preference、100 conflict distractor、100 boundary distractor。 | Section 3.1；Table 2；Appendix A Table 6 |
| 三个诊断轴 | age=`t_eval−t_source` sessions，Fresh=W1/W2、Saturated=W7/W8；substantive KP 有 Current/Historical/Trajectory，conflict/boundary distractors 只有 Current/Historical；证据为 present、missing/boundary、false-premise/conflict。 | Sections 3.2、3.4 |
| Reach/use | 300-probe replay 用 Text-emb-3-small；`R=1` 表示 proxy retriever 可达 gold source session，不等于 gold span必然进入 Reader。透明 Text-emb-3-small RAG production row 中：21/300 reach miss、220/300 reached-unsolved、59/300 solved；再把同一 reach proxy 扩展到 13 configurations，得到 `P(U=0|R=1)=69.2%–88.2%`。top-k/rank cutoff 未明确报告。 | Section 4.4；Figure 5；Table 5；Appendix C.3 Table 12 |
| Oracle | 对 `R=1,U=0` 子集补 gold evidence 后，Oracle Gist 80.4%–83.9%，pooled lift 81.8 pp；这是 open-book diagnostic，不是可部署 controller。 | Section 4.4；Table 5 |
| 主要结果/失败 | HippoRAG-v2 saturated Current 45.4、Historical 50.9、Trajectory 13.4；Mem-T trajectory 19.8 为该列最高。Qwen3.5-35B trajectory 49.0→6.7，GPT-5-nano 38.4→6.5。 | Section 4.2；Table 3 |
| 证据条件细节 | Mem0 boundary abstention 99.3%，但 conflict Gist 14.6%；缺证据应 abstain 与 false-premise 时应纠正不能合并成同一安全行为。Reader 更换也可把 Mem0 conflict Gist 从 14.6 提至 59.8。 | Section 4.3；Table 4；Appendix E Table 18 |
| 明确限制 | 单一 HaluMem-Medium source distribution、20 users；比较的是 end-to-end configurations；reach/use 依赖单一 proxy retriever 与 open-book oracle；结果和 judge 均受 backbone 影响。 | Limitations；Appendices B–D |
| 最强可支持结论 | 在该 benchmark 和 proxy replay 中，KP-level 分解揭示 pooled accuracy 隐藏的失败；gold source session 可达之后的 selection、exposure、temporal organisation、adjudication 与 Reader use 综合链，是该 proxy 下的主要剩余缺口。 | Sections 4.2–4.4 |
| 诱人但不受支持的结论 | 不能推广为所有长期记忆的瓶颈永远是 use、retrieval 不重要，或加入任意 QVF 必然有效。 | Limitations |

**对 QVF 标签边界**：可直接迁移 age curve、KP clustering、Current/Historical/Trajectory 与 present/missing/conflict；`reach→extract→adjudicate→use` 是在 MemTrace 诊断思想上进一步提出的 QVF synthesis，并非论文原生标签。MemTrace 不提供 per-candidate validity、exact source span、entity-slot atom、relation/target、role/action 或 route label；直接把 benchmark condition 或 oracle intervention 当训练标签会造成协议泄漏。

## 6. 截至 2026-07-31 的 QVF 本地实现核对

| 待核问题 | 代码/结果证据 | 可防守结论 |
|---|---|---|
| Reader 是否只看 sidecar | `SidecarReader.answer()` 形参只有 question+sidecar（`qvf/engine_bridge.py:447–464`）；但 raw controller 将 `raw_retrieved_memory_context` 加回 sidecar（`external/.../raw_input.py:366–381`），bridge 保留 top-10 全文本（`engine_bridge.py:193–213`）。 | prompted 路径是“接口上只消费 mediated packet、packet 内仍含完整 raw top-10 文本”的 evidence-preserving advisory mediation；不是 sidecar-only evidence hiding，也不是硬过滤。 |
| Global oracle 是否绕过 retrieval | prompted 先 BM25 top-10（`scripts/run_decisive_stale.py:57–71`）；oracle 直接从 `M_old/M_new/explanation` 构造两条 same-slot replacement pair（`:112–134`; `engine_bridge.py:322–376`）。 | Oracle−Prompted deployment 混合 retrieval recall、distractor removal、atomization、focus、pairing、relation、explanation supervision、render，以及 prompted arm 的 fallback policy；不是纯 extraction headroom。 |
| LLM 与 symbolic engine 的职责 | prompt 要求 query focus、relevance、source span、entity/slot/value、cardinality、relation 与 targets（`engine_bridge.py:47–115,270–315`）；engine 校验 provenance/schema/target/scope，再确定性生成 roles/actions。 | LLM 做实质 semantic parsing 与 relation adjudication；engine 做 structural/provenance/graph consistency validation 与 deterministic execution。结构通过不等于语义正确。 |
| Grounding 与 unresolved | `source_span` 必须是原文连续、逐字一致的 substring，且无 start offset 时需唯一；prompt 要求不确定时优先 `unresolved`（`engine_bridge.py:90–115`; `external/.../raw_input.py:637–641,1020–1037`）。 | 这是 precision-first provenance contract。substring 成立不证明该 span 蕴含 value、cardinality、relation 或 effective time；`unresolved` 也不保证关键 evidence coverage。 |
| same-slot 与 Type-II | prompt 与 target validation 均要求 same entity+slot（`engine_bridge.py:68–81`; `external/.../raw_input.py:936–1010`）。 | 当前 contract 主要覆盖同 slot 竞争；不能显式表示跨 slot dependency/STALE Type-II。global oracle 把 Type-II 强投影为 replacement 不证明 prompted schema 已会传播。 |
| `session_date` 与时间 | `session_date` 既成为 `observed_at`，replacement/correction 时又写为 `effective_from`（`engine_bridge.py:146–172`）。 | 当前实现混淆 observation time 与 state effectivity；过去回忆、延迟报告、未来计划都会破坏该等价。 |
| explicit new state | prompt 要求显式 moved/changed/now 等，禁止仅凭较新时间戳推 replacement（`engine_bridge.py:107–113`）。 | 这是 precision-first 合同，可抑制 recency heuristic，但会漏掉需要逻辑或跨 slot 传播的隐式更新。 |
| `allow_partial=True` | 每 record 独立 validation；至少一条 accepted 且无其他 blocker 时可继续（`external/.../raw_input.py:174–246`）。 | 保证 malformed record 不必摧毁整个请求；不保证关键 pair 完整、accepted 语义正确、被拒文本不影响 Reader、engine 执行或答案正确。 |
| 元数据真实性 | `_engine_memory_row` 固定 `source_type="conversation_round"` 和 `source_confidence=.9`，只从输入取部分元数据（`engine_bridge.py:136–151`）。 | 当前 bridge 不能声称所有 source/confidence 均来自真实已有元数据。 |

## 7. 现有结果的证据边界

### 7.1 Plan A（LongMemEval-S cleaned 子样本）

当前 `results/planA_s_15pt.jsonl` 有 254 行、85 个 unique questions。按现有行只读聚合：baseline `62/85`（非弃权 `47/70`）；QVF `64/85`（`49/70`）；prompt-only `63/84`（`48/69`）。QVF 对 prompt-only 的 69 个配对非弃权题为 `1 win / 1 loss / 67 ties`；配置好的 structured two-call pipeline 相对配置好的 free-text two-call pipeline 未观察到净答案优势。两臂使用不同 analyst/extractor、system prompt、intermediate semantics 和长度，故这不是 schema-only 因果对照。中位延迟约 baseline 4.63 s、prompt-only 27.58 s、QVF 49.12 s；按脚本 Opus 价格估算分别约 `$0.051/$0.146/$0.238` 每题。

`AGENT_BRIEFING.md` 中的 82-question、`44/67→45/66→46/67` 是更早运行快照，与当前 JSONL 聚合不一致。两者都没有显示该 structured 配置相对 free-text 配置的净优势，但不能外推成“schema 无独立作用”或“强 Reader 不需要任何中间表示”。

### 7.2 Decisive STALE route screen

`results/decisive_stale_qwen3-4b.jsonl` 共 315 行，即 105 questions×3 conditions：Direct `18/105`、Prompted deployment `18/105`、Global Oracle+Engine `100/105`。Prompted deployment 实际由 98 个 Engine+Sidecar 和 7 个 Direct fallback 构成，对 Direct 为 `3 wins / 3 losses / 99 ties`；不能把 105 题统称纯 Prompted+Engine。由于 loader 取前 35 items，而数据前 200 items 均为 T1，这只是文件名/运行记录标称的 T1-only weak-reader screen，不覆盖 Type-II；JSONL 本身也未逐行自证模型 ID。

强 oracle 结果只说明 benchmark `M_old/M_new/explanation`、two-memory transport、explanation-derived semantics、engine/sidecar 与 Reader 的联合上限很高；不能把 +82 单独归因给 extraction、validity representation 或 deterministic engine。

### 7.3 历史 structured adapter

STALE 的 Direct `177/1200` 与 full `1088/1200` 非同期、不同精确代码树，且 structured adapter 已注入 exact `M_old/M_new`、时序、同 slot pairing 和 premise binding，故只是 oracle pairing+sidecar/render+Reader 的联合 ceiling。历史保护性聚合摘要在固定 adapter 后报告 Full `1088/1200`、annotation-only/no-stale-blocking `1054/1200`，两者 associated difference 为 `34/1200=2.83 pp`；由于缺少当前代码树下的 raw paired artifact，不把它写成精确因果效应。因此不能写“全部约 76 pp 都由 adapter 带来”，也不能把旧分数归给当前 bridge。

其他历史边界：MemConflict100 `58→67` 属于旧 structured pipeline；LongMemEval500 `195→195` 仅支持 non-degradation；LoCoMo79 `40→43` 是 pilot。MemConflict20 `9→8`、STALE60 `16→21`/selective `22` 来自另一仓库 `D:\ZZL_MPHIL\QVF_github` 的 raw-memory v0.9.2 **legacy endpoint**，不是当前 `engine_bridge.py` 的结果；来源为 `reports/factorized_role_controller_v092_dataset20_20260717/final_report_zh.md`（SHA-256 `691D711A3247D4EAF02D6995DC68FFA45EF46A1D40725C1768E198F241449199`）及 `progress.md:12315`（文件 SHA-256 `36098F30F425C60B5802A4B1F3506C64192517FCCF2F48D042BF6AE472FFF3A2`）。旧 answer bridge 在若干 case 暴露 blocked/raw fallback 文本，故 strict enforcement、same-span `D−C` 与 controller-independent contribution 均不可用；STALE 区间又跨零，不能证明普遍提升。

## 8. 尚未闭合的证据缺口

1. 没有 retrieval-fixed oracle：必须固定同一 top-k、原文、Reader、render，只替换 extraction/relations；gold 不在 top-k 时应记 retrieval failure，不能注入。
2. 没有使用同一 extraction output 的 Extraction-Only 对照；现有 prompt-only 是另一套 free-text analyst，无法分离 engine contribution。
3. 没有严格 matched transport/render control；截至 7 月 31 日的 Direct 与 `prompted+engine` 都保留 raw top-10，但改变了原文 placement/transport、字段、顺序、长度和提示。
4. 当前 decisive screen 全是 T1；Type-II/cross-slot 没有证据。
5. `observed_at` 与 `effective_from` 未拆分，也没有人工语义标签验证 exact span 是否真正蕴含 time/relation。
6. JSONL 未逐行固定 reader/extractor/judge model ID、prompt/hash 与完整参数，正式实验的复现链仍不完整。
7. 五篇论文均未直接验证“当前 QVF contract + current code + current Reader”；文献只能约束问题与实验设计，不能替代本项目的因果对照。
