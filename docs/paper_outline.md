# 论文大纲（工作标题）

**QVF: Query-Conditioned Validity Filtering for Memory-Augmented Language Agents**

目标会场（按契合度）：ACL / EMNLP 主会（NLP 应用与对话）、ICLR / NeurIPS（如强调
结构化中间表示与代理记忆）、或 TACL（篇幅允许更充分的形式化与分析）。

---

## Abstract
- 检索回答 relevance，生成需要 query-conditioned validity；错位造成
  时间性错误/伪冲突/条件丢失/该弃权不弃权
- 提出 QVF：后检索、前生成的 Semantic Adapter，输出结构化 Validity Map
- LongMemEval + LoCoMo 上 knowledge-update / temporal / abstention 题型显著提升，
  简单题型不受损（数字待实验）

## 1 Introduction
- 动机案例：Google→Anthropic 知识更新；"现在"与"2023 年"两个问题需要相反的证据选择
- 核心论点：有效性是查询的函数，不是记忆的属性
- 贡献列表（概念 / 系统 / 实证 / 资源）

## 2 Related Work
（从 docs/related_work.md 提炼；四条线）
- 2.1 记忆增强代理与记忆系统（MemGPT/Letta、Mem0、Zep/Graphiti、A-Mem、HippoRAG）
  ——区别：它们在**写入/存储时**管理有效性（如双时间边），QVF 在**读取时按查询**判定
- 2.2 知识冲突与时间推理（context-memory / inter-context conflict、TimeQA、TempReason 等）
  ——区别：冲突检测多为全局二元判定；QVF 输出查询条件化的细粒度标注
- 2.3 RAG 过滤/验证与结构化中间表示（Self-RAG、CRAG、NLI 过滤、claim decomposition）
  ——区别：过滤是"删证据"，QVF 是"标注证据 + 解释关系 + 交给生成器"
- 2.4 长期对话记忆基准（LongMemEval、LoCoMo）

## 3 Method
- 3.1 问题设定与符号（q, t_q, M, V(q,M)）
- 3.2 Validity Map：查询接地 / 原子声明 / 关系图 / 查询条件化标注 / 充分性与风险
  （附封闭词汇表定义表）
- 3.3 Semantic Adapter：规范提示词 + API 层结构化输出校验 + 引用完整性检查
- 3.4 有效性条件化生成：使用规则（时间匹配、弃权、条件保留）
- 3.5 设计原则讨论：封闭证据边界；为何"晚时间戳≠取代"；为何历史正确≠全局失效

## 4 Experimental Setup
- 基准与题型映射表；条件与消融；持恒变量声明；judge 设置与可比性声明；成本报告口径

## 5 Results
- 5.1 主对照（按题型分解的正确率表）
- 5.2 消融（-relations / -temporal / filter-only / adapter 规模 / oracle 检索）
- 5.3 弃权质量（正确弃权率 vs 误弃权率的权衡曲线）
- 5.4 成本-收益（新增 token 与延迟 vs 提升幅度）

## 6 Analysis
- Validity Map 标注分布与错误归因（适配器错 vs 生成器不遵从 vs 检索缺失）
- 案例研究：knowledge-update 正反例、时间域不重叠的"伪冲突"、条件保留
- 引用完整性违规率（封闭证据边界的可执行性）

## 7 Limitations
- 适配器额外延迟与成本；LLM-judge 偏置；两个基准均为英文对话域；
  adapter 与生成器同族模型的潜在相关性

## 8 Conclusion

## Appendix
- A. Semantic Adapter 完整规范提示词（即研究对象本体）
- B. Validity Map JSON Schema
- C. 生成器提示词（baseline / qvf）
- D. judge 提示词与人工复核协议
- E. 完整分题型结果与样例 Validity Map
