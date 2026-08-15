# P1:算子族最小完备基 —— 命题槽 2 结算(2026-08-16)

对应 `study_logs/QVF_methods_formalization_20260814.md` §7.2 命题槽 2(此前标记"待批")。
工作目录 `D:\ZZL_cluade`。判官 opus(`claude-opus-5`),编译/读者 haiku(`claude-haiku-4-5`)。

## 零、两条命题必须分开裁决

本轮跑的是两件不同的事,预注册判据只约束第二件,但两件事的结论方向相反,必须分开写,不能互相借用对方的措辞:

1. **完备性命题**(本文档主题,构造性、零 LLM、护栏口径):是否存在一个 ≈6 元原语集,使现行 11 算子(`scripts/complex_query_arm.py::OPS`)全部可表示为该原语集上深度 ≤3 的表达式,且宏执行与平面执行逐字节等价。——**猜想被证实**。
2. **泛化准确率命题**(`结果汇报`referenced 的对决结果,经验性、要过 LLM 编译/读者/判官):代数臂在未见组合 split 上的问答准确率是否 ≥65% 且高于平面臂 ≥20pp。——**猜想被否定**(代数臂 49.3% vs 平面臂 52.2%,-3.0pp,详见二.3)。

命题 1 是关于"这个代数能不能表示"的存在性/构造性陈述,命题 2 是关于"LLM 编译器 + haiku 读者在这个代数上问答准不准"的经验陈述。11 算子宏形式与平面执行**逐字节等价**这件事本身独立于任何一次 LLM 调用是否编译对、读者答没答对——这正是护栏与主判据分离预注册的原因。本文档只对命题 1 负责;命题 2 的完整负结果见 `results/wsc_s8_report_20260816.md`,本文档三处引用其数字但不重复其判词。

## 一、原语集 P + 类型签名(构造性定义)

代码:`scripts/qvf_algebra.py`(模块头 §7.2 已有形式化注释,本节为独立成文版本,与代码逐字对照过)。

**类型域**:`Chain`(某属性/标签的有序去重日期化状态链)、`Rec`(链上一条记录)、`Loc`(链上一个定位,含命中日期与序号)、`Value`(聚合值)、`Date`(字面日期或另一表达式导出的日期)。

| 原语 | 类型签名 | 语义 | 求值代码 |
|---|---|---|---|
| `SELECT(slot, hygiene)` | `() → Chain` | 键控选池(`_select_pool`)→(`hygiene=true` 时经算子条件化卫生过滤 `_hygiene_pool`)→ 排序去重合并(`_chain`) | `qvf_algebra.eval_expr`,`p=="SELECT"` 分支 |
| `TAGSET(tag)` | `() → Chain` | 跨键标签命中集,按日期排序 | 同上,`p=="TAGSET"` 分支 |
| `WINDOW(of, bounds)` | `Chain → Chain` | `of` 链上严格落在(可选)下界与(可选)上界之间的子链;每侧界可为字面日期,或另一(可能不同的)属性历史上的值锚/序数锚给出的日期 | `_resolve_bound` + `p=="WINDOW"` 分支 |
| `PICK(of, index\|value)` | `Chain → Rec` | 序数取元(1-based;-1=链尾)或值锚(`_norm` 双向包含匹配;`exclude_last=true` 时只搜 `chain[:-1]`,即 `premise_check` 的"过时值"语义) | `p=="PICK"` 分支 |
| `ASOF(of, date\|at)` | `Chain × Date → Loc` | 右开区间点查:`gi` = 最大 `i` 使 `t_i ≤ d`;`at` 为另一 `Rec` 子表达式时取其记录日期为 `d`(时序 join —— `JOIN_T` 由此被 `ASOF` 吸收,不独立设原语) | `p=="ASOF"` 分支 |
| `AGG(of, fn)` | `Chain → Value` | `fn ∈ {count_changes, distinct_ordered, argmax_dur, by_year, count_elements}` | `p=="AGG"` 分支 |

`|P| = 6`。AST 显式嵌套三层(`LeafExpr`/`MidExpr`/`TopExpr`,pydantic 强类型),结构上深度 ≤3;`check_expr` 是独立于求值器的类型检查器,非良构树在编译后立即被拒绝(见五.2 编译良构率)。

## 二、11 算子宏定义表(构造性完备性证明)

记 `C = SELECT(slot)`,`Cʰ = SELECT(slot, hygiene=true)`,`G = TAGSET(tag)`。下表逐条给出旧 11 算子(`§4 算子指称语义` 表,`QVF_methods_formalization_20260814.md` §4)到 P-表达式的映射,深度 = 表达式树高:

| 旧算子(§4 指称语义) | 宏定义(P-表达式) | 深度 | 代码(`MACROS` 字典键) |
|---|---|---|---|
| `current` | `PICK(C, index=-1)` | 2 | `current` |
| `point_in_time(d)` | `ASOF(C, date=d)` | 2 | `point_in_time` |
| `trajectory` | `C` | 1 | `trajectory` |
| `premise_check(v̂)` | `⟨PICK(C, index=-1), PICK(C, value=v̂, exclude_last=true)⟩` | 2 | `premise_check` |
| `count_changes` | `AGG(Cʰ, fn=count_changes)` | 2 | `count_changes` |
| `count_before(d)` | `AGG(WINDOW(Cʰ, before=d), fn=distinct_ordered)` | 3 | `count_before` |
| `first_last` | `PICK(Cʰ, index=1)` ⊕ 链尾直读 | 2 | `first_last` |
| `longest` | `AGG(Cʰ, fn=argmax_dur)` | 2 | `longest` |
| `tag_filter(g₀)` | `G` | 1 | `tag_filter` |
| `tag_trend(g₀)` | `AGG(G, fn=by_year)` | 2 | `tag_trend` |
| `join_at_change(s₂; a)` | `ASOF(SELECT(s₂), at=PICK(SELECT(slot), index\|value=a))` | 3 | `join_at_change`(`_join_expr`) |

（`⟨·,·⟩` 二元组宏不是双树:第二分量沿共享子树 `of` 的 trace 读出,不重算——见 `qvf_algebra.base_chain`;渲染函数逐条复用平面分支的字符串模板,`_render_chain_op`/`_render_tag`/`_render_join`。）

**这是构造性证明,不是存在性论证**:11 行宏定义 + `MACROS` 字典 + 求值器 = 一份可执行的完备性证据,不依赖任何 LLM 调用。命题成立当且仅当对每个旧算子,宏渲染出的证据包(`ev` 行 + `derived` 行 + `reader_content` 全文)与平面分支逐字节相同——这正是护栏的定义。

**护栏结果(预注册判据,任一不等价即弃)**:

| 切片 | n | 逐字节等价(报告口径) | 逐字节等价(本轮独立复跑,零信任) |
|---|---|---|---|
| S5 全量 | 314 | 314/314 | **314/314**(`results/wsc_s5_test_v42.jsonl`,`QVF_CARDS_KEYED=results/wt_cards_v42` 现场重跑) |
| S5 synthetic(+`current`/`point_in_time`/`trajectory`/`premise_check`) | 316 | 316/316 | 未独立复跑(见四.2 范围缺口) |
| S6(两份) | 15+18=33 | 33/33 | **15/15 + 18/18 = 33/33**(`results/wsc_s6_arm.jsonl` + `wsc_s6_big_arm.jsonl` 现场重跑,分别核对) |
| S7 切片 | 50 | 50/50 | 未独立复跑(见四.2 范围缺口) |

347/347(S5+S6)现场零信任复跑逐字节相同,与报告数字完全一致——**护栏未破一次,命题 1(完备性)成立**。

## 三、S8 实测表(经验命题 2,已否定;转引不重判)

| 臂 | n(未见组合 split) | correct | 准确率 | vs 平面臂 | tok_in/题 | tok_out/题 | 延迟 s/题 |
|---|---|---|---|---|---|---|---|
| 代数臂(QVF_ALGEBRA=1,宏+直接表达式路径) | 67 | 33 | 49.3% | **-3.0pp** | 1777.6 | 170.3 | 6.76 |
| 平面臂(11 算子,被迫落最近算子) | 67 | 35 | 52.2% | — | 2224.0 | 131.0 | 6.23 |
| 直读臂(haiku 稠密直读,对照) | 67 | 47 | 70.1% | — | 798.3 | 90.2 | 11.95 |

主判据(≥65% 且高于平面臂 ≥20pp)两条均未达成——**猜想被否定**。编译良构率 67/67=100%(≥90% 门槛达成)。根因诊断(非猜测,逐题验证,见 `wsc_s8_report_20260816.md` §三):`WINDOW_2ANCHOR∘COUNT` 组合上编译与执行均正确,但通用渲染器 `_render_direct` 的 `Value` 分支未把两个锚点记录放入证据包,读者看不到"确实发生过"的直接证据而拒答——这是**证据包设计缺陷,不是代数完备性缺陷**:命题 1 关心"能否表示",命题 2 的失败原因是"表示出来之后,通用渲染器给读者的证据不够",两者不是同一件事,不能用命题 2 的失败反推命题 1 不成立,也不能用命题 1 的成立反驳命题 2 的否定。

## 四、"算子族不膨胀"论证:新题型 = 新组合,原语零膨胀

**论证**:S8 的 4 个未见组合(`WINDOW∘AGG`、`WINDOW_2ANCHOR∘COUNT`、`NTH∘JOIN_T`、`JOIN_T∘WINDOW`)在旧 11 算子体系下**没有一个是原生算子**——它们是四种新题型,需要新的算子才能表达。但在 P-表达式下,四个组合全部由**同一个原语集 P**(`|P|=6`)的不同树形拼出,零第 7 原语:

- `WINDOW∘AGG` = `AGG(WINDOW(Cʰ, before=d), fn=argmax_dur)`(深度 3;`longest` 的"开窗版")
- `WINDOW_2ANCHOR∘COUNT` = `AGG(WINDOW(Cʰ, before_slot/before_index, after_slot/after_index), fn=count_elements)`(深度 3;`count_before` 的"双锚版")
- `NTH∘JOIN_T` = `join_at_change` 本身(11 算子原生,序数锚形态)——**结构可表达**,S8 未见 split 33.3%/40.0%(代数/平面)的低准确率是编译/读者层面的经验问题,不是表达力问题(见 `scripts/wsc_s8_inexpressible.py` 的机械判定与 §五.1 的可表达率结论)
- `JOIN_T∘WINDOW`:S8 唯一记为**代数臂结构上也不可表达**的组合(n=1,不构成统计证据)——需要"逐段计数+跨段比较"的复合操作,现有 P 的任何单一原语在任何参数下都无法一次性表达;若要收纳,需在 P 之外再加一层"对 WINDOW 切出的每一段分别求值再比较"的高阶组合子(见八、未尽事项)

**推论核实**(与命题槽 2 的推论逐字对照):"新题型 = 新组合,算子族不随题型膨胀"这句话在本轮实测中**部分成立**:4 个未见组合里 3 个(`WINDOW∘AGG`/`WINDOW_2ANCHOR∘COUNT`/`NTH∘JOIN_T`,占未见 split 66/67=98.5%)靠现有 6 原语的新组合覆盖,没有新增第 7 个原语;1 个(`JOIN_T∘WINDOW`,占 1/67)确实表达不了,是该推论的一个真实反例,如实记录,不遮盖。

**"零代码"这一措辞的精确边界(诚实澄清,不夸大)**:上面"零第 7 原语"是精确的——`|P|` 全程等于 6,没有增加过一个新原语类别。但"零代码"不精确:dev 轮 2 为了让 `WINDOW` 表达值锚/序数锚双侧界,给 `WINDOW` 的**参数面**(不是类型签名)加了 `after`/`before_slot`/`before_value`/`before_index`/`after_slot`/`after_value`/`after_index` 七个可选字段,给 `AGG.fn` 加了 `count_elements` 一个新枚举值(见 `qvf_algebra.py` 第 66-72 行注释,dev round 2 记录)。这是**同一个原语内部的参数扩展**,不是新设一个原语(`WINDOW` 求值后仍是 `Chain → Chain`,`AGG` 仍是 `Chain → Value`),但确实是新增了约 60 行代码(`_resolve_bound`)。精确表述应为:**类型签名意义上的原语族零膨胀(6 恒等于 6),但原语的参数面在遇到未见组合时经历过一次扩展**——这与论文里通常讲的"算子族不因题型增长而线性膨胀"是同一件事的两种精确度:前者是强命题(已验证),后者若被读成"连一行代码都不用改"则是过度陈述,需要在论文行文里避免。

## 五、与去耦合原则 3 的联动:原语文档取代模板 few-shot

`study_logs/QVF_decoupling_roadmap_20260815.md` 原则 3 的诊断:`COMPILE_PROMPT` 里六个与出题模板同构的 few-shot 示例是 train-on-test 的根源;该文件第 36 行明确记录了与 P1 的联动关系:"原语文档化(约 6 个原语的形式语义)天然取代 few-shot——组合式编译提示词只含原语定义,连示例都不需要,原则 3 自动满足"。

本轮 `ALGEBRA_COMPILE_PROMPT`(`scripts/qvf_algebra.py` 第 660-736 行)的实际实现核实如下:

- 提示词主体 = 6 原语的**形式语义文档**(类型签名 + 每个原语的自然语言语义 + `WINDOW` 三种界描述方式的显式规则),风格对齐 `QVF_methods_formalization_20260814.md` §4;
- 保留 **2 个**组合示例(未做到"连示例都不需要"的最强版本)——这是预注册纪律④的显式要求("至多 2 个组合示例"),不是对原则 3 的违反,而是原则 3 的**受控partial实现**:纪律④同时要求"示例句式不得取自 gen 出题模板",经核对两个示例("Between when I switched to my third apartment...","What was my job title back when I owned my second phone?")均为新造句式,不出现在 `data/wsc_s8.meta.json` 的 `question_templates` 列表(`wc_cross_*`/`cd_*`/`wa_*`/`w2_*`/`nj_*`/`jw_1`)里,去耦合原则 3 的核心风险(示例与测试题面同构导致的表面模式记忆)未复现。

**联动的准确表述**:P1 完备基命题为去耦合原则 3 提供了一条**可行路径**(原语语义文档可以替代大部分 few-shot 的信息量),本轮是这条路径的一次受控验证(2 个示例、非模板句式),不是路径的完全实现(0 个示例)。是否能进一步压到 0 个示例、编译良构率与准确率是否随之下降,是后续工作,未在本轮验证范围内。

## 六、对抗自查

### 6.1 S8 金答案抽 21 题手推(超额完成"抽 20 题"要求)

按 6 种组合类型分层抽样(`random.seed(20260816)`),覆盖全部 6 个组合、seen/unseen 两个 split。核查方法:不运行 `scripts/gen_wsc_s8.py`(生成器)或 `scripts/verify_wsc_s8.py`(项目自带的独立复核器)的代码路径,直接读取 `data/wikistate_full_*.json` 原始链数据,用纸笔/计算器口径手工重算 gold,与 `data/wsc_s8.jsonl` 落盘值比对:

- **9 题从原始 JSON 链完全独立重推**(拉取 `wikiM003-Q106386024`/`wikiM019-Q13205835`/`wikiM004-Q106606516` 三个跨属性世界的完整原始 `chain`/`chain2`):`NTH∘JOIN_T` ×3、`JOIN_T∘WINDOW` ×1(逐区间手数转移次数,`counts=[0,0,2,0,0]` 与落盘 `params` 逐位吻合)、`WINDOW_2ANCHOR∘COUNT` ×3(含跨链与同链两种 `kind`)、`WINDOW∘COUNT` ×2 —— **21 题中 9 题、全部 unseen split、结果 9/9 与落盘 gold 一致**,零不吻合。
- **4 题闰年精确日数手算**(`NTH∘CMP_DUR`,seen split):逐题手数闰年天数(如 `[1991-01-01,2003-01-01)` = 12×365 + 3 个闰日 = 4383 天,`[2003-01-01,2006-01-01)` = 3×365 + 1 个闰日 = 1096 天),4/4 与落盘 `basis` 字段的天数、与 gold 的胜负判断均一致。
- **4 题 `WINDOW∘AGG` 读法一致性核查**(unseen split):核对 reading A(含未闭合末段裁剪)与 reading B(仅闭区间)两种读法是否指向同一赢家,4/4 一致,与 gold 吻合。
- **4 题 `WINDOW∘COUNT`(seen split)基于 `basis` 字段的内部一致性核查**(未回源始文件,仅核查 `basis` 陈述的区间与落盘 `gold` 是否算术自洽):4/4 自洽。

**21/21 手推结果与落盘 gold 一致,零不吻合**(9 题为最强程度的从零复核,回到原始 JSON;12 题为算术精确复核或自洽性复核)。另行独立重跑 `scripts/verify_wsc_s8.py`(逐组合类型独立重写判定逻辑,不导入 `gen_wsc_s8.py`):`PYTHONIOENCODING=utf-8 python scripts/verify_wsc_s8.py` → **121/121 独立复核一致**,与报告数字相符。三层复核(手推 21 题、项目自带独立复核器 121 题、本轮现场重跑而非只信任历史输出)均通过,S8 金答案纯代码从链导出、零人工裁量的纪律⑤成立。

### 6.2 宏等价对拍复核

不满足于只读 `results/wsc_s8_algebra_parity_r2_20260815.jsonl` 里的历史记录,现场重跑 `scripts/algebra_parity.py`:

```
QVF_CARDS_KEYED=results/wt_cards_v42 python scripts/algebra_parity.py \
  --rows results/wsc_s5_test_v42.jsonl --data <P108/P54/P551> --name reaudit_s5
# → [reaudit_s5] n=314 byte_equal=314 diff=0

QVF_CARDS_KEYED=results/wt_cards_v42 python scripts/algebra_parity.py \
  --rows results/wsc_s6_arm.jsonl --data <5 源文件> --name reaudit_s6a
# → [reaudit_s6a] n=15 byte_equal=15 diff=0

QVF_CARDS_KEYED=results/wt_cards_v42 python scripts/algebra_parity.py \
  --rows results/wsc_s6_big_arm.jsonl --data <5 源文件> --name reaudit_s6big
# → [reaudit_s6big] n=18 byte_equal=18 diff=0
```

S5(314)+S6(15+18=33)= **347/347 现场零信任复跑逐字节相同**,与报告数字完全一致。**范围缺口(如实记录,不回避)**:S5 synthetic(316)与 S7 切片(50)本轮未找到对应的独立可重跑输入文件(S7 现存的 `wsc_s7_*` 文件行数为 20/220/220 三种,均非报告所称的"50"切片,推断该 50 题切片文件在后续跑批中被更大规模的 220 题文件覆盖或改名),故这两项本轮**仅转引历史记录、未做现场复核**——这是本次审计的一个已知缺口,不构成对护栏结论的否定(S5 全量与 S6 已现场复核 100% 通过,S7/synthetic 缺口应在下一轮审计中补上)。

### 6.3 判官盲性

代码级核查(非行为推断):

- 三臂共用同一 `qvf.judge.ClaudeJudge.judge()` 方法,签名为 `judge(question, gold_answer, response, question_type=None, is_abstention=False)`;`_judge_user_prompt` 拼出的用户提示词只含 `QUESTION`/`QUESTION TYPE`/`GOLD ANSWER`/`MODEL RESPONSE` 四段,**没有任何字段传入臂身份、`op`/`expr` 计划、`mode` 标签或 `QVF_ALGEBRA` 旗标状态**。
- 三处调用点逐一核对,签名与参数完全一致:代数臂/平面臂共用 `scripts/complex_query_arm.py:826`——`judge.judge(q["question"], str(gold), answer, q.get("qtype"))`;直读臂 `scripts/wsc_direct_arm.py:222`——同签名。三臂传入判官的只有问题原文、gold、reader(haiku)生成的最终自然语言答案文本、题型标签,答案文本本身不含计划结构或算子名(读者只见证据包与问题,证据包渲染模板逐字节复用平面分支,见二节)。
- 抽样判官返回的 `judge_reason` 文本(如"The model declined to answer rather than providing the gold answer"、"identifies Mölndals Cykelklubb, matching the gold answer")均只针对答案内容措辞,未出现任何指代"代数"/"平面"/"算子"/"expr"/"plan" 的语言——**佐证盲性在实际返回里没有被绕过**,但这是弱证据(判官不知道也可能恰好不提及),真正的保证来自上面的代码级构造(判官从未拿到过可用于分辨臂身份的输入)。

**结论:判官盲性在设计与调用点两个层面均成立**,不是靠信任行为观察,而是靠输入通道里根本不存在可泄露臂身份的字段。

### 6.4 成本账

`results/wsc_s8_algebra_test.jsonl`/`wsc_s8_flat_test.jsonl`/`wsc_s8_direct_test.jsonl`(一次性测,3×67 行)+ `wsc_s8_algebra_dev_r1/r2/r2b/r3/r4.jsonl`(dev 5 份,共 3 轮迭代 + 1 次中途 bug 复现 + 1 次小样本冒烟)逐行 `usage_input_tokens`/`usage_output_tokens` 现场求和(reader+compiler 合计,不含判官):

| 阶段 | n(行) | tok_in | tok_out |
|---|---|---|---|
| dev r1(轮1基线) | 54 | 176,974 | 7,146 |
| dev r2(轮2中途,含 bug 复现) | 54 | 107,214 | 19,047 |
| dev r2b(bug 修复后小样本冒烟) | 5 | 7,161 | 717 |
| dev r3(轮2终版) | 54 | 84,330 | 8,891 |
| dev r4(轮3=锁定版) | 54 | 93,246 | 8,520 |
| 一次性测·代数臂 | 67 | 119,097 | 11,408 |
| 一次性测·平面臂 | 67 | 149,006 | 8,775 |
| 一次性测·直读臂 | 67 | 53,485 | 6,041 |
| **合计(haiku,reader+compiler)** | **422** | **790,513** | **70,545** |

haiku-4.5 按公开定价量级(输入约 $1/M、输出约 $5/M)估算:790,513/1e6×$1 + 70,545/1e6×$5 ≈ **$0.79 + $0.35 = $1.14**。

判官(opus,422 次调用,每次一个短 prompt + 结构化输出,系统提示词走 ephemeral cache)未在结果行里记录 token 用量(`judge.judge()` 返回值不含 usage 字段),本轮**未能从日志逐笔重建判官侧的精确 token 数**——这是成本审计的一个已知缺口。按每次调用输入约 300-500 token(问题+gold+答案文本,多数命中缓存)、输出约 60-100 token(结构化 verdict)的量级估算,opus 按公开定价量级(输入约 $15/M、输出约 $75/M)估算 422 次调用约 $2-6 区间(区间宽是因为没有实测 token 数,缓存命中率未知)。

**结论**:haiku 侧成本($1.14)有精确账目;opus 判官侧成本为量级估算($2-6),两者相加落在 $3-7 区间,**与预算 ≤$8、纪律⑥"达成"的判词方向一致,但本文档不能像 haiku 侧那样给出精确到分的数字**——如实标注为估算区间而非实测值,是本轮成本审计的诚实边界。建议后续版本的 `ClaudeJudge.judge()` 把 `api_response.usage` 一并落盘,消除这个缺口。

## 七、纪律核对(逐条,不复述报告已有的①②③⑤⑥,仅补充本文档新增核查)

- ④编译提示词=原语文档+≤2 示例、示例不取自 gen 模板:本文档五节逐字核对通过。
- 本文档新增的三项独立复核(6.1 手推 21 题、6.2 现场重跑护栏 347 题、6.3 代码级判官盲性核查)均通过,未发现与已发布报告(`results/wsc_s8_report_20260816.md`)、已发布摘要(`results/wsc_s8_summary_20260816.json`)不一致之处。

## 八、未尽事项(如实记录,不回避)

1. `JOIN_T∘WINDOW` 是命题 4 原语组合覆盖论证的一个真实反例(n=1,不构成统计证据,但结构上确实表达不了),若要收纳需要在 P 之外引入"分段求值+跨段比较"的高阶组合子——这会让 `|P|` 从 6 变成 7,与本文档"原语族零膨胀"的核心论证冲突,留作后续命题槽的候选,不在本轮里假装已解决。
2. WINDOW_2ANCHOR∘COUNT 的准确率崩溃(代数臂 4.3%)根因是通用渲染器 `_render_direct` 的证据完整性缺陷,不是完备性缺陷——但这个缺陷本身还没修,若下一轮要用代数臂的准确率数字做任何主张,必须先修这个渲染器再重测,不能拿本轮的 49.3% 当作代数路径准确率的稳定估计。
3. S5 synthetic(316)与 S7 切片(50)护栏结果本轮未现场复核,见 6.2。
4. 判官侧 token 用量未落盘,成本账精确度受限,见 6.4。

## 文件清单

- 完备基实现:`scripts/qvf_algebra.py`
- 护栏对拍脚本:`scripts/algebra_parity.py`;历史记录 `results/wsc_s8_algebra_parity_r2_20260815.jsonl`;本轮现场复核输出见对话记录(347/347)
- S8 数据与独立复核:`data/wsc_s8.jsonl`、`data/wsc_s8.meta.json`、`scripts/gen_wsc_s8.py`、`scripts/verify_wsc_s8.py`(本轮重跑 121/121)
- 平面表达力机械判定:`scripts/wsc_s8_inexpressible.py`
- 判官:`qvf/judge.py`;调用点 `scripts/complex_query_arm.py:826`、`scripts/wsc_direct_arm.py:222`
- 去耦合原则关联文档:`study_logs/QVF_decoupling_roadmap_20260815.md`(原则 3,第 36 行)
- 数学化底稿:`study_logs/QVF_methods_formalization_20260814.md`(§4 指称语义表,§7.2 命题槽 2)
- S8 主报告(经验命题 2 的完整负结果):`results/wsc_s8_report_20260816.md`、`results/wsc_s8_summary_20260816.json`
