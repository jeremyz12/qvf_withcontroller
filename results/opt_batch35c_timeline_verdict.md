# opt-batch35c / timeline(TReMu 式时间线组织)× WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。执行 `results/b35c_README.md` §一共享协议 + §三.1 的 timeline 一节。
**判决:跑通,58/58 题全部作答并判分,零缺题、零判官回退、零 API 报错;acc = 56.90%(33/58)。**
下文所有数字均由本轮新写的 `results/b35c_timeline.jsonl`(58 行)与
`results/b35c_timeline_llm_usage.jsonl`(562 行)重新计算,不引用任何存档。

---

## 一、跑了什么

| 项 | 取值 |
|---|---|
| 语料 | `data/wikistate_full_ALL_v25.json`(144 条目) |
| 库清单 | `results/b35c_sample_uids.txt`(15 uid,按文件顺序建库) |
| 题集 | `results/b35c_questions.jsonl`(58 题) |
| 结果 | `results/b35c_timeline.jsonl`(58 行,14 字段,schema 与 §三.1(f) 一致) |
| 建库 | 每 uid 一座全新库(`TimelineSystem.stores[uid]` 由空 list 起建,库间零共享);会话按 `date` 升序 |
| 会话文本 | `"\n".join(str(t)[:400] for t in turns[:6])`(harness 原样,未改) |
| 写侧 | 每会话一次 `claude-haiku-4-5`,`max_tokens=200`,`temperature=0`,提示 "Write ONE timeline memo line …";504 次调用,零失败 |
| 读侧 | **无检索**(`search()` 忽略 query,返回全时间线),记忆行 `- {line[:300]}`(300 冻结) |
| 读者 | `claude-haiku-4-5`,`temperature=0`,`max_tokens=300`,`READER_SYS` 逐字,user = `MEMORIES:\n{memtext}\n\nUSER'S NEW MESSAGE: {question}` |
| 判官 | `qvf.judge.ClaudeJudge()` 默认档 = `claude-opus-5`(运行时打印确认);`judge.judge(question, str(gold), answer, qtype)` |
| 落盘店 | 无(timeline 全在进程内存) |
| 环境 | 主环境 Python 3.14.5,`anthropic 0.121.0`(运行时打印确认);仅 `ANTHROPIC_API_KEY` |
| 墙钟 | 954.4 s = **15.9 min**(usage log 首尾时间戳),预算 3 h |

### 命令

协议命令(README §三.1(c),逐字):

```
cd D:\ZZL_cluade
python scripts/repro_batch2.py --system timeline \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file results/b35c_sample_uids.txt \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_timeline.jsonl
```

实际执行的是一个**只做旁路观测的外壳**
`C:\Users\25243\AppData\Local\Temp\claude\D--ZZL-cluade\127d6855-ac31-4f09-a027-67dbfc5cf191\scratchpad\b35c_run_timeline.py`:
它用上面这串 argv 调 `scripts/repro_batch2.py::main()`,并在 `anthropic.resources.messages.Messages.create`
外面包一层透传观察器,把每次调用的 `model / max_tokens / has_system / input_tokens / output_tokens / dt`
写进 `results/b35c_timeline_llm_usage.jsonl`(存档 repro_batch2 不记写侧用量,README §三.1(e) 标"未埋点";
本轮借此把建库 $ 从估计升级为实测)。观察器不改任何入参、不吞异常(异常原样 re-raise,交 harness 自己重试),
因此对协议是零偏离。日志 `results/b35c_timeline_run.log`。
判官走 `client.messages.parse`,不经过 `Messages.create`,故不在该 usage log 中(见 §四判官口径)。

### 脚本改动(diff 摘要)

`scripts/repro_batch2.py` 只动 `main()` 的装载段,按 README §二骨架加四个参数,**系统类 / 读者 / 判官 / 提示词 / 常量一行未动**:

- `argparse` 新增 `--vols / --uids-file / --questions-file / --out`(另有 `--store-root`,mem0 专用,timeline 不走);
- `out_p = ROOT / a.out if a.out else ROOT / f"results/wsc_s5_{sysm.name}.jsonl"`(原为硬编码);
- `vols = a.vols.split(",") if a.vols else VOLS`,`entries` 从 `vols` 装载(原为硬编码 `VOLS` 四卷 v1);
- `--questions-file` 给出时 `by_uid` 从题集 jsonl 重建(键 `qid/qtype/question/gold` 与 `sample_stores()` 产物同名);
- `--uids-file` 给出时 `picked` 取该文件行序;末尾仍 `picked = [u for u in picked if u in by_uid]`。

断点续跑逻辑是 harness 原有的(`done = {question_id}` 集合,追加写)。本轮该文件在开跑前不存在,
15 库全部一次跑完(run.log 逐库 "answered 4/3" 合计 58),因此没有触发续跑,也没有历史行需要合并。

---

## 二、结果

**n = 58,acc = 56.90%(33/58)**

| 题型 | 正确 / 总 | acc |
|---|---|---|
| first_vs_last | 15 / 15 | **100.0%** |
| count_before | 7 / 15 | 46.7% |
| change_count | 6 / 15 | 40.0% |
| longest_tenure | 5 / 13 | 38.5% |

形态:把整条时间线塞给读者,"首值 vs 末值"这类只需读两端的题满分;
需要沿时间线做计数 / 取最长区间的三类聚合题都掉到 40% 上下——记忆本身在场(无检索损失),
失分发生在读者对长时间线做计数与区间比较这一步。

---

## 三、成本 / 时间(全部实测)

| 量 | 值 |
|---|---|
| 读者 in / out 均值 | **1853.8 / 95.3** tok/题(合计 107,518 / 5,528) |
| `latency_s` 中位 | **4.61 s**(均值 4.91,min 3.06,max 12.08;口径 = 检索开始→判官返回) |
| 建库(15 库去重) | 合计 **672.3 s**;**44.82 s/库**(中位 44.10)= **11.59 s/题** |
| 建库 LLM 用量 | 504 次 haiku(`max_tokens=200`),**221,853 in / 26,821 out** |
| 建库 $(实测) | **$0.3560 / 15 库 = $0.02373 每库**(haiku-4-5 $1/$5 per M) |
| 读侧 $(实测) | **$0.1352**(58 题,$0.00233/题) |
| 判官 $(估计) | $0.1785(58 次 opus-5,按 `results/judge_cost_measured_20260816.md` 实测均值 198.28/83.45 tok 折算) |
| **合计** | **≈ $0.67**(实测 $0.491 + 判官估计 $0.179),预算上限 $5 |
| 落盘 | 0 字节(无店目录) |

每库建库秒(逐库,`ingest_seconds` 去重):

| uid | 题数 | build_s |
|---|---|---|
| wikiP108035-Q39407125 | 4 | 44.1 |
| wikiP108021-Q37837264 | 4 | 43.9 |
| wikiP108048-Q38640679 | 4 | 43.3 |
| wikiP108008-Q53283502 | 4 | 44.7 |
| wikiP39036-Q15039950 | 4 | 49.2 |
| wikiP39003-Q6248447 | 4 | 45.2 |
| wikiP39033-Q5331705 | 4 | 46.9 |
| wikiP39017-Q24568849 | 4 | 46.7 |
| wikiP551008-Q29918442 | 3 | 42.3 |
| wikiP551000-Q19845625 | 3 | 43.8 |
| wikiP551001-Q20667184 | 4 | 45.4 |
| wikiP551007-Q9153879 | 4 | 43.8 |
| wikiP54031-Q16198306 | 4 | 43.9 |
| wikiP54003-Q26001185 | 4 | 43.7 |
| wikiP54001-Q16225986 | 4 | 45.4 |

注:两个 uid 只有 3 题,`build_s` 必须按库去重后再取均值(README §一口径说明);
按行取均值会得到 44.88,不是 44.82。

---

## 四、与 60 题标定场的偏离

1. **零协议偏离**:读者模型 / temperature / max_tokens / `READER_SYS` / 记忆行 300 字符截断 /
   会话段落化 / 判官 `ClaudeJudge()` 默认档 / 每题记忆 = 全时间线(timeline 本就无 top-k)——全部与
   `scripts/repro_batch2.py --system timeline` 的存档跑法逐字相同。改动只在 `main()` 装载段的四个 CLI 参数。
2. **旁路观测器**(§一):新增,不改协议;仅为把建库 $ 从"未埋点"升级为实测。
3. **判官 token 未落行**:`ClaudeJudge` 把用量记在 `judge.total_usage`(内存),harness 不写进结果行,
   进程结束即丢失;本轮外壳只钩了 `Messages.create`,而判官走 `messages.parse`,所以判官 $ 是**估计**,
   其余全部实测。这是 harness 既有形态,未改。
4. **题面不可与存档直比**:存档 60 题是 v1 题面(acc 63.33),本轮是 v2.5 的 58 题(`_v2cc/cb/lt/fl`,
   change_count 题面已含"首值不计"说明)。56.90% 与 63.33% **不构成同题对比**;
   timeline 的对比只在 b35c 内部按 `question_id` 与其余系统配对。
5. **建库时长与存档一致**:44.82 s/库 vs 存档 43.9 s/库(+2.1%),同一形态,可作为本次复跑健康度的旁证。

## 五、核查

- `question_id` 集合 == `b35c_questions.jsonl` 的 58 个 qid:缺 0 / 多 0 / 重复 0;
- 每行 `gold_answer` 与 `question_type` 与题集逐题一致;
- 15 个 uid 全部出现,`memories_n` ∈ [33, 36] = 各库会话数(与 run.log 的 "ingested N" 逐库吻合);
- 空答案 0 行,判官 FALLBACK 0 行,API 异常 0 次(usage log 无 `error` 记录);
- 读侧 token 双通道对账:结果行合计 107,518/5,528 = usage log 中 58 次 `max_tokens=300` 调用合计,分毫不差;
- 调用计数自洽:504 建库调用 = 15 库会话数之和(33×9 + 34×4 + 35 + 36 = 504),562 = 504 + 58。
