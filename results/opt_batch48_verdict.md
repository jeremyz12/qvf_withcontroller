# 批 48 判词 — 冻结"评审修复"配置全量落地:144 链重建 + 蕴含过滤 + 560 题两轮读者

预注册:`results/opt_batch48_prereg.md`(先于建店)。配置:claude-sonnet-5,QVF_CARD_TEMP0=0,QVF_CARD_THINKING=off,QVF_CARD_SLIM=1,QVF_CARD_STAGE1_K=8,QVF_CARD_VALNORM=1,QVF_CARD_FAIL_LOUD=2 → `results/wt_cards_v51`;`scripts/b47_entail_verify.py --lane-only` 按断言类型过滤 → `results/wt_cards_v51f`(标签全集 `wt_cards_v51f_ent`)。读者 claude-haiku-4-5,smoc 臂,`data/wsc_s5_v25.jsonl` 560 题两轮。评分 `scripts/b48_score.py`、`scripts/b47_score.py`。既有店只读。

## 0. 判决(先判决,后数字)

- **H1(编译上限 ≥ 92.5%)被证实,幅度远超预期。** v51 未过滤 98.4%(551/560),v51f 98.8%(553/560);v48f 92.5%,v45 85.9%。金标行 542/542 全部命中(v48f 528/542,v45 471/542),车道多出行 2(v48f 85,v45 79)。这是本项目第一次在全量 144 链上做到账目与金标零漏行。
- **H2(读者与 v48f 等价)未达等价判据,方向为正、不显著。** v51f 两轮都是 91.43(558/560 逐题一致);对 v48f run1 +1.61(McNemar p = 0.28),对 run2 +1.25(p = 0.41),144 链簇自助 95% CI [−1.6, +4.8] 跨零;90% CI [−1.1, +4.3] 超出 ±3pp,TOST 不判等价。对 v45 +2.14(p = 0.16)。与批 46d 的规律一致:账目上限从 92.5 升到 98.8,读者只动了 1 到 2 个点。
- **H3(读者输入 token ≤ 2,753)被证实。** 每题 1,013 入 token(−63%),$0.00335 一题(v48f $0.00518,−35%);账目从每店 50 张卡缩到 15.6 张。
- **H4(漏行 ≤ 14,过滤零误伤)被证实。** v51 → v51f 金标行 542 → 542,0 处 hit→miss。
- **H5(成本 ≤ $14)被证实。** 建店 $3.25 + 蕴含 $0.79 + 两轮读者 ≈ $3.8 = **≈ $7.8**。

综合读法:评审提出的四项写侧修改(精简 schema、两阶段抽取、语义校验、值规范化)合在一起,把账目质量推到了接近金标的水平,并把建店和读时成本各降了一个量级或三分之一;读者准确率有正向但不显著的变化。读者的剩余错误(48/560)不再是账目缺行或多行造成的:账目上限 98.8 与读者 91.4 之间的 7.4 个点是读者自己的错(见 §4)。

## 1. 写侧诊断(144 链,542 金标行,560 题;b46d 口径)

| 店 | 配置 | 卡/店 | 建店 in/out per store | 金标行 | 漏行 | 车道多出行 | 编译上限 | change_count | count_before | first_vs_last | longest_tenure |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v45(批 33) | haiku,完整 schema | 57.6 | 21,381 / 7,828 | 471 | 71 | 79 | 481/560 = 85.9% | 123 | 126 | 123 | 109 |
| v48f(批 46d) | sonnet,完整 + 第二遍 + 关键词过滤 | 50.6 | 25,940 / 8,174 | 528 | 14 | 85 | 518/560 = 92.5% | 130 | 129 | 137 | 122 |
| **v51** | sonnet,SLIM + STAGE1_K=8 + VALNORM | 16.2 | 2,459 / 1,767 | **542** | **0** | 4 | 551/560 = 98.4% | 140 | 139 | 144 | 128 |
| **v51f** | v51 + 蕴含类型过滤 | 15.6 | — | **542** | **0** | **2** | **553/560 = 98.8%** | 141 | 140 | 144 | 128 |

Stage 1:每店平均从 165 轮里保留 18.7 轮(11.4%);Sonnet 只读候选轮次,输入 token 从 25,940 降到 2,459。蕴含过滤:2,335 张卡里审 680 张车道卡(start 581、restate 55、other_person 11、task 10、plan 10、ended 7、unclear 6),丢 93 张;$0.79。值规范化改动 26 个值。

## 2. 读者(claude-haiku-4-5,560 题)

| 运行 | 准确率 | change_count | count_before | first_vs_last | longest_tenure | in/q | out/q | $/q | 中位延迟 | 撞上限 |
|---|---|---|---|---|---|---|---|---|---|---|
| v51f run1 | **91.43** | 93.1 | 83.3 | 99.3 | 89.8 | 1,013 | 467 | $0.00335 | 5.10 s | 3 |
| v51f run2 | **91.43** | 92.4 | 83.3 | 99.3 | 90.6 | 1,013 | 468 | $0.00335 | 5.13 s | 2 |
| v48f run1(46d) | 89.82 | 86.1 | 86.8 | 96.5 | 89.8 | 2,753 | 486 | $0.00518 | 5.79 s | 1 |
| v48f run2(46d) | 90.18 | 86.8 | 87.5 | 96.5 | 89.8 | 2,753 | 485 | $0.00518 | 5.74 s | 1 |
| v45(33-A) | 89.29 | 85.4 | 86.8 | 94.4 | 90.6 | 2,937 | 476 | $0.00532 | 4.84 s | 0 |
| direct(33-A) | 47.32 | 35.4 | 42.4 | 79.9 | 29.7 | 878 | 86 | $0.00131 | 1.55 s | 0 |

两轮 558/560 逐题一致,运行间差 0.0pp。

## 3. 配对检验

| 比较 | delta | A-only / B-only | McNemar p | 144 链簇自助 95% CI | 90% CI(TOST ±3) |
|---|---|---|---|---|---|
| v51f run1 vs v48f run1 | +1.61 | 32 / 23 | 0.281 | [−1.59, +4.80] | [−1.07, +4.25] 不等价 |
| v51f run2 vs v48f run2 | +1.25 | 30 / 23 | 0.410 | [−1.78, +4.30] | [−1.27, +3.78] 不等价 |
| v51f run1 vs v45 | +2.14 | 37 / 25 | 0.162 | [−1.24, +5.55] | — |
| v51f run1 vs direct | **+44.11** | 261 / 14 | 4e-60 | [+39.4, +48.7] | — |

## 4. 读者错在哪(账目 98.8 对读者 91.4)

分题型:change_count 86.1 → 93.1(账目上限 141/144),first_vs_last 96.5 → 99.3(144/144),longest_tenure 持平 90(128/128 上限);**count_before 86.8 → 83.3**,而账目上限 140/144。count_before 是"某日期之前有几种状态"这类题,账目已经给出完整链,读者在日期截断上仍会错;账目变短没有帮它,反而少了 1 到 2 题。这是下一步该看的读者侧问题,不是写侧问题。

## 5. 与预注册的偏离

- 无。配置、判据、对照与预注册一致;H2 按预注册写法记"未达等价判据",不记"提升"。

## 6. 边界

- Stage 1 的查询只覆盖四个金标槽位类(employer / position / team / residence),与 WikiState 的题集同构;通用记忆要为 schema 里其余类目(device / location / relationship / other)补查询,或对非候选轮次保留一遍粗抽取。v51 每店只剩 15.6 张卡,非金标槽位的状态基本没有入库。
- 蕴含审计只审车道卡;非车道卡标 unjudged 保留。
- 读者只跑了 haiku;强读者(Sonnet 5)在 v51f 上未测。
- 账目上限 98.8 是离线编译答案对金标的命中率,不是读者;两者之差是读者误差。

## 7. 成本

| 项 | $ |
|---|---|
| v51 建店(144 链,Sonnet,两阶段 + 精简) | 3.25 |
| 蕴含审计(680 车道卡,haiku) | 0.79 |
| 读者两轮(1,120 题,haiku) | ≈ 3.76 |
| 嵌入 | ≈ 0.02 |
| **合计** | **≈ 7.8** |

## 8. 精确命令

```bash
for i in 0 1 2 3; do QVF_CARD_SLIM=1 QVF_CARD_STAGE1_K=8 QVF_CARD_VALNORM=1 QVF_CARD_FAIL_LOUD=2 QVF_CARD_MODEL=claude-sonnet-5 QVF_CARD_TEMP0=0 QVF_CARD_THINKING=off PYTHONUTF8=1 python -u scripts/wt_qvf_prototype_v49.py --phase write --data data/wikistate_full_ALL_v24.json --cards-dir results/wt_cards_v51 --uids "$(cat results/b48_shard$i.txt)" & done
PYTHONUTF8=1 python scripts/b47_entail_verify.py --src results/wt_cards_v51 --dst results/wt_cards_v51f --lane-only --workers 8 --tag b48
PYTHONUTF8=1 python -u scripts/lb_reader_arm_b36b.py --reader anthropic:claude-haiku-4-5 --arm smoc --questions data/wsc_s5_v25.jsonl --data data/wikistate_full_ALL_v24.json --cards-dir results/wt_cards_v51f --out results/b48_smoc_v51f_haiku_run1.jsonl --max-tokens 800 --workers 4 --budget 60   # run2 同,--out ..._run2.jsonl
PYTHONUTF8=1 python scripts/b48_score.py
```
