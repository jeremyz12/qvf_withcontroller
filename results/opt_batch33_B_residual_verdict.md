# 批 33-B 判决:v2.4 头条 90.45 的 55 条残余失败归类

预注册:`results/opt_batch33_prereg.md` §33-B(判据 B1:金标类占比 < 20%)。
上游:`results/ladder_decontamination_20260902.md` §二。成本 $0.04(仅 (e) 步复裁),零建店、零改店。

## 判决

**判据 B1 被满足。金标类 = 4/55 = 7.27%(Wilson 95% CI 2.86–17.26),远低于 20% 阈值;
保留集规范不必加"金标平局"闸。** 残余失败的主体不是读者:**写侧 38/55 = 69.09%**。
更进一步,写侧里 **29/38(76.32%)不是"值没抽到",是"值抽到了但落在别的槽位名下"** ——
残余 9.55pp 的多数是**账目槽位标注**问题,不是抽取覆盖问题,也不是读者推理问题。

## 一、复现与前提

三文件按 question_id 覆盖拼接(v22 ← v23 ← v24):n=576 / 正确 521 / **acc 90.45** / 错 55,
逐题型 {longest_tenure 17, count_before 16, change_count 17, first_vs_last 5} —— 与 §二 逐字一致。
行来源:v22 412 行 / v23 104 行 / v24 60 行。

复现性旁注(自查):`results/wt_cards_v44clean` 的三波建店(09-01 15–16h 103 店 / 18h 26 店 / 09-02 01h 15 店)
与"该 uid 存活行所属跑批的完成时间"逐一比对,**漂移 uid = 0**(`store_drift_uids: []`)——
被覆盖的店恰好都是后续跑批重读过的那些,拼接后的每一行都对应盘上现存的那本账目。

## 二、口径变更(必须记录)

`card_quality_eval.card_sequence` 按 `slot_class == target_slot` 过滤,但 v44clean 的
**8313 条记录全部无 `slot_class` 字段**,该过滤在本店退化为 144/144 全 `zero_cards`
(脚本照打此退化证据:`cqe_strict_slot_class_modes: {"zero_cards": 144}`)。
故账目链改由冻结生产路径 `_select_pool_frozen`(无键回退支 = `_slot_match` 槽位词重叠)+ `_chain` 产出;
**四模式分类函数 `classify_failure` 与金链规约 `source_sequence` 逐字复用 card_quality_eval**。

## 三、三大类(n=55,Wilson 95% CI)

| 类 | n | 占比 | 95% CI | 判定规则 |
|---|---|---|---|---|
| 写(账目本身不足以推出金标) | 38 | 69.09 | 55.97–79.72 | 冻结执行器在重渲染账目上复算 ≠ 金标 |
| 读(账目已含答案,读者算错) | 13 | 23.64 | 14.37–36.35 | 复算 == 金标 且账目链长 == 金链长 |
| 金标 + 判官 | 4 | 7.27 | 2.86–17.26 | 读侧残渣中 longest_tenure 头两名任期相对差 ≤1% |

执行器口径校验(关键):在**金链**上复算 576/576 全中 —— 执行器就是 gen_wsc_v2 的金标算式,
它在账目上失手 100% 由账目链缺陷解释(`write_mode == correct` 且执行器失手的行 = **0**)。

金标类的 4 条(全部 longest_tenure,并列被"天"级算术打破,整年粒度下相等):
`wikiP54004-Q29589370_v2lt`(1827 vs 1826 天,差 0.055%)、
`wikiP54019-Q67283693_v2lt`(731 vs 730,0.137%;§二 已点名,读者答案原话即"tied … 2 years each")、
`wikiP108026-Q56530701_v2lt`(4048 vs 4018,0.741%;另有 Weill Cornell Medical Center→Weill Cornell Medicine 改名被记成一次变更)、
`wikiP39037-Q3525068_v2lt`(3793 vs 3763,0.791%)。
判据不敏感:换成"整年粒度相等"口径,三大类计数逐一不变(38/13/4)。

## 四、五小类子表(card_quality_eval 四模式 + correct × 三大类)

| 账目链 vs 金链 | 写 | 读 | 金标 | 小计 |
|---|---|---|---|---|
| correct(逐值全等) | 0 | 11 | 3 | 14 |
| zero_cards(该槽位零链) | 11 | 0 | 0 | 11 |
| missing_value(漏值) | 21 | 0 | 0 | 21 |
| extra_value(多值) | 4 | 0 | 0 | 4 |
| wrong_value_or_order(等长错值/错序) | 2 | 2 | 1 | 5 |
| 小计 | 38 | 13 | 4 | 55 |

逐题型:change_count 写12/读5;count_before 写10/读6;longest_tenure 写11/读2/金标4;first_vs_last 写5/读0/金标0
(**5 条 first_vs_last 全部是写侧**,人工逐条看过:`wikiP108010` 零链、`wikiP108012` 与 `wikiP39020` 账目只剩 1 个状态、
`wikiP108046` 缺末态;另有 2 条读者被账目里的**无日期填充卡**当成"首个状态"——
`wikiP39016` 答 "team leadership"(卡 `team_leadership: leads a team`,源句"I'm planning a team outing"),
`wikiP39020` 答 "graphic designer"(卡 `occupation: graphic designer`,源句是一句谈文件存储的填充),两卡均无日期)。

写侧再分(n=38):**write_B 值在场但选不出 29(76.32,CI 60.79–87.01)** vs write_A 值根本缺失 9(23.68,CI 12.99–39.21)。
典型:`wikiP108010-Q53284080` 的金链值以 `education_institution: Syracuse University` /
`employment: research physicist at CERN` 入账,槽位名不是 `employer`,冻结选池零命中。

## 五、三条独立事实(全部复算,与 §二 一致)

1. **链聚集**:55 错落在 **35/144 链**,分布 {1错:21, 2错:8, 3错:6}。
   独立二项(p=55/576=0.0955、每链 4 题)期望 40.70 / 6.45 / 0.45,**≥3 错尾部富集 13.3×**。
   机制现已定位:账目链与金链**不全等的店** 56/144,其上 224 题错 41(18.30%,CI 13.79–23.89);
   全等的店 352 题错 14(3.98%,CI 2.38–6.56)——**富集 4.6×**。聚集是店级属性,不是逐题读者噪声。
2. **计数方向少数为主**:计数型 33 题(cc 17 + cb 16)= 少数 24 / 多数 9。
   与执行臂的多数为主(+1 占 22/28,批 15)镜像:少数 = 账目没呈现的转移;多数 = 执行器凭空发明的转移。
3. **金标平局的基率对照**(全部 144 道 longest_tenure):头两名相对差 ≤1% 的 16 题错 6(37.50%),
   >1% 的 128 题错 11(8.59%),**富集 4.37×,Fisher 单侧 p=0.0043**。金标平局是可测的错误源,只是量小。

附带上界:同一本账目上,冻结选池+执行器只答对 **407/576 = 70.66**,读者 521/576 = 90.45。
读者比冻结选池多救回 132 题 —— 读者的增量价值主要在**跨槽位名读账**,这正是 write_B 那 29 条的镜像。

## 六、(e) 步独立复裁(claude-haiku-4-5,两遍,$0.0395)

22 题(读侧残渣 13 + 金标 4 + 全部 fvl 5)× 2 遍 = 44 次调用。两遍自一致 17/22(2 次 JSON 解析失败)。
- 写侧:4/5 判 `ledger_insufficient`,与本脚本一致;
- 读侧:11–12/13 判 `model_wrong`,与本脚本一致;
- **金标平局:复裁器不认**。4 条里只有 `wikiP54019`(读者自己写了"tied")在 pass1 被判 `gold_ambiguous`,
  另 3 条两遍全判 `model_wrong`。
**判读:同档单遍 LLM 复裁不能发现"天级算术打破的并列",这条与既有结论(单遍 LLM 复核不可替代人工)一致;
金标类的依据是任期天数差的算术 + 上节 4.37× 富集,不是复裁器的背书。**
敏感性:若采信复裁器,金标类降为 1/55 = 1.82%;若把全部"整年粒度并列"的 lt 错都算金标,升为 7/55 = 12.73%。
**三种口径下 B1 均通过。**

## 七、下一步(不在 33-B 范围内,记录以便定价)

- write_B 是可修的:槽位名归一(`QVF_OPEN_SLOT` / `QVF_SLOT_STRICT` 已有旗标)直接对着 29/55 = 52.7% 的残余错。
- 33-F 的 oracle 卡臂(F2)应与本表互证:F2 与 90.45 的差应 ≈ 写侧 38 条的上限。
- 金标平局虽 <20%,数据表规范仍宜记一句"longest_tenure 的唯一性只在天粒度上成立,16/144 题头两名差 ≤1%"。

## 八、复现命令与产物

```bash
cd D:/ZZL_cluade
PYTHONUTF8=1 python scripts/residual_taxonomy.py      # $0,主流程 (a)-(e)
PYTHONUTF8=1 python scripts/b33B_adjudicate.py        # $0.0395,(e) 步独立复裁
```

新增脚本:
- `scripts/residual_taxonomy.py`
- `scripts/b33B_adjudicate.py`

产物(均新建,未写入任何既有卡店目录):
- `results/b33B_merged_v24.jsonl` —— 重建的 576 行头条跑(带 `_source_file` 溯源)
- `results/b33B_ledgers.jsonl` —— 144 uid 的重渲染账目全文(render_card_ledger,整本视图)
- `results/b33B_writeside.jsonl` —— 逐 uid 账目链 / 金链 / 四模式 / 任意槽位值覆盖
- `results/b33B_taxonomy.jsonl` —— 逐题 576 行归类(三大类标签、执行器复算、任期并列间距)
- `results/b33B_summary.json` —— 全部聚合数字
- `results/b33B_handinspect.md` —— (e) 步人工检视清单 22 条(judge_reason 随行)
- `results/b33B_adjudication.jsonl` —— haiku 两遍复裁逐题标签
- `results/opt_batch33_B_residual_verdict.md` —— 本文件

读入(只读):`results/b31_smoc_v22_full.jsonl`、`results/b31_smoc_v23.jsonl`、`results/b31_smoc_v24.jsonl`、
`results/wt_cards_v44clean/`(144 店)、`data/wikistate_full_ALL_v24.json`。
