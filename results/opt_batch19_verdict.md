# 批 19 终判:外场合并显著性——主判据双过,采纳(预注册 opt_batch19_prereg)

日期:2026-08-28。新鲜扩样(seed=19,排除批 17 店):STALE +40 店 120 题、
MemOps +40 店 120 题;臂与判分与批 17 逐字同口径(场判官为主)。
实测成本 ≈$26(建卡 STALE $12.3 / MemOps $4.8 + 臂与判官 ≈$9),预算内。

## 主判据(新鲜 240 题合并配对):**过**

| 口径 | direct | smoc | Δ | McNemar |
|---|---|---|---|---|
| **合并新鲜 240** | 47.5 | **57.1** | **+9.6**(≥+8 ✓) | b=29/c=52,**p=0.014**(<0.05 ✓) |
| STALE 新鲜 120 | 46.7 | **61.7** | +15.0 | b=12/c=30,**p=0.0079(单场亦显著)** |
| MemOps 新鲜 120 | 48.3 | 52.5 | +4.2 | b=17/c=22,p=0.52 |

次要(序贯附注,批 17+19 全 360 题):b=44/c=80,p=0.0016。

**采纳的论文级主张(措辞定稿)**:"On two third-party benchmarks (STALE,
MemOps), the ledger endpoint beats the retrieval baseline by +9.6pp in a
preregistered paired test on fresh samples (McNemar p=0.014; STALE alone
+15.0, p=0.008), under each benchmark's own official-style judge."
分场数字并报;MemOps 单场不显著如实注明。

## 机制读数

- **STALE dim2(假前提抵抗)是主胜负手**:direct 14/40(35%)vs smoc
  26/40(**65%,+30pp**)——陷阱题维度,与 WikiState 的 premise_check
  能力同源,在第三方考场复现;dim1 +5pp,dim3 +10pp;
- MemOps +4.2(n.s.)与探针 +10 同向收窄:无日期考场账目退化为序保持,
  优势小而稳(五操作类探针无一落后的形态保持);
- smoc 读取 8.5K tok/题 vs 全文 ~170K(1/20 量级,成本形态与批 17 一致);
- 协议偏差(无 ANSWER: 行)smoc 侧 23/120,与批 17 一致偏高,格式重申
  是外场工程遗留(不影响判官,судья读全文)。

## 与批 17 的关系

批 17 三场探针全部中性(升级线未过)→ 本批按预注册扩样,新鲜数据独立过线
——探针-升级两段制的完整闭环:没有一步吃已见数据。
