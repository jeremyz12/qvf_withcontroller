# 预注册:考生批 8(repro batch 4)——WikiState 考生扩编(先于跑数提交)

日期:2026-08-25。用户指令:扩充其他方法/相关研究成果在 WikiState 上的效果。
协议与五系统复现完全同台:同 15 库 60 题、同 haiku-4-5 读者、同判官,结果并入
六方法族表(现有:obs-RAG 13.3 / Mem0 26.7 / LangMem 40.0 / 摘要RAG 46.7 /
直读 51.7 / timeline 63.3 / smw 81.7* / QVF 70.0/83.3)。

## 考生(零基础设施四个;Graphiti 仍等 Docker Desktop)

| 考生 | 形态 | 摄入侧 | 预测 |
|---|---|---|---|
| txtai | 本地嵌入 flat-RAG | 零 LLM(sentence-transformers) | ≈直读 51.7±5(检索器质量锚) |
| langgraph InMemoryStore | 官方记忆基建 | 零 LLM(openai 嵌入) | ≈直读(纯存取,无加工) |
| A-MEM | Zettelkasten 演化笔记 | 每 add 一次 LLM(gpt-4o-mini) | 低于直读(抽取丢链结构,同 Mem0/LangMem 模式) |
| cognee | LLM 知识图谱抽取 | cognify 建图(LLM) | 低于直读;图实体归并可能吞多版本状态(有信息量的失效模式) |

## 纪律

- **抽样先行**:A-MEM 与 cognee 先摄入 1 库实测 token/$,超 $0.15/库 则先报再扩;
- 检索 top-k 与五系统复现一致(k=10;obs-RAG 例外曾按其论文 k=5);
- 判据:进表即胜——本批不设通过线,如实入档;分题型照报;
- 任何系统跑挂(API 兼容性)如实记"管线失败"并区别于"真实失败"(obs-RAG 先例)。

## 成本

txtai/langgraph ≈$0.3(仅读端);A-MEM/cognee 视抽样,预计 $1-3。合计 ≤$4。
