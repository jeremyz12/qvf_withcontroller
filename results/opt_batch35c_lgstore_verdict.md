# b35c 判决:lgstore(langgraph InMemoryStore + OpenAI 嵌入)× WikiState v2.5 小样本

日期 2026-09-03。系统 = `lgstore`;harness = `scripts/repro_batch4.py --system lgstore`。
**判决:猜想被证实 —— lgstore 在 v2.5 58 题上跑通全部 15 库,acc = 46.55%(27/58)。**
本文件所有数字均由 `results/b35c_lgstore.jsonl`(58 行,本次实际写出)重新计算。

---

## 一、跑了什么

| 项 | 取值 |
|---|---|
| 语料 | `data/wikistate_full_ALL_v25.json` |
| 库清单 | `results/b35c_sample_uids.txt`(15 uid,全部跑完) |
| 题集 | `results/b35c_questions.jsonl`(58 题,全部作答;`question_id` 集合与题集**完全相等**,无缺、无多、无重复) |
| 结果 | `results/b35c_lgstore.jsonl`(58 行) |
| 日志 | `results/b35c_lgstore_run.log` |
| 每库会话数 | 33–36,合计 504,按 `date` 升序逐条 `store.put((uid,"sessions"), f"s{i}", {"text": sess_text(s)})` |
| 检索 | `store.search((uid,"sessions"), query=q, limit=10)`;58 题全部 `memories_n = 10` |
| 记忆行 | `- {h.value['text'][:400]}`(400,冻结值,未改) |
| 读者 | `claude-haiku-4-5`,`temperature=0`,`max_tokens=300`,`READER_SYS` 逐字;58 题零空答、零重试落空 |
| 判官 | `qvf.judge.ClaudeJudge()` 默认档 `claude-opus-5`(`QVF_JUDGE_MODEL` 未设) |
| 环境 | 主环境 Python 3.14.5,`anthropic 0.121.0`、`langgraph`、`langchain_openai`;`OPENAI_API_KEY`(嵌入)+ `ANTHROPIC_API_KEY`。**不需要隔离 venv**(README §三.5 (d) 即如此) |
| 落盘店 | 无(InMemoryStore,进程内);因此无 `b35c_lgstore_stores/` 目录 |

### 命令(本次实跑,续跑口径)

```
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python scripts/repro_batch4.py --system lgstore \
  --vols data/wikistate_full_ALL_v25.json \
  --uids-file results/b35c_sample_uids.txt \
  --questions-file results/b35c_questions.jsonl \
  --out results/b35c_lgstore.jsonl
```

### 续跑处理(RESUME)

接手时 `results/b35c_lgstore.jsonl` 已有 **51 行判决行**(13 库整库 + `wikiP54003-Q26001185` 的 1 题),
缺 7 题(`wikiP54001-Q16225986` 的 4 题 + `wikiP54003-Q26001185` 的 v2cb/v2fl/v2lt)。
核 `repro_batch4.py::main()` 确认 harness **追加写 + 按 `question_id` 断点续跑**
(`fh = open(out_p, "a")`;`done = {…question_id…}`;`qs = [q for q in by_uid[uid] if q["qid"] not in done]`),
故**未移动、未覆盖任何既有判决行**,直接原命令续跑,只作答缺失的 7 题。
旧 51 行另存一份只读备份于 scratchpad(`b35c_lgstore_backup51.jsonl`),未参与合并。
续跑对这 2 个 uid 各重建了一座**全新**命名空间(进程新起,`InMemoryStore` 为空),无旧库复用。

## 二、脚本改动摘要

**本次未改任何脚本代码。** `scripts/repro_batch4.py` 的 b35c 接线在接手前已存在于工作区
(`git diff scripts/repro_batch4.py`:98 插入 / 8 删除),lgstore 相关部分仅为装载段与输出路径:

- 新增 CLI:`--vols`(逗号分隔语料 json,默认 `VOLS`)、`--uids-file`(uid 清单,替代 `sample_stores()` 的 `picked`,保持文件顺序)、`--out`(结果 jsonl 全路径)、`--store-root`(仅对实现了 `set_store_root` 的系统生效,lgstore 无)、`--amem-repo`(与 lgstore 无关)。
- `picked = [u for u in picked if u in by_uid]` 从 `--questions-file` 分支内提到分支外,使 `--uids-file` 生效。
- 输出行新增 `build_s`(= `round(ingest_s,1)`,与 `ingest_seconds` 同值,`ingest_seconds` 保留)。
- 其余改动(A-MEM 路径/计量、cognee 用量回调与 store root)对 lgstore 无影响;`LgStoreSystem`、`sess_text`、`READER_MODEL/READER_SYS`、`max_tokens=300`、`temperature=0`、`limit=10`、`[:400]` 截断、判官全部**逐行未动**。

## 三、结果

n = 58,15 库,acc = **46.55%**(27/58)。

| 题型 | 正确/题数 | acc |
|---|---|---|
| first_vs_last | 15/15 | **100.00%** |
| count_before | 8/15 | 53.33% |
| change_count | 3/15 | 20.00% |
| longest_tenure | 1/13 | **7.69%** |

形态与 v1 存档一致(`results/wsc_s5_lgstore.jsonl`,60 题 acc 55.00):平坦语义检索能一击命中"首/末值"类,
对需要跨全部会话做计数与区间比较的题(change_count / longest_tenure)基本无能。
**注意:v2.5 58 题与 v1 60 题题面不同(v2.5 change_count 题面已含"首值不计"说明),两者不得直比**(README §五)。

## 四、成本与时间

| 指标 | 值 | 口径 |
|---|---|---|
| 读者 input 均值 | **1195.0 tok/题**(合计 69,308) | 行内 `usage_input_tokens` |
| 读者 output 均值 | **84.3 tok/题**(合计 4,887) | 行内 `usage_output_tokens` |
| `latency_s` 中位 | **4.97 s**(均值 5.14,范围 3.19–9.73;58 题合计 297.9 s) | 检索开始 → 判官返回 |
| 建库 | **3.87 s/库**(中位 3.80;15 库合计 58.0 s)= **1.00 s/题** | 行内 `build_s`/`ingest_seconds`,按库去重 |
| 读者 $ | **$0.0937** | 69,308 in × $1/M + 4,887 out × $5/M(haiku-4-5) |
| 建库 $(嵌入) | **≈$0.0040(估计)** | 未埋点;按 785,751 摄入字符 + 6,458 查询字符 ÷ 4 ≈ 198k tok × $0.02/M |
| 判官 $ | **≈$0.028(估计)** | 本进程实测 7 次调用 1,427 in / 400 out(203.9 / 57.1 per call);按同均值外推 58 次 ≈ 11,826 in / 3,314 out × opus-5 $5/$25 per M。前 51 行的判官用量未落盘 |
| **合计(本系统 b35c 全程)** | **≈$0.126** | 读者实测 + 嵌入/判官估计;远低于 $5 上限 |
| 墙钟 | 本次续跑 7 题 ≈ 1 分钟;整批(51 题旧 + 7 题新)读者+判官+建库合计 ≈ 6 分钟 | 远低于 3 h 上限 |

15 库全部跑完,未触发"只跑前 N 库"的降级条款。

## 五、与 60 题标定协议的偏离

1. **`build_s` 字段在文件内不齐**:先跑的 51 行只有 `ingest_seconds`(该字段是当时脚本的输出),
   后补的 7 行同时有 `ingest_seconds` 与 `build_s`,两者同值。README §一约定的
   `build_s = row.get("build_s", row.get("ingest_seconds"))` 读法对 58 行全部有效,不影响任何统计。
2. **`wikiP54003-Q26001185` 建库了两次**:中断的那次 4.1 s(其 1 行 v2cc 携带),续跑那次 5.8 s(其 3 行携带)。
   按库去重取该库首值 4.1 s 计入上表;若改取 5.8 s,则 3.87 → 3.98 s/库(中位不变),差异不影响结论。
   两次建库都是全新命名空间、同一份按日期排序的会话,建库内容一致。
3. **建库嵌入 token 未埋点**(与存档同,README §四标"仅嵌入,未埋点"):上表 $0.0040 是按字符数除 4 的**估计**,不是实测。
4. **判官用量只对本次 7 次调用有实测**;58 题的判官 $ 为按该均值外推的估计。
5. 其余协议项(语料/uid/题集/建库顺序/k=10/400 截断/读者模型与提示/判官)与 60 题标定场逐项一致,无偏离。
