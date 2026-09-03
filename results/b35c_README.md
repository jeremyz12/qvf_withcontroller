# b35c 共享协议:竞品记忆系统 × v2.5 小样本(15 库 / 58 题)同题同分

日期 2026-09-03。本文件只做两件事:(1) 固定所有系统必须遵守的同一份考场协议;(2) 逐系统写清
"60 题标定场当时怎么跑的 / 现有 CLI 能接什么 / 缺哪些接线 / 用哪个环境 / 建库成本 / 输出行格式"。
**本轮未跑任何系统**;下文所有分数、token、建库秒数都是从既有存档文件重新计算的(文件名逐一标出),
不是新结果。本轮新产出的文件只有两份:

| 文件 | 内容 |
|---|---|
| `D:\ZZL_cluade\results\b35c_questions.jsonl` | 58 行 = `data/wsc_s5_v25.jsonl`(560 行)中 uid ∈ `results/b35c_sample_uids.txt` 的行,schema 原样(`uid / qid / qtype / question / gold`) |
| `D:\ZZL_cluade\results\b35c_README.md` | 本文件 |

题集核对:15 uid 全部命中,58 题 = change_count 15 / count_before 15 / first_vs_last 15 / longest_tenure 13
(`wikiP551000-Q19845625` 与 `wikiP551008-Q29918442` 各只有 3 题,其余 13 uid 各 4 题)。
15 个 uid 在 `data/wikistate_full_ALL_v25.json`(144 条目)里全部存在,每库 33–36 个会话。

---

## 一、共享协议块(每个系统逐字遵守;违背任一项的结果不入同台表)

| 项 | 取值 |
|---|---|
| 语料 | `data/wikistate_full_ALL_v25.json`。条目字段 `uid / slot / type / chain / sessions / probing_queries / attribution`;`sessions[i] = {chain_index, date, turns}`,`turns` 是 `str(dict)` 文本(`"{'role': 'user', 'content': ...}"`) |
| 库清单 | `results/b35c_sample_uids.txt`(15 行,顺序即跑批顺序) |
| 题集 | `results/b35c_questions.jsonl`(58 行;`qid` 写入结果行的 `question_id`,`qtype` → `question_type`,`gold` → `gold_answer`) |
| 每库建库 | **每 uid 一座全新的库**,库间零共享;会话按 `date` 升序逐条写入 |
| 会话段落化 | `sess_text(s) = "(session date: {date})\n" + "\n".join(str(t)[:400] for t in turns[:6])`(`scripts/repro_batch4.py::sess_text`,日期逐字前缀,前 6 轮、每轮 400 字符) |
| 检索 | 每题 top-**10**(obs-RAG 例外:其论文配方 top-5,存档即如此,冻结不改) |
| 记忆行截断 | 读者看到的每条记忆 `- {text[:400]}`(repro_batch4 家族 / hipporag2 / cognee / amem)。**各 harness 存档时的实际截断值列在 §三每节 (f)**——repro_batch2 家族与 langmem/mstrata 是 300 字符、memos 与 trace 不截断——这些是各 harness 已冻结的常量,b35c 复跑一律保持原值,不得统一 |
| 读者 | `claude-haiku-4-5`,`temperature=0`,`max_tokens=300`,system = `READER_SYS`(下),user = `"MEMORIES:\n{memtext}\n\nUSER'S NEW MESSAGE: {question}"`;检索为空时 `memtext = "(no memories retrieved)"`;失败重试 3 次 |
| `READER_SYS` | `You are the user's personal AI assistant. You will be shown MEMORIES retrieved from a memory system about this user (each may carry dates), followed by the user's new message. Reply to the new message naturally and helpfully in 1-3 sentences, as you would in an everyday chat.`(`scripts/repro_batch2.py:27-31`,逐字) |
| 判官 | `qvf.judge.ClaudeJudge()` 默认档 = `qvf.config.DEFAULT_JUDGE_MODEL` = **`claude-opus-5`**(环境变量 `QVF_JUDGE_MODEL` 未设时);调用 `judge.judge(question, str(gold), answer, qtype)`;判官 usage 不落行,只在 `judge.total_usage` 累计 |
| 延迟口径 | `latency_s` = 从检索开始到判官返回(与榜单其余行同一约定) |
| 输出文件 | **`results/b35c_<system>.jsonl`**,`<system>` ∈ {timeline, sumrag, obsrag, txtai, lgstore, bm25, mstrata, cognee, amem, hipporag2, memos, mem0, langmem, trace, letta_fs};追加写、按 `question_id` 断点续跑 |
| 店目录 | **`results/b35c_<system>_stores/<uid>/`**(需要落盘的系统);既有 `results/hipporag_stores`、`results/trace_stores/*`、`results/memos_stores_*`、`results/letta_fs_corpus`、`D:\tmp\qdrant`(Mem0 默认)一律不得写入 |
| 必需行字段 | `question_id, uid, question_type, gold_answer, answer, judge_correct, usage_input_tokens, usage_output_tokens, latency_s`;有建库的系统再加 **`build_s`**(该库建库墙钟秒,库内每行重复写同一值) |
| `build_s` 与 `ingest_seconds` | 所有既有 harness 把这个量写成 `ingest_seconds`(语义完全相同:该 uid 的建库墙钟)。为了不动 harness 的输出逻辑,汇总脚本按 `build_s = row.get("build_s", row.get("ingest_seconds"))` 读取;新增接线时**若顺手写入 `build_s` 也可,但不得删除 `ingest_seconds`** |
| 其它建议字段 | `mode`(系统名)、`question`、`memories_n`、`judge_reason`;系统内部 LLM/嵌入用量按各自现有字段名(见 §三 (f)) |
| 并行 | 条目级并行 ≤ 4(memos 存档用 3 线程) |
| 库版本 | 所有隔离 venv 的 `anthropic` 钉 **0.121.0**(= 主环境;1.3.0 的 `messages.create` 不再收 `temperature`,会让读者三次重试全空) |
| 价格表(项目冻结口径) | haiku-4-5 $1.00/$5.00 per M;claude-opus-5 $5.00/$25.00;gpt-4o-mini $0.15/$0.60;gpt-4.1-mini $0.40/$1.60;text-embedding-3-small $0.02/M |
| 汇总口径 | acc = mean(judge_correct) over 58;分题型;in/out token 均值;`latency_s` 中位;`build_s` 每库均值与 15 库合计;系统间比较一律按 `question_id` 配对(58 题同集),簇 = 15 uid |

### 关于榜单"建库"列的一个口径说明

`scripts/build_wikistate_leaderboard.py::stats` 的 `ingest = sum(ing)/len(ing)` 是**对行取均值**,而每行携带的是其所在库的
`ingest_seconds`;15 库 × 4 题等权时,这个均值 = **每库**建库秒,榜单却标成 "s/题"。例如 Mem0 "131.2s/题" 实为 131.2 s/库(= 32.8 s/题)。
本文件 §三 (e) 一律同时给 **s/库** 与 **s/题**,并注明来源文件。b35c 里两个 uid 只有 3 题,按行取均值将不再等于按库取均值,
汇总脚本应按库去重后再算。

### 跑前核查清单(本轮已核,状态如下)

| 项 | 状态 |
|---|---|
| `.env` 含 `ANTHROPIC_API_KEY`;`OPENAI_API_KEY` 在环境中 | 已核(均存在,值未读取) |
| 主环境 Python 3.14.5:`anthropic 0.121.0 / openai 2.53.0 / mem0 2.0.16 / cognee 1.5.3 / langchain_openai 1.4.3 / sentence_transformers 6.0.0`;`txtai / langgraph / langmem / rank_bm25` 可 import | 已核 |
| `.venv_hipporag`(3.12.10):`hipporag 2.0.0a3` 在脚本的 vllm/Manager 垫片下 import 成功;`anthropic 0.121.0` | 已核 |
| `.venv_trace`(3.12.10):`openai 3.7.0 / sentence_transformers / networkx / anthropic 0.121.0` | 已核 |
| `.venv_memos`(3.12.10):`memos / qdrant_client / anthropic 0.121.0` | 已核 |
| TRACE 原仓克隆 `C:/Users/25243/AppData/Local/Temp/claude/D--ZZL-cluade/127d6855-ac31-4f09-a027-67dbfc5cf191/scratchpad/TRACE`,commit `1375df3c`(与 H2 判决一致),`configs/longmemeval_main.json` 在 | 已核(位于 Temp 目录,建议先复制到 `external/TRACE` 再跑) |
| A-MEM 源码(repro_batch4 硬编码路径 `.../2b238d36-.../scratchpad/A-mem`) | **缺失**:该目录下 `agentic_memory/` 只剩空壳(无任何 `.py`,`memory_system.py` 不在),主环境也未安装 `agentic_memory` → amem 现在跑不起来,须重新 clone(见 §三.9) |
| 15 个 b35c uid 与既有店目录(`hipporag_stores / trace_stores/trace_v1 / memos_stores_haiku / memos_stores_60q / letta_fs_corpus`)的重叠 | 零重叠(仍按规则使用 b35c_ 新目录) |
| `D:\tmp\qdrant`(Mem0 默认 vector store,collection `mem0`)已存在 | 已核 → mem0 复跑必须改 path(见 §三.12) |

---

## 二、各 harness 现有 CLI 一览(接线缺口总表)

| 系统 | 跑批脚本 | 现有 CLI | 语料可换? | uid 可换? | 题集可换? | 输出路径可指定? | 店目录可指定? |
|---|---|---|---|---|---|---|---|
| timeline / sumrag / obsrag / mem0 | `scripts/repro_batch2.py` | `--system` | 否(VOLS 硬编码) | 否(`sample_stores()`) | 否 | 否(`results/wsc_s5_<name>.jsonl`) | 否(mem0 用默认 `D:\tmp\qdrant`) |
| txtai / lgstore / bm25 / mstrata / cognee / amem | `scripts/repro_batch4.py` | `--system --limit-stores --questions-file --out-suffix` | 否 | 否(`--questions-file` 仍与 `sample_stores()` 15 库取交集 → 对 b35c uid 交集为空) | **是**(schema 恰为 uid/qid/qtype/question/gold) | 仅后缀 | cognee 走全局目录;amem 源码路径硬编码 |
| hipporag2 | `scripts/hipporag2_baseline.py` | `--limit-stores --store-offset --out-suffix --no-truncate --store-root --reuse-store --rerank-llm` | 否 | 否 | 否 | 仅后缀 | **是** |
| memos | `scripts/repro_batch33h_memos.py` | `--limit-stores --out-suffix --llm-model --llm-api-base --llm-api-key-env --embed-model --embed-dims --workers --top-k --drop-top-p` | 否 | 否 | 否 | 仅后缀 | 由 `--out-suffix` 派生(`results/memos_stores<suffix>`) |
| langmem | `scripts/langmem_s5_agg.py` | `--n-stores --store-offset --out` | 否 | 否(等距公式) | 否(`results/wsc_s5_filter_only.jsonl` 硬编码) | **是** | 无落盘 |
| trace | `scripts/trace_contestant.py` | `--questions --vols --uids-file --all-uids --limit-stores --shard --nshards --out-suffix --model --api-base --update-detection --evolution --store-root` | **是** | **是** | **是** | 仅后缀 | **是** |
| letta_fs | `scripts/letta_fs_agent_baseline.py` | `--out --limit-stores` | 否 | 否 | 否 | **是** | 否(`results/letta_fs_corpus` 硬编码) |

**统一接线规范**(所有缺口用同一组参数名,照抄 `trace_contestant.py:269-288` 与 `:311-331` 的实现):

```
--vols PATH[,PATH]      逗号分隔语料 json;默认保持各脚本原 VOLS
--uids-file PATH        uid 清单(每行一个);给出时替代 sample_stores() 的 picked,保持文件顺序
--questions-file PATH   题集 jsonl(uid/qid/qtype/question/gold);给出时 by_uid 从它重建
--out PATH              结果 jsonl 完整路径;默认保持原 results/wsc_s5_<name>{suffix}.jsonl
--store-root PATH       需要落盘的系统:店根目录;默认保持原值
```

实现骨架(替换各脚本 `main()` 里 `entries = ... / picked, by_uid = sample_stores()` 那一段,其余逐行不动):

```python
vols = a.vols.split(",") if a.vols else VOLS
entries = {}
for v in vols:
    for e in json.loads((ROOT / v).read_text(encoding="utf-8")):
        entries.setdefault(e["uid"], e)
picked, by_uid = sample_stores()
if a.questions_file:
    by_uid = {}
    for q in (json.loads(l) for l in open(ROOT / a.questions_file, encoding="utf-8") if l.strip()):
        by_uid.setdefault(q["uid"], []).append(q)      # 键 qid/qtype/question/gold 与 sample_stores 产物同名
if a.uids_file:
    picked = [u.strip() for u in open(ROOT / a.uids_file, encoding="utf-8") if u.strip()]
picked = [u for u in picked if u in by_uid]
out_p = ROOT / a.out if a.out else ROOT / f"results/wsc_s5_{sysm.name}{a.out_suffix}.jsonl"
```

b35c 统一调用尾巴(各系统前缀见 §三):

```
--vols data/wikistate_full_ALL_v25.json --uids-file results/b35c_sample_uids.txt \
--questions-file results/b35c_questions.jsonl --out results/b35c_<system>.jsonl \
[--store-root results/b35c_<system>_stores]
```

汇总脚本(待写,$0):`scripts/b35c_score.py` — 读 `results/b35c_<system>.jsonl`,先核 `question_id` 集合 == `b35c_questions.jsonl` 的 58 个 qid
(缺/多/重复即报错),再出 acc / 分题型 / in-out token 均值 / `latency_s` 中位 / `build_s`(按库去重)均值与合计 / 配对表(McNemar 精确 + 15 簇自助,复用 `scripts/b33h3_stats.py` 的 `sign_test / paired_boot`)。

---

## 三、逐系统

存档统计口径(本节 (e) 与各节首行):从 `results/wsc_s5_<name>.jsonl` 重新计算,n=60,15 库;
`s/库` = 15 库 `ingest_seconds` 去重均值(括号内中位),`s/题` = 15 库合计 ÷ 60。
建库 $ 只在 harness 落盘了内部 token 的系统(hipporag2 / memos / trace)给实测值;其余标"未埋点",
仅引用判决文件里的批级估计并明确标为估计。

### 1. timeline(TReMu 式时间线组织)

存档:`results/wsc_s5_timeline.jsonl` — acc 63.33,in 1841 / out 90,延迟中位 4.93 s。

- **(a) 60 题命令**:`cd D:\ZZL_cluade && python scripts/repro_batch2.py --system timeline`(主环境;`PYTHONUTF8=1`)。
  写侧:每会话一次 haiku 调用(`max_tokens=200`,`temperature=0`,提示"Write ONE timeline memo line ... [date] what happened / what changed")→ 全部 memo 行按序存 list;读侧**无检索**,全时间线交读者。
- **(b) 现有 CLI**:只有 `--system {mem0,sumrag,obsrag,timeline}`。语料 `VOLS`(v1 四卷)、uid(`sample_stores()`)、题源(`results/wsc_s5_filter_only.jsonl`)、输出路径(`results/wsc_s5_timeline.jsonl`)全部硬编码。
- **(c) 缺口**:`--vols / --uids-file / --questions-file / --out`(§二骨架,≈15 行,只动 `main()` 的装载段;`TimelineSystem` 类不动)。无店落盘,不需 `--store-root`。
  b35c 命令:`python scripts/repro_batch2.py --system timeline --vols data/wikistate_full_ALL_v25.json --uids-file results/b35c_sample_uids.txt --questions-file results/b35c_questions.jsonl --out results/b35c_timeline.jsonl`
- **(d) 环境**:主环境(Python 3.14.5,`anthropic 0.121.0`,`qvf`)。仅需 `ANTHROPIC_API_KEY`。
- **(e) 建库(存档)**:15 库合计 658.5 s;**43.9 s/库**(中位 43.4)= 11.0 s/题;每库 ≈33 次 haiku 调用。建库 token **未埋点**(repro_batch2 不记写侧用量),$ 无实测。
- **(f) 行 schema**(14 字段):`question_id, mode, uid, question_type, question, gold_answer, answer, memories_n, usage_input_tokens, usage_output_tokens, judge_correct, judge_reason, ingest_seconds, latency_s`。`build_s` ← `ingest_seconds`。记忆行 `- {line[:300]}`(**300**,冻结)。

### 2. sumrag(摘要 RAG harness)

存档:`results/wsc_s5_sumrag.jsonl` — acc 46.67,in 917 / out 80,延迟中位 5.35 s。

- **(a)**:`python scripts/repro_batch2.py --system sumrag`。写侧:每会话一次 haiku 摘要(`max_tokens=250`,保留日期/名字/数字,前缀会话日期)→ `qvf.retrieval.OpenAIDenseRetriever`(text-embedding-3-small,进程内嵌入缓存,不落盘);读侧 `retrieve(query, top_k=10)`。
- **(b)**:同 timeline(只有 `--system`)。
- **(c)**:同 timeline 四个参数。命令:`python scripts/repro_batch2.py --system sumrag --vols ... --uids-file ... --questions-file ... --out results/b35c_sumrag.jsonl`。
- **(d)**:主环境;`ANTHROPIC_API_KEY` + `OPENAI_API_KEY`。
- **(e)**:15 库合计 789.7 s;**52.6 s/库**(中位 51.9)= 13.2 s/题;每库 ≈33 次 haiku + 一次嵌入。token 未埋点。
- **(f)**:同 14 字段。记忆行 `- [{session_date}] {content[:300]}`(**300**)。

### 3. obsrag(LoCoMo 官方最优配方:observations + top-5)

存档:`results/wsc_s5_obsrag.jsonl` — acc 13.33,in 202 / out 72,延迟中位 5.16 s。

- **(a)**:`python scripts/repro_batch2.py --system obsrag`。写侧:每会话一次 haiku 抽 observations(`max_tokens=300`,一行一条、带日期)→ 逐条入 `OpenAIDenseRetriever`;读侧 `retrieve(query, top_k=5)`(`ObsRagSystem.TOPK = 5`,其论文配方,**冻结例外**,不是 k=10)。
- **(b)/(c)**:同 timeline。命令:`... --system obsrag ... --out results/b35c_obsrag.jsonl`。
- **(d)**:主环境;两把 key。
- **(e)**:15 库合计 1008.9 s;**67.3 s/库**(中位 64.6)= 16.8 s/题。token 未埋点。
- **(f)**:同 14 字段。记忆行 `- {content[:300]}`(**300**)。

### 4. txtai(本地嵌入 flat-RAG)

存档:`results/wsc_s5_txtai.jsonl` — acc 53.33,in 1189 / out 85,延迟中位 5.34 s。

- **(a)**:`python scripts/repro_batch4.py --system txtai`。写侧零 LLM:`txtai.Embeddings(content=True)` 默认模型,`index([(i, sess_text(s), None)])`;读侧 `emb.search(query, limit=10)`。
- **(b)**:`--system`、`--limit-stores N`、`--questions-file PATH`(已能读 b35c schema)、`--out-suffix`。**但** `picked = [u for u in picked if u in by_uid]` 里的 `picked` 仍是 `sample_stores()` 的 v1 15 库 → 与 b35c uid 交集为空,会一题不跑。语料 `VOLS` 硬编码。
- **(c)**:加 `--vols / --uids-file / --out`(`--questions-file` 已有),≈10 行。
  命令:`python scripts/repro_batch4.py --system txtai --vols data/wikistate_full_ALL_v25.json --uids-file results/b35c_sample_uids.txt --questions-file results/b35c_questions.jsonl --out results/b35c_txtai.jsonl`
- **(d)**:主环境(`txtai`、`sentence_transformers 6.0.0`,CPU 版 torch)。仅 `ANTHROPIC_API_KEY`(读者/判官)。
- **(e)**:15 库合计 98.4 s;**6.6 s/库**(中位 6.0)= 1.6 s/题;**$0**(无 API)。内存索引,不落盘。
- **(f)**:同 14 字段;记忆行 `- {text[:400]}`。

### 5. lgstore(langgraph InMemoryStore + openai 嵌入)

存档:`results/wsc_s5_lgstore.jsonl` — acc 55.00,in 1178 / out 82,延迟中位 5.68 s。

- **(a)**:`python scripts/repro_batch4.py --system lgstore`。单个 `InMemoryStore(index={"embed": OpenAIEmbeddings("text-embedding-3-small"), "dims": 1536})`,命名空间 `(uid, "sessions")` 隔离;`store.search(ns, query=q, limit=10)`。
- **(b)/(c)**:同 txtai。命令:`... --system lgstore ... --out results/b35c_lgstore.jsonl`。
- **(d)**:主环境(`langgraph`、`langchain_openai 1.4.3`);`OPENAI_API_KEY` + `ANTHROPIC_API_KEY`。
- **(e)**:15 库合计 55.2 s;**3.7 s/库**(中位 3.4)= 0.9 s/题;仅嵌入费(未埋点,量级 ≈33 段 × ~725 字符/库)。
- **(f)**:同 14 字段;`- {text[:400]}`。

### 6. bm25(rank_bm25 词面检索)

存档:`results/wsc_s5_bm25.jsonl` — acc 13.33,in 1201 / out 81,延迟中位 4.92 s。

- **(a)**:`python scripts/repro_batch4.py --system bm25`。`BM25Okapi(lower().split())`,`get_scores` 取前 10。
- **(b)/(c)**:同 txtai。命令:`... --system bm25 ... --out results/b35c_bm25.jsonl`。
- **(d)**:主环境(`rank_bm25`、numpy)。
- **(e)**:`ingest_seconds` 全为 0.0(合计 0.0 s);**$0**。
- **(f)**:同 14 字段;`- {doc[:400]}`。

### 7. mstrata(写入盖章台账,MemStrata 式复刻)

存档:`results/wsc_s5_mstrata.jsonl` — acc 11.67,in 314 / out 67,延迟中位 4.73 s。

- **(a)**:`python scripts/repro_batch4.py --system mstrata`。写侧:每会话一次 haiku 三元组抽取(`max_tokens=500`,JSON 数组 `{s,r,o}`)→ `(s,r)` 键台账:异值取代(旧行 `superseded=True`)、同值无操作;读侧只对**活跃行**建 `OpenAIDenseRetriever`,`retrieve(top_k=10)`。
- **(b)/(c)**:同 txtai。命令:`... --system mstrata ... --out results/b35c_mstrata.jsonl`。
- **(d)**:主环境;两把 key。
- **(e)**:15 库合计 783.4 s;**52.2 s/库**(中位 51.5)= 13.1 s/题。token 未埋点;`results/repro_batch4b_verdict.md:34` 记批级估计 "mstrata 抽取 $0.9"(15 库,≈$0.06/库,**估计**)。
- **(f)**:同 14 字段;记忆行 `- [since {valid_from}] {s} {r}: {o}`,截 **300**。

### 8. cognee(LLM 知识图谱;取 CHUNKS 喂读者)

存档:`results/wsc_s5_cognee.jsonl` — acc 46.67,in 1177 / out 88,延迟中位 6.62 s。

- **(a)**:`python scripts/repro_batch4.py --system cognee`。构造时 `os.environ.setdefault("LLM_API_KEY", OPENAI_API_KEY)`、`LLM_MODEL=gpt-4o-mini`、`EMBEDDING_API_KEY`;每库 `cognee.add(sess_text, dataset_name=uid)` × 会话数 → `cognify(datasets=[uid])`;读侧 `search(query_text, SearchType.CHUNKS, datasets=[uid], top_k=10)`,取 `search_result[].text`。
- **(b)**:同 txtai。**店目录**:cognee 1.5.3 写入其全局 system/data root(嵌入式 lancedb/kuzu/sqlite),按 `dataset_name=uid` 分数据集;60 题存档的数据集仍在那里。
- **(c)**:同 txtai 三参数 + `--store-root`:在 `CogneeSystem.__init__` 里调用 `cognee.config.system_root_directory(<root>/system)` 与 `cognee.config.data_root_directory(<root>/data)`(两个 API 在 1.5.3 存在,本轮已核),根 = `results/b35c_cognee_stores`。
  命令:`python scripts/repro_batch4.py --system cognee --vols ... --uids-file ... --questions-file ... --out results/b35c_cognee.jsonl --store-root results/b35c_cognee_stores`
- **(d)**:主环境(`cognee 1.5.3`);`OPENAI_API_KEY`(gpt-4o-mini + 嵌入)+ `ANTHROPIC_API_KEY`。无 Docker。
- **(e)**:15 库合计 457.2 s;**30.5 s/库**(中位 29.7)= 7.6 s/题。token 未埋点;`repro_batch4b_verdict.md:34` 批级估计 "cognee cognify $0.8"(15 库,≈$0.053/库,**估计**)。
- **(f)**:同 14 字段;`- {text[:400]}`。

### 9. amem(A-MEM,agiresearch;Zettelkasten 演化笔记)

存档:`results/wsc_s5_amem.jsonl` — acc 43.33,in 1191 / out 85,延迟中位 5.27 s。

- **(a)**:`python scripts/repro_batch4.py --system amem`。`AgenticMemorySystem(model_name="all-MiniLM-L6-v2", llm_backend="openai", llm_model="gpt-4o-mini")`,每会话 `add_note(sess_text(s), time=date)`(TypeError 时退回无 time),读侧 `search_agentic(query, k=10)` 取 `content`。源码通过 `sys.path.insert(0, "C:/Users/25243/AppData/Local/Temp/claude/D--ZZL-cluade/2b238d36-0e89-4591-ac1c-f5ffd6578795/scratchpad/A-mem")` 加载(`repro_batch4.py:105-107`)。
- **(b)**:同 txtai。
- **(c)**:**当前 BLOCKED,不是接线问题**:上述路径下 `agentic_memory/` 目录已空(无 `.py`,`memory_system.py` 不存在,`__pycache__` 亦空),主环境未安装 `agentic_memory`,`import agentic_memory.memory_system` 失败(本轮实测)。原克隆的 commit 未入档。恢复步骤:
  1. `git clone https://github.com/agiresearch/A-mem external/A-mem`,记录 commit;按其 requirements 补装(主环境已有 sentence-transformers / openai;其检索层若依赖 chromadb 等需补装——以 clone 后的 `requirements.txt` 为准);
  2. 把 `repro_batch4.py:105-107` 的硬编码路径改为 `--amem-repo PATH`(或环境变量 `AMEM_REPO`),默认值仍指旧路径以保持存档命令可读;
  3. 再加 txtai 同款三参数。命令:`python scripts/repro_batch4.py --system amem --amem-repo external/A-mem --vols ... --uids-file ... --questions-file ... --out results/b35c_amem.jsonl`。
  若重新 clone 的版本与 8 月 25 日那次行为不一致(接口/提示词改动),结果行须注明 commit,不得与存档 43.33 直比。
- **(d)**:主环境 + A-mem 依赖;`OPENAI_API_KEY`(gpt-4o-mini)+ `ANTHROPIC_API_KEY`。
- **(e)**:15 库合计 2665.7 s;**177.7 s/库**(中位 171.8)= 44.4 s/题。token 未埋点;`repro_batch4_verdict.md:39` 批级估计 "A-MEM 摄入走 gpt-4o-mini 约 $0.4"(15 库,≈$0.027/库,**估计**)。
- **(f)**:同 14 字段;`- {content[:400]}`。

### 10. hipporag2(HippoRAG 2,官方 pip 包 2.0.0a3)

存档:`results/wsc_s5_hipporag2.jsonl` — acc 55.00,in 1177 / out 85,延迟中位 6.15 s。判决 `results/opt_batch33_H1_hipporag2_verdict.md`。

- **(a)**:`PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv_hipporag/Scripts/python.exe scripts/hipporag2_baseline.py > results/_h1_hipporag_run.log 2>&1`。配置:`llm_name=gpt-4o-mini`(BaseConfig 默认)、`embedding_model_name=text-embedding-3-small`、`openie_mode=online`、`retrieval_top_k=10`、每 uid 全新 `save_dir`(`force_index_from_scratch=True`);OpenIE 线程池压到 4;import 期打桩 `vllm` 与 `multiprocessing.Manager`(Windows 必需,不触碰算法)。
- **(b)**:`--limit-stores --store-offset --out-suffix --no-truncate --store-root(默认 results/hipporag_stores) --reuse-store --rerank-llm`。语料/uid/题集全部来自 `VOLS` + `sample_stores()`;输出 `results/wsc_s5_hipporag2{suffix}.jsonl`。
- **(c)**:加 `--vols / --uids-file / --questions-file / --out`(§二骨架,替换 `main()` 第 200-207 行的装载段);`--store-root` 已有。
  命令:`PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv_hipporag/Scripts/python.exe scripts/hipporag2_baseline.py --vols data/wikistate_full_ALL_v25.json --uids-file results/b35c_sample_uids.txt --questions-file results/b35c_questions.jsonl --out results/b35c_hipporag2.jsonl --store-root results/b35c_hipporag2_stores`
  不加 `--no-truncate`(主臂口径);不加 `--reuse-store`(新库)。
- **(d)**:`.venv_hipporag`(Python 3.12.10,`hipporag==2.0.0a3`,`anthropic==0.121.0`;本轮已在垫片下验证 import)。`OPENAI_API_KEY` + `ANTHROPIC_API_KEY`。
- **(e)**:15 库合计 514.9 s;**34.3 s/库**(中位 33.7)= 8.6 s/题。**实测建库 $**(判决 §五,按行内 `hr_ingest_*` 折算):OpenIE gpt-4o-mini 669,651 in / 105,560 out = $0.1637,嵌入 283,907 tok = $0.0057 → 15 库 $0.169,**≈$0.0113/库**;查询期重排 60 次 $0.0267;店体积 149 MB / 15 库。
- **(f)**:14 基础字段 + `retrieve_s, read_s, hr_ingest_llm_in, hr_ingest_llm_out, hr_ingest_llm_calls, hr_ingest_emb_tok, hr_query_llm_in, hr_query_llm_out, hr_query_emb_tok, n_passages, graph_info, hipporag_llm, hipporag_embed, truncate_400, rerank_llm`。记忆行 `- {passage[:400]}`。

### 11. memos(MemOS 2.0.32,general_text + 内嵌 Qdrant)

存档(头条臂,haiku 抽取):`results/wsc_s5_memos_haiku.jsonl` — acc 45.00,in 609 / out 88,延迟中位 5.16 s;
对照臂(gpt-4.1-mini 抽取):`results/wsc_s5_memos.jsonl` — acc 43.33,in 592 / out 88,中位 4.93 s。判决 `results/opt_batch33_H4_memos_verdict.md`。

- **(a)** 头条臂:`PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv_memos/Scripts/python.exe scripts/repro_batch33h_memos.py --workers 3 --out-suffix _haiku --llm-model claude-haiku-4-5 --llm-api-base "https://api.anthropic.com/v1/" --llm-api-key-env ANTHROPIC_API_KEY --drop-top-p`;
  对照臂:`... repro_batch33h_memos.py --workers 3`(默认 gpt-4.1-mini)。每 uid 一只 `GeneralMemCube`(`text_mem=general_text`,extractor_llm openai 后端,vector_db qdrant 本地 path,embedder text-embedding-3-small 1536);写 `text_mem.extract(msgs) → add()`,读 `text_mem.search(query, top_k=10)`。`--drop-top-p` 只在传输层 pop `top_p`(Anthropic 兼容端点 400)。
- **(b)**:`--limit-stores --out-suffix --llm-model --llm-api-base --llm-api-key-env --embed-model --embed-dims --workers --top-k --drop-top-p`。**店根由 `--out-suffix` 派生**:`results/memos_stores{suffix or "_60q"}`;输出 `results/wsc_s5_memos{suffix}.jsonl`。语料/uid/题集硬编码。
- **(c)**:加 `--vols / --uids-file / --questions-file / --out / --store-root`(`--store-root` 覆盖 `store_root = ROOT/"results"/f"memos_stores{...}"` 那一行)。`run_uid` 与 `MemOSSystem` 不动。
  命令(头条口径):`PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv_memos/Scripts/python.exe scripts/repro_batch33h_memos.py --workers 3 --llm-model claude-haiku-4-5 --llm-api-base "https://api.anthropic.com/v1/" --llm-api-key-env ANTHROPIC_API_KEY --drop-top-p --vols data/wikistate_full_ALL_v25.json --uids-file results/b35c_sample_uids.txt --questions-file results/b35c_questions.jsonl --out results/b35c_memos.jsonl --store-root results/b35c_memos_stores`
- **(d)**:`.venv_memos`(Python 3.12.10,`MemoryOS==2.0.32`,`qdrant-client`,`anthropic==0.121.0`;本轮已验证 import)。`OPENAI_API_KEY`(嵌入)+ `ANTHROPIC_API_KEY`。不需要 Docker(`tree_text`/Neo4j 路线在本机 BLOCKED,b35c 同样只覆盖 general_text)。
- **(e)**:haiku 臂 15 库合计 2771.9 s;**184.8 s/库**(中位 182.6)= 46.2 s/题;**实测建库 $0.1732/库**(15 库 haiku 1,076,555 in / 303,790 out + 嵌入 97,037 tok)。gpt-4.1-mini 臂 270.5 s/库,$0.0535/库。店 ≈33 MB/uid。写侧 `temperature=0.7`(MemOS 出厂),同库重跑记忆条数会漂几条。
- **(f)**:14 基础字段 + `memos_llm_model, memos_kept_memories, memos_extract_errors, memos_session_count, memos_ingest_llm_in, memos_ingest_llm_out, memos_ingest_llm_calls, memos_ingest_embed_tokens, memos_retrieved`。记忆行 `- {memory}` **不截断**(冻结)。

### 12. mem0(Mem0 OSS 2.0.16,出厂默认 + gpt-4o-mini)

存档:`results/wsc_s5_mem0.jsonl` — acc 26.67,in 807 / out 97,延迟中位 5.82 s。

- **(a)**:`python scripts/repro_batch2.py --system mem0`。`Memory.from_config({"llm": {"provider": "openai", "config": {"model": "gpt-4o-mini", "temperature": 0.1}}})`(出厂默认 LLM 拒 temperature<1,偏离已入档 `results/repro_batch2_prereg.md`);embedder 默认 text-embedding-3-small;vector store = mem0 默认 qdrant(`path=/tmp/qdrant` → 本机 `D:\tmp\qdrant`,collection `mem0`,`history.db` 在 `C:\Users\25243\.mem0\`),按 `user_id=uid` 隔离;写 `m.add([{"role":"user","content": "(session date: …)\n"+text}], user_id=uid)` 逐会话;读 `m.search(query, filters={"user_id": uid}, limit=10)`。
- **(b)**:只有 `--system`。
- **(c)**:timeline 同款四参数 + **`--store-root`**:在 `Mem0System.__init__` 的 config 里加 `"vector_store": {"provider": "qdrant", "config": {"collection_name": "b35c_mem0", "embedding_model_dims": 1536, "path": "<root>/qdrant", "on_disk": False}}` 与 `"history_db_path": "<root>/history.db"`(字段写法与 `scripts/run_mem0_baseline.py::_mem0_config` 相同),根 = `results/b35c_mem0_stores`。不加这一项就会写进已存在的 `D:\tmp\qdrant/mem0` 集合(违反店目录规则)。另设 `MEM0_TELEMETRY=False`。
  命令:`python scripts/repro_batch2.py --system mem0 --vols data/wikistate_full_ALL_v25.json --uids-file results/b35c_sample_uids.txt --questions-file results/b35c_questions.jsonl --out results/b35c_mem0.jsonl --store-root results/b35c_mem0_stores`
- **(d)**:主环境(`mem0 2.0.16` 可 import);`OPENAI_API_KEY` + `ANTHROPIC_API_KEY`。
- **(e)**:15 库合计 1967.7 s;**131.2 s/库**(中位 127.1)= 32.8 s/题(榜单写 "131.2s/题" 系口径标签错误,见 §一)。token 未埋点(repro_batch2 不包 mem0 客户端;`run_mem0_baseline.py` 有包装器可搬,但那是另一条协议的脚本);prereg 的 "~$1" 是跑前估计。
- **(f)**:同 14 字段;记忆行 `- {json.dumps(memory)[:300]}`(**300**)。

### 13. langmem(LangChain 官方记忆库)

存档:`results/wsc_s5_langmem.jsonl` — acc 40.00,in 818 / out 91,延迟中位 5.70 s。预注册/判定 `results/langmem_s5_prereg.md`。

- **(a)**:`python scripts/langmem_s5_agg.py`(默认 `--n-stores 15 --store-offset 0 --out results/wsc_s5_langmem.jsonl`)。每 uid:`InMemoryStore(index={"dims":1536, "embed":"openai:text-embedding-3-small"})` + `create_memory_store_manager("anthropic:claude-haiku-4-5", namespace=("memories", uid), store=store)`;逐会话 `manager.invoke({"messages":[{"role":"user","content": "(session date: …)\n"+text}]})`;读 `store.search(("memories", uid), query=q, limit=10)`。
- **(b)**:`--n-stores --store-offset --out`。题源硬编码 `results/wsc_s5_filter_only.jsonl`(字段 `question_id/question_type/gold_answer`,脚本内部转成 `qid/qtype/gold`);语料 `VOLS` 硬编码;uid 由等距公式产生。
- **(c)**:加 `--vols / --uids-file / --questions-file`(`--out` 已有):`--questions-file` 给出时直接 `by_uid[uid].append(row)`(b35c 行已是 `qid/qtype/question/gold`,与脚本内部字典同名,无需再映射);`--uids-file` 给出时跳过等距公式。无落盘。
  命令:`python scripts/langmem_s5_agg.py --vols data/wikistate_full_ALL_v25.json --uids-file results/b35c_sample_uids.txt --questions-file results/b35c_questions.jsonl --out results/b35c_langmem.jsonl`
- **(d)**:主环境(`langmem`、`langgraph` 可 import);`ANTHROPIC_API_KEY`(haiku 抽取 + 读者/判官)+ `OPENAI_API_KEY`(嵌入)。
- **(e)**:15 库合计 4170.7 s;**278.0 s/库**(中位 264.7)= 69.5 s/题(全表最慢建库之一)。token 未埋点;prereg "批 1 ≈ $1.3"(含读者/判官)是跑前估计。
- **(f)**:同 14 字段;记忆行 `- {json.dumps(m.value)[:300]}`(**300**)。

### 14. trace(TRACE,arXiv:2607.00339;原仓代码零复刻)

存档(预设 A,出厂 LongMemEval 配置):`results/wsc_s5_trace.jsonl` — acc 16.67,in 2722 / out 84,延迟中位 8.08 s;
预设 B(`--evolution --update-detection`):`results/wsc_s5_trace_evoupd.jsonl` — acc 30.00,in 11517 / out 84。判决 `results/opt_batch33_H2_trace_verdict.md`。

- **(a)** 预设 A,4 分片并行后合并:
  ```
  for s in 0 1 2 3; do PYTHONUTF8=1 TRACE_REPO=<clone> .venv_trace/Scripts/python.exe scripts/trace_contestant.py --shard $s --nshards 4 --out-suffix _sh$s --store-root D:/ZZL_cluade/results/trace_stores/trace_v1 & done
  cat results/wsc_s5_trace_sh{0,1,2,3}.jsonl > results/wsc_s5_trace.jsonl
  ```
  流程:WikiState 库 → LongMemEval 记录格式(`to_longmemeval`,**全部轮次、不截断**,`ast.literal_eval` 还原 role/content)→ `ingest_memories / build_summaries / build_graph` → 每题 `TRACEGraphAgent` + `TRACEPipeline.retrieve().context`(`retrieve_k=10`)→ 我方读者。LLM `gpt-4o-mini` 走 OpenAI 官方端点(`api_base=None`)。
- **(b)**:`--questions --vols --uids-file --all-uids --limit-stores --shard --nshards --out-suffix --model --api-base --update-detection --evolution --store-root`。**语料 / uid / 题集三项已全部接好**,且 `--questions` 读的就是 `uid/qid/qtype/question/gold`。
- **(c)**:只差输出路径(`--out-suffix` 只能生成 `results/wsc_s5_trace{suffix}.jsonl`)。两种做法任选:加 `--out PATH`(一行),或用 `--out-suffix _b35c_sh$s` 跑完后 `cat` 成 `results/b35c_trace.jsonl`(分片原件保留)。`TRACE_REPO` 指向本轮核实的克隆(commit `1375df3c`),建议先 `cp -r` 到 `external/TRACE`。
  命令(预设 A,主口径):
  ```
  for s in 0 1 2 3; do PYTHONUTF8=1 TRACE_REPO=D:/ZZL_cluade/external/TRACE .venv_trace/Scripts/python.exe scripts/trace_contestant.py \
    --questions results/b35c_questions.jsonl --vols data/wikistate_full_ALL_v25.json --uids-file results/b35c_sample_uids.txt \
    --shard $s --nshards 4 --out-suffix _b35c_sh$s --store-root D:/ZZL_cluade/results/b35c_trace_stores & done
  cat results/wsc_s5_trace_b35c_sh{0,1,2,3}.jsonl > results/b35c_trace.jsonl
  ```
  预设 B 若也要:同上加 `--evolution --update-detection`,输出 `results/b35c_trace_evoupd.jsonl`,店根 `results/b35c_trace_evoupd_stores`(建库 $ 涨 5.9×、时长 7.6×,见 (e))。
- **(d)**:`.venv_trace`(Python 3.12.10;`openai 3.7.0 / sentence-transformers / torch / networkx / anthropic==0.121.0`;本轮已验证 import)。`OPENAI_API_KEY` + `ANTHROPIC_API_KEY`。
- **(e)**:预设 A 15 库合计 5168.9 s;**344.6 s/库**(中位 344.8)= 86.1 s/题;**实测建库 $0.5483 / 15 = $0.0366/库**(2,181,794 in / 368,464 out gpt-4o-mini,3,007 次调用)。预设 B:2610 s/库(中位 2613),**$3.2264 / 15 = $0.215/库**(39,988 次调用)。
- **(f)**:`question_id, mode, uid, question_type, question, gold_answer, ingest_seconds, trace_ingest_input_tokens, trace_ingest_output_tokens, trace_ingest_llm_calls, trace_path_mode, trace_path_explanation, [retrieval_error], trace_retrieval_latency_s, trace_query_input_tokens, trace_query_output_tokens, trace_query_llm_calls, trace_context_chars, trace_context_head, answer, usage_input_tokens, usage_output_tokens, judge_correct, judge_reason, latency_s`。无 `memories_n`;上下文整包**不截断**(冻结,已入档为对 TRACE 有利的偏离)。

### 15. letta_fs(Letta 式文件系统 agent 平凡强基线;**不是** Letta 服务器)

存档:`results/wsc_s5_lettafs.jsonl` — acc 56.67,in 18914 / out 513,延迟中位 11.66 s。判决 `results/opt_batch33_H3_letta_verdict.md`
(Letta 0.16.8 服务器本身 BLOCKED:0.16.x `letta/server/db.py` 只有 PostgreSQL 引擎分支,本机无 Postgres、Docker 不可用;b35c 同样不含 Letta 本体)。

- **(a)**:`PYTHONUTF8=1 python scripts/letta_fs_agent_baseline.py --out results/wsc_s5_lettafs.jsonl`。写侧零 LLM/零嵌入:每会话落成 `results/letta_fs_corpus/<uid>/s<NNN>__<date>.md`(内容 = `sess_text`);读侧 `claude-haiku-4-5` agent(`AGENT_SYS`,`max_tokens=700`/轮,`temperature=0`,工具 `list_files / grep_files / read_file`,最多 12 轮,末轮无工具强制作答)。**读者协议与其余系统不同**(agentic、非 `READER_SYS`/300 tokens),这是该基线冻结的自身协议,不改。判官相同。
- **(b)**:`--out --limit-stores`。语料 `VOLS`、uid `sample_stores()`、`CORPUS_ROOT = results/letta_fs_corpus` 硬编码。
- **(c)**:加 `--vols / --uids-file / --questions-file / --corpus-root`(后者覆盖 `CORPUS_ROOT`,根 = `results/b35c_letta_fs_corpus`)。`run_agent / FsTools / AGENT_SYS / TOOLS` 不动。
  命令:`PYTHONUTF8=1 python scripts/letta_fs_agent_baseline.py --vols data/wikistate_full_ALL_v25.json --uids-file results/b35c_sample_uids.txt --questions-file results/b35c_questions.jsonl --corpus-root results/b35c_letta_fs_corpus --out results/b35c_letta_fs.jsonl`
- **(d)**:主环境,仅 `anthropic`(`ANTHROPIC_API_KEY`)。
- **(e)**:15 库合计 0.189 s = **12.6 ms/库**,**$0**。读侧 $0.0215/题(存档实测 in 1,134,841 / out 30,806 for 60 题)。
- **(f)**:14 基础字段 + `agent_rounds, tool_list, tool_grep, tool_read`;`memories_n` = 该库文件数;`usage_*` 为 agent 全部轮次累计。

---

## 四、建库成本/时间总表(存档,15 库;供 b35c 预算)

| 系统 | s/库(中位) | s/题 | 建库 $/库 | $ 来源 | 落盘店 |
|---|---|---|---|---|---|
| timeline | 43.9 (43.4) | 11.0 | 未埋点 | — | 无 |
| sumrag | 52.6 (51.9) | 13.2 | 未埋点 | — | 无 |
| obsrag | 67.3 (64.6) | 16.8 | 未埋点 | — | 无 |
| txtai | 6.6 (6.0) | 1.6 | $0 | 零 API | 无 |
| lgstore | 3.7 (3.4) | 0.9 | 仅嵌入,未埋点 | — | 无 |
| bm25 | 0.0 | 0.0 | $0 | 零 API | 无 |
| mstrata | 52.2 (51.5) | 13.1 | ≈$0.06(估计) | repro_batch4b_verdict:34 | 无 |
| cognee | 30.5 (29.7) | 7.6 | ≈$0.053(估计) | repro_batch4b_verdict:34 | cognee 全局根(b35c 改 `--store-root`) |
| amem | 177.7 (171.8) | 44.4 | ≈$0.027(估计) | repro_batch4_verdict:39 | 无(源码缺失,BLOCKED) |
| hipporag2 | 34.3 (33.7) | 8.6 | **$0.0113(实测)** | H1 判决 §五 / 行内 `hr_ingest_*` | 149 MB/15 库 |
| memos(haiku 臂) | 184.8 (182.6) | 46.2 | **$0.1732(实测)** | H4 判决 §2 / 行内 `memos_ingest_*` | ≈33 MB/uid |
| mem0 | 131.2 (127.1) | 32.8 | 未埋点 | — | qdrant(b35c 改 `--store-root`) |
| langmem | 278.0 (264.7) | 69.5 | 未埋点 | — | 无 |
| trace(预设 A) | 344.6 (344.8) | 86.1 | **$0.0366(实测)** | H2 判决 §四 / 行内 `trace_ingest_*` | memories/summaries/graphs |
| letta_fs | 0.013 | 0.003 | $0 | 零 API | 499 个 .md 文件/15 库 |

按存档线性外推 15 库 b35c 建库墙钟合计 ≈ 1.4 h(串行、不含 amem 恢复与 trace 预设 B);外推值,不作结果引用。
读侧每系统 58 题 haiku + 58 次 opus-5 判官(判官按 `results/judge_cost_measured_20260816.md` 实测均值 198.28/83.45 tok 折算 ≈ $0.18/系统)。

## 五、本轮未做与限定

- 15 个 harness 一个都没在 b35c 上跑;§三 (c) 的接线**尚未写入任何脚本**(本轮只做文档,不改代码、不 git 操作)。
- amem 在接线之前先要恢复 A-MEM 源码(§三.9);重新 clone 的版本若与 8-25 存档不同,须在结果行注 commit。
- Letta 服务器与 Memobase 不在本清单(均 BLOCKED,见 H3/H5 判决);letta_fs 是文件系统 agent 基线,不得冒充 Letta 本体。
- 存档口径是 v1 60 题(`_s5a..d` 题面),b35c 是 v2.5 58 题(`_v2cc/cb/lt/fl`,change_count 题面已含"首值不计"说明);两者**不得直比**,b35c 的比较只在 b35c 内部按 `question_id` 配对。
