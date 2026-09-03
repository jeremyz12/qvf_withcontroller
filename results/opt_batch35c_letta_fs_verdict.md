# b35c 判决:letta_fs(Letta 式文件系统 agent 平凡强基线)× WikiState v2.5 小样本

日期 2026-09-03 · 考场 = `results/b35c_questions.jsonl`(58 题 / 15 库)· 语料 = `data/wikistate_full_ALL_v25.json`
· 判官 = `qvf.judge.ClaudeJudge()`(`claude-opus-5`,全场同一冻结判官)· 结果文件 = `results/b35c_letta_fs.jsonl`

> 本判决的所有数字都从 `results/b35c_letta_fs.jsonl`(58 行,本轮实跑产出)重新计算,
> 计算脚本 `scripts/b35c_score_letta_fs.py`,原始打印留档 `results/b35c_letta_fs_score.txt`。
> 唯一不是实测的一项是**判官花费**(harness 不落判官 usage,只在 `judge.total_usage` 累计),已在 §五标注为估计。

---

## 一、判决

**猜想"文件系统 agent 在 v2.5 聚合题上能靠日期文件名与全库 grep 稳住计数"被否定。**
58 题 acc **43.10%**(25/58)。塌陷面与 v1 标定场同处:两个计数型最差——
`count_before` **26.67%**、`change_count` **40.00%**;两个"取值型"较好——
`first_vs_last` 53.33%、`longest_tenure` 53.85%。
零空答、零"不调工具就答"(58 题全部至少调用一次工具),失败不是"没去查",是查到之后的聚合。

代价面:in-tok 均 **30,191**/题(中位 18,543,max 113,654)、读侧 **$1.9467 / 58 题 = $0.0336/题**,
延迟中位 **12.57 s**。建库仍然近乎免费:**6.9 ms/库**、**$0**(写侧零 LLM、零嵌入)。

---

## 二、实际运行

### 命令(逐字)

```
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python scripts/letta_fs_agent_baseline.py \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file results/b35c_sample_uids.txt \
  --questions-file results/b35c_questions.jsonl \
  --corpus-root results/b35c_letta_fs_corpus \
  --out results/b35c_letta_fs.jsonl > results/b35c_letta_fs_run.log 2>&1
```

- 环境:主环境(Windows,`python` in PATH),仅需 `ANTHROPIC_API_KEY`(`.env`)。无隔离 venv、无 OpenAI、无 Docker。
- 串行、单进程(该 harness 无并行开关);墙钟 **20:44:15 → 20:59:26 = 911 s ≈ 15.2 min**
  (= 58 题 `latency_s` 之和 911.4 s,吻合)。退出码 0,日志末行 `DONE`,`api retry` 出现 **0** 次。
- 断点续跑:本轮开跑前 `results/b35c_letta_fs.jsonl` **不存在**(0 行已判决行),故 RESUME 规则退化为全新起跑;
  没有任何既有已判决行被丢弃或覆盖。harness 本身按 `question_id` 去重续跑
  (`done = {…["question_id"] …}`,`open(out_p,"a")`),若中断可原地重跑补齐。
- 店目录:新建 `results/b35c_letta_fs_corpus/`(15 库 / **504** 个 `.md` / 2.0 MB)。
  既有 `results/letta_fs_corpus` **未被写入**(其 15 个 uid 与 b35c 的 15 个零重叠,且本轮走 `--corpus-root`)。
- 未做 `git commit`。

### 每库建库

每 uid 一座全新的库,`sessions` 按 `date` 升序落成 `s<NNN>__<date>.md`,
内容 = `sess_text(s)`(`(session date: X)` + 前 6 轮 × 每轮 400 字符),与 60 题标定场逐字相同。
15 库文件数 33–36(= 行内 `memories_n`)。

---

## 三、脚本改动(仅 CLI 接线,20 插入 / 1 删除)

唯一改动文件:`D:\ZZL_cluade\scripts\letta_fs_agent_baseline.py`,改动**全部落在 `main()` 的装载段**。

新增四个参数(参数名照 README §二统一规范):`--vols` / `--uids-file` / `--questions-file` / `--corpus-root`
(`--out`、`--limit-stores` 原有)。语义:

- `--vols` 逗号分隔语料 json,缺省仍为 `repro_batch2.VOLS`(v1 四卷);
- `--questions-file` 给出时用它重建 `by_uid`(b35c 行键 `uid/qid/qtype/question/gold` 与 `sample_stores()` 产物同名,无需映射);
- `--uids-file` 给出时替代 `sample_stores()` 的 `picked`,**保持文件顺序**;随后 `picked = [u for u in picked if u in by_uid]`;
- `--corpus-root` 覆盖模块级 `CORPUS_ROOT`(`main()` 里 `global CORPUS_ROOT`),`materialize()` 一行未动。

**未改动**(逐一确认):`AGENT_SYS`、`TOOLS`(list_files / grep_files / read_file)、`FsTools`、
`run_agent`(`READER_MODEL=claude-haiku-4-5`、`max_tokens=700`、`temperature=0.0`、`MAX_ROUNDS=12`、
末轮去工具强制作答、4 次重试)、`MAX_GREP_HITS=60`、工具结果截断 20,000 字符、`sess_text`、
输出行 schema、判官调用 `judge.judge(question, str(gold), answer, qtype)`。

另新增汇总脚本 `scripts/b35c_score_letta_fs.py`(只读 jsonl,$0,不触碰 harness)。

---

## 四、结果

| 指标 | 值 |
|---|---|
| n | **58**(question_id 集合与 `b35c_questions.jsonl` 精确一致:0 缺、0 多、0 重) |
| 库数 | 15 |
| **acc** | **43.10%**(25/58) |
| in-tok / 题 | 均 **30,190.5**(中位 18,542.5;min 2,455;max 113,654;合计 1,751,049) |
| out-tok / 题 | 均 **674.6**(中位 599;max 2,150;合计 39,124) |
| **延迟中位** | **12.57 s**(均 15.71;max 94.32) |
| **建库 s/库** | **0.0069**(中位 0.0070;15 库合计 0.103 s)= 0.0018 s/题 |
| 建库 $ | **$0**(写侧零 LLM、零嵌入) |
| agent 轮次 | 均 6.26,中位 6,max 12;打满 12 轮 5 题 |
| 工具使用 | list 均 0.86 / grep 均 2.93 / read 均 4.21(合计 50 / 170 / 244) |
| 空答 | 0;零工具调用 0 |

### 分题型

| 题型 | 正确/总 | acc |
|---|---|---|
| change_count | 6/15 | 40.00% |
| count_before | 4/15 | **26.67%** |
| first_vs_last | 8/15 | 53.33% |
| longest_tenure | 7/13 | 53.85% |

---

## 五、成本

价格按 README §一冻结口径(haiku-4-5 $1.00/$5.00 per M;claude-opus-5 $5.00/$25.00 per M)。

| 项 | 金额 | 来源 |
|---|---|---|
| 建库 | **$0** | 零 API(实测) |
| 读侧 agent(haiku-4-5) | **$1.9467** | 行内 `usage_input_tokens/usage_output_tokens` 合计 1,751,049 / 39,124,**实测 token** |
| 判官(claude-opus-5) | ≈$0.1785 | **估计**:58 × `results/judge_cost_measured_20260816.md` 实测均值 198.28 in / 83.45 out |
| **合计** | **≈$2.13** | 其中 reader+build **$1.9467**,在 $5 闸内 |

$/题(读侧)= **$0.0336**。墙钟 0.25 h,在 3 h 闸内。**未触发预算降级,15 库 58 题全跑完。**

---

## 六、与 60 题标定场协议的偏离

1. **读侧协议本就与其余考生不同,且本轮逐字保持存档值**:letta_fs 不用 `READER_SYS` / `max_tokens=300` / top-k=10,
   而是 `AGENT_SYS` + 三工具 agent(`max_tokens=700`/轮、最多 12 轮、检索由模型自主 grep/read)。
   这是该基线**自身冻结的协议**(README §三.15a、H3 判决 §二),不是本轮引入的改动。
   因此"k=10 / 记忆行 400 字截断"两条共享条款对本系统不适用——它看到的是整份会话文件原文。
2. **判官 usage 不落行**,判官 $ 只能给估计值(全场 harness 同此)。
3. **无 `build_s` 字段**,建库秒写在 `ingest_seconds`(README §一允许 `build_s = row.get("build_s", row.get("ingest_seconds"))`);
   为不改 harness 输出逻辑,本轮未补写 `build_s`。
4. 店根改为 `results/b35c_letta_fs_corpus`(硬规则:不覆盖既有 `results/letta_fs_corpus`)。
5. **不得与存档 56.67 直比**:存档是 v1 60 题(`_s5a..d` 题面),本轮是 v2.5 58 题
   (`_v2cc/cb/lt/fl`,`change_count` 题面已含"首值不计"说明),题面与语料两处都变了。
   b35c 的系统间比较只在 b35c 内部按 `question_id` 配对(58 题同集,簇 = 15 uid)。
6. 判官模型未设 `QVF_JUDGE_MODEL`,走 `qvf.config.DEFAULT_JUDGE_MODEL = claude-opus-5`(与协议一致)。

---

## 七、产出文件

- `D:\ZZL_cluade\results\b35c_letta_fs.jsonl` — 58 行,字段 `question_id, mode, uid, question_type, question,
  gold_answer, answer, memories_n, judge_correct, judge_reason, ingest_seconds, latency_s,
  usage_input_tokens, usage_output_tokens, agent_rounds, tool_list, tool_grep, tool_read`
- `D:\ZZL_cluade\results\opt_batch35c_letta_fs_verdict.md` — 本文件
- `D:\ZZL_cluade\results\b35c_letta_fs_run.log` — 逐题运行日志(58 行 + `DONE`)
- `D:\ZZL_cluade\results\b35c_letta_fs_score.txt` — 汇总脚本原始打印
- `D:\ZZL_cluade\results\b35c_letta_fs_corpus\` — 15 库 / 504 个 `.md`(本轮新建)
- `D:\ZZL_cluade\scripts\b35c_score_letta_fs.py` — 汇总脚本(新增)
- `D:\ZZL_cluade\scripts\letta_fs_agent_baseline.py` — +20/−1 行 CLI 接线(见 §三)
