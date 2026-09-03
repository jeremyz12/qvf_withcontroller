# b35c 判决:HippoRAG 2 × WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。系统 `hipporag2`(官方 pip 包 `hipporag==2.0.0a3`,OSU-NLP-Group,MIT)。
结果文件 `results/b35c_hipporag2.jsonl`(58 行,一题一行)。本文件所有数字都从该 jsonl 现算,
未从任何存档或榜单摘抄。

## 判决

**猜想被否定**:HippoRAG 2 的图检索并未在 v2.5 时序题上整体站住 —— 58 题 acc **46.55%**(27/58)。
分题型看是"一好三坏":`first_vs_last` 14/15(93.33%)几乎满分,而 `longest_tenure` 2/13(15.38%)、
`change_count` 4/15(26.67%)、`count_before` 7/15(46.67%)全线塌陷。即 HippoRAG 2 能取回**首末两个端点值**,
但取不回**跨会话的计数/时长跨度**——它的 PPR + 三元组图把同一槽位的历次取值压成互相同义的短语节点,
top-10 段落里端点齐全、序列不全。

## 一、实际跑了什么

- 全部 15 库、全部 58 题跑完,**无抽样、无缺题**:结果行 `question_id` 集合与 `results/b35c_questions.jsonl`
  的 58 个 qid **完全相等**(缺 0 / 多 0 / 重复 0,已逐行核对 uid/question/gold/qtype 四字段一致,0 处不符)。
- 每库一座全新 `save_dir`(`force_index_from_scratch=True`),库间零共享;会话按 `date` 升序摄入;
  每库段落数 33–36,与 `data/wikistate_full_ALL_v25.json` 里该 uid 的会话数逐库相等。
- 店目录 `results/b35c_hipporag2_stores/`(15 座,150 MB),既有 `results/hipporag_stores` 未被写入。
- 本轮是**断点续跑**:先前一次尝试被中断,分三段跑完(见 §四),三段合计墙钟约 15 分钟,
  远低于 3 小时闸;成本见 §五,远低于 $5 闸。

### 命令

主命令(`.venv_hipporag`,Python 3.12.10,`hipporag 2.0.0a3` + `anthropic 0.121.0`):

```
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv_hipporag/Scripts/python.exe scripts/hipporag2_baseline.py \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file results/b35c_sample_uids.txt \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_hipporag2.jsonl \
  --store-root results/b35c_hipporag2_stores
```

不加 `--no-truncate`、不加 `--reuse-store`、不加 `--rerank-llm`(= README §三.10 (c) 的主臂口径)。
续跑分段靠 `--store-offset / --limit-stores`(脚本自身还按 `question_id` 跳过已完成题):
第 2 段 `--store-offset 6 --limit-stores 5`,第 3 段 `--store-offset 11`(其余参数逐字相同)。
这两段的旗标是从三份运行日志的 `stores=/questions=` 头与行内 uid 顺序**反推**的,当时未单独入档。
日志:`results/_b35c_hipporag2_run.log`、`_run2.log`、`_run3.log`。

## 二、脚本改动(diff 摘要)

`scripts/hipporag2_baseline.py`,**+21 / −2 行,只动 `main()` 的装载段与输出行**,
算法、读者、判官、k、截断、配置常量一律未动:

| 改动 | 内容 |
|---|---|
| 新增 4 个 CLI(README §二统一接线规范,照抄 `trace_contestant.py` 写法) | `--vols`(逗号分隔语料 json,默认 `VOLS`)、`--uids-file`(uid 清单,保持文件顺序)、`--questions-file`(题集 jsonl,重建 `by_uid`)、`--out`(结果 jsonl 全路径) |
| `out_p` 一行 | `ROOT / a.out if a.out else ROOT / f"results/wsc_s5_hipporag2{suffix}.jsonl"` |
| 语料装载 | `for v in VOLS` → `for v in vols` |
| `picked / by_uid` | `--questions-file` 给出时从题集重建 `by_uid`;`--uids-file` 给出时替换 `sample_stores()` 的 `picked`;随后 `picked = [u for u in picked if u in by_uid]` |
| 输出行 | 增写 `"build_s": round(ingest_s, 1)`(与既有 `ingest_seconds` 并存,未删除) |

未改动、逐字保留的协议常量:`READER_MODEL`(claude-haiku-4-5)、`READER_SYS`(从 `repro_batch2` import)、
`temperature=0.0`、`max_tokens=300`、失败重试 3 次、`TOP_K=10`、记忆行 `- {p[:400]}`、
`sess_text`(日期前缀 + 前 6 轮 × 400 字符)、`judge = ClaudeJudge()` 默认档、
`LLM_NAME=gpt-4o-mini`、`EMBED_NAME=text-embedding-3-small`、`openie_mode=online`、OpenIE 线程池 4、
vllm 与 `multiprocessing.Manager` 两个 import 期垫片。

## 三、结果

n = **58**,15 库。acc = **46.55%**(27/58)。

| 题型 | 正确/总 | acc |
|---|---|---|
| first_vs_last | 14/15 | **93.33** |
| count_before | 7/15 | 46.67 |
| change_count | 4/15 | 26.67 |
| longest_tenure | 2/13 | 15.38 |
| **合计** | **27/58** | **46.55** |

| 读侧口径 | 值 |
|---|---|
| 读者输入 token 均值 | **1194.9**(合计 69,306) |
| 读者输出 token 均值 | **82.3**(合计 4,773) |
| `latency_s` 中位 | **6.04 s**(均值 6.35,min 4.49,max 12.96) |
| `retrieve_s` 中位 / `read_s` 中位 | 1.13 s / 1.78 s |
| `memories_n` | 58 题全部 = 10(top-10 满额,无空检索、无检索异常) |
| 空答复 / 零 token 行 | 0 / 0 |

### 建库(按库去重,15 库)

| 口径 | s/库 均值 | 中位 | 15 库合计 | s/题 |
|---|---|---|---|---|
| **as-run(行内 `build_s` 原值)** | **31.11** | 31.90 | 466.7 | 8.05 |
| cold-sub(把 1 座暖缓存库换成实测冷建值) | 32.46 | 32.30 | 486.9 | 8.39 |

**须知的续跑瑕疵**:`wikiP39033-Q5331705` 一库的 `build_s = 13.1 s`、OpenIE 仅 6 次调用,
明显低于其余 14 库(29.2–37.5 s、66–70 次调用)。原因已查明:第 1 段运行正是在**这座库建索引途中**被中断,
`save_dir/llm_cache` 已写入;第 2 段重建时 HippoRAG 的 LLM 缓存命中,只补跑了 6 次真调用。
该库的图是完整的(36 passage 节点 / 386 phrase 节点 / 1227 triples,与同侪同量级),
**受影响的只有这一库的建库墙钟与计量 token,不影响任何答案**。

为把这一项从推断变成实测,本轮另建了一座**全新**店 `results/b35c_hipporag2_stores_coldcheck/`
(未触碰任何既有目录/文件),对同一 uid 冷建:**33.3 s / 72 次调用 / 46,632+7,439 tok / 19,713 emb tok**,
与同侪完全吻合。该冷建臂对这 4 题的判决结果**同为 0/4**(逐题与主结果一致),
即暖缓存对准确率零影响。冷建臂的 4 行写在 `results/b35c_hipporag2_coldcheck.jsonl`,
**未并入** `results/b35c_hipporag2.jsonl`(诊断臂,不入同台表)。上表 cold-sub 行即用 33.3 替换 13.1 后的结果。

## 四、续跑与去重(RESUME 处置)

进入本轮时 `results/b35c_hipporag2.jsonl` 已存在。核查结果:**58 行 / 58 个不重复 question_id,
与题集 58 个 qid 完全相等,0 缺 0 重**。故:

- 无需再答任何题;**未移动、未覆盖、未丢弃任何已判决行**(该文件本轮零写入)。
- 分段来历(据日志):第 1 段 stores=15 声明、实际完成 6 库 24 题后被中断于第 7 库建索引途中;
  第 2 段补 5 库 18 题(累计 42);第 3 段补 4 库 16 题(累计 58)。
  脚本的 `done` 集合按 `question_id` 跳过,`qs` 为空时 `continue`,因此已完成的库不会重建、不会重复写行。
- 判官用量只在第 2、3 段的进程末尾打印(第 1 段被中断,未打印):34 次调用 6,508 in / 2,738 out。

## 五、成本(实测折算;价格用项目冻结口径)

| 项 | 模型 | token | $ |
|---|---|---|---|
| HippoRAG 建库 OpenIE | gpt-4o-mini | 630,431 in / 99,038 out(942 次调用) | 0.1540 |
| HippoRAG 建库嵌入 | text-embedding-3-small | 271,188 | 0.0054 |
| HippoRAG 查询期(recognition-memory 重排 + 查询嵌入) | gpt-4o-mini / emb | 164,693 in / 1,829 out;3,390 emb | 0.0259 |
| 读者 | claude-haiku-4-5 | 69,306 in / 4,773 out | 0.0932 |
| **小计(建库 + 查询 + 读者)** | | | **0.2785** |
| 判官(34 次实测 + 24 次按实测均值 191.4/80.5 外推) | claude-opus-5 | ≈11,102 in / 4,671 out | ≈0.1723 |
| **合计** | | | **≈0.4508** |

- 建库 **$0.01063/库**(as-run)/ **$0.01132/库**(cold-sub)。cold-sub 值与 60 题存档的 $0.0113/库
  几乎逐位相同,是对本轮计量的一个独立佐证。
- 查询期 $0.00045/题;读侧(读者+判官)≈$0.0046/题。
- 另有冷建诊断臂一次性开销 **$0.0448**(含其 4 题读者与判官),不计入上表。
- 预算闸:reader+build 实际 $0.2785,闸 ≤$5;墙钟约 15 分钟(+1 分钟诊断),闸 ≤3 h。**两闸均大幅未触**。

## 六、与 60 题标定场的口径偏离

| 项 | 状态 |
|---|---|
| 读者(模型/温度/max_tokens/READER_SYS/重试 3 次) | **无偏离**,逐字沿用 |
| 判官 `qvf.judge.ClaudeJudge()` 默认档 | **无偏离** |
| k = 10、记忆行 400 字符截断、`sess_text` 段落化、按日期升序摄入、每库全新索引 | **无偏离** |
| HippoRAG 配置(gpt-4o-mini / text-embedding-3-small / online OpenIE / 线程池 4 / 两个 import 垫片) | **无偏离** |
| 语料 / uid / 题集 / 输出路径 / 店根 | **有意变更**,即本轮任务范围(v2.5 / 15 uid / 58 题),通过新增 CLI 传入,未硬改任何默认值 |
| 建库墙钟与计量 token(仅 `wikiP39033-Q5331705` 一库) | **有偏离**:暖 LLM 缓存导致低估,已在 §三量化并另行冷建实测;不影响答案 |
| 判官 token(24/58 次) | **外推值**,非实测(第 1 段进程被中断未打印);已标注 |

**不得与存档 60 题的 `results/wsc_s5_hipporag2.jsonl`(acc 55.00)直比**:题面版本不同(v1 `_s5a..d` vs
v2.5 `_v2cc/cb/lt/fl`,change_count 题面已含"首值不计"说明)、库集合不同、题数不同(60 vs 58)。
b35c 的系统间比较只在 b35c 内部按 `question_id` 配对(58 题同集),簇 = 15 uid。

## 七、产出文件

- `D:\ZZL_cluade\results\b35c_hipporag2.jsonl` — 58 行主结果(本轮零写入,原样保留并核验)
- `D:\ZZL_cluade\results\opt_batch35c_hipporag2_verdict.md` — 本文件
- `D:\ZZL_cluade\results\b35c_hipporag2_stores\` — 15 座店,150 MB
- `D:\ZZL_cluade\results\b35c_hipporag2_coldcheck.jsonl` + `results\b35c_hipporag2_stores_coldcheck\` — 冷建诊断臂(1 库 4 题,11 MB),**不入同台表**
- 日志:`results\_b35c_hipporag2_run.log` / `_run2.log` / `_run3.log`
