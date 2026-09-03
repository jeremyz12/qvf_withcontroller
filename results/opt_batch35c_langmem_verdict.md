# b35c 判决:langmem(LangChain 官方记忆库)× WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。协议来源 `results/b35c_README.md` §一 + §三.13。
**本文件所有数字均从本轮实际产出的 `results/b35c_langmem.jsonl`(58 行)与观测壳
`results/b35c_langmem_usage.json` 重新计算**,无一项引用存档或外推。

## 判决

猜想"LangMem 在 v2.5 时序题上能守住四成"**被否定**:58 题只对 19 题,**acc = 32.76%**。
按题型看,唯一及格的是 first_vs_last(53.33%);两类计数题(change_count / count_before)
双双 20.00%,即 15 题里各只对 3 题。检索侧不是瓶颈——58 题全部拿满 top-10(`memories_n`
全为 10,零空检索),失分发生在"抽取出的记忆条目不承载可数的状态变更序列"这一环。

## 一、实际运行

| 项 | 值 |
|---|---|
| 命令 | 见下 |
| 进程 | 单进程,PID 6668,起 2026-09-03 20:41:28,止 21:59(本地时) |
| 墙钟 | **4654.8 s = 1.29 h**(观测壳 `elapsed_s`;预算闸 3 h,未触) |
| reader+build 花费 | **$3.3867**(预算闸 $5,未触) |
| 库 | 15/15,全部现建现用,零复用旧店(LangMem 为纯内存 `InMemoryStore`,本就不落盘) |
| 会话 | 504 条全部按 `date` 升序摄入(逐库 33/33/33/33/33/33/36/35/33/33/34/33/34/34/34) |
| 题 | 58/58,`question_id` 集合与 `results/b35c_questions.jsonl` 精确相等(零缺、零多、零重复) |

```
python scripts/b35c_langmem_run.py \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file results/b35c_sample_uids.txt \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_langmem.jsonl
```

`scripts/b35c_langmem_run.py` 是只读观测壳:`import langmem_s5_agg` 后给
`anthropic.resources.messages.Messages.create/parse` 套一层计数装饰器(不改入参、不改返回值),
再原样调用 `langmem_s5_agg.main()`。参数逐字透传。建库侧 token 靠它才有实测值
(harness 自身不埋点写侧用量)。

## 二、脚本改动(接线,协议常量零改动)

`scripts/langmem_s5_agg.py` 只改 `main()` 的装载段,共 +29/-12 行,照抄 README §二 骨架:

- 新增 `--vols`(逗号分隔语料 json,默认仍是原 4 卷 `VOLS`);
- 新增 `--uids-file`(给出时替代原等距抽样公式 `uids[(offset+i)*n//n_stores%n]`,保持文件顺序);
- 新增 `--questions-file`(给出时 `by_uid` 直接从该文件按 `uid` 分组;b35c 行的键
  `qid/qtype/question/gold` 与脚本内部字典同名,无需再映射;不给则走原
  `results/wsc_s5_filter_only.jsonl` 重建路径);
- `--out` 原本就有。

**未改动**(逐字保持 60 题标定场):`READER_MODEL="claude-haiku-4-5"`、`temperature=0.0`、
`max_tokens=300`、`READER_SYS` 全文、user 模板 `"MEMORIES:\n{memtext}\n\nUSER'S NEW MESSAGE: {q}"`、
空检索占位 `(no memories retrieved)`、读者三次重试、`store.search(..., limit=10)`(k=10)、
记忆行 `- {json.dumps(m.value, ensure_ascii=False)[:300]}`(**300 字符,langmem 家族冻结值**)、
会话段落化 `"(session date: {date})\n" + "\n".join(str(t)[:400] for t in turns[:6])`、
`InMemoryStore(index={"dims":1536,"embed":"openai:text-embedding-3-small"})`、
`create_memory_store_manager("anthropic:claude-haiku-4-5", namespace=("memories", uid))`、
判官 `qvf.judge.ClaudeJudge()`(默认 `claude-opus-5`)。
断点续跑逻辑也是脚本原有的(`open(out,"a")` + `done` 集合按 `question_id` 跳过,
且整库题目全 done 时 `continue` 跳过重建),本轮未动。

## 三、结果

**n = 58,acc = 32.76%(19/58),15 库。**

| 题型 | 对/总 | acc |
|---|---|---|
| change_count | 3/15 | 20.00% |
| count_before | 3/15 | 20.00% |
| first_vs_last | 8/15 | 53.33% |
| longest_tenure | 5/13 | 38.46% |

| 读侧指标 | 值 |
|---|---|
| `usage_input_tokens` 均值 | **835.0**(合计 48,432) |
| `usage_output_tokens` 均值 | **100.1**(合计 5,805) |
| `latency_s` 中位 | **5.14 s**(均值 5.47,区间 3.26–18.36) |
| `memories_n` | 全部 = 10(均值 10.00,零空检索行) |
| 空答案行 | 0 |

## 四、建库时间与成本(实测)

| 项 | 值 |
|---|---|
| **build_s / 库**(按 uid 去重) | **均值 288.8 s,中位 291.7 s**,15 库合计 4331.4 s = 1.20 h |
| build_s / 题 | 74.7 s |
| 逐库区间 | 254.5 s(wikiP108035)– 316.5 s(wikiP108021) |
| 建库 LLM 调用 | 506 次 haiku(504 会话 → ≈1.004 次/会话) |
| 建库 token | 1,782,305 in / 305,379 out(haiku-4-5) |
| **建库 $** | **$3.3092 = $0.2206/库**(冻结价 $1.00/$5.00 per M) |
| 读者 $ | $0.0775(58 题;$0.00134/题) |
| **reader + build $** | **$3.3867** |
| 判官 $ | $0.2240(opus-5,12,897 in / 6,379 out;另有 44,022 cache-read token,冻结价表未列缓存档,按 10% 输入价折算约 +$0.022,未计入上表) |
| 全场合计 $ | **$3.6106** |
| 落盘店 | 无(`InMemoryStore`,进程内;0 字节) |

嵌入侧(`openai:text-embedding-3-small`,写入 + 检索)走 OpenAI,观测壳只拦 anthropic 客户端,
**未埋点**;按 504 段 × ~725 字符量级估计 < $0.01,标为估计,不入上表。

## 五、与 60 题标定场的偏离

- **无协议偏离**。读者 / 判官 / k=10 / 300 字符记忆行截断 / 每轮 400 字符 / 前 6 轮 /
  日期前缀 / 逐库新建全部与 `results/wsc_s5_langmem.jsonl` 那次逐字相同;改动仅限装载段三个参数。
- **题集与语料换了**(这是 b35c 的设计,不是偏离):v1 四卷 60 题 → `data/wikistate_full_ALL_v25.json`
  的 15 库 58 题。按 README §五,存档 acc 40.00 与本轮 32.76 **不得直比**,比较只在 b35c 内部按
  `question_id` 配对。
- **建库时长与存档同量级**:288.8 s/库(本轮实测)vs 278.0 s/库(存档),差 +3.9%。
- 本轮跑批期间机器上并行跑着其它系统(trace 4 分片等),`build_s` 与 `latency_s` 含机器竞争,
  应视为上界。
- LangMem 库内部在建库期打印了 **9 次** `Could not apply patch: can't remove a non-existent object 'None'`
  (抽取模型发出删除指令但目标条目不存在)。这是库自身的非致命告警,未中断摄入,未做任何处理。

## 六、断点续跑处置

接手时 `results/b35c_langmem.jsonl` 已有 29 行,且**发起该文件的进程(PID 6668)仍在运行**——
不是被中断的残骸。核对:观测壳里 reader 调用数始终等于文件行数,说明全部行都由这一个进程产出
(19:56 那次早期尝试 `results/b35c_langmem_run_attempt1.log` 只跑了 17 次建库调用、**零行落盘**)。
harness 本身按 `question_id` 追加去重,故按 RESUME 规则的"追加且跳过已完成"分支处理:
**未挪走任何文件、未新开文件、未丢弃任何已判行**,在前台轮询该进程直到自然退出(21:59,15 库全完)。
最终文件 58 行 / 58 个唯一 `question_id`,零重复。`results/b35c_langmem_part1.jsonl` 因此不存在,也不需要。

## 七、行 schema(14 字段,与存档同款)

`question_id, mode, uid, question_type, question, gold_answer, answer, memories_n,`
`usage_input_tokens, usage_output_tokens, judge_correct, judge_reason, ingest_seconds, latency_s`

`build_s` ← `ingest_seconds`(README §一 约定;langmem harness 未额外写 `build_s` 字段,
汇总按 `row.get("build_s", row.get("ingest_seconds"))` 读)。

## 八、产出文件

| 文件 | 内容 |
|---|---|
| `D:\ZZL_cluade\results\b35c_langmem.jsonl` | 58 行结果(本轮唯一结果文件) |
| `D:\ZZL_cluade\results\b35c_langmem_usage.json` | 观测壳 token/调用/耗时分桶 |
| `D:\ZZL_cluade\results\b35c_langmem_run.log` | 跑批日志(逐库建库秒数、库内告警) |
| `D:\ZZL_cluade\results\opt_batch35c_langmem_verdict.md` | 本文件 |
| `D:\ZZL_cluade\scripts\b35c_langmem_run.py` | 只读观测壳(不改协议) |
| `D:\ZZL_cluade\scripts\b35c_summarize_langmem.py` | 只读汇总脚本($0) |
