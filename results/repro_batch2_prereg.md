# 预注册:记忆系统复现批 2(Mem0 + 摘要RAG harness,先于跑数提交)

日期:2026-08-21。目的:扩充 deck 第 6 页"真实跑过 WikiState 的系统"行(现有 LangMem 40.0%)。

## 协议(与 LangMem 行完全同口径,保证可比)

- 考场:同 15 库(uid 等距抽样,与 results/langmem_s5_prereg.md 同一抽法)全部聚合题(60 题);
- 读者/判官:同款 haiku-4-5(temp 0)/同判官——**被测的只是记忆层**;
- 系统 A:**Mem0 v2.0.16 出厂默认**(摄入抽取 = 其默认 LLM 与 text-embedding-3-small;
  逐会话 add,检索 search top-10)——as-shipped 口径,所用模型如实入档;
- 系统 B:**摘要RAG harness**(产品常见模式):每会话 haiku 摘要(保留日期与事实)→
  摘要库上 text-embedding-3-small top-10 检索 → 同读者。它代表"总结再检索"这类 harness 方法;
- 报告规则:描述性行,无通过线,数字无论落哪进表;库抽样固定不得更换;
  token/延迟同口径三列,摄入成本另计脚注。

预期区间(可证伪,基于 LangMem 40.0 与直读 51.7 同子集):两系统预计 35–60%;
若任一 ≥ filter-only(70.0 同子集)→ 如实报并复核我方口径。
成本:Mem0 摄入 ~$1 + 摘要 harness ~$0.5 + 评测 ~$0.5。

## 附录(2026-08-21):批 3 扩充与 Mem0 配置偏离

- Mem0 v2.0.16 出厂默认 LLM 拒绝 temperature<1(400 错,36 行垃圾已删重跑);
  按其论文时代文档默认钉 gpt-4o-mini(temp 0.1),embedder 仍为默认 text-embedding-3-small;
- 新增系统 C:**obs-RAG(LoCoMo 官方最优配方)**——逐会话抽 observations,top-5 检索
  (论文:top-5 observations 优于纯对话日志);
- 新增系统 D:**timeline(TReMu 式)**——逐会话带日期 timeline memo,无嵌入,全时间线直读;
- Graphiti:需本地 neo4j(17687)服务,当前 DOWN,待基础设施后补;
- 同 15 库 60 题、同读者判官协议不变。
