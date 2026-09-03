# b35c 判决:sumrag(摘要 RAG)× WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。结果文件 `D:\ZZL_cluade\results\b35c_sumrag.jsonl`(58 行,每题一行)。
本文件所有数字均由该 jsonl 现算,建库 token 一项除外(harness 未埋点,标为**估计**并写明假设)。

## 判决

**sumrag 在 v2.5 小样本上的准确率是 36.21%(21/58)。** 58 题全部作答并判决,零读者失败行(无 `usage_input_tokens==0` 的行),
15 库全部建成,`question_id` 集合与 `results/b35c_questions.jsonl` 的 58 个 qid **精确相等**、无重复、无多余。

分题型看,系统只在"首值 vs 末值"这一类上站得住(66.67%),两类计数题(change_count / count_before)各只有 20.00%——
即摘要 RAG 能把"第一个/最近一个值"检索出来,但**数不清中间发生了几次变更**。

## 一、跑了什么

- **系统**:`sumrag`(`scripts/repro_batch2.py::SumRagSystem`)。写侧:每会话一次 `claude-haiku-4-5` 摘要(`max_tokens=250`,`temperature=0`,提示要求保留日期/名字/数字并前缀会话日期)→ 全部摘要入 `qvf.retrieval.OpenAIDenseRetriever`(text-embedding-3-small,进程内缓存,不落盘)。读侧 `retrieve(query, top_k=10)`,记忆行 `- [{session_date}] {content[:300]}`。
- **语料**:`data/wikistate_full_ALL_v25.json`(144 条目)。15 个目标 uid 全部命中,每库 33–36 个会话,共 504 个会话 → 504 次摘要调用。会话按 `date` 升序逐条写入。
- **库清单**:`results/b35c_sample_uids.txt`(15 行,按文件顺序)。**每 uid 一座全新的库**——sumrag 无落盘店,检索器随进程新建,库间零共享,不存在旧店复用。
- **题集**:`results/b35c_questions.jsonl`(58 题)。
- **读者/判官**:`claude-haiku-4-5`,`temperature=0`,`max_tokens=300`,`READER_SYS` 逐字未改;判官 `qvf.judge.ClaudeJudge()` 默认档 = `claude-opus-5`(`QVF_JUDGE_MODEL` 未设,已核)。`anthropic 0.121.0`,主环境(sumrag 不需要隔离 venv)。
- **落盘**:仅结果 jsonl。未写入任何既有店目录。

### 命令

CLI 接线已在工作区就位(见 §二),四次调用只是把 uid 清单按原顺序切片以适配前台超时,`--questions-file / --out` 全程指向同两份文件,harness 自带的 `question_id` 断点续跑保证不重不漏:

```
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python scripts/repro_batch2.py --system sumrag \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file <切片文件> \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_sumrag.jsonl
```

切片(顺序即 `b35c_sample_uids.txt` 第 2–15 行,第 1 行 `wikiP108035-Q39407125` 的 4 行已在上一次中断的尝试里判完,harness 自动跳过、未重建):

| 次 | uid | 产出行 |
|---|---|---|
| c1 | wikiP108021 / wikiP108048 / wikiP108008 / wikiP39036 | 16 |
| c2 | wikiP39003 / wikiP39033 / wikiP39017 / wikiP551008 | 15 |
| c3 | wikiP551000 / wikiP551001 / wikiP551007 | 11 |
| c4 | wikiP54031 / wikiP54003 / wikiP54001 | 12 |

四次串行、无并行(保持 `latency_s` 与标定场同口径)。本次会话墙钟 1112 s ≈ 18.5 min。

## 二、脚本改动摘要

**本次未改任何脚本。** `scripts/repro_batch2.py` 的 b35c 接线在我接手前已存在于工作区(未提交,`git diff HEAD` 42 增 6 删),
即 README §二 的骨架:`--vols / --uids-file / --questions-file / --out`(装载段)与 `--store-root`(仅 mem0 用,sumrag 不触发)。
逐行核对确认**协议常量一个未动**:读者模型 `claude-haiku-4-5`、`temperature=0.0`、`max_tokens=300`、`READER_SYS` 原文、
`retrieve(top_k=10)`、判官 `ClaudeJudge`、每轮 `str(t)[:400]` 截断、`turns[:6]`、记忆行 `[:300]`、摘要提示词与 `max_tokens=250` 全部与标定场一致。
`SumRagSystem` 类体零改动。

## 三、结果

n = 58,15 库。

| 指标 | 值 |
|---|---|
| 准确率 | **36.21%**(21/58) |
| 输入 token 均值 | **918.9**(合计 53,295) |
| 输出 token 均值 | **85.9**(合计 4,981) |
| `latency_s` 中位 | **4.86 s**(均值 5.22;四分位 4.24 / 5.60;区间 3.24–10.40) |
| 建库 | **57.1 s/库**(中位 57.1,区间 51.1–65.0;15 库合计 855.8 s)= 14.76 s/题 |
| 检索命中数 | 全部 58 题 `memories_n = 10`(top-10 每题取满) |

### 分题型

| 题型 | 正确/题数 | 准确率 |
|---|---|---|
| change_count | 3/15 | 20.00% |
| count_before | 3/15 | 20.00% |
| first_vs_last | 10/15 | **66.67%** |
| longest_tenure | 5/13 | 38.46% |

### 成本

| 项 | 口径 | $ |
|---|---|---|
| 读者(haiku-4-5) | 行内实测 53,295 in / 4,981 out × $1.00/$5.00 per M | **0.0782** |
| 判官(claude-opus-5) | 58 次 × `results/judge_cost_measured_20260816.md` 实测均值 198.28/83.45 tok × $5.00/$25.00 | **0.1785**(折算) |
| 建库(haiku-4-5 摘要) | **估计**:504 次调用;输入 219,070 tok(848,751 字符 × 0.2581 tok/char,比值由 24 条真实提示的 `count_tokens` 实测标定);输出按 120 tok/次假设 | **≈0.52**(区间 0.47–0.72,对应 100–200 tok/次) |
| 嵌入(text-embedding-3-small) | 504 段摘要 + 58 次查询,≈62k tok × $0.02/M | ≈0.001 |
| **合计** | | **≈0.78**(预算上限 $5,用掉约 16%) |

墙钟合计约 18.5 min(上限 3 h)。两项预算均未触顶,**15 库全部跑完,无一库因预算被裁**。

## 四、与存档的关系(不得直比)

存档 v1 60 题 `results/wsc_s5_sumrag.jsonl` 为 acc 46.67 / in 917 / out 80 / 中位 5.35 s / 52.6 s 库。
本次 in 918.9、out 85.9、中位 4.86 s、57.1 s/库 与之同量级,说明协议与成本结构复现良好;
但 **acc 36.21 与 46.67 不可直比**——题集不同(v2.5 的 `_v2cc/cb/lt/fl` 58 题 vs v1 的 `_s5a..d` 60 题,且 v2.5 的 change_count 题面已含"首值不计"说明)。
b35c 的一切比较只在 b35c 内部按 `question_id` 配对。

## 五、偏离与限定

1. **续跑**:`wikiP108035-Q39407125` 的 4 行(`ingest_seconds` 56.0)产自上一次被中断的尝试,同脚本、同语料、同题集、同协议;本次经 harness 自带的 `question_id` 跳过逻辑保留,未重建该库、未丢弃任何已判决行。其余 14 库 54 题为本次新产。原 4 行已另存备份于 scratchpad(`b35c_sumrag_preexisting_backup.jsonl`)。
2. **uid 切片**:仅为适配前台 10 min 工具超时,把 uid 清单按原顺序切成 4 份串行调用;非脚本改动、非并行、不改变任何库的构建方式与顺序。
3. **建库 token 未埋点**:`repro_batch2.py` 不记写侧用量(存档同此)。上表建库 $ 是估计值,输入侧用 `count_tokens` 标定过、可信;输出侧 120 tok/次为假设,已给出 100–200 tok/次的区间。**不得当实测引用。**
4. **会话段落化的写法**:sumrag 不走 `sess_text()` 的 `"(session date: …)\n"` 前缀,而是把日期写进摘要提示词(`prefix with the session date {date}`),摘要文本自带日期,`memory_id`/`session_date` 元数据取摘要首 10 字符。这是 repro_batch2 家族 sumrag 的冻结写法,与标定场一致,**不是本轮引入的偏离**。
5. **记忆行截断 300 字符**(非共享协议表里的 400):repro_batch2 家族的冻结常量,README §一 明确要求各 harness 保持原值,本轮照旧。
6. 本轮不做 git 提交;`scripts/repro_batch2.py` 的接线仍为未提交的工作区改动。
