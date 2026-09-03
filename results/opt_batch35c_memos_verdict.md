# 批 35c 判决:MemOS(MemTensor,MemoryOS 2.0.32,general_text + 内嵌 Qdrant)× WikiState v2.5 小样本(15 库 / 58 题)

状态:**RUN 完成**(58/58,单臂:claude-haiku-4-5 抽取器)。
日期 2026-09-03。结果文件 `D:\ZZL_cluade\results\b35c_memos.jsonl`(58 行,`question_id` 集合与
`results/b35c_questions.jsonl` 的 58 个 qid 精确一致:无缺、无多、无重复)。
本文件所有数字均从该 jsonl 现场重算,判官/读者用量取自运行日志与行内字段。

---

## 1. 判决

**MemOS 在 v2.5 小样本考场落在 31.03%(18/58)。**
四类聚合题全部低于 50%:`count_before` 20.00% 最弱,`first_vs_last` 40.00% 最强。
每库检索恒为 top-10(58 题全部 `memories_n = 10`),而每库写入 125–148 条记忆节点
(504 会话 → 2079 条,≈4.13 条/会话,抽取零报错):**写侧扩张、读侧只端回 10 条**,
需要全序列的计数/时序题因此结构性缺料。这与 H4 判决在 v1 60 题上的机制观察一致,
但**分数不得与 v1 存档的 45.00 直比**(题面版本不同,见 §6)。

同台比较只能在 b35c 内部按 `question_id` 配对,本次只跑了 memos 一系统,故本文件不给排名。

---

## 2. 实际执行

### 2.1 断点续跑(RESUME)

接手时 `results/b35c_memos.jsonl` 已有 **12 行已判决**(3 个 uid:`wikiP108021-Q37837264`、
`wikiP108035-Q39407125`、`wikiP108048-Q38640679`,各 4 题;均 `memos_llm_model=claude-haiku-4-5`),
是上一次被中断的尝试留下的。核查 `scripts/repro_batch33h_memos.py:293-298`:输出文件以 `"a"` 追加打开,
且启动时把已存在行的 `question_id` 读进 `done`,`run_uid` 里 `qs = [q for q in by_uid[uid] if q["qid"] not in done]`,
`if not qs: return` —— **追加且跳过已完成 id,且已完成的 uid 连建库都不会触发**。
故按 RESUME 规则第一分支处理:**不移走原文件,直接续跑,只答缺失的 46 题**;
另在 scratchpad 存了一份 12 行备份(`.../scratchpad/b35c_memos_backup_12rows.jsonl`),未丢任何已判决行。

`results/b35c_memos_stores/` 下当时有 6 个目录:3 个是上述已完成库,3 个
(`wikiP108008-Q53283502`、`wikiP39003-Q6248447`、`wikiP39036-Q15039950`,各 ~1 MB)是**中断时的半成品**。
按"每库全新、不复用旧店"与"不得覆盖既有店目录"两条,本次 12 个待跑库一律写入**新根**
`results/b35c_memos_stores_r2/`,半成品目录原封不动留在旧根、未被读写。

### 2.2 命令(实跑,一次成功,无重试)

```
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
D:\ZZL_cluade\.venv_memos\Scripts\python.exe scripts/repro_batch33h_memos.py \
  --workers 3 --llm-model claude-haiku-4-5 \
  --llm-api-base "https://api.anthropic.com/v1/" --llm-api-key-env ANTHROPIC_API_KEY --drop-top-p \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file results/b35c_sample_uids.txt \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_memos.jsonl \
  --store-root results/b35c_memos_stores_r2
```

工作目录 `D:\ZZL_cluade`,detached 启动(pid 22044),stdout/stderr →
`results/b35c_memos_run2.log` / `results/b35c_memos_run2.err`。
墙钟:20:41:05 → 20:56:32 = **15 分 27 秒**(12 库 / 46 题,3 线程并行)。
脚本自报尾行:`memos: 31.03% (n=58)`、`judge usage: {'input_tokens': 9715, 'output_tokens': 3699, 'calls': 46}`。

环境:`.venv_memos`(Python 3.12.10,`MemoryOS 2.0.32`,`anthropic 0.121.0`,`qdrant-client` 本地嵌入模式,无 Docker)。
`ANTHROPIC_API_KEY` 由脚本 `load_dotenv(D:\ZZL_cluade\.env)` 载入(抽取器 + 读者 + 判官),
`OPENAI_API_KEY` 取自环境(仅 text-embedding-3-small 嵌入)。

### 2.3 脚本改动摘要

**本次未改任何脚本代码。** `scripts/repro_batch33h_memos.py` 的 b35c 接线在我接手前就已存在于工作树
(未提交,`git diff` = +27 / −3 行),我逐行核对后原样使用:

- 新增 5 个纯装载参数:`--vols / --uids-file / --questions-file / --out / --store-root`;
- `store_root` 与 `out_p` 改为"给了参数用参数,否则保持原默认";
- `entries` 从 `--vols` 指定的语料装载(否则仍是 `repro_batch2.VOLS`);
  `--questions-file` 给出时按 `uid` 重建 `by_uid`;`--uids-file` 给出时替换 `sample_stores()` 的 `picked`;
  末尾 `picked = [u for u in picked if u in by_uid]`;
- 结果行加一个 `build_s`(值 = `round(ingest_s,1)`,与既有 `ingest_seconds` 同值,`ingest_seconds` 未删)。

**协议常量一处未动**:读者 `claude-haiku-4-5` / `temperature=0` / `max_tokens=300` / `READER_SYS`、
user 模板、失败重试 3 次、`TOP_K=10`、判官 `qvf.judge.ClaudeJudge()`、
`sess_text`(日期前缀 + 前 6 轮 × 400 字符)、记忆行 `f"- {it.memory}"`(**memos 臂冻结为不截断**)、
`MemOSSystem` / `run_uid` 主体、会话按 `date` 升序、每 uid 一只全新 `GeneralMemCube`。

---

## 3. 同台数字(n = 58;判官 = ClaudeJudge/claude-opus-5;读者 = claude-haiku-4-5)

| 项 | 值 |
|---|---|
| n | 58(15 库;13 库 4 题、2 库 3 题) |
| **准确率** | **31.03%(18/58)** |
| 读者 in-token 均值 | **613.0**(合计 35,552) |
| 读者 out-token 均值 | **92.4**(合计 5,361) |
| `latency_s` 中位 | **5.02 s**(均值 5.25,最大 9.50) |
| 每题检索条数 | 恒为 10(58/58) |
| 建库 | **207.8 s/库**(中位 206.0;15 库合计 3,116.8 s = 53.7 s/题) |
| 落盘店 | 新根 12 库 27 MB(≈2.2 MB/库);旧根 3 库 + 3 个半成品 9.7 MB |

### 分题型

| 题型 | 正确/总 | acc |
|---|---|---|
| change_count | 4/15 | 26.67% |
| count_before | 3/15 | 20.00% |
| first_vs_last | 6/15 | 40.00% |
| longest_tenure | 5/13 | 38.46% |

### 分库(15 库)

| uid | 正确/题 | build_s | 保留记忆条数 |
|---|---|---|---|
| wikiP108048-Q38640679 | 3/4 | 202.6 | 137 |
| wikiP108035-Q39407125 | 1/4 | 216.4 | 147 |
| wikiP108021-Q37837264 | 1/4 | 219.2 | 134 |
| wikiP108008-Q53283502 | 2/4 | 195.1 | 130 |
| wikiP39036-Q15039950 | 3/4 | 205.7 | 144 |
| wikiP39003-Q6248447 | 1/4 | 205.0 | 138 |
| wikiP39033-Q5331705 | 0/4 | 220.8 | 148 |
| wikiP39017-Q24568849 | 0/4 | 224.9 | 147 |
| wikiP551008-Q29918442 | 1/3 | 192.3 | 125 |
| wikiP551000-Q19845625 | 1/3 | 212.5 | 138 |
| wikiP551001-Q20667184 | 2/4 | 210.7 | 136 |
| wikiP551007-Q9153879 | 1/4 | 195.5 | 134 |
| wikiP54031-Q16198306 | 1/4 | 206.3 | 146 |
| wikiP54003-Q26001185 | 0/4 | 203.8 | 139 |
| wikiP54001-Q16225986 | 1/4 | 206.0 | 136 |

> 前 3 行(108048 / 108035 / 108021)的 `build_s` 来自上一次中断尝试建的库(store 根
> `results/b35c_memos_stores`),其余 12 行来自本次(根 `results/b35c_memos_stores_r2`)。
> 两批同协议同抽取器,`build_s` 分布一致(195–225 s),故合并计均值。

---

## 4. 成本(建库/嵌入 token 为行内实测,判官为运行实测 + 12 行折算)

价格表按项目冻结口径:haiku-4-5 $1.00/$5.00 per M;claude-opus-5 $5.00/$25.00;
text-embedding-3-small $0.02/M。

| 项 | 用量(15 库 / 58 题) | $ |
|---|---|---|
| MemOS 抽取(claude-haiku-4-5,504 次调用) | 1,085,205 in / 307,158 out | **2.6210** |
| MemOS 嵌入(text-embedding-3-small) | 97,511 tok | 0.0020 |
| 读者(claude-haiku-4-5,58 题) | 35,552 in / 5,361 out | 0.0624 |
| 判官(claude-opus-5,58 题) | 46 题实测 9,715 in / 3,699 out = $0.1411;12 题按 `judge_cost_measured_20260816.md` 均值 198.28/83.45 折算 $0.0369 | ≈0.178 |
| **合计(整份 58 题)** | | **≈ $2.86** |
| 其中**本次会话实际支出**(12 库建库 + 46 题读者/判官) | 870,823 in / 245,280 out 抽取;77,649 tok 嵌入;28,362/4,347 读者;9,715/3,699 判官 | **≈ $2.29** |

**每库建库 $0.1749**(= 2.6230 / 15)。预算闸门:读者+建库支出 $2.29 ≤ $5,墙钟 15.5 min ≤ 3 h,
两条都未触发降级,**15 库全跑,58 题全答,无子采样**。

---

## 5. 偏离 60 题标定协议之处(逐条)

1. **抽取器 = claude-haiku-4-5 + `--drop-top-p`**(头条臂口径)。MemOS 的
   `OpenAILLM._build_request_body` 无条件同时发 `temperature` 与 `top_p`,Anthropic 的 OpenAI
   兼容端点会 400 拒;`--drop-top-p` 只在传输层 `kw.pop("top_p")`,不改 MemOS 的提示词/流程/解析。
   此偏离在 H4 判决即已入档,b35c 原样沿用。
2. **写侧 `temperature=0.7`**(MemOS 出厂默认,不可配),同库重跑记忆条数会漂几条 —— 这是 MemOS 自身
   的常量,未改。
3. **记忆行不截断**(`f"- {it.memory}"`)。README §一说明各 harness 的截断值为冻结常量、b35c 不得统一,
   memos 臂即为"不截断",保持原值。
4. **店根用 `results/b35c_memos_stores_r2`**(不是 README 命名的 `results/b35c_memos_stores`):
   后者已被中断尝试写入 3 个半成品,按"不得覆盖既有店目录 / 不复用旧店"另开新根。12 个待跑库全部新建。
5. **`build_s` 分两批采集**(3 库来自中断尝试、12 库来自本次),见 §3 注。
6. **题面版本**:b35c 是 v2.5 的 58 题(`_v2cc/cb/lt/fl`,change_count 题面已含"首值不计"说明),
   与 v1 60 题存档(`results/wsc_s5_memos_haiku.jsonl`,45.00)**不可直比**。
7. `--workers 3`(与存档同,≤ 4 的并行上限内)。

## 6. 未做

- 未跑 gpt-4.1-mini 对照臂(b35c 只要求头条口径一臂)。
- 未跑 `tree_text` / Neo4j 路线(本机 Docker 不可用,与 H4 同为 BLOCKED)。
- 未做与其它系统的配对统计(McNemar / 簇自助):本任务只跑 memos 一家,配对表留给 `scripts/b35c_score.py` 汇总时做。
- 未执行任何 git 操作。
