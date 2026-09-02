# 批 33-H2 判决:对手系统 TRACE 同台(60 题 v1 标定场 + WikiState v2.4 全 576)

> 口径:60 题场与其余 16 系统完全同台(同 15 库 / 同 60 题 / 同读者 / 同判官 / 同 k);
> 576 场与 `results/wsc_v2_direct.jsonl`(48.61)、`results/b33B_merged_v24.jsonl`(90.45)同题配对。
> 一切数字为实测,读者/判官栈见 §三。**完成状态:三轮全部跑完并入档。**

## 一、判决先行

**猜想被证实:TRACE 不构成 QVF 的机制威胁,反而给 QVF"查询时判定"主张提供了一条外部代价证据。**

1. 按其 README / 出厂 LongMemEval 预设(**预设 A**),TRACE 在 60 题标定场拿 **16.67**
   (簇自助 95% CI [6.7, 28.3]),在 **v2.4 全 576 拿 15.97**(簇 CI [12.8, 19.3])
   —— 两个考场彼此复现,不是抽样噪声。576 场上低于同题直读 top-10 的 48.61
   (Δ=−32.64pp,簇级符号检验 w/l=7/109,p=1.2e-24,簇自助 CI [−37.2, −28.0]),
   低于 QVF v2.4 头条 90.45(Δ=−74.48pp,簇 w/l=0/140,p=1.4e-42)。
2. 把两处**规模让步**改回其 LoCoMo 预设(**预设 B**:A-Mem 记忆演化开 + Phase 3
   更新检测开)后,60 题场升到 **30.00**(簇 CI [18.3, 41.7]);升幅 +13.33pp
   **统计上不可分**(簇级 w/l=7/4,p=0.549,簇自助 CI [−1.7, +30.0]),
   代价是建库 $ 涨 5.9×、建库时长涨 7.6×。即便如此仍显著低于直读
   (Δ=−21.67pp,簇 p=0.039),与 A-MEM 打平(Δ=−13.33pp,簇 p=0.065)。
3. **机制事实(本轮最硬的一条)**:预设 A 下,60 题场 15 库 / 499 会话 / 3,126 事件,
   以及 576 场 144 库 / 4,862 会话 / **29,845 事件**里,`updates` 边 = **0**,
   `contradicts` 边 = **0** —— 论文头条的"有效性标注"**一次都没触发**,因为其出厂
   LongMemEval 配置写死 `longmemeval_skip_update_detection: true`
   (论文自承在 haystack 规模上 "prohibitive pairwise checks" 而关掉)。
   预设 B 打开后,3,115 个事件上共 19 条 `updates` + 14 条 `contradicts`,
   而这 15 库的**真值状态转换共 34 次** —— 其写入时两两筛检在我们的场上召回不足,
   且每库要付 ~2,030 次 pairwise LLM 调用。

## 二、身份与来源(已核实)

| 项 | 值 |
|---|---|
| 论文 | arXiv:2607.00339,*TRACE: State-Aware Query Processing over Temporal Evidence Graphs for Conversational Data* |
| 代码 | https://github.com/MorinWang/TRACE ,**MIT**,commit `1375df3cef9aa77444f77cbebc3f26e64ba444bb`(2026-08-17) |
| 自称 | 事件→会话→主题分层图 + typed temporal / causal / update / contradiction 边;维持 validity 标注使过期事实"对历史问题仍可取、对当前态问题被折价" |
| 底座 | A-Mem 笔记层(`memory_layer_robust.RobustAgenticMemorySystem`)+ 图引导检索;LLM 默认走 OpenRouter `openai/gpt-4o-mini` |
| 核验点 | `ingest_longmemeval.py` 确实消费 `(sid, session)` 迭代器并调 `add_note(content, time=...)`(与我方验证器所记一致)。因此 WikiState 库可直接转成 LongMemEval 记录格式喂进它原生的 `LongMemEvalAdapter`,**其代码一行未改** |
| 环境 | 隔离 venv `.venv_trace`(py 3.12.10);openai 3.7.0 / sentence-transformers 6.0.1 / torch 2.13.0 / networkx 3.6.1;`anthropic` 钉 **0.121.0**(= 主环境同版;1.3.0 的 `messages.create` 不再收 `temperature`,会静默毁掉读者栈) |

## 三、同台协议(镜像 scripts/repro_batch4.py,逐条可核)

* **题源/库**:60 题场 = `scripts/repro_batch2.py::sample_stores()` 的 15 库 × 4 题,
  `question_id` 为 `_s5a`.._s5d —— 与 Mem0 / LangMem / A-MEM / cognee / txtai /
  lgstore / timeline / BM25 / obs-RAG / 摘要RAG / Graphiti / LightRAG / 盖章台账 /
  Letta 同一批;语料 `data/wikistate_full_P108.json`、`_P39_ext`、`_P54`、`_P551`。
  576 场 = `data/wsc_s5_v2.jsonl`(144 uid × 4 题)+ `data/wikistate_full_ALL_v24.json`。
* **读者**:`claude-haiku-4-5`,temp 0,`max_tokens=300`,`repro_batch2.READER_SYS`
  逐字复用;输入 `MEMORIES:\n<对手检索到的证据>\n\nUSER'S NEW MESSAGE: <题>`。
* **判官**:`qvf.judge.ClaudeJudge`(冻结默认 `claude-opus-5`)。
* **k**:TRACE 自带 `retrieve_k=10`。
* **只取素材不取其自答**:与 cognee / LightRAG / Graphiti 同处理——取
  `TRACEPipeline.retrieve().context`(其 hybrid context = A-Mem 笔记段 +
  因果路径段,路径段自带 `[OUTDATED]` / `[PARTIALLY UPDATED]` 标记),交我方读者。
* **TRACE 侧零复刻**:`ingest_longmemeval.ingest_memories/build_summaries`、
  `build_graph_longmemeval.build_graph`、`eval_locomo.TRACEGraphAgent` +
  `expand_pipeline_config/expand_reasoner_config`、`eval_longmemeval` 的
  `load_longmemeval_memories / make_memory_view / filter_graph_by_note_ids /
  allowed_notes_for_question` 全部原样调用。适配器只做三件事:WikiState→LongMemEval
  记录格式转换、取它的 context、记账。

### 已入档的四处偏离(全部对 TRACE 有利或中性)

1. **端点**:无 OpenRouter key,置 `api_base=None` 走 OpenAI 官方端点,模型仍
   `gpt-4o-mini`(与 A-MEM / cognee / LightRAG 同档)。
2. **喂入量**:其余考生走 `repro_batch4.sess_text()`(每会话前 6 轮 × 每轮截 400 字);
   TRACE 拿到**全部轮次、不截断**。对 TRACE 有利。
3. **turn 解析**:WikiState 的 turn 以 `str(dict)` 存,60 题场 2,446 轮中 1,016 轮
   `ast.literal_eval` 失败(助手长回合内嵌引号),此时按其余考生的既有做法把整段
   dict 字面量当文本喂入;载有链句的 user 轮基本可解析(抽查 CERN / 剑桥链句均正常入 note)。
4. **预设 B 的两个开关**:`skip_evolution=False`(= `ingest_locomo.py` 走的
   `TRACEAgent` 默认)与 `longmemeval_skip_update_detection=False`
   (= `build_graph_locomo.py` 无条件跑的那一段)。**只改构造参数 / 配置键,不改其代码**;
   理由是这两项都是它为 19k 会话 haystack 做的规模让步,在每库 33 会话的场上不必让。
   不跑它就无法排除"你跑的是他们的残血档"这一反驳。

## 四、结果一:60 题 v1 标定场

| 指标 | 预设 A(出厂 LongMemEval 配置) | 预设 B(改回 LoCoMo 预设) |
|---|---|---|
| n / **acc** | 60 / **16.67** | 60 / **30.00** |
| 题级 bootstrap 95% CI | [8.3, 26.7] | [18.3, 41.7] |
| **簇级(15 uid)bootstrap 95% CI** | **[6.7, 28.3]** | **[18.3, 41.7]** |
| 答题延迟中位 | 8.08s(其检索 2.69s) | 7.38s(其检索 1.61s) |
| 读者 in / out 均值 | 2,722 / 84 tok | **11,517** / 84 tok |
| $/题(读者+判官+其查询期 LLM) | $0.00626 | $0.01505 |
| 建库(15 库合计) | $0.5483(in 2,181,794 / out 368,464 / 3,007 调用) | **$3.2264**(in 15,587,568 / out 1,480,405 / **39,988** 调用) |
| 建库耗时中位 | 344.8s/库 | **2,613s/库** |
| **$/题(含建库摊销)** | **$0.01540** | **$0.06883** |
| 按题型 | cc 20.0 / cb 26.7 / fl 13.3 / lt 6.7 | cc 40.0 / cb 46.7 / fl 20.0 / lt 13.3 |
| `updates` / `contradicts` 边 | **0 / 0**(3,126 事件) | 19 / 14(3,115 事件) |
| 读者答"记忆里没有" | **47 / 60** | 25 / 60 |

### 配对比较(同 60 题;题级 = 精确符号检验,簇级 = 15 uid 一票)

| 比较 | Δ | 题级 w/l, p | 簇级 w/l, p | 簇自助 95% CI |
|---|---|---|---|---|
| A − 直读 top-10 (51.67) | **−35.00** | 3/24, 4.9e-05 | 0/14, 1.2e-04 | [−43.3, −26.7] |
| A − A-MEM (43.33) | −26.67 | 5/21, 0.0025 | 0/10, 0.0020 | [−38.3, −15.0] |
| A − timeline (63.33) | −46.67 | 5/33, 4.3e-06 | 1/13, 0.0018 | [−63.3, −30.0] |
| A − QVF smoc (86.67) | **−70.00** | 1/43, 5.1e-12 | 0/15, 6.1e-05 | [−81.7, −56.7] |
| B − 直读 top-10 | −21.67 | 7/20, 0.019 | 2/10, 0.039 | [−35.0, −8.3] |
| B − A-MEM | −13.33 | 8/16, 0.152 | 2/9, 0.065 | [−25.0, +0.0] |
| B − timeline | −33.33 | 7/27, 8.2e-04 | 1/11, 0.0063 | [−50.0, −16.7] |
| B − QVF smoc | **−56.67** | 3/37, 1.9e-08 | 0/13, 2.4e-04 | [−71.7, −41.7] |
| **B − A(同系统两预设)** | **+13.33** | 14/6, 0.115 | 7/4, **0.549** | **[−1.7, +30.0]** |

> 同场对照文件:QVF smoc = `results/wsc_s5_smoc_v42v.jsonl`,在这 60 题上实测 **86.67**
> (协调方口传的 85.00 与文件不符,以文件为准);直读 =
> `results/wsc_direct_s5_all_b1_union.jsonl` 的 60 题子集 **51.67**
> (与 `results/sys16_bootstrap_ci_20260829.md` 所记 51.7 一致)。

### 60 题标定场名次(插入既有 16 系统表)

timeline 63.3 > Letta 56.7 > lgstore 55.0 > txtai 53.3 > **直读 51.7** > cognee 46.7 =
摘要RAG 46.7 > A-MEM 43.3 > LangMem 40.0 > **TRACE(预设 B)30.0** > Mem0 26.7 >
**TRACE(预设 A)16.7** > obs-RAG 13.3 = BM25 13.3 > 盖章台账 11.7 > Graphiti† 3.3 >
LightRAG† 1.7。(QVF smoc 86.7 为我方臂,不入对手表。)
相邻名次不作主张——CI 互相覆盖;可陈述的是 TRACE 两个预设都落在**直读带以下**。

## 五、结果二:WikiState v2.4 全 576(预设 A)

| 指标 | TRACE(预设 A) | 直读 top-10 | QVF smoc v2.4 头条 |
|---|---|---|---|
| 文件 | `results/wsc_s5_trace_v24.jsonl` | `results/wsc_v2_direct.jsonl` | `results/b33B_merged_v24.jsonl` |
| n / **acc** | 576 / **15.97** | 576 / 48.61 | 576 / 90.45 |
| 题级 bootstrap 95% CI | [13.0, 18.9] | [44.4, 52.8] | [87.8, 92.7] |
| **簇级(144 uid)CI** | **[12.8, 19.3]** | [44.3, 53.0] | [87.2, 93.4] |
| 答题延迟中位 | 7.02s(其检索 1.71s) | 5.51s | 4.95s |
| 读者 in / out 均值 | 2,696 / 82 tok | 884 / 86 tok | 2,950 / 479 tok |
| $/题(答题) | $0.00623 | $0.00439 | $0.00842 |
| 建库(144 库) | **$5.2433**(in 20,913,998 / out 3,510,335 / 29,333 调用) | $0 | $0(账目另计) |
| 建库耗时中位 | 359.4s/库 | — | — |
| **$/题(含建库摊销)** | **$0.01533** | $0.00439 | $0.00842 |
| 按题型 | cc 11.8 / cb 11.1 / fl 23.6 / lt 17.4 | cc 35.4 / cb 44.4 / fl 77.8 / lt 36.8 | cc 88.2 / cb 88.9 / fl 96.5 / lt 88.2 |
| `updates` / `contradicts` 边 | **0 / 0**(29,845 事件 / 4,862 会话) | — | — |
| 读者答"记忆里没有" | **312 / 576** | — | — |

| 配对比较(同 576 题) | Δ | 题级 w/l, p | 簇级 w/l, p | 簇自助 95% CI |
|---|---|---|---|---|
| TRACE − 直读 top-10 | **−32.64** | 23/211, 3.2e-39 | 7/109, 1.2e-24 | [−37.2, −28.0] |
| TRACE − QVF smoc(90.45) | **−74.48** | 5/434, 1.9e-121 | 0/140, 1.4e-42 | [−78.5, −70.3] |

数据完整性:576 行 / 576 个不重复 `question_id` / 144 库 / **0 条检索异常** / 0 缺 0 多。
60 题场的 16.67 与 576 场的 15.97 CI 高度重叠 —— **标定场对全场是保真的**。

### 失败形态(逐条实测,非推测)

* **预设 A:上下文不缺量,缺命中。** 60 题场中位 10.2K 字符 ≈ 2,722 读者输入 tok,
  576 场中位 10.3K 字符 ≈ 2,696 tok(都比 txtai / lgstore 的 ~1.2K 更宽),
  但 60 题里 47 题、576 题里 312 题读者回"记忆里没有相关信息"。两处根因:
  (a) 其 LongMemEval 入口硬编码 `skip_evolution=True`,note 的
  `context/keywords/tags` 全空,MiniLM 索引文本退化成裸单轮文本,对
  "employer / longest / tenure" 类聚合问句几乎检索不到那条链句;
  (b) 图侧证据来自**会话摘要**,抽查一库 34 条摘要只有 2 条保留了雇主事实
  —— 摘要期就把状态变更丢了,于是该库 195 个事件里 **0 个**与雇主相关。
* **预设 B:证据量暴涨,判读仍不达标。** 上下文中位 45.7K 字符
  ≈ 11,517 读者输入 tok(比整库全文裸读的 13.7K 只低一档),"没有信息"降到
  25/60,acc 升到 30.0 —— 但仍低于只喂 926 tok 的直读臂。
  证据**找回来了、没被判对**,与 QVF"读侧判读才是瓶颈"的结论同向。
* **有效性标注的实际覆盖面**:预设 B 的 3,115 个事件里只有 19 个被写 `valid_until`
  (0.6%),而真值状态转换有 34 次。`[OUTDATED]` 标记只能出现在 hybrid context 的
  第二段(因果路径段),其上限就是这 19 个事件。

## 六、新颖性撞车说明(TRACE 主张 vs QVF 主张)

TRACE 与 QVF 在**词面上**撞得很近:它自称 "state-aware query processing",
维持 validity 标注使过期事实"对历史问题仍可取、对当前态问题被折价",
这几乎是 QVF 第①条主张(`valid: S×Q` 形式化 + 查询时判定)的自然语言复述。
但**机制层面并未撞车,反而正好落在我们那条分界轴的对面**:TRACE 的有效性是
`v(e) ∈ {0, 0.5, 1}` 的**事件级标量**,由离线建图阶段的 Phase 3 两两 LLM 判定
一次性写死(论文 Eq. 11–12:`u(e_o)=a(e_n), v(e_o)=0`,再沿 causes/enables 边
把下游降到 0.5),查询期只是把这个**与查询无关**的标量当作路径打分的惩罚项来消费
—— 即"**写入时盖章、查询时消费**",与 Mem0 / MemStrata 式台账同族,
差别只在它保留旧节点而不删除。QVF 的 `valid: S×Q` 则是(陈述 × 查询)的二元函数:
同一条"2003 年入职 CERN"对"我现在在哪上班"判 superseded、对"2005 年前我有几个雇主"
判 in-scope,标签随查询翻转,这在 TRACE 的数据结构里**没有位置可放**。
本轮还测出这条分界轴的三个可报价后果:(i) TRACE 的写入时判定在其自家出厂
LongMemEval 配置下被**整体关闭**(两个考场合计 32,971 个事件上 0 条 updates /
0 条 contradicts),论文自承原因是 haystack 规模上 pairwise 检查代价过高
—— 写入时判定的复杂度随**库**增长,查询时判定只随**检索集**增长;
(ii) 打开后每库要付 ~2,030 次 pairwise LLM 调用、建库 $ 涨 5.9×、时长涨 7.6×,
换来的 +13.33pp 统计上不可分;(iii) 真值 34 次状态转换只被认出 19 条,
写入时一次性判定的漏检**无法在查询期补救**,而 QVF 的账目在查询期重新裁决,
同一份证据可被不同查询重新用。结论:TRACE 不是"别人也做了 S×Q",
而是"别人做了 S 上的一次性盖章、并在自家规模上被迫关掉它"——这恰好是我方
第①条主张的外部代价证据,应作为**对照臂**引用,不改我方叙事主轴
(见 memory: preserve-own-innovation)。

## 七、精确复现命令

```bash
# 环境(隔离)
py -3.12 -m venv .venv_trace
.venv_trace/Scripts/python.exe -m pip install bert-score networkx nltk numpy openai \
    rouge-score scikit-learn sentence-transformers tiktoken tqdm python-dotenv \
    rank_bm25 pydantic "anthropic==0.121.0"
git clone https://github.com/MorinWang/TRACE.git <TRACE_REPO>   # commit 1375df3c

# 预设 A(出厂 LongMemEval 配置),60 题场,4 分片:
for s in 0 1 2 3; do
  PYTHONUTF8=1 TRACE_REPO=<TRACE_REPO> .venv_trace/Scripts/python.exe \
    scripts/trace_contestant.py --shard $s --nshards 4 --out-suffix _sh$s \
    --store-root D:/ZZL_cluade/results/trace_stores/trace_v1 &
done
cat results/wsc_s5_trace_sh{0,1,2,3}.jsonl > results/wsc_s5_trace.jsonl

# 预设 B(改回 LoCoMo 预设):同上加 --evolution --update-detection,
#   --out-suffix _evoupd_sh$s --store-root .../trace_v1_evoupd
cat results/wsc_s5_trace_evoupd_sh{0,1,2,3}.jsonl > results/wsc_s5_trace_evoupd.jsonl

# v2.4 全 576(预设 A;逐题续跑,已落盘 question_id 自动跳过):
for s in 0 1 2 3; do
  PYTHONUTF8=1 TRACE_REPO=<TRACE_REPO> .venv_trace/Scripts/python.exe \
    scripts/trace_contestant.py --shard $s --nshards 4 \
    --questions data/wsc_s5_v2.jsonl --vols data/wikistate_full_ALL_v24.json \
    --all-uids --out-suffix _v24_sh$s \
    --store-root D:/ZZL_cluade/results/trace_stores/trace_v24 &
done
cat results/wsc_s5_trace_v24_sh{0,1,2,3}.jsonl > results/wsc_s5_trace_v24.jsonl

# 统计($0,可重复):
PYTHONUTF8=1 python scripts/trace_verdict_stats.py results/wsc_s5_trace_v24.jsonl \
  --label "TRACE(LME出厂预设) v2.4-576" \
  --vs "直读top10=results/wsc_v2_direct.jsonl" \
  --vs "QVF smoc v2.4头条=results/b33B_merged_v24.jsonl" --restrict-to-main
```

价格口径(项目既用):haiku-4-5 读者 $1.00/M in、$5.00/M out;opus-5 判官
$5.00/M in、$25.00/M out 且按 `results/judge_cost_measured_20260816.md` 实测均值
198.28 / 83.45 tok 计(判官不落盘 usage);gpt-4o-mini $0.15/M in、$0.60/M out。

## 八、成本

| 项 | 实测 $ |
|---|---|
| 预设 A,60 题(建库 $0.5483 + 答题 60×$0.00626) | $0.924 |
| 预设 B,60 题(建库 $3.2264 + 答题 60×$0.01505) | $4.129 |
| 预设 A,v2.4 576(建库 $5.2433 + 答题 576×$0.00623) | $8.831 |
| 单库冒烟(1 库 4 题) | ≈$0.05 |
| **合计** | **≈$13.93 / 上限 $30** |

576 场的增量 = $8.83 < $15 的门槛,故按任务书条件执行。
预设 B 若上 576 需 ≈$40 且 ~26 机时,**超上限,未跑**,已入档为不做项。

## 九、事故与偏差记录(honest log)

1. **`anthropic` 版本陷阱**:`.venv_trace` 里 pip 默认装 1.3.0,其
   `Messages.create()` 不再接受 `temperature`,读者三次重试全部 `TypeError`
   → 答案空串 → 冒烟 0/4。钉回主环境同版 0.121.0 后正常。
   教训:同台跑对手必须把**读者/判官栈的库版本**一起冻结,不只是模型名。
2. **协调方两次基于错误前提的指令,已核实驳回**:
   (a) 称"预设 B 各分片有重启产生的重复行、shard 3 卡在 12/15"——实测
   `results/wsc_s5_trace_evoupd_*.jsonl` 合计 60 行 / **60 个不重复 id** /
   0 重复 / 0 缺失,15 库全覆盖;shard 3 只被分到 15 库中的 3 库(索引 3/7/11),
   12 行即其满额,从未重启。
   (b) 称"跑手被 harness 回收"——实测 4 个进程始终存活,分片 0/2/3 是**跑完自然退出**。
   两次均未按错误前提做"修复",避免了重复行污染。
3. **协调方口传的 smoc = 85.00 与文件不符**,`results/wsc_s5_smoc_v42v.jsonl`
   在该 60 题上实测 86.67,本文件一律以落盘文件为准。
4. **TRACE 的 turn 解析失败率 41.5%**(1,016/2,446)已在 §三 偏离 3 记录;
   其失败集中在助手长回合,载链句的 user 轮基本可解析,且其余考生看到的是
   同样的 `str(dict)` 文本(还额外被截断),故不构成对 TRACE 的不利偏置。

## 十、文件清单

| 文件 | 内容 |
|---|---|
| `scripts/trace_contestant.py` | TRACE 考生适配器(新增) |
| `scripts/trace_verdict_stats.py` | acc / 双层 bootstrap CI / $ / 延迟 / 配对检验(新增,$0) |
| `results/wsc_s5_trace.jsonl` | 预设 A,60 题逐题记录(合并自 `_sh0..3`) |
| `results/wsc_s5_trace_evoupd.jsonl` | 预设 B,60 题逐题记录(合并自 `_evoupd_sh0..3`) |
| `results/wsc_s5_trace_v24.jsonl` | 预设 A,v2.4 576 逐题记录(合并自 `_v24_sh0..3`) |
| `results/wsc_s5_trace_sh[0-3].jsonl` / `_evoupd_sh[0-3]` / `_v24_sh[0-3]` | 分片原件 |
| `results/trace_stores/trace_v1/<uid>/` | 预设 A 每库产物:`memories/`(note pkl + MiniLM 索引)、`summaries/`、`graphs/event_graph_longmemeval_global.json`(含 `metadata.stats`,可复核 updates/contradicts 计数) |
| `results/trace_stores/trace_v1_evoupd/<uid>/` | 预设 B 同上 |
| `results/trace_stores/trace_v24/<uid>/` | v2.4 576 的 144 库同上 |
| `results/_trace_v1_sh[0-3].log` / `_trace_evoupd_sh[0-3].log` / `_trace_v24_sh[0-3].log` | 跑日志(逐次 LLM 调用可数) |

---
**状态行(2026-09-03 00:50)**:60 题标定场两预设 + v2.4 全 576 **三轮全部完成并入档**;
预设 B 上 576 超预算,未跑。未提交 git(按任务书:no git commit/add/push)。
