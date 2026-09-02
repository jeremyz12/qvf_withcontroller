# 批 33-A 终判:单语料冻结重建(v2.4 语料 × v45/v45g 店,576 题一次跑)

日期:2026-09-02。预注册:`results/opt_batch33_prereg.md` §33-A。
读者 `anthropic:claude-haiku-4-5`(temperature=0),判官 `ClaudeJudge`(`claude-opus-5`,冻结),
direct 臂 `QVF_EMBED_BACKEND=openai`(text-embedding-3-small)。

---

## 一、头条(A4 单句)

> **WikiState v2 576 题 / 144 链,语料 v2.4,店 v45 建于 2026-09-02,单次跑,haiku-4.5:
> smoc 89.06 vs direct 47.57,差 +41.49。**

配对 McNemar b/c = 22/261,p = 4.7e-53;144 链簇自助 95% CI **[+36.63, +46.35]pp**;
链级符号检验 124W/7L/13T,p = 8.7e-29。

与 09-01 拼接口径(smoc 90.45 / direct 48.26,结构总价 +42.19)同向且量级一致:
本次一次跑得 **+41.49**,差 0.70pp,落在簇 CI 内 —— 拼接数**不需要撤回**,
但从此可以用"一语料一店一跑"的单句陈述替代它。

---

## 二、判据判定(跑前写死,逐条如实)

| 判据 | 内容 | 结果 |
|---|---|---|
| **A1** | smoc(v45) − direct ≥ 35pp 且 smoc ≥ 88 | **通过**。+41.49 ≥ 35;89.06 ≥ 88(双条件均满足,非临界) |
| **A2** | 六段阶梯每段方向与 v2.0 一致 | **通过(须在键控 regime 判)**。四主段 + 两旁段方向全部 MATCH;详见 §四 |
| **A3** | smoc(v45g) vs smoc(v45) 簇级 TOST ±3pp | **不通过**。Δ = **−3.47pp**,p = 0.0422,簇 CI [−7.81, +0.69];±2/±3/±5pp 三档 TOST 全 FAIL |
| **A4** | 头条以"一语料一店一跑"单句陈述,六个"结构总价"值收敛为一 | **部分通过**。头条单句成立(§一);但中三段被迫用派生店 v45k,故"一店"对中三段有例外,须照实标注 |

**A3 是本批最重要的否定结果**:所有权闸(OWNER_GATE=1)在**干净语料上有真实代价**,
不是"等价、可自由采用"。批 32′ 曾建议把 gate 纳入冻结配置,本结果反对该建议 ——
除非另有理由(如隐私/越权抑制),否则默认应保持 gate=0。

---

## 三、全表(576 题 / 144 链,去重后)

| 臂 | n | 本批 v2.4×v45 | v2.0 存档 | 差 | 拼接 v2.4 |
|---|---|---|---|---|---|
| direct | 576 | **47.57** | 48.61 | −1.04(n.s. p=0.451) | 48.26 |
| filter(原始 v45) | 576 | 58.68 | 62.67 | −3.99 | — |
| usability(原始 v45) | 576 | 60.59 | 65.62 | −5.03 | — |
| compile(原始 v45) | 576 | 77.78 | 75.87 | +1.91 | — |
| smw | 576 | **85.59** | 81.25 | +4.34(p=0.0046) | — |
| smwplain | 576 | 53.47 | 52.26 | +1.22(n.s.) | — |
| 无结构摘要 | 576 | 57.12 | 52.78 | +4.34(p=0.041) | — |
| **smoc(v45)** | 576 | **89.06** | 82.64 | **+6.42**(p=3.4e-04) | 90.45 |
| **smoc(v45g)** | 576 | **85.59** | 82.64 | +2.95(n.s. p=0.125) | — |
| filter(v45k 派生) | 576 | **65.62** | 62.67 | +2.95(n.s.) | — |
| usability(v45k 派生) | 576 | **66.32** | 65.62 | +0.69(n.s.) | — |
| compile(v45k 派生) | 576 | **79.69** | 75.87 | +3.82(p=0.069) | — |

清洗税(v2.0 存档 → 本批)在 smoc 上 **+6.42**,与批 31 的 +7.81 同向;
direct **−1.04 且不显著**(p=0.451,簇 CI [−2.95,+0.87])——"清洗对直读零净变"第三次复现。

---

## 四、阶梯逐段配对(A2)

### 4.1 键控 regime(v45k 派生店,**A2 在此判**)

| 段 | 本批 | b/c | McNemar p | 簇 95% CI | v2.0 同段 | 方向 |
|---|---|---|---|---|---|---|
| 选择 direct→filter | +18.06 | 65/169 | 7.5e-12 | [+11.81,+24.13] | +14.06 | MATCH |
| 认证 filter→usability | +0.69 | 31/35 | 0.712 | [−2.08,+3.47] | +2.95 | MATCH(方向一致但**不显著**) |
| 计算 usability→compile | +13.37 | 12/89 | 1.1e-15 | [+9.90,+16.84] | +10.24 | MATCH |
| 账目+协议 compile→smoc | +9.38 | 35/89 | 1.3e-06 | [+4.34,+14.58] | +6.77 | MATCH |
| [旁] compile→smw | +7.81 | 48/93 | 1.9e-04 | [+2.43,+13.37] | +5.38 | MATCH |
| [旁] smw→smoc | +3.47 | 46/66 | 0.072 | [−0.87,+7.64] | +1.39 | MATCH |

**六段方向全部与 v2.0 一致 → A2 通过。** 唯一须加限定词的是**认证段**:
v2.0 为 +2.95(p=0.036,族校正后仅【方向性】),本批为 +0.69(p=0.712)——
方向保住,**量级被压到统计不可分**。09-02 去污染文档曾预测认证段在干净子集上升到 +5.73;
本批(全库 v2.4 + 新建卡器)未复现该升幅。认证段是整条阶梯**最脆弱的一段**,
论文不应把它作为独立卖点。

### 4.2 原始 v45 regime(无键回退,**不可与 v2.0 存档比绝对值**)

| 段 | 本批 | McNemar p | v2.0 同段 | 方向 |
|---|---|---|---|---|
| 选择 direct→filter | +11.11 | 2.7e-05 | +14.06 | MATCH |
| 认证 filter→usability | +1.91 | 0.222 | +2.95 | MATCH |
| 计算 usability→compile | +17.19 | 3.1e-23 | +10.24 | MATCH |
| 账目+协议 compile→smoc | +11.28 | 1.7e-09 | +6.77 | MATCH |

方向同样六段全 MATCH —— **A2 的结论不依赖于用哪个 regime 判**,这是稳健的。

### 4.3 两个"结构总价"参照臂

- smwplain→smw(协议价)= **+32.12**(p=2.4e-41),v2.0 +28.99,MATCH;
- 无结构摘要→smoc = **+31.94**(p=6.1e-37),v2.0 +29.86,MATCH。
  摘要臂 57.12 与 smoc 89.06 的 32 点差,是"压缩 ≠ 结构"最直接的一条。

---

## 五、A3:所有权闸(v45g)的真实代价

### smoc(v45) → smoc(v45g),576 题 / 144 链

- Δ = **−3.47pp**(89.06 → 85.59);b/c = **54/34**,McNemar **p = 0.0422**;
- 链级符号检验 21W/32L/91T,p = 0.169;
- 144 链簇自助 95% CI **[−7.81, +0.69]**;
- TOST:±2pp **FAIL**、±3pp **FAIL**、±5pp **FAIL**(90% CI [−7.12, 0.00] 三档都伸出边界)。

**判读**:题级 McNemar 显著为负,但链级符号检验不显著、簇 CI 轻微跨零 ——
即"闸有代价"这一判断在**题级稳健、链级证据较弱**。无论如何,
**±3pp 等价性无法主张**,A3 判 FAIL。逐题型看,损失集中在
longest_tenure(89.6→84.0,−5.6)与 count_before(86.8→81.9,−4.9)。

机制侧佐证:v45g 比 v45 少 **30.6%** 记录(5,754 vs 8,288),
账目读取量随之从 2,942 降到 2,110 输入 tok(−28%)。
**闸省了 28% 的读取成本,换来 3.47pp 准确率** —— 这是一条可以写进论文的成本/精度权衡曲线点,
但它不是"免费的安全性"。

---

## 六、逐题型(576 题,每型 144)

| 臂 | change_count | count_before | first_vs_last | longest_tenure |
|---|---|---|---|---|
| direct | 35.4 | 42.4 | 79.9 | 32.6 |
| filter(v45) | 54.2 | 71.5 | 75.7 | 33.3 |
| usability(v45) | 58.3 | 70.8 | 75.7 | 37.5 |
| compile(v45) | 65.3 | 79.9 | 86.8 | 79.2 |
| smw | 64.6 | 91.0 | **99.3** | 87.5 |
| smwplain | 31.9 | 67.4 | 75.7 | 38.9 |
| 无结构摘要 | 49.3 | 52.1 | 87.5 | 39.6 |
| **smoc(v45)** | **85.4** | 86.8 | 94.4 | **89.6** |
| smoc(v45g) | 82.6 | 81.9 | 93.8 | 84.0 |
| filter(v45k) | 59.0 | 75.0 | 89.6 | 38.9 |
| usability(v45k) | 61.8 | 72.9 | 88.9 | 41.7 |
| compile(v45k) | 65.3 | 79.2 | 92.4 | 81.9 |

两处值得记的现象:
1. **smw 在 first_vs_last 上 99.3**,高于 smoc 的 94.4 —— 读原文在"首尾对比"型上仍有上界优势;
   但 smw 读 13,920 tok/题,smoc 只读 2,942,单价 3.0×。
2. **longest_tenure 是账目的护城河**:smoc 89.6 vs compile(v45k)81.9 vs filter 38.9 —— 时长类最吃"可计数账目"。

---

## 七、成本 / token / 延迟(读者侧;haiku $0.80/M in、$4.00/M out)

| 臂 | 均 in tok | 均 out tok | $/题 | 576 题 $ | 中位延迟 s |
|---|---|---|---|---|---|
| direct | 877 | 86 | $0.00105 | $0.60 | 1.55 |
| filter(v45) | 2,139 | 104 | $0.00213 | $1.23 | 5.55 |
| usability(v45) | 2,282 | 108 | $0.00226 | $1.30 | 5.51 |
| compile(v45) | 2,305 | 97 | $0.00223 | $1.29 | 5.37 |
| smw | 13,920 | 457 | $0.01296 | $7.47 | 7.88 |
| smwplain | 13,671 | 135 | $0.01148 | $6.61 | 5.46 |
| 无结构摘要 | 2,454 | 92 | $0.00233 | $1.34 | 4.94 |
| **smoc(v45)** | 2,942 | 479 | $0.00427 | $2.46 | 4.86 |
| smoc(v45g) | 2,110 | 466 | $0.00355 | $2.05 | 4.79 |

**smoc vs smw**:准确率 +3.47(89.06 vs 85.59),读取量 **0.21×**,$/题 **0.33×**,延迟 0.62× —— 账目在四项上全胜。
**smoc vs direct**:准确率 +41.49,$/题 4.1× —— 结构价的单价是每题约 0.32 美分。

**本批总花费**:读者侧 in 31,843,839 / out 1,492,181 tok = **$31.44**(含重复写的作废行);
判官 8,378 次调用 × 实测 97 in / 38 out @ opus-5($5/$25 per M)= **$12.02**;
**合计 ≈ $43.5**,在 $60 上限内。

---

## 八、关键发现:v45 建卡器丢了 `slot_class` / `owner`(schema 回归)

这是本批**计划外但最有价值**的发现,已用隔离实验坐实。

### 8.1 事实

| 店 | `owner` 覆盖 | `slot_class` 覆盖 |
|---|---|---|
| wt_cards_v42(v2.0 阶梯所用) | 100% | 100% |
| **wt_cards_v45 / v45g** | **0%** | **0%** |

`complex_query_arm._select_pool` 的键控路径以 `(owner, slot_class)` 分组;
且 `QVF_OPEN_SLOT` / `QVF_OPEN_KEYS` 的"空池救援"**开头就要求 `slot_class` 存在**
(`keyed = [r for r in recs if r.get("slot_class")]; if not keyed: return pool`)。
故在 v45 上:**中三段整段走无键回退,且两个开放旗标是彻底的 no-op。**

**$0 证明**:v45 上 `_select_pool` 在旗标 OFF / ON 两种设定下返回**逐字节相同**
(SUM 1484,签名 −3389701664031023489,两次一致)。
→ 用 `QVF_OPEN_SLOT=1 QVF_OPEN_KEYS=1` 重跑**不会改变任何一行**,该方案已排除,未执行。

### 8.2 隔离探针(144 道 first_vs_last,三格)

| 格 | 语料 | 店 | fvl 准确率 | 均 evidence_n |
|---|---|---|---|---|
| v2.0 存档 | v2.0 | v42(有 slot_class) | 92.36 | 4.13 |
| **本批探针** | **v2.4** | v42(有 slot_class) | **92.36** | 4.13 |
| 本批正跑 | v2.4 | **v45(无 slot_class)** | **75.69** | 2.92 |

- **语料效应 = +0.00pp(逐题完全一致)**;
- **店/schema 效应 = −16.67pp**(b/c = 32/8,p = 1.8e-04,簇 CI [−25.00, −8.33])。

即:中三段相对 v2.0 存档的下滑,**100% 归因于建卡器 schema 回归,0% 归因于语料清洗**。
这条同时给了"清洗不伤检索/选择"一个额外的独立证据。

### 8.3 派生店 v45k 的修复验证

`scripts/b33A_backfill_slot_class.py` 用**项目自带的 `SLOT_ALIASES` 表**(最长别名优先)
把 v45 的自由 `slot` 名机械映射回 slot_class,`owner` 由 `entity` 抄写;
产物写入**新目录** `results/wt_cards_v45k`,v45 原店全程只读。
映射表与统计存 `results/b33A_v45k_mapping.json`:8,288 条记录,
**18.0% 命中七个闭集类**(position 436 / device 312 / residence 247 / employer 150 /
team 149 / location 119 / relationship 81),**82.0% 记为 `other:<slot>`**(与 v42 的 other:* 同写法;
v42 自身闭集占比约 40%)。

离线验证(用**实跑中 LLM 实际编译出的 slot**回放 `_select_pool`,576 题):

| 店 | 均选池大小 | 空池率 |
|---|---|---|
| v42 | 4.18 | 2.8% |
| v45(原始) | 2.94 | 16.0% |
| **v45k(回填)** | **3.94** | **5.6%** |

在线验证(全 576 题实跑):filter +6.94(p=2.0e-04)、usability +5.73(p=0.0015)、
compile +1.91(n.s. p=0.278)。回填后三臂与 v2.0 存档**全部统计不可分**
(filter +2.95 p=0.204;usability +0.69 p=0.804;compile +3.82 p=0.069)——
schema 补回后,中三段回到存档水平。

### 8.4 须落实的动作(超出本批范围)

**建卡器应把 `slot_class` / `owner` 写回**。当前 v43/v44/v45/v45g 四代店都缺这两个字段,
意味着**批 31/32 以来所有用 complex_query_arm 键控路径的结果都在无键回退下产生**,
需要按本节口径复查。这是一条真实的工程回归,不是本批的测量噪声。

---

## 九、溯源块

- **git rev**:建店与前八臂跑于 `72328335b721d9c64d05a10d3ffcebad236319d0`;记分时 HEAD 已前进到 `95af0e417e0de2e021ceb93b7dcdc2dc4900fe3c`
  (该提交由**本轨道以外**的进程写入；本轨道全程**未执行任何 git add / commit / push**，也未改任何冻结件)
- **语料** `data/wikistate_full_ALL_v24.json`
  sha256 `c62291897f22bc5632e8b155bb7d997ea4880b59ef40d3b5a5e8be5af4060749`,8,118,849 B,mtime 2026-09-02 01:23:15
- **题源** `data/wsc_s5_v2.jsonl`
  sha256 `c9adc32370e4035cc561addd2304f7d05b5c8f02e76a0d6be2c087c11671bd39`,149,795 B,576 题 / 144 链
- **店 `results/wt_cards_v45`**(OWNER_GATE=0):144 文件,建店窗 16:52:05 → **17:10:18**,
  目录 sha256 `bcb31a114dc27479326d981bbce9c6d906d7689c00e18b9d4371aeecf55589d4`,8,288 记录
- **店 `results/wt_cards_v45g`**(OWNER_GATE=1):144 文件,建店窗 16:51:48 → **17:06:03**,
  目录 sha256 `2e7209104f4d3c077a230c29fa088b19344321573f53195cc2304e57d4c8db15`,5,754 记录
- **派生店 `results/wt_cards_v45k`**(本批生成,非建卡器产物):144 文件,19:29:29,
  目录 sha256 `f1e40762ed27b52c54921279aecba884cee6becddf384580dcb1b425c133145f`
- **摘要目录 `results/wt_summaries_v24`**:144 文件,17:07:33 → 18:24:00
- **读店闸**:两店均在"144 文件齐 且 5 分钟无写入"后才开读;
  v45 最后一次写入 17:10:18,smoc(v45) 起跑于 17:15 之后(启动命令内置 `until ... -newermt '-300 seconds'` 守卫)。

### 逐臂运行时窗与读者成本

| 臂 | 产物 | 行数(原始) | 店 | 完成时刻 | in tok | out tok | 读者 $ |
|---|---|---|---|---|---|---|---|
| direct | `results/b33A_direct.jsonl` | 576 | —(不读店) | 17:58:47 | 505,291 | 49,507 | $0.602 |
| filter | `results/b33A_filter.jsonl` | 842 | v45 | 18:57:51 | 1,801,258 | 86,722 | $1.788 |
| usability | `results/b33A_usability.jsonl` | 831 | v45 | 18:59:06 | 1,895,075 | 88,963 | $1.872 |
| compile | `results/b33A_compile.jsonl` | 1,150 | v45 | 19:28:01 | 2,650,800 | 111,608 | $2.567 |
| smw | `results/b33A_smw.jsonl` | 576 | —(读原文) | 18:32:43 | 8,018,040 | 263,290 | $7.468 |
| smwplain | `results/b33A_smwplain.jsonl` | 576 | —(读原文) | 18:01:44 | 7,874,616 | 77,796 | $6.611 |
| 摘要 | `results/b33A_summary.jsonl` | 803 | wt_summaries_v24 | 19:14:55 | 1,969,210 | 74,095 | $1.872 |
| smoc(v45) | `results/b33A_smoc_v45.jsonl` | 576 | v45 | 18:32:35 | 1,694,844 | 276,000 | $2.460 |
| smoc(v45g) | `results/b33A_smoc_v45g.jsonl` | 576 | v45g | 18:30:13 | 1,215,412 | 268,396 | $2.046 |
| filter_k | `results/b33A_filter_k.jsonl` | 576 | v45k(派生) | 20:27:22 | 1,249,504 | 62,514 | $1.250 |
| usability_k | `results/b33A_usability_k.jsonl` | 576 | v45k(派生) | 20:26:40 | 1,351,276 | 64,607 | $1.339 |
| compile_k | `results/b33A_compile_k.jsonl` | 576 | v45k(派生) | 20:24:24 | 1,305,769 | 56,163 | $1.269 |
| fvl 探针 | `results/b33A_filter_v42probe.jsonl` | 144 | **v42**(仅 144 fvl) | 19:25:43 | 312,744 | 12,520 | $0.300 |

---

## 十、执行事故与处置(必须入档)

### 10.1 并发重复写

本会话的后台任务被宿主反复回收(子 python 进程成为孤儿继续运行),
我的重启动作因而在四个臂上造成**双写者**。处置:
用 `Get-CimInstance` 按 `--out` 精确定位后杀掉较晚的那一个,保留较早者跑完;
**记分统一按 question_id 保留首次出现**。

| 臂 | 原始行 | 去重后 | 重复行 | 首/后判定一致率 |
|---|---|---|---|---|
| filter | 842 | 576 | 266 | 97.4% |
| usability | 831 | 576 | 255 | 97.6% |
| compile | 1,147 | 576 | 571 | 99.8% |
| 摘要 | 803 | 576 | 227 | 96.9% |
| 其余 5 臂 + 3 个 _k 臂 | — | 576 | **0** | — |

**副产品(免费的复现性数据)**:1,319 对同题重复回答的判定一致率 **96.9%–99.8%**
—— 同配置下 haiku 读者 + opus 判官的**题级重测信度约 98%**,
可直接作为"单次跑"的噪声上界写进论文(它比任何一段阶梯的效应量都小一个量级)。

**九臂 + 三派生臂全部通过 qid 集校验**:去重后各 576 题,与 `data/wsc_s5_v2.jsonl` 对称差 = 0。

### 10.2 判官不确定性

3 题验证阶段观察到 12 次复判中 2 次判定翻转(答案文本逐字相同)。
ClaudeJudge 非确定性是既有噪声源,与 §10.1 的 98% 一致率互相印证。

---

## 十一、精确命令(可重放)

```bash
# 0) 建派生店(仅中三段用;v45 原店只读)
PYTHONUTF8=1 python scripts/b33A_backfill_slot_class.py

# 1) direct(必须 OpenAI 嵌入)
PYTHONUTF8=1 QVF_EMBED_BACKEND=openai python scripts/lb_reader_arm.py \
  --reader anthropic:claude-haiku-4-5 --arm direct \
  --data data/wikistate_full_ALL_v24.json --questions data/wsc_s5_v2.jsonl \
  --out results/b33A_direct.jsonl

# 2) filter / usability(原始 v45;把 v45 换成 wt_cards_v45k 即 _k 版)
PYTHONUTF8=1 QVF_READER_MODE=filter    QVF_CARDS_KEYED=results/wt_cards_v45 \
  python scripts/complex_query_arm.py --data data/wikistate_full_ALL_v24.json \
  --questions data/wsc_s5_v2.jsonl --out results/b33A_filter.jsonl --resume
PYTHONUTF8=1 QVF_READER_MODE=usability QVF_CARDS_KEYED=results/wt_cards_v45 \
  python scripts/complex_query_arm.py --data data/wikistate_full_ALL_v24.json \
  --questions data/wsc_s5_v2.jsonl --out results/b33A_usability.jsonl --resume

# 3) compile(冻结配置:空证据回退 + 末段计入)
PYTHONUTF8=1 QVF_CARDS_KEYED=results/wt_cards_v45 \
  QVF_EMPTY_EVIDENCE_DIRECT=1 QVF_TENURE_ASOF=1 \
  python scripts/complex_query_arm.py --data data/wikistate_full_ALL_v24.json \
  --questions data/wsc_s5_v2.jsonl --out results/b33A_compile.jsonl --resume

# 4) smw / smwplain
PYTHONUTF8=1 python scripts/repro_batch3_b33.py --system smw \
  --data data/wikistate_full_ALL_v24.json --questions-file data/wsc_s5_v2.jsonl \
  --out results/b33A_smw.jsonl
PYTHONUTF8=1 python scripts/repro_batch3_b33.py --system smwplain \
  --data data/wikistate_full_ALL_v24.json --questions-file data/wsc_s5_v2.jsonl \
  --out results/b33A_smwplain.jsonl

# 5) 无结构摘要(两阶段)
PYTHONUTF8=1 python scripts/summary_arm_b33.py --phase sum \
  --data data/wikistate_full_ALL_v24.json --sum-dir results/wt_summaries_v24
PYTHONUTF8=1 python scripts/summary_arm_b33.py --phase read \
  --data data/wikistate_full_ALL_v24.json --sum-dir results/wt_summaries_v24 \
  --questions data/wsc_s5_v2.jsonl --out results/b33A_summary.jsonl

# 6) smoc 两店(启动前守 5 分钟静默)
until [ "$(find results/wt_cards_v45 -name '*.json' -newermt '-300 seconds' | wc -l)" -eq 0 ]; do sleep 20; done
PYTHONUTF8=1 python scripts/lb_reader_arm.py --reader anthropic:claude-haiku-4-5 \
  --arm smoc --cards-dir results/wt_cards_v45 --data data/wikistate_full_ALL_v24.json \
  --questions data/wsc_s5_v2.jsonl --out results/b33A_smoc_v45.jsonl
PYTHONUTF8=1 python scripts/lb_reader_arm.py --reader anthropic:claude-haiku-4-5 \
  --arm smoc --cards-dir results/wt_cards_v45g --data data/wikistate_full_ALL_v24.json \
  --questions data/wsc_s5_v2.jsonl --out results/b33A_smoc_v45g.jsonl

# 7) schema 隔离探针(144 fvl,v2.4 语料 × v42 店)
PYTHONUTF8=1 QVF_READER_MODE=filter QVF_CARDS_KEYED=results/wt_cards_v42 \
  python scripts/complex_query_arm.py --data data/wikistate_full_ALL_v24.json \
  --questions scratchpad/b33A/fvl144.jsonl --out results/b33A_filter_v42probe.jsonl --resume

# 8) 记分与溯源
PYTHONUTF8=1 python scripts/b33A_score.py      > results/b33A_score_out.txt
PYTHONUTF8=1 python scripts/b33A_score_k.py    > results/b33A_score_k_out.txt
PYTHONUTF8=1 python scripts/b33A_provenance.py > results/b33A_provenance.txt
```

---

## 十二、本批产出的全部文件

**结果 jsonl(13)**:`results/b33A_{direct,filter,usability,compile,smw,smwplain,summary,smoc_v45,smoc_v45g}.jsonl`、
`results/b33A_{filter_k,usability_k,compile_k}.jsonl`、`results/b33A_filter_v42probe.jsonl`

**记分/溯源(4)**:`results/b33A_score_out.txt`、`results/b33A_score_k_out.txt`、
`results/b33A_provenance.txt`、`results/b33A_v45k_mapping.json`

**派生数据(2)**:`results/wt_cards_v45k/`(144 卡)、`results/wt_summaries_v24/`(144 摘要)

**新脚本(5)**:`scripts/repro_batch3_b33.py`(冻结件 + `--data`,2 行)、
`scripts/summary_arm_b33.py`(冻结件 + `--data/--sum-dir/--questions/--out`,默认路径逐字节等同原件)、
`scripts/b33A_backfill_slot_class.py`、`scripts/b33A_score.py`、`scripts/b33A_score_k.py`、
`scripts/b33A_provenance.py`

**冻结件零改动**:`scripts/lb_reader_arm.py`、`scripts/complex_query_arm.py`、
`scripts/repro_batch3.py`、`scripts/summary_arm.py` 全程只读
(`complex_query_arm.py` 本就带 `--data/--questions/--out/--uids/--resume` 与 `QVF_CARDS_KEYED`,无需副本)。

### 副本等价性证明(跑前,3 题)

各副本在 **v2.0 配置**(`data/wikistate_full_ALL.json` + `wt_cards_v42`)下与存档逐行比对:
`usage_input_tokens` **全部逐字节相同**(即渲染出的提示词完全一致),
答案 smw 3/3、compile 3/3、smoc 3/3、direct 3/3、filter 3/3、摘要 3/3 相同,
usability 2/3、smwplain 2/3(差异两条均为"无法回答"型措辞漂移,判定同为错)。
另有 $0 结构证明:`repro_batch2.VOLS` 多卷并集与 `data/wikistate_full_ALL.json`
在 144 个题面 uid 上**逐字段完全相同**(144/144),故 `--data` 覆盖不改变任何输入。

---

## 十三、局限与须加的限定词

1. **"一店"对中三段有例外**:filter/usability/compile 的可比数字来自**派生店 v45k**,
   不是建卡器直出的 v45。头条句(smoc vs direct)不受影响 —— smoc 只用 `slot/value/stated_date/source_span`,
   与 slot_class 无关,direct 完全不读店。
2. **认证段量级不复现**:+0.69(p=0.712),v2.0 为 +2.95(p=0.036)。该段不应单独作为卖点。
3. **A3 的链级证据弱于题级**:题级 p=0.042 显著,链级符号检验 p=0.169 不显著,簇 CI 轻微跨零。
   稳妥表述是"±3pp 等价性无法主张",而非"闸确定性地损失 3.47pp"。
4. **判官非确定性**约 2%(§10.2),与 98% 重测一致率一致;所有 |Δ| < 2pp 的段落都应视为不可分。
5. **v45k 的映射是我构造的**,虽用项目自带 `SLOT_ALIASES` 且确定性、全表入档,
   但它与 v42 建卡器当年由 LLM 赋类的语义**不保证一致**;18% 闭集命中率低于 v42 的约 40%。
   v45k 只用于"证明 schema 是病因、且补回可修复",**不建议作为正式店进入论文主表**。
6. 本批**未**做:33-A 之外的任何轨道;`results/wt_cards_v45`、`v45g` 全程只读未改;未提交任何 git。
