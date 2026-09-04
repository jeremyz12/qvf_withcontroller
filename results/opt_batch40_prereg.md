# 批 40 预注册:104K-token 库 × 强读者(claude-sonnet-5)——补四象限缺格

日期 2026-09-04。目标:填满"库长(14K/104K)× 读者(haiku-4.5/sonnet-5)"四格表里唯一缺的一格——
104K 店 × sonnet-5。三个已在档的格已知:

| 库长 | 读者 | 全上下文 acc | 出处 |
|---|---|---|---|
| 14K(L0,v43 店) | haiku-4.5 | 70.0%(plainctx,mt800) | `results/opt_batch36_verdict.md` §一 |
| 14K(L0,v43 店) | sonnet-5 | 87.9%(mt800)/ **97.1%**(mt4000 截断校正) | 同上 |
| 104K(L2,30 店) | haiku-4.5 | 7.5%(fullplain=PLAIN_PROMPT) | `results/opt_batch33_D_scaleL2_verdict.md` §一 |
| 104K(L2,30 店) | sonnet-5 | **本批要填** | — |

同题集 `data/wsc_long_L1_questions.jsonl`(120 题 = 30 uid × 4 题型),同语料
`data/wikistate_long_L2_b33.json`,卡片库沿用 33-D 原样(只读):
`results/wt_cards_b33_L2`(20 新店)+ `results/wt_cards_b27_L2`(10 旧店)。
读者 `anthropic:claude-sonnet-5`,`max_tokens=4000`、**不发送 temperature**
(sonnet-5 收到该参数会 400,与批 36-B 逐字同一约束)。判官
`qvf.judge.ClaudeJudge`(`claude-opus-5`,冻结)。计价:sonnet-5 $2.00/M in、
$10.00/M out(协调员口径);判官 opus-5 $5.00/M in、$25.00/M out 单列、不入
读者 $40 帽。

## 口径说明(须在跑前写死,跑后不得回改)

1. **"全上下文"用哪个提示词**:104K 侧本批用 `scripts/b36_plain_fullctx.py`
   的 PLAINCTX 提示("Below is the complete record… in chronological order",
   现实措辞、无长度限制),这与 14K 侧批 36 头条(`plainctx`)是**同一个提示词
   逐字节复用**,构成跨库长的干净对照。但 104K 侧的 haiku 参照值(7.5%,
   来自 33-D/39)用的是 **`fullplain`=`PLAIN_PROMPT`**("Reply with only the
   answer")——**两个提示词不同**。四格表因此有一个已知的口径缺口:
   haiku 那一列跨库长可比(70.0%→7.5% 都是同一 `render_transcript` 全文,
   但 14K 用 plainctx、104K 用 PLAIN_PROMPT,句式不同),sonnet 那一列本批
   两格(14K 的 97.1% 与本批的 104K 新值)**才是真正同提示词同读者的干净对
   照**。本预注册跑前即承认这一点,不在事后找补。
2. **max_tokens**:sonnet-5 三档账目/检索臂与 plain 臂统一用 4000(批 36-B
   已实测 800 会把约 14% 的题掐成空答);haiku 参照值原为 800,不重跑。
3. **判官**:与 33-D/39 同一 `ClaudeJudge` 默认模型,不因读者换而换判官。

## H1:104K 全上下文(sonnet-5)远低于其 14K 值(97.1)

**命题**:`plainctx:sonnet-5` 在 104K 店上的准确率显著低于同臂 14K 值 97.1%。
**阈值(跑前承诺)**:点估计 **< 80%** 即判"被证实"(严重衰减);
若落在 [80, 92.1)(即 Δ 在 −5~−17pp 之间,呼应 33-D 对 haiku 全文观察到的
"账目掉 30pp、但账目远比全文抗衰减"不对称)算"部分证实,方向对但未过硬
阈值";若 ≥ 92.1%(Δ 在 ±5pp 内)判"被否定"。同时报店级簇自助 95% CI,
若 CI 上界仍 < 80 则升级为"硬证实"。

## H2:QVF 槽位投影(sonnet-5)≥ 全上下文(sonnet-5),token 只需 1/10

**命题**:`smoc:sonnet-5`(`QVF_LEDGER_VIEW=slot`)的准确率点估计 **≥**
`plainctx:sonnet-5` 的准确率,且投影臂均输入 token **≤** 全上下文均输入
token 的 1/10。
**阈值(跑前承诺)**:token 比例条件用 haiku 侧已实测的量级作先验
(投影 8,800 vs 全文 103,780 ≈ **8.4%**,已满足 ≤10% 的门槛;sonnet-5
读同一份誊录/账目文本,token 数预期与 haiku 侧同量级,只作为观测量报告,
不重新设阈值)。准确率条件:
- 点估计 投影 ≥ 全文 → 方向证实;
- 若 McNemar p < 0.05 或店级簇自助 95% CI 下界 > 0 → **硬证实**;
- 若点估计投影 < 全文但差距 CI 跨零 → "不可分,方向未证实";
- 若投影点估计显著更低(CI 上界 < 0)→ **被否定**。

## H3:最强检索(top-100,sonnet-5)< 投影(sonnet-5)

**命题**:`dense_top100:sonnet-5` 的准确率点估计低于 `smoc(slot):sonnet-5`。
**阈值(跑前承诺)**:
- 点估计 top-100 < 投影 → 方向证实;
- McNemar p < 0.05 或簇自助 CI 上界 < 0(即投影显著更高)→ **硬证实**;
- 差距 CI 跨零 → "方向对但不可分";
- 点估计 top-100 ≥ 投影 → **被否定**。
本批只跑 `dense_top100` 一条检索臂(任务书指定的最强/最深 k,batch 39 已
证明 haiku 读者下 top-100 是四臂里最强的),不追加更深 k。

## 跑批顺序与预算(读者 $40 帽,判官另计不入帽)

1. `smoc(slot 投影)` sonnet-5(120 题)
2. `smoc(全账目)` sonnet-5(120 题)
3. `dense_top100` sonnet-5(120 题,复用 `results/b39_emb_L2_turns.npz`)
4. `plainctx(全文)` sonnet-5(120 题)—— **放最后跑**,预估读者输入
   ≈103,780×120≈12.45M tok ≈ $24.9(输出另计),一旦前三臂已完成,即使
   预算在第 4 臂中途触发停跑,前三臂(H2、H3 所需的全部数据)也不受影响。

粗估读者总花费(按 haiku 侧 token 量级外推,sonnet-5 侧口径待实测校正):
投影 ≈$3、全账目 ≈$6、top-100 ≈$2.5、全文 ≈$25.5,合计 **≈$37**,在 $40 帽内
但余量小;若全文臂在帽内被截停,按已完成题数如实报,不外推补全。

## 记分与产出

- 逐题行:`results/b40_slot_L2_sonnet5.jsonl`、`results/b40_ledger_L2_sonnet5.jsonl`、
  `results/b40_top100_L2_sonnet5.jsonl`、`results/b40_plainctx_L2_sonnet5.jsonl`。
- 记分器 `scripts/b40_score.py`(承 `scripts/b39_score.py` 口径:Wilson 95% CI、
  逐题型、配对 McNemar、店级簇自助 CI N=4000 seed=40)→
  `results/b40_score_out.txt`、`results/opt_batch40_verdict.md`。
- 四格表(14K/104K × haiku/sonnet-5)与 H1–H3 判决写入 verdict,判决式汇报
  (先给"证实/否定"判词,再给数字),并列成本($/题、mean tokens)、延迟中位数。
