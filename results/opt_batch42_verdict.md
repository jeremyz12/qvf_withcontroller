# 批 42 判决:扩大冻结保留集(WikiState-holdout v2,+40 链 → 池化 80 链)

预注册出处:`results/opt_batch42_prereg.md`(2026-09-04,在任何读者臂开跑之前写定)。
本文件是实跑结果;语料构造在读者臂开跑前已完成并冻结,构造实况记入 §一,
实跑结果记入 §二起。

---

## 判决(先判决,后数字)

> **三条假设全部被证实。** 新 40 链上 smoc − direct = **+40.00pp**(40 链簇 95% CI
> [+31.25, +48.12],下界远离零)—— **H1 通过**。池化 80 链(既有 40 链保留集 v1 +
> 本批新 40 链)头条 smoc − direct = **+41.56pp**,与主场单店头条 89.06 vs 47.57
> (+41.49pp)相差仅 **0.07pp**,落在预注册 ±5pp 容差内 —— **H2 通过**。新 40 链上
> plainctx(72.50)点估严格介于 direct(50.62)与 smoc(90.62)之间,且与两者的簇 CI
> 均不重叠 —— **H3 通过**。"结构总价不是开发场过拟合"这条主张现在站在 80 链、
> 640 题的样本上,而不再只是 40 链。

---

## 一、语料构造实况(跑前完成,冻结)

### 1. 探索性供给核验(在预注册中已记录,此处复核)

排除集(144 主链 + L1/L2 + 既有 40 链保留集 v1)= **658 QID**。TARGET=60 试抓,
四个属性**全部**在排除集下轻松触顶:

| 属性 | 探索性候选(排除 658 QID 后) | 参数泄漏闸首轮(KEEP_TARGET=10,length-sorted 前 30) | 参数泄漏闸复跑(unlimited,全 56/56/30/45 验证池) |
|---|---|---|---|
| P108(雇主) | 60/60 | 10 kept / 12 probed / 45 validated | 45 kept / 45 probed |
| P39(任职) | 60/60 | 10 kept / 13 probed / 30 validated | 28 kept / 30 probed(2 drop) |
| P54(队籍) | 60/60 | 10 kept / 12 probed / 56 validated | 56 kept / 56 probed |
| P551(居住地) | 60/60 | 10 kept / 12 probed / 56 validated | 56 kept / 56 probed |

**一处构造中的返工(如实记录,计入成本)**:首轮 build 用 `KEEP_TARGET=10` 只探测
length-sorted 候选池的前 30 条(按链长升序),在高保留率(≈85-95%)下probe 在
第 10-13 条附近就已达标提前停止——这使四个属性的保留池**几乎全部是链长 3**
(P108/P39/P551 首轮池:`{3: 10}`,只有 P54 因原始候选本身长链密集而混入部分 4),
无法满足链长匹配算法(目标直方图 3:24/4:9/5:3/6:2/7:1/8:1)。发现后**重跑 build
为 unlimited**(探测全部 56/56/30/45 条验证候选),四属性保留池随即覆盖 3-8 全部
链长档位(如 P54:`{3:4,4:8,5:9,6:10,7:7,8:18}`)。此次返工多花判官成本 **$0.657**
(首轮 40,602 in / 18,165 out token,opus-5 计价),记入 §三成本表,不影响任何过滤
规则或最终语料内容(首轮产出的 10-链子集被完全丢弃重选)。

### 2. 链长匹配定选(`scripts/b42_holdout_select_v1.py`)

槽位配额采用**均衡配额 10/10/10/10**(与批 33-C 保留集 v1 的比例配额 14/12/11/3
不同,理由见 prereg:双重排除后四个属性供给均充足,不必再按开发场比例压缩
稀缺属性)。链长匹配算法(目标直方图 = 开发场 144 链比例最大余数法缩放到 40)
在扩充后的池上**精确可行**:

| 链长 | 目标(开发场比例缩放) | 批 42 达成 | 批 33-C 保留集 v1 达成 |
|---|---|---|---|
| 3 | 24 | **24** | 23 |
| 4 | 9 | **9** | 10 |
| 5 | 3 | **3** | 3 |
| 6 | 2 | **2** | 2 |
| 7 | 1 | **1** | 1 |
| 8 | 1 | **1** | 1 |

`feasible_exact_match = true`(批 33-C 保留集 v1 当年因一条链被模型拒答,3/4 档各
差 1 格换成同槽位备胎;批 42 无此问题,逐格精确匹配)。

### 3. 渲染、双闸、零交集(`scripts/b42_holdout_render_v1.py` / `b42_holdout_merge_v1.py`)

- 渲染器:claude-opus-5,同 `RenderedState` 契约、同逐字锚点校验、同日期铺法,
  **新种子 SEED=20260904**(批 33-C 保留集 v1 为 20260902,已记录);
- 填充干扰:复用同一份已审计填充池 `data/filler_pool_v23.json`(1,100 会话,
  剔 45 CONFIRMED + 复扫再剔 5 → 干净池 1,050),每链 30 个,按 uid 播种;
- 四个分槽位分片各自锚点校验:P108/P39/P54/P551 均 **0 锚点违例、0 污染残留**;
- 合并后闸1 锚点 **150/150** 逐字完好,闸2 污染残留 **0**;
- **双重零交集核验(硬性判据)**:与 144 主链 + L1/L2 + 既有 40 链保留集 v1 的 QID
  交集 = **0**(`[]`);
- 规模:**40 链 / 160 题**(四型各 40),槽位 employer 10 / position 10 / team 10 /
  residence 10,每链会话数均值 **33.75**(30 填充 + 链段)。

出题(`scripts/b42_holdout_questions_v1.py`)分布判据:change_count 众数占比
**30.0%**、count_before **22.5%**(闸 ≤35% 通过);longest_tenure 链尾命中
**27.5%**(闸 >10% 通过,批 33-C 保留集 v1 为 35.0%)。

产物与校验和:
- `data/wikistate_holdout2_v1.json` sha256 `f764696c93516b9a8c6375a78dedef8e2a378596abd8a80a1c90d37f62d748e5`
- `data/wsc_holdout2_v1.jsonl` sha256 `acd5d19a7177d97510ae02bdd46de0a7292829e38a49118c1936a7ee40e691f1`
- `data/wsc_holdout2_v1.keymap.json`、`data/holdout2_selection_v1.json`
- 中间档:`data/holdout2_candidates_<P>.json`、`data/holdout2_items_<P>.json`、
  `data/holdout2_itempool_<P>.json`、`data/holdout2_part_<P>.json`
- 卡片店(只读):`results/wt_cards_holdout2/`(40 个 uid,新目录,`QVF_CARD_OWNER_GATE=0`,
  不设其余任何 `QVF_CARD_*` 环境变量 —— 与批 33-C 保留集 v1、与开发场 v2.4 头条同一
  建店配置,建后只读、只建一次)

**语料冻结**:第一次读者臂(smoc)已于本批唯一一次跑完;语料与题集自此未再改动。

---

## 二、三臂结果:新 40 链(160 题)

| 臂 | 准确率 | Wilson 95% CI(题级,n=160) | 40 链簇自助 95% CI | 判官侧 |
|---|---|---|---|---|
| **smoc(账目)** | **90.62** | [85.11, 94.24] | [85.00, 95.62] | ClaudeJudge/opus-5 |
| **direct(top-10,OpenAI 嵌入)** | **50.62** | [42.95, 58.27] | [43.12, 58.13] | 同上 |
| **plainctx(整库原文直读,b36 框定)** | **72.50** | [65.11, 78.83] | [64.38, 80.00] | 同上 |

逐题型(新 40 链):

| 题型 | smoc | direct | plainctx |
|---|---|---|---|
| change_count | 90.00 (36/40) | 27.50 (11/40) | 52.50 (21/40) |
| count_before | 85.00 (34/40) | 47.50 (19/40) | 87.50 (35/40) |
| longest_tenure | 87.50 (35/40) | 40.00 (16/40) | 57.50 (23/40) |
| first_vs_last | 100.00 (40/40) | 87.50 (35/40) | 92.50 (37/40) |

配对对比(题级 McNemar + 40 链簇自助,新 40 链):

| 对比 | Δ | b/c | McNemar p | 链级符号检验 | 40 链簇 95% CI |
|---|---|---|---|---|---|
| **smoc − direct(H1)** | **+40.00pp** | 6/70 | 6.31e-15 | 34W/2L/4T,p=1.94e-08 | **[+31.25, +48.12]** |
| smoc − plainctx | +18.12pp | 11/40 | 5.7e-05 | 24W/4L/12T,p=1.8e-04 | [+8.12, +27.50] |
| plainctx − direct | +21.88pp | 14/49 | 1.11e-05 | 27W/4L/9T,p=3.4e-05 | [+12.50, +30.63] |

---

## 三、池化 80 链(既有 40 链保留集 v1 + 批 42 新 40 链)

**方法论边界(严格遵守 prereg 声明)**:池化仅覆盖 smoc 与 direct 两臂 ——
两批用的是**逐字节相同**的臂位实现(`lb_reader_arm.py`/`b42_lb_reader_arm.py`,
仅判官 token 落盘方式不同,不影响读者调用)。第三臂**不池化**:批 33-C 保留集
v1 的 fullplain 用 `repro_batch3.PLAIN_PROMPT`("Answer ... Reply with only the
answer.");批 42 的 plainctx 用 `b36_plain_fullctx.py` 的框定("You are a helpful
assistant." + 无任务框定、无长度约束)。两者是不同提示词条件,混池会把"提示词
效应"误记成"批次效应",故第三臂只在各自批次内报告(新 40 链见 §二;既有 40 链
见批 33-C 判决文件)。

| 臂 | 池化 80 链 320 题准确率 | Wilson 95% CI | 80 链簇自助 95% CI |
|---|---|---|---|
| **smoc** | **92.81** | [89.45, 95.16] | [89.06, 95.94] |
| **direct** | **51.25** | [45.79, 56.68] | [45.94, 56.25] |

逐题型(池化 80 链):

| 题型 | smoc | direct |
|---|---|---|
| change_count | 93.75 (75/80) | 28.75 (23/80) |
| count_before | 90.00 (72/80) | 42.50 (34/80) |
| longest_tenure | 87.50 (70/80) | 45.00 (36/80) |
| first_vs_last | 100.00 (80/80) | 88.75 (71/80) |

**H2 头条对比**:

| 对比 | Δ | b/c | McNemar p | 链级符号检验 | 80 链簇 95% CI |
|---|---|---|---|---|---|
| **pooled80 smoc − direct** | **+41.56pp** | 10/143 | 2.7e-31 | 68W/3L/9T,p=5.06e-17 | **[+35.62, +47.50]** |

对照口径:主场单店头条(144 主链,无闸/最新单店)smoc 89.06 vs direct 47.57,
Δ=+41.49pp,144 链簇 CI [+36.5,+46.4](`results/ladder_decontamination_20260902.md:106`,
任务书指定口径,未重新推导)。**池化 80 链头条 41.56pp 与主场 41.49pp 相差
0.07pp**,80 链簇 CI [+35.62,+47.50] 与主场 144 链簇 CI [+36.5,+46.4] 大幅重叠。

---

## 四、三条假设逐条判读

- **H1(新 40 链 smoc−direct ≥+30pp 且簇 CI 下界>0)—— 通过**。
  点估 +40.00pp(远超 +30pp 门槛),簇 CI [+31.25,+48.12] 下界为正、远离零;
  b/c=6/70 说明差异由 70 题"direct 错、smoc 对"驱动,反向仅 6 题;链级 34 胜 2 负 4 平。
- **H2(池化 80 链头条与主场 89.06 vs 47.57 相差 ≤5pp)—— 通过**。
  池化 Δ=+41.56pp,目标区间 [+36.49,+46.49],点估落在区间正中央,偏差仅 0.07pp;
  这是本批最强的单条结论 —— 40 条**全新**链(与主场 144 链、与既有 40 链保留集
  均零交集)贡献的 smoc−direct 头条,与主场数字几乎逐点重合。
- **H3(新 40 链 plainctx 介于 direct 与 smoc 之间)—— 通过,且是清晰分层而非模糊地带**。
  点估 50.62 < 72.50 < 90.62,三者两两簇 CI **互不重叠**(plainctx 与 direct:
  [64.38,80.00] vs [43.12,58.13];plainctx 与 smoc:[64.38,80.00] vs [85.00,95.62]),
  即"账目 > 全文裸读(无框定)> 检索直读"这一排序在新语料上是统计显著的三层分离,
  不只是点估恰好落在中间。

**与批 33-C 保留集 v1 的比较(锦上添花,不是判据)**:新 40 链的 smoc(90.62)、
direct(50.62)与既有 40 链保留集 v1 的 smoc(95.00)、direct(51.88)几乎逐点相同
(Δ 分别为 −4.38pp、−1.26pp,均落在彼此的簇 CI 内);plainctx(72.50)与 v1 的
fullplain(71.88)点估也几乎相同(Δ+0.62pp)——**尽管两者是不同的提示词条件**,
数字仍然接近,这本身是一条值得记录的观察,但不构成 H2/H3 之外的额外判据
(方法论不同,不作为"迁移"证据引用)。

---

## 五、成本与延迟(读者/判官侧 token 全部实测;渲染/嵌入侧沿用批 33-C 估算口径)

### 1. 建店 + 三臂读者(计入 $22 预算上限)

| 项 | 输入 tok | 输出 tok | $ | 口径 |
|---|---|---|---|---|
| 建店(haiku,40 链一次,4 分片并发) | 853,057 | 326,676 | **1.9891** | 实测 |
| smoc 读者(haiku-4.5) | 477,532 | 76,350 | **0.6874** | 实测 |
| direct 读者(OpenAI 嵌入 + haiku 读) | 138,434 | 13,620 | **0.1652** | 实测 |
| plainctx 读者(haiku-4.5) | 2,180,308 | 30,448 | **1.8660** | 实测 |
| **建店+读者合计** | | | **4.7077** | 实测,**$22 上限内**(余量 $17.29) |

### 2. 判官(任务书口径:另计,不设同一上限,逐笔实测)

| 项 | 输入 tok | 输出 tok | $ | 口径 |
|---|---|---|---|---|
| 参数泄漏闸判官(首轮 KEEP_TARGET=10,后弃) | 40,602 | 18,165 | 0.6571 | 实测,**返工浪费**(见 §一 1) |
| 参数泄漏闸判官(unlimited 复跑,采用) | 155,120 | 71,975 | 2.5749 | 实测 |
| 参数泄漏闸判官合计 | 195,722 | 90,140 | **3.2321** | 实测 |
| 三臂判官(smoc+direct+plainctx,新 40 链) | 101,465 | 30,618 | **1.2728** | 实测(本批已修复 `lb_reader_arm.py` 判官 token 不落盘的遗留项) |
| **判官合计** | | | **4.5049** | 实测 |

### 3. 未计价(沿用批 33-C 估算口径,未实测)

| 项 | 估算 | 说明 |
|---|---|---|
| 会话渲染(opus-5,150 次状态抽取调用) | ≈$2.34 | 按批 33-C 同款单价估算(渲染脚本未落盘 usage,继承的既有限制,本批未修) |
| direct 嵌入(text-embedding-3-small) | ≈$0.01 | 量级与批 33-C 保留集 v1 相当,可忽略 |

### 4. 汇总

批 42 全部实测 + 估算总成本 ≈ **$4.71(建店+读者,实测)+ $4.50(判官,实测)+
$2.35(渲染+嵌入,估算)≈ $11.56**,与批 33-C 保留集 v1 的 ≈$11.7 同一量级。
**建店+读者侧 $22 上限未超**(实际用量 $4.71,余量 $17.29);判官侧按任务书要求
另计、未设上限,已逐笔实测。

### 5. 延迟

| 臂 | 平均延迟 |
|---|---|
| smoc | 5.60s |
| direct | 1.73s |
| plainctx | 3.05s |

（本批与其他并行进程共享同一 API 配额，延迟数不作为干净时延测量引用，口径与批 33-C 一致。）

---

## 六、偏差与局限(如实记录)

1. **槽位配额从比例配额改为均衡配额**:批 33-C 保留集 v1 用 14/12/11/3(按开发场
   槽位比例缩放),批 42 用 **10/10/10/10**——预注册已声明并给出理由(双重排除后
   供给核验显示四属性均可轻松达到 60 候选),已按 prereg 判据执行,非事后调整。
2. **build 步返工**:首轮 `KEEP_TARGET=10` 只探测了 length-sorted 候选池前 30 条,
   在高保留率下过早停止,导致保留池几乎只有链长 3,链长匹配算法在此池上不可行。
   发现后重跑为 unlimited(探测全部 56/56/30/45 条),问题解决,但多花判官成本
   $0.657(已计入 §五)。此返工**不影响**最终语料的过滤规则或双闸判据,只是构造
   过程中的一次工程调整,产出的 10-链子集已完全丢弃。
3. **第三臂方法论不可跨批池化**:批 42 的 plainctx(b36 框定)与批 33-C 保留集 v1
   的 fullplain(repro_batch3 PLAIN_PROMPT 框定)是不同的提示词条件,H2 池化只
   覆盖 smoc/direct;第三臂的"新旧几乎相同"(72.50 vs 71.88)只作观察记录,不当
   作迁移证据引用(见 §四 末段)。
4. **渲染与嵌入侧成本仍为估算**:`b42_holdout_render_v1.py`(继承自
   `holdout_render_v1.py`)与检索器均未捕获 API usage,该项估算口径与批 33-C
   保留集 v1 相同,本批未修复(非本批引入的新缺陷,是既有生成器的既有限制)。
5. **单读者单判官**:仍只有 haiku-4.5 读者 + opus-5 判官一组,与既有全部批次一致。
6. **residence(P551)供给核验的意义**:批 33-C 保留集 v1 曾把 P551 配额压到 3,
   理由是"候选稀缺";批 42 在双重排除下同样轻松找到 60 个候选、10 个保留 ——
   说明 v1 的稀缺是**局部耗尽**(v1 自己挑走了最容易发现的那批),不是 P551 属性
   本身在 Wikidata 上稀缺。此观察记入本文件供后续扩容(批 43+)参考,不改动
   v1 的既有判决。
7. **人工核验**:本批零人工审阅(与批 33-C 保留集 v1、与 144 主链的自动化流程
   一致);20% 抽样算 κ 的步骤仍未做。

---

## 七、复现命令(逐字,与实跑一致)

```bash
# 1 候选发现(排除集含既有 40 链保留集 v1)
PYTHONUTF8=1 python -u scripts/b42_holdout_scrape_v1.py P551 60 8000
PYTHONUTF8=1 python -u scripts/b42_holdout_scrape_v1.py P54  60 6000
PYTHONUTF8=1 python -u scripts/b42_holdout_scrape_v1.py P39  60 6000
PYTHONUTF8=1 python -u scripts/b42_holdout_scrape_v1.py P108 60 4000
# 2 标签解析 + 链清洗 + 参数泄漏闸(unlimited,第二参数=0)
PYTHONUTF8=1 python -u scripts/b42_holdout_build_v1.py P551 0
PYTHONUTF8=1 python -u scripts/b42_holdout_build_v1.py P54  0
PYTHONUTF8=1 python -u scripts/b42_holdout_build_v1.py P39  0
PYTHONUTF8=1 python -u scripts/b42_holdout_build_v1.py P108 0
# 2.5 合并条目池 + 链长匹配定选(配额 10/10/10/10)
PYTHONUTF8=1 python -u scripts/b42_holdout_select_v1.py
# 3 渲染(SEED=20260904,分槽位四进程)
QVF_HOLDOUT_QUOTA='{"P108":10}' QVF_HOLDOUT_OUT='data/holdout2_part_P108.json' PYTHONUTF8=1 python -u scripts/b42_holdout_render_v1.py
QVF_HOLDOUT_QUOTA='{"P39":10}'  QVF_HOLDOUT_OUT='data/holdout2_part_P39.json'  PYTHONUTF8=1 python -u scripts/b42_holdout_render_v1.py
QVF_HOLDOUT_QUOTA='{"P54":10}'  QVF_HOLDOUT_OUT='data/holdout2_part_P54.json'  PYTHONUTF8=1 python -u scripts/b42_holdout_render_v1.py
QVF_HOLDOUT_QUOTA='{"P551":10}' QVF_HOLDOUT_OUT='data/holdout2_part_P551.json' PYTHONUTF8=1 python -u scripts/b42_holdout_render_v1.py
# 4 合并 + 双闸 + 双重零交集核验
PYTHONUTF8=1 python -u scripts/b42_holdout_merge_v1.py
# 5 出题
PYTHONUTF8=1 python -u scripts/b42_holdout_questions_v1.py
# 6 建店(同批 33-C 保留集配置)
QVF_CARD_OWNER_GATE=0 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype.py --phase write \
  --data data/wikistate_holdout2_v1.json --cards-dir results/wt_cards_holdout2 --uids "<40 uids>"
# 7 三臂
PYTHONUTF8=1 python -u scripts/b42_lb_reader_arm.py --reader anthropic:claude-haiku-4-5 --arm smoc \
  --data data/wikistate_holdout2_v1.json --questions data/wsc_holdout2_v1.jsonl \
  --cards-dir results/wt_cards_holdout2 --out results/b42_smoc_holdout2.jsonl
QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python -u scripts/b42_lb_reader_arm.py --reader anthropic:claude-haiku-4-5 --arm direct \
  --data data/wikistate_holdout2_v1.json --questions data/wsc_holdout2_v1.jsonl \
  --cards-dir results/wt_cards_holdout2 --out results/b42_direct_holdout2.jsonl
PYTHONUTF8=1 python -u scripts/b36_plain_fullctx.py --reader anthropic:claude-haiku-4-5 \
  --data data/wikistate_holdout2_v1.json --questions data/wsc_holdout2_v1.jsonl \
  --out results/b42_plainctx_holdout2.jsonl --workers 4 --budget 20
# 8 统计
PYTHONUTF8=1 python -u scripts/b42_stats.py | tee results/b42_score_out.txt
```

---

## 八、文件清单

| 类 | 路径 |
|---|---|
| 预注册 | `results/opt_batch42_prereg.md` |
| 语料(冻结) | `data/wikistate_holdout2_v1.json`(sha256 `f764696c…f62d748e5`) |
| 题集(冻结) | `data/wsc_holdout2_v1.jsonl`(sha256 `acd5d19a…e40e691f1`) |
| 答案键/定选记录 | `data/wsc_holdout2_v1.keymap.json`、`data/holdout2_selection_v1.json` |
| 中间档 | `data/holdout2_candidates_<P>.json`、`holdout2_items_<P>.json`、`holdout2_itempool_<P>.json`、`holdout2_part_<P>.json` |
| 卡片店(只读) | `results/wt_cards_holdout2/`(40 uid) |
| 三臂结果 | `results/b42_smoc_holdout2.jsonl`、`results/b42_direct_holdout2.jsonl`、`results/b42_plainctx_holdout2.jsonl` |
| 统计 | `results/b42_score_out.txt`、`results/b42_stats.json` |
| 生成器脚本 | `scripts/b42_holdout_scrape_v1.py`、`b42_holdout_build_v1.py`、`b42_holdout_select_v1.py`、`b42_holdout_render_v1.py`、`b42_holdout_merge_v1.py`、`b42_holdout_questions_v1.py`、`b42_lb_reader_arm.py`、`b42_stats.py`(+ 直接复用 `scripts/b36_plain_fullctx.py`、`scripts/wt_qvf_prototype.py`) |

## 九、关掉了什么、没关掉什么

**关掉**:
1. "结构总价的未过拟合判决只站在 40 链上"——现在是 80 链、640 题,H1/H2/H3 全过;
2. "池化头条会不会被新语料的难度差拉偏"——池化 Δ=+41.56pp 与主场 +41.49pp 只差
   0.07pp,新 40 链单独的 Δ 也是 +40.00pp,两个独立估计互相印证;
3. "账目 vs 全文裸读(不同提示词条件下)的分层是否稳健"——H3 在新语料、新提示词
   条件下重新验证,三层分离统计显著(簇 CI 两两不重叠);
4. "判官侧成本只能估算"(批 33-C 保留集 v1 §二 9 遗留项)——本批三臂判官成本
   已逐笔实测($1.2728),脚本改动已记入文件清单。

**没关掉**(与批 33-C 保留集 v1 相同的局限,未在本批解决):
1. 渲染/嵌入侧 token 仍为估算,非实测;
2. 单读者(haiku-4.5)单判官(opus-5)组合,未做交叉模型核验;
3. 零人工审阅,20% 抽样 κ 未做;
4. 第三臂(plainctx)只在批 42 内部有效,不能与批 33-C 的 fullplain 数字换算池化。
