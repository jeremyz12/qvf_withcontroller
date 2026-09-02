# 批 33-F 判决:上界臂(F1 oracle 证据 / F2 oracle 卡)@ v2.4 全 576 题

跑期 2026-09-02。语料 `data/wikistate_full_ALL_v24.json`(144 链),题集
`data/wsc_s5_v2.jsonl`(576,四型各 144)。读者 `anthropic:claude-haiku-4-5`
(temperature 0,max_tokens 800),判官 `qvf.judge.ClaudeJudge`(claude-opus-5,冻结)。
并行度 4(每臂 4 分片)。实测总成本 **$5.01**(上限 $8)。

---

## 一、四条判决

**判决 1:写侧仍有余量,但只有 +4.51pp,且方向显著。**
F2(金链渲染的账目 + 同一 SMW 提示词)= **94.97%**,v2.4 实跑 smoc = 90.45%。
配对 McNemar **p = 0.0022**(b=47 / c=21),144 链簇自助 95% CI **[+1.39, +7.99]pp**。
把建卡环节整个换成完美金链,只买回 4.51pp —— **建卡不是 v2.4 的主要瓶颈**。
毛账更能说明问题:F2 修好 smoc 的 47 题(+8.16pp),同时**打坏 smoc 已答对的 21 题**
(−3.65pp),净 +4.51pp。那 21 题的成因见判决 3,是渲染面变稀导致的,不是写侧优势。

**判决 2:完美检索**不能**追平结构化账目 —— 猜想"证据可得性是主要瓶颈"被否定。**
F1(把 direct 臂的 top-10 换成金链锚句,系统提示词与内容格式逐字沿用 direct)
= **76.74%**。
- F1 − direct(48.26)= **+28.47pp**,McNemar p = 6.3e-28,CI [+23.96, +33.16]。
  检索天花板确实很高:direct 的错里有 203 题只要给对句子就能答对。
- F1 − smoc(90.45)= **−13.72pp**,McNemar p = 8.0e-11(b=36 / c=115),
  CI [−17.88, −9.55]。**给了金句的直读臂,仍比真实账目臂低 13.72pp。**
  分型看死因:longest_tenure 47.2%、change_count 72.2%(count_before 88.9、
  first_vs_last 98.6)—— 聚合型问题不是"看不到证据",是没有可供逐段计算的表征与协议。
- 限定:F1 沿用 direct 的读者协议(1–3 句日常口吻回复,无两段式状态迹),
  所以 smoc − F1 这 13.72pp **同时**含"账目表征"与"两段式协议"两项,本臂不可拆分。

**判决 3:100 − F2 = 5.03pp 的残差里,没有一条确认的金标错误;成分是
"日期欠定约定 + 读者run间不稳",不是标注错。**
29 条 F2 失败逐条机械归类(表见 §四):
| 成因 | 条数 |
|---|---|
| 账目里含**晚于题面"今日"**的金链行(change_count,金标按今日截断,账目未截断) | 10 |
| 截止年**日期欠定** `YYYY-00-00`,金标静默按 `01-01` 解析并计入 | 9 |
| longest_tenure **近平局**(第一/第二差 ≤40 天,其中 7 条恰为 30d 或 1d,即 00→01 解析的产物) | 8 |
| 读者算错(差 457d / 2581d,金标无歧义) | 2 |

- **金标本身在这 29 条上都自洽**:10 条 longest_tenure 的金标全部等于按金链
  日期做区间算术得到的第一名(无一条出现"金标 ≠ 算术第一");count_before /
  change_count 的金标在"`YYYY-00-00`=1 月 1 日"与"今日截断"两条约定下也都正确。
  **确认金标错误 = 0/29(0%)**,与 33-B 的 B1 判据(金标类 < 20%)不冲突。
- 但**约定不可从渲染面恢复**:读者看到的是字面 `2007-00-00`,无从知道出题器把它
  解析成 `2007-01-01`。这是**数据表/规范缺陷**,不是标注错误。

**判决 4(事后诊断,非预注册):F2 的"失败"有 38% 是同配置重跑就会翻转的抖动。**
拿 F2 的 29 条失败原样重跑(同提示词、同 temperature 0、无任何改动),
**11/29 变对**。再拿同一 29 条把账目日期按出题器约定补全(`YYYY-00-00`→`YYYY-01-01`,
`QVF_B33F_DATEFIX=1`)重跑,**18/29 变对**。
- 配对比较(补全 vs 同配置对照,同 29 题):b=10 / c=3,**p = 0.092**,
  在这个被选出的子集上**不显著**。
- 唯一干净的信号在 count_before:对照 4/9 → 补全 **9/9**(全恢复);
  change_count 4/10→4/10 无变化(补全不触碰"未来行"机制),longest_tenure 3/10→5/10。
- **判读**:F2 = 94.97 是一次抽样的点估计,读者在这批边界题上run间不稳定;
  "上界"应读作 ≈95(±抖动),不应读作精确值。若把"日期补全"当作规范修复,
  条件上界 ≈ 98.1(94.97 + 18/576),**该数字未在全 576 题上验证**(只重跑了 29 条失败题,
  未检验 547 条已答对题是否回退),因此**只作方向性上界,不入表**。

---

## 二、数字表

### 准确率(全 576,判官同一冻结判官)

| 臂 | 总 | change_count | count_before | first_vs_last | longest_tenure |
|---|---|---|---|---|---|
| direct v2.4(OpenAI 嵌入) | 48.26 | 34.72 | 43.75 | 80.56 | 34.03 |
| **F1 oracle 证据** | **76.74** | 72.22 | 88.89 | 98.61 | 47.22 |
| smoc v2.4(实跑) | 90.45 | 88.19 | 88.89 | 96.53 | 88.19 |
| **F2 oracle 卡** | **94.97** | 93.06 | 93.75 | **100.00** | 93.06 |

### 配对检验(McNemar 精确二项双侧;CI = 144 链簇自助 5000 次)

| 比较 | Δ | 95% CI | b / c | p |
|---|---|---|---|---|
| F2 − smoc v2.4 | **+4.51pp** | [+1.39, +7.99] | 47 / 21 | 2.2e-03 |
| F2 − direct | +46.70pp | [+42.19, +51.39] | 279 / 10 | 2.0e-69 |
| F1 − smoc v2.4 | **−13.72pp** | [−17.88, −9.55] | 36 / 115 | 8.0e-11 |
| F1 − direct | +28.47pp | [+23.96, +33.16] | 203 / 39 | 6.3e-28 |

### 成本与延迟(逐题 usage token 实计;haiku-4-5 $1/$5,opus-5 判官 $5/$25 每 MTok)

| 跑次 | n | 读者 in/out | 判官 in/out | $ | 读者延迟均值 |
|---|---|---|---|---|---|
| F1 oracle 证据 | 576 | 127,168 / 47,148 | 112,977 / 52,190 | 2.2325 | 1.55 s |
| F2 oracle 卡 | 576 | 268,796 / 274,604 | 62,858 / 20,906 | 2.4788 | 4.26 s |
| 诊断:补全日期(29 失败题) | 29 | 13,888 / 15,374 | 2,789 / 1,450 | 0.1410 | — |
| 诊断:同配置对照(29 失败题) | 29 | 13,888 / 15,195 | 2,791 / 1,356 | 0.1377 | — |
| 冒烟(各 3 题) | 6 | 2,007 / 1,401 | 791 / 225 | 0.0186 | — |
| **合计** | | | | **5.0086** | |

读者 token/题对照:F1 221/82,F2 467/477,smoc(实跑)2951/479,direct 877/86。
F2 的读取侧只有 smoc 的 1/6 —— 金链账目 3–8 行,实跑账目 50–70 行。
墙钟未插桩;上表延迟为逐题实测的读者调用耗时,判官耗时未记。

协议偏差(无 `ANSWER:` 末行):F2 2/576,smoc 1/576。

---

## 三、精确复现命令

```bash
# F1(4 分片并行)
for i in 0 1 2 3; do PYTHONUTF8=1 python scripts/lb_reader_arm_b33oracle.py \
  --reader anthropic:claude-haiku-4-5 --arm oracle_evidence \
  --data data/wikistate_full_ALL_v24.json --questions data/wsc_s5_v2.jsonl \
  --shard $i --nshards 4 --out results/b33_F1_oracle_evidence_shard$i.jsonl & done; wait

# F2(4 分片并行)
for i in 0 1 2 3; do PYTHONUTF8=1 python scripts/lb_reader_arm_b33oracle.py \
  --reader anthropic:claude-haiku-4-5 --arm oracle_cards \
  --data data/wikistate_full_ALL_v24.json --questions data/wsc_s5_v2.jsonl \
  --shard $i --nshards 4 --out results/b33_F2_oracle_cards_shard$i.jsonl & done; wait

# 事后诊断:29 条 F2 失败题,补全日期 vs 同配置对照
PYTHONUTF8=1 QVF_B33F_DATEFIX=1 python scripts/lb_reader_arm_b33oracle.py \
  --reader anthropic:claude-haiku-4-5 --arm oracle_cards \
  --data data/wikistate_full_ALL_v24.json --questions <29题子集> \
  --out results/b33_F2diag_datefix_misses.jsonl
PYTHONUTF8=1 python scripts/lb_reader_arm_b33oracle.py \
  --reader anthropic:claude-haiku-4-5 --arm oracle_cards \
  --data data/wikistate_full_ALL_v24.json --questions <29题子集> \
  --out results/b33_F2diag_rerun_control.jsonl
```

对照基线(既有文件,本次未重跑):
smoc v2.4 = `results/b31_smoc_v22_full.jsonl` ← `b31_smoc_v23.jsonl` ← `b31_smoc_v24.jsonl`
(按 qid 后覆盖前,576 题,复算 = 90.45);direct v2.4 = `results/b33_direct_v24oai_shard{0..5}.jsonl`
(576 题,复算 = 48.26)。

## 文件

| 用途 | 路径 |
|---|---|
| 跑批器(`scripts/lb_reader_arm.py` 的副本 + 两 oracle 臂;原件未改动) | `scripts/lb_reader_arm_b33oracle.py` |
| F1 结果 | `results/b33_F1_oracle_evidence_shard{0,1,2,3}.jsonl` |
| F2 结果 | `results/b33_F2_oracle_cards_shard{0,1,2,3}.jsonl` |
| 诊断:补全日期 / 同配置对照 | `results/b33_F2diag_datefix_misses.jsonl` / `results/b33_F2diag_rerun_control.jsonl` |
| 本判决 | `results/opt_batch33_F_oracle_verdict.md` |

**口径固定(与对照臂逐字同源,不新造)**:
F1 用 `ext_direct_arm.READER_SYSTEM` + `ext_direct_arm.reader_content` +
`ext_direct_arm._query_date`,只把 top-10 检索结果换成金链锚句
(`MemoryItem(content=state_span, metadata.session_date=chain.date)`,按日期升序),
答案取读者原文(不走 `parse_answer`),与 direct 臂一致。
F2 用 `repro_batch3.SMW_PROMPT` + `repro_batch3.parse_answer`,账目行格式逐字镜像
`repro_batch3.render_card_ledger` 的整本视图分支
(`[entry n] <date> | <slot>: <value> — "<span[:120]>"`),日期取金链行日期、
slot 取条目 `slot` 字段。金链最长 span = 120 字符,故 `[:120]` 截断在本语料上为空操作。

---

## 四、F2 的 29 条失败(逐条,金标 / 答案 / 机制)

**读法**:这些是"候选金标错误"的**全部候选**;逐条核对后**无一条被确认为金标错误**。
"同配置重跑""补全日期重跑"两列来自 §一判决 4 的诊断跑。

| 型 | qid | 金标 | F2 答 | smoc | F1 | 同配置重跑 | 补全日期重跑 | 机制 |
|---|---|---|---|---|---|---|---|---|
| change_count | `wikiP108004-Q54196276_v2cc` | 1 | 2 | 对 | 错 | 对 | 错 | 今日2006-02-14 之后仍有 1 条金链行(2006-10-01)被渲入账目 |
| change_count | `wikiP108006-Q67650882_v2cc` | 1 | 2 | 对 | 错 | 错 | 错 | 今日2018-02-07 之后仍有 1 条金链行(2019-04-01)被渲入账目 |
| change_count | `wikiP108017-Q61756107_v2cc` | 1 | 2 | 对 | 错 | 错 | 对 | 今日1985-10-18 之后仍有 1 条金链行(1987-01-04)被渲入账目 |
| change_count | `wikiP108030-Q67469956_v2cc` | 1 | 2 | 对 | 错 | 对 | 对 | 今日2019-03-17 之后仍有 1 条金链行(2022-03-00)被渲入账目 |
| change_count | `wikiP108035-Q39407125_v2cc` | 1 | 2 | 对 | 对 | 错 | 错 | 今日2014-01-20 之后仍有 1 条金链行(2023-05-30)被渲入账目 |
| change_count | `wikiP108038-Q37830162_v2cc` | 1 | 2 | 对 | 对 | 错 | 错 | 今日2008-08-16 之后仍有 1 条金链行(2012-09-01)被渲入账目 |
| change_count | `wikiP39004-Q4989135_v2cc` | 1 | 2 | 对 | 对 | 对 | 错 | 今日2004-10-08 之后仍有 1 条金链行(2006-10-10)被渲入账目 |
| change_count | `wikiP54002-Q56709404_v2cc` | 1 | 2 | 对 | 错 | 对 | 错 | 今日2023-01-01 之后仍有 1 条金链行(2024-00-00)被渲入账目 |
| change_count | `wikiP54012-Q25618290_v2cc` | 1 | 2 | 对 | 错 | 错 | 对 | 今日2021-08-16 之后仍有 1 条金链行(2024-04-01)被渲入账目 |
| change_count | `wikiP54029-Q22911202_v2cc` | 1 | 2 | 对 | 错 | 错 | 对 | 今日2023-01-01 之后仍有 1 条金链行(2024-01-01)被渲入账目 |
| count_before | `wikiP108049-Q43145446_v2cb` | 4 | 3 | 对 | 对 | 错 | 对 | 截止 2007-06-30,末行日期欠定 ['2007-00-00'](金标按 01-01 解析计入) |
| count_before | `wikiP39011-Q5581581_v2cb` | 7 | 6 | 对 | 对 | 对 | 对 | 截止 1963-06-30,末行日期欠定 ['1963-00-00'](金标按 01-01 解析计入) |
| count_before | `wikiP39015-Q7167656_v2cb` | 6 | 5 | 错 | 错 | 对 | 对 | 截止 1896-06-29,末行日期欠定 ['1896-00-00'](金标按 01-01 解析计入) |
| count_before | `wikiP39024-Q6250233_v2cb` | 4 | 3 | 错 | 错 | 错 | 对 | 截止 1859-06-30,末行日期欠定 ['1859-00-00'](金标按 01-01 解析计入) |
| count_before | `wikiP39030-Q6265172_v2cb` | 7 | 6 | 对 | 错 | 错 | 对 | 截止 1892-06-29,末行日期欠定 ['1892-00-00'](金标按 01-01 解析计入) |
| count_before | `wikiP54008-Q54622403_v2cb` | 3 | 2 | 对 | 对 | 对 | 对 | 截止 2021-06-30,末行日期欠定 ['2021-00-00'](金标按 01-01 解析计入) |
| count_before | `wikiP54023-Q16200523_v2cb` | 4 | 3 | 对 | 对 | 错 | 对 | 截止 2014-06-30,末行日期欠定 ['2014-00-00'](金标按 01-01 解析计入) |
| count_before | `wikiP551001-Q20667184_v2cb` | 4 | 3 | 对 | 对 | 错 | 对 | 截止 1924-06-29,末行日期欠定 ['1924-00-00'](金标按 01-01 解析计入) |
| count_before | `wikiP551009-Q5321987_v2cb` | 4 | 3 | 对 | 对 | 对 | 对 | 截止 1890-06-30,末行日期欠定 ['1890-00-00'](金标按 01-01 解析计入) |
| longest_tenure | `wikiP108012-Q61996585_v2lt` | University of Arkansas for Medical Sciences | Institute of Cancer Research | 错 | 对 | 错 | 对 | 第一 University of Arkansas for Medical 4229d vs 第二 Institute of Cancer Research 4199d,差 30d |
| longest_tenure | `wikiP108019-Q41470166_v2lt` | United States National Institutes of Health | University of Perugia (5 years, tied with Un | 对 | 错 | 错 | 错 | 第一 United States National Institutes  1827d vs 第二 University of Perugia 1826d,差 1d |
| longest_tenure | `wikiP108030-Q67469956_v2lt` | CERN | Institute of Theoretical and Experimental Ph | 错 | 对 | 错 | 对 | 第一 CERN 2312d vs 第二 Institute of Theoretical and Exper 2282d,差 30d |
| longest_tenure | `wikiP108033-Q40033742_v2lt` | San Raffaele Hospital | - Istituto Oncologico della Svizzera | 对 | 错 | 对 | 对 | 第一 San Raffaele Hospital 1188d vs 第二 Ospedale Regionale di Locarno 731d,差 457d |
| longest_tenure | `wikiP39001-Q4942028_v2lt` | member of the Committee on Finance | member of the Swedish Riksdag | 错 | 对 | 错 | 错 | 第一 member of the Committee on Finance 3662d vs 第二 member of the Swedish Riksdag 1081d,差 2581d |
| longest_tenure | `wikiP39009-Q6242279_v2lt` | member of the 53rd Parliament of the United Kingdom | - 52nd Parliament | 对 | 对 | 错 | 错 | 第一 member of the 53rd Parliament of t 3271d vs 第二 member of the 45th Parliament of t 3241d,差 30d |
| longest_tenure | `wikiP39015-Q7167656_v2lt` | High Sheriff of Wiltshire | member of the 22nd Parliament of the United  | 错 | 错 | 对 | 对 | 第一 High Sheriff of Wiltshire 5784d vs 第二 member of the 22nd Parliament of t 5754d,差 30d |
| longest_tenure | `wikiP39037-Q3525068_v2lt` | colonial governor of Guadeloupe | member of the 16th Parliament of Great Brita | 错 | 错 | 对 | 对 | 第一 colonial governor of Guadeloupe 3793d vs 第二 member of the 16th Parliament of G 3763d,差 30d |
| longest_tenure | `wikiP54004-Q29589370_v2lt` | Roskilde Junior | Roskilde Cykle Ring | 错 | 错 | 错 | 错 | 第一 Roskilde Junior 1827d vs 第二 Roskilde Cykle Ring 1826d,差 1d |
| longest_tenure | `wikiP54028-Q22681824_v2lt` | Benotti Berthold | Leopard Pro Cycling | 对 | 错 | 错 | 错 | 第一 Benotti Berthold 923d vs 第二 Leopard Pro Cycling 893d,差 30d |

---

## 五、限定与遗留

1. **F2 不是干净的"完美写侧"上界。** 金链账目比实跑账目**稀疏得多**(3–8 行 vs 50–70 行),
   并且日期用的是 Wikidata 原始占位串(`1992-00-00`),而实跑卡片的 `stated_date`
   是会话侧已归一的日期(渲成 `1992`)。所以 F2 的 21 条回退里,至少
   count_before 一类(7 条)是**渲染面比实跑更差**造成的,不是"完美写侧"该有的行为。
   +4.51pp 因此是写侧余量的**下界**估计。
2. **抖动未量化到全卷。** 只在 29 条失败题上测到 38% 的run间翻转;
   全 576 题的重复跑没做($ 与预注册范围外)。F2 = 94.97 的重复性未知。
3. **判官未双盲复核。** 29 条失败全部由 opus-5 判官单次判定,未做二判或人工核。
   逐条读判词未见明显误判(答案与金标确为不同实体/不同数字)。
4. **"日期补全"的条件上界 98.1 未验证。** 需在全 576 题上重跑 `QVF_B33F_DATEFIX=1`
   才能确认 547 条已答对题不回退;本次未做。
5. **与 33-B 的互证结论**:F2 侧给出的"确认金标错误 = 0/29",支持 B1 判据
   (金标类 < 20%)。但 33-B 若把"日期欠定/未来行"这类**规范缺陷**归入金标类,
   比例会跳到 19/29 = 65.5% —— 两者的差别完全在于"标注错" 与 "约定未写进数据表"
   如何归类。建议 33-B 采用两档:`gold_wrong`(错标)与 `gold_underspecified`(约定缺失),
   并把后者写进 WikiState 数据表的构造规范(占位日期解析规则、"今日"截断是否作用于账目)。
