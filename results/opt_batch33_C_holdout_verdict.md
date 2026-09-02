# 批 33-C 冻结保留集(WikiState-holdout v1)判决

预注册出处:`results/opt_batch33_prereg.md:17-19`(33-C)。
本文件 §一 在**任何读者臂开跑之前**写定;§二 起为实跑结果。

---

## 一、预注册(跑前写死,2026-09-02)

### 1. 语料构造(与开发场同一生成器)

| 环节 | 保留集做法 | 开发场同源件 |
|---|---|---|
| 实体来源 | 候选发现:WDQS(P39/P54/P551 成功)或搜索 API `srsort=random`(P108,WDQS 全局 GROUP BY 三次 504);链解析仍走 EntityData(时间串保留 Wikidata 原精度,含 `-00` 段)。**排除集 = 仓库内出现过的全部 QID**(144 链 uid、L1/L2、历史 items/full/candidates 各档,共 618 个) | `scripts/wikistate_scrape.py`(过滤规则逐字) |
| 低知名度闸 | sitelinks ≤ 5;值去重后带 P580+P582 的段 ≥ 3 | 同上(逐字) |
| 链清洗 | 非重叠 + 起止齐全 + 值去重 ≥3 段 | `scripts/wikistate_build.py` |
| 参数泄漏闸 | haiku-4.5 裸答四问(dim1/2/4/5),ClaudeJudge(opus-5)判对任一 → 弃条目 | 同上(逐字) |
| 会话渲染 | claude-opus-5,同提示词、同 `RenderedState` 契约、同逐字锚点校验(date 精确 / span 逐字在 turn 内 / 值名逐字在 span 内),失败重试 3 次后弃链 | `scripts/wikistate_render.py` |
| 填充干扰 | **不取 STALE 原始干草堆**,改取已逐个审计的 v2.3 填充池(`data/filler_pool_v23.json`,1,100 会话),池层面剔除 `results/pool_verdicts.json` 中 verdict=CONFIRMED 的会话 + `results/v23_residual_verdicts.json` 的 CONFIRMED 残留;每链 30 个,日期铺法逐字同源 | 批 31 构造规范 `results/opt_batch31_verdict.md:208-217` |
| 装配后复扫 | 任一 CONFIRMED 逐字引文若仍出现在填充里 → ABORT 不落盘;锚点 span 必须逐字可在会话 blob 中找到 | 双闸,同 `build_corpus_v24.py` |
| 出题 | 四型 change_count / count_before / longest_tenure / first_vs_last,题面口径、锚点候选、贪心平衡、末段计入至今、1/4 库"链尾可反超"锚全部逐字同源 | `scripts/gen_wsc_v2.py` |
| 槽位配额 | 按开发场 144 链比例(employer 51 / position 44 / team 38 / residence 11)最大余数法缩放到 40 链 → **P108 14 / P39 12 / P54 11 / P551 3** | — |
| 链长匹配 | 开发场链长直方图 3:86 / 4:33 / 5:9 / 6:8 / 7:5 / 8:3(均值 **3.76**)。新切片长链占比明显更高,若按发现序取会让保留集系统性更难、把 C2 与难度差混淆。故把链长当**匹配变量**:目标直方图 = 开发场比例最大余数法缩放到 40 链(3:24/4:9/5:3/6:2/7:1/8:1),在四槽位配额下求可行分配(`scripts/holdout_select_v1.py`,名单落盘 `data/holdout_selection_v1.json`)——只改"选哪 40 条",不动任何过滤规则;实际达成的直方图在 §二 照报 | — |
| 随机种子 | 填充采样 `random.Random(20260902)` | — |

规模:**40 链 / 160 题(四型各 40)**。与现有 144 链 uid **零交集**,与 L1/L2 零交集。
产物:`data/wikistate_holdout_v1.json`、`data/wsc_holdout_v1.jsonl`、`data/wsc_holdout_v1.keymap.json`。

**语料冻结条款:第一次读者臂跑完之后,语料与题集一律不得再改**(prereg:19"不许回头改语料")。
若发现缺陷,只能作为 limitation 记入本文件,不得重建后重跑。

### 2. 臂位(跑前写死)

| 臂 | 命令口径 | 读者 | 判官 |
|---|---|---|---|
| smoc(账目) | `scripts/lb_reader_arm.py --arm smoc --cards-dir results/wt_cards_holdout` | anthropic:claude-haiku-4-5 | ClaudeJudge(claude-opus-5,冻结) |
| direct(top-10 检索直读) | 同脚本 `--arm direct`,**`QVF_EMBED_BACKEND=openai`**(text-embedding-3-small) | 同上 | 同上 |
| fullplain(全文裸读) | 同脚本 `--arm fullplain` | 同上 | 同上 |

建店:`scripts/wt_qvf_prototype.py --phase write --cards-dir results/wt_cards_holdout`,
`QVF_CARD_OWNER_GATE=0`(与开发场 v2.4 头条同配置),**新建目录、建后只读、只建一次**。

与 33-C 预注册的偏差(明记):预注册第三臂写的是 smw,本次执行改为 **fullplain**——
`lb_reader_arm.py` 的臂集合为 smoc/direct/fullplain/closedbook/ledgerplain,不含 smw;
且开发场可比数字 52.26 正是全文裸读臂(`results/wsc_v2_smwplain.jsonl`)。

### 3. 开发场参照值(冻结,来自盘上实跑文件)

| 臂 | 全库 576 | change_count | count_before | first_vs_last | longest_tenure | 出处 |
|---|---|---|---|---|---|---|
| smoc(v2.4) | **90.45** | 88.19 | 88.89 | 96.53 | 88.19 | `results/b33B_merged_v24.jsonl` |
| direct(v2.4,OpenAI 嵌入) | **48.26** | 34.72 | 43.75 | 80.56 | 34.03 | `results/b33_direct_v24oai_shard*.jsonl` |
| fullplain(v2.0 语料) | **52.26** | 29.86 | 67.36 | 72.22 | 39.58 | `results/wsc_v2_smwplain.jsonl` |
| fullplain(v2.4 语料,33-A 同日跑完,跑后补入) | 53.47 | 31.94 | 67.36 | 75.69 | 38.89 | `results/b33A_smwplain.jsonl` |

结构总价(开发场,同日实跑口径)= 90.45 − 48.26 = **+42.19**。

开发场同法复算(144 链簇自助 10,000 次,种子 20260902):

| 量 | 开发场点估 | 开发场 95% 簇 CI |
|---|---|---|
| smoc | 90.45 | [87.15, 93.40] |
| direct | 48.26 | [43.92, 52.43] |
| fullplain | 52.26 | [47.74, 56.77] |
| **smoc − direct** | **+42.19**(b=17/c=260) | **[+37.15, +47.22]** |
| smoc − fullplain | +38.19(b=20/c=240) | [+32.99, +43.23] |
| fullplain − direct | +3.99(b=111/c=134) | [−1.39, +9.20] |

开发场 smoc−direct 的实测簇 CI [+37.15,+47.22] 落在预注册区间 [+35,+48] 内,C1 以两者取并集判读。

### 4. 判据(跑前写死)

- **C1**:保留集上 smoc − direct 的 40 链簇自助 95% CI 与开发场区间 [+35, +48] **有重叠**。
- **C2**:任何臂从开发场到保留集的下降 **≤ 5pp**;任一臂超过 → 报"开发场过拟合"。
- 统计:配对 McNemar(题级,精确二项);簇单位 = 链(40 个),自助 10,000 次,分位数法 95% CI。
- 成本:按 usage tokens 结算,读者 haiku-4.5 $0.80/M 输入、$4/M 输出;判官 opus-5 $5/$25 另计。上限 $25。

---

## 二、语料构造实况(跑前完成,冻结)

### 1. 规模与匹配

| 项 | 保留集 v1 | 开发场 v2.4 |
|---|---|---|
| 链 / 题 | **40 / 160**(四型各 40) | 144 / 576 |
| 槽位 | employer 14 / position 12 / team 11 / residence 3 | 51 / 44 / 38 / 11(比例一致) |
| 链长直方图 | 3:23 / 4:10 / 5:3 / 6:2 / 7:1 / 8:1(均值 3.78) | 3:86 / 4:33 / 5:9 / 6:8 / 7:5 / 8:3(均值 3.76) |
| 每链会话数 | 均值 33.8(30 填充 + 链段) | 均值 33.8 |
| 每链体量 | ≈12,812 tok | ≈12,869 tok |
| 链跨年数 | 均值 11.9 年 | 均值 14.1 年 |
| 与既有 144 链 / L1 / L2 的 QID 交集 | **0** | — |
| 与开发场题集 uid 交集 | **0**(144 vs 40) | — |

链长目标本为 3:24 / 4:9(与开发场比例逐格相等),因一条链渲染被模型**确定性拒答**
(见下)换成同槽位 4 段备胎,实际落在 3:23 / 4:10 —— 一条链一格的偏差,槽位配额未动。

### 2. 双闸与构造规范

- **闸1 锚点**:151/151 条链段的 `state_span` 逐字出现在该链会话里(0 违例);
- **闸2 污染**:70 条池级 CONFIRMED + 4 条链级 CONFIRMED 逐字引文,在 1,200 个填充实例中**残余 0**;
- 填充池:1,100 审计会话 → 剔 45 个 CONFIRMED 会话 → **复扫**再剔 5 个含同句的会话 → 干净池 **1,050**;
  每链 30 个,按 uid 播种取样(`random.Random(20260902 + md5(qid))`),分进程渲染可逐位复现;
- 参数泄漏闸:P108 17 条过闸 16 keep(1 drop)、P39 33 条中前 17 条过闸 14 keep、
  P54 15 probe 13 keep、P551 14 条 14 keep;drop 判据 = haiku 裸答四问被 opus 判官判对任一。
- 出题分布判据(与开发场生成器同款):change_count 众数占比 30.0%、count_before 22.5%
  (闸 ≤35% 通过);longest_tenure 链尾命中 35.0%(闸 >10% 通过)。

两处**残余难度差**(生成器同款但落点不同,判读时必须计入):

| 量 | 开发场 576 | 保留集 160 | 方向 |
|---|---|---|---|
| longest_tenure 金标 = 链尾值的比例 | 24.3% | **35.0%** | 保留集对"直接答最新值"的朴素读者更友好 |
| 链段日期为年/月精度(`-00`) | 42.6% | 36.4% | 保留集日期略更精确 |
| change_count 金标分布(1/2/3/≥4) | 30.6 / 29.9 / 22.2 / 17.4% | 30.0 / 27.5 / 25.0 / 17.5% | 基本一致 |

### 3. 构造中的三处如实记录

1. **WDQS 对 P108 不可用**:`GROUP BY ?item HAVING(COUNT(DISTINCT ?v)>=3)` 在公共端点
   对 P108 五次全部 504/502/429(降 LIMIT、加内层 LIMIT 子查询均无效);P39/P54/P551 成功。
   P108 改用搜索 API `srsort=random` 随机抽样(相关度排序前 150 个 offset 命中率实测为 0
   —— 名人优先与 sitelinks≤5 闸直接冲突),命中率 ≈7.5%,过滤规则未变。
2. **一条链被模型拒答**:`holdP108-Q45326326`(Andrew Broadbent)第 2 段
   (Pirbright Institute, 2014-07-07)在 claude-opus-5 上 `stop_reason=refusal`,
   三次重试 + 单独复验均如此;该链丢弃,用同槽位 4 段备胎 Q61049349 顶替(记入 keymap)。
3. **渲染并发化**:链内各段互不依赖,改为 4 线程并发发起(同提示词、同契约、同校验、
   结果按下标归位),与串行等价;填充取样改为按 uid 播种以保证分进程可复现。

产物与校验和:
- `data/wikistate_holdout_v1.json` sha256 `69c25b202b3dc212fad295af18421eaeaf685885658fd0526412df27df4ff72c`
- `data/wsc_holdout_v1.jsonl` sha256 `0a92109f2b1af00550ecbe0642b5c24d3ba7d960f39493e9c7a3d3284eb4f4d4`
- `data/wsc_holdout_v1.keymap.json`(答案键:每链槽位、Wikidata QID、值序列、日期序列、锚句)
- `data/holdout_selection_v1.json`(定选名单 + 链长匹配 + 替换记录)
- 中间档:`data/holdout_candidates_<PROP>.json`、`data/holdout_items_<PROP>.json`、
  `data/holdout_itempool_<PROP>.json`、`data/holdout_part_<PROP>.json`

## 三、实跑结果(2026-09-02,160 题 × 3 臂,语料自第一跑起未再改动)

### 1. 判决

> **C1 通过,C2 通过:结构总价在从未碰过的 Wikidata 切片上原样成立——
> 保留集 smoc − direct = +43.12pp(40 链簇 CI [+34.38, +51.25]),
> 与开发场 +42.19(簇 CI [+37.15, +47.22])统计不可分;三个臂无一下降。
> 但"账目 vs 全文裸读"这条差不迁移:开发场 +36.98 → 保留集 +23.12,两侧簇 CI 不重叠——
> 保留集对**全文读者**明显更容易,对**检索直读**则几乎逐点等同。**未见开发场过拟合;
> 见到的是"全文裸读基线是切片敏感的"。**

### 2. 三臂点估与 40 链簇 CI

| 臂 | 保留集 160 题 | 40 链簇 95% CI | 开发场 576 题 | 开发场簇 CI | Δ(保留−开发) |
|---|---|---|---|---|---|
| **smoc(账目)** | **95.00** | [90.00, 98.75] | 90.45(v2.4) | [87.15, 93.40] | **+4.55** |
| **direct(top-10,OpenAI 嵌入)** | **51.88** | [44.38, 59.38] | 48.26(v2.4) | [43.92, 52.43] | **+3.62** |
| **fullplain(全文裸读)** | **71.88** | [66.25, 77.50] | 53.47(v2.4)/52.26(v2.0) | [49.31, 57.64] | **+18.41** |

逐题型:

| 题型 | smoc 保留 / 开发 | direct 保留 / 开发 | fullplain 保留 / 开发(v2.4) |
|---|---|---|---|
| change_count | 97.50 / 88.19 | 30.00 / 34.72 | 50.00 / 31.94 |
| count_before | 95.00 / 88.89 | 37.50 / 43.75 | 82.50 / 67.36 |
| longest_tenure | 87.50 / 88.19 | 50.00 / 34.03 | 60.00 / 38.89 |
| first_vs_last | 100.00 / 96.53 | 90.00 / 80.56 | 95.00 / 75.69 |

### 3. 三组配对对比(题级 McNemar + 40 链簇自助)

| 对比 | 保留集 Δ | b/c | McNemar p | 40 链簇 95% CI | 链级符号检验 | 开发场同法 Δ(簇 CI) |
|---|---|---|---|---|---|---|
| **smoc − direct(结构总价)** | **+43.12** | 4/73 | 1.9e-17 | **[+34.38, +51.25]** | 34W/1L/5T,p=2.1e-09 | +42.19([+37.15,+47.22]) |
| smoc − fullplain | +23.12 | 3/40 | 3.0e-09 | [+16.88, +29.38] | 30W/1L/9T,p=3.0e-08 | +36.98([+32.12,+41.67]) |
| fullplain − direct | +20.00 | 20/52 | 2.1e-04 | [+9.38, +30.00] | 25W/8L/7T,p=0.0046 | +5.21([−0.17,+10.59]) |

### 4. 判据逐条

- **C1(smoc−direct 的簇 CI 与开发场区间有重叠)—— 通过**。
  保留集 [+34.38, +51.25] 与开发场实测 [+37.15, +47.22] 和预注册 [+35, +48] 均大幅重叠;
  点估相差 0.93pp。b/c=4/73 说明差异不是少数题拉动:73 题 direct 错而 smoc 对,反向只有 4 题;
  链级 34 胜 1 负 5 平。
- **C2(任何臂开发场→保留集下降 ≤5pp)—— 通过,且方向全为上升**。
  smoc +4.55、direct +3.62、fullplain +18.41,无一下降,**不支持"开发场过拟合"**。

### 5. 但保留集**不是**开发场的等难度复制:一处必须写进 limitation

fullplain 的两侧簇 CI **不重叠**([66.25,77.50] vs [49.31,57.64]),即保留集对全文裸读**显著更容易**;
连带 smoc−fullplain 从 +36.98 掉到 +23.12(两侧 CI 不重叠)。逐一排查后**排除**了四个解释:

| 候选解释 | 检验 | 结论 |
|---|---|---|
| 上下文体量不同 | fullplain 每题输入 13,620 tok(保留) vs 13,671(开发);smoc 3,118 vs 2,950 | 排除 |
| 链长分布不同 | 按链长分层:length-3 上 direct 56.5(保留) vs 57.3(开发),**逐点等同**;而 fullplain 72.8 vs 57.8,**同一链长仍差 15pp** | 排除(不是链长) |
| 锚句更套路化 | 锚句提示词命中率 51.7%(保留) vs 53.1%(开发);每锚平均 9.9 vs 10.9 词;每锚不同开头数 0.185 vs 0.149(保留更散) | 排除 |
| 填充在链内更同质(旧构造从 12 个 STALE 条目各取 5 段,可能出现同一人设连续会话) | 链内填充两两 Jaccard 的逐会话最大值均值 0.159(保留) vs 0.161(开发) | 排除 |
| 语料版本(开发场 fullplain 旧值 52.26 在受污染的 v2.0 上) | 用 33-A 同日在 v2.4 上跑的 smwplain 复算 = 53.47 | 只解释 1.2pp,**排除为主因** |

分层结果给出本条最硬的形式:**direct 的迁移是逐点的(同链长差 0.8pp),fullplain 的迁移不是(同链长差 15pp)**。
成因未定 —— 记为保留集 v1 的已知缺陷,不得把 "smoc − fullplain" 的开发场数值当作可迁移量引用。

### 6. 成本与延迟(实测 usage token;判官侧 lb_reader_arm 不落盘,标注为估算)

| 项 | 输入 tok | 输出 tok | $ | 口径 |
|---|---|---|---|---|
| smoc 读者(haiku-4.5) | 498,872 | 73,111 | **0.6915** | 实测 |
| direct 读者 | 138,991 | 13,230 | **0.1641** | 实测 |
| fullplain 读者 | 2,179,228 | 23,432 | **1.8371** | 实测 |
| 建店(haiku,40 链一次) | 845,950 | 328,533 | **1.9909** | 实测 |
| 参数泄漏闸判官(opus-5,含被弃的首轮) | 83,899 | 38,033 | **1.3703** | 实测(`judge.total_usage`) |
| 参数泄漏闸裸答(haiku) | ≈29K | ≈38K | ≈0.17 | 估算(≈480 次调用) |
| 会话渲染(opus-5) | ≈29K | ≈144K | ≈3.74 | 估算(≈240 次调用) |
| 三臂判官(opus-5) | ≈105K | ≈47K | ≈1.68 | 估算(506 次×实测均值 207/92) |
| direct 嵌入(text-embedding-3-small) | ≈520K | — | ≈0.01 | 估算 |
| **合计** | | | **≈$11.7**(实测部分 $6.05) | 上限 $25,**未超** |

每题成本(读者侧):smoc $0.0043 / direct $0.0010 / fullplain $0.0115 —— 账目臂是全文臂的 **1/2.7**,
读取 tok 是 **1/4.4**(3,118 vs 13,620)。平均延迟:smoc 4.83s / direct 1.67s / fullplain 2.62s
(**注**:本批与 30+ 个其他 33 批进程共享同一 API 配额,延迟数不可当作干净的时延测量)。
判官回退(结构化输出失败转包含式启发)在三臂 480 条里**为 0**;协议偏离 0 条;空答 0 条。

### 7. 复现命令(逐字)

```bash
# 1 候选发现(P39/P54/P551 走 WDQS;P108 自动回退到搜索 API srsort=random)
PYTHONUTF8=1 python -u scripts/holdout_scrape_v1.py P551 14 3000
PYTHONUTF8=1 python -u scripts/holdout_scrape_v1.py P54  35 2000
PYTHONUTF8=1 python -u scripts/holdout_scrape_v1.py P39  40 2000
PYTHONUTF8=1 python -u scripts/holdout_scrape_v1.py P108 25 3000
# 2 标签解析 + 链清洗 + 参数泄漏闸(第二参数 = keep 上限)
PYTHONUTF8=1 python -u scripts/holdout_build_v1.py P108 16
PYTHONUTF8=1 python -u scripts/holdout_build_v1.py P39 14
PYTHONUTF8=1 python -u scripts/holdout_build_v1.py P54 13
PYTHONUTF8=1 python -u scripts/holdout_build_v1.py P551 6
# 2.5 合并条目池 + 按开发场链长直方图定选 40 条
PYTHONUTF8=1 python -u scripts/holdout_select_v1.py
# 3 渲染(分槽位四进程,可断点续跑)
QVF_HOLDOUT_QUOTA='{"P108":14}'  QVF_HOLDOUT_OUT='data/holdout_part_P108.json'  PYTHONUTF8=1 python -u scripts/holdout_render_v1.py
QVF_HOLDOUT_QUOTA='{"P39":12}'   QVF_HOLDOUT_OUT='data/holdout_part_P39.json'   PYTHONUTF8=1 python -u scripts/holdout_render_v1.py
QVF_HOLDOUT_QUOTA='{"P54":11}'   QVF_HOLDOUT_OUT='data/holdout_part_P54.json'   PYTHONUTF8=1 python -u scripts/holdout_render_v1.py
QVF_HOLDOUT_QUOTA='{"P551":3}'   QVF_HOLDOUT_OUT='data/holdout_part_P551.json'  PYTHONUTF8=1 python -u scripts/holdout_render_v1.py
# 4 合并 + 双闸 + 零交集核验 → data/wikistate_holdout_v1.json
PYTHONUTF8=1 python -u scripts/holdout_merge_v1.py
# 5 出题 160 + 答案键
PYTHONUTF8=1 python -u scripts/holdout_questions_v1.py
# 6 建店(新目录,OWNER_GATE=0,建后只读;<uids> = 逗号分隔的 40 个 uid)
QVF_CARD_OWNER_GATE=0 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype.py --phase write \
  --data data/wikistate_holdout_v1.json --cards-dir results/wt_cards_holdout --uids "<uids>"
# 7 三臂(读者 anthropic:claude-haiku-4-5,判官 ClaudeJudge/claude-opus-5)
PYTHONUTF8=1 python -u scripts/lb_reader_arm.py --reader anthropic:claude-haiku-4-5 --arm smoc \
  --data data/wikistate_holdout_v1.json --questions data/wsc_holdout_v1.jsonl \
  --cards-dir results/wt_cards_holdout --out results/holdout_smoc.jsonl
QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python -u scripts/lb_reader_arm.py --reader anthropic:claude-haiku-4-5 --arm direct \
  --data data/wikistate_holdout_v1.json --questions data/wsc_holdout_v1.jsonl \
  --cards-dir results/wt_cards_holdout --out results/holdout_direct.jsonl
PYTHONUTF8=1 python -u scripts/lb_reader_arm.py --reader anthropic:claude-haiku-4-5 --arm fullplain \
  --data data/wikistate_holdout_v1.json --questions data/wsc_holdout_v1.jsonl \
  --cards-dir results/wt_cards_holdout --out results/holdout_fullplain.jsonl
# 8 统计(点估 + 逐题型 + McNemar + 40 链簇自助 + 成本)
PYTHONUTF8=1 python -u scripts/holdout_stats_v1.py
```

**分片说明**:实跑时 smoc 因 API 配额争用被切成 6 个题目分片并行
(`results/holdout_smoc.jsonl`、`..._b/_c/_d/_e/_f.jsonl`),统计脚本按 `holdout_smoc*.jsonl` 通配去重合并
(160 唯一题,26 条重复由 question_id 去重,判读不受影响);单进程跑法与上表命令等价。

### 8. 文件清单

| 类 | 路径 |
|---|---|
| 语料(冻结) | `data/wikistate_holdout_v1.json`(sha256 `69c25b20…4ff72c`) |
| 题集(冻结) | `data/wsc_holdout_v1.jsonl`(sha256 `0a92109f…4eb4f4d4`) |
| 答案键 | `data/wsc_holdout_v1.keymap.json` |
| 定选与替换记录 | `data/holdout_selection_v1.json` |
| 中间档 | `data/holdout_candidates_<P>.json`、`data/holdout_items_<P>.json`、`data/holdout_itempool_<P>.json`、`data/holdout_part_<P>.json` |
| 卡片店(只读) | `results/wt_cards_holdout/`(40 个 uid,2,457 条状态记录,gate 0,建后只读) |
| 结果 | `results/holdout_smoc*.jsonl`、`results/holdout_direct.jsonl`、`results/holdout_fullplain.jsonl` |
| 统计 | `results/holdout_stats_v1.json` |
| 生成器 | `scripts/holdout_scrape_v1.py`、`holdout_build_v1.py`、`holdout_select_v1.py`、`holdout_render_v1.py`、`holdout_merge_v1.py`、`holdout_questions_v1.py`、`holdout_stats_v1.py`、`holdout_run_v1.sh` |

### 9. 关掉了什么、没关掉什么

**关掉**:
1. "576 主场无留出集"——现有 40 链 / 160 题的冻结保留集,与 144 链零交集,预注册在先、语料在第一跑后未改;
2. "结构总价可能是开发场过拟合"——保留集 +43.12,与开发场 +42.19 统计不可分,C1/C2 双过;
3. "v3 循环"(题型在同一批语料上反复调优)——四型题在全新切片上一次跑完,无迭代;
4. 构造规范可执行性——批 31 的"审池不审实例 + 复扫残余为零"在新语料上跑通(池 1,100 → 剔 45 + 复扫再剔 5 → 1,050,残余 0)。

**没关掉**:
1. **人工核验**:本批零人工;保留集 20% 抽样算 κ 的那一步(现状文档 §五第 3 项)未做;
2. **fullplain 不迁移**:上文 §5,成因未定,是保留集 v1 的已知缺陷;
3. **单读者单判官**:仍只有 haiku 读者 + opus 判官一组;
4. **residence 只有 3 条链**:按开发场比例缩放的必然结果,该槽位在保留集上无统计力;
5. **判官侧 token 不落盘**:`lb_reader_arm.py` 仍未写 judge usage,本文件三臂判官成本为估算
   (代码修复项已列在现状文档 §五末尾,本批未做)。
