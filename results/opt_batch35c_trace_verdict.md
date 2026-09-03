# 批 35c 判决:TRACE(arXiv:2607.00339,LoCoMo/FAIR 配置)× WikiState v2.5 小样本(15 库 / 58 题)

状态:**RUN 完成**(58/58,单臂:LoCoMo 配置 = `--evolution --update-detection`,批 33-H2 判决里在
60 题场拿 30.00 的那档)。日期 2026-09-03/04。结果文件 `D:\ZZL_cluade\results\b35c_trace.jsonl`
(58 行,`question_id` 集合与 `results/b35c_questions.jsonl` 的 58 个 qid 精确一致:无缺、无多、无重复)。
本文件所有数字均从该 jsonl 现场重算,判官/读者/建库用量取自行内字段与运行日志。

---

## 1. 判决

**TRACE(LoCoMo/FAIR 配置)在 v2.5 小样本考场落在 31.03%(18/58)**,与批 33-H2 在 v1 60 题标定场
测得的同配置 30.00%(18/60)**同一量级、彼此复现**——两个语料版本、两套题面上数字几乎重合,
不是抽样噪声。四类聚合题全部 ≤ 47%:`change_count` 20.00% 最弱,`first_vs_last` 46.67% 最强
(`count_before` 33.33%,`longest_tenure` 23.08%)。

插入 `results/b35c_leaderboard.md` 现有 14 系统榜单(按准确率降序,TRACE 用本文件数字):

timeline 56.9 > lgstore 46.6 ≈ HippoRAG2 46.5 ≈ txtai/cognee 44.8 > Letta-FS 43.1 > A-MEM 39.7 >
摘要RAG 36.2 > LangMem 32.8 > **TRACE 31.03** ≈ MemOS 31.0 > 盖章/obs-RAG 13.8 > BM25 12.1 > Mem0 10.3。
TRACE 落在中下段,与 LangMem/MemOS 三家互相覆盖(58 题 Wilson 区间在小样本下天然宽),
明显低于直读 top-10(同店 37.9,见榜单文件 §一)与全上下文裸调用(63.8)。

机制侧确认:15 库合计 3,045 个事件 / 504 会话上,`update_edges` = **35**、`contradiction_edges` = **4**
(逐库 0–6 条 update、0–2 条 contradiction,见 §3 分库表)——**不是 0**,证实本次确实跑的是
`--update-detection` 打开的那档配置,不是出厂 LongMemEval 默认(那档在 H2 判决里 60 题场
3,126 个事件上 update/contradict 恒为 0)。这一点连同建库时长(2,066–2,820 s/库,中位 2,546 s)
与 H2 判决"预设 B"记录的 2,610 s/库(中位 2,613 s)高度吻合,构成配置正确性的第二重证据。

同台比较只在 b35c 内部按 `question_id` 配对;本次只跑了 TRACE 一家,配对统计(McNemar/簇自助)
留给 `scripts/b35c_score.py` 汇总时统一做。

---

## 2. 实际执行

### 2.1 接手状态与 RESUME 判断

接手时 `results/b35c_trace_sh0.jsonl` .. `_sh3.jsonl` 四个文件均为 **0 字节**——核对
`results/_b35c_trace_sh{0..3}.log`(19:55 起)确认这是更早一次 `--nshards 4` 并行尝试:
进程在第一个库(`wikiP108035-Q39407125`)摄入到 48%(16/33 会话)时被中断(env-limits 记录的
"子代理后台任务被回收"类中断,而非 API 错误——四份 `.err` 无一条 429/529/RateLimit/overloaded 记录),
`open(out_p, "a")` 建了空文件但一行未写就中断,**没有任何已判决行需要保全**。按任务书指示
直接删除这四个空文件(不改变任何结果)。

同一目录下另有 7 个 `results/b35c_trace_locomo_sh{0,1,2,3,12,13,14}.jsonl`(合计 58 行、
15 个不重复 uid、0 条 `retrieval_error`、0 个空答案),源自**同一命令的两波真实执行**:

* **WAVE1**(`_b35c_trace_locomo_timing.txt`:`WAVE1 START 2026-09-03T20:43:21+10:00`):
  `--nshards 4`,4 个进程并行,`shard∈{0,1,2,3}`,`--out-suffix _locomo_sh$s`;
  每进程内部对分到的 uid **顺序**摄入+作答。4 个进程各自处理 4/4/4/3 个 uid 的分配
  (`i%4==shard`,15 库均分),但**前三个进程在处理到各自分到的第 4 个 uid 前再次中断**
  (`sh0`/`sh1`/`sh2` 各只完整跑完 3 个 uid,共 11/11/12 行;`sh3` 本来就只分到 3 个 uid,
  跑满 12 行),留下 3 个 uid(`wikiP54031-Q16198306`/`wikiP54003-Q26001185`/`wikiP54001-Q16225986`,
  均是抽样表里最后 3 行)未覆盖。
* **WAVE2**(单库定点补跑,日志 `_b35c_trace_locomo_sh{12,13,14}.log`,23:32–23:34 完成):
  同一命令改 `--nshards 15 --shard {12,13,14}`(`i%15==shard` 精确点中抽样表第 13/14/15 行,
  即上面 3 个缺口 uid),`--out-suffix _locomo_sh{12,13,14}`,补齐剩余 12 题。

两波用的 `--store-root` 相同(`D:/ZZL_cluade/results/b35c_trace_evoupd_stores`),`force=False`
(`ingest_memories`/`build_graph` 原仓语义:目录已有完整产物则跳过重建),故 WAVE2 对 WAVE1 已建好的
12 座库零touch,只新建了 3 座。7 个分片文件的 `question_id` 并集精确等于 `b35c_questions.jsonl`
的 58 个 qid,无交集重复——**本次会话未新跑一次 TRACE 调用**,只做了:核验完整性
(qid 并集/去重/uid 覆盖/`retrieval_error`/空答案/gold-qtype 一致性五项核对,§2.3)
→ 按 uid 顺序、题内按 `b35c_questions.jsonl` 原序合并为 `results/b35c_trace.jsonl`
→ 删除四个 0 字节的空分片文件。

### 2.2 命令(WAVE1/WAVE2 同一条命令模板,来自 `launch_trace_tail.ps1`)

```powershell
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
$env:TRACE_REPO = "D:/ZZL_cluade/external/TRACE"      # 克隆自 https://github.com/MorinWang/TRACE,commit 1375df3c(与 H2 判决一致)
.venv_trace/Scripts/python.exe scripts/trace_contestant.py `
  --questions results/b35c_questions.jsonl `
  --vols data/wikistate_full_ALL_v25.json `
  --uids-file results/b35c_sample_uids.txt `
  --shard $Shard --nshards {4|15} `
  --evolution --update-detection `
  --out results/b35c_trace_locomo_sh$Shard.jsonl `
  --store-root D:/ZZL_cluade/results/b35c_trace_evoupd_stores
```

`--evolution`(A-Mem 记忆演化改回 LoCoMo 默认 `skip_evolution=False`)与 `--update-detection`
(打开 TRACE Phase 3 更新/矛盾检测,`longmemeval_skip_update_detection=False`)两个开关合起来
即批 33-H2 判决里的"预设 B"/LoCoMo 配置——README 与任务书指定的 "scored 30.0 on the 60-q set,
with update detection enabled" 那档,不是出厂 LongMemEval 默认(预设 A,60 题场只有 16.67)。

环境:`.venv_trace`(Python 3.12.10;`openai 3.7.0` / `sentence-transformers` / `torch` /
`networkx` / `anthropic==0.121.0`,与主环境同版,规避 1.3.0 的 `temperature` 陷阱)。
`OPENAI_API_KEY`(TRACE 侧 LLM,`gpt-4o-mini`,官方端点)+ `ANTHROPIC_API_KEY`(读者+判官)。

### 2.3 核验(本次会话执行,$0)

* `question_id` 并集 == `b35c_questions.jsonl` 的 58 个 qid:缺 0 / 多 0 / 重复 0(逐分片脚本核对,§2.1);
* 15 个 uid 全部出现,与 `b35c_sample_uids.txt` 逐一对照,13 库 4 题 + 2 库(`wikiP551000`/`wikiP551008`)3 题,
  与 README 题集核对结果一致;
* `gold_answer`/`question_type` 与 `b35c_questions.jsonl` 逐题比对,0 处不一致;
* 空答案 0 行,`retrieval_error` 0 行,`trace_path_mode` 58/58 均为 `"paths"`(无一行退化到 `amem_fallback`/`no_paths`);
* commit 校验:`external/TRACE` 的 `git log -1` = `1375df3cef9aa77444f77cbebc3f26e64ba444bb`(2026-08-17),
  与 H2 判决记录的 commit 完全一致;`configs/longmemeval_main.json` 现场确认
  `longmemeval_skip_update_detection: true`(出厂默认,本次靠 `--update-detection` CLI 在运行时覆盖为 `false`,
  未改配置文件本身);
* `scripts/trace_contestant.py` 现场 `git diff` 为空(HEAD 已含所需接线,见 §2.4)——**本次会话零代码改动**。

### 2.4 脚本改动摘要(已在 commit `089ca4b` 入库,非本次新增)

`scripts/trace_contestant.py` 相对更早版本(`fc20d75`)的全部差异只有 3 处、6 行,
全部落在装载/输出段,不碰任何检索/摄入/判分逻辑:

1. 结果行新增 `"build_s": round(ingest_s, 1)`(与既有 `ingest_seconds` 同值,后者未删,
   满足 README §一 "`build_s` 与 `ingest_seconds`" 的兼容口径);
2. `argparse` 新增 `--out PATH`(完整结果路径);
3. `out_p` 改为 `(ROOT / a.out) if a.out else (ROOT / f"results/wsc_s5_trace{a.out_suffix}.jsonl")`
   ——给了 `--out` 用 `--out`,否则保持原硬编码后备值。

`--questions / --vols / --uids-file / --shard / --nshards / --out-suffix / --store-root /
--update-detection / --evolution` 九个参数**在这次改动之前就已存在**(批 33-H2 原始交付),
本次任务书要求的"缺什么补什么"实际上一行都不缺,验证了 README §二总表里对 TRACE 一行
"语料/uid/题集/店目录全部可换"的评估。

---

## 3. 同台数字(n = 58;判官 = ClaudeJudge/claude-opus-5;读者 = claude-haiku-4-5)

| 项 | 值 |
|---|---|
| n | 58(15 库;13 库 4 题、2 库 3 题) |
| **准确率** | **31.03%(18/58)** |
| 读者 in-token 均值 | **10,969.9**(合计 636,252) |
| 读者 out-token 均值 | **89.9**(合计 5,217) |
| `latency_s` 中位 | **7.88 s**(均值 11.66,min 5.27,max 63.45) |
| TRACE 检索延迟中位(`trace_retrieval_latency_s`) | **1.69 s** |
| 上下文长度中位(`trace_context_chars`) | **45,005 字符**(不截断,冻结偏离,对 TRACE 有利) |
| `trace_path_mode` | 58/58 = `"paths"`(零 fallback) |
| 建库 | **2,496.2 s/库均值**(中位 2,545.9;min 2,066.1 / max 2,820.1;15 库合计 37,443.7 s = 645.6 s/题) |
| 建库 LLM 用量(gpt-4o-mini,`RobustLLMController`) | 37,242 次调用,14,806,636 in / 1,402,869 out tok |
| 查询期 TRACE 自身 LLM 用量(`generate_query_llm` 等) | 116 次调用,12,496 in / 1,076 out tok |
| 图统计(15 库合计) | 3,045 事件 / 504 会话;**update_edges = 35 / contradiction_edges = 4** |
| 落盘店 | `results/b35c_trace_evoupd_stores/<uid>/{memories,summaries,graphs}` |

### 分题型

| 题型 | 正确/总 | acc |
|---|---|---|
| change_count | 3/15 | 20.00% |
| count_before | 5/15 | 33.33% |
| first_vs_last | 7/15 | 46.67% |
| longest_tenure | 3/13 | 23.08% |

### 分库(15 库,按 `b35c_sample_uids.txt` 顺序)

| uid | 正确/题 | build_s | 摄入 LLM 调用 |
|---|---|---|---|
| wikiP108035-Q39407125 | 1/4 | 2563.8 | 2688 |
| wikiP108021-Q37837264 | 2/4 | 2404.3 | 2450 |
| wikiP108048-Q38640679 | 0/4 | 2620.5 | 2721 |
| wikiP108008-Q53283502 | 1/4 | 2540.4 | 2605 |
| wikiP39036-Q15039950 | 0/4 | 2358.1 | 2334 |
| wikiP39003-Q6248447 | 1/4 | 2662.2 | 2763 |
| wikiP39033-Q5331705 | 0/4 | 2637.0 | 2671 |
| wikiP39017-Q24568849 | 2/4 | 2820.1 | 2916 |
| wikiP551008-Q29918442 | 2/3 | 2391.8 | 2337 |
| wikiP551000-Q19845625 | 3/3 | 2396.5 | 2360 |
| wikiP551001-Q20667184 | 2/4 | 2066.1 | 1956 |
| wikiP551007-Q9153879 | 2/4 | 2303.1 | 2256 |
| wikiP54031-Q16198306 | 1/4 | 2551.4 | 2380 |
| wikiP54003-Q26001185 | 0/4 | 2582.5 | 2412 |
| wikiP54001-Q16225986 | 1/4 | 2545.9 | 2393 |

---

## 4. 成本(建库/查询期 TRACE 用量为行内实测,判官为均值折算)

价格表按项目冻结口径:haiku-4-5 $1.00/$5.00 per M;claude-opus-5 $5.00/$25.00;
gpt-4o-mini $0.15/$0.60 per M。

| 项 | 用量(15 库 / 58 题) | $ |
|---|---|---|
| TRACE 建库(gpt-4o-mini,37,242 次调用) | 14,806,636 in / 1,402,869 out | **3.0627** |
| TRACE 查询期(gpt-4o-mini,116 次调用) | 12,496 in / 1,076 out | 0.0025 |
| 读者(claude-haiku-4-5,58 题) | 636,252 in / 5,217 out | 0.6623 |
| 判官(claude-opus-5,58 题,按 `judge_cost_measured_20260816.md` 均值 198.28/83.45 tok 折算,未落行实测) | — | ≈0.1785 |
| **合计** | | **≈ $3.91** |

**每库建库 $0.2042**(= 3.0627 / 15)——比 H2 判决记录的 LoCoMo 配置 $0.215/库(60 题场)低约 5%,
同量级,差异来自不同 uid 抽样的会话/事件密度。预算闸门:$3.91 ≤ 本任务 $5 上限;
本次会话新增的墙钟成本仅为核验+合并(数分钟),**远低于 3 小时上限**——因为实际 TRACE 调用
(WAVE1 20:43 → WAVE2 23:34,约 2h51min)发生在本次会话接手**之前**,已在结果文件与日志中留痕,
本文件对此如实注明,不冒领为本次会话的实时执行。

---

## 5. 偏离 60 题标定协议之处(逐条,均与 H2 判决"预设 B"一致,非本次新引入)

1. **配置 = LoCoMo/FAIR(`--evolution --update-detection`)**,不是 TRACE 出厂 LongMemEval 默认
   (后者 `longmemeval_skip_update_detection=true`,`skip_evolution=true`)。这是任务书明确指定的档位,
   已在 §1/§2.2 交代理由与出处(H2 判决"预设 B",60 题场 30.00)。
2. **上下文不截断**:读者看到的是 TRACE `pipeline.retrieve().context` 整包(中位 45,005 字符 ≈ 10,970
   读者输入 tok),不像 repro_batch2/4 家族截到 300–400 字符——README §一冻结的既有偏离,对 TRACE 有利。
3. **turn 解析**:WikiState 的 `turns` 以 `str(dict)` 存,`parse_turn()` 用 `ast.literal_eval` 还原;
   解析失败时整段字面量当文本喂入(与 H2 判决 §三 偏离 3 同一处理,未重新统计本次失败率)。
4. **判官 token 未落行**:`ClaudeJudge` 用量记在内存 `judge.total_usage`,`trace_contestant.py` 不写进
   结果行,故判官 $ 是**按测量均值折算的估计**,其余(建库、查询期、读者)全部实测。
5. **端点**:无 OpenRouter key,`api_base=None` 走 OpenAI 官方端点,模型仍 `gpt-4o-mini`(与 H2 判决同)。
6. **题面版本**:b35c 是 v2.5 的 58 题(`_v2cc/cb/lt/fl`),与 H2 判决 v1 60 题存档(`wsc_s5_trace_evoupd.jsonl`,
   30.00)**不可直接相减**——§1 已用"同量级、彼此复现"而非"相等"来表述这个对照。

## 6. 未做

- 未跑出厂 LongMemEval 默认配置(H2 判决"预设 A")在 b35c 上的对照臂——任务书只要求 LoCoMo/FAIR 一档。
- 未做与其它 14 系统的配对统计(McNemar/簇自助):本任务只交付 TRACE 一家的合并与核验,
  配对表留给 `scripts/b35c_score.py` 汇总或后续任务统一做。
- `results/b35c_leaderboard.md` 尚未加入 TRACE 行(该文件由另一批任务生成/维护,本文件 §1 已给出
  插入后的名次供参考,未直接改动该文件,避免与其汇总脚本的口径冲突)。
- 未执行任何 git 操作(按任务书:no git commit)。

## 7. 文件清单

| 文件 | 内容 |
|---|---|
| `results/b35c_trace.jsonl` | 最终交付,58 行,按 uid 顺序(`b35c_sample_uids.txt`)+ 题内原序合并 |
| `results/b35c_trace_locomo_sh{0,1,2,3,12,13,14}.jsonl` | 源分片(WAVE1 四片 + WAVE2 三片),保留作溯源,未删除 |
| `results/b35c_trace_evoupd_stores/<uid>/{memories,summaries,graphs}` | 15 库落盘产物 |
| `results/_b35c_trace_locomo_sh*.log` / `.err` | 两波执行的运行日志(WAVE2 三个 `.err` 无 429/529 记录) |
| `results/b35c_trace_sh{0,1,2,3}.jsonl` | **已删除**(更早中断尝试留下的 0 字节空文件,任务书指示移除) |
