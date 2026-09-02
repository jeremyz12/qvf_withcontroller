# QVF 与 WikiState 现状、下一批考场与考生、论文叙事缺口(2026-09-02)

由 102+ 代理工作流(9 路检索扫描 → 逐候选对抗核验 → 5 位评审人格找缺口 → 逐条对照仓库核实 → 完整性批评)
产出,本人逐数复核其中改变既有结论的条目并已入档(commit d7a002e)。标签:【已验证】【方向性】【探针】【撤回】【未测试】沿用编撰口径。

## 一、现状:QVF 与 WikiState 各是什么水平

### QVF(系统)

| 主张 | 数字 | 标签 | 出处 |
|---|---|---|---|
| 净化语料 v2.4 全库账目臂(haiku 读者) | smoc **90.45** vs direct 48.61,结构总价 **+41.84** | 已验证(但为三文件拼接,见 §三) | opt_batch31_verdict:197-202 |
| 清洗增益(v2.0→v2.4,同题配对) | +7.81,题级 p=1.6e-05;**簇 CI [+2.95,+12.67]**,链级 p=0.022 | 已验证(簇级刚过族阈值,无余量) | cluster_units_20260902 |
| 干净子集阶梯(v2.0 语料 332 题) | 选择 +18.98 / 认证 **+5.72(p=0.0019)** / 计算 +10.84 / 账目+协议 +6.93 | 已验证(本日新算,每段比全库更大) | ladder_decontamination_20260902 |
| 压缩 vs 结构(批 30) | 无结构摘要 52.78 = 全文 52.26;账目 82.64——压缩贡献零 | 已验证 | compendium §六 |
| 弱读者抬升(同读者同信息) | 56.42 → 82.12,+25.7,p=7e-25 | 已验证 | compendium §一 |
| 读取成本(小库 14K) | 账目 1/5.5 全文;同精度(smoc 82.64 vs smw 81.25 n.s.) | 已验证 | compendium §一 |
| 规模轴账目"恒定 2.9K" | **证伪**:L2(104K)账目读取实测 20,204 tok、80.0 分;对 gpt-5-mini 全文成本优势 5×→1.14×,准确率 +15 仍在 | 撤回→改"衰减率"主张 | ladder_decontamination §三 |
| 协议适配律 | F.1 协议 haiku +10.9 / gpt −3.5 / qwen n.s. | 已验证 | compendium §三 |
| 推理读者反向受损 | gpt-5-mini 读账目 78.65 < 读全文 85.76(p=1.4e-4) | 已验证,限定"非推理读者" | MASTER 308-311 |
| 16 系统同台(60 题 v1) | QVF-编译 83.3 ≫ Mem0 26.7 / LangMem 40.0 / A-MEM 43.3;Graphiti †3.3 / LightRAG †1.7 | 已验证,中段 CI 互覆盖不排名 | compendium §五 |
| 外场 STALE | +15.0,p=0.0079,三判官同向 | 已验证(唯一对外外场主张;红队三连击见 §四) | compendium §七 |
| ElephantBench-OB | C=98.3 vs 闭卷 14.2 | 已验证(合成) | opt_batch29 |
| 批 32:第三人称同槽干扰 | smoc −18.4 vs direct −4.9——**QVF 真实缺陷** | 已验证 | opt_batch32_verdict |
| 批 32′:写侧归属闸 | 干扰建卡 83%→1%;闸店 vs 无闸 +17.01(簇 CI [+11.6,+22.2]);vs v2.4 −1.39 | 修复效力已验证;**非劣性未证**(±3pp TOST 不过,±5pp 过) | opt_batch32p_verdict + cluster_units |
| 批 32′:读侧只加提示 | −9.90(簇 CI [−14.4,−5.7]),写 vs 读 +8.51 | 已验证 → 修复点在写侧 | 同上 |
| v3 新题型 | correction_count +15.3(p=2e-04);corr_longer +12.5(p=0.004,翻转子集 +28.6) | 已验证;correction_date / scoped_count / corr_tenure 撤回 | opt_batch32 / 32p |
| v2.4 残余失败 | 55 错落 35/144 链(≥3 错尾 13× 富集);计数型以**少数**为主;金标平局残留 ≥1 | 已验证(本日) | ladder_decontamination §二 |

一句话:**QVF 在自建 WikiState 上是强仪器**(结构总价 +41.8、逐段可定价、清洗后每段更大),
**对外主张只有 STALE 一场**,规模轴与非劣性两处此前措辞过强,今日已按证据收窄。

### WikiState(基准)

| 项 | 状态 |
|---|---|
| 规模 | v2:144 链 / 576 题(4 型);v1:105 链 / 418 题;v3 增补 correction_count + corr_longer |
| 语料版本 | v2.0 → v2.1/2.2/2.3/2.4 四刀(247 句,−0.42%,542 锚全程);v2.4 = 唯一能陈述覆盖范围的版本(1,100 填充会话逐个审计) |
| 效度硬指标 | 锚点机核 542/542;闭卷污染 0.69/7.81;判官机械一致 97.2%;顺序不变性 n.s.;格式伪影已定价 |
| 污染因果 | 受污染链判错 76% 为"模型多数了"=金标错;清洗逐题型效应与理论预测逐格吻合 |
| 人工核验 | senior2 84/84(污染链富集 7.2×,p=0.053);author 8/149;senior1 0/85;**κ 仍不可算**;第二轮 85 题已部署 |
| 复现性 | 同店两跑逐题一致 94.9%;**但 wt_cards_v44clean 被原地覆盖三波**(103/26/15 店),v2.2 全库跑已不可从盘上复现 |
| 交付短板 | 零公开、无保留集、人工覆盖 2.2%、datasheet 冻结在 08-28(未记 28–32′ 缺陷) |

一句话:**作为内部测量仪器强且经得起复算;作为对外可引用基准弱**,差距全在社会化验证(κ / 保留集 / 公开),不在测量学。

## 二、其他考场(外部基准):153 个候选 → 87 个逐一对抗核验(第三批 62 个待入)

核验闸:存在 + 开放许可 + fit≥2(直击"按查询条件化的状态有效性") + 接入忠实(不伪造对话)。
**先纠正扫描的四个"新考场"其实已跑过**:HoH(8 月,final_table 直读 95%)、LoCoMo(人工抽查闸未过)、
MemoryAgentBench-FC(=MAB-FC,08-12 负结果)、TempReason L2;Supersede 的评测集就是 LongMemEval-KU 78 题;
HorizonBench 与 MINTEval multi_turn 是同一份数据。

### A 档:建议跑(fit 3,许可干净,接入近乎零改造)

| 考场 | 直击什么 | 规模/成本 | 许可 | 主要风险 |
|---|---|---|---|---|
| **PersonaMem v2**(COLM 2025) | 逐行标注 QVF 三条腿:updated(取代,1,047 行且给出被取代值)/ ask_to_forget(1,048)/ who=other(第三人称 522) | 600 题分层 ≈ $10–15 | CC-BY-4.0 | GPT-4o 合成,仅 90 对人工校验(best-response 90%) |
| **MINTEval multi_turn**(=HorizonBench) | 偏好随时间演化,n_steps_back 给剂量-响应曲线 | 600 题/40 用户 ≈ $25–45(建卡占大头) | CC-BY-4.0 | 上下文 155–385K,haiku 全文臂跑不了;须按 n_steps_back 分层抽样 |
| **AMemGym**(ICLR 2026) | 2,200 个(问题,时段)对,exposed_states 金标,精确匹配无判官 | 600 题单臂 ≈ $3–8 | MIT / CC-BY-4.0 | 静态转换丢掉助手回复(论文称 off-policy),须披露 |
| **Temporal Wiki**(arXiv 2506.07270) | 878 实体的逐年快照,employer/team/position 槽位,19/20 链答案随年变 | 300 题 ≈ $5 | MIT(正文 CC-BY-SA) | 公众人物 → 预训练污染;必须配闭卷对照臂 |

### B 档:有条件跑(fit 2–3,各有一处硬约束)

| 考场 | 价值 | 约束 |
|---|---|---|
| GroupMemBench | 唯一的**归属压力测试**(多主体共享记忆,asking_user_id 条件化)——正是批 32 暴露的缺陷 | 数据无许可声明,需致信作者;语料 10–30× 常规体量 |
| GateMem | 727 访问控制 + 763 主动遗忘检查点,MIT+CC-BY | 全合成三段流水线 |
| CoTempQA(ACL 2024) | 共时重叠推理,S1 同主体类;$3–5 全臂 | 公众人物污染;HF 标 CC-BY-SA |
| BEAM knowledge_update(ICLR 2026) | 180 题严格取代;100K/500K 分层 | CC-BY-SA 传染:派生卡必须同许可或不发布 |
| TDBench(ICLR 2026)synthetic-Medical | 时态数据库元组 = QVF 卡(key→T value);**用实验回应"时态 DB 先例"这条相关工作缺口** | 仓库无 LICENSE;仅合成 Medical 切片无第三方权利 |
| RHELM(Microsoft) | 提供方最可信,629 会话 + 邮件 + 附件异质表面 | 纯取代核心只有 65 题 |
| EverMemBench(KDD 2026) | 多方、365 天跨度,归属压力 | Gemini 全合成 |
| Memora / DynamicMem / PERMA | Apache/MIT,取代密度可调 | 有效 n = 10 个人物,推断只能按簇 |

### C 档:自然真人对话(扫描整类漏项,批评家点名)

| 考场 | 状态 |
|---|---|
| CareCall-Memory(NAVER,真实部署对话 + 原生记忆更新标注) | 许可禁止修改与再分发 → 无法做 QA 转换;只能引用 |
| AlpsBench(SIGIR 2026,WildChat 真人对话) | ODC-BY,~938 更新题带金标,$3–16;多语种(样例葡/俄语),须过滤 |
| MSC / DuLeMon / RealTalk / Conversation Chronicles | 第三批核验中 |

### 已否决(勿再列为"新考场")

HaluMem(CC-BY-NC-ND,禁派生)、LTP/A-TMA(无公开数据)、LifeBench(仓库 404)、StateAuditor(无代码)、
LongMemEval-V2(无时间戳)、PersistBench(无时序)、TempTabQA/ChronoSense/ToT/TRAM(事件算术,非状态)、
ConflictBank/ClashEval/FaithEval/RAMDocs(静态冲突)、TAQA/ChroKnowBench/TemporalWiki-2022/DyKnow(闭卷参数化探针)、
WikiBigEdit/EvoWiki/evolveQA/BeliefShift(不开放或近重复)。

### 盘上已有、零接入成本、尚未跑的

- LongMemEval 其余 split:multi-session 133 / single-session-user 70 / -assistant 56 / -preference 30(只跑过 KU 78 + TR 133);
- MemoryAgentBench-FC 剩余 6 格(mh_6k/32k 约 $2–5;64k/262k 需重建卡 $20–45)——补完已有的负结果。

### 批评家的结构性判断(本人同意)

1. **最便宜、最决定性的考场不在候选表上:WikiState 自己的冻结保留集**(用从未碰过的 Wikidata 切片建 40 链/160 题,预注册臂位,一次跑完,不许回头改语料),≈$8–15 + 1 天。它一次关掉"无保留集 / datasheet 冻结 / v3 循环 / 人工覆盖 2.2%"四条 major。
2. 候选闸 fit≥2 = 按确认性筛选;现有两条负面证据(MemConflict conditional −32.5、gpt 读账目 −3.5)都是撞上的。应**刻意选一个预期会输的考场**(候选:AMemGym 的 off-policy 设定、GroupMemBench 多主体)。
3. 外场若只报准确率就是在最弱的轴上重复;每个新考场必须带 $/题、建店 $、延迟三列。
