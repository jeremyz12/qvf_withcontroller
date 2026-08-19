# 预注册:判官交叉审计(聚合题集 + 孪生批,先于跑数提交)

日期:2026-08-20。来源:持续优化循环 rank-7。动机(审计):kappa 0.979 来自旧语料;
决定性语料(WikiState 聚合四题型、孪生两批)上判官零审计;judge.py 规则
("含 gold 信息即对"/"多部分 gold 答子集算错")可能结构性偏向结论行含 gold 逐字的
编译臂;全部 <5pp 主张(+2.66/+3.1/+5.11/+6.46)落在未测噪声带内。

## 抽样(确定性,qid 排序后等距,无随机数)

- 聚合 418:3 臂(直读 union / filter-only / 编译 v42b1)× 4 题型 × 13 行 ≈ 156 行;
- 孪生批:替换(direct / wt_mf)+ 集合(direct / compile_setsem)各 25 行 = 100 行;
- 交叉判官 = gpt-5-mini,**同一 JUDGE_SYSTEM_PROMPT**(沿用 scripts/cross_judge_generic.py
  的既有管线与解析),≈256 次调用,预计 ≤$0.5。

## 判据(先写死)

设各臂分歧率 d_arm = P(gpt ≠ claude|该臂),flip 净方向 = (claude对gpt错) − (claude错gpt对):

1. max(d_arm) − min(d_arm) < 2pp 且各臂 flip 方向 binomial 双侧 p > 0.05
   → **"同判官=公平"成立**;总分歧率作为噪声带写入 REPORT_SAFE_CLAIMS,
   规则:引用任何小于噪声带 2 倍的差值必须注明"位于判官噪声带内"。
2. 某臂被系统性偏宽:该臂 claude对gpt错 净超出其他臂 ≥3pp 且 binomial p<0.05
   → 该臂相关的全部 <5pp 主张降级为"判官噪声带内",并触发全量双判官重判(另轮,~$3)。
3. 中间情形:报每臂分歧率与方向,<5pp 主张统一加"单判官"限定词,不下二值判决。

无论方向如实入档。产物:results/crossjudge_s5_twin.jsonl + 判定节(本文件追加)。
