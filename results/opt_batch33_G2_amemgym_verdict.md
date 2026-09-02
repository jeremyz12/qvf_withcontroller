# 批 33-G2 终判:外场 AMemGym——**判据 G 判负**,账目臂不优于直读,方向为负

日期:2026-09-02。预注册:`results/opt_batch33_prereg.md` §33-G(外场 A 档,
AMemGym 600 题;判据 G:*smoc − direct > 0 且簇 CI 不跨零方可写入外场表*)。
读者 `claude-haiku-4-5`(两臂同款,t=0);direct 臂 `QVF_EMBED_BACKEND=openai`
(text-embedding-3-small);判官 `qvf.judge.ClaudeJudge`(`claude-opus-5`,冻结默认);
并行度 ≤4;实测成本 **$15.15**(上限 $15,**超支 $0.145 = 0.97%,已如实入档**)。

---

## 一、判决

> **猜想被否定。** 在 AMemGym 上,卡片账目臂(smoc)**没有**跑赢稠密直读基线
> (direct):官方 exact-match 口径 **49.00 vs 52.33(−3.33pp,簇 CI
> [−8.83, +2.17] 跨零)**;ClaudeJudge 口径 **47.67 vs 52.33(−4.67pp,簇 CI
> [−9.83, +0.67],McNemar b=81/c=109,p=0.0499)**。判据 G 的两个条件(差值 >0、
> 簇 CI 不跨零)**一个都没满足**,且点估计方向为负。
> **本场不得写入外场表的正向栏;按预注册,应作为负面外场如实并列。**

两把尺子(官方 exact-match 与 ClaudeJudge)**逐题一致率 direct 100.0%、
smoc 98.7%**——判分口径不是分歧来源,负号是稳的。

---

## 二、主表(600 题配对,20 persona 簇,自助 10,000 次)

| 臂 | EM_official | EM_strict | ClaudeJudge | 号码解析失败 | 读入 tok/题 | 输出 tok/题 | 延迟/题 |
|---|---|---|---|---|---|---|---|
| **direct**(top-10 稠密检索) | **52.33** [48.33, 56.67] | 52.33 | **52.33** [48.33, 56.67] | 0.0% | 1,149 | 88 | 5.02s |
| **smoc**(卡片账目) | 49.00 [43.67, 55.00] | 48.00 | 47.67 [42.50, 53.67] | 2.0% | 2,144 | 648 | 10.56s |
| 官方 random 基线(本 600 题重算) | 23.17 | — | — | — | — | — | — |

配对差(smoc − direct):

| 口径 | Δ | 簇 CI95 | McNemar(b=smoc only / c=direct only) | p |
|---|---|---|---|---|
| EM_official(官方口径) | **−3.33** | [−8.83, +2.17] | 84 / 104 | 0.166 |
| EM_strict(解析失败判错) | −4.33 | [−9.67, +1.17] | 81 / 107 | 0.068 |
| ClaudeJudge | **−4.67** | [−9.83, +0.67] | 81 / 109 | **0.0499** |

- 三个口径同号同量级;唯一擦线显著的是 ClaudeJudge,方向**不利于 smoc**。
- 两臂都远高于官方 random 基线(23.17),说明考场本身对我们的读者是可解的,
  负号不是"题做不了"造成的。

### 分周期(EM_official,600 题按 period 拆)

| period | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| direct | 78.2 | 67.9 | 64.2 | 52.7 | 53.7 | 43.9 | 35.2 | 37.7 | 41.1 | 51.9 | 50.0 |
| smoc | 69.1 | 62.3 | 58.5 | 50.9 | 53.7 | 33.3 | 37.0 | 35.8 | 42.9 | 50.0 | 46.6 |

两臂随周期同步衰减(状态翻转次数累积),**smoc 的劣势不集中在早期**——
这否定了"建卡看到全时间线 → 早期账目行被未来值污染"这一自审假设(见 §五-3)。
不一致题的逐周期分布也均匀(smoc-only / direct-only 每周期各 4–11 对)。

---

## 三、参照臂:整库直塞(QVF_FULL_CONTEXT=1,150 题 / 5 persona)

| 臂(同 150 题) | EM_official | Δ vs direct | 读入 tok/题 |
|---|---|---|---|
| fullctx(整库按时序全进上下文,零检索) | **54.00** | +2.00(簇 CI [−6.67,+10.67],p=0.68) | 2,432 |
| direct(top-10) | 52.00 | — | 1,120 |
| smoc(账目) | 52.67 | +1.33(fullctx−smoc,p=0.89) | 2,084 |

(该子集只有 5 个 persona 簇,功效很低,只作机制指示,不作判据;smoc 在这 5 店
上恰好偏高——全 600 题上它是 49.00。)

**这是本场的机制判读关键**:把整个记忆库原文塞给同一读者,只比 top-10 检索
高 2.0pp 且不显著。也就是说——

> **AMemGym 的瓶颈不在"取到没取到",而在"取到之后能不能分辨"。**
> 该考场的题面是 4–7 个措辞相近的生活化长答案,判分要求同时命中两个状态槽;
> 区分信号藏在用户自己的**行文细节**里。账目把每条记忆压成
> `slot: value — "≤120 字原句片段"`,恰好丢掉这层细节:覆盖大体不缺(1,227 条卡
> 对 943 个会话,均 1.30 条/会话;20 店中 17 店的卡数 ≥ 会话数,最低 3 店为
> 0.89–0.98),**但表达粒度不够选型**。
> 这与批 29-K 的结论同源:**正确性轴与表达完整轴是两根独立的轴**,本场判分
> 恰好考在表达轴上。

---

## 四、成本与代价(全部取自 usage token;判官输出侧标注为抽样外推)

| 项 | 调用数 | input tok | output tok | $ |
|---|---|---|---|---|
| 建卡(haiku-4-5,20 店) | 20 | 127,443 | 155,188 | 0.9034 |
| smoc 读者(haiku-4-5) | 600 | 1,286,140 | 388,582 | 3.2290 |
| direct 读者(haiku-4-5) | 600 | 689,171 | 52,513 | 0.9517 |
| fullctx 读者(haiku-4-5) | 150 | 364,832 | 13,597 | 0.4328 |
| 判官 smoc(opus-5) | 600 | 685,759(精确) | 25,080* | 4.0558 |
| 判官 direct(opus-5) | 600 | 760,112(精确) | 25,080* | 4.4276 |
| 判官 fullctx(opus-5) | 150 | 189,460(精确) | 6,270* | 1.1040 |
| 判官输出标定探针(opus-5) | 6 | 4,339 | 251 | 0.0280 |
| 嵌入(text-embedding-3-small) | 220 店次 + 600 题 | ≈652,710** | — | 0.0131 |
| **合计** | | | | **15.1454** |

牌价:haiku-4-5 $1/$5 per MTok、opus-5 $5/$25、text-embedding-3-small $0.02。

\* **判官输出侧是抽样外推,不是实测全量**:冻结臂(`ext_smoc_arm.py` /
`ext_direct_arm.py`)不把判官 usage 落盘,为不改冻结件,输入侧用免费的
`messages.count_tokens` 对**每一行**按 `qvf.judge` 的真实调用形状(同 system +
同 `_judge_user_prompt`)精确复算(脚本 `scripts/ext_judge_cost_amemgym.py`),
输出侧用 6 次真实判官调用实测(34/71/37/32/32/45,均值 41.8 tok/次)外推。
判官输出项合计 56,430 tok = $1.41;按该 6 点样本的均值 95% 置信区间
[26, 57] tok/次重算,**总额区间 $14.61–$15.66**——即"是否超 $15 上限"落在
这段抽样不确定性之内,点估计 $15.1454 已超,如实报超。
\*\* 嵌入 token 数按字符/4 估算(OpenAI 未回传 usage),$0.013 量级不影响结论。

**$/题(不含判官)**:direct **$0.00161**;smoc **$0.00689**(读者 $0.00538 +
建卡按本 600 题摊 $0.00151;若按全库 2,200 对摊则为 $0.00579);
fullctx $0.00289。**smoc 花 4.3× 的钱、2.1× 的延迟、7.4× 的输出 token,
换来 −3.33pp。**

---

## 五、必须随数字一起引用的四条披露

1. **off-policy 静态转换(最大偏离)**。AMemGym 是 *on-policy* 环境:官方
   `eval/overall.py` 让被测助手**先与模拟用户逐轮对话**(助手自己的回复进入
   其后续可读的历史),再答题。静态文件无法承载助手回复,本转换**只保留用户
   侧发言**(`session["query"]`,并逐字保留官方的 `[Current Time: ...]` 前缀,
   与 `query_with_time` 同形),丢弃助手侧。故本场是**离策略静态场,绝对值
   与论文表不可比**。
   转换的**充分性已被断言验证**:2,200/2,200 对里,两个 `required_info` 槽的
   当期金值,都能由截止该周期的用户发言中 `exposed_states` 的最新值唯一还原
   (`scripts/ext_convert_amemgym.py` 里 assert,失败即中止)。
2. **题面尾句偏离**。官方 `OVERALL_PROMPT` 的题干与选项块逐字复用,但把
   "输出 `{"answer": int}` JSON" 的尾句换成 "Answer with the number of the
   single best option."——两个冻结臂各自带输出协议(smoc 的 `ANSWER:` 行、
   direct 的 1–3 句日常口吻),批 29c 已实测**在弱读者上叠加第二条输出协议
   要付 ~11pp**。两臂题面逐字节相同,配对性不受影响。
3. **建卡看到全时间线**。冻结 `write_phase` 的字符预算(320K)远大于本场单店
   (12K 字符),故 20 店各只用 1 个批次建卡,抽取器**一次看到该 persona 的
   全部会话**;账目按 `date <= period_end` 过滤后才进读者,但早期账目行的
   *内容* 原则上可能被未来会话影响。分周期结果(§二)显示 smoc 的劣势并**不**
   集中在早期,该污染若存在也不是败因。direct 臂无此问题(原文按日期过滤后检索)。
4. **cutoff 精确性已验证**:`date <= period_end` 在全部 220 个 (persona, period)
   格上,选出的正好是周期 0..pi 的会话集合——不前漏、不后泄(转换脚本内 assert)。

**次要观察**:smoc 的协议偏差(无 `ANSWER:` 行)63/600 = 10.5%,与批 17/19 外场
同档;这 63 题的 EM 只有 **34.9%**,而协议正常的 537 题为 **50.7%**——格式失守
与答错强相关,是外场工程遗留而非本判决的主因(即便把这 63 题全按正常率折算,
smoc 也只到 ~50.7%,仍低于 direct 的 52.33)。

---

## 六、与论文口径的关系(不作横向比较)

AMemGym 论文的头条指标是**归一化记忆分**(相对上界与 random 基线归一;
论文 Table 2 里 AWE 系 0.262–0.291、RAG-(2,4,30) 0.227、native gpt-4.1-mini
0.203、AWI 0.172)。该分数需要额外跑官方 `eval/upperbound.py`(utilization
上界,每题每选项各一次调用 ≈ 8.8K 次)才能计算,**本批未跑,故不报归一化分**。
我们报的是原始 exact-match 准确率 + 官方 random 基线在本 600 题上的重算值
(23.17)。加之 §五-1 的离策略偏离与读者档位不同(haiku-4-5 vs 论文的
gpt-4.1 系),**任何与论文数字的直接对比都不成立**。

---

## 七、复现命令(逐字,按实际执行顺序)

```bash
# 0) 取数(HF: AGI-Eval/AMemGym, config default, split v1.base, CC-BY-4.0)
#    官方 harness 判分模块副本(GitHub AGI-Eval-Official/amemgym, MIT)
#    -> data/external/amemgym/data.json, data/external/amemgym/official/*

# 1) 统一格式(含 cutoff 精确性 + 离策略充分性两组 assert)
PYTHONUTF8=1 python scripts/ext_convert_amemgym.py
#   -> data/external/amemgym_unified.json  (20 店 / 943 会话 / 2200 题)

# 2) 分层抽样 600(seed=33;每 persona 恰 30 题,每 (persona,period) 格 2–3 题)
PYTHONUTF8=1 python scripts/ext_make_probe_amemgym.py
#   -> data/external/amemgym_probe.jsonl, data/external/amemgym_cardable.json

# 3) 建卡(冻结 write_phase 原样;4 并行分片,uid mod 4)
for k in 0 1 2 3; do PYTHONUTF8=1 python scripts/ext_build_cards.py \
  --data data/external/amemgym_cardable.json \
  --cards-dir results/ext_cards_amemgym \
  --uids-file scratchpad/amemgym/uids_shard$k.txt & done
#   -> results/ext_cards_amemgym/amemgym-{00..19}.json  (1,227 条卡)

# 4) smoc 臂(账目读法;4 并行分片)
for k in 0 1 2 3; do PYTHONUTF8=1 QVF_READER_MODEL=claude-haiku-4-5 \
  python scripts/ext_smoc_arm.py \
  --data data/external/amemgym_cardable.json \
  --questions scratchpad/amemgym/probe_shard$k.jsonl \
  --cards-dir results/ext_cards_amemgym \
  --out results/ext_amemgym_smoc.shard$k.jsonl --resume & done
cat results/ext_amemgym_smoc.shard{0,1,2,3}.jsonl > results/ext_amemgym_smoc.jsonl

# 5) direct 臂(top-10 稠密检索,OpenAI 嵌入;4 并行分片)
for k in 0 1 2 3; do PYTHONUTF8=1 QVF_EMBED_BACKEND=openai \
  QVF_ADAPTER_MODEL=claude-haiku-4-5 python scripts/ext_direct_arm.py \
  --data data/external/amemgym_cardable.json \
  --questions scratchpad/amemgym/probe_shard$k.jsonl \
  --out results/ext_amemgym_direct.shard$k.jsonl --resume & done
cat results/ext_amemgym_direct.shard{0,1,2,3}.jsonl > results/ext_amemgym_direct.jsonl

# 6) 整库直塞参照臂(shard0 的 150 题)
PYTHONUTF8=1 QVF_FULL_CONTEXT=1 QVF_ADAPTER_MODEL=claude-haiku-4-5 \
  python scripts/ext_direct_arm.py \
  --data data/external/amemgym_cardable.json \
  --questions scratchpad/amemgym/probe_shard0.jsonl \
  --out results/ext_amemgym_fullctx.jsonl --resume

# 7) 判分(官方 exact-match 三口径 + ClaudeJudge + persona 簇自助 + McNemar)
PYTHONUTF8=1 python scripts/ext_score_amemgym.py \
  --probe data/external/amemgym_probe.jsonl \
  --arm direct results/ext_amemgym_direct.jsonl \
  --arm smoc   results/ext_amemgym_smoc.jsonl \
  --out results/ext_amemgym_scored.json

# 8) 判官侧成本(输入精确 count_tokens,输出抽样外推)
for f in smoc direct fullctx; do PYTHONUTF8=1 python scripts/ext_judge_cost_amemgym.py \
  --in results/ext_amemgym_$f.jsonl --probe data/external/amemgym_probe.jsonl \
  --out-mean 41.8; done
```

分片文件为 uid mod 4 的确定性划分,已同时留存于
`data/external/amemgym/shards/`(与 `scratchpad/amemgym/` 内容相同)。

---

## 八、产出文件

**数据**
- `data/external/amemgym/data.json`——HF `AGI-Eval/AMemGym` v1.base 原始档(CC-BY-4.0)
- `data/external/amemgym/official/`——GitHub `AGI-Eval-Official/amemgym`(MIT)判分/提示词模块副本
  (`eval/metric.py`、`eval/overall.py`、`eval/upperbound.py`、`eval/random.py`、
  `eval/diagnosis.py`、`assistants/{prompts,base,native}.py`、`configs/env/v1.base.json`、`LICENSE`、`README.md`)
- `data/external/amemgym_unified.json`——统一店(20 店 / 943 会话 / 2,200 题)
- `data/external/amemgym_cardable.json`——建卡用店(加 chain/probing_queries 占位)
- `data/external/amemgym_probe.jsonl`——600 题分层样本(seed=33)
- `data/external/amemgym/shards/`——4 份题分片 + 4 份 uid 分片

**卡店**
- `results/ext_cards_amemgym/amemgym-{00..19}.json`(20 店 / 1,227 条卡 / $0.9034)

**臂输出**
- `results/ext_amemgym_smoc.jsonl`(+ `.shard{0..3}.jsonl`)
- `results/ext_amemgym_direct.jsonl`(+ `.shard{0..3}.jsonl`)
- `results/ext_amemgym_fullctx.jsonl`

**判分**
- `results/ext_amemgym_scored.json`——主表 + 配对统计 + 分周期
- `results/ext_amemgym_scored.{smoc,direct}.rows.jsonl`——逐题判分明细
- `results/ext_amemgym_fullctx_vs_direct.json`、`results/ext_amemgym_fullctx_vs_smoc.json`
  ——150 题参照臂配对(§三)

**脚本(新增)**
- `scripts/ext_convert_amemgym.py`、`scripts/ext_make_probe_amemgym.py`、
  `scripts/ext_score_amemgym.py`、`scripts/ext_judge_cost_amemgym.py`

**日志**:`scratchpad/amemgym/*.log`

---

## 九、论文可用句(负面外场,措辞定稿)

> "On AMemGym (ICLR 2026), converted to a static off-policy stream of the
> user's own utterances, the ledger endpoint does **not** beat a top-10 dense
> retrieval baseline read by the same haiku-4.5 reader: 49.0% vs 52.3% under
> the benchmark's own exact-match state-matching rule (paired Δ = −3.3pp,
> persona-clustered 95% CI [−8.8, +2.2]; the same sign under an independent
> LLM judge, −4.7pp, McNemar p = 0.050), against a 23.2% random baseline.
> Feeding the reader the entire raw store instead of the top-10 retrieval adds
> only +2.0pp (n.s.), which localises the failure: on this benchmark the
> discriminating signal lives in the user's own phrasing, not in *which*
> memory is retrieved, and the ledger's slot–value abstraction discards it."

## 十、遗留 / 建议

- **不建议**为本场做读法微调后重跑再报正号——那会变成开发场过拟合;本场应
  作为**负面外场原样并列**,与 STALE(+15.0)/ MemOps(+4.2 n.s.)构成谱系。
- 若日后要与论文表对齐,需补跑官方 `eval/upperbound.py`(utilization 上界,
  ≈8.8K 次调用)以给出归一化记忆分;并需真做 on-policy 交互才谈得上可比。
- 一条便宜的机制追问(未跑,待令,≈$3):把账目行的 `source_span` 上限从
  120 字符放宽/或改用"账目 + 命中原句"的混合视图,检验 §三 的"表达粒度不够
  选型"判读——若混合视图能把 smoc 抬到 direct 之上,则本场败因坐实为渲染
  粒度而非机制。
