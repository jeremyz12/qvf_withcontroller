# 预注册:考生批 3——StateMemWrapper 及其匹配对照上 WikiState(先于跑数提交)

日期:2026-08-23。来源:OPTIMIZATION_DESIGN_20260823 §8b 考生批 3;用户指示"给 WikiState
增加更多考生"。机制出处:arXiv 2608.19652(UIUC Han 组)附录 F.1,**提示词已从 PDF
逐字取回**(Trace+Resolve 融合提示 + Wrapper-Ctrl 匹配对照,含 ANSWER: 行约定)。

## 为什么先跑这一对

1. **竞品自己的机制在我们考场受审**:StateMem 是与 WikiState 构念最近的新竞品
   (StateMemBench 数据未放出),先把它可复刻的部分(wrapper)搬来同台;
2. **自带干净归因**:Wrapper-Ctrl 与 wrapper 只差"状态结构"(同格式/同 250 词
   Section 1/同 ANSWER 行/同上下文),差值即状态结构的纯价钱——与我们逐段定价同构;
3. **风险声明(先写死)**:若 wrapper ≥ 编译臂 83.3(60 题口径),即"一段提示词
   买到我们全管线"——这是对 QVF 的实质威胁发现,**照样如实入档并升级为头号攻击面**。

## 协议(与五系统复现同台:同 15 库 60 题、同 haiku-4-5 读者、同判官)

- 臂 smw:附录 F.1 融合提示逐字使用;transcript = 该库全部会话按日期排序、
  轮次全局连续编号 `[turn N] role: text`,会话间插 `--- session date: D ---` 行
  (与我们其他臂的日期信息可得性对齐);400k 字符尾部截断照抄(WikiState 库 ~12k
  token 远不触发)。单次调用,max_tokens 800(trace ≤250 词 + 答案),解析末行
  `ANSWER:` 为预测;无 ANSWER 行则取末行并计一次协议偏差。
- 臂 smwctrl:匹配对照提示逐字使用,其余同上。
- 不接检索后端(backend=none):WikiState 库小,全 transcript 在场——即论文
  "long-context+SMW"形态;这也使 smw 与我们整库直读(50.5,418 题口径)可比。

## 判据(先写死;全部同题配对 McNemar)

1. **C1 状态结构价**:smw − smwctrl。预测为正(论文报 +15~+32 归因状态结构);
   若 n.s. → "状态结构提示在带日期语料上无增益"如实入档。
2. **C2 与 QVF 对表**:smw vs filter-only 70.0 / 编译臂 83.3(60 题归档行)。
   预测 smw 落在直读 51.7 与 filter 70.0 之间;**若 smw ≥ 83.3 触发风险声明条款**。
3. 分题型四型照报;吐旧值行为顺手统计(答案命中链上非金旧值的比率)。

## 成本

2 臂 × 60 题 × ~12k in + ~500 out ≈ 1.5M in / 60k out(haiku)≈ **$2.1**
(超 $2 纪律线 0.1,如实注明;不拆步,拆步会破坏同批可比性)。

## 批 3b 预告(另行预注册)

txtai(本地检索锚,需 pip 装)+ A-MEM(clone+pip -e,OPENAI key 走 gpt-4o-mini,
add_note 成本抽 1 库先测)+ cognee;Graphiti 走 FalkorDB 路线,等 Docker Desktop 启动。
