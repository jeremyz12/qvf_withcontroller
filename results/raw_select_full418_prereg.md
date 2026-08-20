# 预注册:raw_select 全量 418 升级(先于跑数提交)

日期:2026-08-21。来源:持续优化循环低优先队列(raw_select 判决遗留项,
results/raw_select_verdict_20260820.md §遗留)。

## 动机

n=100 判决已触发第 1 档:选择下界 R−W=+17.0pp(McNemar p=0.0085)。
但**规范化增量 F−R=+9.0pp 只有 p=0.066**——deck 选择阶梯 60→69 一段
仍可被攻击("规范化增量是噪声")。全量 418 把两个差值的检验收紧,
一次性买断这个攻击点。

## 设计(全部复用冻结件,零新实现)

- 输出:`results/wsc_s5_raw_select_418.jsonl`。先把 100 题产物行
  (`results/wsc_s5_raw_select_100.jsonl`)原样拷入,`--resume` 跳过已做,
  只补跑其余 318 题。
- 臂:`QVF_READER_MODE=raw_select`(冻结旗标,8367df2),
  `QVF_CARDS_KEYED=results/wt_cards_v42`,读者 claude-haiku-4-5,同判官。
- 题源:`--questions` 由 `results/wsc_s5_filter_only.jsonl` 归档行重建
  (question_id→qid / question_type→qtype / gold_answer→gold,418 行);
  `--data` 四卷 wikistate_full(P108/P39_ext/P54/P551)。
- 对照(同 418 题同题配对,全部用归档行,不重跑):
  提示词臂 W = `results/wsc_warned_s5_all_b1.jsonl`(47.61%,418 行已核);
  filter-only F = `results/wsc_s5_filter_only.jsonl`(66.03%)。

## 判据(先写死)

设 R = raw_select 全 418 成绩:

1. **C1 选择下界**:R−W,McNemar。预期保持显著正(点估 +10~+18)。
   若 p≥0.05:100 题第 1 档判决**降级**,对外拆报口径撤回,重审抽样批。
2. **C2 规范化增量**:F−R,McNemar。
   - p<0.05 → "规范化增量"确认,阶梯 60→69 段保留现叙述;
   - p≥0.05 → deck/讲稿该段加注**"规范化增量点估为正但未过显著线,选择价为主"**。
3. 分题型四型照报;change_count"含结构性编码成分"注记在任何判决下照挂;
   longest_tenure 绝对值照旧不得单独引用(gold 缺陷注记)。

## 可证伪预测

R418 ∈ [52, 62](n=100 点估 60 的抽样收缩);C1 显著;C2 方向为正但
显著性**真不确定**——这正是本轮花钱要买的那一位信息。
若 R418 与 R100 点估差 >5pp,如实注记抽样波动并回查分题型漂移。

## 成本

318 题 × (filter-only 实测 $2.39/418 题) ≈ **$1.8**,$2/轮纪律内。
无论方向如实入档。
