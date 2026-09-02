# 批 33 预注册:全量收口(2026-09-02 晚,用户令"都跑")

范围 = 09-02 现状文档 §五 全部 10 项 + §二 A 档 4 考场 + §三 对手 5 系统 / 读者 / 基线。判据在跑前写死;绝对分一律挂语料、店、嵌入器、读者。
通用口径:haiku-4.5 读者、ClaudeJudge 冻结判官、direct 臂 `QVF_EMBED_BACKEND=openai`(text-embedding-3-small)、配对 McNemar + 144 链簇自助 CI;
所有 n.s. 结论若涉及"不回退/等价"判据一律附簇级 TOST。店目录一律新建、建后只读,不得原地覆盖。

## 33-A 单语料冻结重建(已开跑)
- 店:`results/wt_cards_v45`(OWNER_GATE=0)与 `results/wt_cards_v45g`(OWNER_GATE=1),同一 v2.4 语料、同一建卡器、同一时间窗;
- 臂(全 576):direct / filter / usability / compile / smw / smwplain / 无结构摘要 / smoc(v45)+ smoc(v45g);
- 判据 A1:smoc(v45)− direct ≥ 35pp 且 smoc ≥ 88;A2:六段阶梯每段方向与 v2.0 一致;A3:smoc(v45g)vs smoc(v45)簇级 TOST ±3pp;
  A4:头条以"一语料一店一跑"单句陈述,六个"结构总价"值收敛为一。

## 33-B 残余失败归类($0)
- 55 错(v2.4 头条)→ 重渲染读者所见账目 → card_quality_eval 四模式判写侧 → 冻结执行器复算判读侧 → 人工看金标/判官;
- 报三大类(写 / 读 / 金标+判官)带 Wilson CI;判据 B1:金标类比例 < 20%(否则保留集规范须加"金标平局"闸)。

## 33-C 冻结保留集(WikiState-holdout)
- 从未碰过的 Wikidata 切片建 40 链 / 160 题(四型各 40),与现有 144 链 uid 零交集;建店一次(gate 0),跑 smoc / direct / smw 一次;
- 判据 C1:smoc − direct 的簇 CI 与开发场 [+35,+48] 有重叠;C2:任何臂开发场→保留集下降 ≤ 5pp(否则报"开发场过拟合")。**不许回头改语料**。

## 33-D 规模轴 L2(27b)
- 再建 20 个 L2(≈104K)店(gate 0,与现有 10 店同配置),n=120;臂:smoc / 槽位投影 / haiku 全文;
- 判据 D1:账目 acc ≥ 小库同题 −20pp;D2:账目读取 ≤ 25K tok;D3:$/题 vs haiku 全文 ≥ 3×;vs gpt-5-mini 全文照报无阈值。

## 33-E 更强基线
- E1 bge-reranker-v2-m3 交叉编码重排(dense top-50 → rerank top-10)的 direct 臂;E2 TempRALM 时间项融合检索臂;
- 判据 E:若任一基线把 direct 抬 ≥ 10pp,结构总价改按最强基线报。

## 33-F 上界臂
- F1 oracle 证据(给金句 state_span);F2 oracle 卡(由金链渲染账目);576 题;
- 判据 F:报 90.45 距 F2 的差,并与 33-B 的金标类比例互证。

## 33-G 外场 A 档(各带 $/题、建店 $、延迟)
- PersonaMem v2(600 分层:updated 200 / ask_to_forget 200 / who=other 200)、AMemGym(600)、Temporal Wiki(300 + 闭卷对照)、MINTEval multi_turn(600,按 n_steps_back 分层);
- 臂:smoc / direct(OpenAI 嵌入)/(Temporal Wiki 加闭卷);判据 G:smoc − direct > 0 且簇 CI 不跨零方可写入外场表;闭卷 ≥ direct 的考场标"污染"。

## 33-H 对手系统(60 题标定场 + 若可行 v2.4 全 576;acc / $ / 延迟三项)
- HippoRAG 2、TRACE、Letta、MemOS、Memobase;配置按各自 README 默认 + 同档 haiku 作抽取/读者;
- 判据 H:任何系统进入同台表须附 60 题簇自助 CI;装不起来的如实报阻塞,不得用复刻替代。

## 33-I 盘上零成本
- LongMemEval 其余 289 题(multi-session 133 / single-session 156)smoc vs direct;MAB-FC mh_6k / mh_32k。

## 33-J 小捆
- J1 读时建账目臂(read-time ledger,576);J2 S1/S2 有效性探针(dim1 144 + dim4 144);J3 无填充对照梯(3 格);J4 强读者日期粗化 E1(56 题×2)。

## 33-K 第三厂商读者
- Gemini 3.6 Flash:账目臂 + direct 臂 + 整库直塞臂(v2.4 576;L1/L2 现有 10 店整库);判据 K:协议适配律/读者双端定理是否在第三厂商上复现。

成本上限 ≈$500;结果各写 results/opt_batch33_<track>_verdict.md;由主会话统一提交。
