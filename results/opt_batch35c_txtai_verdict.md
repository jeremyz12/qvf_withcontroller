# b35c · txtai(本地嵌入 flat-RAG)× WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。结果文件 `D:\ZZL_cluade\results\b35c_txtai.jsonl`(58 行,`question_id` 集合与
`results/b35c_questions.jsonl` 的 58 个 qid **完全相等**,无缺无重)。本判决的所有数字都由该 jsonl 现算,
未引用任何存档统计。

## 判决

**猜想被证实**:txtai 这类零 LLM 的扁平嵌入检索在 v2.5 聚合题上过不了"计数/时长"这一关——
58 题 **26 对,acc = 44.83%**;其中 `first_vs_last` 13/15(86.67%),而 `change_count` 3/15(20.00%)、
`longest_tenure` 3/13(23.08%)。原因是机制性的:每库 33–36 个会话,top-10 只递给读者不到三成的会话,
计数类题目在检索层就已经丢掉了做对所需的证据(58 题全部 `memories_n = 10`,无一题检索为空)。

## 实际执行

- **续跑**:本次开工时 `results/b35c_txtai.jsonl` 已有 **49 行已判决**(13 uid;`wikiP54031-Q16198306` 缺 1 题,
  `wikiP54003-Q26001185` 与 `wikiP54001-Q16225986` 各缺 4 题)。`scripts/repro_batch4.py::main` 是**追加写 +
  按 `question_id` 断点续跑**(`done = {...}`;`qs = [q for q in by_uid[uid] if q["qid"] not in done]`,
  `if not qs: continue`),所以直接原地续跑,**只作答缺的 9 题**,一行既有判决都没有丢弃。
  续跑前把原文件另存了一份只读副本到 scratchpad(`b35c_txtai_before_resume.jsonl`),未使用 part1 合并路径。
- **命令**(主环境,Python 3.14.5;本次唯一一条跑批命令,日志 `results/b35c_txtai_run.log`):

```
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python scripts/repro_batch4.py --system txtai \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file results/b35c_sample_uids.txt \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_txtai.jsonl
```

- 续跑段输出:`[wikiP54031-Q16198306] ingested 34 in 6s, answered 1` / `[wikiP54003-Q26001185] ... answered 4` /
  `[wikiP54001-Q16225986] ... answered 4`,收尾打印 `txtai: 44.83% (n=58)`、
  `judge total_usage (this process): {'input_tokens': 1705, 'output_tokens': 548, 'calls': 9}`。
- **每库全新建库**:`TxtaiSystem.ingest` 每个 uid 新建一只 `txtai.Embeddings(content=True)`(纯内存,不落盘,
  无 `results/b35c_txtai_stores` 目录),会话按 `date` 升序 `sorted(...)` 后逐条 `index()`;续跑段的三座库
  全部是新建的(`wikiP54031` 因还剩 1 题被重建了一次,6.5 s,与首段的 6.3 s 属同一协议的两次独立建库)。

## 脚本改动(diff 概要)

**本次没有再改任何脚本**:`scripts/repro_batch4.py` 里 b35c 所需的接线在上一次(被中断的)尝试中已写入,
本次只做了核对。与 HEAD 相比该文件的未提交改动共 106 行,其中与 **txtai 相关的只有 `main()` 装载段**这几处:

| 改动 | 内容 |
|---|---|
| 新增 `--vols` | `vols = a.vols.split(",") if a.vols else VOLS`,语料由 CLI 指定 |
| 新增 `--uids-file` | 给出时 `picked = [每行 uid]`,保持文件顺序,替代 `sample_stores()` 的 v1 15 库 |
| 修 `picked` 过滤位置 | `picked = [u for u in picked if u in by_uid]` 从 `if a.questions_file:` 块内提到块外(否则 b35c uid 与 v1 抽样交集为空,一题不跑) |
| 新增 `--out` | `out_p = ROOT / a.out if a.out else ROOT / f"results/wsc_s5_{name}{suffix}.jsonl"` |
| `--questions-file` 读行加 `if l.strip()` | 容忍尾部空行 |
| 行内新增 `build_s` | 与 `ingest_seconds` 同值,`ingest_seconds` 保留未删 |
| 收尾多打一行 `judge.total_usage` | 只打印,不写文件 |

其余改动(`--store-root`/cognee 用量回调、`--amem-repo`、A-MEM 与 cognee 的用量埋点)属别的系统,
txtai 代码路径一行未碰。**协议常量零改动**:读者 `claude-haiku-4-5` / `temperature=0` / `max_tokens=300` /
`READER_SYS` 逐字、检索 `limit=10`、记忆行 `- {text[:400]}`、`sess_text` 的日期前缀 + 前 6 轮 × 400 字符、
判官 `qvf.judge.ClaudeJudge()`(`QVF_JUDGE_MODEL` 未设 → `DEFAULT_JUDGE_MODEL = claude-opus-5`,本次已核)
全部与 60 题标定场一致。

## 数字(n = 58,15 库)

| 项 | 值 |
|---|---|
| 准确率 | **44.83%**(26/58) |
| change_count | 20.00%(3/15) |
| count_before | 46.67%(7/15) |
| first_vs_last | **86.67%**(13/15) |
| longest_tenure | 23.08%(3/13) |
| 读者输入 token 均值 | **1205.2**/题(合计 69,899) |
| 读者输出 token 均值 | **81.9**/题(合计 4,748) |
| 延迟中位(检索→判官返回) | **4.56 s**(均值 4.66,合计 270.1 s) |
| 建库 | **6.15 s/库**(中位 6.10,15 库合计 92.2 s;按 uid 去重取首现行)= 1.59 s/题 |
| `memories_n` | 58 题全为 10;检索为空 0 题;空回答 0 题 |

**成本**(项目冻结价目表):
- 读者 haiku-4-5:69,899 in + 4,748 out = **$0.0936**(实测,行内 usage 求和)。
- 判官 claude-opus-5:本次续跑段 9 次调用 **实测** 1,705 in / 548 out = $0.0222;其余 49 行的判官用量
  harness 不落行、上次进程也未存,按 `results/judge_cost_measured_20260816.md` 的实测均值(198.28/83.45 tok/次)
  折算 ≈ $0.1508(**估计**)→ 判官合计 ≈ **$0.173**。
- 建库:**$0**(txtai 用本地 sentence-transformers,零 API 调用)。
- **合计 ≈ $0.27**(其中 $0.116 实测、$0.151 估计),远低于 $5 上限;两段合计的计算墙钟(建库 92 s + 作答延迟 270 s)
  约 6 分钟,远低于 3 h 上限。**15 库全跑,未做任何缩减**。

## 与 60 题协议的偏离 / 说明

1. **无偏离的协议项**:语料、库清单顺序、每库全新库、会话日期升序、`sess_text`、top-10、`[:400]` 截断、
   读者模型/温度/max_tokens/`READER_SYS`、判官类与默认模型——逐项与 60 题标定场一致。
2. **题集与题面不同**(设计如此,非偏离):b35c 是 v2.5 的 58 题(`_v2cc/_v2cb/_v2lt/_v2fl`,change_count 题面
   已含"首值不计"说明),存档 60 题是 v1 题面。**44.83% 不得与存档 `results/wsc_s5_txtai.jsonl` 的 53.33% 直比**;
   比较只在 b35c 内部按 `question_id` 配对。
3. **两段拼接**:58 行由两次进程写成——前 49 行来自上一次被中断的尝试(行内**没有** `build_s` 字段,只有
   `ingest_seconds`,值相同;README §一约定 `build_s = row.get("build_s", row.get("ingest_seconds"))`,汇总不受影响),
   后 9 行由本次写入(两个字段都有)。txtai 检索无随机性来源(固定模型 + 固定语料),但两段的读者/判官调用
   是不同进程的不同 API 调用。
4. **`wikiP54031-Q16198306` 的库建了两次**(首段 6.3 s 供 3 题,续跑段 6.5 s 供第 4 题)。上表"6.15 s/库"
   按 uid 去重、取该 uid 首现行的值(6.3);若把续跑那次也算进去则是 16 次建库合计 98.7 s。
5. **判官用量不落行**是 repro_batch4 家族的既有设计,本次未改;因此 49 行的判官成本只能给估计值(已标注)。
6. txtai **不落盘**,所以没有 `results/b35c_txtai_stores/` 目录;既有店目录一个都没被写入。
