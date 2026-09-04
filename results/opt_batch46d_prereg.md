# 批 46d 预注册 — 冻结写入侧配置,144 链全量建店 + 全量 headline

日期 2026-09-04。运行前提交,先注册后跑批。上游:批 38(v47s,36 链抽样,
`QVF_CARD_MODEL=claude-sonnet-5` / `QVF_CARD_THINKING=off` / `max_tokens=16000`
一链一次调用)、批 38-E(v47skf,断言类型过滤器 `scripts/b38e_build_v47skf.py`)、
批 41(v47skf2,gold-anchor 触发的第二遍抽取,仅 3 链——**本批不复用批 41 的
触发规则**,那条规则用金标链判断哪条链要重抽,本批任务书明确要求 gold-free
规则)。本批把这条写入侧配置从 36 链抽样**放大到全部 144 链**,并产出一次
全量 headline。

## 零、开工前核验:任务书引用的基线数字,能否在全量口径下复现(重要修正)

任务书写"H1 compiled-ledger-vs-gold on all 560 questions ≥ 98%(v45 was
91.7% of rows)"。**91.7% 这个数字的真实出处**是 `results/opt_batch38_verdict.md`
§六:36 条链抽样、133 条金标行、122 行精确命中 = 91.7%——**这是 36 链/133
金标行口径,从未在 144 链/560 题的全量口径下复现过**。开工前用
`scripts/b38e_score.py` 里 `diag_uid()`/`compiled_answer()`/`gold_equal()`
的**逐字同一套函数**(零改动,离线复算、零 API 调用)在 `results/wt_cards_v45`
店上重新measure 两种可能口径,结果如下:

| 口径 | 分母 | v45 全量结果 |
|---|---|---|
| compiled-answer ceiling(§4b method,question-level,560 题) | 560 题 | **481/560 = 85.9%** |
| gold row exact-match(§六 method,row-level,144 链) | 542 金标行 | **471/542 = 86.9%** |

两个口径在全量下都不是 91.7%,而是 85.9%/86.9%——**36 链抽样本来就不是
144 链的无偏子集**(批 38 挑选 36 链时未做分层抽样),放大到全量后账目保
真度的表观上限下降约 5-6pp 是符合预期的(更多链 = 更多机会遇到抽取器的
边缘失败模式)。

**据此修正**:H1 的度量口径采用任务书原文"on all 560 questions"这一措辞
最贴合的 **compiled-answer ceiling(question-level,560 题分母)**,阈值
**≥98% 原样保留**(任务书明确给出的数字,不因基线对不上而下调);但判词
会同时报告 v45 全量真实基线 **85.9%**(而非任务书援引的 91.7%),并明确
写"任务书援引的 91.7% 是 36 链子样本的历史数字,不是本批验证的口径"。
row-level 口径(471/542=86.9%)作为§4b 之外的补充证据一并入档,不作为
H1 判据。

## 一、假设(H1–H3,任务书原样阈值 + 上面的口径修正)

- **H1(编译账本上限,零 API,离线复算)**:`results/wt_cards_v48f`(见下)
  在全部 560 题(`data/wsc_s5_v25.jsonl`)上用 `compiled_answer()`/
  `gold_equal()`(逐字复用 `scripts/b38e_score.py`,lane 选择用
  `diag_uid()` 同一套 gslot 命中逻辑)算出的 gold-equal 命中率
  **≥98%**。对照:v45 全量真实基线 85.9%(见零节,非任务书援引的 91.7%)。
- **H2(真实读者账本准确率)**:`results/wt_cards_v48f` 店上跑
  `claude-haiku-4-5` 读者(`scripts/lb_reader_arm_b36b.py --arm smoc`)
  在全部 560 题上的判官准确率 **≥92%**(对照 v45 = 89.29%,出处
  `results/opt_batch44_verdict.md` §3.1 smoc 行,任务书原样引用)。两次
  独立跑(run1/run2)分别判定,并报均值。
- **H3(读者侧成本)**:每题均输入 token **≤ v45 的 2,937**(出处
  `results/opt_batch44_verdict.md` §3.5 smoc 行"均 in tok"列,任务书原样
  引用)。run1/run2 分别判定,并报均值。

## 二、写入侧冻结配置(建店,144 链全量)

- 抽取模型:`claude-sonnet-5`(环境变量 `QVF_CARD_MODEL=claude-sonnet-5`)。
- 建卡器:`scripts/wt_qvf_prototype_b38.py`(批 38 冻结副本,相对
  `scripts/wt_qvf_prototype.py` 只有"不发 temperature + 可关思考"两处
  受控改动,逐字节复用,不新建副本)。
- 关思考:`QVF_CARD_THINKING=off`(显式 `thinking={"type":"disabled"}`,
  理由与批 38 相同——避免 `max_tokens` 被思考吃满导致同链拆两次调用)。
- `max_tokens=16000`(脚本内建默认,不覆盖)。
- 不发 `temperature`(`_card_wants_temperature("claude-sonnet-5")` 为
  `False`,脚本自动省略该键,与批 38 逐字节同构)。
- `QVF_CARD_OWNER_GATE=0`(批 38/41 同配置)。
- `QVF_CARD_TRACE=1`(逐批 trace 落日志,供逐链成本核算)。
- 一链一次调用(除非模型侧因批过大自适应对半分批——脚本内建的失败重试
  路径,`QVF_CARD_TRACE=1` 会在日志里暴露是否触发)。
- 语料:`data/wikistate_full_ALL_v24.json`(与批 33-A/38/41 同一份,只读;
  与题源 `data/wsc_s5_v25.jsonl` 配对)。
- uid 全集:144 链,清单 `results/b46d_all144_uids.txt`(逐字等于
  `results/wt_cards_v45` 的 144 个文件名词干,已核验 `match: True`)。
- 命令(N 分片并行,分片数视本机并发观测调整,记入
  `results/b46d_provenance.txt`):
  ```
  QVF_CARD_OWNER_GATE=0 QVF_CARD_MODEL=claude-sonnet-5 QVF_CARD_THINKING=off \
  QVF_CARD_TRACE=1 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype_b38.py \
    --phase write --data data/wikistate_full_ALL_v24.json \
    --cards-dir results/wt_cards_v48 --uids <shard>
  ```
- 幂等性:脚本对已存在的 `<uid>.json` 直接跳过(`if out_f.exists(): continue`),
  故分片跑批可断点续跑,不会重复计费。

## 三、GOLD-FREE 第二遍规则(不看金标链,只看第一遍记录数)

- **触发判据**:链 u 的 `results/wt_cards_v48/<u>.json` 记录数
  `len(records)`,若满足 **(a) 落在 144 链记录数分布的下四分位(≤Q1,
  numpy 线性插值法 `numpy.percentile(counts, 25)`)或 (b) 低于 144 链
  记录数中位数的 60%(`< 0.6 * median`)** 之一,即触发第二遍抽取。
  两条件取 **并集(OR)**,链一旦满足其一即入选。
- 判据只读 `wt_cards_v48` 自己的记录数,**不读语料的 `chain` 字段、不看
  金标行数、不做任何金标锚点核验**——与批 41(gold-anchor 触发,只挑
  3 条金标缺口链)在方法论上是两条互斥的规则,本批严格执行任务书指定的
  gold-free 版本。
- 触发链的第二遍抽取:命令与二节逐字相同,只换 `--cards-dir
  results/wt_cards_v48_pass2`,`--uids` 限定为触发链子集。
- 联集与过滤(`results/wt_cards_v48f`,新脚本 `scripts/b46d_build_v48f.py`,
  逐字复用 `scripts/b41_build_v47skf2.py` 的去重键与断言类型过滤器):
  - 未触发的链:`wt_cards_v48` 原样字节复制到 `wt_cards_v48f`,再套用
    与 `scripts/b38e_build_v47skf.py` 逐字相同的断言类型过滤器(丢
    plan/task/other_person/restate,留 start+unknown)。
  - 触发的链:`wt_cards_v48` 现有卡片 ∪ `wt_cards_v48_pass2` 新抽卡片,
    去重键 = `(slot_class 或 slot 缺省, value 规范化, stated_date,
    source_span)`(与批 41 逐字相同),联集后再套用同一断言类型过滤器。
  - 记录:触发链数、每条触发链的 pass1/pass2/联集记录数、新增记录数。

## 四、读者臂(全量 560 题,两次独立跑)

- `scripts/lb_reader_arm_b36b.py --arm smoc --reader anthropic:claude-haiku-4-5
  --cards-dir results/wt_cards_v48f --questions data/wsc_s5_v25.jsonl
  --data data/wikistate_full_ALL_v24.json --max-tokens 800 --workers 4
  --out results/b46d_smoc_v48f_haiku_run{1,2}.jsonl`(两次独立、各自从零
  跑,不共享 `done` 续跑状态——run2 用独立输出文件保证真独立)。
- 撞 `max_tokens=800` 上限的行(`stop_reason=="max_tokens"`)用同 qid、
  `--max-tokens 4000` 补跑,写 `..._run{1,2}_mt4000.jsonl`,记分时按批
  38-E 同一口径合并校正(mt4000 覆盖 mt800 的同 qid 行)。
- 判官:`qvf.judge.ClaudeJudge`(默认模型,未改动)。

## 五、记分与产物

- `scripts/b46d_score.py` → `results/b46d_score_out.txt`:
  - 四店(v45/v47s 参照 + v48/v48f 本批,视文件是否存在)写入侧保真度表
    (`diag_uid` 聚合:金标行/精确命中/日期偏/漏行/多出/卡片总数/完美链);
  - H1 编译账本上限表(560 题,zero-API,v45 对照 + v48f 本批);
  - H2/H3:run1、run2、run 均值三行,准确率/分题型/tokens/$每题;
  - 配对 McNemar:run1 vs v45(`results/b33A_smoc_v45.jsonl` 过滤到 560
    题)、run 均值 vs v45(560 题上每题取两次跑的多数判定或平均正确率,
    如实注明口径);
  - 144 链簇自助 CI(`N_BOOT=10000, seed=20260902`,逐字复用
    `scripts/b33A_score.py::compare()`):v48f-haiku vs
    `results/b33A_direct.jsonl`、vs `results/b33A_smw.jsonl`、vs
    `results/b33A_smwplain.jsonl`(三个比较对全部先把 33-A 那三个文件
    过滤到 560 个 question_id 上,不外推、不重跑);
  - 成本表(建店 + 读者,判官另计)。
- `results/opt_batch46d_verdict.md`:H1-H3 判决(先判决后数字)、成本、
  偏离、未验证。
- 溯源:`scripts/b46d_provenance.py` → `results/b46d_provenance.txt`(仿
  `scripts/b38_provenance.py`:建店窗口、逐链成本、店目录 sha256、读者臂
  运行时窗/成本)。

## 六、硬约束

- `wt_cards_v45`、`wt_cards_v47s`、`wt_cards_v47sk`、`wt_cards_v47skf`、
  `wt_cards_v47skf2` 全部既有店全程只读(建店前后目录 sha256 逐字相同,
  与批 38/38-E/41 同一机械证明方法)。
- `wt_cards_v48`/`wt_cards_v48_pass2`/`wt_cards_v48f` 三店互相不覆盖(各
  自独立目录,`wt_cards_v48f` 从空目录重建,不残留旧文件)。
- 断言类型过滤规则与 `scripts/b38e_build_v47skf.py` 逐字同源,不为凑分
  改规则。
- Gold-free 纪律:第三节的触发判据函数本身不得 import 语料 `chain` 字段
  或任何 gold 相关数据结构——代码审查项,记入 `results/opt_batch46d_verdict.md`。

## 七、预算

- 环境准则:builder+读者合计花费上限 $40(判官另计)。
- 预估:建店 pass1 144 链 × 约 $0.14/链(批 38 逐链均值)≈ **$20.2**;
  pass2(视触发链数,预估约 25-35 链)≈ $3.5-4.9;读者两轮 560 题
  haiku(mt800,参照批 44 smoc $1.627/560题 量级,本店可能行数不同,
  留量级余地)≈ $1.5-2.5/轮 × 2 ≈ $3-5;mt4000 校正补跑(历史上撞顶行
  很少)≈ $0.5 缓冲。合计预估 **≈ $27-31**,在 $40 内,留有余量。实际
  花费见 `results/b46d_provenance.txt` 与 `results/opt_batch46d_verdict.md`
  §成本。

## 八、已知偏离(先于跑批列出)

1. H1 的判据口径从任务书援引的"91.7%"改判为"全量复算的 85.9%"作为
   基线上下文(见零节)——阈值本身(≥98%)不变,只是不再声称"v45 在全
   量口径下就是 91.7%",这个数字对不上是本批开工前核验发现的,不是本
   批引入的偏离,是对任务书援引数字的必要修正。
2. run1/run2"独立"的操作化定义是"各自零续跑状态、各自从空产物文件开
   始",不是"两次完全独立的进程环境"(判官、卡片店、语料都共享同一份
   只读输入)——这是"两次独立读者调用"在这个项目里的标准操作化,与批
   38-E 的 mt800→mt4000 校正口径一致,不是本批新发明的宽松化。
