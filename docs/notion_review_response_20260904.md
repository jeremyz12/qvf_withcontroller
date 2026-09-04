# 对 Notion 页《WikiState Chain》评审意见的核对与回应

日期:2026-09-04。来源:评审在 Notion 页 "WikiState Chain" 上对 QVF 写侧(建卡器)的六组意见。核对基准:仓库当前代码(分支 v20260812,提交 e393d5cd)与截至批 46d 的实验结果;本文里的离线实测全部零 API,脚本在会话 scratchpad(`measure_stores.py`、`measure2.py`、`localizer_recall.py`)。

## 0. 评审看的是哪个版本

评审看的是 GitHub 默认分支 origin/main 的 2026-08-27 快照,不是最新代码。证据:

- 评审引用的 `_catalog(batch, depth=0)` 没有 `digest` 参数;该参数在 2026-08-28 的批 22 提交(f8bca8a8)加入,origin/main 里没有,origin/v20260812 里有。
- 评审引用的 `_CARD_TEMP0`(08-17,ebdaece7)与 `_CARD_VERIFY_SPAN >= 3`(08-18,19f4302f)两者 main 都有,和引用一致。

v20260812 分支已推到 09-04(领先 origin/main 的写侧改动:`scripts/b38e_build_v47skf.py`、`b41_build_v47skf2.py`、`b46d_build_v48f.py`、`wt_qvf_prototype_v49.py` 四个新文件与 `wt_qvf_prototype.py` 112 行改动,合计 2,196 行)。评审因此没有看到批 38 至 46 的写侧结果:断言类型过滤、Sonnet 建卡店、第二遍抽取、建卡器回归修复、144 链全量冻结配置。下面逐条区分"评审说对了"与"基于旧代码或误读"。

## 1. 总表

| 条目 | 判决 | 一句话证据 | 行动 |
|---|---|---|---|
| 总体:会凭空抽出状态 | 部分成立,已量化 | 原句在语料里找不到的卡:v45 6.9%,v48f 3.5%;编译账目多出行 79 / 85(对 542 金标行);批 38c 逐卡审计:多出的是提名、计划、任务、重述,不是捏造的状态 | 关键词过滤已上线(批 38e);下一步换成语义蕴含校验 |
| 总体:预生成内容多、token 开销大 | 成立,但一次性且可摊销 | 每店 57.6(v45)/ 50.6(v48f)张卡;金标槽位车道只有 4.7 张对 3.76 行金标,其余 45–53 张属于别的槽位;建店 21.4K 入 / 7.8K 出 token(约 $0.06 一店);读时每题 2.75K 对整份记忆 13.6K,第 7 题回本 | 精简 schema 可省约 42% 卡片字符 |
| schema:claim 冗余 | 成立 | 账目渲染和编译路径都不读 claim;claim 占卡片字符 13.8%;只有 qvf/ 引擎路径用它 | 主线建卡器删 claim |
| schema:owner 无意义 | 基于旧代码;部分成立 | 主店 v45 / v48 根本没有 owner 字段(QVF_CARD_KEYS 默认关);它只在归属闸臂里有用:注入第三人称同槽状态时直读掉 18.4,写侧闸收回 92%;干净语料上闸店 86.25 对 89.29 | 保留为默认关的旗标,写明用途 |
| schema:value_tags 没用上 | 成立 | 三个主店 0 张卡带 value_tags;唯一消费者是标签查询臂,不在 WikiState 主线 | 从主线 schema 移除 |
| schema:implies_stale_slots / condition / VALIDITY SPECIES 纯猜测且没用 | 成立;且评审引用的 SPECIES 提示词属于另一条路径 | 非空率 implies_stale_slots 0.2%(v45)/ 3.1%(v48f),condition 2.3% / 0.9%;WikiState 账目路径不消费;`EXTRACTION_SYSTEM_PROMPT_SPECIES` 在 `qvf/engine_bridge.py:304`,是读时引擎抽取器的提示词,建卡用的是 `CATALOG_PROMPT` | 主线 schema 删这两个字段;species 留在引擎路径 |
| 抽取:单次 LLM 任务过重、上下文太长、漏状态 | 部分成立 | 漏金标行:haiku 单遍 71/542,Sonnet 单遍 21/542,加第二遍 14/542;14K 店 61K 字符,144 店全部单批(0 店超过 320K 字符预算),"token 太长"在 14K 店不成立;104K 店(440K 字符)才拆 2 批 | 两阶段值得试,前提是 Stage 1 无损 |
| 抽取:两阶段(廉价定位 → 强抽取) | 未证实;离线实测规则定位器有损 | LoCoMo 正则对 542 金标锚句召回 12.5%;加 20 条起始 / 槽位线索后 64.9%(只保留 5.2% 的轮次);批 33-J1:少一个会话的题 15.9 对覆盖齐 85.3 | 先测嵌入式定位器的锚句召回,≥99% 才进 Stage 2 |
| 校验器:只查子串,不查蕴含 | 成立,已部分处理 | v45 / v48 建店时 QVF_CARD_VERIFY_SPAN=0;逐字命中率 v45 91.7%,v48f 96.4%;评审的例子就是批 38c 的发现,批 38e 用关键词规则丢 203 张,编译上限 131→137/140,读者 88.6/91.4→93.6/95.0;批 46d 发现两处误伤 | LLM 蕴含判定替换关键词规则,144 链约 $4 |
| 规范化:槽位写在提示词里 | 基于旧代码;部分成立 | 后处理别名表 `SLOT_ALIASES` 与 v49 建卡器回填都存在;批 38b:提示词 slot_class 把碎片化链 7→1/36,但读者分数 92.9→88.6、92.1→91.4,无收益 | 保留后处理;不再指望提示词规范化提分 |
| 规范化:value 太弱 | 成立,已量化 | 相邻同值合并只用 `_norm`;金标车道相邻值变化中"近似重复"v45 47/300(16 链)、v48f 18/232(11 链),形态是 "CERN (fellow)"→"CERN" | 加值规范化(去括注、机构别名),离线回放 |
| 状态转移:关系边一次性生成、跨批悬空、更新缺失 | 误读;结论被否定 | WikiState 账目路径不读 temporal_relation / relation_target_record_ids;转移由 compile 按日期排序、相邻同值合并、计数得出,即评审提议的 Step 3–5;14K 店全部单批,v45 1,124 条边 0 悬空;编译上限 v48f 518/560 | 主线 schema 删关系字段(省 28% 字符) |

## 2. 评审的整体论点(如实转述)

评审认为:建卡器让一个 LLM 在一次调用里同时完成"判断是否状态、定槽位、定值、定日期、定关系、抄原句"六件事,这种设计既容易幻觉又浪费 token;schema 里 claim、owner、value_tags、implies_stale_slots、condition 这些字段要么冗余要么下游没人用;校验只查原句是否存在,不查原句是否支持该状态;规范化要么写在提示词里要么过弱;状态转移关系靠 LLM 在批内一次性标注,跨批必然断链。评审提议的替代方案是一条显式流水线:廉价定位候选句 → 强抽取器解析 → 规范化 → 按主体、槽位、时间排序 → 单独构建转移 → 给每条转移找证据。这个方案的前半段(两阶段抽取、语义校验)是本文认可的方向,后半段(排序、构转移、找证据)是仓库里已经在跑的 compile 路径。

## 3. 逐条核对

### 3.1 总体:幻觉、预生成内容多、token 开销大

评审原话:hallucination,会凭空提取一些 state;预生成内容过多;token overhead 很大。

判决:幻觉部分成立且已量化;内容多、开销大成立,但是一次性成本,读时反而省。

评审说对了什么:

- 原句在语料里找不到的卡确实存在:v45 8,288 张卡里 6.9% 的 source_span 在全店找不到(改写或捏造),v48f 3.5%(本文离线实测,`measure2.py`)。另外 1.4% / 0.1% 原句在店内但挂错了会话。
- 编译账目相对金标有多出的行:v45 79 行,v48f 85 行,对 542 金标行(results/opt_batch46d_verdict.md §2)。

需要修正或补充的事实:

- 多出的行不是"凭空捏造的状态"。批 38c 逐卡审计(results/b38c_card_audit.md §二)把非金标车道卡分成七类,落在 (c) 提名 / 候选与 (d) 一次性任务两类,原句都真实存在,是断言类型判断错了。这正是评审在"verifier"一节举的那类例子。
- 卡片数量的构成:每店 57.6 张(v45)/ 50.6 张(v48f),其中金标槽位车道只有 4.7 张(对 3.76 行金标),其余 45–53 张是这个人物的旅行、购物、家庭关系等别的槽位。"预生成内容多"多在别的槽位上,不是同一槽位重复抽。
- token 开销:建店 v45 每店 21,381 入 / 7,828 出 token,约 $0.06 一店(haiku 价);v48 Sonnet 25,940 / 8,174。读时每题 2,753 入 token(v48f)对整份记忆进 prompt 的 13,600;一个店问到第 7 题就收回建店成本(results/opt_batch46d_verdict.md §4、talk 第 16 页口径)。
- 卡片字符里 claim 占 13.8%,temporal_relation / relation_target_record_ids / condition / implies_stale_slots / slot_cardinality 五个字段占 28.2%;这两块加起来 42%,删掉可直接省输出 token。

行动:断言类型过滤已在批 38e 上线;下一步把关键词规则换成语义蕴含校验(见 3.4);schema 精简(见 3.2)。

最小实验:精简 schema(去 claim、关系与种类字段)在 36 链上重建一店,比较编译上限与建店输出 token;约 $5(Sonnet)。能判定:字段精简是否影响账目保真度。

### 3.2 schema 设计

评审原话:claim 没必要;owner 和 entity 重合;value_tags 没用上;implies_stale_slots 与 VALIDITY SPECIES 纯猜测、后续代码没用,不如删。

判决:claim、value_tags、implies_stale_slots、condition 四项成立;owner 基于旧代码,部分成立;评审引用的 SPECIES 提示词属于另一条路径。

逐字段核对(消费者用 file:line):

- claim:`scripts/repro_batch3.py:125` 起的 `render_card_ledger` 只渲染 stated_date、slot、value、source_span;`scripts/complex_query_arm.py` 读的字段是 value(17 处)、owner(6)、slot_class(5)、stated_date、source_span、source_memory_id、slot、slot_cardinality、value_tags,没有 claim。claim 只在 qvf/adapter.py、qvf/prompts.py、qvf/store_index.py 等引擎路径出现。占卡片字符 13.8%。判决:主线删。
- owner:v45、v48、v48f 三个主店的卡上根本没有 owner 字段(本文实测字段存在率;原因是 QVF_CARD_KEYS 默认关,批 46e 查明,2026-08-13 起如此)。有 owner 的是派生店 v45k / v45k2 与归属闸店。owner 和 entity 在干净语料上几乎重合(entity 99.2% 是 user),但它的用途是第三人称注入:批 32′ 往语料里注入第三人称同槽状态,直读从 90.45 掉到 72.05(−18.4,p=5e-20),写侧归属闸收回 92%;干净语料上闸店 86.25 对无闸 89.29,所以默认关(results/opt_batch32p_verdict.md)。判决:保留为旗标,文档写明"只在多人物语料开"。
- value_tags:三个主店 0 张卡有该字段(QVF_CARD_TAGS 默认关);唯一消费者 `scripts/complex_query_arm.py:472` `_tagged()`,服务标签查询臂,不在 WikiState 主线。判决:从主线移除。
- implies_stale_slots / condition:非空率 implies_stale_slots v45 0.2%、v48f 3.1%,condition 2.3% / 0.9%;账目路径不消费;消费者只有 qvf/engine_bridge.py、qvf/openai_bridge.py。没有任何一批测过它们的效果。判决:主线删。
- VALIDITY SPECIES 提示词:评审引用的 `EXTRACTION_SYSTEM_PROMPT_SPECIES` 在 `qvf/engine_bridge.py:304`,由 `engine_bridge.py:751-754` 的读时引擎抽取器使用;WikiState 建卡用的是 `scripts/wt_qvf_prototype.py` 的 `CATALOG_PROMPT`,其规则 3 只有 replacement / cessation / contradiction / unresolved 四种。评审把两条路径的提示词看成了一条。
- temporal_relation / relation_target_record_ids:见 3.6。

### 3.3 抽取:单次 LLM 任务过重、两阶段建议

评审原话:LLM 一步同时决定六件事;token 太长;long-context missing state;容易幻觉;建议 Stage 1 廉价定位候选句、Stage 2 强抽取器解析;问 `scripts/locomo_chain_extract.py` 的正则定位为何没迁移。

判决:漏状态与幻觉成立且已量化;"token 太长"在 14K 店不成立;两阶段方案未证实,规则定位器离线实测有损。

事实:

- 漏金标行(results/opt_batch46d_verdict.md §2,144 链 542 行):haiku 单遍 71 行(13.1%),Sonnet 单遍 21 行(3.9%),Sonnet 加无金标触发的第二遍 14 行(2.6%)。漏行随抽取器变强而下降,说明是抽取器能力问题,不只是上下文长度问题。
- 批大小:主语料 144 店平均 61,373 字符(约 15K token),最长 66,314;建卡预算 QVF_CATALOG_BUDGET 是 320,000 字符,144 店全部单批。104K 轨(data/wikistate_long_L2_b33.json,440K 字符)拆成 2 批。所以 14K 店上"一次调用上下文太长"不成立;104K 店上是否因分批漏状态,没有单独测过(未核实)。
- `scripts/locomo_chain_extract.py` 是 LoCoMo 链标注试点(提交 93125a74),用正则 PAT 找候选轮次交给 opus 做标注,是数据集标注工具,不是建卡器;没有迁移是因为它没被设计成建卡器。
- 本文离线实测(`localizer_recall.py`,542 金标锚句,23,754 轮):LoCoMo 正则 PAT 的锚句召回 12.5%,只保留 3.7% 的轮次;加上 20 条起始动词与槽位线索后召回 64.9%,保留 5.2% 的轮次。漏掉的锚句形如 "I'm officially on staff at Fermilab now"、"desde hoy trabajo en el Instituto de Física de Cantabria"(西班牙语)。规则定位器在这套语料上丢三分之一的锚句。
- 覆盖丢失的代价:批 33-J1(读时才建账目)检索覆盖齐的题 85.3,少一个会话的题 15.9(results/opt_batch33_verdict.md)。Stage 1 每漏一句,链就断一段。

行动:两阶段方案保留为候选,但 Stage 1 换成嵌入式定位器(按槽位类做查询,每店 top-k),先离线测锚句召回;批 37 的 dense top-50 在读时按题检索能到 99.8% 锚句覆盖,写时没有题,只能按槽位查询,召回需要重新测。

最小实验:嵌入式定位器锚句召回(OpenAI embedding,144 店约 24K 轮,约 $0.5);召回 ≥99% 再做 Stage 2 建店对照(36 链,约 $5)。能判定:两阶段是否在不丢覆盖的前提下降低漏行与多出行。

### 3.4 校验器:只查子串,不查蕴含

评审原话:代码只检查 source_span 是否出现在原文,不检查原句是否支持抽出的状态;例 "I considered joining Google" 被当成 employer=Google;建议加语义校验。

判决:成立;已用关键词规则部分处理;评审提议的 LLM 蕴含判定是更强的版本,值得做。

事实:

- v45 / v48 建店时 QVF_CARD_VERIFY_SPAN=0(卡上没有 source_span_verbatim 字段),子串校验也没开;本文离线实测逐字命中率 v45 91.7%、v48f 96.4%。
- 评审的例子就是批 38c 的发现:非金标车道卡是提名、候选、一次性任务、重述,原句真实、断言类型错(results/b38c_card_audit.md §二)。
- 批 38e 用关键词规则(`scripts/b38e_build_v47skf.py:42-72`,PLAN / TASK / PERSON / RESTATE 四组线索)在 36 链上丢 203 张(plan 136、restate 32、task 20、other_person 15),金标行零丢失,编译上限 131→137/140,读者 haiku 88.6→93.6、Sonnet 91.4→95.0(results/opt_batch38e_verdict.md)。
- 关键词规则的代价:批 46d 在 144 链上发现两处误伤,"I signed the offer and I'm officially joining Syracuse University" 因 "offer" 被当成 plan,"relocated to Cambridge for new job" 因 "new job" 被当成 task;因同一事实有另一张卡,净金标行未丢(results/opt_batch46d_verdict.md §7)。
- 但要说明上限:批 46d 显示账目质量提升(漏行 71→14,编译上限 85.9→92.5)没有传导成读者准确率(90.0 对 89.3,p=0.80)。语义校验能让账目更干净、更可审计,不应指望它提主表分数。

行动:用 LLM 蕴含判定替换关键词规则,输入是 (source_span, slot, value),输出 entailed 与类型(start / plan / task / other_person / restate / hypothetical)。成本:每店约 50 张卡,每张约 400 入 / 30 出 token,haiku 约 $0.03 一店,144 链约 $4。

最小实验:在 v48(过滤前)上离线回放,比较关键词规则与蕴含判定各自丢掉的卡、误伤金标行数、编译上限与多出行;$4 加判官。能判定:蕴含判定是否在零误伤下比关键词多清掉多出行。

### 3.5 规范化

评审原话:槽位规范化写在提示词里而不是后处理;value 只做 lower 与去连字符,Google / GOOGLE / google LLC、TUM 的三种写法不会合并。

判决:槽位部分基于旧代码,后处理早已存在,且实测提示词规范化无收益;value 部分成立,已量化。

事实:

- 槽位:提示词侧是 CATALOG_PROMPT_V4 的 slot_class(QVF_CARD_KEYS=1);后处理侧是 `scripts/complex_query_arm.py` 的 SLOT_ALIASES 别名表与 (owner, slot_class) 分组,v49 建卡器(`scripts/wt_qvf_prototype_v49.py`)在后处理阶段回填 slot_class。批 38b 实测:v47sk 把碎片化链从 7/36 压到 1/36(H1 证实),但 26 道碎片化题只多对 1 题(73.1% 对 69.2%),140 题总分 haiku 92.9→88.6(p=0.24)、Sonnet 92.1→91.4(p=1.0),H2、H3 被否定(results/opt_batch38b_verdict.md)。规范化把槽位名统一了,分数没动。
- value:compile 的相邻同值合并(`scripts/complex_query_arm.py:446-454`)只用 `_norm`。本文实测金标车道按日期排序后的相邻值变化:v45 300 次里 47 次是近似重复(包含关系或词重叠 ≥0.5),涉及 16 链;v48f 232 次里 18 次,涉及 11 链。形态是 "CERN (fellow)"→"CERN"、"University of Michigan (postdoctoral research fellow)"→"University of Michigan, postdoctoral research fellow"、"South Australian Health (research fellow)"→"South Australian Health"。这些会被数成一次变化,直接影响 change_count 与 longest_tenure。WikiData 标签本身一致,风险来自抽取器把职位并入雇主值。评审举的 TUM 例子在真实聊天记忆里更常见,在本数据集上少见。
- 金标比对函数 val_match(`scripts/b38e_score.py`)允许包含关系,所以这类近似重复在"命中金标"统计里大多算命中,但在计数题里仍多数一次。

行动:值规范化后处理:去括注、去 "LLC / Inc / Ltd"、机构别名表;同链同槽内再用嵌入相似度或一次廉价 LLM 判等价。

最小实验:离线回放 v45 与 v48f,统计规范化后 change_count 与 longest_tenure 的编译答案有多少题从错变对、多少从对变错;零 API。能判定:值规范化是否值得进主线。

### 3.6 状态转移

评审原话:建卡 LLM 一次性生成卡片和它与旧卡的关系;`_renumber_batch` 加批前缀后跨批引用悬空并在读时被静默丢弃;两批各两个雇主的例子"一定提取不出转移,直接缺失更新";建议五步流水线(抽卡、规范化、排序、构转移、找证据)。

判决:对关系字段的批评成立(这些字段对账目路径是多余的);"更新缺失"的结论被否定,因为账目路径不用关系边。

事实:

- WikiState 账目路径不读 temporal_relation 与 relation_target_record_ids:`scripts/complex_query_arm.py` 与 `scripts/repro_batch3.py` 里没有这两个字段的引用(grep 为零)。转移由 compile 得出:按 stated_date(缺则会话日期)排序、相邻同值合并、数转移、算任期(`complex_query_arm.py:446` 起)。这正是评审提议的 Step 3 与 Step 4;每行渲染时带 source_span(`render_card_ledger`),就是 Step 5。
- 批 44 已经把这条路径拆开量过:只按日期排序渲染(不合并、不计数)85.0,完整账目 89.3;读者看到的转移不来自 LLM 的关系标签。
- 关系边在哪里用:`scripts/wt_qvf_prototype.py:755-800` read_phase 的并查集里,关系边只作决胜(评分 4×槽位命中 + min(边数, 3)),槽位匹配主导;以及 qvf/engine_bridge.py 引擎路径。评审引用的 "read_phase :469 `if tgt in by_rid`" 是我方 `_renumber_batch` 文档字符串里的旧行号,当前对应 `wt_qvf_prototype.py:771`。
- 跨批:主语料 144 店全部单批(见 3.3),`QVF_CARD_RENUMBER` 默认关(`wt_qvf_prototype.py:107`);v45 的 1,124 条关系边全部在店内可解析,0 条悬空;v48f 有 43 条悬空,来源是第二遍抽取并集时 record_id 命名空间不同,不是跨批。104K 店拆 2 批时关系边确实会跨批悬空,但账目路径不用它们。
- 评审的两批例子放到本系统里:四张卡各带 stated_date,compile 排序后得到 Google→Meta→OpenAI→Anthropic 三次转移,和关系标签无关。编译上限 v48f 518/560 = 92.5%,change_count 130/144(results/b46d_score_out.txt §2)。
- 评审说对的部分:关系字段占卡片字符 28.2%(与 condition、implies_stale_slots、slot_cardinality 合计),LLM 标的关系是否可靠从未测过(v45 里 equivalent 5,534、replacement 757;v48f 里 unresolved 5,799、replacement 802,两个抽取器的标注分布完全不同,本身就说明标签不稳)。

行动:主线 schema 删 temporal_relation、relation_target_record_ids、slot_cardinality、condition、implies_stale_slots,关系边只留给引擎路径;与 3.1 的精简实验合并。

## 4. 遗漏点

- 评审页首附了一张图(截图),浏览器里无法放大读取,本文未核对其内容。
- 评审对 `_catalog` 对半分批递归的引用没有附意见,本文不作回应。

## 5a. 修复可行性(离线回放,零 API;脚本 `scripts/audit_notion_review/fix_replay.py`)

| 问题 | 能否修 | 回放结果 | 结论 |
|---|---|---|---|
| 四个多余字段(claim、value_tags、implies_stale_slots、condition)与关系字段 | 能,零风险 | 账目路径不读;占卡片字符 42% | 建卡器加精简旗标;省 token 要重建店才兑现 |
| 值规范化(employer / team / residence 去括注、去公司后缀) | 能,影响面小 | v45:改动 263/8,288 个值,金标车道链长变化 3/144 链,涉及 change_count 3、count_before 3、longest_tenure 2 题;v48f:改动 477 个值,15/144 链,涉及 15、15、13 题 | 读者是否因此改答案要跑读者才知道(离线上限口径 val_match 已容忍包含关系,看不出差别);最多影响 8% 的计数题 |
| 原句校验丢掉找不到原句的卡 | 只对强抽取器安全 | v48f 丢 257 张,编译上限 92.5% → 92.5% 不变;v45 丢 574 张,上限 85.9% → 83.6%,掉 13 题(改写了原句但值正确的卡被一起丢掉) | 用"标记 + 机械修复"(现有 QVF_CARD_VERIFY_SPAN=3),不用"丢弃"(=2) |
| 语义蕴含校验替换关键词规则 | 能,约 $4 | 未跑 | 见 3.4 最小实验 |
| 两阶段抽取 | 取决于定位器 | 规则定位器锚句召回 12.5%–64.9%,不可用;嵌入式定位器未测(约 $0.5) | 召回 ≥99% 才做建店对照 |
| owner ≈ entity | 不需要修 | 主店无该字段;归属闸旗标默认关 | 文档写明用途 |
| 跨批关系边悬空 | 不需要修 | 账目路径不用关系边;主语料全部单批 | 随精简字段一起删 |

回放里作废的一项:直接调用 `complex_query_arm._select_pool` 做"读侧编译回放"得到 v45 69.3%、v48f 56.1%,远低于编译上限,原因是两个主店没有 slot_class,池选择走了回退路径,这不是主表用过的路径(主表账目臂渲染整店,合并由读者完成;编译档用带 slot_class 的派生店 v45k)。该数字不作为证据。

## 5. 行动清单

零 API 离线可做:

1. 值规范化回放(3.5):去括注与机构别名,统计 change_count / longest_tenure 编译答案的变化。决定值规范化是否进主线。
2. 精简 schema 的字符与 token 节省估算(3.1):已算出 42%,无需再跑。

小额 API:

3. 蕴含校验回放(3.4):v48 全部 7,290 张卡过一遍 haiku 蕴含判定,约 $4;与关键词规则比误伤与多出行。
4. 嵌入式定位器锚句召回(3.3):约 $0.5;决定两阶段方案是否有资格进入建店对照。

新一批实验:

5. 精简 schema 建店(3.1、3.6):36 链 Sonnet,约 $5;比较编译上限与输出 token。
6. 若 4 通过:两阶段建店对照(3.3),36 链约 $5 加读者 $3。

## 6. 给评审的回复草稿

总:谢谢逐段读代码。你看的是 main 分支 8 月 27 日的快照,9 月 4 日推的 v20260812 分支上写侧多了断言类型过滤、Sonnet 建卡、第二遍抽取和建卡器修复,下面按你的六点逐条说结论。

幻觉与开销:成立。原句在语料里找不到的卡 v45 占 6.9%,新店 3.5%;多出的账目行 79 到 85 行(对 542 行金标),逐卡审计发现多出的是提名、计划、任务这类原句真实但断言类型错的卡。建店每店约 $0.06 一次性,读时每题 2.75K token 对整份记忆 13.6K,第 7 题回本。

schema:claim、value_tags、implies_stale_slots、condition 四个字段账目路径确实不读,准备从主线删掉,合计能省约 42% 卡片字符。owner 在主店里根本没有(旗标默认关),只在多人物注入实验里用,那里它收回了 92% 的损失,所以保留为旗标。你引用的 VALIDITY SPECIES 提示词是读时引擎那条路径的,建卡用的是 CATALOG_PROMPT。

抽取:漏状态成立,haiku 单遍漏 71/542 行,Sonnet 加第二遍漏 14 行。14K 店全部单批,上下文长度不是主因。两阶段方案我认同方向,但规则定位器离线测下来对金标锚句只有 12.5% 到 64.9% 的召回,漏掉的多是 "I'm officially on staff at Fermilab now" 这类句子;下一步先测嵌入式定位器的召回,不低于 99% 再做建店对照。

校验器:成立。你举的例子正是我们 38 批审计的发现,目前用关键词规则处理,编译上限从 131 提到 137/140,但在 144 链上有两处误伤。准备换成你说的蕴含判定,144 链约 $4。要说明的是账目更干净没有换来读者分数,144 链全量上是 90.0 对 89.3。

规范化:槽位这边后处理别名表一直在,提示词规范化实测把碎片化链从 7 压到 1 但分数没涨。值这边你说得对,相邻值变化里有 6% 到 16% 是 "CERN (fellow)" 对 "CERN" 这类近似重复,会被多数一次变化,准备加值规范化后处理并离线回放。

状态转移:关系字段对账目路径是多余的,准备删。但转移不是靠关系边算的:compile 按日期排序、相邻同值合并、计数,就是你画的 Step 3 到 5,你的两批例子在这条路径上会得到三次转移。主语料 144 店都是单批,v45 的 1,124 条关系边零悬空;104K 店拆两批时边会悬空,但那条路径不用它们。

## 7. 未核实清单

- 104K 店拆 2 批建店是否因分批漏状态:没有单独测过。
- LLM 标注的 temporal_relation 是否可靠:从未评估,只知道两个抽取器的标签分布差异很大。
- 蕴含判定是否在零误伤下优于关键词规则:未跑。
- 嵌入式定位器在写时按槽位查询的锚句召回:未测。
- 关系边对 qvf 引擎路径(非 WikiState)的贡献:未测。
- 评审页首的截图内容:未读取。
