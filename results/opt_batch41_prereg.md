# 批 41 预注册:第二次抽取(extraction instability)能否补回金标缺行?

**日期**:2026-09-04。**上游**:`results/opt_batch38e_verdict.md`(v47skf 真实
读者证实,haiku 93.6%/131/140、sonnet-5 95.0%/133/140,残留缺口全部集中在
`wikiP39037-Q3525068` 3 题)、`results/opt_batch38d_verdict.md`(离线诊断
"该链抽取阶段整体少产出、1784/1794 两行金标从未被抽取,断言类型过滤这类
减法规则原理上无法触及";§七方差表另标注 `wikiP39006-Q5220520`、
`wikiP39017-Q24568849` 为记录数跌幅较大的链)。任务书据此点名三条链复查
建店日志:`wikiP39037-Q3525068`、`wikiP39006-Q5220520`、
`wikiP39017-Q24568849`。

## 零、开工前核验:三条链在当前店里的锚点缺口(重要修正)

任务书原话"chains with gold-anchor loss = 三条链"来自批 38-D §七的方差表,
但该表是**三店(v45/v47s/v47sk)联合视角**——三条链里有的链只在 `v45`
(144 链、haiku 建、与本管线 v47sk→v47skf 无关的对照店)锚点不满,在
`v47sk`/`v47skf`(本管线实际使用的店)早已满分。开工前用
`scripts/b38e_score.py` 的 `diag_uid()` 逐店逐链实测(而非照抄批 38-D 文字),
结果如下:

| uid | gold | v45 exact/missing | v47s exact/missing | v47sk exact/missing | v47skf exact/missing |
|---|---|---|---|---|---|
| wikiP39037-Q3525068 | 4 | 1 / 3 | 4 / 0 | **2 / 2** | **2 / 2** |
| wikiP39006-Q5220520 | 3 | 1 / 2 | 3 / 0 | 3 / 0 | 3 / 0 |
| wikiP39017-Q24568849 | 5 | 1 / 4 | 5 / 0 | 5 / 0 | 5 / 0 |

**结论(先判决,后数字)**:三条链里,只有 `wikiP39037-Q3525068` 在
`v47sk`/`v47skf`(本管线实际要修的店)里存在金标锚点缺口(**2 行缺失**:
1784 年"member of the 16th Parliament of Great Britain"、1794-04-21
"colonial governor of Guadeloupe"——`data/wikistate_full_ALL_v24.json` 逐条
核对)。另外两条链在 `v47sk`/`v47skf` 里都已是满分(3/3、5/5),它们的锚点
缺口只出现在与本管线无关的 `v45`(单独的 144 链 haiku 对照店,批 33-A 建,
本批全程不碰)。

**据此修正 H1 的可验证阈值**(其余按任务书原样执行:三条链都重抽,作为
稳定性/回归检查,不只抽有缺口的那条):把"≥2/3 chains' missing gold
anchors"换算成"≥1/2 缺失的金标行"(因为实际总缺口是 2 行,不是 3 行);
若 2/2 全部补回记为**完全证实**,1/2 记为**部分证实**,0/2 记为**证伪**。
`wikiP39006`/`wikiP39017` 因为在 v47sk 已经零缺口,第二次抽取对它们的预期
结果是**不变**(0 处新增锚点)——这是一次零成本的稳健性检验点,不是本批
的证实目标,若这两条链的抽取结果与 v47sk 现有账目出现锚点级别的净损失
(命中→未命中翻转),视为本批的一个警报,不是预期内噪声。

## 一、假设(H1–H3)

- **H1(写入侧,已按上面修正)**:用 `scripts/wt_qvf_prototype_b38.py`
  (批 38 冻结副本,`QVF_CARD_MODEL=claude-sonnet-5`、
  `QVF_CARD_THINKING=off`、`max_tokens=16000`、一链一次调用,与建
  `wt_cards_v47s` 逐字同一命令,唯独目标目录换成
  `results/wt_cards_v47s_pass2`)对这 3 条链重新抽取一遍,得到的新卡片
  联集进 `wt_cards_v47sk` 现有卡片后,**至少补回 wikiP39037 缺失的 2 行
  金标锚点中的 1 行**(部分证实阈值);**2 行全补回**记完全证实。
- **H2(编译账本上限)**:联集 + 断言类型过滤后的新店
  `results/wt_cards_v47skf2`,离线编译账本(与 `scripts/b38e_score.py`
  §4b 逐字同一 `compiled_answer()`/`gold_equal()` 方法)在 140 题上的
  金标一致题数 **≥ 139/140**(现状 `v47skf` = 137/140,残留 3 题全部是
  `wikiP39037` 的 `v2cb`/`v2cc`/`v2fl`;若 2 行锚点全补回,离线编译理论上
  可以让这 3 题全部转对,达到 140/140——139/140 是留给"抽取到了但值/日期
  轻微对不上"这类边界情况的安全阈值,不是没把握达到 140)。
- **H3(真实读者)**:在 `results/wt_cards_v47skf2` 上跑真实读者(与
  `results/opt_batch38e_verdict.md` 同一读者/参数):
  - `sonnet-5 ≥ 96.0%`(现状 v47skf = 95.0%,`plainctx@sonnet5 mt4000` =
    97.1%),且与 `plainctx@sonnet5 mt4000` 的配对 McNemar 精确二项检验
    **不显著**(α=0.05,即"追平,不显著落后")。
  - `haiku-4.5 ≥ 94.0%`(现状 v47skf = 93.6%)。

## 二、方法(逐步骤,任务书原样)

1. **重抽**:`QVF_CARD_OWNER_GATE=0 QVF_CARD_MODEL=claude-sonnet-5
   QVF_CARD_THINKING=off QVF_CARD_TRACE=1 PYTHONUTF8=1 python -u
   scripts/wt_qvf_prototype_b38.py --phase write --data
   data/wikistate_full_ALL_v24.json --cards-dir
   results/wt_cards_v47s_pass2 --uids wikiP39037-Q3525068,
   wikiP39006-Q5220520,wikiP39017-Q24568849`(3 条链,单进程串行即可,
   预期成本量级 3×$0.14 ≈ $0.42,参照 `results/b38_provenance.txt` 的
   逐链均值)。`wt_cards_v47sk`/`wt_cards_v47skf`/`wt_cards_v47s` 全程只读
   (建店前后目录 sha256 核验,与批 38-B/38-E 同一机械证明方法)。
2. **联集 + 过滤**(新脚本 `scripts/b41_build_v47skf2.py`):对这 3 条链,
   把 `wt_cards_v47sk` 现有卡片与 `wt_cards_v47s_pass2` 新抽卡片取并集,
   去重键 = `(slot_class 或 slot 缺省, value 规范化, stated_date,
   source_span)`(v47sk 卡片有 `slot_class`,pass2 卡片是原版
   `wt_qvf_prototype_b38.py` 输出、没有 `slot_class` 字段,故键的第一段
   按"有 slot_class 用 slot_class,否则退化用 slot")。报告新增卡片数、
   新增金标锚点数(逐链)。再对联集结果应用与 `scripts/b38e_build_v47skf.py`
   逐字相同的断言类型过滤规则。其余 33 条链从 `wt_cards_v47skf` 原样字节
   复制。产物:`results/wt_cards_v47skf2`。
3. **读者**:`scripts/lb_reader_arm_b36b.py --arm smoc --cards-dir
   results/wt_cards_v47skf2 --questions results/b35_questions_sample36.jsonl
   --data data/wikistate_full_ALL_v24.json`,haiku-4.5
   `--max-tokens 800`(撞 `max_tokens` 上限的行用 `--max-tokens 4000` 补跑
   同 qid 写 `_mt4000.jsonl` 校正文件,口径与批 38-E 逐字相同)、sonnet-5
   `--max-tokens 4000`。输出
   `results/b41_smoc_v47skf2_<reader>.jsonl`。
4. **记分**(`scripts/b41_score.py`,改自 `scripts/b38e_score.py`):准确率、
   分题型、配对 McNemar(vs `v47skf` 两读者、vs `plainctx@sonnet5 mt4000`)、
   账本保真度(四店扩五店)、`wikiP39037` 3 题逐题现状、成本。产出
   `results/b41_score_out.txt`、`results/b41_provenance.txt`、
   `results/opt_batch41_verdict.md`。
5. **抽取不稳定性量化**:对这 3 条链,逐卡比较
   `results/wt_cards_v47s`(批 38 用同一脚本/同一命令建的"第一次抽取"
   结果)与本批 `results/wt_cards_v47s_pass2`("第二次抽取"),按
   `(slot, value 规范化, stated_date)` 做集合差,报告两轮各自独有的卡片数、
   共同卡片数、金标命中集合是否一致。

## 三、硬约束

- `wt_cards_v45`、`wt_cards_v47s`、`wt_cards_v47sk`、`wt_cards_v47skf`
  四店全程只读(建店前后目录 sha256 逐字相同)。
- `wt_cards_v47skf2` 的过滤规则必须与 `wt_cards_v47skf` 逐字同源(不得为了
  凑分改规则)；金标锚点零误删(与批 38-D/38-E 同一双重核验方法:命中索引
  集合翻转 + span 文本二次核验)。

## 四、预算

预算上限 $6(仓库纪律)。预估:抽取 ≈ $0.42 + 读者(haiku mt800 + sonnet
mt4000,140 题 ×2)≈ $0.63 + $1.79 ≈ $2.42 + 判官(另计,历史量级
$0.1-0.3)+ mt4000 校正补跑(haiku 撞顶行,历史 0 条,预留 $0.2 缓冲)。
合计预估 **≈ $3.0-3.3**,在预算内。实际花费见
`results/opt_batch41_verdict.md` §成本。
