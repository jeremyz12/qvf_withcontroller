# 批 33-H4 判决:MemOS(MemTensor,Apache-2.0)× WikiState 60 题标定场

状态:**RUN 完成**(60/60,两条抽取器臂各一遍)。
Docker 路线(Neo4j + Qdrant + server / tree_text)**BLOCKED**,已改走预注册允许的
纯 Python `general_text` + 内嵌 Qdrant 路线,详见 §6。

---

## 1. 判决

**猜想"MemOS 的写时结构化记忆能把 60 题标定场抬到直读带以上"被否定。**

MemOS 落在 **45.00**(haiku 抽取臂,n=60,题级自助 95% CI [31.7, 58.3],
簇级 95% CI [33.3, 58.3])。

- vs 直读 top-10 检索(51.67):**−6.67pp,簇自助 CI [−16.7, +3.3] 跨零,
  簇级符号检验 p=0.51 —— 与直读打平,不可作"高于/低于直读"的主张**;
- vs QVF 编译臂(83.33):−38.33pp,簇 CI [−56.7, −20.0] 不跨零,簇 p=0.013;
  vs QVF smoc(85.00):−40.00pp,簇 CI [−56.7, −23.3],簇 p=0.0034 —— **显著低于 QVF 臂**;
- vs Mem0(26.67):+18.33pp,簇 CI [+8.3, +30.0] 不跨零,簇 p=0.021 —— **显著高于 Mem0**;
- vs timeline(63.33):−18.33pp,簇 CI [−35.0, −1.7](题级 p=0.080,簇级 p=0.146);
  vs lgstore(55.00):−10.00pp,簇 CI [−25.0, +3.3] 跨零。

**次判决:MemOS 的分数不由抽取模型档位决定。** 同一协议换抽取器
(claude-haiku-4-5 vs gpt-4.1-mini)差 **+1.67pp**,簇自助 CI [−13.3, +15.0],
题级符号检验 p=1.0 —— 两档不可分。瓶颈在 MemOS 的记忆构造/检索形态,不在 LLM 档位。

**机制观察(非统计主张):MemOS 在本考场是"扩张"而非"整合"。**
33.3 会话/库 → 135.2~135.9 条记忆节点(≈4.1 条/会话),与 Mem0 的写时合并/删除
路线相反;错误集中在需要跨会话计数的题型(count_before 26.7~33.3%),
而 top-10 语义检索一次只端回 10 条节点,聚合题所需的全序列因此不可能齐备。

---

## 2. 同台数字(60 题标定场,v1;判官 = ClaudeJudge/claude-opus-5;读者 = claude-haiku-4-5)

| 臂 | n | acc | 题级 95% CI | 簇级 95% CI | in-tok | out-tok | 延迟中位 | 建库 |
|---|---|---|---|---|---|---|---|---|
| **MemOS(haiku 抽取)** | 60 | **45.00** | [31.7, 58.3] | [33.3, 58.3] | 609 | 88 | 5.16s | 46.2s/题 |
| MemOS(gpt-4.1-mini 抽取) | 60 | **43.33** | [30.0, 56.7] | [30.0, 58.3] | 592 | 88 | 4.93s | 67.6s/题 |

榜单口径参照(引自 `results/wikistate_leaderboard_20260828.md` 与
`results/sys16_bootstrap_ci_20260829.md`,本次未重跑):
Mem0 26.7 / LangMem 40.0 / A-MEM 43.3 / cognee 46.7 / txtai 53.3 / lgstore 55.0 /
timeline 63.3 / 直读 51.7 / QVF 编译臂 83.3 / smoc 85.0。
**MemOS 落在 A-MEM(43.3)与 cognee(46.7)之间的产品带,CI 与该带全体重叠——
相邻名次不作主张**(沿用 08-29 修补审计结论)。

### 分题型(各 15 题)

| 题型 | haiku 抽取 | gpt-4.1-mini 抽取 |
|---|---|---|
| longest_tenure | 53.33 | 40.00 |
| change_count | 53.33 | 53.33 |
| count_before | 33.33 | 26.67 |
| first_vs_last | 40.00 | 53.33 |

### 成本(实测 token,非估算)

| 项 | haiku 抽取臂 | gpt-4.1-mini 抽取臂 |
|---|---|---|
| MemOS 建库 LLM(15 库合计) | in 1,076,555 / out 303,790 | in 944,347 / out 264,824 |
| MemOS 建库嵌入(15 库合计) | 97,037 tok | 85,484 tok |
| 建库 $/库 | $0.1732 | $0.0535 |
| 建库摊销 $/题(4 题/库) | $0.04329 | $0.01339 |
| 读端 $/题 | $0.00105 | $0.00103 |
| **合计 $/题** | **$0.04434** | **$0.01442** |
| 判官(claude-opus-5,60 次) | in 11,642 / out 8,066 → $0.2599 | in 11,664 / out 6,777 → $0.2277 |

价格口径(项目既用):haiku-4-5 $1.00/$5.00 per M;gpt-4.1-mini $0.40/$1.60 per M;
text-embedding-3-small $0.02/M;claude-opus-5 $5.00/$25.00 per M。

**本轨实际花费 ≈ $4.2**(两臂正式跑 $1.09 + $2.92,两次单库冒烟 ≈ $0.15,
探针 < $0.01),上限 $30,**未触顶**。

### 建库形态

| | haiku 抽取 | gpt-4.1-mini 抽取 |
|---|---|---|
| 会话/库 | 33.3 | 33.3 |
| MemOS 抽出记忆节点/库 | 135.9 | 135.2 |
| 抽取失败会话(3 次重试后仍失败) | 0 | 0 |
| 建库耗时/库(mean / median) | 184.8s / 182.6s | 270.5s / 271.0s |

---

## 3. 装配(隔离环境,精确复现)

```bash
# 1) 隔离 venv(Python 3.12.10;项目主环境是 3.14,MemOS 未支持)
py -3.12 -m venv .venv_memos

# 2) MemOS 本体 + 其可选依赖(chonkie=句切分器,qdrant-client=向量库,
#    langchain_text_splitters=其 markdown 切分器;neo4j 仅为完整性,本跑未用)
./.venv_memos/Scripts/python.exe -m pip install "MemoryOS==2.0.32"
./.venv_memos/Scripts/python.exe -m pip install chonkie qdrant-client neo4j langchain_text_splitters
# 3) 让 harness 能复用项目自己的读者/判官(与其它考生逐字同款)
./.venv_memos/Scripts/python.exe -m pip install "anthropic==0.121.0" rank_bm25
#    anthropic 钉 0.121.0 = 主环境同版本,保证 ClaudeJudge 行为一致
```

安装校验:`MemoryOS 2.0.32`,License `Apache-2.0`,
Repository `https://github.com/MemTensor/MemOS`,import 名 `memos`。

---

## 4. 运行(精确命令)

```bash
# 冒烟(1 库 4 题)
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv_memos/Scripts/python.exe \
  scripts/repro_batch33h_memos.py --limit-stores 1 --out-suffix _smoke

# A 臂:gpt-4.1-mini 抽取(MemOS 出厂 openai 后端,默认 api_base)
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv_memos/Scripts/python.exe \
  scripts/repro_batch33h_memos.py --workers 3 \
  > scratchpad/memos_60q.log 2>&1

# B 臂(头条,预注册"同档 haiku 抽取"口径):claude-haiku-4-5 走 Anthropic
#     OpenAI 兼容端点;--drop-top-p 见 §6 偏离说明
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ./.venv_memos/Scripts/python.exe \
  scripts/repro_batch33h_memos.py --workers 3 --out-suffix _haiku \
  --llm-model claude-haiku-4-5 --llm-api-base "https://api.anthropic.com/v1/" \
  --llm-api-key-env ANTHROPIC_API_KEY --drop-top-p \
  > scratchpad/memos_60q_haiku.log 2>&1
```

统计(复用 `scripts/bootstrap_ci.py` 的函数,与项目其它 CI 口径逐字一致):

```bash
python scratchpad/memos_analyze.py results/wsc_s5_memos_haiku.jsonl        # acc/CI/$/延迟
python scratchpad/memos_paired.py  results/wsc_s5_memos_haiku.jsonl memos # 配对簇统计
```

并行度 = 3 工作线程(≤4 硬约束满足)。

---

## 5. 协议(与 repro_batch2 / repro_batch4 逐条镜像)

| 环节 | 本轨做法 | 与其它考生一致? |
|---|---|---|
| 题源 / 抽样 | `repro_batch2.sample_stores()`:由 `results/wsc_s5_filter_only.jsonl` 的 418 题按 uid 排序等距抽 15 库 → 60 题 | 是(同一函数) |
| 会话文本 | `repro_batch4.sess_text()`:前 6 轮、每轮截 400 字,首行 `(session date: YYYY-MM-DD)` | 是(同一函数) |
| 写入顺序 | 按 `date` 升序逐会话 | 是 |
| 每条目新库 | 每 uid 一只全新 `GeneralMemCube`(独立 Qdrant path + collection) | 是 |
| 检索 | `cube.text_mem.search(query, top_k=10)` | 是(k=10) |
| 证据形态 | MemOS 原生记忆句,逐条 `- {memory}` | 各系统按自身原生形态,同规则 |
| 读者 | claude-haiku-4-5,temp 0,max_tokens 300,`READER_SYS` 原文 | 是(同一常量) |
| 判官 | `qvf.judge.ClaudeJudge()`(claude-opus-5) | 是 |

MemOS 侧全部走其官方 API:`GeneralMemCubeConfig` → `GeneralMemCube` →
`text_mem.extract()`(其自带 `SIMPLE_STRUCT_MEM_READER_PROMPT`)→ `text_mem.add()`
→ `text_mem.search()`。**未复刻其任何机制,未改其提示词、解析或流程。**

配置(README/出厂默认,除注明):

- `text_mem.backend = general_text`
- `extractor_llm.backend = openai`,`temperature=0.7 / top_p=0.95 / max_tokens=8192`(MemOS 默认)
- `vector_db.backend = qdrant`,本地嵌入模式(`path=results/memos_stores_*/<uid>/qdrant`),
  `vector_dimension=1536`,`distance_metric=cosine`
- `embedder.backend = universal_api`(provider openai),`text-embedding-3-small`,1536 维
- `act_mem / para_mem / pref_mem = uninitialized`

---

## 6. 偏离与限定(四条,全部如实入档)

**(1) Docker 路线 BLOCKED —— 未能跑 MemOS 的旗舰 `tree_text`(Neo4j 图记忆)。**
本机 Docker Desktop 29.4.2 的 Linux 引擎起不来:

```
docker info -> failed to connect to the docker API at
npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if
the daemon is running: open //./pipe/dockerDesktopLinuxEngine:
The system cannot find the file specified.
```

`wsl -l -v` 显示 `docker-desktop` 分发 `Stopped`(手动 `wsl -d docker-desktop` 可起,
说明 WSL 本身没问题);`Docker Desktop.exe -Autostart` 启动后 ~6 分钟管道仍不出现;
`docker desktop status` 同样挂死。主会话随后通报"backend 每次弹错误框",
并令全面停用 docker——遂停止该路线,按预注册允许的
"lighter general_text(Qdrant only)"备选执行。
**因此本判决只覆盖 MemOS 的 `general_text` 记忆,不覆盖其 `tree_text` 图记忆
(MemOS 论文的主卖点)。这是本轨最大的覆盖缺口,需要一台能起 Neo4j 的机器补跑。**

**(2) `--drop-top-p`:haiku 臂在传输层丢掉一个不被支持的采样参数。**
MemOS 的 `OpenAILLM._build_request_body` 无条件同时发 `temperature` 与 `top_p`,
且无配置项可关;Anthropic 的 OpenAI 兼容端点对此返回 400:

```
Error code: 400 - {'error': {'code': 'invalid_request_error', 'message':
'`temperature` and `top_p` cannot both be specified for this model.
Please use only one.', 'type': 'invalid_request_error', 'param': None}}
```

`--drop-top-p` 只在 `chat.completions.create` 的关键字里 `pop("top_p")`,
其余请求体(模型、提示词、temperature、max_tokens)原样。这是**采样参数层的
供应商兼容改动,不是对 MemOS 机制的改写**;为对冲此偏离,另跑了一条完全不改
请求体的 gpt-4.1-mini 臂,两臂统计不可分(+1.67pp,CI [−13.3, +15.0],p=1.0)。

**(3) 嵌入器钉 text-embedding-3-small(1536),而非 MemOS 默认的 text-embedding-3-large。**
理由:与本项目直读臂及 Mem0 / lgstore / 摘要 RAG 等考生同款嵌入,把差异隔离到
"记忆构造"这一项上。两臂用的是同一嵌入器,故不影响 §1 的次判决。

**(4) MemOS 出厂 temperature=0.7,写侧非确定性。** 同一库两次跑抽出的记忆条数
会差几条(冒烟 138 → 正式跑 141)。本轨每臂只跑一遍,acc 的重跑波动未测。

补充说明(不算偏离,但影响解读):MemOS 的 OS 级 `MOS.add()` 对非 `tree_text`
后端是**逐条原文入库、不过 LLM 抽取**(见
`.venv_memos/Lib/site-packages/memos/mem_os/core.py` 的 `process_textual_memory`:
`if ...backend != "tree_text": TextualMemoryItem(memory=message["content"])`)。
若照那条路走,MemOS 就退化成 lgstore 式平铺 RAG、量不到它的记忆构造。
本轨因此走 `GeneralTextMemory` 自己的模块级文档路径 `extract() → add()`——
这是 MemOS 对 general_text 后端的官方用法,写侧确实过它自带的抽取提示词。

---

## 7. 产出文件

| 文件 | 内容 |
|---|---|
| `scripts/repro_batch33h_memos.py` | 本轨 harness(新增;协议镜像 repro_batch2/4) |
| `results/wsc_s5_memos_haiku.jsonl` | **头条臂** 60 行(haiku 抽取) |
| `results/wsc_s5_memos.jsonl` | 60 行(gpt-4.1-mini 抽取) |
| `results/wsc_s5_memos_smoke.jsonl` | 冒烟 4 行(gpt-4.1-mini) |
| `results/wsc_s5_memos_haikusmoke.jsonl` | 冒烟 4 行(haiku) |
| `results/memos_stores_haiku/` `results/memos_stores_60q/` | 每 uid 一只 Qdrant 本地库(各 33MB) |
| `scratchpad/memos_60q.log` `scratchpad/memos_60q_haiku.log` | 逐库建库日志(会话数/记忆数/耗时/token) |
| `.memos/logs/memos.log` | MemOS 自身日志(逐次请求体与响应,32MB) |
| `scratchpad/memos_analyze.py` `scratchpad/memos_paired.py` | 聚合与配对簇统计脚本($0 可复算) |
| `.venv_memos/` | 隔离环境(未污染主环境) |

每行含:`answer` / `judge_correct` / `judge_reason` / `memos_retrieved`(top-10 原文)
/ `memos_kept_memories` / `memos_ingest_llm_in|out` / `memos_ingest_embed_tokens`
/ `ingest_seconds` / `latency_s` —— 读侧与写侧都可复算,不需重跑。

## 8. 入榜建议(留给主会话决定,本轨未改榜单)

若要并入 `results/wikistate_leaderboard_20260828.md` 的"16 系统同台"表,
在 `scripts/build_wikistate_leaderboard.py` 该节列表里加一行即可:

```python
("MemOS(general_text)", "results/wsc_s5_memos_haiku.jsonl",
 "抽取 haiku;tree_text/Neo4j 路线因本机 Docker 不可用未跑"),
```

注:榜单该节现有各行均无 CI,本轨的题级/簇级 CI 见 §2,建议同时补进
`results/sys16_bootstrap_ci_20260829.md` 的续表。

---

*2026-09-02。判官 claude-opus-5(冻结)。全部数字来自实测落盘 jsonl,无估算、无外推。*
