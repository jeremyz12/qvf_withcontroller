# QVF 相关工作与定位简报

> **文档说明**：本简报为 QVF（Query-conditioned Validity Filter，查询条件化有效性过滤器）项目的相关工作调研与新颖性定位文档，内容基于 6 个并行调研通道（LongMemEval 基准、LoCoMo 基准、LLM 智能体记忆系统 2023–2026、知识冲突与时间有效性、RAG 证据过滤/验证/结构化、查询条件化有效性新颖性核查）的结构化调研结果汇总整理。截稿日期：2026-07-31。
>
> **QVF 一句话定位**：QVF 位于外部记忆检索之后、答案生成之前，其核心模块 Semantic Adapter 将（用户查询 + 原始检索记忆 + 真实元数据）转换为结构化的"查询条件化有效性图谱（Query-Conditioned Validity Map）"：带记忆 ID 引用的原子声明（atomic claims）、声明间语义关系（EQUIVALENT / SUPPORTS / COMPLEMENTS / COEXISTS / CONDITIONALLY_COMPATIBLE / CONTRADICTS / SUPERSEDES / UNRELATED / UNKNOWN）、查询条件化适用性标签（APPLICABLE / PARTIALLY_APPLICABLE / NOT_APPLICABLE / UNKNOWN）、查询条件化时间标签（CURRENT_FOR_QUERY / HISTORICAL_FOR_QUERY / SUPERSEDED_FOR_QUERY / FUTURE_OR_NOT_YET_VALID / TIME_INSENSITIVE / UNKNOWN）、记忆角色（DIRECT_SUPPORT / CORROBORATION / UPDATE / CONTRAST / QUALIFIER / BACKGROUND / DISTRACTOR / UNRESOLVED），以及充分性评估（SUFFICIENT / INSUFFICIENT / AMBIGUOUS）与风险标志。核心论点：**有效性是查询条件化的**——旧记忆并非全局无效，它对历史性问题可能恰恰是正确的；单凭更晚的时间戳不能证明取代（supersession）。

---

## 目录

1. [两个基准的精确细节](#1-两个基准的精确细节)
2. [相关工作分类综述](#2-相关工作分类综述)
3. [QVF 的新颖性定位：最接近的先行工作逐一对比](#3-qvf-的新颖性定位最接近的先行工作逐一对比)
4. [新颖性风险与需要在论文中规避/引用的重合点](#4-新颖性风险与需要在论文中规避引用的重合点)
5. [建议的基线方法列表与评测指标设计](#5-建议的基线方法列表与评测指标设计)
6. [完整参考文献列表](#6-完整参考文献列表)

---

## 1. 两个基准的精确细节

### 1.1 LongMemEval（主评测基准）

**基本信息**："LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory"，作者 Di Wu, Hongwei Wang, Wenhao Yu, Yuwei Zhang, Kai-Wei Chang, Dong Yu；ICLR 2025；arXiv 2410.10813；OpenReview ID: pZiyCaVuti。这是长期对话记忆评测的事实标准基准。包含 **500 道人工精选问题**，每题嵌入一个可自由扩展、带时间戳的用户-助手对话历史（"haystack"，草垛），由属性控制流水线以 needle-in-a-haystack 风格构建。测试五种核心能力：信息抽取、跨会话推理、时间推理、知识更新、拒答（abstention）。

#### 1.1.1 数据格式与字段（三个变体共享同一 schema）

每条实例是一个 JSON 对象，字段如下：

| 字段 | 说明 |
|---|---|
| `question_id` | 唯一 ID；**以 `_abs` 结尾表示拒答/伪前提（false-premise）问题，共 30 条**，由其他题型改写而来 |
| `question_type` | 六种标签之一：`single-session-user`、`single-session-assistant`、`single-session-preference`、`temporal-reasoning`、`knowledge-update`、`multi-session`；拒答是隐式的"第七类"，仅通过 `_abs` 后缀标记 |
| `question` | 问题文本 |
| `answer` | 参考答案 |
| `question_date` | **提问时刻的时间戳**——对查询条件化时间推理至关重要 |
| `haystack_session_ids` | 会话 ID 列表 |
| `haystack_dates` | 每会话时间戳列表（与 session_ids 对齐） |
| `haystack_sessions` | 会话列表；每个会话为轮次列表 `{"role": "user"/"assistant", "content": ...}`；**证据轮次额外携带 `"has_answer": true`** |
| `answer_session_ids` | 真值证据会话 ID（用于记忆召回评测） |

**题型分布（合计 500）**：single-session-user 70、single-session-assistant 56、single-session-preference 30、multi-session 133、knowledge-update 78、temporal-reasoning 133；30 条拒答实例通过 `_abs` ID 分布在各题型中。

#### 1.1.2 三个变体

| 变体 | 规模 | 文件大小 |
|---|---|---|
| `longmemeval_s`（"S"） | 每题约 **115k tokens** 历史（约 40–50 会话，Llama 3 分词器计） | HF 文件约 277–278 MB |
| `longmemeval_m`（"M"） | 每历史约 **500 会话，约 1.5M tokens** | HF 文件约 2.74–2.75 GB |
| `longmemeval_oracle` | 仅包含证据会话（oracle 检索） | 15.4 MB |

三个变体均包含相同的 500 道问题。**2025 年 9 月发布了清洗版重制**（"further cleaned up the history sessions to prevent interference on answer correctness"），是官方当前推荐版本（文件 `longmemeval_s_cleaned.json`、`longmemeval_m_cleaned.json`、`longmemeval_oracle.json`，位于 HF 仓库 `xiaowu0162/longmemeval-cleaned`）。

#### 1.1.3 官方评测协议

**(a) QA 准确率（LLM 裁判）**：生成系统输出 JSONL 假设文件，每行含 `question_id` 与 `hypothesis`；运行 `python3 src/evaluation/evaluate_qa.py <judge_model> <hypothesis_file> <reference_file>`（论文使用 **gpt-4o-2024-08-06** 为裁判；脚本支持 gpt-4o / gpt-4o-mini / llama-3.1-70b-instruct；temperature 0，最大 10 tokens），使用**按题型定制的二元 yes/no 裁判提示**，裁判判定通过 `'yes' in eval_response.lower()` 解析为 `autoeval_label`；再由 `print_qa_metrics.py` 汇总总体与分题型准确率。论文报告裁判与人工一致率 **>97%**。

分题型裁判规则（对 QVF 设计有直接意义）：

- **默认题型**：答案必须包含正确答案，仅答出子集算错；
- **temporal-reasoning**：日/周/月计数的 off-by-one 误差不扣分；
- **knowledge-update**：只要包含**更新后的答案**即算对，即使同时提到旧信息；
- **single-session-preference**：按 rubric 评分，但"不需要覆盖 rubric 中的全部要点"；
- **拒答（`_abs`）**：当且仅当模型识别出问题不可回答/信息缺失时判对。

**(b) 检索评测（独立进行）**：Recall@k 与 NDCG@k，粒度为 `turn` 或 `session`（`bash run_retrieval.sh IN_FILE RETRIEVER GRANULARITY`；基线检索器 flat-bm25 / flat-contriever / flat-stella / flat-gte；`print_retrieval_metrics.py` 汇总；真值 = `answer_session_ids` 与 `has_answer` 标志；**检索指标跳过 30 条拒答实例**）。

论文另提出跨索引/检索/阅读三环节的记忆设计优化：会话分解（session decomposition）、事实增强键扩展（fact-augmented key expansion）、时间感知查询扩展（time-aware query expansion）；键扩展输出可从 README 中的 Google Drive 链接下载。仓库结构：`data/`、`src/evaluation/`（evaluate_qa.py、print_qa_metrics.py、print_retrieval_metrics.py）、`src/retrieval/`、`src/generation/`、`generation_logs/`。

#### 1.1.4 精确下载方式与文件名

- **官方 GitHub**：https://github.com/xiaowu0162/LongMemEval
- **推荐清洗版数据（2025/09）**：HuggingFace 仓库 https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned，文件：`longmemeval_s_cleaned.json`（277 MB）、`longmemeval_m_cleaned.json`（2.74 GB）、`longmemeval_oracle.json`（15.4 MB）
- **原始数据**：HuggingFace 仓库 https://huggingface.co/datasets/xiaowu0162/longmemeval，文件 longmemeval_s（278 MB）、longmemeval_m（2.75 GB）、longmemeval_oracle（15.4 MB）；仓库脚本中的规范本地文件名为 `longmemeval_s.json`、`longmemeval_m.json`、`longmemeval_oracle.json`，置于 `data/` 下
- **自定义历史编译语料（Google Drive）**：https://drive.google.com/file/d/1loTKBdywbCfYL5h5zwfnVcqlh7QwnBQm/view，包含 `1_attr_bg/data_1_attr_bg.json`、`2_questions/`、`5_filler_sess/data_5_filler_sess.json`、`6_session_cache/data_6_session_cache.json`
- 论文：https://arxiv.org/abs/2410.10813；OpenReview：https://openreview.net/forum?id=pZiyCaVuti；项目页：https://xiaowu0162.github.io/long-mem-eval/
- **LongMemEval-V2**（2026/05，转向 agentic 记忆：451 题，多模态 web-agent 轨迹草垛，最高 500 轨迹 / 1.15 亿 tokens；能力维度：静态状态回忆、动态状态追踪、工作流知识、环境陷阱、前提感知；榜单指标 "LAFS Gain" 奖励准确率-延迟前沿）：https://github.com/xiaowu0162/LongMemEval-V2，HF 数据集 `xiaowu0162/longmemeval-v2`，论文 arXiv 2605.12493，站点 https://xiaowu0162.github.io/longmemeval-v2/

#### 1.1.5 SOTA 数字

**论文基线（S 变体，GPT-4o 裁判）**：

| 系统 | oracle | S | 相对下降 |
|---|---|---|---|
| GPT-4o 全上下文 | 0.870 | 0.606 | 30.3% |
| Llama 3.1 70B | 0.744 | 0.334 | 55.1% |
| Phi-3 14B | 0.702 | 0.380 | — |

商用助手在约为 S 十分之一长度的历史上：ChatGPT（GPT-4o）相比离线阅读下降 37%，Coze 下降 64%。

**2025–2026 各系统结果（多为厂商自报，longmemeval_s，GPT-4o 裁判除非另注；数据版本/裁判/答案模型不一，不严格可比）**：

| 系统 | 总体 | 分题型 | 备注 |
|---|---|---|---|
| Zep（arXiv 2501.13956, 2025-01） | 71.2%（gpt-4o；vs 全上下文 60.2%）；63.8%（gpt-4o-mini；vs 55.4%） | SSU 92.9 / SSA 80.4 / SSP 56.7 / TR 62.4 / KU 83.3 / MS 57.9（gpt-4o） | 延迟 2.58s vs 28.9s；约 1.6k 上下文 tokens vs 115k |
| Emergence AI（博客, 2025-06） | 86% | SSA 100 / SSU 98.57 / TR 85.71 / KU 83.33 / MS 81.20 / SSP 60 | 会话级 RAG + 交叉编码器重排 + CoT；vs Oracle GPT-4o 82.4%；naive RAG 52%；"Simple Fast" 变体 79% |
| Mastra（博客, 2025-07） | 80% | SSA 100 / SSU 97.1 / KU 84.6 / MS 76.7 / TR 75.2 / SSP 46.7 | 纯语义召回 topK-20 + 日期分组格式化；第三方榜单后来流传 Mastra 94.87% |
| Supermemory（自报研究页） | 约 95% | SSU 97 / SSA 100 / SSP 90 / KU 99 / TR 91 / MS 93 | Zep 对照数字直接抄自 Zep 论文，未重跑 |
| Mem0（自报, 2026） | 94.4 | 各页面自报数字互不一致（如博客：SSU 98.6 / SSA 98.2 / KU 93.6 / MS 88.0） | 平均检索 tokens 约 6.8k |
| ByteRover 2.1.5（自报博客） | 92.8% | — | 延迟 1.6s |
| Hindsight（arXiv 2512.12818） | 91.4% | — | 2026 年初自称 SOTA |
| OMEGA（omegamax.co, 2026-02） | 95.4%（466/500） | — | **非标准**：GPT-4.1 同时作为生成器与裁判 |
| agentmemory（GitHub 自称，未验证） | 96.2%（481/500） | — | 边缘自报 |
| MemPalace/MemPal（未验证） | 约 96.6% | — | 边缘自报 |
| Letta | 未发布 | — | — |

**关键警示**：以上数字横跨原始版与清洗版数据集、不同裁判与答案模型，且多为厂商自报——**V1 不存在中立榜单**。QVF 实验必须显式钉死：数据集版本（建议 cleaned）、裁判（gpt-4o）、检索预算（如 Zep 的 top-20）。

#### 1.1.6 LongMemEval 对 QVF 的意义（缺口）

LongMemEval 只评测两个端点——检索召回（Recall@k/NDCG@k）和最终 QA 准确率（二元 LLM 裁判）——**中间什么都没有**，恰是 QVF 占据的检索后/生成前空位。可利用缺口：

1. **无声明级/关系级真值**：基准从不标注检索记忆之间的矛盾/取代/共存关系；QVF 的 Validity Map 是全新的标注与评测层。knowledge-update（78 题）+ temporal-reasoning（133 题）提供天然弱监督：更新链与 `question_date` 允许由 `answer_session_ids` + `haystack_dates` **程序化推导** SUPERSEDED_FOR_QUERY vs CURRENT_FOR_QUERY vs HISTORICAL_FOR_QUERY 标签。
2. **查询条件化有效性是该基准最难的失败模式但从未被直接测试**：temporal-reasoning 几乎是所有系统最弱类别（Zep 62.4、Mastra 75.2、Emergence 85.71、全上下文 GPT-4o 45.1），Mem0 自己承认 ADD-only 架构在 knowledge-update 上退化——但没有任何指标区分"检索到了正确记忆但误判了其对本查询的有效性"与"根本没检索到"。QVF 可定义此分解（检索错误 vs 有效性判断错误 vs 阅读错误）作为新诊断指标。
3. **拒答在 LongMemEval 中很边缘**（仅 30 条 `_abs`，检索指标跳过，单一 yes/no 裁判）；QVF 的充分性评估把拒答泛化为校准化充分性，可在 `_abs` 子集上验证（INSUFFICIENT 应预测拒答）。
4. **裁判协议是分题型二元制，无部分分、无解释审计**——QVF 的带引用结构化声明支持可归因评测（哪些 memory-ID 支撑了答案）。
5. **干扰项维度隐含**（filler sessions 来自 5_filler_sess）**但从未被打分**；QVF 的 DISTRACTOR/UNRELATED 角色使之显式化。
6. 实操建议：以 `longmemeval_s_cleaned.json` 为主测床（115k tokens 适配标准检索预算；M 变体压测规模），保留官方 GPT-4o 裁判以便与 Zep/Emergence/Supermemory/Mem0 端到端可比，报告标准分题型准确率 **加上** QVF 新中间指标。V1 饱和声称（94–96% 自报）本身就是 QVF 细粒度评测故事的动机；LongMemEval-V2（agentic、前提感知）是合理的未来扩展目标。

---

### 1.2 LoCoMo（泛化评测基准）

**基本信息**："Evaluating Very Long-Term Conversational Memory of LLM Agents"，Maharana, Lee, Tulyakov, Bansal, Barbieri, Fang；ACL 2024 Long Papers（2024.acl-long.747）；arXiv:2402.17753。机器生成 + 人工编辑的超长多会话双人对话（两个 LLM 模拟人设，人设种子来自 MSC，发布为 `data/msc_personas_all.json`；对话锚定在时间事件图上，含图片分享轮次，携带 `img_url` + BLIP caption）。

**论文版统计（50 段对话，未完整公开）**：平均 19.3 会话、304.9 轮、约 9,209 tokens/对话，最长 35 会话跨数月；7,512 个 QA，五类：single-hop 2,705（36%）、multi-hop 1,104（14.6%）、temporal 1,547（20.6%）、open-domain 285（3.9%）、adversarial 1,871（24.9%）。人类 QA F1 87.9。

**发布版（实际所有人使用的版本）**：`data/locomo10.json`——**仅 10 段对话，1,986 个 QA**；每段约 600 轮、约 26k tokens（最长 35 会话）。按类别编号计数：**1=282、2=321、3=96、4=841、5=446**；排除类别 5 剩下被广泛引用的 **1,540 题**。

#### 1.2.1 数据格式（经抓取原始 locomo10.json 验证）

顶层为对话样本的 JSON 列表。每个样本字段：`sample_id`、`qa`（列表）、`conversation`（对象），以及 README 记载的标注：`event_summary`（每说话者的 events_session_&lt;n&gt;，事件摘要任务真值）、`observation`（session_&lt;n&gt;_observation，生成的事实，用作一种 RAG 数据库）、`session_summary`（session_&lt;n&gt;_summary，生成的摘要，用作另一种 RAG 数据库）。

- `conversation` 包含：`speaker_a`、`speaker_b`，以及成对键 `session_<n>`（轮次列表）与 `session_<n>_date_time`——**自然语言时间戳字符串，如 "1:56 pm on 8 May, 2023"，非 ISO 格式；任何时间系统必须先解析它们**。
- 每轮：`speaker`、`dia_id`（如 "D1:3" = 会话 1 第 3 条）、`text`，可选 `img_url`、`blip_caption`（及取图搜索词）。
- 每个 qa 项：`question`、`answer`（字符串或数字）、`evidence`（dia_id 字符串列表，如 `["D1:3","D7:11"]`——**真值支撑轮次**）、`category`（整数 1–5）；**类别 5 的条目携带 `adversarial_answer` 而非普通 `answer` 字段**。

#### 1.2.2 类别编号——关键陷阱

按原论文分类学与发布版计数/题风匹配，**数据中的编号是：1 = multi-hop（282）、2 = temporal reasoning（321）、3 = open-domain/反事实（"Would X still ... if ..." 风格，96）、4 = single-hop（841）、5 = adversarial/不可回答（446）**。

然而 **Mem0 评测框架**（Memobase、Backboard 及大多数后续厂商评测均从其派生）硬编码 `categories = ["single_hop","temporal","multi_hop","open_domain"]` 按 1..4 索引——即把类别 1 叫 "single_hop"、类别 3 叫 "multi_hop"、类别 4 叫 "open_domain"。**因此 Mem0 系谱表格的分类别列相对论文分类学是错贴标签的（只有 "temporal" 对得上）**：例如 Mem0 的高 "open-domain" 分数实际是在 841 道 single-hop 题上，其低 "multi-hop" 分数实际是在 96 道 open-domain 反事实题上。多个来源记载了这一论文-代码映射错位；**用计数（282/321/96/841/446）消歧任何已发表表格**。

#### 1.2.3 官方/原始评测协议（task_eval/evaluation.py + 论文）

- QA：**词元级 F1**，答案归一化（小写、去冠词/标点、Porter 词干化）；类别 1（multi-hop）答案按逗号切分做部分多答案 F1；类别 2/3/4 用普通 F1；**类别 5 二元评分**——检查输出是否包含 "no information available" 或 "not mentioned"（模型被提示对不可回答问题说 "No information available"）。另实现：exact match、ROUGE-L、BERTScore。
- 检索质量：对三个 RAG 数据库（原始对话 / observations / session summaries）测 recall@k（脚本 evaluate_gpts.sh、evaluate_claude.sh、evaluate_gemini.sh、evaluate_hf_llm.sh、evaluate_rag_gpts.sh，top-k ∈ {5,10,25,50}）。
- 事件摘要：ROUGE-1/2/L + FactScore precision/recall/F1；多模态对话生成：MMRelevance（这两项评测代码始终未完整发布，"Coming soon"）。
- 论文头条结果：最佳 QA 总体约 **37.8% F1**（GPT-3.5-turbo-16K 系基线；人类 87.9%；temporal 最差约 20.3% vs 人类 92.6%）；长上下文与 RAG 变体仍远低于人类。事件摘要最好约 45.9 FactScore F1。

#### 1.2.4 后续论文事实标准协议（Mem0 系，arXiv:2504.19413 起）

用 gpt-4o-mini 从检索记忆生成答案，指标为 F1、BLEU-1 与 **"J" = LLM-as-a-Judge**（二元对/错；Mem0 用 gpt-4o-mini 裁判、宽松指令、JSON 输出；Memobase 用 gpt-4o），**仅评类别 1–4**（1,540 题；排除 adversarial，声称"无真值"——实为类别 5 行是 `adversarial_answer` 字段且原始拒答评分从未被移植），10 次运行取均值，另报搜索/总延迟 p50/p95。

**Mem0 论文 J 分数（10 次均值）**：Mem0 66.88（其自报分类别：single-hop 67.13 / multi-hop 51.15 / temporal 55.51 / open-domain 72.93——注意标签已互换）、Mem0-graph 68.44、Zep 65.99、LangMem 58.10、OpenAI Memory 52.90、A-Mem 更低（如 single-hop 39.79、multi-hop 18.85）、**全上下文基线 72.90（即全上下文击败所有记忆系统）**；延迟：Mem0 search p95 0.200s、total p95 1.440s；Zep total p95 2.926s；全上下文 total p95 17.117s（"p95 延迟降低 91%"来源）。

#### 1.2.5 争议与可信度问题（QVF 必须了解）

1. **Mem0 vs Zep 之战**：Zep 反驳博客（"Lies, Damn Lies, Statistics: Is Mem0 Really SOTA?"）称 Mem0 错误配置了 Zep（两个说话者被灌入同一 user 角色；时间戳被拼进消息文本而非 Zep 的 created_at 字段；串行而非并行搜索），并报告修正后 Zep J = **75.14% ± 0.17**、p95 search 0.632s；Mem0 CTO 在 getzep/zep-papers issue #5 反击：Zep 后来的 "84%" 声称把 adversarial 答对计入分子却不计入分母、改了提示/模板、只跑一次；在 Mem0 标准协议下 Zep 为 **58.44% ± 0.20**。
2. **基准质量审计**（Penfield Labs / dial481/locomo-audit, 2026）：**99/1,540（6.4%）金标答案错误 → 有效分数上限约 93.57%**（分类别上限如 single-hop 95.72%、multi-hop 90.07%）；LLM 裁判对故意错误但模糊沾边的答案接受率高达约 63%；**类别 5（446 题）在任何已发表记忆系统结果中从未被评测**；open-domain 仅 n=96，需约 15 个百分点差距才具显著性；相邻榜单对比中 56% 在统计上不可区分；某些厂商分数（如 EverMemOS single-hop 95.96%）超过数学上限，意味着从错误金标获得了得分。
3. **Letta 博客**：一个只把对话历史存文件系统的平凡 agent（gpt-4o-mini）拿到 **74.0%**，论证 LoCoMo 接近饱和、无法区分记忆架构。
4. **Zep 等指出**：对话约 16k–26k tokens，装得进现代上下文窗口；且 LoCoMo **没有任何知识更新/取代类问题**——他们为此推荐 LongMemEval。
5. **跨厂商分数不可比**：裁判不同（gpt-4o vs gpt-4o-mini）、提示、检索配置、单次 vs 10 次平均、类别标签互换。较新自报数字：Memobase v0.0.37 J=75.78（gpt-4o 裁判）；Mem0 2026 算法自报 LoCoMo 92.5（平均 6,956 tokens/查询）与 LongMemEval 94.4——已逼近审计上限，自报需谨慎。
6. **多选题重制版**：HuggingFace `Percena/locomo-mc10`——全部 1,986 题转为 10 选项 MC（字段 question / choices / correct_choice_index / question_type 含 adversarial，另附 haystack_sessions / haystack_session_summaries / haystack_session_datetimes），用普通准确率替代 LLM 裁判。

#### 1.2.6 精确下载方式与文件名

- **官方仓库**：https://github.com/snap-research/locomo（README：`README.MD`；LICENSE.txt 在仓库内）
- **数据文件**：`data/locomo10.json`——直链：https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json
- `data/` 下另有：`msc_personas_all.json`（种子人设）、`multimodal_dialog/example/`（图片分享示例）
- **评测代码**：`task_eval/`（evaluation.py 等）与 `scripts/`（evaluate_gpts.sh、evaluate_claude.sh、evaluate_gemini.sh、evaluate_hf_llm.sh、evaluate_rag_gpts.sh、generate_observations.sh、generate_session_summaries.sh、generate_conversations.sh）
- 项目页：https://snap-research.github.io/locomo/；论文：https://aclanthology.org/2024.acl-long.747/（PDF：https://aclanthology.org/2024.acl-long.747.pdf）、https://arxiv.org/abs/2402.17753
- **事实标准记忆系统评测框架**：Mem0 评测代码（原在 github.com/mem0ai/mem0 的 evaluation/ 目录，现已从 main 移除；保留分叉含 run_experiments.py、evals.py、generate_scores.py、compute_p95_latency.py、prompts.py，位于 https://github.com/memodb-io/memobase/tree/main/docs/experiments/locomo-benchmark，分叉自 mem0 提交 `393a4fd5a6cfeb754857a2229726f567a9fadf36`）
- 多选版：https://huggingface.co/datasets/Percena/locomo-mc10；审计 + 修正标签：https://github.com/dial481/locomo-audit
- 注意：**只发布了 10 段对话子集；论文中的 50 段全集不公开**。

#### 1.2.7 LoCoMo 对 QVF 的意义（缺口）

1. **类别 5（adversarial，446 题）从未被任何记忆系统正式评测**——QVF 的充分性评估（INSUFFICIENT）+ DISTRACTOR 角色 + 拒答输出提供了原则性方法，可率先恢复完整 1,986 题基准。
2. **evidence 字段（每题 dia_id 列表）除检索召回外从未被利用**——QVF 带记忆 ID 引用的原子声明可对照 evidence 计算引用精确率/召回率（citation precision/recall），这是没有任何 LoCoMo 论文报告过的忠实性指标。
3. 裁判宽松 + 金标错误意味着头条 J 不可靠；QVF 可报告更严格的结构化评测（分类别 Wilson 置信区间、修正标签、多裁判），并将 Validity Map 定位为可审计的中间产物。
4. QVF 应公布显式的编号→名称映射（1=multi-hop、2=temporal、3=open-domain、4=single-hop、5=adversarial）与分类别计数以锚定可比性。
5. LoCoMo **没有知识更新/取代类问题**且时间戳是自然语言字符串——它无法测试 QVF 核心的 SUPERSEDES/SUPERSEDED_FOR_QUERY 逻辑（须由 LongMemEval 承担），但其 temporal 类别（321 题）测试对 "1:56 pm on 8 May, 2023" 式时间戳的解析与算术，在另一个 regime 中锻炼 QVF 的时间标签（HISTORICAL_FOR_QUERY vs TIME_INSENSITIVE）。
6. **全上下文击败所有记忆系统（72.9 vs ≤68.4）且平凡文件系统 agent 拿 74.0**——证明开放问题在检索后的、查询条件化的记忆推理，恰是 QVF 的空位；QVF 还应报告 token 成本（Mem0 2026 报约 6,956 tokens/查询）以证明 validity map 的开销物有所值。

### 1.3 可选的第三评测

- **STALE**（arXiv 2605.06527）：400 个专家验证的隐式冲突场景、1,200 个查询、上下文至 150K tokens；探测 State Resolution / Premise Resistance / Implicit Policy Adaptation；最佳前沿模型（Gemini-3.1-pro）仅 55.2%；直接题 92% 的模型在陈旧前提查询下崩至约 30%；被评测的记忆框架（LightMem、Zep、LiCoMemory、A-MEM、Mem0）表现均差；其 CUPMem 原型（写侧状态裁决）达 68%。
- **MemConflict**（arXiv 2605.20926）：显式把记忆有效性表述为"查询条件化的适用性（fitness-for-use）问题"，形式化动态（时间）/静态（事实）/条件（情境）三类冲突的多会话对话基准。

二者都是冲突聚焦测床，**尚无结构化图谱类方法在其上报告结果**——在 LongMemEval/LoCoMo 之外加入其一将显著强化 QVF 的新颖性主张。

---

## 2. 相关工作分类综述

### 2.1 记忆系统（Memory Systems for LLM Agents，2023–2026）

本类的总体结论：**所有处理冲突的现有系统都在写入/摄取时处理；没有任何系统在读取时、以当前查询为条件重新推导有效性。**

#### 2.1.1 经典/OS 式记忆管理

- **MemGPT / Letta**（arXiv 2310.08560）：OS 启发的"虚拟上下文管理"，三层：core memory（可编辑上下文内块）、recall memory（可搜索历史）、archival memory（向量库）。agent 通过工具调用自管理记忆。**有效性处理：几乎没有**——无时间模型、无取代语义，陈旧归档条目永久存在并可与新的矛盾条目一同被检回；矛盾消解完全留给生成 LLM。DMR 基准 93.4%（Zep 论文引用）。
- **MemOS**（arXiv 2507.03724）：MemCube 抽象统一参数/激活/明文记忆，含生命周期治理（溯源、版本、访问控制）；LoCoMo LLM 裁判 73.31→75.80（MemOS-1031）vs MIRIX 64.33、Mem0 59.22；相对 OpenAI memory 时间推理提升 159%；2026 营销称 LoCoMo 88.83 / LongMemEval 89.20。治理元数据存在但冲突处理是基础设施性的（版本、溯源），**不是语义性的**——无查询条件化适用性、无记忆间关系类型。
- **MemoryOS**（EMNLP 2025 Oral，arXiv 2506.06326）：短/中/长期分层，短→中为对话链 FIFO，中→长为热度（HEAT）分页晋升/驱逐；LoCoMo 相对基线 F1 平均 +48.36%（GPT-4o-mini）。更新是**纯 recency/热度驱动的覆盖**，无语义冲突消解；被取代的信息被驱逐而非时间限定。
- **MIRIX**（arXiv 2507.07957）：六个类型化存储（core、episodic、semantic、procedural、resource、knowledge-vault），各有管理 agent + 路由器；多模态截屏记忆；LoCoMo 平均 85.38%。**存储被类型化但记忆间关系没有**——无跨记忆矛盾/取代分析、无查询时有效性标签。

**与 QVF 的关系**：这些是 QVF 可以"包裹"的记忆后端，而非在有效性上的竞争者。QVF 可被定位为此类 OS 式系统缺失的语义"有效性层"。

#### 2.1.2 写入时冲突解决

- **Mem0 / Mem0g**（arXiv 2504.19413）：两阶段流水线——抽取候选事实；更新阶段检索 top-s 相似旧记忆并让 LLM 四选一：ADD / UPDATE / **DELETE（删除被新信息矛盾的记忆）** / NOOP。这是显式矛盾消解，但**破坏性且在写入时**：被矛盾的旧记忆被全局删除，尽管它可能正是历史性问题需要的。Mem0g 图变体在冲突时把过时关系标为 invalid 而非硬删。值得注意：Mem0 平台 v3 迁移说明称新算法"只添加新事实"（抽取时无 UPDATE/DELETE）——**业界对破坏性写入时消解的退却**。LoCoMo J 66.9–67.13 vs OpenAI Memory 52.9；Mem0g temporal 58.13 vs OpenAI 21.71；p95 search 约 0.20s；比全上下文省约 90% tokens（约 1,764 vs 26,031/对话）。
- **Memory-R1**（arXiv 2508.19828）：RL（PPO/GRPO）微调 Memory Manager 执行 {ADD, UPDATE, DELETE, NOOP} + Answer Agent 做"记忆蒸馏"——检回至多 60 个候选并过滤到相关子集再作答；仅 152 条训练 QA 即在 LoCoMo 上超 Mem0 +48% F1 / +69% BLEU-1 / +37% J（LLaMA-3.1-8B），泛化到 MSC 与 LongMemEval。**其 Answer Agent 是最接近 QVF 检索后过滤空位的 RL 类比，但它是习得的不透明过滤器**——无原子声明、无关系标签、无时间/适用性标签、无充分性/拒答输出，且其 Memory Manager 仍做破坏性写入操作。
- **CUPMem**（STALE 论文原型，arXiv 2605.06527）：写侧状态裁决/结构化状态整合，在 STALE 上达 68%。

**与 QVF 的关系**：写入时删除/更新是 QVF 论点的直接反面案例——冲突被一次性、全局地裁决，历史信息永久损失。QVF 保留全部记忆，在读取时按查询判定有效性。

#### 2.1.3 时间知识图谱

- **Zep / Graphiti**（arXiv 2501.13956）：时间感知知识图谱引擎，三个子图（情节/语义实体/社区）。**QVF 时间故事的最关键先行者：双时态模型**——每条事实/边四个时间戳：t_created/t_expired（事务/摄取时间线）与 valid_at/invalid_at（现实世界有效时间线）。摄取时新边由 LLM 与语义相关旧边比较；若被取代，旧边被 **INVALIDATED（置 expired_at/invalid_at）但不删除**，保留历史使 agent 能回答"上周二什么为真"。对双时间线的时间逻辑决定任意查询时刻的事实有效性。**但关键在于：取代决定在写入时一次性、全局做出——不会按查询重推**。数字：DMR 94.8%（gpt-4-turbo）vs MemGPT 93.4%，gpt-4o-mini 98.2%；LongMemEval 相对全上下文最高 +18.5% 准确率、延迟降约 90%；二级来源引 71.2% 总体、时间检索子任务 63.8%。

**与 QVF 的关系**：最强的时间限定先行工作。差异：(a) 失效在写入时由摄取 LLM 一次性判定，不按查询重推；(b) 有效性是边的全局属性，而 QVF 的标签（如 HISTORICAL_FOR_QUERY）以查询为条件——一条"已失效"的事实对历史问题仍可是 CURRENT_FOR_QUERY，这是 Zep 全局边失效表达不了的；(c) Zep 输出图，不是带引用的声明/关系/角色/充分性可解释图谱。

#### 2.1.4 追加式（append-only）系统——零冲突语义

- **A-MEM**（arXiv 2502.12110；NeurIPS 2025）：Zettelkasten 式原子"记忆笔记"（LLM 生成的上下文描述、关键词、标签 + 嵌入）；添加时做链接生成（与最近邻双向链接）与"记忆演化"（LLM 决定是否改写邻居笔记的描述/标签）。**无删除、无显式矛盾/取代/时间语义**——冲突笔记共存；任何"有效性"只在演化恰好改写邻居文本时隐式出现。LoCoMo 上对 MemGPT/MemoryBank/ReadAgent 有增益（尤其 multi-hop）。
- **HippoRAG**（NeurIPS 2024，arXiv 2405.14831）与 **HippoRAG 2**（ICML 2025，arXiv 2502.14802）：OpenIE 三元组构建无 schema KG（海马体索引）+ 从查询实体出发的 Personalized PageRank；HippoRAG 2 加入段落节点、query-to-triple 链接与 LLM "recognition memory" 种子过滤，自称非参数持续学习。**有效性处理：无**——图是追加式的；矛盾三元组共存，无时间戳、无失效、无陈旧模型。HippoRAG 2 在联想（多跳）记忆任务上超最佳嵌入模型 NV-Embed-v2 约 7%。
- **MemoChat**（arXiv 2308.08239）：指令微调的记忆-检索-响应循环，基于自撰的结构化主题备忘录（memos）；备忘录只追加不修订——无更新/失效/时间限定/矛盾机制。
- **Reflexion**（NeurIPS 2023，arXiv 2303.11366）：失败后生成语言自省存入有界情节缓冲（常 1–3 条）；任务级作用域、任务间重置；"陈旧"仅靠滑窗上限处理。是文本式 LLM 记忆产物范式的源头。

**与 QVF 的关系**：追加式系统把冲突仲裁完全静默留给阅读 LLM——STALE 显示即使前沿模型也只有约 55% 且在陈旧前提查询下崩到约 30%，量化了 QVF 要预防的失败。A-MEM 是 QVF 实验中自然的基线记忆后端。

#### 2.1.5 遗忘曲线/衰减式陈旧处理

- **MemoryBank**（AAAI 2024，arXiv 2305.10250）：分层存储（原始轮次、每日事件摘要、演化人格摘要），驱动 SiliconFriend；更新机制为**艾宾浩斯遗忘曲线**式衰减——记忆强度被检索时强化、随时间衰减，旧的未被检索的记忆被遗忘/删除。这是**纯时间/新近度的全局陈旧启发式**：无矛盾检测、无取代语义，且可能删除对历史查询仍有效的旧事实——**正是 QVF 查询条件化框架针对的失败模式**，也是论文相关工作中的最佳反衬基线。

#### 2.1.6 2025–2026 其他值得引用的系统

- **LightMem**（ICLR 2026，arXiv 2510.18866）：Atkinson-Shiffrin 式感官缓冲 → 主题感知短期记忆 → **睡眠期离线长期整合**（更新与推理解耦）；LongMemEval +2.09–6.40%（GPT），tokens 最多降 38 倍。整合（含冲突合并）是离线、全局的，与任何具体查询解耦；被 STALE 评为仍无法处理隐式失效。
- **SeCom**（ICLR 2025，arXiv 2502.05589，Microsoft）：分段级记忆粒度 + LLMLingua-2 压缩去噪；LoCoMo 与 Long-MT-Bench+ 上有增益。纯粒度/压缩工作，无有效性维度——但佐证了原始检索记忆是有噪的；QVF 处理的是语义噪声（无效/矛盾/干扰）而非 token 噪声。
- **MemInsight**（EMNLP 2025，arXiv 2503.21760，Amazon）：自主属性挖掘标注记忆以改进检索；LoCoMo 检索召回超 RAG 基线 +34%。写入时对单条记忆的语义富化；无记忆间关系、无查询条件化判断——QVF 的 Validity Map 是其读取时、关系化的对应物。
- **M+**（ICML 2025，arXiv 2502.00592）：潜空间记忆池（MemoryLLM）+ 共同训练检索器，保留跨度从 <20k 扩到 >160k tokens——参数化路线，有效性/引用/矛盾根本不可表达；用于圈定 QVF 的作用域为符号/文本记忆。
- **Hindsight**（arXiv 2512.12818，vectorize.io）：四网络（World / Experience / Opinion / Entity-Observation）+ retain/recall/reflect 操作；自报 LongMemEval 总体 91.4%（2026 年初称 SOTA）。区分观点与世界事实，但不输出查询条件化有效性/时间标签。
- **EverMemOS**（ACL 2026）：面向长程推理的自组织记忆 OS（其 LoCoMo 自报分数被审计指超数学上限，见 §1.2.5）。

#### 2.1.7 2026 年与 QVF 直接毗邻的有效性研究

- **STALE**（arXiv 2605.06527）：见 §1.3。证明 QVF 问题在 2026 年被公认为开放且困难。其修复（CUPMem）在写入时；QVF 的读取时查询条件化图谱是未被尝试的替代方案。
- **TOKI**（arXiv 2606.06240）：双时态算子代数（有效时间 × 事务时间），为 agent 记忆定义形式化的取代/矛盾消解/时间复合算子。QVF 差异：把有效性当作查询条件化的**语义**判断（LLM adapter 输出类型化标签），覆盖 TOKI 无法表达的关系（COMPLEMENTS、QUALIFIER、DISTRACTOR、充分性、风险标志）。
- **MemStrata**（"Temporal Validity in Retrieval Memory"，arXiv 2606.26511）：确定性 (subject, relation, object) 取代层，在双时态账本中退役陈旧值；论证朴素 RAG 从构造上无法消除陈旧事实错误。详见 §3.3。
- **MOSAIC**（该文献中报告）：摄取时矛盾检测 66%，对比现有记忆系统的 2–14%。
- **"Beyond Dialogue Time: Temporal Semantic Memory for Personalized LLM Agents"**（arXiv 2601.07468）。

**小结**：这些工作确认 QVF 针对的问题在 2026 年被公认为开放——**但全部把消解机制放在写入/摄取时或确定性账本中，没有一个是查询条件化的读取时语义分析**。

---

### 2.2 知识冲突与时间有效性（RAG QA 语境）

#### 2.2.1 知识冲突（context-memory 与 inter-context）

- **Longpre et al.**（EMNLP 2021）：实体替换框架制造 context-memory 冲突（同类型/别名/语料/流行度变体）；发现 QA 模型过度依赖参数记忆，受模型规模与实体流行度调制。QVF 差异：把冲突作为多种类型化关系之一，作用于真实检索记忆而非合成替换，并以查询为条件。
- **Chen, Zhang & Choi**（EMNLP 2022）：扩展到真实多段落设定（最多 100 段检索 + 参数知识），发现来源间矛盾几乎不动摇模型置信度；提出在证据含多个冲突候选时不强行给单一答案的校准目标——**QVF 的充分性/AMBIGUOUS 输出的最早先例，但它只校准置信度，不识别哪条证据有效、为何有效**。
- **Xie et al.（Adaptive Chameleon or Stubborn Sloth，ICLR 2024）**：LLM 对连贯的反记忆证据高度顺从，但只要有任何证据符合其参数信念就表现出强确认偏差——支持在生成前外置显式有效性图谱。
- **ClashEval**（NeurIPS 2024 D&B）：1,200+ 题、扰动检索文档；LLM 超过 60% 的情况采纳错误检索内容；采纳概率随扰动不合理程度下降、随先验置信度低而上升；用先验 vs 上下文 token 概率对比做简单冲突消解。其仲裁机制是答案级、基于概率的；QVF 是声明级、元数据落地的查询条件化判断。
- **Jin et al.（Tug-of-War, LREC-COLING 2024）**：越强的 RALM 越顽固地坚持错误内部记忆（Dunning-Kruger 式）——消解不能留给生成器的证据。
- **知识冲突综述**（EMNLP 2024，arXiv 2403.08319）：确立标准分类学——context-memory、inter-context、intra-memory 冲突，梳理成因与缓解族（忠实上下文提示、解码干预如 context-aware decoding、解耦如 DisentQA、微调如 KAFT）。**QVF 的关系集把 "inter-context 冲突" 细化为类型化关系并加入综述指为开放问题的查询条件化时间/适用性轴。**
- **ConflictBank**（NeurIPS 2024 D&B）：最大冲突基准（745 万 claim-evidence 对、55.3 万 QA），显式覆盖误信息、**时间**、语义三类冲突成因——可为 QVF 的 CONTRADICTS vs SUPERSEDES 区分提供辅助训练/评测数据。
- **DynamicQA**（Findings EMNLP 2024）：时间动态事实产生更多参数内冲突且**更难被上下文覆盖**——记忆增强 agent 最常更新的事实恰是模型最抗拒更新的，正是 QVF 的 UPDATE/SUPERSEDED 标签针对的失败。
- 机制级干预：IRCAN（上下文感知神经元重加权）、ParamMute（抑制知识关键 FFN）、Micro-Act（对冲突的可执行自推理，arXiv 2506.05278）、代理模型引导上下文敏感度（arXiv 2508.19720）；真实文档行为研究（Kortukov et al. 2024）与任务依赖研究（arXiv 2506.06485）表明**合成冲突与自然冲突行为不同**。

#### 2.2.2 inter-context 冲突与冲突感知 RAG

- **Astute RAG**（Google，arXiv 2410.07176）：来源感知地迭代整合内外知识；其研究中 70% 检索段落缺乏直接答案、19.2% 实例存在内外冲突（其中 47.4% 可由内部知识正确解决）；3 轮整合后 TriviaQA 84.45% / BioASQ 62.24%。整合成单一答案、不暴露结构；QVF 显式输出中间有效性图谱，支持审计、拒答与下游控制。
- **RAMDocs / MADAM-RAG**（arXiv 2504.13079，COLM 2025）：模拟歧义、误信息、噪声的真实混合；按文档 agent 辩论 + 聚合器区分正当歧义（多个有效答案）与误信息——概念上接近 QVF 的角色标签，但以自由形式辩论实现，非类型化结构图谱；AmbigDocs 上超强基线 +11.40%，FaithEval 上 Llama3.3-70B 绝对 +15.80%。其"多个有效答案可共存"立场对应 QVF 的 COEXISTS/CONDITIONALLY_COMPATIBLE。
- **Open Domain QA with Conflicting Contexts**（arXiv 2410.12311，Findings NAACL 2025）：众包标注 Google 检索上下文中的自然冲突（约 25% 的真实检索上下文存在冲突）；微调 LLM 解释冲突消解有帮助——支持 QVF 带引用声明的设计。
- 医疗领域工作（arXiv 2511.06668）指出过时建议与共识演化是 inter-context 冲突的典型来源。

#### 2.2.3 时间 QA 基准

- **TimeQA**（NeurIPS 2021 D&B）：Wikidata 时间演化事实，easy/hard（隐式）变体；41k 问题-段落对。假定证据已按时间限定好——无"判断检索记忆有效性"的概念。
- **TempLAMA**（TACL 2022）：时间限定完形填空 + 时间前缀训练；已知偏差：仅覆盖 2010–2020，且 70.69% 的问题可由主语最频繁宾语回答（频率捷径）。
- **SituatedQA**（2021）：答案依赖提问者的时间/地理语境。
- **TempReason**（ACL 2023）：三层时间推理（time-time、time-event、event-event）；低资源年份上准确率崩塌。
- **MenatQA**（Findings EMNLP 2023）：2,853 条时间敏感样本，scope/order/counterfactual 三因子扰动——其 **scope 因子（问题时间窄于/宽于事实有效区间）正是 QVF 的 PARTIALLY_APPLICABLE / 时间标签问题**。
- **TIQ**（WWW 2024 Companion）：隐式时间约束（"冷战期间"）——查询时间常不是字面写出的，QVF 的 Semantic Adapter 必须先推断隐含参考时间再打有效性标签。
- **ChroKnowledge / ChroKnowBench**（ICLR 2025）：跨领域按年评测演化 vs 不变事实（对应 QVF 的 TIME_INSENSITIVE 标签）；ChroKnowPrompt 遍历相邻年份唤起知识；纯参数化评测、无检索证据过滤。
- 动态/实时基准：RealTimeQA、**FreshQA/FreshLLMs**（Findings ACL 2024；never/slow/fast-changing 与 false-premise 分类；FreshPrompt；约 600 题定期刷新答案；Relaxed/Strict 双模式人评——**Strict 模式要求回答任何位置都不得出现过时陈述，值得 QVF 借用为陈旧内容泄漏指标**）、PAT-Questions（现在锚定、自更新）、UnSeenTimeQA（免记忆化）、DyKnow（评测时查 Wikidata 实时真值）、**EvolvingQA**（NAACL 2024；持续学习模型恰恰在更新与移除过时知识上失败）、GrowOVER（ACL 2024）、DynaQuest、Test of Time（合成时间逻辑）、TRAVELER（模糊/隐式/显式引用）、Complex-TR、TEMPO（2026，时间推理密集检索）。
- **时间 QA 综述 "It's High Time"**（arXiv 2505.20243）：按来源（历时新闻 vs Wikipedia 快照）、显式性、推理复杂度分类；开放挑战：静态快照上的答案漂移、时间不确定性（"所有日期被当作精确的"）、隐式时间意图、鲁棒性弱——**点名了 QVF 填补的缺口：系统把日期当精确值、推不出隐藏时间框架、把检索与有效性"分开"处理**。

#### 2.2.4 时间对齐与时间有效性

- **Time Vectors**（arXiv 2312.13401）：微调 LM 权重中的时间线性衰减 + 季节性错位；权重算术可操纵。
- **Set the Clock**（Findings ACL 2024）：预训练 LM 内部时间感"混乱"，可对齐到目标年份——但对齐到**一个**全局时间；QVF 的前提是有效性必须按查询（含历史查询时间）逐一条件化。
- **Ticktack**（arXiv 2503.04150）：六十干支循环编码长程时间；激活工程（arXiv 2505.14158）操纵时间敏感事实。
- **Right Knowledge, Wrong Answer**（arXiv 2606.20959，2026）：模型常**同时保有**过时与新事实却输出过时者（参数化时间冲突）；Temporal Attractor Steering 恢复 29–57% 冲突案例（同时保持 85–99% 非冲突准确率；Qwen2.5/Mistral/Llama3.1，8,746 条 Wikidata 记录）。**激活引导永远偏向新事实，无法服务历史查询——QVF 的查询条件化正是区分点。**
- **Temporal Validity Change Prediction**（Wenzel & Jatowt，Findings ACL 2024）：检测改变某陈述有效时长的上下文语句（Twitter 数据）——确立"时间有效性"为 NLP 文本属性；**QVF 把它操作化为对检索记忆的查询条件化标签**而非独立时长。
- **Chronocept**（arXiv 2505.07637）：把有效性建模为随时间的连续概率曲线。
- **QA under Temporal Conflict**（arXiv 2506.07270）：Temporal Wiki（Wikipedia 快照）与 Unified Clark（带时间戳新闻）基准；当同一事实的多个版本在上下文共现时，agentic 结构化外部记忆 + 时间过滤优于 ICL/RAG——消解手段是按时间排序过滤，非类型化逐声明标签，且无适用性/充分性评估。

#### 2.2.5 现有方法如何决定"哪条证据对该查询时间有效"——机制与局限

机制族：

- **(a) 检索时分数融合**：TempRALM（arXiv 2401.13222；给 Atlas 加时间相关性打分，最高 +74%）；半衰期新近度先验（score = α·cos + (1−α)·0.5^(age/h)）；时间戳感知嵌入（TempRetriever、TsContriever）。
- **(b) 查询分解 + 重排**：TimeR4（EMNLP 2024；retrieve-rewrite-retrieve-rerank 把隐式时间接地到 TKG 事实）；MRAG（Findings EMNLP 2025；分离语义与时间相关性，在 TempRAGEval——人工时间扰动 + 金标证据——上评测；**TempRAGEval 的逐证据诊断协议是评测 QVF 逐记忆标签的范本，但 MRAG 打的仍是相关性分，不是有效性，且无冲突结构**）。
- **(c) 硬时间过滤/窗口**。
- **(d) 版本/结构感知索引**：VersionRAG、DyG-RAG（事件中心动态图）、RAG-meets-temporal-graphs（arXiv 2510.13590）、MemoTime、HALO（arXiv 2505.07509；按关系半衰期过滤 TKG 过时事实——全局过滤会摧毁历史查询所需证据）、AionRAG。
- **(e) 结构化记忆上的确定性取代**（MemStrata）。
- **(f) LLM 先验-上下文仲裁**（ClashEval 的 token 概率）、自整合（Astute RAG）、多 agent 辩论（MADAM-RAG）。
- **(g) 参数化干预**（时间对齐、TAS 引导）。

**已被文献记录的局限（QVF 论点的实证支柱）**：

1. **新近度启发式对语料敏感且静默失败**：Freshness 研究（arXiv 2509.19376）显示某语料上最优的 (α, 半衰期) 在另一语料上 Latest@10 从 1.00 崩到 0.00；窄 top-K 语义候选选择在新近度先验起作用前就把最新条目丢掉了；朴素规则的趋势标注仅 0.08 macro-F1。
2. **LLM 重排器有系统性新近度偏差**（SIGIR-AP 2025，arXiv 2509.11353）：所有被测 LLM 重排器把人工做新的时间戳条目提升至多 95 名、在内容完全相同的情况下逆转 25% 的成对偏好、Top-10 平均出版年份偏移最多 +4.78 年；大模型减弱但从不消除该偏差——**这正是 QVF 拒绝的"更晚时间戳 = 取代"谬误的量化证据**。
3. 按新近度取代在历史问题上失效（综述指出系统"把所有日期当精确值"、推不出隐式查询时间）。
4. 过滤类方法**删除而非标注**，丢失历史/比较类查询所需证据。
5. 冲突消解类方法（辩论、整合、校准）输出单一答案或拒答，**而非可审计的逐声明有效性结构**。
6. 几乎所有冲突基准的冲突是合成制造的（实体替换、扰动）；近期工作显示这与真实文档中自然发生的冲突行为不同——QVF 使用真实检索记忆与真实元数据是可辩护的现实性主张。

---

### 2.3 RAG 过滤与验证 / 结构化中间表示

2023–2026 检索后证据处理文献可分六股。**对 QVF 的关键结论：许多系统在检索与生成之间插入了"某种东西"，但几乎没有系统插入类型化、声明级、查询条件化的有效性结构；时间适用性要么在索引时全局处理，要么完全不处理。**

#### 2.3.1 自反思/纠错式过滤

- **Self-RAG**（ICLR 2024，arXiv 2310.11511）：训练 LM 产生反思 token——Retrieve、ISREL（段落是否相关）、ISSUP（输出是否被支持）、ISUSE（效用）——逐段落批判成为显式离散中间信号。**最早被广泛采纳的结构化逐段落信号；但只有相关/支持/效用标签——无证据间关系、无时间、无查询条件化有效性语义。**
- **CRAG**（arXiv 2401.15884）：轻量 T5 检索评估器把文档分桶 Correct / Incorrect / Ambiguous，坏桶触发 web 搜索兜底，decompose-then-recompose 剥离无关片段。检索后有效性闸门的原型，但是文档级、三分类、**时间上查询无关**（"correct" 是绝对的，不是"对本查询时间框架正确"）。在查询错误下比 Self-RAG 优雅退化。
- **RankRAG**（NeurIPS 2024）：单一指令微调 LLM 统一排序与生成；Llama3-RankRAG-70B 在九个知识密集基准上胜 GPT-4——纯相关性、完全无显式中间表示，是 QVF 可解释外部图谱的对立设计点。
- **FILCO**（arXiv 2311.08377）：用蕴含、词面重叠、条件交叉互信息（CXMI）训练句级上下文过滤器；六个任务提升并削减提示长度至多 64%。输出只是过滤后的字符串——**丢弃而非标注**。
- NLI 重排/过滤实证结果好坏参半：纯 NLI 重排会降 EM/F1；DPR+BM25+NLI 混合更好。
- **SEER**（EMNLP 2024，arXiv 2410.11315）：自对齐证据抽取；**InstructRAG**（arXiv 2406.13629，ICLR 2025）：自合成去噪 rationale——自由文本理由，QVF 用可审计类型化 schema 替代；**Speculative RAG**（arXiv 2407.08223，ICLR 2025）：小模型对文档子集并行起草答案+理由，大模型验证选择——子集间视角多样性松散呼应 COEXISTS/CONTRAST，但无类型化、无查询条件化。

#### 2.3.2 声明分解（claim decomposition）

**FActScore**（EMNLP 2023，arXiv 2305.14251）确立"分解为原子事实再验证"范式；**WICE**（2023）做子声明蕴含；**VeriScore**（2024）只抽取可验证声明（滑动上下文窗）；**Core**（arXiv 2407.03572）做信息量加权子声明去重；**DnDScore**（2024/EMNLP 2025）证明分解必须伴随去语境化（decontextualization）；**Decomposition Dilemmas**（NAACL 2025，arXiv 2411.02400）显示分解对验证可助可害。

**与 QVF 的关系**：这股文献提供 QVF 原子声明机制的工具箱（及陷阱），但被用于**输出侧事实性评估**，不是输入侧生成前结构；且没有任何工作把声明有效性以查询为条件。QVF 的去语境化必须**保留记忆元数据（时间戳、会话）**使声明保持可裁决。

#### 2.3.3 结构化中间表示

- **StructRAG**（ICLR 2025，arXiv 2410.08815）：旗舰工作——推理时混合结构路由器按任务选最优结构类型（表格/图/算法/目录/块），结构化器把检索文档转为该结构，利用器把问题对结构分解；在知识密集推理上 SOTA。**证明了检索-生成之间的推理时重构值得做，但其结构承载的是内容组织，不带有效性/时间语义。QVF 可引它为结构范式并在标签语义上区分。**
- **Chain-of-Note**（arXiv 2311.09210，EMNLP 2024）：逐文档生成阅读笔记（direct-answer / inferential / unknown）再作答（平均 +1.97 EM）；支持 unknown 拒答——**QVF 记忆角色与充分性输出的文本化、无类型前身**：笔记是无 schema 散文，无声明-引用映射、无文档间关系、无时间标签。
- **Astute RAG**：一致 vs 冲突分簇——QVF 九关系分类学的粗糙二关系祖先。
- **CARE-RAG**（arXiv 2507.01281）：参数感知 vs 上下文感知证据表示 + 蒸馏 3B 检测器做冲突驱动摘要，含对过时基准答案的 QA 修复步骤。**管线形状最接近 QVF（精炼→冲突检测→结构化综合→生成），但其中间物是摘要而非标注图谱，"过时"靠修金标处理而非查询条件化时间标签。**
- 证据/声明图：**FactCG**（arXiv 2501.17144）图式多跳数据训练事实核查器；**Reasoning-with-Graphs**（arXiv 2501.07845）从上下文抽取显式推理图；**GRS-QA**（arXiv 2411.00369）推理结构标注 QA；2026 年有面向科学文献的"Typed Claim Network"工作；GraphRAG 系检索三元组/子图。**边是推理/蕴含依赖，不是有效性关系；均无查询条件化或时间维度。**
- 压缩是中间结构化的退化形态：**RECOMP**（ICLR 2024，arXiv 2310.04408）抽取式/摘要式压缩（空摘要选项是粗糙的充分性信号）；**LLMLingua / LongLLMLingua / LLMLingua-2**（arXiv 2310.06839 等）token 级剪枝（LongLLMLingua 查询感知）；2026 有论文把软压缩重述为"query-conditioned selector"——**该短语已存在，但仅指 token 选择，不指有效性**。压缩综述：arXiv 2409.13385。

#### 2.3.4 充分性与证据力

- **Sufficient Context**（Google，ICLR 2025，arXiv 2411.06037）：定义并自动评估"检索上下文本身是否足以作答"；显示大模型在上下文不足时**答错而不拒答**；充分性引导的拒答把选择性准确率提升 2–10 点；已上线 Vertex AI RAG Engine。**QVF 的 SUFFICIENT/INSUFFICIENT/AMBIGUOUS 字段的直接先例——但它是单一查询级二元信号，与任何声明结构脱钩；QVF 把充分性与逐声明角色和风险标志整合，使 INSUFFICIENT/AMBIGUOUS 裁决可归因到具体缺失或冲突的声明。**
- **Relevant Is Not Warranted**（arXiv 2605.28044，2026）：主张在带引用 RAG 中把主题相关性与证据力（文档是否真正担保所引声明）分离——**独立支持 QVF 区分 DIRECT_SUPPORT 与 BACKGROUND/CORROBORATION/DISTRACTOR 的角色分类学：相关与支持是不同的轴**。

#### 2.3.5 知识冲突（RAG 侧检测与基准）

- **Contradiction Detection in RAG Systems**（arXiv 2504.00180）：把 LLM 当"上下文验证器"评测其对检索集内矛盾的检测——验证了 QVF 前提（需要对检索上下文做专门验证遍），但仅检测、无消解标签、无时间/适用性维度。
- **DRAGged into Conflicts / CONFLICTS 基准**（arXiv 2506.08500）：冲突类型分类学 + 首个专家标注的真实 RAG 冲突类型基准；**显式推理冲突类型显著改善响应**。其分类学分类的是"冲突"，QVF 标注的是"每条声明对该查询的有效性"——粒度互补。
- **WikiContradict**（NeurIPS 2024 D&B，arXiv 2406.13805）：真实维基百科内部矛盾（很多是时间性的）QA 基准——只有评测无机制。
- **MAGIC**（arXiv 2507.21544）：KG 派生的多跳 inter-context 冲突——冲突常是间接的（经链条），扁平逐文档分类器发现不了，**支持 QVF 声明间关系边的设计**。冲突类型感知可加约 24 个准确点（CONFLICTS/MAGIC 一线文献）。

#### 2.3.6 时间有效性与记忆侧近邻（最接近 QVF，多为 2025–2026）

- 时间 RAG 多把时间烤进索引：T-GRAG / TG-RAG / DyG-RAG / E2RAG 构建带时间戳或事件中心的时间图；SAT-Graph RAG 做结构感知时间检索；**IA-RAG**（arXiv 2606.06044，2026）用 Allen 区间代数做动态知识时间推理；ChronoQA（5,176 条中文时间问题，30 万新闻，2019–2024）与 Nature Scientific Data 2025 时间敏感 RAG 数据集（arXiv 2508.12282）提供基准。**时间性在索引/检索结构中、检索前或检索中被解决；QVF 在读取时按查询裁决时间适用性，无需重建记忆库索引。**
- **MemStrata**、**"Don't Ask the LLM to Track Freshness"**（arXiv 2606.01435；主张 LLM 不应在推理时裁决新鲜度，提出确定性元数据规则，MemoryAgentBench 上评测；**承认旧记忆对回溯性查询可以是正确的**）——确定性阵营，详见 §3、§4。
- **STALE / CUPMem**、**MemConflict**、**MemChain**、**ConvMemory v3**、**DeferMem**（arXiv 2605.22411，查询时证据蒸馏 RL）、**RaMem**（arXiv 2606.22844，有效性感知的情境重现）——同一插槽的相邻工作，详见 §3。

#### 2.3.7 本股文献的底线结论

已被提出的结构化中间物清单：反思/批判 token（Self-RAG）、正确性分桶（CRAG）、阅读笔记（Chain-of-Note）、抽取/摘要式压缩（RECOMP、压缩系）、路由选择的表/图结构（StructRAG）、一致-冲突簇（Astute RAG、CARE-RAG）、证据/声明/推理图（FactCG、RwG、GraphRAG、类型化声明网络）、草稿+理由（Speculative RAG、InstructRAG）、充分性标签（Sufficient Context）、带语义角色的证据计划/轨迹（MemChain）。**没有任何一个在原子声明级同时建模查询条件化适用性与查询条件化时间有效性并附类型化声明间关系；时间处理凡存在者皆为索引时或全局确定性；查询条件化有效性只作为基准表述（MemConflict）或隐式习得策略（MemChain）存在，从未作为显式、可解释的输出 schema。**

---

## 3. QVF 的新颖性定位：最接近的先行工作逐一对比

调研结论：QVF 的问题空间（按查询判定检索记忆是否有效、适用、时间上当前）已在 2025–2026 成为活跃研究领域，**但没有任何现有系统产出 QVF 提出的产物**——一个把原子声明+记忆 ID 引用、9 元关系分类学、逐查询适用性标签、逐查询时间标签、记忆角色、充分性评估、风险标志合并在一起的结构化"查询条件化有效性图谱"。以下是必须逐一对比的 5 个最接近工作（按重合度排序）。

### 3.1 ConvMemory v3（arXiv 2606.26753，2026）——总体最接近的方法

- **它做什么**：在记忆检索与生成之间插入"Validity Context Layer"，做**目标条件化关系验证（target-conditioned relation verification）**：存储事实的取代/有效性相对被问的目标命题/实体来判断，只有通过有效性检验的记忆送达生成器；在 **LongMemEval 与 LoCoMo** 上评测。
- **与 QVF 的相同点**：同一管线插槽（检索后、生成前）；同一洞察（有效性是条件性的而非全局的）；同样的两个基准。
- **与 QVF 的差异**：(1) 其条件化对象是**目标实体/命题**而非完整查询——因此无法区分对同一目标的历史意图查询与当前意图查询；(2) 验证的关系集狭窄、以取代为中心，而非 QVF 的 9 元关系分类学；(3) 输出是**过滤后的记忆集合**，不是带逐查询适用性标签、逐查询时间标签（HISTORICAL_FOR_QUERY、FUTURE_OR_NOT_YET_VALID 等）、记忆角色、充分性评估与风险标志的声明式图谱。
- **论文对策**：必须显式引用并区分；理想情况下作为基线复现或至少构造消融（"仅目标条件化 vs 完整查询条件化"）。

### 3.2 MemChain（arXiv 2607.24097，2026）——输出结构重合最重的工作

- **它做什么**：可训练的检索后记忆策略（SFT + 轨迹引导 RL / TMPO），把（查询 + 检索记忆）转为**问题条件化证据计划**（含时间范围属性：current/recent/historical/any）、**带证据角色、候选 ID 引用与步骤间关系的接地证据轨迹**，以及 KEEP/DROP/MERGE/REFINE/ADD 动作，产出紧凑证据上下文交给冻结答案模型。LoCoMo 69.80%（GPT-4.1-mini 答案器，比最强基线 +6.10），也在 LongMemEval-S 评测；证据上下文 143.3 tokens vs 基线 3,491（约 24 倍压缩）。
- **与 QVF 的相同点**：同插槽、同基准；"问题条件化计划 + 角色 + 关系 + 引用 + 冻结生成器"与 QVF 重合度极高。
- **与 QVF 的差异**：(1) MemChain 是**端到端按答案奖励优化的训练型小模型策略**，目标是 token 高效压缩，不是可解释的声明式有效性裁决；(2) 其标签是动作与松散角色，**不是规范性有效性分类学**；(3) 无查询条件化适用性/时间标签语义（其 temporal scope 是计划属性，不是逐记忆标签）；(4) 无显式 UNKNOWN/拒答标签、无充分性或风险标志输出；(5) 被取代的记忆被**丢弃**，不是被标为 HISTORICAL_FOR_QUERY；(6) 其产物是压缩证据包，不是可审计有效性图谱。
- **论文对策**：这是相关工作章节 QVF 最需要区分的论文。QVF 的贡献应被框定为**声明式、可解释、免训练（prompt-based、Claude 后端）的裁决层 + 校准化拒答**，而非又一个压缩策略。

### 3.3 MemStrata（"Temporal Validity in Retrieval Memory"，arXiv 2606.26511，2026）——设计上的对立面（anti-thesis）

- **它做什么**：确定性取代层——双时态账本（valid_from / valid_to / superseded_by），以 (subject, relation) 为键的结构化取代在**摄取时**决定，读取路径无 LLM、无相似度阈值；被取代事实存档以支持 as-of-time 查询。陈旧事实回答率从 RAG 的 15–40% 降至约 0%；在代码/配置/API 演化基准上 0.95–1.00 vs RAG 0.20–0.47；读取延迟约 2.1s vs LLM 重排基线约 16–18s。**关键副产品**：证明嵌入相似度无法区分矛盾与复述/重复（AUROC 0.59，接近随机；矛盾与原文的相似度甚至高于重复与原文）。取代可靠性在干净单值事实上 97%，**在杂乱散文上跌至 44%**。
- **与 QVF 的相同点**：同一问题（陈旧事实错误）；同样反对"让 LLM 凭感觉追踪新鲜度"；其嵌入不可能结果是 QVF 语义 adapter 必要性的**强支持证据**。
- **与 QVF 的差异**：其有效性是**全局的、查询无关的**，在写入时按摄取顺序对结构化三元组固定；QVF 的中心主张是有效性仅相对查询有定义、更晚时间戳不能证明取代——恰是 MemStrata 拒绝做的语义判断（其 LLM 兜底只用于非三元组散文）。MemStrata 无法表达部分适用、条件兼容、佐证 vs 干扰、充分性；(s,r,o) 匹配漏掉复述/条件/部分冲突，也表达不了"对这个历史查询有效"。
- **论文对策**：作为关键对照引用；同时**必须回应其确定性/延迟批评**（QVF 在读取路径加了一次 LLM 调用）——用确定性规则欠定有效性的案例（历史查询、条件事实、佐证 vs 更新）与 AUROC 0.59 结果正面立论，并纳入确定性规则基线。

### 3.4 STALE + CUPMem（arXiv 2605.06527，2026）——问题动机与评测资源

- **它做什么**：基准——agent 是否知道自己的记忆已不再有效：400 个专家验证的隐式冲突场景（共指型 vs 传播型冲突）、1,200 查询、100+ 主题、上下文至 150K tokens；三探针：State Resolution、Premise Resistance、Implicit Policy Adaptation；最佳前沿模型仅 55.2%；直接题 92% 的模型在陈旧前提下崩至约 30%；被测记忆框架（LightMem、Zep、LiCoMemory、A-MEM、Mem0）表现均差。配套原型 **CUPMem** 通过结构化状态整合与传播感知搜索强化**写入时**修订，达 68%。
- **与 QVF 的关系**：提供 QVF 最需要的实证动机（"检索到"与"按有效性行动"之间的巨大鸿沟），其隐式冲突（无显式否定的失效）应由 QVF 的 CONTRADICTS/SUPERSEDES/CONDITIONALLY_COMPATIBLE 处理。差异：它是基准 + 写入时方法；QVF 在读取时按查询操作，旧记忆对历史问题保持有效——写入时状态覆盖处理不好的场景。其 Premise Resistance 探针还提示了 QVF 目前欠缺的扩展：**标记查询本身的错误预设**（可纳入风险标志）。
- **论文对策**：作为动机与（可选）第三评测引用；与 CUPMem 做"写入时 vs 读取时"的正面对比。

### 3.5 MemConflict（arXiv 2605.20926，2026）——概念表述最接近的基准

- **它做什么**：诊断基准，**明文把记忆有效性表述为"查询条件化的适用性（query-conditioned fitness-for-use）问题"**，并分解为时间有效性、事实正确性、情境适用性三维（与 QVF 三个标签维度对应）；受控多会话对话注入跨会话冲突与语义相似干扰项；黑盒答案准确率 + 白盒检索/排序分析评测六个记忆系统，发现答案正确性与支撑记忆检索质量频繁错位，且随历史长度与冲突距离退化。
- **与 QVF 的关系**：共享 QVF 的**精确概念框架**——但它是基准不是方法：不提出 adapter、无结构化有效性图谱、无关系分类学、无记忆角色、无充分性/风险输出。是"该问题已被承认"的最强证据，也是 QVF 应考虑追加的评测目标。
- **论文对策**：必须引用；把 QVF 定位为"对 MemConflict 所测问题的**首个结构化输出方法侧回答**"。**注意：不能再宣称"查询条件化适用性"这一表述本身是 QVF 首创**——首创点在于把它做成显式可解释 schema 与模块。

### 3.6 次级近邻（简要）

- **Zep/Graphiti**（arXiv 2501.13956）：双时态图可以**回答**历史查询，但取代判定写入时一次性全局做出（见 §2.1.3）——QVF 相关工作中必须精确措辞的对照（见 §4 风险 7）。
- **Memory-R1**（arXiv 2508.19828）：Answer Agent 的检索后蒸馏是同插槽的 RL 类比，但为不透明过滤器。
- **DeferMem**（arXiv 2605.22411）与 **RaMem**（arXiv 2606.22844）：同插槽相邻工作（查询时证据蒸馏 / 有效性感知情境重现），应引用。
- **CRAG**（arXiv 2401.15884）：查询条件化检索后过滤在 RAG 中的正典祖先；QVF 把该插槽从"相关性"泛化为"有效性/适用性/时间性"并作用于个人 agent 记忆。

---

## 4. 新颖性风险与需要在论文中规避/引用的重合点

1. **"查询条件化有效性"表述已被 MemConflict 占用**（"query-conditioned fitness-for-use"）。QVF 不能宣称提出该概念，只能宣称提出**首个以显式可解释 schema 输出它的方法**。必须引用并明确承接关系（诊断 → 方法）。
2. **MemChain 占据同一插槽、同一基准，且输出含角色/关系/引用**。若不正面区分（训练型压缩策略 vs 免训练声明式裁决；答案奖励优化 vs 规范性标签；丢弃 vs 标注；无充分性/拒答 vs 有），审稿人会认为 QVF 是 MemChain 的提示工程版。建议将 MemChain（或其思想的复现）纳入基线。
3. **ConvMemory v3 已提出"Validity Context Layer"并用同样两个基准**。QVF 必须在引言/相关工作中给出精确差异表（目标条件化 vs 查询条件化；取代中心 vs 9 元关系；过滤 vs 标注图谱），否则新颖性主张脆弱。
4. **确定性阵营的反击**（MemStrata、"Don't Ask the LLM to Track Freshness"、TOKI）：他们会主张 LLM 裁决不必要、且读取路径 LLM 调用带来延迟/成本（MemStrata 读取约 2.1s vs LLM 重排 16–18s）。论文必须：(a) 纳入确定性规则基线；(b) 构造确定性规则欠定有效性的案例集（历史查询、条件事实、复述冲突、佐证 vs 更新）；(c) 引用 MemStrata 自己的证据（嵌入 AUROC 0.59；杂乱散文上取代可靠性仅 44%）论证语义裁决恰在规则失效处必要；(d) 报告 QVF 的延迟与 token 开销并论证其换取的准确率/可审计性。
5. **充分性字段有直接先例**：Sufficient Context（ICLR 2025）已提出充分性自动评估并展示 2–10 点选择性准确率收益。QVF 的增量必须表述为"与逐声明结构整合、可归因到具体缺失/冲突声明的充分性"，而非"提出充分性评估"。同理，Chen et al. 2022 的冲突下校准是 AMBIGUOUS 的早期先例；CRAG 的 Ambiguous 桶是粗糙类比。
6. **角色分类学有部分先例**：Chain-of-Note 的三类笔记（direct-answer/inferential/unknown）是无类型前身；"Relevant Is Not Warranted"（2026）已分离相关性与证据力；MemChain 有松散证据角色。QVF 的差异在于**固定的、规范性的、逐记忆的角色 schema**（含 DISTRACTOR/UNRESOLVED），并使角色可被量化评测（干扰项识别指标）。
7. **对 Zep 的措辞必须精确**：Zep 的双时态图**能够服务**历史时间点查询（valid_at/invalid_at 上的时间逻辑），不能说"Zep 无法回答历史问题"；正确的批评是**取代判定在写入时一次性全局做出、不按查询重推、且以"后时间戳 + LLM 摄取判断"为准**——一旦误判即对所有查询生效，而 QVF 每次查询重新裁决且不预设"更新即取代"。
8. **冲突关系分类学的部分重合**：知识冲突综述（context-memory/inter-context/intra-memory）、RAMDocs（歧义 vs 误信息 vs 噪声）、DRAGged/CONFLICTS（冲突类型分类学 + "类型感知有帮助"的证据，约 24 点收益）。QVF 的 9 元关系集（尤其 CONDITIONALLY_COMPATIBLE、COMPLEMENTS、SUPERSEDES-vs-CONTRADICTS 的区分）比已发表工作细——建议在相关工作里放一张**分类学对齐表**，这本身是可陈述的贡献。
9. **"时间有效性"术语已有出处**：Wenzel & Jatowt（Temporal Validity Change Prediction）与 Chronocept 把 temporal validity 确立为文本属性研究方向；引用并说明 QVF 的操作化差异（对检索记忆的查询条件化标签 vs 独立的有效时长/概率曲线）。
10. **评测可信度风险**：LongMemEval V1 数字多为厂商自报且版本/裁判混乱（无中立榜单）；LoCoMo 存在金标错误（6.4%）、裁判过宽（约 63% 错误模糊答案被接受）、类别标签互换、类别 5 从未被评。QVF 若不显式钉死协议（数据版本、裁判、检索预算、运行次数、类别映射、置信区间），其数字会被质疑；反之，把这些问题处理好本身就是贡献（首个正式评测 LoCoMo 类别 5、修正标签、Wilson CI）。
11. **写入时 vs 读取时的边界要诚实**：Memory-R1 的 Answer Agent、DeferMem、RaMem、MemChain 都已在"读取时"做某种过滤/蒸馏——QVF 不能宣称"首个读取时处理"，只能宣称"首个读取时**查询条件化的、显式 schema 的有效性裁决**"。
12. **缩写冲突**："QVF" 在 ML 领域无已知冲突；但领域外有 (1) Qlik Sense 应用文件格式 `.qvf`（BI/分析领域广为人知，搜索噪声将被其主导）、(2) 密歇根州 "Qualified Voter File" 官方选民登记库。均不阻碍在 ML 论文中使用，但建议全文一致地写作 "QVF (Query-conditioned Validity Filter)"。

---

## 5. 建议的基线方法列表与评测指标设计

### 5.1 基线方法（按论证角色分组）

**A. 下界与上界锚点**

1. **无记忆**（仅当前问题直接作答）——下界。
2. **全上下文阅读**（整个 haystack 塞进上下文；LongMemEval S 上 GPT-4o 60.6%；LoCoMo 上 72.90 J）——LoCoMo 上它击败一切记忆系统，是 QVF 必须有意义超越的强参照。
3. **Oracle 检索**（longmemeval_oracle；GPT-4o 87.0% / Emergence 报 82.4%）——阅读上界，用于分离检索误差。
4. **平凡强基线**：Letta 式文件系统 agent（LoCoMo 74.0）与 Mastra 式纯语义召回 topK-20 + 日期分组格式化（LongMemEval 80%）——证明 QVF 的收益不只是"把时间戳给模型看"。

**B. 检索/重排类（证明 QVF 不是更好的检索）**

5. 标准 RAG：flat-bm25 / flat-contriever / flat-stella / flat-gte（LongMemEval 官方检索脚本），session 与 turn 粒度，固定预算（建议对齐 Zep 的 top-20）。
6. Emergence 式会话级检索 + 交叉编码器重排 + CoT（86%）。
7. **新近度先验重排**（score = α·cos + (1−α)·0.5^(age/h)）与 LLM 重排器——同时用于展示新近度偏差失败案例（arXiv 2509.11353 / 2509.19376 的现象复现）。

**C. 检索后过滤/结构化类（QVF 的直接同类）**

8. **CRAG 式相关性闸门**（Correct/Incorrect/Ambiguous 三分类过滤）。
9. **Self-RAG 式逐段落批判**（ISREL/ISSUP 提示化复现）。
10. **Chain-of-Note**（逐记忆自由文本笔记再作答）——无类型结构 vs QVF 类型化图谱的关键消融。
11. **MADAM-RAG 式多 agent 辩论**（冲突消解的辩论路线）。
12. **确定性取代规则**（MemStrata 式：同 (subject, relation) 新值退役旧值；及 "Don't Ask the LLM" 式元数据规则）——确定性阵营的正面对照，重点展示历史查询与散文记忆上的失效。
13. **MemChain**（若可复现）或其思想的提示化近似（问题条件化计划 + KEEP/DROP 动作、无有效性标签）——最重要的差异化基线。

**D. 记忆系统后端（证明 QVF 可叠加）**

14. Mem0 / Zep（Graphiti）/ A-MEM 作为检索后端，各自"裸用" vs "+QVF"——展示 QVF 是可叠加层而非又一个记忆系统。注意复现 Zep 时避免 Mem0-vs-Zep 之战暴露的配置陷阱（说话者角色、created_at 时间戳字段、并行搜索）。

**E. QVF 消融**

15. 完整 Validity Map vs 去掉时间标签 vs 去掉关系 vs 去掉角色 vs 去掉充分性 vs 仅过滤（输出保留集而非图谱）vs 图谱仅作提示但不过滤——分离每个 schema 组件的贡献；另做"目标条件化 vs 完整查询条件化"消融以对位 ConvMemory v3。

### 5.2 评测指标设计

**端到端（可比性层）**

- LongMemEval：官方协议——`longmemeval_s_cleaned.json`，gpt-4o（gpt-4o-2024-08-06）裁判，总体 + 六题型分项准确率 + `_abs` 拒答分项；同时报 M 变体压测（可选）。
- LoCoMo：双轨报告——(a) Mem0 系协议（gpt-4o-mini 答案器，F1/BLEU-1/J，10 次平均）以便与已发表数字对齐，但**修正类别名称为论文分类学**（1=multi-hop、2=temporal、3=open-domain、4=single-hop、5=adversarial）并公布计数；(b) **完整 1,986 题**（首次含类别 5，用 QVF 的 INSUFFICIENT/拒答输出评分，沿用原始拒答短语协议或结构化拒答判定）。
- 判决稳健性：分类别 Wilson 置信区间；多裁判（gpt-4o + 一个更严格协议）；采用 locomo-audit 修正标签跑一遍敏感性分析；可选 LoCoMo-MC10 多选版做免裁判准确率通道。

**中间层（QVF 的新指标——核心贡献）**

1. **引用忠实性**：QVF 原子声明的 memory-ID 引用对照真值证据（LoCoMo `evidence` dia_ids；LongMemEval `answer_session_ids`/`has_answer`）计算 citation precision / recall / F1——现有任何 LoCoMo/LongMemEval 论文都未报告的指标。
2. **有效性标签准确率（弱监督）**：在 LongMemEval knowledge-update（78 题）与 temporal-reasoning（133 题）上，由更新链 + `question_date` + `haystack_dates` + `answer_session_ids` 程序化推导 SUPERSEDED_FOR_QUERY / CURRENT_FOR_QUERY / HISTORICAL_FOR_QUERY 真值，评测 adapter 标签准确率。
3. **误差分解**：每道错题归因为检索错误（证据未进候选）vs 有效性判断错误（证据在候选但被误标）vs 阅读错误（图谱正确但生成器答错）——LongMemEval/LoCoMo 均无此诊断维度。
4. **充分性校准**：INSUFFICIENT 预测对 LongMemEval `_abs` 子集与 LoCoMo 类别 5 的拒答行为（precision/recall + 校准曲线/选择性准确率，对齐 Sufficient Context 的 2–10 点收益口径）。
5. **干扰项识别**：DISTRACTOR/UNRELATED 标签对 filler/干扰会话的识别率（LongMemEval filler sessions；LoCoMo 语义相似干扰）。
6. **陈旧内容泄漏**（借 FreshQA Strict 模式思想）：最终回答任何位置出现被取代信息的比率——直接量化 QVF 相对无过滤基线的核心收益。
7. **新近度偏差抵抗**：构造历史意图查询对（同一目标，当前意图 vs 历史意图），测系统是否错误偏向新记忆——直接检验"更晚时间戳不证明取代"论点（呼应 arXiv 2509.11353 的实验设计）。

**成本层**

- 每查询 token 数（对齐 Mem0 2026 报的约 6,956 tokens/查询与 Zep 的约 1.6k）、adapter 调用延迟（p50/p95，对齐 Mem0 total p95 1.44s / 全上下文 17.1s / MemStrata 约 2.1s 的报告口径）、每题 API 成本——正面回应确定性阵营的开销批评。

**协议卫生（发表时必须钉死）**

- 数据集版本（cleaned）、裁判模型与提示、检索器与预算、运行次数、类别映射表、随机种子；发布假设文件与图谱产物以供审计——QVF 的图谱本身即"可审计中间产物"，应作为论文卖点演示。

**可选第三评测**：STALE（写入时 CUPMem 68% vs QVF 读取时对照）或 MemConflict（首个结构化图谱方法的成绩）——二者其一即可显著强化新颖性叙事。

---

## 6. 完整参考文献列表

（按主题分组；同一工作只列一次。年份为发现记录所载；URL 为调研通道给出的可用链接。）

### 6.1 评测基准（主）

1. LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory — 2024 (ICLR 2025) — https://arxiv.org/abs/2410.10813 （OpenReview: https://openreview.net/forum?id=pZiyCaVuti；项目页: https://xiaowu0162.github.io/long-mem-eval/；代码: https://github.com/xiaowu0162/LongMemEval；数据: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned）
2. LongMemEval-V2: Evaluating Long-Term Agent Memory in Agentic Context — 2026 — https://github.com/xiaowu0162/LongMemEval-V2 （arXiv 2605.12493；站点: https://xiaowu0162.github.io/longmemeval-v2/）
3. Evaluating Very Long-Term Conversational Memory of LLM Agents (LoCoMo) — 2024 — https://aclanthology.org/2024.acl-long.747/ （arXiv: https://arxiv.org/abs/2402.17753；代码/数据: https://github.com/snap-research/locomo；项目页: https://snap-research.github.io/locomo/）
4. LoCoMo-MC10（多选题重制版）— 2025 — https://huggingface.co/datasets/Percena/locomo-mc10
5. LoCoMo 审计（6.4% 金标错误 / 裁判宽松性）— 2026 — https://github.com/dial481/locomo-audit
6. STALE: Can LLM Agents Know When Their Memories Are No Longer Valid? (含 CUPMem) — 2026 — https://arxiv.org/abs/2605.06527
7. MemConflict: Evaluating Long-Term Memory Systems Under Memory Conflicts — 2026 — https://arxiv.org/abs/2605.20926

### 6.2 记忆系统与厂商评测

8. MemGPT: Towards LLMs as Operating Systems (Letta) — 2023 — arXiv 2310.08560；https://docs.letta.com/concepts/memory-management/
9. Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory — 2025 — https://arxiv.org/abs/2504.19413 （评测框架保留分叉: https://github.com/memodb-io/memobase/tree/main/docs/experiments/locomo-benchmark）
10. Zep: A Temporal Knowledge Graph Architecture for Agent Memory (Graphiti) — 2025 — https://arxiv.org/abs/2501.13956
11. A-MEM: Agentic Memory for LLM Agents — 2025 (NeurIPS 2025) — https://arxiv.org/abs/2502.12110
12. HippoRAG: Neurobiologically Inspired Long-Term Memory for LLMs — 2024 (NeurIPS 2024) — https://arxiv.org/abs/2405.14831
13. From RAG to Memory: Non-Parametric Continual Learning for LLMs (HippoRAG 2) — 2025 (ICML 2025) — https://arxiv.org/abs/2502.14802
14. MemoryBank: Enhancing Large Language Models with Long-Term Memory — 2023 (AAAI 2024) — https://arxiv.org/abs/2305.10250
15. MemoChat: Tuning LLMs to Use Memos for Consistent Long-Range Open-Domain Conversation — 2023 — https://arxiv.org/abs/2308.08239
16. Reflexion: Language Agents with Verbal Reinforcement Learning — 2023 (NeurIPS 2023) — https://arxiv.org/abs/2303.11366
17. MemOS: A Memory OS for AI System — 2025 — https://arxiv.org/abs/2507.03724
18. Memory OS of AI Agent (MemoryOS) — 2025 (EMNLP 2025 Oral) — https://arxiv.org/abs/2506.06326
19. MIRIX: Multi-Agent Memory System for LLM-Based Agents — 2025 — https://arxiv.org/abs/2507.07957
20. Memory-R1: Enhancing LLM Agents to Manage and Utilize Memories via Reinforcement Learning — 2025 — https://arxiv.org/abs/2508.19828
21. LightMem: Lightweight and Efficient Memory-Augmented Generation — 2025 (ICLR 2026) — https://arxiv.org/abs/2510.18866
22. SeCom: On Memory Construction and Retrieval for Personalized Conversational Agents — 2025 (ICLR 2025) — https://arxiv.org/abs/2502.05589
23. MemInsight: Autonomous Memory Augmentation for LLM Agents — 2025 (EMNLP 2025) — https://arxiv.org/abs/2503.21760
24. M+: Extending MemoryLLM with Scalable Long-Term Memory — 2025 (ICML 2025) — https://arxiv.org/abs/2502.00592
25. Hindsight: Building Agent Memory that Retains, Recalls, and Reflects — 2025 — https://arxiv.org/pdf/2512.12818
26. Beyond Dialogue Time: Temporal Semantic Memory for Personalized LLM Agents — 2026 — https://arxiv.org/abs/2601.07468
27. SOTA on LongMemEval with RAG (EmergenceMem) — 2025 — https://www.emergence.ai/blog/sota-on-longmemeval-with-rag
28. Zep Is The New State of the Art In Agent Memory（博客）— 2025 — https://blog.getzep.com/state-of-the-art-agent-memory/
29. Is Mem0 Really SOTA in Agent Memory?（Zep 反驳博客）— 2025 — https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/
30. Revisiting Zep's 84% LoCoMo Claim（zep-papers issue #5，Mem0 CTO）— 2025 — https://github.com/getzep/zep-papers/issues/5
31. Benchmarking AI Agent Memory: Is a Filesystem All You Need?（Letta 博客）— 2025 — https://www.letta.com/blog/benchmarking-ai-agent-memory/
32. Yes, you can use RAG for agent memory（Mastra 博客）— 2025 — https://mastra.ai/blog/use-rag-for-agent-memory
33. LongMemEval — Supermemory Research（自报研究页）— 2025/2026 — https://supermemory.ai/research/longmembench/
34. Mem0 Research: Token-Efficient Memory（自报）— 2026 — https://mem0.ai/research
35. State of AI Agent Memory 2026（Mem0 博客）— 2026 — https://mem0.ai/blog/state-of-ai-agent-memory-2026
36. OMEGA LongMemEval Benchmark Leaderboard（厂商榜单）— 2026 — https://omegamax.co/benchmarks
37. Memobase LoCoMo benchmark（Mem0 评测分叉文档）— 2025 — https://github.com/memodb-io/memobase/blob/main/docs/experiments/locomo-benchmark/README.md

### 6.3 有效性/取代/时间语义的直接毗邻工作（QVF 差异化重点）

38. ConvMemory v3: A Validity Context Layer for Conversational Memory via Target-Conditioned Relation Verification — 2026 — https://arxiv.org/pdf/2606.26753
39. MemChain: Learning Interpretable Memory Traces for Memory-Augmented LLM Agents — 2026 — https://arxiv.org/abs/2607.24097
40. Temporal Validity in Retrieval Memory: Eliminating Stale-Fact Errors for AI Agents (MemStrata) — 2026 — https://arxiv.org/html/2606.26511
41. TOKI: A Bitemporal Operator Algebra for Contradiction Resolution in LLM-Agent Persistent Memory — 2026 — https://arxiv.org/pdf/2606.06240
42. Don't Ask the LLM to Track Freshness: A Deterministic Recipe for Memory Conflict Resolution — 2026 — https://arxiv.org/pdf/2606.01435
43. DeferMem（查询时证据蒸馏，RL）— 2026 — https://arxiv.org/abs/2605.22411
44. RaMem（有效性感知的情境重现）— 2026 — https://arxiv.org/abs/2606.22844

### 6.4 知识冲突

45. Entity-Based Knowledge Conflicts in Question Answering (Longpre et al.) — 2021 (EMNLP 2021) — https://aclanthology.org/2021.emnlp-main.565/ （代码: https://github.com/apple/ml-knowledge-conflicts）
46. Rich Knowledge Sources Bring Complex Knowledge Conflicts (Chen, Zhang & Choi) — 2022 (EMNLP 2022) — https://arxiv.org/abs/2210.13701
47. Adaptive Chameleon or Stubborn Sloth (Xie et al.) — 2024 (ICLR 2024) — https://arxiv.org/abs/2305.13300
48. ClashEval: Quantifying the tug-of-war between an LLM's internal prior and external evidence — 2024 (NeurIPS 2024 D&B) — https://arxiv.org/abs/2404.10198
49. Knowledge Conflicts for LLMs: A Survey — 2024 (EMNLP 2024) — https://arxiv.org/abs/2403.08319 （资源列表: https://github.com/pillowsofwind/Knowledge-Conflicts-Survey）
50. Tug-of-War Between Knowledge (Jin et al.) — 2024 (LREC-COLING 2024) — https://arxiv.org/abs/2402.14409
51. ConflictBank: A Benchmark for Evaluating the Influence of Knowledge Conflicts in LLMs — 2024 (NeurIPS 2024 D&B) — https://arxiv.org/abs/2408.12076 （代码: https://github.com/zhaochen0110/conflictbank；HF: Warrieryes/ConflictBank）
52. DynamicQA: Tracing Internal Knowledge Conflicts in Language Models — 2024 (Findings EMNLP 2024) — https://arxiv.org/abs/2407.17023 （代码: https://github.com/copenlu/dynamicqa）
53. Astute RAG: Overcoming Imperfect Retrieval Augmentation and Knowledge Conflicts — 2024 (ICLR 2025, Google) — https://arxiv.org/abs/2410.07176
54. Retrieval-Augmented Generation with Conflicting Evidence (RAMDocs / MADAM-RAG) — 2025 (COLM 2025) — https://arxiv.org/abs/2504.13079 （代码: https://github.com/HanNight/RAMDocs）
55. Open Domain Question Answering with Conflicting Contexts — 2024 (Findings NAACL 2025) — https://arxiv.org/abs/2410.12311
56. WikiContradict: A Benchmark for Evaluating LLMs on Real-World Knowledge Conflicts from Wikipedia — 2024 (NeurIPS 2024 D&B) — https://arxiv.org/abs/2406.13805
57. DRAGged into Conflicts: Detecting and Addressing Conflicting Sources in Search-Augmented LLMs (CONFLICTS) — 2025 — https://arxiv.org/abs/2506.08500
58. MAGIC: A Multi-Hop and Graph-Based Benchmark for Inter-Context Conflicts in RAG — 2025 — https://arxiv.org/abs/2507.21544
59. Contradiction Detection in RAG Systems: Evaluating LLMs as Context Validators — 2025 — https://arxiv.org/abs/2504.00180
60. Micro-Act（冲突上的可执行自推理）— 2025 — https://arxiv.org/abs/2506.05278

### 6.5 时间 QA 与时间有效性

61. TimeQA: A Benchmark for QA over Time-Evolving Facts — 2021 (NeurIPS 2021 D&B) — https://arxiv.org/abs/2108.06314 （代码: https://github.com/wenhuchen/Time-Sensitive-QA）
62. Time-Aware Language Models as Temporal Knowledge Bases (TempLAMA) — 2022 (TACL) — https://arxiv.org/abs/2106.15110
63. TempReason: Benchmarking and Improving Temporal Reasoning of LLMs — 2023 (ACL 2023) — https://arxiv.org/abs/2306.08952 （代码: https://github.com/DAMO-NLP-SG/TempReason）
64. MenatQA — 2023 (Findings EMNLP 2023) — https://arxiv.org/abs/2310.05157
65. TIQ: Temporal QA with Implicit Time Constraints — 2024 (WWW 2024 Companion) — https://dl.acm.org/doi/10.1145/3589335.3651895
66. ChroKnowledge / ChroKnowBench — 2025 (ICLR 2025) — https://arxiv.org/abs/2410.09870 （HF: https://huggingface.co/datasets/dmis-lab/ChroKnowBench；代码: https://github.com/dmis-lab/ChroKnowledge）
67. FreshLLMs / FreshQA — 2024 (Findings ACL 2024) — https://arxiv.org/abs/2310.03214 （代码: https://github.com/freshllms/freshqa）
68. Carpe Diem: Evaluation of World Knowledge in Lifelong LMs (EvolvingQA) — 2024 (NAACL 2024) — https://arxiv.org/abs/2311.08106 （代码: https://github.com/kimyuji/EvolvingQA_benchmark）
69. DyKnow: Dynamically Verifying Time-Sensitive Factual Knowledge in LLMs — 2024 (EMNLP 2024) — https://arxiv.org/html/2404.08700
70. It's High Time: A Survey of Temporal Question Answering — 2025 — https://arxiv.org/html/2505.20243v3
71. Time is Encoded in the Weights of Finetuned Language Models (Time Vectors) — 2023 (ACL 2024) — https://arxiv.org/abs/2312.13401 （代码: https://github.com/yizhongw/llm-temporal-alignment）
72. Set the Clock: Temporal Alignment of Pretrained Language Models — 2024 (Findings ACL 2024) — https://arxiv.org/abs/2402.16797
73. Ticktack（六十干支循环时间编码）— 2025 — https://arxiv.org/abs/2503.04150
74. Right Knowledge, Wrong Answer: Test-Time Steering for Temporal Fact Conflicts (TAS) — 2026 — https://arxiv.org/abs/2606.20959
75. Temporal Validity Change Prediction (Wenzel & Jatowt) — 2024 (Findings ACL 2024) — https://arxiv.org/abs/2401.00779
76. Chronocept（有效性的连续时间概率建模）— 2025 — https://arxiv.org/abs/2505.07637
77. Question Answering under Temporal Conflict (Temporal Wiki / Unified Clark) — 2025 — https://arxiv.org/abs/2506.07270
78. It's About Time: Incorporating Temporality in RALMs (TempRALM) — 2024 — https://arxiv.org/abs/2401.13222
79. TimeR4: Time-aware Retrieval-Augmented LLMs for TKG QA — 2024 (EMNLP 2024) — https://aclanthology.org/2024.emnlp-main.394/
80. MRAG: A Modular Retrieval Framework for Time-Sensitive QA (含 TempRAGEval) — 2025 (Findings EMNLP 2025) — https://aclanthology.org/2025.findings-emnlp.167.pdf
81. Freshness and the Limits of Heuristic Trend Detection in Temporal RAG — 2025 — https://arxiv.org/html/2509.19376
82. Do LLMs Favor Recent Content? Recency Bias in LLM-Based Reranking — 2025 (SIGIR-AP 2025) — https://arxiv.org/abs/2509.11353
83. HALO: Half-Life Based Outdated Fact Filtering in Temporal KGs — 2025 — https://arxiv.org/pdf/2505.07509
84. RAG Meets Temporal Graphs — 2025 — https://arxiv.org/abs/2510.13590
85. IA-RAG（Allen 区间代数时间推理 RAG）— 2026 — arXiv 2606.06044
86. 时间敏感 RAG QA 数据集（Nature Scientific Data 2025）— 2025 — arXiv 2508.12282

### 6.6 RAG 过滤、验证与结构化中间表示

87. Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection — 2023 (ICLR 2024) — https://arxiv.org/abs/2310.11511
88. Corrective Retrieval Augmented Generation (CRAG) — 2024 — https://arxiv.org/abs/2401.15884 （代码: https://github.com/HuskyInSalt/CRAG）
89. RankRAG: Unifying Context Ranking with RAG in LLMs — 2024 (NeurIPS 2024) — https://papers.nips.cc/paper_files/paper/2024/hash/db93ccb6cf392f352570dd5af0a223d3-Abstract-Conference.html
90. Learning to Filter Context for RAG (FILCO) — 2023 — https://arxiv.org/abs/2311.08377 （代码: https://github.com/zorazrw/filco）
91. Chain-of-Note: Enhancing Robustness in Retrieval-Augmented Language Models — 2023 (EMNLP 2024) — https://arxiv.org/abs/2311.09210
92. RECOMP: Improving Retrieval-Augmented LMs with Compression and Selective Augmentation — 2023 (ICLR 2024) — https://arxiv.org/abs/2310.04408
93. LLMLingua / LongLLMLingua / LLMLingua-2 — 2023–2024 (EMNLP 2023 / ACL 2024) — https://arxiv.org/abs/2310.06839
94. Contextual Compression in RAG for LLMs: A Survey — 2024 — https://arxiv.org/abs/2409.13385
95. FActScore: Fine-grained Atomic Evaluation of Factual Precision — 2023 (EMNLP 2023) — https://arxiv.org/abs/2305.14251 （pip 包 `factscore`）
96. Core: Robust Factual Precision with Informative Sub-Claim Identification（及 WICE / VeriScore / DnDScore）— 2023–2025 — https://arxiv.org/abs/2407.03572
97. Decomposition Dilemmas — 2025 (NAACL 2025) — arXiv 2411.02400 （代码: https://github.com/qishenghu/Decomp_Dilemmas）
98. StructRAG: Inference-time Hybrid Information Structurization — 2024 (ICLR 2025) — https://arxiv.org/abs/2410.08815 （代码: https://github.com/icip-cas/StructRAG）
99. Sufficient Context: A New Lens on RAG Systems — 2024 (ICLR 2025, Google) — https://arxiv.org/abs/2411.06037 （代码: https://github.com/hljoren/sufficientcontext）
100. Speculative RAG: Enhancing RAG through Drafting — 2024 (ICLR 2025) — https://arxiv.org/abs/2407.08223
101. InstructRAG: Instructing RAG via Self-Synthesized Rationales — 2024 (ICLR 2025) — https://arxiv.org/abs/2406.13629
102. SEER: Self-Aligned Evidence Extraction for RAG — 2024 (EMNLP 2024) — https://arxiv.org/abs/2410.11315
103. CARE-RAG: Trustworthy RAG via Conflict-Driven Summarization — 2025 — https://arxiv.org/abs/2507.01281
104. Relevant Is Not Warranted: Evidence-Force Calibration for Cited RAG — 2026 — https://arxiv.org/html/2605.28044
105. FactCG: Enhancing Fact Checkers with Graph-Based Multi-Hop Data — 2025 — https://arxiv.org/abs/2501.17144
106. Reasoning with Graphs (RwG) — 2025 — arXiv 2501.07845
107. GRS-QA（推理结构标注 QA）— 2024 — arXiv 2411.00369

---

**文档使用说明**：§1 的下载路径与协议细节可直接用于搭建评测流水线；§3 的五项对比与 §4 的十二条风险应逐条落实到论文的 Related Work 与 Introduction 措辞中；§5 的基线与指标即实验章节的骨架。本文所有数字与结论均出自调研发现记录，未添加记录之外的论文或数据。