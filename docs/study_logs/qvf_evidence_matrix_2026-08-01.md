# QVF Five-Paper Evidence Matrix — 2026-08-01

## 0. 最终五篇与本地证据

| Paper | Status / venue | Local PDF | SHA-256 |
|---|---|---|---|
| [*Learning to Filter Context for Retrieval-Augmented Generation*](https://arxiv.org/abs/2311.08377) | arXiv:2311.08377 v1 preprint | `docs/papers/2026-08-01/FILCO_2311.08377.pdf` | `88C58A9D6F0A2F992097634790CAB5D3454943DE5DF2C07BB61FA6DF2A769E52` |
| [*RECOMP: Improving Retrieval-Augmented LMs with Context Compression and Selective Augmentation*](https://proceedings.iclr.cc/paper_files/paper/2024/hash/bda88ed2892f5e61c9a9bf215c566913-Abstract-Conference.html) | ICLR 2024；本地 PDF 为 arXiv v1，标题少 “Context” | `docs/papers/2026-08-01/RECOMP_2310.04408.pdf` | `9D8AA7881E786D6B3593FE6C60BC2E52944AEE82AB6CA577097618BAF8D21066` |
| [*ECoRAG: Evidentiality-guided Compression for Long Context RAG*](https://aclanthology.org/2025.findings-acl.1365/) | Findings of ACL 2025 | `docs/papers/2026-08-01/ECoRAG_2025.findings-acl.1365.pdf` | `BD8445E34E39429DE2F8508AD6D261049FB77AF288FAB8025EF72D4F35D5A7DE` |
| [*Corrective Retrieval Augmented Generation*](https://arxiv.org/abs/2401.15884) | arXiv:2401.15884 v3 preprint | `docs/papers/2026-08-01/CRAG_2401.15884.pdf` | `975AA1FD3C1B603126E93FF99D6504858B61301BF1D34C9DF88EBE53A0B026CB` |
| [*How Does Knowledge Selection Help Retrieval Augmented Generation?*](https://aclanthology.org/2025.findings-emnlp.218/) | Findings of EMNLP 2025 | `docs/papers/2026-08-01/Knowledge_Selection_RAG_2025.findings-emnlp.218.pdf` | `3024CFB478F8C334441BEB3DB351E374551B31E8304A4D98B2C5E5F8073612D8` |

## 1. FILCO

| Evidence item | Full-text finding | QVF boundary |
|---|---|---|
| Authors | Zhiruo Wang, Jun Araki, Zhengbao Jiang, Md Rizwan Parvez, Graham Neubig | 预印本，不写成正式 ACL 接收论文 |
| Stage | DPR top-1/top-5 后，生成式 `M_ctx` 用 filtered text 替代 full passage；另训练 `M_gen` | 与 `filtered` 权限相近，但不是固定黑盒 Reader 的纯插件实验 |
| Supervision | STRINC/LEXICAL/CXMI 均使用 canonical output；任务选择不同策略 | 不能从目标 Benchmark 答案/类别构造 QVF labels |
| Main results | Top-1 六任务平均：FLAN-T5 +2.8、LLaMA2 +3.0 points。Top-5 FLAN-T5：NQ 47.6→61.8、TQA 67.3→71.1、HotpotQA 61.5→65.0、FEVER 88.0→91.4 | context surgery 有正向先例；无 CI/显著性，且 filter+Generator 联合训练 |
| Cost | Generator 输入减少 44%–64%；“≥4.7×”只指 generation model | 未计 3B/7B filter，总 latency/FLOPs 未报告 |
| Internal inconsistency | §4.2、Table 4、Table 5 的 FEVER strategy/run 存在未解释差异 | 各表分别引用，不拼成同一 run |
| Transfer | ID-grounded extractive view、raw archive、matched Reader control | 不支持 temporal validity、replacement、coexistence 或 provenance guarantee |

## 2. RECOMP

| Evidence item | Full-text finding | QVF boundary |
|---|---|---|
| Authors | Fangyuan Xu, Weijia Shi, Eunsol Choi | ICLR 2024；本地 arXiv v1 标题略不同 |
| Stage/actions | 固定 retriever；extractive 选 1 句（Hotpot 2），abstractive 生成摘要，可输出 empty string | 支持 `SELECT/EMPTY`；abstractive 无 candidate-ID 约束 |
| Supervision | 用 gold target 与目标 Reader utility 选正例/摘要；各数据集单独训练 | 不满足目标 Benchmark 独立训练 |
| Main results | Full top-5→extractive：NQ 660 tok/39.39 EM→37/36.57；TQA 677/62.37→38/58.99；Hotpot 684/32.80→75/30.40 | 主要是 4.7%–11% context 与 2.40–3.38 EM 损失的 trade-off，不是普遍提分 |
| Wrong-copy signal | NQ gold 不在 evidence 时，从 evidence 复制答案：full 81%，extractive 33%，abstractive 39% | 支持“过滤可降低错误服从”，但只是字符串启发式 |
| Faithfulness | 每数据集 30 例人评；abstractive fully faithful：NQ 80%、TQA 83%、Hotpot 67% | 自由摘要不能作权威 memory；优先 extractive provenance |
| Cost | 只报 Reader context token | 未计 110M/775M compressor、总 latency/FLOPs |

## 3. ECoRAG

| Evidence item | Full-text finding | QVF boundary |
|---|---|---|
| Authors/venue | Jeong, Kim, Lee, Hwang；Findings ACL 2025，pp.26607–26628 | 正式同行评审论文 |
| Stage/actions | retriever 预取 top-100；句级 evidentiality 排序；sufficiency 不足时每次加 4 句，最多 20 | 是 `EXPAND_WITHIN_POOL`，不是外部 re-retrieval |
| Supervision | Flan-UL2+gold answer 反事实标 strong/weak/distractor；evaluator 学 `<EVI>/<NOT>` | Reader/答案依赖，不能用于目标 Benchmark label |
| Main results | GPT-4o-mini：NQ 13,905 tok/36.09/50.18→632/36.48/49.81；TQA 14,167/56.21/64.22→441/65.34/75.37；WQ 13,731/21.11/38.72→560/30.17/46.13 | TQA/WQ 正向，NQ F1 略负；相对最强压缩 baseline EM 只 +0.77/+1.38/+0.40 |
| Evaluator ablation | 去 evaluator，NQ/TQA EM 降 0.77/1.80 | sufficiency gate 有小而直接的独立证据 |
| Cross-reader | Llama3 TQA/WQ closed-book 60.89/21.79，ECoRAG 59.25/21.60 | 不能宣称普遍优于不使用 retrieval |
| Transfer | strong/weak/distractor + sufficiency + 动态 evidence amount | sufficiency≠truth/temporal validity；必须保 record/source ID |

## 4. CRAG

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

## 5. How Does Knowledge Selection Help RAG?

| Evidence item | Full-text finding | QVF boundary |
|---|---|---|
| Authors/venue | Xiangci Li, Jessica Ouyang；Findings EMNLP 2025，pp.4104–4121 | 实证分析，不是可部署 selector |
| Design | 固定 gold/distractor pool，用 `p_gold/p_noise` 随机抽样，操纵 evidence precision/recall | 对固定 Reader/数据集有较强机制证据；依赖部署不可得的 gold labels |
| Data/Readers | WoW 452 utterances；HotpotQA 500 cases；GPT-4o-mini、Llama3.1 8B、Mistral7B | 小子集、三种轻量 Reader；不含 temporal/conflict/provenance |
| Hotpot results | no/full/gold F1：GPT-4o-mini .437/.780/.828；Llama .298/.545/.671；Mistral .260/.151/.627 | 强 Reader full–gold gap 小；弱 Reader 会被 distractor 严重伤害 |
| WoW results | GPT-4o-mini .200/.251/.276；Llama .216/.248/.278；Mistral .203/.233/.268 | “distractor”可能支持合理回答，过滤收益非单调 |
| Mechanism | 强 Reader 主要受 recall 影响；弱 Reader+清晰噪声更依赖 knowledge F1；低 recall 时继续删证据可伤害 | QVF 必须优先 coverage/recall，并预注册 Reader-strength 分层 |
| Label-noise intervention | gold false negative 会使表面 100% precision selector 输给 full context | 必须报告 false deletion、raw fallback 与 `DEFER` |

## 6. 今日 Claude 分支的证据状态

| Branch | Code-level fact | Evidence status |
|---|---|---|
| `prompted` | sidecar 仍含完整 raw top-10 | 105/105 完成；Direct=18、Prompted=18，3W/3L/99T |
| `filtered` | engine evidence IDs 映射回 source-memory round；无裁决/失败/空集时 full fallback | 2026-08-01 02:08 正式运行中；54/105 infrastructure rows，0 duplicate/parse/explicit-failure；不据中途正确率调参 |
| `repaired` | 一次 BM25 repair；query=extracted entity+slot+fixed update terms；最多加5条 | 仅 3-case mock plumbing；没有正式语义效果证据 |

## 7. 主张边界与筛选记录

### 共同可支持

- 真正改变 Reader-visible evidence 的 post-retrieval mediation 有现实方法与部分正向证据。
- validity 与 sufficiency 必须分开；固定池扩展与外部补检索也必须分开。
- selector 的收益取决于 evidence recall、Reader 能力与任务噪声结构。
- answer accuracy、evidence coverage/provenance、false deletion 与完整成本必须联合验收。

### 共同不支持

- 不支持当前 QVF 已有正向收益。
- 不支持任何 gold-answer-derived labels、逐数据集阈值或关键词规则进入目标 Benchmark evaluation。
- 不支持把 relevance/evidentiality/sufficiency 当成真实性、时间有效性或 relation oracle。
- 不支持把 Reader input token 降幅直接写成端到端成本降幅。

### 完整筛选但未纳入主五篇

| Paper | 不纳入主五篇的理由 |
|---|---|
| *Sufficient Context: A New Lens on RAG Systems*（ICLR 2025） | 很适合定义独立 sufficiency 维度，但其 controller 只做 ANSWER/ABSTAIN；ECoRAG 已覆盖更直接的“sufficiency→扩大 evidence”动作。保留为训练无 GT sufficiency detector 的补充依据。 |
| *Astute RAG*（ACL 2025） | 强调 source-aware consistency/conflict grouping，相关性高；但生成无来源的 internal knowledge，并把 controller 与 final answer 耦合。7/31 的 DRAGged 已覆盖 conflict taxonomy，故本日优先补齐 selection 因果边界。 |
| *Efficiency vs. Verifiability in Evidence-Aware RAG*（CustomNLP4U 2026） | 重要反证：answer 指标小降时 citation grounding 可大幅下降；但单一 Reader/数据集/压缩器，且没有清楚报告真实输入 token/latency。作为安全指标补充，不作正向方法证据。 |
| *SELF-multi-RAG*（Findings EMNLP 2024） | retrieve/rewrite tokens 与 conversational QA 相关，但与 CRAG 的 corrective route 重叠，且不直接研究 temporal memory validity。 |
