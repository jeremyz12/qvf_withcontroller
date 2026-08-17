# T4:COMPILE_PROMPT few-shot → 规范文档去耦合(2026-08-16)

> 背景:耦合审计(study_logs/QVF_coupling_audit_20260815.md)判定全库杀伤力最大一项 ——
> `scripts/complex_query_arm.py:140-192` 的 `COMPILE_PROMPT` 六个 few-shot 与
> `scripts/gen_wikistate_complex.py` 出题模板逐字/同构,是"提示词空间的 train-on-test"。
> 去耦合路线图原则 3("few-shot→规范文档")对此的处置状态是**全库 57 项 benchmark_specific
> 高危项中唯一完全未处理的一条**。本文件执行 T4:量化同构度 → 改写为规范文档版(新旗标
> `QVF_COMPILE_SPEC`,默认 0)→ 在已有改写题集上一次性对照测 → 报告。

## 判决

**猜想被证实:规范文档版可在不显著损失编译质量的前提下替代 few-shot。** 在 1107 条盲写
改写题(与出题模板无关)上,规范文档版计划一致率 99.28%(1099/1107)、执行等价率 99.82%
(1105/1107),相对 few-shot 版的 100.00%/100.00% 分别低 **0.72pp / 0.18pp**,均远优于预注册判据
"不低于 few-shot 版 −2pp"。旗标关闭时,`COMPILE_PROMPT` 常量逐字节不变,`compile_plan()`
在同一批题上重跑,输出计划与 2026-08-15 冻结记录逐项相同。

---

## 一、同构度量化(step 1)

**方法**:word n-gram containment(沿用污染检测通用口径,词级 n-gram、大小写不敏感)。
`containment(A→B) = |ngrams_n(A) ∩ ngrams_n(B)| / |ngrams_n(A)|`。对每条 few-shot 问句 A,
用出题器模板(`gen_wikistate_complex.py` 的 f-string,逐行核对源码后手工同参数代入)生成对照
问句 B,计算正向(A 的 n-gram 被 B 覆盖多少)与反向(B 的 n-gram 被 A 覆盖多少,区分度更高
——反向低说明 A 只是 B 去掉装饰词后的核心句干,反向=1 说明二者完全同构)。脚本:
`scratchpad/ngram_containment.py`(n=4)。

| few-shot | 对应模板 | fwd(A→B) | rev(B→A) | 判定 |
|---|---|---|---|---|
| #1 count_changes/position | S5b (`gen_s5`) | 1.000 | 1.000 | **逐字同构** |
| #2 count_before/employer | S5c (`gen_s5`) | 1.000 | 1.000 | **逐字同构** |
| #3 tag_trend/饮食 | S7a (`gen_s7`,连括号 gloss) | 1.000 | 1.000 | **逐字同构** |
| #4 tag_filter/高糖 | S7b (`gen_s7`,连括号 gloss) | 1.000 | 1.000 | **逐字同构** |
| #5 join_at_change 值锚(CERN) | S6 显式题 (`gen_s6`) | 1.000 | 0.500 | 结构同构(缺 "(Today is..)"/"at that time" 装饰) |
| #6 join_at_change 序数锚(second employer) | S6 隐式序数孪生 (`gen_s6`) | 1.000 | 0.571 | 结构同构(同上) |

平均 fwd=1.000、平均 rev=0.845。六例无一例外与出题模板同构,与耦合审计定性("#1↔S5b、
#2↔S5c 逐字同构,#3/#4 连括号 gloss 都相同,#5/#6 短语同词")完全对应,量化结果确认该定性
判断成立且无夸大。**#1-4 是最危险的四例**(反向 containment 也是 1.000,即模板句面完全等于
few-shot 句面,零信息量之外的差异)。

---

## 二、规范文档版重写(step 2)

新增 `scripts/complex_query_arm.py`:
- 旗标 `QVF_COMPILE_SPEC`(默认 0,`_COMPILE_SPEC` 变量,新增于既有旗标块,紧邻
  `_TAG_LATTICE`)。
- 新常量 `COMPILE_PROMPT_SPEC`(JSON 输出契约、Field rules 与原版逐字一致;"Examples:"
  换成 11 算子的**指称语义表**——每个算子用 chain 记号 `⟨(v_1,t_1),...,(v_m,t_m)⟩` 与
  区间语义描述,内容对应 `study_logs/QVF_methods_formalization_20260814.md` §4 的定义,
  译为编译模型可读的英文规范而非逐句重抄该文件)。
- 保留 **2 个域外示例**(上限,严格执行"至多 2 个"):`园艺`(gardening,tag_filter)与
  `medication/dosage`(join_at_change 序数锚)。两者均确认不出现在 `SLOT_ALIASES`、
  `CLOSED_TAGS`、`SUB_TAGS`、或任何出题模板字符串中(已用 grep 核实零命中)。
- `compile_plan()` 内部新增一行 `_prompt = COMPILE_PROMPT_SPEC if _COMPILE_SPEC else
  COMPILE_PROMPT`,取代原来硬编码的 `COMPILE_PROMPT`;旗标关时 `_prompt is COMPILE_PROMPT`
  ,该函数其余逻辑逐字节不变。
- 与 `QVF_ALGEBRA` 互不干扰:算子表达式编译器有独立的 `ALGEBRA_COMPILE_PROMPT`,不受
  本旗标影响(两旗标同开时 `QVF_ALGEBRA` 分支在模块加载顺序上后定义,整体覆盖
  `compile_plan`,`QVF_COMPILE_SPEC` 对平面编译器的改写不生效——符合预期,T4 范围仅限
  平面编译器)。

`git diff --stat scripts/complex_query_arm.py`:89 insertions / 2 deletions;2 处删除分别是
(a) `compile_plan` 文档字符串补充说明(纯注释)、(b) `"text": COMPILE_PROMPT` →
`"text": _prompt` 这一行本身。无任何其他既有行被修改。

---

## 三、一次性对照测(step 3)

**测试集**:`results/paraphrase_set_20260815.jsonl`(1107 条 = 369 题 × 3 改写,与出题模板
无关的盲写改写集,08-15 已交付,本次复用不重新生成)。**评测脚本**:
`scripts/eval_paraphrase.py`(冻结,未改;通过设置环境变量 `QVF_COMPILE_SPEC=1` 在模块导入
前生效,脚本本身零改动)。

| 版本 | 计划一致率 | 执行等价率 | tokens_in | tokens_out | 墙钟 | 成本上界* |
|---|---|---|---|---|---|---|
| few-shot(冻结基线,复用 08-15 记录) | 1107/1107 = **100.00%** | 1107/1107 = **100.00%** | 2,100,668 | 35,573 | 1190.6s | $2.28 |
| 规范文档版(`QVF_COMPILE_SPEC=1`,本次新跑) | 1099/1107 = **99.28%** | 1105/1107 = **99.82%** | 2,262,290 | 28,745 | 1489.9s | $2.41 |
| **膨胀量(few-shot − 规范文档版)** | **+0.72pp** | **+0.18pp** | — | — | — | — |

\* 成本上界按 haiku-4-5 公开单价 $1/$5 每百万 token(input/output)折算,未拆分 ephemeral
cache 读/写(与 08-15 口径一致),缓存命中时实际显著更低。

**判据:规范文档版不低于 few-shot 版 −2pp**(即膨胀量 ≤ 2pp 视为通过)。**0.72pp / 0.18pp
均远低于 2pp 门槛,判据通过。**

### 失败案例分析(8 例 plan_agree=False,2 例 exec_equal=False)

- **6/8 集中在 `s7_category`(tag_trend↔tag_filter 混淆)**:出现在两个标签(工作学习、
  宠物)的多条改写句上,规范文档版把 `tag_trend` 误判为 `tag_filter`。根因可定位:两个算子
  的语义表描述本身相近("每条打了该标签的记录" vs "按年分桶的同一批记录"),而**规范文档版
  仅保留的 2 个域外示例里恰好只演示了 `tag_filter`(园艺),没有演示 `tag_trend`**——few-shot
  版本因为原本就同时含 #3(tag_trend/饮食)与 #4(tag_filter/高糖)两个例子,这对算子从未
  混淆过。这是**规范文档对"易混淆算子对"覆盖不足**的直接证据,而非语义表本身有错误。
- **2/8 集中在 `s6_cross_slot`(join_at_change 的 slot 命名/字段遗漏)**:一例把 `employer`
  命名为同义词 `organization`(不在 `SLOT_ALIASES` 词表内,`plans_agree` 的槽位归一失配,
  执行池按槽位类分组时同样落空,exec_equal 随之为 False);一例遗漏 `presupposed` 字段
  (锚值本应回填但留空)。两例均属编译模型对指称语义表述的**边界情形处理**不如例句直接展示
  来得稳,但仅 2/1107 = 0.18%,不改变整体判据结论。

**如实报告**:规范文档版并非在所有维度上不劣于 few-shot 版——它在两个具体失败模式
(相近算子混淆、罕见槽位命名)上确有可测的小幅回退,只是幅度(0.72pp/0.18pp)远低于预注册
的 2pp 容忍线,不构成对"形式语义可替代示例"这一处置方向的否定。若后续要进一步收紧,直接
可做的补丁是给规范文档版补一个 `tag_trend` 域外示例(如"园艺"改问"是否随时间变化过"),
预期可消掉 6/8 的失败——本轮按纪律未回头改動再重测,如实留档。

---

## 四、旗标关闭时逐字节不变(step 4,对拍验证)

- **常量级**:提取 `COMPILE_PROMPT` 字符串(assignment 起点到闭合三引号),与
  `git show HEAD:scripts/complex_query_arm.py` 中的原文本逐字节比较 —— **完全相同**
  (3142 字符,`==` 为 True)。
- **代码路径级**:`git diff` 显示新增代码全部是新增行(新旗标注释块、`COMPILE_PROMPT_SPEC`
  常量、`compile_plan` 内的 `_prompt` 选择行);唯一改动的既有行是把 `"text":
  COMPILE_PROMPT` 换成 `"text": _prompt`,旗标关时二者指向同一字符串对象。
- **运行级**(实测,非仅推理):旗标关闭状态下用 `scripts/eval_paraphrase.py --model haiku
  --limit 5` 重跑改写集前 5 条(`results/para_compile_haiku_flagoff_check_20260816.jsonl`),
  与 2026-08-15 冻结记录(`results/para_compile_haiku_20260815.jsonl`)逐题比较
  `test_plan` 字段——**5/5 完全相同**。冻结行为在旗标关闭时确认未变。

---

## 五、成本与落盘

| 项目 | tokens_in | tokens_out | 成本上界 |
|---|---|---|---|
| 规范文档版全量(1107 题) | 2,262,290 | 28,745 | $2.41 |
| 冒烟(20 题) | 41,032 | 964 | $0.05 |
| 旗标关对拍复核(5 题) | 9,523 | 246 | $0.01 |
| **合计** | 2,312,845 | 29,955 | **$2.46**(预算 ≤$3) |

落盘文件:
- 代码:`scripts/complex_query_arm.py`(新增 `_COMPILE_SPEC` 旗标 + `COMPILE_PROMPT_SPEC`
  常量 + `compile_plan()` 选路逻辑,均为附加式变更,冻结默认行为不变)
- 量化脚本:`scratchpad/ngram_containment.py`(n-gram containment 计算,零 API 成本)
- 全量结果:`results/para_compile_haiku_spec_20260816.jsonl` +
  `results/para_compile_haiku_spec_20260816.meta.json`
- 冒烟:`results/para_compile_haiku_spec_smoke_20260816.jsonl`(20 条)
- 对拍复核:`results/para_compile_haiku_flagoff_check_20260816.jsonl`(5 条,旗标关)
- 本报告:`results/compile_spec_decoupling_20260816.md`

## 六、结论与后续

耦合审计标记的**全库最高危项**(COMPILE_PROMPT 与出题模板同分布)现已有一个**默认关闭、
经量化验证不显著劣化**的替代实现路径。旗标 `QVF_COMPILE_SPEC=1` 可在下一轮零改动新域测试
(去耦合路线图排期第 3 项)中作为编译侧的对照臂纳入,检验"形式语义 → 泛化"这条链路在真正
域外数据(P69/P1303/P26)上是否同样成立;本轮的 1107 条改写集虽题面盲写、但槽位/标签体系
仍与训练分布同源(闭集内),不能替代零改动新域测试的证据效力,这一点须在论文中一并注明,
不可用本结果单独主张"few-shot 去除后即可泛化到任意新域"。
