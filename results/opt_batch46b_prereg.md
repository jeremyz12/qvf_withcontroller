# 批 46b 预注册 — 104K 规模上 write-time 卡片是否仍然重要(render-only / render-raw 复刻批 44,换到 L2)

日期 2026-09-04。运行前提交,先注册后跑批。

## 0. 动机与待验证问题

批 44(14K 规模,`results/opt_batch44_verdict.md`)发现:layout+协议解释了
ledger 相对全文的约 88% 的增益,render-raw(关键词命中的原始 user 轮次,零
write-time 抽取)几乎追平 render-only(卡片账目,题面槽位选中)——
85.36% vs 85.00%,统计上不可分(McNemar p=0.927)。这对论文主张构成一个
尚未在规模轴上检验的反例:**write-time 卡片抽取本身,在 14K 规模上看不出
可测的价值**。批 39/40 已经证明"规模一上去,检索会先坍塌"(dense_top100
只有 38.3%,金锚覆盖需要 top-100 才够);本批要问的是同一规模轴上,
**卡片抽取(write-time compile)相对"只是把关键词命中的原始语句按日期
排表",价值是否会随店变大而显现**——因为直觉上店越大,越需要"提前算好"
的结构化摘录来对抗噪声稀释,关键词检索也越容易在原始文本上大海捞针。

## 1. 复用与不改动的部分(如实声明)

- 两条臂的**实现代码逐字复用** `scripts/lb_reader_arm_b44.py` 的
  `--arm renderonly` / `--arm renderraw` 两个分支(owner/slot 三层选择、
  关键词命中 user 轮次、`SMW_PROMPT`/`parse_answer`、行版式),**不重写
  选择/渲染逻辑本身**——本批只是把 `--data`/`--questions`/`--cards-dir`
  换成 L2 规模的语料,新写的部分只有:①一层"渲染行数过大时按同题
  render-only 行数截断"的防御性配额闸(§4,预期不触发,见 §6 干跑数据),
  ②按两个卡片店目录分别跑、结果追加合并到同一输出文件(与批 40 处理
  L2 卡片店拆两目录的做法同构)。
- 判官:`qvf.judge.ClaudeJudge`(与批 39/40/44 同一冻结类,未改动)。
- 读者:`claude-haiku-4-5`,`temperature=0.0`(仅 haiku 分支发送),
  `max_tokens=800`(与批 44 逐字同值;任务书指定 haiku-4.5/mt800 与批 44
  一致,不是批 40 用的 sonnet-5/mt4000)。
- 计价:haiku $1.00/M in、$5.00/M out(与批 39 协调员口径一致,批 44 脚本
  `PRICES` 常量本身用的也是这个数,逐字沿用)。

## 2. 数据配置

- 语料:`data/wikistate_long_L2_b33.json`(30 店,104K-token 库,与批
  33-D/39/40 同一份,只读)。已核验:30 个 uid 与题集、两个卡片店目录的
  uid 并集**完全重合、零缺口、零重叠**(20 店在 `results/wt_cards_b33_L2`,
  10 店在 `results/wt_cards_b27_L2`,并集=语料 30 uid,交集=空)。
- 题集:`data/wsc_long_L1_questions.jsonl`(120 题 = 30 uid × 4 题型,
  与批 33-D/39/40 逐字节同一份)。
- 卡片店(仅 renderonly 需要,renderraw 不读卡片店,直接读语料
  `sessions`):`results/wt_cards_b33_L2`(20 店)+ `results/wt_cards_b27_L2`
  (10 店),与批 40 的投影/全账目臂同一张卡片店,只读、不重建(遵循卡店
  冻结纪律)。renderonly 按 uid 归属分两次调用(`--cards-dir` 分别指向
  两个目录),结果追加到同一个 `--out` 文件(脚本自带
  append-and-skip-done,与批 40 处理两卡片店目录的方式同构)。

## 3. 归档对照臂(不重跑,直接复用批 39/40 已入库产物)

| 对照臂 | 头条准确率 | 来源 |
|---|---|---|
| 槽位投影(archived projection) | **61.67** | 批 39/33-D,`b33d_slot_L2_new20`+`b33_smoc_L2probe_slot` |
| 全账目 smoc(archived full ledger) | **54.17** | 批 39/33-D,`b33d_smoc_L2_new20`+`b33d_smoc_L2_old10_repro` |
| dense_top100(最强检索基线) | **38.33** | 批 39,`results/b39_dense_top100_L2.jsonl` |
| haiku 全文(fullplain/PLAIN_PROMPT) | **7.50** | 批 39/33-D,`b33d_full_haiku_L2_new15`+`b27_full_haiku_L2` |

四个数字与 `results/opt_batch39_verdict.md` §一头条表逐位一致,本批
记分脚本会重新从这些既有 jsonl 文件计算一遍(不手抄数字),核验后如与此表
不符会在判词里如实标注。

## 4. 渲染行数配额闸(防御性,预期不触发)

- **判据**:某题 render-raw 渲染文本的估算 input token(`len(text)/3.4`,
  与批 44 脚本预算估算口径同函数)若 **> 40,000**(= L2 单店全文 token
  中位数 103,736 的约 38.6%——超过这个比例,已经不是"挑出相关语句"而是
  "几乎把整店都塞进去",判定为"表泛滥",不是"检索"),则触发截断:
  - 截断参照行数 = **同一题号 render-only 实际渲染的行数**(同一 uid、
    同一目标槽位,render-only 已经算出;两臂的截断参照口径统一到"同题
    卡片抽取会用几行"这一个数,而不是外部再定义一个行数);
  - 截断方式:render-raw 命中行按日期升序排序后,**保留最早的 N 行**
    (N=render-only 该题行数,不足 2 则至少保留 2 行)——保留最早而非
    最新,是因为 render-raw 的渲染循环本身按日期升序编号,保留前缀即
    保留"最早出现的证据",这是一个任意但预先声明的 tie-break,不依据
    结果调整;
  - 每题记录 `renderraw_rows_before_cap` / `renderraw_rows_dropped`
    两个字段,判词里逐店点名报告(如触发)。
- **干跑核验**(`scratchpad/b46b/dry_run_diag.py`,零 API 调用,基于
  `len(text)/3.4` 估算):120 题里 render-raw 估算 input token
  均值 **4,377**、中位 **4,068**、**最大 17,867**(1 店 4 题触顶,
  `wikiP54004-Q29589370`,199 行)——**全部远低于 40,000 的配额闸**,
  预期本批**不会触发**任何截断。若实跑(真实 tokenizer,非 `/3.4` 估算)
  出现与此干跑估算显著不符的情况(截断触发),会在判词里如实报告,
  不回改这条判据。

## 5. 假设与阈值(运行前预注册,不得事后按结果调整)

- **H1**(render-raw 在 104K 规模上相对槽位投影大幅失分,原因是关键词
  匹配在约 10 万 token 规模上要么灌水要么漏检):
  `acc(render-raw) <= 61.67 - 15 = 46.67`(即比投影低 ≥15pp)。
- **H2**(render-raw 的渲染行数与 input token 双双相对投影发生量级膨胀):
  两个子判据都要满足才算 H2 成立:
  - token 子判据(任务书原话锚定的数字):
    `mean(render-raw 实测 usage_input_tokens) >= 2 x 8,800 = 17,600`;
  - 行数子判据(**操作化说明,需在此明确、跑前定死**:归档投影臂
    `results/b33d_slot_L2_new20.jsonl` 等四个文件**没有记录
    `rendered_rows` 字段**,无法直接取"投影渲染了几行"这个数;因此行数
    对照改用**本批同一方法论新跑出的 render-only 臂自身的
    `mean(rendered_rows)`** 作为"投影量级"的同批次代理——render-only
    在概念上就是"题面槽位卡片账目",与批 39/40 里 `QVF_LEDGER_VIEW=slot`
    的投影是同一构造思路的两种实现,批 44 判词已证明二者在 14K 规模上
    统计不可分,故用它作代理不改变比较的实质含义):
    `mean(render-raw rendered_rows) >= 2 x mean(render-only rendered_rows)`。
  - 干跑参考(§4 已给出,非最终判据,仅供跑前预期):估算 rows 比值
    ≈8.05x、估算 token 比值 ≈7.26x——若实测比值维持在这个量级,H2 会
    被证实;若实测 token 比值大幅低于估算(比如系统性地小于 2x),
    H2 的 token 子判据会被否定,报告会如实按子判据分别判定,不合并成
    一个笼统结论。
- **H3**(render-only 相对全账目仍然维持"编译机制份额小"的结论,即使
  规模从 14K 上到 104K):
  `|acc(render-only) - 54.17| <= 5`(render-only 落在 [49.17, 59.17] 区间
  内,即与全账目差距在 ±5pp 内)。**注**:与批 44 不同,批 44 的 H1 比较
  对象是"smoc(全账目)vs render-only",在 14K 规模上 smoc(89.29)>
  render-only(85.00);但批 39/40 已发现 L2 规模上排序反转——投影
  (61.67)> 全账目(54.17)。本批 H3 沿用任务书指定的比较对象"全账目
  54.2",但判词会同时报告 render-only 相对投影(61.67)的差距作为
  补充读数,避免因规模反转而产生误导性的单一数字。

## 6. 统计方法(与批 39/44 同源,逐字复用)

- 头条:准确率 + Wilson 95% CI(与批 39 `wilson()` 同函数);
- 配对 McNemar(精确符号检验,`sign_p`,与批 33-A/39/44 同函数);
- 30 店级簇自助 95% CI(N=10000,seed=20260904;批 39 用的是 30 店/N=4000,
  本批题量与批 39 相同(120 题 30 店),沿用"以 uid 为簇"的同一构造,
  仅把 seed 换成本批日期避免与其它批次自助抽样巧合复用同一随机流,
  N 提到 10000 与批 44 一致、比批 39 的 4000 更保守);
- 配对对象:render-only vs render-raw、render-only vs 投影(61.7)、
  render-only vs 全账目(54.2)、render-raw vs 投影(61.7)、render-raw vs
  全账目(54.2)、render-raw vs dense_top100(38.3)、render-only vs
  dense_top100(38.3)、两臂各自 vs haiku 全文(7.5)。

## 7. 产物

- `results/b46b_renderonly_L2.jsonl`(120 行,追加写 + 已完成跳过续跑,
  4 workers)
- `results/b46b_renderraw_L2.jsonl`(120 行,同上)
- 跑批脚本:`scripts/lb_reader_arm_b46b.py`(`lb_reader_arm_b44.py` 的
  L2 适配副本,变更点见 §1/§4,逐条注释标注与原件的差异)
- 记分脚本:`scripts/b46b_score.py`,完整输出 `results/b46b_score_out.txt`
- 判词:`results/opt_batch46b_verdict.md`

## 8. 已知偏离与限制(先于跑批列出)

1. render-only 的"三层 owner/slot 选择"逻辑是批 44 的新写代码(非
   `render_card_ledger` 现成路径),在 14K 规模的 144 店上做过离线预演;
   本批是它第一次跑在 104K 规模的 30 店上,选择层级分布会在判词里重新
   报告,不假定与 14K 规模同分布。
2. render-raw 的角色解析器、关键词表构造(含混入语料 `chain` 取值词的
   让步)与批 44 完全相同,继承批 44 prereg §7.4 里"这不是零先验知识的
   检索基线"的限定,本批同样如实标注。
3. 配额闸(§4)的截断参照用"同题 render-only 行数"而非独立定义的行数
   上限,这是本批新引入的操作化选择(批 44 在 14K 规模上从未触发过这类
   截断,没有先例可循),已在跑前定死规则,不按结果调整。
4. H2 的"行数子判据"改用同批次 render-only 均值作代理(§5 已说明原因),
   是相对任务书原文"projection's (8.8K)"字面表述的一处操作化偏离,已在
   跑前如实注册,不是跑后为了凑判决而改的。
5. 单次跑,无重复;本机 run 间抖动 3–4pp(环境限制在档),H1/H2/H3 的
   判据阈值(≥15pp / ≥2x / ±5pp)均设计为远大于这一抖动量级。
6. 判官 usage 不落盘到判官侧累计文件(环境限制在档),判官成本本批仅按
   `judge_input_tokens`/`judge_output_tokens` 逐行落盘的字段汇总,不依赖
   judge 对象的进程内累计器。
