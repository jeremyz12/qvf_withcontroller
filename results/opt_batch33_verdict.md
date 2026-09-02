# 批 33 终判(滚动汇总;2026-09-02 晚起)

预注册 results/opt_batch33_prereg.md。各轨道独立判决文件 results/opt_batch33_<track>_verdict.md;本文只汇总判决与关键数,数字以各轨文件为准。
口径:haiku-4.5 读者、ClaudeJudge(opus-5)、direct = OpenAI text-embedding-3-small top-10、配对 McNemar + 144 链簇自助;成本按 usage token 计。

## 已收口轨道

| 轨 | 判决 | 关键数 | 成本 |
|---|---|---|---|
| **B 残余归类** | B1 过 | 55 错 = 写侧 38(69%,其中 76% 为"值在场但槽位名不合")/ 读侧 13 / 金标+判官 4(7.3%,CI 2.9–17.3);账目链不全等店错误率 18.3% vs 4.0%;lt 近平局题错 37.5% vs 8.6%(p=0.004) | 0.04 |
| **F 上界臂** | 写侧余量 +4.5(下界) | oracle 卡 94.97(vs smoc +4.51,簇 CI [+1.4,+8.0],p=0.002);oracle 证据 76.74(比 smoc 低 13.7,p=8e-11)→ 瓶颈不在证据可得性;残差 29 条金标错标 0,约定欠定 19(占位日期/截止解析);原样重跑翻对 11/29 = run 间抖动 | 5.0 |
| **E 强基线** | E 未触发(反向) | bge-reranker 重排 35.07(−13.2,p=1e-8)、TempRALM 23.44(−24.8);交叉编码器判"无一记忆与聚合题相关"(99.8% top-1 分<0.1),gold 召回 0.788→0.573/0.501;α→0 即 direct 为族最优;结构总价按 48.26 不变 | 7.5 |
| **G3 Temporal Wiki** | G 判负(显著反向) | smoc 82.3 < direct 86.7(−4.3,簇 CI [−7.0,−2.0],p=1e-3);闭卷 25.3,去污染子集结论不变 → 非污染;机制 = 建卡器按叙述年份填日期(31.6% 行年份≠快照年);边界:记忆条须为"一次带时刻的陈述",不能是"某时刻对全史的快照" | 6.3 |
| **G2 AMemGym** | G 判负(负向) | 600 题 / 20 人物:smoc 49.0 vs direct 52.3(EM −3.3,簇 CI [−8.8,+2.2],p=0.17;ClaudeJudge −4.7,p=0.05);全上下文 54.0 仅 +2.0 → 瓶颈非检索;机制 = 题靠用户措辞细微差别区分近义选项,卡片 span 抽象丢掉细微差别(29-K 表达轴重现);smoc 4.3× 成本 | 15.1 |
| **H1 HippoRAG 2** | 同台入表 | 60 题 55.00,CI [41.7,68.3];vs direct +3.3 n.s.;vs smoc −33.3(p=9e-5);检索赢(链态 recall@10 0.915)裁决输(整链在场仍 56.9);41.7% 查询事实闸全关退回 DPR;换 gpt-4o 闸无改善 | 1.8 |
| **H3 Letta** | 服务端 BLOCKED;文件系统 agent 入表 | 0.16.x 无 SQLite 路径(源码级),无 Postgres;Letta 式文件系统 agent 60 题 56.67(vs direct +5.0 n.s.;vs smoc −28.3,p=5e-4;每题 0.021 美元,约 21×) | 1.6 |
| **H4 MemOS** | 同台入表(general_text 路径;tree_text 图记忆因 Docker 阻塞未测) | 60 题 45.00,CI [31.7,58.3];vs direct −6.7 跨零;vs smoc −40.0(p=0.003);vs Mem0 +18.3;haiku / gpt-4.1-mini 抽取不可分;写时扩张 4.1 节点/会话,聚合题 top-10 端不回全序列 | 4.2 |
| **H5 Memobase** | BLOCKED | 服务端硬依赖 Postgres+Redis(源码三证),本机 Docker 后端无法启动;仅静态 schema 对比;日期入口 = message.created_at | 0 |
| **I 盘上(第一段)** | 两条否定 | LME single-session-preference smoc 42.9 vs direct 71.4(−28.6,CI 排除 0;弃答 35.7%,写侧不抽偏好类内容);MAB-FC mh_6k/mh_32k 零效应(sh_6k 与 mh_6k 草堆逐字节相同 → 61pp 差全由跳数,该格无鉴别力);LME 建卡实测每题 0.19 美元;建卡器失败批次不记 usage | 8.3 |

## 进行中
A 冻结重建(direct 47.57、smwplain 53.47 已出;smoc×2 / smw / filter / usability / compile / summary 在跑)、C 保留集、D 规模 L2、G1 PersonaMem、G4 MINTEval、H2 TRACE(出厂配置 60 题 16.67,0 条取代边;其 LoCoMo 配置重跑中)、J 小捆(J4 已收口:补全日期**没有**救回 gpt-5-mini 降级层 → "日期粗化"归因猜想被否定)、K Gemini、I 第二段(LME multi-session 133 + single-session 126)。

## 已能写进论文的三句(证据已齐)
1. 结构溢价对检索基线的强弱不敏感:更强的重排/时间感知检索让 direct 变差而非变好;完美检索的直读也只到 76.7,距账目臂 −13.7。
2. 写侧余量有上界:金链账目 94.97,即建卡再完美最多再拿 +4.5;残余里 2/3 是数据表约定欠定而非金标错。
3. 账目机制的边界:记忆条须是"带时刻的陈述";快照式语料(Temporal Wiki)与偏好类内容(LME-preference)上账目臂显著输给直读。
