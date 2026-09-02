# 批 33-G4 终判:MINTEval multi_turn_dialogue 外场——猜想被否定,账目臂未跑赢直读(2026-09-02)

预注册 results/opt_batch33_prereg.md §33-G(外场 A 档,判据 G:
"smoc − direct > 0 且簇 CI 不跨零方可写入外场表")。

**判决:33-G4 判负。** smoc 1.21%(7/577)对 direct 1.91%(11/577),
配对差 **−0.69 pp**,精确 McNemar b=6 / c=10 **p=0.4545**,
簇(用户)自助 95% CI **[−1.93, +0.52] pp 跨零**。按判据 G,
**MINTEval multi_turn_dialogue 不进外场表**。CI 完全落在 ±3pp 内,
可同时陈述"两臂在 ±3pp 意义上不可区分"(簇级等价,满足 §33 对 n.s. 结论的
TOST 要求),而非"账目臂更好但没跑出显著"。

两臂都贴近地板(≈2%),故**剂量反应不可解读**:两条 acc×n_steps_back 曲线
全程在 0–7% 之间抖动,逻辑回归斜率 CI 双双含零。地板不是判官苛刻造成的,
下面第五节把病灶定位到**账目的槽位词表与"偏好变更事件"这个序数概念不对齐**,
且已用一个抬输出预算的诊断子臂排除了"输出预算不够"这一竞争解释。

成本 **$37.82**(上限 $45),其中 Anthropic 侧 $37.44 全部由落盘 usage token
算出,OpenAI 嵌入 $0.38 为唯一估算项(检索器不记账,已标注)。

---

## 一、考场与转换

- 数据集:HF **`dinobby/MINTEval`**(arXiv:2605.18565,**CC-BY-4.0**),
  split **`multi_turn_dialogue`**(100 条,源自 HorizonBench;论文自述该 split
  考"跨长对话回忆用户陈述的事实与偏好取值")。只下
  `data/multi_turn_dialogue-00000-of-00001.parquet`(84,593,503 B)。
- 一条记录 = 一个模拟用户:`contexts[]` 是带 ISO 时间戳的对话场次,
  `questions[]` 五型(simple / counting / history / ordering / multi-hop),
  **只有 `history` 型带 `n_steps_back`**(2,909 / 6,905 题),
  题面形如 *"What was the user's value for 'X' in their "Y" preference
  N preference-change events ago?"*,金标是规范化标签(如 `deadline_driven`),
  并附 `candidates` 候选清单。
- 转换 `scripts/ext_convert_minteval.py`:每个 context 的 content 是
  `[scenario] ...` 抬头 + `user:` / `assistant:` 轮次(轮次正文可跨行);
  按发言行切回**一轮一条记忆**、续行回挂本轮、抬头存成 `scenario: ...`,
  得 `sessions[{date, turns[]}]` —— 与 STALE / MemOps / MemConflict 同粒度,
  直读基线因此跨考场可比。断言:时间戳全为合法日期、场次日期单调、
  问题与金标非空。
- **只物化抽样用户**:全 split 展开约 144M 字符,而两臂脚本会把 `--data`
  整份 load 进内存。抽样种子写死 33,名单落盘
  `data/external/minteval_sampled_uids.txt`(uid ↔ 原 id ↔ 字符数)。

## 二、抽样:为什么必须按 n_steps_back 分层

`n_steps_back` **按用户强聚簇**:`o3__user_113` 的 30 道 history 题深度全在
3–7,`sonnet-4.5__user_0` 跨 2–51。在题池里随机抽,深度桶与用户身份共线,
"深度越大越差"就无法与"某些用户天生更难"分开。故:

1. 只从 `history` 题抽(其余四型无深度标注);
2. 每用户等配额;
3. 用户内按**全局深度桶**(宽 5,46+ 并作一桶)轮转取题,桶内 seed=33 随机,
   轮转起点按用户序号错开。

结果 **577 题 / 22 用户**,每个深度桶由 3–17 个不同用户供题:

| 深度桶 | 1-5 | 6-10 | 11-15 | 16-20 | 21-25 | 26-30 | 31-35 | 36-40 | 41-45 | 46+ |
|---|---|---|---|---|---|---|---|---|---|---|
| n | 63 | 109 | 108 | 53 | 55 | 55 | 50 | 39 | 23 | 22 |
| 供题用户数 | 15 | 17 | 17 | 13 | 13 | 11 | 10 | 9 | 5 | 3 |

**与"600 题 / 40 用户 / 15 题一人"的偏离,以及为什么**:建卡是本轨主成本,
上限 $25。先建 2 个店试算——`minteval-000`(1.06M 字符)431 卡
in=484,190 out=53,778 $0.753;`minteval-001` 449 卡 $0.789——按字符外推
40 店(56.7M 字符)= **$40.16**,远破 $25 建卡闸,且会吃掉几乎全部 $45。
按令中预置规则**收在 22 店**(000–021,25.6M 字符),再把每人配额从 15 抬到
27,把题数拉回 **577 ≈ 600**;深度分层法不变(k=15 的题集是 k=27 的真子集,
已断言)。事后实测 22 店建卡 **$13.86($0.630/店)**,比试跑外推便宜
(试跑那两店偏小),按实测反推 40 店约 $25.2 —— 恰好卡在闸上,收 22 店的
决定在决策时刻的证据下成立,此处如实披露外推与实测的差。

## 三、haiku 全文臂:**不可跑**(实测,非估算)

`scripts/ext_minteval_ctxsize.py` 用 `messages.count_tokens`(免费)按
`ext_direct_arm.py` 的 `QVF_FULL_CONTEXT=1` 渲染逐店计数,产物
`results/ext_minteval_ctxsize.json`:

- 40 店:**min 149,675 / 中位 350,589 / max 492,421** input token;
- **只有 9/40 ≤ 200K**(claude-haiku-4-5 上下文窗),31/40 超窗。

且那 9 店正是**历史最短的店**(会话数 39–75、最深事件序号 5–16),
只跑它们等于只考浅题,是有偏子样本。故本轨**不设 haiku 全文臂**,
外场表该格记"不可跑(31/40 超 200K,余下 9 店为浅史有偏子集)"。

## 四、题面协议:注入官方候选清单(两臂同字节)

MINTEval 官方 `_common.py` 的题面本身带
*"Pick the answer from this candidate list ..."* + 候选项,并要求
`\boxed{}` 输出、按 EM/F1 判分;金标是规范标签,**在对话原文里从不逐字出现**
(抽查 `minteval-000` 一题金标 `deadline_driven`,全店 0 次字面命中)。

不给清单时先跑了 8 题双臂试跑:direct **0/8 全弃答**("我没有偏好变更日志"),
考场直接触底、两臂无法区分。故按官方题面协议注入候选清单,
**两臂拿到逐字节相同的题面**(与批 17 MemConflict 注入 `(Today is X.)`
同一先例);候选项中位 49 条(p90 153,max 287),中位约 315 token,
两臂等量加载。那 8 题无清单试跑作废但成本入账($0.22)。

其余仍与官方口径不同,已知且不可比:我们不用 `\boxed{}`、不用官方提示词,
**故本轨绝对分不能与 MINTEval 论文表里的数字对比**。主指标用 ClaudeJudge
(与 STALE/MemOps/MemConflict 各臂同判官),副指标报官方度量族
(normalize_answer 语义重建的严格 EM + token-F1)。

## 五、结果

### 5.1 主表(577 题 / 22 用户,读者 claude-haiku-4-5 t=0)

| 臂 | 判官 acc | Wilson 95% | 簇自助 95% | 官方严格 EM | 含金串 | token-F1 | 弃答率 |
|---|---|---|---|---|---|---|---|
| smoc(账目) | **1.21%**(7/577) | [0.59, 2.48] | [0.52, 1.93] | 1.21 | 1.39 | 1.32 | 79.5% |
| direct(OpenAI 稠密 top-10) | **1.91%**(11/577) | [1.07, 3.38] | [0.88, 2.99] | 0.35 | 5.20 | 0.61 | 97.4% |

- 配对:**delta = −0.69 pp**;精确 McNemar b=6 / c=10,**p=0.4545**;
  簇级符号检验 4 胜 / 7 负 / 11 平,p=0.5488;
  簇自助 95% CI **[−1.93, +0.52] pp**(n_clusters=22,B=10000)。
- **判据 G 未过**(要求 delta>0 且 CI 不跨零)。
- **冗长度陷阱已量化**:direct 的"含金串"(答案任意位置出现金标)5.20%
  远高于其判官分 1.91%,而 smoc 两者几乎相等(1.39 vs 1.21)。
  direct 的答句是 1–3 句自由文本、常把多个候选值一起念一遍;
  smoc 只吐一个值。**若换用"提到即算对"的宽松指标,排名会翻转成
  direct 5.20 vs smoc 1.39 —— ClaudeJudge 没有上这个当**,
  这条要写进任何跨考场指标讨论。

### 5.2 剂量反应(acc × n_steps_back)

| 深度桶 | 1-5 | 6-10 | 11-15 | 16-20 | 21-25 | 26-30 | 31-35 | 36-40 | 41-45 | 46+ |
|---|---|---|---|---|---|---|---|---|---|---|
| n | 63 | 109 | 108 | 53 | 55 | 55 | 50 | 39 | 23 | 22 |
| smoc | 0.0 | 0.0 | 2.8 | 0.0 | 0.0 | 3.6 | 4.0 | 0.0 | 0.0 | 0.0 |
| direct | 1.6 | 0.9 | 1.9 | 1.9 | 7.3 | 0.0 | 2.0 | 2.6 | 0.0 | 0.0 |

`correct ~ depth` 逻辑回归(簇自助 CI):smoc β=+0.0140 [−0.0233, +0.0514]
(OR/步 1.014);direct β=+0.0017 [−0.0497, +0.0428](OR/步 1.002)。
**两臂斜率 CI 均含零,且方向与"越深越难"相反**——但这不是"深度不影响记忆",
而是**地板效应下剂量反应无意义**:acc≈2% 时任何斜率都由个位数命中驱动。
本轨**不对 MINTEval 的深度轴给出任何结论**。

### 5.3 病灶定位:不是输出预算,是槽位词表与序数概念

跑批时 smoc 有 39.0% 的行被 `parse_answer` 判为"协议偏差"。逐行归因
(`scratchpad/b33g_devcheck.py`,零 API):

| 归因 | 占 577 题 |
|---|---|
| 正常 ANSWER 行 | 58.1% |
| **加粗前缀 `**ANSWER:**`**(解析器不认,但兜底取末行拿到的是同一句) | 39.0% |
| 真被 max_tokens 截断 | **2.9%** |

把 189 条加粗行的真答案抠出来按"含金串"重打分,只多 1 条(**+0.2 pp**)——
**解析器格式问题不背这口锅**。

再跑**诊断子臂**(60 题分层子样本,只把读者 `max_tokens` 800→4000,
提示词/温度/模型/判官全不动,`results/ext_minteval_smoc_diag4k.jsonl`):

| | acc | 协议偏差 | 平均 out_tok | 触顶次数 |
|---|---|---|---|---|
| 冻结 800(同 60 题) | 0/60 | 43.3% | 483 | — |
| 诊断 4000 | **0/60** | **43.3%** | **492** | **0** |

**输出预算这条竞争解释被排除**:抬 5 倍上限,读者写的字数几乎没变(492 vs 483),
一次都没触顶,准确率与偏差率一模一样。

真正的病灶有两条,互相叠加:

1. **词表不对齐(写侧)**。账目槽位是抽取器自造的自由词表
   (`learning_style` / `feedback_preference` / `roommate_noise_issue`…),
   而题问的是 HorizonBench 的规范偏好分类学
   (`'prioritization required'` in `"Actionability Format"`)。
   账目里**有料**——按题面属性词/偏好族做内容词匹配,每题中位命中 **19 行**
   (p90 42,零命中仅 0.2%)——但读者找不到题里点名的那个偏好族,
   于是给出 79.5% 的"Unable to determine — 账目里没有 X 偏好"。
   **这是同一事实用两套本体表述、读者不做本体对齐的失败,不是存储缺失。**
2. **序数索引不可得(读侧)**。"N 个偏好变更事件之前"要求先把流切成
   canonical 偏好变更事件序列再倒数第 N 个。账目条目数与该店最深事件序号
   之比中位 **14.2×**(428 条账目 vs 最深事件序号 28)——
   要答对得先把 ~93% 的账目行判为"不是偏好变更事件",账目里没有任何字段
   支持这个判定。试跑里能看到读者确实在做正确的事(逐条枚举偏好变更再倒数),
   只是枚举出来的是自由槽位而非官方事件链,数出来必错。

direct 那 11 条命中的形态是另一回事:它无视"N 事件之前"这个条件,
按检索到的 10 条摘录答**"你一直是 X"**,当该槽位长期未变时蒙对。
逐条读原文:**11 条里 9 条**是"先声明我没有偏好变更日志、再按摘录给当前值"
的长答句,只有 2 条是裸值。smoc 的 7 条命中则全是裸值
(medium / formal / visual / numbered_steps / 5 / benjamini_hochberg /
flowing_prose)——都是槽位名恰好与账目自由词表撞上的通用词。
**即:两臂都没有真正解这道题;direct 的分靠"报当前值"捷径,
smoc 的分靠偶然对上词表。**

## 六、成本与延迟(全部由落盘 usage token × 官方单价算出)

单价:claude-haiku-4-5 $1 / $5 per MTok;claude-opus-5 $5 / $25 per MTok。

| 项 | in_tok | out_tok | USD |
|---|---|---|---|
| 建卡(22 店,haiku,`QVF_CATALOG_BUDGET=160000`) | 8,388,831 | 1,093,298 | **13.86** |
| smoc 主臂读者(577) | 11,439,630 | 264,602 | 12.76 |
| direct 主臂读者(577) | 1,077,149 | 64,086 | 1.40 |
| smoc 诊断子臂读者(60) | 1,270,513 | 29,507 | 1.42 |
| 作废试跑(无候选清单,8 题×2 臂) | 190,742 | 5,782 | 0.22 |
| 判官 ClaudeJudge(opus-5,1,230 次) | 1,138,823 | 83,701 | 7.79 |
| **Anthropic 侧小计(全实测)** | | | **37.44** |
| OpenAI text-embedding-3-small(**唯一估算项**:检索器不记账;22 店 25.6M 字符 ≈6.4M tok/遍 × 3 遍) | | | ≤0.38 |
| **合计** | | | **≈37.82**(上限 45) |

- **$/题**:smoc 读者 $0.0221 + 判官 $0.0063 = **$0.0284**;
  direct 读者 $0.0024 + 判官 $0.0063 = **$0.0087**。
  smoc 若摊入建卡($13.86 / 577 = $0.0240/题),全口径 **$0.0524/题 ≈ direct 的 6.0×**。
- **读取侧 token**:smoc 19,826 tok/题 vs direct 1,867 tok/题(**10.6×**)。
- **中位延迟**:smoc 9.3s,direct 5.5s。
- 建卡:$0.630/店,单进程 120–697 s/店(中位 388 s),卡数 min/中位/max = 132/428/628;
  22 店 3 进程并行,墙钟约 55 分钟。

## 七、精确复现命令

```bash
# 0) 取数(84,593,503 B)
python -c "import urllib.request;urllib.request.urlretrieve('https://huggingface.co/datasets/dinobby/MINTEval/resolve/main/data/multi_turn_dialogue-00000-of-00001.parquet',r'D:\ZZL_cluade\data\external\minteval\multi_turn_dialogue-00000-of-00001.parquet')"

# 1) 转统一格式(种子 33 抽 40 店)
PYTHONUTF8=1 python scripts/ext_convert_minteval.py --n-users 40 --seed 33

# 2) 建卡(22 店,4 分片并行,parallelism<=4)
#    scratchpad/b33g_pilot_a.txt=000, _b=001, shard3=002-011, shard4=012-021,
#    shard5=021,020,019,011,010,009(抢跑尾巴,已存在的 uid 自动跳过)
PYTHONUTF8=1 QVF_CATALOG_BUDGET=160000 python scripts/ext_build_cards.py \
  --data data/external/minteval_cardable.json \
  --cards-dir results/ext_cards_minteval --uids-file scratchpad/b33g_shard3.txt

# 3) 分层出题(k=15 的题集是 k=27 的真子集,可增量扩)
head -22 scratchpad/b33g_all40_uids.txt > scratchpad/b33g_built22_uids.txt
PYTHONUTF8=1 python scripts/ext_make_probe_minteval.py \
  --uids-file scratchpad/b33g_built22_uids.txt --per-user 27 \
  --out data/external/minteval_probe.jsonl

# 4) 全文臂可跑性实测(免费 count_tokens)
PYTHONUTF8=1 python scripts/ext_minteval_ctxsize.py

# 5) 两臂(ext_minteval_run.py 只在冻结臂外加一层判官 token 记账)
PYTHONUTF8=1 python scripts/ext_minteval_run.py --arm smoc \
  --questions scratchpad/b33g_w1_smoc_A.jsonl \
  --out results/ext_minteval_smoc.wA.jsonl --resume
QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/ext_minteval_run.py --arm direct \
  --questions scratchpad/b33g_probe_wave1.jsonl \
  --out results/ext_minteval_direct.w1.jsonl --resume

# 6) 诊断子臂(只抬读者 max_tokens)
PYTHONUTF8=1 python scripts/ext_minteval_run.py --arm smoc \
  --questions scratchpad/b33g_diag.jsonl \
  --out results/ext_minteval_smoc_diag4k.jsonl --reader-max-tokens 4000

# 7) 合并 + 统计
cat results/ext_minteval_smoc.w{A,B,C,2A,2B}.jsonl > results/ext_minteval_smoc.jsonl
cat results/ext_minteval_direct.w{1,2}.jsonl        > results/ext_minteval_direct.jsonl
PYTHONUTF8=1 python scripts/ext_minteval_analyze.py
PYTHONUTF8=1 python scratchpad/b33g_devcheck.py     # 协议偏差归因
PYTHONUTF8=1 python scratchpad/b33g_cost.py         # 全轨成本清点
```

`QVF_EMBED_BACKEND=openai` 已正面验证:在与跑批同一 import 顺序下
`ext_direct_arm._retriever_cls()` 返回 `qvf.retrieval.OpenAIDenseRetriever`
(本机 ollama 在跑,不验证就有静默走本地嵌入的风险)。

## 八、产物清单

**脚本(新建)**
- `scripts/ext_convert_minteval.py` — parquet → 统一格式 + 种子抽样
- `scripts/ext_make_probe_minteval.py` — 按 n_steps_back 分层出题 + 候选清单注入
- `scripts/ext_minteval_ctxsize.py` — 全文臂可跑性实测
- `scripts/ext_minteval_run.py` — 冻结臂跑批壳(判官 token 记账 / 诊断用 max_tokens 覆盖)
- `scripts/ext_minteval_rejudge.py` — 重判器(修诊断子臂第一版代理挡掉判官的事故)
- `scripts/ext_minteval_analyze.py` — 主统计

**数据**
- `data/external/minteval/multi_turn_dialogue-00000-of-00001.parquet`(原始,CC-BY-4.0;
  被 `.gitignore:42 data/external/*/` 排除,与 stale/ memops/ 同待遇,按第七节 0) 重取)
- `data/external/minteval_unified.json` / `minteval_cardable.json`(40 抽样店)
- `data/external/minteval_sampled_uids.txt`(uid ↔ 原 id ↔ 字符数)
- `data/external/minteval_probe.jsonl`(577 题,含候选清单)

**结果**
- `results/ext_cards_minteval/`(22 店卡库,**建后只读**)
- `results/ext_minteval_smoc.jsonl` / `ext_minteval_direct.jsonl`(各 577 行)
- `results/ext_minteval_smoc_diag4k.jsonl`(诊断 60 行)
- `results/ext_minteval_ctxsize.json`、`results/ext_minteval_summary.json`
- 分片原件 `results/ext_minteval_{smoc,direct}.w*.jsonl` 与 `*.judgeusage.json`

## 九、遗留与勘误

1. **诊断子臂第一版事故**:读者 `max_tokens` 代理只暴露了 `messages.create`,
   把 `qvf.judge` 的 `messages.parse` 一起挡掉,60 次判官调用全落进
   ClaudeJudge 的兜底"含金串"启发式(judgeusage 里 `no_usage=60`,
   当时虚报 2/60)。代理已改为透传其余属性,并用
   `scripts/ext_minteval_rejudge.py` 原样重判,真值 **0/60**。
   主臂 577×2 未受影响(不带该旗标时不装代理,judgeusage 里 `no_usage`
   只有 wA 分片的 2 次判官自身失败)。
2. **建卡分批预算改为 160,000 字符**(默认 320,000)。MINTEval 店卡密度高
   (22 店实测 0.000326 卡/字符,为 STALE 的 1.42×),320K 批的结构化输出会顶到
   16K max_tokens 触发对半重跑、成本翻倍。该环境变量本就是为"卡片密度极高的
   内容"预留的,但跨考场建卡成本因此不逐字可比,需在合表时标注。
3. **只覆盖 `history` 一型**。simple / counting / ordering / multi-hop 四型
   无 `n_steps_back`,本轨未跑;"MINTEval 上 QVF 不占优"这句话目前只对
   **序数历史回忆题**成立,不可外推到该 split 的其余四型,更不可外推到
   state_tracking / wiki_revisions / github_commits 三个 split。
4. **两条可检验的修复方向**(未跑,待令):
   ① 写侧本体对齐——建卡提示词接受一份外部槽位词表(考场给的
   preference family / attribute 清单),把自由槽位映射过去;
   ② 账目加"事件类型"字段,把 canonical 偏好变更从其余状态事实里分出来,
   使"倒数第 N 个事件"成为可机械执行的操作。
   两条都是**写侧**改动,与 33-B/33-F 的"写侧存储恒完整、读侧表达是提示词
   函数"那条统一律不冲突:这里失败的是**存储的本体**,不是存储的完整性。
5. 本轨**未 commit**(按令);上述新文件均为工作区未跟踪状态,由主会话统一提交。

## 论文可用句(负结果)

"On MINTEval's multi_turn_dialogue split (577 ordinal-recall questions over 22
simulated users, stratified by n_steps_back), the ledger arm scores 1.21% vs
1.91% for a dense-retrieval baseline reading the same corpus (paired
delta −0.69 pp, exact McNemar p=0.45, user-cluster 95% CI [−1.93, +0.52]);
both arms sit at the floor. Raising the reader's output budget five-fold
changes neither accuracy nor output length, so the failure is not a truncation
artefact: the write-side schema names states in its own free-form slot
vocabulary, and the benchmark indexes them by position in a canonical
preference-change event chain that the ledger — holding 14.2x more entries than
that chain is long — provides no way to reconstruct."
