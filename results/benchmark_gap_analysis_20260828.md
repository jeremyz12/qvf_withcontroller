# WikiState 对标十基准:缺口分析与补齐台账(2026-08-28)

> 方法:10 篇已发表基准论文的标准化报告卡(舰队逐篇取证,存
> results/benchmark_report_cards_20260828.json;每张卡含规模/构建/人工验证/
> 判官验证/质控/划分/基线/成本报告/发布 11 栏)× 我方档案逐项对表。
> 对标集:LongMemEval(ICLR25)、LoCoMo(ACL24)、STALE、MemConflict、MemOps、
> StateMemBench、Veracium、PrecisionMemBench、ChronoScope(ACL26)、Neuromem。

## 一、领域现状速写(十卡合读)

| 报告项 | 领域现状 | 我方现状 |
|---|---|---|
| 人工验证+一致性统计 | **十家无一报 κ**。LongMemEval 3 专家 550 小时但无 κ;STALE"专家审校"无人数;MemConflict 仅定性;其余多为 NONE | 预注册 Cohen's κ 协议 + 检查题在收(**收上即超全场**) |
| 判官对人效度 | **仅 LongMemEval 有数**(每型 30 题,>97%);Veracium 明写零验证;多家无判官(词面 F1) | 机械效度 97.2%@2,555 可提取行(scripts/mech_consistency_check.py v2 规则,逐行产物 results/mech_consistency_20260830.jsonl;账目/协议五臂 100%);判官-人类一致率待人工核验重叠集 |
| dev/test 划分 | **十家无一有正规 split**(Veracium 生成序保留、Neuromem 时间检查点为最好实践) | S8 组合题自带 SEEN/UNSEEN 一次性测纪律 + s8_heldout;四型主场无 untouched 测试集(见补齐 F1) |
| 成本报告(token/$/延迟) | 多家 NONE;MemConflict/PrecisionMemBench/Neuromem 仅延迟;**Veracium 最全(tok/q 逐架构)** | **全场最全**:38 行榜单三项全记 + 建库耗时 + 成本三档表 |
| 污染/参数泄漏检查 | LongMemEval NONE;ChronoScope 以确定性论证代替;余家 NONE | 构建期参数可答排除闸;**闭卷基线双读者在跑**(量化上限,补上即超全场) |
| 干扰/弃答子集 | LongMemEval 30 道假前提最完备;LoCoMo adversarial 14.6% | premise_check 陷阱型 + STALE 系 400 探针 + inj30 注错臂(已有,待文档化) |
| 发布/许可/datasheet | 除 StateMemBench 外全公开;**无一家有正式 datasheet** | 未公开(缺口);datasheet 本日补齐(docs/wikistate_datasheet_v2.md) |
| 版本维护 | LongMemEval 清洗版+changelog 为最佳 | v1→v2 缺陷自审+修复史 + 店版本挂口径纪律(**独有,超场**) |
| 基线广度 | LongMemEval 9+ 配置;MemConflict 6 系统;多家 3-6 | **16 系统 + 6 读者矩阵 + 梯子逐段**(最广) |
| 统计纪律 | 多家单跑无检验(StateMemBench 明写 single run) | 配对 McNemar/CI/FDR 全族控制 + 多种子(**独有级**) |

## 二、我方优势(对外可写的差异句)

1. **金标可机核**:金答案纯代码从链导出、逐字锚点 542/542 机器全检——对
   比 LoCoMo(人编 15% 轮次)与 LongMemEval(5% 得率人工筛)的标注噪声路径;
2. **考场自审并修复公开**(v1 三缺陷→v2)+ 店版本口径纪律:十家仅
   LongMemEval 有事后清洗可比;
3. **成本-准确度双轴完整**:38 行 acc/tok/延迟/建库全记,超过最佳者 Veracium;
4. **基线广度与机制验尸**:16 系统逐行归因(抽取丢链/图谱排序错/盖章天花板
   11.7),领域内没有第二家做机制归因;
5. **稳健性套件**:乱序阶梯、风格配平、硬负例、身份泄漏否证、判官交叉审计、
   多种子孪生——十卡中最接近的是 ChronoScope 的确定性论证,广度不及;
6. **人工验证协议(收数后)**:预注册 κ + 检查题 + 裁决规则,将是十一家中
   唯一有独立评审一致性统计的基准。

## 三、缺口与补齐台账(用户令:缺的补上)

| # | 缺口 | 状态 |
|---|---|---|
| F1 | 四型主场无 untouched 测试集(生成器确定性无种子,重跑=同题) | **待预注册批 26**:新域链条(P26/P69/P1303 已探明)+ v2 口径出题 = 全新保留测试集,冻结后只测一次;估 $15-25,等用户点单 |
| F2 | 判官对人效度数 | 一半已补:机械效度 **97.2%**@2,555 可提取行(可复现:scripts/mech_consistency_check.py;账目臂 100%,残余分歧双向——判官正确否掉计数碰对内容错的答案 + 少数宽松格);人类侧待人工核验重叠 20 题(协议已预注册) |
| F3 | 闭卷污染基线 | **在跑**:haiku + gpt-5-mini 双读者零上下文 576(落地即入榜单) |
| F4 | datasheet/许可/发布件 | **本日补齐**:docs/wikistate_datasheet_v2.md(含许可建议:数据 CC BY 4.0、代码 MIT、检查题钥匙不随发布);公开与否为用户决策 |
| F5 | 弃答/陷阱子集文档化 | 并入 datasheet §陷阱与弃答(premise_check/STALE-400/inj30 均已有实测) |
| F6 | 人工一致性统计 | 平台在收,协议超场;等评审完成(用户侧) |
| F7 | Oracle 证据配置(LongMemEval 最佳实践) | 已有等价物:金链直给臂 + 账目即结构化 oracle 近似;datasheet 记为官方配置之一 |

## 未核实清单

十卡为舰队一手取证,本机未逐篇复核原文;引用任一卡中数字入论文前过七问
框架;MemConflict"判官经人工核对"与 STALE"三独立跑"等细节以原文为准。
