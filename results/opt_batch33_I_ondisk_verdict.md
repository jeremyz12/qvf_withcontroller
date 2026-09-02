# 批 33-I 判决:盘上考场(LongMemEval 剩余切分 + MemoryAgentBench-FC 小格)

**日期**:2026-09-02 · **预注册**:`results/opt_batch33_prereg.md` §33-I("LongMemEval 其余 289 题 smoc vs direct;MAB-FC mh_6k / mh_32k")
**通用口径**:读者 `claude-haiku-4-5`(temperature=0.0)、判官 `claude-opus-5`(`qvf/judge.py` 冻结)、direct 臂 `QVF_EMBED_BACKEND=openai`(text-embedding-3-small)、并行 ≤4、卡片库一律新建目录。
**价格口径**:haiku-4-5 in \$1.00/M · out \$5.00/M;opus-5 in \$5.00/M · out \$25.00/M;text-embedding-3-small \$0.02/M。

---

## 〇、三条判决(先判决后数字)

1. **猜想"账目/卡片路线在 LongMemEval 剩余自然语料上至少不劣于稠密直读"—— 在 single-session-preference 上被否定。** smoc **42.86%** vs direct **71.43%**(n=28 配对),**Δ = −28.57pp**,W/L/T = **3/11/14**,精确符号检验 **p = 0.0574**,簇自助 95% CI **[−50.00, −3.57] 不含 0**。机制已定位:账目臂**弃答率 10/28 = 35.7%**,直读臂 **2/28 = 7.1%**——建卡器抽的是"状态型槽位",偏好类软属性根本没进账目,读者据账目判"无此信息"而拒答。

2. **猜想"卡片路线在 MAB-FC 多跳小格上优于直读"—— 在两格上都被否定为零效应。** mh_6k:wt **12.00%** vs direct **14.00%**,Δ = −2.00pp,5/7/88,**p = 0.774**,CI [−9.00, +5.00];mh_32k:wt **12.00%** vs direct **10.00%**,Δ = +2.00pp,8/6/86,**p = 0.791**,CI [−5.00, +9.00]。**两格四臂全部落在 10–14% 的地板区**,与该考场单跳格(sh_6k 直读 75%、sh_262k 直读 81%)相差 61–71pp。

3. **猜想"33-I 是盘上零成本"—— 被否定。** LongMemEval 建卡实测 **\$0.1911/题**(28 库实测,与归档 KU/TR 的 \$0.1917/\$0.1911 三处独立吻合),**289 题端到端需 \$64.80**(建卡 \$55.23 + 读判 \$9.57),**是本轮 \$10 上限的 6.5 倍**。故 289 题**未跑完**:只跑通 single-session-preference **28/30 库(93.3%)**,另三切分(multi-session 133 / single-session-user 70 / single-session-assistant 56)**报阻塞,零数字**。

---

## 一、覆盖与阻塞(逐格如实)

| 考场 | 目标 | 实跑 | 状态 |
|---|---|---|---|
| LME single-session-preference | 30 | **28**(smoc + direct 配对全跑) | 完成 93.3%;缺 uid `07b6f563`、`0a34ad58`(建卡进行中被预算闸停) |
| LME multi-session | 133 | 0 | **BLOCKED**:建卡 \$25.42 |
| LME single-session-user | 70 | 0 | **BLOCKED**:建卡 \$13.38 |
| LME single-session-assistant | 56 | 0 | **BLOCKED**:建卡 \$10.70 |
| MAB-FC mh_6k | 100 | **100 × 2 臂** | 完成 |
| MAB-FC mh_32k | 100 | **100 × 2 臂** | 完成 |

**排除的 2 个 uid 不是挑出来的**:三个建卡分片按文件顺序轮转取 uid,预算闸在第 28 个卡片落盘时停机,剩下的是"最后完成的两个",与题面内容无关。名单已落 `scratchpad/b33i_ssp_subset.json`,可复核。**这仍是一个非随机的停止规则,如实标注。**

**为什么选 single-session-preference 而不是 multi-session**:$10 上限只够一条切分,选能**做满一格**的最小切分(30 库),使记录表里多一个"完整格"而不是四个各 8 题的碎格。**代价必须同页写明**:该切分是四条里对卡片路线**最不利**的一条(答案在单会话内、金标是评分量表、不需要跨会话聚合),因此 §〇.1 的否定**只能覆盖 preference 型,不能外推到 multi-session**。multi-session 才是与 LME-TR(卡片臂 +12.78pp 胜出)同形的那条,它**仍未被测**。

---

## 二、结果表

### 2.1 LongMemEval · single-session-preference(n=28 配对,1 题/库,簇=题)

| 臂 | 正确 | 准确率 | in/题 | out/题 | 读端 \$/题 | 判官 \$/题 | 延迟 | 产物 |
|---|---|---|---|---|---|---|---|---|
| **smoc**(卡片账目 + F.1 提示词) | 12/28 | **42.86%** | 4,271 | 537 | \$0.00696 | \$0.00756(实测) | 11.4s | `results/b33i_lme_ssp_smoc.jsonl` |
| **direct**(稠密 top-10,OpenAI 嵌入) | 20/28 | **71.43%** | 7,049 | 252 | \$0.00831 | \$0.00756(换算) | 5.1s | `results/b33i_lme_ssp_direct.jsonl` |

配对:**Δ = −28.57pp**,W/L/T = 3/11/14,精确符号检验 **p = 0.0574**,自助 95% CI(10,000 次,种子 20260902)**[−50.00, −3.57]**。
**内部张力如实报**:符号检验 p = 0.0574 未过 .05,而自助 CI 不含 0。两者检验对象不同(前者只看分歧对方向,后者看整体准确率差);此处**取更保守的一个**——"账目臂显著低于直读"这句话在 n=28 上**未达 .05**,可主张的是"点估计与 CI 都在负向,且负向幅度大到 −28.6pp"。n=28 时精确符号检验的最小可测配对差约 **21–25pp**,本轮观测值恰在门槛附近。

### 2.2 MemoryAgentBench-FC(每格 100 题,单库,簇=题)

| 格 | 臂 | 正确 | 准确率 | in/题 | out/题 | 读端 \$/题 | 延迟 | Δ vs direct | W/L/T | p | 自助 95% CI |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **mh_6k** | wt(卡片) | 12/100 | **12.00%** | 1,179 | 125 | \$0.00180 | 7.1s | **−2.00pp** | 5/7/88 | 0.774 | [−9.00, +5.00] |
| mh_6k | direct | 14/100 | **14.00%** | 998 | 103 | \$0.00151 | 2.1s | — | — | — | — |
| **mh_32k** | wt(卡片) | 12/100 | **12.00%** | 1,184 | 120 | \$0.00179 | 7.0s | **+2.00pp** | 8/6/86 | 0.791 | [−5.00, +9.00] |
| mh_32k | direct | 10/100 | **10.00%** | 1,017 | 99 | \$0.00151 | 2.1s | — | — | — | — |

产物:`results/b33i_mabfc_mh6k_{wt,direct}.jsonl`、`results/b33i_mabfc_mh32k_direct.jsonl`、`results/b33i_mabfc_mh32k_wt.jsonl`(+ 分片 `_p0/_p1`,三文件按 `question_id` 去重后恰 100 行,零重叠)。

---

## 三、三个新发现(本轮独有,均可零成本复核)

### 3.1 ⭐ `mab_fc_mh_6k` 与 `mab_fc_sh_6k` 的语料**逐字节相同**——61pp 差全归题型,不归记忆

两文件 `sessions` 段的规范化 JSON **SHA-256 完全一致**(48,992 字符,455 条事实轮次;`data/mab_fc_mh_6k.json` vs `data/mab_fc_sh_6k.json`)。差的只有 `probing_queries`:

- sh:`Which sport is goaltender associated with?` → 单跳查表
- mh:`What is the country of citizenship of the spouse of the author of Our Mutual Friend?` → 两跳组合

**因此 sh_6k 直读 75% 与 mh_6k 直读 14% 之间的 61pp,是在同一份记忆、同一检索器、同一读者下测出来的,唯一变量是问句要几跳。** 这是一个**天然的完美对照**,此前无人指出。判读:**MAB-FC 上的瓶颈是多跳组合,不是记忆表示**;任何记忆系统(我们的卡片、他们的管线)在 mh 格上的排名差异都发生在 10–14% 的地板区,**该格不具备区分记忆方案的功效**,不应作为记忆能力的证据。

### 3.2 ⭐ 同一份语料、同一建卡器,两次跑批产出 **271 vs 83** 张卡(3.3×)

| 库 | 语料 | 卡数 | in / out tok | 建卡 \$ | 覆盖率(卡/事实轮次) |
|---|---|---|---|---|---|
| `results/wt_cards/mabfc-factconsolidation_sh_6k.json`(归档) | 同上 455 轮 | **271** | 33,363 / 31,499 | \$0.1908 | 59.6% |
| `results/wt_cards_b33i_mab/mabfc-factconsolidation_mh_6k.json`(本轮) | **同一份** | **83** | 25,598 / 10,569 | \$0.0784 | **18.2%** |

两份卡片的**顶层键、13 个记录字段、`record_id` 命名(`r1,r2,…`)完全一致**,即旗标签名无差别。可见的唯一未记录变量是 08-17 之后 `QVF_CARD_TEMP0` 默认由 0 改 1(温度不落盘)。**故判读为二选一,两者都在写入侧**:①建卡器在稠密事实库上的跑批不确定性达 3.3×;②该温度默认变更把抽取量砍到三分之一。**不能主张是哪一个**,但两条都意味着"卡片库数量"这一量在该语料上**不可复现**,任何依赖卡数的成本/覆盖主张须附此限定。
对照:mh_32k 覆盖率更低,**225 卡 / 2,310 轮 = 9.7%**。

### 3.3 ⭐ `wt_qvf_prototype._catalog()` 的失败路径**丢弃已计费的 usage**,导致建卡成本系统性低报

`scripts/wt_qvf_prototype.py` 的 `_catalog()` 在异常分支 `return [], 0, 0` —— 该次 API 调用**已经发生并已计费**,但 token 用量被清零后再向上合并。mh_32k 建卡触发了这条路径:日志 `scratchpad/b33i_mab32k_write.log` 记 **8 次终态失败**(3 × `ValueError` 空目录 + 5 × `ValidationError`),而按对半递归树推算,**31 次调用里有 23 次没有被记账**(depth0–3 全部失败 15 次 + 叶层失败 8 次)。

落盘只记 **in 67,147 / out 26,572 = \$0.2000**;按叶层实测的 2.49 字符/token 反推,**未记账输入约 590,735 tok(≈\$0.59)**,未记账输出在 \$0.46(多数失败为"空目录"短输出)到 \$1.84(多数为 16k 截断)之间。**该格真实计费 ≈ \$1.25 – \$2.63,中位估 \$1.80,而账面只有 \$0.20(低报 6–13×)。**

**建议修复(未改动,留给主会话决定)**:`_catalog()` 异常分支改为把已知的 `resp.usage` 一并回传;并对事实密度高的语料把 `QVF_CATALOG_BUDGET` 调小到不触发递归。**在修复前,所有引用建卡成本的句子都应标注"仅统计成功批次"。**

---

## 四、机制:LME-SSP 上账目臂为什么输 28.6pp

| 指标 | smoc | direct |
|---|---|---|
| 弃答式作答("对话中没有这方面信息…") | **10/28 = 35.7%**(其中仅 1 题被判对) | 2/28 = 7.1% |
| 非弃答子集准确率 | 11/18 = **61.1%** | — |
| 协议偏差(无 `ANSWER:` 末行) | **0/28** | 不适用 |
| 触顶读者 `max_tokens=800` | 2/28 | 0 |
| 作答长度中位数 | 361 字符 | 1,205 字符 |

**判读:输在写入侧的召回,不是读取侧的格式。** 协议偏差为 0 说明 F.1 两段式提示词被正确遵守;失败集中在读者看着账目说"没有这类记录"。逐题核对确认了这一点——金标要的是"用户自种的樱桃番茄与罗勒""用户偏好的纪录片题材""厨房用具架",这些**软属性/偏好信号在账目里根本不存在**,而建卡器抽满了 `education / employment / camera_equipment` 这类状态型槽位。**当账目确实携带了相关内容时,账目臂与直读同档(61.1% vs 71.4%,n=18)。**

**两条次要噪声,如实报**:①2/28 因读者 800 token 预算被截断(其中 1 题答句停在 "Diversify inspiration by");②账目臂答句只有直读的 30% 长,量表型金标天然吃亏。这两条合计最多解释几个百分点,**不足以吃掉 28.6pp**。

---

## 五、自然语料记录表(合并全部 LongMemEval 切分 + LoCoMo 状态 + MAB-FC 各格)

读者一律 `claude-haiku-4-5`,判官一律 `claude-opus-5`;"卡片臂"列在 LME-KU/TR 上是 `wt_qvf`(账目+裁决读法),在 LME-SSP 上是 `smoc`(整本账目+F.1),在 MAB-FC 上是 `wt_qvf`——**三者不是同一读法,禁止跨行相减**。

| 考场 / 切分 | n | 直读 | 卡片臂 | Δ(卡片−直读) | 配对 p | 本轮? | 产物 |
|---|---|---|---|---|---|---|---|
| **LME temporal-reasoning** | 133 | 47.37% | **60.15%** (wt) | **+12.78** | 0.0115 | 归档(08-17) | `tr_full133.jsonl` / `lmetr_cardfix_20260817.jsonl` |
| **LME knowledge-update** | 78 | 78.21% | **80.77%** (wt) | +2.56 | 0.824 | 归档(08-17) | `final2_lmek_h45.jsonl` / `lmeku_cardfix_20260817.jsonl` |
| **LME single-session-preference** | **28/30** | **71.43%** | **42.86%** (smoc) | **−28.57** | 0.0574 | ✅ **本轮** | `b33i_lme_ssp_{direct,smoc}.jsonl` |
| LME multi-session | 0/133 | — | — | — | — | ❌ 阻塞 \$25.42 | — |
| LME single-session-user | 0/70 | — | — | — | — | ❌ 阻塞 \$13.38 | — |
| LME single-session-assistant | 0/56 | — | — | — | — | ❌ 阻塞 \$10.70 | — |
| **LoCoMo-300** | 300 | 80.33% | 69.3%(wt,归档表) | −11.0 | 归档 | 归档 | `locomo_direct_h45.jsonl`;wt 值取 `RESULTS_MASTER_20260811.md:64` |
| **LoCoMo-full** | 1,986 | 69.44% | —(仅 rt 72.16%) | — | — | 归档 | `locomo_full_{direct,qvf}.jsonl` |
| **LoCoMo 链抽取** | 96 链抽查 20 | — | — | — | — | **闸未过**:改判率 35%(过度合并 5/7、计划误作状态 2/7),链**不得用于任何对外数字** | `locomo_spotcheck_verdict_20260826.md` |
| **MAB-FC sh_6k**(单跳) | 100 | 75.00% | 56.00% (wt) | −19.00 | 归档 | 归档 | `mabfc_sh6k_{direct,qvf}.jsonl` |
| **MAB-FC sh_262k**(单跳) | 100 | 81.00% | 71.28%(wt,195 行去重前) | −9.72 | 归档 | 归档 | `mabfc_sh262k_{direct,qvf}.jsonl` |
| **MAB-FC mh_6k**(多跳) | 100 | **14.00%** | **12.00%** (wt) | −2.00 | 0.774 | ✅ **本轮** | `b33i_mabfc_mh6k_{direct,wt}.jsonl` |
| **MAB-FC mh_32k**(多跳) | 100 | **10.00%** | **12.00%** (wt) | +2.00 | 0.791 | ✅ **本轮** | `b33i_mabfc_mh32k_{direct,wt*}.jsonl` |

**这张表读出来的三句话**:
1. **卡片路线在自然语料上的符号不稳定**:LME-TR **+12.8**、LME-KU +2.6、LME-SSP **−28.6**、LoCoMo-300 **−11.0**、MAB-FC 四格 −19.0 / −9.7 / −2.0 / +2.0。**六个非零方向里四个为负。** 唯一稳定为正的是时序推理型(TR)。
2. **负的那几格有共同形状**:LoCoMo(实体归属)、MAB-FC(稠密事实库)、LME-SSP(偏好软属性)——都是**"要的信息不是带日期的状态更替"**的场合;卡片 schema 的强项(`stated_date` + `temporal_relation` + 取代边)在这些格上无处发力,而抽取的损失(SSP 弃答 35.7%、MAB 覆盖 9.7–18.2%)照收。
3. **一格没有区分度**:MAB-FC 两个 mh 格四臂全在 10–14%,该格测的是多跳组合,不是记忆(§3.1 的同语料对照证明)。**不应写进"记忆系统同台表"。**

---

## 六、成本账(全部由 usage token 复算)

| 条目 | in tok | out tok | USD |
|---|---|---|---|
| 建卡 · LME-SSP(28 库) | 3,873,563 | 295,449 | **\$5.3508**(\$0.1911/库) |
| 建卡 · MAB-FC(2 库,仅成功批次) | 92,745 | 37,141 | **\$0.2784** |
| 读端 · 六臂合计(456 题次) | — | — | **\$1.0890** |
| 判官 · LME-SSP smoc(28 次,逐行实测) | 8,970 | 6,674 | **\$0.2117** |
| 判官 · 其余五臂(428 次,冻结跑批器不落盘,按 \$/次换算) | — | — | **\$1.3157** |
| OpenAI 嵌入(LME 13.7M 字符 + MAB) | — | — | **\$0.0804** |
| **合计(usage-token 口径)** | | | **\$8.33** |
| 追加:mh_32k 建卡失败批次的未记账计费(§3.3 重建) | | | **+\$1.05 ~ +\$2.43(中位 \$1.60)** |
| **合计(含重建)** | | | **\$9.38 ~ \$10.76(中位 \$9.93)** |

**判官 \$/次的两个基准**:LME-SSP 实测 **\$0.00756/次**(量表金标 + 长答句,320 in / 238 out);归档 LME-TR 实测 **\$0.00276/次**(短金标)。MAB 各臂金标为单词级(如 `Belgium`),按 \$0.00276 换算;LME direct 与 smoc 同题同金标,按 \$0.00756 换算。

**对上限的诚实结论**:按任务书指定的口径(**cost from usage tokens**)本轮为 **\$8.33,在 \$10 之内**;但把 §3.3 重建的未记账部分计入后,中位估 **\$9.93**、上界 **\$10.76**,**上界可能已越过 \$10**。这一不确定性**完全来自冻结建卡器丢弃失败调用的用量**,在跑之前不可知;发现后已立即停掉 LME 建卡分片(28/30 而非 30/30)以留出余量。

---

## 七、复现命令(逐字,可直接重跑)

```bash
# 0) 适配四条剩余切分(零成本)
for q in multi-session single-session-user single-session-assistant single-session-preference; do
  PYTHONUTF8=1 python scripts/adapt_lme_for_wt.py $q
done

# 1) LME single-session-preference 建卡(新目录;$0.1911/库)
PYTHONUTF8=1 QVF_EMBED_BACKEND=openai python scripts/wt_qvf_prototype.py --phase write \
    --data data/lme_single_session_preference_wt.json --cards-dir results/wt_cards_b33i_lme \
    --uids "<逗号分隔 uid 子集,分片并行用>"

# 2) smoc 臂(账目 + 附录 F.1 提示词;渲染器/提示词/解析全部 import 自冻结的 repro_batch3.py)
PYTHONUTF8=1 python scripts/b33i_smoc_arm.py \
    --data data/lme_single_session_preference_wt.json --cards-dir results/wt_cards_b33i_lme \
    --qtype single-session-preference --out results/b33i_lme_ssp_smoc.jsonl

# 3) direct 臂(必须 openai 嵌入;qid 文件把两臂钉在同 28 库)
PYTHONUTF8=1 QVF_EMBED_BACKEND=openai python scripts/run_decisive_stale.py \
    --benchmark longmemeval --data data/longmemeval_s_cleaned.json \
    --qtype single-session-preference --qid-file scratchpad/b33i_ssp_qids.txt \
    --conditions dense_direct --reader claude-haiku-4-5 \
    --out results/b33i_lme_ssp_direct.jsonl --resume

# 4) MAB-FC 两格:建卡 → wt 臂 → direct 臂
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

# 5) 统计与成本($0)
PYTHONUTF8=1 python scripts/b33i_report.py
```

## 八、产物清单

**新建卡片库(建后只读,未覆盖任何既有目录)**
- `results/wt_cards_b33i_lme/`(28 个 LME-SSP 库)
- `results/wt_cards_b33i_mab/`(2 个 MAB-FC 库:mh_6k 83 卡 / mh_32k 225 卡)

**跑批产物**
- `results/b33i_lme_ssp_smoc.jsonl`(28)、`results/b33i_lme_ssp_direct.jsonl`(28)
- `results/b33i_mabfc_mh6k_wt.jsonl`(100)、`results/b33i_mabfc_mh6k_direct.jsonl`(100)
- `results/b33i_mabfc_mh32k_wt.jsonl`(34)+ `_wt_p0.jsonl`(33)+ `_wt_p1.jsonl`(33)= 去重后 100
- `results/b33i_mabfc_mh32k_direct.jsonl`(100)

**新脚本(未修改任何冻结原件)**
- `scripts/b33i_smoc_arm.py` —— 任意 wt-schema 语料上的 smoc 臂;渲染器 / 提示词 / 解析 / 读者常量全部 `from repro_batch3 import`,本文件只负责换语料源与把**真实考场 question_type**(而非 `stale_chain` 载入器的 `chain-q1`)传给判官,使两臂在判官提示词上同口径。**这是与 08-17 归档 KU/TR 轮的唯一协议差异,必须同页写明**:那两轮的卡片臂给判官的是 `chain-q1`,量表型金标下会系统性吃亏,故本轮不沿用。
- `scripts/b33i_stats.py`、`scripts/b33i_report.py` —— 配对精确符号检验 / 自助 CI / 成本复算,零 LLM。

**新数据(适配器产物,零成本)**
- `data/lme_multi_session_wt.json`、`data/lme_single_session_user_wt.json`、`data/lme_single_session_assistant_wt.json`、`data/lme_single_session_preference_wt.json` —— 289 题全部已适配好,**建卡之外的准备工作已完成**,解封预算即可续跑。

---

## 九、后续(按性价比排序,均已备好命令)

1. **multi-session 133 题(\$25.4 建卡 + \$4.4 读判 ≈ \$30)** —— 这是唯一与 LME-TR 同形(跨会话聚合)的剩余切分,也是 §〇.1 的负结论**唯一可能被翻转**的地方。不跑它,"卡片路线在自然语料上"这句话就只有一正一负两个极端锚点。
2. **修 §3.3 的用量丢弃**(\$0)——一行改动,之后所有建卡成本主张才可审计。
3. **验 §3.2 的建卡不确定性**(\$0.08 × 3)—— 在同一份 `mab_fc_sh_6k` 语料上重建 3 次,看卡数落在 83 还是 271 附近,即可把"跑批不确定性"与"温度默认变更"分开。这是**本轮最便宜、最能定分界的实验**。
4. **MAB-FC mh 两格不再投入**——§3.1 已证明该格测的是多跳组合、四臂全在地板区,继续加臂不产生信息。
