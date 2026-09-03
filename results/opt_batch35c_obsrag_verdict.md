# b35c 判决:obs-RAG(LoCoMo 官方最优配方)× WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。本文件所有数字均由本轮实际产出的 `results/b35c_obsrag.jsonl`(58 行)与
`results/b35c_obsrag_build_usage{,_part1}.json` 重新计算,不引用任何既有存档分数。

## 判决

**猜想被证实:obs-RAG 在 v2.5 小样本上仍然崩在同一处。** 58 题准确率 **13.79%**(8/58),
与 60 题标定场存档 13.33%(8/60)在同一水平,四个题型全部落在 13–15% 区间(无题型幸免)。
机制上原因在行里可读:top-5 观察句检索给读者的上下文只有 **210 token 均值**(其余系统 900–1800),
读者在 count_before / change_count 上普遍答"记录不全、无法给出计数"。这不是 v2.5 语料造成的新问题,
是该配方的写侧(逐会话抽 observations)+ 读侧(top-5)组合本身把聚合题所需的全序列证据切碎了。

## 一、实际运行

| 项 | 值 |
|---|---|
| 命令 | `python <scratchpad>/b35c_run_obsrag.py`(观测壳,内部 `sys.argv = ["repro_batch2.py", "--system", "obsrag", "--vols", "data/wikistate_full_ALL_v25.json", "--uids-file", "results/b35c_sample_uids.txt", "--questions-file", "results/b35c_questions.jsonl", "--out", "results/b35c_obsrag.jsonl"]` 后直接调 `repro_batch2.main()`) |
| 环境 | 主环境 Python 3.14.5,`anthropic 0.121.0` / `openai 2.53.0`;`PYTHONUTF8=1`。**不需要隔离 venv**(README §三.3(d):obsrag 走主环境,两把 key) |
| 语料 | `data/wikistate_full_ALL_v25.json` |
| 库清单 | `results/b35c_sample_uids.txt`(15 uid,按文件顺序) |
| 题集 | `results/b35c_questions.jsonl`(58 题) |
| 结果 | `results/b35c_obsrag.jsonl`(58 行,`question_id` 集合与题集 58 个 qid **精确相等**,无重复) |
| 观测侧文件 | `results/b35c_obsrag_build_usage.json`(本次 13 库)、`results/b35c_obsrag_build_usage_part1.json`(前次中断的 2 库,已另存不覆盖)、`results/b35c_obsrag_run.log` + `results/b35c_obsrag_run_part1.log` |
| 墙钟 | 本次续跑 **1233.5 s**(20.6 min,13 库 50 题);前次中断段(2 库 8 题)未完整埋点,建库合计 149.3 s。全程 ≈ 24 min,**远低于 3 h 上限** |
| 建库 | 每 uid 一座全新库,零复用(`ObsRagSystem.stores[uid]` 进程内新建,无落盘目录);会话按 `date` 升序写入(`sorted(..., key=lambda s: s.get("date",""))`) |

### 断点续跑的处理(RESUME RULE)

`scripts/repro_batch2.py::main` 原生支持追加续跑,**未动一行**:`done = {json.loads(l)["question_id"] ...}`
从已有 out_p 读出已答 qid,`qs = [q for q in by_uid[uid] if q["qid"] not in done]`,`if not qs: continue`
连该库的建库都跳过。跑前核对:已有 8 行(uid `wikiP108035-Q39407125` / `wikiP108021-Q37837264` 各 4 题),
8 个 question_id 全部唯一、`judge_correct` 非空、`answer` 非空、无 FALLBACK 判官行 → **不需要挪走旧文件**,
直接续跑,只补齐缺失的 50 题(13 库)。既有判决行一行未丢、未重判、未覆盖。
仅把会被观测壳重写的侧文件 `b35c_obsrag_build_usage.json` / `b35c_obsrag_run.log` 复制成 `*_part1.*` 保留,
建库用量按两份 per_uid 合并(15 库不重不漏)。

## 二、脚本改动

**本轮对仓库脚本的改动:0 行。** `scripts/repro_batch2.py` 的 b35c 接线(`--vols / --uids-file /
--questions-file / --out / --store-root`)在本轮开始前已存在于工作区(`git diff` 42+/6-),
完全按 README §二 的统一骨架:只替换 `main()` 的装载段(`vols` 取代 `VOLS`、`by_uid` 从 questions-file 重建、
`picked` 从 uids-file 取代 `sample_stores()`、`out_p` 走 `--out`),另加 mem0 专用的 `--store-root`。
`ObsRagSystem`(写侧提示、`max_tokens=300`、`temperature=0`、`TOPK=5`、`- {content[:300]}` 截断)、
`READER_MODEL` / `READER_SYS` / `max_tokens=300` / 读者三次重试 / `ClaudeJudge()` **逐行未动**。

唯一新增的是一个**只读观测壳**(不在仓库内,位于本会话 scratchpad):
`C:\Users\25243\AppData\Local\Temp\claude\D--ZZL-cluade\127d6855-ac31-4f09-a027-67dbfc5cf191\scratchpad\b35c_run_obsrag.py`。
它 monkey-patch 四处、每处都原样转发 `*args/**kwargs` 后只累加计数,不改任何入参:
`anthropic.resources.messages.Messages.create`(按模型累计 in/out/calls)、
`openai.resources.embeddings.Embeddings.create`(累计 total_tokens)、
`qvf.judge.ClaudeJudge.judge`(从返回的 JudgeResult 累计判官 usage)、
`repro_batch2.ObsRagSystem.ingest`(前后快照差分 → 每库建库秒/观察句数/haiku token/嵌入 token)。
作用是补上 README 标注的 "repro_batch2 建库 token **未埋点**" 这个缺口,让建库 $ 从实测而非估计得出。

## 三、结果

### 总体(n=58,15 库)

| 指标 | 值 |
|---|---|
| **准确率** | **13.79%**(8 / 58) |
| 读者输入 token 均值 | **210.1**(合计 12,184) |
| 读者输出 token 均值 | **74.9**(合计 4,346) |
| `latency_s` 中位 | **4.75 s**(均值 5.06) |
| 建库 | **75.25 s/库**(中位 74.23;15 库合计 1,128.8 s)= **19.46 s/题** |
| 检索条数 | 全部 58 行 `memories_n = 5`(TOPK=5,零空检索) |
| 空答案 / FALLBACK 判官 | 0 / 0 |

### 分题型

| 题型 | 正确/总 | 准确率 |
|---|---|---|
| change_count | 2 / 15 | 13.33% |
| count_before | 2 / 15 | 13.33% |
| first_vs_last | 2 / 15 | 13.33% |
| longest_tenure | 2 / 13 | 15.38% |

### 与 60 题标定场存档的对照(不同题集,仅供量级参照,非配对比较)

| | 60 题存档 `results/wsc_s5_obsrag.jsonl` | 本轮 b35c 58 题 |
|---|---|---|
| acc | 13.33%(8/60) | **13.79%**(8/58) |
| in / out 均值 | 202.4 / 71.7 | **210.1 / 74.9** |
| 延迟中位 | 5.16 s | **4.75 s** |
| 建库 | 67.26 s/库(合计 1008.9) | **75.25 s/库**(合计 1128.8) |

建库变慢 ≈12%,与 v2.5 每库会话数更多一致(15 库合计 **504 个会话**,33–36/库;存档 v1 每库 ~33)。

### 建库内部用量(实测,15 库合并 part1+part2 的 per_uid)

| 项 | 值 |
|---|---|
| haiku 写侧调用 | **504 次**(= 504 个会话,严格每会话一次) |
| haiku 写侧 token | in **222,357** / out **90,129** |
| 抽出的 observations | **4,267 条**(≈284 条/库,≈8.5 条/会话) |
| 嵌入 token(建库) | **79,298**(text-embedding-3-small) |

### 成本(项目冻结价目表:haiku-4-5 \$1/\$5 per M;claude-opus-5 \$5/\$25;embedding-3-small \$0.02/M)

| 项 | 计量来源 | \$ |
|---|---|---|
| 建库 haiku | 实测 222,357 in / 90,129 out | **0.6730** |
| 建库嵌入 | 实测 79,298 tok | 0.0016 |
| 读者 haiku | jsonl 58 行 12,184 in / 4,346 out | **0.0339** |
| 检索侧嵌入 | 实测 ≈1,578 tok | 0.00003 |
| **读者+建库小计(预算闸口)** | | **\$0.709**(上限 \$5) |
| 判官 claude-opus-5 | 实测 54 次 9,819 in / 5,265 out | 0.1807 |
| 判官(前次中断段 4 次未埋点) | 按 54 次均值外推 ≈724 in / 369 out | ≈0.013(**估计**) |
| **含判官合计** | | **≈ \$0.90** |

## 四、与 60 题协议的偏离

1. **题集/语料/库清单换成 v2.5 小样本**(这正是 b35c 的目的):`data/wikistate_full_ALL_v25.json`、
   `results/b35c_sample_uids.txt`(15 uid)、`results/b35c_questions.jsonl`(58 题)。n 从 60 → 58
   (`wikiP551000-Q19845625` 与 `wikiP551008-Q29918442` 各只有 3 题)。库数仍为 15,但 uid 与存档零重叠。
2. **top-5 而非 k=10**:`ObsRagSystem.TOPK = 5`,其论文配方,README §一 明列为冻结例外,与 60 题标定场一致,**未改**。
3. **记忆行截断 300 字符**(`- {h.content[:300]}`),repro_batch2 家族冻结常量,与 60 题标定场一致,**未改**。
   (README §一 的 400 是 repro_batch4 家族的值,不适用于本 harness。)
4. 读者 `claude-haiku-4-5` / `temperature=0` / `max_tokens=300` / `READER_SYS` 逐字、检索空回退串、三次重试:**全部未改**。
   判官 `qvf.judge.ClaudeJudge()` 默认档 = `claude-opus-5`(环境变量 `QVF_JUDGE_MODEL` 未设,已核):**未改**。
5. 无并行(单线程,条目级并行 = 1,低于 ≤4 的上限)。
6. **本轮为续跑**:8 行(2 库)来自 2026-09-03 19:58 被中断的同一命令、同一脚本、同一协议常量;
   50 行(13 库)来自本轮。两段之间脚本与协议常量无任何变化,故合并计分。**唯一后果**是前次那 8 题里
   有 4 题的判官 token 未被观测壳捕获(侧文件在这些调用之前就已落盘,进程随后被杀,`finally` 的最终 dump 未执行),
   上表中已单独标为估计;准确率、读者 token、延迟、建库秒数四项**全部为实测,不含估计**。
7. obsrag 无落盘店目录(检索器在进程内),因此未使用 `--store-root`,也未写入任何既有店目录。

## 五、可复现命令

```
cd D:\ZZL_cluade
set PYTHONUTF8=1
python scripts\repro_batch2.py --system obsrag ^
  --vols data/wikistate_full_ALL_v25.json ^
  --uids-file results/b35c_sample_uids.txt ^
  --questions-file results/b35c_questions.jsonl ^
  --out results/b35c_obsrag.jsonl
```
(本轮通过上述只读观测壳调用同一 `main()`,以额外记录建库 token;不用观测壳直接跑这条命令,
除 `b35c_obsrag_build_usage.json` 外结果完全相同。)
