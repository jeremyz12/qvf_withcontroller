# 批 33-H1 判决:HippoRAG 2 同台 —— **跑通,55.00 分,与直读打平,离 QVF 差 33.3pp**

**状态:COMPLETED**(官方 pip 包跑通,零复刻,60/60 题全部产出,零报错、零空答)

**头条判决**:
1. **"图记忆能靠更好的检索赢下 WikiState"这一猜想被否定。** HippoRAG 2 在 60 题标定场取 **55.00**(60 题自助 95% CI **[41.7, 68.3]**;15 实体簇自助 CI **[45.0, 65.0]**),与直读 top-10 的 51.67 **配对无差异**(+3.33pp,簇 CI [−11.7, +20.0],McNemar 精确 p=0.85),与 txtai 53.33 / lgstore 55.00 同档,低于 timeline 63.33。
2. **但它确实赢下了"检索"这个子问题——而且赢得很明显。** 事后诊断(不重建索引,重放同 60 个 query)显示 HippoRAG 2 的 top-10 **平均召回 91.5% 的链状态,85.0%(51/60)的题把整条状态链完整送进读者上下文**;同题同金标下,直读 top-10(轮级)只有 **76.9% / 55.0%**。
3. **判决式结论:瓶颈不在"取回来",在"取回来之后怎么裁"。** 在那 51 道**整条链都已在上下文里**的题上,HippoRAG 2 仍然只有 **56.86**;其中 `change_count` 只有 **2/15 = 13.3**,失败形态是逐字可查的裁决错误——它把四个雇主全列对了,却答"换了 4 次"(金标 3,首值不算一次变更)。这正是 QVF 主张的读时状态裁决层;同一考场同一读者的 QVF smoc 拿 **88.33**,配对 **+33.33pp**(簇 CI [+16.7, +48.3],McNemar 精确 **p=8.8e-05**)。
4. **不是"抽取模型太便宜"的伪影。** 其自带的 recognition-memory 事实闸在 **41.7%(25/60)** 的题上筛剩零事实、直接回落稠密检索;把该闸的 LLM 从 gpt-4o-mini 换成 **gpt-4o**,回退率 45.0%、总分 53.33,与默认 **配对 p=1.0 打平**(§3.6)。

成本:**约 $1.80**(见 §五完整分账),远低于 $60 上限。

---

## 一、考生身份与安装(可复核)

| 项 | 值 |
|---|---|
| 系统 | HippoRAG 2(ICML 2025,OSU-NLP-Group/HippoRAG) |
| 包 | `hipporag==2.0.0a3`(PyPI 官方发布,Home-page 即该 GitHub 仓库) |
| 环境 | **隔离 venv `D:\ZZL_cluade\.venv_hipporag`(Python 3.12.10)**,未污染项目环境 |
| 抽取/重排 LLM | **`gpt-4o-mini`** —— `BaseConfig.llm_name` 的**出厂默认值**,亦即 README 快速开始示例里的 `llm_model_name` |
| 嵌入 | **`text-embedding-3-small`** —— README 快速开始示例里的 `embedding_model_name`,包内 `_get_embedding_model_class` 的官方 `OpenAIEmbeddingModel` 分支 |
| OpenIE 模式 | `online`(BaseConfig 默认;`offline` 需 vllm,见 §四) |
| 检索 | `retrieval_top_k=10`,`linking_top_k`/`passage_node_weight` 等全部保持默认 |

安装命令(实际执行):

```bash
py -3.12 -m venv .venv_hipporag
uv pip install --python .venv_hipporag/Scripts/python.exe --index-strategy unsafe-best-match hipporag
uv pip install --python .venv_hipporag/Scripts/python.exe "anthropic==0.121.0" python-dotenv rank_bm25
```

`anthropic` 钉死 **0.121.0**,与项目环境同版本——venv 默认装到的 1.3.0 已移除 `messages.create(temperature=...)`,会让读者调用整体失败(第一次冒烟 4/4 空答,已定位并修复,该批冒烟数据已删)。

**未选 `nvidia/NV-Embed-v2`(BaseConfig 的字段默认)的理由**:那是 7B 本地模型(约 14GB fp16),本机 RTX 5080 16GB 不保险;且 README 快速开始给的就是 `text-embedding-3-small`,同时与本项目 direct 臂 / lgstore / sumrag 同款嵌入器,口径可比。此项如实记录为配置选择,不是缺省偏离。

---

## 二、同台协议(与其余 16 系统逐字一致)

考场 = **v1 60 题标定场**,由 `scripts/repro_batch2.py::sample_stores()` 定义:从 `results/wsc_s5_filter_only.jsonl`(418 题)按 uid 排序等距抽 **15 个实体库**,每库 4 题(`_s5a` 最长任期 / `_s5b` 变更次数 / `_s5c` 某日前计数 / `_s5d` 首末雇主)= **60 题**。语料卷 = `data/wikistate_full_{P108,P39_ext,P54,P551}.json`。

镜像 `scripts/repro_batch4.py`(txtai / lgstore / bm25 / cognee / graphiti / lightrag 的同一 harness)的每一环:

| 环节 | 做法(与 repro_batch4 逐字相同) |
|---|---|
| 段落化 | `sess_text(s) = "(session date: {date})\n" + "\n".join(str(t)[:400] for t in turns[:6])` —— **日期逐字前缀** |
| 摄入 | 会话按 `date` 升序、逐条 `index(docs)`;**每条目一座全新的 save_dir**,库间零共享 |
| 检索 | 每题 `retrieve(queries=[q], num_to_retrieve=10)` |
| 记忆行 | `f"- {passage[:400]}"`(**16 系统一律 400 字符截断**;另设不截断对照臂,见 §三.3) |
| 读者 | `claude-haiku-4-5`,`max_tokens=300`,`temperature=0`,`READER_SYS` 取自 `repro_batch2`,消息体 `"MEMORIES:\n{...}\n\nUSER'S NEW MESSAGE: {q}"` |
| 判官 | `qvf.judge.ClaudeJudge()` 默认档 = **claude-opus-5**(冻结判官,与全部同台系统同一实例配置) |
| 延迟口径 | `latency_s` 自检索前计到判官返回后,与榜单其余行同一约定 |

跑批命令:

```bash
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv_hipporag/Scripts/python.exe \
  scripts/hipporag2_baseline.py > results/_h1_hipporag_run.log 2>&1
```

并行:**条目级串行(=1)**;HippoRAG 内部 OpenIE 的 `ThreadPoolExecutor()` 默认 `min(32, cpu+4)` 被压到 **max_workers=4**(纯并发上限,逐段落独立,不改抽取结果)。

---

## 三、结果

### 3.1 榜单同格式行(可直接并入 `results/wikistate_leaderboard_20260828.md` 的"16 系统同台"节)

| 系统/臂 | n | acc | in-tok | out-tok | 延迟中位 | 建库 | 注 |
|---|---|---|---|---|---|---|---|
| **HippoRAG 2** | 60 | **55.00** | 1177 | 85 | 6.15s | **34.3s/题目库(=8.6s/题)** | gpt-4o-mini OpenIE + text-embedding-3-small;95% CI [41.7, 68.3] |

> 建库口径说明:榜单既有行写的是"s/题"。本系统 **15 座库共 515s**,即 **34.3s/条目库**、**8.6s/题**。对照:cognee 30.5s/题、txtai 6.6s/题、Mem0 131.2s/题、Graphiti 280.2s/题。
> 延迟 6.15s **含判官**(与榜单同约定);纯"检索+读者"中位 **2.97s**(检索 1.24s + 读者 1.73s)。

### 3.2 自助 CI(与 `results/sys16_bootstrap_ci_20260829.md` 同格式)

| 系统 | n | acc | 95% CI(题级自助) | 95% CI(15 实体簇自助) |
|---|---|---|---|---|
| **HippoRAG 2** | 60 | **55.0** | **[41.7, 68.3]** | **[45.0, 65.0]** |

自助代码用同法复算了已发表的四行做校验:txtai [40.0,66.7] vs 存档 [41.7,65.0]、Mem0 [16.7,38.3] vs [15.0,38.3]、timeline [51.7,75.0] vs [50.0,75.0]、lgstore [43.3,66.7] vs [43.3,68.3] —— 差异 ≤1 个自助网格步(1/60=1.67pp),仅随机种子不同,**方法与口径一致**。

### 3.3 配对比较(同 60 题按 question_id 对齐;簇 = 15 个 WikiState 实体)

| 对照 | Δacc | 簇自助 95% CI | McNemar 精确 p | 胜/负 |
|---|---|---|---|---|
| vs **直读 top-10**(51.67) | **+3.33** | [−11.7, +20.0] | 0.851 | 15 / 13 |
| vs **txtai**(53.33) | +1.67 | [−10.0, +13.3] | 1.0 | 10 / 9 |
| vs **lgstore**(55.00) | 0.00 | [−10.0, +10.0] | 1.0 | 4 / 4 |
| vs **timeline**(63.33) | −8.33 | [−21.7, +5.0] | 0.383 | 8 / 13 |
| vs **cognee**(46.67) | +8.33 | [−10.0, +26.7] | 0.383 | 13 / 8 |
| vs **A-MEM**(43.33) | +11.67 | [+1.7, +23.3] | 0.248 | 17 / 10 |
| vs **Mem0**(26.67) | **+28.33** | [+13.3, +41.7] | **0.0033** | 24 / 7 |
| vs **QVF smoc**(88.33) | **−33.33** | [−48.3, −16.7] | **8.8e-05** | 3 / 23 |

判读:HippoRAG 2 稳稳压过写时合并类产品(Mem0),与本地/托管稠密 RAG(txtai / lgstore / 直读)**同档不可分**,**未**跑赢时间线组织(timeline),与 QVF 账目读法差距 **CI 完全不跨零**。

### 3.4 分题型(同 60 题,横向对照)

| 系统 | change_count | count_before | first_vs_last | longest_tenure | 总 |
|---|---|---|---|---|---|
| **HippoRAG 2** | **2/15 = 13.3** | 8/15 = 53.3 | **15/15 = 100.0** | 8/15 = 53.3 | 55.0 |
| HippoRAG 2(不截断) | 3/15 = 20.0 | 10/15 = 66.7 | 15/15 = 100.0 | 6/15 = 40.0 | 56.7 |
| 直读 top-10 | 8/15 = 53.3 | 8/15 = 53.3 | 9/15 = 60.0 | 6/15 = 40.0 | 51.7 |
| txtai | 4/15 = 26.7 | 5/15 = 33.3 | 15/15 = 100.0 | 8/15 = 53.3 | 53.3 |
| timeline | 8/15 = 53.3 | 8/15 = 53.3 | 15/15 = 100.0 | 7/15 = 46.7 | 63.3 |
| **QVF smoc** | 12/15 = 80.0 | 14/15 = 93.3 | 13/15 = 86.7 | 14/15 = 93.3 | 88.3 |

**HippoRAG 2 在 `first_vs_last` 上满分 15/15**(与 timeline、txtai 并列全场最高)——图检索确实把"首状态"和"末状态"两头都稳稳拉进上下文;**同时它的 `change_count` 是全部 13 个总分 ≥40 的系统里最低的一个(2/15,下一低是 lgstore 3/15、txtai 4/15,直读 8/15)**,只有已判"集成问题"或"机制天花板"的一档(obs-RAG / mstrata / Graphiti 各 0,BM25 / LightRAG 各 1)比它更低。两件事同时为真,正是 §3.5 的诊断。

### 3.5 决定性诊断:检索赢了,裁决输了

事后重放(`scripts/hipporag2_retrieval_diag.py`,复用已建的 15 座库、**不重建索引**,重跑同 60 个 query,把 top-10 段落首行的 `(session date: …)` 与该实体 `chain[].date` 逐字比对):

| 指标 | HippoRAG 2 | 直读 top-10(轮级) |
|---|---|---|
| 链状态平均召回@10 | **0.915** | 0.769 |
| 整条链完整进上下文的题 | **51/60 = 85.0%** | 33/60 = 55.0% |

**然后**:在那 51 道整条链都已在读者眼前的题上,HippoRAG 2 的准确度是 **56.86**(不截断臂同为 56.86),其中 `change_count` **2/15 = 13.3**。逐字失败样本(两条,均 `chain_recall = 1.0`):

```
wikiP108000-Q59200022_s5b  金标 3
问:(Today is 1998-09-01.) How many times did I change my employer?
答:"...changed employers **4 times**: Caltech in 1985, then CERN in 1989,
    then Cambridge in 1995, and most recently Birmingham ... today (1998)"
判官:把首个雇主也算成了一次变更

wikiP108011-Q42430132_s5b  金标 2
答:"...changed employers **3 times**: Manchester in 1970, Shell in 1976,
    and just joined the Indian Institute of Petroleum today in 1984"
判官:同一错型
```

四个状态一个不落地列对了,却把"状态个数"当成了"变更次数"。**证据齐备而裁决失败**——这不是记忆系统的召回问题,是读时状态代数问题。同一考场、同一读者模型、同一判官下 QVF smoc 在 `change_count` 拿 12/15,差距来自账目读法给出的显式取代链,而不是来自更强的检索。

### 3.6 第二处诊断:它自己的"recognition memory"闸在这套语料上几乎全关

HippoRAG 2 的检索链是 事实检索 → **recognition memory 重排(DSPyFilter,LLM 逐题筛事实)** → PPR;若重排后**零事实**,官方代码 `HippoRAG.py:413-415` 直接回落到纯稠密段落检索(DPR)。补测(patch `rerank_facts` 计数,复用已建店、重排 LLM 走缓存,零新增成本):

| 重排 LLM | 零事实回退 | 平均保留事实数(候选 `linking_top_k=5`) | 该臂总分 |
|---|---|---|---|
| **gpt-4o-mini(README 默认)** | **25/60 = 41.7%** | 1.07 | **55.00** |
| gpt-4o(诊断臂,非默认) | 27/60 = 45.0% | 1.00 | 53.33(配对 McNemar **p=1.0**,4o 赢 2 / 默认赢 3) |

即:**在四成题上,HippoRAG 2 实际退化成了稠密段落检索**;而把这个闸的 LLM 从 gpt-4o-mini 换成 gpt-4o **既没救回回退率、也没动分数**,说明这不是"抽取/筛选模型太便宜"的伪影,而是其默认事实闸对"时序聚合型提问"本身判为不相关。

分开看两半(默认臂):

| 子集 | n | acc | 链状态召回@10 |
|---|---|---|---|
| 走了图检索(PPR) | 35 | **68.6** | 0.943 |
| 回落 DPR | 25 | **36.0** | 0.876 |

两半的链召回差距很小(0.943 vs 0.876),分数差 32.6pp —— 图检索这一段是有价值的;但它只在 58% 的题上被触发,且触发后仍解不开 `change_count`(见 §3.5)。

> 更正留痕:本文件初稿曾据日志无 `"No facts found after reranking"` 字样写"零 DPR 回退"。该判断**错误**——`hipporag/utils/logging_utils.py` 的 `get_logger` 不挂任何 handler,`logger.info` 全被根 logger 的 lastResort(WARNING 级)吞掉,日志缺席不构成证据。上表是打开 INFO 后逐题计数复测的结果(`results/_h1_hipporag_fallback.log` 里可见 25 条 `No facts found after reranking, return DPR results`)。

### 3.7 稳健性:400 字符截断不是它输的原因(两条独立证据)

1. **构造性证据**:该 15 库共 49 个链状态,其金句 `state_span` 在 400 字符截断后仍**逐字保留 48/49(98.0%)**(段落平均 725 字符,状态句几乎总落在首轮)。
2. **实验证据**:复用同一批库、**同一次检索结果**、只把记忆行从 `passage[:400]` 换成完整段落(读者入 token 1177 → 3673,+212%),准确度 **55.00 → 56.67**,配对 **+1.67pp,McNemar p=1.0**(不截断赢 7 / 截断赢 6)。命令:

```bash
./.venv_hipporag/Scripts/python.exe scripts/hipporag2_baseline.py \
  --reuse-store --no-truncate --out-suffix _nt
```

---

## 四、跑通过程中的两处环境垫片(均不触碰 HippoRAG 算法)

两处都只在 `scripts/hipporag2_baseline.py` 的 import 期生效,**OpenIE / 同义边 / 事实检索 / recognition-memory 重排 / PPR 全部走官方包代码,一行未改、一行未复刻**:

1. **`vllm` 打桩**。`hipporag/HippoRAG.py:24` 无条件 `from .information_extraction.openie_vllm_offline import VLLMOfflineOpenIE` → `from vllm import SamplingParams, LLM` → `vllm/utils.py:15 import resource`(POSIX-only)→ Windows 上 `ModuleNotFoundError: No module named 'resource'`。我们跑的是 `openie_mode="online"`,全程不进这条路径,故在 `sys.modules` 里放一个空的 `vllm` 模块。
2. **`multiprocessing.Manager` 打桩**。`hipporag/embedding_model/base.py:225`(`class EmbeddingCache` 的**类体**内)执行 `multiprocessing.Manager()`;在 Windows + Store Python 的 venv 里,这次 spawn 拉起的是 `WindowsApps\...\python3.12.exe`(不带本 venv 的 site-packages),父进程等待管理器连接**永久挂死**(首次尝试 12 分钟零输出,已定位并 kill)。该 `EmbeddingCache` 类**全包 grep 只有定义处一行、零引用点**,是死代码,故用同接口的本地假对象顶替。

两处均在本文件 docstring 与代码注释中留痕。

---

## 五、成本与时间(按实测 token 折算,非估算)

| 项 | 模型 | in-tok | out-tok | USD |
|---|---|---|---|---|
| 建库 OpenIE(15 库 / 499 段落 / **998** 次 LLM 调用 = NER + 三元组抽取各一遍) | gpt-4o-mini | 669,651 | 105,560 | 0.1637 |
| 建库嵌入 | text-embedding-3-small | 283,907 | — | 0.0057 |
| 查询期 recognition-memory 重排(60 次) | gpt-4o-mini | 169,878 | 1,920 | 0.0267 |
| 查询期嵌入 | text-embedding-3-small | 2,430 | — | ~0.0000 |
| 读者(60 题) | claude-haiku-4-5 | 70,643 | 5,089 | 0.0961 |
| 判官(60 题) | claude-opus-5 | 11,380 | 6,800 | 0.2269 |
| **主跑合计** | | | | **0.519** |
| 不截断对照臂(读者 + 判官;检索复用,LLM 全缓存命中) | | 231,987 | 12,090 | 0.476 |
| gpt-4o 重排诊断臂(重排 169,878/2,000 @gpt-4o + 读者 70,600/5,003 + 判官 11,295/7,019) | | 251,773 | 14,022 | 0.772 |
| 检索/回退诊断重放 ×3(LLM 全缓存命中,只付 query 嵌入) | | ~7,300 | — | ~0.000 |
| 冒烟 1 库(anthropic 版本问题那一次,jsonl 已删,故此行为**按已打印的建库/判官计数复算、查询期按 4 题均值外推**,标为约值) | | ≈57,400 | ≈8,530 | ≈0.029 |
| **总计** | | | | **≈ $1.80** |

- $/题(不含判官):**$0.0049**;仅查询期(不摊建库):**$0.0020**。
- 建库墙钟:**515s / 15 库 = 34.3s 每条目库**(33.3 段落/库,均值 374 三元组、381 短语节点)。
- 每题延迟中位:**6.15s**(含判官)/ **2.97s**(检索 1.24s + 读者 1.73s)。
- 落盘店体积:`results/hipporag_stores/` 共 **149MB**(15 库)。

---

## 六、产物文件

| 文件 | 内容 |
|---|---|
| `D:\ZZL_cluade\scripts\hipporag2_baseline.py` | 考生跑批器(镜像 repro_batch4 协议) |
| `D:\ZZL_cluade\scripts\hipporag2_report.py` | 汇总:acc / CI / 成本 / 配对 McNemar + 簇自助 |
| `D:\ZZL_cluade\scripts\hipporag2_retrieval_diag.py` | 事后检索诊断:top-10 链状态召回(不重建索引) |
| `D:\ZZL_cluade\scripts\hipporag2_rerank_diag.py` | 事后事实闸诊断:逐题保留事实数 / DPR 回退计数 |
| `D:\ZZL_cluade\results\wsc_s5_hipporag2.jsonl` | **主结果 60 行**(逐题答案 / 判官理由 / 逐题 token / 图统计) |
| `D:\ZZL_cluade\results\wsc_s5_hipporag2_nt.jsonl` | 不截断对照臂 60 行 |
| `D:\ZZL_cluade\results\wsc_s5_hipporag2_rr4o.jsonl` | gpt-4o 重排诊断臂 60 行 |
| `D:\ZZL_cluade\results\b33_H1_hipporag2_retrieval_diag.jsonl` | 60 题链召回诊断 |
| `D:\ZZL_cluade\results\b33_H1_hipporag2_rerank_diag.jsonl` / `..._gpt4o.jsonl` | 60 题事实闸保留数(默认 / gpt-4o) |
| `D:\ZZL_cluade\results\_h1_hipporag_run.log` / `_h1_hipporag_nt.log` / `_h1_hipporag_rr4o.log` / `_h1_hipporag_diag.log` / `_h1_hipporag_fallback.log` | 五份跑批与诊断全日志(零 Traceback;`_fallback.log` 含 25 条 DPR 回退记录) |
| `D:\ZZL_cluade\results\hipporag_stores\<uid>\` | 15 座 per-item 店(OpenIE 结果 / 三套嵌入 parquet / igraph / LLM 缓存) |
| `D:\ZZL_cluade\.venv_hipporag\` | 隔离环境(hipporag 2.0.0a3) |

**⚠ 提交前必看**:`.venv_hipporag/`(**2.3GB**)与 `results/hipporag_stores/`(**149MB**)当前**均未被 `.gitignore` 覆盖**,`git status` 会把它们列为未跟踪。本轮按纪律**未执行任何 git 操作**;由主会话统一提交时,请先在 `.gitignore` 追加:

```
.venv_hipporag/
results/hipporag_stores/
```

(店目录可由 `scripts/hipporag2_baseline.py` 用约 $0.17、9 分钟重建;jsonl 结果与日志体积很小,应当入库。)

复现三条命令:

```bash
./.venv_hipporag/Scripts/python.exe scripts/hipporag2_baseline.py
./.venv_hipporag/Scripts/python.exe scripts/hipporag2_baseline.py --reuse-store --no-truncate --out-suffix _nt
./.venv_hipporag/Scripts/python.exe scripts/hipporag2_baseline.py --reuse-store --rerank-llm gpt-4o --out-suffix _rr4o
./.venv_hipporag/Scripts/python.exe scripts/hipporag2_retrieval_diag.py
python scripts/hipporag2_report.py results/wsc_s5_hipporag2.jsonl results/wsc_s5_hipporag2_nt.jsonl
```

---

## 七、限定与不可写的话

- **60 题标定场抽样**,依榜单既定规矩**不得与 576 题 / 418 题全量直比**;本文件所有对照都在同 60 题上配对完成。
- 相邻名次不作主张:HippoRAG 2 55.0 与 lgstore 55.0 / txtai 53.3 / 直读 51.7 的 CI 互相覆盖,**只能说"同档"**,不能说"优于"。
- 未跑 v2.4 全 576(33-H 的"若可行"项):本轮时间与并行额度用在 60 题主跑 + 不截断对照 + 检索诊断三件上;若续跑,建库成本按实测线性外推 = 144 库 × 34.3s ≈ 82 分钟、约 $1.6 建库,**该数字是外推不是实测,不得当结果引用**。
- `change_count` 题面在 v1 考场未附"首值不计"的显式说明(v2 题面才有)。此约定对**全部**同台系统一致,且直读 53.3、timeline 53.3、smoc 80.0 表明该约定可被同档读者习得,**不能用题面歧义解释 HippoRAG 2 的 13.3**。
- **gpt-4o 重排臂是诊断,不是同台成绩。** 它偏离 README 默认(用了更贵的重排模型),只用来回答"41.7% 回退率是不是廉价模型伪影"这一个问题;榜单行一律以 gpt-4o-mini 默认臂的 55.00 为准。
- 嵌入器选了 README 快速开始的 `text-embedding-3-small` 而非字段默认的 `nvidia/NV-Embed-v2`;若日后有 ≥24GB 显存的机器,**建议以 NV-Embed-v2 复跑一次**再定谳其检索上限——不过 §3.5 已表明其瓶颈在裁决而非召回,换嵌入器预计动不了 `change_count` 那一栏(此为预测,非结果)。
