# 批 33-H5 判决:Memobase 对手位 —— BLOCKED(装不起来,非跑分低)

**状态:BLOCKED。** 猜想"Memobase 能在本机进同台表"被否定,否定的原因是部署层而非能力层:
Memobase 服务端只有 docker-compose 一条部署路径,Postgres+pgvector 与 Redis 是硬依赖,
本机 Docker Desktop 后端起不来且已被上游叫停;本机既无原生 Postgres/Redis,也无可 pip 安装的
Windows 版嵌入式 Postgres。**60 题标定场与 v2.4 576 题一题未跑,无 acc / $ / 延迟可报。**
按硬规则不作复刻替代(scripts/ 下不存在任何"仿 Memobase"实现)。

- 上榜口径:**不入** `results/wikistate_leaderboard_20260828.md`「16 系统同台」表,亦不入
  `results/sys16_bootstrap_ci_20260829.md`。装不起来只作阻塞记录。
- 实际花费:**< $0.01**(仅 2 次 claude-haiku-4-5 兼容端点探针,24+17 tok 与 1 次 400;
  无摄入、无读者、无判官调用)。上限 $30 未动用。

---

## 一、对手身份与取材(已完成部分)

| 项 | 值 |
|---|---|
| 仓库 | `memodb-io/memobase`,Apache-2.0 |
| 克隆位置 | `D:\ZZL_cluade\external\memobase`(未 git add) |
| 提交 | `358c16bbc6d687937d79bc2f984a11c3be8da901`(2026-01-11,`fix: increase max_tokens in llm_sanity_check`) |
| 客户端版本 | `memobase` 0.0.27(PyPI,与克隆内 `src/client/memobase/__init__.py` 版本一致) |
| 隔离环境 | `D:\ZZL_cluade\.venv_memobase`(Python 3.14.5;装 memobase / anthropic 1.3.0 / openai 3.7.0 / pydantic / python-dotenv / rank_bm25) |

命令(全部已执行,exit 0):

```
cd D:/ZZL_cluade/external && git clone --depth 1 https://github.com/memodb-io/memobase.git
cd D:/ZZL_cluade && python -m venv .venv_memobase
./.venv_memobase/Scripts/python.exe -m pip install memobase anthropic pydantic python-dotenv openai rank_bm25
```

---

## 二、两次诚实尝试与精确报错

### 尝试 1:README 默认路径 `docker compose`(失败)

README(`external/memobase/src/server/readme.md` §Launch)只给这一条:
`cp .env.example .env; cp ./api/config.yaml.example ./api/config.yaml; docker-compose build && docker-compose up`。
`docker-compose.yml` 三个服务:`pgvector/pgvector:pg17`、`redis:7.4`、自建的 `memobase-server-api`。

引擎从未起来。`docker version` 客户端 29.4.2 / compose v5.1.3 存在,但守护进程侧:

```
$ docker info
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine;
check if the path is correct and if the daemon is running:
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

用 `Start-Process` 与 `Win32_Process.Create` 两种方式拉起 Docker Desktop,进程能起、
`docker-desktop` WSL 发行版始终 `Stopped`、命名管道始终不出现(20s×10 轮轮询):

```
iter=0 desktop=1 backend=2 pipe=False
iter=1 desktop=5 backend=2 pipe=False
...
iter=9 desktop=5 backend=2 pipe=False
```

上游随后通报"Docker Desktop 后端起不来,每次尝试都给用户弹错误框",并令**全面停用
docker / docker compose**。据此终止本路径,并已把本次拉起的 Docker Desktop / com.docker.backend /
docker-ai 进程全部结束,不再残留弹框源。

### 尝试 2:绕开 docker 原生起服务(失败)

结论:**Memobase 服务端没有无 docker 的路径**,理由三条,均来自源码而非推测:

1. `src/server/api/memobase_server/connectors.py` 顶部即 `create_engine(DATABASE_URL)` +
   `redis.asyncio`,`create_tables()` 第一步是 `CREATE EXTENSION IF NOT EXISTS vector;`
   —— Postgres 且必须带 pgvector,Redis 同为进程外硬依赖;
2. `src/server/api/pyproject.toml` 依赖含 `pgvector>=0.4.1`、`psycopg2-binary`、`redis>=6.2.0`,
   全仓 grep 无 sqlite / 内嵌模式;README 的 "Development" 路径第一步仍是
   `sh script/up-dev.sh`(还是起 docker 数据库);
3. 本机可用件盘点:`psql / pg_ctl / initdb / redis-server / podman / nerdctl` **均不存在**,
   `C:\Program Files` 下无 PostgreSQL / Redis / Podman 安装。

唯一可能的纯 pip 兜底(嵌入式 Postgres+pgvector)也不成立:

```
$ ./.venv_memobase/Scripts/python.exe -m pip download --no-deps -d <tmp> pgserver
ERROR: Could not find a version that satisfies the requirement pgserver (from versions: none)
ERROR: No matching distribution found for pgserver
```

(对照:`psycopg2-binary` 有 cp314-win_amd64 轮子,能装 —— 缺的不是驱动,是**服务端本体**。)

两次尝试用尽,按硬规则报 BLOCKED。

---

## 三、顺带证实/否定的两条技术判断(有实测,可复用)

### 1. "response_format 可能出问题"这一预判 —— **被否定**(对 0.0.27 不成立)

Anthropic OpenAI 兼容端点 `https://api.anthropic.com/v1/` + `claude-haiku-4-5` 实测:

| 探针 | 结果 |
|---|---|
| 普通 chat.completions(无 response_format) | **OK**,`usage=24/17`,`prompt_tokens_details=None` |
| 带 `response_format={"type":"json_object"}` | **400** `response_format.type: Input should be 'json_schema'` |

但 `src/server/api` 全仓 grep `json_mode` 只有三处,**全在 `llms/__init__.py` 自身**
(形参默认 `False`、`if json_mode:` 分支、`if not json_mode:` 分支),**无任何调用点传 True**。
抽取/合并/事件摘要走的是纯文本 `- TOPIC::SUB_TOPIC::MEMO` 行格式,不发 `response_format`。
故:**服务端一旦起得来,claude-haiku-4-5 走兼容端点是可行配置,不需要退到 gpt-4.1-mini。**
另:`openai_model_llm.py` 读 `response.usage.prompt_tokens_details.cached_tokens`,兼容端点该字段为
`None`,`getattr(None, ..., None)` 不抛错,无需改代码。

### 2. 日期怎么进 Memobase —— 已定位原生接口

`memobase_server/utils.py:get_message_timestamp()` 用的是**每条 message 的 `created_at`**
(缺失才回落 blob 时间);客户端 `Blob.to_request()` 恰恰 `exclude={"created_at"}`,
即 **blob 级 created_at 根本不上线**。所以会话日期必须挂在 `OpenAICompatibleMessage.created_at` 上,
渲染成 `[YYYY/MM/DD] user: ...` 喂给抽取器。已按此写进恢复脚本。

---

## 四、Schema 对照:Memobase 槽位画像 vs QVF 写时卡

**限定:Memobase 一侧是"声明式 schema + 厂商自带示例",不是本机实测输出**(服务端未起,不许编)。
QVF 一侧是实测文件 `results/wt_cards_v44clean/wikiP108000-Q59200022.json`
(该 uid 正是 60 题标定场 15 条目的第 1 条)。

### 4.1 Memobase 侧(取自源码)

写时产物是三元组 `topic / sub_topic / memo`(客户端 `core/user.py:UserProfile`
= `id, created_at, updated_at, topic, sub_topic, content`;`content` 即 memo)。
默认槽位表 `prompts/user_profile_topics.py` 共 8 topic:
`basic_info`(Name/Age/Gender/birth_date/nationality/ethnicity/language_spoken)、
`contact_info`(email/phone/city/country)、`education`(school/degree/major)、
`demographics`、**`work`(company/title/working_industry/previous_projects/work_skills)**、
`interest`、`psychological`、`life_event`(marriage/relocation/retirement)。

厂商自带示例(`prompts/extract_profile.py:EXAMPLES`,原文):

```
topic=interest  sub_topic=movie
memo="Inception, Interstellar[mention 2025/01/01]; favorite movie is Tenet [mention 2025/01/02]"
```

合并规则(`prompts/merge_profile.py`)是**写时三选一**:`APPEND` / `UPDATE\t[UPDATED_MEMO]` / `ABORT`,
其 UPDATE 示例把历史压成一条串:
`"...Currently self-studying Japanese...[mentioned on 2025/05/05]; Preparing for final exams [mentioned on 2025/06/01];"`

### 4.2 QVF 侧(实测)

同一条链 56 条记录,每条 13 个字段:
`record_id, source_memory_id, source_span, entity, slot, value, claim, slot_cardinality,
temporal_relation, relation_target_record_ids, condition, implies_stale_slots, stated_date`。
实测三条:

```
r1  slot=job_title  value=research fellow                    card=single  temporal=replacement  stated_date=1985-11-01
    span="I officially started as a research fellow at the California Institute of Technology this morning"
r2  slot=employer   value=California Institute of Technology card=single  temporal=replacement  stated_date=1985-11-01
r3  slot=last_name  value=Johnson                            card=single  temporal=replacement  stated_date=1986-02-15
    span="I actually just received my new one on February 15th with my new last name, Johnson"
```

该链 slot 取值 27 种(`employer / job_title / office_location / commute_method / travel_history / ...`),
`temporal_relation` 三态(`replacement / additive / equivalent`),56 条中 19 条带 `stated_date`。

### 4.3 差在哪(结构性,不依赖跑分)

| 维度 | Memobase | QVF 卡 |
|---|---|---|
| 槽位来源 | 预设 8 topic 固定表,越表要靠 `additional_user_profiles` 配置扩;人物-雇主类聚合题只落到 `work::company` 一格 | 语料自生 slot(本链 27 种),不预设表 |
| 单位 | 一个 `topic::sub_topic` 一条 memo 自由文本 | 一条 record 一个 (entity, slot, value) 断言 |
| 溯源 | 无 span 回指字段 | `source_memory_id` + `source_span` 逐字回指 |
| 时间 | 日期以 `[mention YYYY/MM/DD]` 形式**嵌在 memo 文本里**,靠读者自己解析 | `stated_date` 独立字段 |
| 变更语义 | 写时 LLM 三选一(APPEND/UPDATE/ABORT),UPDATE 把旧值改写进同一串 | `temporal_relation`(replacement/additive/equivalent)+ `implies_stale_slots` + `relation_target_record_ids` 显式建边,旧值保留 |
| 基数 | 无 | `slot_cardinality`(single/set)显式 |
| 条件 | 无 | `condition` 字段(如 "on weekends") |

**可陈述的判读(结构层,非实测胜负):** Memobase 与 QVF 同属写时结构化,但 Memobase 把"变更"
折叠进单格 memo 字符串、把日期留在自由文本里、且槽位受预设表约束;这三点正好落在
WikiState 四型聚合题(longest_tenure / change_count / count_before / first_vs_last)所需的
"逐条带日期的历史"上。**这是待验假设,不是结论 —— 服务端未起,一题未跑,不得写进任何对比表。**

---

## 五、恢复清单(换一台能跑 docker 的机器,或本机 docker 修好后)

文件已就位,一条命令起服务 + 一条命令跑场:

1. 起服务(**本机禁用中**;换机后执行):
   ```
   cd D:/ZZL_cluade/external/memobase/src/server
   cp .env.example .env                       # 端口:DB 15432 / Redis 16379 / API 8019;ACCESS_TOKEN=secret
   cp ./api/config.yaml.example ./api/config.yaml
   # 把 api/config.yaml 改成(密钥从环境注入,勿写进仓库):
   #   llm_base_url: https://api.anthropic.com/v1/
   #   llm_api_key: <ANTHROPIC_API_KEY>
   #   best_llm_model: claude-haiku-4-5
   #   summary_llm_model: claude-haiku-4-5
   #   embedding_provider: openai
   #   embedding_base_url: https://api.openai.com/v1/
   #   embedding_api_key: <OPENAI_API_KEY>
   #   embedding_model: text-embedding-3-small
   #   embedding_dim: 1536
   docker compose build && docker compose up -d
   ```
   (其余一律用 README 默认,不动 profile 槽位表 —— 同台要求"各自 README 默认"。)

2. 跑 60 题标定场:
   ```
   cd D:/ZZL_cluade
   MEMOBASE_URL=http://localhost:8019 MEMOBASE_TOKEN=secret PYTHONUTF8=1 \
   ./.venv_memobase/Scripts/python.exe scripts/memobase_s5_agg.py \
       --out results/wsc_s5_memobase.jsonl
   ```

3. 若 60 题跑通且余额 > $15,再上 v2.4 576(`data/wikistate_full_ALL_v24.json` +
   `data/wsc_s5_v2.jsonl`),按同一 per-item 新 user / 按日插入 / flush / profile+context 读法。

### 新增文件

| 文件 | 说明 |
|---|---|
| `scripts/memobase_s5_agg.py` | 对手位跑场脚本,**从未成功执行过**(只做过 `--help` 导入自检,exit 0)。协议逐字镜像 `scripts/langmem_s5_agg.py`:同一取库公式(15 库 / 60 题)、同一 `READER_SYS`、同一 `ClaudeJudge`、同一行 schema;只把记忆系统换成 Memobase(每条目 `add_user` 新 user、会话按日期升序 `insert(ChatBlob)` 且日期挂 message `created_at`、`flush(sync=True)`、每题读 `profile()` + `context(chats=[问题])`)。 |
| `external/memobase/` | 上游克隆(未 git add) |
| `.venv_memobase/` | 隔离环境 |

### 已核验的场地口径(供其他对手位复用)

60 题标定场 = `results/wsc_s5_filter_only.jsonl` 按 uid 分组、`n_stores=15 / store_offset=0`
取库公式选出的 15 条链 × 4 型题。已复算:选出的 60 个 qid 与
`results/wsc_s5_{mem0,langmem,amem,cognee,txtai,lgstore,timeline,bm25,sumrag,mstrata,obsrag,graphiti,lightrag}.jsonl`
的 60 题**集合完全一致**(13 个文件两两同集)。题型各 15:
`longest_tenure / change_count / count_before / first_vs_last`。15 条链:
`wikiP108000-Q59200022, wikiP108011-Q42430132, wikiP108019-Q41470166, wikiP108029-Q28320577,
wikiP108036-Q39032964, wikiP108046-Q37831543, wikiP39004-Q4989135, wikiP39016-Q5538488,
wikiP39027-Q5889991, wikiP39037-Q3525068, wikiP54005-Q58454919, wikiP54012-Q25618290,
wikiP54019-Q67283693, wikiP54027-Q16228153, wikiP54035-Q104099076`。

---

## 六、阻塞项一句话

**Memobase 不是跑输了,是本机起不来:它的服务端只有 docker 一条路,而本机 docker 守护进程不可用、
无原生 Postgres+pgvector / Redis、亦无 Windows 版嵌入式 Postgres 可 pip 装。**
配置与跑场脚本已备好,换一台 docker 可用的机器后按第五节两条命令即可补齐 acc / $ / 延迟 / 建库 三项 + 60 题簇自助 CI。
