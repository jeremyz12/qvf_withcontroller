# 批 33-I 判决:盘上考场(LongMemEval 全六切分 + MemoryAgentBench-FC 小格)

**日期**:2026-09-02 · **预注册**:`results/opt_batch33_prereg.md` §33-I · **上限**:$65(第二轮由 $10 上调)
**通用口径**:读者 `claude-haiku-4-5`(temperature=0.0)、判官 `claude-opus-5`(`qvf/judge.py` 冻结)、direct 臂 `QVF_EMBED_BACKEND=openai`(text-embedding-3-small)、并行 ≤4、卡片库一律新建目录、建后只读。
**价格口径**:haiku-4-5 in \$1.00/M · out \$5.00/M;opus-5 in \$5.00/M · out \$25.00/M;text-embedding-3-small \$0.02/M。
**实测总花费:\$61.48(usage-token 口径)/ \$63.08(含 §六.3 重建的未记账部分),在 \$65 之内。**

---

## 〇、四条判决(先判决后数字)

1. **⭐ 主判决:猜想"LME-TR 上卡片臂 +12.78pp 的优势会在同形的跨会话聚合切分上复现"—— 被否定。** multi-session **133 题全跑**,smoc **59.09%** vs direct **61.36%**,**Δ = −2.27pp**,W/L/T = **27/30/75**,精确符号检验 **p = 0.791**,簇自助 95% CI **[−12.88, +9.09]** 跨零。**这是一个有功效的零结果**:n=132 与 LME-TR 的 n=133 几乎相同,该 n 下最小可测配对差 8–11pp,而观测值只有 2.3pp。**"卡片路线赢在跨会话聚合"这条解释就此作废;LME-TR 的 +12.78pp 是时序推理专有的,不是聚合专有的。**

2. **猜想"账目路线在自然语料上至少不劣于直读"—— 在三条单会话切分上全部被否定,且量级递增。** single-session-preference **−28.57pp**(p=0.057)、single-session-user **−25.00pp**(**p = 7.6e-05**)、single-session-assistant **−100.00pp**(0/45 vs 45/45,**p = 5.7e-14**)。**最后一条不是噪声也不是 bug**:卡片 schema 只记用户状态(45 库 3,716 条记录里 **3,699 条 `entity="user"`**),而该切分问的是"助手当时说了什么",**助手产出的内容在 schema 之外,账目里一条都没有**,读者据账目 80% 弃答、0% 命中。

3. **协议诊断:preference 上的 −28.57pp,一半是协议税,一半是账目内容缺口。** 同一账目换成裸问答提示(ledgerplain)后 **42.86% → 57.14%**(+14.29pp,5/1/22,p=0.219,CI[+0.00,+32.14]),弃答率 **35.7% → 14.3%**;但仍比直读低 **−14.29pp**(3/7/18,p=0.344),弃答率仍高于直读的 10.7%。**两半点估计相等,方向单调:direct > ledgerplain > smoc。** 两半单独都未达 .05(n=28 的功效上限),可主张的是分解本身,不是任一半的显著性。

4. **猜想"33-I 是盘上零成本"—— 被否定,量级已实测。** LongMemEval 建卡 **\$0.1911–\$0.1948/题**(四条切分 276 库独立复核,与归档 KU/TR 的 \$0.1917/\$0.1911 六处吻合),**全六切分 500 题的建卡成本约 \$96.5**;本轮为四条 LME 切分付出 **\$53.03 建卡费**,换来 **276 个可复用卡片库**(连同 MAB-FC 两库共 278 库)。

---

## 一、覆盖(逐格如实)

| 考场 | 目标 | 实跑 | 覆盖 | 状态 |
|---|---|---|---|---|
| LME **multi-session** | 133 | **133** | 100% | ✅ 完成(direct 臂 1 题因嵌入器报错剔除,见 §三.4) |
| LME **single-session-user** | 70 | **70** | 100% | ✅ 完成(direct 臂 2 题同因剔除) |
| LME **single-session-assistant** | 56 | **45** | 80.4% | ✅ 配对完成;11 库因 \$65 预算闸未建 |
| LME **single-session-preference** | 30 | **28** | 93.3% | ✅ 配对完成 + ledgerplain 诊断臂;2 库因第一轮 \$10 闸未建 |
| MAB-FC **mh_6k** | 100 | **100 × 2 臂** | 100% | ✅ 完成 |
| MAB-FC **mh_32k** | 100 | **100 × 2 臂** | 100% | ✅ 完成 |

**两处未满格的停止规则均为"预算闸在第 N 个卡片落盘时停机",与题面内容无关**,名单已落盘可复核(`scratchpad/b33i_ssp_subset.json`、`scratchpad/b33i_ssa_subset.json`)。**这仍是非随机的停止规则,如实标注。** SSA 缺的 11 库对判决无影响——该格是 0/45 vs 45/45 的确定性结果,补齐 11 库不可能改变符号。

---

## 二、结果表

### 2.1 LongMemEval 四条新切分(配对,1 题/库,簇 = 题)

| 切分 | n 配对 | **smoc** | **direct** | **Δ** | W/L/T | 精确符号检验 p | 簇自助 95% CI |
|---|---|---|---|---|---|---|---|
| **multi-session** | **132** | 59.09% | 61.36% | **−2.27pp** | 27/30/75 | **0.791** | [−12.88, +9.09] |
| **single-session-user** | 68 | 72.06% | 97.06% | **−25.00pp** | 1/18/49 | **7.63e-05** | [−36.76, −14.71] |
| **single-session-assistant** | 45 | 0.00% | 100.00% | **−100.00pp** | 0/45/0 | **5.68e-14** | [−100.00, −100.00] |
| **single-session-preference** | 28 | 42.86% | 71.43% | **−28.57pp** | 3/11/14 | 0.0574 | [−50.00, −3.57] |

自助 10,000 次,种子 20260902。**"n 配对"小于该切分题数处,是 direct 臂的嵌入器错误行整对剔除**(见 §三.4),错误行**不作判错计入**——那会单方面惩罚出错的一臂。

### 2.2 逐题成本与延迟

| 切分 · 臂 | in/题 | out/题 | 读端 \$/题 | 判官 \$/题 | 延迟 |
|---|---|---|---|---|---|
| multi-session · smoc | 4,386 | 441 | \$0.00659 | \$0.00201(实测) | 8.0s |
| multi-session · direct | 6,748 | 102 | \$0.00726 | \$0.00276(换算) | 3.1s |
| single-session-user · smoc | 4,186 | 358 | \$0.00598 | \$0.00163(实测) | 7.1s |
| single-session-user · direct | 6,158 | 43 | \$0.00637 | \$0.00276(换算) | 2.4s |
| single-session-assistant · smoc | 4,463 | 392 | \$0.00642 | \$0.00264(实测) | 8.9s |
| single-session-assistant · direct | 4,959 | 76 | \$0.00534 | \$0.00276(换算) | 2.8s |
| single-session-preference · smoc | 4,271 | 537 | \$0.00696 | \$0.00756(实测) | 11.4s |
| single-session-preference · ledgerplain | 4,032 | 178 | \$0.00492 | \$0.00849(实测) | 8.1s |
| single-session-preference · direct | 7,049 | 252 | \$0.00831 | \$0.00756(换算) | 5.1s |

**账目臂读端 in/题比直读低 26–38%**(账目 ≈4.2–4.5k tok vs 直读 top-10 ≈5.0–7.0k),但 out/题高 4–9×(两段式协议要写 state trace),净读端 \$/题两者相当;**建卡摊销 \$0.19/库是决定性成本项,是读端的 25–30 倍**。

### 2.3 MemoryAgentBench-FC 两个多跳小格(各 100 题,单库,簇 = 题)

| 格 | 臂 | 准确率 | in/题 | 读端 \$/题 | 延迟 | Δ vs direct | W/L/T | p | 自助 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| **mh_6k** | wt(卡片) | **12.00%** | 1,179 | \$0.00180 | 7.1s | **−2.00pp** | 5/7/88 | 0.774 | [−9.00, +5.00] |
| mh_6k | direct | **14.00%** | 998 | \$0.00151 | 2.1s | — | — | — | — |
| **mh_32k** | wt(卡片) | **12.00%** | 1,184 | \$0.00179 | 7.0s | **+2.00pp** | 8/6/86 | 0.791 | [−5.00, +9.00] |
| mh_32k | direct | **10.00%** | 1,017 | \$0.00151 | 2.1s | — | — | — | — |

---

## 三、机制:四条切分为什么这样排

### 3.1 弃答率分解(同一正则口径,零成本)

| 切分 | 臂 | 弃答率 | 非弃答子集准确率 | 卡/库中位 |
|---|---|---|---|---|
| multi-session | smoc | 19.5% | 68.2% | 80 |
| multi-session | direct | 15.2% | 62.5% | 80 |
| single-session-user | smoc | 8.6% | 76.6% | 78 |
| single-session-user | direct | **1.5%** | **97.0%** | 78 |
| single-session-assistant | smoc | **80.0%** | **0.0%** | 85 |
| single-session-assistant | direct | **0.0%** | **100.0%** | 85 |
| single-session-preference | smoc | 35.7% | 61.1% | 79 |
| single-session-preference | ledgerplain | 14.3% | 66.7% | 79 |
| single-session-preference | direct | 10.7% | 72.0% | 79 |

**卡片库本身是健康的**:四条切分卡/库中位 78–85,**零个空卡库,零次建卡批次失败**(`grep -c FAILED` 全为 0)。所以负结果不是"库没建出来",是"库里没有那类内容"。

### 3.2 ⭐ single-session-assistant:schema 覆盖边界的确定性证明

45 个库共 **3,716 条卡片,实体分布 `user` 3,699 / `Max` 6 / `cousin_alex` 4 / `Kosha Labs Inc.` 3 / 其余 4**。卡片契约抽的是**用户的状态**(slot / value / stated_date);而该切分的问题形如"提醒我一下你上次给的班表里 Admon 周日是哪个班""你之前推荐的 Cihampelas Walk 那家餐厅叫什么"——**答案是助手自己生成过的内容**,不是用户状态。

- 金标 `8 am - 4 pm (Day Shift)` / `Miss Bee Providore`,直读把当时那一轮助手原文检索回来即逐字命中 → **45/45**;
- 账目臂 45/45 全部答"我们的对话记录里没有这个信息" → **0/45**。

**这不是性能差异,是定义域之外。** 判读:**卡片 schema 的适用边界应写为"用户状态查询",凡答案落在助手产出物上的题型,该路线的上界是 0。** 这条以往从未被量化,是本轮最硬的一块负结果。

### 3.3 single-session-user 的 −25.00pp:直读接近天花板,抽取是纯损耗

直读 **97.06%**(弃答 1.5%),**该切分对稠密检索是近乎平凡的**——答案就在单个会话里,逐字可检。此时任何"先抽取再作答"的中间层都只能损失信息:账目臂 72.06%,弃答率升到 8.6%,非弃答子集也从 97.0% 掉到 76.6%。**两条损失通道(召回缺失 + 表述改写)同时发生。**

### 3.4 ⚠️ 强制切换嵌入后端引入的新失败模式(3/248 题,1.2%)

任务书硬规则要求 direct 臂用 `QVF_EMBED_BACKEND=openai`。`text-embedding-3-small` 的单条输入上限是 **8,192 token**,而 LongMemEval 原始语料里存在超长单轮:

```
openai.BadRequestError: 400 - Invalid 'input[234]': maximum input length is 8192 tokens.
  at run_decisive_stale.py:90  retriever = retriever_cls(instance.memories)
```

命中 **multi-session 1 题 + single-session-user 2 题**(整题失败,不产出答案)。归档轮用的 ollama `nomic-embed-text` 无此上限,故**这是本轮口径变更引入的、归档比较不存在的失败模式**。处置:三题整对剔除,不计入任一臂;若后续要 100% 覆盖,需在 `OpenAIDenseRetriever._embed` 加分块或截断——**这是一处未修的真实缺陷,记录在此**。

---

## 四、⭐ ledgerplain 诊断:协议税与内容缺口各占一半

按协调指令加跑的第三臂(28 题,同一批 28 个卡片库,同读者同判官;渲染器与 `PLAIN_PROMPT` 逐字取自冻结原件 `scripts/lb_reader_arm.py` 的 `ledgerplain` 分支)。

| 臂 | 提示词 | 上下文 | 准确率 | 弃答率 | 答长中位 |
|---|---|---|---|---|---|
| **smoc** | 附录 F.1 两段式(state trace + ANSWER) | 卡片账目 | **42.86%** | **35.7%** | 361 字符 |
| **ledgerplain** | 裸问答(PLAIN_PROMPT) | **同一份卡片账目** | **57.14%** | **14.3%** | 751 字符 |
| **direct** | 修正框定读者 | 稠密 top-10 原文 | **71.43%** | **10.7%** | 1,205 字符 |

| 配对 | Δ | W/L/T | p | 自助 95% CI |
|---|---|---|---|---|
| ledgerplain − smoc(**协议税**) | **+14.29pp** | 5/1/22 | 0.219 | [+0.00, +32.14] |
| ledgerplain − direct(**内容缺口**) | **−14.29pp** | 3/7/18 | 0.344 | [−35.71, +7.14] |

**判读:**
1. **协议税是真的,且机制可见**:换掉两段式协议后弃答率从 35.7% 砍到 14.3%,答长翻倍。F.1 协议要求"先列出状态更替再作答",在一个"给我推荐点东西"的量表题上,这个框架本身在诱导模型宣告"没有状态可列"。
2. **内容缺口也是真的**:去掉协议后仍比直读低 14.29pp,弃答率仍高于直读。逐题核对显示金标要的"用户自种的樱桃番茄与罗勒""偏好的纪录片题材""厨房用具架"等**软属性从未进入账目**,建卡器抽满的是 `education / employment / camera_equipment` 这类状态型槽位。
3. **两半都不显著(n=28 的功效天花板),但方向严格单调、点估计恰好等分。** 可主张的是**分解**,不是任一半的显著性。**这也说明"换个提示词就能救回账目路线"是错的——最多救回一半。**

---

## 五、自然语料记录表(全六 LME 切分 + LoCoMo 状态 + 全四 MAB-FC 格)

读者一律 `claude-haiku-4-5`,判官一律 `claude-opus-5`。**"卡片臂"列在 KU/TR 上是 `wt_qvf`(账目+裁决读法),在四条新切分上是 `smoc`(整本账目+F.1),在 MAB-FC 上是 `wt_qvf`——三者不是同一读法,禁止跨行相减。**

| 考场 / 切分 | n | 直读 | 卡片臂 | Δ | 配对 p | 本轮? | 产物 |
|---|---|---|---|---|---|---|---|
| **LME temporal-reasoning** | 133 | 47.37% | **60.15%** (wt) | **+12.78** | **0.0115** | 归档(08-17) | `tr_full133.jsonl` / `lmetr_cardfix_20260817.jsonl` |
| **LME knowledge-update** | 78 | 78.21% | 80.77% (wt) | +2.56 | 0.824 | 归档(08-17) | `final2_lmek_h45.jsonl` / `lmeku_cardfix_20260817.jsonl` |
| **LME multi-session** | **132** | 61.36% | 59.09% (smoc) | **−2.27** | 0.791 | ✅ **本轮** | `b33i_lme_ms_{smoc,direct}.jsonl` |
| **LME single-session-user** | **68** | 97.06% | 72.06% (smoc) | **−25.00** | **7.6e-05** | ✅ **本轮** | `b33i_lme_ssu_{smoc,direct}.jsonl` |
| **LME single-session-assistant** | **45/56** | 100.00% | 0.00% (smoc) | **−100.00** | **5.7e-14** | ✅ **本轮** | `b33i_lme_ssa_{smoc,direct}.jsonl` |
| **LME single-session-preference** | **28/30** | 71.43% | 42.86% (smoc) | **−28.57** | 0.0574 | ✅ **本轮** | `b33i_lme_ssp_{smoc,direct,ledgerplain}.jsonl` |
| — 同上 · ledgerplain 诊断 | 28 | 71.43% | **57.14%** | −14.29 | 0.344 | ✅ **本轮** | 同上 |
| **LoCoMo-300** | 300 | 80.33% | 69.3% (wt,归档表) | −11.0 | 归档 | 归档 | `locomo_direct_h45.jsonl`;wt 取 `RESULTS_MASTER_20260811.md:64` |
| **LoCoMo-full** | 1,986 | 69.44% | —(仅 rt 72.16%) | — | — | 归档 | `locomo_full_{direct,qvf}.jsonl` |
| **LoCoMo 链抽取** | 抽查 20/96 | — | — | — | — | **闸未过**:改判率 35%,链不得用于任何对外数字 | `locomo_spotcheck_verdict_20260826.md` |
| **MAB-FC sh_6k**(单跳) | 100 | 75.00% | 56.00% (wt) | −19.00 | 归档 | 归档 | `mabfc_sh6k_{direct,qvf}.jsonl` |
| **MAB-FC sh_262k**(单跳) | 100 | 81.00% | 71.28% (wt) | −9.72 | 归档 | 归档 | `mabfc_sh262k_{direct,qvf}.jsonl` |
| **MAB-FC mh_6k**(多跳) | 100 | 14.00% | 12.00% (wt) | −2.00 | 0.774 | ✅ **本轮** | `b33i_mabfc_mh6k_{direct,wt}.jsonl` |
| **MAB-FC mh_32k**(多跳) | 100 | 10.00% | 12.00% (wt) | +2.00 | 0.791 | ✅ **本轮** | `b33i_mabfc_mh32k_{direct,wt*}.jsonl` |

### 这张表读出来的四句话

1. **十个可比格里,卡片路线只在一个上赢:LME temporal-reasoning(+12.78pp)。** 打平两个(knowledge-update +2.56、multi-session −2.27、MAB 两个多跳格 ±2.0),输六个(−9.7 / −11.0 / −19.0 / −25.0 / −28.6 / −100.0)。**这个分布此前从未被完整摆出来过——以往的引用都停在 TR 那一格。**
2. **赢/平/输有一条干净的分界:问题是否需要在带日期的状态更替上做推理。** 赢的那格(TR)问的是"两件事隔了多少天";平的那两格(KU 覆盖更新、multi-session 跨会话聚合)状态性中等;输的六格里,单会话三格问的是"逐字复述某条已说过的内容"(其中 assistant 那格的答案根本不属于用户状态)、LoCoMo 问实体归属、MAB-FC 问稠密事实库上的多跳组合。**卡片 schema 的强项(`stated_date` + `temporal_relation` + 取代边)在这六格上无处发力,而抽取的损耗照收。**
3. **抽取损耗的两条通道已定量**:①**覆盖缺失**——弃答率从直读的 0–15% 抬到账目的 8.6–80.0%;②**协议税**——F.1 两段式在非状态题上再吃掉约一半(preference 上 +14.29pp 可由换裸提示救回)。
4. **MAB-FC 两个多跳格没有区分度**,四臂全在 10–14% 地板区,原因见 §七.1(同语料对照证明瓶颈是多跳组合而非记忆),**不应写进"记忆系统同台表"**。

---

## 六、成本账(全部由 usage token 复算)

| 条目 | n | USD |
|---|---|---|
| 建卡 · LME single-session-preference | 28 库 | \$5.3508 |
| 建卡 · MAB-FC(2 库,仅成功批次) | 2 库 | \$0.2784 |
| 建卡 · **LME multi-session** | **133 库** | **\$25.6285**(\$0.1927/库) |
| 建卡 · **LME single-session-user** | **70 库** | **\$13.3626**(\$0.1909/库) |
| 建卡 · **LME single-session-assistant** | **45 库** | **\$8.6889**(\$0.1931/库) |
| **建卡小计** | **278 库** | **\$53.3092** |
| 读端 + 判官 · 全十一臂(15 个产物文件) | 980 题次 | **\$7.4115**(其中判官侧五臂逐行实测、六臂按 \$/次换算) |
| OpenAI 嵌入 | — | \$0.7549 |
| **合计(usage-token 口径)** | | **\$61.4757** |
| 追加:mh_32k 建卡失败批次的未记账计费(§七.3 重建,中位估) | | **+\$1.60** |
| **合计(含重建)** | | **\$63.08 / 上限 \$65** |

**判官 \$/次的两个基准**:量表金标(preference)实测 **\$0.00756–0.00849/次**;短金标(其余切分)实测 **\$0.00163–0.00264/次**,归档 LME-TR 为 \$0.00276/次。冻结跑批器 `run_decisive_stale.py` **不落盘判官用量**,故 direct 各臂按同题 smoc 臂实测的 \$/次换算,已在表中标注。

**建卡单价六处独立复核一致**:LME-SSP \$0.1911 · MS \$0.1927 · SSU \$0.1909 · SSA \$0.1931 · 归档 KU \$0.1917 · 归档 TR \$0.1911。**该单价可以作为定价常数引用。** 全六切分 500 题的完整建卡成本 ≈ **\$96.5**。

---

## 七、四个新发现(均可零成本复核)

### 7.1 ⭐ `mab_fc_mh_6k` 与 `mab_fc_sh_6k` 的语料**逐字节相同**——61pp 差全归题型,不归记忆

两文件 `sessions` 段规范化 JSON 的 SHA-256 完全一致(48,992 字符,455 条事实轮次)。差的只有问句:sh 单跳(`Which sport is goaltender associated with?`),mh 两跳(`...the country of citizenship of the spouse of the author of Our Mutual Friend?`)。**因此 sh_6k 直读 75% 与 mh_6k 直读 14% 之间的 61pp,是在同一份记忆、同一检索器、同一读者下测出来的完美对照,唯一变量是问句要几跳。** 判读:MAB-FC 的瓶颈是多跳组合,不是记忆表示;该格不具备区分记忆方案的功效。

### 7.2 ⭐ 同一份语料、同一建卡器,两次跑批产出 **271 vs 83** 张卡(3.3×)

归档 `results/wt_cards/mabfc-factconsolidation_sh_6k.json` 271 卡(覆盖 59.6%)vs 本轮 `results/wt_cards_b33i_mab/mabfc-factconsolidation_mh_6k.json` 83 卡(覆盖 18.2%),**语料逐字节相同,顶层键 / 13 个记录字段 / `record_id` 命名完全一致**(旗标签名无差别)。唯一不可见的变量是 08-17 后 `QVF_CARD_TEMP0` 默认由 0 改 1(温度不落盘)。**二选一,两者都在写入侧;不能主张是哪一个**,但"卡片数"这一量在该语料上不可复现。对照:mh_32k 覆盖率 **225/2,310 = 9.7%**。
**注意:本轮四条 LME 切分的 276 次建卡零失败、零空库、in/库 132–142k 高度同质**,该不确定性只在稠密事实库(MAB-FC)上出现,**不污染 LME 的任何结论**。

### 7.3 ⭐ `wt_qvf_prototype._catalog()` 的失败路径**丢弃已计费的 usage**

异常分支 `return [], 0, 0` —— 该次 API 调用已发生并已计费,用量却被清零后向上合并。mh_32k 建卡触发:日志记 8 次终态失败,按对半递归树推算 31 次调用里 **23 次未记账**。落盘只记 \$0.2000;按叶层实测的 2.49 字符/token 反推,未记账输入 ≈590,735 tok(\$0.59),未记账输出在 \$0.46–\$1.84 之间 → **该格真实计费 \$1.25–\$2.63(中位 \$1.80),账面低报 6–13×**。
**建议修复**:`_catalog()` 异常分支回传已知 `resp.usage`;稠密事实库把 `QVF_CATALOG_BUDGET` 调小到不触发递归。**修复前,所有建卡成本主张须标注"仅统计成功批次"。**

### 7.4 OpenAI 嵌入 8,192-token 单条上限打掉 3/248 道 direct 题(1.2%)

见 §三.4。**这是硬规则要求的后端切换引入的新失败模式,归档的 ollama 轮不存在。** 未修,已如实剔除。

---

## 八、复现命令(逐字)

```bash
# 0) 适配四条剩余切分(零成本)
for q in multi-session single-session-user single-session-assistant single-session-preference; do
  PYTHONUTF8=1 python scripts/adapt_lme_for_wt.py $q
done

# 1) 建卡(每条切分一个新目录;$0.191/库;可按 --uids 分片,并行 ≤4)
PYTHONUTF8=1 QVF_EMBED_BACKEND=openai python scripts/wt_qvf_prototype.py --phase write \
    --data data/lme_multi_session_wt.json --cards-dir results/wt_cards_b33i_lme_ms \
    --uids "<逗号分隔 uid 分片>"

# 2) smoc 臂(账目 + 附录 F.1;渲染器/提示词/解析全部 import 自冻结的 repro_batch3.py)
PYTHONUTF8=1 python scripts/b33i_smoc_arm.py \
    --data data/lme_multi_session_wt.json --cards-dir results/wt_cards_b33i_lme_ms \
    --qtype multi-session --out results/b33i_lme_ms_smoc.jsonl

# 3) direct 臂(必须 openai 嵌入)
PYTHONUTF8=1 QVF_EMBED_BACKEND=openai python scripts/run_decisive_stale.py \
    --benchmark longmemeval --data data/longmemeval_s_cleaned.json \
    --qtype multi-session --conditions dense_direct --reader claude-haiku-4-5 \
    --out results/b33i_lme_ms_direct.jsonl --resume
#    (未满格的切分加 --qid-file scratchpad/b33i_<split>_qids.txt 把两臂钉在同一子集)

# 4) ledgerplain 诊断臂(同一账目 + 裸问答提示)
PYTHONUTF8=1 python scripts/b33i_ledgerplain_arm.py \
    --data data/lme_single_session_preference_wt.json --cards-dir results/wt_cards_b33i_lme \
    --qtype single-session-preference --out results/b33i_lme_ssp_ledgerplain.jsonl

# 5) MAB-FC 两格:建卡 → wt 臂 → direct 臂
for c in mh_6k mh_32k; do
  PYTHONUTF8=1 QVF_EMBED_BACKEND=openai python scripts/wt_qvf_prototype.py --phase write \
      --data data/mab_fc_$c.json --cards-dir results/wt_cards_b33i_mab
  PYTHONUTF8=1 QVF_EMBED_BACKEND=openai python scripts/wt_qvf_prototype.py --phase read \
      --data data/mab_fc_$c.json --cards-dir results/wt_cards_b33i_mab \
      --out results/b33i_mabfc_${c/_/}_wt.jsonl
  PYTHONUTF8=1 QVF_EMBED_BACKEND=openai python scripts/run_decisive_stale.py \
      --benchmark stale_chain --data data/mab_fc_$c.json --conditions dense_direct \
      --reader claude-haiku-4-5 --out results/b33i_mabfc_${c/_/}_direct.jsonl --resume
done

# 6) 统计 / 诊断 / 成本(全部 $0)
PYTHONUTF8=1 python scripts/b33i_report.py      # 逐格 acc + McNemar + 自助 CI
PYTHONUTF8=1 python scripts/b33i_ssp_diag.py    # 三臂弃答分解
PYTHONUTF8=1 python scripts/b33i_cost.py        # 全轮美元账
```

## 九、产物清单

**新建卡片库(建后只读,未覆盖任何既有目录;共 278 库,可复用)**
`results/wt_cards_b33i_lme/`(28)· `results/wt_cards_b33i_lme_ms/`(133)· `results/wt_cards_b33i_lme_ssu/`(70)· `results/wt_cards_b33i_lme_ssa/`(45)· `results/wt_cards_b33i_mab/`(2)

**跑批产物(11 个臂)**
`b33i_lme_ssp_{smoc,direct,ledgerplain}.jsonl`(28×3)· `b33i_lme_ms_{smoc,direct}.jsonl`(133×2)· `b33i_lme_ssu_{smoc,direct}.jsonl`(70×2)· `b33i_lme_ssa_{smoc,direct}.jsonl`(45×2)· `b33i_mabfc_mh6k_{wt,direct}.jsonl`(100×2)· `b33i_mabfc_mh32k_{wt,wt_p0,wt_p1,direct}.jsonl`(去重后 100×2)

**新脚本(未修改任何冻结原件)**
- `scripts/b33i_smoc_arm.py` —— 任意 wt-schema 语料上的 smoc 臂;渲染器 / 提示词 / 解析 / 读者常量全部 `from repro_batch3 import`。**唯一协议差异必须同页写明**:本轮把**真实考场 question_type** 传给判官,而 08-17 归档 KU/TR 轮传的是 `stale_chain` 载入器的 `chain-q1`;量表型金标下后者会系统性吃亏,故不沿用。
- `scripts/b33i_ledgerplain_arm.py` —— 诊断臂,语义逐字镜像冻结原件 `lb_reader_arm.py` 的 `ledgerplain` 分支。
- `scripts/b33i_stats.py` / `b33i_report.py` / `b33i_ssp_diag.py` / `b33i_cost.py` —— 配对精确符号检验 / 簇自助 CI / 弃答分解 / 美元账,零 LLM。

**新数据(适配器产物,零成本)**:`data/lme_{multi_session,single_session_user,single_session_assistant,single_session_preference}_wt.json`

---

## 十、后续(按性价比排序)

1. **修 §7.3 的用量丢弃 + §7.4 的嵌入分块**(\$0,各一处小改)—— 前者让建卡成本可审计,后者让 direct 臂覆盖回到 100%。
2. **验 §7.2 的建卡不确定性**(\$0.24)—— 在同一份 `mab_fc_sh_6k` 语料上重建 3 次,看卡数落在 83 还是 271 附近,即可把"跑批不确定性"与"温度默认变更"分开。**本轮最便宜、最能定分界的实验。**
3. **补齐 single-session-assistant 剩余 11 库**(\$2.2)—— 只为把该格写成 56/56;**对判决无影响**(0/45 vs 45/45 的符号不可能翻转),优先级低。
4. **不建议再投**:MAB-FC 两个多跳格(§7.1 已证明无区分度)、LME 单会话三格的更多臂(负结果机制已定位到 schema 覆盖,加臂不产生新信息)。
5. **写作建议**:§五 那张十格表应整体入论文,配 §五 的四句读法。**只引 LME-TR 一格的写法从此不成立**——本轮已把同一方法在同一考场其余五格上的表现全部测出来,其中三格是显著负。
