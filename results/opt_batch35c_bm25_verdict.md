# b35c 判决:bm25(rank_bm25 词面检索)× WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。系统 `bm25`,harness `scripts/repro_batch4.py`(`Bm25System`)。
结论:**58/58 题全部作答并判决完毕,acc = 12.07%(7/58)**。

## 一、实际运行的内容

本次是**断点续跑**。开跑前 `results/b35c_bm25.jsonl` 已有 **54 行**(前 14 个 uid,由此前被中断的
同一命令产生),缺 `wikiP54001-Q16225986` 的 4 题。harness 用
`done = {question_id ...}` 读旧文件后以 `"a"` 追加、`qs = [q for q in by_uid[uid] if q["qid"] not in done]`
跳过已完成题目,**只重建缺失 uid 的库、只答缺失 4 题**(运行日志 `results/b35c_bm25_run.log`:
`[wikiP54001-Q16225986] ingested 34 in 0s, answered 4`)。已判决的 54 行一行未动、一行未丢。
(为保险,跑前把 54 行副本存到 scratchpad;因 harness 确为追加+跳过,未启用 `_part1` 拆分-合并路径。)

命令(逐字):

```
python scripts/repro_batch4.py --system bm25 \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file results/b35c_sample_uids.txt \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_bm25.jsonl
```

环境:主环境 Python(`rank_bm25 0.2.2` / `numpy 2.5.1`),无隔离 venv(bm25 不需要)。
`QVF_JUDGE_MODEL` 未设 → 判官取 `qvf.config.DEFAULT_JUDGE_MODEL = claude-opus-5`。

## 二、脚本改动(diff 摘要)

`scripts/repro_batch4.py` 的 b35c 接线在本次开跑前已在工作区(`git diff` 98 增 8 删),
**本次未再改一行**。与 bm25 相关的部分只有装载段:

- 新增 CLI:`--vols`(逗号分隔语料 json,默认仍 `VOLS`)、`--uids-file`(uid 清单,保持文件顺序,
  替代 `sample_stores()` 的 `picked`)、`--out`(结果 jsonl 全路径)、`--store-root`(bm25 无落盘,未用)、
  `--amem-repo`(与 bm25 无关)。
- `picked = [u for u in picked if u in by_uid]` 从 `--questions-file` 分支里提到分支外,使
  `--uids-file` 给出的 uid 能与题集求交(原实现只与 v1 的 `sample_stores()` 取交 → 对 b35c uid 为空集)。
- 结果行加写 `build_s`(= `ingest_seconds`,不删原字段)、结束时打印 `judge.total_usage`。
- 其余为 amem/cognee 的用量埋点与路径参数,bm25 代码路径不经过。

**协议常量零改动**:读者 `claude-haiku-4-5` / `temperature=0` / `max_tokens=300` / `READER_SYS` 逐字、
`sess_text`(日期前缀 + 前 6 轮 × 每轮 400 字符)、检索 top-10、记忆行 `- {doc[:400]}`、
判官 `qvf.judge.ClaudeJudge`、失败重试 3 次、会话按 `date` 升序、每 uid 全新库,全部与 60 题标定场一致。

## 三、结果(全部由 `results/b35c_bm25.jsonl` 现算)

| 项 | 值 |
|---|---|
| n | **58**(question_id 集合 == `b35c_questions.jsonl` 58 个 qid,无重复、无多余) |
| 库数 | 15(每库 33–36 会话,零共享) |
| **acc** | **12.07%**(7/58) |
| 读者 in / out 均值 | **1213.4 / 86.1** tokens(合计 70,376 / 4,995) |
| `latency_s` 中位 | **4.63 s**(均值 4.95,区间 3.48–12.86) |
| 建库 | 见下 |
| 检索 | 58 题全部 `memories_n = 10`(无空检索) |

分题型:

| 题型 | 正确/总数 | acc |
|---|---|---|
| change_count | 1/15 | 6.67% |
| count_before | 5/15 | 33.33% |
| first_vs_last | 0/15 | 0.00% |
| longest_tenure | 1/13 | 7.69% |

对照存档 `results/wsc_s5_bm25.jsonl`(v1 60 题):acc 13.33,in 1201 / out 81,延迟中位 4.92 s
——v2.5 小样本上 12.07 / 1213 / 86 / 4.63,与词面检索锚的既有量级一致。

### 建库秒/库

harness 写入的 `ingest_seconds` = `build_s` = **0.0 s**(15 库全为 0.0,合计 0.0),因为 `round(x, 1)`
把真实耗时抹平。本轮另做了一次纯本地计时(无 API,`sess_text` + `BM25Okapi` 同一代码路径):
**每库 0.0017 s**(0.0015–0.0023),15 库合计 **0.026 s** = 0.0004 s/题。BM25 索引在内存中,不落盘,
故 `results/b35c_bm25_stores/` 不存在也不需要。

### 成本

| 项 | in / out tokens | $ |
|---|---|---|
| 读者 haiku-4-5(58 题,实测) | 70,376 / 4,995 | **$0.0954** |
| 摄入侧 | 0 / 0(bm25 零 LLM、零嵌入) | **$0** |
| 判官 opus-5(本进程实测 4 次调用) | 850 / 985 | $0.0289 |
| 判官 opus-5(58 次,按实测均值 212.5/246.3 外推) | ~12,325 / ~14,282 | ~$0.419 |
| **合计(估)** | | **≈ $0.51** |

预算闸门:读者+建库实际花费 $0.0954(闸门 ≤ $5);本次墙钟 < 1 分钟(闸门 ≤ 3 h)。15 库全跑,未削减。

## 四、与 60 题标定协议的偏差

1. **续跑而非一次跑完**:54 行由此前被中断的同一命令产生,4 行由本次产生;两段用的是同一脚本、
   同一常量、同一语料与题集。唯一可见差异是**旧 54 行没有 `build_s` 字段**(只有 `ingest_seconds`,
   两者语义相同且此系统恒为 0.0),新 4 行两个字段都有。汇总按
   `build_s = row.get("build_s", row.get("ingest_seconds"))` 读取,不受影响。
2. **判官用量只有本进程的 4 次调用被记下**(`judge.total_usage` 不落盘,旧 54 次的 usage 已随中断的
   进程丢失)。表中 58 次判官成本是**外推值**,已标注;读者 token 与延迟全部是逐行实测,非外推。
3. 题集为 58 题(v2.5 小样本),非 60 题;`wikiP551000-Q19845625` 与 `wikiP551008-Q29918442`
   各只有 3 题,故 `longest_tenure` 只有 13 题。这是 b35c 共享协议本身的设定,非本系统偏差。
4. 其余(读者模型/温度/max_tokens/系统提示/k=10/400 字符截断/判官/日期序摄入/每库新建)零偏差。
