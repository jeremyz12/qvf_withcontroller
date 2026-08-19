# 预注册:dim 表覆盖混淆对质 · 整库臂补测(先于跑数提交)

日期:2026-08-20。来源:持续优化循环 rank-1 第二步(首轮攻击面审计;$0 复算见
results/dim_coverage_confront_20260820.md)。

## 动机(攻击原文)

"变化历程类 +51.6pp、换模型/加提示词买不到"的 5 个卷上从未跑过整库臂;
归档卷(chain-212/w2)显示整库直读 dim5 可达 84–91%。若覆盖对齐后差距消失,
主张 2 头条必须改写。

## 设计

- 语料:data/wikistate_full_P108_ext.json(69 库)、data/wikistate_full_P54_ext.json(41 库)。
- 臂:整库直读(QVF_FULL_CONTEXT 语义,scripts/framing_fullctx_arm.py --benchmark stale_chain,
  零改动复用产出过 wiki_fullctx_*_w2 的同一管线;reader=claude-haiku-4-5,判官同管线内置)。
- 批次(成本纪律 $2/轮):**批 1 只跑 dim5**(69+41=110 题,本预注册覆盖);
  dim4(110 题)为批 2,判据同式,另轮执行。
- 剪枝卷实现:复制卷 json,probing_queries 只保留 dim5_trajectory,
  条目/会话/链逐字节不动(每题提示独立,剪枝不改变单题输入)。
- 配对对象:results/wtqvf3_v42_P108ext.jsonl、results/wtqvf3_v42_P54ext.jsonl 的 dim5 行
  (卡片臂,dim5 = 92.8% / 100.0%)。

## 判据(先于跑数写死)

结构净增量 := wt − fullctx(同题配对,McNemar,两卷合并 n=110)。dim5 上:

1. wt − fullctx ≥ +20pp 且 p<0.05 → 主张保留,措辞改写为
   "检索覆盖对齐后结构仍 +Xpp"(废除与 top-10 饥饿基线的对比口径);
2. wt − fullctx < +10pp → 头条改写为"覆盖买得到大半,结构只买剩余",
   +51.6pp 从对外口径撤下,dim5 归入"列举类靠覆盖可达"(与归档卷判读一致);
3. +10 ~ +20pp → 报区间,撤"只有建库买得到"绝对措辞,保留方向性表述。

副产物一并落盘:两臂 token/延迟中位数;fullctx 在 dim5 的绝对成绩
(预期若 ≥80% 则与归档卷 84–91% 一致,若 <60% 则说明 ext 卷更难,须在判读中说明)。

无论结果方向如何,如实入档并同步 REPORT_SAFE_CLAIMS 与讲稿。
