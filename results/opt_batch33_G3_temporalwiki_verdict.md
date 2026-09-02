# 批 33-G3 终判:Temporal Wiki 外场——猜想被否定,smoc 在百科快照语料上显著输给直读(2026-09-02)

预注册 `results/opt_batch33_prereg.md` §33-G(判据 G:**smoc − direct > 0 且簇 CI
不跨零**方可写入外场表;闭卷 ≥ direct 的考场标"污染")。

**一句话判决:33-G3 判负且方向显著反转——smoc 82.3 vs direct 86.7,Δ = −4.3pp,
簇级 95% CI [−7.0, −2.0](不跨零,但在零的负侧),McNemar b/c = 1/14,p = 9.8e-04;
本考场不得写入外场表。同时闭卷 25.3 ≪ direct 86.7 → 考场标 NOT CONTAMINATED,
但闭卷单靠参数知识就答对 1/4,污染量级须随场公布。**

实测成本 **$6.32**(上限 $15 内);并行度 4;判官 ClaudeJudge(claude-opus-5,
冻结默认);读者 `anthropic:claude-haiku-4-5`;direct 臂 `QVF_EMBED_BACKEND=openai`
(text-embedding-3-small)。

---

## 一、考场来源与构造(datasheet)

| 项 | 值 |
|---|---|
| 论文 | Atahan Özer & Çağatay Yıldız, *Question Answering under Temporal Conflict*, arXiv 2506.07270 |
| 数据仓 | https://github.com/atahanoezer/TQA(MIT License, Copyright (c) 2025 Atahan Özer) |
| 落地 | `data/external/temporalwiki/repo/`(pin 到 commit `ef99ea0fc269f5f87ca2d4813d37767474246d3e`,2025-06-08;`full_data_filtered/*.json` 共 **878** 文件 = 878 实体链) |
| 官方规模(实测) | **2,035** 题 / 878 链;9 种关系;年份跨度 2010–2020(2010 占 626 题) |
| 关系分布(题) | P54 团队 557 / P108 雇主 330 / P39 职位 326 / P286 主教练 233 / P102 政党 224 / P488 主席 158 / P127 所有者 72 / P6 政府首脑 68 / P69 就学 67 |

### 转换口径(`scripts/tw_build_arena.py`,逐条写死)

1. **一个 event 文件 = 一条实体链 = 一个店**(uid `tw-0000`…`tw-0142`);
   实体 = 该链 Wikipedia 条目主体,轮次前缀统一写 `owner:`(对应本项目卡片
   schema 的 owner 位;会话语料里那一位是 `user`)。
2. **每个 incident = 一个带日期轮次**,`date = f"{q_year}-01-01"`,文本 =
   `owner: Wikipedia article "<title>" — snapshot for <year>.` + `Infobox: k: v; …`
   (清洗后最多 1400 字符)+ `Article: <匹配段落>`(最多 1500 字符)。
   底层 revision 多为 q_year+1 年初抓取(`map_year − q_year == 1` 占 1,721/2,035),
   本转换按**提问所指年份**落日期,使"as of 年份"与账目行日期对齐;
   该重标定对四臂逐字节同一份文本,不构成臂间偏置。
3. **题目原样取** `incidents[y]["question"]`(自带 "in \<year\>" 的 as-of 年,
   只去掉前缀 `Question: `),gold = Wikidata 标准标签。
4. **入样三重条件(arm-independent)**:
   - ① 链内各 incident 的 revision url 互不相同——排除 **112 条**多个 q_year 共用
     同一快照的链(那类链不存在"逐年快照"这一前提,给它们编造两个同文异日的
     轮次等于伪造时序);
   - ② 只取**单答案**题(`len(answer)==1`)——冻结 ClaudeJudge 判据明写"多部分
     gold 只答其一即错",672/1,676 的多答案题会把四臂一律判错、纯加噪;
   - ③ 链内保留题 ≥2 且答案至少两取值(= **答案跨年份发生变化**,任务硬要求)。
   → 抽样框:**343 链 / 734 题**。
5. **分层抽样**:按 relation 的可用题量比例(最大余数法)配满 300 题,
   关系内按 `seed=33` 打乱链序、整链纳入、超配额只截**题**不截快照——
   **被选中的链一律把全部合格快照写进店**,故任何店都保有 ≥2 个冲突年份快照。
6. 产出:**300 题 / 143 店**;店内快照数 2 (129 店) / 3 (12 店) / 4 (2 店);
   轮次平均 944 字符(最长 2,291)。

### 三条必须随场公布的构造局限

- **L1 证据择段是 gold 条件化的**:"匹配段落"= 与**该快照自身年份 gold 标签**
  词重叠最高的段落(重叠为 0 时退回导语)。这是 evidence-oracle 选段,保证考场
  可答(实测 gold 词在读者可见全文中的可得性 **293/300 = 97.7%**),但**同一份
  文本喂给全部四臂**,不产生臂间偏置;绝对分不可与官方 TQA 表对比。
- **L2 本考场不检验检索**:每店只有 2–4 条记忆,direct 臂 `top_k=10` 恒等于
  取全部(日志逐题 `k=2`/`k=3`)。故 "direct" 在此实为**带日期誊录 + 助手框定
  提示词的全上下文臂**,与 fullplain 只差提示词(实测 Δ = +1.0pp,p = 0.508)。
  结构化机制在此比的是"压缩账目 vs 原始快照",**不是**"账目 vs 检索"。
- **L3 判官口径**:全场 ClaudeJudge(claude-opus-5)统一判,与官方 TQA 的
  EM/子串判据不同;跨论文绝对分不可比,场内四臂配对可比。

---

## 二、结果

### 2.1 总体准确率(n = 300,四臂逐题齐全)

| 臂 | 正确 | acc | 全口径 $/题 | 延迟 s/题 |
|---|---|---|---|---|
| **direct**(稠密直读 top-10,OpenAI 嵌入) | 260 | **86.7** | $0.00386 | 4.7 |
| **fullplain**(全文裸读) | 257 | **85.7** | $0.00310 | 0.9 |
| **smoc**(卡→账目→读) | 247 | **82.3** | $0.00972 | 7.5 |
| **closedbook**(零上下文) | 76 | **25.3** | $0.00398 | 1.7 |

### 2.2 配对比较(精确双侧符号检验 = McNemar;簇 = 实体 uid,143 簇;N_BOOT=10000,SEED=20260803)

| 对比 | Δ(pp) | 簇 95% CI | b/c | McNemar p | 簇 W/L/T | 簇 p |
|---|---|---|---|---|---|---|
| **smoc − direct** | **−4.3** | **[−7.0, −2.0]** | 1/14 | **9.77e-04** | 1/13/129 | 1.83e-03 |
| smoc − fullplain | −3.3 | [−6.2, −0.7] | 3/13 | 0.0213 | 3/12/128 | 0.0352 |
| smoc − closedbook | +57.0 | [+50.3, +63.6] | 179/8 | 3.4e-43 | 107/2/34 | 1.85e-29 |
| direct − closedbook | +61.3 | [+54.9, +67.8] | 187/3 | 1.46e-51 | 113/1/29 | 1.11e-32 |
| fullplain − closedbook | +60.3 | [+53.9, +66.8] | 183/2 | 7.02e-52 | 113/1/29 | 1.11e-32 |
| direct − fullplain | +1.0 | [−1.0, +3.0] | 6/3 | 0.508 | 6/3/134 | 0.508 |

**判据 G 判负**:smoc − direct 为负且簇 CI 完全落在零的负侧(不是"不显著",
而是**显著为负**)。本考场按预注册不得写入外场表。

### 2.3 分关系(题数 / 四臂 acc)

| relation | 槽 | n | smoc | direct | fullplain | closedbook |
|---|---|---|---|---|---|---|
| P54 | 团队 | 65 | 84.6 | 89.2 | 87.7 | 35.4 |
| P39 | 职位 | 52 | 75.0 | 82.7 | 84.6 | 40.4 |
| P286 | 主教练 | 47 | 97.9 | 97.9 | 97.9 | 8.5 |
| P102 | 政党 | 40 | 70.0 | 72.5 | 62.5 | 15.0 |
| P108 | 雇主 | 37 | 75.7 | 78.4 | 81.1 | 8.1 |
| P488 | 主席 | 29 | 93.1 | 100.0 | 100.0 | 20.7 |
| P127 | 所有者 | 14 | 64.3 | 78.6 | 78.6 | 21.4 |
| P6 | 政府首脑 | 14 | 100.0 | 100.0 | 100.0 | 64.3 |
| P69 | 就学 | 2 | 50.0 | 50.0 | 50.0 | 50.0 |

smoc 在 9 个关系里 0 胜 6 负 3 平(逐关系点估计),无一关系上占优。

### 2.4 近因陷阱轴(提问年份在店内的位置)

| 位置 | n | smoc | direct | fullplain | closedbook |
|---|---|---|---|---|---|
| 最早快照 | 143 | 84.6 | 88.1 | 88.1 | 26.6 |
| 中间快照 | 16 | 93.8 | 100.0 | 100.0 | 31.2 |
| 最新快照 | 141 | 78.7 | 83.7 | 81.6 | 23.4 |

三臂在"问最新快照"上一致更差(smoc −5.9 / direct −4.4 / fullplain −6.5 pp),与论文"模型偏向近因/高频答案"
的现象方向一致但幅度温和;**smoc 没有在任何一档上把差距翻正**。

---

## 三、污染对照(闭卷)

- **closedbook 25.3 vs direct 86.7 → 考场标 `NOT CONTAMINATED`**(预注册判据:
  闭卷 ≥ direct 才标污染)。
- 但**污染量级不为零且须公布**:haiku-4.5 零上下文即答对 76/300;关系间极不均匀
  ——P6 政府首脑 64.3、P39 职位 40.4、P54 团队 35.4(高知名度长尾实体),
  而 P108 雇主 8.1、P286 主教练 8.5(真长尾)。
- **去污染子集(闭卷答错的 224 题)结论不变**:smoc 79.9 / direct 83.5 /
  fullplain 81.7;smoc − direct = **−3.6pp**,簇 CI [−6.7, −0.9],b/c = 1/9,
  McNemar p = 0.0215,簇 p = 0.0391(127 簇)。**负向结论不是污染伪影。**
- 论文自带的参数化偏置诊断(答案里出现**非本年**的 most_recent / most_frequent
  答案):smoc 0.0% / 2.7%,fullplain 0.3% / 2.0%,direct 4.7% / 10.0%,
  closedbook 5.0% / 5.0%。**smoc 的"踩陈值"率确实最低**——它输的不是踩陈值,
  是另一种错(见 §四)。

---

## 四、失败归因(零成本,机制已定位在写侧对齐而非写侧丢失)

15 个不一致对里 smoc 输 14 / 赢 1。逐条重渲染账目后:

- **写侧没丢**:gold 标签词在**卡片账目**中的可得性 **290/300 = 96.7%**
  (全文底料 97.7%);14 个 smoc 败例里 **13 例 gold 就在账目行上**(唯一未命中
  的 `tw-0040-2013` gold 标签是单字母 "X",被 ≥4 字符的机械匹配规则滤掉,
  实际账目里写着 "Google X",属判官口径而非写侧丢失)。
- **病灶 = 快照边界在账目里被抹掉**。百科条目叙述的是实体**一生**的履历,
  建卡器把段落里的历史事实按**叙述年份**填 `stated_date`,于是:
  **1,656 条账目行中 523 条(31.6%)的 stated_date 年份 ≠ 其来源快照的年份**。
  账目因此从"逐年快照时间线"退化成"生平事件时间线",
  "**year-Y 的快照把什么登记为当前值**"这一关键对齐被抹除;
  而 direct/fullplain 保留原文,答案里普遍复述 "Based on the 2014 Wikipedia
  snapshot, …"。
- 典型:`tw-0080-2014` Joseph Dunford——2014 快照 infobox 写 Commandant,
  账目里却混着 2005/2008 的历次任职行,smoc 答 "Assistant Commandant";
  `tw-0020-2014` Michael Arthur——账目同时有 Leeds(旧)与 UCL(新),
  smoc 取旧值;`tw-0042-2010` Têtu——gold 在账目上,smoc 答"未明确说明"。
- **与批 29-K 的判读一致**:写侧存储近乎恒真(96.7%),失分在读侧解析;
  但本场揭示了 29-K 没有的第二条:**当语料是"as-of 快照"而非"逐轮对话"时,
  抽取式建卡会用叙述日期覆盖快照日期,把时序锚点搬到错误的轴上**。
  这是账目机制对百科型语料的一条**结构性适用边界**,不是提示词能补的。
- **代价侧同样不利**:账目没有带来 token 节省(读者输入 759 vs 全文 712 tok),
  两段式协议把输出推到 423 tok(direct 64 / fullplain 19),叠加建卡摊销
  $0.0047/题,**全口径 $/题 = direct 的 2.5×、fullplain 的 3.1×**。

---

## 五、成本与时间(全部来自 usage token,list price;haiku-4-5 \$1/\$5,opus-5 \$5/\$25,embed \$0.02/M)

| 臂 | 读者 in/题 | 读者 out/题 | 判官 in/题 | 判官 out/题 | 读+判 $/题 | 全口径 $/题 | 延迟 s/题 |
|---|---|---|---|---|---|---|---|
| smoc | 759 | 423 | 94 | 67 | $0.00502 | **$0.00972** | 7.5 |
| direct | 760 | 64 | 162 | 79 | $0.00385 | $0.00386 | 4.7 |
| fullplain | 712 | 19 | 102 | 72 | $0.00310 | $0.00310 | 0.9 |
| closedbook | 45 | 103 | 214 | 94 | $0.00398 | $0.00398 | 1.7 |

- 建卡:143 店,in = 330,594 / out = 216,057 → **$1.411**,摊到 300 题 = $0.00470/题;
  平均 11.6 卡/店(共 1,656 卡,min 2 / max 25);
- direct 嵌入:记忆 77,336 tok + 查询 4,227 tok → $0.0016;
- 四臂读者+判官(300 题):$4.79;**正式轮合计 $6.20**;
- 预跑(4 店 9 题 × 4 臂,实测)$0.121 → **本轨总计 $6.32**(上限 $15 内);
- 串行等效墙钟:smoc 37.4 min / direct 23.3 min / fullplain 4.6 min /
  closedbook 8.4 min;四臂并行(并行度 4)实际约 40 min,另建卡 4 分片约 8 min。
- 自检(排除"负结论是格式伪影"这一解释):smoc 协议偏差 **0/300**(300 题全部
  给出合规 `ANSWER:` 行)、输出触顶 **0/300**(无一题达到 max_tokens=800)、
  送判文本平均 40 字符(判官看到的是干净的单句答案,不是两段式草稿);
  四臂空答 **0**;判官 1,200 次调用全部返回。

---

## 六、复现命令(逐字)

```bash
# 0) 取数(MIT 仓库,pin ef99ea0)
git clone --depth 1 https://github.com/atahanoezer/TQA.git \
    data/external/temporalwiki/repo

# 1) 建场:统一店 + 探针题集(300 题 / 143 店,seed=33)
PYTHONUTF8=1 python scripts/tw_build_arena.py \
    --repo data/external/temporalwiki/repo/full_data_filtered \
    --out-data data/external/temporalwiki_unified.json \
    --out-probe data/external/temporalwiki_probe.jsonl \
    --n 300 --seed 33

# 2) 建卡(冻结 write_phase;143 店按 uid 四分片并行,并行度 4)
PYTHONUTF8=1 python - <<'PY'
import json
d=json.load(open('data/external/temporalwiki_unified.json',encoding='utf-8'))
u=[e['uid'] for e in d]
for i in range(4):
    open(f'scratchpad/tw/uids_shard{i}.txt','w',encoding='utf-8').write("\n".join(u[i::4])+"\n")
PY
for i in 0 1 2 3; do
  PYTHONUTF8=1 python scripts/ext_build_cards.py \
      --data data/external/temporalwiki_unified.json \
      --cards-dir results/ext_cards_temporalwiki \
      --uids-file scratchpad/tw/uids_shard$i.txt &
done; wait

# 3) 四臂(并行度 4;tw_run_arm.py 只给 ClaudeJudge.judge 挂记账猴补,
#    冻结臂脚本零字节改动,判官 token 落 sidecar)
export PYTHONUTF8=1
D=data/external/temporalwiki_unified.json
Q=data/external/temporalwiki_probe.jsonl
J=results/ext_temporalwiki_judgeusage

python scripts/tw_run_arm.py --arm smoc --judge-log ${J}_smoc.jsonl -- \
  --data $D --questions $Q --cards-dir results/ext_cards_temporalwiki \
  --out results/ext_temporalwiki_smoc.jsonl --resume &
QVF_EMBED_BACKEND=openai python scripts/tw_run_arm.py --arm direct --judge-log ${J}_direct.jsonl -- \
  --data $D --questions $Q \
  --out results/ext_temporalwiki_direct.jsonl --resume &
python scripts/tw_run_arm.py --arm fullplain --judge-log ${J}_fullplain.jsonl -- \
  --reader anthropic:claude-haiku-4-5 --arm fullplain --data $D --questions $Q \
  --out results/ext_temporalwiki_fullplain.jsonl &
python scripts/tw_run_arm.py --arm closedbook --judge-log ${J}_closedbook.jsonl -- \
  --reader anthropic:claude-haiku-4-5 --arm closedbook --data $D --questions $Q \
  --out results/ext_temporalwiki_closedbook.jsonl &
wait

# 4) 统计(acc / McNemar / 簇 CI / $/题;统计三件套 import 自 bootstrap_ci.py)
PYTHONUTF8=1 python scripts/tw_arena_stats.py
```

## 七、文件清单

| 用途 | 路径 |
|---|---|
| 原始数据(MIT,pin ef99ea0,24MB,含嵌套 .git) | `data/external/temporalwiki/repo/` |
| 建场器 | `scripts/tw_build_arena.py` |
| 统一店(143 店,414KB) | `data/external/temporalwiki_unified.json` |
| 探针题集(300 题,174KB) | `data/external/temporalwiki_probe.jsonl` |
| 卡店(**建后只读**,143 文件,1.2MB) | `results/ext_cards_temporalwiki/` |
| 臂驱动器(判官记账猴补) | `scripts/tw_run_arm.py` |
| smoc 臂结果 | `results/ext_temporalwiki_smoc.jsonl` |
| direct 臂结果 | `results/ext_temporalwiki_direct.jsonl` |
| fullplain 臂结果 | `results/ext_temporalwiki_fullplain.jsonl` |
| closedbook 臂结果 | `results/ext_temporalwiki_closedbook.jsonl` |
| 判官 usage sidecar(四份) | `results/ext_temporalwiki_judgeusage_{smoc,direct,fullplain,closedbook}.jsonl` |
| 统计器 | `scripts/tw_arena_stats.py` |
| 统计原始输出 | `scratchpad/tw/stats_full.txt` |

> 仓库卫生提醒(未自行处理,交主会话决定):`data/external/temporalwiki/repo/`
> 是 24MB 的**嵌套 git 克隆**,`git add` 会触发 embedded-repository 警告。
> 建议 `.gitignore` 加 `data/external/temporalwiki/repo/` 一行,provenance 由本
> 终判记录的 commit hash `ef99ea0` 承担;派生的 unified/probe/卡店/结果均为
> 小文件,可正常入库。

---

## 八、判读与后续

1. **判据 G 判负,不升级、不入外场表。** 这是 QVF 在外场上第一例**显著为负**
   (批 17 三场为"幅度过、显著不过"的中性偏正;批 29-K 的负是完整性轴,
   正确性轴仍为正)。本场是**正确性轴上的显著负**,须如实入档。
2. **主张边界因此收紧一句**:账目机制的增益前提是"**记忆条 = 一次带时刻的
   陈述**";当记忆条是"**某时刻对全部历史的一次快照**"(百科条目、财报、
   版本化文档)时,抽取式建卡会把 31.6% 的行按叙述日期而非快照日期落锚,
   **销毁快照边界**,增益转为损失。论文里应把这条写成适用条件,而不是留给
   审稿人来发现。
3. **不建议**用"再加一句提示词"去救(批 29c 已证弱读者协议容量约一条,
   叠加即双输)。若要救,应改**写侧**:建卡时把快照日期作为不可覆盖的
   `snapshot_date` 与 `stated_date` 并列,并令账目渲染按 snapshot_date 分组。
   这是 schema 改动,属独立小批(未跑,待令)。
4. **可复用产物**:本场是目前唯一带**闭卷污染对照**的外场;闭卷 25.3 的
   逐关系分布(P6 64.3 → P108 8.1)可作为"长尾闸"设计的经验参照。
