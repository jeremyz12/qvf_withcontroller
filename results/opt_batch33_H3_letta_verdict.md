# 33-H3 判决:Letta(MemGPT)对手系统 + "Letta 式文件系统 agent"平凡强基线

日期 2026-09-02 · 考场 = 60 题 v1 标定场(15 库 × 4 型)· 判官 = `qvf.judge.ClaudeJudge`(claude-opus-5,全场同一冻结判官)

## 一、两句话判决

1. **Letta 服务器(钉 0.16.8)= BLOCKED,不是"跑输了",是装不起来。**
   猜想"pip 装 letta 0.16.x 可用默认 SQLite 起服务器"**被否定**:0.16.x 全线的
   `letta/server/db.py` 把异步引擎硬接到 PostgreSQL,SQLite 分支根本不存在
   (源码级证据见 §三)。Docker 后端本机起不来(协调方已确认),无本地 Postgres,
   两次诚实起服务尝试均失败 → 按硬规则报 BLOCKED,**不复刻 Letta**。

2. **`docs/related_work.md:448` 许诺三个月的"Letta 式文件系统 agent 平凡强基线"落地了,
   猜想"它只是把时间戳给模型看就能追平结构化账目"被否定。**
   头条:**文件系统 agent 56.67(60 题,题级/簇级 bootstrap 95% CI 均 [43.3, 70.0])**,
   与稠密直读 51.67 **统计不可分**(Δ+5.00,精确 p=0.69,簇 CI [−5.0,+15.0]),
   而对 QVF 账目臂 85.00 **净输 −28.33**(精确 p=5e-4,簇 CI [−43.3, −15.0])。
   $0.0215/题,延迟中位 11.66s——**比直读贵约 21×、慢约 2.1×,准确度打平**。

---

## 二、平凡强基线:Letta 式文件系统 agent(已跑,60/60 完成)

### 设计(复刻 Letta 博客 "Is a Filesystem All You Need?" 的形态,非其代码)

- **写侧:零 LLM、零嵌入、零索引。** 每条目的会话按日期升序落成真实文件
  `results/letta_fs_corpus/<uid>/s<NNN>__<session date>.md`;文件内容 =
  `scripts/repro_batch4.sess_text` **逐字相同**的渲染
  (`(session date: X)` + 前 6 轮 × 每轮 400 字)——与 60 题标定场其余 16 个
  考生同一语料切法,保证同台可比。建库耗时 12.6 ms/库(33–35 个文件/库)。
- **读侧:agent 自主检索。** `claude-haiku-4-5`(与全场读者同款,temperature 0),
  三个文件系统工具:`list_files()` / `grep_files(pattern)`(全库大小写不敏感正则,
  返回 `<文件>:<行号>: <行>`,上限 60 命中)/ `read_file(name)`;最多 12 轮工具调用,
  末轮去掉工具强制作答。system 提示词明确告知"你没有别的记忆,必须先查再答"。
- **判官:** 同一冻结 `ClaudeJudge`。题源/库源 = `repro_batch2.sample_stores()`,
  与 Mem0 / LangMem / A-MEM / cognee / txtai / lgstore / timeline / BM25 /
  obs-RAG / 摘要RAG / 盖章台账 **同一 15 库 60 题**。

### 结果

| 指标 | 值 |
|---|---|
| n | 60 |
| **acc** | **56.67**(34/60) |
| 题级 bootstrap 95% CI(与 sys16 表同法) | [43.3, 70.0] |
| 簇级(15 uid)bootstrap 95% CI(prereg 判据 H) | [43.3, 70.0] |
| in-tok / 题 | 均 18,914;中位 12,452;max 91,734 |
| out-tok / 题 | 均 513 |
| **$/题(读者侧 haiku,$1/$5 per M)** | **$0.02148** |
| 延迟中位 / 均 | 11.66s / 12.93s |
| 建库 | 0.189s / 15 库 = **12.6 ms/库**(零 API) |
| agent 轮次 | 均 5.40(分布 3–12,仅 1 题打满 12 轮) |
| 工具使用 | grep 均 2.42 次、read 均 2.87 次、空答 0、零工具调用 0 |

逐题型:`longest_tenure` 73.3 / `first_vs_last` 60.0 / `change_count` 46.7 /
`count_before` 46.7。**聚合计数型仍是塌陷面**——和写时学派同一处塌陷。

### 同 60 题配对比较(McNemar 精确符号检验 + 15 簇配对自助 CI)

| 对手 | 对手 acc | Δ(文件系统 agent − 对手) | 精确 p | 赢/输 | 簇 CI |
|---|---|---|---|---|---|
| QVF smoc(账目) | 85.00 | **−28.33** | 0.0005 | 3/20 | [−43.3, −15.0] |
| QVF filter-only | 70.00 | −13.33 | 0.1686 | 9/17 | [−28.3, +0.0] |
| 稠密直读 top-10 | 51.67 | +5.00 | 0.6900 | 14/11 | [−5.0, +15.0] |
| timeline | 63.33 | −6.67 | 0.5716 | 12/16 | [−21.7, +8.3] |
| lgstore | 55.00 | +1.67 | 1.0000 | 13/12 | [−18.3, +20.0] |
| txtai | 53.33 | +3.33 | 0.8318 | 12/10 | [−11.7, +18.3] |
| cognee | 46.67 | +10.00 | 0.3449 | 17/11 | [−5.0, +25.0] |
| A-MEM | 43.33 | +13.33 | 0.1153 | 14/6 | [+1.7, +25.0] |
| LangMem | 40.00 | +16.67 | 0.0872 | 19/9 | [+0.0, +31.7] |
| Mem0 | 26.67 | **+30.00** | 0.0009 | 23/5 | [+15.0, +45.0] |
| 摘要 RAG | 46.67 | +10.00 | 0.3771 | 19/13 | [−16.7, +35.0] |
| obs-RAG | 13.33 | +43.33 | <1e-4 | 30/4 | [+30.0, +56.7] |
| BM25 | 13.33 | +43.33 | <1e-4 | 29/3 | [+26.7, +60.0] |
| 盖章台账 | 11.67 | +45.00 | <1e-4 | 28/1 | [+30.0, +60.0] |

> 注:QVF smoc / filter-only / 稠密直读三行取自 418 题存档文件按这 60 个 qid 的子集,
> 因此是**同题配对**,不是"60 题 vs 418 题"的跨规模比较。

### 三条可写进论文的读数

1. **平凡强基线不平凡也不强。** 它显著打败所有写时巩固产品(Mem0 +30.0 p=9e-4)与
   词面基线(BM25 / obs-RAG / 盖章台账 +43~45),证明"agent 自己 grep 原始带日期会话"
   确实是一条真基线;但它**没有超过最朴素的稠密直读**(Δ+5.0,p=0.69),
   也**没有超过 timeline 组织**(Δ−6.7,n.s.)。LoCoMo 上 74.0 的那种"文件系统即够用"
   结论**在带链式状态更替的 WikiState 上不复现**。
2. **收益不来自"把时间戳给模型看"。** 该基线拿到的是**逐字原文 + 完整日期 + 全库检索权**,
   信息集是账目臂的超集,仍净输 28.33pp(簇 CI 不跨零)。这正面回应
   `related_work.md:448` 自设的证伪测试。
3. **上下文膨胀反噬。** 读入 >20K tok 的 16 题 acc 43.8,≤20K 的 44 题 acc 61.4——
   agent 一旦开始大量 `read_file`,就退化成本项目已测的"全文裸读"形态
   (leaderboard:haiku 全文裸读 v2 576 题 = 52.26,13.7K tok/题)。
   $0.0215/题 ≈ 稠密直读的 21×,多花的钱没买到准确度。

### 复现命令(逐字)

```bash
# 语料落盘 + 60 题(约 12 分钟,读者侧 $1.29,判官另计)
cd /d/ZZL_cluade
PYTHONUTF8=1 python scripts/letta_fs_agent_baseline.py --out results/wsc_s5_lettafs.jsonl
# 统计(CI / 配对检验 / 成本)
PYTHONUTF8=1 python scripts/b33h3_stats.py
```

产物文件:
- `scripts/letta_fs_agent_baseline.py`(基线实现)
- `scripts/b33h3_stats.py`(统计)
- `results/wsc_s5_lettafs.jsonl`(60 行逐题记录:答案 / 判官理由 / token / 延迟 / 工具计数)
- `results/lettafs_smoke.jsonl`(4 题冒烟,已被正式跑覆盖,保留备查)
- `results/letta_fs_corpus/<uid>/*.md`(499 个会话文件,15 库)

---

## 三、Letta 服务器:BLOCKED(状态 = 装不起来,零题跑出)

### 环境(全部隔离、全部钉版本)

```
.venv_letta            Python 3.12.10(独立 venv,与主环境零共享)
letta                  0.16.8      (pip,单次解析:pip install "letta[postgres]==0.16.8")
letta-client           1.12.1      (letta 0.16.8 自身约束 letta-client>=1.7.12 解析所得)
mcp                    1.16.0      (第 3 次尝试所钉,见下)
fastmcp                2.12.5      (同上)
```

### 尝试与逐字报错

**尝试 1 —— `pip install letta==0.16.8` + `letta server --port 8283`(默认 SQLite,未设 LETTA_PG_URI)**

```
File ".venv_letta\Lib\site-packages\letta\orm\sqlalchemy_base.py", line 9, in <module>
    from asyncpg.exceptions import DeadlockDetectedError, ...
ModuleNotFoundError: No module named 'asyncpg'
```
即:**默认 SQLite 配置下服务器仍在 import 期强依赖 asyncpg**(PostgreSQL 驱动)。
按官方 extras 补 `letta[postgres]` 后继续。

**尝试 2 —— 干净重建 venv,单次解析 `pip install "letta[postgres]==0.16.8"`,再起服务器**

```
File ".venv_letta\Lib\site-packages\letta\server\rest_api\routers\v1\tools.py", line 9
    from mcp.shared.exceptions import McpError
ImportError: cannot import name 'McpError' from 'mcp.shared.exceptions'. Did you mean: 'MCPError'?
```
根因:letta 0.16.8 的依赖写成无上界的 `mcp[cli]>=1.9.4`,而 `mcp` 2.x 把
`McpError` 改名为 `MCPError`(pin drift)。按"钉版本"规则钉回 `mcp==1.16.0` +
`fastmcp==2.12.5`(pip check 通过,import 自检通过)后继续。

**尝试 3 —— mcp 钉回 1.x 后再起服务器(仍为默认 SQLite,未设 LETTA_PG_URI)**

导入全部通过、FastAPI 起来了,**死在数据库初始化**:

```
letta.server.db - WARNING - Database connection error (attempt 1/3): [WinError 1225] 远程计算机拒绝网络连接
  ...
  File ".venv_letta\Lib\site-packages\asyncpg\connect_utils.py", line 969, in _create_ssl_connection
ConnectionRefusedError: [WinError 1225] 远程计算机拒绝网络连接
  ...
  File ".../letta/services/organization_manager.py", line 51, in create_default_organization_async
RuntimeError: generator didn't stop after athrow()
ERROR:    Application startup failed. Exiting.
```
完整日志:`results/letta_logs/server_attempt3_sqlite_default.log`(609 行)。

### 源码级终判:0.16.x 的 `letta server` 根本没有 SQLite 分支

自检输出(在 `.venv_letta` 内、默认配置下):

```
database_engine   = DatabaseChoice.SQLITE          <-- 设置层确实选了 SQLite
letta_pg_uri      = postgresql+pg8000://letta:letta@localhost:5432/letta
async engine uri  = postgresql+asyncpg://letta:letta@localhost:5432/letta   <-- 引擎却接 PG
sqlite attempt    = sqlite+asyncpg:/D:/x/letta.db   <-- 强塞 sqlite URI 也会被改写成 asyncpg
```

三条硬证据:

1. `letta/server/db.py:21` 只有一行 `async_pg_uri = get_database_uri_for_context(settings.letta_pg_uri, "async")`,
   **全文无 `sqlite` 字样、无 `DatabaseChoice` 判断、无第二条引擎分支**;
   `settings.letta_pg_uri` 是**带默认值**的属性,未配置时返回
   `postgresql+pg8000://letta:letta@localhost:5432/letta`(`settings.py:472-479`)。
   因此 `settings.database_engine == SQLITE` 被彻底忽略。
2. 想用 `LETTA_PG_URI=sqlite+aiosqlite:///...` 绕过也不行:
   `database_utils.convert_to_async_uri` **无条件**把 driver 改写成 `asyncpg`
   (`database_utils.py:110`),产出 `sqlite+asyncpg:/...` 这种 SQLAlchemy 无法加载的方言。
3. 该缺陷**贯穿整条 0.16.x**:下载 `letta-0.16.0 / 0.16.4 / 0.16.7` 三个 wheel
   直接读 `letta/server/db.py`,三者均 `has sqlite branch: False`、均用带默认值的
   `settings.letta_pg_uri`。(仅 `letta/orm/sqlite_functions.py` 保留了残留的
   SQLite 向量函数辅助代码,但没有任何代码路径会构造 SQLite 引擎。)

**结论:钉版 0.16.x 的 Letta 服务器必须有一个跑着的 PostgreSQL(+pgvector),
"默认 SQLite" 在这条版本线上不是一个可用配置。** 本机 Docker 后端起不来
(协调方已确认,后续未再调用 docker),亦无本地 PostgreSQL 服务(5432 无监听)。
唯一能让它起来的办法是改 Letta 源码——**属于复刻,硬规则禁止**。故终判 BLOCKED。

### Anthropic 支持性(未能验证)

服务器从未起来,因此**无法**验证 0.16.8 是否把 `claude-haiku-4-5` 作为可用 agent 模型。
`letta` 0.16.8 的依赖里带 `anthropic`(装出 1.3.0)且 `ANTHROPIC_API_KEY` 已在环境中,
但**这不构成"支持 haiku-4.5 句柄"的证据**,不写入任何结论。
未跑 `gpt-4.1-mini` 回退臂——回退的前提也是服务器能起来。

### 解除阻塞需要什么(按代价升序,均未执行)

| 路线 | 代价 | 备注 |
|---|---|---|
| 本机装 PostgreSQL 17 + pgvector,`LETTA_PG_URI` 指过去 | 0.5–1 天工程,$0 基建 | 不改 Letta 源码,合规;之后 60 题预估 $8–15(499 会话 × 逐会话 agent step) |
| 修好 Docker 后端,起 `pgvector/pgvector:pg17` | 视 Docker 故障而定 | 本轮已被明令排除 |
| 换 Letta ≥0.17 / Letta Cloud | 违反"钉 0.16.8" | 且 Cloud 需付费额度 |

---

## 四、成本与工时

| 项 | 值 |
|---|---|
| 文件系统 agent 读者侧(实测 token) | in 1,134,841 / out 30,806 → **$1.289** |
| 冒烟 4 题(`results/lettafs_smoke.jsonl`) | in 37,659 / out 2,070 → $0.048 |
| 判官(claude-opus-5,$5/$25 per M) | 未逐行埋点(与其余 16 考生 $/题 口径一致);64 次判官调用估 **<$0.30** |
| Letta 服务器尝试 | **$0**(零 API 调用,全部死在启动) |
| **本轮合计** | **≈ $1.6,远低于 $60 上限,也低于"平凡强基线 <$10"的约束** |
| 工时 | 约 3.5 小时(其中 ~2 小时耗在 Letta 依赖漂移与 DB 诊断) |

## 五、给主会话的两条交付建议

1. `results/wikistate_leaderboard_20260828.md` 的"16 系统同台(60 题标定场)"表加一行:
   `Letta 式文件系统 agent | 60 | 56.67 | 18914 | 513 | 11.66s | 12.6ms/库 | 平凡强基线,零 LLM 写侧`。
   同时 `results/sys16_bootstrap_ci_20260829.md` 加 `文件系统 agent | 60 | 56.7 | [43.3, 70.0]`。
   它落在该文件自己划的"直读带 ~52"里,**不改变**该文件"相邻名次不作主张"的结论。
2. `docs/related_work.md:448` 那条许诺可以从"未落地"改成"已落地并被证伪":
   平凡强基线拿到原文+日期+检索权仍净输账目臂 28.33pp(p=5e-4)。
   **Letta/MemGPT 本体仍必须如实标注"未接入(0.16.x 服务器强依赖 PostgreSQL,本机无法起)"**,
   不得用本基线冒充 Letta 系统本身——两者是不同的东西。
