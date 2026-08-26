# 预注册:批 11——论文数据面补全三件(先于跑数提交)

日期:2026-08-26。性质:**完备性数据补全**,非机制优化(批 9/10 已判双侧饱和,
配置冻结;本批不动任何机制,只补冻结配置下缺失的数字)。

## P0 · 头条复核:smoc 全 418 重跑一次

87.80@418 自批 1 起带"待复核"(单种子;批 2 的 60 题复跑漂移 +3.33pp 超 ±2pp 线,
限定词未摘)。本批全 418 同配置重跑一次:

```
python scripts/repro_batch3.py --system smoc --full --out results/wsc_smoc418_rerun_20260826.jsonl
```

**判据(写死)**:
- |rerun − 87.80| ≤ 2.0pp → 摘除"待复核";对外头条改报两次均值(附两次原始值);
- 2.0pp < |Δ| ≤ 4.0pp → 限定词保留,追加第三次跑,三次报均值±全距,并查漂移源
  (判官侧 vs 读者侧:复用判官交叉审计口径);
- |Δ| > 4.0pp → 87.80 从对外口径撤下,以多次均值重立头条,如实入档。

预算 ≈$4。

## P1 · v2 消融梯子补全:filter / usability / smw 三臂 × 576 题

v2(data/wsc_s5_v2.jsonl,576 题/144 链)现只有直读 48.61 / 编译 75.87 / smoc 82.64。
补齐梯子与所有权对照。卡店与批 7 编译臂同店(wt_cards_v42,"店不动只换题"),
数据源 data/wikistate_full_ALL.json(144 链全覆盖):

```
QVF_READER_MODE=filter    QVF_CARDS_KEYED=results/wt_cards_v42 python scripts/complex_query_arm.py --data data/wikistate_full_ALL.json --questions data/wsc_s5_v2.jsonl --out results/wsc_v2_filter.jsonl --resume
QVF_READER_MODE=usability QVF_CARDS_KEYED=results/wt_cards_v42 python scripts/complex_query_arm.py --data data/wikistate_full_ALL.json --questions data/wsc_s5_v2.jsonl --out results/wsc_v2_usability.jsonl --resume
python scripts/repro_batch3.py --system smw --questions-file data/wsc_s5_v2.jsonl --out results/wsc_v2_smw.jsonl
```

(filter/usability 不开 EMPTY_EVIDENCE_DIRECT/ASOF——与 v1 梯子同义,保持逐级
定价可比;回退与 ASOF 属路由/执行器层,只在编译臂配置生效,批 7 已如此。)

**判据(完备性数据,无升级线;预期写死,偏出如实入档)**:
1. 梯子序保持:48.61(直读) < filter < usability < 75.87(编译)——任何一级
   倒挂不隐藏,入档并调查;
2. smoc − smw 预测窗 ∈ [+1, +8](v1 为 +3.35:87.80 vs 84.45);
3. 全臂 > majority 基线(~25/30.6);
4. 三臂均记 token/成本/延迟三项。

预算 ≈$10-12(576×3,参照批 7 三臂 $8.2)。

## P2 · 修正:LongMemEval 冒烟撤销(前提失实)

批 11 立项时曾计划 LME 时序子集 oracle 冒烟(<$1)。核查发现**该考场数据已存在
且远超冒烟深度**:KU 78 题,写入侧修复(QVF_CARD_RENUMBER=1)后卡片臂 63/78=80.77%
> 直读 78.2%,题级配对 W/L/T=15/2/61,p=0.00235,簇自助 95% CI [+7.7,+26.9]
(commit ba0ed72;results/lmeku_cardfix_verdict_20260817.md);TR 亦有成套产物
(final2_lmet_* 等)。冒烟撤销,不重复花钱。

改列 $0 核实项:①核对 LME 各数与当前冻结口径的适配性(是否需在对外材料中标注
"2026-08-17 配置");②KU/TR 结论纳入对外材料清单。真正未执行的外部考场为
TRACE / MemOps,列候选,**不在本批**,待另批预注册。

## 总预算

≈$14-16。无论方向,如实入档。
