# QVF 四线缺陷修复 · 可实施施工规格(2026-08-18)

**本文档由四份只读复算规格(线一 日期比较 / 线二 算子层契约违反 / 线三 分组键与打分 / 线四 溯源修复)合并而成,目的是让主线程照着逐条实施。**

**本文档自身的纪律**:全程只读复核了四份规格引用的代码锚点(见 §1.4 锚点核验表),未修改任何 `.py` 或 `results/` 文件;未打开任何 gold / `judge_correct` / 题目答案;未消耗任何数据集的揭盲预算。

---

## 〇、去特调自检表

**筛子**:不看 gold 就能发现的缺陷是 bug;必须看了 gold 才发现的是特调。

`discovered_by` 三值:`contract_violation`(输出违反代码自己的契约/类型承诺)/ `internal_inconsistency`(代码自相矛盾:字段被填却从不被读、注释与实现不符、裸串比较混粒度)/ `answer_was_wrong`(靠答案错才发现)。

### 0.1 逐项自检表

| 编号 | 修复项 | `discovered_by` | 引用过 gold | 消耗揭盲预算 | 本轮实施 |
|---|---|---|---|---|---|
| **R1-1** | `_rec_date` 不校验返回值(`complex_query_arm.py:340-342`) | `contract_violation` | 否 | 否 | ✅ 阶段 1 |
| **R1-2** | `_rec_date` 同缺陷第二处(`wt_qvf_prototype.py:477-478`) | `contract_violation` | 否 | 否 | ✅ 阶段 1 |
| **R1-3** | `point_in_time` 裸字符串 `<=`,同库另一臂有 `_pdate` 却不共用(`wt_qvf_prototype.py:612-614`) | `internal_inconsistency` | 否 | 否 | ✅ 阶段 1 |
| **R1-4** | `_hygiene_pool` 平局判据 `bool("April")` 为真(`complex_query_arm.py:484-486`) | `internal_inconsistency` | 否 | 否 | ✅ 阶段 1 |
| **R1-5** | 两套入链判据(真值 vs `_pdate is not None`)⇒ 幽灵链位 | `internal_inconsistency` | 否 | 否 | ✅ 被 R1-1/2 蕴含 |
| **R1-6** | `asof_index` docstring 自称与线性扫描"逐一等价",实测分歧(`qvf/store_index.py:185-204`) | `contract_violation` | 否 | 否 | ✅ 阶段 1(文档+assert) |
| **R1-7** | I3 保持性论证称"由构造自动保证",构造只在输入合规时成立(`qvf/store_index.py:44-63`) | `internal_inconsistency` | 否 | 否 | ✅ 阶段 0(纯文档) |
| **R1-8** | `_query_date` 可产出 `2025-02-31`(`complex_query_arm.py:797-801`) | `internal_inconsistency` | 否 | 否 | ⛔ 延后(破坏基线) |
| **R1-9** | `check_invariants()` 写了不变量但无任何生产路径调用;I1/I4 在归档库上失败 | `internal_inconsistency` | 否 | 否 | ⛔ 延后(线一之外) |
| **R2-F1** | `_pdate` 静默猜错年份(`"02-12"`→公元 2 年)、丢弃 `parse_partial_date` 的规约记号 `note` | `contract_violation` | 否 | 否 | ✅ 阶段 1(并入 R1) |
| **R2-F2** | `longest`/`argmax_dur` 把粗粒度日期当日精度上报;冠亚军区间重叠仍指名冠军 | `contract_violation` | 否 | 否 | ✅ 阶段 3 |
| **R2-F3** | 时点/窗界比较在候选记录区间跨过被比较日期时不由数据决定,却带 `This IS the answer` | `contract_violation` | 否 | 否 | ✅ 阶段 3 |
| **R2-F4** | `check_expr` 放行域外索引;`_resolve_bound` 把越界序数静默降级成"该侧无界",双侧窗退化成单侧 | `contract_violation` | 否 | 否 | ✅ 阶段 2 |
| **R2-F5** | 空集合上的聚合被渲染成答案(0 行证据 + 确定数字 + `IS the answer`);`count_changes` 空链返 −1 | `contract_violation` | 否 | 否 | ✅ 阶段 2 |
| **R2-F6** | `EVIDENCE_CAP=12` 静默截断,而 `tag_trend` 结论行枚举全量并要求"只引用上面这些" | `internal_inconsistency` | 否 | 否 | ✅ 阶段 3 |
| **R2-F7** | `winners` 复数列表被算出却只渲染 `winners[0]`,并列从不披露 | `internal_inconsistency` | 否 | 否 | ✅ 阶段 3 |
| **R2-S1** | `slot_cardinality` 抽而不用(= R3-4 同一条,合并) | `internal_inconsistency` | 否 | 否 | ✅ 阶段 5 |
| **R2-S2** | `first_last` 宏建的 `PICK` 节点从不被渲染器读取 | `internal_inconsistency` | 否 | 否 | ⛔ 延后 |
| **R2-S3** | `COMPILE_PROMPT_SPEC` 称 `count_before` = "at or before" 并自称与严格 before 等价;代码用严格 `<` | `internal_inconsistency` | 否 | 否 | ⛔ 延后(改提示词=重编译) |
| **R2-S4** | 台账「306 条未补零」不可复现(实测 0 条) | `internal_inconsistency` | 否 | 否 | ✅ 阶段 0(纯文档) |
| **R3-1** | `comp_score` 上游块注释权重方向与代码相反,且两条注释对"污染卡有无关系边"假设互斥 | `internal_inconsistency` | 否 | 否 | ✅ 阶段 0(纯注释) |
| **R3-2** | `_slot_match` 第三分支被同时用于"等价关系"与"相关性"两种语义;R1 上与写入侧命名契约矛盾 | `internal_inconsistency` | 否 | 否 | ✅ 阶段 4 |
| **R3-3** | 同上,`qvf_router.py:322-325` 的 union | `internal_inconsistency` | 否 | 否 | ✅ 阶段 4 |
| **R3-4** | `slot_cardinality` 被 schema 定义、被写入侧与另一条读取路径消费,11 算子主读取路径 0 次读取 | `internal_inconsistency` | 否 | 否 | ✅ 阶段 5 |
| **R3-5** | `qvf_router.py:290` docstring 自称"v3 同款",而 `rel` 项定义与 `wt_qvf_prototype.py:578` 不同 | `internal_inconsistency` | 否 | 否 | ✅ 阶段 0(纯注释) |
| **R3-6** | `rel` 项两处定义对齐(`QVF_SCORE_ALIGN`) | `internal_inconsistency` | 否 | 否 | ⛔ 不实施(0.04% 分量,收益不明) |
| **R3-7** | `_hygiene_pool` 注释逐字称"一句话至多宣告一个状态",对集合值属性为假(一句可宣告多个成员)—— **本轮合并时新发现,未量化** | `internal_inconsistency` | 否 | 否 | ⛔ 先量化再实施 |
| **R4-1** | 建卡契约 Rule 1 要求 `source_span` 是逐字子串,建卡路径上无一行校验 | `contract_violation` | 否 | 否 | ✅ 阶段 6 |
| **R4-2** | `VERIFY_SPAN=2` 把"引文为真、仅指针指错"的卡片与编造卡一起剔除 | `contract_violation` | 否 | 否 | ✅ 阶段 6 |
| **R4-3** | 模型自加说话人标签后从轮次中段截取,被裸 `in` 判成同一类违约 | `internal_inconsistency` | 否 | 否 | ✅ 阶段 0'(level 1) |
| **R4-4** | `source_memory_id` 指向同 uid 内不存在的 memory(悬空);9 条指向该卡批次之外 | `contract_violation` | 否 | 否 | ✅ 阶段 6 |
| **R4-5** | `_all = "\n".join(...)` 拼接判据在 span 跨拼接换行时误判"在库内" | `internal_inconsistency` | 否 | 否 | ⛔ 不实施(实测 0 次,属潜在) |

### 0.2 总结

> **本批 33 项修复中,33 项是零 gold 发现的,0 项不是。**
> `contract_violation` 11 项 / `internal_inconsistency` 22 项 / **`answer_was_wrong` 0 项**。
> 因此附录「待独立验证的猜想」为**空**,**本批未消耗任何数据集的揭盲预算**。

### 0.3 必须披露的两处持出集轻度窥视(主动补盲,非 gold)

| 处 | 读了什么 | 是否 gold | 是否参与方案选择 |
|---|---|---|---|
| 线一 §2.1/§2.3 | 读了 `results/wt_cards_s8_heldout/` 的 30 个**卡片文件**,得"7 条违约日期 / 5 条幽灵链(5 在链尾)" | 否(写入侧统计) | **否**,只作"同一缺陷在持出集同样在场"的存在性说明 |
| 线二 §0(a) | 在 heldout 切分上计了**违反行数**(16/133),未打开题面与答案 | 否(算子输出自检) | **否**,不参与 F1–F7 任何规则选择 |

S8 的揭盲预算按**未动**计。但两处都说明:**S8 heldout 的输入已被机械扫过**,因此 §6.4 的"持出集只准用一次"约定必须写死并 commit。

### 0.4 本文档明确拒绝的做法(与四份输入一致)

- 逐题打开答错的题去找修法(用持出集选修法);
- 比较"哪个打分公式/哪种 tie-break/哪个 level 准确率更高"然后选高的那个;
- 以"准确率降了"为理由回退语义选择或改选备选规则。

---

## 一、施工顺序与冲突表

### 1.1 文件 × 函数 冲突矩阵

| 文件 | 函数/区块 | 线一 | 线二 | 线三 | 线四 | 冲突级别 |
|---|---|---|---|---|---|---|
| `scripts/complex_query_arm.py` | 旗标块(`:73`–`:82` 之后) | 加 `_DATE_STRICT` | 加 `_DATE_STRICT` + 4 个 | 加 `_SLOT_CARD` | — | **⚠️ 插入位置三方争夺 + 旗标同名** |
| | `_rec_date` `:340-342` | **改函数体** | — | — | 改它读的字段值 | **⚠️ 语义耦合(见 C2)** |
| | `_pdate` `:345-350` | 不改 | **改** | — | — | ⚠️ 见 C1 |
| | `_chain` `:424-435` | 不改(靠蕴含) | **改(重排+剔除)** | 之后插入 2 个纯函数 | — | **⚠️ 见 C1** |
| | `_hygiene_pool` `:467-490` | **改 `:484-486`** | — | (语义质疑 R3-7) | 去重键受指针变更影响 | ⚠️ 三方 |
| | `longest` `:694-713` | — | **改(F2/F7)** | **改(set 分支)** | — | **⚠️ 同分支两旗标,见 C6** |
| | `point_in_time` `:668-684` / `count_before` `:714-723` | — | **改(F3)** | **改(set 分支)** | — | ⚠️ 同分支两旗标 |
| | `current`/`premise_check` `:653-667` | — | — | **改(set 分支)** | — | 无 |
| | `tag_trend` `:626-638` | 不改(`[:4]` 被蕴含) | **改(F6)** | — | — | 无 |
| | `_query_date` `:797-801` | 延后 | — | — | — | 无 |
| `scripts/wt_qvf_prototype.py` | `:93-95` 旗标块 | — | — | — | **插入 ~30 行** | ⚠️ 行号漂移源 |
| | `_slot_match` `:465-474` 之后 | — | — | **插入 ~45 行** | — | ⚠️ 行号漂移源 |
| | `_rec_date` `:477-478` | **改** | — | — | — | 见 C2 |
| | union 循环 `:565-568` | — | — | **改** | — | **⚠️ 在线四哈希守卫块内** |
| | `point_in_time` `:612-614` | **改** | — | — | — | **⚠️ 在线四哈希守卫块内** |
| | 裁决块 `:534-657` 整体 | 改 1 处 | — | 改 1 处 | **sha256 守卫** | **⚠️ 见 C4** |
| | `:362-374` / `:401-404` | — | — | — | **改** | 无 |
| `scripts/qvf_algebra.py` | `_resolve_bound` `:243-255` | — | **改(F4)** | — | — | 无 |
| | `check_expr` `:176-226` | — | **改(F4)** | — | — | 无 |
| | `_render_direct` `:664-671` | — | **改(F5)** | — | — | 无 |
| | `count_changes` `:334-335` | — | **改(F5)** | — | — | 无 |
| | `argmax_dur` `:342-349` | — | **改(F2)** | — | — | 无 |
| | `ASOF` `:366-374` / `_in_window` `:302-310` | 不改(靠蕴含) | **改(F3)** | — | — | ⚠️ 见 C5 |
| `scripts/qvf_router.py` | `:25-26` import / `:322-325` union / `:290` docstring | — | — | **改** | — | 无 |
| `qvf/store_index.py` | `:44-63` / `:185-204` | **文档+assert** | — | — | — | 无(自动继承 `_rec_date`) |
| `qvf/date_norm.py` | 新建 | ✅ | — | — | — | 无 |
| `qvf/span_repair.py` | 新建 | — | — | — | ✅ | 无 |

### 1.2 六条真冲突与处置

**C1 · 旗标同名、语义相反(最严重)。**
线一与线二都占用 `QVF_DATE_STRICT`,但语义不同且**对同一批记录的处置相反**:

| | 线一 `QVF_DATE_STRICT=2` | 线二 F1 `QVF_DATE_STRICT=1` |
|---|---|---|
| 咽喉点 | `_rec_date`(输入校验) | `_pdate` + `_chain`(解析与链构造) |
| 违约 `stated_date` 的处置 | **判缺失 → 回落会话日期**(记录留在链上,拿到合法日期) | **记录被剔除**(不进任何有日期的链) |
| 排序 | 不改(证明 G 内字符串序 ≡ 日历序,0/54,303,831) | 改成 `_date_key` 补零键 |

处置(**决策 D1,需拍板**):`QVF_DATE_STRICT` 保留线一语义(0=冻结 / 1=判缺失但不回落=诊断挡 / 2=判缺失并回落=采纳目标)。**线二 F1 的"剔除"语义等于线一的 `=1`,不另立旗标。** 线二 F1 的"补零排序键"在 `=2` 下是 **no-op**(链上日期已全在文法 G 内),按"无证据不改冻结代码"**不实施**。线二 F1 中**不被蕴含**、必须单独落地的只有一半:`_pdate` 自身对**非 `_rec_date` 来源**的日期串仍会静默猜错(见 C5)。

**C2 · `_rec_date` 的语义耦合(线一 × 线四)。**
线四的 `date_neutral` 判据是 `bool(rec["stated_date"]) or mem_dates[new]==mem_dates[declared]`。线一开旗标后,`bool(stated_date)` 不再等价于"`_rec_date` 不看指针"——违约的 `stated_date` 会回落到会话日期,于是指针**又变得重要**。
处置:线四 `repair_spans` 的 `date_neutral` 计算**必须改为比较 `_rec_date` 的实际返回值**,不得用 `bool(stated_date)`。规格见 §3.4.3。**这条不修,线四 L2 的"日期中性"承诺在线一落地后即失效。**

**C3 · 行号漂移。**
`wt_qvf_prototype.py` 上三条线各自插入代码块:线四在 `:95` 后 +30 行、线三在 `:474` 后 +45 行。若按行号盲改,后落地的补丁必然打错位置。
处置:**本文档每一处补丁除行号外都给"锚串"(文件内唯一的改前文本片段),实施时以锚串定位,行号仅作参考。** 施工顺序按 §1.3,每阶段落地后重新 `grep -n` 记录新行号并更新本文档的行号列(内容不变)。

**C4 · 线四的 sha256 冻结块守卫必然失效。**
线四 `scripts/verify_span_repair_wt_parity.py` 逐字复制 `wt_qvf_prototype.py:534-657` 裁决块并断言 `sha256[:16]=897c85a68de068b8`;而线一改 `:612-614`、线三改 `:565-568`,**两处都在块内**。
处置:①**阶段 6(线四)必须最后落地**,守卫哈希在冻结块**最终形态**上登记一次;②守卫的语义从"块未变"改为"块与本脚本内的副本一致",并在文档里写死"任何冻结块变更后必须重新登记哈希并同步副本";③若阶段 4/5 之后还要动该块,重登记一次。

**C5 · 线一的咽喉点归并论证不覆盖 LLM 流入的日期(本轮合并时补的盲)。**
线一证明"`_rec_date` 归一后所有下游站点被蕴含",但**只覆盖从卡片流出的日期**。以下站点的日期**从编译器/聚焦 LLM 流入**,不受建卡契约约束,咽喉点管不到:

| 站点 | 日期来源 | 现状 |
|---|---|---|
| `complex_query_arm.py:669` `qd = _pdate(plan["date"])` | 编译 LLM | 归档里有 `2013-10-00`(合法)与月粒度被当日期用 |
| `complex_query_arm.py:715` `count_before` 的 `qd` | 编译 LLM | 同上 |
| `qvf_algebra.py:241` `_pdate(literal)` | 编译 LLM 的 `before`/`after` 字面量 | 同上 |
| `wt_qvf_prototype.py:613` `qf.point_date` | 聚焦 LLM | 线一 R1-3 已覆盖 |

处置:线一的 `_rec_date` 补丁**必须**配一个 `_pdate` 侧的严格化(拒 `year<1000`、拒非 ISO、不猜),即线二 F1 的**保留部分**。合并规格见 §3.1.3。**这是两条线的交集,任一条单独实施都留有洞。**

**C6 · `longest` / 时点算子分支被 R2-F2/F3 与 R3-4 双重改写。**
`complex_query_arm.py:694-713`(`longest`)、`:668-684`(`point_in_time`)、`:714-723`(`count_before`)三个分支上,线二加"粒度不可判定"前置分支,线三加"set 链无定义"前置分支。
处置(**决策 D4b**):**定义域检查先于精度检查** —— `set` 判定在最外层,粒度判定在 `single` 分支内。第一性原理:若属性是集合值,"最长持有"这个问法根本没有指称对象,讨论它的**精度**是无意义的;反之精度问题只在问法有指称时才存在。代码形态:

```python
if _SLOT_CARD and card == "set":
    ...            # R3-4 的 set 分支(无定义/加入-移除计数)
elif per_value and _DUR_GRAN:
    ...            # R2-F2 的粒度区间分支
elif per_value:
    ...            # 冻结原文逐字保留
```

### 1.3 推荐施工顺序(不冲突序 + 理由 + 工时/成本)

| 阶段 | 内容 | 顺序理由 | 预估工时 | LLM 成本 | 零 LLM 可验 |
|---|---|---|---|---|---|
| **0** | 纯注释/文档:R3-1、R3-5、R1-7、R2-S4、R1-6 的文档半 | 平凡字节等价;先把"注释打架"清零,后续所有 diff 归因不再受错注释误导。**台账 306 条必须此刻更正,否则将来有人据它立项** | 1.0 h | $0 | `import` 冒烟 + `algebra_parity.py` |
| **0'** | R4-3(`QVF_CARD_REPAIR_SPAN=1`,只剥说话人标签) | 与后续所有基线**正交**:唯一受影响的 kufix 是 wt 臂语料,**不含 plan 行**,不在线一 3,209 行 / 线二 1,463 行复放语料内;v42 上 0 卡受影响;`read_phase` 全程不读 `source_span` | 1.5 h | $0(离线派生) | `span_audit.py` 复跑 + `filecmp` |
| **1** | 日期层地基:R1-1、R1-2、R1-3、R1-4 + `_pdate` 严格化(C5)+ R1-6 的 assert;新建 `qvf/date_norm.py` | 阶段 3 的粒度判据依赖它给出的 `gran`;**必须先捉 3,209 行与 1,463 行两套基线再打补丁**(顺序颠倒即测不出任何东西) | 4.0 h | $0 | `date_strict_replay.py` + `census2.py` + `check_i3.py` |
| **2** | R2-F4 → R2-F5(成对,顺序不可倒) | F4 把静默丢界升级为显式失败,F5 负责不把失败渲染成答案;先 F5 后 F4 会让 F5 接不到那 17 例。只碰 `qvf_algebra.py`,与阶段 1 的 `complex_query_arm.py` 改动不冲突。二者合计杀 98/245 例 | 3.0 h | $0 | `census2.py`(C1/B1/C3/A1b/B5/C2/C4 → 0) |
| **3** | R2-F2+F7、R2-F3、R2-F6(三者互相独立,可并行) | 依赖阶段 1 的 `gran`;合计杀 236/245 例 | 4.5 h | $0 | `census2.py`(E1/E4/E6/E7/E2 → 0) |
| **4** | R3-2、R3-3(`QVF_SLOT_STRICT`) | 它改变**分量与选池**,会让阶段 1–3 的全部基线数字位移。放在后面 ⇒ 前面每一步的 diff 可单独归因。**落地后必须重跑 §4 的 census 与线一 replay 基线并如实登记新数字**(旧的 245 / 655 不再成立) | 2.5 h | $0 | `router_offline_ab.py` 0 分歧 + 并查集细化断言 |
| **5** | R3-4(`QVF_SLOT_CARD`) | 依赖阶段 4 固定的池成分(修严后多数票基数可能翻转);与阶段 3 的 `longest` 分支按 C6 嵌套 | 5.0 h | $0 | `algebra_parity.py` + `single` 池 diff 恒 0 |
| **6** | R4-1、R4-2、R4-4(`QVF_CARD_REPAIR_SPAN=2/3`) | ①它改**卡片库内容**,一旦落地前五阶段的 replay 基线全部作废(基线的定义是"同一卡片库上的纯代码重放");②C4 的哈希守卫必须在冻结块最终形态上登记 | 6.0 h | $0(离线派生) | `span_audit.py` 硬断言 5 条 + wt 槽位全枚举对拍 |
| **⛔** | R1-8、R1-9、R2-S2、R2-S3、R3-6、R3-7、R4-5 | 见 §0.1 与 §7 | — | — | — |

合计 27.5 h,LLM 成本 $0(**全部 8 个阶段的验证均零 LLM**;唯一烧 token 的是 §6 预注册之后的端到端判分,题数由零 LLM 对拍先判定后再登记,本文档不预估)。

### 1.4 锚点核验表(本轮只读复核,截至当前 HEAD)

| 锚点 | 声明位置 | 复核结果 |
|---|---|---|
| `_CARD_RENUMBER/_CARD_VERIFY_SPAN/_CARD_FAIL_LOUD` 三行 | `wt_qvf_prototype.py:93-95` | ✅ 一致 |
| `if _CARD_VERIFY_SPAN:` 校验块 | `wt_qvf_prototype.py:375-392` | ✅ 一致(`_all = "\n".join(...)` 在 `:377`) |
| `_norm` / `_slot_match` / `_rec_date` | `wt_qvf_prototype.py:463-478` | ✅ 一致 |
| `chain = sorted(cand, ...)` / `valid = [... <= qf.point_date]` / `if _rec_date(r) < _rec_date(latest)` | `wt_qvf_prototype.py:599 / 613 / 645` | ✅ 一致 |
| `_rec_date` / `_pdate` | `complex_query_arm.py:340-342 / 345-350` | ✅ 一致 |
| `sorted(pool, key=...)` ×2 / `_chain` 真值判据 / `_hygiene_pool` 平局 | `complex_query_arm.py:378,380 / 428-430 / 484-486` | ✅ 一致 |
| `longest` / `count_before` / `_query_date` | `complex_query_arm.py:694-713 / 714-718 / 797-801` | ✅ 一致 |
| `EVIDENCE_CAP = 12` | `complex_query_arm.py:105` | ✅ 一致 |
| `_resolve_bound` 越界返回 `(False,None,None)` | `qvf_algebra.py:246-255` | ✅ 一致 |
| `_in_window` 双侧严格开 / `count_changes = len(chain)-1` / `argmax_dur` / `ASOF` `gi` / `_render_direct` Value | `qvf_algebra.py:302-310 / 334-335 / 342-349 / 366-374 / 664-671` | ✅ 一致 |
| `sort_key` 第一分量裸串 / `_asof_dates` 注释"严格递增" / `asof_index` docstring"逐一等价" | `qvf/store_index.py:163-167 / 185-186 / 188-204` | ✅ 一致 |
| `from scripts.wt_qvf_prototype import _norm, _slot_match` | `qvf/store_index.py:139` | ✅ 一致 |

**行号在阶段 0 落地后即开始漂移**,以锚串为准。

---

## 二、统一旗标设计

### 2.1 旗标全表

| 旗标 | 取值 | 默认 | 所在文件 | 依赖 | 互斥/告警 |
|---|---|---|---|---|---|
| `QVF_DATE_STRICT` | 0/1/2 | **0** | `complex_query_arm.py`、`wt_qvf_prototype.py` | 无 | 1 与 2 互斥取值;**吸收线二 F1 的剔除语义为 `=1`** |
| `QVF_DUR_GRAN` | 0/1 | **0** | `complex_query_arm.py`、`qvf_algebra.py` | **要求 `QVF_DATE_STRICT>=1`,否则启动即 `SystemExit`** | 与 `QVF_SLOT_CARD` 按 C6 嵌套 |
| `QVF_DUR_TIE` | 0/1 | **0** | 同上 | 无(日粒度并列也发生) | 可单独开 |
| `QVF_ASOF_GRAN` | 0/1 | **0** | `complex_query_arm.py`、`qvf_algebra.py` | **要求 `QVF_DATE_STRICT>=1`** | 同上 |
| `QVF_TYPECHECK_DOMAIN` | 0/1 | **0** | `qvf_algebra.py` | 无 | 建议与 `QVF_OP_FAIL_LOUD` 同开(F4 的显式失败需 F5 接住) |
| `QVF_OP_FAIL_LOUD` | 0/1 | **0** | `qvf_algebra.py` | 无 | 同上 |
| `QVF_EV_CAP_HONEST` | 0/1 | **0** | `complex_query_arm.py`、`qvf_algebra.py` | 无 | 无 |
| `QVF_SLOT_STRICT` | 0/1 | **0** | `wt_qvf_prototype.py`、`qvf_router.py` | 无 | **只作用于 R1(卡↔卡分组),R2(查询↔卡选池)一字不动** |
| `QVF_SLOT_CARD` | 0/1/2 | **0** | `complex_query_arm.py` | 无 | **`QVF_ALGEBRA=1` 时不生效 ⇒ 必须启动告警(见 2.3)** |
| `QVF_CARD_REPAIR_SPAN` | 0/1/2/3 | **0** | `wt_qvf_prototype.py` + `qvf/span_repair.py` | 与 `QVF_CARD_VERIFY_SPAN` **正交**(笛卡尔积) | `date_neutral` 判据随 `QVF_DATE_STRICT` 变(C2) |

**新增 9 个旗标,全部默认 0。** 不新增:`QVF_DATE_GRAN`(`_pdate_gran` 是无副作用新纯函数,不需旗标守护;只有 `QVF_DUR_GRAN`/`QVF_ASOF_GRAN` 会调用它)、`QVF_SCORE_ALIGN`(不实施)。

### 2.2 依赖的强制方式:fail loud,不静默降级

依赖不满足时**不得**静默按 0 处理(那会产出一份"看起来开了旗标其实没开"的实验)。统一在 `complex_query_arm.py` 旗标块末尾加:

```python
# 旗标依赖强制(照 QVF_CARD_FAIL_LOUD 的风格:宁可拒跑,不静默降级)。
# 理由:_DUR_GRAN/_ASOF_GRAN 的区间上下界由 _pdate_gran 给出,而 _DATE_STRICT=0
# 时链上仍可能带 "02-12"->公元 2 年这类被猜出来的日期(实测 26,959 条带日期
# 记录中 230 条,0.85%),此时区间边界本身无意义 —— 静默跑出来的"不可判定
# 告警"会指向错的记录。
if (_DUR_GRAN or _ASOF_GRAN) and not _DATE_STRICT:
    raise SystemExit(
        "QVF_DUR_GRAN/QVF_ASOF_GRAN require QVF_DATE_STRICT>=1 "
        "(granularity bounds are meaningless on unvalidated dates)")
```

`QVF_SLOT_CARD` × `QVF_ALGEBRA` 的告警见 2.3。

### 2.3 一条必须写进代码的臂间一致性告警(本轮合并时新增)

线三自己声明:`QVF_ALGEBRA=1` 时 `execute_plan` 被重绑,set 语义在代数臂上**需另立规格,本轮不实施**。但路由会把同类题分派到平面臂与代数臂两侧 —— 若 `QVF_SLOT_CARD=1` 且 `QVF_ALGEBRA=1`,同一个集合值属性在平面臂上得"成员集合",在代数臂上得"末值 + 单值裁决",**结果不可归因**。

```python
if _SLOT_CARD and int(os.environ.get("QVF_ALGEBRA", "0") or 0):
    raise SystemExit(
        "QVF_SLOT_CARD is not implemented on the algebra arm "
        "(qvf_algebra.py rebinds execute_plan); running both flags at once "
        "makes set-valued slots behave differently per arm and the result "
        "un-attributable. Implement the algebra-arm spec first.")
```

### 2.4 旗标注释统一格式(照抄 `QVF_CARD_*` 风格)

每个旗标的注释必须含以下五段,缺一不可:

```
# QVF_XXX=1:<一句话说明改了什么>。
#   缺陷证据:<实测数字> + <文件:行号> + <最小可复现例的脚本命令>。
#   语义依据:<第一性原理/契约原文逐字引用>,不含任何准确率理由。
#   默认 0 = 冻结行为逐字节不变(<关时为何等价的机械论证:短路/恒值/未 import>)。
#   预注册代价:<零 LLM 复算出的行数/题数迁移>,达不到怎么处置见
#   study_logs/QVF_repair_specs_20260818.md §6。
```

**"关时逐字节等价"的机械论证必须逐条写出**,不能只写一句"默认关"。三种可接受的论证形态:①`if _FLAG and ...` 的**短路**(旗标为 0 时第一个合取项即假,后续不求值);②新增函数/变量的**恒值**(`card` 恒为 `"single"`、`_rec_batch` 恒为 `[]`);③**延迟 import**(`from qvf.span_repair import ...` 写在 `if` 内,旗标关时模块不进 `sys.modules`)。

---

## 三、逐条实施规格

### 3.1 第一节 · 日期层(线一 + 线二 F1 的保留部分)

#### 3.1.1 缺陷证据(全部零 gold,只用"顺序是否与真实时序相反 / 代码是否违反自己的契约")

**必须先纠正两条历史台账口径**(否则修法立项依据是错的):

| 台账原文 | 复算结果 |
|---|---|
| `results/QVF_system_reality_audit_20260817.md:88` 与 `:851`:"306 条未补零(如 `2019-3`)" | **不可复现。** 全 30–34 个 `results/wt_cards*` 库、40,088 条带日期记录中 `YYYY-M`/`YYYY-MM-D` 形态 = **0 条**(两条独立复算脚本一致) |
| "另有 3 条 5 段、1 条 7 段垃圾值" | 段数 >3 共 **15 条**,且不是垃圾,全是**日期区间/多日期串**(`2025-02-20 to 2025-02-25`、`2025-10-15,2025-10-22,2025-10-29`) |

真实违约形态与量(全 30 个 `results/wt_cards*` 库,40,088 条带 `stated_date` 记录):

| 形态 | 条数 | 占比 | 实例 |
|---|---|---|---|
| 合规(文法 G) | 38,484 | 96.00% | — |
| `_pdate` → `None`(对日期算子隐形) | 1,243 | 3.10% | `April`(61)、`04-15`(33)、`1920s`(31) |
| **`_pdate` → 公元 1000 年前的荒谬日** | 361 | 0.90% | `02-10`→`0002-10-01`(56)、`06`→`0006-01-01`(23) |
| 段数 >3 | 15 | 0.04% | 日期区间串 |

**关键的反直觉结论(本批最重要的范围收缩)**:裸字符串比较**在合规输入上是正确的,不是缺陷**。在归档库 ∪ 数据集实际出现的 **10,422 种 G 内日期串**上,字符串序 ≡ 日历序:**54,303,831 对中 0 对不一致**。对照:G 外可解析串与 G 内串之间存在 **83,933,014** 个逆序对 —— 缺陷的**全部**来源。
⇒ 修法不是"重写 5 处 `sorted()` + 4 处比较运算符",而是**一个咽喉点的输入校验**。

三条判决性证据:

1. **幽灵链位**:`_chain()` 入链判据是 `_rec_date` **真值**,`WINDOW`/`ASOF` 可见判据是 `_pdate is not None` —— 两个判据不同 ⇒ 一批记录占着链位却对点查隐形。`wt_cards_v42` 216 条 / `v43` 218 / `keyed` 215,其中 **120–123 条在链尾**,即 **`current` 算子正在向读者输出一个系统自己解析不了的日期串**:
   ```
   chain011-3c88e770 ('user','other:hobby')  : current 报 'March 19th' since 'March 19'
   chain002-4781d89c ('','other:activity')   : current 报 'Halloween Horror Nights...' since '2025-10-22 and 2025-10-29'
   ```
2. **`store_index` 自带不变量在归档库上失败**:`check_invariants()` 在 `wt_cards_keyed` 425 个 uid 上 I3 失败 2 个、I2 失败 2 个。I3 = "链内解析日期不得逆序" ⇒ `_asof_dates` 注释声明的"严格递增"前置条件不成立 ⇒ `bisect` 前提被违反。**实测分歧**:
   ```
   wikiP108047-Q30001912  key=('user','device')
     链上日期串: ['1990-11-15','1993-12-26','1993-12-26','1995-10-13','1995-10-13','1996-05-03','2','2']
     asof(1994-01-01):  bisect -> 2     冻结线性扫描 -> 7     <<< 分歧
   ```
   两个被 docstring 断言"逐一等价"的实现给出不同答案。**且线性扫描给的 `7` 才是错的那个** —— 它取"最后一个满足 `pd<=qd` 的下标",不是"日期最大的满足者"。
3. **逆序对的唯一来源是年份段非四位**(683 条):`wt_cards` 139 对(`'001898'` vs `'1896'`)、`wt_cards_keyed` 16 对(`'2'`/`'22'` vs `'1990-11-15'`);`v42`/`v43`/`s8_heldout` **0 对**。

**爆炸半径上界**:用真实 `_select_pool` 选池,对 **3,209 行归档 plan**(全部 `results/*.jsonl`,**已排除 `s8_heldout*` 的 183 行**)判"选中链是否含违约日期"⇒ **655 / 3,209 = 20.41%** 为修复后必然出现 diff 的行数**上界**。按文件:`wsc_s5_test` 163/314、`wsc_s5_test_v42` 151/314、`wsc_s5_test_v42b1_union` 96/418、`writeside_sensitivity_v42_subset76` 44/76、`boundary_duel` 30/116、S8-dev 各 23/54。
误差源如实标注:卡片库按跑批文件名启发式映射,缺省 `wt_cards_keyed`;21 行因 uid 在 `data/` 找不到条目而跳过。**655 是量级正确的上界,不是精确值**,实施后由复放实测替换。

**附带的合法约定,修法必须接受**:归档 `plan.date` 中有 **20 行**是 `YYYY-MM-00` / `YYYY-00-00`(`2013-10-00`、`2003-00-00`)。这是 `parse_partial_date` 既有、S5 gold 生成器在用的**合法**约定(`00` = 未指定 → 规约为 1),**不得判违约**。

#### 3.1.2 新建 `qvf/date_norm.py`(全新文件,无冻结约束)

```python
# -*- coding: utf-8 -*-
"""日期可采纳文法 G、比较键与粒度。零依赖、零副作用、纯函数。

缺陷证据与出处:study_logs/QVF_repair_specs_20260818.md §3.1.1;
复现脚本 scratchpad/iso_check2.py(G 内 54,303,831 对中 0 对与字符串序不一致)。
G 的定义**不是**新发明:它是把 wt_qvf_prototype.CATALOG_PROMPT Rule 4
("stated_date: copy the date the TEXT states ... (YYYY[-MM[-DD]]), else empty")
与 gen_wikistate_complex.parse_partial_date 既有的 "00 = 未指定" 约定写成
可机械判定的谓词 —— 建卡契约本来就声明了这个类型,只是读取侧从未校验过。
"""
from __future__ import annotations
import re
from datetime import date

_G = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def is_admissible(raw) -> bool:
    """raw 是否为契约声明的 YYYY[-MM[-DD]](四位年、两位月/日、'00'=未指定)。"""
    s = str(raw or "").strip()
    if not _G.match(s):
        return False
    p = s.split("-")
    mo = int(p[1]) if len(p) > 1 else 0
    d = int(p[2]) if len(p) > 2 else 0
    try:
        date(int(p[0]), mo or 1, d or 1)   # 同时拒 2025-02-31 这类不存在的日
    except ValueError:
        return False
    return True


def granularity(raw):
    """返回 (规约后的日历日, 粒度) 或 None。粒度 ∈ {'year','month','day'}。
    '00' 月/日按 parse_partial_date 文档规约为 1,但粒度记为更粗的那一档 ——
    这是 QVF_DUR_GRAN / QVF_ASOF_GRAN 判"不可判定"的唯一依据。"""
    s = str(raw or "").strip()
    if not is_admissible(s):
        return None
    p = s.split("-")
    y = int(p[0])
    mo = int(p[1]) if len(p) > 1 else 0
    d = int(p[2]) if len(p) > 2 else 0
    if mo == 0:
        return (date(y, 1, 1), "year")
    if d == 0:
        return (date(y, mo, 1), "month")
    return (date(y, mo, d), "day")


def date_key(raw):
    """比较键 = (规约后的日历日, 原串)。不可采纳返回 None。

    第二分量取**原串**而非粒度秩:同一日历日内的平局由此退化为现行的字符串
    序,平局行为与冻结实现逐字节一致(论证见 §3.1.4(c))。
    """
    g = granularity(raw)
    return None if g is None else (g[0], str(raw).strip())


def span_bounds(raw):
    """粗粒度日期的**真实取值区间** [lo, hi](闭)。日粒度时 lo == hi。
    QVF_DUR_GRAN 的区间时长、QVF_ASOF_GRAN 的"区间是否跨过被比较日"都由此得出。
    """
    g = granularity(raw)
    if g is None:
        return None
    lo, gran = g
    if gran == "day":
        return (lo, lo)
    if gran == "month":
        nm = date(lo.year + (lo.month == 12), (lo.month % 12) + 1, 1)
        return (lo, date.fromordinal(nm.toordinal() - 1))
    return (date(lo.year, 1, 1), date(lo.year, 12, 31))
```

#### 3.1.3 补丁清单(六处)

**补丁 1-A · `complex_query_arm.py:82` 之后 —— 统一旗标块(三条线共用一处插入点,顺序固定)**

锚串:`_COMPILE_SPEC = int(os.environ.get("QVF_COMPILE_SPEC", "0") or 0)`

改后(在该行之后插入;`QVF_SLOT_CARD` 的完整注释见 §3.3.4,此处只占位):

```python
# QVF_DATE_STRICT:日期字段的契约化输入校验。见 qvf/date_norm.py 与
#   study_logs/QVF_repair_specs_20260818.md §3.1。
#   缺陷证据:全 30 个 results/wt_cards* 库、40,088 条带日期记录中 1,604 条
#   (4.00%)的 stated_date 违反建卡契约 Rule 4 声明的 YYYY[-MM[-DD]] 文法
#   —— 1,243 条使 _pdate 返 None(记录进链、进证据包、计入 count_changes,
#   却对每个日期算子隐形:v42 216 / v43 218 / keyed 215 条幽灵链位,其中
#   120-123 条在链尾,即 current 算子正在输出系统自己解析不了的日期串),
#   361 条被静默猜成公元 1000 年前的日期("02-10"->0002-10-01)。683 条年份
#   段非四位是全部逆序对的唯一来源(wt_cards 139 对 / keyed 16 对)。
#   语义依据(不含任何准确率理由):CATALOG_PROMPT Rule 4
#   (wt_qvf_prototype.py:146-148)自己写明 else 分支是 empty,并说明
#   "The round's own date is provided in metadata";_rec_date 的
#   "stated_date or session_date" 结构本身就把会话日期确立为声明的缺省值。
#   一个不属于声明文法的值,在该字段的类型语义下与"不存在"不可区分,故契约
#   忠实的读法就是走它自己的 else 分支。实测 255-318 条违约记录**确有**一个
#   合法会话日期可用,该回落是有货的,不是空转。
#   0 = 冻结行为(唯一新增开销是一次模块级 int() 读取)
#   1 = 【诊断挡】违约值判缺失但**不回落**,记录被 _chain 既有逻辑逐出链
#       —— 仅用于把"重排序效应"与"重定日效应"分开归因,不是采纳目标。
#       (此挡即线二 F1 原提的"剔除不可解析记录"语义。)
#   2 = 【采纳目标】违约值判缺失并回落会话日期;无会话日期则该记录无日期,
#       由 _chain 既有的 if not d: continue 排除,不需新逻辑。
#   预注册代价:3,209 行归档 plan 中 <=655 行(20.41%)出现 diff,判据见 §6.2。
_DATE_STRICT = int(os.environ.get("QVF_DATE_STRICT", "0") or 0)

# QVF_DUR_GRAN / QVF_DUR_TIE / QVF_ASOF_GRAN / QVF_EV_CAP_HONEST:见 §3.2。
_DUR_GRAN = int(os.environ.get("QVF_DUR_GRAN", "0") or 0)
_DUR_TIE = int(os.environ.get("QVF_DUR_TIE", "0") or 0)
_ASOF_GRAN = int(os.environ.get("QVF_ASOF_GRAN", "0") or 0)
_EV_CAP_HONEST = int(os.environ.get("QVF_EV_CAP_HONEST", "0") or 0)
# QVF_SLOT_CARD:见 §3.3.4(注释全文在那里,不得省略)。
_SLOT_CARD = int(os.environ.get("QVF_SLOT_CARD", "0") or 0)

from qvf.date_norm import (is_admissible as _date_admissible,  # noqa: E402
                           granularity as _date_gran,
                           span_bounds as _date_span)

# 旗标依赖强制(照 QVF_CARD_FAIL_LOUD 的风格:宁可拒跑,不静默降级)。理由见
# study_logs/QVF_repair_specs_20260818.md §2.2 与 §2.3。
if (_DUR_GRAN or _ASOF_GRAN) and not _DATE_STRICT:
    raise SystemExit(
        "QVF_DUR_GRAN/QVF_ASOF_GRAN require QVF_DATE_STRICT>=1 "
        "(granularity bounds are meaningless on unvalidated dates)")
if _SLOT_CARD and int(os.environ.get("QVF_ALGEBRA", "0") or 0):
    raise SystemExit(
        "QVF_SLOT_CARD is not implemented on the algebra arm "
        "(qvf_algebra.py rebinds execute_plan); running both at once makes "
        "set-valued slots behave differently per arm and the result "
        "un-attributable. Implement the algebra-arm spec first.")
```

> **注意**:`from qvf.date_norm import ...` 是**无条件** import。它不改变任何行为(纯函数,旗标关时不被任何代码路径调用),但会让 `qvf.date_norm` 进 `sys.modules` —— 与线四 `qvf.span_repair` 的"延迟 import"要求**不同**,因为线四的等价性断言里显式含 `"qvf.span_repair" not in sys.modules`,本处没有这条断言。若主线程希望统一口径,改为在 `if _DATE_STRICT or _DUR_GRAN or _ASOF_GRAN:` 内延迟 import。

**补丁 1-B · `complex_query_arm.py:340-342` —— 咽喉点**

锚串:`return rec.get("stated_date") or mem_dates.get(`

改前
```python
def _rec_date(rec: dict, mem_dates: dict) -> str:
    return rec.get("stated_date") or mem_dates.get(
        rec.get("source_memory_id", ""), "")
```
改后
```python
def _rec_date(rec: dict, mem_dates: dict) -> str:
    sd = rec.get("stated_date")
    if _DATE_STRICT and sd and not _date_admissible(sd):
        # QVF_DATE_STRICT:stated_date 违反建卡契约 Rule 4 的 YYYY[-MM[-DD]]
        # 文法(实测 1,604/40,088 违约)。契约自己的 else 分支是 empty,故违约
        # 值按缺失处理,走本函数既有的会话日期缺省。=1 不回落(诊断挡),
        # =2 回落(采纳目标)。见 §3.1。
        if _DATE_STRICT == 1:
            return ""
        sd = None
    return sd or mem_dates.get(rec.get("source_memory_id", ""), "")
```
**关时逐字节等价的机械论证**:`_DATE_STRICT` 为 0 ⇒ `if` 短路于第一个合取项 ⇒ 函数体等价于 `sd = rec.get("stated_date"); return sd or mem_dates.get(...)`,与改前表达式同一求值序、同一返回值。

**补丁 1-C · `complex_query_arm.py:345-350` —— `_pdate` 不猜(§1.2-C5,线二 F1 的保留部分)**

锚串:`return parse_partial_date(str(s))[0]`

改前
```python
def _pdate(s: str):
    """部分日期解析(与 S5 gold 生成器同一规约函数);失败返回 None。"""
    try:
        return parse_partial_date(str(s))[0]
    except Exception:  # noqa: BLE001
        return None
```
改后
```python
def _pdate(s: str):
    """部分日期解析(与 S5 gold 生成器同一规约函数);失败返回 None。

    QVF_DATE_STRICT>=1 时改走文法 G(qvf/date_norm.py):非 G 内的串一律返
    None,**决不猜**。这一半不被 _rec_date 咽喉点蕴含 —— 本函数还接收从
    编译器/聚焦 LLM 流入的日期(plan["date"] :669/:715、qvf_algebra
    _resolve_bound 的 before/after 字面量 :241),那些日期不受建卡契约约束。
    缺陷证据:parse_partial_date("02-12") 不抛异常,把首段当年份得公元 2 年,
    无任何范围检查;归档 26,959 条带日期记录中 230 条(0.85%)被这样猜错,
    并直接产出 655,369 天(1,795 年)的"最长任期"
    (复现:scratchpad/opaudit/repro.py --rules F1,F2 newdom_P26
     wikiP26028-Q119041180_s5a)。
    """
    if _DATE_STRICT:
        g = _date_gran(s)
        return g[0] if g else None
    try:
        return parse_partial_date(str(s))[0]
    except Exception:  # noqa: BLE001
        return None
```

**补丁 1-D · `complex_query_arm.py:484-486` —— `_hygiene_pool` 平局判据(不被咽喉点蕴含)**

锚串:`better = ((bool(r.get("stated_date")), len(str(r.get("value", ""))))`

改后
```python
            # QVF_DATE_STRICT:平局判据原用 bool(stated_date) —— bool("April")
            # 为 True,导致违约日期的碎卡反而**优先**于同会话内日期合法的那张
            # 被保留。本函数直接读 r["stated_date"],绕过 _rec_date,故不被
            # 咽喉点蕴含,必须单独改。旗标开时以"是否为契约内的日期"替代
            # "是否非空"。旗标关时 _dk(x) == bool(x.get("stated_date")),
            # 逐字节等价。
            def _dk(x):
                s = x.get("stated_date")
                return bool(s) and (not _DATE_STRICT or _date_admissible(s))
            better = ((_dk(r), len(str(r.get("value", ""))))
                      > (_dk(cur), len(str(cur.get("value", "")))))
```

**补丁 1-E · `wt_qvf_prototype.py:477-478` 的 `_rec_date`** —— 与补丁 1-B **同形**(该文件的 `_rec_date` 是独立定义,不与 `complex_query_arm` 共用)。旗标块与 `from qvf.date_norm import ...` 加在 `:95` 之后(与线四 Patch 1 同一插入区,顺序:线四注释块 → 线一注释块)。

**补丁 1-F · `wt_qvf_prototype.py:612-614` —— 全系统唯一一处连 `_pdate` 都没有的日期比较**

锚串:`valid = [r for r in chain if _rec_date(r, mem_dates) <= qf.point_date]`

改前
```python
            if scope == "point_in_time" and qf.point_date:
                valid = [r for r in chain if _rec_date(r, mem_dates) <= qf.point_date]
```
改后
```python
            if scope == "point_in_time" and qf.point_date and (
                    not _DATE_STRICT or _date_admissible(qf.point_date)):
                # QVF_DATE_STRICT:qf.point_date 来自读取侧聚焦 LLM 调用
                # (:525-530),不受建卡契约约束;它若违约,裸字符串 <= 的结果
                # 无意义。旗标开时交给下面既有的 else 分支("预设日期早于所有
                # 已知状态"文案)—— 不新增分支,不新增文案。
                valid = [r for r in chain if _rec_date(r, mem_dates) <= qf.point_date]
```
`:645` 的 `_rec_date(r) < _rec_date(latest)` **不改**:两端都是 `_rec_date` 输出,旗标开时同属 G,由字符串序 ≡ 日历序保证正确。

**补丁 1-G · `qvf/store_index.py` —— 仅文档更正 + 一条 assert(零行为改动)**

- `:44-63` 的 I3 保持性论证声称"由构造(严格单调排序 + 合并)自动保证" ⇒ 更正为:"构造只在**输入合规**时保证单调,而输入合规性从未被校验;实测 `wt_cards_keyed` 425 个 uid 上 I3 失败 2 个、I2 失败 2 个,`wt_cards` 上 I1 失败 11 个 / I4 失败 6 个(2026-08-18 复算,`scratchpad/check_i3.py`)"。
- `:188-191` 的"语义与冻结实现的线性扫描逐一等价" ⇒ 更正为:"**在 `_asof_dates` 单调时**等价;归档库上该前置条件不成立,实测 `wikiP108047-Q30001912` 的 `asof(1994-01-01)` bisect→2 / 线性→7,且**线性扫描给的 7 才是错的那个**(它取最后一个满足者,不是日期最大的满足者)。`QVF_DATE_STRICT>=1` 使前置条件成立。"
- `asof_index` 内加一条 `if __debug__` 断言,把"注释里的前置条件"变成"可失败的检查":
  ```python
  if __debug__:
      assert ds == sorted(ds), (
          "asof_index precondition violated: _asof_dates not monotonic "
          "(see study_logs/QVF_repair_specs_20260818.md §3.1.1)")
  ```
  理由:本轮 I3 之所以能被发现,靠的是这个模块**写了**不变量;`asof_index` 自己没写。

#### 3.1.4 三个语义选择的第一性原理依据(不用任何准确率)

**(a) `YYYY` 与 `YYYY-MM-DD` 比较时年份视为哪天 → 年初(1-1),月份视为月首。** 三条独立理由:
1. **右开区间语义强制**。链的语义是 `第 i 段有效区间 = [t_i, t_{i+1})`,`t_i` 读作"**自此**生效"。`"1997"` 断言"该状态在 1997 年内某时生效",与之相容的**最早**时刻是 `1997-01-01`。取年末等于断言"1997 年前 364 天该状态不生效",在"自此生效"的下界语义里凭空制造一段空洞 —— 而链上前一个状态的区间会去填这段空洞,即把一个我们**知道已被替换**的旧值判为在这 364 天有效。取年初不引入任何未被数据支持的断言。
2. **与已有 gold 生成器同源**。`gen_wikistate_complex.parse_partial_date` 已是年初/月首规约(`mo = mo or 1; d = d or 1`),S5 的机械 gold 与 `longest`/`count_before` 的闭区间时长口径全部建立在它之上。改成年末会让读取侧与出题侧用两套时间轴 —— 那是**新造**一个不一致,不是修一个。
3. **只有年初规约不改写归档序**。反事实实测:年末/月末规约在同一 51,242,626 对合规日期上产生 **13,606 对**与现行字符串序不一致(`'1710'` vs `'1710-01'`、`'1705-06'` vs `'1705-06-08'`)⇒ 选年末则全部归档实验必须无条件重算;选年初则合规链上零漂移,diff 可被逐条归因。

**被否决的第三选项(记录在案,不是遗漏)**:把 `YYYY` 表示成区间 `[1-1, 12-31]`,让 `ASOF` 在跨界时返回"不确定"。否决理由(第一性原理,非性能):11 算子闭集的 `Loc` 类型只有 `{gi: int | None}` 两个居民,没有"不确定"这个居民;引入它要改类型系统与 `check_expr` 的类型规则(`qvf_algebra.py:172-226`),那是改代数的定义域。**但见 §5 决策 D3:线二 F3 用"渲染层告警"而非"类型层第三居民"实现了同一诉求,两者可调和,不必否决整个诉求。**

**(b) 空值与违约值 → 违约值 ≡ 缺失,走契约自己的 else 分支(回落会话日期)。** 这不是启发式,是照读契约(依据见补丁 1-A 注释)。段数 >3 的日期区间串同样判违约→回落,**不做区间解析**(从"单点生效时刻"字段里恢复区间需要改字段语义)。**"剔除记录"是更严的选项,予以否决**:契约已经告诉了我们该怎么缺省,丢弃一条只是日期字段违约、值与锚点都完好的记录严于契约本身;保留为诊断挡 `=1`。

**(c) 归一化后 `asof`/`WINDOW` 的开闭区间语义 → 一个字节都不改。** `ASOF` 保持 `t_i <= d`;`WINDOW` 保持 `before` 严格 `<` / `after` 严格 `>`。论证:归一化只改**送进比较运算符的键**,不改运算符;而 G 内键序 ≡ 字符串序**且**平局分量取原串 ⇒ `<`/`<=`/`>` 的每一次判定结果逐位相同,平局的稳定排序落位也相同。**开闭区间语义是本次修改的不变量,不是待定选项。**

#### 3.1.5 零 LLM 验证命令(**顺序不可颠倒**)

```bash
cd D:\ZZL_cluade

# 步骤 1(先于任何改动)· 地基断言:G 内 54,303,831 对中 0 对与字符串序不一致
python scratchpad/iso_check2.py
#   不成立 ⇒ §3.1.6 的全部归并论证作废,整节规格作废,不许继续。

# 步骤 2(先于任何改动)· 捉基线。照 scripts/algebra_parity.py 的复放模式新建
#   scripts/date_strict_replay.py,对 3,209 行归档 plan(results/*.jsonl 里
#   plan 非空,**排除 s8_heldout***)落盘 scratchpad/date_baseline.jsonl:
#   每行 (file, question_id, uid, sha256(ev_join), sha256(derived_join),
#         sha256(reader_content)) + 该行当时的 QVF_CARDS_KEYED / QVF_ALGEBRA。
#   环境值不确定的行**标记并排除,不猜**。
python scripts/date_strict_replay.py --capture --out scratchpad/date_baseline.jsonl
python scripts/date_strict_replay.py --capture --out scratchpad/date_baseline2.jsonl
#   护栏:两次基线自身 sha 必须一致(排除字典序/集合序泄漏)。

# 步骤 3 · 打补丁,然后旗标关复放
QVF_DATE_STRICT=0 python scripts/date_strict_replay.py --against scratchpad/date_baseline.jsonl
#   判据:3,209/3,209 三个 sha256 全等。任一行不等 ⇒ 补丁在旗标关时不等价 ⇒ 回退重写。
#   "N/N 相同怎么测":靠的不是"跑两次拿到同一个数",而是同一份归档 plan 在
#   同一份归档卡片库上的**纯代码重放** —— execute_plan 无随机性、无网络、无
#   时间依赖,故 N/N 相同是可判定的确定性断言,不是统计结论。

# 步骤 4 · 旗标开(预注册判据见 §6.2,先写死再跑)
QVF_DATE_STRICT=2 python scripts/date_strict_replay.py --against scratchpad/date_baseline.jsonl
QVF_DATE_STRICT=1 python scripts/date_strict_replay.py --against scratchpad/date_baseline.jsonl
#   =1 只为把"重排序/离链"与"重定日"的贡献分开归因,不参与采纳决策。

# 步骤 5 · store_index 专项
python scratchpad/check_i3.py     # I3 失败 2->0、I2 失败 2->0;幽灵链位 215/216/218 -> 0
python scratchpad/demo_two.py     # bisect vs 线性扫描分歧 >=1 -> 0
```
另需一条独立断言(§3.1.6 最后一行的验证):对每个 `(uid, key)` 与探针日期集(链上每个日期 ±1 天 ∪ 链外前后各 1 点),断言 `KeyChain.asof_index(qd)` **≡** 冻结线性扫描。现状 ≥1 处分歧,修后必须 0 处。

#### 3.1.6 预估效果与依据

| 项 | 预估 | 依据 |
|---|---|---|
| 出现 diff 的归档行 | **≤ 655 / 3,209(20.41%)** | 真实 `_select_pool` 判定 |
| 幽灵链位 | v42 216 / v43 218 / keyed 215 → **0** | 旗标开后链上每条记录 `_rec_date ∈ G` ⇒ `_pdate` 必不为 `None` ⇒ 两套入链判据外延相同 |
| `store_index` I3 失败 | keyed 2 → **0** | `sort_key` 第一分量落回 G 内 ⇒ `_asof_dates` 单调 ⇒ `bisect` 前提成立 |
| `sorted(key=_rec_date)` 5 处(`cqa:378/380/420/615`、`algebra:278`) | **零行需改** | G 内字符串序 ≡ 日历序(0/54,303,831);`""` 只出现在随后被 `_chain` 丢弃的记录上,相对位置不可观测 |
| "取最后一个满足 `pd<=qd`"3 处(`cqa:581/671`、`algebra:368`) | **零行需改**,只加 assert | 链按日历日单调时 ≡ argmax;单调性由上一条保证 |
| `qvf/store_index.py` | **零代码改动**(仅文档 + assert) | 它从 `complex_query_arm` import `_rec_date`,自动继承 |

**"四条缺陷由咽喉点自动消解"是本节最重要的结构性主张,也是最该被攻击的一条。** §6.2 的 P1/P2 就是为攻击它设计的:若在 655 行之外出现 diff,或出现第四类 diff,该主张即被证伪。

---

### 3.2 第二节 · 算子层契约(线二 F2–F7)

缺陷证据的全库数字与最小可复现例见 §四(单独成节),本节只给补丁。

#### 3.2.1 R2-F4 · `QVF_TYPECHECK_DOMAIN` —— 类型检查覆盖索引域

**规则**:①`check_expr` 拒绝 `PICK.index == 0`、`index < -1`(只有 `-1` 合法)、`WINDOW.before_index/after_index <= 0`;②`WINDOW` 的 `*_index` 在缺 `*_slot` 且 `of` 非 `SELECT` 叶时无从自指,判非良构;③`_resolve_bound` 对**序数越界**返回 `(True, None, None)`("已声明但解析不出"),不再返回 `(False, None, None)`("该侧无界")。

`qvf_algebra.py:246-255`,锚串:`return True, _pdate(_rec_date(arec, mem_dates)), arec`(其后紧跟的 `return False, None, None`)

改后
```python
        if 1 <= index <= len(achain):
            arec = achain[index - 1]
            return True, _pdate(_rec_date(arec, mem_dates)), arec
        # QVF_TYPECHECK_DOMAIN=1:返回"已声明但解析不出",不再静默降级成
        # "该侧未设界" —— 后者会让一个双侧窗悄悄退化成单侧窗,聚合在比声明
        # 更大的范围上算完并照报 "This computed result IS the answer"
        # (归档 2 例:wikiP54010-Q105871142_s8cd / wikiP54014-Q2856385_s8cd,
        #  编译器给出 after_index=0)。MidExpr.before_index 的文档
        # (qvf_algebra.py:123-125)逐字为 "1-based ordinal position",而
        # check_expr 的 WINDOW 分支(:196-215)不检查索引域。
        # 旗标关时下面这一行逐字节等价于改前的 return False, None, None。
        return (True, None, None) if _TYPECHECK_DOMAIN else (False, None, None)
```
`check_expr` 的 WINDOW 分支(`:196-215`)末尾追加:
```python
        if _TYPECHECK_DOMAIN:
            for fld in ("before_index", "after_index"):
                v = getattr(e, fld, None)
                if isinstance(v, int) and not isinstance(v, bool) and v <= 0:
                    raise IllFormed(f"WINDOW.{fld}={v} out of domain (1-based)")
            for side in ("before", "after"):
                if getattr(e, side + "_index", None) is not None and \
                        getattr(e, side + "_slot", None) is None and \
                        getattr(e.of, "prim", "") != "SELECT":
                    raise IllFormed(
                        f"WINDOW {side}_index needs {side}_slot when 'of' is "
                        f"not a SELECT leaf (no slot to self-anchor on)")
```
`PICK` 分支(`:192-194`)同法加 `index == 0 or index < -1` 的拒绝。
**杀灭**:C2(2 例)、C4(2 例);并把 C3 的一部分从"静默丢界"升级为可被 F5 接住的显式失败。`compile_wellformed=False` 的明确拒收 +2 —— `complex_query_arm.py:897/:940` 已有接住路径,跑批不中断。

#### 3.2.2 R2-F5 · `QVF_OP_FAIL_LOUD` —— 空求值/界不可解析不得渲染成答案

**规则**:渲染前检查 ①`AGG.of` 的链是否为空,②是否有"已声明但解析不出"的窗界。任一成立则:证据包退回被开窗前的**基链**(让读者看见"这条链确实存在"),结论行只给 `UNRESOLVED: ...`,**不出现任何数字、不出现 `IS the answer`**。`count_changes` 在空链上不得返回 −1。

`qvf_algebra.py:668-671`,锚串:`". This computed result IS the answer; do not recount.")`

改后
```python
        # QVF_OP_FAIL_LOUD=1:空集合上的聚合不是答案。check_expr 对 AGG 返回
        # "Value",承诺该子式**指称一个 Value**;当 AGG.of 的链为空时返回的是
        # 空集上的聚合(count_elements->0、argmax_dur->{}),而本分支仍无条件
        # 加 "This computed result IS the answer",且证据包 0 行 —— 读者收到
        # 一个零证据的确定数字。缺陷证据:归档 104 个 expr:AGG 计划里 31 个
        # (29.8%)如此;其中 17 个的空集来自"已声明但解析不出的窗界"
        # (_resolve_bound :229-263 对值锚未命中返回 (True,None,None),
        #  _in_window :302-307 对 b_req=True,qd=None 让每条记录都落选,窗静默
        #  清空 —— "界找不到"与"区间里确实没有记录"被压成同一个 0),1 个报出
        # -1(count_changes on empty chain,:334-335 的 len(chain)-1)。
        # 最小例:repro.py --rules F4,F5 S8seen_alg wikiM003-Q106386024_s8wcb2。
        if _FAIL_LOUD and not (node.get("of") or {}).get("chain"):
            base = base_chain(node)
            ev = [_line(r, mem_dates) for r in base][:EVIDENCE_CAP]
            derived.append(
                "UNRESOLVED: the set of records this computation ranges over "
                "is empty, so no count/aggregate can be computed. State that "
                "the requested span cannot be resolved from memory; do NOT "
                "report a number.")
            return ev[:EVIDENCE_CAP], derived
        derived.append(
            f"Computed {node['fn']} over the dated records above: "
            + json.dumps(node["data"], ensure_ascii=False)
            + ". This computed result IS the answer; do not recount.")
```
界不可解析的分支同形(参考实现:`scratchpad/opaudit/fixes.py` 的 `wrap()` 里 `"F5"` 段,已在 1,463 行上跑通;文案须含**被丢的是哪一侧**)。`:334-335` 的 `count_changes` 在旗标开时对空链返回 `None` 并交本分支处理,不返回 −1。
**杀灭**:C1(46)、B1(46)、C3(17)、A1b(33)、B5(1)。

#### 3.2.3 R2-F2 + R2-F7 · `QVF_DUR_GRAN` / `QVF_DUR_TIE`

**规则**:`longest`/`argmax_dur` 把每个值的时长算成**区间** `[lo, hi]`(粗粒度端点按 `qvf.date_norm.span_bounds` 取上下界)。仅当所有端点为日粒度且区间退化为点时,才允许上报确定天数;否则上报区间,并且当 `∃v≠win: hi_v ≥ lo_win` 时明确宣布**在库存精度下不可判定**,禁止指名单一冠军。日粒度下若出现精确并列,必须披露并列(`winners` 已算出,不得只报 `winners[0]`)。

`complex_query_arm.py:702-708`,锚串:`f"Held longest (closed intervals only): {winners[0]} "`

改后(**外层嵌套遵守 §1.2-C6:set 判定在最外层**)
```python
        if _SLOT_CARD and card == "set":
            ...  # §3.3.4 的 set 分支:该问法在集合值属性上无定义
        elif per_value and (_DUR_GRAN or _DUR_TIE):
            # QVF_DUR_GRAN=1:粗粒度端点 -> 时长是区间不是点;区间重叠时
            # argmax 无定义。QVF_DUR_TIE=1:日粒度精确并列必须披露。
            # 缺陷证据:gen_wikistate_complex.parse_partial_date 的返回契约是
            # (date, note),note 是 "raw->normalized" 规约记号、文档写明"供
            # 写入 basis",而 _pdate(:345-350)用 [0] 把 note 丢掉,于是
            # 2019 / 2019-00-00 / 2019-05 被当成日精度参与日算术。归档 237 个
            # longest 计划里 128 个链含非日粒度端点却上报确定天数(E1),
            # 38 个的冠亚军可能天数区间重叠(E4),1 个精确三方并列被报成唯一
            # 冠军(E7:winners 已算出却只渲染 winners[0])。最小例
            # S5_418/wikiP108010-Q53284080_s5a:证据行显示 [2005-09]、
            # [2010-09](月粒度),结论行给 1826 天 —— 精度是凭空造的。
            lo, hi = _dur_bounds(chain, dates, values)
            win = max(lo, key=lambda k: lo[k] + hi[k])
            amb = [v for v in lo if v != win and hi[v] >= lo[win]]
            if amb and _DUR_GRAN:
                derived.append(
                    "Duration comparison is UNDECIDABLE at the stored date "
                    "precision: possible closed-interval day ranges per value "
                    "are " + json.dumps({k: [lo[k], hi[k]] for k in lo},
                                        ensure_ascii=False)
                    + ". Say which values are unresolved; do NOT name a "
                      "single longest value.")
            elif lo[win] != hi[win] and _DUR_GRAN:
                derived.append(
                    f"Held longest: {win} (possible closed-interval range "
                    f"{lo[win]}-{hi[win]} days; stored dates are coarser than "
                    f"day precision, so no exact day count can be given). "
                    "Possible ranges per value: "
                    + json.dumps({k: [lo[k], hi[k]] for k in lo},
                                 ensure_ascii=False) + ".")
            else:
                best = max(per_value.values())
                winners = [v for v, d in per_value.items() if d == best]
                if len(winners) > 1 and _DUR_TIE:
                    derived.append(
                        f"Longest is a TIE at {best} days between: "
                        + ", ".join(winners) + ". Closed days per value: "
                        + json.dumps(per_value, ensure_ascii=False)
                        + ". Report the tie; do NOT name a single value.")
                else:
                    derived.append(
                        f"Held longest (closed intervals only): {winners[0]} "
                        f"({best} days). Closed days per value: "
                        + json.dumps(per_value, ensure_ascii=False) + ".")
        elif per_value:
            ...  # 冻结原文六行逐字保留
```
`_dur_bounds` 为新模块级辅助(参考实现 `scratchpad/opaudit/fixes.py:dur_bounds`,已在 1,463 行上跑通),内部用 `qvf.date_norm.span_bounds`。`qvf_algebra.py:342-349`(`argmax_dur`)与 `:573-586`(`_render_chain_op` longest)同形改动。
**F7 单列的理由**:F2 的其余部分只在**粗粒度**下生效,而并列在全日粒度链上也会出现(E7 那 1 例 `wikiP108027-Q20829689_s8wa`:`{ESO:1461, MPI:1461, Open University:1461}` 三方精确并列,输出却是 `Held longest ...: European Southern Observatory (1461 days)`)。
**杀灭**:E1(128)、E4(38)、E7(1)、E5(潜伏)。

#### 3.2.4 R2-F3 · `QVF_ASOF_GRAN` —— 时点比较须粒度可判

**规则**:`ASOF`/`point_in_time`/`count_before`/`WINDOW` 界比较时,若任一候选记录的日期**不确定区间跨过被比较的日期**,该次定位在库存精度下不可判定;结论行必须声明这一点,且不得再带 `This IS the answer`。**不改 `gi` 的计算,不改 `Loc` 类型** —— 见 §5 决策 D3。

改哪:`complex_query_arm.py:668-684`(`point_in_time`)、`:714-723`(`count_before`)、`qvf_algebra.py:368-372`(ASOF 求 `gi`)、`:302-310`(`_in_window`)。
改法:在算出 `gi` 之后加旗标分支,用 `span_bounds` 取每条候选记录的 `[lo, hi]`,若 `∃r: lo_r <= qd <= hi_r 且 gran_r != "day"`,追加
```python
derived.append(
    "PRECISION WARNING: at least one stored date is only year/month precise "
    "and its possible range spans the date being compared, so this lookup is "
    "not determined by memory. Answer with the ambiguity stated, not a single "
    "definite value.")
```
并把该分支里的 `"This IS the answer."` 替换为 `"This is the best available reading, but see the precision warning."`。
另:`point_in_time` 现行 `:680-684` 的 `", unchanged until {dates[gi+1]}"` 在 set 链上是错的(下一次是**新增**,不是"改变")—— 该措辞由 §3.3.4 的 set 分支接管,本旗标不碰。
最小例:`S5_418/wikiP54003-Q26001185_s5c`(`count_before`, `date=2020-12-31`):链上 `[2020-00-00]` 是年粒度,真实区间 `[2020-01-01, 2020-12-31] ∋ 2020-12-31` ⇒ "是否早于 2020-12-31"未定,而冻结输出给 `2 different team value(s)` 的确定答案。另一例 `boundary_duel/wikiP108010-Q53284080_bswitch`:**查询日期本身**是 `2013-10-00`(月粒度)却被当日期用。
**杀灭**:E6(57)。

#### 3.2.5 R2-F6 · `QVF_EV_CAP_HONEST` —— 截断必须显式

**规则**:源链长度超 `EVIDENCE_CAP` 时,证据包末尾追加显式截断标记行;结论行不得再声称 `every one is listed above`,按年枚举时须标注枚举范围超出证据包。

改哪:`complex_query_arm.py:105`(常量旁加注释)、`:613-638`(tag 分支)、`:644`;`qvf_algebra.py:430-452`(`_render_tag`)。新增:
```python
def _cap_note(n_total: int) -> Optional[str]:
    """QVF_EV_CAP_HONEST=1:截断显式化。缺陷证据:EVIDENCE_CAP=12
    (complex_query_arm.py:105)在 8 处静默截断(ev[:EVIDENCE_CAP]),而
    tag_trend 的 by_year 结论行(:626-637)枚举**全部**命中项并指示
    "citing ONLY these items with their dates" —— 归档 115 个 tag_trend
    计划里 12 个的链 >12 条(最长 20),读者被要求引用它看不到的记录的日期。
    最小例 S7_220/chain002-4781d89c_s7a:链 20 条、证据 12 行、结论列 20 项。"""
    if not _EV_CAP_HONEST or n_total <= EVIDENCE_CAP:
        return None
    return (f"[evidence pack truncated: {n_total - EVIDENCE_CAP} of "
            f"{n_total} matching records are NOT shown above]")
```
并在 `:621-625` 把 `every one is listed above` 在旗标开时改为 `only {EVIDENCE_CAP} of {len(hits)} are listed above`。
**杀灭**:E2(12)。

#### 3.2.6 零 LLM 验证命令

```bash
cd D:\ZZL_cluade
# 基线(阶段 1 之前跑一次;阶段 1 与阶段 4 之后各重跑一次并如实登记新基线)
PYTHONIOENCODING=utf-8 python scratchpad/opaudit/census2.py            # 期望 245 违反
# 旗标关逐字节等价 + 爆炸半径
PYTHONIOENCODING=utf-8 python scratchpad/opaudit/blast.py              # 期望 1463/1463 等价
# 逐规则杀灭核验(每条单独开,不许只跑全开)
OPFIX=F4       python scratchpad/opaudit/census2.py   # C2/C4 -> 0,明确拒收 +2
OPFIX=F4,F5    python scratchpad/opaudit/census2.py   # C1/B1/C3/A1b/B5 -> 0
OPFIX=F1,F2    python scratchpad/opaudit/census2.py   # E1/E4/E7 -> 0
OPFIX=F1,F3    python scratchpad/opaudit/census2.py   # E6 -> 0
OPFIX=F6       python scratchpad/opaudit/census2.py   # E2 -> 0
OPFIX=F1,F2,F3,F4,F5,F6,F7 python scratchpad/opaudit/census2.py        # 期望 0
# 单例复现(每条修复至少留一个可粘贴的最小例)
python scratchpad/opaudit/repro.py --rules F1,F2 newdom_P26 wikiP26028-Q119041180_s5a
python scratchpad/opaudit/repro.py --rules F4,F5 S8seen_alg wikiM003-Q106386024_s8wcb2
python scratchpad/opaudit/repro.py --rules F1,F3 S5_418 wikiP54003-Q26001185_s5c
```
> `scratchpad/opaudit/fixes.py` 是 monkeypatch 形态的**规则级参考实现**,已在 1,463 行上跑通。实施时把它的逻辑搬进冻结文件的旗标分支,**不得**保留两份实现;搬完后 `OPFIX=...` 与 `QVF_*=1` 必须给出同一结果 —— 这是一条可跑的断言,建议写成 `scripts/opfix_parity.py`。

#### 3.2.7 预估效果与依据

| 项 | 预估 | 依据 |
|---|---|---|
| 违反行 | 245 → **0**(dev 0 / test 0 / heldout 0) | 七条规则全开后复放,同一套**未改动的**判据 |
| 输出改变行 | **245 / 1,463 = 16.7%**,与违反行数**完全相等** | 规则只碰违反行,零漂移 |
| 类型检查明确拒收 | **+2 行**(不计违反,属正确行为) | `compile_wellformed=False`,`:897/:940` 已有接住路径 |
| 旗标关等价 | **1,463 / 1,463** | `blast.py` 已核验 |
| ⚠️ 落在 heldout 的改变行 | **16 行** | 测准确率前必须先预注册,见 §6.4 |

---

### 3.3 第三节 · 分组键与打分(线三)

#### 3.3.1 R3-1 / R3-5 · 注释更正(阶段 0,纯注释,零行为风险)

**缺陷证据(逐字对照)。** `wt_qvf_prototype.py:538-541` 块注释与 `:574-581` 的代码/内联注释三方对照:

| | `:541` 块注释 | `:575-576` 内联注释 | `:581` 代码 |
|---|---|---|---|
| 关系边项 | **系数 2,主导** | "**仅作决胜**" | `min(rel, 3)`,上限 3 |
| 槽位命中项 | 系数 1 | "**主导**" | `4 * slot_hits`,无上限 |
| 对污染的假设 | "**污染卡与链无关系边**" | "**污染闲聊常有**(关系边)" | — |

⇒ 代码与内联注释一致;**块注释与代码权重方向相反,且两条注释对"污染卡有无关系边"的假设互相矛盾**。这是"两条注释打架",不是"注释与代码打架"。

**判定:代码对,`:541` 是残留散文。三条独立证据,全部与准确率无关:**
1. 内联注释给出了机制**因果**("累加型状态链不产生 replacement 边,反而污染闲聊常有"),而块注释给的是被它用"反而"明确转折否定的前提;代码实现了前者。
2. `git log -L 565,590:scripts/wt_qvf_prototype.py`:该文件整体在 `a0bca46` 一次入库,`comp_score` **入库即为现形**(`4*slot_hits + min(rel,3)`,含内联注释)⇒ **从未存在过 `2×rel + hits` 的实现版本**。
3. **`2×rel + hits` 在本系统的卡片上是退化的打分函数**:带关系边的卡片仅 5.3%–9.5%,**89.3%–93.6% 的分量内部关系边数恰为 0**(`wt_cards` 14,803/16,549 个分量为 0 边)。一个在九成输入上取常数的项不可能是作者设计的主导项;`min(rel, 3)` 的"决胜"定位才与实现自洽。

⇒ **修复 = 改注释,不改代码。** 改后文本(`wt_qvf_prototype.py:538-541`):
```python
        # 抗污染 v3:关系链连通分量。图:节点=全库卡片;边=关系链接 ∪ 槽位
        # 分组匹配(见 _slot_group)。组件得分见下方 comp_score:
        #   4×匹配查询槽位的卡数 + min(内部关系边数, 3)——槽位命中主导,
        #   关系边仅作决胜。
        # 【08-18 更正】本段原文曾写作"真实状态链的卡片被抽取器用
        # replacement/cessation 关系互相链接;污染卡与链无关系边""组件得分
        # = 2×内部关系边数 + 匹配查询槽位的卡数",与 comp_score 的实现权重
        # 方向相反,且与 comp_score 内联注释("累加型状态链不产生 replacement
        # 边,反而污染闲聊常有")的前提互相矛盾。判定依据(与准确率无关):
        #   ① git log -L 565,590 显示本文件整体在 a0bca46 一次入库,
        #      comp_score 入库即为 4×hits+min(rel,3),从未存在 2×rel 的实现;
        #   ② 实测关系边极稀疏 —— 带边卡片仅 5.3%-9.5%,89.3%-93.6% 的分量
        #      内部边数恰为 0(results/wt_cards 14,803/16,549)。以 rel 为
        #      无上限主导项的打分在九成输入上取常数,不具区分力,不可能是
        #      设计意图;min(rel,3) 的"决胜"定位才与实现自洽。
        # 因此更正的是本段散文,不是代码。
```

**R3-5**:`qvf_router.py:290` 的 `"""v3 同款分量深度:...` 改为 `"""v3 同精神分量深度(rel 项定义与 wt_qvf_prototype.py:578 不同:此处为出边表长度求和、含悬空目标,那里为分量内部边计数;实测差异 7/16,549 分量 = 0.04%,且被 min(rel,3) 吸收 —— 见 08-18 线三复算):...`。
**代码对齐(`QVF_SCORE_ALIGN`)本轮不实施**:两处只在存在**悬空目标**时数值不同(凡目标存在的边必被 union,两端必同分量),`wt_cards` 悬空 7/4,516 边、受影响分量 7/16,549 = 0.04%;`v43`/`keyed`/`newdom` 悬空 0。改它会改变 0.04% 分量的选择而收益不明。

**验证**:纯注释 ⇒ 字节级等价平凡成立。仍须 `python -c "import scripts.wt_qvf_prototype"` + `scripts/algebra_parity.py` 冒烟确认无语法/缩进破坏。

#### 3.3.2 R3-2 / R3-3 · `QVF_SLOT_STRICT` —— 分组谓词与匹配谓词分离

**缺陷证据。** `wt_qvf_prototype.py:465-474` 的 `_slot_match` 被用在两种**数学性质不同**的关系上:

| 角色 | 数学性质 | 调用点 |
|---|---|---|
| **R1 卡↔卡分组**(并查集 union) | **等价关系**,要求"同一属性",错并不可逆(传递闭包) | `wt_qvf_prototype.py:567`、`qvf_router.py:324` |
| **R2 查询槽位↔卡**(相关性/选池) | **相关性**,允许宽松(用户措辞 ≠ 抽取器措辞),错配代价小得多 | `wt_qvf_prototype.py:580,598`、`qvf_router.py:332,358`、`complex_query_arm.py:379`、`qvf/store_index.py:482` |

第三分支("共享词数 ≥ min(词数)−1")在 R1 上是错的、在 R2 上未必错。**本修复只动 R1。**

量化(按 uid 内不同槽位串两两;`wt_cards_s8_heldout` 排除):

| 卡片库 | 槽位串对总数 | 分支③命中 | 命中率 | **③占全部跨名合并** |
|---|---|---|---|---|
| `wt_cards` | 1,343,698 | 36,286 | 2.70% | **93.2%** |
| `wt_cards_v43` | 358,515 | 8,091 | 2.26% | 87.1% |
| `wt_cards_keyed` | 370,473 | 9,061 | 2.45% | 87.2% |

误并的**结构性质**:四库分支③的 55,797 个合并实例中,**(1,1) 形状(两侧各一私有词 = 替换 → 对立)占 31,808**,(2,1)+(1,2) 占 21,411,而"纯增词/纯换序"(= 特化或同一)仅 **340 = 0.61%**。最高频替换词对:`planned↔recent`(133)、`history↔plans`(93)、`event↔trip`(77)、`activity↔event`(76)、`cost↔provider`(30) —— 前 60 高频替换里仅 `attendance↔participation`(38) 一项可辩护为近义。
`wt_cards` 前 30 误并对中 **24 条为明确误并(80%)、6 条边界、0 条明确同属性**:`travel history‖travel plans`(69 uid,时体对立)、`education plans‖travel plans`(25,领域对立)、`fitness activity‖fitness goal`(20,事实 vs 目标)、`residence location‖work location`(12,**不同实体的地点**)……
**巨型分量病理**:`wt_cards` 上 **140/691 = 20.3% 的 uid**,其"最佳分量"已吞掉 ≥50% 的全库卡片(`:538-540` 注释宣称的"抗污染"在该库上名存实亡);换 (a) 规则后降至 2/691 = 0.3%。即使 `record_id` 无碰撞也如此(`v43` 碰撞率 0.5% 时仍有 1.2%)。

**修法选择的两条第一性原理(与准确率无关):**
> **P1(写入侧契约)**:`CATALOG_PROMPT` Rule 2(`:140`)逐字 "Use consistent slot names across records for the same attribute.";`CATALOG_PROMPT_V4` Rule 7(`:161-162`)逐字 "Records about the same real-world attribute must share the same slot_class." ⇒ **按系统自己的写入契约,"槽位名不同"本身就是"属性不同"的声明。** 读取侧凭"共享 1 个词"合并不同名,是在推翻自家契约。
> **P2(构词法)**:英语定语复合名词中**增词 = 特化**(`recent purchase` → `recent clothing purchase`,同属性更窄),**同位换词 = 对比**(`residence location` vs `work location`)。抽取器在两个名字里各放一个对方没有的词,等于**主动标注了一处对立**。⇒ 正确判据是"一个名字的词集 ⊆ 另一个",而非"共享词数 ≥ min−1"。

三种修法在 P1/P2 下的评分(四库 55,797 实例上实测保留率):

| 修法 | 规则 | 保留 | 精确性 | 判定 |
|---|---|---|---|---|
| **(a) 词集包含** | `a==b ∨ 子串 ∨ 词集包含` | **362(0.65%)** | **最高**:保留下来的正是纯特化/换序(`recent clothing purchase‖recent purchase`、`coffee bean preference‖coffee preference`、`planned road trip‖planned trip`) | **采纳** |
| (b) 核心词(最后一名词)相同 | 头名词相等 + ≥1 共享词 | 23,725(42.5%) | **低**:放行全部"同头对比"(`residence location‖work location`、`bedtime routine‖morning routine`) | 弃 |
| (c) 通用后缀黑名单 | 去掉通用词后共享词仍非空 | 35,556(63.7%) | **最低**:`travel` 不在黑名单 ⇒ `travel history‖travel plans` 照并 | 弃 |

**(b)/(c) 的共同致命点**:都以"哪些词是核心/通用"为参数,而该参数**无法从系统契约导出**,只能靠人挑词表 —— 那本身就是一条新的可调旋钮(正是耦合审计标为 `benchmark_specific` 的形态)。**(a) 是三者中唯一零参数、零词表的规则。**
**(a) 的反向误差**:唯一系统性失手是**同义替换**(两侧各一私有词但语义相同)。配套一个**显式同义对白名单,初始为空**,只允许写入能在写入侧契约里找到依据的对(实证同 `slot_class` 而 `slot` 不同者),每条附出处。**禁止以"加了哪些同义对准确率更高"填这张表。**

**改动 1 · `wt_qvf_prototype.py:474` 之后插入(锚串:`_slot_match` 函数体最后一行 `return len(aw & bw) >= max(1, min(len(aw), len(bw)) - 1) and bool(aw & bw)`)**

```python
# ── QVF_SLOT_STRICT:卡↔卡分组谓词与查询↔卡匹配谓词分离(默认 0 = 冻结)──
# 缺陷证据(results/QVF_system_reality_audit_20260817.md §1.2 + 08-18 线三复算,
# 详见 study_logs/QVF_repair_specs_20260818.md §3.3.2):
#   _slot_match 的第三分支"共享词数 >= min(词数)-1"被同时用于两种语义:
#     R1 卡↔卡并查集 union(:567 / qvf_router.py:324)—— 等价关系,错并不可逆;
#     R2 查询槽位↔卡选池(:580,:598 / qvf_router.py:332,358 /
#        complex_query_arm.py:379 / qvf/store_index.py:482)—— 相关性,宽松无害。
#   在 R1 上该分支占全部跨名合并的 93.2%(results/wt_cards:36,286/38,942),
#   四库 55,797 个合并实例中只有 340(0.61%)是"一名词集含另一名"的特化关系,
#   其余 99.4% 是双向私有词的对立对(planned↔recent 133、history↔plans 93、
#   event↔trip 77、cost↔provider 30、duration↔method 29 ...)。
#   后果:results/wt_cards 上 140/691(20.3%)的 uid 出现"单个分量吞掉 >=50%
#   全库",本函数上方 :538-540 注释宣称的"抗污染分量"在该库上名存实亡。
# 修法依据(与任何准确率无关,不看 gold):
#   ① 写入侧契约 CATALOG_PROMPT Rule 2(:140)"Use consistent slot names
#      across records for the same attribute" 与 V4 Rule 7(:161)"Records
#      about the same real-world attribute must share the same slot_class"
#      —— 按系统自己的契约,槽位名不同即属性不同;
#   ② 英语定语复合名词:增词=特化(同属性更窄),同位换词=对比(不同属性)。
#   故 R1 的正确判据是"一名的词集包含于另一名",而非容许双向私有词的
#   min-1 阈值。三种候选中只有本规则不含人挑词表参数。
# 预注册代价(08-18 离线复算,5,511 条归档聚焦,零 LLM):wt 臂占比
#   36.2%->27.1%(Config K),约 491 题(8.9pp)由 wt 改派 prompt 臂;键控卷
#   (wiki-P39/P108/P54/P551、newdom)逐卷 wt 计数完全不变(_keyed_depth 先
#   返回,不经本谓词);冲击全部落在无 slot_class 的旧库。判据见 §6.3。
_SLOT_STRICT = int(os.environ.get("QVF_SLOT_STRICT", "0") or 0)

# 同义槽位名白名单:仅收录能在写入侧契约里找到依据的对(如实证同 slot_class
# 而 slot 不同者),每条必须附出处。默认空 = 纯词集包含规则。
# 【禁止】以"加哪些对准确率更高"为依据填写本表。
_SLOT_SYNONYMS: frozenset = frozenset()


def _slot_same_attr(a: str, b: str) -> bool:
    """卡↔卡分组用的等价谓词:归一相等 ∨ 归一子串 ∨ 词集包含 ∨ 白名单同义。
    与 _slot_match 的差别仅在于去掉 min-1 词重叠分支(容许双向私有词)。"""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    sa, sb = set(a.split()), set(b.split())
    if sa <= sb or sb <= sa:
        return True
    return (frozenset((a, b)) in _SLOT_SYNONYMS
            or frozenset((b, a)) in _SLOT_SYNONYMS)


def _slot_group(a: str, b: str) -> bool:
    """R1 分组入口:旗标关时逐字调用 _slot_match(冻结行为逐字节等价)。"""
    return _slot_same_attr(a, b) if _SLOT_STRICT else _slot_match(a, b)
```

**改动 2 · `wt_qvf_prototype.py:565-568`**(锚串:`if _slot_match(cards[i].get("slot", ""), cards[j].get("slot", "")):`)
```python
                # R1 分组(等价关系):QVF_SLOT_STRICT 关时 == _slot_match
                if _slot_group(cards[i].get("slot", ""), cards[j].get("slot", "")):
                    union(ids[i], ids[j])
```
`:580` 与 `:598` 的 `_slot_match`(R2)**一字不动**。

**改动 3 · `qvf_router.py:25-26` import 加 `_slot_group`;`:322-325`** (锚串:`if _slot_match(recs[i].get("slot", ""), recs[j].get("slot", "")):`)
```python
            # R1 分组(等价关系);R2 的 hits()/direct_idx 仍用 _slot_match
            if _slot_group(recs[i].get("slot", ""), recs[j].get("slot", "")):
                union(i, j)
```
`:332` 与 `:358`(R2)**一字不动**。`scripts/open_slot.py:72-79` 的 `_str_match` 服务 slot→slot_class 匹配(R2 性质)、`qvf/store_index.py:482` 是 R2 回退扫描,**都不动**。

**【必答】修严后会不会让更多题降级?会,幅度大,这是本条修复的主要代价。**
方法:读 `results/router_focus_cache.json` 的 5,742 条归档聚焦(只读 `focus_slot/scope/presupposed`,**不读 `result`/`picked_arm`**),配 uid 得 5,511 条可复算题,离线重算 `chain_depth` + `route`/`route_v2`。

| 配置 | cur | **(a)** | (b) | (c) |
|---|---|---|---|---|
| Config F(冻结 v1.2,`QVF_ROUTER_KEYS=0`)wt 占比 | 28.2%(1556) | **18.3%(1011)** | 18.3% | 23.9% |
| Config K(`QVF_ROUTER_KEYS=1`)wt 占比 | 36.2%(1993) | **27.1%(1491)** | 26.9% | 32.3% |

迁移方向 **100% 是 wt→rt**,无一题 wt→direct(`direct` 由 `scope=="unclear" and not presupposed` 前置决定,与链深无关,恒 376 题)。开 `QVF_GATE_V2=1` 时降级落到 **prompt 臂**:prompt 49.6%(2731)→ **58.4%(3219)**、wt 35.9%(1976)→ **26.9%(1485)**。
**若 R1+R2 都修严**(不做角色拆分):wt 再多掉 135/139 题,且这部分损失来自 R2(查询措辞容错),语义上不该修 ⇒ **角色拆分不是可选优化,是必须项。**
逐卷:**键控库完全免疫**(P39/P39-ext/P108-w2/P108-ext/P54-w2/P54-ext/P551 在 Config K 下 wt 计数 cur 与 (a) **逐卷完全相同**,因为 `_keyed_depth` 先返回、根本不走 `_slot_match`);冲击全落在无 `slot_class` 的旧库:`stale-150` wt 67→1、`LME-KU` 16→0、`LME-TR` 43→6、`LoCoMo-full` 437→72。
**这个分布本身是一条独立的诚实结论**:"链深"信号在无键控库上,其数值主要由分支③的模糊合并制造,而不是由真实的状态更替制造。修严让这些库的链深回落到真实形态(多为二态/事件流),路由改派 prompt 臂 —— 按 `qvf_router.py:398` 自己的注释("整库皆浅(STALE 二态/LME 事件流)才值得改派提示词臂"),**这正是 GATE_V2 设计时想要的行为**。

**零 LLM 验证**:
```bash
# 1. 旗标关等价(硬护栏)
QVF_ROUTER_KEYS=1 QVF_GATE_V2=1 QVF_CARDS_KEYED=results/wt_cards_newdom \
  python scripts/router_offline_ab.py --routes results/newdom_routes_P26.jsonl ...   # 逐题 0 分歧
QVF_CARDS_KEYED=results/wt_cards_v42 python scripts/algebra_parity.py \
  --rows results/wsc_s5_test_v42.jsonl --data data/wikistate_full_P108.json ... --name s5
# 新增穷举断言:五库全 uid,_slot_group == _slot_match 逐对返回值相同(~2.5M 对)
# 2. 旗标开的机制断言(全部预注册为"必须成立",不涉准确率)
#   - 分量数单调不减,且每个分量是修严前某分量的子集(并查集细化,逐 uid 断言)
#   - 键控卷逐题 keyed_depth 与归档 routes 的 keyed_depth 字段**逐题相等**
#   - "最大分量占全库 >=50%" 的 uid 数:wt_cards 140 -> <=5
#   - 路由分布与上表数字**逐题一致**(line3_route_shift.py 为参考实现,
#     实施后应移入 scripts/ 作为回归器)
```

#### 3.3.3 R3-4 · `QVF_SLOT_CARD` —— 11 算子消费 `slot_cardinality`

**缺陷证据。** 分布:`wt_cards` 65,774 卡中 `single` 40,004(60.8%)/ **`set` 25,689(39.1%)** / `unknown` 81 / 缺失 0;v42/v43/keyed/newdom 同形(`set` 36.3%–40.7%)。**约四成卡片自报 `set`。**
消费现状(`grep -rn slot_cardinality scripts/ qvf/`,排除 external):

- **写入侧已消费**:`scripts/write_persession.py:279-283` `_cardinality_for_group()` 组内多数票;`:296` 文档逐字"set 组不连边(值并存)"。
- **另一条读取路径已消费**:`scripts/run_decisive_stale.py:1248-1255`,注释逐字 "SET-valued slots (interests, hobbies) are excluded from the trigger: their values COEXIST, and latest-wins adjudication there is a category error"。
- **11 算子主读取路径 0 次读取**:`complex_query_arm.py` / `qvf_router.py` / `qvf/store_index.py` / `qvf_algebra.py` 全文该字段名出现 **0 次**。

⇒ **内在矛盾成立且有明确内部先例**:同一仓库的写入侧和一条旧读取路径都按"set 值并存"处理,主读取路径却对四成卡片按单值链裁决。**语义不需要凭空发明,只需把已有先例接进 11 算子。**
(注:`qvf/engine_bridge.py:152` 的 schema 是 `Literal["single","set","unknown"]`,而 `scripts/write_persession.py:87` 收紧为 `Literal["single","set"]`,两处并存 ⇒ 消费者必须处理三值 + 缺失四种情况。)

**语义设计的第一性原理。** `complex_query_arm.py:224-228` `COMPILE_PROMPT_SPEC` 逐字定义 `chain(slot) = <(v_1,t_1),...,(v_m,t_m)>`,`v_i` 在**右开区间** `[t_i, t_{i+1})` 内 in force。**右开区间语义预设了排他性** —— `v_i` 一到 `t_{i+1}` 就失效。对 `slot_cardinality=set` 的属性(兴趣、访问过的博物馆、拥有的设备),**这个预设是假的**:`t_{i+1}` 加入 `v_{i+1}` 不使 `v_i` 失效。
⇒ **凡语义依赖"区间/转移"的算子,在 set 链上没有定义;凡只依赖"断言事件序"的算子仍有定义。**

| 算子 | `single`(不动) | **`set` 语义** | 理由 |
|---|---|---|---|
| `current` | 末值 + "since t_m" | **成员全集** `S(now) = {v : t_v ≤ now} \ {已 cessation}`,渲染"当前 X 包含 A、B、C(分别自 …)" | 只报最近提及的成员,等于**断言其余成员已失效** —— 凭"最近被提到"推出"其他已不成立"是无据推断。先例 `run_decisive_stale.py:1251-1255` |
| `point_in_time` | 末个 `date ≤ qd` 的值 | **`S(qd)`** | 同上,窗口截到 `qd`。现行 `:680-684` 的 `", unchanged until ..."` 对 set 是错的(下一次是新增) |
| `trajectory` | `v1 -> v2 -> ...` | **累积事件序**:"t1 加入 A;t2 加入 B;t3 移除 A",**禁用 `->`** | `->` 是替换算符;set 链上只有 `+v` / `−v` 事件 |
| `count_changes` | `m-1` | **无定义 → 显式失败闭合**:不给整数,给"该属性为集合值,'变了几次'无定义;期间累计新增 N、移除 M" | `:240` 逐字定义为 "the number of transitions";set 链没有 transition。给一个数就是把"新增次数"冒充"变更次数"。**"m−1 还是 m"这个问题本身没有正确答案 —— 正确动作是不回答** |
| `longest` | 闭区间时长 argmax | **无定义 → 显式失败闭合** | `:246` 逐字 "argmax_v of total closed-interval duration",闭区间由排他性定义。强行按"加入到 cessation"算则**最早加入者恒胜**(多数成员无 cessation ⇒ 区间到 now),结果与内容无关 —— 这个退化本身就是"算子不适用"的证明 |
| `first_last` | 首值 + 末值 | **有定义**,仅改措辞:`"First X added: A (t1); most recently added: C (t3)"`(去掉 `since`) | 只问断言事件的首末,不预设排他性;但 `:726-727` 的 `since` 暗示"至今且唯一",对 set 是错的措辞 |
| `count_before` | date 前不同值数 | **有定义**,措辞改 `"N member(s)"` | 只数不同值,不数转移 |
| `premise_check` | 前置值非末值即判 OUTDATED | **成员身份不因有更晚成员而失效**:仅当该值带显式 `temporal_relation ∈ {cessation, contradiction}`(或有指向它的 cessation 边)才判过期,否则输出"该前置值仍是当前集合的成员" | **本条风险最高**:现行代码对任何非末位命中的值发 `"IMPORTANT: ... is OUTDATED"` 强指令,对 set 属性就是凭时间顺序制造一条虚假纠正,并被 `READER_SYSTEM`(`wt_qvf_prototype.py:455-456` 逐字 "any bracketed analysis notes among them are authoritative conclusions you should follow")钉成权威结论 |
| `tag_filter`/`tag_trend` | — | **不受影响**(不建链,走 `_tagged()`) | 标签与槽位链正交 |
| `join_at_change` | 锚变更日 | 锚为 set 时"变到 V 的时刻" = V 的**加入日**;结论行写"加入"而非"变更" | 加入事件有明确日期,join 有定义;只是措辞不得暗示替换 |

**组内基数不一致**:实测 **600/5,511 题(10.9%)** 的选池同时含 `set` 与 `single` 卡。处置**取多数票**,逐字复用先例 `write_persession.py:279-283`(`single if n_single >= n_set else "set"`,平票偏 `single` = 偏冻结行为);`unknown` 与缺失一律计入 `single` 侧。

**落在 set 链上的题量(只数题,不看答案;选池口径逐字复刻 `_select_pool_frozen`,n=5,511)**:

| 池的基数多数票 | 题数 | 占比 |
|---|---|---|
| 空池 | 2,509 | 45.5% |
| `single` | 1,503 | 27.3% |
| `single` + 带日期不同值 ≥2 | 940 | 17.1% |
| **`set`** | 456 | 8.3% |
| **`set` + 带日期不同值 ≥2** | **81** | **1.5%** |
| `unknown`(±multi) | 22 | 0.4% |
| (交叉)池内 `set`/`single` 混杂 | **600** | **10.9%** |

⇒ set 多数池共 **537 题(9.7%)**;其中"单值裁决真会开火"的是 **81 题(1.5%)**。逐卷:`LoCoMo-full` 354(multi 42)、`LoCoMo` 60(8)、`LME-TR` 43(9)、`confirm-228` 27(10)、`chain-212` 14(5)、`stale-150`/`STALE-full` 14(3)、`LME-KU` 7(1)、`wiki-P39` 4(0)、**其余 wiki 卷全 0**。
**规模判断(诚实版)**:这不是一条大幅提分的修复,是一条**正确性修复**。价值在 (i) 81 题上消除"制造自信错答"的机制(`premise_check`/`count_changes`/`longest` 三个算子),(ii) 10.9% 混杂池暴露的槽位分类噪声可被显式记录。**wiki 系列几乎不受影响,因此这条修复的效果不该以 S5/S6 榜面变化来评判。**

#### 3.3.4 R3-4 的补丁

**旗标块**(加在 §3.1.3 补丁 1-A 的 `_SLOT_CARD` 占位处,注释全文如下,**不得省略**):
```python
# QVF_SLOT_CARD=1:读取侧消费 slot_cardinality(默认 0 = 冻结,输出逐字节不变)。
#   缺陷证据(08-18 线三复算):该字段 qvf/engine_bridge.py:152 起即在 schema
#   (Literal["single","set","unknown"]),写入侧 scripts/write_persession.py
#   :279-283 已按多数票消费、:296 文档逐字"set 组不连边(值并存)",另一条读取
#   路径 scripts/run_decisive_stale.py:1248-1255 也已消费并逐字写明"SET-valued
#   slots ... their values COEXIST, and latest-wins adjudication there is a
#   category error";但本文件(11 算子主读取路径)与 scripts/qvf_router.py 全文
#   0 次读取该字段。实测四成卡片自报 set(results/wt_cards 25,689/65,774 =
#   39.1%),归档 5,511 题中 537 题(9.7%)选池为 set 多数,其中 81 题(1.5%)池内
#   带日期不同值 >=2 —— 即现行单值链裁决会在这 81 题上把并存成员当成状态更替。
#   另有 600 题(10.9%)选池 set/single 混杂。
#   语义依据(第一性原理,不看 gold):COMPILE_PROMPT_SPEC(:224-228)把 chain 的
#   每个值定义在右开区间 [t_i,t_{i+1}) 内 in force —— 该区间语义预设排他性,
#   对集合值属性为假。故依赖区间/转移的算子(count_changes:240 定义为 m-1 个
#   transition、longest:246 定义为闭区间时长 argmax)在 set 链上【无定义】,
#   只依赖断言事件序的算子(first_last / count_before)仍有定义。
#   =1:current/point_in_time 给成员集合;trajectory 渲染为加入/移除事件(禁用
#      "->");first_last/count_before 仅改措辞;premise_check 不再仅凭时序把
#      成员判 OUTDATED(需显式 cessation/contradiction);count_changes/longest
#      输出"集合值属性上该问法无定义"的结论行,不给整数。
#   =2:在 =1 之上,count_changes/longest 遇 set 链改为空 derived + 交
#      QVF_FAIL_CLOSED 显式降级(不猜)。
#   组内基数取多数票,平票偏 single;unknown/缺失计入 single 侧 —— 与先例
#   scripts/write_persession.py:279-283 逐字同款(偏向冻结行为)。
#   ⚠ QVF_ALGEBRA=1 时本旗标不生效(qvf_algebra 重绑 execute_plan),两者同开
#     会让同一集合值属性在两臂上语义不同、结果不可归因 ⇒ 见 §2.3 的启动拒跑。
_SLOT_CARD = int(os.environ.get("QVF_SLOT_CARD", "0") or 0)
```

**新增纯函数**(插在 `:435` `_chain` 之后、`:438` `_label` 之前):
```python
def _pool_cardinality(pool: List[dict]) -> str:
    """选池的基数多数票(与 scripts/write_persession.py:279-283 逐字同款:
    平票偏 single;unknown/缺失计入 single 侧)。"""
    n_single = sum(1 for r in pool
                   if (r.get("slot_cardinality") or "single") != "set")
    n_set = len(pool) - n_single
    return "single" if n_single >= n_set else "set"


def _ceased(rec: dict) -> bool:
    return str(rec.get("temporal_relation", "")) in ("cessation",)
```

**分支改法**:在 `:649` 之后取一次 `card = _pool_cardinality(chain) if _SLOT_CARD else "single"`。此后每个算子分支以 `if _SLOT_CARD and card == "set":` 起,`else` 保留原代码逐字不动 ⇒ **旗标关时 `card` 恒为 `"single"`,走原分支,逐字节等价**。

`current` / `premise_check`(`:653-667`)改后:
```python
    if op in ("current", "premise_check"):
        if card == "set":
            live = [(str(r.get("value", "")), _rec_date(r, mem_dates))
                    for r in chain if not _ceased(r)]
            derived.append(
                f"The user's {label} is a SET-valued attribute; current "
                f"members: "
                + "; ".join(f"{v} (since {d})" for v, d in live) + ".")
        else:
            derived.append(f"The user's current {label} is {values[-1]} "
                           f"(since {dates[-1]}).")
        pv = _norm(plan.get("presupposed") or "")
        if op == "premise_check" and pv:
            stale = next(
                (r for r in chain[:-1]
                 if pv in _norm(r.get("value", ""))
                 or _norm(r.get("value", "")) in pv), None)
            if stale is not None and card == "set" and not _ceased(stale):
                # set 成员并存:更晚的成员不使更早的成员失效。判过期需显式
                # cessation/contradiction(先例 run_decisive_stale.py:1248-1255)。
                derived.append(
                    f"The presupposed {stale.get('value', '')} is still one "
                    f"of the user's {label} members (this attribute holds "
                    f"multiple values at once); the premise is NOT stale.")
            elif stale is not None:
                derived.append(
                    f"IMPORTANT: the message presupposes "
                    f"{stale.get('value', '')}, which is OUTDATED — the "
                    f"user's current {label} is {values[-1]}. Correct this "
                    f"premise before helping.")
```
`count_changes`(`:689-693`)改后:
```python
    elif op == "count_changes":
        if card == "set":
            adds = len(chain)
            drops = sum(1 for r in chain if _ceased(r))
            if _SLOT_CARD >= 2:
                derived.append("")   # 交 QVF_FAIL_CLOSED 显式降级
            else:
                derived.append(
                    f"{label} is a SET-valued attribute (values coexist), so "
                    f"'how many times it changed' has no defined answer for "
                    f"it: {adds} member(s) were added and {drops} removed "
                    f"between {dates[0]} and {dates[-1]}.")
        else:
            n = len(chain) - 1
            derived.append(...)   # 原文逐字
```
`point_in_time`(`:668-684`)、`trajectory`(`:685-688`)、`longest`(`:694-713`,**外层嵌套见 §1.2-C6**)、`count_before`(`:714-723`)、`first_last`(`:724-727`)依 §3.3.3 的表同法加前置分支,`else` 保原文。

**零 LLM 验证**:
```bash
# 1. 旗标关等价(硬)
QVF_SLOT_CARD=0 python scripts/algebra_parity.py ...      # S5 全量 314 + S6 30 + S7 切片 50
QVF_SLOT_CARD=0 python scripts/store_index_equiv.py ...   # 逐字节
# 新增断言:对既有 results/wsc_s5_*/wsc_s7_* 的全部 (uid, plan),
#   execute_plan 的 ev + derived 逐字节相同
# 2. 旗标开的机制断言(可预注册为"必须成立",不涉准确率)
#   - **single 多数池的题:diff 必须恒为 0**(定义域承诺:只动 set 链)。
#     按 §3.3.3 口径应有 4,443 题 + 2,509 空池题零漂移
#   - 有 diff 的题数 = 537 ± 键控口径差,且逐题 _pool_cardinality == "set"
#   - premise_check 上被撤销的 OUTDATED 强指令条数可枚举,逐条附 record_id +
#     source_span(供人工抽检"该值是否真的仍是成员" —— **该抽检只看卡片原文,
#     不看题目答案**)
#   - count_changes/longest 的 set 分支不输出任何整数(正则断言 derived 行)
```

---

### 3.4 第四节 · 溯源修复(线四)

#### 3.4.1 缺陷证据与判决

**判决:猜想被证实。** `14.98%` 的"指错记忆"卡片中,**98.2% 可机械唯一定家**(kufix 925/942),其中 **85.3% 的修复对 `_rec_date` 零影响**(789/925)。**修复优于剔除**:`QVF_CARD_VERIFY_SPAN=2` 在 LME-KU 上丢掉 1,767 卡(28.26%),修复后应丢 799 卡(12.78%),**净救回 968 卡 = 库的 15.48%**。

五档分类(比原审计的四档多拆一档):

| 档 | 判据 | `wt_cards_kufix`(6,253) | `wt_cards_v42`(22,339) |
|---|---|---|---|
| T1 严格通过 | span ∈ text[声明 id] | 4,486 = **71.74%** | 20,179 = **90.33%** |
| T2 剥说话人标签后通过 | 指针对,span 文本错 | 49 = **0.78%** | 0 |
| **T2b 仅归一化后通过**(新拆) | 只在 NFKC+casefold+空白折叠+弯引号统一下匹配 | 24 = **0.38%** | 199 = **0.89%** |
| T3 库内指错 | 精确/剥标签/归一化能在同 uid 别处找到 | 942 = **15.06%** | 390 = **1.75%** |
| T4 精确找不到 | 改写/编造 | 752 = **12.03%** | 1,571 = **7.03%** |

T2b 是从原审计"全库找不到"里拆出来的:**24 条 kufix / 199 条 v42 其实是格式伪违约**,声明的指针没错,只有排版差异。**本规格不修这一档**(要改 span 文本,而"哪种归一化才是规范形式"无契约依据 —— Rule 1 只说 VERBATIM),但把它从"编造"里拆出来,让 `VERIFY_SPAN=2` 的剔除数字诚实。

T3 内部三档:

| 档 | kufix | v42 |
|---|---|---|
| **唯一命中(可安全修复)** | 925/942 = **98.20%** | 381/390 = **97.69%** |
| ├ 精确匹配定家 | 912 | 367 |
| ├ 剥标签后精确定家 | 7 | 0 |
| └ 仅归一化定家(**本规格拒绝定家**) | 6 | 14 |
| **多处命中(需决策规则)** | 17 = 1.80% | 9 = 2.31% |
| **修复后会改变回退日期** | 136/925 = 14.70% | 52/381 = 13.65% |
| ├ 悬空指针 → 获得日期 | 7 | 3 |
| ├ 日期平移 | 129 | 49 |
| └ **丢失日期** | **0** | **0** |
| **日期安全** | 789/925 = **85.30%** | 329/381 = 86.35% |

**日期安全率这么高是机制,不是巧合**:LME-KU 的 memory 粒度是**单轮**,同一 `sN` 下所有轮共享一个 `session_date`;而 925 条唯一命中中 **746(80.6%)落在同会话不同轮**(轮次差 Top3:`+2` 322 / `+1` 100 / `+4` 94),`_rec_date` 只看会话日期 ⇒ 修复对日期无影响。主流失效模式是**"引对了会话、指错了轮"**。
**重排上界**(仅针对 136 条会改日期的):无同槽位同伴 22 / 有同伴但一个都没跨过 59 / **跨过 ≥1 个同伴 55 = 全库 0.88%**。
**批次可见性**:按 `write_phase:316-325` 的字符预算规则重建批次边界,919 条精确唯一命中中 **915(99.6%)重挂目标在本批内**,**4 条(0.4%)跨批**(抽取器没看见过);另有 **9 条原声明指针本来就跨批**(D4 证据)。分批可复现的 uid 74/78。

**D3 实例**(`results/wt_cards_kufix/0977f2af.json`,`0977f2af/s3#r9`):
```
span  : 'user: Now tell me what I should tell this manager, like what does he want to hear as to wh…'
memory: 'user: Perfect - Now tell me what I should tell this manager, like what does he want to hea…'
```
模型截掉了 `Perfect - `,却把轮次开头的 `user: ` 标签搬到了截取点前面。剥掉标签后**是**声明处的逐字子串 —— 声明的指针本来就是对的。

#### 3.4.2 歧义裁定(依据全是溯源语义,不是准确率)

**Q1 多处命中 → 拒绝修复**,不取最早/最晚/最接近 `stated_date`。
`source_memory_id` 的语义是"这句话是从哪条 memory 里抄来的",卡片本身**不携带**该信息;当 span 在多条 memory 里逐字出现时,这个问题在证据上**无解**。
- "最接近 `stated_date`":用卡片自己的日期主张挑选支持该主张的证据,再让该证据回头确认那个日期 —— **循环论证**,正是本轮禁止的自证。
- "最早/最晚":把数据集的呈现顺序当成溯源事实,无依据。
- 正确工程行为:**标注不可判定并保持违约态**,去留交给 `VERIFY_SPAN`。
多处命中的实际长相(证实"不可判定"不是空谈):`'I just got back from'`(v42,4 家,**4 个不同日期** `2025-02-14/03-18/06-09/09-03`)、`'Dell XPS 13'`(3 家)、`'My 9-year-old'`(2 家) —— 短、通用、库内重复的片段,任何 tie-break 都是编造。代价:kufix 17 条(0.27%)、v42 9 条(0.04%)。

**Q2 剥前缀那 0.78% → 一并处理,且优先于重挂。**
依据是**最小改动原则**加**契约后置条件可验证**:数据集里每条 memory 文本本身以 `user: `/`assistant: ` 开头,因此一个**不在轮次开头**却带该标签的 span,其标签必然是模型自加的、不属于被引文本。剥掉后可机械验证为声明处的逐字子串 ⇒ 契约成立、指针不动、`_rec_date` 零影响、`extra_ids`/`drop_ids` 零影响。
顺序必须是"先试声明处剥标签,再考虑重挂":实测 kufix 有 **1 条**卡片,其 span 在别处精确出现、而声明处只在归一化下匹配 —— 若先重挂就会把一条本来指对的卡片挂走。

**Q3 仅归一化匹配(T2b 24 + T3-norm 6)→ 不修,只重新分类。** 归一化匹配**给不出"逐字连续子串"这个契约后置条件**。

#### 3.4.3 连带效应清单(**任务书前提必须纠正:"日期中性" ≠ "下游中性"**)

改 `source_memory_id` 会波及:

| 位置 | 效应 | 被"日期中性"守卫覆盖? |
|---|---|---|
| `wt_qvf_prototype.py:477-478` `_rec_date` | `stated_date` 为空时回退会话日期 | ✅(守卫的正是这一条) |
| `:599` / `:600` / `:611` / `:613` / `:645` | 链的顺序 / 链的**成员**(7 条悬空指针卡从"被踢出"变成"进链")/ 谁是当前态 / 时点裁决 / 谁进 `drop_ids` | ✅ |
| **`:623` / `:635` / `:640` `extra_ids.append(...)`** | **强制注入读者上下文的是哪条 memory 文本** | ❌ **否** |
| **`:646` `drop_ids.add(...)`** | **从读者上下文里删掉的是哪条 memory 文本** | ❌ **否** |
| `complex_query_arm.py:340-342` `_rec_date` | 编译臂同一日期回退 | ✅ |
| **`complex_query_arm.py:467-490` `_hygiene_pool`** | 去重键是 `source_memory_id`,"同一来源会话只留一张卡"。移动指针会改变**哪些卡被合并掉** ⇒ 直接影响 `count_changes`/`count_before`/`first_last`/`longest` 四个算子的计数 | ❌ **否** |
| `qvf/store_index.py:163-168` `sort_key` | 第一分量是 `_rec_date` | ✅ |
| **`scripts/write_persession.py:227-240` `_record_id()`** | `record_id = sha256(… source_memory_id, source_span …)`,是**内容派生哈希**;事后改这两个字段会让 `record_id` 与内容脱钩,并使 `relation_target_record_ids`(`:333-349` 依 `record_id` 连边)全部悬空 | ❌ **禁止运行**(守卫 G6) |
| **`scripts/write_persession.py:310-315` `stated_date_effective`** | 逐会话库在**写入时**把日期回退烧进卡片;事后改指针不会更新它 ⇒ 卡片日期与其指针互相矛盾(新的 internal_inconsistency) | ❌ **禁止运行** |

改 `source_span`(仅 T2 剥标签):`read_phase` **零效应**(全程不读 `source_span`,已 grep 确认该文件里它只出现在写入侧校验块 `:379-390`);`complex_query_arm.py:442-448` `_line()` 引文行去掉一个假的 `user: `(这是**修正**);`qvf/store_index.py:149-159` `content_fingerprint` 含 `source_span`,同日期平局的**次级排序**会变。影响面:kufix 仅 3 个 uid、v42 **0 个 uid**。

> **必须写进注释的结论**:L2 的"日期中性"只保证**排序/时点**不变,**不保证读者上下文不变**。kufix 上 784 条日期中性修复**全部**改变 `extra_ids`/`drop_ids` 命中的轮次(错指落点 80.6% 是同会话**不同轮**)。因此 L2 不是"零风险",而是"零日期风险";端到端行为变化必须实测,不能推定。

> **⚠️ 本文档新增的一条(§1.2-C2)**:线一落地后,`bool(stated_date)` 不再等价于"`_rec_date` 不看指针"(违约的 `stated_date` 会回落会话日期,指针又变重要)。因此 `repair_spans` 的 `date_neutral` **必须**改为比较 `_rec_date` 的实际返回值:
> ```python
> # 与 QVF_DATE_STRICT 的交互(见 §1.2-C2):旗标开时违约 stated_date 会被判
> # 缺失并回落会话日期,于是"stated_date 非空 ⇒ 指针无关"不再成立。故日期中性
> # 判据不得用 bool(stated_date),必须比较 _rec_date 在新旧指针下的实际返回值。
> old_d = _rec_date_like(rec, declared, mem_dates)
> new_d = _rec_date_like(rec, new, mem_dates)
> date_neutral = (old_d == new_d)
> ```
> 其中 `_rec_date_like(rec, mid, mem_dates)` = `qvf.date_norm` 校验后的 `stated_date` 或 `mem_dates.get(mid, "")`,与读取侧 `_rec_date` 同口径。**这条不修,线四 L2 的日期中性承诺在线一落地后即失效。**

#### 3.4.4 新文件 `qvf/span_repair.py`

模块 docstring 必须含:①建卡契约 Rule 1 的出处(`wt_qvf_prototype.py:139`、`write_persession.py:176`)与"建卡路径上无一行校验"的事实;②五档分类的实测数字(见 §3.4.1);③七条设计不变量;④"多处命中为何拒绝修复"的溯源语义论证(见 §3.4.2-Q1)。

七条不变量(**全部机械可验,不依赖任何答案/gold**):

| # | 不变量 | 作用 |
|---|---|---|
| **I1** | **后置条件**:被改写的记录改完后 `source_span` 必须是 `texts[source_memory_id]` 的逐字连续子串;不成立则整条**回滚** | 本模块**永不产出违约卡片** |
| **I2** | **最小改动**:先试"声明处仍对"(剥说话人标签),只有声明处在精确匹配下彻底不成立时才动指针 | 实测 kufix 有 1 条依赖这个顺序才不被挂走 |
| **I3** | **唯一性**:指针只在全 uid 历史中**恰好一条** memory 精确包含该 span 时移动 | 多处命中拒修 |
| **I4** | **只用精确匹配定家**:归一化/模糊匹配给不出 I1 的后置条件,只用于审计分档 | T2b/T3-norm 不修 |
| **I5** | **因果可见性**:抽取器一次只看见自己那批 memory,不可能从批外引用;提供批次映射时跨批重挂被拒 | 实测拒 4 条(0.4%) |
| **I6** | **改写来源保真守卫**:若 span 与**声明处**的 word-4-gram containment ≥ 0.5,说明该 span 更像是从声明处改写而来、唯一命中可能是巧合 ⇒ 拒绝重挂 | 实测拒 kufix 15/925(1.62%)、v42 14/381(3.67%) |
| **I7** | **幂等**:已满足 I1 的记录不再处理;重复运行输出不变 | — |

核心函数签名与 level 语义:
```python
def repair_spans(
    records, texts, mem_dates, level=1,
    batch_of_memory=None, batch_of_record=None, paraphrase_guard=True,
) -> Tuple[List[dict], dict]:
    """按 level 修复 source_span 契约违约。返回 (新记录列表, 统计字典)。

    level 语义(单调递增于**改动半径**):
      0  不做任何修复(仅统计)。
      1  只剥模型自加的说话人标签;source_memory_id 不动 -> _rec_date 零影响。
      2  1 + 唯一精确命中重挂,但仅限【可证日期中性】的(判据见 §3.4.3 的
         _rec_date_like 比较,**不是** bool(stated_date))。
      3  2 + 唯一精确命中重挂,含会改变回退日期的。

    永不修复:多处命中、仅归一化匹配、全库精确找不到。
    """
```
执行流程(逐记录):
1. span 为空 → `skip_no_span`;`declared not in texts` → 计 `declared_dangling`(D4)。
2. `span in own` → `ok_strict`,原样返回(**I7**)。
3. **步骤 1(I2)**:`trimmed = _trim_speaker(span)`;若 `trimmed != span and trimmed in own` 且 `level>=1` ⇒ 写回 `source_span=trimmed`、打标 `span_repaired="trim_speaker_prefix"`,**并重验 I1**,失败则 `postcondition_failed` + 回滚。`continue`。
4. `level < 2` ⇒ `left_violation`,原样返回。
5. **步骤 2**:`homes = find_homes(span, texts)`(**仅精确**);为空则用 `trimmed` 再搜一次。仍为空 ⇒ `unrepairable_not_found_exact`。
6. `len(homes) > 1` ⇒ `refused_multi_home`,只打标 `span_multi_home=len(homes)`,**不修**(**I3**)。
7. **I5**:`batch_of_memory[new] != batch_of_record[idx]` ⇒ `refused_cross_batch`。
8. **I6**:`_containment(span, own) >= 0.5` ⇒ `refused_paraphrase_of_declared`,打标 `span_likely_paraphrase_of_declared`。
9. **日期守卫**:按 §3.4.3 的 `_rec_date_like` 比较算 `date_neutral`;`not date_neutral and level < 3` ⇒ `deferred_date_changing`。
10. 提交:写 `source_memory_id=new`(必要时同时写 `source_span=cand`),**重验 I1**,失败回滚;打标 `span_repaired`(`"rehome"` / `"rehome+trim_speaker_prefix"`)、`span_repair_from=declared`,日期变了则 `span_repair_date_changed=[old, new]`。

辅助:`_SPEAKER_RE = re.compile(r"^\s*(?:user|assistant)\s*:\s*", re.I)`;`_TOK_RE = re.compile(r"[A-Za-z0-9一-鿿']+")`;`PARAPHRASE_GUARD_N = 4`、`PARAPHRASE_GUARD_T = 0.5`;`_containment(a, b, n)` = `|ngrams(a) ∩ ngrams(b)| / |ngrams(a)|`;`find_homes(span, texts)` 返回所有**逐字**包含 span 的 memory_id(按 id 升序)。

#### 3.4.5 `wt_qvf_prototype.py` 四处 patch

**Patch 1(旗标声明)** · 锚串:`_CARD_FAIL_LOUD = int(os.environ.get("QVF_CARD_FAIL_LOUD", "0") or 0)`,在其后插入:
```python
# QVF_CARD_REPAIR_SPAN:溯源修复 —— 违反 Rule 1 的卡片改为"重新挂对",而不是
#   被 QVF_CARD_VERIFY_SPAN=2 当垃圾剔除。缺陷证据与不变量见 qvf/span_repair.py
#   的模块 docstring 与 study_logs/QVF_repair_specs_20260818.md §3.4
#   (实测:kufix 上 VERIFY_SPAN=2 丢 1,767 卡 = 28.26%,其中 968 卡 = 15.48%
#    的引文是真的、只是指针指错)。
#   与 QVF_CARD_VERIFY_SPAN 【正交、不合并成同一个整数】:那个梯子按"后果强度"
#   单调(0 不管 / 1 打标 / 2 剔除),而修复会让【剔除量减少】,放进同一个整数会
#   破坏梯子的单调性,且"修复 × 打标/剔除"是笛卡尔积,一个整数表达不了。修复在
#   VERIFY_SPAN 校验块【之前】执行,因此 VERIFY_SPAN=1/2 的计数与剔除自动作用在
#   修复后的库上,校验块本身不改;QVF_CARD_VERIFY_SPAN 的历史语义不变 ⇒ 所有已
#   归档的 span_verify_mode=1/2 结果仍可逐字节复现。
#   0 = 关(默认;write_phase 输出与旗标引入前逐字节一致,且不 import
#       qvf.span_repair —— 延迟 import 写在 if 里)
#   1 = 只剥模型自加的 "user: "/"assistant: " 说话人标签(指针不动)。实测
#       kufix 49 卡(0.78%)、v42 0 卡;read_phase 全程不读 source_span,故对
#       wt 臂零下游面。
#   2 = 1 + 唯一精确命中重挂,仅限可证日期中性者。实测 kufix +784、v42 +317。
#       ⚠ "日期中性"只保证 _rec_date(:477)以及依赖它的排序/成员/时点
#         (:599,:600,:611,:613,:645)不变;【不保证】:623/:635/:640 的
#         extra_ids 与 :646 的 drop_ids 命中同一条 memory —— 错指落点 80.6%
#         是同会话【不同轮】,故 784 条日期中性修复全部会改变注入/删除的轮次。
#         端到端行为变化必须实测,不得推定为零。
#       ⚠ 日期中性的判据随 QVF_DATE_STRICT 变(见 §3.4.3 与 §1.2-C2)。
#   3 = 2 + 含会改变回退日期的重挂(kufix +135、v42 +50;其中 7/3 条是悬空指针
#       从"无日期被踢出链"变成"进链",是成员变化不只是顺序变化;重排上界实测
#       kufix 55 卡 = 0.88% 会跨过同槽位同伴)。
#   永不修复:多处命中(kufix 17 / v42 9,溯源语义不可判定)、仅归一化匹配
#   (kufix 30 / v42 213,给不出"逐字子串"后置条件)、全库精确找不到
#   (kufix 752 / v42 1,571)。
_CARD_REPAIR_SPAN = int(os.environ.get("QVF_CARD_REPAIR_SPAN", "0") or 0)
```

**Patch 2(记录批次归属)** · 锚串 ①`_failed_batches = _span_bad = _span_missing = 0` → 其后加 `_rec_batch: List[int] = []   # 仅 QVF_CARD_REPAIR_SPAN 用(I5 可见性守卫)`;锚串 ②`recs.extend(br)` → 其前加
```python
            if _CARD_REPAIR_SPAN:
                _rec_batch.extend([bi] * len(br))
```

**Patch 3(修复调用)** · 插入在 `recs.extend(br)` 所在循环之后、`if _CARD_VERIFY_SPAN:`(锚串)**之前**:
```python
        _span_repair_stats: dict = {}
        if _CARD_REPAIR_SPAN:
            # 延迟 import:旗标关时 qvf.span_repair 不进 sys.modules
            from qvf.span_repair import repair_spans  # noqa: E402
            recs, _span_repair_stats = repair_spans(
                recs,
                {p["memory_id"]: p["text"] for p in payload},
                {p["memory_id"]: p["date"] for p in payload},
                level=_CARD_REPAIR_SPAN,
                batch_of_memory={p["memory_id"]: _bi
                                 for _bi, _b in enumerate(batches) for p in _b},
                batch_of_record=(_rec_batch if len(batches) > 1 else None),
            )
```

**Patch 4(落盘统计)** · 锚串:`_extra["span_verify_mode"] = _CARD_VERIFY_SPAN` → 其后加
```python
        if _CARD_REPAIR_SPAN:
            _extra["span_repair_mode"] = _CARD_REPAIR_SPAN
            for _k, _v in sorted(_span_repair_stats.items()):
                _extra[f"span_repair_{_k}"] = _v
```
> **旗标关时逐字节等价的机械论证**:`_rec_batch` 恒为 `[]`(未 extend)、`_span_repair_stats` 恒为 `{}`、`_extra` 不增键、`qvf.span_repair` 不被 import ⇒ 输出 JSON 逐字节等价。

#### 3.4.6 `scripts/derive_span_repair.py`(离线派生,零 LLM,零 token)

归档卡片库重建要烧 LLM token,所以主路径是离线派生,**复用同一个 `repair_spans`**(禁止第二份实现)。仿 `scratchpad/derive_spanclean.py` 结构。
```
python scripts/derive_span_repair.py --level 2 --src results/wt_cards_kufix \
    --dst scratchpad/wt_cards_kufix_repair2 --data data/lme_knowledge_update_wt.json
  [--batch-guard]              # 重建分批边界启用 I5(仅对重算段数与文件头
                              #   n_segments 一致的 uid 生效;kufix 74/78)
  [--no-paraphrase-guard]      # 关闭 I6,只用于对照,默认开
```
行为要求:
1. **守卫 G6:拒绝在内容派生 `record_id` 的库上运行。** 判据:抽样 32 条,若 `record_id` 匹配 `^r_[0-9a-f]{16}$` 或存在 `stated_date_effective`/`slot_raw` 键 ⇒ 判为 `write_persession` 产物,**报错退出**并打印 §3.4.3 的理由。`wt_cards_kufix`(`b0#r1` 式)与 `wt_cards_v42`(`r1` 式)均可通过。
2. 文件头继承 `derive_spanclean.py` 写法,追加 `span_repair_mode` / `span_repair_*` 统计 / `derived_from` / `derivation`。
3. `--level 0` 必须输出与源库 **`records` 列表逐字段全等**(脚本内自检断言)—— 这是离线路径的旗标对等测试。
4. `--batch-guard` 的段数一致性检查结果必须打印,不一致的 uid 计数并跳过守卫(**不静默**)。

#### 3.4.7 零 LLM 验证 + 可被证伪的预测

**A. 旗标对等**
- 在线路径:仿 `scripts/verify_persession_determinism.py`,用 stub 替换 `client.messages.parse`(返回固定 `CatalogExtraction`),在 `QVF_CARD_REPAIR_SPAN` 未设 / `=0` 下跑 `write_phase`,与打补丁前的 golden 输出 **`filecmp` 逐字节比对**。
- 离线路径:`--level 0` 的自检断言。
- 静态:旗标未设时跑完 `write_phase`,断言 `"qvf.span_repair" not in sys.modules`。

**B. 机械校验复跑(`scratchpad/span_audit.py`,同口径,零 LLM)** —— **如实报告实测值,不得回头改选择**:

`wt_cards_kufix` → 派生库:

| 指标 | 原库 | **L1 预测** | **L2 预测** | **L3 预测** |
|---|---|---|---|---|
| `strict_ok` | 4,486(71.74%) | **4,535(72.53%)** | **5,319(85.06%)** | **5,454(87.22%)** |
| `prefix_ok` | 49(0.78%) | **0** | **0** | **0** |
| `wrong_mem` | 937(14.98%) | 937 | **153** | **18** |
| `not_found` | 781(12.49%) | **781(恒不变)** | **781** | **781** |
| `VIOLATION` | 1,718(27.47%) | 1,718 | 934(14.94%) | **799(12.78%)** |

`wt_cards_v42` → 派生库:

| 指标 | 原库 | L1 | **L2 预测** | **L3 预测** |
|---|---|---|---|---|
| `strict_ok` | 20,179(90.33%) | 20,179 | **20,496(91.75%)** | **20,546(91.97%)** |
| `wrong_mem` | 376(1.68%) | 376 | 59 | **9** |
| `not_found` | 1,784(7.99%) | **1,784(恒不变)** | 1,784 | 1,784 |
| `VIOLATION` | 2,160(9.67%) | 2,160 | 1,843(8.25%) | **1,793(8.03%)** |

**硬断言(不成立即回滚,不许调参数迁就)**:
1. `not_found` 在任何 level 下**一条都不变** —— 修复从不触碰 T4。
2. L3 的残余 `wrong_mem` **恰好** = 多处命中 + 仅归一化定家 + 被 I5/I6 拒绝者。
3. 每条带 `span_repaired` 的记录都满足 I1(独立重验一遍,`postcondition_failed` 必须为 **0**)。
4. 每条带 `span_repaired` 的记录,除 `source_memory_id`/`source_span`/`span_repair_*` 外**所有字段逐字段全等**源记录。
5. `span_repair_refused_multi_home` = **17**(kufix)/ **9**(v42);`span_repair_refused_cross_batch` ≤ **4**(kufix,开 `--batch-guard`)。

**C. 零 LLM 下游对拍**
- **编译臂(v42/S5)**:`scratchpad/s5_replay_evidence.py` 用归档 jsonl 的 plan 逐题重放 `execute_plan`(纯代码),比对读者输入是否逐字节相同;只有变化的题才需端到端。预筛上界:L2 touch 210/434 uid、L3 touch 224/434 uid ⇒ **≥48% 的 uid 可证读者输入不变,零 LLM 即判定准确率不变**。
- **wt 臂(kufix/LME-KU)· 新脚本 `scripts/verify_span_repair_wt_parity.py`,槽位全枚举,真零 LLM**:`read_phase` 的裁决块(`:534-657`)是纯代码,唯一外部输入是 `qf`(`slot`/`scope`/`point_date`/`presupposed_value`),而 `qf` **只依赖问题、不依赖卡片库** ⇒ 不必调用 focus 模型,直接枚举全部可能的 `qf`:`slot` ∈ 该 uid 库内全部 distinct `slot`(每 uid ~50–80 个);`scope` ∈ `{current, unclear, trajectory}` ∪ `{point_in_time} × 该 uid 全部会话日期`;`presupposed_value` ∈ `{""}` ∪ 该 uid 全部 distinct `value`。对每个组合用原库与修复库分别跑裁决,比对 `(notes, drop_ids, extra_ids)`。
  - 全部相同 ⇒ 无论 focus 返回什么,读者输入逐字节相同 ⇒ 准确率**证明**不变,零 LLM 结案。
  - 有差异 ⇒ 输出差异 `(uid, slot, scope)` 集合;只有 focus 可能落在该集合上的 uid 才需端到端,且对照臂必须**同场重跑**(同一会话内用原库跑一遍),把库效应与采样噪声分开(沿用 `results/writeside_fix_sweep_20260817.md` §五的做法)。
  - **⚠️ 防复制漂移守卫(§1.2-C4)**:该脚本逐字复制冻结裁决块,并在开头校验来源哈希。**但线一改 `:612-614`、线三改 `:565-568`,两处都在块内** ⇒ 原登记值 `897c85a68de068b8` **必然失效**。规定:阶段 6 落地时在冻结块**最终形态**上重新登记一次;守卫语义为"块与本脚本内副本一致",不匹配即 `SystemExit`;文档中写死"任何冻结块变更后必须重登记并同步副本"。
- **编译臂 `_hygiene_pool` 专项(零 LLM)**:`complex_query_arm.py:467-490` 以 `source_memory_id` 为去重键。对四个计数算子用两库分别跑 `_hygiene_pool`,比对**池大小与成员集合**。这是一条不经日期、纯指针的通道,必须单独查。同样加哈希守卫(原登记 `5befe886fa2e9bd2`,若阶段 1 的补丁 1-D 改了 `:484-486` 则需重登记)。

#### 3.4.8 必答:会不会把对的挂成错的?

**会。** 四条通道,已逐条量化并配防护。

| 通道 | 机制 | 最坏上界 | 防护 |
|---|---|---|---|
| **1 · span 是从声明处改写而来,唯一命中是巧合** | 抽取器读 A、输出 A 的轻度改写,该改写串恰好逐字出现在 B ⇒ 重挂到 B 就是把对的挂成错的 | **kufix 15 卡(全库 0.24%)、v42 14 卡(0.06%)** | **I6**:containment ≥ 0.5 即拒绝重挂,只打标。风险集实例多为 `s0#r0→s0#r4` 这类同会话邻轮(即使误挂也是日期中性)—— **但仍拒绝:防护不该依赖"错了也不太疼"** |
| **2 · 重挂到抽取器没看见过的 memory** | 多批建卡时抽取器一次只看一批,批外命中必然是巧合 | **kufix 4 卡(0.06%)** | **I5**:跨批即拒。另有 9 条**原始**声明指针本身跨批(D4),这类原指针可确证为错,重挂是纯改进 |
| **3 · 重挂正确但下游变差** | 即使指针改对,`extra_ids`/`drop_ids` 注入删除的是另一条轮次文本,`_hygiene_pool` 合并掉的是另一批卡 | **无法机械防护** | 只能测:kufix L2 已 touch 全部 78 uid(uid 级预筛在 KU 上无效,必须走槽位全枚举);v42 L2 touch 210/434、L3 224/434。处理:①L2 注释明写"日期中性 ≠ 下游中性";②`2` 与 `3` 各自预注册后再测;③不因结果不好回头改 level |
| **4 · 多处命中** | 不动 ⇒ **风险 = 0** | 代价:kufix 17 / v42 9 卡继续被 `VERIFY_SPAN=2` 剔除 | 已选择付出,理由见 §3.4.2-Q1 |

**兜底**:**I1 保证本模块不可能制造新的契约违约**。残余风险**全部**是"契约成立但历史上挂错了",上界 **kufix ≤19 卡(0.30%)、v42 ≤14 卡(0.06%)**,且已被 I5/I6 拒绝。

#### 3.4.9 被拒条目(不进实施清单)

| 条目 | 拒绝理由 |
|---|---|
| 用"哪种 tie-break 让准确率更高"决定多处命中怎么办 | 教科书级特调,`benchmark_specific` |
| 用"修复后准确率升了"决定 level 用 2 还是 3 | 同上;level 由改动半径与可证性定义,预注册后再测 |
| 改写 T2b / T3-norm 的 `source_span` 文本使其通过严格校验 | "哪种归一化是规范形式"无契约依据;Rule 1 只说 VERBATIM |
| 用 LLM 判定"这条 span 到底出自哪条 memory" | 本线的价值就在零 LLM、确定性、可复算;引入 LLM 即引入不可复现裁决 |
| 顺手修 D5(`_all` 拼接串判据) | 实测当前两库发生 0 次,不是现行缺陷;动它属于无证据改冻结代码 |

---

## 四、⭐ 算子层契约违反率(独立诊断结果,不消耗任何揭盲预算)

**本节是本批的主产出之一。它不需要任何正确答案就能测,可直接作为论文里的诊断结果。**
普查代码从不读 `gold_answer` / `judge_correct`(可 grep 验证:`scratchpad/opaudit/census2.py` 里这两个字段名不出现)。持出集只贡献违反计数,题面/答案未被打开。

### 4.1 主数字

> **在 1,463 个归档 `(plan, store)` 对上,输出级契约违反率 = 245 / 1,463 = 16.7%。**

| 切分 | n | 违反 | 率 |
|---|---|---|---|
| **全部** | 1,463 | 245 | **16.7%** |
| dev/seen | 1,196 | 176 | 14.7% |
| test(S8 unseen) | 134 | 53 | **39.6%** |
| heldout(S8 p2) | 133 | 16 | 12.0% |
| 平面臂 | 1,270 | 152 | 12.0% |
| **代数臂** | 193 | 93 | **48.2%** |

覆盖:381 个 uid × 7 个卡片库 × 20 份归档跑批(S5 418 / S6 45 / S7 259 / S8 seen+unseen+heldout 314 / newdom 207 / boundary_duel 137 / writeside 76),按 `(arm, lib, uid, question, plan)` 去重。

按算子(dev+test):

| 算子 | n | 违反率 |
|---|---|---|
| `expr:AGG`(代数组合) | 104 | **64.4%** |
| `longest` | 237 | **41.4%** |
| `point_in_time` | 101 | **39.6%** |
| `tag_trend` | 115 | 13.9% |
| `count_before` | 124 | 4.0% |
| `count_changes` | 233 | 0.9% |
| `first_last` | 190 | 0.5% |
| `tag_filter` / `trajectory` / `join_at_change` / `expr:ASOF` | 140 / 4 / 65 / 15 | **0.0%** |

> **判决:猜想被证实 —— 算子层存在系统性契约违反,且违反集中在"时长/时点算术"与"代数组合的窗算子"两处,与题型无关。** 每 6 个归档计划里就有 1 个,其输出与它自己的输入或自己的类型承诺矛盾。

**零 LLM 能修好多少:245 / 245 = 100%。** 七条规则全开后再复放,同一套**未改动的**判据在 1,463 行上得 **0 违反**(dev 0 / test 0 / heldout 0),另加 2 行由类型检查**明确拒收**(不计违反,属正确行为)。冻结纪律核验:旗标全关时 **1,463/1,463 逐字节等价**;全开时输出改变 **245/1,463 = 16.7%**,与违反行数**完全相等** —— 规则只碰违反行,零漂移。

### 4.2 逐类型明细与最小可复现例

单例复现命令统一为 `PYTHONIOENCODING=utf-8 python scratchpad/opaudit/repro.py [--rules F1,F2] <set> <qid>`。

| 违反 | 例数(dev/test/heldout) | `discovered_by` | 机制 | 最小可复现例 |
|---|---|---|---|---|
| **E1** 粗粒度日期被当日精度上报 | **128**(97/31/0) | `internal_inconsistency` | `parse_partial_date` 返回契约是 `(date, note)`,`note` 是 `"raw→normalized"` 规约记号(文档写明"供写入 basis"),`_pdate`(`:345-350`)用 `[0]` **把 note 丢掉** ⇒ `2019`/`2019-00-00`/`2019-05` 被当 `2019-01-01`/`2019-05-01` 参与日算术 | `S5_418 / wikiP108010-Q53284080_s5a`:证据行是 `[2005-09]`、`[2010-09]`(月粒度),结论行 `Syracuse University (1826 days)` —— **精度是凭空造的** |
| **E4** `argmax_dur` 的胜者不由数据决定 | **38**(28/10/0) | `contract_violation` | `AGG.fn="argmax_dur"` 契约是 "days each value was held"(`:765-768`);展开粗粒度为真实取值区间后**冠亚军区间重叠**,即 `argmax` 无定义,而代码报确定冠军 | `S5_418 / wikiP108012-Q61996585_s5a`(粒度 `[year,year,month]`):冻结报 `ICR (4199 days)`;独立区间 `Leeds [3288,4016]` vs `ICR [3835,4229]` —— **重叠,胜者未定** |
| **E6** 时点/窗界比较不由数据决定 | **57**(48/8/1) | `contract_violation` | `point_in_time(d)` 契约是 `v_i s.t. t_i <= d < t_{i+1}`;某记录只有年/月精度且真实区间**跨过 d** 时,`t_i <= d` 是否成立不确定,而代码给确定答案 + `This IS the answer` | `S5_418 / wikiP54003-Q26001185_s5c`(`count_before`, `date=2020-12-31`):`"2020-00-00"` 真实区间 `[2020-01-01, 2020-12-31] ∋ 2020-12-31`;另 `boundary_duel / wikiP108010-Q53284080_bswitch`:**查询日期本身**是 `2013-10-00` |
| **C1 + B1 + A1b** 空集合上的聚合被渲染成答案 | **46 / 46 / 33** | `contract_violation` | `check_expr` 对 `AGG` 返回 `"Value"`,承诺该子式**指称一个 Value**;链为空时返回空集聚合(`count_elements→0`、`argmax_dur→{}`),`_render_direct`(`:668-671`)仍无条件加 `"This computed result IS the answer"`,证据包 0 行 ⇒ **读者收到一个零证据的确定数字** | `S8seen_alg / wikiM003-Q106386024_s8wcb2`:`after_slot="residence city"` 归一后未命中 residence 组 ⇒ 界解析失败 ⇒ 全窗清空 ⇒ 报 `count_elements: 0` |
| **C3** 已声明但解析不出的窗界被当成"计数 0"上报 | **17**(2/6/**9**) | `contract_violation` | `_resolve_bound`(`:229-263`)对值锚未命中返回 `(True, None, None)`;`_in_window`(`:302-307`)对 `b_req=True, qd=None` 让每条记录落选,窗静默清空 ⇒ **"界找不到"与"区间里确实没有记录"被压成同一个 0** | 同上 |
| **C2 + C4** 类型检查放行域外索引,界被静默丢弃 | **各 2** | `contract_violation` | `MidExpr.before_index` 文档为 `"1-based ordinal position"`(`:123-125`),`check_expr` 的 WINDOW 分支(`:196-215`)不检查索引域;编译器产出 `after_index=0` 时 `_resolve_bound:243-255` 当"该侧未设界" ⇒ **双侧窗静默退化成单侧窗**,聚合在比声明更大的范围上算完 | `S8seen_alg / wikiP54010-Q105871142_s8cd`:`after_index=0` 被丢,`argmax_dur` 在全链上算出 `{Watersley: 731}` |
| **B5** 计数为负 | **1** | `contract_violation` | `:334-335` `data = len(chain) - 1`,空链 → **−1**,`_render_direct` 照渲染 | `S8seen_alg / wikiM018-Q12257073_s8wca2`:`"Computed count_changes ...: -1. This computed result IS the answer"` |
| **D2 + D3 + B6** 不可解析/被猜错的日期留在链里 | **9 / 5 / 5** | `contract_violation` | `_chain`(`:423-435`)只要求 `_rec_date` 字符串非空,不要求可解析 ⇒ ①`"February 10"`/`"2023-Q2"`/`"2025-02-20 to 2025-02-25"` 进链、进证据包、计入 `count_changes`,却对每个日期算子**不可见**;②`parse_partial_date("02-12")` 不抛异常,把首段当年份 → **公元 2 年**,无范围检查;③`tag_trend` 年桶键是 `_rec_date(r)[:4]`(`:629`)⇒ 桶键 `"Febr"`、`"02-1"`、`"04-0"` | `S7_220 / confirm031-194b9288_s7a`:`Items tagged 社交关系 by year — 02-1: February 12; 03-2: March 22; 04-0: April 1; 2025: ...` |
| **E3** 时长区段被静默跳过(后果最触目) | **1** | `contract_violation` | `longest`(`:698-701`)要求 `parsed[i]` 与 `parsed[i+1]` **都**非 None 才累加,否则整段消失;而年份被猜错的记录仍在链里当端点 | `newdom_P26 / wikiP26028-Q119041180_s5a`:`[02-10]` 被猜成公元 2 年 ⇒ **`Held longest: paternal grandmother passed away (655369 days)` = 1,795 年**。三重违约叠加:①年份猜错 ②丧亲卡进了配偶状态链 ③明显不可能的天数被当确定答案上报 |
| **E2** 证据截断无标记而结论覆盖全量 | **12** | `internal_inconsistency` | `EVIDENCE_CAP = 12`(`:105`),`ev[:EVIDENCE_CAP]` 在 8 处静默截断;而 `tag_trend` 的 `by_year` 结论行(`:626-637`)枚举**全部**命中项并指示 `"citing ONLY these items with their dates"` | `S7_220 / chain002-4781d89c_s7a`:链 20 条、证据 12 行、结论列 20 项 —— 读者被要求引用它看不到的 8 条记录的日期 |
| **E7** 并列被当唯一最长 | **1** | `internal_inconsistency` | `complex_query_arm.py:704-706` 与 `qvf_algebra.py:577-579` **算出了 `winners` 复数列表,却只渲染 `winners[0]`,从不提及并列** —— 变量被填却不被读,注释也未说明 | `S8unseen_flat / wikiP108027-Q20829689_s8wa`:`{ESO:1461, MPI:1461, Open University:1461}` 三方精确并列,输出 `Held longest ...: European Southern Observatory (1461 days)` |

### 4.3 已逐条核查但**不存在**的违反(重要负结果,同样零 gold)

| 类别 | 结果 | 为什么 |
|---|---|---|
| **D1** 链不按时间序 | **0 / 1,463** | 8 个读取侧库里 `stated_date` **未补零者 = 0 条**,故裸字符串排序与真实时序在这些库上一致。**缺陷是潜伏的,不是活动的** |
| **D4** ASOF 返回的不是 ≤d 的最新态 | **0 / 1,463** | 同上,序正确则"取最后一个满足者" ≡ "取最大 `t_i`" |
| **D5** ASOF 返回晚于查询日的记录 | **0 / 1,463** | 判据 `pd <= qd` 结构上排除 |
| **C5** 双锚都存在而 WINDOW 出空区间 | **0 / 1,463** | 空窗全部由"界解析失败"(C3/C2)造成,不是区间运算错 |
| **A1a** 选池漏掉库里确有的记录 | **0 / 1,463** | 用比 `_slot_match` **严格更弱**的独立判据逐槽位比对,零漏检 |
| **B2/B3/B4** 结论引用证据包里没有的记录/日期 | **0 / 1,463** | 除 E2(`tag_trend` 截断)外,结论与证据同源 |
| **E5** 负时长 | **0 / 1,463** | 需要链乱序才会出现,而 D1 = 0 |

**D1 = 0 与线一的"逆序对 = 139/16 对"并不矛盾**:线一在 `wt_cards` / `wt_cards_keyed` 上确有逆序(来源是年份段非四位),但那 3 个 uid 的链未被本次 1,463 个归档计划选中 —— 即缺陷**在库里活着,在归档计划上没开火**。**两处数字必须同时报,不得只报其一。**

### 4.4 两套口径不可互换引用(本文档合并时的重要提醒)

| | 线一 | 线二 |
|---|---|---|
| 分母 | **3,209 行** | **1,463 对** |
| 定义 | 全部 `results/*.jsonl` 中 `plan` 非空的行,**排除 `s8_heldout*`**(183 行) | 按 `(arm, lib, uid, question, plan)` **去重**且可求值的 `(plan, store)` 对,**含** heldout 133 |
| 分子 | 655(选中链含违约日期的行,**上界**) | 245(输出违反自身契约,**实测**) |
| 交集 | **未求**(§7 遗留项) | — |

**引用规则**:说"算子层契约违反率"时用 **16.7% (245/1,463)**;说"日期修复的爆炸半径上界"时用 **20.41% (655/3,209)**。两个百分比看起来接近纯属巧合,**不得混用、不得相加、不得说"合计约 37%"**。

### 4.5 台账更正(必须在阶段 0 完成)

`results/QVF_system_reality_audit_20260817.md:88` 与 `:851` 称生产库有"306 条未补零(如 `2019-3`)"。两条独立复算扫描全部 34 个卡片库:**未补零 = 0 条**;"3 条 5 段、1 条 7 段"对应的实际是 4 条**日期列表/区间**值。真实缺陷形态不同且更严重(1,093–1,604 条非 ISO,含 863–1,243 条隐形 + 230–361 条猜错年份)。
> **任何修复都不得以"306 未补零"为依据立项**,应改引本文档 §3.1.1 / §4.2 的数字。该台账错误已出现在两处 `results/` 文档中,**不更正就会有人据它立项**。

---

## 五、语义决策清单(需要拍板)

每条给:选项 / 各选项后果 / 推荐 + **第一性原理层面的理由**(不许用准确率作理由)。**共 11 条。**

### D1 · `QVF_DATE_STRICT` 的采纳语义:回落 vs 剔除(**最高优先,阻塞阶段 1**)

| 选项 | 后果 |
|---|---|
| **(A) 回落会话日期**(线一 `=2`) | 违约记录留在链上、拿到合法会话日期;实测 255–318 条**确有**可用会话日期 ⇒ 链更完整。链成员变化小,`current`/`ASOF` 的定位从"解析不了的串"变成"会话那天" |
| (B) 剔除记录(线二 F1 / 线一 `=1`) | 违约记录离链;链变短,`count_changes` 等计数变小;值与锚点完好的记录被丢弃 |
| (C) 两个都做成独立旗标 | 旗标数 +1,组合爆炸;且二者对同一记录**互斥**,不存在同开的语义 |

**推荐 (A),(B) 保留为诊断挡 `=1`。理由**:`CATALOG_PROMPT` Rule 4 **自己写明了 else 分支是 empty**,并紧接着说明"The round's own date is provided in metadata";`_rec_date` 的 `stated_date or session_date` 结构本身就把会话日期确立为**声明的缺省值**。一个不属于声明文法的值,在该字段的类型语义下与"不存在"不可区分 ⇒ **契约忠实的读法就是走它自己的 else 分支**。(B) 严于契约本身:契约已经告诉了我们该怎么缺省。

### D2 · `YYYY` / `YYYY-MM` 与日期比较时视为哪天

| 选项 | 后果 |
|---|---|
| **(A) 年初 / 月首** | 合规链上与现行字符串序**零漂移**,diff 可逐条归因 |
| (B) 年末 / 月末 | 51,242,626 对合规日期上产生 **13,606 对**序反转 ⇒ 全部归档实验无条件重算 |
| (C) 区间 `[1-1, 12-31]` + `ASOF` 返回"不确定" | 需给 `Loc` 类型增加第三个居民,改 `check_expr` 类型规则 ⇒ 改代数定义域 |

**推荐 (A)。理由**(三条,见 §3.1.4(a)):右开区间"自此生效"语义强制取最早相容时刻;与 `parse_partial_date`(gold 生成器)同源,否则读取侧与出题侧用两套时间轴;且只有 (A) 不改写归档序。**(C) 的诉求由 D3 以渲染层方式满足,不必改类型系统。**

### D3 · 粗粒度日期上的时点定位:确定点 vs 宣告不可判定(**两份输入规格互相矛盾,必须裁决**)

线一 §3.1.4(a) **否决**了"不确定"选项(理由:`Loc` 类型只有 `{gi: int|None}` 两个居民);线二 F3 **恰恰要**在结论行宣告不可判定。

| 选项 | 后果 |
|---|---|
| (A) 只取确定点(线一),不告警 | 系统继续对"库存精度决定不了"的定位给确定答案 + `This IS the answer`(57 例) |
| (B) 改 `Loc` 类型加"不确定"居民(线一否决的第三选项) | 改代数定义域与类型规则,超出本批授权 |
| **(C) 调和:定位仍用确定点(类型系统不变),但渲染层加 `PRECISION WARNING` 并撤掉 `This IS the answer`** | 类型系统零改动;读者收到"最佳可得读法 + 明示不确定",不再收到伪确定断言 |

**推荐 (C)。理由**:两条线管的是**不同层**——线一管**送进比较运算符的键**(必须是确定的点,否则算子无法定位,`gi` 无从产生);线二管**读者收到的断言强度**。`This IS the answer; do not recount` 是一条**认识论断言**(声称答案由记忆确定),它的真值条件与 `gi` 的计算方式无关。当库存精度不足以确定 `t_i <= d` 时,`gi` 仍可算(取最早相容时刻),但**那条认识论断言为假**。⇒ 撤掉假断言、保留定位,是唯一同时忠于两层语义的选择,且**不需要类型系统的第三个居民**。

### D4a · set 链上各算子语义

**推荐**:按 §3.3.3 的表。核心分界(第一性原理):**依赖"区间/转移"的算子在 set 链上无定义;只依赖"断言事件序"的算子仍有定义。** 因为右开区间 `[t_i, t_{i+1})` 语义预设排他性,而集合值属性上"加入 `v_{i+1}`"不使 `v_i` 失效。
需拍板的细项:`count_changes`/`longest` 在 set 链上给 **=1(输出"无定义"+新增/移除计数)** 还是 **=2(空 `derived` 交 `QVF_FAIL_CLOSED`)**。
**推荐 =1。理由**:`=1` 的输出仍然**忠实报告数据里有什么**(N 个成员加入、M 个移除),只拒绝回答那个没有指称对象的问法;`=2` 引入一条新的降级路径,而降级路径本身有独立的行为(`FAIL_CLOSED` 的文案与统计),会把"算子不适用"与"系统失败"混成同一个可观测事件。**信息量更大且不新增机制的那个更优。**

### D4b · set 判定与粒度判定的嵌套顺序

**推荐:set(定义域)判定在最外层,粒度(精度)判定在 `single` 分支内。理由**:定义域检查先于精度检查 —— 若属性是集合值,"最长持有"根本没有指称对象,讨论它的**精度**是无意义的;反之精度问题只在问法有指称时才存在。

### D5 · span 多处命中挂哪个

| 选项 | 后果 |
|---|---|
| **(A) 不修,标注不可判定** | 代价 kufix 17 卡(0.27%)、v42 9 卡(0.04%)继续被 `VERIFY_SPAN=2` 剔除;误挂风险 = 0 |
| (B) 取最接近 `stated_date` 的 | **循环论证**:用卡片自己的日期主张挑选支持该主张的证据,再让证据回头确认那个日期 |
| (C) 取最早/最晚 | 把数据集的**呈现顺序**当成溯源事实 |

**推荐 (A)。理由**:`source_memory_id` 的语义是"这句话从哪条 memory 抄来的",而卡片**不携带**该信息;当 span 在多条 memory 里逐字出现时,这个问题**在证据上无解**。多处命中的实际长相(`'I just got back from'` 在 v42 有 4 家、4 个不同日期)证实"不可判定"不是空谈。**正确工程行为是标注不可判定,不是编造一个 tie-break。**

### D6 · `_slot_match` 收严规则

| 选项 | 保留分支③实例 | 参数 |
|---|---|---|
| **(a) 词集包含** | 362(0.65%) | **零参数、零词表** |
| (b) 核心词(头名词)相同 | 23,725(42.5%) | 需定义"哪个是核心词" |
| (c) 通用后缀黑名单 | 35,556(63.7%) | 需人挑词表 |

**推荐 (a)。理由**:①写入侧契约 Rule 2 / V4 Rule 7 逐字规定"同一属性必须用一致的槽位名/同一 `slot_class`" ⇒ 按系统自己的契约,**槽位名不同即属性不同**;②英语定语复合名词:增词 = 特化(同属性更窄),同位换词 = 对比 ⇒ 正确判据是"词集包含"。**(b)/(c) 都以"哪些词是核心/通用"为参数,而该参数无法从系统契约导出,只能靠人挑词表 —— 那本身就是一条新的可调旋钮**(耦合审计标为 `benchmark_specific` 的形态)。(a) 是三者中唯一零参数的。
配套:同义对白名单**初始为空**,只收能在写入侧契约里找到依据的对,每条附出处;**禁止**以"加哪些对准确率更高"填表。

### D7 · `QVF_CARD_REPAIR_SPAN` 采纳到哪个 level

**推荐:先上 `1`(阶段 0'),`2` 与 `3` 各自作为独立预注册实验。理由**:level 单调于**改动半径**,而改动半径是可证的(`1` 不动指针 ⇒ `_rec_date` 与 `extra_ids`/`drop_ids` 零影响;`2` 动指针但日期可证中性;`3` 连日期一起动)。按半径递增逐级上,每级的下游面都能先用零 LLM 对拍框定,再决定要不要往上走。**禁止**以"哪个 level 准确率更高"来选。

### D8 · 线二 F1 的"补零排序键"是否实施

**推荐:不实施。理由**:采纳 D1(A) 后链上日期已全在文法 G 内,而 G 内字符串序 ≡ 日历序(0/54,303,831)⇒ 改排序键是 **no-op**。按"无证据不改冻结代码"的纪律,一个可证无行为变化的改动不该动冻结文件(它只增加 diff 面与回归风险)。**注意这条推荐依赖 §3.1.5 步骤 1 的地基断言;若该断言复跑不成立,本条推荐立即反转。**

### D9 · `count_before` 的提示词 vs 代码不一致(R2-S3)

`COMPILE_PROMPT_SPEC:241` 写 `"the number of transitions at or before date"` 并声称与 `"strictly before"` 等价;`:714-718` 代码用严格 `<`。两者在边界日期上**不等价**。

| 选项 | 后果 |
|---|---|
| **(A) 改提示词(改代码不动)** | 提示词变 ⇒ 编译器产出的 plan 可能变 ⇒ 需重编译 ⇒ **烧 token**,且全部归档 plan 的复放基线口径要重新说明 |
| (B) 改代码为 `<=` | 改冻结算子语义;而 `count_before` 的**名字**就是 "before" |
| (C) 本轮只更正注释/文档,标注为已知不一致 | 零成本,但不一致仍在 |

**推荐 (C) 本轮做,(A) 下一轮做。理由**:算子名 `count_before` 与其指称定义(严格早于)一致 ⇒ **代码是对的**,错的是提示词的措辞与"自称等价"那句话。但改提示词会改变编译输出,属于**另一类改动**(会改 plan,而本批全部修复都是"给定 plan 改执行"),混在本批里会让基线不可比。

### D10 · `_hygiene_pool` 的"一句话至多一个状态"(R3-7,本轮新发现)

`complex_query_arm.py:467-472` 注释逐字:"同一来源会话只保留一张卡(一句话至多宣告一个状态)"。**对集合值属性为假** —— "我喜欢爬山、游泳和摄影"一句宣告三个成员。

| 选项 | 后果 |
|---|---|
| (A) 本轮就改(set 池上不做同源去重) | 未量化;会与 `QVF_SLOT_CARD` 的作用面叠加,难以归因 |
| **(B) 先量化再实施** | 需一条只读脚本:数"同一 `source_memory_id` 下 ≥2 张 `set` 卡"的组数与受累题数 |

**推荐 (B)。理由**:本条是合并四份规格时新发现的,尚无任何实测数字;按本批的自律(每条修复都要带零 gold 的量化证据),**无量化不进施工清单**。列入 §7 未解项。

### D11 · 旗标关等价的验证语料是否包含 heldout

**推荐:包含。理由**:旗标关等价是**确定性断言**(纯代码重放,无随机性),它**不看 gold、不判分**,因此在 heldout 上跑它不消耗任何揭盲预算,反而能证明补丁在 heldout 上也是字节等价的。线二的 `blast.py` 已经这么做(1,463 含 heldout 133)。而线一的 3,209 行**排除**了 heldout —— 这是不必要的保守,但**保持现状即可**(重新纳入要重捉基线,不值)。**旗标开的准确率测量则严格受 §6.4 约束。**

---

## 六、预注册判据(跑数前写死)

**本节必须在跑任何带判分的测量之前落成独立文件 `results/prereg_repair_20260818.md` 并 git commit。** 未 commit 即跑 = 该次测量作废。

### 6.1 全局硬护栏(任一不过 ⇒ blocked,不报任何数字)

| # | 判据 | 必须值 | 达不到怎么处置 |
|---|---|---|---|
| **G1** | 读取侧 plan 复放(线一口径),`QVF_*=0` 全关 | **3,209 / 3,209** 三个 sha256 全等 | 补丁在旗标关时不等价 ⇒ **回退重写补丁**,不许放宽判据 |
| **G2** | 算子普查复放(线二口径),旗标全关 | **1,463 / 1,463** 逐字节等价 | 同上 |
| **G3** | 路由离线对拍,`QVF_SLOT_STRICT=0` | 逐题 route **0 分歧** | 同上 |
| **G4** | 证据包对拍 `algebra_parity.py`,全部旗标关 | 逐字节等价 | 同上 |
| **G5** | 写入侧 `write_phase`(stub 掉 LLM),`QVF_CARD_REPAIR_SPAN` 未设/`=0` | `filecmp` 逐字节等价 **且** `"qvf.span_repair" not in sys.modules` | 同上 |
| **G6** | 基线自身可重现 | 同一命令连跑两次,基线 sha 一致 | 存在字典序/集合序泄漏 ⇒ 先修基线脚本,不许继续 |
| **G7** | 地基断言 | `iso_check2.py`:G 内 **54,303,831 对中 0 对**与字符串序不一致 | 不成立 ⇒ §3.1.6 的归并论证作废、D8 反转 ⇒ **整份日期规格重写** |

> **"旗标关时 N/N 相同怎么测"**:靠的不是"跑两次拿到同一个数",而是**同一份归档 plan 在同一份归档卡片库上的纯代码重放** —— `execute_plan` 无随机性、无网络、无时间依赖,故 N/N 相同是**可判定的确定性断言**,不是统计结论。G6 是它的护栏。

### 6.2 日期层(阶段 1)

| # | 判据 | 性质 | 达不到怎么处置 |
|---|---|---|---|
| **P1** | `QVF_DATE_STRICT=2` 的全部 diff 行 **⊆ §3.1.1 的 655 行集合** | **必须成立** | 655 行之外出现任何 diff ⇒ 补丁有非预期副作用 ⇒ **blocked**,逐行定位后重写 |
| **P2** | 每条 diff 可归入且仅归入三类:(i) 链**重排序** (ii) 幽灵记录**被重定日** (iii) 违约记录因无会话日期而**离链** | **必须成立** | 出现第四类 ⇒ **blocked** |
| **P3** | 实际 diff 行数 N | **观测项,不设门槛** | **如实汇报并替换 655 上界。无论 N 是多少,都不回头改 §3.1.4 的任何语义选择** |
| **P4** | `store_index`:I3 失败 2→**0**、I2 失败 2→**0**;幽灵链位 keyed 215/v42 216/v43 218 → **0**;`asof_index` vs 线性扫描分歧 ≥1 → **0** | **必须成立** | 任一不为 0 ⇒ 咽喉点归并论证被证伪 ⇒ 逐站点补丁,不许声称"已蕴含" |

`QVF_DATE_STRICT=1` 同样跑一遍,**只为把 (i)+(iii) 与 (ii) 的贡献分开归因**,不参与采纳决策。

### 6.3 其余三线的机制判据(全部零 LLM,可预注册为"必须成立")

| 线 | 判据 | 必须值 |
|---|---|---|
| 算子契约 | 逐规则单开的杀灭数 | E1 128→0、E4 38→0、E6 57→0、E7 1→0、E2 12→0、C1 46→0、B1 46→0、C3 17→0、A1b 33→0、B5 1→0、C2 2→0、C4 2→0、D2 9→0、D3 5→0、B6 5→0、E3 1→0 |
| 算子契约 | 全开后总违反 | **245 → 0**;输出改变行 **= 245**(相等,零漂移);明确拒收 **+2** |
| 算子契约 | `OPFIX=...`(参考实现)与 `QVF_*=1`(落地实现)结果 | **逐行相同**(禁止两份实现分叉) |
| 分组键 | 分量数单调不减,且每个新分量 ⊆ 修严前某分量 | 逐 uid 断言成立(并查集细化) |
| 分组键 | 键控卷 `keyed_depth` 与归档 `routes` 字段 | **逐题相等**(证明键控路径不受影响) |
| 分组键 | "最大分量占全库 ≥50%" 的 uid 数 | `wt_cards` **140 → ≤5** |
| 分组键 | 路由分布 | 与 §3.3.2 表**逐题一致**(wt 36.2%→27.1%、prompt 49.6%→58.4%,Config K + GATE_V2,n=5,511) |
| set 语义 | `single` 多数池 + 空池题的 diff | **恒为 0**(定义域承诺:只动 set 链;4,443 + 2,509 题零漂移) |
| set 语义 | 有 diff 的题数 | **≈537**,且逐题 `_pool_cardinality == "set"` |
| set 语义 | `count_changes`/`longest` 的 set 分支 | **不输出任何整数**(正则断言 `derived` 行) |
| 溯源 | §3.4.7-B 的五条硬断言 | 全部成立;`postcondition_failed` **= 0** |
| 溯源 | `not_found` | 任何 level 下**一条都不变**(修复从不触碰 T4) |

### 6.4 准确率:允许下降的上限与持出集约定

**允许下降的上限**(工程闸门,**不是**语义选择的依据):

| 卷组 | 承诺 | 依据 |
|---|---|---|
| 键控卷(P39/P108/P54/P551、newdom) | **\|Δ\| ≤ 0.5pp** —— 这是本批**唯一的"应当无害"承诺** | 这些卷走 `_keyed_depth` 先返回、几乎无 set 池、日期几乎全合规 ⇒ 机制上不该被碰 |
| 整体(全部非持出卷加权) | **下降 ≤ 1.5pp** | 最大的机制性改派是 `QVF_SLOT_STRICT` 的 wt→prompt 491 题(8.9pp 臂迁移),1.5pp 是其最坏情况下的可容忍带 |
| 无键卷(STALE/LME/LoCoMo) | **不预测方向** | wt→prompt 迁移是机制性的,其准确率影响取决于 prompt 臂相对 wt 臂的强弱,**与本批缺陷的正确性无关** |

**超过上限怎么处置(写死)**:
1. 超过 1.5pp ⇒ 说明某条修复的**实现**有 bug(而非语义选择错),必须**逐条二分定位**(每次只开一个旗标复跑零 LLM 对拍),定位到实现缺陷后修实现。
2. **任何情况下不得以"准确率降了"为理由回退语义选择、改选 (b)/(c) 规则、或下调 level。** 允许的后续动作只有两条:给无 `slot_class` 的库**补 `slot_class`**(走写入侧 `QVF_CARD_KEYS`/`write_persession` 路径),或**改进 prompt 臂**。
3. 无键卷净负 ⇒ **如实同时报出"修严前/后 × 逐卷"两套数字**,并明确标注"修严的理由是契约与构词法,不是这个数字"。

**持出集只准用一次的约定(写死)**:
1. S8 heldout p2(133–134 行)的**判分测量**,在 §6.1–§6.3 全过、且旗标组合**冻结**、且 `results/prereg_repair_20260818.md` 已 commit 之后,**只跑一次**。
2. 跑完**无论结果如何**,不得改旗标组合再跑第二次;不得逐题打开被改的 16 行去找"为什么错了"。
3. 已知消耗:线二的规则会改变 heldout 上 **16 行**的输出;线一的 3,209 行语料已排除 heldout;线四不涉 S8。
4. **旗标关的等价性验证不受此约束**(见 D11:它不看 gold、不判分,是确定性断言)。
5. 已发生的两处轻度窥视(§0.3)必须在预注册文件里原样披露,不得省略。

### 6.5 每条修复的"达不到怎么处置"汇总

| 修复 | 判据 | 达不到 |
|---|---|---|
| R1(日期层) | G1/G7 + P1–P4 | G7 不过 ⇒ 整节作废重写;P1/P2 不过 ⇒ blocked 逐行定位;P4 不过 ⇒ 放弃"咽喉点蕴含"主张,改为逐站点打补丁 |
| R2-F4/F5 | G2 + 杀灭数 | 残余非零 ⇒ 视为**新引入的回归**,不许当"未覆盖的边缘情况"放过 |
| R2-F2/F3/F6/F7 | G2 + 杀灭数 | 同上 |
| R3-2/3(分组键) | G3 + 四条机制断言 | 分量非细化 ⇒ `_slot_same_attr` 不是 `_slot_match` 的加强,实现有 bug ⇒ 重写;键控卷 `keyed_depth` 不等 ⇒ 说明键控路径确实被碰,回退并重新定位 |
| R3-4(set 语义) | G4 + `single` 池 diff = 0 | `single` 池出现 diff ⇒ 定义域承诺被破坏 ⇒ **立即回退**(这是本条修复的定义,不是调参问题) |
| R4(溯源) | G5 + 五条硬断言 | `postcondition_failed > 0` ⇒ I1 被破坏,模块正在产出违约卡片 ⇒ **立即回退**;`not_found` 变化 ⇒ 修复触碰了 T4 ⇒ 回退 |
| 阶段 0 纯注释 | `import` 冒烟 + G4 | 任一失败 ⇒ 缩进/语法被破坏,直接 `git checkout` 该文件 |

---

## 七、未解与风险

### 7.1 结构性风险

1. **旗标组合爆炸。** 本批新增 9 个旗标,与既有 `QVF_ALGEBRA`/`QVF_CARDS_KEYED`/`QVF_ROUTER_KEYS`/`QVF_GATE_V2`/`QVF_CARD_*` 叠加后组合空间 ≫ 可测量数。**规定**:只测三类点 —— ①全关(9 次,每条旗标各自的 G 系列护栏);②每条旗标**单独开**(9 次零 LLM 复放);③**预注册的唯一采纳组合**(1 次)。**任何"扫一遍组合看哪个最好"的做法都是特调,禁止。**
2. **代数臂的 set 语义缺失。** `QVF_ALGEBRA=1` 时 `execute_plan` 被重绑,`QVF_SLOT_CARD` 不生效 ⇒ 臂间语义不一致。已用 §2.3 的启动拒跑挡住"两者同开",但代价是**采纳 set 语义后代数臂不能用** —— 这是一条硬遗留,需另立规格。
3. **线四通道 3 无法机械防护。** 重挂正确但 `extra_ids`/`drop_ids`/`_hygiene_pool` 命中另一条轮次,答案两个方向都可能翻。只能测,不能证。kufix L2 已 touch 全部 78 uid ⇒ uid 级预筛在 KU 上无效,必须走槽位全枚举。
4. **哈希守卫的维护成本。** 线四的两个冻结块哈希(`wt_qvf_prototype.py:534-657`、`complex_query_arm.py:467-490`)会被线一/线三的补丁打破,每次冻结块变更都要重登记 + 同步副本。**风险**:有人只改代码不重登记 ⇒ 守卫报错被当噪声关掉 ⇒ 验证器悄悄失效。建议在 `scripts/` 里加一条 CI 式检查,或改为运行时提取而非复制。
5. **行号漂移。** 三条线在同一文件的相邻区域插入代码块。本文档已给锚串,但**每阶段落地后必须重新 `grep -n` 更新行号**,否则后续补丁会打错位置。

### 7.2 未量化 / 需先量化的项

| 项 | 缺什么 |
|---|---|
| **R3-7** `_hygiene_pool` 的"一句话至多一个状态"对 set 属性为假 | 需一条只读脚本数"同一 `source_memory_id` 下 ≥2 张 `set` 卡"的组数与受累题数(见 D10) |
| **`_chain` 的"相邻同值合并"在 set 链上的语义** | 线三 B.2 逐算子给了语义,但**没有审 `_chain` 本身**;set 属性上同一成员被反复提及时,"相邻去重"是否还对?未量化 |
| **值为日期短语的碎卡在点查路径上不被剔除** | `_DATEPHRASE_RE` 只作用于计数算子(`_hygiene_pool` 注释自己写明"点查/轨迹算子不经此路"),而 §3.1.1 的幽灵链位实例(`current 报 'March 19th'`)正是这类卡。是设计选择还是缺陷,需先给判据 |
| **655 与 245 的交集** | 两套口径的重叠行数未求(§4.4)。这个数决定"阶段 1 与阶段 2/3 的 diff 是否互相污染",应在阶段 1 之前算出来 |
| **归档实验重算的判分成本** | 655 行(线一)+ 245 行(线二)有重叠但未求交,重算的判分 token 与 $ **未估**。按纪律必须在预注册文件里登记实测口径,不预估 |

### 7.3 已知的口径误差与诚实标注

1. 线一 §3.1.1 的 655 行:卡片库按跑批文件名**启发式映射**(`v42`→`wt_cards_v42` 等),缺省 `wt_cards_keyed`;21 行因 uid 在 `data/` 找不到条目而跳过 ⇒ **量级正确的上界,不是精确值**。
2. 线四批次重建:4 个 uid 的文件头 `n_segments=1` 与重算的 2 不符 ⇒ 这 4 个 uid 的 I5 守卫自动跳过并计数(不静默)。
3. 线二 D1 = 0 与线一"逆序对 139/16 对"并存的解释见 §4.3 —— 缺陷在库里活着、在归档计划上没开火。**两处数字必须同时报。**
4. 台账「306 条未补零」已出现在 `results/QVF_system_reality_audit_20260817.md` 两处,**必须在阶段 0 更正**(§4.5)。
5. `wt_cards` 的 `record_id` 碰撞 37.9% 与本批缺陷叠加放大巨型分量,但**分支③单独就能造成 20.3%**(`v43` 碰撞率 0.5% 时仍有 1.2%)⇒ 两条缺陷线独立,不得互相解释。

### 7.4 本批**不会**改变的已归档结论(防止过度声称)

| 结论 | 是否变 |
|---|---|
| `store_index` REPRO NOTE "B4 数据集范围内零个真实同日多值平局实例" | **不变**(那是关于**平局**的负结果,与本批的**逆序/违约**是不同缺陷) |
| `results/QVF_system_reality_audit_20260817.md` 的 57 项 `benchmark_specific` 计数 | **不变**(本批不新增任何数据集耦合;文法 G 来自建卡契约,不来自考纲;`_slot_match` 收严规则零词表参数) |
| `wt_cards` 的 `record_id` 碰撞 37.9%、逐字锚点四档比例 | **不变**(不同缺陷线;四档比例由线四拆成五档,是**细化**不是修正) |
| S5/S6 榜面 | R3-4(set 语义)几乎不影响 wiki 系列 ⇒ **这条修复的效果不该以 S5/S6 榜面变化来评判** |

---

## 附录 A · 待独立验证的猜想(`discovered_by = answer_was_wrong`)

**空。**

本批 33 项修复全部由以下四类证据得出:①代码自身的契约文本(提示词 Rule、schema、docstring、类型注解);②代码自相矛盾(字段被填却不被读、两条注释打架、同一模块两套判据);③卡片库与记忆库的机械比对;④git 历史。**没有任何一项依赖"某道题答错了"才被发现。**

因此:
- 本批**未消耗任何数据集的揭盲预算**;
- 附录 A 为空,不存在"只能作为猜想另列"的条目;
- 若实施过程中有人从"哪些题错了"出发提出新的修法,该修法**必须单独立项**、标 `discovered_by = answer_was_wrong`、登记它消耗了哪个数据集的揭盲预算,并且**不得混入本文档的施工清单**。

## 附录 B · 复现脚本索引(全部只读、零 LLM,已跑通)

**日期层**:`scratchpad/date_blast_radius.py`、`date_blast_radius2.py`、`date_check3.py`(否证"306 条未补零")、`check_i3.py`(I1–I4 实跑 + 幽灵链位普查)、`demo_two.py`(bisect vs 线性扫描分歧)、`iso_check.py`(年初 vs 年末反事实,0 vs 13,606)、`iso_check2.py`(**序同构证明 0/54,303,831**)、`predict_diff.py`(diff 上界 655/3,209)
**算子契约**:`scratchpad/opaudit/census2.py`(普查主脚本,判据)、`fixes.py`(F1–F7 规则级参考实现,monkeypatch)、`blast.py`(旗标关等价 + 爆炸半径)、`repro.py`(单例对照)、`census2_base.jsonl` / `census2_fixed.jsonl`、`base.txt` / `fixed.txt`;`census.py` / `census.jsonl` 为第一版(判据两处过宽,已被 v2 取代,保留供审计对照)
**分组键与打分**:`scratchpad/line3_slotmatch_analysis.py`、`line3_pairs_detail.py`、`line3_diffwords.py`、`line3_route_shift.py`、`line3_gate2.py`、`line3_setchain_count.py`、`line3_relterm.py`、`line3_giant.py`、`line3_slotmatch_out.json`
**溯源**:`scratchpad/prov_repair_quant.py`、`prov_repair_effects.py`、`prov_repair_risk.py`、`prov_repair_batch.py`、`prov_repair_table.py`、`_prov_T3_wt_cards_kufix.json`(942 行)、`_prov_T3_wt_cards_v42.json`(390 行)

## 附录 C · 待新建 / 待改文件清单(绝对路径)

**新建**
- `D:\ZZL_cluade\qvf\date_norm.py`(§3.1.2 全文)
- `D:\ZZL_cluade\qvf\span_repair.py`(§3.4.4)
- `D:\ZZL_cluade\scripts\date_strict_replay.py`(照抄 `scripts/algebra_parity.py` 的对拍模式)
- `D:\ZZL_cluade\scripts\derive_span_repair.py`(§3.4.6)
- `D:\ZZL_cluade\scripts\verify_span_repair_wt_parity.py`(§3.4.7-C)
- `D:\ZZL_cluade\scripts\opfix_parity.py`(参考实现 vs 落地实现的一致性断言,§3.2.6)
- `D:\ZZL_cluade\results\prereg_repair_20260818.md`(**跑数前必须 commit**,§6)

**待改**
- `D:\ZZL_cluade\scripts\complex_query_arm.py` — `:82` 后旗标块、`:105`、`:340-342`、`:345-350`、`:435` 后两个纯函数、`:467-490`、`:613-638`、`:653-727`、`:797-801`(延后)
- `D:\ZZL_cluade\scripts\wt_qvf_prototype.py` — `:95` 后旗标块、`:362-374`、`:401-404`、`:474` 后插入分组谓词、`:477-478`、`:538-541`(注释)、`:565-568`、`:612-614`
- `D:\ZZL_cluade\scripts\qvf_algebra.py` — `:176-226`、`:243-255`、`:302-310`、`:334-335`、`:342-349`、`:368-372`、`:430-452`、`:573-586`、`:664-671`
- `D:\ZZL_cluade\scripts\qvf_router.py` — `:25-26`、`:290`(docstring)、`:322-325`
- `D:\ZZL_cluade\qvf\store_index.py` — **仅文档更正** `:44-63`、`:185-191` + 可选 `assert`
- `D:\ZZL_cluade\results\QVF_system_reality_audit_20260817.md` — `:88`、`:851` 台账更正(§4.5)
