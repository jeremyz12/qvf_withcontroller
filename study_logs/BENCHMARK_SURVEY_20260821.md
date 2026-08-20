# WikiState vs. 现有长程记忆基准对比

## 1. 对比表

| 基准 | 上下文规模 | Embedding | 检索配置 | 有无真值状态链 | 金答案来源 | 能否做错误归因 |
|---|---|---|---|---|---|---|
| **LoCoMo** (arXiv:2402.17753) | 论文版 50 段对话,均 19.3 sessions / 304.9 turns / 9,209.2 tok;公开发布仅 10 段子集(子集文字统计 unverified) | DRAGON(dragon-plus query/context encoder);备选 Contriever/DPR/OpenAI 但官方脚本固定 DRAGON | 三种粒度(逐轮 / observations / session summaries);dialog/obs top-k=5,10,25,50,summary top-k=2,5,10;reader gpt-3.5-turbo | 无(链标注字段实测为空,133 项) | 人工标注 QA(标注含答案 turn ID) | 部分:recall@k 可测检索命中,无链条件归因 |
| **LongMemEval** (arXiv:2410.10813) | S 版 ~115k tok/题(~40 sessions,Llama 3 tokenizer);M 版 ~500 sessions / ~1.5M tok;500 题 | Stella V5 1.5B(主基线);repo 另支持 BM25/Contriever/gte-Qwen2-7B | top-k=按 session 提供给 reader,论文无统一固定 top-k(unknown);报 @5/@10 指标点 | 无(链标注字段实测为空,78 项) | 人工精编 500 题(含 knowledge updates、abstention 类) | 部分:五能力分类可定位能力短板,无链条件归因 |
| **Zep/Graphiti** (arXiv:2501.13956,评于 DMR+LongMemEval_s) | DMR:500 个对话 × 5 sessions × ≤12 条消息;LongMemEval_s:~115k tok/对话 | 论文实验 BGE-m3(embedding+rerank);repo 默认 text-embedding-3-small(可配) | cosine + BM25 + 图 BFS 三路;top-20 edges(facts)+ entity nodes;RRF/MMR 重排 | 无(时序知识图为系统内部构建,非基准提供的真值链) | 沿用 DMR / LongMemEval 原基准答案 | 否(沿用宿主基准,基准侧无链归因) |
| **Mem0** (arXiv:2504.19413,评于 LoCoMo) | 10 段对话,均 ~600 条消息 / ~26,000 tok;记忆占用 Mem0 ~7k / Mem0g ~14k tok(记忆条数 unknown) | text-embedding-3-small(论文原文拼作 "text-embedding-small-3";repo 默认同型号,1536 维) | RAG 基线 chunk ∈ {128…8192} tok,k ∈ {1,2};写入阶段 s=10 相似记忆 + mm=10 前文消息;回答阶段检索条数 unknown | 无(沿用 LoCoMo,链字段为空) | 沿用 LoCoMo 标注答案 | 否 |
| **MemoryBank** (arXiv:2305.10250) | 15 虚拟用户 × 10 天 ChatGPT 角色扮演对话;194 个探测问题(repo README 写 100,不一致);记忆库 token 总量 unknown | 英 all-MiniLM-L6-v2 / 中 text2vec-large-chinese(LangChain+FAISS) | top-k=3、CHUNK_SIZE=200(均出自 repo 代码,论文未给) | 无 | 人工设计探测问题,人工+ChatGPT 评分 | 否 |
| **MSC** (arXiv:2107.07567) | 4000 episodes(3 sessions)+1001(4 sessions),验证/测试至 5 sessions;完整对话均 1,614 tok(BlenderBot BPE) | DPR bi-encoder(RAG/FiD/FiD-RAG 基线) | 检索单元按 utterance vs 整 session 调参(整 session 更优);top-N ∈ {3,5,6} 按验证集择优 | 无 | 无 QA 金答案(评困惑度与人评 engagingness) | 否 |
| **A-TMA / LTP** (arXiv:2607.01935) | 10 profiles × 800 probes(400 历史回忆 + 400 当前冲突);每 profile 绑一条 LoCoMo 对话 + 40 旧态线索 + 40 冲突线索;token 数论文未报 | 宿主系统自带(overlay 不指定);写入侧 Sentry 用 nomic-embed-text-v1.5 | top-k=5;可选 controller 看 ≤10 行 × 220 字符、选 ≤3 行;判卷独立 llama3.3:70b | **部分**:人工插入旧态/当前冲突线索对(状态变更对,非完整链;链标注字段实测为空,10 项) | 构造式冲突 probe(判卷用 LLM judge) | 部分:区分历史回忆失败 vs 当前状态冲突(ghost memory)两类失效 |
| **TReMu** (arXiv:2502.01630) | 基于 LoCoMo(自测口径 304.9 turns / 19.3 sessions / 9,209.2 tok);600 道时序多选题(含 112 道不可回答) | N/A——全文无 embedding,检索为 LLM 提示式(MemoChat 三阶段) | 无 top-k / chunk;记忆单元为每 session 一条带推断日期的 timeline 摘要 | 无(时间线为系统侧推断,非基准真值链) | 增强 LoCoMo 构造的多选题(构造方式细节未核) | 部分:三类推理(Anchoring/Precedence/Interval)分项可定位推理类型 |
| **WikiState(我方)** | 单库 33–35 sessions,单会话中位 372 tok,整库中位 ~11.9k tok(cl100k),整库读者提示 14,780 tok/题;top-10 直读 962 tok/题 | OpenAI text-embedding-3-small(冻结检索协议;早期 nomic-embed-text) | top-10 直读;冻结检索协议(QVF_EMBED_BACKEND=openai) | **有**:Wikidata(CC0)真值状态链 | **机械金答案**(由真值链机械导出,非人工/LLM 标注) | **有**:链条件归因 + 受控孪生 + 十项对照(泄漏探针 0.7%、判官交叉 2.7% 噪声带、乱序对照) |

*注:表中 unknown/unverified 均按一手核实结果如实标注;"链标注字段实测全空(133/78/10)"为我方对 LoCoMo/LongMemEval/LTP 公开数据文件的实测。*

## 2. WikiState 创新性概括(仅引表中事实)

1. WikiState 是表中唯一以外部真值状态链(Wikidata CC0)为基准底座的数据集——LoCoMo、LongMemEval、LTP 的公开数据中链标注字段实测全空(133/78/10),其余基准的时间线或知识图均为被评系统侧构建而非基准侧真值。
2. 金答案由真值链机械导出,而其余含 QA 的基准均依赖人工标注(LoCoMo、LongMemEval、MemoryBank)或 LLM 构造/判卷(LTP、TReMu),这消除了标注一致性作为混杂变量。
3. 真值链使链条件归因成为可能——即把答错定位到链上具体状态转移——而现有基准最多做到检索命中率(LoCoMo recall@k)、能力分类(LongMemEval 五能力)或失效类型二分(A-TMA 的历史/冲突)。
4. 受控孪生与十项对照(泄漏探针 0.7%、判官交叉 2.7% 噪声带、乱序对照)提供了表中其他基准均未报告的构造效度检验层。
5. 上下文规模(33–35 sessions、整库中位 ~11.9k tok)与 LoCoMo(19.3 sessions / 9,209 tok)同量级且会话数更多,因此归因能力的提升并非以缩小任务规模为代价。

## 3. 最接近的竞争者(按性质)

- **也有"状态变更/链"性质:A-TMA 的 LTP**(arXiv:2607.01935)——最近的竞争者。它同样围绕状态变更构建(每 profile 插入 40 旧态 + 40 当前冲突线索,400+400 probes),且能区分两类失效(历史回忆失败 vs ghost memory 冲突)。差异点:其状态对为人工插入的线索对而非完整外部真值链(公开数据链字段实测为空,10 项),判卷依赖 LLM judge(llama3.3:70b)而非机械金答案。
- **也偏"机械/构造式金答案":TReMu**(arXiv:2502.01630)——600 道多选题由增强 LoCoMo 构造,含 112 道不可回答题,多选格式使判分机械化;但其时间线为系统侧推断,基准侧无真值链。
- **也覆盖"状态更新"能力:LongMemEval**(arXiv:2410.10813)——五能力中含 knowledge updates 与 temporal reasoning,与我方任务域重叠最大;但 500 题为人工精编,无链结构(78 个链字段实测为空),归因止步于能力分类。

---

# 附:逐家核实明细(一手来源与原文引句)

## LoCoMo — "Evaluating Very Long-Term Conversational Memory of LLM Agents" (Mahara
- 上下文规模:论文数据集:50 段对话("a datset of 50 high-quality very long conversations");每对话平均 19.3 个会话(Avg. sessions per conv. 19.3)、平均 304.9 轮(Avg. turns per conv. 304.9)、平均 9,209.2 tokens(Avg. tokens per conv. 9,209.2),最多 35 个会话("300 turns and 9K tokens on avg., over up to 35 sessions")。注意:官方 repo 实际发布的是 10 段对话子集(data/locomo10.json);该子集的平均会话/token 数在 README 中只以统计图(PNG)形式出现、无文字数值,二手来源称约 27.2 sessions / ~20k tokens,但未在一手来源核实——按要求标为 unverified(见 notes)。
- Embedding:RAG 基线检索器 = DRAGON(Lin et al., 2023),论文原句 "For the retrieval model, we employ DRAGON (Lin et al. 2023)。" 代码实现(task_eval/rag_utils.py)使用 HuggingFace 'facebook/dragon-plus-query-encoder' + 'facebook/dragon-plus-context-encoder';同文件还实现了备选项 facebook/contriever、facebook/dpr-ctx_encoder-single-nq-base / dpr-question_encoder-single-nq-base、OpenAI embedding(get_openai_embedding),但官方评测脚本固定 --retriever dragon。
- 检索配置:检索库三种粒度(非固定 token 分块):dialog history(逐轮)、observations(从对话抽取的关于说话人的断言)、session-level summaries——论文原句 "Retrieval-augmented Generation (RAG) involves retrieving relevant context from a database of dialog history, observations, or session-level summaries." 官方脚本 scripts/evaluate_rag_gpts.sh:dialog 与 observation 模式 top-k = 5, 10, 25, 50;summary 模式 top-k = 2, 5, 10;reader 为 gpt-3.5-turbo,--batch-size 1,命令模式 "python3 task_eval/evaluate_qa.py ... --model gpt-3.5-turbo --batch-size 1 --use-rag --retriever dragon"。论文另报 recall@k 衡量检索命中(QA 样本标注了含答案的 turn ID)。
- 备注:核实方法:arXiv HTML(v1)全文下载后本地 grep 逐句核对,repo 文件走 raw.githubusercontent 原文核对,均为一手来源。两处需注意:(1) 论文写 50 段对话,但 repo 公开发布仅 10 段(locomo10.json),README 提及初始 50 段未全部放出;引用 LoCoMo 数字时应注明用的是论文版(19.3 sessions / 9,209.2 tokens)还是 locomo10 子集(子集文字数值一手来源缺失,标 unverified,如需精确值可下载 locomo10.json 自行统计)。(2) 论文 RAG 主结果:"a noticeable 5% improvement with gpt-3.5-turbo when the input is top 5 relevant observations instead of pure conversation logs"——observation 粒度 + 小 top-k 最优,session summary 粒度收益不显著。查不到的字段:无(所有目标字段均已核实);唯一 unknown 是 locomo10 子集的官方文字版统计数值。
- 来源:
  - https://arxiv.org/abs/2402.17753 —— “each encompassing 300 turns and 9K tokens on avg., over up to 35 sessions”
  - https://arxiv.org/html/2402.17753v1 —— “Avg. sessions per conv. 19.3 / Avg. turns per conv. 304.9 / Avg. tokens per conv. 9,209.2 (Table 1)”
  - https://arxiv.org/html/2402.17753v1 —— “For the retrieval model, we employ DRAGON (Lin et al. 2023).”
  - https://arxiv.org/html/2402.17753v1 —— “Retrieval-augmented Generation (RAG) involves retrieving relevant context from a database of dialog history, observation”
  - https://github.com/snap-research/locomo/blob/main/scripts/evaluate_rag_gpts.sh —— “--model gpt-3.5-turbo --batch-size 1 --use-rag --retriever dragon (dialog/observation: top-k 5,10,25,50; summary: top-k ”
  - https://github.com/snap-research/locomo/blob/main/task_eval/rag_utils.py —— “'facebook/dragon-plus-query-encoder' / 'facebook/dragon-plus-context-encoder'; also facebook/contriever, facebook/dpr-*-”

## LongMemEval — "LongMemEval: Benchmarking Chat Assistants on Long-Term Interactiv
- 上下文规模:LongMemEval_S: ~115k tokens per problem (~40 history sessions, token count w.r.t. Llama 3 tokenizer). LongMemEval_M: ~500 sessions per chat history, around 1.5 million tokens. 500 questions total.
- Embedding:论文主检索基线:Stella V5 1.5B(dense retrieval,选它因 MTEB 高分)。官方 repo 另支持的检索器:flat-bm25、flat-contriever、flat-stella (Stella V5 1.5B)、flat-gte (gte-Qwen2-7B-instruct)。注意:text-embedding-3 和 BGE 均不在官方基线列表中(任务提示里的这两个猜测不成立)。
- 检索配置:
- 备注:核实方法:arXiv HTML(v2)与官方 GitHub README(含 raw 文件逐字校验)双源交叉验证。~115k token 的说法两处均确认。一个细节差异:论文写 "approximately 115k tokens per problem",README 写 "roughly consumes 115k tokens (~40 history sessions) for Llama 3"——即 token 数是按 Llama 3 tokenizer 计的。未查到论文对检索实验统一固定某个 top-k 的表述(按 unknown 处理,只报告了 @5/@10 指标点)。
- 来源:
  - https://arxiv.org/abs/2410.10813 —— “With 500 meticulously curated questions embedded within freely scalable user-assistant chat histories, LongMemEval prese”
  - https://arxiv.org/html/2410.10813v2 —— “LongMemEval_S with approximately 115k tokens per problem”
  - https://arxiv.org/html/2410.10813v2 —— “LongMemEval_M with 500 sessions (around 1.5 million tokens)”
  - https://arxiv.org/html/2410.10813v2 —— “For the retriever, we choose dense retrieval with the 1.5B Stella V5 model, given its high performance on MTEB”
  - https://github.com/xiaowu0162/LongMemEval —— “Concatenating all the chat history roughly consumes 115k tokens (~40 history sessions) for Llama 3.”
  - https://github.com/xiaowu0162/LongMemEval —— “flat-bm25, flat-contriever, flat-stella (Stella V5 1.5B), or flat-gte (gte-Qwen2-7B-instruct)”

## 两个基准:(1) DMR (Deep Memory Retrieval,MemGPT 团队引入,Zep 94.8% vs MemGPT 93.4%);(2) L
- 上下文规模:DMR:500 个多会话对话,每个含 5 个 chat sessions、每 session 最多 12 条消息;LongMemEval_s:每个对话平均约 115,000 tokens
- Embedding:需区分两处:论文实验实现用 BAAI 的 BGE-m3(同时做 embedding 和 reranking);graphiti 开源 repo 的代码默认值是 OpenAI text-embedding-3-small(graphiti_core/embedder/openai.py 中 DEFAULT_EMBEDDING_MODEL = 'text-embedding-3-small'),且可配置——支持 OpenAI / Azure OpenAI / Gemini / 任意 OpenAI 兼容端点(如 Ollama),通过 embedder 参数注入
- 检索配置:三种检索函数:cosine 语义相似度 (φ_cos)、Okapi BM25 全文检索 (φ_bm25)、广度优先图搜索 (φ_bfs);LongMemEval 实验中检索 top-20 条最相关 edges(facts)+ entity nodes(实体摘要);重排支持 RRF 与 MMR(实验实现的重排用 BGE-m3)
- 备注:用户问"graphiti 默认 embedding 是不是 openai text-embedding-3-small、可配否"——答案:是,且可配。但注意论文评测跑分用的是 BGE-m3,不是 repo 默认的 OpenAI 模型,引用论文数字时不要把两者混为一谈。arXiv 编号 2501.13956 (Rasmussen et al., 2025, "Zep: A Temporal Knowledge Graph Architecture for Agent Memory")。
- 来源:
  - https://arxiv.org/abs/2501.13956 —— “In the DMR benchmark, which the MemGPT team established as their primary evaluation metric, Zep demonstrates superior pe”
  - https://arxiv.org/html/2501.13956v1 —— “The Deep Memory Retrieval evaluation ... comprises 500 multi-session conversations, each containing 5 chat sessions with”
  - https://arxiv.org/html/2501.13956v1 —— “with conversations averaging approximately 115,000 tokens in length”
  - https://arxiv.org/html/2501.13956v1 —— “Our experimental implementation employs the BGE-m3 models from BAAI for both reranking and embedding tasks.”
  - https://arxiv.org/html/2501.13956v1 —— “We then retrieved the 20 most relevant edges (facts) and entity nodes (entity summaries) using the techniques described ”
  - https://arxiv.org/html/2501.13956v1 —— “Zep implements three search functions: cosine semantic similarity search, Okapi BM25 full-text search, and breadth-first”

## LOCOMO (LoCoMo)。Mem0 论文 (arXiv:2504.19413) 在 LOCOMO 上做系统评测,覆盖 "single-hop, tempo
- 上下文规模:LoCoMo:10 段长对话,每段平均约 600 条对话消息(dialogues)、约 26,000 tokens,分布在多个 session("It comprises 10 extended conversations, each containing approximately 600 dialogues and 26000 tokens on average")。记忆条目规模:论文只给了 token 口径——Mem0 每段对话的记忆占用平均约 7k tokens,图变体 Mem0g 约 14k tokens;每段对话的"记忆条数"论文未给出 → unknown。
- Embedding:论文原文写作 "text-embedding-small-3"(原句:"We initialized the LLM with gpt-4o-mini and used text-embedding-small-3 as the embedding model."——按原文照录,应即 OpenAI text-embedding-3-small,论文拼写疑似倒置);RAG 基线同样用它:"All chunks are embedded using OpenAI's text-embedding-small-3 to ensure consistent vector quality across configurations."。Repo 默认 embedder:OpenAI text-embedding-3-small,维度 1536(mem0/embeddings/openai.py:model or "text-embedding-3-small",embedding_dims or 1536)。
- 检索配置:RAG 基线:固定长度分块,chunk size ∈ {128, 256, 512, 1024, 2048, 4096, 8192} tokens(8192 为其 embedding 模型上限),k ∈ {1, 2}(k=2 时拼接最多 16384 tokens)。Mem0 自身写入/更新阶段:检索 top s=10 条语义相似记忆 + mm=10 条前文消息("'mm' = 10 previous messages for contextual reference and 's' = 10 similar memories for comparative analysis")。Mem0 回答阶段(query time)检索多少条记忆:论文正文未明确给出 → unknown。
- 备注:核实方式:arXiv 摘要页 + arXiv HTML v1 全文 + GitHub main 分支源码 + 官方 docs。三点提醒:(1) 论文实验配置(gpt-4o-mini + text-embedding-small-3)与 repo 当前默认(gpt-5-mini + text-embedding-3-small)不一致,截至 2026-08 repo main 已改默认 LLM;docs 只写默认 provider 是 OpenAI,不写具体型号,具体型号要看源码回退值。(2) "记忆条目条数"这一字段两边都查不到确数,只有 7k/14k tokens per conversation 的占用口径。(3) 引文经 WebFetch 摘取,已尽量要求逐字照录;"text-embedding-small-3" 的倒置拼写是论文原文如此。
- 来源:
  - https://arxiv.org/abs/2504.19413 —— “four question categories: single-hop, temporal, multi-hop, and open-domain”
  - https://arxiv.org/html/2504.19413v1 —— “It comprises 10 extended conversations, each containing approximately 600 dialogues and 26000 tokens on average”
  - https://arxiv.org/html/2504.19413v1 —— “All language model operations utilized GPT-4o-mini as the inference engine.”
  - https://arxiv.org/html/2504.19413v1 —— “We initialized the LLM with gpt-4o-mini and used text-embedding-small-3 as the embedding model.”
  - https://arxiv.org/html/2504.19413v1 —— “All chunks are embedded using OpenAI's text-embedding-small-3 to ensure consistent vector quality across configurations.”
  - https://arxiv.org/html/2504.19413v1 —— “We first segment each conversation into fixed-length chunks (128, 256, 512, 1024, 2048, 4096, and 8192 tokens)”

## MemoryBank (Zhong et al., arXiv:2305.10250, AAAI 2024):自建评估集——ChatGPT 角色扮演 15 个虚
- 上下文规模:MemoryBank:15 个虚拟用户 × 10 天模拟对话构成记忆库,每天对话覆盖至少 2 个话题,194 个探测问题(注意:官方 repo README 写的是 "100 probing questions",与论文 v3 的 194 不一致);论文未报告记忆库 token 总量(unknown)。MSC:训练集 4000 个 episode(3 sessions)+ 1001 个 episode(4 sessions),验证/测试集延至 5 sessions;4-session 训练对话平均约 53 条 utterance,5-session 验证/测试对话平均约 66 条 utterance;完整对话平均 1614 tokens(BlenderBot BPE 分词),而当时 BlenderBot 截断长度仅 128。
- Embedding:MemoryBank:论文正文称采用类 DPR 的 dual-tower dense retrieval,实现上经 LangChain + FAISS;英文用 MiniLM,中文用 Text2vec。官方 repo 配置文件坐实具体型号:EMBEDDING_MODEL_EN = "minilm-l6" → sentence-transformers 的 all-MiniLM-L6-v2;EMBEDDING_MODEL_CN = "text2vec" → GanymedeNil/text2vec-large-chinese。MSC:检索增强基线(RAG / FiD / FiD-RAG)用 DPR Transformer bi-encoder(基座 DPR 在 QA 数据对上预训练;FiD-RAG 则用 RAG 端到端训练后的 retriever)。所以答案是:MemoryBank=MiniLM(英)/Text2vec(中),MSC=DPR,两者不混。
- 检索配置:MemoryBank:论文正文未给 top-k/块大小;官方 repo 代码给出 VECTOR_SEARCH_TOP_K = 3(注释 "return top-k text chunk from vector store")、CHUNK_SIZE = 200(model_config.py),FAISS 向量库。MSC:检索单元(chunk/passage 粒度)作为超参数,对比按 utterance 切分 vs 整个 session(或 session summary)作一个 document,后者更优并用于最终结果;top-N 在 {3, 5, 6} 中按验证集为每个方法择优;论文指出其记忆规模不需要 FAISS 近似索引,直接存 DPR 向量做精确打分。
- 备注:核实方式:MemoryBank 用 arXiv v3 官方 HTML 全文 + GitHub 官方 repo 源码(raw 文件);MSC 用 ar5iv HTML 全文(arXiv v1,即 ACL 2022 论文 2022.acl-long.356 的 arXiv 版)。两处不一致点已如实标注:(1) MemoryBank repo README 说 100 个探测问题,论文说 194;(2) MemoryBank 论文本身不含 top-k,k=3 来自 repo 代码而非论文。MemoryBank 记忆库 token 总量:unknown(论文与 README 均未报)。MSC 论文未给单一固定 top-N,是 {3,5,6} 调参,不要写成定值。
- 来源:
  - https://arxiv.org/html/2305.10250v3 —— “we use MiniLM (Wang et al. 2020) as the embedding model for English and Text2vec (Ming 2022) for Chinese”
  - https://arxiv.org/html/2305.10250v3 —— “we adopt a dual-tower dense retrieval model similar to Dense Passage Retrieval (Karpukhin et al. 2020)”
  - https://arxiv.org/html/2305.10250v3 —— “we use LangChain (LangChain Inc. 2022) for memory retrieval. LangChain supports open-source embedding models and FAISS i”
  - https://arxiv.org/html/2305.10250v3 —— “we create a memory storage consisting of 10 days of conversations ... These conversations involve 15 virtual users with ”
  - https://arxiv.org/html/2305.10250v3 —— “we design 194 probing questions to assess whether the model could successfully recall pertinent memories”
  - https://github.com/zhongwanjun/MemoryBank-SiliconFriend/blob/main/memory_bank/memory_retrieval/configs/model_config.py —— “EMBEDDING_MODEL_EN = "minilm-l6" ... 'minilm-l6':'all-MiniLM-L6-v2' ... CHUNK_SIZE = 200”

## A-TMA (arXiv 2607.01935, NUS, v2 2026-07-08): 自建 LTP (LoCoMo Temporal Plus) 冲突型状
- 上下文规模:A-TMA — LTP: 10 个用户 profile、800 个判卷 probe(400 历史事实回忆 + 400 当前状态冲突);每个 profile 绑定一条 LoCoMo 对话并插入 40 旧态线索 + 40 当前/冲突线索;LoCoMo 全量:10 个样本、1,986 个 QA 对(论文未报 LTP 的 token 数)。TReMu — 基于 LoCoMo,论文正文引述其"平均 600 turns、16,000 tokens、最多 32 sessions";其 Table 1 实测统计为每对话平均 304.9 turns、19.3 sessions、9,209.2 tokens;自建基准共 600 道时序多选题(Anchoring 264 / Precedence 102 / Interval 234),其中 112 道不可回答,对比原 LoCoMo 仅 321 道时序 QA。
- Embedding:A-TMA: 检索侧不指定自有 embedding 模型——它是宿主记忆系统(A-Mem、Graphiti/Zep、Mem0 等)之上的 overlay,"The host keeps its own storage substrate, index backend, seed retriever, and answer model";论文唯一点名的 embedding 模型是写入侧 Sentry 组件用的 nomic-ai/nomic-embed-text-v1.5(SentenceTransformer backbone,接 topic/logic 两个 MLP 投影头,阈值 tau_top=0.60)。TReMu: N/A——全文无 "embedding" 一词;检索不用向量检索,而是 LLM 提示式检索(m_retrieved <- LLM_retrieval(q, M),Figure 12 为检索 prompt),框架建立在纯 prompting 的 MemoChat 三阶段管线上。
- 检索配置:A-TMA: 检索预算 top k=5;可选 retrieve controller(qwen3b-grpo-v6, 经 Ollama/OpenAI 兼容端点)只看候选池中最多 10 行、每行内容截断至 220 字符,最多选 3 行,其余槽位由稳定 pre-rank 回填;QA 模型 qwen2.5:3b,判卷用独立 llama3.3:70b;QA prompt 给每条检索行加 current/historical/transition 等五类状态标签;无传统 chunk size(记忆单元为状态记录)。TReMu: 无 top-k、无 chunk size——记忆单元是"每个 session 一条带推断日期的 timeline 摘要",检索由 LLM 按 prompt(Figure 12)从全部记忆中挑相关条目;底座模型 gpt-4o-2024-05-13 / gpt-4o-mini-2024-07-18 / gpt-3.5-turbo-0125。
- 备注:两篇均以 arXiv HTML 原文核实(A-TMA v2: /html/2607.01935v2;TReMu v2: /html/2502.01630v2)。两篇均未找到官方公开代码仓库(搜索无果,论文页无 code 链接),故无 repo/config 佐证,以上实现细节均出自论文附录 A.8 (A-TMA) 与正文/附录 D (TReMu)。注意 TReMu 的两组 LoCoMo 规模数字并存:正文转述 LoCoMo 原论文口径(600 turns/16K tokens/32 sessions),Table 1 为其自测口径(304.9/19.3/9,209.2)。A-TMA 的 A-TMA 展开名论文标题未给缩写全称,系统定位为 "state alignment overlay";LTP 结果主口径:Graphiti/Zep+A-TMA 冲突准确率 0.480->0.720(+0.240)。
- 来源:
  - https://arxiv.org/abs/2607.01935 —— “A-TMA: Decoupling State-Aware Memory Failures in Long-Term Agent Memory”
  - https://arxiv.org/html/2607.01935v2 —— “We build LTP (LoCoMo Temporal Plus) as a conflict heavy benchmark for ghost memory, with 10 profiles and 800 probes. LoC”
  - https://arxiv.org/html/2607.01935v2 —— “The release contains 400 historical fact recall probes and 400 current state conflict probes.”
  - https://arxiv.org/html/2607.01935v2 —— “Unless otherwise stated, QA uses qwen2.5:3b, retrieval uses top k=5, and the answer judge is a separate llama3.3:70b ser”
  - https://arxiv.org/html/2607.01935v2 —— “The deployed Sentry implementation uses nomic-ai/nomic-embed-text-v1.5 as the SentenceTransformer backbone with trust_re”
  - https://arxiv.org/html/2607.01935v2 —— “The host keeps its own storage substrate, index backend, seed retriever, and answer model.”
