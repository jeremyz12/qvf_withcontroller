# 批 50 预注册 — 通用版写侧配置在三个考场上的同一配置验证

写于任何建店/读者调用之前(2026-09-04)。问题来自用户:"修改后的是否还能通用?不通用就完全无法使用。"

## 通用版配置(冻结)

- 契约:QVF_CARD_SLIM=2(七字段精简契约 + owner/slot_class 规范键 + 可选 `ended`、`condition`),QVF_CARD_KEYS=1,QVF_CARD_VALNORM=1;**Stage 1 关**。
- 蕴含过滤:`scripts/b47_entail_verify.py`,按断言类型丢 plan / task / other_person / hypothetical / restate,**保留 ended**(标记不丢);WikiState 用 --lane-only,第三方考场审全店。
- 渲染:QVF_LEDGER_FLAGS=1 时账目行对 ended 卡加 "ENDED:" 前缀、对 condition 追加 "(only: …)";默认关,旧结果逐字节不变。
- 抽取器与各自基线同族:STALE / MemOps 用 claude-haiku-4-5(批 19 旧建卡是 haiku),WikiState 用 claude-sonnet-5(与 v53sf / v52f 同)。

## 考场与对照

- STALE:40 店 120 题(批 19 新鲜样本),对照旧建卡 61.7、直读 46.7;分维度报。
- MemOps:40 店 120 题,对照旧建卡 52.5、直读 48.3。
- WikiState:36 链 140 题(与 v53sf 同链),对照 v53sf 95.7(无 ended/condition)、v52f 95.7 / 94.3(带 Stage 1)、v48f 90.0。

## 判据

- H1(通用):三个考场上通用版对各自旧建卡的差都在 −3pp 以上(点估计),且没有一处 McNemar p < 0.05 的下降。任一考场掉 ≥ 5pp 且 p < 0.05 即判"不通用",并定位到字段。
- H2(WikiState 代价):通用版对 v53sf 的差在 ±3pp 内。
- H3(成本):建店 + 蕴含 + 读者 + 判官 ≤ $32。

硬约束:既有店与结果只读;新店新目录(ext_cards_stale_v54、ext_cards_memops_v54、wt_cards_v54s 及 *_f);判官、题集、读者提示词与批 19 / 38e 逐字同。
