# b35c 判决:amem(A-MEM,agiresearch)× WikiState v2.5 小样本(15 库 / 58 题)

日期 2026-09-03。系统 `amem`,harness `scripts/repro_batch4.py --system amem`。
本文件全部数字均由 **`results/b35c_amem.jsonl`(58 行,本轮实跑)** 重新计算,不引用任何存档值。

## 判决

**A-MEM 在 v2.5 小样本上的猜想被否定**:58 题准确率 **39.66%**(23/58)。
Zettelkasten 演化笔记没有把"状态随时间变更"这类题做对——`first_vs_last` 80.0% 尚可(纯首尾取值),
但一旦要数变更次数就崩:`change_count` 13.33%、`longest_tenure` 23.08%、`count_before` 40.00%。
检索永远命中 10 条(`memories_n` 全为 10),不是召回为空导致的失败,而是演化笔记把"哪一年换成了什么"
摊平成了主题笔记后无法计数。

## 一、实际执行

| 项 | 值 |
|---|---|
| 语料 | `data/wikistate_full_ALL_v25.json` |
| 库清单 | `results/b35c_sample_uids.txt`(15 uid,按文件顺序) |
| 题集 | `results/b35c_questions.jsonl`(58 题) |
| 结果 | `results/b35c_amem.jsonl`(58 行,`question_id` 无缺无多无重复,与题集 58 个 qid 精确同集;`gold`/`qtype` 逐行核对一致) |
| A-MEM 源码 | `D:\ZZL_cluade\external\A-mem`,commit **`ceffb860f0712bbae97b184d440df62bc910ca8d`**(2025-12-12,重新 clone;README §三.9 记录的旧 Temp 路径已空)。每行都带 `amem_repo` / `amem_commit` |
| 运行环境 | 主环境 Python 3.14.5(`anthropic 0.121.0`、`chromadb`、`sentence_transformers`、`openai`);**未用隔离 venv**(README amem 节写的就是主环境) |
| 墙钟 | run2 2026-09-03 20:41:51 → 21:17:04 = **35 分 13 秒**(单进程串行 15 库)。此前 19:59 的 run1 在模型加载后被中断,**0 行入档**,本轮 58 行全部产自 run2 |
| 断点续跑 | harness 追加写 + `done` 集按 `question_id` 跳过;run1 未写行,故未触发跳过,58 题均为一次跑完 |

命令(实际执行的那一条):

```
cd D:\ZZL_cluade
$env:PYTHONUTF8=1
python scripts/repro_batch4.py --system amem --amem-repo external/A-mem \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file results/b35c_sample_uids.txt \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_amem.jsonl
```

日志 `results/b35c_amem_run2.log`(run1 残留 `results/b35c_amem_run.log`)。

## 二、脚本改动摘要(`scripts/repro_batch4.py`,只加接线)

与 amem 有关的四处(cognee 相关的 `set_store_root` / litellm 用量回调是同批另一系统的接线,与 amem 无关):

1. **`--amem-repo PATH`**(相对 ROOT)→ 写入环境变量 `AMEM_REPO`;`AmemSystem.__init__` 改为
   `repo = os.environ.get("AMEM_REPO") or <旧硬编码 Temp 路径>`,再 `sys.path.insert(0, repo)`。
   默认值仍指旧路径,存档命令语义不变。同时 `git -C repo rev-parse HEAD` 取 commit,与 repo 一起
   作为 `row_extra` 写入每一行(`amem_repo` / `amem_commit`),满足 README "重新 clone 须注 commit"。
2. **`--vols` / `--uids-file` / `--out`**(`--questions-file` 原就有)——按 README §二 骨架替换 `main()` 的装载段:
   `vols` 决定 `entries`;`--uids-file` 给出时 `picked` 直接取文件顺序(不再走 `sample_stores()` 的 v1 15 库);
   `picked = [u for u in picked if u in by_uid]` 从 `--questions-file` 分支里提出来,对两条路径都生效
   (原实现只在给了题集时过滤,给了 uid 清单时会漏过滤);`out_p = ROOT / a.out if a.out else <原路径>`。
3. **建库用量埋点**:`AmemSystem.ingest` 里把 `m.llm_controller.llm.client.chat.completions.create`
   包一层只读 `response.usage` 的计数器(参数原样透传,失败时静默跳过),把该库的
   `amem_ingest_llm_in/out/calls` 随行写出。**不改 A-MEM 的任何调用参数或提示词。**
4. **`build_s`**:结果行在保留 `ingest_seconds` 的同时增写同值 `build_s`(README 要求的字段名);
   并在收尾多打一行 `judge.total_usage`。

**没有动的**(逐项确认):`sess_text`(日期前缀 + 前 6 轮 + 每轮 400 字符)、`READER_MODEL="claude-haiku-4-5"`、
`temperature=0.0`、`max_tokens=300`、`READER_SYS`(自 `repro_batch2` 导入)、user 模板、空检索占位
`(no memories retrieved)`、读者 3 次重试、`AgenticMemorySystem(model_name="all-MiniLM-L6-v2",
llm_backend="openai", llm_model="gpt-4o-mini")`、`add_note(text, time=date)`、`search_agentic(query, k=10)`、
记忆行 `- {content[:400]}`、判官 `qvf.judge.ClaudeJudge()`(默认 `claude-opus-5`)、会话按 `date` 升序。

**每库全新库**:`ingest` 每个 uid 新建一只 `AgenticMemorySystem`;A-MEM 的 `ChromaRetriever` 用
`chromadb.Client(Settings(allow_reset=True))`(纯内存),且 `AgenticMemorySystem.__init__` 先 `client.reset()`
再建集合 → 库间零共享、零落盘(amem 无 `results/b35c_amem_stores`,与存档一致)。

## 三、结果

n = 58,15 库。

| 指标 | 值 |
|---|---|
| 准确率 | **39.66%**(23/58) |
| 读者输入 token 均值 | **1211.8**(合计 70,283) |
| 读者输出 token 均值 | **84.6**(合计 4,908) |
| `latency_s` 中位 | **4.88 s**(均值 5.22,范围 3.34–9.65) |
| 建库 | **120.0 s/库**(中位 120.4,15 库合计 1799.7 s)= 31.0 s/题 |
| 检索条数 | 全部 58 题命中 10 条(`memories_n` 恒为 10) |
| 空答复 | 0 |

分题型:

| 题型 | 正确/总 | 准确率 |
|---|---|---|
| change_count | 2/15 | 13.33% |
| count_before | 6/15 | 40.00% |
| first_vs_last | 12/15 | 80.00% |
| longest_tenure | 3/13 | 23.08% |

## 四、成本(冻结价格表)

| 环节 | 用量 | $ |
|---|---|---|
| 建库 gpt-4o-mini(**实测**,行内 `amem_ingest_*`) | 1,357,153 in / 204,941 out,489 次调用 | **0.3265**(= **$0.02177/库**) |
| 读者 haiku-4-5 | 70,283 in / 4,908 out | 0.0948 |
| 判官 claude-opus-5(进程内 `judge.total_usage`:11,544 in / 5,140 out,58 次) | — | 0.1862 |
| **合计** | | **≈ $0.61** |

预算闸门:读者+建库 **$0.42**(≤ $5),含判官 $0.61;墙钟 **35 分钟**(≤ 3 h)。**15 库全跑,未做任何截断。**
本轮建库首次拿到 A-MEM 的实测 token(存档 README §四 只有批级估计 $0.027/库);实测 $0.0218/库,同量级。

## 五、偏离 / 限定

1. **源码为重新 clone,不得与存档 43.33 直比。** README §三.9 记录的旧 Temp 克隆已被清空、commit 未入档;
   本轮用 `github.com/agiresearch/A-mem` commit `ceffb860`。存档口径还是 v1 60 题,题面也不同(v2.5 的
   `change_count` 题面已含"首值不计"说明),两处不可比的理由叠加。b35c 的比较只在 b35c 内部按
   `question_id` 配对。
2. **建库比存档快 1.48×**(120.0 vs 177.7 s/库)。同为串行、同为 gpt-4o-mini,差异应归到 clone 版本
   与网络抖动;本行不作为"A-MEM 变快了"的结论,只作为本轮实测记录。
3. **A-MEM 自身的演化步骤有 5 次 JSON 解析失败**(日志 `Error in memory evolution: Unterminated string
   starting at ...`,`grep -c` = 5;按日志位置归属为 wikiP108021 / wikiP39033 / wikiP39017 / wikiP54003 /
   wikiP54001 各 1 次——A-MEM 的这条错误不带 uid,归属按"落在哪两条 `ingested` 行之间"推定)。
   这是 A-MEM 自己吞掉的异常(其代码 catch 后跳过该次演化),摄入未中断、笔记仍然入库;
   属该系统在长会话文本上的原生行为,未做任何补救(补救会改动被测系统)。
4. **写侧非确定性**:A-MEM 的笔记构造/演化用 gpt-4o-mini 默认温度(未由 harness 指定),同库重跑
   笔记内容会漂移。读者/判官侧 `temperature=0` 不变。
5. `probing_queries` / `attribution` 未使用(全系统统一)。amem 无落盘店目录,故未创建
   `results/b35c_amem_stores`;未写入任何既有店目录或结果文件。
6. run1(19:59)在 sentence-transformers 权重加载后被中断,未写出任何行;本轮 58 行同属 run2 一次跑完,
   不存在跨进程拼接的行。
