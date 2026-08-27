# 预注册:批 18——count_changes 缺 as-of 截断修复(诊断-治疗-验证环第二例)

日期:2026-08-28。动因:批 15 附注"+1 过数 22/28"追根(用户令四方向依次全开)。

## 诊断(已完成,零 API,scripts/opt_batch18_diagnose.py + 离线重放)

- 逐链对齐发现错题主体**不是链噪**:18/28 例执行器链与金链逐值相同而计数不同,
  全部带链中段的 "(Today is X.)"——**执行器 count_changes 数全链,金按 as-of
  只数到 Today**;plan.date 恒 null,执行器对 Today 失明。与 longest 的
  QVF_TENURE_ASOF 同族缺陷;
- 离线重放(144 题,与执行器同路径 _select_pool+_hygiene+_chain):数字对金
  全链 76/144 → 截断 **103/144**;边界约定 ≤ 与 < 无差(无恰好压线转移),
  取 **≤(含 Today 当日)**;
- 相对存档臂预计翻转:错→对 16 / 对→错 5,**预测 change_count 63.9 → ~71.5**;
- 次要根因(本批不治,移批 18b 候选):P39 家族杂卡穿滤(~7 例,'marketing
  specialist' 等干扰人设卡混入议员链,全在过滤器零剔除店);1 例抽取错值。

## 治疗(已打补丁,待验证)

`QVF_COUNT_ASOF=1`(env 门控,complex_query_arm count_changes 分支;默认 0
逐字节不变,与 _TENURE_ASOF 同样式):按题面 Today 截断链前缀后计数。

## 验证命令(逐字入档)

```
QVF_COUNT_ASOF=1 QVF_EMPTY_EVIDENCE_DIRECT=1 QVF_TENURE_ASOF=1 \
QVF_CARDS_KEYED=results/wt_cards_v42_mf \
python scripts/complex_query_arm.py --data data/wikistate_full_ALL.json \
  --questions data/wsc_s5_v2_countfam.jsonl \
  --out results/wsc_v2_countfam_mf_asof.jsonl --resume
```

对照 = 存档 results/wsc_v2_countfam_mf.jsonl(change_count 63.9 / count_before
76.4),同题配对。

## 判据(写死)

- **C1**:change_count(144)≥ 63.9 + 6pp 且配对 McNemar p<0.05;
- **C2 护栏**:count_before(144)≥ 76.4 − 2pp(本补丁不触其分支,应零变);
- **C3**:空证据回退率不升(>5pp 判废);
- 全过 → `QVF_COUNT_ASOF=1` 入冻结配置,系统总分(修复编译臂)重算并出勘误;
  预测窗:change_count +6~+10(离线重放点估 +7.6)。

## 预算

288 题 haiku+判官 ≈ **$1.5**;跑前本文件与补丁先提交。
