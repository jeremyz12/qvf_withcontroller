# QVF 系统现实审计(自下而上)—— 2026-08-17

> **方法声明**:本轮审计的地面真相只有两样——`scripts/` 与 `qvf/` 下的代码执行路径,以及 `results/` 与 `data/` 下的归档产物。开工阶段未读 `study_logs/` 任何主张文档;所有分数一律从 jsonl 复算;每条"系统做了 X"给 `文件:行号`,追不到的一律写"未能定位"或"无法确定是否被执行"。只有在独立判断成型之后,才在第八节比对文档说了什么。
>
> **注释与 docstring 一律按文档对待,不按事实对待。** 本报告中凡注释与行为不符,单独列条。
>
> 覆盖面:代码侧 6 个模块、44 个 `QVF_*` 旗标、119 个 `except`;产物侧 `results/` 下 629 个 `*.jsonl`(625 个非空)+ 10 个 `*.meta.json`,合计 154,022 行,以及 `data/` 下全部题集与 24 个 `wt_cards*` 卡片库目录。
>
> 只读执行:所有一次性分析脚本写入 `D:\ZZL_cluade\scratchpad\`,未改动任何仓库文件。

---

## 〇、这个系统实际是什么

它不是一个系统,是四件共用一套词汇、但执行路径互不相交的东西。

第一件是**一次性离线抽取器**:把一个用户的全部对话轮次按字符预算切块,每块一次结构化调用,产出一个 16 键的 JSON 记录数组。它对自己产出的任何东西不做校验——逐字锚点不查、日期格式不查、批间 id 不重编号(生产库 37.9% 的记录与同库另一条同名),整批失败会写出一个"成功的"空文件并因"存在即跳过"永久缓存。

第二件是**每题两次小模型调用加若干 Python 分支的读取器**:一次聚焦、一次读者;中间的"确定性裁决"只有三个分支,排序用裸字符串比较日期,槽位靠"共享一个词"合并,缺卡片文件时静默变成一次普通检索问答,而行里照写自己是卡片臂。

第三件是**离线记分板重组器**:它不 import 任何一个臂,把四个归档 jsonl 里的对错布尔值按路由标签查表相加,唯一的实时计算是一次未固定温度的聚焦调用——同一道题被两次调用会有 13.6% 的概率落到不同臂。所谓"整合系统的成绩"是这张查表的和。

第四件是**真正产生了全部头条数字的那条通路**:编译成算子计划、纯 Python 在事实表上算、把结论行伪装成一条记忆摘录交回模型。它是四件里唯一有实质机制的,而第三件从不调用它;读者可以无视它,并且在归档里确实无视过。

外围是 44 个旗标,其中相当一部分注释描述的是别的模块的行为,而它们的取值一律不落盘:629 个归档产物没有一个能自证配置。

它真正稳固的产出有两样:一个可零 LLM 复算的证据包生成器,和一份 15 万行、诚实但溯源为零的测量档案。

---

## 一、系统实际行为逐模块

### 1.1 写入侧建卡(`scripts/wt_qvf_prototype.py` write_phase + `qvf/engine_bridge.py` 契约)

**实际行为**

- 建卡契约不是"六字段",是 **13 个常开 + 3 个旗标门控**,定义在 `qvf/engine_bridge.py:139-217` 的 `ExtractedRecord`;`scripts/wt_qvf_prototype.py:71-74` 的 `CatalogExtraction` 只是把它包成 `records: List[ExtractedRecord]`。`owner`/`slot_class` 由 `engine_bridge.py:194`、`value_tags` 由 `:209` 的**类模体内 `if`** 控制——旗标关时字段在发给模型的 JSON schema 里根本不存在。这个性质是本报告全部旗标反推的硬指纹。
- 输入粒度是 **turn 级,不是 session 级**:`eval/stale_chain_dataset.py:38-45` 把每个 turn 变成一个 `MemoryItem`。实测 `wikiP108000-Q59200022` 在 `data/wikistate_full_P108.json` 里有 34 个 session,喂给建卡的是 **166 条**。
- `wt_qvf_prototype.py:250-252` **存在即跳过**(`if out_f.exists(): continue`),使卡片库目录成为**跨旗标累积体**而非一次实验的产物。
- `:259-270` 按 `QVF_CATALOG_BUDGET`(默认 320000 字符)切块,每块独立一次 `messages.parse`,`:312` 用 `recs.extend(br)` 直接拼接,**无跨批 `record_id` 重编号**。
- `:315-318` 卡片文件只写 4 个键:`{uid, records, usage_in, usage_out}`。

**死路径**

| 项 | 位置 | 判据 |
|---|---|---|
| `_V5_VARIANTS.get(variant, _V5_RULE_H1)` 未命中回退 | `wt_qvf_prototype.py:223` | 无法确定是否被执行:卡片文件与归档行都不记变体名 |
| `--uids` 子集重建、`--item-offset` | `:242-245`、`:399-400` | 无法确定:命令行不落盘 |
| `qvf/prompts.py` 的 ATOMIC CLAIM EXTRACTION 契约 | `qvf/prompts.py:102-131` | **对建卡零执行**,import 图不可达(仅 `adapter→pipeline→run_eval/smoke_test`);归档 `mode="qvf"` 仅 146 行 |
| `write_persession.py` 顺序版 `write_phase` | `:363-420` | 近零覆盖:persession 产物里 `schema="persession_v1"` 仅 3 个文件,其余全是 `_batch` |
| `assemble()` 的 `correction`/`contradiction` 连边分支 | `write_persession.py:339-341` | **零执行**:6 个 persession 库 3679 条记录中非空关系目标的 `temporal_relation` 只有 `replacement`(97)与 `cessation`(4) |

**静默回落**

1. **[严重]** `_catalog()` 的 `except` + 对半分批递归触底(`:297-305`)打印一行并 `return [], 0, 0`;外层 `:308-312` 不检查、`:315-318` 照常写卡片文件。**丢卡与"这几轮确实没有状态事实"不可区分**,且被存在即跳过永久缓存。物证:`results/wt_cards/71017276.json` 与 `gpt4_fe651585_abs.json` 各 `usage_in≈142k`、`records=0`,两者都在 `results/wtqvf3_lmetr.jsonl` 里被当作 `mode="wt_qvf"` 计了分(前者 `judge_correct=True`)。
2. **[严重]** `source_span` 逐字契约**零校验**。实测(`data/wikistate_full_P108.json` 51 个 uid):`results/wt_cards` 3006 张卡中 **330 张(11.0%)** 的 `source_span` 不是其 `source_memory_id` 对应文本的子串,其中 **262 张(8.7%)在该用户全部历史里根本找不到**;`results/wt_cards_v43` 同批 237/2543(9.3%),193 张(7.6%)全库找不到。`scripts/complex_query_arm.py:443` 直接把 `source_span` 当引文喂读者。
3. **[严重]** 跨批 id 不重编号导致 **生产库 37.9% 记录 id 碰撞**(694 文件中 242 个有碰撞,65774 条中 24942 条;最坏一个文件 349 条都叫 `r1`)。按跑批归属:`wtqvf3_stale50` 50/50 uid、`wtqvf3_lmeku` 68/72、`wtqvf3_lmetr` 37/42、`wtqvf3_locomo_full` 1/10;wikistate 系 0/53。
4. **[中]** `_catalog` 的空返回守卫只在 `len(batch) > 8` 时判失败(`:294-296`);`<=8` 的空返回被当合法结果接受并计 token。
5. **[中]** `_cardinality_for_group` 平票偏向 single(`write_persession.py:279-283`,`n_single >= n_set`);`_canonical_slot` 把众数槽位名**覆盖写回** `slot`(`:248-264`、`:330`),原文只留 `slot_raw`。

**旗标实际效果(要点)**

- `QVF_CARD_KEYS`:同一环境变量被 `wt_qvf_prototype.py:42` 与 `engine_bridge.py:38` **两个模块各自独立读取**,分别改提示词基底与 pydantic 类模体。闭集(`slot_class` 的 `position|employer|...`)**类型是 `str`,从未校验**;且 `owner`/`slot_class` 在 wt 臂 read_phase 里**从不被消费**,故开它对 wt 臂唯一影响是提示词变长导致抽取分布漂移。
- `QVF_CARD_TEMP0`(`:67`,08-17 起默认 1):唯一效果是 `_catalog()` 是否传 `temperature=0.0`(`:277-279`)。**卡片文件无温度字段**,唯一线索是 mtime:`results/wt_cards` 全在 08-07~08-12(旧行为),`results/wt_cards_s8_heldout` 全在 08-17 13:04-13:23(横跨默认值变更日)。
- `QVF_CATALOG_BUDGET`:**不是纯性能旗标**——批数直接决定 (a) Rule 2 跨记录一致 slot 名能否成立,(b) id 是否碰撞,(c) 关系边能否跨批建立。
- `QVF_CARD_KEYS` × 存在即跳过的耦合:`results/wt_cards_s8_heldout` **8 个文件带 `owner`/`slot_class`、22 个不带**,却被 `QVF_CARDS_KEYED=results/wt_cards_s8_heldout` 当单一库读取——同一次测量里 8 个 uid 走键控、22 个走无键回退。同样混合见 `results/wt_cards_ooo_seq`(3/12)。
- `QVF_CARD_TAGS=2`:`engine_bridge.py:209` 是 `if _CARD_TAGS:` 真值判断,无 `=2` 分支,故字段描述仍写 "from the CLOSED SET",与开放标签提示词(`wt_qvf_prototype.py:127-135`)**在同一次调用里自相矛盾**。产物证明模型服从提示词:`wt_cards_opentags` 8852 个标签 **0%** 落在闭集内、3343 个互异全英文;对照 `wt_cards_tagged` 98.9% 在闭集内。
- `QVF_EXTRACT_TRUNC`:名字与建卡无关。`_etrunc` 只经 `_ewindow`(`engine_bridge.py:86`)被 `:740`/`:833` 用,那是遗留读取时抽取器;建卡 payload(`wt_qvf_prototype.py:253-255`)用原始 `m.content`。

**注释与代码不符**

- `engine_bridge.py:12-16` docstring:"span verbatimness is **enforced by the engine**, and rejections are counted via extraction_report";`:275`/`:369`/`:370` 的提示词逐字告诉模型 "mechanically verified / paraphrase gets rejected"。**建卡路径上不存在任何 span 校验器**,实测 9–11% 违约全部入库——**一个不存在的校验器被逐字发给了模型**。
- `engine_bridge.py:210` 注释 "QVF_CARD_TAGS=1 only",条件却是 `if _CARD_TAGS:`;`:195` 注释 "EXACTLY one of: ...",`:203` 类型却是 `str`。
- `write_persession.py:9-19` 反复说"逐会话独立抽取"、字段叫 `n_sessions`(`:412`),实际粒度是 **turn**。物证:`results/wt_cards_p3_subset/wikiP108000-Q59200022.json` 记 `n_sessions=166`,该 uid 只有 34 个 session。同一错误见 `wt_qvf_prototype.py:256-258`。
- `write_persession_batch.py:11-16` 自称 "does not change what is sent to the model or how records are assembled",但它**改变了产物 schema**(多写 `n_fail`、`schema` 值变 `persession_v1_batch`,`:95-100`),导致 `results/wt_cards_p3_subset` 里混着两种 schema。

---

### 1.2 wt 读取臂(`scripts/wt_qvf_prototype.py` read_phase)

**实际行为**

- `:421` `cards = ... if cards_f.exists() else []` —— 卡片文件缺失静默变成零卡片。
- `:431-437` 唯一前置 LLM 调用产出 `QueryFocusMini`(`:325-343`,5 字段),其中 **`entity` 抽了但全函数不读**。
- `:463-475` 并查集节点 id 取 `record_id`(缺失才退化 `idx{i}`),再用 `_slot_match` 对**所有卡片两两**做槽位模糊 union。`_slot_match`(`:374-381`)判据是"相等 ∨ 互为子串 ∨ 共享词数 ≥ min(词数)−1",**两个二词槽位共享 1 个词即判同槽**。实测(`wt_cards_v43` 前 80 uid,101870 组不同槽位)**2708 组(2.7%)被误并**:`device_preference`↔`diet_preference`、`income_event`↔`family_event`、`backup_routine`↔`bedtime_routine`。
- `:481-488` `comp_score = 4*slot_hits + min(rel, 3)`。
- 裁决只有 **三支**(`:506-564`):`point_in_time`(两个子支)、`trajectory`、`current/unclear`。`count_changes`/`longest`/`count_before`/`first_last`/`join`/`tag_*` 一个都没有。
- 日期比较是**裸字符串比较**:`_rec_date`(`:384-385`)、`:506` `sorted(key=_rec_date)`、`:520` `<= qf.point_date`。生产库 `stated_date` 混杂 `YYYY`/`YYYY-MM`/`YYYY-MM-DD`,另有 306 条未补零(如 `2019-3`)、3 条 5 段、1 条 7 段垃圾值。`2019-3` 与 `2019-11-01` 的字符串比较结果与真实时序**相反**。同仓库 `scripts/write_persession.py:267-276` 的 `_date_key()` 实现了补零排序键,**生产路径不用它**。
- `:507` 无日期的卡整条静默丢弃,无计数。

**死路径与零执行**

- `QVF_FAIL_CLOSED` 降级标记(`:604-605`):**零执行**。7989 行 `mode="wt_qvf"` 中 `wt_fail_closed` 出现 0 次;而条件 `_FAIL_CLOSED and cards and not notes` **恰好排除了 `cards` 为空(卡片库缺失)这一最危险情形**。
- `idx{i}` 兜底(`:463`):零执行(抽查全部卡片库 `record_id` 100% 存在)。
- point_in_time 的 `else` 子支(`:531-535`)、`presupposed_value` 反查回退(`:495-505`):**无法确定是否被执行**——归档行只落 `notes_n`,note 文本、scope 分支、`qf` 各字段都不落盘。

**静默回落**

1. **[严重]** 卡片库缺失静默归零(`:421`):该题实际退化成"检索 + 读者"(即直读基线),行里照写 `mode="wt_qvf"`、`extractor_model="write-time-cache"`。物证:`results/wt_read_strict3_P39ext.jsonl` 44 个 uid 里只有 4 个在 `results/wt_cards_strict3_probe` 有卡片,其余 40 个 uid 的 **160/176 行(91%)** 全部 `notes_n=0`(一一对应,零例外);`wt_read_strict3_P551.jsonl` 同理 7/11 uid、**28/44 行(64%)**。
2. **[中]** `:469 if tgt in by_rid` 静默丢弃悬空关系目标,不计数——分批建卡下必然产生跨批悬空。
3. **[中]** 断点续跑 `done` 收集裸 `except: pass`(`:409-412`)且不加锁,追加写(`:414`)。物证:`results/mabfc_sh262k_qvf.jsonl` **195 行 / 100 unique,95 行重复**,2 组两份判决不一致;行级 71.3% vs 去重 70.0%。

**注释与代码不符**

- `:445-448` 注释写"组件得分 = **2×内部关系边数 + 匹配查询槽位的卡数**",`:488` 代码是 `4 * slot_hits + min(rel, 3)`——**系数、主次、上限全不同**;`:482-483` 上方另有一段描述正确新口径的注释,**同一函数上方两段互相矛盾的注释**。
- `:2-7` docstring 说"读取时仅一次微型聚焦 + 确定性裁决 + 读者",实际还有第三次 LLM 调用(judge,`:592`),而 `:599` 的 `usage_input_tokens` 不含 judge。
- `:141-142` 对 `QVF_FAIL_CLOSED` 的措辞让人以为覆盖了空证据情形,`:604` 的条件明确排除了卡片库缺失,注释未提这个边界。

**零 LLM 离线复算的结论**:在有 id 碰撞的库上分量结构塌陷。`results/wt_cards/01f694b2-....json`:真 id → 8 个分量/最大 181-of-190;唯一 id → 37 个分量/最大 104-of-190。`01493427.json`:分量数 30→8、最大 31/108→94/108。**"抗污染连通分量"在所有多批库上等于失效。**

---

### 1.3 路由(`scripts/qvf_router.py`)

**最重要的一条:这个文件里没有任何臂的实现。**

全部 import 只有标准库、`dotenv`、`anthropic`,以及 `:25-26` 从 `wt_qvf_prototype` 取的 `FOCUS_PROMPT, QueryFocusMini, _norm, _slot_match`。**没有 import 任何一个臂**:无 `framing_arm`、无 `framing_qvf_arm`、无 `wt_qvf_prototype.read_phase`、无 `framing_tlcot_arm`、无 `complex_query_arm`、无 `qvf_algebra`。四臂答案全部来自已归档 jsonl 的 `judge_correct` 布尔值,经 `load_arm()`(`:98-112`)读入字典;"整合系统的输出"就是 `:489-525` 按路由标签查表求和。运行它唯一真实发起的 LLM 调用是 mini 聚焦(`:183-202`)。

**逐题真算的两个信号**

- `focus_of`(`:183-202`):缓存键 `f"{bench}|{qid}"`,缓存文件 `results/router_focus_cache.json`;未命中则 `messages.parse(model="claude-haiku-4-5", max_tokens=400)`,**不传 temperature**(全文件无该字符串)→ 走 API 默认 1.0。只取 5 字段中的 3 个(`entity`、`point_date` 被生成、被计费、被丢弃)。
- `chain_depth`(`:289-359`):`:359` 是 `max(comp_depth, len(dated_vals(hit_union)), len(dated_vals(direct_idx)))`。因 `best ⊆ hit_union` 且 `direct_idx ⊆ hit_union`,**第二项恒为最大**。326 个真实(卡片, 聚焦槽位)组合实测 **0 反例**。
- `_keyed_depth`(`:253-286`,仅 `QVF_ROUTER_KEYS=1` 经 `:299-302` 进入):分组键**恒为 `(owner, slot_class)`**(`:283`),且**不要求 `stated_date`**——与词重叠路径的计数口径不同,两条路径产出的 depth 是**两个不同量纲的数**,却写进产物同一个 `keyed_depth` 字段。

**死路径**

| 项 | 位置 | 判据 |
|---|---|---|
| 并查集 + 关系边遍历 + 分量打分 + best 选择(47 行) | `:304-350` | **可证明永远影响不了返回值**(见上);docstring `:290-291` 描述的正是被丢弃的那一项 |
| `intent_of()` 与 `QVF_LLM_INTENT` 全路径 | `:221-243` | **在整合系统里从未执行**:`results/router_intent_cache.json` 300 条键前缀**全部**是 `intent_eval`(唯一写入者 `scripts/eval_intent_vs_regex.py:87`),无一条以 15 个 bench 名开头 |
| 冻结 `route()` 的逐题产物 | `:362-368` | **零存在**:只在两旗标全关时被调用,而同一条件下 `route_f` 为 None(`:446`),不写路由日志 |
| `_ROUTER_KEYS=1` 且走 `route()` | `:299-302` + `:435` | **结构上不可达** |
| `QVF_GATE_DEPTH` 非 3 的取值 | `:385-386` | 全库唯一非读取引用是 `newdom_router.py:33` 的 `assert == "3"` |
| rt→direct 降级链 | `:503-507` | 正式产物 `router_routes_v42_final.jsonl` **0 次触发**;`router_routes_frozen_equiv.jsonl` 触发 5 次 |
| prompt 缺行→`pick=None` | `:497-499` | v42_final 0 次;`router_routes_v2.jsonl` 2651 次、`v41.jsonl` 2430 次、`v41_final`/`v42` 各 1071 次 |
| `--direct-rows` 覆盖分支 | `:427-429`、`:500-501` | 无法确定:全库无任何脚本/日志/md 提到该参数 |
| open_slot 分支 | `:264-269` | **只在一个 100 题的域上执行过一次**:`openslot_repair_20260816_routes_P69.jsonl` vs `newdom_routes_P69.jsonl` 100 行中 15 行不同(13 行 rt→wt) |
| `open_slot.match_classes` 第 ③ 级嵌入相似度 | `open_slot.py:155-170` | 无法确定:P69 那 15 行改判可能全由第 ② 级字符串归一产生 |

**静默回落**

1. **[严重]** `focus_of` 三次全败后返回并**持久化**默认值 `{slot:"", scope:"unclear", presupposed:""}`(`:187-201`)。该值经 `route`/`route_v2` 第一条规则**必然**产出 `direct`。归档缓存有 **5 条**完全等于该默认值的条目(全在 LoCoMo-full:`locomo00-conv-26_cat4_q125`、`locomo03-conv-42_cat4_q108`、`locomo03-conv-42_cat5_q232`、`locomo09-conv-50_cat2_q51`、`locomo09-conv-50_cat4_q100`),与"模型真的说 unclear"不可区分。
2. **[严重]** 卡片文件不存在时 `chain_depth` 返回 0(`:293-294`)、`_store_max_depth` 返回 0(`:394-420`,且 `:417-418` 是 `except: d = 0`),与"库存在但确实浅"**同值**。`QVF_GATE_V2=1` 下规则 5 两个深度条件同时满足 → 无条件改派 prompt。实测:v42_final 的 1037 个 uid 里 **350 个两卡库都无文件,对应 1048 题(19.0%)全部 route=prompt**。
3. **[严重]** prompt 臂字典**跨 bench 共用、不做命名空间隔离**且后写覆盖前写(`:100-101`、`:437-440`)。`results/prompt_rows_all.jsonl` 4482 行只有 4332 个不同 normkey,**150 个 qid 出现两次,其中 27 个(18%)两次 `judge_correct` 相反**。谁胜出取决于 `--prompt-rows` 参数顺序与文件行序,产物无记录。
4. **[中]** `:468` `qs = [x for x in qs if x[1] in arms["direct"]]`:direct 臂缺行的题被从题集与**分母**里静默删除(归档配置下丢 0 题)。
5. **[中]** `:527-528` `accs` 分母恒为全卷 n。**STALE-full 的 wt 列打印 5.2%,而 wt 在其覆盖的 150 题上是 41.3%(62/150)——差 8 倍。**
6. **[中]** `:111` `bool(r.get("judge_correct"))`:字段缺失或 null 一律折成 False。

**旗标实际效果**

| 旗标 | 实际效果 |
|---|---|
| `QVF_ROUTER_KEYS` | 唯一效果是 `chain_depth` 里先试 `_keyed_depth`。**卡片无 `slot_class` 时是完全的 no-op** —— `results/wt_cards` 抽样 48473 条中带 `slot_class` 的是 **0** 条。真正改变行为的是 `QVF_CARDS_KEYED` |
| `QVF_GATE_V2` | 规则 1(事件算术直通)决定 71 题;规则 5(时序薄链改 prompt)决定 **2729 题 = 49.5%**。规则 5 第二合取项在无键控卡片时**恒为真**,于是"薄链才改派"退化为"**所有 rt 都改派 prompt**"。实证:v42_final 中 `route=rt` 的 393 行**全部**属于有 `wt_cards_v42/uid.json` 的 uid |
| `QVF_OPEN_SLOT` vs `QVF_OPEN_KEYS` | `:264` 是 `if _OPEN_SLOT or _OPEN_KEYS`,`:267` 是 `use_embed=bool(_OPEN_SLOT)`。**前者行为是后者的严格超集**,故 OPEN_SLOT=1 时 OPEN_KEYS 无独立效果;两个已归档调用点(`boundary_run.py:58-59`、`boundary_ooo_run.py:36-37`)都同时设两个 |
| `QVF_CARDS_KEYED` | 回落是**逐 uid** 的:`wt_cards_v42` 只有 434 个文件而 `wt_cards` 有 694 个,v42_final 的 1037 个 uid 里 416 走键控、621 回落——**同一次跑批混用两套量纲的深度定义** |

**注释与代码不符**

- `:5` "路由决策逐题真算……**路由为确定性函数**"。**被实测否定**:450 道在两个 bench 名下重复调用的题,聚焦输出 300/450 不同(scope 不同 57 例),**最终路由标签 61/450(13.6%)不同**(prompt↔direct 36、prompt↔wt 18、wt↔direct 7)。确定性只由缓存文件提供。
- `:290-291` `chain_depth` docstring 描述"含聚焦槽位的**最佳分量**的不同取值数"——那正是被 `max()` 丢弃的那一项。
- `:44-45` 对 `QVF_OPEN_KEYS` 说"键控分组以 slot_class 字符串本身为键"——**分组键与该旗标无关**(`:283` 恒按 `(owner, slot_class)`)。
- `:168-169` BENCHES 里 STALE-full 的注释"深度0→**rt**",而 GATE_V2 正式配置下深度 0 → **prompt**:v42_final 的 STALE-full 1200 题里 prompt 1134、wt 64、direct 2、**rt 0**。
- `:256-258` "一人称问题(**本组基准默认**)"。实测 `_FP_RE` 命中率:LoCoMo **0/300**、LoCoMo-full **0/1986**、STALE-full 401/1200 —— 约 3100/5511(56%)不是一人称,owner 过滤对它们不生效。
- `:32-33` "默认全 0/空 = v1.2 冻结行为,输出逐字节不变":stdout 层成立,但**旗标全关时不产出任何逐题路由日志**,"输出逐字节不变"对产物集合不成立。
- `:50-53` 关于正则召回的长注释(624 条、16.2%、longest 与 count_before 为 0%)—— 用 `results/paraphrase_set_20260815.jsonl` 独立复算:624 条、101 命中 = 16.2%、longest 0/207、count_before 0/219、count_changes 101/198。**这条注释准确。**
- `:471-475` "去耦合记录 08-16"声称把"用 wt 结果文件反推测试集"改为数据层 `split` 声明并由 `verify_split_parity.py` 证明等价。**该证明是循环的**:`git log -S'"split"' -- data/wikistate_full.json` 显示 split 字段与那行代码的删除在**同一提交** e732efc;且 `split=="test"` 的 52 个 uid 与 `results/wiki_wtqvf3_test.jsonl` 出现的 uid 集合**完全相等**。耦合从代码搬到了数据,没有解除。

**路由分布反推**(`results/router_routes_v42_final.jsonl` 5511 行,唯一被 `train_router.py:172-173` 硬编码消费的日志)

prompt 2729(49.5%)/ wt 1949(35.4%)/ direct 440(8.0%)/ rt 393(7.1%)。direct 440 = 规则 2(scope unclear)**369** + 规则 1(事件算术)**64** + 两者同时 **7**。路由几乎是考场身份函数:chain/confirm/9 个 wiki 卷(1664 题)**从不出 prompt、从不出 direct**;LME-TR/LME-KU/LoCoMo/LoCoMo-full/STALE-full/stale-150(3847 题)**从不出 rt**。分水岭正是有没有键控卡库。

事件算术正则的真实召回:归档中 **73 题**字面就是事件算术(`How many days passed between…`),正则一条不中(它要连续子串 `days between`,文本是 `days passed between`);这 73 题里 **66 题被路由到 prompt(51)或 wt(15)**。

---

### 1.4 学习路由与统计(`train_router.py`、`router_ablation.py`、`router_eps_scaling.py`)

**实际行为**

- `assemble()`(`train_router.py:171-256`)以 v42_final 的 5511 行为主键,`direct/rt/wt` 从**独立复制**的 BENCHES 表(`:80-141`)、`prompt` 从 `results/prompt_rows_all.jsonl`。实测:4 臂全在 3557 题、3 臂 1953、2 臂 1,`restricted = 1954`;`replay_mismatch = 0`、`v42_tok_missing = 0`。臂级实测 direct 60.30% @1904 tok / rt 66.31% @21946 / wt 69.40% @2837 / prompt 65.37% @1392;逐题 oracle 82.14%;v4.2 手写 70.15% @3177。
- `featurize`(`:265-310`)44 维,含 **4 个 `route=` one-hot(手写路由自己的决策)**。`kd` 直接取产物 `keyed_depth`(`:293-294`),**两个不同量纲混在一列**(键控中位数 3-4,词重叠可达 51)。
- `SEED = 20260814`(`:40`)出现三处:`:618` 5 折按 uid 分组、`:688` 40/20/40 切分、`:757` LODO(`SEED+7`)。
- λ 的选择:`same_acc`/`same_cost`/`lam_star` 都在**全量 5511 上评估出的 frontier** 里扫 17 个 λ 取最优(`:648-668`),**无留出集**。`same_acc` λ=1.5 得 70.30% vs 手写 70.15%,tok 1349 vs 3177(−57.5%)——**准确率余量 +0.15pp ≈ 8 道题,且是 17 个 λ 里挑出的最大值**。目标域 13 卷微平均:**学习 79.78% vs 手写 82.71%(学习差 2.93pp)**,整体"赢"完全由 STALE-full + LoCoMo-full 两个大卷承担。λ ≥ 0.5 的所有操作点上 `picks` 里 **rt = 0**。
- `policy_pick`(`:462-470`)的成本项是该臂在该题上的**实测 token**,部署时不可先验获得(报告 §9 已披露并给了常数成本敏感性表)。
- 证书(`:687-747`):主口径在 ε∈{0.03,0.05} 上 `lam_hat` **均为 None**(λ=0 在 calib 上经验风险已 8.79%,首个检验即 break),故 `:719-726` 的测试集评估分支**在归档跑批里从未执行**。次级口径 ε=0.03 得 λ̂=0.05、ε=0.05 得 λ̂=0.5。
- LODO(`:750-786`)15 个留一域全部发出 λ̂,其中 **9 个证书成立 / 6 个不成立**(chain-212 8.96%、confirm-228 17.11%、wiki-P39 5.77%、wiki-P108-ext 13.77%、LME-TR 7.52%、LoCoMo-full 5.49% 超 ε=0.05)。

**死路径 / 零覆盖**

- **全库不存在任何多种子循环**。本轮 `grep -rn "for seed|seed in (|seed in \[" --include=*.py .`(排除 scratchpad)**零命中**;`router_ablation.py:34` 直接 `SEED = tr.SEED`,`router_eps_scaling.py:48` 只派生 `BOOT_SEED = SEED+777`。`router_learned_raw_20260814.json` 顶层无多切分容器。
- `:768-769` LODO 里 `if m_tr.sum() < 20: continue` —— 该臂 `ph3` 全列保持 0.0,而 `policy_pick` 仍会对它取 argmax:**一个从未训练的臂拿到 p̂=0 并参与比较**,无计数无告警。
- LTT 的 `binom_cdf`(`:496-507`)按**独立题目**算尾界,而 5511 里 10 个 LoCoMo uid 承载 2286 题、450 行是**同一道题的重复计数**。无任何 uid 层 cluster bootstrap。

**`router_eps_scaling.py` 的循环诊断**

`:126-151` 对固定池做**有放回 bootstrap** 子采样(25/50/75/100% × 200 次),再拟合 `ε_ub(n) ≈ p_inf + c/√n`(`:157-161`)。**有放回重采样的风险期望恒等于原池经验风险,与子样本量 m 无关**,所以"四档 risk 均值几乎不随 n 变化"是构造上的必然,对"增加真实新数据能否降风险"零信息量。8 个拟合点实际是**两条不同高度的平线**(两个池经验风险不同),`1/√n` 拟合把池间水平差归给有限样本项,导致 `p_inf = 9.27%` **高于全部 8 个观测点**。结论(ε=5% 不可达)从 calib 池单点 CP 上界 9.95% 即可直接得到,**曲线本身不构成论据**。

**注释与代码不符**

- `train_router.py:18-20` docstring 称复刻了 `_slot_match`,**该函数在本文件根本不存在**(grep 全文只有 docstring 这一处提及)。
- `:47` 出处行号注释"(qvf_router.py 76-81 / wt_qvf_prototype.py 269-280)"**两处都错**(`normkey` 在 90-95;`_norm` 在 370-371)。
- `:903-906`/`:924`/`:926-928`/`:1049-1052`/`:1123-1126` 报告的判决段落把结论与数字**硬编码进 `A(...)` 字符串**("oracle-gap ≈9%"、"覆盖率 5511/5511"、"−19/−122/−143")。本次归档值恰与之一致,但**换一次数据文字就会说谎**;`:926-928` 的受限动作空间明细加总 **1955**,而实际 `restricted = 1954`(1 题同时缺 rt 与 prompt 被重复计)。
- `router_eps_scaling.py:351-357` "读图要点"把 bootstrap 的数学恒等式当成"结构性下界的标准诊断特征"。

**唯一真正的可复现性硬校验**在 `router_ablation.py:111-124`:用 `assert` 核对 `cv_fold` 逐题一致、`|p̂−p̂_stored| ≤ 5.01e-5`。同文件 `hybrid_eval`(`:55-79`)对 `picked_arm=None` 的行会 `KeyError`,v42_final 无 None 所以没炸,但**无断言保护**。

---

### 1.5 编译-执行臂(`scripts/complex_query_arm.py` + `scripts/qvf_algebra.py`)

**实际行为**

- 这是**第四条独立通路**(`mode: complex_arm`,归档 3276 行),不经过 `run_decisive_stale`,也不被 `qvf_router` import。
- 平面编译器 `complex_query_arm.py:292-317`:`messages.parse` + `CompiledPlan`,重试 3 次,全失败回落 `{"op":"current", 全 null}` 且 `ok=False`(该 dict **缺 `slot2`/`anchor_index` 两键**,与成功路径行形状不同)。
- 代数编译器 `qvf_algebra.py:793-835`:`messages.create` 纯文本 + 手工 JSON 抽取(`_json_candidates`,`:783-790`,**从后往前**取模型改口后的最终版本),重试 3 次,全失败回落 `AlgebraProgram(expr=MidExpr(prim="PICK", of=LeafExpr(prim="SELECT"), index=-1))`。
- 执行 `complex_query_arm.py:602-728` 零 LLM。共同前置:`_select_pool`(键控 `(owner, slot_class)` 分组,`:353-380`)→ 计数类 op 过 `_hygiene_pool`(`:467-489`)→ `_chain` 相邻同值合并(`:423-435`)。
- **截断两处**,均在 `:105-106`:`EVIDENCE_CAP = 12`、`_SPAN_CAP = 240`。
- 读者提示词拼装 `:757-768`:证据行 → `[memory summary] <derived>` → `TODAY'S DATE` → `USER'S NEW MESSAGE`。

**死路径**

| 项 | 位置 | 判据 |
|---|---|---|
| 平面编译 fallback(`op=current` 空计划) | `:316-317` | 3276 条 `complex_arm` 行 `plan.op` 中 `current` **0 次**;13 条 `compile_ok=false` 全部来自代数臂 |
| `current` / `premise_check` 算子执行与渲染 | `:653-667` | 各 **0 次 / 3276** |
| `point_in_time` 算子 | `:668-684` | **1 次 / 3276**,实质零覆盖 |
| **代数 11 算子宏路径整体** | `qvf_algebra.py:401-426` MACROS + `:686-696` 宏分派 + `:430-597` 三个宏渲染器 | `QVF_ALGEBRA=1` 时 `compile_plan` 被重绑(`complex_query_arm.py:748-753`)必产 `expr` 计划,故带 `op` 的宏分支**在任何 LLM 跑批里不可达**:410 条 expr 行、**0 条带 op**。宏表只被零 LLM 的 `scripts/algebra_parity.py` 执行过 |
| `AGG fn=by_year` | `qvf_algebra.py:350-355` | 410 条 expr 的 AGG.fn 分布 `count_elements 109 / argmax_dur 121 / count_changes 61 / distinct_ordered 18`,**by_year 0** |
| `PICK.value` 锚 / `PICK.exclude_last` | `:316-322` | 1 次 / **0 次** |
| `ASOF` 的 `date` 字面量分支 | `:365-367` | 74 次 ASOF **全部**用 `at` 子表达式 |
| `AGG(WINDOW(TAGSET))` 组合 | — | 归档 **2 次**,标签链上的窗口语义基本未测 |
| `QVF_COMPILE_SPEC=1` 的独立效果 | `complex_query_arm.py:82` | 无法确定:不落盘,且与 `QVF_ALGEBRA` 互斥 |
| `QVF_TAG_LATTICE=1` × `QVF_ALGEBRA=1` 组合 | `:73`、`qvf_algebra.py:278` | 无法确定是否被执行 |

**静默回落**

1. **[最高危]** WINDOW 界声明但解析不出时该侧一律判负 → 窗内子链清空 → **AGG 照常输出一个自信的数值**(`qvf_algebra.py:256-263`、`:302-310`)。实测 410 条 expr 行里 **121 行(29.5%)是 AGG over 空窗且 `evidence_n=0`,全部判错**(count_elements 60 / argmax_dur 38 / count_changes 23)。`_render_direct`(`:668-671`)照样写 "Computed <fn> over the dated records above: <值>. This computed result IS the answer; do not recount."——**证据 0 条、结论满分自信**;`count_changes` 在空链上给出 `len(chain)-1 = -1`。
2. **[严重]** 代数编译三次全败的 fallback **类型检查放行**:`check_expr` 对 SELECT **不检查 slot 是否为 None**(`:185-186` 直接 `return "Chain"`),于是 `compile_wellformed=True` 但 `SELECT(slot=None)` → `_select_pool(recs, "")` → `_slot_match(r.slot, "")` → `wt_qvf_prototype.py:376-377` 对空串 `return False` → **池空 → 证据 0 条**。触发处:`results/wsc_s8_algebra_dev_r2.jsonl` **12 条** + `wsc_s8_algebra_test.jsonl` **1 条**,共 13 条全判错。
3. **[严重]** 执行抛异常(代数类型检查拒绝)时记 `wellformed=False`、证据置空、derived 换成 `[compile rejected: ...]`,然后**照常调读者、照常送判官**(`complex_query_arm.py:868-876`)。`dev_r2` 14 行、`dev_r1` 1 行。编译器拒绝被记成读者答错,不被排除在分母外。
4. **[严重]** 证据包为空时(默认 `QVF_FAIL_CLOSED=0`)仍把 `(no matching records found in memory)` 交读者猜(`:640-648`)。实测 **863/3276 = 26.3%** 的 `complex_arm` 行 `evidence_n=0`,其中未 fail-closed 的 828 行为 325 false + 503 null。
5. **[中]** `_load_records`(`:330-337`):卡片文件不存在或 JSON 坏掉都返回 `[]` —— **卡库路径拼错会表现为"这个人没有任何记忆"**。3276 行里只有 76 条记了 `card_library`(且那是 `writeside_sensitivity_part2.py:131` 外挂加的)。
6. **[中]** `_pdate` 解析失败静默返回 None(`:345-350`),脏日期表现为"状态更少"。
7. **[中]** `_query_date` 的 `+1 月` 算式 except 返回空串(`:789-803`),`TODAY'S DATE` 整行消失,读者失去时间锚点而无标记。

**截断与结论的不对称(本模块最锋利的机制缺陷)**

`EVIDENCE_CAP` 只砍证据、**不砍结论**:`derived` 在未截断的全链/全命中集上算(`:615-637`、`:649-727`)。**57 条归档行 `evidence_n == 12`**(tag_trend 51 / count_changes 2 / first_last 2 / longest 2),分布在 `results/wsc_s7_arm_full.jsonl`、`wsc_s7_arm_full2.jsonl`、`s7_220_guardrail_lattice_arm.jsonl`(各 16)。用 `results/wt_cards_tagged/` 重算证明是截断:`chain002-4781d89c_s7a` 实有 **20** 条精确命中、`confirm007-902a1ada_s7a` **21** 条、`confirm023-512107d2_s7a` **16** 条,都被砍到 12。而 `tag_filter` 的结论行逐字写着 "every one is listed above with its date"(`:621-625`)——命中 >12 时**这句话是假的,且被当指令原文发给模型**(该臂归档里 tag_filter 恰好未超 12,风险已在、覆盖为零)。

**结论行的权威性不被任何机制保证**

结论行被伪装成一条"记忆摘录"(前缀 `[memory summary]`),与真实证据行同处一段;系统提示词(`:279-285`)从未声明它是权威计算结果。**读者完全可以无视它,而且实测在无视**:`results/wsc_s8_algebra_dev_r3.jsonl` 中 `wikiM003-Q106386024_s8wcb2` 的 derived 给出了 `count_elements` 的计算值,读者答 "I don't have any information about when you moved to Bogotá ... this is the first time we're chatting.";`wikiP54008-Q54622403_s8cd` 给了 `argmax_dur` 结果,读者答 "This appears to be our first conversation."。另有内在冲突:系统提示词硬性要求 "1-3 sentences"(`:283-284`),而 `trajectory`/`tag_filter`/`tag_trend` 的结论行要求"列出每一条及日期",两条指令方向相反,无协调机制。

**旗标实际效果**

- `QVF_ALGEBRA`:重绑 `execute_plan`/`compile_plan`/`COMPILE_PROMPT`/`CompiledPlan` 四个模块级名字(`:735-753`),关时确实不 import。**但重绑后必产 expr 计划,导致它自己带来的 11 算子宏路径永远走不到。**
- `QVF_RENDER_ANCHORS`(`qvf_algebra.py:82`):注释准确(只影响 `_render_direct` 的 Value 分支;`eval_expr` 无论真假都算锚记录,`:311-314`)。但**它不落盘**。
- `QVF_OPEN_KEYS`(`complex_query_arm.py:67`):注释 `:62-64` 描述的是 `qvf_router` 的行为。在本模块唯一作用是让 `_select_pool` 的**空池救援**分支被启用(`:393-400`),键控分组逻辑(`:365-378`)完全不看它。
- `QVF_COMPILE_SPEC`(`:82`):注释自陈"`QVF_ALGEBRA=1` 时不生效"——**代码确实如此**,这是一处诚实标注的旗标间耦合。
- `QVF_TAG_LATTICE`(`:73`):关时零副作用(延迟 import)。但 `qvf_algebra.py:278` 的 TAGSET 原语复用同一个 `_tagged`,**代数臂会连带受它影响**,两处注释都没提。

**注释与代码不符**

- `:2` 模块 docstring "证据包(带日期条目行,**上限 12 条**)+ 计算结论" —— 未说上限只作用于证据、结论在全集上算。
- `qvf_algebra.py:25-27` docstring 列 AGG 的 fn 只有 4 个,实际 `_AGG_FNS`(`:64-65`)有 5 个,**多出的 `count_elements` 恰是归档里用得第二多的(109 次)**。
- `qvf_algebra.py:600-603` `_render_direct` 标着"仅新组合走此路(未见组合用)",实际这是**唯一**被真实跑批执行的渲染路径(410/410);宏渲染才是没人走的。
- `complex_query_arm.py:293-297` docstring 说回落"流程不中断",未提返回 dict 缺两个键、落盘行形状因此不同。

---

### 1.6 跑批 harness 与判官(`scripts/run_decisive_stale.py`、`framing_arm.py`、`wsc_direct_arm.py`、`qvf/judge.py`)

**结构性纠正:这里没有"一个 harness 跑四臂"。**

`run_decisive_stale.py` 是一个 **34 个 `mode` 的单臂跑批器**(`:2142-2250`),每次 `--conditions` 选若干 mode,逐题逐 mode 独立跑、独立落盘。四臂路由是**离线重放**。从归档 `mode` 字段反查对应关系:

| 文档口径的"臂" | 实际 mode | 归档行数 |
|---|---|---|
| rt 臂 | `minimal_rules_species2` | 19586 |
| wt 臂 | `wt_qvf`(`wt_qvf_prototype.py`) | 7989 |
| direct 臂 | `dense_direct` | 22119 |
| prompt 臂 | `warned_direct`(`_WARN_INSTRUCTION`) | 13764 |
| —(第四条独立通路) | `complex_arm` | 3276 |
| —(其对照直读) | `wsc_direct` | 1257 |

**三种 "direct" 是三套不同检索**:`mode="direct"`(984 行)默认 `retriever_cls=BM25Retriever`(`:88`、`:2143`)——**是 BM25 不是稠密**,`prompted`/`filtered`/`repaired` 同;`dense_direct` 才走 `_dense_retriever_cls()`(`:2157-2159`);`full_context_direct`(`:134-144`)不检索。`TOP_K = 10`(`:46`),`--top-k` 直接改模块全局(`:1876-1877`),**不落盘**。

**prompt 臂的落盘缺口**:`_WARN_INSTRUCTION`(`:107-113`)被拼在**问题文本尾部**(`:124-126`),落在 user 消息的 `USER'S NEW MESSAGE:` 之后,不进 system;覆盖范围是该次跑批**全部题目,无条件无过滤**。而 `:2271` 写入的是 `instance.question` ——**未拼警告的原文**。实测 13764 条 `warned_direct` 行中 `question` 含 `[Instruction:` 的有 **0 条**。**这个现在承担 49.5% 路由流量的臂,到底给读者发了什么,归档里不可重建。**

**`framing_arm.py` 的猴补不落盘**:`:18-24` 与 `:27-40` 在导入期替换 `qvf.generator.BASELINE_GENERATOR_SYSTEM_PROMPT` 与 `format_baseline_generator_input`,然后调 `rds.main()` 固定 `--conditions dense_direct`(`:56-57`)。产出行 `mode` 仍是 `dense_direct`,**framing 版与非 framing 版在架构上不可区分**(22119 条里哪些是哪个只能靠文件名猜)。

**跨模块副作用**:`wt_qvf_prototype.py:25` 在**模块导入期**执行 `os.environ.setdefault("QVF_EMBED_BACKEND", "openai")`,而 `complex_query_arm.py:48` 无条件导入它 —— **导入一个模块会静默改掉另一个模块的检索后端默认值**。`wsc_direct_arm.py:24-26` 明确记录并规避了这一点,`complex_query_arm` 自己没有任何提示。

**rt 臂的实际执行路径**(`:539-1313`,全模块最长函数):稠密 top-10 →(可选 `_USE_MMR`)→ `agg_guard` 正则透传(`:564-581`,在付抽取钱之前)→ 一次 `extract(scoped=True, contract="species2")` → `abstain_guard`(`:600-633`)→ scope gate + **确定性日期覆盖**(`:638-651`,归档 1186 行带 `scope_overridden_by_date`)→ `past_or_change` 分支的四种链补全扫掠(`_resweep` `:754-768` / `_sibling_sweep` `:770-786` / `_extract_sweep` `:788-858` / `strong_extractor` 重抽 `:873-905`,**每种都是额外一次抽取调用**)→ 点查/轨迹判决(月份名解析成**月末 31 日**,`:908-926`)→ 物种裁决(`:1069-1289`)→ 前提反驳注(`:1217-1243`,仅 species2 + subtractive,归档 627 行)。

`filter_strategy` 全库 30 个取值的真实流量:`rules_conflict_latest` 3968 / `rules_replacement_subtract` 3841 / `rules_admit_noop` 3729 / `scope_pass_point_in_time` 3614 / `scope_pass_trajectory` 3064 / `scope_pass_history` 2896;尾部 `rules_cessation` 30、`rules_conflict_surgery` 26、`ledger_pass_history` 12。

**死路径**

| 项 | 位置 | 判据 |
|---|---|---|
| `conflict_fallback_full` | `:1640-1642` | 全库 `filter_strategy` census **0 行** |
| `ledger_pass_history_fallback` | `:381` | **0 行** |
| `minimal_rules_v6` 的**当前实现** | `:1447-1466` | AST 校验:`premise_note` 既非 v6 参数也未在体内赋值,也无模块级同名变量 → 全局查找 → **主路径必抛 `NameError`**。归档 75 条 v6 行 0 errors 且含会走到 `:1448` 的 `filter_strategy`,说明是 08-02 旧代码产物 —— **现版本零覆盖且旧结果不可复现** |
| `time_sweep` 链头救援 | `:944-952` | **2 行 / 19586** |
| species2 内 `strong_extractor` 死路升级 | `:873-905` | **13 行 / 19586(0.07%)** |
| `repair_slotted` 槽位感知修复查询 | `:1030-1039` | 只有 `mode=minimal_rules_srepair` 用(`results/srepair_t2.jsonl` 150 行,该文件全库零引用) |
| `abstain_guard` | `:600-633` | 96 行 `no_valid_record_note`,集中在 3 个 abstain 文件 |
| `_USE_MMR` 分支 | `:558-559` | `--mmr` 只在 `run_minimal_rules` 内被检查,且 `BM25Retriever` **没有 `retrieve_mmr`** → 对 `direct`/`dense_direct`/`prompted`/`qvf_v4` 是**静默空操作** |
| `qvf/generator.py:101-118` `PromptOnlyGenerator` | — | 34 个 runner 无一构造它 |
| `--redo-empty` | `:2123-2135` | 无法确定是否被执行;它会用 `'w'` 重写输出文件,中途崩溃将造成**不可逆行丢失** |

**静默回落**

1. **[最高危]** `qvf/judge.py:149-156` 判官两次失败后回落到 `gold in response` 子串包含启发式,**返回真 True/False 而不是 None**,唯一痕迹是 `judge_reason` 的 `"FALLBACK containment heuristic"` 前缀,**没有独立布尔字段**,三个跑批器都不过滤它。全库 **629 行**这样判出(288 判对 / 341 判错)。
2. **[严重]** `premise_note` 参数(`:544`)是 `run_minimal_rules` 的形参但**函数体内零次读取**(AST 校验:Load 次数 0)。`mode=minimal_rules_pnote`(`:2209-2212`)传 `premise_note=True` + contract 默认 `'v5'`,而真正的前提反驳注(`:1217-1243`)要求 `contract=="species2"` 且 subtractive —— **两个条件都不满足**。结论:`minimal_rules_pnote` 与 `minimal_rules_v5` **行为完全等价**,`results/pnote_t1.jsonl` 的 165 行**不构成任何 premise-note 消融**。
3. **[严重]** `query_gate` fail-open(`:229-250`):任何异常返回 `(True, 0, 0)`,失败与真 `invoke=True` 不可区分,行里只有 `gate_invoked=true`、token 记 0。
4. **[严重]** `run_ledger_v8` 槽位挑选 LLM 调用 `except: pass` → `picked=[]` → `scope='current'` → `_fallback('ledger_no_slot')`(`:326-341`)。**API 故障被记成"账本里没这个槽位"**:归档 36 行(占 ledger_v8 111 行的 32%)。
5. **[严重]** runner 抛异常 → `record = {'error': traceback}`,随后**照常补上 question/gold/mode/latency 并写盘**(`:2261-2265`)。全库 **304 行**;`results/wiki_direct_bm25.jsonl` 是 228/228 全 traceback(urllib3 连接错误),却是一份看起来完整的 228 行 jsonl。
6. **[中]** 判官异常 → `judge_correct=None`,而控制台聚合(`:2301-2317`)用 `a["correct"] += 1 if r.get("judge_correct") else 0` 而 `a["n"] += 1` —— **None 被当答错计入分母**。
7. **[中]** `qvf/generator.py:78-79` `stop_reason=='refusal'` → `answer='[refused]'` 且 **usage 归零**;`stop_reason=='max_tokens'` 连标记都没有,截断答案直接送判官。

**成本口径的三个缺口(全部 CONFIRMED)**

- **判官 token 从不落盘**:`qvf/judge.py:100-102` 有 `total_usage` 累加器,但 `run_decisive_stale.main()`、`complex_query_arm.run()`、`wsc_direct_arm.run()` **全都不读它**(全库只有 `judge_cost_measure_20260816.py`、`s8_render_fix_judge_cost.py`、`b1_run_p39.py`、`writeside_sensitivity_part2.py` 读)。判官默认 `claude-opus-5`(`qvf/config.py:25`)——**最贵的一次调用完全不在任何行的成本里**。
- **嵌入 token 全库零计量**:`OpenAIDenseRetriever` 的 embedding 调用无任何计数。所有 "rt 21.9k tok vs direct 1.9k tok" 型对比都缺这一项。
- **单行 usage 是抽取 + 全部扫掠 + 读者(+ gate)的求和**(`:1055-1056`、`:827-828`、`:896-897`、`:1017-1018`),无法拆分;gate 的 token 折进总数且失败时记 0。

**旗标实际效果**

- `QVF_SCAN_BUDGET`(`:52-66`):注释写 "per pipeline invocation"。实际 `_scan_taker()` 在每次 `run_minimal_rules` 调用时新建(`:592`),而 `run_qvf_final` 死路升级时会**再调一次**(`:413`/`:419`),`run_minimal_rules_escalated` 同理(`:282`/`:288`)。**`QVF_SCAN_BUDGET=N` 对升级题实际允许 2N 次额外抽取轮。**
- `QVF_LOCAL_EXTRACTOR`(`:1985`):选 `LocalSlotExtractor`(`engine_bridge.py:788`,ollama 本地零 API)。**与建卡路径完全无关**,替换的是遗留决定性实验的读取时抽取器。
- `--items` 对 `longmemeval/locomo/memconflict` 的语义是 `instances[: items*3]`(`:1933`,注释自称 "keep --items semantics loose")——`--items 100` 实际最多 300 题。名字与效果不符且不落盘。

**注释与代码不符**

- `:1-8` 顶部 docstring 仍写 "direct vs prompted+engine vs oracle+engine" 三条件与 §3 预注册判据,而今天该文件有 34 个 mode、主力是 `minimal_rules_species2`/`qvf_final`;`--conditions` 默认值仍是 legacy 的 `direct,prompted,oracle`(`:1821-1823`)。
- `:116-120` `run_warned_direct` docstring 自陈 "The prompted condition is NOT this ... a referee pass caught the mislabel" —— 已修正的历史误标,但 **mode 名 `prompted` 保留至今**(718 行归档),名字仍在误导。
- `:1063-1067` 注释说 needs-current recognition sweep 已被 "Removed",但归档仍有 `nc_sweep_added`(18 行)、`early_sweep_added`(6)、`sweep_debug`(6)、`scope_pass_point_in_time_hedged`(14)——**全部是现版本源码无法产生的取值**,文档只说"移除",没说这些归档行因此不可复现。
- `wsc_direct_arm.py:8-9` 称检索器"缺省 ollama nomic-embed-text",实际缺省取决于同进程是否已导入 `wt_qvf_prototype`;`:24-26` 自己也写了这个陷阱,**两处说法互相矛盾**。

---

## 二、零实验覆盖清单(本报告最重要的一节)

合并去重后 **26 条**。按"是否有主张依赖它"排序:**11 条有主张依赖**(A1、A4、B1、B2、B5、C2、D1、D2、D3、F1、F2),15 条无。

### 有主张依赖(11 条)

| # | 能力 | 实现位置 | 判断它从未被测的依据 | 有主张依赖 | 补测成本 |
|---|---|---|---|---|---|
| A1 | `source_span` 逐字校验 | `engine_bridge.py:144-147`(仅描述);docstring `:12-16` 声称已 enforce | **能力从未实现**,故属性从未由系统自身测量:建卡路径无校验函数,无 `extraction_report`,无归档产物含 span 校验统计。本轮 9–11% 违约率是首次测量 | **是,核心**:"硬约束一条,可用一行代码校验"整段推理建立在此 | **$0**,纯字符串包含检查,一次全库扫描 |
| A4 | **多主体(owner≠user)正确性** | `qvf_router.py:274-275` owner 过滤;`engine_bridge.py:148` `entity`;`wt_qvf_prototype.py:326` `QueryFocusMini.entity` | `entity` 两端零消费;`wt_cards_v42` 具名 owner(Rachel/Luna/Emily…)总计仅百余条,`"user"` 18923 条;LoCoMo/LoCoMo-full 一人称命中率 **0/300、0/1986** | **是,最锋利**:LoCoMo 负结果的根因被定为"说话人库未键控",而该归因依赖的 owner 分组防护**从未在任何真实多人库上被检验过**。**这条归因是假说,不是实测** | 中:需建一个真多主体键控卡库(约 10 uid × 建卡成本)+ 一次 300 题重跑 |
| B1 | `current` / `premise_check` / `point_in_time` 三个算子的端到端行为 | `complex_query_arm.py:653-684` | 3276 条 `complex_arm` 行 `plan.op` 计数:`current` **0**、`premise_check` **0**、`point_in_time` **1** | **是**:"11 算子构成读取侧操作闭集";`premise_check` 被当作三条防线之一("答前 premise_check"),**在计分跑批里一次都没跑过** | 低:构造 30–50 题定向题集,一次跑批 |
| B2 | 代数 **11 算子宏路径**整体 | `qvf_algebra.py:401-426` + `:686-696` + `:430-597` | `QVF_ALGEBRA=1` 必产 `expr`(`complex_query_arm.py:748-753`),归档 410 条 expr、**0 条带 op** | **是,需精确限定**:护栏(MACROS vs 平面逐字节等价 347/347、874 次)是**纯符号事实、成立**,但**护栏保护的宏路径与被 LLM 评测的 `expr` 路径不是同一条** | **$0**:加一句限定即可;若要真测需让编译器产 op 计划 |
| B5 | 能隔离"谁做算术"的第三臂(evidence-only,无 derived) | 全库 `no_derived`/`evidence_only` 零命中 | 该臂不存在 | **是**,但已被文档完整自认并列为最短路径第 1 项 | 低:一个旗标 + 一次跑批 |
| C2 | `QVF_LLM_INTENT` 的**路由效应** | `qvf_router.py:221-243` | `router_intent_cache.json` 300 条键前缀全是 `intent_eval`;7 份路由日志无该旗标字段。**从未跑过一次带该旗标的路由跑批** | **是,作为缓解论证**:"该正则在生产题面上仅命中 1.3%,受影响题量小"。而正则漏检实测 —— 73 题字面即事件算术,一条不中,66 题被判给 prompt/wt。**该缓解是用一个已知漏检 84% 的判定器度量出来的** | 中:5511 题 × 一次 haiku 分类 ≈ 一次聚焦跑批的成本 |
| D1 | 学习路由的**切分敏感性** | `train_router.py:40` 单一 `SEED = 20260814` | 本轮 grep 三个脚本无任何多种子循环;`router_learned_raw_20260814.json` 顶层无多切分容器 | **是**:"方向经 3 种子稳健"与"3 种子 6 验 2 败"两条互相矛盾的表述**都无实现** | **$0 API**:纯离线重放,加 `for seed in [...]` 循环,约 1 小时工 |
| D2 | headline λ 的**样本外验证** | `train_router.py:648-668`;`router_ablation.py:139-146` | `same_acc`/`same_cost`/`lam_star` 全在全量 5511 上扫 17 个 λ 选出,无留出集 | **是**:"同准确率省 57.5% token",而准确率余量只有 **+0.15pp ≈ 8 道题** | **$0 API**:复用现有 40/20/40 切分重选 λ |
| D3 | 聚类稳健的置信界 | `train_router.py:496-507` `binom_cdf` | 按独立题算尾界,而 10 个 LoCoMo uid 承载 2286 题、450 行是同题重复;无任何 uid 层 cluster bootstrap | **是**:证书主张的界偏乐观 | **$0 API**:加 uid 层 bootstrap,约半天工 |
| F1 | **MAB fact-consolidation 整卷** | `data/mab_fc_*` 8 个配置 | 只跑了 `sh_6k` 与 `sh_262k` **两格**,6 格零覆盖 | **是,反向**:见第六节 | 中:6 格 × 100 题 |
| F2 | S8 held-out p2 的**直读对照臂** | `scripts/wsc_direct_arm.py`(独立 runner) | 61 题卷上三个编译臂变体(16.4/18.0/21.3%)全跑了,**唯独没对 p2 调用过直读臂一次**;同族 test 卷上直读是 **70.1%** vs 编译臂 49.3% | **是**:该卷三个数字是当前最锋利的自认边界,**却没有同卷基线** | **低**:61 题 × 一次直读 ≈ 几分钟、$1 量级 |

### 无主张依赖(15 条)

| # | 能力 | 位置 | 判断依据 |
|---|---|---|---|
| A2 | `implies_stale_slots`(每卡都抽"这次更新让哪些槽位过期") | `engine_bridge.py:181-186` | **全库零消费**(grep 仅命中定义/mock/docstring)且**全库文档零提及**。建卡契约里唯一的跨槽位依赖信息,付了 token,从未被利用也从未被披露 |
| A3 | `claim` / `slot_cardinality` 字段 | `engine_bridge.py:151`、`:152-155` | `claim` 仅遗留引擎 `:576` 用;`slot_cardinality` 唯一消费点是 `write_persession.py:283`,生产读取路径三处(read_phase / complex_query_arm / store_index)一处都不读 |
| A5 | `temporal_relation` **标签本身** | `engine_bridge.py:156-168` | read_phase 只用 `relation_target_record_ids`。Rule 3 那套 replacement/cessation/contradiction/unresolved 分类准确率**对 wt 臂最终答案无直接影响**,也从未单独测量 |
| B3 | `AGG fn=by_year` / `PICK.value` / `PICK.exclude_last` / `ASOF` date 字面量 | `qvf_algebra.py:350-355`、`:316-322`、`:365-367` | 归档 0 / 1 / 0 / 0 次。`tag_trend` 与 `premise_check` 两个宏的语义在真实跑批里零覆盖 |
| B4 | `AGG(WINDOW(TAGSET))` | — | 归档 2 次 |
| C1 | `QVF_FAIL_CLOSED` 在 **wt 臂** | `wt_qvf_prototype.py:604-605` | 7989 行 `wt_qvf` 中 `wt_fail_closed` **0 次**;而它本应是本报告 §三 S2 的检测器,条件却排除了卡片库缺失 |
| C3 | `QVF_GATE_DEPTH` 非 3 取值 | `qvf_router.py:385-386` | 唯一非读取引用是 `newdom_router.py:33` 的断言;该阈值决定 rt/prompt 分界(393 vs 2729) |
| C4 | `QVF_OPEN_KEYS` 单开;`OPEN_SLOT/KEYS` 在主系统(5511 题) | `qvf_router.py:264-269` | 两个调用点都同时开两个,且 OPEN_SLOT 是超集;主系统零覆盖,只在 newdom-P69 100 题跑过一次 |
| C5 | `QVF_CARD_STRICT` 的效果 | `wt_qvf_prototype.py:138-157` | 只在 **8 个 uid / 32 题**上被真正观测过(消费它的两份归档里 40/44 与 7/11 个 uid 根本没有卡片) |
| C6 | 冻结 `route()` 的逐题产物 | `qvf_router.py:446` | 旗标全关时不写路由日志,**该配置的逐题决策永久不可复核** |
| D4 | prompt 臂反事实覆盖(MNAR) | `framing_tlcot_arm.py:59-62` | 覆盖 4652/5511,缺的 859 题(LoCoMo 110 + LoCoMo-full 749)恰是手写路由没派给 prompt 的题。已披露,掩码不能修复 |
| E1 | `write_persession` 两层拆分方案端到端 | `write_persession.py:286-352` | 6 个 persession 库共 12 个 uid 文件,7989 行 `wt_qvf` 无一行能追溯到它;且 persession 卡带 `stated_date_effective`/`slot_raw`,read_phase 读 `stated_date` —— **即使读了也读不到有效日期**。**这套方案解决了 id 碰撞与顺序泄漏两个真实缺陷,却零端到端覆盖** |
| E2 | `conflict_fallback_full` / `ledger_pass_history_fallback` / `time_sweep` / `escalated_extraction` / `minimal_rules_v6` 现版本 | `run_decisive_stale.py:1640`、`:381`、`:944`、`:873`、`:1447` | 0 / 0 / 2 / 13 行;v6 现版本必抛 NameError |
| E3 | `QVF_CATALOG_BUDGET` 对卡片图结构的影响 | `wt_qvf_prototype.py:260` | 代码当纯成本旋钮,实际决定 id 碰撞率;**无任何归档实验对比"同一 uid 单批 vs 多批"** |
| E4 | 卡片库完整性检测 | — | 无 uid 覆盖率断言,`len(cards)` 不落盘。`wt_read_strict3_*` 两份归档在 91%/64% 题无卡片的情况下产出,**该事实无法从产物自身发现** |
| F3 | `data/wsc_s8_v2.jsonl` 的 106 道 unseen 中 45 道 | — | 从未被任何臂跑过 |

---

## 三、静默失败与失败伪装成结果

全库 154,022 行。类别间有重叠,末行给并集上界。

| # | 位置 | 触发条件 | 会污染哪类结果 | 归档中实际触发的证据 | 受影响行数上界 |
|---|---|---|---|---|---|
| S1 | `qvf/judge.py:149-155` | 判官两次调用失败 | **任何按 `judge_correct` 汇总的准确率** | `judge_reason` 以 `FALLBACK containment heuristic` 开头。按 mode 统计:`final2_lmek_h45` dense_direct **37/78=47.4%**、species2 **38/78=48.7%**;`final2_lmet_h45` species2 **59/133=44.4%**;`final2_lmek_gpt` 27/78 与 29/78;`final_chain_sonnet_direct` 62/212=29.2%、`_warned` 59/212=27.8%。对照:`wtqvf3_lmeku`(64.10%)与 `prompt_rows_lmeku_tlcot`(92.31%)**FALLBACK 为 0** | **629**(288 判对 / 341 判错) |
| S2 | `wt_qvf_prototype.py:421` | 卡片文件不存在 | **整条 wt 臂的分数**(该题实际退化为直读,行仍写 `mode="wt_qvf"`) | `wt_read_strict3_P39ext.jsonl` 40/44 uid 无卡片 → **160/176 行(91%)** `notes_n=0`,一一对应零例外;`_P551.jsonl` 7/11 uid → **28/44(64%)** | ≤ **190** |
| S3 | `wt_qvf_prototype.py:297-318` | 建卡某批抽取失败触底 | 卡片库完整性;下游全部 wt 分数 | `results/wt_cards/71017276.json`、`gpt4_fe651585_abs.json` 各 `usage_in≈142k`、`records=0`,两者都在 `wtqvf3_lmetr.jsonl` 里计了分(前者判 True) | 2 个卡片文件,牵连计分行 |
| S4 | `complex_query_arm.py:640-648` | 证据包为空且 `QVF_FAIL_CLOSED=0`(默认) | 编译臂全部准确率 | **863/3276 = 26.3%** 行 `evidence_n=0`(未 fail-closed 828 行:325 false + 503 null)。S8 heldout p2 三臂 28/25/23 行(46/41/38%);S7 三份 arm 各 108/220 | **863** |
| S5 | `qvf_algebra.py:256-263`、`:302-310`、`:668-671` | WINDOW 界声明但解析不出 | **S8 全部代数臂结果**;`count_changes` 在空链上给 −1,而渲染行写 "This computed result IS the answer" | **121/410 expr 行(29.5%)**是 AGG over 空窗且 `evidence_n=0`,全部判错(count_elements 60 / argmax_dur 38 / count_changes 23) | **121** |
| S6 | `qvf_algebra.py:833-835` + `:185-186` | 代数编译三次全败 | 代数臂 dev 与 test 准确率;表现为 `compile_wellformed=True` 的正常行 | `wsc_s8_algebra_dev_r2.jsonl` 12 + `wsc_s8_algebra_test.jsonl` 1,全判错 | **13** |
| S7 | `complex_query_arm.py:868-876` | 执行抛异常(类型检查拒绝) | 编译器拒绝被记成读者答错,不排除在分母外 | `dev_r2` 14 行、`dev_r1` 1 行 | **15** |
| S8 | `wsc_s7_judge.py:419-420`、`s7div_judge.py:147-148`;`run_decisive_stale.py:2291-2293` | 判官异常 / `claims_n==0` / `store_tagged_n==0` | **P/R 口径的分母**;混合文件里无字段区分已判与未判 | `wsc_s7_judged_full2.jsonl` **108/220 行 P 与 R 同时为 null 且全是 `store_tagged_n==0`**,打印 P 0.966 / R 0.905 (n=112),按 0 计为 **P 0.492 / R 0.461**;`s7div_judged_test_*` 39 题里 34–35 题 `claims_n=0`,打印 `mean precision = 1.0000 (n=4~5)`;`openslot_repair_..._s5_arm_P69.jsonl` **33/75 行(44%)** `judge_correct=null` | **33 混合 + 910 全 null**(11 文件) |
| S9 | `wt_qvf_prototype.py:408-414`;`qvf_router.py:100-111` | 追加写 + `done` 收集吞异常;`load_arm` 后写覆盖前写 | 行级 vs 去重口径;prompt 臂在 STALE 两卷的成绩 | `mabfc_sh262k_qvf.jsonl` 195 行/100 qid,**95 行重复**、2 组判决矛盾(71.3% vs 70.0%);`prompt_rows_all.jsonl` **150 个 qid 两次,27 个(18%)判决相反**,谁胜出取决于参数顺序 | **95 + 150 + 7** |
| S10 | `qvf_router.py:187-201` | 聚焦三次全败 → 持久化默认值 → 必然判 `direct` | 路由分布与 direct 臂成绩 | 缓存中 **5 条**完全等于默认值(全在 LoCoMo-full,qid 已点名) | ≥ **5** |
| S11 | `qvf_router.py:100-111`、`:527-528` | 臂文件缺失返回 `{}`;null 折 False;分母恒为全卷 n | ROUTER 表格的臂列 | **STALE-full 的 wt 列打印 5.2%,wt 在其覆盖的 150 题上是 41.3%(差 8 倍)** | 表格级 |
| S12 | `run_decisive_stale.py:2261-2265` | runner 抛异常 | 整轮失败被归档成"完整"文件;不检查 `error` 键的脚本会读成 0% 准确率 | **304 行**带 `error`;`wiki_direct_bm25.jsonl` **228/228 全 traceback** | **304** |
| S13 | `qvf/generator.py:78-79`;`analyze_decisive.py:137-139` | 本地模型基线臂不记 usage;拒答归零 | **成本口径**:基线臂 token 分母为 0,并按 opus 单价给跑在 qwen3-4b 上的实验估价 | `decisive_stale_qwen3-4b.jsonl` 210/735 行(direct 105 + oracle 105)`token=0` 且 `reader_model=null` 而 answer/judge 为真(该子集 acc 56.2%);`heldout_stale_ctx16k` 630/1050;`lme_ku_ctx16k` 78/234(该子集 acc 78.21%,answer 如 `"25:50"`);`lme_tr_ctx16k` 133/399;`memconflict_ctx16k` 150/450 | ≈ **3,500** |

**上界与真实分布**:影响**准确率**的行 ≤ **约 2,800 行 ≈ 1.8%** 全库。但这个平均数没有意义——**按已发表单元看,最坏单元的受影响比例是 44%–91%**:

- LME-KU 直读 78.21% / rt 82.05%:**47%–49% 的行由判官回落判出**
- LME-TR rt 45.86%:**44.4%**
- S7 精确率 0.966 / 召回 0.905:**49.1% 的行被剔出分母**
- S7-div precision 1.0000:**87%–90% 被剔出分母**
- `openslot` P69 57.14%:**44% 未判**
- S8 heldout p2 三臂 16.4/18.0/21.3%:**38%–46% 行零证据**
- 影响**成本**的行 ≈ **3,500**,且这些卷的基线臂 token 分母为 0

**判官稳定性证据对失败类零覆盖**(本轮新):`results/judge_cost_measured_sample_20260816.jsonl` 155 行重判 99.35% 一致,但其中 `archived_judge_reason` 以 FALLBACK 开头的 **0 行**;该样本含 15 行来自 `lme_ku`,而该域 FALLBACK 占比约 47%(15 抽 0 的概率 ≈ 0.53^15 ≈ 6e-5)。`CONFIRMED`:该证据对判官失败模式零覆盖。`PLAUSIBLE`:抽样器可能按"judge_reason 可解析"筛过,故不指控刻意排除。

---

## 四、旗标实际语义表

全库 44 个 `QVF_*` 旗标。下表按"实际效果与名字/注释的偏离程度"排序;`QVF_MOCK` 等 6 个纯 plumbing 旗标合并在末行。

| 旗标 | 名字/注释所述 | **实际效果** | 关闭时是否逐字节等价 | 与其他旗标的隐式耦合 |
|---|---|---|---|---|
| `QVF_EXTRACT_TRUNC` | "抽取截断" | **与建卡完全无关**。`_etrunc` 只经 `_ewindow`(`engine_bridge.py:86`)被 `:740`/`:833` 用 —— 遗留读取时抽取器 payload。建卡用原始 `m.content`(`wt_qvf_prototype.py:253-255`) | 是 | **被 `QVF_HIT_WINDOW` 覆盖**(`:85-86` 先判 HIT_WINDOW),优先级只写在注释里 |
| `QVF_OPEN_KEYS`(router 侧) | `:44-45` "键控分组以 slot_class 字符串本身为键,other:* 一等公民" | **分组键与它无关**(`:283` 恒按 `(owner, slot_class)`)。唯一效果:让 `:264-269` 调 `open_slot.match_classes(use_embed=False)` | 是 | **被 `QVF_OPEN_SLOT` 完全吸收**(后者 `use_embed=True` 是超集);两个调用点都同时开 → 独立效果从未测量 |
| `QVF_OPEN_KEYS`(编译臂侧) | `complex_query_arm.py:62-64` 抄了 router 的描述 | 唯一作用是启用 `_select_pool` 的**空池救援**分支(`:393-400`);键控分组(`:365-378`)完全不看它 | 是 | 救援触发看 `(_OPEN_SLOT or _OPEN_KEYS)`,嵌入只看 `_OPEN_SLOT` → 两者非叠加关系 |
| `QVF_FAIL_CLOSED` | wt 侧 `:141-142` "卡片库在场但裁决链为空时标记" | 条件是 `_FAIL_CLOSED and cards and not notes` —— **`cards` 为空(卡库缺失)时不加标记**,恰恰漏掉最危险情形。归档**零次出现** | 是 | **同名旗标在 `complex_query_arm.py:68` 是完全不同的语义**(跳过读者调用),两处共用一个变量名 |
| `premise_note`(参数,非 env,但语义等价) | `mode=minimal_rules_pnote` 暗示 premise-note 消融 | `run_decisive_stale.py:544` 形参**体内零次读取**;真正的代码要求 `contract=="species2"` 且 subtractive,而该 mode 传 `v5` → **`minimal_rules_pnote` 与 `minimal_rules_v5` 行为完全等价** | — | `results/pnote_t1.jsonl` 165 行**不构成任何消融** |
| `QVF_ROUTER_KEYS` | `:33-34` "无键卡片回退词重叠" | 唯一效果是 `chain_depth` 里先试 `_keyed_depth`。**`results/wt_cards` 抽样 48473 条带 `slot_class` 的是 0 条 → 单独开启逐字节等于关闭** | 是 | 真正改变行为的是 `QVF_CARDS_KEYED`;且开它必使 `v2_active` 为真 → 冻结 `route()` 结构不可达 |
| `QVF_GATE_V2` | `:35-36` "按 (时序性 × 键控深度 × 整库形态) 四选一" | 加规则 1(事件算术直通,决定 71 题)与规则 5(时序薄链改 prompt,决定 **2729 题 = 49.5%**)。**规则 5 第二合取项在无键控卡片时恒为真** → "薄链才改派"退化为"**所有 rt 都改派 prompt**" | 是 | **× `QVF_CARDS_KEYED` 的耦合,注释完全没提**。实证:`route=rt` 的 393 行全部属于有 `wt_cards_v42/uid.json` 的 uid |
| `QVF_CARD_TAGS` | `engine_bridge.py:210` "QVF_CARD_TAGS=1 only" | `:209` 是 `if _CARD_TAGS:` 真值判断,`=2` 也进;字段描述固定说 "from the CLOSED SET",**与 =2 的开放标签提示词在同一次调用里自相矛盾**。产物证明模型服从提示词:`wt_cards_opentags` 8852 标签 **0%** 在闭集内 | 是 | 可与 KEYS 叠加(基底自动选 V4,编号 6→8);`=1` 与 `>=2` 互斥(`elif`) |
| `QVF_CARD_KEYS` | `:195` "EXACTLY one of: position\|employer\|..." | 类型是 `str`,**闭集从未校验**;且 `owner`/`slot_class` 在 wt read_phase **从不被消费** → 开它对 wt 臂唯一影响是提示词变长导致抽取分布漂移 | 是 | **× 存在即跳过**:`wt_cards_s8_heldout` 8 带 / 22 不带,却被当单一库读 |
| `QVF_SCAN_BUDGET` | `:48-54` "per pipeline invocation" | `_scan_taker()` 按 `run_minimal_rules` 调用创建(`:592`),升级路径调两次 → **实际允许 2N 次** | 是 | × `qvf_final` / `escalated` 的升级逻辑 |
| `QVF_CATALOG_BUDGET` | "卡片密度极高的内容可调小批预算" | **不是纯性能旗标**:批数决定 (a) 跨记录一致 slot 名能否成立,(b) `record_id` 是否碰撞,(c) 关系边能否跨批建立 → **改它改变卡片图结构** | 是(默认 320000) | 与 KEYS/TAGS 无耦合,但与读取侧的并查集/`by_rid` 强耦合 |
| `QVF_EMBED_BACKEND` | `:70-73` "必须只在跑批之间切换" | `wt_qvf_prototype.py:25` 在**导入期** `setdefault("openai")`,而 `complex_query_arm.py:48` 无条件导入它 → **任何同进程既导入前者又用后者检索器的脚本静默拿到 OpenAI 嵌入** | 否(导入顺序即可改变默认) | `wsc_direct_arm.py:24-26` 记录并规避,`complex_query_arm` 无提示。**不落盘** |
| `QVF_ALGEBRA` | 切换到代数编译器 | 重绑 `execute_plan`/`compile_plan`/`COMPILE_PROMPT`/`CompiledPlan` 四个模块级名字并额外写 `compile_wellformed`。**重绑后必产 expr 计划,导致它自己带来的 11 算子宏路径永远走不到** | 是(`:736` 的 if 守卫真实有效) | **使 `QVF_COMPILE_SPEC` 完全失效**(已诚实标注);连带影响 `_tagged`(经 `qvf_algebra.py:278`)故与 `QVF_TAG_LATTICE` 隐式耦合,两处注释都没提 |
| `QVF_CARD_TEMP0` | `:62-66` 明说 08-17 前历史库未固定温度、不可混用 | 唯一效果是 `_catalog()` 是否传 `temperature=0.0`。**代码没有任何机制落盘或校验这一点**,卡片文件无温度字段,唯一线索是 mtime | 是(`=0` 时与引入前等价) | `results/wt_cards_s8_heldout` 的 mtime **横跨默认值变更日** |
| `QVF_CARD_V5` + `_V5_VARIANT` | h1 / h2 / h1h2 | V5=1 时在所有其他旗标叠加完的基底后追加变体规则。**未命中的变体名静默回落 h1**(`:223`),日志与产物都不记变体名 | 是 | 叠加在最后,不覆盖前面字节 |
| `QVF_CARD_STRICT` | 严格建卡 | 只追加 `_CATALOG_STRICT_RULE`(`:148-157`),不改 schema | 是 | 可与任意旗标叠加。**实际只在 8 个 uid / 32 题上被真正观测过** |
| `QVF_GATE_DEPTH` | 规则 5 阈值,默认 3 | **同时**控制 `depth < D` 与 `_store_max_depth < D` 两个条件 | 是(默认 3) | **从未以非 3 的值运行过**;唯一非读取引用是 `newdom_router.py:33` 的断言 |
| `QVF_CARDS_KEYED` | 键控卡库路径 | 不是行为旗标而是数据路径,且**回落是逐 uid** 的:v42_final 的 1037 个 uid 里 416 走键控、621 回落 | 是(空值) | **同一次跑批混用两套量纲的深度定义**,产物 `keyed_depth` 字段无法区分 |
| `QVF_LLM_INTENT` | 事件算术判定换 LLM | 换 `is_event_arith` 为 haiku 单词分类。**在整合系统里从未生效** | 是 | 隐藏缺陷:`newdom_router.py:81` 调 `route_v2` 不传 bench/qid → `intent_of` 缓存键为常量 `"|"`,**该域所有题共用第一题的分类** |
| `QVF_OPEN_SLOT` | 槽位→类三级瀑布 | `match_classes(use_embed=True)`。**主系统(5511 题)零覆盖**,只在 newdom-P69 100 题跑过一次(15/100 改判) | 是 | 是 `OPEN_KEYS` 的严格超集 |
| `QVF_RENDER_ANCHORS` | `:67-81` 只影响 `_render_direct` 的 Value 分支 | **注释准确**(`eval_expr` 无论真假都算锚记录,`:311-314`,关时无人读取)。但**不落盘**:`s8_heldout_algebra_off_p2` 与 `_on_p2` 两份文件无任何字段记录它,只能靠跨文件 diff(61 行中 12 行 `evidence_n` 不同、35 行 answer 不同)反推 | 是 | — |
| `QVF_COMPILE_SPEC` | few-shot 换指称语义表 + 2 个域外示例 | 注释自陈 `QVF_ALGEBRA=1` 时不生效 —— **代码确实如此**,一处诚实标注的耦合 | 是 | 与 ALGEBRA 互斥。**不落盘 → 归档行无法区分两套提示词** |
| `QVF_TAG_LATTICE` | 标签格匹配 | 关时零副作用(延迟 import,`:453`);只改 `_tagged` | 是 | 代数臂经 `qvf_algebra.py:278` 复用同一 `_tagged` → **连带受影响,两处注释都没提** |
| `QVF_HIT_WINDOW` | 抽取命中窗 | 覆盖 `QVF_EXTRACT_TRUNC`(`engine_bridge.py:85-86` 先判它) | 是 | 优先级只写在注释里 |
| `QVF_LOCAL_EXTRACTOR` | 本地零 API 抽取器 | 选 `LocalSlotExtractor`(`engine_bridge.py:788`)。**与建卡路径完全无关**,替换的是遗留决定性实验的读取时抽取器 | 是 | — |
| `QVF_WRITE_PERSESSION` | 准入门 | 只是 `main()` 的门(`write_persession.py:424-427`),不改任何行为。`.env` 不含任何 `QVF_*` 键(已核) | 是 | `write_persession_batch.py:37-39` **import 门变量本身** → 只有一处判定 |
| `--top-k` / `--mmr` / `--items`(CLI,语义同旗标) | 全局检索策略 / 题量 | `--top-k` 直接改模块全局 `TOP_K`,影响所有 mode 但不影响 `wsc_direct_arm.py:60` 的独立副本;`--mmr` 只在 `run_minimal_rules` 内生效且 `BM25Retriever` 无 `retrieve_mmr` → **对 direct/prompted/filtered/repaired 静默空操作**;`--items` 对 3 个 benchmark 是 `items*3` | — | 三者**全部不落盘** |
| 其余 plumbing(`QVF_MOCK` 等 6 个) | — | 只影响是否发起真实 API 调用 | 是 | 归档里留下 48 条 `[mock answer]` 行 |

**跨旗标的总结论**:44 个旗标里,**注释描述与实际行为不符或严重不完整的有 11 个**(`QVF_EXTRACT_TRUNC`、两个 `QVF_OPEN_KEYS`、`QVF_FAIL_CLOSED`、`QVF_ROUTER_KEYS`、`QVF_GATE_V2`、`QVF_CARD_TAGS`、`QVF_CARD_KEYS`、`QVF_SCAN_BUDGET`、`QVF_CATALOG_BUDGET`、`QVF_EMBED_BACKEND`);**取值落盘的有 1 个**(`boundary_duel_20260816.jsonl` 的 `flags`);**存在隐式跨旗标耦合的有 7 组**。

---

## 五、实际测量矩阵与空格

### 5.1 v4.2 四臂矩阵(复刻 `qvf_router.py:115-177` 的 BENCHES,分数全部复算)

| 卷 | uid | 声明题 | 参评题 | direct | rt | wt |
|---|---|---|---|---|---|---|
| chain-212 | 53 | 212 | 212 | 64.2 | 76.4 | 80.7 |
| confirm-228 | 57 | 228 | 228 | 65.4 | 79.8 | 86.0 |
| stale-150 | 50 | 150 | 150 | 45.3 | 52.0 | 41.3 |
| wiki-P39 | 57 | 228 | **208** | 48.6 | 63.0 | 86.5 |
| wiki-P39-ext | 44 | 176 | 176 | 55.1 | 66.5 | 87.5 |
| wiki-P108-w2 | 51 | 204 | 204 | 62.7 | 81.9 | 92.2 |
| wiki-P108-ext | 69 | 276 | 276 | 56.2 | 78.6 | 94.6 |
| wiki-P54-w2 | 38 | 152 | 152 | 78.9 | 87.5 | 90.1 |
| wiki-P54-ext | 41 | 164 | 164 | 59.1 | 78.0 | 93.9 |
| **wiki-P551** | 11 | 44 | 44 | 81.8 | **代码写死 None** | 88.6 |
| LME-TR | 133 | 133 | 133 | 47.4 | 45.9 | 53.4 |
| LME-KU | 78 | 78 | 78 | 78.2 | 82.1 | 64.1 |
| LoCoMo | 10 | 300 | 300 | 80.3 | 81.0 | 69.3 |
| STALE-full | 400 | 1200 | 1200 | 41.0 | 42.3 | **wt 覆盖仅 12.5%** |
| LoCoMo-full | 10 | 1986 | 1986 | 69.4 | 72.2 | 58.6 |

**四个空格**

1. **wiki-P551 的 rt 臂被代码声明为不存在,产物就在盘上。** `qvf_router.py:154` 与 `train_router.py:119` 都写 `None`,而 `results/wiki_qvf_P551.jsonl`(08-11 23:15)有 44 行、qid 与 direct 逐一相同、`mode=minimal_rules_species2`、复算 **81.8%**。同卷还有 `wiki_tlcot_P551.jsonl`(**90.9%**)与 `wiki_direct_sonnet5_P551.jsonl`(**100.0%**)。→ **跑过但被排除在矩阵外**;且该卷最强直读基线 44/44 全对,wt 的 88.6 在此卷低于 prompt(90.9)与强直读(100.0)。
2. **STALE-full 的 wt 格与 stale-150 共用同一个文件**(`results/wtqvf3_stale50.jsonl`,150 行),对 1200 题只覆盖 12.5%,同一文件在矩阵里被当成两格计。
3. **LME-KU 的 direct 与 rt 是同一次跑批的两个 mode 切片**(`final2_lmek_h45.jsonl` 按 mode 过滤),不是两次独立跑批。
4. **wiki-P39 只参评 208/228**(test-52 of 57 uid);其余 14 卷无 `split`,全量参评。**全库只有 `data/wikistate_full.json` 带 `split` 字段。**

### 5.2 S5–S8 新臂族矩阵(complex_arm / wsc_direct / flat / algebra)

| 题集 | 编译臂 | 直读臂 | 其它 | 空格判定 |
|---|---|---|---|---|
| S5 `wsc_s5_all`(314) | 87.9 → 89.8(两轮) | 56.1 | — | 齐 |
| S5 b1_union(418) | 83.7 | 48.3 | — | 齐 |
| S5 P39 子集(104) | 65.4 | 25.0 | — | 齐 |
| S5 newdom P26(75) | 78.7 / 80.8 | 68.0 | combined 78.7 | 齐 |
| S5 newdom P69(75) | **21.3** / 57.1\* | **60.0** | combined **60.0** | 齐(编译臂败) |
| S5 newdom P1303(57) | 68.4 | **77.2** | — | 齐(编译臂败) |
| S6 v1(15) | **0.0** → 73.3 | **100.0** | — | 齐(编译臂败) |
| S6 v2(30) | 70.0 | **90.0** | — | 齐(编译臂败) |
| S6 big(18) | 83.3 | 83.3 | — | 平 |
| **S7(220)** | 3 轮,**全部 `judge_correct=null`** | **从未跑过** | P/R 口径 | **只有对我方有利的单臂** |
| **S7-div test(39)** | 5 配置 A–E,**全部 null** | **从未跑过** | P/R 口径 | **只有单臂,且 87% 空证据** |
| S8 test(67) | flat 52.2 / algebra 49.3 | **70.1**(最高) | — | 齐(编译臂败) |
| **S8 heldout p2(61)** | flat 16.4 / off 18.0 / on 21.3 | **从未跑过** | — | **编译臂全线崩到 16–21% 的那一卷,唯独缺直读基线** |
| **boundary(137)** | 单系统 duel,86.9% 同答 | **从未跑过** | — | **只有单臂** |
| ooo(45 对) | seq/shuf 互比 | 不适用 | — | 无金标准可比臂 |
| **MAB-FC(8 配置)** | sh_6k 56.0 / sh_262k 71.3 | **75.0 / 81.0** | rt 50.0 / 48.0 | **8 格只跑 2 格,两格全败,零报告** |

\* P69 的 57.1% 分母只有 42 题(33/75 行未判,见 §三 S8)。

### 5.3 "只跑过对我方有利的臂"的三处实证

1. **S7 / S7-div**:从头到尾只跑编译臂,直读臂一次没跑;而这两卷用的是 precision/recall 口径,分母**天然剔除失败行**(`wsc_s7_judge.py:419-420`)。**"只有单臂" + "只算成功行"叠加。**
2. **S8 held-out p2**:同一套 S8 题在 08-16 的 test 卷上直读臂以 **70.1% 完胜**编译臂(49.3%);到 08-17 的 p2 卷,三个编译臂变体(16.4 / 18.0 / 21.3)全跑了,**唯一没跑的就是那个已知会赢 20pp 的直读臂**。直读臂的 runner 是独立脚本 `scripts/wsc_direct_arm.py`,一次也没对 p2 调用过。补测成本 61 题 ≈ 几分钟、$1 量级。
3. **`wsc_boundary`**:137 题只有系统自答 vs gold 的 duel,无任何对照臂;其中 **21/137 行 `card_src="synthetic-direct"`,同答率 21/21 = 100%**,剔掉这 21 行后同答率从 86.9% 降到 **98/116 = 84.5%**。

### 5.4 时序法证

**(a) 归档结果早于它所对照的题集文件(5/15 卷)**

| 卷 | 题集文件 mtime | 早于它的臂 |
|---|---|---|
| wiki-P39 | 08-16 12:37(commit e732efc 改写) | direct 08-07 / rt 08-08 / wt 08-09 —— **三臂全早 7–9 天** |
| stale-150 | 08-10 17:06 | direct 08-07 01:27、rt 08-07 02:26 |
| LME-TR | 08-10 19:39 | direct 08-04 13:26、rt 08-05 19:47 |
| LME-KU | 08-10 20:51 | direct + rt 08-05 19:29 |
| STALE-full | 08-11 23:45 | direct 08-11 14:42、rt 08-11 18:43、wt 08-10 19:35 |

**但金答案没漂**:逐题比对归档行 `gold_answer` 与当前题集,**6 卷 / 18 个产物 qid 缺失 0、gold 不一致 0**。这 5 处倒置是"文件被重写过但内容等价",不是评分基准偷换。**这一条对项目有利,应照写。**

**(b) test 卷在 dev 调参**中间**被反复评估**

- **S5**:dev5(08-13 14:34)→ **test 314 第一次 87.9%(15:15)** → dev5_strict(22:32)/ strict2(22:44)→ **test 314 第二次 89.8%(08-14 00:43)** → dev5_strict3(08-14 11:29)/ strict3e(12:36)→ **test 418 第三次 83.7%(08-16 15:01)**。同一 test 卷被评了 3 次,每次之间都有配置改动。
- **S8**:dev r1(08-15 23:52)→ r2(00:29)→ r3(00:41)→ **test flat 52.2%(00:45)** → **dev r4(00:50)** → test direct(00:54)→ test algebra 49.3%(00:58)。**test 跑批夹在 r3 与 r4 之间。**

**(c) S5 的 dev 题就在 test 题集里(可逐 qid 证明)**
第一批 dev(`wsc_s5_dev5.jsonl`,5 个 `wiki00x` uid)与 test 314 **零交集**;但 08-13 22:32 之后 dev 队列被换成 5 个 `wikiP108*` uid(`wsc_s5_dev5_strict2/strict3e`),**这 20 题完全落在 test 314 与 union 418 之内**。即 08-14 00:43 的 89.8% 与 08-16 15:01 的 83.7% 都含 20 道调参题(6.4% / 4.8%)。

**(d) 题集在跑批之后被改写**
`data/wsc_s8.jsonl` mtime 08-17 12:26,晚于所有 S8 跑批;`data/wsc_s8_v2.jsonl`(08-17 12:50,160 题)只含 08-16 那 67 道 test 题里的 **45 道**。三代 S8 题集(121/160/61)并存,v2 的 106 道 unseen 里 **45 道从未被任何臂跑过**。

### 5.5 同一格重复轮次的分数散布

**93 个"同 qid 集 + 同 mode + 同 reader"的格子被跑过 2 次以上。** 散布最大的:

| 格子 | 各轮 | 散布 |
|---|---|---|
| S6 编译臂 15 题 | 08-13 23:07 **0.0%** → 23:21 **73.3%** | 73.3 pp |
| tempreason 200 题 direct | `tempr_n200_direct` **95.0** vs `temprraw_n200_direct` **30.0** | 65.0 pp |
| S8 algebra dev 54 题 | r1 61.1 → r2 **9.3** → r3 18.5 → r4 51.9 | 51.8 pp |
| LME-TR 133 题 rt | `final_lmet_h45` **80.9** vs `final2_lmet_h45` **45.9** | 34.9 pp |
| LME-TR 133 题 direct | 82.0 vs 47.4 | 34.6 pp |
| P39 wt 228 题 | 60.1 / 86.4(emb3l)/ 89.5(v42) | 29.4 pp |
| P39-ext wt 176 题 | 87.5 / 82.4(v42)/ **59.7**(strict3) | 27.8 pp |
| LME-KU 78 题 rt | 91.0 vs 80.1 | 10.9 pp |
| P54-ext wt 164 题 | 93.9(入矩阵)/ **100.0**(v42,孤儿) | 6.1 pp |

**入选路由矩阵的那一轮并不总是最高的一轮**:P54-ext / P54-w2 / P108-w2 / P39 / chain / confirm 上 `wtqvf3_v42_*` 系列都更高却是孤儿;反过来 LME-TR/KU 上入矩阵的是**更低**的 `final2_*`。**现有取舍不是"挑高的",而是没有任何成文规则**——这本身是第七节的溯源缺口。

---

## 六、孤儿实验与选择性报告

### 6.1 零引用比例

引用语料 = 全库 `**/*.md` + `**/*.py` + `.txt/.json/.sh/.ps1/.ipynb`,共 5,711 个文件,**排除 `scratchpad/`**。

| 引用状态 | 文件数 | 占比 |
|---|---|---|
| 至少被一个 `.md`(报告/台账)点名 | 99 / 629 | 15.7% |
| 只被 `.py`/`.json` 点名,从未进入任何叙述文本 | 100 / 629 | 15.9% |
| **全库零引用** | **425 / 629** | **67.6%** |

425 个孤儿共 **76,314 行 = 全部归档行的 49.5%**;其中 **356 个是有判分的真实评测**,69 个是中间产物/路由转储/失败跑批。

口径披露:若把 `scratchpad/` 里的临时审计脚本也算引用,零引用数降到 0,而 430 个文件只被 scratchpad 引用——那些引用绝大多数来自机器枚举产物与 glob 式脚本,不构成"有人用过这个结果"的证据,故不计入。另有 5 个用缩写形式引用的文件(如报告里写作 `_r2.jsonl`)已回收,425 是回收后的数。

**溯源缺口的最锋利形态:发表了数字,产生它的文件全库零引用**

| 已发表数字 | 实际产生它的文件 | 引用数 | 文件自身记录的配置 |
|---|---|---|---|
| STALE-full 提示词臂 **53.50** | `prompt_rows_stalefull_tlcot.jsonl`(1200 行,复算 53.50%) | **0** | 仅 `mode=warned_direct` |
| Mem0 **20.00 / 30.00 / 26.25** | `wiki_mem0_h45/_P54/_P108.jsonl`(各 80 行) | **0/0/0** | 无 `reader_model` |
| 摘要基线 **54.39** | `wiki_summarymem_h45.jsonl`(228 行) | **0** | 9 个字段,无任何模型/旗标 |

同类但被引用一次的:`wiki_graphiti.jsonl`(2.50%)、`wiki_langmem.jsonl`(51.25%)——两者字段集只有 9 个,**无 `reader_model`、无 `judge_model`**。**四条在售基线对照线全部落在"读者模型不可从产物自证"的区间里。**

### 6.2 成对变体的分数对比

**(a) `final_` vs `final2_`:实际五对,机制已定位**

| 对 | 臂 | `final_` | `final2_` | Δ | `final_` 引用数 |
|---|---|---|---|---|---|
| lmek_gpt | dense_direct | 91.03 | 80.77 | +10.26 | 0 |
| lmek_gpt | species2 | 89.74 | 74.36 | +15.38 | 0 |
| lmek_h45 | dense_direct | 88.46 | 78.21 | +10.26 | 1 |
| lmek_h45 | species2 | 93.59 | 82.05 | +11.54 | 1 |
| **lmet_gpt_direct** | dense_direct | **81.95** | **47.37** | **+34.59** | **0** |
| **lmet_gpt_species2** | species2 | **84.96** | **59.40** | **+25.56** | **0** |
| **lmet_h45** | species2 | **80.92** | **45.86** | **+35.05** | **0** |

**机制(本轮新发现)**:统计 `retrieved_memory_ids` 中 `answer_*`(LongMemEval 金答案会话)占比:

```
answer_share=100.00%  acc=100.00%  n= 20  pilot_oracle_10.jsonl        <- 文件名自认 oracle
answer_share=100.00%  acc= 91.03%  n=156  final_lmek_h45.jsonl
answer_share=100.00%  acc= 90.38%  n=156  final_lmek_gpt.jsonl
answer_share=100.00%  acc= 84.96%  n=133  final_lmet_gpt_species2.jsonl
answer_share=100.00%  acc= 81.95%  n=133  final_lmet_gpt_direct.jsonl
answer_share=100.00%  acc= 80.92%  n=133  final_lmet_h45.jsonl
-------------------------- 断层 --------------------------
answer_share= 60.92%  acc= 77.56%  n=156  final2_lmek_gpt.jsonl
answer_share= 60.40%  acc= 80.13%  n=156  final2_lmek_h45.jsonl
answer_share= 55.56%  acc= 47.37%  n=133  final2_lmet_gpt_direct.jsonl
answer_share= 49.93%  acc= 59.40%  n=133  final2_lmet_gpt_species2.jsonl
answer_share= 49.54%  acc= 45.86%  n=133  final2_lmet_h45.jsonl
```

逐题对照(同 qid,`gold_answer` 与 `question` 逐字节相同 133/133):

```
qid 08f4fc43  gold="30 days..."
 final  jc=True   ids=[answer_6ea1541e_2#r0..r4, answer_6ea1541e_1#r0]  in_tok=6880
 final2 jc=False  ids=[answer_6ea1541e_2#r3, ultrachat_292416#r0..r3, sharegpt_JJu53iW_0#r0]  in_tok=3734
```

**判决**:`final_*` 是 oracle / 近 oracle 干草堆跑批,**被正确弃用**;发表口径取较低的 `final2_*`,**方向保守,不是选择性报告**。
**但这是溯源缺口的教科书案例**:两组文件字段集、`mode`、`reader_model`、`extractor_model` 逐值相同(仅 `final2_lmek_h45` 多 `recog_sweep_added`/`sib_sweep_added`,`final_lmet_h45` 多 `error`),**决定 35pp 的配置在产物里唯一可查的痕迹是证据 id 的字符串前缀**——换一个 id 不带 `answer_` 前缀的基准,这个区分彻底消失。

**(b) 报告清单不完整(方向保守)**

S8 dev 五轮:r1 61.11% / r2 9.26% / **r2b 0/5** / **r3 18.52%** / r4 51.85%(锁定)。文件清单缺 **r2b 与 r3**,而同报告写"未做任何事后美化或选择性汇报"。锁定值 51.85% < r1 61.11%,**方向保守**;问题是清单与措辞不匹配,`$0` 可修。同时命名错位:文件 `_r4` 在报告里被称作"轮3"。

**(c) 其它 ≥3pp 的"未记录 vs 已发表"同格对照**

| 类型 | mode | 未记录 | 已发表 | Δ | 方向 |
|---|---|---|---|---|---|
| 系统臂 | complex_arm | `openslot_..._s5_arm_P69` 57.14%(**分母仅 42**) | `newdom_s5_arm_P69` 21.33%(75) | +35.81 | 分母口径不同即造出提升 |
| 基线 | warned_direct | `confirm_tlcot_v2_h45` **73.25%**(228) | `tlcot_confirm_h45` 68.42%(228) | **+4.82** | **存在更强的提示词基线未被发表** |
| 系统臂 | wt_qvf | `wt_read_strict3_P39ext` 59.66%(176,零引用) | `wiki_wtqvf3_P39_ext` 87.50%(176,仅被 scripts 引用) | −27.84 | 区分二者的 `strict3` 配置**两个文件都不落盘** |
| 系统臂 | wt_qvf | `wiki_wtqvf3_P54_ext` 93.90%(入矩阵) | `wtqvf3_v42_P54ext` **100.00%**(孤儿) | −6.10 | **孤儿更高,反向证据** |
| 基线 | pra_newest | `wiki_pra_newest` 2.19% | `wiki_pra_newest_dense` **32.02%** | −29.82 | 发表了更高的基线 = 保守 |
| 基线 | dense_direct | `final_chain_sonnet_direct` 47.17% | `chain_direct_sonnet5` **72.17%** | −25.00 | 同上,保守 |

**(d) `openslot` P69 的逐题拆解**:`combined` 45/75 = **60.0%**,直读臂 45/75 = **60.0%** —— 数值完全相同;42 道编译臂真答了的题上编译臂对 24、直读臂对 24(**持平**);33 道 fail-closed 题上直读臂对 21、旧编译臂对 0。→ **"21.3 → 60.0"的全部增益来自 44% 的题让位给直读基线,编译臂在新域上的净边际为 0。**

### 6.3 有无选择性报告的物证

**判决:没有找到"系统臂跑砸了就藏起来、只报好的那次"的成规模物证。方向上项目多数时候偏保守(发表较低的系统值 / 较高的基线值)。但有一处整卷负结果零报告。**

**唯一的重量级问题:MAB fact-consolidation 整卷负结果零报告** — `CONFIRMED`

```
mabfc_sh6k_direct.jsonl    75.0% (100 题)  |  mabfc_sh262k_direct.jsonl        81.0%
mabfc_sh6k_qvf.jsonl       56.0%           |  mabfc_sh262k_qvf.jsonl           71.3%(195 行/100 题,去重 70.0%)
mabfc_sh6k_rt.jsonl        50.0%           |  mabfc_sh262k_rt.jsonl            48.0%
                                           |  mabfc_sh262k_direct_4omini.jsonl 70.0%
```

引用扫描 `grep -rl "mabfc" --include=*.md --include=*.py .` → **仅 `study_logs/repo_hygiene_20260816.md` 的大文件清单**。`results/*.md` 与全部主张文档零命中;`data/mab_fc_*.json` 8 个配置在案。同时该榜被作为**外部引文**使用("22 系统最好 HippoRAG-v2 = 54")。

**性质**:不是"同配置变体分数更低而未发表",而是**一整卷公开基准上自家两臂都被自家直读基线打败 19–25pp,从未进入任何报告或台账**。它直接推翻一句现行措辞:"**唯一的**公开真实基准上系统本体告负:LoCoMo-full"——至少还有 MAB-FC。

`PLAUSIBLE` 附注:自家直读 81.0% 高于该榜最好系统 54,提示题集切分/判分口径与官方不同,不能直接与排行榜对比——**这是必须写的限定,不是不报的理由**。

### 6.4 给项目的正面结论(应进附录)

- `router_routes_v42` 与 `_v42_final`、`v41` 与 `v41_final` 逐题路由 **5061/5061 = 100% 一致** —— 两个大孤儿是**纯冗余副本**,不是"多版本挑最好"。
- 9 个 `wtqvf3_v42_*` 孤儿多数**高于**入矩阵那一轮。
- `backup_pre_patch/lme_tr_ctx16k.jsonl` 保留了污染版(87/266 行空答案、44 行带 error)且全部零引用;修补后版本空答案为 0。**污染版被保留而非删除,是好实践。**
- 6 卷 18 个产物的 gold 与 qid **零漂移**(§5.4a)。

---

## 七、溯源缺口

### 7.1 判决:100%

**629 个归档 jsonl 中,能只凭自身确定"模型 / 旗标 / 卡片库 / 题集版本"四项的是 0 个(0.0%)。** 分档:部分 **556(88.4%)** / 无 **73(11.6%)**。

| 配置轴 | 有该字段的文件 | 占比 |
|---|---|---|
| 回答模型(`reader_model`/`model`) | 496/629 | 78.9% |
| 写入侧模型(`extractor_model`) | 428/629 | 68.0% |
| 臂/模式标签 | 542/629 | 86.2% |
| **判官模型** | **9/629** | **1.4%**(全部是 S7 `*_judged*`) |
| **QVF_* 旗标状态** | **1/629** | **0.2%**(`boundary_duel_20260816.jsonl` 的 `flags`) |
| **卡片库身份** | **2/629** | **0.3%**(同上的 `card_src` + `writeside_sensitivity_b6rep3_arm.jsonl` 的 `card_library`) |
| **题集版本/切分** | **3/629** | **0.5%**(`wsc_s8_seen`/`_unseen` 的 `split` + `router_learned_triples_20260814` 的 `cert_split`) |
| **随机种子** | **1/629** | **0.2%** |
| **temperature** | **0/629** | **0.0%** |
| **git commit / 代码版本** | **0/629** | **0.0%** |

**已发表子集同样是 0%**:99 个被 `.md` 点名的文件里,记录旗标的 0 个、记录卡库的 0 个、记录 temperature 的 0 个。**7,924 行 / 30 个文件**同时满足"有 answer、有 `judge_correct`、但 `reader_model` 为 null"——包含全部四条在售基线对照。

10 个 `.meta.json` 边车(全部是 `*_compile_*` 系列)是全库最好的一档,但**仍不含旗标、卡库、题集版本、种子、commit**,最多只有 `model` + 计数。

### 7.2 "不可复现"不是理论风险:四个不落盘的轴都已实测到 ≥10pp 的分数移动

| 不落盘的轴 | 实测分数移动 | 对照 |
|---|---|---|
| 检索池(oracle vs 全量) | **35.05pp** | `final_lmet_h45` 80.92 vs `final2_lmet_h45` 45.86 |
| 语料(同 qid / 同 question / 同 gold / 同 mode / 同 reader) | **65.0pp** | `tempr_n200_direct` 95.0 vs `temprraw_n200_direct` 30.0(input token 中位数 1228 vs 1938 是唯一线索) |
| 读取侧配置(`strict3`) | **27.84pp** | `wt_read_strict3_P39ext` 59.66 vs `wiki_wtqvf3_P39_ext` 87.50 |
| 卡片库版本(`_w2`) | **13.82pp** | `wiki_qvf_P54` 73.68 vs `_w2` 87.50 |

### 7.3 缺哪些字段(逐项)

**卡片文件**只有 4 键 `{uid, records, usage_in, usage_out}`(`wt_qvf_prototype.py:315-318`)。不落盘:抽取模型(硬编码 `MODEL="claude-haiku-4-5"`,`:36`)、`QVF_CARD_KEYS/TAGS/STRICT/V5/V5_VARIANT/TEMP0`、`QVF_CATALOG_BUDGET`、实际批数、`max_tokens`、源数据文件路径与版本、建卡时间、失败批数。可反推的只有 KEYS(靠 `owner` 键)、TAGS(靠 `value_tags` 键)、批数(靠 `r1` 出现次数)、时间(靠 mtime)。**TEMP0、STRICT、V5、V5_VARIANT、源数据文件完全不可恢复。**

**路由日志**每行只有 8 键 `bench/uid/qid/qid_raw/route/keyed_depth/picked_arm/result`(`qvf_router.py:511-515`)。7 个旗标一个都不落盘,无伴生 meta。且 `result: null` 的语义不落盘 → `router_routes_v42.jsonl`(56.72%)与 `_v42_final`(70.15%)的 **13.4pp 差异全部是覆盖率伪影**;v41_final(56.54%)vs v42_final(70.15%)看起来差 13.6pp,而在 v41 有行的 4440 题子集上两者是 **70.18% vs 70.41%(相差 0.23pp)**。

**读取结果行**不含 `cards_dir`、不含 `len(cards)`、不含数据文件路径、不含任何 `QVF_*` 快照(grep 全部 `results/*.jsonl`:零行含 `cards_dir`);裁决内容(note 文本、scope 分支、`qf` 各字段、被丢弃的 memory id)全不保存。**对照:`scripts/boundary_run.py:310` 会把 `QVF_FAIL_CLOSED` 等写进产物——仓库里已有更好的做法,但未用于主模块。**

**编译臂行**(`complex_query_arm.py:927-936`)不记 `QVF_CARDS_KEYED`(31 个 `wt_cards*` 候选)、`QVF_ALGEBRA`、`QVF_RENDER_ANCHORS`、`QVF_TAG_LATTICE`、`QVF_COMPILE_SPEC`、`QVF_OPEN_*`、`--data`、`--questions`、判官模型。且 `evidence_n` 是**截断后**的长度 → 永远 ≤12,**单看一行无法判断是否发生截断**。证据包与结论行本身**都不落盘**——而结论行是这个臂的核心机制。

**判官侧**:`total_usage` 不落盘;FALLBACK 只体现在 `judge_reason` 自由文本前缀,无布尔字段。

**归档里存在现版本源码无法产生的字段/取值**:`scope_pass_point_in_time_hedged`(14 行)、`nc_sweep_added`(18)、`early_sweep_added`(6)、`sweep_debug`(6)、`minimal_rules_v6` 的 75 行、`router_routes_v4_full.jsonl` 的 rt=0 分布。**这些结果的产生代码已不在仓库里,永久不可解释。**

**文档与产物的行数漂移**:`decisive_stale_qwen3-4b.jsonl` 现为 **735 行 / 7 个 mode**,而五处文档写"共 315 行,即 105 questions × 3 conditions"。文档给的是按 mode 的分子分母所以仍可复算,但行数口径已失效,**无任何机制检测这类漂移**。

### 7.4 修法:给跑批脚本加 env 快照的具体建议

在每个跑批脚本(`run_decisive_stale.py`、`complex_query_arm.py`、`wsc_direct_arm.py`、`qvf_router.py`、`algebra_parity.py`、`wt_qvf_prototype.py` 两个 phase)的输出文件**首行**写一条 `__META__` 记录,内容:

```json
{"__META__": 1,
 "git_commit": "<git rev-parse HEAD>", "git_dirty": <bool>,
 "argv": [...],
 "env_qvf": {"QVF_ALGEBRA": "1", "QVF_CARDS_KEYED": "results/wt_cards_v42", ...},   // 全部 44 个,含未设者写 null
 "cards_dir_resolved": "<绝对路径>", "cards_n_uid": 434, "cards_n_records": 20737,
 "dataset_path": "data/wsc_s8_v2.jsonl", "dataset_sha256": "...", "dataset_n": 160, "split": "unseen",
 "retrieval_pool": "full_haystack" | "oracle",     // 关掉 final_/final2_ 那一类 35pp 的歧义
 "models": {"reader": "...", "extractor": "...", "judge": "claude-opus-5", "embed": "text-embedding-3-large"},
 "temperature": {"reader": null, "extractor": 0.0, "focus": null, "judge": null},
 "top_k": 10, "mmr": false, "scan_budget": 2, "catalog_budget": 320000,
 "run_id": "<uuid4>", "started_at": "<iso8601>"}
```

三条实现要点:

1. **一个共享函数**(建议 `qvf/provenance.py:run_meta()`),六个跑批脚本各加一行调用——这一条改动同时关掉 §7.1 的全部 10 个轴、§6.2a 的 35pp 歧义、§7.3 的行数漂移检测。
2. **卡片文件同步加 meta 键**:`{uid, records, usage_in, usage_out, __meta__: {...}}`,并在 `_catalog` 触底时落 `n_fail`/`n_batches`/`n_skipped_rounds`(对照 `write_persession_batch.py:95-100` 已有的 `n_fail`)。这一条同时让 §1.1 静默回落 1 与 §三 S3 可见。
3. **`algebra_parity.py` 这类零 LLM 对拍脚本**除 env 快照外,还要落 `macro_table_sha256` 与 `check_expr_version` —— 因为它验证的是符号等价,一旦 `MACROS` 或 `check_expr` 被改,旧的 874 次比较结论就失效而无任何提示。

**三个 `$0` 的落盘布尔**(与上并列,不需要 meta 基建):`judged`(`judge_correct is not None`)、`mechanism_fired`(`evidence_n>0` 或 `chain_vals` 非空)、`judge_fallback`(`judge_reason` 以 FALLBACK 开头)。它们让下游无法把失败行静默算进准确率。

**一个 `$0` 的分析脚本修正**:`scripts/analyze_decisive.py:137-139` 的成本行必须按 mode 分组、对 `reader_model is None` 的行报"未记账"而不是 0、并把 opus 单价改成运行时实际模型单价。

---

## 八、文档与代码的差异清单

> 本节是审计的**最后一步**。上文全部结论在读文档之前已定稿;本节只标差异,不以文档纠正代码。

### 8.1 文档说系统会做、代码里做不到或没有

| # | 差异 | 标签 |
|---|---|---|
| 1 | "硬约束一条:`source_span` 必须是会话原文的逐字连续子串,**可用一行代码校验**" —— 约束只存在于提示词与字段描述,建卡路径无任何校验器;而 `engine_bridge.py:14` docstring 与 `:275`/`:369` 提示词都声称已 enforce / mechanically verified。"可用一行代码校验"是真的,"已校验"是假的 | **CONFIRMED** |
| 2 | 卡片是"六字段" —— 实际 13 常开 + 3 门控;零消费的是 `entity`、`claim`、`slot_cardinality`、`implies_stale_slots` 四个 + `temporal_relation` 标签。文档只披露了 `slot_cardinality` 一个 | **CONFIRMED** |
| 3 | "路由:按 (问题时序性 × 该槽位键控深度 × 整库形态) 四选一" —— 第三项在无键控卡片时恒为 0,规则退化为"所有 rt 一律改 prompt";**19.0% 的题被判 prompt 的直接判据是卡片文件不存在** | **CONFIRMED** |
| 4 | 路由消费"替换边" —— `chain_depth` 的关系边计算被 `:359` 的 `max()` 丢弃,**对返回值影响恒为零**(326 例 0 反例) | **CONFIRMED** |
| 5 | 读取侧 "一次微型聚焦 + 确定性裁决 + 读者" —— 实际还有 judge(`:592`)且不计入 usage;裁决只有三支;**日期比较是裸字符串比较**,而同仓库有正确的补零排序键未被生产路径使用 | **CONFIRMED** |
| 6 | "路由为确定性函数"+"无任何跨查询状态" —— `focus_of` 不传 temperature,450 道重复题 **13.6% 路由标签不同**;确定性由一个跨跑批、跨版本累积、永不覆盖的缓存文件提供 | **CONFIRMED** |
| 7 | "方向经 **3 种子**稳健" / "3 种子 6 验 2 败" —— **仓库里没有任何多种子循环**(grep 零命中),不是产物丢了,是代码里从来没有这个循环 | **CONFIRMED** |
| 8 | 判官/读者未固定温度被定性为"可复现性缺口" —— `focus_of` 的未固定温度已经**改变了 13.6% 重复题的路由标签**,它不止是复现问题,是测量本身的噪声源 | **CONFIRMED** |

### 8.2 标签或归属错了(两条 load-bearing)

| # | 差异 | 标签 |
|---|---|---|
| 9 | **LME-KU 的"提示词臂 82.1%"标错了臂。** 五处文档写"提示词臂 82.1% > 直读 78.2% > 卡片臂 64.1%"。逐文件复算全部 21 个 KU 产物:`final2_lmek_h45.jsonl` 的 `dense_direct` 78.21%、`minimal_rules_species2` **82.05%**;`wtqvf3_lmeku.jsonl` wt 64.10%;`prompt_rows_lmeku_tlcot.jsonl` `warned_direct` **92.31%**。**82.05% 是 rt 臂,不是提示词臂;没有任何 KU 产物给出 82.1 的 `warned_direct`。**同一份文档内部即矛盾(另一处正确写了 92.3%)。**方向后果:这条边界比文档写的更伤——卡片臂落后最强单臂不是 18.0pp 而是 28.2pp,且落后的是"一段提示词"** | **CONFIRMED** |
| 10 | **支撑该边界的两个数字近半数行由判官回落启发式判出**:`final2_lmek_h45` dense_direct FALLBACK 37/78 = **47.4%**、species2 38/78 = **48.7%**;而输的那一臂(`wtqvf3_lmeku` 64.10%)与最强臂(`prompt_rows_lmeku_tlcot` 92.31%)FALLBACK 为 **0**。**这条三元比较里输的一臂是干净判的,赢的两臂近半数行是判官挂掉后按子串包含判的。**结论方向大概率不变(64.1 与 92.3 差距太大),但比较的两端不同口径,必须重判 | **CONFIRMED** |
| 11 | 判官稳定性证据(155 行重判 99.35% 一致)**对失败类零覆盖**:FALLBACK 行 0 条,而其中 15 行来自 FALLBACK 占比约 47% 的 lme_ku(15 抽 0 ≈ 6e-5) | CONFIRMED(事实)+ **PLAUSIBLE**(成因,不指控刻意排除) |

### 8.3 代码里做了、文档从没提

| # | 差异 | 标签 |
|---|---|---|
| 12 | 卡片跨批 id 碰撞 **37.9%**,使"抗污染连通分量"在所有多批库上失效(离线重放:分量 30→8) | **CONFIRMED** |
| 13 | 槽位模糊匹配"共享 1 个词即同槽",基础卡库上 49% 的 wt 决策深度 ≥10、最大 51 —— **所谓"链深"在无键控库上不是链深** | **CONFIRMED** |
| 14 | 建卡"存在即跳过"使卡片库成为跨旗标累积体;`wt_cards_s8_heldout` 8 带 / 22 不带 `slot_class` 却被当单一库读 | **CONFIRMED** |
| 15 | `EVIDENCE_CAP = 12` 只砍证据、结论在未截断全集上算;`tag_filter` 结论行的 "every one is listed above" 在命中 >12 时是假陈述且被当指令发给模型。**`study_logs/` 全库无 "EVIDENCE_CAP" / "上限 12" 命中** | **CONFIRMED** |
| 16 | 结论行伪装成 `[memory summary]` 记忆摘录,读者无任何机制义务采纳,**归档里确实无视过**(两个 qid 已点名);系统提示词的 "1-3 sentences" 与 trajectory/tag_* 的"列全"要求方向相反 | **CONFIRMED** |
| 17 | `warned_direct` 行存的是**未拼警告**的问题原文(13764 行含 `[Instruction:` 的 0 条)—— 这个承担 49.5% 路由流量的臂,**发给读者什么不可重建** | **CONFIRMED** |
| 18 | `framing_arm.py` 猴补系统提示词但产出行 `mode` 仍是 `dense_direct`;22119 条里哪些是 framing 版只能靠文件名猜 | **CONFIRMED** |
| 19 | 导入 `wt_qvf_prototype` 会静默改掉全进程嵌入后端默认值 | **CONFIRMED** |
| 20 | `minimal_rules_v6` 现版本主路径必抛 `NameError`,归档 75 行是旧代码产物、不可复现 | **CONFIRMED** |
| 21 | `minimal_rules_pnote` 与 `minimal_rules_v5` **行为完全等价**,`pnote_t1.jsonl` 165 行不构成任何 premise-note 消融 | **CONFIRMED** |
| 22 | **嵌入 token 全库零计量**,判官 token 从不落盘(判官默认 opus-5,是最贵的一次调用)。所有 "rt vs direct token 倍数" 型对比都缺这两项 | **CONFIRMED** |
| 23 | 44 个旗标中 11 个注释与行为不符;`QVF_FAIL_CLOSED` 在两个模块同名不同义 | **CONFIRMED** |
| 24 | 学习路由报告的多处结论与数字**硬编码进字符串**而非从结果取值;受限动作空间明细加总 1955 而实际 1954 | **CONFIRMED** |
| 25 | `router_eps_scaling.py` 的 ε 下界诊断在数学上循环(bootstrap 风险期望恒等于原池经验风险),`p_inf = 9.27%` 高于全部 8 个观测点;结论正确但曲线不构成论据 | **CONFIRMED** |
| 26 | `verify_split_parity.py` 的去耦合证明是循环的:split 字段与被批评代码的删除在**同一提交**,且 `split=="test"` 的 uid 集合与旧判据产物的 uid 集合**完全相等** | **CONFIRMED** |

### 8.4 主张依赖零覆盖能力(三条尚未标为假说)

| # | 差异 | 标签 |
|---|---|---|
| 27 | LoCoMo 负结果的根因被定为"说话人库未键控" —— 该归因依赖的 owner 分组防护**从未在任何真实多人库上被检验过**(具名 owner 仅百余条,LoCoMo 一人称命中率 0/2286),`entity` 字段两端零消费。**这是假说,不是实测** | **CONFIRMED**(零覆盖)+ PLAUSIBLE(归因本身可能仍对) |
| 28 | "事件算术正则在生产题面上仅命中 1.3%,受影响题量小" —— 该缓解是用一个**已知漏检 84%** 的判定器度量出来的(73 题字面即事件算术,正则一条不中,66 题被判给 prompt/wt) | **CONFIRMED** |
| 29 | S8 held-out p2 的三个数字(16.4/18.0/21.3%)是最锋利的自认边界,**却没有同卷直读基线**,而同族 test 卷上直读赢 20pp | **CONFIRMED** |
| 30 | "**唯一的**公开真实基准上系统本体告负:LoCoMo-full" —— 至少还有 MAB-FC(两格全败 19–25pp,整卷零报告),以及文档已认的 LongMemEval-KU/TR | **CONFIRMED** |
| 31 | 完备基护栏"874 次逐字节比较、11/11 算子覆盖" —— 符号层**成立**,但**护栏保护的宏路径与被 LLM 评测的 `expr` 路径不是同一条**(410 条 expr、0 条带 op)。需一句限定 | **CONFIRMED** |

### 8.5 文档正确、应照录的部分(交叉确认)

- `qvf_router.py:50-53` 关于正则召回的长注释(624 条、16.2%、longest 与 count_before 为 0%)—— 独立复算逐位相符。
- 5511 → 5061 的重复题(450 行,61 个路由不一致)与 v42_pick 差 61 —— 独立复算相符。
- `QVF_COMPILE_SPEC` 在 `QVF_ALGEBRA=1` 时不生效 —— 代码确实如此,诚实标注。
- `QVF_RENDER_ANCHORS` 的注释描述准确。
- 判官侧 token 从未落盘、`SidecarReader`/`focus_of`/judge 三处温度缺口 —— 台账已完整记录且按纪律未改。
- 乱序鲁棒性的修正值 68.9%(vs 旧值 77.8%)在 `p5_index_report_20260816.md` 有据实记载并注明"脚本 bug 修复带来的诚实收窄"——**旧值滞留传播于五处,不是隐瞒**。
- 6 卷 18 个产物 gold 与 qid 零漂移;`backup_pre_patch/` 保留污染版;两个大孤儿是纯冗余副本。

---

## 九、处置建议

距投稿 2–3 个月。三档,标预估成本与工期。

### 九·A 投稿前必须做

| # | 动作 | 拆掉的风险 | 成本 | 工期 |
|---|---|---|---|---|
| A1 | **重判 629 行 FALLBACK 判决**,优先 LME-KU/TR 五个单元 | §三 S1;§8.2 第 10 条。这五个单元是当前定位的靶心证据,其中 44%–49% 的行是判官挂掉后按子串包含判的 | 629 行 × 实测判官单价 $0.003078 ≈ **$1.94** | **半天** |
| A2 | **改 LME-KU 的臂标签**:五处"提示词臂 82.1%"改为"rt 臂 82.05%",补入真实提示词臂 **92.31%**;卡片臂落后幅度由 18.0pp 改 **28.2pp** | §8.2 第 9 条。这是标错臂,不是数字微调;改完边界更伤但更准 | **$0** | **1 小时** |
| A3 | **补跑 S8 held-out p2 的直读臂**(61 题) | §5.3 第 2 条;§二 F2。当前最锋利的自认边界没有同卷基线,审稿人一句就能问倒 | 61 题 × 一次直读 ≈ **$1 量级** | **1 小时** |
| A4 | **MAB-FC 整卷入档**:两格实测(直读 75.0/81.0 vs wt 56.0/71.3 vs rt 50.0/48.0)写进 C 类边界,附"与官方榜口径不同"的限定;并撤回"**唯一的**公开真实基准"这一措辞 | §6.3。整卷负结果零报告是本报告最重的单条;不补,任何人 `ls results/mabfc*` 就能发现 | **$0**(已跑完)+ 可选补 6 格 | **半天**(仅入档) |
| A5 | **给三条无实验支撑的主张加假说标记**:LoCoMo"说话人库未键控"归因(owner 机制零覆盖)、"事件算术正则仅命中 1.3%"缓解(判定器漏检 84%)、S8 p2 三臂无同卷对照 | §8.4 第 27–29 条 | **$0** | **2 小时** |
| A6 | **给 P1 完备基加一句限定**:护栏验证的宏路径与被 LLM 评测的 `expr` 路径不是同一条(与已披露的 `PICK` 死覆盖 33.2% 并列写) | §二 B2;§8.4 第 31 条 | **$0** | **半小时** |
| A7 | **`__META__` 首行基建**(见 §7.4 的完整 schema),六个跑批脚本 + 卡片文件 + 三个 `$0` 布尔(`judged`/`mechanism_fired`/`judge_fallback`) | §七 全节 + §6.2a 的 35pp 歧义 + §三 S4/S5/S8 的可见性。**一条改动关掉本报告最大的一类问题** | **$0** | **1–2 天**(含回填现有产物的 best-effort 版) |
| A8 | **修 `analyze_decisive.py:137-139`**:按 mode 分组、`reader_model is None` 报"未记账"而非 0、单价按运行时实际模型 | §三 S13(≈3500 行成本口径被清零,并按 opus 单价给 qwen3-4b 估价) | **$0** | **1 小时** |
| A9 | **修 S8 报告的轮次清单**(补 r2b、r3)并把"未做任何选择性汇报"改成可核表述(五轮全列 + 说明为何锁 r4) | §6.2b | **$0** | **1 小时** |
| A10 | **孤儿清单进附录**:425 个零引用文件分成「冗余副本 / 中途调试轮 / 未发表独立结果」三类;第三类目前 356 个有判分文件 | §6.1。审稿人一次 `ls` 就能问出来的账 | **$0** | **半天** |
| A11 | **改 λ 的选择方式**:在现有 40/20/40 切分的留出集上重选 `same_acc`/`same_cost`,并公布 17 个 λ 的完整扫描曲线 | §二 D2。当前 headline 的准确率余量 +0.15pp ≈ 8 题,是 17 个 λ 里挑出的最大值 | **$0 API**(纯离线重放) | **1 天** |
| A12 | **加多种子循环 + uid 层 cluster bootstrap** | §二 D1、D3;§8.1 第 7 条。"3 种子稳健"现在**没有实现** | **$0 API** | **1–2 天** |

**A 档合计:API 成本 < $10;工期约 5–8 个工作日。**

### 九·B 应该做

| # | 动作 | 理由 | 成本 | 工期 |
|---|---|---|---|---|
| B1 | 修 `_slot_match` 的词重叠阈值(单/双词槽位退化为"共享 1 词") | §1.2。基础卡库上 49% 的 wt 决策深度 ≥10,"链深"信号在无键控库上失真 | $0 代码 + 重跑受影响 wt 卷 ≈ 中 | 3–5 天 |
| B2 | 给 `wt_cards` 生产库做一次跨批 `record_id` 重编号(或改用 `write_persession` 的内容 sha256 方案),并重跑 `wtqvf3_stale50`/`lmeku`/`lmetr` | §1.1 静默回落 3;§二 E1。这条同时把已零覆盖的两层拆分方案接进生产 | 中(重建卡库 + 3 卷重跑) | 1 周 |
| B3 | 补 `source_span` 校验器(一行字符串包含)+ 落 `n_span_violation`,并把 9–11% 的违约率作为写入侧质量指标正式发表 | §二 A1。把审计的功劳变成系统的能力 | $0 代码 | 1 天 |
| B4 | 统一日期口径:让 read_phase 用 `write_persession.py:267-276` 的 `_date_key()` | §1.2。生产库 306 条未补零,字符串比较与真实时序相反 | $0 代码 + 重跑 | 2–3 天 |
| B5 | 修 `EVIDENCE_CAP` 与结论行的不对称:结论行只在被展示的证据上算,或在证据被截断时把 `tag_filter` 的 "every one is listed above" 改成明示 "showing first 12 of N" | §1.5;§8.3 第 15 条 | $0 代码 | 1 天 |
| B6 | 落 `warned_direct` 的实际发送文本(或至少落 `warn_applied=true` + 警告文本 sha256) | §8.3 第 17 条。49.5% 流量的臂输入不可重建 | $0 代码 | 半天 |
| B7 | 补 `QVF_GATE_DEPTH` 的敏感性表(至少 2/3/4 三点) | §二 C3。一个决定半数路由流向的参数只测过一个点 | 低($0 API,离线重放) | 1 天 |
| B8 | 补 `QVF_LLM_INTENT` 的一次完整路由跑批(5511 题 × haiku 分类) | §二 C2。当前的缓解论证建立在漏检 84% 的判定器上 | 中(≈ 一次聚焦跑批) | 2 天 |
| B9 | 把 `results/wiki_direct_bm25.jsonl`(228/228 traceback)移入 `results/failed/` 或改名 `*.FAILED.jsonl`;给 BM25 基线补一个正式引用(`_v2.jsonl` 21.5% 当前无人报) | §三 S12 | $0 | 1 小时 |
| B10 | 给 S5/S6/S7 的题集补 `.meta.json` 与 `split` 字段;记录 S5 那 20 道调参题落在 test 内这一事实 | §5.4c。dev/test 划分只存在于文件名约定 | $0 | 1 天 |

### 九·C 可以不做(但要在限制章节写清)

| # | 项 | 为何可以不做 |
|---|---|---|
| C1 | 补测 `implies_stale_slots` / `claim` / `slot_cardinality` / `temporal_relation` 标签的效用 | 无主张依赖;正确做法是**从契约里删掉它们并公布省下的 token**,而不是补测 |
| C2 | 打通代数 11 算子的宏路径覆盖 | 只要 A6 的限定写到,符号护栏本身仍是有效贡献;强行让编译器产 op 计划会引入新变量 |
| C3 | `AGG fn=by_year` / `PICK.value/exclude_last` / `ASOF` date 字面量 / `AGG(WINDOW(TAGSET))` 的补测 | 归档 0–2 次,属实现冗余;在算子表里标"未评测"即可 |
| C4 | `QVF_OPEN_KEYS` 单开效果 | 它是 `QVF_OPEN_SLOT` 的严格子集,单开无独立意义;应**合并成一个旗标** |
| C5 | `QVF_CARD_STRICT` 扩大覆盖(现只 8 uid / 32 题) | 没有主张依赖;标"探针级"即可 |
| C6 | 复现 `minimal_rules_v6`、`nc_sweep_added` 等已删代码的归档行 | 产生代码不在仓库,永久不可解释;**正确做法是把这些行标为 archived-unreproducible 并排除在任何表格外** |
| C7 | `router_eps_scaling.py` 的曲线重做 | 结论(ε=5% 不可达)从 calib 单点 CP 上界 9.95% 即可得到;删掉曲线、保留单点结论,比修拟合更诚实 |
| C8 | 补齐 `wsc_boundary` / ooo / S7 的对照臂 | 这三卷的定位是机制探针不是分数卷;但**必须在文中明确它们不产生可比分数**,并把 boundary 的 21 行 `synthetic-direct` 剔除后同答率(84.5% vs 86.9%)一并给出 |

### 九·D 一句话优先级

**A1 + A2 + A3 + A4 + A7 五项**加起来 API 成本 < $5、工期约 3–4 天,拆掉的是审稿人最容易一击命中的四类:**标错臂的靶心数字、由判官回落判出的头条、没有同卷基线的最锋利边界、整卷零报告的负结果**;而 A7 是唯一能让上述问题以后不再复发的基建。

---

*报告结束。全部结论可由 `D:\ZZL_cluade\scratchpad\` 下的只读分析脚本复现;本轮未修改任何仓库文件。*
