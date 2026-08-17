# T3:temperature=0 的正式采纳决策

> 工作目录 D:\ZZL_cluade。冻结代码(qvf_router.py / complex_query_arm.py / qvf_algebra.py)全程只读,本轮未做任何改动。本任务改动的唯一生产文件是 `scripts/wt_qvf_prototype.py`(新旗标默认值翻转,逻辑分支本身零改动),外加 `study_logs/VERSION_LEDGER.md` 追加记录。成本:**$0**(核查步骤为纯代码 execute_plan 对拍,零 LLM 调用;决策落地为纯代码改动)。

## 判决(先判决,后数字)

**采纳。`QVF_CARD_TEMP0` 默认值由 0 改为 1(建卡默认固定 temperature=0)。**

08-16 诊断已经把"B6 的 ±20pp 方差主要来自未固定采样温度"这一**归因假设**判为不成立(σ 降 46.5%,差预注册"减半"门槛 0.25pp)。但本任务的判据不是这个假设,而是工程问题:**固定温度会不会伤害任何已归档的具体结论?** 零成本核查——把 3 轮 temperature=0 卡片库(`wt_cards_p6_rep1/2/3`)与归档库 `wt_cards_v42` 放到同一批 48 道 S5 题上做纯代码 execute_plan 对拍——**0 例"归档库对、temp0 库错"的反向情形**,反而 15 例方向相反(归档库错、temp0 库对,且三轮温度库口径完全一致)。**无反向证据 → 按预注册规则采纳。**

三项强制要求已全部落实:①旗标仍可显式关闭(`QVF_CARD_TEMP0=0`)以逐字节复现历史结果;②口径分裂已在代码注释与 VERSION_LEDGER 明确记录;③未重建任何已归档卡片库。

顺带排查发现:判官(`qvf/judge.py`)与 STALE-Chain 旗舰读者(`qvf/engine_bridge.py:SidecarReader`)两处温度设置缺口,同文件内"有的设、有的没设"的系统性不一致确认属实,但因改变判官/读者采样行为会牵连所有已发表数字的可复现性,本轮**只列清单不下手改**,留作后续独立预注册任务。

---

## 一、决策所需的反向证据核查(零成本)

### 方法

- **对象**:P6 覆盖的 30 个 uid(P108/P108_ext/P54/P54_ext 分层子集,见 `results/p6_fixed_subset30.json`)在当前口径 S5 全量测试集 `results/wsc_s5_test_v42.jsonl`(314 题)中命中的题 —— 共 **48 道**。
- **四个卡片库**:归档库 `results/wt_cards_v42`,以及 08-16 诊断阶段建成的 3 轮 temperature=0 库 `results/wt_cards_p6_rep{1,2,3}`。
- **执行方式**:直接调用冻结模块 `scripts/complex_query_arm.py` 的 `execute_plan()`(纯代码,S5 题目自带的编译计划 `plan` 字段,不重新编译、不调用任何 LLM),把每题的 `plan` 分别喂给四个库产出的证据包(`ev`)与结论行(`derived`),唯一切换手段是 monkeypatch 该模块的 `CARDS` 路径全局变量(运行时内存赋值,未改动 `.py` 文件任何一行,已用 `git status`/`git diff` 核实该文件零改动)。
- **正确性代理**:`gold_answer` 是否作为子串出现在 `derived + ev` 拼接文本中(与 `qvf/judge.py` 兜底逻辑同一形状的 containment 检验),四库统一使用同一把尺子,**库间可比**;但与原表用 LLM 判官对最终读者答案打分的口径不同量纲,**不与原表 `judge_correct` 直接比较**。
- 产物:`results/temp0_crosscheck_20260817.json`、脚本 `scratchpad/t3_temp0_crosscheck.py`(留痕,非生产代码)。

### 结果

| 库 | 纯代码 containment 正确率(48 题) |
|---|---|
| v42_archived(归档) | 31/48 = 64.6% |
| p6_rep1(temp0) | 36/48 = 75.0% |
| p6_rep2(temp0) | 36/48 = 75.0% |
| p6_rep3(temp0) | 36/48 = 75.0% |

- **反向情形("归档库对、temp0 库错")数:0/48。**
- **反方向情形("归档库错、temp0 库对")数:15/48**,且这 15 例在三轮 temp0 库上**逐题结果完全一致**(0 处三轮互相分歧)。
- 三轮 temp0 库在全部 48 题上的逐题判定**100% 相互一致**(0/48 分歧)——与诊断阶段"固定温度使方差降 46.5%"的方向一致:同批题在固定温度下的结果比历史更稳定,不只是均值更高。

### 解读边界(如实)

- 这不是对"归因假设"的重新裁决(该假设仍按诊断阶段判定为不成立,差 0.25pp),而是回答一个更直接的工程问题:有没有具体反例。**没有找到任何一个**。
- containment 代理比原表 LLM 判官更严格(v42 在此代理下 64.6% vs 原表该子集对应的 judge_correct 更高),这是检验工具本身偏严导致的绝对水平差异,**不影响库间横向比较的有效性**(同一工具测四个库)。
- 样本仍是 48 题(30-uid 子集的可命中题量),不是全量 314 题;若要更强的置信度,应在预算充裕时对全量库跑同样的对拍,但当前证据已足以支持"无反向证据"这一采纳判据。

---

## 二、正式采纳与代码改动

`scripts/wt_qvf_prototype.py` 第 51-67 行(旗标定义)与第 273-278 行(`_catalog()` 调用点)：

- `_CARD_TEMP0 = int(os.environ.get("QVF_CARD_TEMP0", "1") or 0)`(原默认 `"0"`)。
- 逻辑分支本身**零改动**:`_CARD_TEMP0` 为真值时仍是 `_kw["temperature"] = 0.0` 后传给 `client.messages.parse(**_kw)`,与诊断阶段完全一致;唯一变化是默认值。
- 旗标关闭路径(`QVF_CARD_TEMP0=0`)完整保留,行为与旗标引入前逐字节一致——用于复现历史结果。
- 注释已写明:**自 08-17 起新建卡片库默认 temperature=0;此前所有归档库(`wt_cards_v42`/`v43`/`v5dev`/`v5held`/`keyed`/`tagged`/`opentags`/`newdom` 等,08-17 之前建成)均在未固定温度下建成,两者不可混用于同一对照实验。**
- **未重建任何已归档卡片库**——本次改动只影响此后新建卡片库时的调用参数,`results/wt_cards_v42` 等目录本轮零改动,已发表数字的可复现性不受影响。

冻结文件确认未触碰:`git status`/`git diff` 核实 `scripts/qvf_router.py`、`scripts/qvf_algebra.py` 均不在本次改动列表。**`scripts/complex_query_arm.py` 在本次核查开始前即已存在一份与本任务无关的未提交改动(`QVF_COMPILE_SPEC` / T4 去耦合的编译提示词规范化工作)**——经核实该改动不是本轮产生(本轮仅以只读方式 import 该模块做 execute_plan 对拍,未调用任何写文件操作),推断为同仓库并行任务的在制品,本轮未触碰、未回退,如实记录以免误认为本任务所为。

---

## 三、顺带排查:其他 LLM 调用的 temperature 设置清单(聚焦/编译/读者/判官)

| 职能 | 位置 | 状态 | 备注 |
|---|---|---|---|
| **判官** | `qvf/judge.py:ClaudeJudge.judge()`(`messages.parse`) | ❌ **未设** | 全项目当前唯一的"生产判分口径"判官,S1-S8/STALE/LME/LoCoMo/WikiState 全部经此打分 |
| 判官(S7 专用) | `scripts/wsc_s7_judge.py:159` | ✅ 已设 `temperature=0.0` | 同为判官职能,附属判官反而比主判官严格 |
| **读者(生产路径,STALE-Chain/确认集旗舰臂)** | `qvf/engine_bridge.py:SidecarReader.answer()`(`messages.create`) | ❌ **未设**,且类本身不支持该参数 | `scripts/run_decisive_stale.py:2040` `reader = SidecarReader(model=args.reader)`,是 rt-QVF/oracle/prompted/qvf_v4 等臂的默认在线读者 |
| 读者(同文件其余生成器) | `run_decisive_stale.py` 的 `direct_gen`/`validated_gen`/`conflict_gen`/`_CONTRA_READER`(均为 `qvf/generator.py:BaselineGenerator`) | ✅ 已设(`"haiku" in args.reader` 时 `.temperature = 0.0`,第 2054-2058、2104-2105 行) | **同一文件同一段落内"有的设、有的没设"的直接证据**——唯独旗舰 SidecarReader 没有这条路径 |
| 聚焦(路由 scope/presupposed) | `scripts/qvf_router.py:focus_of()`(`messages.parse`) | ❌ 未设 | **冻结只读文件**,本轮未改动,记录待后续单独走预注册流程 |
| 聚焦(QVF_LLM_INTENT 新旗标,默认关) | `scripts/qvf_router.py` 事件算术意图分类调用 | ❌ 未设 | 同上,冻结文件,且本身是默认关闭的新机制 |
| 编译 | `scripts/complex_query_arm.py:216,821`、`scripts/qvf_algebra.py:772`、`scripts/build_tag_lattice.py:137,176,210` | ✅ 均已设 `temperature=0.0` | 无需处理 |
| 读者(其余生产/基线路径) | `wt_qvf_prototype.py:570`、`wsc_direct_arm.py:207`、`complex_query_arm.py:821`、`demo_one_question.py:103`、`graphiti_baseline.py`、`langmem_baseline.py`、`summary_memory_baseline.py`、`run_mem0_baseline.py` | ✅ 均已设 `temperature=0.0` | 无需处理 |
| 早期架构遗留(非生产路径) | `qvf/adapter.py:SemanticAdapter.analyze()` / `FreeTextAnalyst.analyze()` | ❌ 未设 | 只被 `qvf/pipeline.py` 引用,`pipeline.py` 只被 `scripts/smoke_test.py` 引用——"QVF-frozen(ecac890)"旧协议遗留代码,不在当前生产路径,优先级最低 |

**本轮按纪律未修改** `qvf_router.py`(强制冻结)、`qvf/judge.py`、`qvf/engine_bridge.py`、`qvf/adapter.py`(均不在强制冻结清单内,但改变判官/旗舰读者的采样行为会同时影响所有已发表数字的可复现性,性质与本任务的建卡温度决策相同,理应走同等规格的独立预注册流程,不适合作为本任务的"顺带"项直接改动)。**列为清单,交下一个任务处理**;其中判官与旗舰读者(SidecarReader)两处优先级最高。

---

## 四、成本与纪律核对

| 项目 | 结果 |
|---|---|
| 本任务 API/LLM 成本 | **$0**(核查为纯代码 execute_plan 对拍;决策落地为纯代码文件编辑) |
| 预算上限 | ≤$3 |
| 冻结文件(qvf_router.py / complex_query_arm.py / qvf_algebra.py) | 本轮未改动(`complex_query_arm.py` 存在与本任务无关的并行在制品,已核实非本轮产生且未触碰) |
| 已归档卡片库 | 零重建(`wt_cards_v42` 等目录本轮未写入) |
| 旗标可关性 | `QVF_CARD_TEMP0=0` 完整保留,逐字节复现旧行为 |
| VERSION_LEDGER 记录 | 已追加两行(零反向证据核查 + 正式采纳),含口径分裂警示;未修改任何历史行 |

## 五、总结表

| 统计口径 | 数值 |
|---|---|
| 反向证据("归档对、temp0 错") | 0/48 |
| 反方向("归档错、temp0 对") | 15/48,三轮一致 |
| 三轮 temp0 库逐题互相分歧 | 0/48 |
| 决策 | 采纳,默认值 0→1 |
| 已重建的归档库 | 0 |
| 新发现的 temperature 缺口(生产路径) | 2 处(判官 `qvf/judge.py`、旗舰读者 `SidecarReader`) |
| 新发现的 temperature 缺口(冻结文件/遗留代码,记录不改) | 3 处(`qvf_router.py` 聚焦×2、`qvf/adapter.py` 遗留×1) |
| 本轮成本 | $0 |
