# 批 44 预注册 — render-matched control(层版式 vs 编译机制拆分)

日期 2026-09-04。运行前提交,先注册后跑批。

## 0. 动机

对照 arXiv 2607.16019《Presentation, Not Mechanism》的质疑:ledger 账目臂
(smoc)相对全文/摘要臂的增益,有多少来自"表格版式本身"(结构化、按日期
排序的行,视觉上更易扫读),有多少来自"编译机制"(卡片抽取/筛选/去重/
计数等 write-time 或 render-time 的计算)。本批构造两条**版式对齐**的对
照臂,与既有 smoc/smw/smwplain 三臂做拆分。

## 1. 代码走查结论(先于设计的必读项,发现与任务预设有偏差,如实记录)

- `scripts/lb_reader_arm_b36b.py::build_prompt` 的 `--arm smoc` 分支:
  `user = SMW_PROMPT.format(question=..., transcript=led[uid])`,
  `led[uid] = render_card_ledger(uid, entries[uid], cards_dir=a.cards_dir)`
  (定义于 `scripts/repro_batch3.py` / 逐字同拷于 `repro_batch3_b33.py`)。
- **`render_card_ledger` 实测行为**(逐行读码 + 现场跑样本核验):
  - 从 `cards_dir/{uid}.json` 的 `records` 列表读入(write-time 卡片抽取
    产物,每条记录 = 一次 LLM 对单个 memory turn 的槽位抽取,字段
    `record_id/source_memory_id/slot/value/source_span/entity/stated_date`
    等);
  - 按 `stated_date`(缺则查 `_mem_dates` 用会话日期兜底)**升序排序**;
  - 渲染成 `[entry N] DATE | SLOT: VALUE — "SPAN(前120字符)"` 逐行;
  - **默认视图(`QVF_LEDGER_VIEW` 未设置,33-A 实跑用的正是这个默认分支)
    不做任何槽位筛选 —— 渲染该 uid 名下的全部记录,不限槽位、不限实体**。
    实测 `results/wt_cards_v45/wikiP108000-Q59200022.json`:50 条记录跨
    ~20 个槽位(hobby/employer/job_title/commute_mode/…),题面槽位
    `employer` 仅占 4 条 —— 即 33-A 里真正喂给读者的 smoc 账目是"全店
    多槽位账目",并非"本题相关槽位账目"。
  - **代码里确实没有"证书过滤(certify)/合并相邻同值(merge)/转变计数
    (transition count)"这三步** —— 这三个词描述的其实是另一条**完全
    独立**的读取管线:`scripts/complex_query_arm.py` 的 `filter`/
    `usability`/`compile` 三臂(阶梯量表见 `results/b33A_score_out.txt`
    §4:select→certify→compute,对应 `filter→usability→compile` 三个
    rung),它们用查询计划执行器 `execute_plan`/`execute_plan_indexed`
    在**答题时**对某个槽位的链条做选择(select_chain)、去噪
    (`_hygiene_pool`/certify)、合并(`_chain_merge`)、并计算
    `count_changes`/`count_before`/`longest` 等派生结论行 —— 这条管线
    用 `PLAIN_PROMPT`,产物是 `results/b33A_{filter,usability,compile}.jsonl`,
    与 smoc 的账目管线**互不调用**。阶梯里 `compile→smoc(v45)` 一档
    (`+11.28pp`,`results/b33A_score_out.txt` 第92-96行)本身就同时改了
    两件事(证据完整度 + 协议提示词),不是一次干净的"机制开关"对照。
  - `qvf/store_index.py`(`select_chain`/`asof`/`_chain_merge`/
    `_hygiene_pool`)是上述 filter/usability/compile 管线的索引化实现,
    同样**不被 smoc 调用**。

  **结论(需在结果里明确复述,不能默认任务预设成立)**:任务描述"compile
  做 date sort、merge adjacent equal values、transition count、certify/date
  filtering"这四件事里,`render_card_ledger`(smoc 实际用的渲染函数)
  只做了第一件(date sort);merge/count/certify 三步不存在于 smoc 的渲染
  路径,它们是 filter/usability/compile 三臂的机制,与 smoc 无关。因此
  本批"机制关闭"控制臂在**代码事实**层面几乎不需要"关掉"merge/count/
  certify(它们本来就没开);(A)臂与 smoc 的可分离差异被迫收窄为:
  ① 全店多槽位 vs 本题槽位(噪声行的取舍),② 别无其它。这是与任务预设
  最大的偏离,已按认知纪律记录为"偏离与未证实项"(见 §7)。

## 2. 两条控制臂的操作化定义

两臂都：沿用 smoc 逐字不改的 `SMW_PROMPT`(F.1 协议提示词,来自
`scripts/repro_batch3.py`,不重新定义,直接 import 复用)、逐字沿用
`parse_answer`(`ANSWER:` 行解析)、同样的行版式
`[entry N] DATE | LABEL: "TEXT"`(与 smoc 默认视图的行文法一致:方括号
序号、日期、竖线、标签冒号、引号包住的正文)。

### (A) render-only — 卡片账目,槽位选中,机制关闭

- 数据源:`results/wt_cards_v45/{uid}.json` 的 `records`(与 smoc 同一
  张卡片店,零改动只读)。
- **owner/slot 选择**(逐字复用 `render_card_ledger` 里那段目前默认关闭
  的 `QVF_LEDGER_VIEW=slot` 分支的 `hit()` 子串判定逻辑,新增
  `entity=="user"` 的 owner 闸 —— smoc 默认不做 owner 闸,这里加上是
  因为任务原文明确写"owner/slot selection",且 owner 闸只会剔除罕见的
  第三方记录(实测 8288 条卡片里仅 66 条 entity≠user,占 0.8%),不影响
  可比性):
  - Tier 1(chain-crosswalk):用语料自带的 `entry["chain"]`(该 uid 目标
    槽位的黄金链,含 `date`/`value`)去卡片店里找 `(stated_date==date and
    value 双向子串命中)` 的记录,取这些记录自己的 `slot` 字段众数,作为
    该店卡片抽取器实际使用的槽位标签(**只用来定位标签词,不用链条的
    date/value 直接选行或拼进正文**——链条本身是语料生成时的答案元数据,
    直接拿来选行等于泄漏 oracle;这里只把它当"标签对照表"用,行内容
    仍然 100% 来自卡片店自己的记录)。
  - Tier 2(literal-slot):`entry["slot"]` 原串与卡片 `slot` 字段互为子串
    (与 `render_card_ledger` 现有 `hit()` 逐字同逻辑)。
  - Tier 3(alias-kw):`entry["slot"]` 切词 + 与
    `scripts/complex_query_arm.py::SLOT_ALIASES` 做前缀/包含匹配展开的
    关键词集,对卡片 `slot` 字段做包含判定。
  - 三层按顺序取命中行数更多者;若三层结束仍 `<2` 行(实测 144 店里
    5 店,约 3.5%),回退到该店卡片店全部记录(与 `render_card_ledger`
    自己的 slot-view 兜底行为同构:命中不足两行时退回整本账目,并打印
    提示)——这 5 店会在跑批日志与记分报告里点名列出。
  - 实测(144 店离线预演):行数中位数 3、均值 3.6、最大 8;Tier 分布
    chain-crosswalk 76 / literal-slot 59 / alias-kw 5 / 兜底整本 4。
- 渲染:命中记录按 `stated_date`(同 smoc 的日期兜底口径)升序,逐行
  `[entry N] DATE | {r['slot']}: {r['value']} — "{r['source_span'][:120]}"`
  —— 与 smoc 默认视图的行文法逐字节相同,只是行的**集合**收窄到目标
  槽位。**不做**近邻同值合并、不做转变计数、不追加任何计算摘要行(哪怕
  三层选择兜底触发,也只回退"整本账目"这一种形态,不新增计算内容)。

### (B) render-raw — 原始锚定轮次,无卡片抽取

- 数据源:`data/wikistate_full_ALL_v24.json` 该 uid 的 `sessions`(原始
  会话,不读卡片店,不需要 `--cards-dir`)。
- **轮次角色解析(实现细节,必须写明——原始数据里 turn 字段的序列化不
  统一,直接 `eval()` 会静默丢真实 user 轮次)**:先 `ast.literal_eval`;
  失败则退化为正则 `^\{'role':\s*'(user|assistant)',\s*'content':\s*(['"])`
  前缀匹配(处理长回复被截断在 400 字符导致字典字面量不闭合的情况);
  两者都不匹配时(该 uid 的部分会话整轮就是裸字符串,没有 role 包装,
  实测均为第一人称用户自述)记为 `role='user'`。此口径下 144 店里
  `user` 轮 15,114 条、`assistant` 轮 8,640 条、`other` 0 条 —— 若改用
  `render_transcript` 里那句 `eval(txt, {"__builtins__": {}})`(遇非法
  语法直接 `except: pass` 保留原文、不判角色),会把这类裸字符串轮次
  完全排除在"user 轮"之外,实测导致近三分之一的店命中 <2 行,故本臂
  弃用该写法,改用上述更稳健的解析器。
- **槽位关键词匹配**(纯字符串子串检索,零 LLM、零 write-time 抽取):
  关键词集 = `entry["slot"]` 的下划线转空格全串 + 切词(长度≥4 的词)
  + `SLOT_ALIASES` 前缀/包含展开的别名词 **+ `entry["chain"]` 里每个
  `value` 的下位串与长度≥4 的切词**(值本身,不是抽象槽名,才是对话
  原文里真实出现的词——实测仅用槽名匹配时中位命中数为 1、47/144 店
  <2 行;加入 value 词后中位命中数升到 7,144 店全部 ≥3 行,零兜底)。
  **这一步只用链条挑"要搜索的词表",不读链条的日期/取值来直接选行或
  拼正文** —— 被选中的行仍然是原始 user 轮次的**完整原文**,不是链条
  里的 `state_span`(那是语料生成时的理想化摘录,不是聊天原文)。
- 命中 user 轮:关键词(不分大小写)作为子串出现在该轮 `content` 里即
  命中,不限次数、不去重、不合并相邻同值、不排除对话轮内的噪声内容。
- 渲染:命中轮按其所属**会话日期**(`session["date"]`,轮次本身无独立
  日期,与 `render_transcript` 的日期可得性口径对齐)升序,逐行
  `[entry N] DATE | {entry['slot']}: "{content[:400] 换行替换为空格}"`。
  400 字符截断口径与该语料本身对 assistant 长回复的截断量级对齐(纯
  显示层截断,不是抽取)。
- 实测(144 店离线预演):命中行数中位数 7、均值 8.2、最小 3、最大 27,
  零店需要兜底。

## 3. 数据与读者配置

- 语料:`data/wikistate_full_ALL_v24.json`(144 库,与 33-A 同一份,只读)。
- 题源:`data/wsc_s5_v25.jsonl`(560 题,4 类:change_count/count_before/
  first_vs_last/longest_tenure)。经核验,其 560 个 `qid` 是
  `data/wsc_s5_v2.jsonl`(33-A 用的 576 题源)的**真子集**(576 题里
  longest_tenure 部分 16 题在 v25 里被清理掉),故本批产物可与
  `results/b33A_{smoc_v45,smw,smwplain,direct}.jsonl` 在这 560 个
  `question_id` 上直接配对比较(比较时把 33-A 那四个文件过滤到这 560
  个 id 上,不新增、不外推)。
- 卡片店(仅 (A) 需要):`results/wt_cards_v45`(与 33-A smoc 同店,只读)。
- 读者:`claude-haiku-4-5`,`temperature=0.0`,`max_tokens=800`
  (与 33-A 的 `repro_batch3_b33.py` 默认配置逐字同值)。
- 判官:`qvf.judge.ClaudeJudge`(`config.DEFAULT_JUDGE_MODEL`,与 33-A 同
  一判官类、同一提示词,未改动)。
- 并发:4 workers(`--workers 4`,追加写 + 已完成 question_id 跳过续跑)。
- 读者侧花费闸:$4(判官侧不计入,遵循环境准则里"Reader spend cap $4
  (judge separate)")。离线预演行数远小于 smoc 全店账目(中位 3~7 行 vs
  smoc 全店 ~50 行),预计单题成本远低于 33-A smoc 的 $0.00427/q,总花费
  预估在 $1~2 量级,留足余量。

## 4. 产物

- `results/b44_renderonly.jsonl`(臂 A,mode=`renderonly:anthropic:claude-haiku-4-5`)
- `results/b44_renderraw.jsonl`(臂 B,mode=`renderraw:anthropic:claude-haiku-4-5`)
- 两文件行 schema 对齐 `lb_reader_arm_b36b.py` 的超集 schema(question_id/
  uid/question_type/question/gold_answer/answer/protocol_deviation/
  usage_input_tokens/usage_output_tokens/judge_correct/judge_reason/
  latency_s/reader_model/reader_max_tokens/stop_reason/reader_error/
  judge_input_tokens/judge_output_tokens/cards_dir),新增
  `rendered_rows`(该题账目渲染出的行数)与 `rendered_chars`(账目文本
  字符数)用于"逐臂平均渲染行数与 token 数"的记录要求。
- `results/b44_score_out.txt`、`results/opt_batch44_verdict.md`。

## 5. 假设与阈值(运行前预注册,不得事后调整)

- **H1**(机制份额存在):`acc(smoc) - acc(render-only) >= +5pp`(整体
  560 题配对)。**但见 §1 结论**:代码事实上 render_card_ledger 没有
  merge/certify/count 步骤,smoc 与 render-only 的唯一系统性差异是
  "全店多槽位 vs 本题槽位"的证据取舍范围,不是通常意义的"编译机制"。
  H1 的检验仍按字面阈值跑,但判词会同时报告这一归因限定,不把
  smoc-render-only 的差值直接等同于论文语境下的"compile 机制"。
- **H2**(版式份额存在):`acc(render-only) >= acc(full-text-plain) + 10pp`,
  其中 full-text-plain 取既有 `results/b33A_smwplain.jsonl`(原文全文 +
  `PLAIN_PROMPT`,无协议提示词,同一读者/判官/语料)按 560 题源过滤后
  的成绩,不重跑。
- **H3**(机制份额集中在 change_count/count_before):按题型拆分
  smoc−render-only 的差值,若 change_count/count_before 两类的差值均值
  明显高于 first_vs_last/longest_tenure 两类均值(经验判据:高出
  ≥5pp 且方向一致),记为 H3 成立;否则否定。**鉴于 §1 结论,H3 若成立
  也不能解释为"计数机制"造成——因为 render-only 与 smoc 都不含计数
  步骤——只能解释为"更完整的多槽位证据在计数类题型上更有用"这一更
  弱的机制假说,判词会明确改写这一归因。**

## 6. 统计方法(与 33-A 同源,逐字复用)

- 配对 McNemar(精确符号检验,`scripts/b33A_score.py::sign_p`);
- 144 链簇自助 CI(N=10000, seed=20260902,与 `compare()` 同函数/同参数);
- 比较对:smoc vs render-only、render-only vs smwplain、render-only vs
  smw、render-raw vs smwplain(任务指定的四对),外加 smoc vs render-raw、
  render-only vs render-raw、smoc vs smwplain(拆分表需要的辅助对);
- 拆分表:`layout share = acc(render-only) - acc(smwplain)`,
  `mechanism share = acc(smoc) - acc(render-only)`,
  `total = acc(smoc) - acc(smwplain) = layout + mechanism`,整体与逐题型
  各报一行。

## 7. 已知偏离与未证实项(先于跑批列出)

1. 任务预设"compile 做 date sort/merge/count/certify"与代码实测不符
   (merge/count/certify 不存在于 smoc 渲染路径)——已在 §1 详述,不是
   本批引入的偏离,是对既有预设的纠正,跑批与判词都会照此如实报告。
2. (A) 臂加了 smoc 默认没有的 `entity=="user"` owner 闸——为满足任务
   原文"owner/slot selection"的字面要求,影响面很小(0.8% 记录)。
3. (A) 臂槽位选择用了三层回退(含用语料 `chain` 做"标签对照表"这一步),
   非 `render_card_ledger` 现成代码路径的逐字复用,是本批新写的选择
   逻辑——已尽量贴合 `render_card_ledger` 现有 `hit()` 判定式与其
   "命中不足两行退整本"的既有兜底惯例,但仍是新代码,需要之后复核。
4. (B) 臂关键词表混入了 `entry["chain"]` 的取值词——只用来构造搜索词表,
   不作为行内容或行选择的直接依据(行内容始终是原始 user 轮次原文)——
   但这类似于"知道答案关键词去搜索"的关键词基线做法,并非纯粹独立于
   语料生成过程的检索,需要在判词里说明这一让步,不宣称 render-raw 是
   "零先验知识"的检索基线。
5. (B) 臂的角色解析器(正则前缀匹配 + 裸字符串默认判 user)是本批新写
   的鲁棒化方案,针对的是语料里 turn 序列化不统一/超长回复截断导致
   `eval()` 静默失败的既有数据质量问题——这是本次代码走查中新发现的
   语料缺陷,与批 44 任务本身无关,但会影响任何依赖角色解析的读取臂,
   值得记录以供后续批次参考。
6. H3 的经验判据("高出 ≥5pp 且方向一致")是本批临时定的阈值,非既有
   项目惯例延续,判词会原样报告数值,不做进一步显著性宣称。
