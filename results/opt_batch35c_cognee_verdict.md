# 批 35c 判决:cognee 1.5.3 × WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。系统:**cognee**(LLM 知识图谱路线,`add → cognify`,检索取 CHUNKS 喂我方同款读者)。
状态:**done** —— 58/58 题全部作答并判分,零缺题、零重复、零多题。

## 1. 判决

**猜想被证实**:cognee 在 v2.5 58 题上落在"中游偏下"档,acc **44.83%**(26/58),与 v1 60 题存档 46.67% 同一量级。
分题型看,它只在 `first_vs_last`(首末对照)上像样(73.33%),三类需要**跨会话计数 / 时序聚合**的题(change_count、
count_before、longest_tenure)全部塌在 33–38%,即"取回 10 个 chunk 让读者自己数"这条路对聚合题不成立。
检索侧本身没有失灵:58 题全部取满 10 条记忆(`memories_n` 均值 10.00,零空检索),失败发生在聚合而非召回。

## 2. 实际运行

命令(主环境 Python 3.14.5,`PYTHONUTF8=1 PYTHONIOENCODING=utf-8`;后台启动,前台轮询到结束):

```
python scripts/repro_batch4.py --system cognee \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file results/b35c_sample_uids.txt \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_cognee.jsonl \
  --store-root results/b35c_cognee_stores2
```

- 语料 `data/wikistate_full_ALL_v25.json`;15 库(`results/b35c_sample_uids.txt` 顺序);58 题(`results/b35c_questions.jsonl`)。
- 每库全新数据集:`cognee.add(sess_text(s), dataset_name=uid)` 逐会话(**按 date 升序**)→ `cognify(datasets=[uid])`;
  读侧 `search(query_text, SearchType.CHUNKS, datasets=[uid], top_k=10)`,取 `search_result[].text`,记忆行 `- {text[:400]}`。
- 读者 `claude-haiku-4-5` / `temperature=0` / `max_tokens=300` / `READER_SYS` 逐字未改;判官 `qvf.judge.ClaudeJudge()`
  默认档 `claude-opus-5`(`QVF_JUDGE_MODEL` 未设,已核)。k=10,截断 400——与 60 题标定场一致。
- 落盘:`results/b35c_cognee_stores2/`(system+data 根,15 数据集,504 条会话,397 MB;`cognee_db` 内 `datasets=15`、`data=504`)。
  **未写** cognee 全局根,也未写入上一次中断留下的 `results/b35c_cognee_stores/`(28 MB,只含 wikiP108035 一库)。
- 运行日志:`results/_b35c_cognee_run2.log`(stdout)、`results/_b35c_cognee_run2.err`(cognee 日志);
  上一次中断的日志为 `results/_b35c_cognee_run.log`。

### 断点续跑(RESUME)

`results/b35c_cognee.jsonl` 在本次开始前已有 **2 行**已判决结果(wikiP108035-Q39407125 的 `_v2cc` / `_v2cb`,
上一次尝试在第 3 题 `longest_tenure` 检索完成后被杀)。`repro_batch4.py::main` 是**追加写 + 按 `question_id` 跳过**
(`done = {…}`,`qs = [q for q in by_uid[uid] if q["qid"] not in done]`),所以本次只作答缺失的 **56 题**,
两行旧判决原样保留、未被覆盖或丢弃(无需 `_part1` 分文件与合并)。

唯一副作用:harness 对"还有缺题"的库会无条件重新建库,而 cognee 的 `add` 是往同名 dataset 追加。为避免把 wikiP108035
的 33 条会话灌进已存在的数据集(会重复成 66 条),本次改用**全新店根** `results/b35c_cognee_stores2`,
该库因此被**重新全新建库一次**(34.4 s),其余 14 库均为首次建库。结论:15 座库全部是"全新库、按日期升序摄入",
无旧库复用;代价是 wikiP108035 的前 2 题与后 2 题分别命中两座**同协议、同语料、独立重建**的库(见 §5 偏离 D-1)。

## 3. 结果(全部由本次写出的 `results/b35c_cognee.jsonl` 现算)

| 指标 | 值 |
|---|---|
| n | 58(= 题集 58 个 qid,精确匹配,无缺/多/重) |
| accuracy | **44.83%**(26/58) |
| 读者 input token 均值 | 1198.1(合计 69,488) |
| 读者 output token 均值 | 84.1(合计 4,877) |
| `latency_s` 中位 | **6.33 s**(均值 6.53,min 5.15,max 9.88) |
| 建库 | **33.3 s/库**(中位 33.9,15 库合计 499.6 s)= **8.6 s/题** |
| `memories_n` | 均值 10.00(58/58 题取满 10 条,零空检索) |
| 墙钟 | 本次约 14.4 min(20:42→20:56:24)+ 上次中断段约 1.4 min ≈ **16 min** |

分题型:

| 题型 | 正确/题数 | acc | in 均值 | out 均值 | 延迟中位 |
|---|---|---|---|---|---|
| change_count | 5/15 | 33.33% | 1210.7 | 68.1 | 5.98 s |
| count_before | 5/15 | 33.33% | 1191.5 | 93.3 | 6.38 s |
| longest_tenure | 5/13 | 38.46% | 1200.8 | 109.2 | 6.79 s |
| first_vs_last | 11/15 | **73.33%** | 1189.6 | 69.1 | 6.29 s |

每库建库秒(`build_s`,本次 15 次建库):
29.1 / 29.6 / 29.7 / 30.6 / 31.3 / 32.8 / 33.5 / 33.9 / 34.3 / 34.4 / 34.5 / 35.0 / 35.5 / 36.6 / 38.8。
(另:上次中断时 wikiP108035 建库 36.8 s,已计入两行旧结果的 `ingest_seconds`,未计入上面 15 库统计。)

## 4. 成本

| 项 | token | $ | 口径 |
|---|---|---|---|
| 读者 haiku-4-5 | 69,488 in / 4,877 out | **$0.0939** | 实测(行内 `usage_*`,$1/$5 per M) |
| 判官 claude-opus-5 | 11,026 in / 4,395 out(56 次) | **$0.1650** | 实测(进程末 `judge.total_usage`,$5/$25 per M) |
| 判官(旧 2 行,上次进程) | ≈394 in / 157 out | ≈$0.0059 | 按本次均值外推 |
| 建库 cognify(gpt-4o-mini + text-embedding-3-small) | **未测得** | ≈$0.80(15 库,≈$0.053/库) | **估计**,取自 `results/repro_batch4b_verdict.md:34` 的批级估计 |
| 合计 | — | **≈$1.06** | 其中实测 $0.265,其余为估计 |

建库用量为何未测得:harness 里的埋点是 `litellm.success_callback` 被动回调,cognee 1.5.3 的调用路径没有触发它,
`results/b35c_cognee_stores2/usage_build.jsonl` 15 行的 `llm_in/llm_out/emb_tok` 全为 0,`usage_total.json` 同样全 0;
cognee 自带的 `session_model_usage` 表也是空表(已查 `cognee_db`)。因此建库 $ 只能引用存档批级估计,**不得当作实测值**。
预算闸门:实测支出 $0.265 + 估计建库 $0.80 ≈ $1.06 ≪ $5;墙钟 16 min ≪ 3 h,15 库全跑,无裁库。

## 5. 与 60 题标定协议的偏离

- **D-1(本次唯一实质偏离)**:wikiP108035-Q39407125 的 4 题分属两座独立重建的库——`_v2cc`/`_v2cb`(上次中断前判决,
  店根 `results/b35c_cognee_stores`,建库 36.8 s)与 `_v2lt`/`_v2fl`(本次,店根 `results/b35c_cognee_stores2`,建库 34.4 s)。
  两次建库同语料、同顺序、同协议,但 cognee 的图抽取不保证逐字复现,故这一库的 4 题不是同一座库的产物。
  按"绝不丢弃已判决行"的规则保留旧行;若要求单库同源,需重跑该库 4 题(约 1 min + 约 $0.06)。
- **D-2**:两行旧结果缺 `build_s` 字段(写它们时脚本尚未加该字段),只有语义相同的 `ingest_seconds`;
  汇总按 README §一 的 `build_s = row.get("build_s", row.get("ingest_seconds"))` 读取,数值无损。
- **D-3**:店根改为 `results/b35c_cognee_stores2`(README §三.8 写的是 `results/b35c_cognee_stores`),原因见 §2 断点续跑;
  两者都不是 cognee 全局根,均符合"新批新目录、不得原地覆盖"。
- **D-4**:建库 token/$ 未埋点成功(见 §4),该系统的建库成本在本轮**没有实测值**。
- 其余全部与标定场一致:语料按 `date` 升序、`sess_text` 前 6 轮 × 400 字符、k=10、记忆行 400 字符截断、
  读者模型/温度/max_tokens/READER_SYS 逐字未改、判官 `ClaudeJudge()` 默认 `claude-opus-5`、失败重试 3 次、单进程串行(无并行)。
- **不得**与 v1 60 题存档(46.67%)直比:题面版本(_v2cc/cb/lt/fl)与库集合都不同;比较只在 b35c 内部按 `question_id` 配对。

## 6. 脚本改动

本次**未新增任何代码**。`scripts/repro_batch4.py` 的 b35c 接线在本次开跑前就已存在于工作区(未提交,由上一次尝试写入),
本次只做核对后原样使用,核对结论:

- `main()` 装载段新增 `--vols / --uids-file / --out / --store-root / --amem-repo`,并把 `picked = [u for u in picked if u in by_uid]`
  提到 `--uids-file` 之后(否则 b35c uid 与 `sample_stores()` 的 v1 15 库交集为空,会一题不跑);
- `CogneeSystem.set_store_root()`:调 `cognee.config.system_root_directory()` / `data_root_directory()`,并写 `usage_build.jsonl` sidecar;
  `__init__` 挂 `litellm.success_callback` 被动计量(本轮未生效,见 §4);
- 结果行新增 `build_s`(与 `ingest_seconds` 同值,后者保留)与 `**row_extra / **store_extra`(cognee 两者都为空);
- **协议常量零改动**:`READER_MODEL / READER_SYS / max_tokens=300 / temperature=0 / top_k=10 / 400 字符截断 / ClaudeJudge()`
  与 `sess_text()` 逐行未动;`repro_batch2.py` 的改动只涉及 mem0 店根与同款 CLI,`READER_MODEL/READER_SYS` 未被触碰(已 diff 核对)。
- 未做 git 提交(按硬规)。

## 7. 产出文件

- `D:\ZZL_cluade\results\b35c_cognee.jsonl` —— 58 行结果(2 行沿用上次判决 + 56 行本次)
- `D:\ZZL_cluade\results\opt_batch35c_cognee_verdict.md` —— 本文件
- `D:\ZZL_cluade\results\b35c_cognee_stores2\` —— 15 座新库(397 MB)+ `usage_build.jsonl`(15 行,token 列全 0)
- `D:\ZZL_cluade\results\_b35c_cognee_run2.log` / `_b35c_cognee_run2.err` —— 本次运行日志
