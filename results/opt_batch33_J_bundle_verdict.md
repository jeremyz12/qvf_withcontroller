# 批 33-J 小捆判决书(2026-09-02)

> 预注册出处:`results/opt_batch33_prereg.md` §33-J。
> 动机与预测出处:`results/narrative_gaps_grounded_20260902.md` 排序表第 6/19/20/22 行,
> 及"四、必须补的实验清单"的 E-G(rtl)/ E-E(S1-S2)/ E-K(无填充)/ E-F(日期修复 E1)。
> **四格全部跑完,总花费 $14.28(上限 $15)。**

## 判决四句(先判决,后数字)

1. **J1 猜想被否定**:"读时建账目"不是写时建卡的等价替代。同语料同检索同提示词下
   读时账目 **60.24**,只把裸检索(48.26)抬 **+11.98pp**,却比写时账目(90.45)
   低 **30.21pp**(p=4.6e-40),且**读取全口径更贵**($0.0137/题 vs smoc 读端 $0.0053)。
   写时闸买的不是准确率的一小截,而是**对检索失败的免疫**:检索命中全部链会话时
   rtl 85.33,漏掉任一链会话就塌到 **15.87**;smoc 在同两层是 93.48 / 85.10。
2. **J2 一半被证实、一半被否定**:S2(时点值)预测 ≥+30pp —— 实测 **+59.03pp**,
   证实且大幅超出;S1(当前值)预测"打平 ±5pp" —— 实测 **+8.33pp,p=4.9e-04,
   簇 CI [+4.17,+13.19] 不跨零**,**"S1 无优势"这条自我限定被自己的实验否定**。
3. **J3 猜想被证实(且是全捆信息量最大的一格)**:干扰填充是直读崩溃的**因果**成分
   而不只是观察性分箱 —— 拿掉填充,direct **+22.50pp**(43.33→65.83,p=2.5e-05),
   fullplain **+20.00pp**,而 smoc **+1.67pp(n.s.)**。结构溢价因此从
   **+47.50pp 降到 +26.67pp**:**约 44% 的溢价是"扛干扰",56% 是"扛聚合"**。
4. **J4 猜想被否定**:把账目里被粗化的日期改回金标精度,**没有**修复强读者在降级层的
   成绩(Δ **−3.57pp**,p=0.727)。停机 3 建议的"日期粗化"替代归因**没有干预证据**,
   不得按"已定因"写入 MASTER。

---

## 零、口径与纪律(全捆通用)

- 语料:`data/wikistate_full_ALL_v24.json`(sha256[:16] = `c62291897f22bc56`,144 链 / 4,862 会话)。
- 主题集:`data/wsc_s5_v2.jsonl`(576 题 = 144 链 × 四型)。
- 读者:`anthropic:claude-haiku-4-5`(J4 按分轨要求用 `openai:gpt-5-mini`)。
- 判官:`qvf.judge.ClaudeJudge`,`claude-opus-5`(冻结,未改)。
- direct / rtl 检索:`QVF_EMBED_BACKEND=openai`(text-embedding-3-small),top-10,
  记忆装配 = `ext_direct_arm._memories`(轮级,`uid/s{si}#r{ri}`)。
- 并发恒 ≤4 进程;**本轨未执行任何 git add/commit/push**;新店只建新目录,不原地覆盖。
- **`scripts/lb_reader_arm.py` 一字节未改**;本轨全部跑批走其副本
  `scripts/lb_reader_arm_b33j.py`(自 git rev `7232833` 复制)。
- 成本一律由**行内 usage token** 折算:haiku-4.5 $1/$5 per MTok、gpt-5-mini $0.25/$2、
  opus-5(判官)$5/$25。**唯一例外并已标注**:J4 的 112 行落盘于"判官 usage 字段
  补丁"之前,其判官成本按归档实测单价 $0.00308/行
  (`results/judge_cost_measured_20260816.md:5`)折算。

### 新增文件

| 文件 | 性质 |
|---|---|
| `scripts/lb_reader_arm_b33j.py` | 新建(lb_reader_arm.py 副本 + `rtl` 臂 + `--patch-dates` + `--shard/--nshards/--shard-mode` + 溯源字段 + 判官 usage) |
| `scripts/b33j_gen_dim4_probes.py` | 新建(J2 的 S2 探针生成器,规则 import 自 newdom_gen_probes) |
| `scripts/b33j_build_nofiller.py` | 新建(J3 无填充语料构造器) |
| `scripts/b33j_analyze.py` | 新建(McNemar + 链级符号检验 + 链簇自助 CI + 成本) |
| `scripts/b33j_cost_ledger.py` | 新建(成本总账,全部按 usage token) |
| `scripts/b33j_run_rest.sh` | 新建(J2→J3→J1 串行驱动,并发恒 ≤4) |
| `data/b33j_datedeg_56.jsonl` | J4 降级层 56 题 |
| `data/b33j_ws_dim4_probes.jsonl` + `.meta.json` | J2 的 144 道 S2 探针 |
| `data/b33j_nofiller_30.json` / `_q120.jsonl` / `.meta.json` | J3 无填充语料 + 120 题 |
| `results/wt_cards_b33j_nofiller/` | J3 无填充卡店(30 店,新目录) |
| `results/b33j/*.jsonl` + `log_*.txt` | 全部结果与日志 |

### 溯源字段(每行 `prov`)

`corpus` / `corpus_sha256_16` / `cards_dir` / `git_rev` / `top_k` / `embed_backend` /
`patch_dates`;rtl 行另带 `rtl_n_records` / `rtl_catalog_input_tokens` /
`rtl_catalog_output_tokens` / `rtl_catalog_cached` / `retrieved_memory_ids`。

---

## 一、J1 读时建账目臂(rtl,576 题)

### 设计(与写时臂的唯一差别 = 卡在哪里建)

逐题三步:① 与 direct 臂**同一检索器、同一 top-10**(openai 嵌入)取回 10 条记忆;
② 对这 10 条跑**同一建卡提示词** —— `wt_qvf_prototype._catalog_prompt()`,旗标全关,
机核断言其输出与 `CATALOG_PROMPT` **逐字节相同**(1,026 字符),模型 `claude-haiku-4-5`、
`temperature=0.0`、`output_format=CatalogExtraction`,与写时建卡同一调用形态;
③ 用 `render_card_ledger` 的**同一行格式与排序**(`[entry N] {date} | {slot}: {value} — "{span}"`,
日期取 `stated_date` 否则 `_mem_dates` 回填,按日期升序)渲染;④ 同 `SMW_PROMPT`(F.1)读者。

### 数字

| 对照 | n | base | test | Δ | b/c | McNemar p | 链级符号 | 链簇 95% CI |
|---|---|---|---|---|---|---|---|---|
| rtl vs direct | 576 / 144 链 | 48.26 | **60.24** | **+11.98** | 42/111 | 2.25e-08 | 75W/21L/48T p=2.71e-08 | [+7.99, +15.97] |
| rtl vs smoc | 576 / 144 链 | 90.45 | **60.24** | **−30.21** | 188/14 | 4.58e-40 | 8W/97L/39T p=1.50e-20 | [−35.42, −25.00] |

逐型:

| qtype | rtl | smoc | direct | n |
|---|---|---|---|---|
| change_count | 45.83 | 88.19 | 34.72 | 144 |
| count_before | 39.58 | 88.89 | 43.75 | 144 |
| first_vs_last | 79.17 | 96.53 | 80.56 | 144 |
| longest_tenure | 76.39 | 88.19 | 34.03 | 144 |

### 机制:塌掉的不是"卡片质量",是"覆盖"

`retrieved_memory_ids` 机核回算 top-10 命中链会话的比例(链会话 = `chain_index is not None`):
**均值 84.8%,只有 368/576(63.9%)的题拿到了全部链会话**。按这条**臂无关**的
分层(它只由检索决定,不看任何一臂的对错):

| 层 | n | rtl | smoc | direct |
|---|---|---|---|---|
| 链会话**全命中** | 368 | **85.33** | 93.48 | 63.59 |
| **未全命中** | 208 | **15.87** | 85.10 | 21.15 |

**rtl 跨层落差 −69.5pp,smoc 只有 −8.4pp。** 写时建卡的价值可以一句话定死:
它把"账目完整性"从检索的运气里摘出来,变成建库时的构造保证。在全命中层里
rtl 仍比 smoc 低 8.15pp —— 那才是"小上下文抽取 vs 全库抽取"的纯质量差,只占总差的 27%。

### 成本(实测 usage,576 题)

| 项 | in tok | out tok | $ |
|---|---|---|---|
| rtl 读时建卡(每题一次) | 1,553,009 | 726,376 | 5.186 |
| rtl 读者 | 403,172 | 260,793 | 1.713 |
| rtl 判官(opus-5,实测 576 行) | — | — | 1.007 |
| **rtl 全口径** | | | **7.905($0.01372/题)** |
| smoc 读端(归档 usage) | mean_in 2,950 | mean_out ~478 | 3.079($0.00534/题) |
| direct(归档 usage) | mean_in 877 | mean_out 86 | 0.754($0.00131/题) |

每题产卡 mean **9.3** 张(3–22);**检索集缓存命中 0/576** —— 同一 uid 的四道题
检索出的 top-10 从不相同,故"读时建账目"在本考场里**没有任何摊销可言**,
每题都要重付一次抽取。

### 判决与可写的句子

> 读时账目 = 把写时的一次性抽取重付 576 次,买到的是 direct 之上 +11.98pp、
> smoc 之下 −30.21pp,读取全口径反贵 2.6×。B′4 类"账目在读时建也一样"被判负。
> 机制:rtl 的账目只能覆盖检索捞回来的东西,而 63.9% 的题才拿到完整链;
> 未全命中层 rtl 15.87 vs smoc 85.10。

同时**修正**`narrative_gaps_grounded_20260902.md` 第 6 行引用的"写侧闸 +8.51pp":
在同语料、同检索、同提示词、576 题的正面对照下,写侧闸的实测值是 **+30.21pp**
(CI [+25.00,+35.42])。+8.51 那个数出自 `opt_batch32p_verdict.md:29-38` 的另一口径,
不应再当作"读时 vs 写时"的定价。

---

## 二、J2 S1/S2 有效性探针(各 144 题)

### 题集

- **S1** 复用 `data/ws_dim1_probes.jsonl`(144 行;机核确认 144/144 的 gold 与
  v2.4 `chain[-1].value` 完全一致)。
- **S2** 用 `scripts/b33j_gen_dim4_probes.py` 在 v2.4 上重生成 144 道 dim4:
  金标规则(相邻且日期不同、左端日期链内唯一、查询日在 floor/ceil 两种残缺日期约定下
  严格居中、gold = 最后一个 date ≤ d 的链值)**直接 import 自 `newdom_gen_probes.py`
  的日期工具与 S2 分支**,题面用其 `BRIDGE["dim4_point_in_time"]`。
  **144/144 条目全部合格,0 条被跳过**;与语料自带的归档 dim4 探针做金标规则交叉核对:
  **一致 144 / 不一致 0**。

### 数字

| 探针 | n | direct | smoc | Δ | b/c | McNemar p | 链级符号 | 链簇 95% CI | 预注册预测 | 判决 |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 dim1_current | 144 | 90.97 | **99.31** | **+8.33** | 0/12 | 4.88e-04 | 12W/0L/132T p=4.88e-04 | [+4.17, +13.19] | 打平 ±5pp | **被否定** |
| S2 dim4_point_in_time | 144 | 38.19 | **97.22** | **+59.03** | 1/86 | 1.14e-24 | 86W/1L/57T p=1.14e-24 | [+50.69, +67.36] | ≥ +30pp | **被证实** |

### 判决

- **S2**:三种有效性里的"时点检索"格补齐,+59.03pp,是全项目单格最大效应之一,
  远超预注册的 +30pp 门槛。S3(轨迹)+34.0 已在档,S1/S2 至此全部落地。
- **S1**:预注册写死的是"打平",实测**不打平**。direct 在 S1 上 90.97 已接近天花板,
  smoc 仍把剩下的 9pp 吃掉 8.33pp(12 题净修复,0 题反向)。
  **须同页写的两条**:① 这条否定的是**我们自己的保守限定**("QVF 在查找型题上零优势"),
  方向对自己有利,因此更要连口径一起报:S1 的 direct 基线本就在 90 以上,
  +8.33pp 是天花板附近的残差,**不能与 S2 的 +59.03pp 同尺度并列**;
  ② 顺手修 `MASTER:66-67` 的自相矛盾时,应写"S1 上 direct 已 90.97,结构仍显著
  但边际(+8.33,CI [+4.17,+13.19])",而不是原来的"零优势"或"打平"。

### 成本

| 臂 | n | mean_in | mean_out | 读者 $ | 判官 $ | 合计 |
|---|---|---|---|---|---|---|
| dim1 smoc | 144 | 2,940 | 378 | 0.696 | 0.204 | 0.900 |
| dim1 direct | 144 | 828 | 56 | 0.159 | 0.713 | 0.873 |
| dim4 smoc | 144 | 2,935 | 438 | 0.738 | 0.190 | 0.928 |
| dim4 direct | 144 | 829 | 86 | 0.182 | 0.687 | 0.869 |

**一条零成本的观察**:direct 臂读者便宜 4.3×,判官却贵 3.5×(判官输出 167 vs 37 tok)——
因为 direct 的答案是 1-3 句闲聊体,判官要写更多理由才能判。**两臂全口径几乎相等
($0.87 vs $0.90)**。这条应进 §7:把判官计入后,"直读更省"在小题集上并不成立。

---

## 三、J3 无填充对照梯(30 链 / 120 题)

### 语料构造

`scripts/b33j_build_nofiller.py`:按 slot 比例分层(employer 11 / position 9 / team 8 /
residence 2)、固定种子 `b33j-nofiller-30` 抽 30 条链;**只删 `chain_index is None` 的会话**,
其余字节逐字不动。结果:**保留 125 会话 / 删除 900 会话;保留字符 85,725 / 删除 1,464,942
—— 链文本仅占全语料的 5.53%**(与 G23 记载的 5.1% 同量级)。题集 = `wsc_s5_v2` 中属于
这 30 条链的 120 题(四型各 30)。卡店 `results/wt_cards_b33j_nofiller`(30 店,新目录,
旗标全关,与 v43/v44clean/v45 同一建卡口径 —— 三者卡片字段集机核比对完全相同)。

### 三格 × 两语料

| 臂 | 有填充 | 无填充 | Δ | b/c | McNemar p | 链级符号 | 链簇 95% CI |
|---|---|---|---|---|---|---|---|
| smoc | 90.83 | **92.50** | **+1.67** | 6/8 | 0.7905 | 5W/5L/20T p=1 | [−4.17, +8.33] |
| direct | 43.33 | **65.83** | **+22.50** | 7/34 | 2.53e-05 | 20W/0L/10T p=1.91e-06 | [+15.00, +30.83] |
| fullplain | 58.33 | **78.33** | **+20.00** | 7/31 | 1.16e-04 | 17W/4L/9T p=7.20e-03 | [+8.33, +30.83] |

无填充语料**内部**的对照:

| 对照 | Δ | McNemar p | 链簇 95% CI |
|---|---|---|---|
| smoc vs direct | **+26.67** | 9.43e-07 | [+17.50, +35.83] |
| fullplain vs direct | **+12.50** | 8.13e-03 | [+4.17, +20.83] |

### 判决

- **干扰契约第一次拿到操纵证据**:12pp 检索缺口此前只是"有填充语料内部按命中与否分箱"
  的观察量;现在把填充整体移除,direct 直接涨 **+22.50pp(CI 不跨零)**,
  而 smoc 纹丝不动(+1.67,p=0.79,TOST 意义上落在 ±8.33 带内)。
  **"填充是直读的致因、而非相关"这句话现在可以写。**
- **结构溢价的分解**:同 120 题上,有填充时 smoc−direct = **+47.50pp**,
  无填充时 **+26.67pp**。即 **20.83pp(43.9%)是"扛干扰"买的,26.67pp(56.1%)
  是"扛聚合"买的**,后者在 700 tok 的小库里依然存在 —— 这直接回应
  "把语料做干净了你们就没优势了"这条审稿意见。
- **top-10 在小库上仍不等于全文**:无填充库里 direct 平均读 641 tok、fullplain 903 tok
  (top-10 ≈ 全文的 71%),而 fullplain 仍高 **+12.50pp**。G23 预期的
  "700 tok 的店会让 top-10≈全文"**只对了一半**:预算接近,信息不接近。

### 限定(必须同页)

**有填充的 fullplain 那一格用的是归档行 `results/b28_fullplain_haiku_fmt.jsonl`,
它跑在 `wikistate_full_ALL_fmtnorm.json`(v2.0 系格式规范化语料)上,不是 v2.4。**
smoc / direct 两格的有填充数据分别来自 v2.4 口径的 b31 三文件合并与
`b33_direct_v24oai_shard*`,与本行不同源。fullplain 的 +20.00pp 因此**混入了语料版本差**,
只能当作"量级一致的旁证",不能与 direct 的 +22.50pp 同精度并列。补齐它需在 v2.4 上
重跑 120 题 fullplain(实测口径约 $2.1),**本轮因 $15 上限未跑,列为遗留**。

### 成本

| 项 | n | mean_in | 读者 $ | 判官 $ | 合计 |
|---|---|---|---|---|---|
| 无填充建店 | 30 店 | in 89,357 / out 33,730 | — | — | 0.258 |
| nofiller smoc | 120 | 639 | 0.364 | 0.189 | 0.553 |
| nofiller direct | 120 | 641 | 0.129 | 0.410 | 0.538 |
| nofiller fullplain | 120 | 903 | 0.171 | 0.383 | 0.554 |

---

## 四、J4 强读者日期粗化 E1(gpt-5-mini smoc)

### 设计

1. `scripts/ledger_fidelity_audit.py` 的判定逐字复现:**542 条金链锚行中 value 缺席 4 条
   (0.7%)、账目日期比金标粗 20 条(3.7%);完全保真链 130/144**。
2. 降级层 = 14 链 / 56 题(`data/b33j_datedeg_56.jsonl`)。其中 **10 链(40 题)是日期
   粗化**(20 行可补),**4 链(16 题)是 value 缺席**——后者按定义无法用"改日期"修复,
   故单列子层。
3. 补丁臂:渲染后按金链顺序找到第一条含该 value 的账目行,若日期粒度低于金标则把日期
   token 改写为金标日期(粒度还原:`2012-08-00` → `2012-08`);**只改日期 token**,
   命中逻辑与 `ledger_fidelity_audit.main()` 同源。两臂同题、同读者、同判官、同轮跑完。

### 数字

| 层 | n | 不补丁 | 补丁 | Δ | b/c | p | 链簇 95% CI |
|---|---|---|---|---|---|---|---|
| 全降级层 | 56(14 链) | 67.86 | 64.29 | **−3.57** | 5/3 | 0.727 | [−12.50, +5.36] |
| 日期粗化子层 | 40(10 链) | 77.50 | 75.00 | **−2.50** | 4/3 | 1.000 | [−12.50, +7.50] |

逐型(粗化子层,各 n=10,不补丁 → 补丁):change_count 70 → 80;count_before 80 → 80;
first_vs_last 100 → 100;**longest_tenure 60 → 40** —— 对日期精度最敏感的题型不升反降。

### 三条必须同页写的限定

1. **预注册阈值未达成**:`narrative_gaps_grounded_20260902.md:107` 写"降级层 66.1 → ≥80
   ⇒ 删掉该 limitation"。本轮 smoc(F.1)臂实测 67.86 → 补丁 64.29,**远不及 80**。
   **不得删除该 limitation。**(注:预注册那一格的读者协议是**裸账目 ledgerplain**,
   本轨按任务书跑的是 **smoc/F.1**;两者归档值分别为 66.1 与 64.3。裸账目那一格未跑,列为遗留。)
2. **效应量 ≤ 复跑噪声,本实验对 ±3.6pp 无功效**:同 56 题上归档
   `wsc_v2_smoc_v43_gpt5mini.jsonl` 为 **64.29**,本轮不补丁重跑为 **67.86** ——
   同配置同题的复跑漂移 **3.57pp**,与观测效应等大。该漂移**确证是纯读者不确定性**:
   机核比对 144 条链在 v2.0 与 v2.4 语料下由同一 v43 卡店渲染的账目,**143/144 逐字节相同**,
   唯一不同的 `wikiP551009-Q5321987` 不在降级层内(v2.4 删掉了某张卡的来源填充句,
   该卡日期回落 `undated`)。gpt-5-mini 走 chat.completions 无 temperature=0 通道。
3. **不能反过来说"日期粗化无害"**:本实验只否定了"把日期补回去就能修复"这条**修复路径**。
   `ledger_fidelity_audit` 的分层相关性(降级层 66.1 vs 保真层 83.8,全文臂跨层持平
   85.0/85.7)仍是**观察性**的;14 条降级链只占 9.7%,分层比较本就低功效。

### 对停机 3 的连带订正(建议措辞)

停机 3 原建议把 MASTER:308-311 的归因从"协议不适配"改成"账目日期粗化"。
**本实验说明这条替代归因同样没有干预证据。** 可写的版本只有:

> 上限归因未决。已定价的成分只有 F.1 协议税 −3.5(p=0.012,MASTER:357-359)。
> 其余约 −3pp 的候选解释"账目日期粗化"在 E1 直接修复测试下**未获支持**
> (补丁 vs 不补丁 Δ −3.57pp,p=0.727,n=56;该 n 下噪声地板即 ±3.6pp)。

### 成本

| 臂 | n | in tok | out tok | 读者 $ | 判官 $(归档单价) | 合计 |
|---|---|---|---|---|---|---|
| 不补丁 | 56 | 141,766 | 121,909 | 0.279 | 0.172 | 0.452 |
| 补丁 | 56 | 142,070 | 120,801 | 0.277 | 0.172 | 0.450 |

---

## 五、精确命令(可复现)

```bash
cd /d/ZZL_cluade
export PYTHONUTF8=1
export QVF_EMBED_BACKEND=openai       # direct / rtl 臂强制 openai 嵌入

# ── 题集/语料构造(全部 $0) ─────────────────────────────────
python scripts/b33j_gen_dim4_probes.py          # -> data/b33j_ws_dim4_probes.jsonl
python scripts/b33j_build_nofiller.py           # -> data/b33j_nofiller_30.json / _q120.jsonl
# J4 降级层 56 题(判定与 scripts/ledger_fidelity_audit.py:66-84 同源)
#   -> data/b33j_datedeg_56.jsonl

# ── J1:读时账目臂(4 分片,block 分片) ───────────────────────
for s in 0 1 2 3; do
  python scripts/lb_reader_arm_b33j.py --reader anthropic:claude-haiku-4-5 --arm rtl \
    --data data/wikistate_full_ALL_v24.json --questions data/wsc_s5_v2.jsonl \
    --out results/b33j/j1_rtl_s$s.jsonl --nshards 4 --shard $s --shard-mode block &
done; wait

# ── J2:S1/S2 各两臂(4 进程) ────────────────────────────────
python scripts/lb_reader_arm_b33j.py --reader anthropic:claude-haiku-4-5 --arm smoc \
  --data data/wikistate_full_ALL_v24.json --cards-dir results/wt_cards_v44clean \
  --questions data/ws_dim1_probes.jsonl --out results/b33j/j2_dim1_smoc_s0.jsonl &
python scripts/lb_reader_arm_b33j.py --reader anthropic:claude-haiku-4-5 --arm direct \
  --data data/wikistate_full_ALL_v24.json \
  --questions data/ws_dim1_probes.jsonl --out results/b33j/j2_dim1_direct_s0.jsonl &
python scripts/lb_reader_arm_b33j.py --reader anthropic:claude-haiku-4-5 --arm smoc \
  --data data/wikistate_full_ALL_v24.json --cards-dir results/wt_cards_v44clean \
  --questions data/b33j_ws_dim4_probes.jsonl --out results/b33j/j2_dim4_smoc_s0.jsonl &
python scripts/lb_reader_arm_b33j.py --reader anthropic:claude-haiku-4-5 --arm direct \
  --data data/wikistate_full_ALL_v24.json \
  --questions data/b33j_ws_dim4_probes.jsonl --out results/b33j/j2_dim4_direct_s0.jsonl &
wait

# ── J3:无填充建店(1 进程)+ 三臂(3 进程) ───────────────────
python scripts/wt_qvf_prototype.py --phase write \
  --data data/b33j_nofiller_30.json --cards-dir results/wt_cards_b33j_nofiller
for arm in smoc direct fullplain; do
  extra=""; [ "$arm" = smoc ] && extra="--cards-dir results/wt_cards_b33j_nofiller"
  python scripts/lb_reader_arm_b33j.py --reader anthropic:claude-haiku-4-5 --arm $arm \
    --data data/b33j_nofiller_30.json $extra \
    --questions data/b33j_nofiller_30_q120.jsonl \
    --out results/b33j/j3_${arm}_nofiller_s0.jsonl &
done; wait

# ── J4:两臂各两分片(4 进程) ────────────────────────────────
for s in 0 1; do
  python scripts/lb_reader_arm_b33j.py --reader openai:gpt-5-mini --arm smoc \
    --data data/wikistate_full_ALL_v24.json --cards-dir results/wt_cards_v43_20260828 \
    --questions data/b33j_datedeg_56.jsonl \
    --out results/b33j/j4_smoc_patched_s$s.jsonl --patch-dates --nshards 2 --shard $s &
  python scripts/lb_reader_arm_b33j.py --reader openai:gpt-5-mini --arm smoc \
    --data data/wikistate_full_ALL_v24.json --cards-dir results/wt_cards_v43_20260828 \
    --questions data/b33j_datedeg_56.jsonl \
    --out results/b33j/j4_smoc_plain_s$s.jsonl --nshards 2 --shard $s &
done; wait

# ── 统计与成本 ───────────────────────────────────────────────
python scripts/b33j_analyze.py all
python scripts/b33j_cost_ledger.py
```

(实跑时 J2→J3→J1 由 `scripts/b33j_run_rest.sh` 串行驱动,以保证并发恒 ≤4。)

---

## 六、假设与已知缺陷(不得当成已解决)

1. **对照基线继承了 33-A 之前的溯源缺陷**。smoc **90.45** 是三文件增量拼接
   (`b31_smoc_v22_full` 412 行 v2.2 语料 / `b31_smoc_v23` 104 行 / `b31_smoc_v24` 60 行),
   且其卡店 `results/wt_cards_v44clean` 被三波原地覆盖(09-01 15:03 / 18:24 / 09-02 01:24),
   即那次跑批已不可从磁盘复现(出处 `scratchpad/wf_gaps_full.md:4,6`)。
   **J1 的 −30.21pp 与 J3 的有填充 smoc 格全部继承这个缺陷。** 33-A 的
   `results/b33A_smoc_v45.jsonl`(单语料单建单跑)落地后,这两处**必须换基线重算**;
   本轨已把 rtl/无填充两侧的原始行全部落盘,重算是 $0。
2. **J2 的 smoc 用的就是 `wt_cards_v44clean`**,同样带上述覆盖史。J2 的两个 Δ 是
   **同店内 A/B**(两臂同店同题),重建方差对两臂同向,故结论稳健度高于 J1/J3 的跨批对照。
3. **J3 的 fullplain 有填充格跨语料**(fmtnorm vs v2.4),见 §三限定。
4. **J4 判官成本按归档单价**($0.00308/行),非行内 usage —— 该 112 行落盘早于判官 usage
   字段补丁。其余 1,304 行判官成本全部按行内 usage 实算。
5. **嵌入侧未计价**:text-embedding-3-small 无 usage 落盘,按语料 token 量级估 <$0.15,
   未计入总账($14.28)。
6. **J1 有 2 行重复**(`wikiP39020-Q11801663_v2lt` / `_v2fl`,收尾补跑与分片进程竞态):
   两次判决**均为 True**,措辞不同;分析器按 `question_id` 去重后 n=576 唯一,不影响任何数字。
7. **J4 用 gpt-5-mini,无 temperature=0 通道**,n=56 上噪声地板 ±3.6pp(实测),
   该格**不具备否定 ≤3.6pp 真效应的功效**。

---

## 七、成本总账(全部按 usage token;`python scripts/b33j_cost_ledger.py`)

| 条目 | n | 读者 $ | 建卡 $ | 判官 $ | 合计 $ |
|---|---|---|---|---|---|
| J4 gpt-5-mini smoc 补丁 | 56 | 0.277 | — | 0.172* | 0.450 |
| J4 gpt-5-mini smoc 不补丁 | 56 | 0.279 | — | 0.172* | 0.452 |
| J2 dim1 smoc | 144 | 0.696 | — | 0.204 | 0.900 |
| J2 dim1 direct | 144 | 0.159 | — | 0.713 | 0.873 |
| J2 dim4 smoc | 144 | 0.738 | — | 0.190 | 0.928 |
| J2 dim4 direct | 144 | 0.182 | — | 0.687 | 0.869 |
| J3 nofiller smoc | 120 | 0.364 | — | 0.189 | 0.553 |
| J3 nofiller direct | 120 | 0.129 | — | 0.410 | 0.538 |
| J3 nofiller fullplain | 120 | 0.171 | — | 0.383 | 0.554 |
| J3 无填充建店 | 30 店 | — | 0.258 | — | 0.258 |
| J1 rtl(读时账目) | 578 行/576 题 | 1.713 | 5.186 | 1.007 | 7.905 |
| **总计** | | **4.708** | **5.444** | **4.127** | **$14.279** |

\* 归档单价折算(见 §六第 4 条)。上限 $15,余量 $0.72(含未计价嵌入 <$0.15)。

---

## 八、遗留(有明确触发条件才跑)

| 编号 | 内容 | 触发条件 | 估价 |
|---|---|---|---|
| J3′ | v2.4 上重跑 120 题 fullplain(有填充) | 审稿人质疑 fullplain 那一格跨语料 | ~$2.1 |
| J4′ | 裸账目(ledgerplain)× gpt-5-mini,补丁 vs 不补丁,56 题 | 要按预注册原口径(66.1 → ≥80)判 | ~$0.8 |
| J4″ | 同 J4 但每臂重复 3 次以压噪声地板 | 想在 ±3.6pp 内下结论 | ~$2.7 |
| J1′ | 用 33-A 的 `b33A_smoc_v45` 作基线重算 rtl 差 | 33-A 落地 | **$0**(行已全部落盘) |
| J1″ | rtl 加深检索(top-24/top-40)看覆盖能否补上 | 要回答"是不是只要检索够深读时就够用" | ~$10(建卡随 k 线性涨) |
