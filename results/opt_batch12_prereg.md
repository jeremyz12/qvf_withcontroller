# 预注册:批 12——change_count 执行器修复(成员过滤店入计数路径)

日期:2026-08-26。先于跑数提交。

## 假设与治疗

诊断(批 7/11 入档):编译臂 change_count 弱(v2 55.6 vs smoc 76.4)因执行器
`len(chain)-1` 依赖卡片链行数,卡片链≠真值链(非成员卡/重复宣告混入)时算错。
治疗 = **算法 3 成员过滤器**(修复环组件,受控场识破 100%/误删 0.7%)先净化卡店,
计数路径读过滤店。

## 命令(逐字入档)

```
python scripts/chain_membership_filter.py --data data/wikistate_full_ALL.json --cards results/wt_cards_v42 --out-cards results/wt_cards_v42_mf --report results/mf_v42_report.json
# 计数族题集(change_count + count_before,288 题)由 wsc_s5_v2.jsonl 机械抽取
QVF_CARDS_KEYED=results/wt_cards_v42_mf QVF_EMPTY_EVIDENCE_DIRECT=1 QVF_TENURE_ASOF=1 \
  python scripts/complex_query_arm.py --data data/wikistate_full_ALL.json \
  --questions data/wsc_s5_v2_countfam.jsonl --out results/wsc_v2_countfam_mf.jsonl --resume
```

基线不重跑:与批 7 `wsc_v2_compile.jsonl` 同 qid 行配对(同配置同判官)。

## 判据(写死)

- **C1(主)**:change_count(144 题)过滤店 − 基线 55.6 ≥ **+6pp** 且 McNemar p<0.05
  → 计数路径采纳过滤店(路由级:仅 count 类算子读过滤店);
- **C2(护栏)**:count_before(144 题)Δ ≥ −2pp(回退超线则不采纳,如实入档);
- **C3(安全)**:空证据回退率(empty_to_direct 占比)较基线上升 ≤ 5pp(过滤过狠
  会制造空池,由回退兜底但须计量);
- 预测:change_count +4~+12;count_before −2~+4。偏出如实入档。

## 预算

过滤 144 库 ≈$0.6 + 治疗臂 288 题 ≈$1.4 ≈ **$2**。无论方向如实入档。
