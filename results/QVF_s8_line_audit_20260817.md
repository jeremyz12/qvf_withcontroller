# S8 代数 / 组合泛化线 · 复算审核(2026-08-17)

> 本线在 08-17 全项目实验审核(`results/QVF_experiment_audit_20260817.md`)中因技术故障漏掉,单独补做。**它是支柱二(六原语完备基)的全部实验依据。**
> 复算脚本全部在 `scratchpad/s8_audit/`:`REPRO.sh`(全部命令)、`parity_deep.py`(逐 op 分母 + 11 个变异)、`parity_deep2.py`(加 synthetic + 决定性变异)、`arms_recompute.py`(三臂 + 去重 + 独立性)、`forensics_cards_flags.py`(卡片库/旗标法证)、`render_fix_decompose.py`(+3.3pp 因果分解)、`parity_reaudit.jsonl`(12 次切片运行落盘)。
> `results/` 与 `study_logs/` 全程只读,零改动。

---

## 总判决

**支柱二的核心实验事实站得住,但它的"强度标签"被系统性地贴高了一档。**

12 次切片运行、约 1,762 次逐字节比较、零反例。护栏从未破过一次,复算完全相符;并且把 P1 文档自称"未找到输入文件、未能复核"的两个缺口(S7 切片、synthetic)全部跑通补上。**"宏执行与平面执行的证据包逐字节相同"是真的,纯符号、零 LLM、两条命令可独立复算——这确实是全项目最硬的资产。**

但 347/347 的准确强度是:**一次高质量的重构等价性回归测试(refactoring-equivalence regression),覆盖 5/11 算子,其中 2 个算子的宏语义未被实际执行,70.9% 的被比字节由两侧共享的同一段选池/建链/渲行代码生成。**它证明"宏展开这一遍没写错",不证明"这 6 个原语独立地实现了 11 个算子的语义"。

---

## 一、复算相符(好消息)

| 归档主张 | 复算命令 | 得到值 |
|---|---|---|
| 台账 L136「逐字节等价 347/347(S5 314 + S6 33)」 | `QVF_CARDS_KEYED=results/wt_cards_v42 python scripts/algebra_parity.py --rows results/wsc_s5_test_v42.jsonl --data data/wikistate_full_P108.json data/wikistate_full_P54.json data/wikistate_full_P551.json --name AUDIT_s5_full` | `n=314 byte_equal=314 diff=0`;S6 两份 15/15、18/18 → 合 347/347 **相符** |
| P1 §6.2 自述"未能复核"的两项 | `--synthetic`;`--rows results/wsc_s7_arm_full2.jsonl` | synthetic **316/316**;S7 **50/50** 与全量 **220/220** —— **缺口不存在** |
| `algebra_render_fix` §二「S5 314/314 + S6 30/30」 | 同上 + `results/complex_s6_v2.jsonl` | 相符;另跑 `wsc_s6_arm2.jsonl` 15/15 |
| 旗标隔离(`QVF_RENDER_ANCHORS` 不触达 11 算子宏路径) | `QVF_RENDER_ANCHORS=1` 下三切片 | S5 314/314、complex_s6_v2 30/30、S7 220/220 **相符** |
| 对拍比的是完整输出而非只比结论行 | `scripts/algebra_parity.py:105` | 判据为 `ev_f==ev_a and de_f==de_a and rc_f==rc_a`(证据包全行 + 计算结论全行 + `reader_content` 全文);`EVIDENCE_CAP=12` 在这些切片上**从未触发**(0 行达 12) |
| 无 try/except 吞异常、无题被剔出分母 | 五切片 `skipped=0` | n 与文件行数逐一相等;`IllFormed` 直接冒泡非零退出 |
| 变异测试:对拍在 count/join 家族上有牙齿 | `parity_deep.py` / `parity_deep2.py` | 11 个变异中 **7 个被抓到**:`AGG.count_changes` 差一→76/314;`argmax_dur` 少算末段→74/314;`distinct_ordered` 丢首见序→11/314;`SELECT` 忽略 hygiene→8/314;`base_chain` 不下钻→抛错;`PICK` 序数差一→6/18;`ASOF` 永远定位失败→13/15+17/18+58/316;`AGG` 永远返回空→226/314 |
| `verify_wsc_s8.py` 独立复核 121/121 | `PYTHONIOENCODING=utf-8 python scripts/verify_wsc_s8.py` | 六 combo 全部 `independently reproduced`,`ALL ROWS ... (100% match)` |
| 台账 L136 / 报告 §三 三臂 49.3 / 52.2 / 70.1 | `arms_recompute.py` | algebra 33/67=49.25%、flat 35/67=52.24%、direct 47/67=70.15% **精确相符**;三臂 qid 完全相同、问题文本零不一致、gold 零不一致、reader 均 `claude-haiku-4-5`;`judge_correct is None`=0、`fail_closed`=0,**分母无任何剔除**。61 题持出集同样 10/61、11/61、13/61 精确相符 |
| 「三臂读同一份 v43」 | `forensics_cards_flags.py` | 可验证而非自述:flat 臂 `evidence_n` 在 v43 下 **67/67** 吻合、v42 下仅 52/67;代数臂 v43+旗标关 **67/67**。v43 与 v42 恰只有 4 个 uid 卡片不同(`wikiM003/M004/M018/M019`),与报告"4 个跨属性 uid 重建"逐一对应,零多余改动 |
| 去耦合原则 3 在代数臂上落地 | 4-gram containment | 代数编译提示词 2 个示例 vs 61 题持出题面 **最大 0.118**、vs 阶段一 121 题 **0.118**;而平面 `COMPILE_PROMPT` few-shot 在归档审计里是 **1.000**。**这一条真做到了** |
| 61 题持出集独立性 | `arms_recompute.py` | 与**全部 8 份** dev/test 产物(r1/r2/r2b/r3/r4 + 三臂 test,共 121 个 id)交集 **0**;30 uid 与阶段一 72 uid 交集 **0**。报告只声明剔了 r1/r4,**实际比声称更强** |
| 判官盲性 | 代码级 | `qvf/judge.py:57-73` 用户提示词只有 QUESTION / QUESTION TYPE / GOLD ANSWER / MODEL RESPONSE 四段;`complex_query_arm.py:923` 与 `wsc_direct_arm.py:222` 调用签名逐字一致,无臂身份字段 |
| **读者与判官在输入相同时是确定性的**(意外好消息) | `render_fix_decompose.py` | 61 题里 plan 与证据包**逐字节相同**的 43 题上,修复开/关判决 **W/L/T = 0/0/43**。此前担心的"temp=0 仍抖动"在读取侧未发生,**噪声全在编译侧** |
| 「最小性已撤回」这个撤回是对的 | 见三.2 | 独立确认找不到任何最小性论证 |
| `data/wsc_s8.jsonl` 生成器可复现 | `git status --porcelain` | 08-17 12:26 重跑生成器,产出与 HEAD **逐字节相同**。这是"金答案纯代码从链导出"最强的旁证,**目前完全没被引用** |

---

## 二、发现(按严重度)

### [critical] 347 只覆盖 11 算子中的 5 个,而 6/11 算子的唯一覆盖恰是被声明"未复核"的两个切片 — CONFIRMED

**被审主张**:`QVF_P1_completeness_20260816.md:52`「命题成立**当且仅当对每个旧算子**,宏渲染出的证据包与平面分支逐字节相同」;`:63`「347/347 现场零信任复跑逐字节相同……护栏未破一次,命题 1(完备性)成立」;`:130`「S5 synthetic(316)与 S7 切片(50)本轮未找到对应的独立可重跑输入文件……**不构成对护栏结论的否定**」。

**逐算子拆分**:

| 算子 | S5 314 | S6 33 | **347 分母内** | S7 50 | synthetic 316 |
|---|---|---|---|---|---|
| count_changes | 79 | | 79 | | |
| longest | 77 | | 77 | | |
| count_before | 79 | | 79 | | |
| first_last | 79 | | 79 | | |
| join_at_change | | 33 | 33 | | |
| tag_filter | | | **0** | 25 | |
| tag_trend | | | **0** | 25 | |
| current | | | **0** | | 79 |
| point_in_time | | | **0** | | 79 |
| trajectory | | | **0** | | 79 |
| premise_check | | | **0** | | 79 |

即 347 覆盖 **5/11**;剩下 6 个里 2 个只在 S7、4 个只在 synthetic。11/11 覆盖必须写成 **347 + 316 + 50**,而台账 L135 阶段一那行本来就是这么写的。

**附带发现**:台账 L170 第⑤项把话术从 `394/394` 改成 `347/347`「消除同文件内部矛盾」。但 **394 = 314 + S6 30 + S7 50 覆盖 7/11**,**347 = 314 + S6 33 覆盖 5/11**,两者互不包含。这次"消除矛盾"把头条换成了**覆盖面更小**的那一个,而周边"11 算子完备"的措辞没动。

**推翻尝试**:①怀疑 op 分布更均匀 → 逐行统计 `plan.op`,就是 4+1;②怀疑"synthetic 与 S7 只是冗余加强项" → `scripts/algebra_parity.py:4-8` 的预注册判据原文写的是「S5 全量 314 + S6 30 + **S7 切片 50** 上……逐题证据包逐字节等价」,**S7 本来就在主判据里**;③怀疑文档别处说清了覆盖面 → grep 全部 347 出现处(`QVF_repositioned:59`、`system_and_claims:93`、`walkthrough_QA:33`、`project_overview:112`)都是单独给 347 不给构成。**推翻失败。**

**复现**:`QVF_CARDS_KEYED=results/wt_cards_v42 python scratchpad/s8_audit/parity_deep.py`(A 段)

### [critical] 变异测试:`PICK` 原语在全部 713 行上是死覆盖 — CONFIRMED

**被审主张**:`QVF_P1_completeness_20260816.md:38`「`current` | `PICK(C, index=-1)` | 深度 2」、`:44`「`first_last` | `PICK(Cʰ, index=1)` ⊕ 链尾直读」、`:52`「11 行宏定义 + `MACROS` 字典 + 求值器 = 一份**可执行的**完备性证据」。

| 变异 | s5(314) | synth(316) | s6a(15) | s6big(18) | s7(50) | 判定 |
|---|---|---|---|---|---|---|
| `PICK(-1)` 取链首而非链尾 | 0 | 0 | 0 | 0 | 0 | **★存活** |
| `PICK` 序数永远返回空记录 | 0 | 0 | 0 | 9/18 | 0 | 仅 join 侧被抓 |
| `PICK` 值锚忽略 `exclude_last` | 0 | 0 | 0 | 0 | 0 | **★存活** |
| `WINDOW` 上界开区间改闭区间 | 0 | 0 | 0 | 0 | 0 | **★存活** |
| `TAGSET` 不按日期排序(v42) | 0 | 0 | 0 | 0 | 0 | **★存活** |
| `ASOF` 右开改严格小于 | 0 | **40/316** | 0 | 0 | 0 | 仅 synthetic 抓到 |

**根因(代码级)**:`scripts/qvf_algebra.py:540-551` 的 `_render_chain_op`,`current` 分支只用 `values[-1]`/`dates[-1]`(来自共享 `base_chain`),**从不读 `node["rec"]`**;`:593-596` 的 `first_last` 同理只用 `values[0]`/`values[-1]`。全文 `node["rec"]` 仅出现两处(`:545` premise_check、`:615` 另一函数)。`trajectory` 的宏是 `_sel(slot)` 叶子,与平面路径同一句。故 **`current`(79)+ `first_last`(79)+ `trajectory`(79)= 237/713 = 33.2% 的分母在结构上必然相等**,与原语实现是否正确无关。

**另两个死点**:`premise_check` 的 `exclude_last`(整个宏唯一语义特征)在 synthetic 里开关无差别(`_synth_plans` 把 `presupposed` 填成 `chain[0]` 的值,链长 ≥2 时必然落在 `chain[:-1]`);`ASOF` 的 `t_i ≤ d` 右闭语义——**"JOIN_T 被 ASOF 吸收"这条论证最吃劲的一处**——在 S6 的 33 行 join 上完全测不到,因为出题时已显式剔除锚点日期与目标链转移重合的行(`wsc_s8_inexpressible.py:29-32` 自己写着这条剔除规则)。

**推翻尝试**:①怀疑变异注入未生效 → 加 `sys.modules` 注册后基线 713 行全等且 7 个变异正常被抓,注入生效;②怀疑 synthetic 能测到 → synthetic 有 79 行 `current`,变异仍 0/316;③怀疑 `_render_chain_op` 别处读了 `node["rec"]` → 全文检索否。**推翻失败。**

**复现**:`QVF_CARDS_KEYED=results/wt_cards_v42 python scratchpad/s8_audit/parity_deep2.py`

### [high] S7 切片 50/50 在归档口径下是空转 — CONFIRMED(并已补齐)

归档 parity jsonl 记录 `rows_file=results/wsc_s7_arm_full2.jsonl, limit=50` 但**不记录 `QVF_CARDS_KEYED`**。用 `wt_cards_v42` 复跑:220 行**全部**标签零命中,证据包全空,两侧 `derived` 都是 `['No stored item carries the tag 社交关系.']`,证据字节 **0**。即 `tag_filter`/`tag_trend` 的护栏比的是同一句"查无此标签"重复 50 次。

**已补齐**:换 `results/wt_cards_tagged` 后 220 行里 **112 行证据非空**(与归档 `wsc_s7_arm_full2.jsonl` 自身 `evidence_n` 非零行数 220−108=112 **精确吻合**,证明这才是原跑批用的库),证据总字节 89,198,对拍 **220/220 逐字节等价**;此时 TAGSET 变异**才被抓到**(不排序 92/220、`by_year` 值替换 96/220、`base_chain` 不下钻 110/220)。

**复现**:`QVF_CARDS_KEYED=results/wt_cards_tagged python scripts/algebra_parity.py --rows results/wsc_s7_arm_full2.jsonl --data data/wikistate_full_P108.json --name AUDIT_s7_TAGGEDCARDS_220 --out scratchpad/s8_audit/parity_reaudit.jsonl`

### [high] 347 分母含 9 行同题重复,唯一题数是 338 — CONFIRMED

`results/wsc_s6_arm.jsonl`(15 qid)与 `wsc_s6_big_arm.jsonl`(18 qid)**交集 9 个**(`wikiM003-Q106386024_s6a1/_s6a2/_s6b1/_s6b2`、`wikiM019-Q13205835_s6a1/_s6a2/_s6b2/_s6b3/_s6b4`),并集 24。这 9 对的问题文本相同、uid 相同、**执行后证据包+结论+reader_content 逐字节相同 9/9**——同一个测试跑了两遍。故 S6 独立用例 **24**,347 的唯一题数 **338**。旁证:`results/complex_s6_v2.jsonl` 正好收录这两份文件全部 qid 且只有 30 行,08-17 那轮护栏表里 S6 也正是写 30。

**唯一有力辩护**:对拍单位是 (question, plan) 对,9 对的 `plan` 字段确实不同(`big_arm` 多了 `anchor_index: null`,1 对还是 `residence city` vs `residence`)。该辩护**部分成立**:说"347 个测试用例"可以,但输出逐字节相同 9/9,信息增量为零。按最宽松口径应写「**338 唯一题 / 347 次执行,其中 9 次为重复执行**」。这与另一条线上的「5511 实为 5061 unique qid」是**同一类缺陷**。

### [high] `wsc_s8_inexpressible.py` 不是穷举判定,是手写白名单 — CONFIRMED

**被审主张**:`results/wsc_s8_report_20260816.md:111-114`「平面臂结构性不可表达率(严格口径,按 combo 类型**机械判定**,非逐行 LLM 判断):**52/67 = 77.6%**」;台账 L136④把 77.6% 当作"支持表达力更强"的证据。

全文 130 行,判定逻辑是两个字面量字典 `EXPRESSIBLE_BY_COMBO`(`:54-61`)与 `EXPRESSIBLE_STRICT`(`:93-100`),`classify()`(`:103-112`)按 `combo` 字段查表求和。**无表达式生成、无搜索、无反例构造**;论证全在 docstring 自然语言里(`:10-43`)。全库 `itertools|permutations|combinations|穷举|exhaust` 在 `scripts/` 与 `qvf/` 下**零命中**。

**更需修的一处错引**:`QVF_P1_completeness_20260816.md:81-82` 把该脚本引作 `JOIN_T∘WINDOW`「**代数臂**结构上也不可表达」的依据,但两个字典判的都是**平面臂 11 算子**的表达力(`:86-92` 注释明确说 `--strict` 是"平面臂自身单算子口径"),它从未评估过 P-表达式空间。

**影响**:①77.6% 实为"6 个 combo 标签上的人工判定按行数加权";②`JOIN_T∘WINDOW` 作为"独立于设计者意图的客观边界"这条**辩护要点**(创新法庭 `:117`、台账 L218 辩护方第②条)——**边界本身是设计者手写进字典的,作为"客观性证据"要打折**。

严重度定 high 而非 critical:`classify()` 确实确定性,**这不是造假,是措辞把"人工论证的确定性查表"说成了会被读成"穷举搜索"的词**。

**复现**:`grep -rn "itertools\|permutations\|combinations" --include=*.py scripts/ qvf/`;`sed -n '54,112p' scripts/wsc_s8_inexpressible.py`

### [high] 两次"我没找到文件"假阴性,其中一次导致护栏分母静默从 33 变 30 — CONFIRMED

**①** `QVF_P1_completeness_20260816.md:130` 称 S7 的 50 题切片文件"未找到……推断被更大规模的 220 题文件覆盖或改名"。**事实**:归档 `results/wsc_s8_algebra_parity_r2_20260815.jsonl` 第 5 行自己就写着 `{"slice":"s7_slice50_r2","rows_file":"results/wsc_s7_arm_full2.jsonl","limit":50}`。50 题切片不是文件,是 `--limit 50`;synthetic 同理是 `--synthetic` 开关(`algebra_parity.py:79`)。两项 5 分钟内跑通(50/50、316/316)。

**②** `results/algebra_render_fix_20260816.md:48-51` 称 S6"当前唯一可直接对拍的产物"是 `complex_s6_v2.jsonl` 30 题。**事实**:`wsc_s6_arm.jsonl`(15)、`wsc_s6_arm2.jsonl`(15)、`wsc_s6_big_arm.jsonl`(18)**全部带 `plan` 字段**,三份都跑通(15/15、15/15、18/18)。作者查的是 `wsc_s6.jsonl`(题库源文件),没查 `*_arm*.jsonl`。后果:该轮护栏表 S6 从 33 静默降为 30,报告未标"与上一轮口径不同"。

**影响**:「347/347」在跨轮之间口径漂移(394 → 347 → 314+30),每次漂移都由一次检索失败驱动,且每次都写成"当前唯一可用/未找到"。

### [medium] `algebra_render_fix` 纪律表把两条勾成"达成",证据是空占位符 + 不存在的文件 — CONFIRMED

`:135-137` §五「预注册判据裁决」= `<!-- VERDICT_PLACEHOLDER -->`;`:145` §六判官成本 = `<!-- JUDGE_COST_PLACEHOLDER -->`;而 `:157-158` 纪律核对写「⑤判官 opus 同段代码……**达成**(见六)」;`:174` 文件清单列 `results/s8_render_fix_judge_recheck_p2.jsonl` —— **该文件不存在**。`qvf/judge.py:100-102` 的 `total_usage` 累计器已实现,技术上零障碍,只是没做。

**按该文件自己写死的判据逐条裁决**(用 `results/s8_heldout_*_p2.jsonl`):

| 判据 | 出处 | 裁决 | 数字 |
|---|---|---|---|
| ① 旗标关时逐字节等价回归 | §七① | **通过** | S5 314/314、complex_s6_v2 30/30,另加 S7 220/220;`RENDER_ANCHORS=1` 下亦全通 |
| ② 主判据:代数(修复开)≥ 平面臂 | `s8_render_fix_analyze.py:95-98` | **形式通过,但判据无功效** | +4.9pp(21.31% vs 16.39%),脚本判 `PASS (>=0)`;而归档审计已测出 W/L/T=6/3/52、p=0.508、簇自助 CI[−3.0,+13.6] **跨零** |
| ③ 机制判据:拒答措辞率下降 | `:99-113` | **整体不通过,靶心 combo 通过** | 整体 60.7%→59.0%(−1.7pp,无方向性);`WINDOW_2ANCHOR∘COUNT`(n=16)93.8%→68.8%(−25.0pp),准确率 0.0%→18.8% |
| ④ 持出集规模 ≥30-40 题 | §三 | **通过** | 61 题 |
| ⑤ 覆盖两类 combo(含 `WINDOW∘AGG`) | §七② | **不通过**(报告已如实标为部分满足) | `WINDOW∘AGG` 整类缺席 |
| ⑥ 持出集从未被任何臂跑过 | §七② | **通过,且比声称更强** | 与全部 8 份产物(121 id)交集 0;30 uid 与阶段一 72 uid 交集 0 |

**应落的判词**:①④⑥ 达成;⑤ 部分满足;②③ **在 n=61 下不可裁决**。

### [medium] +3.3pp 的因果足迹只有 7 题 — CONFIRMED

| 子集 | n | 修复开 vs 关 W/L/T |
|---|---|---|
| (a) 同 plan **且**旗标确实改变了证据包 | 7(全为 `WINDOW_2ANCHOR∘COUNT`) | **3 / 0 / 4** |
| (b) 两臂编译出不同 plan | 11(`JOIN_T∘WINDOW` 10 + `W2ANCHOR` 1) | 1 / 2 / 8 |
| (c) plan 与证据包逐字节相同 | 43 | **0 / 0 / 43** |
| 合计 | 61 | 4 / 2 / 55 |

即 **+3 来自修复本身(在唯一能触达的 7 题上 3胜0负,符号检验 p=0.25)、−1 来自编译不稳定**,净 +2 题 = 11→13。`JOIN_T∘WINDOW` 那格 `3/19→2/19` 按报告自己的隔离论证就是噪声,却被当作分 combo 结果呈现且未标注——同一页对 `NTH∘JOIN_T` 用了这个论证、对 `JOIN_T∘WINDOW` 没用,内部不一致。

**新增机制事实(可写进论文)**:代数编译器在 `JOIN_T∘WINDOW` 上 temperature=0 仍有 **10/19 = 53%** 的 plan 不稳定率,其余 combo 50/50 稳定。**"表达力边界会以计划不稳定的形式显影"**——支柱一/二都能用,数据已在手。

**复现**:`QVF_CARDS_KEYED=results/wt_cards_s8_heldout python scratchpad/s8_audit/render_fix_decompose.py`

### [medium] 61 题持出集的构成使它无法回答它被造出来要回答的问题 — CONFIRMED

| combo | 阶段一 unseen 67 | 61 题持出集 | 代数臂可表达? |
|---|---|---|---|
| `WINDOW∘AGG` | 28(41.8%) | **0** | 是(阶段一代数臂 92.9%,三 combo 最高) |
| `WINDOW_2ANCHOR∘COUNT` | 23(34.3%) | 16(26.2%) | 是(旗标唯一靶心) |
| `NTH∘JOIN_T` | 15(22.4%) | 26(42.6%) | 是 |
| `JOIN_T∘WINDOW` | 1(1.5%) | **19(31.1%)** | **项目自判"代数臂结构上也不可表达"** |

代数臂表现最好的一类整类缺席,自判不可表达的一类从 1.5% 涨到 **31.1%**;`W2ANCHOR` 也从 70% cross-chain 变 100% cross-chain。旗标物理上只能触达 61 题里的 7 题(11.5%)。

**影响台账 L250(更正②)**:把 16-21% 与阶段一 49-52%、S5 83.7% 并列是**跨构成比较**。按 combo 配对看 `NTH∘JOIN_T` 复现得很好(阶段一 33.3%/40.0% → 持出 30.8%/38.5%);真正"拉低"的是新增的 31% 不可表达题与 100% cross 化的 W2ANCHOR(平面臂在这一类从 30.4% 掉到 0.0%)。**结论方向(修复未翻转)不变,但"三臂一起拉低"的原因是构成变了,不是系统变差了。**

### [low] dev 锁定/测前禁触在 git 上无独立痕迹;`flat_test` 早于最后一轮 dev — CONFIRMED

`data/wsc_s8.jsonl`、`wsc_s8.meta.json`、`wsc_s8_seen.jsonl`、`wsc_s8_unseen.jsonl`、`scripts/qvf_algebra.py` **全部只有一个共同 commit `4219e27`(08-16 01:15:08)**,晚于最后一次一次性测(`wsc_s8_algebra_test.jsonl` mtime 00:58:05)17 分钟,期间零 commit。

mtime 时序:`unseen` 23:43:50 → dev_r1 23:52:57 → r2 00:29:40 → r2b 00:32:38 → r3 00:41:57 → **`flat_test` 00:45:52** → r4 00:50:00 → `direct_test` 00:54:22 → `algebra_test` 00:58:05。**平面臂在未见 split 上的跑批发生在最后一轮 dev 结束之前。**

dev 各轮准确率与报告吻合(r1 61.1%、r2 9.3%、r4 51.9%)。实质隔离成立(平面臂不 import `qvf_algebra`,代数臂一次性测在 r4 之后),但"全程未触碰直至锁定"字面为假,且"测前禁触"的**唯一**证据是可变的文件 mtime。

### [low] 三处口径小账 — CONFIRMED

1. **"三重比对"实为二重**:`reader_content` 是两侧共用的同一函数(`complex_query_arm.py:757`),`rc_f==rc_a` 在前两重相等时恒真,第三重零增量。
2. **"编译良构率 67/67=100%"掩盖 1 次彻底编译失败**:`compile_ok` 只有 **66/67**,1 题三次重试全失败落了 `compile_plan_algebra` 的退化 fallback(`PICK(SELECT(), index=-1)`,`qvf_algebra.py:833-835`),而该 fallback 本身良构。口径没错,但"100%"会被读成"编译零失败"。
3. **dev_r1 的 "53/54=98%"** 是把 26 行缺字段行当良构算出来的(53 = 26 + 27)。合理但需脚注。

---

## 三、未找到 / 未能核实

1. **`JOIN_T∘WINDOW` 在 P-表达式空间里"不可表达"的任何形式论证或穷举**——未找到。搜索过:`wsc_s8_inexpressible.py` 全文、`qvf_algebra.py` 全文、`scripts/`+`qvf/` 下 `itertools|permutations|combinations|穷举|exhaust|search_space|enumerate_expr` 零命中、`QVF_methods_formalization_20260814.md` §4/§7.2、`QVF_P1_completeness_20260816.md` §四/§八、`wsc_s8_report_20260816.md` 全文、`git log --diff-filter=A -- scripts/`。现存依据是 docstring 自然语言论证,且该文件两个判定字典判的是平面臂。
2. **"5 原语不足以表出 11 算子"的证明或穷举**——未找到,**确认台账 L253 的撤回是对的**。唯一命中都是记录这件事没做的自审条目。
3. **`algebra_render_fix` 那轮四条预注册判据的原文**——未找到完整归档。判据①②以**可执行代码**存在于 `s8_render_fix_analyze.py:94-113`(这是最强的预注册形式);③④只以散句存在于报告 §三/§七②;原文只在会话记录里。
4. **`results/s8_render_fix_judge_recheck_p2.jsonl`**——不存在(脚本 `s8_render_fix_judge_cost.py` 存在,产物没有)。
5. **归档 parity 运行时的 `QVF_CARDS_KEYED`**——不可从产物核实。`algebra_parity.py:110-115` 落盘字段不含 env。
6. **08-17 那轮结果在台账里的独立行**——不存在,只在 L250(更正②)顺带提了三个数字。

---

## 四、处置建议

### 投稿前必须做

| # | 事项 | 成本 | 工期 |
|---|---|---|---|
| 1 | **347 → 换口径。**全部 8 处引用改成「唯一题 338 / 执行 347 次(S6 含 9 次重复);覆盖 5/11 算子」,或直接换成已跑完的完整口径:**S5 314 + S6 24(去重)+ S7 220(带标签卡片)+ synthetic 316 = 874 次比较,覆盖 11/11 算子,零不等价** | $0 | 半天 |
| 2 | **把 3 处死覆盖补成真覆盖。**让 `_render_chain_op` 的 `current`/`first_last` 分支读 `node["rec"]`(约 6 行);`premise_check` 的 synthetic 计划改用 `chain[-2]` 之外的过时值;`join_at_change` 补 3-5 行边界重合用例。然后把变异测试固化为**元判据**:「任一变异存活即视为该算子未被覆盖」 | $0 | 1 天 |
| 3 | **S7 那格必须用 `wt_cards_tagged` 重报**,并给 `algebra_parity.py` 落盘行加 env 快照(`QVF_CARDS_KEYED`/`QVF_ALGEBRA`/`QVF_RENDER_ANCHORS`/`QVF_TAG_LATTICE`)。已跑通 220/220 | $0 | 2 小时 |
| 4 | **改 `wsc_s8_inexpressible.py` 的措辞并修一处错引。**「机械判定」→「按 combo 类型的人工形式语义论证 + 确定性查表」;删除或改写 `QVF_P1_completeness:81-82` 把该脚本引作代数臂判定处。77.6% 保留但加限定 | $0 | 2 小时 |
| 5 | **`algebra_render_fix` §五落判**(按二.7 表逐条:①④⑥达成、⑤部分、②③在 n=61 下不可裁决),§六填实测判官成本(`total_usage` 已实现,重判 183 次 ≈ $0.56),纪律表⑤"达成"改"未完成",并补进 `VERSION_LEDGER.md`。**这是支柱三自身的收口,不能空着投稿** | ≈$0.6 | 半天 |
| 6 | **61 题持出集结论加构成限定**:标明 31% 是代数臂结构不可表达的 `JOIN_T∘WINDOW`、`WINDOW∘AGG` 整类缺席、W2ANCHOR 100% cross 化;16-21% 与阶段一 49-52%、S5 83.7% **不可并列**。`JOIN_T∘WINDOW` 那格标为旗标不可触达(噪声)。+3.3pp 改写成「在唯一能触达的 7 题上 3胜0负,p=0.25」 | $0 | 半天 |

### 应该做

| # | 事项 | 成本 |
|---|---|---|
| 7 | **把编译不稳定写成一条诊断结果**:代数编译器在结构不可表达的 combo 上 temperature=0 仍有 **53%** plan 不稳定率,其余 combo 50/50 稳定。"表达力边界以计划不稳定形式显影",数据已在手 | $0 |
| 8 | **给护栏结论补强度声明**:「70.9% 的被比字节由两侧共享代码生成;29.1% 为代数侧独立实现的结论行。护栏是重构等价性回归,不是两套独立实现的交叉验证」。12 个结论行模板逐字相同(实测 12/12) | $0 |
| 9 | **把生成器可复现性做成正面证据**:08-17 重跑生成器产出与 HEAD 逐字节相同,是"金答案纯代码从链导出"最强旁证,目前零引用 | $0 |
| 10 | **今后预注册判据须与结果同文件落盘且附最小可检出效应量**;判据代码先 commit 再跑数 | $0 |

### 可以不做

| # | 事项 | 理由 |
|---|---|---|
| 11 | 补"5 原语不足"的穷举证明 | 撤回"最小"已解决。真做需先做参数抽象(`WINDOW` 有 8 个界字段,`PICK`/`ASOF` 有连续值参数),是一篇独立工作的量 |
| 12 | 持出集扩到 250-300 题以"真裁决"渲染修复 | 落「本样本量不可裁决」本身就是合格的预注册闭环产出。$20-40 + 1-2 周换一个大概率仍不显著的结论,不值 |
| 13 | 补 S6 那 9 行重复执行 | 去重报数即可;输出已验逐字节相同,补跑不产生新信息 |
| 14 | 重跑 dev 以在 git 上留痕 | 实质隔离已成立,补跑不能追溯历史。改进点是**今后**每轮 dev 结束即 commit |
