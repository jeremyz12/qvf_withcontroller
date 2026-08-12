# QVF 研究 · 智能体接入简报

> 版本：2026-07-31 深夜 | 状态：判定实验即将启动
> 本文档自包含：假定读者（其他 AI 智能体或协作者）没有任何先前对话上下文。
> 主会话正在运行判定实验；本文档末尾列出了可并行开展、且不与主会话冲突的准备任务。

---

## 一、项目一句话

**QVF（Query-conditioned Validity Filter）**：研究"LLM 检索到长期记忆之后错误使用"的问题——检索回答的是*相关性*，但生成需要知道的是*该记忆对这个查询当下是否有效*（旧工作地对"现在在哪工作"是干扰项，对"2023 年在哪工作"却是正确证据）。

当前研究问题已收敛为：**神经符号组合是否成立**——用通用 LLM 做抽取（entity/slot/value/新旧配对），喂给一个确定性的符号有效性引擎做裁决，能否在"陈旧/冲突记忆"场景显著减错。

## 二、背景时间线与关键数字（重要：理解为什么走到这一步）

### 第一代系统（用户早期工作，github.com/jeremyz12/qvf_withcontroller，已克隆到 `external/qvf_withcontroller/`）
纯符号规则引擎（零 LLM 调用），检索后有效性控制器。关键事实：
- STALE 基准历史结果 Direct 14.75% → QVF 90.67%（**+76pp**），但归因分析证明增益来自**手写 benchmark adapter 提供的 oracle 新旧配对**；固定 adapter 后引擎 policy 本身的净增量仅 **+2.83pp**
- MemConflict100 历史结果 58→67（9 胜 0 负）——唯一干净的正信号，但是 n=100 的历史保护分数，未在当前代码树重跑
- 跨模型脆弱：同一 sidecar 让 GPT-4o-mini +4，却让 Claude Haiku **-4**（73→69）
- 代码深读结论（本次完成）：抽取契约是 span-grounded 的（每个语义字段必须是原文逐字子串）、可分解为三个头（查询焦点/槽位填充/跨记录关系配对）、校验器返回机器可读拒收原因（可当免费监督信号）；`_pipeline_core.py` 约 40% 是死代码；router 含数据集形状的词表（发表时必须切除）；clarify 动作实际不可达

### 第二代系统（本仓库 `qvf/` + `eval/`，本次会话新建）
LLM 驱动的 Semantic Adapter：把（查询+检索记忆+元数据）转成结构化 Validity Map（原子声明、9 元关系、查询条件化适用性/时间标签、充分性、风险标志），API 层 schema 强制。关键实验结果（全部当前可复现）：
- 冒烟测试：同一记忆随查询翻转 SUPERSEDED↔HISTORICAL 标签、条件限定保留——机制按设计工作
- **方案 A null 结果**（LongMemEval-S cleaned，82 题 × 3 条件，opus 读者）：qvf 46/67 ≈ prompt-only 45/66 ≈ baseline 44/67——**强读者面前任何中间表示（结构化或散文）都无端到端增益**
- 成本实测：qvf $0.237/题（51s）、prompt-only $0.146/题、baseline $0.051/题（opus 单价 $5/$25 每 MTok）

### 两代系统合并出的结论
价值集中在**抽取/对齐**这一步：不在下游 policy（+2.83pp）、不在呈现格式（null 结果）。第一代证明"oracle 抽取 + 引擎"上限极高，第二代证明抽取器可以通用化——**但"通用 LLM 抽取 + 引擎"这个组合从未被测过**。判定实验就是去测它。

### 用户已做的路线决策
- ❌ 训练 RL/蒸馏策略（与 MemChain 竞争位差、微调缺点多）
- 🔒 测量/诊断基准论文（保留为备选，用户觉得不太符合想法）
- ✅ **当前主线：最小修改现有 QVF = 神经符号组合**，发表预期诚实定在 Findings/系统 track 档位

## 三、即将运行的判定实验（主会话负责，其他 agent 勿动）

**目的**：一次实验出两个关键数字——(a) 组合是否成立（生死）；(b) prompted 抽取离 oracle 差多远（headroom）。

**设计**：STALE 子集（前 30-40 个条目 × 3 维查询 ≈ 100 查询）× 三条件：

| 条件 | 抽取 | 裁决 | 读者 |
|---|---|---|---|
| direct | 无 | 无 | claude-haiku-4-5（BM25 top-10 直读） |
| prompted+engine | Claude 从检索轮中抽 structured_records | 冻结符号引擎 → sidecar | claude-haiku-4-5 读 sidecar |
| oracle+engine | 从数据字段 M_old/M_new/explanation 程序化构造 | 同上 | 同上 |

读者选 haiku 是有意的：弱读者是这条路线的目标部署档位（强读者已被 null 结果证明不需要帮助）。判分用 Claude judge（对齐"须反映新状态、不得把旧状态当作当前"的规则）。预算 $30-50。

**判定规则（预注册）**：
- prompted+engine 显著优于 direct 且抽取覆盖率不崩（fail-closed 拒收率 <30%）→ 路线成立，进入系统论文轨道
- prompted+engine ≈ direct 或覆盖率崩塌 → 路线证伪，产出"LLM 抽取喂不饱严格符号契约"的负结果 + 拒收原因分布，转向备选路线
- oracle+engine 与 prompted+engine 的差 = 抽取 headroom，无论生死都写进论文

**产出位置**：`results/decisive_stale_*.jsonl` + 主会话的分析报告。

## 四、代码与数据地图

```
D:\ZZL_cluade\
  qvf/                    第二代核心库（schema/adapter/generator/judge/pipeline/config）
                          ⚠️ 主会话实验期间勿改
  eval/
    run_eval.py           实验主脚本（--mode 逗号分隔条件、--resume 断点续跑）
    datasets.py           LongMemEval/LoCoMo 加载器
    stale_dataset.py      STALE 加载器（已跑通；M_old/M_new=数据内 oracle 标签）
    download_data.py      数据下载
  scripts/analyze_results.py   结果分析（弃权拆分/分题型/成本/错例对照）
  data/
    longmemeval_s_cleaned.json / longmemeval_oracle.json（官方推荐 cleaned 版）
    locomo10.json
    stale_T1_T2_400_FULL.json      (CC BY 4.0)
    memconflict_step4_4.jsonl      (⚠️ 仓库无许可证，论文使用需标注)
  results/                实验产出（planA_s_15pt.jsonl = 82 题三条件null结果等）
  docs/
    research_proposal.md  研究方案（含 prompt-only 对照与防御性设计）
    related_work.md       112 篇文献的调研简报（含基准精确细节、SOTA、新颖性定位）
    related_work_findings.json    结构化文献数据
    paper_outline.md      论文大纲（旧版，待按新路线改写）
  external/qvf_withcontroller/    第一代符号引擎（入口 run_raw_memory_validity_controller，
                          输入契约见 01_核心代码/src/qvf_validity_admission/raw_input.py
                          与 examples/run_raw_input_example.py）
  .env                    ANTHROPIC_API_KEY（⚠️ 勿外传勿提交）
```

模型配置：默认 `claude-opus-5`，环境变量 `QVF_ADAPTER_MODEL`/`QVF_GENERATOR_MODEL`/`QVF_JUDGE_MODEL` 可覆盖；`QVF_MOCK=1` 全流程免 API 跑通。

## 五、给其他智能体的并行任务清单（按优先级）

以下任务与主会话不冲突（不碰 `qvf/`、`eval/run_eval.py`、`.env`、不跑花钱的 API 实验）：

1. **MemConflict 加载器**（`eval/memconflict_dataset.py`）：解析 `data/memconflict_step4_4.jsonl`（persona + Full_Session_Chain 格式，QA 嵌在会话链中），输出与 `eval/datasets.py` 的 `QAInstance` 相同的接口。这是判定实验阳性后的第二战场，也是基准备选路线的素材。参考官方评测脚本：github.com/TaoZhen1110/MemConflict 的 `Evaluation/` 目录（含 Mem0/Letta/MemOS 等六系统脚本与 AA/SEH@K/SRS 指标定义——顺便整理一份指标说明）。
2. **旧引擎体检**：在 `external/qvf_withcontroller/01_核心代码` 下跑通 `examples/run_raw_input_example.py` 和 smoke test（PYTHONPATH=src）；补一个最小回归测试断言"旧值确实被 block 为 current"（现有 smoke test 没断言这个）；列出 `_pipeline_core.py` 中与 `memory.py` 重复的死代码清单（勿删，先列清单）。
3. **论文相关工作章节草稿**：基于 `docs/related_work.md` §3-4，写 QVF vs {MemChain, ConvMemory v3, MemStrata, STALE/CUPMem, MemConflict} 的逐一对比表 + "rule-based 攻击"的防御段落草稿（框架：可执行形式语义而非启发式；须声明切除 router 词表）。
4. **诊断最小对集设计**：起草 50-100 对成对查询的构造方案（同记忆集，当前意图 vs 历史意图；仅时间戳更晚 vs 显式更新语言;复述 vs 真矛盾）——所有路线通用的资产。可基于 STALE 的 M_old/M_new 字段程序化生成初稿。
5. **弱监督标签脚本**（备选路线资产）：从 LongMemEval 的更新链（answer_session_ids + haystack_dates + question_date + question_type）推导声明级 SUPERSEDED/CURRENT/HISTORICAL_FOR_QUERY 标签。

**纪律要求（对所有 agent 生效）**：
- 不引用第一代仓库的"历史保护分数"作为当前结论（其文档自己声明未重绑定代码树）
- 不跑任何花钱的 API 调用（判定实验由主会话统一执行和记账）
- 所有新代码走新文件，不改主会话正在使用的模块
- 协议卫生：任何评测记录数据版本、judge 模型与提示、检索预算、随机性来源

## 六、关键事实速查

| 事实 | 数值/位置 |
|---|---|
| STALE 数据内 oracle 标签 | `M_old`/`M_new`/`explanation` 字段（槽位级） |
| STALE 三维探针 | dim1 直接问 / dim2 陷阱前提 / dim3 隐式使用（旧引擎的 reader_profile 与之对应） |
| 旧引擎抽取契约要点 | span 必须逐字且唯一；entity/slot/value/claim 必填；temporal_relation 需 evidence + 目标 ID 全覆盖；fail-closed |
| 已花实验费 | 约 $95（试点 $10 + 方案A $85） |
| 单价参考 | opus $5/$25、sonnet $3/$15、haiku $1/$5 每 MTok |
| 已证伪的主张 | "结构化图谱对强读者有端到端增益"、"通用准确率插件" |
| 存活的主张（待判定实验检验） | "LLM抽取+符号引擎在冲突/陈旧场景减错且普通召回零退化" |
