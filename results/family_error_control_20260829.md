# 全族错误控制重算 v2(2026-08-29):m=186(旧族 142 + 批11-28 新 44)

BH(q=0.05)经验阈值 = **0.0225**;Holm 存活 49 条。

## 原显著、合族 BH 后失显(降级为方向性观察,共 13 条)

- p=0.03 | S5 选择性偏差:剔除组 vs 保留组卡片保真率(VERSION_LEDGER.md) (2020-08-20族)
- p=0.036 | b11 usability vs filter (v2 576) (results/opt_batch11_verdict.md)
- p=0.037 | xmodel gpt-5-mini retrieval baseline vs haiku (576) (results/xmodel_probe_20260827.md)
- p=0.039 | b22 T1 per-session smoc vs A1 batch (n=60) (results/opt_batch22_verdict.md)
- p=0.0416 | LTT 次级 break 证书 ε=0.05(λ̂=0.5)(router_learned_report_202608) (2020-08-20族)
- p=0.0416 | LTT 次级 break 安全证书 ε=0.05(router_learned_report_202608) (2020-08-20族)
- p=0.043 | b12 C1 change_count member-filter store (results/opt_batch12_verdict.md)
- p=0.049 | errata-closure STALE third judge (gpt-4.1-mini, b19) (study_logs/QVF_MASTER_20260826.md)
- p=0.177 | errata-closure cache order invariance run (v43 576) (study_logs/QVF_MASTER_20260826.md)
- p=0.229 | b23 v43 store rebuild upgrade (store-level sign test) (results/self_audit_20260828_verdict.md)
- p=0.27 | b14 slot projection vs full ledger (v42 576) (results/opt_batch14_verdict.md)
- p=0.33 | b24 P slot projection v43 migration (576) (results/opt_batch24_verdict.md)
- p=1 | b14 smw vs smoc-slot direct pairing (576) (results/opt_batch14_verdict.md)

## 原显著且 BH 存活:93 条(明细见 JSON);关键存活样例:

- p=0.0213 | LME-TR 增益定位:碰撞 uid vs 空操作 uid(内建安慰剂)(writeside_fix_sweep_202
- p=0.0213 | TR 内建安慰剂对照(增益定位)(writeside_fix_sweep_20260817)
- p=0.0215 | STALE dim2_premise new vs 归档(writeside_fix_sweep_20260817)
- p=0.0215 | STALE dim2_premise:new vs 归档(writeside_fix_sweep_20260817)
- p=0.022 | KU 提示词臂 vs 修复后卡片臂(lmeku_cardfix_verdict_202608)
- p=0.0225 | B(k=40)vs 直读 McNemar(token_matched_prereg.md)
- p=0.0225 | B 臂(k=40)vs 直读 k=10(token_matched_prereg.md)
- p=0.0225 | LME-KU 提示词臂 vs 新卡片臂(lmeku_cardfix_verdict_202608)
## 口径注(先于引用写死)

1. **等价类条目不适用拒绝型降级**:b14/b24 投影平价(p=0.27/0.33)、缓存
   不变性(p=0.177)以 n.s. 为支撑,属等价主张——按勘误第 7 条以 CI 语言
   表述,不入"失显降级"清单语义;
2. **拒绝型真降级(合族后)**:usability v2 级 +2.95(p=0.036)、批 12 过滤
   +8.3(p=0.043)、gpt 直读更差(p=0.037)、批 22 T1 smoc(p=0.039)、
   STALE 第三判官(p=0.049)——全部转方向性观察;
3. **外场三判官句定稿**:"STALE 三判官同向;主判官 p=0.0079 **族校正存活**,
   第二/三判官(0.024/0.049)族校正后方向性"——较 08-29 晨版更保守;
4. 族存活的关键采纳:v2 阶梯选择级(1.5e-08)与计算级(1.8e-09)、结构总价
   (2.2e-25)、弱读者抬升(5.4e-38)、外场 STALE(0.0079)、证据饥饿 sonnet
   (0.008)、序贯附注(0.0016)。
