# MAGMA 伴读材料(供 Jeremy 亲读)

> **文档性质:伴读材料,不是分析报告。** 左手放 PDF,右手放这份。第一、二节是读之前和读之中用的;第三节读完再看;**第四节是本文档最有行动价值的一节**。
> 生成日期:2026-08-17(整合 08-18 凌晨三条全文核实线后重写)。
> 目标论文:**MAGMA: A Multi-Graph based Agentic Memory Architecture for AI Agents**(Dongming Jiang, Yi Li〔UT Dallas〕, Guanpeng Li〔U. Florida〕, Bingzhe Li*〔UT Dallas〕),ACL Anthology **2026.acl-long.1709**,pp. **36848–36865**,**ACL 2026 主会长文**(San Diego);arXiv **2601.03236**(v1 2026-01-06 / v2 2026-04-16,comments 栏 "ACL 2026 Main")。开源:`github.com/FredJiang0324/MAGMA`(摘要末句 + 正文脚注 1)。
> 作者单位是 **UT Dallas + University of Florida**,**不是 Amazon**——勿与 APEX-MEM 混。

**本次重写相对 08-18 00:06 版的四处更正(先说,免得你按错的地图读)**:

1. 这篇有 **10 张表**,不是 7 张。旧版承重表清单漏了 **Table 8 / 9 / 10**。
2. F1/BLEU 备用指标表**不在附录 D**,在 **附录 F + Table 9 + Table 10**(附录 D 是 Baseline Configurations)。而 **Table 9 恰好是全篇最重要的一张反证表**——旧版把它当"除引用纪律外不必细看"处理,错了。
3. LongMemEval 上 MAGMA 输给 Full-context 的是 **三类**,不是两类。
4. 危险度改判从"**与 APEX-MEM 同级**"回撤到"**高于 A-TMA,但低于 APEX-MEM**"——理由见 4.2。旧版那句是过冲。

---

## 〇、开卷五分钟须知

这是 UT Dallas + U. Florida 四位作者的 **ACL 2026 主会长文**(Anthology `2026.acl-long.1709`,pp. 36848–36865,18 页含附录 A–F、Table 1–10、Algorithm 1–3),做法是把每条记忆同时投影到语义/时序/因果/实体四张关系图上,检索表述为按查询意图引导的有界图遍历,配一个非阻塞写入的双流机制,在 LoCoMo 与 LongMemEval 上报数并开源。**你现在要读它,不是因为它新,而是因为我们档案里对它的定级是"扫描级"(没开全文)做出的,而扫描级刚刚被证明会错**——同一份 `study_logs/QVF_related_work_verified_20260814.md` 五.3 对 APEX-MEM 的三条分界句,08-17 开全文后被判**三条里两条错、另一条方向相反**(那两条错是"循环步数无保证上限"和"论文未报告端到端 token 成本",而 APEX-MEM §6.2 明写 max limit of 40、附录 C Table 9/10 报得很细)。所以**读这篇的第一目标不是学它的方法,而是排掉"档案又错了"这个风险**:拿第四节那张六行表逐条回原文对,尤其盯第 5 条(我们已判"错")、第 6 条(我们已判"方向相反")和第 2 条(我们已判"六条中唯一完全站得住")。**本轮取到的层级如实说明**:三条独立线都以 **ACL Anthology camera-ready 全文**为依据(本地 `pdftotext -layout` / `-table` 双抽 + pypdf/pdfplumber 按词坐标逐格重建 Table 2 / 6 / 9,这三张在纯文本抽取里会串行错位);arXiv v2 已就 §3.2 时序图定义、节点元组、§3.3 意图集合、supersession 词汇四点逐句交叉校验,**与 camera-ready 无实质差异**(本篇没有重演 APEX-MEM 的 camera-ready 改写陷阱),唯一已知差异是 camera-ready 摘要末尾多了代码 URL 一句;**本轮未打开代码仓库**,凡涉及仓库的判断一律标"上一轮代码级观察,本轮未复核"。

---

## 一、阅读路线与时间预算

**总 90 分钟,按承重顺序,不按页码顺序。** 页码写法 `PDF p.N / 刊 p.368XX`(PDF 第 1 页 = 刊 p.36848,依次加一)。

| 程 | 分钟 | 打开哪几页,做什么 | 出程时要能说出的一句话 |
|---|---|---|---|
| **0 · 定位** | 6 | **PDF p.2 / 36849**:只读 "Our contributions" 四条编号段 + Figure 2 图注(**PDF p.3 / 36850**)。**跳过摘要、§1 前半、§2 Background** | 它自称的贡献 2 就是"按 query intent 路由检索",贡献 3 是双流写入。这两条是它的真机制 |
| **1 · 读取骨架** | 16 | **PDF p.4–5 / 36851–36852**:§3.2 的 Eq.(3) 节点定义 + 四张关系图各自的 bullet 定义;§3.3 Stage 1→4,Eq.(4) RRF、Eq.(5) 转移分数、Eq.(6) 意图权重;**Algorithm 1 逐行读**(横跨 p.4–5)。**PDF p.6 / 36853** 顶部:Eq.(7) provenance 序列化 + Salience-Based Token Budgeting 三行 | 确定性代码从哪开始、到哪结束(提示:结束点不是"答案") |
| **2 · 写入骨架** | 6 | **PDF p.6 / 36853**:§3.4 + **Algorithm 2**(Fast Path,9 行)+ **Algorithm 3**(Slow Path,12 行)。把两个算法里出现的**所有写操作动词**抄在纸上 | 写入侧一共有几种操作;其中有没有一种是"改" |
| **3 · 头条表 + 练习一二** | 22 | **PDF p.7 / 36854 → Table 1**;然后**直接跳到 PDF p.15 / 36862 → Table 7**(类目计数),两张并排。做**练习一**。回到 **PDF p.8 / 36855 → Table 4**,做**练习二**(顺带扫 **PDF p.9 / 36856 → Table 5**) | 0.700 是怎么算出来的,以及五行里有几行算不出来 |
| **4 · 备用指标表 + 练习三** | 12 | **PDF p.17 / 36864 → Table 9**(F1/BLEU 全表)。做**练习三**。然后读 **PDF p.16 / 36863 → 附录 F + F.1** 与 **PDF p.18 / 36865 → Table 10** | 换一个指标以后谁是第一;以及它用什么证据说服你别看那个指标 |
| **5 · 第二基准与成本** | 10 | **PDF p.8 / 36855**:Table 2(**原表列错位,用第二节给的重建版对照**)、Table 3;§4.3、§4.4 正文 | 它在第二基准上输给了谁、输在哪几类;Table 3 里**没有**哪一项成本 |
| **6 · 提示词与判官** | 10 | **PDF p.14 / 36861**:附录 **C.2 Adaptive QA Prompt** 全文(含指令 2、指令 4 及其脚注、四条 Dynamic Instruction)+ 附录 **C.3 Semantic Grader** 全文(尤其 Evaluation Constraints 第 3 条)+ 附录 **D** 四条 bullet。再翻 **PDF p.13 / 36860 → Table 6** 抄五个常数 | 哪些"能力"其实是提示词里的一行英文;基线拿到的是不是同一行英文 |
| **7 · 落笔** | 8 | 填第二节末尾两栏模板。**此刻仍不要读第三、四节** | 这篇该改 QVF 哪一句话 |

**明确的跳读许可**:§1 前半、§2 Background、§3.5 Implementation、§5 Conclusion、附录 A Related Work、附录 B、附录 C.1、附录 E.1 —— 全部只扫标题。**Figure 1 完全不用看**(见 2.3 装饰)。参考文献不看。

---

## 二、伴读手册

### 2.1 承重结构清单

先给按坐标重建的 **Table 2**(原 PDF 该表数据列整体错位,纯文本抽取会串行;已用 §4.3 正文 "Full-context baseline performs strongly on single-session-assistant tasks (89.3%)" 做归属互证):

| Question Type | Full-context (101K tok) | Nemori (3.7–4.8K) | MAGMA (0.7–4.2K) |
|---|---|---|---|
| single-session-preference | 6.7% | 62.7% | **73.3%** |
| single-session-assistant | **89.3%** | 73.2% | 83.9% |
| temporal-reasoning | 42.1% | 43.0% | **45.1%** |
| multi-session | 38.3% | **51.4%** | 50.4% |
| knowledge-update | **78.2%** | 52.6% | 66.7% |
| single-session-user | **78.6%** | 77.7% | 72.9% |
| Average | 55.0% | 56.2% | **61.2%** |

#### 承重(拿掉就塌)

| 编号 | 位置 | 它证明什么 | 分母 | 最可能被攻在哪 |
|---|---|---|---|---|
| **Table 1** | PDF p.7 / 36854 | 全篇头条:Overall 0.700,"relative margins of 18.6% to 45.5%" | **n=1,986**,但分母不在这张表上,在 **Table 7**(隔 8 页) | ① Overall 列五行有两行还原不出(练习一);② 对最强基线的 0.110 差距 85%+ 来自 Adversarial 单一类;③ 单 backbone gpt-4o-mini、单次运行——全文 `seed`/`runs`/`std`/`deviation` **零命中** |
| **Table 7** | PDF p.15 / 36862 | Table 1 / 4 / 5 / 9 的**唯一分母来源**:Single-Hop 841 / Adversarial 446 / Temporal 321 / Multi-Hop 282 / Open-Domain 96 / 合计 1,986(分项自洽) | 自己就是分母 | 它把 **Adversarial 446 题(22.5%)** 当一等类目计入 Overall——这个权重选择决定了头条,而正文从未讨论权重合理性 |
| **Table 4**(leave-one-out) | PDF p.8 / 36855 | "它有路由"的**唯一实验证据**:`w/o Adaptive Policy` 0.700→**0.637**,最大跌幅 | 同 n=1,986(未复述) | 四条边际贡献加总 **≫** 它对最强基线的总提升(练习二);且只给聚合分数、不给分类别拆解 |
| **Table 9**(F1/BLEU) | **PDF p.17 / 36864** | 它自己给出的**反证**:换成词级指标,排名翻转 | **只有四类,没有 Adversarial**,n=1,540 | 直接反驳摘要与 §5 的 "consistently outperforms" |
| **Algorithm 1 / 2 / 3** | PDF p.4–6 / 36851–36853 | 确定性边界的**唯一严格定义处**:Alg.1 的 `MaxDepth` 外循环 + `Candidates.TOPK(BeamWidth)` + 第 19 行 `if Visited.SIZE() ≥ Budget then break`;Alg.2 四种写操作;Alg.3 LLM 推边 | 无 | Alg.1 第 2 行只 RRF 了 `V.SEARCH(q)` + `K.SEARCH(q_key)` **两路**,而 Eq.(4) 写的是 `{vec, key, time}` **三路**——Stage 1 辛苦解析出的时间窗**在伪码里消失了** |
| **附录 C.2 + C.3** | PDF p.14 / 36861 | 能力实际写在哪:C.2 指令 2 = 弃答机制;C.2 指令 4 的四条 Dynamic Instruction = 生成侧路由;C.3 Evaluation Constraints 第 3 条 = 判官对抗题判分规则 | 无 | **C.2 指令 2 与 C.3 第 3 条是对偶的**;而 **附录 D 说基线用各自 official default 配置**,全文 `identical prompt`/`same prompt` **零命中** |
| **附录 D** | PDF p.14–15 / 36861–36862 | 基线口径:统一 backbone、统一判官(均 gpt-4o-mini)、Full Context 上限 128k、基线用官方默认 | 无 | 它统一了 **backbone** 和 **judge**,**没说统一 QA 提示词**。这就是 Adversarial 0.742 vs 0.205 最省事的替代解释 |
| **Table 6** | PDF p.13 / 36860 | "它有界"的硬证据(坐标已重建):**Max Depth 5 hops / Max Nodes 200 / Drop Threshold 0.15 / RRF k=60 / Vector Top-K 20 / λ₁=1.0 base / λ₂ 0.3–0.7 / w_entity 2.5–6.0 / w_temporal 0.5–4.0 / w_causal 3.0–5.0 / w_phrase 2.5–5.0** | 无 | 意图权重给的是**区间**不是定值;`BeamWidth` 与因果边阈值 τ 完全未报。但**"检索无界/无保证终止"这类话在这篇上会当场翻车** |

#### 半承重(有用,别当主证据)

| 编号 | 位置 | 用法 |
|---|---|---|
| **Table 2** | PDF p.8 / 36855 | 唯一的第二基准。承重方向是**反向的**:找它输给 Full-context 的三类。引用时必须注明"原表列错位,已按坐标重建" |
| **Table 3** | PDF p.8 / 36855 | 唯一成本口径:Build 0.39 h / Tokens-per-query 3.37 k / Latency **1.47 s(全表最低)**。**"近邻不报成本"这句话在这篇上不能用了。** 但它**只报查询侧 token**——Slow Path 每事件一次 LLM 推边的 token 全篇无数字 |
| **Table 5**(单图消融) | PDF p.9 / 36856 | Causal Only 0.590(单视图最高)/ Temporal Only 0.577、时序类 0.620 / Entity Only 0.531。练习二第 3 问要用 |
| **Table 8**(案例) | PDF p.16 / 36863 | 表本身是装饰,但含全篇对你最值钱的一句(警觉表第 13 条) |

#### 装饰(可以不看)

| 编号 | 位置 | 为什么 |
|---|---|---|
| **Figure 1** | PDF p.2 / 36849 | 画的是 MAG 范式的通用回路(Query→Agent→Memory→Output),**与 MAGMA 本身无关**,零信息 |
| **Figure 3** | PDF p.5 / 36852 | §3.3 文字的图形复述。**唯一例外**:图里画着 "Entity Relationship Check" 与 "Logic Check" 两个方框,而正文 §3.3 从未定义、Table 4 从未消融——这两个框是形式化空档的证据,不是机制 |
| **Figure 2** | PDF p.3 / 36850 | 图注值得读(点出三层),但图里 "Synaptic Ingestion" 框下画了 Semantic/Temporal/Entity **三种连边**,而 **Alg.2 的 Fast Path 只加了一条 `type=TEMP` 边**。图与算法冲突,以算法为准 |
| **Table 10** | PDF p.18 / 36865 | 七个**手工构造**的 Gold/Pred 玩具串(Gold "three items" / Pred "five items";Gold "compatible" / Pred "not compatible" 得 F1=0.857;"14:00" vs "2 PM" 得 0.000),**不是任何系统的真实输出**。但它是附录 F 的全部证据 |

### 2.2 三个五分钟练习(先自己算)

**练习一 · Overall 列还原(5 分钟)** 只用 Table 1(PDF p.7)+ Table 7(PDF p.15)。用 Table 7 五个类目计数,对 Table 1 每一行的五类分数做加权平均,看能不能还原它报的 Overall。**五行都算。**

**练习二 · 四个视图的贡献加起来等于总提升吗(5 分钟)** 只用 Table 4 + Table 5 + Table 1。① 算出 Table 4 里四条 `w/o` 各自的跌幅并**加总**;② 把加总和"MAGMA 对最强基线 Nemori 的 Overall 提升"比,差多少倍;③ 看 Table 5:**最好的那一张单图** Overall 是多少?这个数在 Table 1 里等于谁?

**练习三 · 换指标以后谁第一(5 分钟)** ① 在 Table 4 抄下 `MAGMA (Full)` 那行的 F1 与 BLEU-1;② 翻到 Table 9(PDF p.17),在 Overall 两列里**把这两个数找出来**,确认落在哪一行;③ 按 F1 Overall 第一名是谁?按 BLEU-1 Overall 第一名是谁?再逐类看 Multi-Hop / Temporal / Open-Domain;④ **Table 9 有几个类目列?** 和 Table 1 比少了哪一列?

---

**练习一答案 —— 三行对得上,两行对不上**

| 行 | 加权算出 | 论文报 | 差 |
|---|---|---|---|
| MAGMA | **0.7003** | 0.700 | ✓ |
| A-MEM | **0.5804** | 0.580 | ✓ |
| MemoryOS | **0.5525** | 0.553 | ✓ |
| **Full Context** | **0.4936** | 0.481 | **+0.013 ✗** |
| **Nemori** | **0.6057** | 0.590 | **+0.016 ✗** |

**该注意的不是"有两行错",是"错的是哪两行"**:算不出来的恰好是它整篇要打倒的长上下文对照,和它头条差距的对手,而且**两处偏差方向都让基线看起来更低**。交叉验证:同一套权重与分母去算 Table 5 的四行(Causal Only 0.5898/报 0.590、Temporal Only 0.5765/报 0.577、Entity Only 0.5311/报 0.531、Full 0.7003/报 0.700),**四行全部吻合到小数第三位**——所以不是权重算错,是那两行不自洽。
措辞纪律:偏差 0.013/0.016 **不足以推翻结论**,只能写"Overall 列计算口径不自洽",**不能写数据造假**。
若采用复算值,MAGMA 对 Nemori 的优势从 +0.110 收窄到 **+0.0946**,论文头条的 "18.6%–45.5% 相对提升" 应为 **15.5%–41.7%**。

**顺手一算(值钱)**:Adversarial 对头条差距的贡献 = (0.742 − 0.325) × 446/1986 = **+0.0937**,占 0.110 的 **85.1%**;若用复算后的 Nemori 0.6057(总差 0.0946),占比 **99.0%**。按类目全分解(对 Nemori):

| 类别 | 题量 | MAGMA − Nemori | 贡献 | 占比 |
|---|---|---|---|---|
| **Adversarial** | 446 | +0.417 | **+0.0937** | **99.0%** |
| Single-Hop | 841 | +0.012 | +0.0051 | 5.4% |
| Open-Domain | 96 | +0.032 | +0.0016 | 1.6% |
| Temporal | 321 | **+0.001** | +0.0002 | 0.2% |
| Multi-Hop | 282 | **−0.041** | **−0.0058** | −6.2% |

**剔除 Adversarial 后的 1,540 题上:MAGMA 0.6882 / Nemori 0.6869 / MemoryOS 0.5885 / Full Context 0.5772 / A-MEM 0.5701。** 即对 Nemori 打成 **+0.001** 的平手,但仍高出其余三者 0.10 以上。
**必须同时如实报的正面事实**:相对 **A-MEM** 的 +0.120,按题量分解是 Single-Hop +0.052 / Temporal +0.028 / Adversarial +0.028 / Open-Domain +0.006 / Multi-Hop +0.005 —— **五类全正、分布均匀**。相对 A-MEM / MemoryOS / Full-Context,MAGMA 的胜利是真实且宽基础的。

**练习二答案 —— 加起来是总提升的 1.87 倍,不可加**

| w/o | 分数 | 跌幅 |
|---|---|---|
| Adaptive Policy | 0.637 | 0.063 |
| Causal Links | 0.644 | 0.056 |
| Temporal Backbone | 0.647 | 0.053 |
| Entity Links | 0.666 | 0.034 |
| **加总** | | **0.206** |

- 它对 Nemori 的 Overall 提升只有 **0.110**。四条边际贡献加总 **0.206 = 1.87×**。
- 换基准也不成立:0.700 − 0.206 = **0.494**,而 Table 5 最弱单图变体是 0.531、最强是 0.590。"拿掉四样"的加总落点比"只留一张图"还低,说明四条 leave-one-out 跌幅高度重叠,**不能读成"各视图各自贡献了多少"**。
- **第 3 问,这条最狠**:Table 5 的 **Causal Only = 0.590**,而 Table 1 里 **Nemori 报的 Overall 恰好也是 0.590**。**只保留一张因果图的 MAGMA,和最强基线打平。** 正文只说"所有单图变体都低于 0.60",没把这个数和基线对上。

**练习三答案 —— 换成 F1 或 BLEU-1,第一名是 Nemori**

Table 4 的 `MAGMA (Full)` = Judge 0.700 / **F1 0.467** / **BLEU-1 0.378**。这两个数在 Table 9 里落在**最后一行**(`MAGMA (ours)`)——行归属由此**锁死**(纯文本抽取会把方法名与数据行错开,必须靠这个交叉验证或按坐标读)。

| Method | Multi-Hop | Temporal | Open-Domain | Single-Hop | **Overall F1** | **Overall BLEU-1** |
|---|---|---|---|---|---|---|
| Full Context | 0.182 | 0.079 | 0.042 | 0.229 | 0.140 | 0.096 |
| A-MEM | 0.128 | 0.128 | 0.076 | 0.174 | 0.116 | 0.074 |
| MemoryOS | 0.365 | 0.434 | 0.246 | 0.493 | 0.413 | 0.355 |
| **Nemori** | **0.363** | **0.569** | **0.247** | 0.548 | **0.502** | **0.403** |
| MAGMA (ours) | 0.264 | 0.509 | 0.180 | **0.551** | 0.467 | 0.378 |

- **F1 Overall 第一 = Nemori 0.502**(MAGMA 0.467);**BLEU-1 Overall 第一 = Nemori 0.403**(MAGMA 0.378)。
- 逐类:MAGMA 在 **Multi-Hop(0.264 vs 0.363)、Temporal(0.509 vs 0.569)、Open-Domain(0.180 vs 0.247)三类都输给 Nemori**,只在 Single-Hop 以 0.551 vs 0.548 微胜。
- 第 4 问:**Table 9 只有四类,没有 Adversarial 列。** 它唯一大胜的那一类,在备用指标表里**不出现**——而这一类正承担头条差距的 85%–99%。
- 口径自校验:按 Table 7 四类计数(n=1,540)加权,MAGMA F1 算得 **0.4666**(报 0.467 ✓)、Nemori **0.4997**(报 0.502 ≈✓);但 Full Context(+0.038)、A-MEM(+0.034)、MemoryOS(+0.029)三行**又对不上,且又都是报低**。**同一方向的口径漂移在 Table 1 与 Table 9 各出现一次。**
- **这就是摘要与 §5 那句 "consistently outperforms" 的直接反例,而反例由论文自己的附录提供。**

**延伸 60 秒(用 2.1 的 Table 2 重建版)**:MAGMA 有 **三类** 低于 Full-context——knowledge-update 66.7% vs 78.2%(**−11.5pp**)、single-session-user 72.9% vs 78.6%、single-session-assistant 83.9% vs 89.3%。**§4.3 只解释了第三类**(讲成 efficiency–granularity 取舍:89.3% 要 100k+ token,83.9% 只要 0.7–4.2k),对前两类**一字未提**。而 knowledge-update 正是"事实后来被改写"那一类。
另一处该算的:Table 2 的 61.2% 里唯一大幅领先的是 single-session-preference(73.3% vs Full-context 的 **6.7%**)。剔掉这一类,五类简单均值 **Full-context 65.3% > MAGMA 63.8% > Nemori 59.6%**。6.7% 是需要解释的异常值(Full-context 其余五类在 38.3%–89.3%),论文一字未提。

### 2.3 读到这几句要警觉

| # | 原文短语(位置) | 为什么是设置不是结论 | 去哪验证 |
|---|---|---|---|
| 1 | 摘要末句 & §5:**"consistently outperforms state-of-the-art memory systems"** | 只在一个指标(LLM-Judge)上成立的选择性陈述 | **Table 9**:F1 与 BLEU-1 上 Nemori 反超,三类里输 |
| 2 | §4.2:**"advantage is particularly pronounced in reasoning-intensive settings"** | 未受表格支持的定性升级 | 同一张 **Table 1**:Multi-Hop **0.528**,低于 Nemori 0.569 与 MemoryOS 0.552 |
| 3 | §4.2:**"slightly but consistently outperforms others (Judge: 0.650 vs 0.422–0.649)"**,并称此 **"validating"** 其 Temporal Inference Engine | 对 Nemori 的差是 **+0.001**;LongMemEval 时序类是 45.1% vs 42.1%(+2.1pp)。**+0.001 不能 validate 任何东西** | 全文搜 `seed`/`runs`/`variance`/`std` —— **零命中**。**你不可以写"显著优于"** |
| 4 | §3.2 Temporal Graph:**"This immutable chain provides the ground truth for chronological reasoning"** | "immutable" 只是"只追加不改",**不等于"值有版本"**;"ground truth" 是**声明**不是证明 | **Alg.2 第 2 行** `n_prev ← GETLASTNODE(G_t)` ——**按到达顺序**建边;而 §3.2 把 E_temp 形式化为 τ_i<τ_j 的**事件时间**序。**两个时钟从未对账** |
| 5 | §3.2 Causal Graph:**"e_ij ∈ E_causal exists if S(n_j\|n_i, q) > θ"** | **注意那个 q。** 存储层的因果边被定义成一个**查询条件化**的分数,与摘要主张的 orthogonal graphs / "decoupling memory representation from retrieval logic" **自相矛盾** | Eq.(5) 定义在 §3.3 Stage 3(检索侧)。存储层定义引用了检索侧函数 |
| 6 | §3.3 Stage 1:**"[τ_s, τ_e] … defining a hard time window for filtering"** | 看着像 bitemporal 有效期区间,**其实是查询侧过滤窗** | **Alg.1 第 2 行**只两路 RRF;而 **Eq.(4)** 写 `m ∈ {vec, key, time}` 三路。**时间窗在伪码里没有出现** |
| 7 | §3.4 **节标题写着 "Memory Evolution (Write and Update)"** | 标题许诺了 update,**正文一个 update 都没有** | 把 Alg.2 + Alg.3 的写操作动词抄全:只有 `ADDEDGE`/`ADDEDGES`/`VDB.ADD`/`ENQUEUE`。全文 `supersede`/`overwrite`/`version`/`delete`/`conflict`/`stale`/`invalidat`/`deprecat`/`obsolet`/`valid_from` **各零命中**。代价在 Table 2 的 knowledge-update 一行 |
| 8 | 附录 C.2 指令 2:**"If the answer is not present, respond exactly with 'Information not found'"**;附录 C.3 Evaluation Constraints 第 3 条 **Adversarial Handling**:Gold 为 "Unanswerable" 时 candidate 必须明确声明缺少信息,任何幻觉事实记 0.0 | 这两条**是对偶的**:提示词教模型说的那句话,正好是判官规则奖励的行为。而 **附录 D** 只统一了 backbone 与 judge,说基线用 "official default hyperparameters and storage settings",全文 `identical prompt`/`same prompt` **零命中** | 三处并读:**C.2 指令 2 + C.3 第 3 条 + 附录 D 四条 bullet**(都在 PDF p.14)。这既是 0.742 vs 0.205 最省事的替代解释,也是**它的弃答机制确实存在**的证据——**"它没有拒答能力"这句话不能说** |
| 9 | 附录 F:**"granular failure analysis on seven representative test cases"** | 它用这一节说服你**不要看 F1/BLEU**,而这一节的全部证据是 **Table 10 的七个手工构造串**,不是任何系统的真实输出,也无人工标注一致性 | Table 10(PDF p.18)逐格看 Case Detail。论证方向本身没错(词级指标确有 false reward/penalty),但它**没有量化 Table 9 的排名翻转有多少能被这个机制解释** |
| 10 | 附录 C.2 指令 4 脚注:**"Automatically generated by our engine's query classifier/router (no oracle labels)"** | **作者主动澄清"我没用 oracle 标签",说明知道审稿人会问。** 全篇最"怕被查"的一句;而分类器的模型/实现/提示词/精度**一个数字都没报**,免责声明不可核验 | 论文级只能读到声明。上一轮有一条仓库层观察与它冲突,**本轮未复核,一律标"未核"**(见第七节) |
| 11 | §3.3 Stage 4:**"forces the LLM to act as an interpreter of evidence rather than a creative writer, significantly reducing grounding errors"** | "significantly" 没有实验——Table 4/5 两套消融里**都没有 `w/o Provenance`** | 回 Table 4(四行)与 Table 5(三行)数一遍消融项。provenance 契约的效果**从未被单独测量**;RRF、salience budgeting 同样无消融 |
| 12 | Limitations(PDF p.9 / 36856):**"even under these constraints, … MAGMA substantially outperform traditional baselines, including full-context approaches"** | Limitations 段里塞了一句正面主张,而它被自己的 Table 2 反驳三次 | Table 2 重建版三类 |
| 13 | Table 8 案例 2 的 MAGMA 机制栏:**"Logic: 2 (Photo) + 1 (Son/Brother) = 3"**,答案 **"At least three."** | **全篇对你最值钱的一句**:它**自己逐字写出**聚合是模型在子图上做的一道算式,不是算子;答案还带 hedge | §3.3 Stage 4 三个 phase 里没有任何计算步骤;附录 C.2 `[Temporal]` 指令原文把算时长交给模型("Calculate durations if asked")。**QVF 的算子闭集论证要引这一句,标"附录 E.2 / Table 8, Case 2"** |

### 2.4 读完要能回答的七个问题(不给答案,给合格判据)

| 问 | 什么样的回答算合格 |
|---|---|
| **A · 它认为的问题是什么,它把问题收窄成了什么?** | 必须是**两句**:一句它明说的(扁平/纯语义记忆撑不住长时程推理;§2 末段的硬句是 "associative proximity" vs "mechanistic dependency"),一句它**实际**下注的位置——它把问题收窄成"**检索到的子图结构不对**",全部投入在关系建模与遍历。**必须点出它没把"记忆里的值会过期/被改写"当成一个问题**,并给出证据(§3.4 标题含 Update、正文无 update;十个替换类词零命中) |
| **B · 它有哪几条前提没有验证?** | 至少三条,每条落到具体位置:①"证据排好放进上下文,LLM 就能可靠完成剩下的推理与聚合"(Table 8 Case 2);②"四视图正交且互补"(§3.2 只有断言,无边集重叠率/互信息/条件可达性任何测量;Table 4 四条跌幅高度重叠、加总 1.87×);③"单一 backbone 上的相对排序可外推"(全文只跑 gpt-4o-mini);④"意图分类几乎不出错"(Eq.5 结构项 λ₁·w∈[0.5,6.0] 压过语义项 λ₂·sim≤0.7 约一个数量级,误分类代价不对称大,而路由器精度未报)。**只答"没做消融"不合格——它做了两套消融** |
| **C · 去掉包装,真机制有几样?** | 要**区分"真机制"与"已有件的组装",两边都点名**。真机制:意图条件化的边类型权重向量(Eq.5/6)+ 按题型的确定性上下文排序(Stage 4-1:WHEN 按 τ、WHY 在 E_causal 上拓扑排序)+ 双流非阻塞写入(Alg.2/3 换来 1.47 s)+ provenance 序列化与 salience 预算。组装:RRF、beam search、"多图记忆"本身、"associative vs mechanistic" 这个提法(引自 Kiciman et al. 2023)。**答案里出现"多图是它的创新",不合格** |
| **D · 它的确定性代码从哪开始、到哪结束?** | 必须给出**明确的终点,且终点不是"答案"**。四个确定性环节:RRF 锚点融合(Eq.4)、启发式束搜索(Alg.1)、按意图的拓扑/时间排序(Stage 4)、Eq.(7) 序列化;写入侧还有相对日期归一化。终点:**到"选中并排好子图"为止**。必须说出边界常数出处(Table 6:5 hops / 200 nodes / 0.15),因为**"检索无界"这句话你不能说** |
| **E · 它有没有路由?哪一级?** | 合格答案是"**有,两级**",且必须**同时给出限定**。两级:检索侧 `T_q ∈ {WHY, WHEN, ENTITY}` 改边权(Eq.6);生成侧按 Multi-hop/Temporal/Open-domain/Single-hop 注入不同提示词指令(附录 C.2)。限定精确到:**只改边权、剪枝偏好与上下文排序;不选择算子、不产生可校验计划、不切换执行器**;预算常数是全局的,不随 T_q 变。**答"它没有路由"直接不合格**——贡献 2 的标题就是路由,消融是最大增益项 |
| **F · 你若是审稿人,主质疑三条是什么?给什么分?** | 三条**必须都可核验、指得出表号**,不能是"新意不足"这类口水。至少一条来自 Table 9 或 Table 1 的口径,至少一条来自评测卫生(自评判官 + 单次运行 + 提示词非对称)。**必须给到"接/拒 + 理由"这一步**,并说出它凭什么达到主会水位(两基准、四基线、两套消融、三项成本、开源、附录 F 的评估口径讨论)。只列缺点不给判决 = 不合格 |
| **G · 它留给 QVF 的位置是什么?哪几条是硬差异?** | 要**分硬/软/不成立三档**,不许一律算硬。至少要判出:替换语义 = **硬**(十词零命中 + knowledge-update 66.7% < 78.2% 的未讨论负结果);答案级确定性聚合算子闭集 = **硬**(Table 8 Case 2 自认);计划表示与生成前校验 = **硬**;premise_check = **机制硬 / 收益软到负**(它 0.742 全表最高);"有路由" = **由硬降软**;"有确定性执行" = **不成立**;成本口径 = **不成立**(Table 3 三项);双时态 = **由硬降软**(它有 T_session→归一化事件日期两个时间点,QVF 硬差异只剩有效期区间 + 替换边)。**如果你的清单里没有任何一条被降级或判不成立,说明你没读附录** |

### 2.5 与 QVF 对照的两栏模板

读的时候每遇到一个机制就填一行。**左栏只写论文原文有的(带节号/表号);右栏只写 QVF 代码里真有的(带文件名/字段名)。** 想不起来出处的那一格留空——留空比写猜的有用。

```
机制轴                  | 它占走了我什么(节号/表号)   | 它留下什么空位(QVF 文件/字段) | 硬 / 软 / 不成立
------------------------|-----------------------------|------------------------------|------------------
确定性执行器            |                             |                              |
按意图路由              |                             |                              |
provenance / 证据渲染   |                             |                              |
有界检索与终止保证      |                             |                              |
弃答 / 不可答处理       |                             |                              |
成本与延迟口径          |                             |                              |
写入侧相对日期归一化    |                             |                              |
------------------------|-----------------------------|------------------------------|------------------
写入侧值替换 / 版本     |                             |                              |
事件时间 vs 到达时间    |                             |                              |
确定性聚合(计数/时长) |                             |                              |
计划表示与生成前校验    |                             |                              |
契约违约率的实测        |                             |                              |
组合题的分解诊断        |                             |                              |
评测卫生的显式声明      |                             |                              |
```

上半格是"它可能占走的",下半格是"它可能留下的"。**填完之前不要假定哪一格属于哪一半。** 填完后自问四句:

1. **右栏里,有几条是"QVF 有机制**且**有测量"?** 只有机制没有测量的不能当贡献写(c₁=99.6% 是测量,"11 算子闭集"是机制——证据强度不是一个量级)。
2. **我判"硬差异"的那几条,如果审稿人只读 MAGMA 的附录(C.2 / C.3 / D / E.2 / Table 6 / Table 9),他会不会当场反驳我?** 逐条演一遍。
3. **哪一条我原以为是硬差异,读完发现是"它的漏洞"而不是"我的机制"?**(提示:警觉表第 4 条那两个时钟。它没对账 ≠ 我有新意。)
4. **Table 3 只报了查询侧 3.37k token,没报 Slow Path 推边的 LLM token。** 如果我的成本表把写入侧 LLM 成本算进去了而它没算,该怎么写这一行,才既诚实又不被它比下去?

---

## 三、七镜精读全文(供读后对照,不要先读)

### 三条判决(先看这三行)

> **C 真实创新点:中(工程/技术层,概念层弱)** —— 四类边空间 + 意图条件化的边类型权重向量 + 双流写入,是一次干净的架构组合;但每个零件都有在先工作(Zep 时序知识图谱、GraphRAG 实体图、A-Mem 语义链接、adaptive RAG 的查询分类),论文没有改变问题定义。

> **D 实验支持度:支持不足** —— 相对最强 baseline(Nemori)的加权优势 +0.0946 中有 **+0.0937(99%)来自 Adversarial 单一类别**(自算,依据 Table 1 + Table 7);而该类别的胜负由"是否弃答"决定,MAGMA 独享一条提示词级弃答指令(附录 C.2 指令 2),baseline 按附录 D 用各自默认提示词。剔除 Adversarial 后 MAGMA 0.688 vs Nemori 0.687(+0.001);而唯一给出的替代指标表(Table 9,F1/BLEU-1)**恰好删掉了 Adversarial 这一列**,并且在该表上 Nemori 总分反超 MAGMA(0.502 vs 0.467)。

> **F 审稿倾向:弱拒** —— 三条主要质疑中两条作者无法在不补实验的情况下回应。可修复(补弃答对齐对照、补语义视图消融、补 Zep/Mem0),但当前证据不足以支撑"multi-graph 架构带来增益"这一因果归因。
> (需说明:本文已被 ACL 2026 主会接收,这是既成事实。弱拒是按本框架标准独立下的判决,不是对该结果的预测。)

### A · 这篇文章究竟要解决什么问题

**A1 作者声称要解决的问题。** 摘要:现有 MAG 方法 "largely rely on semantic similarity over monolithic memory stores, **entangling** temporal, causal, and entity information",这一设计 "limits interpretability and alignment between query intent and retrieved evidence, leading to suboptimal reasoning accuracy"。§2 末段给出更硬的一句(全文真正的问题陈述):

> "prior work typically organizes memory around **associative proximity** (e.g., semantic similarity) rather than **mechanistic dependency** (Kiciman et al., 2023). As a result, such methods can retrieve **what** occurred but struggle to reason about **why**."

§1 末贡献四条:① 多图代理记忆架构,显式建模 semantic/temporal/causal/entity 四类关系,"essential for long-horizon reasoning";② **Adaptive Traversal Policy**,按查询意图路由检索,"enabling efficient pruning of irrelevant graph regions and achieving lower latency and reduced token usage";③ **dual-stream memory evolution**,把延迟敏感的事件写入与异步结构固化解耦;④ 在 LoCoMo 与 LongMemEval 上 "consistently outperforms state-of-the-art agentic memory systems… while reducing retrieval latency and token consumption relative to prior systems"。摘要另许两愿:"provides **transparent reasoning paths** and fine-grained control over retrieval";§3.2 声明四类边空间 "preserving their **orthogonality**"。

**A2 贡献 ↔ 证据对照表**(只看 method + experiments。✅ 有受控消融/对照;⚠️ 只有间接指标或跨系统对照;❌ 未被测)

| # | 声称(位置) | 受控证据 | 定位 | 判 |
|---|---|---|---|---|
| C1-a | 时序视图有独立贡献 | leave-one-out + single-graph 双消融 | Table 4 `w/o Temporal Backbone` 0.647;Table 5 `Temporal Only` 0.577、时序类 0.620 | ✅ |
| C1-b | 因果视图有独立贡献 | 同上 | Table 4 `w/o Causal Links` 0.644;Table 5 `Causal Only` 0.590(单视图最高) | ✅ |
| C1-c | 实体视图有独立贡献 | 同上 | Table 4 `w/o Entity Links` 0.666;Table 5 `Entity Only` 0.531 | ✅ |
| **C1-d** | **语义视图 E_sem 是四正交视图之一** | **无任何消融** | Table 4 无 `w/o Semantic`;Table 5 无 `Semantic Only`;**Table 6 的意图权重四行是 w_entity / w_temporal / w_causal / w_phrase——没有 w_semantic,而 "phrase" 这一边类型全文未定义** | ❌ |
| C1-e | 四视图 "orthogonal" | 从未量化 | §3.2 只有断言;无边集重叠率/互信息/条件可达性任何测量 | ❌ |
| C1-f | 多关系结构 "essential for long-horizon reasoning" | 方向相反 | Table 1 Multi-Hop:MAGMA **0.528** < Nemori 0.569、MemoryOS 0.552(五法第三);Table 9 F1 Multi-Hop 0.264(第四)。正文一句未提 | ❌ |
| C2-a | Adaptive Policy 提升准确率 | 有消融,最大落差 | Table 4 `w/o Adaptive Policy` 0.637(−0.063) | ✅ |
| **C2-b** | **Adaptive Policy 带来 lower latency** | **无同架构对照** | Table 3 只有跨系统对比;Table 4 不报延迟 | ❌ |
| **C2-c** | **Adaptive Policy 带来 reduced token usage** | **无同架构对照** | Table 4 无 token 列 | ❌ |
| C2-d | "efficient pruning of irrelevant graph regions" | 无剪枝率测量 | 全文无访问节点数/剪枝比例/子图规模统计 | ❌ |
| C3 | dual-stream 保持 responsiveness | 只有跨系统建图时间 | Table 3 Build Time 0.39h vs A-MEM 1.01h、MemoryOS 0.91h,但 **Nemori 0.29h 更快**;无"单流同步版"对照;**慢路径每事件一次 LLM 调用的 token 完全未计入任何表** | ⚠️/❌ |
| C4-a | LoCoMo 上 consistently outperforms | 部分成立 | Overall 0.700 最高;但 Multi-Hop 第三,Temporal 仅 +0.001 | ⚠️ |
| C4-b | LongMemEval 上 consistently outperforms | 半数类别不成立 | Table 2:6 类中 **3 类低于 Full-context**,**2 类低于 Nemori** | ⚠️ |
| C4-c | "reducing token consumption relative to prior systems" | 对 A-MEM 不成立 | 3.37k/query 比 A-MEM 2.62k **高 28.6%**;比 Nemori 3.46k 仅低 2.6%;仅对 Full Context(8.53k)与 MemoryOS(4.76k)成立 | ⚠️ |
| Abs-1 | "transparent reasoning paths" | 完全未测 | 无可解释性评测、无人工评分、无路径忠实度指标;附录 E 三案例的 "Mechanism" 是作者事后解释 | ❌ |
| §3.3 | 出处脚手架 "significantly reducing grounding errors" | 无消融、无检验 | Table 4 无 `w/o Provenance`;"significantly" 后无统计量 | ❌ |
| §3.3 | Salience-Based Token Budgeting | 无消融 | Table 4 无该项 | ❌ |
| §3.3 | RRF 多信号锚点融合(Eq.4) | 无消融 | 且 **Eq.4 三路信号 {vec,key,time},Alg.1 第 2 行只两路,时间信号在伪码中消失** | ❌ |
| C.2 | 路由器 "no oracle labels" | 无精度数字 | 只被描述为 "a lightweight classifier";模型/实现/提示词/精度全未报。既然它是最高价值组件(−0.063),这是最要紧的空白 | ❌ |

**A1–A2 落差,集中三处**:① **标题级主张的四分之一无证据**——"四正交视图"里的语义视图既无 leave-one-out、也无 single-graph 变体、还在 Table 6 的权重向量里被一个未定义的 `w_phrase` 取代,三条独立线索指向同一件事。② **贡献 2 是"准确率贡献"被当成"效率贡献"报的**——准确率有受控消融(唯一最硬的证据),两项效率收益只有跨系统数字,没有一次 MAGMA-vs-MAGMA 对照。③ **贡献 1 的机制主张在最能检验它的类别上被自己的表格否掉**——Multi-Hop 判分第三、F1 第四,正文零字讨论,反而写 "advantage is particularly pronounced in reasoning-intensive settings"。

**A3 领域位置。** 上游:LoCoMo(Maharana 2024)/LongMemEval(Wu 2024);RRF(Cormack 2009);beam search;GraphRAG(Edge 2024)、Zep/Graphiti(Rasmussen 2025)的图化记忆;A-Mem(Xu 2025)、Nemori(Nan 2025)、MemoryOS(Kang 2025);Kiciman 2023 提供 "associative vs mechanistic" 修辞轴。下游:agent 记忆中间件;同组 Hippocampus(Li 2026)与 taxonomy 综述(Jiang 2026, arXiv 2602.19320)构成其生态位。定位:**在老问题上换方法**,不开新问题也不换场景。附带做了一件评估口径的活——附录 F 用 7 个手挑案例论证"为什么该用 LLM-judge 而非 F1/BLEU-1",而它恰好落在 MAGMA 在 F1/BLEU-1 上被 Nemori 反超的位置上。

**A4 已有方法卡在哪里(论文自给四点,全部可定位)**:① 纯语义链接把细节摘要掉——A-MEM 在 Open-Domain 退到 **0.385**(其 Single-Hop 尚有 0.653),附录 E Case 1 给了原始失败输出("violin" 在早期 session 摘要里被抽掉);Table 3 同时显示 A-MEM token 最低(2.62k),即低 token 是靠激进摘要买的。② 叙事式记忆在不可答问题上崩——Nemori Adversarial **0.325**(其 Single-Hop 0.764),Full Context 更低 **0.205**。③ 相对时间表达无法落地——附录 E Case 3,A-MEM 直接抄会话时间戳答 "20 October 2023",MemoryOS 幻觉出 "29 December 2025"。④ OS 式分层存储延迟不可接受——MemoryOS **32.68s**,是 MAGMA 的 22 倍。
**由 baseline 表推得的第五个卡点(论文未点出,对 QVF 最重要)**:LongMemEval knowledge-update 类,Full-context **78.2%**、Nemori **52.6%**、MAGMA **66.7%** —— **三个系统里两个记忆系统都被"直接塞全文"打败**。根因:两者都没有"旧值已作废"的表示。

**A5 一句话真实问题意识。** 作者真正害怕的失败模式是"**向量最近邻会把话题相近、结构无关的干扰项塞进上下文,让模型答出一个语法通顺、事实错误、且无从追责的答案**"——所以他们把 λ₂(0.3–0.7)压到比结构权重(2.5–6.0)低一个数量级,让遍历实际上由边类型而非相似度主导。而他们真正想占住的是 **"multi-graph + intent-aware routing" 这个架构名分**:被反复重复的都是架构词,不是任何一个可独立检验的机制指标。

### B · 他默认了哪些前提

**B1 数据假设。** 明说的:§6 第三条,LoCoMo/LongMemEval "do not cover the full range of settings…"。没明说但实际依赖:(a) **依赖 Adversarial 占 446/1986 = 22.5%**,而该类金标是 "Unanswerable"(附录 C.3 第 3 条),胜负由"会不会弃答"而非"检索得多准"决定,类别配比直接决定头条;(b) 依赖会话级时间戳可得且可信(Case 3 全靠 `T_session(Oct20) − 1 day`);(c) **依赖写入顺序到达**(§3.2 "strictly ordered pairs… This **immutable** chain",Alg.2 第 4 行只连 `(n_prev, n_t)`,迟到写入无插入路径);(d) 依赖事件分段器 `SEGMENTEVENT(I)`——全文没描述实现,也没消融。**高风险**:若评测语料没有"不可答"题型,MAGMA 相对最强 baseline 的优势按其自身表格复算只剩 **+0.001**。

**B2 方法假设。** 明说的:§6 第一条图质量取决于慢路径 LLM 抽取保真度,"susceptible to extraction errors and hallucinations";第二条多图基质带来 "a little higher implementation and memory overhead"。没明说但实际依赖:(a) **依赖意图分类几乎不出错**(结构项 0.5–6.0 vs 语义项 ≤0.7,一旦判错遍历被高权重错误边类型牵走且语义项无力纠偏;路由器精度从未报告);(b) **依赖三套互不一致的意图分类法能对齐**——§3.3 Stage 1 是 `{WHY, WHEN, ENTITY}`(3 类),附录 C.2 是 4 支(Multi-hop/Temporal/Open-Domain/Single-hop),Table 6 是 4 项(entity/temporal/causal/**phrase**),三者维度都不同,论文未解释映射;(c) **"policy-guided" 里没有任何学习成分**——w_{T_q} 是手工给定区间,无训练无 RL,是术语通胀;(d) **依赖 LLM 在线性化文本里心算聚合**(Case 2 "At least three" + "Logic: 2+1=3";C.2 `[Temporal]` 写 "Calculate durations if asked");(e) 依赖 200 节点 / 5 跳预算够用。**高风险**:**依赖"事实不会失效"**——节点只有单时间戳,边集无 supersession;这条假设已在它自己的 Table 2 里翻了。

**B3 任务假设。** 明说的:把长期会话记忆定义为"检索出对齐意图的证据子图 → 线性化 → 交 LLM 作答"。没明说但实际依赖:(a) **假定"结构化上下文 + 强约束提示词"足以逼出正确答案**(§3.3 原句用了 **forces**),而没有 grounding-error 率、没有出处引用正确率;(b) 假定答案层不需要确定性执行;(c) 假定 "transparent reasoning path" = 上下文里带 `<ref:id>`,即把"可追溯"等同于"可解释"。**高风险**:若任务里存在必须精确的量,把该步交给 LLM 心算就是把确定性上限交出去;Case 2 答案带 hedge 本身就是该假设失效的样本。

**B4 实验假设。** 明说的:附录 D 四条——Full Context 上限 128k;基线 "we applied **their official default hyperparameters and storage settings**";所有系统统一 gpt-4o-mini;统一同一 LLM-judge(也是 gpt-4o-mini,temperature=0.0)。没明说但实际依赖:(a) **假定"用各自默认提示词"就是公平**——但 MAGMA 的 QA 提示词含两条基线没有的东西(指令 2 的弃答规则,与判分规则第 3 条一一对应;按评测类别注入的四支动态指令,与 LoCoMo 类别标签同名),这把提示词工程增益与架构增益焊死;(b) 假定同一模型作答与判分不产生自偏好;(c) **假定超参可以在评测集上调**——§B.1 明写 "empirically optimized on the LoCoMo benchmark",而 LoCoMo 就是 Table 1/3/4/5 的评测集,全文无 dev/test 划分;(d) 假定单次运行的点估计可信(全文无 seed、无 std、无置信区间、无显著性检验,已 grep 确认)。**高风险**:弃答指令的不对称是**足以翻掉头条的**单点假设。

**B5 应用假设。** 明说的:§6 第二条承认资源受限环境可能不适用;§3.5 声称存储层可换后端。没明说但实际依赖:(a) **假定异步固化的延迟不影响正确性**——Alg.3 是后台 worker 逐个出队做 2-hop 邻域推理,因此"刚写入的事件"在被固化前其因果边与实体边尚不存在,**一个紧跟写入的查询会读到结构不完整的图**;论文既未给固化滞后时间,也未测"写后即读";(b) 假定写侧 LLM 调用可以不计成本(每事件一次,不在 Table 3 任何列里);(c) 假定 3 类意图 / 4 支指令能覆盖真实查询分布。**高风险**:生产环境的"写后即读"与"迟到/追溯写入"两类流,都直接踩在 §3.2 的不可变线性链假设上,两者都未测。

### C · 相比已有方法的真实创新点

**C1 改变了哪个环节(权重递减)**:**检索(主要)**——把"向量 top-k 一次取回"换成"多信号 RRF 定锚(Eq.4)→ 边类型加权的启发式 beam search(Eq.5/6,Alg.1)→ 按意图做拓扑排序的线性化(Stage 4)";**表示(次要)**——同一节点集上切出四个**互斥的边子空间**;**写入(次要)**——同步快路径与异步慢路径拆开。

**C2 引入的可实现新方式**:① **意图条件化的边类型权重向量** `Φ(r,T_q) = w_{T_q}·1_r`,`S(n_j|n_i,q) = exp(λ₁·Φ + λ₂·sim)`,取值见 Table 6;② **意图条件化的上下文排序**——`WHEN` 按 τ_i 排,`WHY` 在 E_causal 上拓扑排序保证因先于果进入提示词(**这是我在同类工作里第一次看到把"因果拓扑序"当作提示词构造规则写清的**);③ **出处脚手架 + 显著性预算**——Eq.(7),低分节点压成 brevity code("…3 intermediate events…");④ **评估口径的辩护材料**——附录 F + Table 10,7 个受控案例展示 F1/BLEU-1 的两类系统性错误。

**C3 为什么可能有效(机制解释)**:结构项 λ₁·w ∈ [0.5, 6.0],语义项 λ₂·sim ≤ 0.7,**结构项主导语义项约一个数量级**,所以遍历实际是"带类型优先级的图搜索",相似度只做同类型内细排。这解释了它在 Adversarial 上的 0.742(对抗题的干扰项恰好"语义近、结构远",打分函数天然给低分)。**同样的机制也解释它在 Multi-Hop 上失手**:多跳题需要跨越多种边类型的组合路径,而按意图把某一类边权重抬到 6.0 会让 beam 在单一类型上过早收敛。论文没做这个解释——但这是它自己的公式和自己的表格连起来的必然读法。

**C4 概念/技术/工程**:概念**弱**(问题定义没变,提法引自 Kiciman 2023);技术**中偏弱**(Eq.5/6 可实现可复现有消融,但是一个手工权重查找表,称 "policy" 名不副实);工程**中**(双流写入 + 三层抽象 + 完整提示词库 + 开源;Table 3 的 0.39h / 1.47s 是真实系统数字)。

**C5 与最相关 2–3 篇的可判定分界句**

- **vs Zep(Rasmussen 2025;§2 与附录 A 都点名讨论,但从未纳入任何实验表)**:Zep/Graphiti 是**双时态**知识图谱,边带 valid-from/valid-to 区间,事实失效由区间关闭表示。MAGMA 的节点是单时间点,边集恰好四类,**其中没有任何一类表示"作废/被替换"**。分界点在此:MAGMA 用类型化边空间买到了意图条件化的检索控制,代价是放弃有效期语义;Zep 相反。**这也是本文最该比而没比的一篇。**
- **vs GraphRAG(Edge 2024)**:GraphRAG 在静态语料上建实体图 + 社区摘要,服务"全局性问题"的摘要式回答;MAGMA 在持续写入的交互流上建四类边,服务定位式回答。分界句:GraphRAG 的图是为"概览"建的,MAGMA 的图是为"定位"建的。
- **vs A-Mem / Nemori**:两者检索都是"一种边"上的近邻扩展;MAGMA 的可判定差异是**边被打上类型标签,且类型权重随查询意图切换**。反过来,MAGMA 相对 Nemori 的实证差异并不落在这个机制上——剔除 Adversarial 的 1540 题上二者 0.688 vs 0.687,F1/BLEU-1 上 Nemori 反超。**必须如实报这一点。**

> **判决:新意 中(工程/技术层为主,概念层弱)。** 理由:意图条件化的类型化边遍历 + 因果拓扑序线性化 + 双流写入是一次组合清晰、可实现、可复现的架构工程,且对其中三个视图做了双消融——这部分是扎实的。判不到"强",因为 (i) 四个组成部分逐个都有在先工作;(ii) "policy" 无学习成分;(iii) 标题级主张里的第四个视图没有任何证据;(iv) 最能体现"机制依赖优于关联邻近"的多跳类别上它排第三。

### D · 实验是否足够支持核心结论

**D1 核心结论**:① 显式建模多关系结构 → 长时程推理更准;② 优势在推理密集与对抗设定下尤为明显;③ 泛化到超长上下文(61.2% vs 55.0%/56.2%),以 0.7–4.2k 换 100k+ 的 95% 削减;④ 系统效率更优;⑤ 四组件均有非替代性贡献,且无单一视图可恢复全系统能力。

**D2 直接支持的**:结论 5 的三分之三(因果/时序/实体)——两套独立消融方向一致,全文最硬的一块;Table 5 三行总分可用 Table 7 题量精确复算(0.5898/0.5764/0.5311),内部自洽。结论 4 的延迟部分——1.47s 确为五法最低。结论 1 相对 **A-MEM** 是宽基础的——五类全正、分布均匀(见 2.2)。

**D3 只能间接支持的**:结论 3 的"泛化"——Table 2 只对比两条线,A-MEM 与 MemoryOS 在 LongMemEval 缺席;且 Average 无法审计(LongMemEval 各题型题量全文未给)。结论 3 的"95% 削减"——被拿来配对的准确率是 single-session-assistant 的 83.9% vs 89.3%,**即在这一类上 MAGMA 是输的**,论文措辞为 "competitive accuracy (83.9%)"。结论 4 的建图时间——**劣于 Nemori 0.29h(慢 34%)**,论文未提。结论 2——"reasoning-intensive" 无操作化定义;若指 Multi-Hop,证据反向。

**D4 缺关键 baseline**

| 缺的 | 为什么最该比 |
|---|---|
| **Zep** | 唯一与 MAGMA 直接竞争"时序 + 图 + agent 记忆"生态位的系统,§2 与附录 A 各讨论一次却不入任何表。Graphiti 开源,LoCoMo 分数公开可得 |
| **Mem0** | intro 第一批被点名的 MAG 系统之一,LoCoMo 是其主战场,不比 |
| **MemGPT / MemOS / Hippocampus** | 前二附录 A 详述;Hippocampus 是作者同组工作,附录 A 点名,不比 |
| **"MAGMA 的提示词 + 平坦向量记忆"这条消融式 baseline** | 全文最关键的缺失对照。没有它无法区分"架构增益"与"提示词增益" |
| **LoCoMo 官方/原论文的 RAG baseline** | Full Context 之外没有任何标准 RAG 对照,而"击败向量相似度"正是全文动机 |

**D5 缺消融(声称过但没被单独摘掉的组件,共 7 项)**:语义图 E_sem;RRF 三路锚点融合;出处脚手架;显著性 token 预算;双流写入(无单流同步对照);意图分类器(无精度、无 oracle 上界);附录 C.2 的动态指令注入(**含弃答规则**)。另外 Table 4/5 **只给聚合分数、不给分类别拆解**——在"99% 头条优势来自单一类别"的情况下,聚合级消融无法把组件价值归因到任何类别。而且 `w/o Adaptive Policy` 到底摘掉了什么并不清楚:§4.5 说"retrieval degenerates into a static graph walk",听起来只摘掉了边权重;若动态 QA 指令(含弃答规则)仍在,则这次消融根本没碰到提示词那一半。

**D6 数据集/指标/设置偏向(五条,均可定位)**:① 超参在评测集上调,无 dev/test 分离;② 答题模型 = 裁判模型(gpt-4o-mini, T=0.0),自偏好未做任何控制,无人工一致性研究;③ 裁判规则与 MAGMA 的提示词咬合(C.3 第 3 条 ↔ C.2 指令 2),而基线用各自默认提示词;④ **替代指标表恰好删掉了决定胜负的那一列**(Table 9 无 Adversarial;已复算确认其 Overall 在 1540 题上算:MAGMA 0.4666 ≈ 报 0.467 ✔;而 Nemori F1 0.502 > MAGMA 0.467,BLEU-1 0.403 > 0.378);⑤ 动态指令的分支名与 LoCoMo 类别名同构,作者加了 "no oracle labels" 脚注,但分类器精度一个数字没报,该免责声明不可核验。

**D7 提升是否足够显著。** **统计层面:零。** 无 seed、无重复运行、无 std、无置信区间、无显著性检验。全部数字是单次运行点估计。**幅度层面:把 Table 1 按 Table 7 题量拆开,头条就散了**——五行里三行精确吻合、两行吻合不了,而吻合不了的恰好是两条最强对照,且两者被报得**比自身分类分蕴含的值更低**(详见 2.2 练习一与分解表)。这三段合起来是本轮最要紧的东西:MAGMA 相对 A-MEM/MemoryOS/Full-Context 的优势是真实且宽基础的;相对最强 baseline Nemori 的优势几乎全部来自一个由"是否弃答"决定胜负的类别;而唯一能交叉验证该类别的替代指标表,把该类别删掉了,并且在剩下的题上 Nemori 反超。
顺带两处措辞与数字不符:"about **40%** faster than the next best retrieval baseline (A-MEM)" —— (2.26−1.47)/2.26 = **35.0%**,且与无记忆的 Full Context(1.74s)只快 15.5%;"In the Temporal category… **validating** the effectiveness of our Temporal Inference Engine" —— 对 Nemori 的差是 **+0.001**。**+0.001 不能 validate 任何东西。**
Table 2 的头条同理:61.2% 里唯一大幅领先的是 single-session-preference(73.3% vs 6.7%),剔掉这一类五类简单均值 **Full-context 65.3% > MAGMA 63.8% > Nemori 59.6%**。

> **判决:核心结论 支持不足。** 结论 5(三个视图各有非替代贡献)与"相对 A-MEM/MemoryOS/Full-Context 更准"这两条被受控消融与可复算的分类别数据**充分支持**。但作为头条的结论 1/2/3 支持不足,四个独立理由:(i) 相对最强 baseline 的优势 99% 集中在一个由提示词级弃答规则支配的类别,而该规则只有 MAGMA 有;(ii) 唯一的替代指标表删掉了该类别,并在其余题上被 Nemori 反超;(iii) 最能检验其机制主张的 Multi-Hop 上判分第三、F1 第四,正文零字讨论;(iv) 零方差/零检验,超参在评测集上调优,两行 Overall 与自身分类分不自洽,LongMemEval 题量缺失导致 Average 不可审计。

### E · 可能的反例(8 条,每条指向具体依赖)

1. **依赖"金标含 Unanswerable + 系统侧有弃答指令"**。在没有对抗/不可答题型的语料上(TimelineQA、TempReason、纯抽取型 KGQA,或任何"答案保证存在"的基准),按其自己表格复算,相对 Nemori 只剩 +0.001。→ 直接挑战"multi-graph 带来增益"这一因果归因:被归给架构的东西,可能属于一条提示词。
2. **依赖会话级时间戳可得且可信**。在时间戳缺失、被合并、或来自异构来源(导入的历史记忆、日志流、跨设备同步)的场景中,Temporal Parser 失去锚点,而 w_temporal 高达 4.0 会把 beam 推向一条时间未归一化的链。未测任何时间戳缺失设定。
3. **依赖写入顺序到达**。迟到写入、追溯更正、多说话人并发会话都会让物理顺序与语义时间顺序脱钩,而"不可变"意味着无重排路径。→ 挑战 "provides the ground truth for chronological reasoning"。
4. **依赖 LLM 在线性化文本里心算聚合**。凡需要精确次数/时长/首末的问题,答案随子图召回抖动且带 hedge。无任何聚合算子,也没有计数/时长类子集评测。
5. **依赖"事实不会被覆盖"**。这条依赖在论文自己的 Table 2 上已经翻了:knowledge-update **66.7%** < Full-context **78.2%**,在最需要"旧值已作废"的题型上被无记忆基线反超 11.5pp。→ **这不是我构造的反例,是论文自带的反例。**
6. **依赖意图分类近乎无错**。误分类的代价不对称地大,而语义项没有纠偏能力;路由器精度未报、oracle-intent 上界未给。→ 挑战"最大消融落差 −0.063 归功于 Adaptive Policy"这一归因:落差也可能来自"随便给一个类型偏好都比不给好"。
7. **依赖 200 节点 / 5 跳预算够用**。证据分散在 200 节点以外或 5 跳以上的超长会话会被静默截断且无告警。Table 2 multi-session 类 50.4% < Nemori 51.4%,方向与该约束一致。
8. **依赖同一模型作答与判分**。换更强裁判、换人工、或换答题骨干,自偏好即消失。附录 F 只有 7 个手工构造案例,无抽样、无人工一致性系数;而 Table 9 表明换成非 LLM 指标结论就翻。

(第 5、8 是"论文自证的反例",第 1 是"按论文数字复算得到的反例"——这三条杀伤力高于纯设想类。)

### F · 以严格但公正的审稿人身份评价

| 项 | 评 |
|---|---|
| 问题重要性 | **高**。长期会话记忆的检索层确实是 agent 落地瓶颈 |
| 创新性 | **中偏弱**。组合是新的,零件都不是;"policy" 无学习成分 |
| 方法是否清楚 | **部分**。§3.2/3.3 形式化与三段伪码清楚可实现;但意图分类器、事件分段器、慢路径因果抽取提示词三个关键件全部未描述(附录 C 自称"three distinct types"的提示词库里,恰恰没有 Alg.3 用的那条) |
| 实验充分性 | **不足** |
| baseline 公平性 | **不公平**。"各用自己的默认配置"在存在弃答指令不对称时不构成公平;缺 Zep/Mem0 |
| 结论是否夸大 | **是**。"consistently outperforms"(LongMemEval 6 类中输 3 类给 Full-context);"reducing token consumption"(比 A-MEM 高 28.6%);"about 40% faster"(实为 35.0%);"validating"(+0.001);"significantly reducing grounding errors"(无任何测量) |
| 可复现性 | **中偏低**。开源是加分项;但 Table 6 的 λ₂、Sim. Threshold、四个意图权重全部只给**区间**,BeamWidth 与因果边阈值 τ 完全未报,且超参在评测集上调 |
| 逻辑跳跃 | **三处**。(a) 声称优势在 reasoning-intensive 显著而 Multi-Hop 第三;(b) 用 +0.001 "validating" 时序引擎;(c) 断言 orthogonality 并据以论证 "complementary, non-substitutable axes",而正交性从未测量 |

**三条主要质疑**

**M1｜头条优势 99% 来自单一类别,且该类别与 MAGMA 独享的弃答指令混淆;而唯一的替代指标表恰好删掉了该类别。** *作者可能回应*:Adversarial 是官方类别、占比由基准给定;弃答是系统设计的组成部分;A-MEM 用自己的默认提示词也拿到 0.616。*能否成立*:**不成立**。第三点确实削弱了"纯提示词假说",但正因为基线在该类上分布宽达 0.205–0.616,它更像在测"系统是否会说不知道"而不是"多图检索是否更准"。要剥出架构增益,唯一办法是补 **baseline + 同一条弃答指令** 与 **MAGMA − 弃答指令** 两组对照,现有数据无法替代。**Table 9 恰好缺 Adversarial 列**这一事实也让"选择性呈现"的辩解成本变高。

**M2｜"四正交视图"是标题级主张,而第四个视图(语义)既无消融也不在遍历权重表里;且 Table 6 出现一个全文未定义的 w_phrase。** *作者可能回应*:语义图就是向量检索通路,Full Context 与 A-MEM 已充当对照;"phrase" 是命名笔误。*能否成立*:**部分成立但远不足**。A-MEM 不是"MAGMA 去掉语义图"的同架构变体,不能替代消融;w_phrase 无论是笔误还是另有其物,都意味着 §3.2 的四类边空间与 Eq.6 实际作用的权重维度不一致——这是正文与表格的直接冲突,必须给出对应关系并补 `w/o Semantic Links` 与 `Semantic Only`。补这两个数字成本很低,拒不补会被读成"补了不好看"。

**M3｜主结果不可复算:超参在评测集上 "empirically optimized",多项关键超参只给区间,两个关键超参完全未报,建图因果边的提示词未公开。** *作者可能回应*:代码已开源,默认值在 repo 里;区间反映不同意图下的取值范围。*能否成立*:**不成立**。开源解决不了三件事:(a) 论文表格用的是区间里哪一组值,读者无法从代码反推;(b) "在 LoCoMo 上调、在 LoCoMo 上报"这一无 dev/test 分离的问题代码不解决;(c) 建图提示词不公开,则"因果图"这个最核心的差异化产物无法被独立复建,而 §6 已自认这一步的保真度是最大风险源。

**三条次要质疑**

**m1｜缺 Zep 与 Mem0。** Zep 在 §2 与附录 A 各被讨论一次(附录 A 明写它是 "temporally-aware knowledge-graph engine (Graphiti)"),却不入任何表。*能否成立*:**部分成立**——范式覆盖论在同期投稿中常被接受;但 Zep 是本文分界叙事的正面靶心,Graphiti 开源,回避成本低于被质疑成本。建议至少引用其公开数字。

**m2｜Table 1 中两行 Overall 无法用 Table 7 题量复算;Table 2 的 Average 完全无法审计。** *作者可能回应*:不同系统在部分样本上失败/超时被排除。*能否成立*:**若不给出排除规则与各方法有效样本数,不成立**——恰好是两条最强对照被报低,方向不利于中立解读。(按 LongMemEval-S 公开分布试算,Full-context 55.0% 与 Nemori 56.2% 可精确复现,MAGMA 复算 59.8% 而论文报 61.2% —— **此项因题量来自本文之外,仅作为需向作者提问的疑点,不作结论**。)

**m3｜三套互不一致的意图分类法 + 术语通胀 + 伪码与公式不符。** *能否成立*:**作为次要项可以接受,但必须在正文补一张映射表**;"policy" 一词建议改为 "typed-edge preference schedule" 之类不暗示学习的说法。

> **判决:审稿倾向 弱拒。** 问题重要、工程扎实、消融有三分之三做对、开源、附录 F 的评估口径讨论有独立价值——这些都是真的。但作为一篇声称"multi-graph 架构带来长时程推理增益"的主会长文,它相对最强 baseline 的优势 99% 落在一个由弃答行为支配的类别里,而剥离该混淆所需的两组对照一组都没有;标题级主张的四分之一零证据;主结果的超参在评测集上调且只给区间。M1 与 M3 无法在不补实验的前提下回应。三条都可修复,故为弱拒而非拒绝。

### G · 如果我要扩展这篇论文(5 个具体研究想法)

**G1 弃答对齐重跑:剥离提示词增益后,多图检索还剩多少?** 研究问题:当所有系统都被给予同一条"证据不足则输出固定弃答串"的指令后,多视图图检索相对平坦/叙事式记忆的增益还剩多少?值得做的理由:MAGMA 的头条 99% 压在这条指令覆盖的类别上,而整条 agentic memory 线的 LoCoMo 数字都可能带这个混淆——这不是针对一篇论文,是给一个基准的评测协议打补丁。怎么做:2×4 设计,四个基线 × {各自默认提示词, +统一弃答指令},MAGMA 加做 {完整, −弃答指令};判分固定用强于答题骨干的裁判,并对 Adversarial 全 446 题 + 其余类抽 200 题做人工复核,报 Cohen's κ;必报"含/剔除 Adversarial"两组数字。难点:各基线提示词结构不同,注入位置本身引入自由度,**必须预注册注入规则**,否则这项研究会重犯它想纠正的错误。

**G2 给四视图加装第五类"作废边" + 确定性 ASOF:补上 knowledge-update 这个空位。** 研究问题:增加一类 supersession 边与节点级有效期区间,并把"某时点该属性是什么"编译成确定性 ASOF 取值,能否把 knowledge-update 从 66.7% 推过 Full-context 的 78.2%?值得做:这是论文自己数据里最刺眼的空位,根因在表示层缺失而非检索强度,补它是加法而非否定。怎么做:写入侧在事件抽取 JSON schema 上增加 `(entity, attribute, value)` 三元组识别 + 同槽位冲突检测,冲突时加 supersession 边并关闭旧节点有效期;读取侧在意图集里加 `ASOF`,该意图下遍历只走 supersession 链并由代码取区间覆盖 τ_query 的唯一值,跳过 LLM。指标:knowledge-update 准确率 + "新旧两版都被召回时选对新版的比例";消融 {仅加边不加算子, 边+算子}。难点:同槽位判定本身靠 LLM;冲突检测的假阳性会把无关事实误标为作废,**必须报这个副作用**。

**G3 把 LLM 心算换成确定性聚合算子,专攻 MAGMA 最弱的 Multi-Hop。** 研究问题:把"数一数/算多久"从"读线性化上下文心算"改为编译到 COUNT / DURATION / FIRST-LAST 算子后由代码执行,在 Multi-Hop(现为五法第三,0.528)上能拿回多少?怎么做:保留检索层不动作为共同前端,只替换 Stage 4——意图落入聚合类时把子图投影成 (entity, attribute, value, τ) 表,由代码执行算子。指标:报"链全对时算子判对率"与"编译正确率"两个分解指标,以便区分"执行错"和"编译错"。难点:编译错误会替换掉心算错误,净收益可能为负——**这正是我方 QVF 自审里 c₂ = 46.2% 那面墙。必须把 c₁/c₂ 式分解作为主报告指标,而不是只报端到端准确率。**

**G4 路由器精度—收益曲线:意图路由从多少精度开始盈利?** 研究问题:意图分类精度 a 与"意图条件化边权重"的收益之间是什么函数关系?在什么 a 以下,类型化路由不如统一权重?值得做:Table 4 显示 `w/o Adaptive Policy` 是最大落差,但既不报路由器精度也不给 oracle 上界——社区无法判断该落差里有多少是"路由对了"、多少是"随便给个类型偏好都比不给好"。同样的空白存在于所有带路由的记忆系统上。怎么做:在开源 MAGMA 上注入受控路由噪声(0/5/10/20/30/40% 概率随机替换 T_q),画 Judge–精度曲线;两端各加一条水平线:oracle intent 与 uniform weight;全量 × 8 噪声水平 × 3 seed(顺手补上论文缺的方差),并在剔除 Adversarial 的 1540 题上重跑一遍。难点:均匀噪声偏乐观,需拿真实分类器的混淆矩阵做加权版噪声。

**G5 "正交性"的可测定义:四个视图到底重叠多少?** 研究问题:四个边集两两重叠率是多少?"orthogonal" 成立到什么程度?视图重叠率能否预测 leave-one-out 落差?值得做:§3.2 的断言是整条论证链的地基,而这个性质从未测量;测量便宜、可复现、结论无论正负都有价值——若重叠很高,则"多视图"其实是"一张图上的多套权重",这会改写整条 multi-view memory 线的自我叙述。怎么做:导出四个边集,算(a)两两 Jaccard;(b)去掉某类边后节点对仍可达的比例(替代性的直接度量);(c)每类边的条件熵;再把这些量对四个 leave-one-out 落差做回归;同时扫 Sim. Threshold 看敏感度。顺带补上论文完全缺失的图统计量。难点:E_sem 边数由阈值决定,结论必须以阈值扫描曲线呈现;因果边由 LLM 生成,需报图层面的方差。

> **说明**:七镜 H 节(档案定级复核)的内容已并入第四节,不在此重复。

---

## 四、⚠️ 档案六条断言的逐条复核结果

> 复核对象:`study_logs/QVF_related_work_verified_20260814.md` **五.3** 对 MAGMA 的判定,**全部为扫描级(未开全文)**。
> **结论先行:六条中 3 条成立(其中 1 条可加强)、2 条不精确须软化、1 条错;总定级须上调,但上调幅度小于 08-18 00:06 版所写。**

### 4.1 六条逐条判定表

| # | 档案原断言(扫描级) | 判定 | 关键原文位置 | 必须改成什么 |
|---|---|---|---|---|
| **1** | 时序图 §3.2 定义为按时间戳严格排序的线性链(τ_i<τ_j 有序对),**无 bitemporal 有效期区间** | **成立,但须加两条限定** | §3.2 逐字:"Temporal Graph (E_temp): Defined as strictly ordered pairs (n_i, n_j) where τ_i < τ_j. This immutable chain provides the ground truth for chronological reasoning";Eq.(3) 节点 `n_i = ⟨c_i, τ_i, v_i, A_i⟩`;`supersed*/invalidat*/overwrit*/deprecat*/valid_from/obsolet*` 全文命中 **0**;唯一区间 `[τ_s, τ_e]` 是 §3.3 Stage 1 的**查询过滤窗** | "无有效期区间"成立且证据很硬,**可升级为逐字引用 + 伪码行号**。**限定 A**:附录 E.2 Case 3 与 Table 8 显示它把 `T_session(Oct20) − 1 day = Oct19` 归一化后存为节点属性 `date="2023-10-19"`,即**会话时间戳与归一化事件日期并存**,所以**不可**说它"只有单时态戳/无 ingestion-event 分离"——那正是 APEX-MEM 那条翻车的句式。**限定 B**(反过来是它的漏洞):Alg.2 只做尾部追加(`n_prev ← GETLASTNODE(G_t)`),链按**到达顺序**接,`τ_i < τ_j` 不是写入路径的不变量,而链被声明 immutable,无重排路径 |
| **2** | **无 supersession / superseded-by 链** | **成立,六条中证据强度最高,且档案漏了它的硬代价** | 词汇零命中;两条写路径**纯增边**(Alg.3 末 `G.ADDEDGES(E_new)`;§3.4 "densifies the graph structure";主干 "immutable");**全文没有任何冲突检测或版本择取**——这一点上它**弱于 APEX-MEM**(后者至少检索双版本交 LLM 按时间戳择取),MAGMA 连"发现同一属性有两个值"这一步都没有 | 措辞可**加强**,并配 LongMemEval **knowledge-update 66.7% < Full-context 78.2%** 这一论文未讨论的负结果。**这是由竞争对手论文提供的、可直接引用的空位证据** |
| **3** | 聚合(如"几个孩子")由 LLM 读子图**心算**得出,**无确定性计数/时长算子** | **成立,且证据比档案预期更硬;但"无确定性执行环节"若这么概括则错** | 附录 E.2 Case 2 / Table 8:答 "**At least three.**",Mechanism 栏逐字写 "Logic: 2 (Photo) + 1 (Son/Brother) = 3";附录 C.2 `[Temporal]` 指令逐字 "**Calculate durations if asked**";§3.3 全无聚合算子,全文无查询语言(无 SQL/XPath/JSON 计划) | 限定为"**无面向证据集的、答案级的确定性聚合算子**"。管线里有四处确定性代码:RRF(Eq.4)、beam search 转移打分(Eq.5 + Alg.1)、`TOPOLOGICALSORT(Visited, T_q)`、写入期相对日期归一化。**不可说"MAGMA 无确定性环节"** |
| **4** | **无 premise_check** | **不精确,须软化;且这是对 QVF 的实质威胁** | 机制层"无形式化的答前前提校验算子"成立;但有两件档案没看到的东西:(a) 附录 C.2 指令 2 "If the answer is not present, respond **exactly** with 'Information not found'",与附录 C.3 Evaluation Constraints 第 3 条 Adversarial Handling 咬合;(b) Figure 3 画着 "Entity Relationship Check" 与 "Logic Check" 两个方框,**正文 §3.3 从未定义、Table 4 从未消融**。**效果:LoCoMo Adversarial = 0.742,五法最高**(Nemori 0.325 / Full-context 0.205) | 改为"无**答前**确定性前提校验,弃答靠提示词层指令 + 结构化上下文 + 判分器口径"。**QVF 不得再由"缺 premise_check"推出"不可答会崩";premise_check 的真实对手是一条提示词,必须跟它比增量,而不是跟"不做检查"比** |
| **5** | **无管线级路由**(所有查询走同一多图遍历流程) | **❌ 错。本轮最重要的一条更正** | **贡献第 2 条标题即"按 query intent 路由检索"**;§3.1 "the **Intent-Aware Router for dispatching tasks**";§3.3 Stage 1 "A lightweight classifier maps q to a specific intent type T_q ∈ {WHY, WHEN, ENTITY}. This acts as the **'steering wheel'**";Eq.(6) 意图专属权重向量;Stage 4 按意图分支排序;附录 C.2 四支动态指令 + "no oracle labels" 脚注;**Table 4 `w/o Adaptive Policy` 0.700→0.637 是四项消融中最大落差**——路由是它按自己数据算出的最高价值组件 | 改为"**有**按意图的两级分派"。保住的部分必须精确到:意图只改**边类型权重、剪枝偏好、上下文排序、生成侧提示词分支**,所有查询仍走同一条 `anchor → 束搜索 → 线性化 → LLM 生成` 通路,同一执行器;**预算常数(5 hops / 200 nodes / 0.15)是全局的,不随 T_q 变**。且**不能用"数据集级配置切换"话术脱身**——分类器在线判 T_q,论文特意标注 no oracle labels |
| **6** | 总定级"**危险度不高于 A-TMA**" | **❌ 错,须上调(但幅度小于 00:06 版所写)** | 见 4.2 | 改判为 **A-TMA < MAGMA < APEX-MEM**;并需一条独立分界句,不能沿用既有框架也不能并入反面证据簇 |

**同一分界句里另外三处措辞的核实(档案原句包含,但不在"六条"编号内)**

| 措辞 | 核实 | 判 |
|---|---|---|
| "四正交视图图(语义/时序/因果/实体)" | §3.2 边集划分为 E_temp / E_causal / E_sem / E_ent,四类确认 | ✅ 正确 |
| "检索 = **LLM 驱动的**自适应遍历(§3.3 动态转移分数)" | **❌ 错。** 转移分数是闭式算术(Eq.5/6),权重取自 Table 6 固定区间,beam search 由 Alg.1 执行,**遍历执行层零 LLM 介入**,与我方"纯 Python 执行"同类。LLM 只出现在三处:写入期事件抽取(附录 C.1)、慢路径因果/实体边推断(Alg.3 第 10 行)、最终作答(附录 C.2) | ❌ 错,须改判 |
| "取回子图后交 LLM 生成叙述并**自由**推理作答" | 核心正确(答案由 LLM 生成,无符号执行),但"自由"过宽:Stage 4 有拓扑排序 + `<ref:id>` 出处 + 显著性预算,附录 C.2 强制 "Use ONLY information explicitly stated in the context" 与固定弃答串 | ⚠️ 须软化为"受结构化脚手架约束的生成" |

**顺带撤回一类措辞**:MAGMA **有明确的步数与预算上限**——Alg.1 的 `MaxDepth` 外循环、`Candidates.TOPK(BeamWidth)`、第 19 行 `if Visited.SIZE() ≥ Budget then break`;Table 6 给 Max Depth 5 hops / Max Nodes 200 / Drop Threshold 0.15。**"循环无保证上限""检索无界/无保证终止"这类措辞在 MAGMA 上会和在 APEX-MEM 上一样翻车。** 这已是同一类错误第二次出现,**扫描级判"对方没报成本/没有上限"这类结论,今后一律不许进档案。**

### 4.2 总判决:MAGMA 比 A-TMA 更危险还是不更危险?

> ### **更危险。改判为:A-TMA < MAGMA < APEX-MEM。**
> **危险维度是"意图路由 + 有界确定性遍历 + provenance 契约 + 成本口径",不是"时序推理"。** 前者削掉 QVF 若干原以为是差异的东西;后者反而给 QVF 留了空档。

**MAGMA 高于 A-TMA 的四条**(A-TMA 按档案五.1 全部不具备)

| 轴 | A-TMA(档案已核) | MAGMA(本轮核实) |
|---|---|---|
| 按题型路由 | **无管线级路由**;四类查询画像仅用于检索排序与证据打标 | **有**在线意图分类器,同时改遍历权重(Eq.6)与生成指令(C.2);**消融里贡献最大**(0.700→0.637) |
| 确定性执行 | 读取侧终点是把标签向量塞进提示词 | **有界确定性检索执行器**(RRF + beam search + Budget/MaxDepth)+ **按题型的确定性上下文排序**(WHEN 按 τ、WHY 在 E_causal 上拓扑排序)。这是"题型 → 确定性后处理"的雏形 |
| 引用/日期纪律 | 证据打标,但无逐项时间戳 + 引用 ID 的提示词契约 | **有**:Eq.(7) `C_prompt = ⊕[<t:τ_i> n_i.content <ref:n_i.id>]`,明写 "To mitigate hallucination" |
| 成本口径 | 档案未记 | **有** Table 3 三项实测(0.39h / 3.37k / 1.47s)+ Table 6 硬上界 |
| venue | arXiv preprint 2026-07 | **ACL 2026 主会长文**,pp. 36848–36865 |

**MAGMA 低于 APEX-MEM 的三条(这是相对 00:06 版的回撤理由)**:① **无任何查询语言与结构化执行**——APEX-MEM 有 GraphSQL 的 SELECT/JOIN/AGGREGATE/TEMPORAL 只读执行,MAGMA 的确定性部分是**一个固定算法**,不是可组合算子;② **无任何冲突检测或版本择取**——APEX-MEM 至少检索双版本交 LLM 按时间戳择取,MAGMA 连"发现同一属性有两个值"都没有;③ 答案级归约 100% 在 LLM 提示词内。

**同时必须记入的减分项(把 MAGMA 的威胁封在"架构/路由"轴)**:① **它不是一篇强的时序推理结果**——LoCoMo Temporal 0.650 vs Nemori 0.649(+0.001);LongMemEval temporal-reasoning 45.1% vs 直读 42.1%(+2.1pp);总分优势 85%–99% 来自 Adversarial 一格。② **换指标就输**——Table 9 上 F1/BLEU-1 总体输给 Nemori(0.467/0.378 vs 0.502/0.403),四类里只赢 Single-Hop;而附录 F 整节的作用恰恰是论证 F1/BLEU 不可信,**那节同时也是唯一会显示 MAGMA 落后的那节**。③ **Overall 列对两条最强基线复算不上**,且两处偏差都指向压低基线,头条 "18.6%–45.5%" 按复算应为 15.5%–41.7%。④ **基线只四个**,Zep/GraphRAG/Mem0/MemOS/MemGPT/Hippocampus 在附录 A 大段讨论却一个都没进对照;也未引 A-TMA 与 APEX-MEM。

**唯一"不如 A-TMA"的轴**:A-TMA 是状态感知记忆失效的**诊断**论文,与 QVF 当前诊断定位正面撞位;MAGMA 是方法/系统论文,威胁形态不同。**但形态不同 ≠ 危险度更低。**

**一句话**:MAGMA 危险在"它在 ACL 2026 主会先把 **intent 路由 + 时间戳/引用 ID 的 provenance 契约 + 成本三项表 + 有界确定性遍历** 发出来了",不危险在"它把时序推理做好了"。

**本轮内部分歧记录(不隐去)**:七镜线独立给出的定级是"**与 A-TMA 相当或略高**",档案复核线给出"**A-TMA < MAGMA < APEX-MEM**",00:06 版写的是"**与 APEX-MEM 同级**"。三者的分歧全在"高多少",不在"是否更高"。本文档采用中间口径(高于 A-TMA、低于 APEX-MEM),依据是 4.2 那两张对照;**但"MAGMA vs APEX-MEM"这一侧未做逐轴打分,且 A-TMA 本轮未重读——若 A-TMA 也是扫描级定级,则本判决的基准一侧仍未加固**(见第七节第 10 条)。

### 4.3 更正后可直接替换档案五.3 的分界句(整段,可原样粘贴)

> **MAGMA(Jiang et al., ACL 2026 主会长文,`2026.acl-long.1709`, pp. 36848–36865;arXiv 2601.03236;开源)是本档中与 QVF 读取侧架构最形似的会议论文。** 它把每条记忆表示在语义/时序/因果/实体四张正交关系图上,并由一个在线意图分类器(`T_q ∈ {WHY, WHEN, ENTITY}`,论文明确标注不使用 oracle 标签)按题型调节遍历时的边类型权重(§3.3, Eq. 6)与生成时注入的推理指令(附录 C.2),其消融显示这条自适应策略是全系统贡献最大的单一部件(0.700→0.637, Table 4);检索为有界的确定性启发式束搜索(RRF 锚点融合 + Eq. 5 的闭式转移分数,配 Max Depth 5 hops、Max Nodes 200 与 Algorithm 1 的 `Visited ≥ Budget` 中断),遍历执行层不调用语言模型,亦不存在由语言模型临场生成查询串这一不受控环节;提示词按 `[<t:τ_i> content <ref:n_i.id>]` 逐节点携带时间戳与引用 ID 以抑制幻觉(§3.3, Eq. 7),并对低显著性节点压缩为摘要码;写入侧在图构建期把相对时间表达归一为绝对日期,分同步快路径与异步慢路径两流,并报告了 build time / tokens-per-query / latency 三项实测成本(Table 3)。
>
> **QVF 与其的分野不在"有没有路由""有没有确定性执行""有没有引用纪律"或"有没有成本口径",而在三处**:
>
> **(i) 路由的作用域。** MAGMA 的路由只改变边类型权重、剪枝偏好、上下文排序与生成提示词分支,四类意图仍共用同一条 `anchor → 束搜索 → 线性化 → 语言模型生成` 通路,预算常数为全局常量,不存在按题型切换数据基质或执行方式的分臂;QVF 的路由切换的是四条不同证据基质的臂。
>
> **(ii) 确定性执行的值域。** MAGMA 的确定性代码止于"选中并排好证据子图";从证据到答案的归约完全在提示词内由语言模型完成——计数在其案例研究中是 "2 (Photo) + 1 (Son/Brother) = 3" 的模型推断且输出带 hedge("at least three"),时长计算由提示词指令 "Calculate durations if asked" 交由模型执行,系统不含任何答案级算子、算子清单、计划表示或生成前的合法性校验。QVF 的算子计划求值输出的是答案值本身。
>
> **(iii) 记忆是纯追加的。** 时序主干被声明为 immutable,巩固阶段只增边,全文对 supersession / 覆盖 / 失效 / 版本 / 删除零提及,亦无任何冲突检测或版本择取,同一属性的新旧取值以同等身份并存;该设计的代价在其自身 Table 2 上可见:LongMemEval 的 knowledge-update 一类 66.7%,**低于**把整段历史直接塞入的 Full-context 基线 78.2%,而论文未讨论这一失守。
>
> **关于不可答:MAGMA 并非不处理。** 生成提示词含 "If the answer is not present, respond exactly with 'Information not found'",与判分提示词的 Adversarial Handling 条款咬合;其在 LoCoMo Adversarial 一类的判分 **0.742 是全表最高**,且按类目计数加权,该格贡献其相对最强基线 Nemori 优势的 85%(按论文所报 Overall)至 99%(按类目分数复算的 Overall)。QVF 的区别只在于该校验是确定性的、发生在生成之前、并与生成解耦,而非提示词层的弃答指令与判分口径;因此 QVF 不可由"缺 premise_check"推断其在该类上必然失守。
>
> **须一并注意的三点限定,以免被反证**:其一,MAGMA **有**确定性的相对日期归一化(把 "yesterday" 在写入时落成绝对日期 `date="2023-10-19"` 存入节点属性),故不可称其"只存到达时间"或"单时态戳";其 `[τ_s, τ_e]` 记号是查询侧过滤窗而非事实有效期区间;其真正的时间学缺口不是"单时间戳",而是**有效期区间与替换边的缺失**,以及**时序骨架按到达顺序构造(Fast Path 以上一个节点为前驱加边)却被形式化为事件时间序、两个时钟之间没有任何对账机制**。其二,MAGMA 在时序类上的优势本身很薄(LoCoMo Temporal 0.650 对 Nemori 0.649;LongMemEval temporal-reasoning 45.1% 对直读 42.1%),且在附录 F 的 F1/BLEU-1 口径下总体落后于 Nemori(0.467 对 0.502),因此不宜把它当作"多图检索已解决时序推理"的证据。其三,其形式化本身不完整——意图分类法在 §3.3(3 类)、附录 C.2(4 支)、Table 6(4 项,含全文未定义的 `w_phrase`)三处互不一致;Eq. 4 的三路 RRF 在 Algorithm 1 中只剩两路;Figure 3 画出的 "Entity Relationship Check" 与 "Logic Check" 在正文无定义、在消融无对应;语义视图 E_sem 既无 leave-one-out 也无 single-graph 变体。
>
> **危险度改判:高于 A-TMA,低于 APEX-MEM。** 高于 A-TMA 的理由是它已越过"检索 + 语言模型直答"这条线(有有界确定性执行器与按题型的确定性后处理)、有 provenance 契约、直接压住 premise_check 卖点、且成本口径与可复现性比 A-TMA 完整;低于 APEX-MEM 的理由是它没有查询语言与可组合算子,也没有任何冲突检测或版本择取。此前"不高于 A-TMA"的定级系扫描级误判,已撤回。限定词:2026 年论文,标 concurrent / ACL 2026 主会。

**替换操作提示**:此段替换五.3 的 MAGMA 行 + 该条结论句;替换时在档案里留一行"原文保留 + 更正注(2026-08-17,扫描级 → camera-ready 全文)",与 08-16 成本口径更正同一格式。**同时把两条 MAGMA 自身形式漏洞——时序链按到达顺序而非 τ 排序、意图分类法三处不一致——收入"可用反例/形式化空档"清单**,它们支持 QVF 的 formalization 定位。

**必须从档案与论文稿中删除或改写的五条既有话术(均已被原文否证)**:
- ❌ "MAGMA 无管线级路由 / 所有查询走同一流程" → 改为"路由只改权重、排序与提示词,不切换数据通路与执行器"
- ❌ "检索是 LLM 驱动的自适应遍历" → 遍历执行层零 LLM,是 Eq.5/6 + Alg.1 的闭式算术
- ❌ "论文未报告端到端成本" → Table 3 三项齐报
- ❌ "遍历步数无上限 / 检索无界" → Max Depth 5 hops / Max Nodes 200 / Budget break
- ❌ "无 premise_check / 不处理不可答" → 有弃答指令,且 Adversarial 是其最强格(0.742)

### 4.4 QVF 残余差异清单(标硬/软)

| # | 差异 | 硬/软 | 证据强度与依据 | 使用注意 |
|---|---|---|---|---|
| 1 | **有效期区间(valid_from/valid_to)** | **硬** | **强**。节点元组仅单个 τ_i;`valid_*`/`obsolet*` 全文 0 命中;唯一区间是查询窗 | 必须限定为"事实有效期",**不可**说成"无 ingestion/event 分离"(它有 T_session → 归一化日期) |
| 2 | **supersession / 旧值失效链** | **硬** | **强(本轮最强)**。词汇 0 命中 + 两条写路径纯增边 + 主干 immutable + 无冲突检测;并有 knowledge-update 66.7% < 78.2% 的自证代价 | 最值得引用的一条。可同时指出它在这点上**弱于 APEX-MEM** |
| 3 | **答案级确定性聚合算子(计数/时长/首末/join)** | **硬** | **强**。Case 2 计数为 LLM 推断且答案 hedged;`[Temporal]` 指令把算时长交给模型;全文无查询语言 | 措辞必须是"**答案级**归约无算子",**不可**说"无确定性环节"(RRF、Eq.5 打分、拓扑排序、日期归一都是确定性代码) |
| 4 | **闭集算子词表 + 生成前合法性校验 + 计划表示** | **硬(对 MAGMA)/ 软(对 Semantic XPath)** | 对 MAGMA **强**:无任何查询语言,确定性部分是一个固定算法,不存在"待校验的生成物"。但**对 APEX-MEM 只是软差异**(它有 GraphSQL),**对 Semantic XPath 几乎不成立**(它有闭合 BNF + 递归求值器) | 分界句必须分开写。见第五节 |
| 5 | **执行阶段零 LLM 介入** | **不成立(须改述)** | MAGMA 的检索段本就无 LLM(Fast Path 明写 "no blocking LLM reasoning occurs here";遍历是闭式算术) | 改述为"**从计划到答案值的归约段**零 LLM";**不能**说"MAGMA 的执行有 LLM 介入" |
| 6 | **按题型切换数据通路的分臂路由** | **软** | **中**。MAGMA 有在线意图路由,只是不换通路。二者差的是"路由的**作用域**",不是"有无路由" | ⚠️ 本轮翻车处。**绝不能**再写"MAGMA 无路由"。且 QVF 四臂"从未显著跑赢提示词臂",这条差异当前无正向实验支撑,**建议只作机制描述、不作贡献主张** |
| 7 | **确定性、答前、与生成解耦的前提校验** | **软(机制硬 / 收益软到负)** | **中**。MAGMA 有提示词层弃答 + Adversarial 0.742 最强格 | ⚠️ 反向证据在此:一条提示词把 0.205→0.742。QVF 若主张 premise_check 有价值,**必须给出超过提示词弃答的增量**,否则这条应降级 |
| 8 | **逐字锚点契约 + 违约率测量** | **软(架构)/ 硬(审计)** | 架构侧**弱**:MAGMA 已有 `<t:τ><ref:id>` 契约(Eq.7),明写为抑制幻觉。审计侧**强**:MAGMA 对其 ref 不做任何校验,也不报违约率,更未按语料分层 | 贡献应改述为"**对该契约的可验证性与语料条件性的量化**"(WikiState 9.67% vs LongMemEval 27.47%;剔除违约卡 KU 80.77%→85.90% 但 S5 −1.44pp),而不是"提出该契约" |
| 9 | **双时态(ingestion / event 分离)** | **软(由硬降软)** | MAGMA 有写入侧确定性日期归一化,功能上与 stated_date 重叠。QVF 真差异只剩"显式两个时间字段 + 有效期区间 + 对账",而它两个时钟隐含且未对账——那是**它的漏洞**,不是 QVF 的机制新意 | **这已是同一件事第二次被扫描级判错**(APEX-MEM 的 created_at + anchor_datetime),应记入纪律条目 |
| 10 | **六原语代数 P 的形式化闭性** | **软偏硬** | **中**。MAGMA 完全无代数;但其形式化本身不完整(意图分类法三处不一致、`w_phrase` 无定义、`τ_i<τ_j` 写入不保证、Eq.4 三路 vs Alg.1 两路)——这既是空档,也说明该空档在此 venue 未被视为门槛 | 作为 formalization 贡献的"存在性"证据可用;**不能推断"形式化本身构成 ACL 级贡献"** |
| 11 | **组合式查询的分解诊断**(c₁/c₂/d₁ 式) | **硬** | **强**。全文无"两跳链都对时组合题仍答错多少"这类分解;Table 4/5 只有聚合级消融 | **这是 QVF 当前"诊断论文"定位最有力的立脚点**——一篇主会长文在同一问题上只报了聚合数字 |
| 12 | 成本/延迟口径 | **不成立** | Table 3 报三项(0.39h / 3.37k / 1.47s)+ Table 6 硬上界 | **不可再说近邻不报成本、不可说检索无界** |

### 4.5 档案完全没提到、但对 QVF 有约束的机制

**A. Context Scaffolding with Provenance —— 逐节点"时间戳 + 引用 ID"提示词契约(最重要的一条)。** §3.3 Stage 4.2:"To mitigate hallucination, each node is serialized into a structured block containing its timestamp, content, and explicit reference ID";Eq.(7) `C_prompt = ⊕_{n_i ∈ Sort(G_sub)} [<t:τ_i> n_i.content <ref:n_i.id>]`;并且 "This structured scaffold **forces the LLM to act as an interpreter of evidence rather than a creative writer**, significantly reducing grounding errors"。这与 QVF 的"每张卡带陈述日期 + 逐字锚点、读者渲染受约束"在提示词层面**几乎同构**,动机措辞也高度接近。**后果:QVF 不能把"带日期与锚点的证据卡渲染"作为新意主张**;剩下的是"锚点是可对源校验的逐字 span,并且我们测了违约率"——MAGMA 的 `<ref:id>` 无任何校验。这正好把 QVF 的贡献锚在"审计/诊断"上,与当前诚实定位一致。

**B. Salience-Based Token Budgeting + brevity codes(§3.3 Stage 4.3)。** "Low-probability nodes are summarized into brevity codes (e.g., '…3 intermediate events…'), while high-salience nodes retain full semantic detail." 按 Eq.5 相关度动态压缩上下文。**约束:QVF 关于 token 效率的任何"机制新意"表述都要避开这一处在先公开**,可比较的只有具体数字。

**C. 写入期相对日期归一化(附录 E.2 Case 3)。** `T_session(Oct20) − 1 day = Oct19`,存为节点属性 `date="2023-10-19"`。**约束:QVF 的 `stated_date` 抽取(把"上周五"落成绝对日期)在此已有会议级在先公开**,不能列为独有写入侧设计;QVF 的差异只在于进一步区分陈述日期与有效期区间。

**D. 有界遍历 + 三项成本实测。** Max Depth 5 hops / Max Nodes 200 / Drop Threshold 0.15 / RRF k=60 / Vector Top-K 20(Table 6)、`if Visited.SIZE() ≥ Budget then break`(Alg.1)、Table 3 三项。**约束:"代理式检索成本不可控/不透明"这条通用批评不能对 MAGMA 用。**

**E. 提示词层弃答 + 判分器的不可答口径。** 见 4.1 断言 4。**约束:premise_check 的价值主张必须给出超过"一条弃答指令"的增量**,否则这是 QVF 现阶段最脆弱的一条主张。

**F. 双流写入(Fast/Slow Path)的延迟-深度解耦。** Fast Path 明写 "no blocking LLM reasoning occurs here";Slow Path 异步 worker 取 2-hop 邻域交 LLM 补因果/实体边,结果是全表最低查询延迟 1.47s。**约束:QVF 若声称"写入侧离线抽卡"是工程优势,此处已有同构设计与命名(synaptic ingestion / structural consolidation);且 QVF 若报延迟,必须说明是否含写入侧 LLM 成本**——注意 MAGMA 的 Table 3 **不含**慢路径每事件一次 LLM 调用的 token,这是可以对称指出的口径缺口。

**G. 它留下的六个明确空位(QVF 可站的位置)。** ① 答案级确定性聚合算子(六原语里 AGG/WINDOW/PICK 这一格文献里完全空着);② 有效期区间 + 替换边(有自证代价数字);③ **组合式查询的分解诊断**(c₁/c₂/d₁ 口径在文献里仍是空位——最有力的立脚点);④ 逐字锚点契约的**违约率测量**与语料条件性;⑤ **路由器精度与其收益的关系**(它把路由当最高价值组件却不报分类精度、不给 oracle 上界);⑥ 正交性/视图重叠的测量、写后即读的结构不完整性、迟到/追溯写入——三处都是"论文明确依赖但从未测"的位置。

**H. 两篇必须立刻补查的同组关联工作(档案完全没有)**

1. ⚠️ **`Jiang, Li, Wei, Yang, Kishore, Zhao, Kang, Hu, Chen, Q. Li, et al. 2026. "Anatomy of agentic memory: Taxonomy and empirical analysis of evaluation and system limitations." arXiv:2602.19320`** —— **与 MAGMA 同一第一作者**,被 MAGMA §6 引用。从题目看是"分类法 + 评测与系统局限的实证分析",**这正是 QVF 当前自审后确定的"合格的经验/诊断论文"这一体裁的直接竞品**。QVF 的诊断结论(c₁=99.6% / d₁=55.9% / c₂=46.2%,组合的墙在编译-执行-渲染层)是否已被该文以另一种形式覆盖,**必须在写 related work 之前独立核实。优先级高于本轮任何其他遗留项。**
2. `Yi Li, Cao, Ahmed, Sharma, B. Li. 2026. "Hippocampus: An efficient and scalable memory module for agentic AI." arXiv:2602.13594` —— 同组,附录 A 与 MemoryOS/MemOS 并列。优先级中。
3. 次要:`Xu, Wu, Jia, Wang, Liu, Dong. 2026. "Self-correcting RAG: … NLI-guided MCTS." arXiv:2604.10734` —— 与 premise_check 相邻,扫描级即可。

**I. 上一轮的仓库级观察(本轮未复核,原样留档并降级)。** 08-18 00:06 版依据仓库 HEAD 记录了四条代码级观察:`answer_formatter.build_qa_prompt(..., category)` 按 LoCoMo 数据集类别字段分支(与附录 C.2 "no oracle labels" 脚注冲突)、`validate_adversarial_answer` 仅 `category==5` 触发、`--best-of-n` 默认 3 + `--best-of-n-method` 默认 `llm_judge` 且用 gold 答案选优、约 1059 行的答案归一化层。**本轮三条线均未打开仓库,这四条一条都没有复核。** 引用时一律标"**代码级观察,未复跑,仓库 HEAD 未必等于产出论文数字的版本**",且**不得作为审稿级指认使用**。由此对 QVF 的约束不变:不要把 MAGMA 的 0.700 / 0.742 当作该范式的可信性能上限来对标;若当基线必须自己复跑并显式关闭 best-of-n 与 gold-category 分支;**QVF 自己的报数纪律应在论文里显式声明**(不做 best-of-n、路由标签由自家分类器产出、premise_check 不看 gold)——这条"评测卫生"声明本身可以成为诊断论文的一个真实、零成本、可核验的贡献点。

---

## 五、Semantic XPath 定级判定(顺带线)

> 对象:**Semantic XPath**,ACL 2026 **System Demonstrations(demo track,不是主会)**,`2026.acl-demo.28`,pp. **286–296**,DOI `10.18653/v1/2026.acl-demo.28`,多伦多大学 Sanner 组(D3M lab)。camera-ready 全文已抽(含附录 A 执行语义 / B 分域表 / C 案例),arXiv v1 HTML 就 §3.1 数据模型句、语法块、Setup 段逐条交叉校验——**语法块与 Setup 完全一致**,数据模型句有措辞重写但**无实质差异,两版均不含时间戳字段**。(档案记的 arXiv 号 2603.01160 本轮未复核,标弱证据。)

### 5.1 是否需要升级

**需要"部分升级",但升级的**维度**和档案原判不同——不是"危险度从低升到高",而是**危险维度判错了**。

- **不需要升级的部分**:它**不是时序推理近邻**。数据模型 `T = (V, E, r)`,"Each node v ∈ V stores a **node type τ and textual attributes**",字段清单里**没有任何时间字段**;文法层也没有时间谓词(位置选择器 `[i] [-i] [i:j]` 的语义在附录 A.4 明写为 "in the **tree order** induced by the memory tree",是树序/插入序,不是时间序);聚合算子集是 `{avg, min, max, gmean}`,作用域是 **[0,1] 的相关性分数**(`Rel: V × Φ → [0,1]`),**没有 count、没有 sum、没有 duration、没有 as-of**——"变了几次""持续多久"在文法上**不可写**,不是"效果差";无 premise_check(且结构上不可能:模糊打分必然返回 top-1);无管线级路由(全部请求走同一条 translate → execute → generate)。作为"时序状态记忆"竞品,危险度**明显低于 A-TMA**,这一半档案对了。
- **必须升级的部分**:档案把它归入"Zep/Mem0/Engram 类:保时间线但读取无查询条件化"的**反面证据簇,这个归类错了**。它恰恰**有**读取侧的形式化查询语言 + 确定性递归执行器 + 可视化执行 trace。**档案原句"XPath 查询由 LLM 临场生成,无算子闭集"——前半对,后半错**:§3.2 给了完整闭合 BNF(`Q ::= ∅ | S∅ | SQ`;`S ::= A N [R] [P]`;`A ::= / | //`;`N ::= NodeType | *`;`R ::= [i] | [-i] | [i:j]`;`P ::= (P+P)/2 | P·P | min(P,P) | max(P,P) | 1-P | Local | Agg(S)`;`Local ::= [attr_name ~= String] | [node ~= String]`;`Agg ::= avg|min|max|gmean`),**没有 escape hatch**;§3.3 + 附录 A.1–A.5 定义**单一递归求值函数** `E : X × W → W`(`W ⊆ V × [0,1]`),对每种语法形式逐例给出闭式定义,并有基例保证终止,**执行期零 LLM 介入**(唯一神经成分是 `Atom_loc` 相关性打分,Qwen3-Embedding-8B 或 `bart-large-mnli`,作为 oracle 被确定性执行器调用,不决定控制流)。
- 因此:它应从 D 组(反面证据簇)移入 **"编译-执行范式近邻"组,与 APEX-MEM 并列**,并需一条独立分界句。**它在"闭集"这一点上比 APEX-MEM 离 QVF 更近**(APEX-MEM 是 LLM 临场写 SQL,无固定算子清单),**但在"算什么"上离得更远**(APEX-MEM 的 GraphSQL 有真 AGGREGATE/TEMPORAL,能算出值;Semantic XPath 的值域只到节点集)。**两篇合起来,把 QVF 的"闭集编译 + 确定性执行"这条卖点从两侧夹住了。这是本节最该带走的一条**,与自审结论"三条候选技术创新全部零成本证否 / 查新判 0 条为新"方向一致。
- **最关键、档案完全没抓到的分界事实——值域**:Semantic XPath 执行的**输出类型是带权节点集 `W ⊆ V × [0,1]`**,永远不是一个答案值。定位到子树之后 "The retrieved substructure is passed to **downstream generation**",答案、算数、编辑全部由 LLM 读子树自由完成;写入侧同理("the update by creating a new version branch" 由下游步骤执行,算子只负责选中节点)。**所以它的确定性只覆盖"选哪一块",不覆盖"算出什么"。**
- 档案第 1 条须精修一处措辞:"无法回答某时点是什么类时序聚合问题"作为**机制陈述**成立,作为**能力陈述**略微越界——它在 LoCoMo 上报了 Temporal 分列成绩,GPT-5 mini 下 **62.31 vs In-context 59.81**(反超),Gemini 3 Flash 下 **77.26 vs 84.74**(落后),靠的是 LoCoMo 原生树里 session 顺序隐含时序 + 语义打分。建议改为"**无时间维度语义**(数据模型与文法均无时间戳/有效期/时间谓词),时序题只能靠结构顺序与语义相似度间接命中"。

### 5.2 它和 QVF 的"逐字锚点 + 版本保留"是不是同一件事?

**不是,但要拆成两半答:版本保留有实质重叠,逐字锚点零重叠。**

| 维度 | Semantic XPath 的 Version 节点 | QVF 的六字段卡片 |
|---|---|---|
| **粒度** | 整棵子树的快照/分支(一次编辑 → 一个新 Version 分支) | 单个 (属主, 槽位) 的取值 + 替换边 |
| **寻址方式** | `[-1]` 树序位置(取最新)/ `[3]`(第三次修订),由代码算出;或 `[node~="delete poster session"]` 对**编辑动作文字描述**的 embedding 匹配 | 陈述日期(时间坐标)+ 显式 superseded-by 指针 |
| **溯源契约** | 无。Version 只有 textual attributes,**无出处字段、无 answer-support 校验、无契约违约概念** | 逐字锚点契约 + 违约率可审(WikiState 9.67% / LongMemEval 27.47%) |
| **回答的问题** | "把那次编辑时的子树给我"(**定位**) | "t 时刻的值是什么 / 改过几次 / 持续多久"(**计算**) |

- **版本保留:实质重叠。** 双方都非破坏性、都在编辑时分支、都能检回被删值。附录 C 案例是全文唯一真正用到 Version 节点的地方:用户问"刚删掉的 poster session 原来几点?",查询 `//Version[node~="delete poster session"]//POI[node~="poster"]` 把删掉十轮的时间捞回来,**且不用任何时间字段就答上了**。分界句:"**同为非破坏性修订史;SXP 是序数/语义索引的取代,QVF 是时间索引的取代。**" **后果:QVF 不能再声称"既有系统无法确定性检回历史版本";ASOF 的价值必须改口径,只在绝对时间点、时长、变更计数三处论证。**
- **逐字锚点:无重叠。** 分界句:"**SXP 的文本属性是被打分的内容,QVF 的逐字锚点是被核验的证据。**" 但 QVF 自审已测出该契约价值是语料条件性的,所以这条分界**只能当定性差异用,不能当性能来源**。
- **新增撞车点(档案未记)**:§3.1 明写不预设人工 schema、σ 由数据中已有结构决定——与 QVF 开槽写入侧(`QVF_openslot_writeside_design.md`)同一主张:**算子闭集 + 模式开放**。这条要进相关工作,不能当自己的新意。

### 5.3 建议入档的分界句(可直接用)

> 同期 ACL 2026 的**系统演示论文** Semantic XPath 在结构化对话记忆上给出了与本文同类的形式化读取接口:一个闭合的 XPath 式文法(轴 / 类型选择器 / 位置选择器 / 语义相关性算子,聚合子集为 {avg, min, max, gmean})与一个逐例定义的递归求值函数,执行期不调用语言模型。但其求值函数的**值域是带权节点集 `W ⊆ V × [0,1]`**——算子只负责"选中哪一块子树",答案、计数与编辑一律交由下游语言模型读子树自由生成;其聚合算子作用于 [0,1] 的语义相关性分数而非取值本身,文法中既无计数与时长算子,也无任何时间谓词,Version 节点只存文本属性、不存时间戳或有效期区间,版本寻址靠对编辑描述的语义相似度或树序位置(`[-1]`),因此"某时点是什么 / 改过几次 / 持续多久"在其文法上不可表达;查询由语言模型依 schema 临场翻译且无执行前合法性校验(语法非法查询直接计入失败),全部请求走同一条 translate → execute → generate 管线,无按问题类型的路由、无答前前提纠错。QVF 与其一线之隔在**值域与时间**:算子计划的输出是答案值而非节点集,闭集内含计数/时长/定点(ASOF)与 premise_check,时间是数据模型的一等字段而非文本属性。

### 5.4 一条可用的正向借力

SXP 拿 ACL 2026 靠的是"结构化访问效率 + 系统演示",且在唯一标准基准 LoCoMo 上**明确输给 in-context 上界**(answer score 65.19 vs 74.55;73.25 vs 87.01),换来 12.2% / 14.1% 的 input token。这是 QVF"卡片臂从未显著跑赢提示词臂"这一处境的**同行先例**——同样的形状,人家在 demo track 过了。

---

## 六、引用纪律

### 6.1 可以直接引(camera-ready 原文明载,坐标已核)

- 四张关系图的划分与各自定义(§3.2);Eq.(3) 节点四元组 `⟨c_i, τ_i, v_i, A_i⟩`;Eq.(4) RRF;Eq.(5) 转移分数;Eq.(6) 意图权重 `Φ(r,T_q)=w_{T_q}·1_r`;Eq.(7) provenance 序列化格式。
- 意图三类 `{WHY, WHEN, ENTITY}` 与 "steering wheel" 定位;Stage 4 按意图的排序分支(WHEN 按 τ、WHY 在 E_causal 上拓扑排序)。
- 时序图逐字定义句("strictly ordered pairs… This immutable chain provides the ground truth for chronological reasoning")与 Alg.2 第 2/4 行。
- 界限常数:Max Depth 5 hops / Max Nodes 200 / Drop Threshold 0.15 / RRF k=60 / Vector Top-K 20;λ₁=1.0 base(Table 6)。
- Table 1 五类分数 + Table 7 类目计数(1,986 题;Adversarial 446);Table 3 三项成本(0.39h / 3.37k / 1.47s);Table 4/5 两套消融数值(含 `w/o Adaptive Policy` 0.637);**Table 9 全表 F1/BLEU-1**(引用时说明"Overall 在剔除 Adversarial 的 1,540 题上,已按 Table 7 题量复算 MAGMA 行吻合")。
- 附录 E.2 Case 2 / Table 8 的聚合算式 "Logic: 2 (Photo) + 1 (Son/Brother) = 3" 与答案 "At least three."(标附录 E.2 / Table 8, Case 2)。
- 附录 E.2 Case 3 的日期归一化 `T_session(Oct20) − 1 day = Oct19` 与 `date="2023-10-19"`。
- 附录 C.2 指令 1/2 与 `[Temporal]` 指令 "Calculate durations if asked";附录 C.3 Evaluation Constraints 第 3 条 Adversarial Handling。
- 判官与骨干配置:统一 gpt-4o-mini,LLM-as-a-Judge temperature=0.0,答题与判分同一模型(附录 D)。
- 十个替换类词(supersede/overwrite/version/delete/conflict/stale/invalidate/deprecate/obsolete/valid_from)的**零命中**结论——这是可引的否定性证据,因为已逐词 grep camera-ready 全文。

### 6.2 必须加限定词才能引

| 数字/说法 | 必须加的限定词 |
|---|---|
| Overall 0.700 与 "18.6%–45.5% 相对优势" | "论文报数;按其自报类目计数复算,五个系统中 Full Context 与 Nemori 两行不能还原所报值(算得 0.494 / 0.606,报 0.481 / 0.590),若采用复算值该相对提升应为 15.5%–41.7%" |
| Adversarial 0.742 | "按类目计数加权,该格贡献其对最强基线优势的 **85%(按所报 Overall)至 99%(按复算 Overall)**;判官与答题为同一模型;MAGMA 独享一条提示词级弃答指令而基线用各自默认提示词" |
| Table 9 的 F1/BLEU-1 | "该表只有四类、无 Adversarial,n=1,540;MAGMA 与 Nemori 两行可复算,Full Context / A-MEM / MemoryOS 三行不能复算且均报低" |
| Table 2 各数 | "原表列错位,本处为按词坐标重建值,并以正文 89.3% 归属互证";**且不得写"在 N 题上"** |
| 全部 LoCoMo/LongMemEval 数字 | "单一 backbone(gpt-4o-mini)、单次运行、未报 seed/方差/置信区间/显著性检验;超参在 LoCoMo 上 empirically optimized 而结果亦在 LoCoMo 上报,无 dev/test 划分" |
| "它有路由" | 精确到"意图条件化的边类型权重 + 剪枝偏好 + 上下文排序 + 生成侧提示词分支;不选择算子、不产生可校验计划、不切换执行器;预算常数为全局常量" |
| "它有确定性执行" | 精确到"遍历执行层零 LLM,值域止于选中并排好的证据子图;答案级归约仍在提示词内由模型完成" |
| "它有确定性日期归一化" | "写入侧相对表达式归一化,存为节点属性;不是有效期区间,`[τ_s,τ_e]` 是查询过滤窗" |
| "它有弃答机制" | "提示词层固定串 + 判分器 Unanswerable 口径,不是答前的确定性前提校验算子" |
| 任何仓库级观察 | "上一轮代码级观察,本轮未复核,未复跑;仓库 HEAD 未必等于产出论文数字的版本" |
| Semantic XPath 的 176.7% / 9.1% | **两个数字来自两个不同配置**:176.7% = 单轮 / GPT-5 mini / entailment 打分器 / 三自建域宏平均(约 60–65 条请求)对 Flat RAG 的 pass-rate 相对增益(83.0 vs 30.0);9.1% 只能从**多轮 / GPT-5 mini / semantic-similarity** 那一格复现(6,294/69,097);**没有任何单一配置同时达成**。且必须写 **ACL 2026 System Demonstrations(demo track)**,不得写主会 |

### 6.3 不可引

- **LongMemEval 的 n 与子集**:论文未报题数、未说明用 S 还是 M 子集,**不得写"在 N 题上"**,也**不得做类目加权自校验**(这是它与 Table 1 的关键差别)。
- **任何显著性/置信区间表述**:全文无检验、无 seed、无重复运行,**不得写"显著优于"**;Temporal 0.650 vs 0.649 尤其不得写成"一致优于"或"验证了时序引擎"。
- **不得说"判官模型未指名"**:已核实为 gpt-4o-mini、T=0.0、与答题同一 backbone(附录 D)。凡依赖"判官身份不明"的批评一律作废;可用的批评是"**自评风险未量化**"。
- **不得说"近邻不报成本"**、**不得说"检索无界/无保证终止"**、**不得说"它没有拒答机制"**、**不得说"它无管线级路由"**、**不得说"它的遍历由 LLM 驱动"**——五条都会被正文/附录/伪码当场反证。
- **不得把仓库级观察绝对化**,也不得据以作审稿级指认(本轮未复核)。
- **不得由"MAGMA 无 premise_check"推出"它在不可答类会失守"**——它是全表最高 0.742。
- **不得称 MAGMA "单时态戳"或"只存到达时间"**——它有会话时间戳 + 归一化事件日期两个时间点。
- **判官自评抬高多少分:不得给数字**,论文未测,我方也未测。
- **附录 F 与 Table 9 排名翻转的定量关系:不得下结论**——只能说"它在两个词级指标上被 Nemori 反超,而它对此的辩护是七个手工构造样例"。
- 页码引用用 ACL Anthology 版(`2026.acl-long.1709`, pp. 36848–36865, DOI `10.18653/v1/2026.acl-long.1709`, San Diego, month=jul),arXiv 2601.03236 仅作 eprint 备注。作者单位 **UT Dallas + University of Florida**,不是 Amazon。档案 §四 现有 BibTeX 条目(第 148 行)信息正确,无需改动。

### 6.4 对称纪律:对我方有利方向的更正也要如实引用

这条是硬纪律,不是姿态。**本轮至少五处更正对我方有利,同样必须如实、带限定地写进档案与论文**:

1. **它的两个时钟未对账**(§3.2 声明 τ-序 vs Alg.2 按到达顺序建边 + 允许回溯定日)——对我方有利,但必须同时写明它**确实有**日期归一化,不能只写前半句。
2. **它 Overall 口径不自洽、两处偏差都对基线不利**——对我方有利,但必须同时写明偏差幅度仅 0.013/0.016,**不足以推翻其结论**,措辞只能是"口径不自洽"。
3. **Table 9 上 Nemori 反超、且该表恰好无 Adversarial 列**——对我方极有利,但必须同时写明附录 F 对词级指标的批评**方向本身是对的**(false reward/penalty 确实存在),我方未量化这能解释多少翻转。
4. **knowledge-update 66.7% < Full-context 78.2% 且论文未讨论**——对我方最有利的一条,但必须同时写明 MAGMA 在该基准的 Average 上仍最高(61.2%),不能只摘这一格。
5. **它形式化不完整**(意图分类法三处不一致、`w_phrase` 无定义、Eq.4 三路 vs Alg.1 两路)——对我方的 formalization 定位有利,但必须同时写明**这个空档在 ACL 主会未被视为门槛**,不能推断"把它讲清楚就构成 ACL 级贡献"。

**反方向的六处(它有路由、有界限、遍历是确定性代码、有 provenance 契约、有日期归一化、Adversarial 全表最高)已在 4.3 段如实写入,不得在对外材料里悄悄省掉。** 上一轮仓库级观察对我方极有利,本轮未复核,**因此本轮一律降级处理**——这条纪律必须双向,否则就变成单向武器。

---

## 七、未核实清单(一条不省)

1. **本轮完全未打开代码仓库**(`github.com/FredJiang0324/MAGMA`)。因此:Table 6 六项区间超参的实际点值、`BeamWidth` 的值、因果边阈值 τ、意图分类器的实现与提示词、事件分段器 `SEGMENTEVENT` 的实现,全部**未核实**;"三套意图分类法如何映射"只能从论文推测。
2. **上一轮四条仓库级观察本轮未复核**:`build_qa_prompt(..., category)` 按数据集类别字段分支、`validate_adversarial_answer` 仅 `category==5` 触发、`--best-of-n` 默认 3 + `llm_judge` 用 gold 选优、约 1059 行答案归一化层。行号与调用链来自上一轮 HEAD 快照,**未复跑;仓库 HEAD 与产出论文数字的版本关系未验证;best-of-3 是否用于论文报数未证实**(论文正文未提 best-of-n)。
3. **未逐字 diff arXiv v2 与 camera-ready 全文正文与表格。** 已核标题、版次(v1 2026-01-06 / v2 2026-04-16)、comments 栏("ACL 2026 Main"),并就 §3.2 时序图定义、节点元组、§3.3 意图集合、supersession 词汇四点逐句比对(一致);已知唯一差异是 camera-ready 摘要多了代码 URL 一句。**表格是否有差异未核。**
4. **LongMemEval 各题型题量与子集(S/M)论文未给。** 因此 Table 2 百分比不能反算题数、不能做类目加权自校验。§m2 里那组试算(TR 133 / MS 133 / KU 78 / SU 70 / SA 56 / SP 30,合计 500)**来自本文之外的公开分布,本轮未独立核实**;该组权重能精确复现 Full-context 55.0% 与 Nemori 56.2%,但 MAGMA 复算 59.8% ≠ 报告 61.2% —— **仅作为向作者提问的疑点,不作任何结论**。相反,LoCoMo 的 Table 1/9 复算用的是本文 Table 7 自带题量,结论可靠。
5. **Table 2 的列归属**依赖一处互证(§4.3 正文把 89.3% 归给 Full-context)。自洽,但若取到官方 LaTeX/HTML 源应再核一次。
6. **Table 2 中 Full-context 在 single-session-preference 上的 6.7% 未获解释。** 该异常值决定 Table 2 的整个头条(剔除后五类简单均值 Full-context 65.3% > MAGMA 63.8%),论文一字未提,我无从判断是实现问题、评测口径问题还是真实现象。
7. **Table 5 与 Table 1 的小数精度不一致**(两位 vs 三位)。用 Table 7 题量复算三行 single-graph 总分均吻合,**推断**为同一 1,986 题集的不同舍入,未获论文确认。
8. **Figure 3 里的 "Entity Relationship Check" 与 "Logic Check" 两个方框在正文无对应描述。** 只能确认它们出现在图里、不在 §3.3 的四阶段叙述里、不在 Table 4 的消融里;实际功能**未核实**。Figure 1/2/3 均只读了图注与文字层,未逐格读图元(Figure 2 与 Alg.2 已发现一处冲突:Fast Path 连边种类)。
9. **Table 6 的 `w_phrase` 在全文其他任何位置都不出现。** 已用坐标 dump 确认四行权重名依次为 w_entity / w_temporal / w_causal / w_phrase,但"phrase"指什么、与 §3.2 的 E_sem 是否同一物,**无法从论文判定**。
10. **判官的自偏好程度未量化。** 只能指出答题与判分同为 gpt-4o-mini、附录 F 的支撑材料只有 7 个手挑构造案例、无抽样与人工一致性系数;偏好方向与大小**未核实**。另:判官配置的确切出处在"附录 B"还是"附录 D",两条线记法不一致,**未定**(本文档采用附录 D)。
11. **慢路径固化滞后时间、图统计量(节点数/各类边数/因果边密度)全文缺失。** B5-a"写后即读会读到结构不完整的图"是从 Alg.3 队列语义**推得**,论文既未确认也未否认,更未测量。
12. **附录 F 的论证与 Table 9 排名翻转之间的定量关系,论文没做,我也没做。**
13. **Nemori 是 arXiv 预印本(2508.03341),未经同行评审**——它是本文最强 baseline,也是关键复算的对照方,其自身数字的可靠性本轮未独立核实。
14. **"A-TMA < MAGMA < APEX-MEM" 这一改判未做横向逐轴打分。** 本轮只做了 MAGMA vs A-TMA 的五轴对照与 MAGMA vs APEX-MEM 的三条定性理由;**A-TMA 本轮未重读**,若它也是扫描级定级,则本判决的基准一侧仍未加固——**这条应作为下一轮的第一项**。三条线对定级幅度的内部分歧已记在 4.2 末。
15. **Semantic XPath 侧**:arXiv 号(档案记 2603.01160)与 GitHub `D3Mlab/SemanticXpath-Chat` 本轮未核;"请求 → 查询"这一步由什么模型翻译、用什么提示词,**论文从未点明**(demo 论文级复现缺口),"LLM 生成"是由 Table 1 caption "input tokens include query generation" 与 Figure 8 失败分类学倒推的;自建三域题数口径未解(To-do List 单轮出现 64.0 / 84.0 / 48.0,是 4 的倍数,反算 n=25,与正文"每域 20 single-turn"自相矛盾,论文未解释);Version 层是否有隐含时间字段仅由 grep 零命中支持;LoCoMo 题数论文未报。
16. **同组两篇关联工作未查**:arXiv 2602.19320(与 MAGMA 同一第一作者的 agentic memory 分类法 + 评测局限实证分析,**是 QVF 诊断定位的直接竞品**)、arXiv 2602.13594(Hippocampus)。**前者优先级高于本轮任何其他遗留项。**
17. **MAGMA 是否已有第三方复现或勘误未查。**
18. **QVF 侧数字全部引自本轮任务背景交付的自审结论**(S5 +35.4pp、c₁ 99.6% / c₂ 46.2% / d₁ 55.9%、违约率 9.67% vs 27.47%、KU 80.77%→85.90%),**本轮未回原始结果文件复核**。第四节的"占走/空位"判断依赖这些数字为真。
19. **本文档第三节的七镜 A–G 与第四节的复核结论来自三条独立线的整合**,其中定级幅度一条存在内部分歧(已在 4.2 末如实记录);三条判决(C/D/F)未经第二人复核。
