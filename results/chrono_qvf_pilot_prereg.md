# 预注册:ChronoScope 原卷 × QVF 作用域外置试点(先于跑数提交)

日期:2026-08-21。来源:用户点名("尝试我的 QVF 是否能在上面起效")+ 七镜报告 G1
(修复臂对照——"这就是我们论文的天然实验")。

## 材料

- **原卷**:HuggingFace `yashkumaratri/ChronoScope` 的 `merged_scope_benchmark.jsonl`,
  下载校验 1,272,579,530 字节,全量扫描 **1,469,628 链 / 11 链族**——顺带把七镜
  未核实清单第 5 条("1.4 million"口径)核实关闭。
- **判分**:逐行移植其 repo `hf_scope_benchmark.py` 的 `match_relaxed`(含
  postprocess/normalize/候选抽取),与论文运行同口径(sbatch 实证 relaxed 档);
  Drift = 判错 且 命中 `present_day_answer`(其 drift1 定义)。

## 抽样(确定性,无随机数)

5 个作用域链族(carryover / carryover_then / scope_switch / cross_entity_then /
multi_turn_chain)× 各 12 链 = **60 链**;限 `is_drift_candidate=true`(Drift 可测);
族内按 chain_id 排序等距抽取。样本落盘 `data/chronoscope/pilot60.jsonl`。

## 臂(同链同轮配对;读者 claude-haiku-4-5,temp 0,max_tokens 32,指令"只答名字")

- **A0 仅问题**:逐轮独立作答——参数知识下限锚。
- **A1 金上下文镜像**:历史 = 此前轮的问题+金答案(论文头条条件的复刻)。
- **A2 QVF 作用域外置**:**信息与 A1 完全相同**,呈现由纯代码重排:
  ①历史机械转写为带日期账目行 `[as of YEAR] subject: property = value`(零 LLM);
  ②作用域寄存器:轮 0 问题文本正则解析年份初始化;当前轮问题含显式年份则覆盖,
  否则沿用;向当前轮追加一句 `Answer as of {t_q}.`。
  **不使用当前轮的 year/pid 金字段**——只用问题文本可推信息 + 历史金答案,
  与 A1 严格同信息量。
- **A3 自条件镜像**:历史 = 模型自己此前的答案(误差累积条件)。

## 判据(先写死)

1. **C1 病灶复现**:A1 追问轮(turn_index≥1)Drift 率 > 0,且追问轮 Acc 低于其
   轮 0 Acc——现象在我们的读者上复现。不复现则如实入档并停。
2. **C2 主判据(Drift)**:A2 vs A1 追问轮 Drift 同题配对 McNemar;
   **A2 Drift ≤ A1 的一半 且 p<0.05** → "作用域外置消除大部分漂移"在原卷成立。
3. **C3 次判据(Acc)**:A2 vs A1 追问轮 Acc 配对报数,不设通过线——追问常考
   历史中不存在的新属性,Acc 受参数知识约束,不是作用域机制的干净测量。
4. **C4 解释边界**:A0 轮 0 Acc 报出;若 <20%,全部 Acc 结论加"知识受限读者"限定词。

任何方向如实入档;不加选样,不改判据重跑。

## 诚实边界(先写明)

- 读者不在论文模型列表,数字不与其表格逐格可比,只比**方向与结构**;
- A2 是 QVF **作用域编译组件**的适配,不是完整管线(原卷无记忆库设定,无卡片
  抽取与 point_in_time 执行)——对外只可表述"QVF 式作用域外置",不得称完整系统;
- 60 链试点只买方向;显著后扩样再谈效应量。

## 成本

60 链(多为 2-3 轮,含 multi_turn 长链)≈ 700 次调用,短提示短生成,估 **≈$0.5-1**。
