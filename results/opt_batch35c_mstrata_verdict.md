# b35c · mstrata(MemStrata 式写入盖章台账)× WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。判决:**跑通,58/58 题全部作答并判定,零读者失败、零检索空集;准确率 13.79%(8/58)**。
该数值与 v1 60 题存档(`results/wsc_s5_mstrata.jsonl`,11.67%)量级一致,但两者题面不同,**不得直比**
(存档 `_s5a..d`,b35c 为 `_v2cc/cb/lt/fl`);b35c 的系统间比较只在 b35c 内部按 `question_id` 配对。

结果文件:`D:\ZZL_cluade\results\b35c_mstrata.jsonl`(58 行)
运行日志:`D:\ZZL_cluade\results\b35c_mstrata_run.log`、`D:\ZZL_cluade\results\_b35c_mstrata_resume.out`

---

## 一、跑了什么

| 项 | 取值 |
|---|---|
| 语料 | `data/wikistate_full_ALL_v25.json`(144 条目;15 个 b35c uid 全部命中) |
| 库清单 | `results/b35c_sample_uids.txt`(15 行,按文件顺序建库) |
| 题集 | `results/b35c_questions.jsonl`(58 题;13 uid × 4 + `wikiP551000-Q19845625` / `wikiP551008-Q29918442` 各 3) |
| 每库建库 | 每 uid 一座全新台账,库间零共享;会话按 `date` 升序逐条写入(每库 33–36 会话,15 库合计 504 会话) |
| 写侧 | 每会话一次 `claude-haiku-4-5` 三元组抽取(`max_tokens=500`,`temperature=0`,提示词逐字未改)→ `(s,r)` 键台账:异值取代(旧行 `superseded=True`)、同值无操作 |
| 读侧 | 仅活跃行建 `qvf.retrieval.OpenAIDenseRetriever`(text-embedding-3-small),`retrieve(top_k=10)`;记忆行 `- [since {valid_from}] {s} {r}: {o}`,截 **300** 字符(该 harness 冻结值) |
| 读者 | `claude-haiku-4-5`,`temperature=0`,`max_tokens=300`,`READER_SYS` 逐字,user = `MEMORIES:\n{memtext}\n\nUSER'S NEW MESSAGE: {question}` |
| 判官 | `qvf.judge.ClaudeJudge()` 默认档 = `claude-opus-5`(`QVF_JUDGE_MODEL` 未设,本轮已核) |
| 环境 | 主环境(Python 3.14,`anthropic 0.121.0`);**不需要**隔离 venv。`ANTHROPIC_API_KEY`(.env)+ `OPENAI_API_KEY`(环境) |
| 店目录 | 无落盘(mstrata 台账与检索器均在内存);未写入任何既有店目录 |

### 命令(续跑轮,本轮实际执行)

```
set PYTHONUTF8=1 & set PYTHONIOENCODING=utf-8
python scripts/b35c_mstrata_run.py --system mstrata ^
  --vols data/wikistate_full_ALL_v25.json ^
  --uids-file results/b35c_sample_uids.txt ^
  --questions-file results/b35c_questions.jsonl ^
  --out results/b35c_mstrata.jsonl
```

`scripts/b35c_mstrata_run.py` 是 `scripts/repro_batch4.py::main()` 的零改写包装:只在
`MemStrataSystem.ingest` 之后追加一行诊断打印(台账总行/活跃行/首行 memory_id/会话日期跨度),
用于事后核 `OpenAIDenseRetriever` 类级缓存键跨库碰撞。**不触碰任何协议常量、提示词、检索或输出逻辑。**

### 断点续跑(RESUME)处理

前一轮在第 3 库建库中途被打断,`results/b35c_mstrata.jsonl` 已存 **8 行**
(`wikiP108035-Q39407125` / `wikiP108021-Q37837264` 各 4 题),无残缺行。
核过 `repro_batch4.py::main()`:输出文件以 `"a"` 打开、开跑前读入 `done = {question_id}` 并
`qs = [q for q in by_uid[uid] if q["qid"] not in done]`,`qs` 为空即 `continue`(该库不重建)。
**该 harness 追加且跳过已完成 id,因此直接原地续跑,未移走任何文件,零判定行被丢弃**;
本轮新答 50 题 / 新建 13 库,合并后 58 行。核验:`question_id` 集合与 58 个 qid 精确相等,
无重复、无缺失、无多余,`gold_answer` 与题集逐题一致。

**schema 说明**:前 8 行由旧版 harness(md5 `dfdecd09…`)写出,只有 `ingest_seconds` 没有 `build_s`;
新 50 行两者都有且同值。按 README `build_s = row.get("build_s", row.get("ingest_seconds"))` 读取,
15 库建库秒完整可得。除该新增字段外,两版 `MemStrataSystem` 与读者/判官逐行相同(见下节 diff)。

---

## 二、脚本改动摘要

**本轮未新增任何改动**——`scripts/repro_batch4.py` 的 b35c 接线在前一轮已写入(工作区已修改、未提交),
本轮逐行核对确认其只动装载段与字段追加,协议常量原封不动:

| 改动 | 性质 |
|---|---|
| `--vols / --uids-file / --out / --store-root / --amem-repo` 五个新参数 | 纯 CLI 接线 |
| `vols = a.vols.split(",") if a.vols else VOLS`;`out_p = ROOT / a.out if a.out else <原默认>` | 装载段,默认值等价原行为 |
| `picked` 在 `--uids-file` 给出时改为读文件(保持文件顺序);`picked = [u for u in picked if u in by_uid]` 由 `--questions-file` 分支内提到分支外 | 装载段 |
| `--questions-file` 读取加 `if l.strip()` 空行保护 | 装载段 |
| 结果行追加 `"build_s"`,以及 `**row_extra` / `**store_extra[uid]`(mstrata 两者皆无属性 → 展开为空) | 只增字段 |
| `AmemSystem` 路径参数化 / `CogneeSystem` 用量埋点与 `set_store_root` | 其它系统,mstrata 不经过 |

**`MemStrataSystem` 类(抽取提示词、`max_tokens=500`、`temperature=0`、台账取代规则、活跃行读路径、
`top_k=10`、`[:300]` 截断)与读者块(模型/温度/max_tokens/`READER_SYS`/user 模板/3 次重试)、
判官调用逐行未改。** 60 题标定场协议在 mstrata 上完整保持。

---

## 三、数字(全部由 `results/b35c_mstrata.jsonl` 现算)

### 总表

| 指标 | 值 |
|---|---|
| n | **58**(= 58 题全集) |
| 准确率 | **13.79%**(8/58) |
| 读者输入 token 均值 | **319.8**(合计 18,550) |
| 读者输出 token 均值 | **75.6**(合计 4,382) |
| `latency_s` 中位 | **4.63 s**(均值 4.89,范围 3.74–7.91) |
| 建库 | **67.8 s/库**(中位 66.8;15 库合计 1,016.9 s;= 17.5 s/题) |
| 检索命中 | 每题 `memories_n = 10`(58/58,零空集) |
| 读者失败 | 0(无 `usage_input_tokens == 0` 行) |

### 分题型

| 题型 | n | 准确率 | in 均值 | out 均值 | 延迟中位 |
|---|---|---|---|---|---|
| change_count | 15 | 26.67%(4/15) | 327.5 | 77.5 | 4.42 s |
| count_before | 15 | 13.33%(2/15) | 314.6 | 84.5 | 4.47 s |
| first_vs_last | 15 | 6.67%(1/15) | 313.1 | 62.6 | 4.51 s |
| longest_tenure | 13 | 7.69%(1/13) | 324.8 | 78.0 | 5.27 s |

形态与预注册预测一致:活跃行读路径把被取代的历史整体丢弃,聚合类题(需要跨版本计数与时长比较)
因此塌到近底噪;change_count 略高是因为"取代次数"偶尔还残留在活跃行的 `[since …]` 日期上。

### 每库建库秒(15 库,去重后)

| uid | 会话 | build_s | uid | 会话 | build_s |
|---|---|---|---|---|---|
| wikiP108035-Q39407125 | 33 | 71.1 | wikiP551008-Q29918442 | 33 | 69.2 |
| wikiP108021-Q37837264 | 33 | 66.8 | wikiP551000-Q19845625 | 33 | 66.2 |
| wikiP108048-Q38640679 | 33 | 67.8 | wikiP551001-Q20667184 | 34 | 65.8 |
| wikiP108008-Q53283502 | 33 | 63.8 | wikiP551007-Q9153879 | 33 | 66.2 |
| wikiP39036-Q15039950 | 33 | 67.8 | wikiP54031-Q16198306 | 34 | 66.6 |
| wikiP39003-Q6248447 | 33 | 63.4 | wikiP54003-Q26001185 | 34 | 68.0 |
| wikiP39033-Q5331705 | 36 | 76.3 | wikiP54001-Q16225986 | 34 | 65.5 |
| wikiP39017-Q24568849 | 35 | 72.4 | | | |

存档 v1 为 52.2 s/库(33 会话);b35c 67.8 s/库,涨幅主要来自 v2.5 会话文本更长与本机 run 间抖动。

### 成本

| 项 | token | 单价 | $ |
|---|---|---|---|
| 读者 haiku-4-5(实测,58 题) | 18,550 in / 4,382 out | $1.00 / $5.00 per M | **0.0405** |
| 判官 claude-opus-5(50 次实测 9,108/4,174,按 182.2/83.5 每次外推到 58 次) | 10,565 in / 4,842 out | $5.00 / $25.00 per M | **0.174**(估计) |
| 建库 haiku 抽取(harness 未埋点;10 次同提示词采样实测均值 439.9 in / 202.0 out,× 504 会话外推) | 221,710 in / 101,808 out | $1.00 / $5.00 per M | **0.731**(估计,$0.049/库) |
| 嵌入 text-embedding-3-small(未埋点;15 库 × ≈158 活跃行 + 58 查询,量级估算) | ≈33 k | $0.02 per M | ≈0.001(估计) |
| 上述采样测量本身(10 次 haiku) | 4,399 in / 2,020 out | — | 0.014 |
| **合计** | | | **≈ $0.96**(实测部分 $0.055,其余为标注的估计) |

预算闸门 ≤ $5:**通过**(≈$0.96)。建库外推值 $0.049/库 与存档判决 `results/repro_batch4b_verdict.md:34`
的批级估计 ≈$0.06/库 同量级,互相印证。

### 墙钟

- 本续跑轮:13 库建库 879.0 s + 50 题读答判 244.8 s ≈ **18.7 min**(单进程串行,无并行)。
- 前一轮已完成的 2 库计入后,15 库全量口径 ≈ 21 min。
- 预算闸门 ≤ 3 h:**通过**。全部 15 库均已跑完,**未做任何 N-库截断**。

---

## 四、与 60 题标定场协议的偏离

1. **无协议偏离。** 语料/题集/uid 三项按 b35c 规范换掉(这是本批设计),读者模型、温度、`max_tokens`、
   `READER_SYS`、user 模板、重试次数、`top_k=10`、记忆行 300 字符截断、判官类与默认模型、
   会话段落化 `sess_text`(日期前缀 / 前 6 轮 / 每轮 400 字符)、按 `date` 升序摄入,全部与存档一致。
2. **结果文件混版 schema**:前 8 行无 `build_s` 键(仅 `ingest_seconds`,同值),见 §一。不影响任何统计。
3. **建库 token 未埋点**:该 harness 不记写侧用量,§三的建库 $ 是 10 次采样外推的**估计值**,已逐处标注;
   判官 $ 中 8 行(前一轮进程)未落盘用量,按本轮 50 次实测均值外推,同样标为估计。
4. **`OpenAIDenseRetriever` 类级缓存键**(`(model, memories[0].memory_id, len(memories))`)是该检索器的
   既有行为,本轮未改。事后核 15 库诊断行:15 个 `(首行 valid_from, 活跃行数)` 二元组**两两互异**
   (最接近的一对为 `1807-01-01/164` 与 `2007-01-01/164`,首行 id 不同),**零跨库缓存碰撞**,
   每库嵌入均为独立计算。
5. **不与 v1 存档 11.67% 直比**(题面不同,见开篇)。
