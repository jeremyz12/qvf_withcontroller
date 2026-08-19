# 全族统计检验错误控制重算(2026-08-20,$0)

收集条目 218,去重后 216;入 α 族 142(Holm/BH 双口径,α=q=0.05);LTT/仅CI 另列 74。
口径规则见 scripts/family_error_control.py 文件头(先于计算写死)。

## α 族总表(按 p 升序)

| # | 检验 | p(口径) | 原文显著? | Holm | BH-FDR | 校正后判定 |
|---|---|---|---|---|---|---|
| 1 | S5 修正后定稿 418 题 编译臂 vs 直读(b1_s5_corrected_20260816.md) | 1.59e-29(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 2 | B1 S5 418 定稿并集:编译臂 vs 直读(b1_s5_corrected_20260816.md) | 1.59e-29(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 3 | QVF_DATE_STRICT 183 题 McNemar(s51_date_strict_prereg.md) | 2.03e-29(精确(χ²=126.82,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 4 | QVF_DATE_STRICT 处理组 183 题(McNemar)(s51_date_strict_prereg.md) | 2.03e-29(精确(χ²=126.82,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 5 | 编译臂 vs full-context McNemar(set_vs_replacement_prereg.md) | 4.84e-26(精确(χ²=111.4,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 6 | 编译臂 vs full-context(set_vs_replacement_prereg.md) | 4.84e-26(精确(χ²=111.4,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 7 | S5 编译臂 vs 提示词臂 McNemar(s5_prompt_arm_prereg.md) | 6.41e-26(精确(χ²=110.84,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 8 | S5 编译臂 vs 提示词臂(McNemar)(s5_prompt_arm_prereg.md) | 6.41e-26(精确(χ²=110.84,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 9 | 预算匹配 A vs 编译臂 McNemar(token_matched_prereg.md) | 6.46e-24(精确(χ²=101.7,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 10 | A 臂 vs 编译臂(token_matched_prereg.md) | 6.46e-24(精确(χ²=101.7,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 11 | 编译臂 vs B McNemar(token_matched_prereg.md) | 5.92e-21(精确(χ²=88.2,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 12 | 编译臂 vs B 臂(token_matched_prereg.md) | 5.92e-21(精确(χ²=88.2,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 13 | P108-ext wt_qvf vs 直读(旗舰①,簇校正)(redteam_cluster_attribution_) | 3.58e-18(聚类稳健) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 14 | 聚类稳健:P108-ext wt_qvf vs 直读(旗舰①)(redteam_cluster_attribution_) | 3.58e-18(聚类稳健) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 15 | v4.1 STALE 全量同题配对(题级符号检验)(VERSION_LEDGER.md) | 6.4e-15(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 16 | S5 编译臂 vs 直读(旗舰②,簇校正)(redteam_cluster_attribution_) | 1.19e-14(聚类稳健) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 17 | 聚类稳健:S5 complex_arm vs 直读(旗舰②)(redteam_cluster_attribution_) | 1.19e-14(聚类稳健) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 18 | STALE 全量头条补 400 条目簇校正(QVF_experiment_audit_2026081) | 2.2e-14(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 19 | 机制③ Fisher 检验自我否定(QVF_new_mechanisms_feasibili) | 5.97e-13(点值) | 否 | ✅ | ✅ | (原文即不显著) |
| 20 | P108-w2 wt_qvf vs 直读(簇校正)(redteam_cluster_attribution_) | 3.82e-11(聚类稳健) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 21 | heldout_stale minimal_rules vs 直读(redteam_cluster_attribution_) | 7.05e-11(聚类稳健) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 22 | S5 头条按证据完整性分层(QVF_experiment_audit_2026081) | 2.69e-10(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 23 | S5 头条检索覆盖度分层(QVF_experiment_audit_2026081) | 2.69e-10(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 24 | P39 同预算头条补簇校正(QVF_experiment_audit_2026081) | 4.21e-09(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 25 | filter-only vs 提示词臂 McNemar(s5_selection_vs_computation_) | 4.97e-09(精确(χ²=34.2,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 26 | filter-only vs 提示词臂(选择的价值)(s5_selection_vs_computation_) | 4.97e-09(精确(χ²=34.2,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 27 | P54-ext wt_qvf vs 直读(簇校正)(redteam_cluster_attribution_) | 5.4e-09(聚类稳健) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 28 | P39-ext wt_qvf vs 直读(簇校正)(redteam_cluster_attribution_) | 1.94e-08(聚类稳健) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 29 | heldout_stale qvf_v4 vs 直读(redteam_cluster_attribution_) | 3.24e-08(聚类稳健) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 30 | usability vs filter-only McNemar(s5_selection_vs_computation_) | 4.79e-08(精确(χ²=29.80,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 31 | usability vs filter-only(标注的价值)(s5_selection_vs_computation_) | 4.79e-08(精确(χ²=29.80,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 32 | S5 P39 新增 104 题 编译臂 vs 直读(b1_s5_corrected_20260816.md) | 5.71e-08(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 33 | B1 S5 P39 新增段:编译臂 vs 直读(b1_s5_corrected_20260816.md) | 5.71e-08(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 34 | Graphiti vs 同题直读(80 题)(QVF_experiment_audit_2026081) | 1.1e-07(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 35 | 在售系统同题重比:Graphiti / Mem0 vs 直读(QVF_experiment_audit_2026081) | 1.1e-07(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 36 | T1 v42 编译臂 vs 直读(参照质量库)(writeside_sensitivity_202608) | 2.46e-07(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 37 | T1 b6_rep3 编译臂 vs 直读(最低质量库)(writeside_sensitivity_202608) | 2.56e-06(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 38 | LoCoMo-full v4.2 vs 直读(簇校正复算)(QVF_experiment_audit_2026081) | 5.13e-05(点值) | 否 | ✅ | ✅ | (原文即不显著) |
| 39 | LoCoMo-full v4.2 vs 直读(−3.2pp)补簇校正(QVF_experiment_audit_2026081) | 5.13e-05(点值) | 否 | ✅ | ✅ | (原文即不显著) |
| 40 | STALE dim2_premise new vs 直读(writeside_fix_sweep_20260817) | 0.000275(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 41 | T1 参照库 v42:编译臂 vs 直读(同 76 题)(writeside_sensitivity_202608) | 0.000275(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 42 | STALE dim2_premise:new vs 直读(writeside_fix_sweep_20260817) | 0.000275(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 43 | STALE-150 新卡片臂 vs 归档卡片臂(ALL)(writeside_fix_sweep_20260817) | 0.000294(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 44 | STALE-50 新卡片臂 vs 归档卡片臂(ALL)(writeside_fix_sweep_20260817) | 0.000294(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 45 | LoCoMo 全量头条簇级复检(QVF_experiment_audit_2026081) | 0.000344(点值) | 否 | ✅ | ✅ | (原文即不显著) |
| 46 | 成员过滤后编译臂 vs 过滤前 McNemar(C2)(membership_filter_prereg.md) | 0.00048(精确(χ²=12.19,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 47 | 成员过滤器 C2 端到端恢复(McNemar)(membership_filter_prereg.md) | 0.00048(精确(χ²=12.19,1df)) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 48 | 六公开基准卷系统 vs 自家单臂(QVF_experiment_audit_2026081) | 0.00052(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 49 | 整合系统 vs 提示词单臂六卷对照(QVF_experiment_audit_2026081) | 0.00052(点值) | 是 | ✅ | ✅ | ✅ 双口径存活 |
| 50 | 新域 S1–S4:系统 vs 直读(QVF_experiment_audit_2026081) | 0.00082(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 51 | T1 最低质量库 b6_rep3:编译臂 vs 直读(writeside_sensitivity_202608) | 0.00131(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 52 | LME-KU 新卡片臂 vs 归档卡片臂(碰撞修复)(lmeku_cardfix_verdict_202608) | 0.00235(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 53 | KU record_id 修复:cardfix vs 归档卡片臂(lmeku_cardfix_verdict_202608) | 0.00235(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 54 | Mem0 vs 同题直读(QVF_experiment_audit_2026081) | 0.0024(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 55 | LoCoMo-full 卡片臂 vs 直读(簇级)(QVF_experiment_audit_2026081) | 0.0039(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 56 | LoCoMo-full 卡片臂 vs 直读(硬负结果)(QVF_experiment_audit_2026081) | 0.0039(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 57 | heldout2_stale minimal_rules_v5 vs 直读(redteam_cluster_attribution_) | 0.00434(聚类稳健) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 58 | 新域 S5 合计与逐卷(含 S1-S4 对照)(QVF_experiment_audit_2026081) | 0.00878(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 59 | 新域 S5 合计:编译臂 vs 直读(QVF_experiment_audit_2026081) | 0.00878(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 60 | LME-TR cardfix vs 提示词臂(n=133)(writeside_fix_sweep_20260817) | 0.0094(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 61 | TR cardfix vs 提示词臂(timeline-CoT)(writeside_fix_sweep_20260817) | 0.0094(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 62 | LME-TR cardfix vs 直读(剔 2 uid 敏感性,n=131)(writeside_fix_sweep_20260817) | 0.0095(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 63 | P54-w2 wt_qvf vs 直读(簇校正)(redteam_cluster_attribution_) | 0.0106(聚类稳健) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 64 | LME-TR cardfix vs 同题直读(n=133)(writeside_fix_sweep_20260817) | 0.0115(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 65 | TR cardfix vs 同题直读(writeside_fix_sweep_20260817) | 0.0115(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 66 | STALE dim1_still new vs 归档(writeside_fix_sweep_20260817) | 0.0129(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 67 | STALE dim1_still:new vs 归档(writeside_fix_sweep_20260817) | 0.0129(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 68 | LME-TR cardfix vs 提示词臂(n=131)(writeside_fix_sweep_20260817) | 0.0146(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 69 | 机制② 类型化弃答 τ=0.096(预注册判据)(QVF_new_mechanisms_feasibili) | 0.0156(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 70 | STALE-150 新卡片臂 vs 同题直读(ALL)(writeside_fix_sweep_20260817) | 0.0186(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 71 | STALE-50 新卡片臂 vs 同题直读(ALL)(writeside_fix_sweep_20260817) | 0.0186(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 72 | heldout2_stale extraction_only vs 直读(redteam_cluster_attribution_) | 0.0192(聚类稳健) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 73 | LTT 次级 break 证书 ε=0.03(λ̂=0.05)(router_learned_report_202608) | 0.0207(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 74 | LTT 次级 break 安全证书 ε=0.03(router_learned_report_202608) | 0.0207(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 75 | LME-TR 增益定位:碰撞 uid vs 空操作 uid(内建安慰剂)(writeside_fix_sweep_20260817) | 0.0213(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 76 | TR 内建安慰剂对照(增益定位)(writeside_fix_sweep_20260817) | 0.0213(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 77 | STALE dim2_premise new vs 归档(writeside_fix_sweep_20260817) | 0.0215(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 78 | STALE dim2_premise:new vs 归档(writeside_fix_sweep_20260817) | 0.0215(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 79 | KU 提示词臂 vs 修复后卡片臂(lmeku_cardfix_verdict_202608) | 0.022(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 80 | B(k=40)vs 直读 McNemar(token_matched_prereg.md) | 0.0225(精确(χ²=5.21,1df)) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 81 | B 臂(k=40)vs 直读 k=10(token_matched_prereg.md) | 0.0225(精确(χ²=5.21,1df)) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 82 | LME-KU 提示词臂 vs 新卡片臂(lmeku_cardfix_verdict_202608) | 0.0225(点值) | 是 | ❌ | ✅ | ⚠️ FWER 失显,FDR 存活 |
| 83 | S5 选择性偏差:剔除组 vs 保留组卡片保真率(VERSION_LEDGER.md) | 0.03(点值) | 是 | ❌ | ❌ | ❌ 降级(FDR 失显) |
| 84 | LangMem vs 同题直读(题级+簇级+Holm)(QVF_experiment_audit_2026081) | 0.0357(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 85 | LangMem vs 同题直读(簇级降级)(QVF_experiment_audit_2026081) | 0.0357(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 86 | LTT 次级 break 证书 ε=0.05(λ̂=0.5)(router_learned_report_202608) | 0.0416(点值) | 是 | ❌ | ❌ | ❌ 降级(FDR 失显) |
| 87 | LTT 次级 break 安全证书 ε=0.05(router_learned_report_202608) | 0.0416(点值) | 是 | ❌ | ❌ | ❌ 降级(FDR 失显) |
| 88 | LME-KU 剔除违约 vs 同场控制(最干净)(writeside_fix_sweep_20260817) | 0.0625(上界) | 否 | ❌ | ❌ | (原文即不显著) |
| 89 | KU 逐字锚点剔除 vs 同场控制(最干净对照)(writeside_fix_sweep_20260817) | 0.0625(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 90 | 集合批 S2 vs 直读显著性上界(OPTIMIZATION_LOOP_STATE.md) | 0.0625(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 91 | LME-TR cardfix vs 归档卡片(n=133)(writeside_fix_sweep_20260817) | 0.0636(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 92 | LME-TR cardfix vs 归档卡片(n=131)(writeside_fix_sweep_20260817) | 0.0636(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 93 | TR cardfix vs 归档卡片臂(writeside_fix_sweep_20260817) | 0.0636(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 94 | M4 LME-KU 卡片臂 −14.1pp 复检(QVF_experiment_audit_2026081) | 0.0707(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 95 | newdom-P26 wt_qvf vs 直读(试探)(redteam_cluster_attribution_) | 0.0768(聚类稳健) | 否 | ❌ | ❌ | (原文即不显著) |
| 96 | lme_tr minimal_rules vs 直读(redteam_cluster_attribution_) | 0.0931(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 97 | 对照组簇校正:lme_tr minimal_rules vs 直读(redteam_cluster_attribution_) | 0.0931(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 98 | HIGH-16 LoCoMo 全量头条簇级检验(QVF_experiment_audit_2026081) | 0.109(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 99 | newdom-P1303 wt_qvf vs 直读(试探,n 小)(redteam_cluster_attribution_) | 0.125(聚类稳健) | 否 | ❌ | ❌ | (原文即不显著) |
| 100 | locomo_temporal minimal_rules vs 直读(redteam_cluster_attribution_) | 0.125(聚类稳健) | 否 | ❌ | ❌ | (原文即不显著) |
| 101 | S5-418 剔除违约卡片 vs 控制(逐字锚点契约)(writeside_fix_sweep_20260817) | 0.18(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 102 | S5 逐字锚点剔除:剔除 vs 控制(span 契约臂 A)(writeside_fix_sweep_20260817) | 0.18(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 103 | LME-KU 剔除违约 vs 归档(writeside_fix_sweep_20260817) | 0.219(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 104 | KU 逐字锚点剔除 vs 归档(span 契约臂 B)(writeside_fix_sweep_20260817) | 0.219(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 105 | P6「方差减半」F 检验与 chi2 区间(QVF_experiment_audit_2026081) | 0.222(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 106 | HIGH-11 B6 vs P6 方差减半 F 检验(QVF_experiment_audit_2026081) | 0.222(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 107 | lme_ku minimal_rules_v5 vs 直读(redteam_cluster_attribution_) | 0.227(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 108 | 对照组簇校正:lme_ku minimal_rules_v5 vs 直读(redteam_cluster_attribution_) | 0.227(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 109 | S8 修复因果足迹 7 题符号检验(QVF_s8_line_audit_20260817.m) | 0.25(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 110 | newdom-P69 wt_qvf vs 直读(试探)(redteam_cluster_attribution_) | 0.263(聚类稳健) | 否 | ❌ | ❌ | (原文即不显著) |
| 111 | heldout_stale dense_recency vs 直读(redteam_cluster_attribution_) | 0.286(聚类稳健) | 否 | ❌ | ❌ | (原文即不显著) |
| 112 | STALE dim3_natural new vs 归档(writeside_fix_sweep_20260817) | 0.302(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 113 | STALE dim3_natural:new vs 归档(writeside_fix_sweep_20260817) | 0.302(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 114 | STALE-150 新卡片臂 vs 提示臂(ALL)(writeside_fix_sweep_20260817) | 0.341(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 115 | STALE-50 新卡片臂 vs 提示臂(ALL)(writeside_fix_sweep_20260817) | 0.341(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 116 | lme_tr minimal_rules_v5 vs 直读(redteam_cluster_attribution_) | 0.375(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 117 | first_vs_last 检索完整层配对符号检验(QVF_experiment_audit_2026081) | 0.375(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 118 | 对照组簇校正:lme_tr minimal_rules_v5 vs 直读(redteam_cluster_attribution_) | 0.375(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 119 | first_vs_last 完整/截断分层(HIGH-1)(QVF_experiment_audit_2026081) | 0.375(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 120 | P551 wt_qvf vs 直读(簇校正)(redteam_cluster_attribution_) | 0.508(聚类稳健) | 否 | ❌ | ❌ | (原文即不显著) |
| 121 | LME-KU 四臂排序检验(M7)(QVF_experiment_audit_2026081) | 0.549(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 122 | M7 LME-KU 四臂排序功效(QVF_experiment_audit_2026081) | 0.549(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 123 | memconflict minimal_rules vs 直读(redteam_cluster_attribution_) | 0.581(聚类稳健) | 否 | ❌ | ❌ | (原文即不显著) |
| 124 | STALE dim1_still new vs 直读(writeside_fix_sweep_20260817) | 0.648(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 125 | STALE dim1_still:new vs 直读(writeside_fix_sweep_20260817) | 0.648(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 126 | S8 三臂补做配对检验(61 题)(QVF_experiment_audit_2026081) | 0.688(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 127 | S8 渲染修复三方对照补检验(QVF_experiment_audit_2026081) | 0.688(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 128 | T1-3 b6_rep3 vs v42 编译臂(纯质量效应)(writeside_sensitivity_202608) | 0.727(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 129 | lme_ku qvf_v4 vs 直读(redteam_cluster_attribution_) | 0.791(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 130 | 对照组簇校正:lme_ku qvf_v4 vs 直读(redteam_cluster_attribution_) | 0.791(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 131 | LME-KU 新卡片臂 vs 同题直读(lmeku_cardfix_verdict_202608) | 0.824(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 132 | KU cardfix vs 同题直读(lmeku_cardfix_verdict_202608) | 0.824(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 133 | locomo_temporal minimal_rules_v5 vs 直读(redteam_cluster_attribution_) | 1(聚类稳健) | 否 | ❌ | ❌ | (原文即不显著) |
| 134 | memconflict minimal_rules_v5 vs 直读(redteam_cluster_attribution_) | 1(聚类稳健) | 否 | ❌ | ❌ | (原文即不显著) |
| 135 | STALE dim3_natural new vs 直读(writeside_fix_sweep_20260817) | 1(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 136 | LME-KU 同场控制 vs 归档(噪声底)(writeside_fix_sweep_20260817) | 1(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 137 | 开放槽位修复后 vs 直读(QVF_experiment_audit_2026081) | 1(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 138 | T1-3 功效与置换复检(M17)(QVF_experiment_audit_2026081) | 1(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 139 | LTT 主口径风险证书 ε=0.05(router_learned_report_202608) | 1(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 140 | T1 纯质量效应:b6_rep3 vs v42 编译臂配对(writeside_sensitivity_202608) | 1(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 141 | STALE dim3_natural:new vs 直读(writeside_fix_sweep_20260817) | 1(点值) | 否 | ❌ | ❌ | (原文即不显著) |
| 142 | KU 同场控制 vs 归档(噪声底)(writeside_fix_sweep_20260817) | 1(点值) | 否 | ❌ | ❌ | (原文即不显著) |

## 判定汇总

- 原文当显著且**双口径存活**:45 条
- 原文当显著且 **Holm 失显、FDR 存活**:33 条(论文中引用须注明按 FDR 口径)
- 原文当显著但 **FDR 亦失显 → 降级为方向性观察**:3 条

### 必须降级的条目

- **S5 选择性偏差:剔除组 vs 保留组卡片保真率**(p=0.03,study_logs/VERSION_LEDGER.md:151)——主张:noise_interference 剔除引入渐进式写入质量偏差(猜想被证实)
- **LTT 次级 break 证书 ε=0.05(λ̂=0.5)**(p=0.0416,results/router_learned_report_20260814.md:172)——主张:ε=0.05 证书成立:λ̂=0.5 下 71.48% @1557 tok/题
- **LTT 次级 break 安全证书 ε=0.05**(p=0.0416,results/router_learned_report_20260814.md:172)——主张:ε=0.05 证书成立(71.48%@1557 tok)

## 附录:不入 α 族的条目(LTT 自带控制 / 仅 CI)

- [LTT(自带 δ 控制)] LTT 主口径证书 ε=0.03(二项精确尾界)(results/router_learned_report_20260814.md:119)
- [LTT(自带 δ 控制)] LTT 主口径证书 ε=0.05(results/router_learned_report_20260814.md:127)
- [仅 CI] 留一域外推证书退化(15 域)(results/router_learned_report_20260814.md:198)
- [仅 CI] B6 契约质量 t 区间(主口径)(results/card_quality_b6_interval_report_20260816.md:64)
- [仅 CI] B6 uid 级 bootstrap(交叉验证)(results/card_quality_b6_interval_report_20260816.md:76)
- [仅 CI] P6 temp0 质量护栏 t 区间(results/card_temperature_diagnosis_20260816.md:20)
- [仅 CI] 判官重判一致率 Wilson CI(results/judge_cost_measured_20260816.md:126)
- [仅 CI] 顺序不变写入新路径 n=10 Wilson CI(results/order_invariant_write_20260816.md:56)
- [仅 CI] 路由 ε-vs-n 渐近拟合(bootstrap)(results/router_eps_scaling_20260816.md:8)
- [仅 CI] 结构化机制净增益(剥离提示词反事实)(results/QVF_experiment_audit_20260817.md:78)
- [无法解析] 全库 Holm/BH 多重比较复算(m=59)(results/QVF_experiment_audit_20260817.md:157)
- [无法解析] 「簇稳健」双量冲突批次+置换检验仲裁(results/QVF_experiment_audit_20260817.md:185)
- [仅 CI] 「增益单调递增」相邻档差 bootstrap CI(M15)(results/QVF_experiment_audit_20260817.md:266)
- [仅 CI] 契约质量单库 95% 预测区间(M16)(results/QVF_experiment_audit_20260817.md:267)
- [仅 CI] 边界压力对拍一致率 Wilson CI(M18)(results/QVF_experiment_audit_20260817.md:269)
- [无法解析] LTT 多种子敏感性重跑(L5)(results/QVF_experiment_audit_20260817.md:280)
- [无法解析] LTT 去重复检(L6)(results/QVF_experiment_audit_20260817.md:281)
- [无法解析] LTT 证书聚类违反 DEFF 量化(§3.5)(results/QVF_experiment_audit_20260817.md:326)
- [无法解析] S5 提示词臂 vs 直读 McNemar(results/s5_prompt_arm_prereg.md:69)
- [仅 CI] armdom wt 臂实测准确率 CI(results/armdom_wt_gap_prereg.md:56)
- [无法解析] 预算匹配 A(k=24)vs 直读 McNemar(results/token_matched_prereg.md:81)
- [无法解析] B vs A McNemar(results/token_matched_prereg.md:117)
- [仅 CI] 实验 A set 占比跨语料相关(results/set_vs_replacement_prereg.md:122)
- [仅 CI] 实验 B 卷内 set 占比分层 bootstrap(results/set_vs_replacement_prereg.md:132)
- [仅 CI] 实验 B′ 卷内日期覆盖率分层 bootstrap(results/set_vs_replacement_prereg.md:173)
- [仅 CI] 实验 B″ 卷内对话轮数分层(15 卷)(results/set_vs_replacement_prereg.md:186)
- [无法解析] full-context vs 直读 k=10 McNemar(results/set_vs_replacement_prereg.md:275)
- [仅 CI] 实验 C 孪生批 卡片臂−提示词臂 CI(results/set_vs_replacement_prereg.md:296)
- [无法解析] 冻结规则组合 vs 直读 McNemar(替代 78.79%)(results/twin_leak_audit_20260820.md:95)
- [LTT(自带 δ 控制)] LTT 主口径风险证书 ε=0.03(固定序列二项精确尾界)(results/router_learned_report_20260814.md:119)
- [无法解析] 次级证书切分敏感性 → cluster-robust 90% UCB(study_logs/VERSION_LEDGER.md:101)
- [无法解析] 聚类稳健:P39-ext(results/redteam_cluster_attribution_20260816.md:36)
- [无法解析] 聚类稳健:P54-ext(results/redteam_cluster_attribution_20260816.md:37)
- [无法解析] 聚类稳健:P108-w2(results/redteam_cluster_attribution_20260816.md:38)
- [无法解析] 聚类稳健:P54-w2(results/redteam_cluster_attribution_20260816.md:39)
- [无法解析] 聚类稳健:P551(results/redteam_cluster_attribution_20260816.md:40)
- [无法解析] 聚类稳健:newdom-P26(试探性)(results/redteam_cluster_attribution_20260816.md:41)
- [无法解析] 聚类稳健:newdom-P69(试探性)(results/redteam_cluster_attribution_20260816.md:42)
- [无法解析] 聚类稳健:newdom-P1303(n 小)(results/redteam_cluster_attribution_20260816.md:43)
- [无法解析] 对照组簇校正:heldout_stale minimal_rules vs 直读(results/redteam_cluster_attribution_20260816.md:49)
- [无法解析] 对照组簇校正:heldout_stale qvf_v4 vs 直读(results/redteam_cluster_attribution_20260816.md:50)
- [无法解析] 对照组簇校正:heldout_stale dense_recency vs 直读(results/redteam_cluster_attribution_20260816.md:51)
- [无法解析] 对照组簇校正:heldout2 minimal_rules_v5 vs 直读(results/redteam_cluster_attribution_20260816.md:52)
- [无法解析] 对照组簇校正:heldout2 extraction_only vs 直读(results/redteam_cluster_attribution_20260816.md:53)
- [无法解析] 对照组簇校正:locomo_temporal minimal_rules vs 直读(results/redteam_cluster_attribution_20260816.md:58)
- [无法解析] 对照组簇校正:memconflict minimal_rules vs 直读(results/redteam_cluster_attribution_20260816.md:60)
- [仅 CI] B6 建卡契约期望质量 t 区间(results/card_quality_b6_interval_report_20260816.md:11)
- [仅 CI] B6 uid 级 bootstrap 对照(results/card_quality_b6_interval_report_20260816.md:76)
- [仅 CI] 顺序不变写入质量护栏(Wilson 区间)(results/order_invariant_write_20260816.md:56)
- [仅 CI] 判官独立重判一致率(results/judge_cost_measured_20260816.md:126)
- [仅 CI] Z1 学习路由 ε-规模 bootstrap 诊断(results/router_eps_scaling_20260816.md:12)
- [仅 CI] P6 固定温度方差减半判据(results/card_temperature_diagnosis_20260816.md:20)
- [仅 CI] 全库反事实:纯提示词回落规则 vs QVF(归因分解)(results/QVF_experiment_audit_20260817.md:40)
- [无法解析] HIGH-10 全库 Holm 多重比较校正(results/QVF_experiment_audit_20260817.md:157)
- [无法解析] S8 阶段一直读对照簇级复检(results/QVF_experiment_audit_20260817.md:176)
- [无法解析] 簇级符号翻转置换检验仲裁(cluster_p vs clusterCI 矛盾)(results/QVF_experiment_audit_20260817.md:185)
- [仅 CI] M15 '增益随算术负担单调增强'重采样检验(results/QVF_experiment_audit_20260817.md:266)
- [仅 CI] M18 边界压力一致率区间(results/QVF_experiment_audit_20260817.md:269)
- [仅 CI] P3 LTT 证书聚类违反量化(results/QVF_experiment_audit_20260817.md:326)
- [仅 CI] 机制① c₂ 组合通过率估计(study_logs/QVF_new_mechanisms_feasibility_20260817.md:96)
- [无法解析] S5 提示词臂 vs 直读(McNemar)(results/s5_prompt_arm_prereg.md:69)
- [仅 CI] armdom wt 抽样准确率区间(results/armdom_wt_gap_prereg.md:56)
- [仅 CI] armdom 总账重算 CI 传播(results/armdom_wt_gap_prereg.md:76)
- [无法解析] token 匹配臂 A vs 直读 k=10(results/token_matched_prereg.md:81)
- [无法解析] B 臂 vs A 臂(results/token_matched_prereg.md:117)
- [仅 CI] 实验 A 跨语料相关(set 占比 vs wt 优势)(results/set_vs_replacement_prereg.md:122)
- [仅 CI] 实验 B 卷内 set 占比分层(results/set_vs_replacement_prereg.md:132)
- [仅 CI] 实验 B′ 卷内日期覆盖率分层(results/set_vs_replacement_prereg.md:173)
- [仅 CI] 实验 B″ 卷内对话轮数分层(results/set_vs_replacement_prereg.md:186)
- [仅 CI] 实验 C 替换孪生批:卡片臂 vs 提示词臂(results/set_vs_replacement_prereg.md:296)
- [仅 CI] 实验 C 集合孪生批:卡片臂 vs 提示词臂(results/set_vs_replacement_prereg.md:296)
- [无法解析] full-context 整库直读 vs 直读 k=10(results/set_vs_replacement_prereg.md:275)
- [无法解析] 泄漏审计后替换批组合策略 vs 直读(results/twin_leak_audit_20260820.md:95)
- [仅 CI] CPC 反事实 treatment−sham(用户侧)(study_logs/EXPERIMENT_INDEX_20260819.md:40)
