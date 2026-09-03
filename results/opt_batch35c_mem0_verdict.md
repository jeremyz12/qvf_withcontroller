# b35c / mem0(Mem0 OSS 2.0.16,出厂默认 + gpt-4o-mini)× WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。协议依据 `results/b35c_README.md` §一(共享考场)与 §三.12(mem0 分节)。
**本判决所有数字都从本轮实际写出的文件重算**:`results/b35c_mem0.jsonl`(58 行)、
`results/b35c_mem0_build_usage_all.json`(6 个分块计量表合并)、`results/b35c_mem0_summary.json`。

## 一、判决

**猜想被证实:Mem0 出厂默认配方在 WikiState v2.5 的时序聚合题上基本失效。** 58 题 acc = **10.34%**(6/58),
四类题里只有 change_count(4/15)与 longest_tenure(2/13)各有零星命中,count_before 与 first_vs_last **全错(0/15、0/15)**。
检索从不空手(58 行 `memories_n` 全为 20),失败不在"取不到",而在**取回来的记忆已经没有时间轴**:
本轮建成的库里 1928 条记忆只有 **17.0% 的正文含年份或日期**,`(session date: …)` 前缀在 Mem0 的抽取阶段被丢掉
(样例:"User hiked to the top of a nearby mountain on September 3, 2026…" 属于少数带日期的,多数是
"User needs to buy paper filters and a new thermos…" 这种无时间戳的偏好陈述)。数"改了几次 / 某日之前有几次 /
首末值 / 哪段最长"都需要事件的时间序,这层信息在写入侧即已损失。

## 二、跑了什么

| 项 | 值 |
|---|---|
| 语料 | `data/wikistate_full_ALL_v25.json` |
| 库清单 | `results/b35c_sample_uids.txt`(15 uid,按文件顺序) |
| 题集 | `results/b35c_questions.jsonl`(58 题) |
| 结果 | `results/b35c_mem0.jsonl`(58 行,`question_id` 集合与题集**完全一致**:missing 0 / extra 0 / dup 0) |
| 店目录 | `results/b35c_mem0_stores/`(qdrant collection `b35c_mem0` + `history.db`,32 MB) |
| 建库计量 | `results/b35c_mem0_build_usage_all.json`(分块原件 `_part1/_c0…_c4` 保留) |
| 读者 / 判官 | `claude-haiku-4-5`,temperature 0,max_tokens 300,`READER_SYS` 逐字;`qvf.judge.ClaudeJudge()`(默认 `claude-opus-5`) |
| 检索 | `m.search(query, filters={"user_id": uid}, limit=10)`;记忆行 `- {json.dumps(memory)[:300]}`(300,冻结) |
| 会话段落化 | `"(session date: {date})\n" + "\n".join(str(t)[:400] for t in turns[:6])`,按 `date` 升序逐条 `m.add` |
| 环境 | 主环境 Python 3.14.5,`mem0 2.0.16`、`anthropic 0.121.0`;`OPENAI_API_KEY` + `ANTHROPIC_API_KEY` |

命令(6 个分块,uid 清单按 `results/b35c_sample_uids.txt` 顺序切成 1+3+3+3+3+2;分块 uid 文件在
`…/scratchpad/b35c_mem0_uids_c0..c4.txt`。同一个 `--out` 追加写、按 `question_id` 断点续跑):

```
cd D:\ZZL_cluade
PYTHONUTF8=1 python scripts/b35c_run_mem0.py \
  --usage-out results/b35c_mem0_build_usage_c<N>.json \
  --system mem0 \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file <scratchpad>/b35c_mem0_uids_c<N>.txt \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_mem0.jsonl \
  --store-root results/b35c_mem0_stores
```

第一块(uid #1 `wikiP108035-Q39407125`)用的是全量 `--uids-file results/b35c_sample_uids.txt`,跑完首库后被中断;
其 4 行判决结果保留在 `results/b35c_mem0_part1.jsonl`(与主文件同内容,未丢弃),后续分块由 harness 的
`done = {question_id}` 跳过机制续跑,主文件从未被覆盖。

## 三、脚本改动(只加接线,协议常量一字未改)

`scripts/repro_batch2.py`(+42/-6,`git diff --numstat` 可核):

1. `main()` 增 `--vols / --uids-file / --questions-file / --out / --store-root` 五个可选参数,实现照抄 README §二骨架
   ——只替换装载段(`entries` 来源、`picked`、`by_uid`、`out_p`),循环体、读者调用、判官调用、写行逻辑逐行不动。
2. `Mem0System.__init__(store_root=None)`:给出 `--store-root` 时在 config 里加
   `vector_store={"provider":"qdrant","config":{"collection_name":"b35c_mem0","embedding_model_dims":1536,"path":"<root>/qdrant","on_disk":False}}`
   与 `history_db_path="<root>/history.db"`(字段写法同 `scripts/run_mem0_baseline.py::_mem0_config`)。
   **LLM(gpt-4o-mini,temperature 0.1)与 embedder(text-embedding-3-small)未动**,只把落盘位置从出厂
   `D:\tmp\qdrant` / `~/.mem0` 挪到 b35c 新目录(店冻结纪律)。旧目录时间戳仍为 8-21,本轮零写入(已核)。

`scripts/b35c_run_mem0.py`(新增,只读计量外壳,不改协议):设 `MEM0_TELEMETRY=False`;
在 `openai` 的 `Completions.create` / `Embeddings.create` 类级别包一层计数器,按 uid 在 `Mem0System.ingest` 前后取差
→ 每库 LLM/嵌入用量;持有 `ClaudeJudge` 实例以读 `judge.total_usage`;`ingest` 前先 `m.delete_all(user_id=uid)`
(断点续跑安全:被杀的分块可能在共享 collection 里留下半库;对没进过库的 uid 是空操作,不改变干净跑的行为)。

`scripts/b35c_summarize_mem0.py`(新增,$0):核对 `question_id` 集合后算 acc / 分题型 / token 均值 /
延迟中位 / `build_s`(按 uid 去重)/ 实测成本,写 `results/b35c_mem0_summary.json`。

## 四、数字(n = 58,15 库)

| 指标 | 值 |
|---|---|
| acc | **10.34%**(6/58) |
| change_count | 26.67%(4/15) |
| count_before | 0.00%(0/15) |
| first_vs_last | 0.00%(0/15) |
| longest_tenure | 15.38%(2/13) |
| 读者输入 token 均值 | **786.4**(min 721 / max 881,合计 45,611) |
| 读者输出 token 均值 | **101.0**(min 50 / max 152,合计 5,857) |
| `latency_s` 中位 | **5.05 s**(均值 5.56,min 4.05,max 12.08) |
| `memories_n` | 全部 58 行 = 20(见 §五 偏离 5) |
| 建库墙钟 | **81.0 s/库**(中位 79.4,15 库合计 1215.0 s = 20.3 min)= 21.0 s/题 |
| 建库 LLM(gpt-4o-mini) | 504 次调用,4,556,974 in / 105,177 out |
| 建库嵌入(text-embedding-3-small) | 1,062 次调用,242,042 tok |
| 库内记忆条数 | 15 个 user_id 合计 1928 条(116–149 条/库),平均 128.5 条/库 |

成本(项目冻结价目表:gpt-4o-mini $0.15/$0.60,haiku-4-5 $1.00/$5.00,opus-5 $5.00/$25.00,嵌入 $0.02/M):

| 项 | 实测 $ |
|---|---|
| 建库(gpt-4o-mini + 嵌入) | **0.7515**(= $0.0501/库) |
| 读者(haiku,58 题) | **0.0749** |
| **读者 + 建库(预算口径)** | **0.8264**(预算上限 $5,占 16.5%) |
| 判官(opus-5) | 0.2054(实测覆盖 54/58 次调用;按均值外推 58 次 ≈ 0.221) |
| 合计(含判官) | 1.0318(外推口径 ≈ 1.047) |

墙钟:建库 1215 s + 读答判 58 题(中位 5.05 s/题)≈ 5 min,合计约 **26 min** 的净计算时间,远在 3 h 上限内。
15 库全部跑完,**未做任何降规模**。

## 五、与 60 题标定场协议的偏离

1. **题面与语料按任务书更换**(v2.5 / 58 题 / b35c 15 uid),读者、判官、k、截断、提示词、段落化全部保持标定场原值。
   与存档 `results/wsc_s5_mem0.jsonl`(v1 60 题,acc 26.67)**不得直比**(README §五)。
2. **落盘位置改到 `results/b35c_mem0_stores`**(出厂默认会写进已存在的 `D:\tmp\qdrant` collection `mem0` 与
   `~/.mem0/history.db`,违反店冻结纪律)。collection 名改为 `b35c_mem0`;向量维度、距离、embedder 均为默认值。
3. **`MEM0_TELEMETRY=False`** 与 openai 客户端类级计量包装(只读计数,不改请求/响应)。
4. **每库 ingest 前 `delete_all(user_id=uid)`**(续跑安全)。对本轮而言只有 uid #1 有可能受影响,而它是在
   全新空 collection 上第一次建库,该调用为空操作。15 个 user_id 在最终库里点数 116–149,无重复堆叠迹象。
5. **`memories_n` = 20 而 `limit=10`**:Mem0 2.0.16 的 `search` 在本机返回 20 条。这是 harness 冻结代码的既有行为,
   **存档 60 题运行同样是 60 行全 20**(`results/wsc_s5_mem0.jsonl` 核对),不是本轮引入的改动,故按"不改冻结常量"原则原样保留并在此登记。
6. **mem0 内部 LLM 用 gpt-4o-mini、temperature 0.1**:标定场既有偏离(出厂默认 LLM 拒 `temperature<1`),已入档
   `results/repro_batch2_prereg.md`,本轮沿用未改。
7. **环境缺 mem0 的可选依赖**(`spaCy` / `fastembed`,启动时三条 warning):BM25 关键词混检与 spaCy 词形归并未启用,
   走纯向量检索。这是本机主环境的既有状态(与存档运行同一环境),未为本轮改动。
8. **判官用量只实测到 54/58 次**:首块(uid #1 的 4 题)在被中断前计量表最后一次落盘发生在判官调用之前。
   `judge_cost_usd` 因此是 54 次的实测值,表中同时给出按均值外推到 58 次的估计。
9. 运行被切成 6 个分块(中断后续跑),分块之间除共享 collection 与追加写外无状态传递;每库仍是"全新的库、
   会话按日期升序逐条写入"。

## 六、可复核清单

- `results/b35c_mem0.jsonl` — 58 行,字段 `question_id, mode, uid, question_type, question, gold_answer, answer, memories_n, usage_input_tokens, usage_output_tokens, judge_correct, judge_reason, ingest_seconds, latency_s`(`build_s` ← `ingest_seconds`,README §一 约定)
- `results/b35c_mem0_part1.jsonl` — 首块 4 行原件(已包含在主文件中,未丢弃)
- `results/b35c_mem0_build_usage_all.json` — 合并计量;`_part1/_c0…_c4` 为分块原件
- `results/b35c_mem0_summary.json` — 本文件所有数字的机器可读版
- `results/b35c_mem0_run.log` / `results/b35c_mem0_run2.log` — 运行日志(每库 "ingested N in Ms, answered K")
- `results/b35c_mem0_stores/` — qdrant + history.db(32 MB)
