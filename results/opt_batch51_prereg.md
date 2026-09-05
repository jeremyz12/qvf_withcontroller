# 批 51 预注册 — 主线配置:完整契约 + 闭集槽位规则 + 值规范化 + 状态链槽位类蕴含过滤,Stage 1 关;WikiState 全量 + STALE + MemOps

写于任何建店/读者调用之前(2026-09-05)。用户批准的问题:"最通用、效果最好的版本"要作为一个完整的店建出来,在三个考场同一配置报数。

## 配置(冻结)
- 建卡器 `scripts/wt_qvf_prototype_v49.py`:QVF_CARD_KEYS=1(V4 提示词闭集 slot_class + owner),QVF_CARD_VALNORM=1,QVF_CARD_SLIM=0(完整契约 ExtractedRecord),QVF_CARD_STAGE1_K=0,QVF_CARD_FAIL_LOUD=2。
- 抽取器与各自基线同族:WikiState claude-sonnet-5(TEMP0=0,THINKING=off;对照 v48f / v45),STALE、MemOps claude-haiku-4-5(对照批 19 旧建卡)。
- 蕴含过滤 `scripts/b47_entail_verify.py --chain-slots`:只审 slot_class ∈ {position, employer, team, residence, device, location, relationship} 的卡,按断言类型丢 plan/task/other_person/hypothetical/restate,保留 start/unclear/ended;other:* 卡不审、保留。
- 渲染:默认(不开 QVF_LEDGER_FLAGS),与旧结果同版式。
- 店:`results/wt_cards_v55` → `v55f`;`results/ext_cards_stale_v55` → `v55f`;`results/ext_cards_memops_v55` → `v55f`。

## 判据
- H1 WikiState 560 题 haiku 两轮均值 ≥ 92.5(v48f 90.0 + 2.5);对 v48f 配对 McNemar 与 144 链簇自助 CI;预期 93–95。
- H2 STALE 120 题 ≥ 58.7(旧建卡 61.7 − 3);MemOps ≥ 49.5(旧 52.5 − 3)。任一考场掉 ≥ 5 且 p < 0.05 判"主线配置不通用"。
- H3 WikiState sonnet-5 140 题 ≥ 92(v47skf 95.0 − 3)。
- H4 成本 ≤ $45。

硬约束:既有店与结果只读;新店新目录;判官、题集、读者提示词与批 19 / 46d / 38e 逐字同。
