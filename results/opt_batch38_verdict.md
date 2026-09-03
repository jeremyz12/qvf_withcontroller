# 批 38 终判:写入侧抽取器换 claude-sonnet-5 —— 账目的天花板是不是建卡器?

**待验证猜想(批 36-B 提出)**:账目臂对读者不敏感(smoc 91.4%@haiku vs
90.7%@sonnet-5,同一 140 题同一店),而同读者的全文直读能到 97.1%;
故**账目的天花板由写入侧建卡决定**,换更强的抽取器应当抬高天花板。

**判决:猜想被部分证实,而且以一种反直觉的方式。**

- **写入侧保真度这一半:被证实,且是压倒性的。** 把抽取器从
  claude-haiku-4-5 换成 claude-sonnet-5 后,编译账目对金标链的命中从
  **122/133(91.7%)升到 133/133(100%)**,漏行从 11 条降到 **0** 条,
  完美链从 31/36 升到 **36/36**。这是本批最硬的一个数字。
- **端到端准确率这一半:被否定。** 同样这 140 题,smoc 只从 91.4% 升到
  **92.9%**(haiku 读者,+1.43pp,McNemar **p=0.81**)、从 90.7% 升到
  **92.1%**(sonnet-5 读者,+1.43pp,**p=0.82**)。**两条都不显著。**
  与全文直读的差距(97.1%)**没有被关上**:92.1% vs 97.1%,
  配对 −5.00pp,翻转 2 正 / 9 负,**p=0.065**。
- **原因(事后发现,非预注册)**:更强的抽取器把**漏行**修光了,却同时引入
  **两条新的写入侧退化**——槽位名碎片化(7/36 链 vs v45 的 2/36)与
  日期粒度丢失(24/133 行 vs v45 的 2/122)。这两条恰好吃掉了保真度的红利。
  在**没有**被这两条打到的 29 条链(114 题)上,
  smoc_v47s@sonnet-5 = **97.4%** vs 全文直读 98.2%,
  配对翻转 1 正 / 2 负,**p=1.00 —— 与全文直读统计上打平**。

一句话:**"账目的天花板在写入侧"是对的;但把它顶住的不是抽取的准不准,
而是抽取的规不规范。**

---

## 一、口径与产物

| 项 | 值 |
|---|---|
| 题源 | `results/b35_questions_sample36.jsonl`,140 题 / 36 链 |
| 语料 | `data/wikistate_full_ALL_v24.json`(v2.4),sha256 `c62291…4060749`(与批 33-A 逐字同) |
| 对照店 | `results/wt_cards_v45`(claude-haiku-4-5 建,批 33-A),**本批全程只读** |
| 本批店 | `results/wt_cards_v47s`(claude-sonnet-5 建,36 链),36 文件 / 1,743 记录 |
| 建店窗 | 2026-09-03 22:23:22 → 22:46:51 |
| 目录 sha256 | v47s `a80ea1f36554abff8964a1d536f911f613bac7e54200cfd9928b7fb946cdb3dd` |
| 建卡器 | `scripts/wt_qvf_prototype_b38.py`(冻结件 `wt_qvf_prototype.py` 的副本 + 两处最小改动) |
| 跑批脚本 | `scripts/lb_reader_arm_b36b.py`(批 36-B 原件,**零改动**) |
| 记分 | `scripts/b38_score.py` → `results/b38_score_out.txt` |
| 溯源 | `scripts/b38_provenance.py` → `results/b38_provenance.txt` |
| 产物 | `results/b38_smoc_v47s_haiku-4-5.jsonl`、`results/b38_smoc_v47s_sonnet-5.jsonl`(各 140 行) |

**v45 未被触碰的机械证明**:本批溯源块重算的 v45 目录 sha256 =
`bcb31a114dc27479326d981bbce9c6d906d7689c00e18b9d4371aeecf55589d4`,
与 `results/b33A_provenance.txt` 里 2026-09-02 记录的值**逐字相同**。

---

## 二、v45 建店配置(问题 1 的答案,已逐字复核)

抽取模型的开关是**环境变量 `QVF_CARD_MODEL`**
(`scripts/wt_qvf_prototype.py:150`,注释在 :139-149):

```python
_CARD_MODEL = os.environ.get("QVF_CARD_MODEL", "") or MODEL   # MODEL = "claude-haiku-4-5"
```

它**只作用于建卡调用 `_catalog()`**,不影响读取侧聚焦与读者(那两处仍用 `MODEL`)。

v45 的建店命令(自 `results/opt_batch33_A_rebuild_verdict.md` §九 与
`scripts/b35_provenance.py:118` 两处独立复核):

```bash
QVF_CARD_OWNER_GATE=0 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype.py \
  --phase write --data data/wikistate_full_ALL_v24.json \
  --cards-dir results/wt_cards_v45 --uids <shard>        # 6 分片并行
```

`QVF_CARD_MODEL` **未设** → 抽取器 = `claude-haiku-4-5`;
`QVF_CARD_TEMP0` 默认 1 → 发 `temperature=0.0`;`max_tokens=16000`;
其余建卡旗标(KEYS/TAGS/V5/STRICT/ABS_DATE/RENUMBER/VERIFY_SPAN/
FAIL_LOUD/INCR/BY_SESSION)全 0。建店窗 16:52:05 → 17:10:18。
建卡日志在 `scratchpad/build_v45_{0..5}.log`。

### v47s 与 v45 的差异只有三处,逐条照实记

| # | 差异 | 理由 |
|---|---|---|
| 1 | `QVF_CARD_MODEL=claude-sonnet-5` | **本批的自变量** |
| 2 | **不发 `temperature`** | claude-sonnet-5 已移除采样参数。本批实测:`400 invalid_request_error: \`temperature\` is deprecated for this model.`;`top_p` 同。闸写成 `_card_wants_temperature()`,**只对不接受该参数的模型生效**——传 claude-haiku-4-5 时仍发 `temperature=0.0`,与冻结件逐字节同。批 36-B 已在读者侧确认同一 API 行为 |
| 3 | `thinking={"type":"disabled"}` | 见下方"必须照实读的一条" |

**第 3 条必须照实读**:claude-sonnet-5 默认开自适应思考,而 `max_tokens`
同时封顶「思考 + 可见文本」。用**默认设定**实跑一条链(`build_v47s_smoke.log`):
首次调用在 `max_tokens=16000` 上被截断 → `messages.parse` 解析失败 →
`_catalog()` 触发对半分批,**同一条链被拆成两次互不可见的抽取**,与 v45 的
「一链一次调用」不同构;而且被截断那次的 token 白烧却**不进 usage 统计**
(实测该链 54 卡、logged out=25,450,真实 out ≈ 41,000)。

关掉思考后:一链一次调用、`stop_reason=end_turn`、`max_tokens` 保持 16000 不变。
**这同时让写入侧调用与 v45 同构** —— v45 的 claude-haiku-4-5 不配
`budget_tokens` 本就零思考,故两店都是"零思考抽取,只有模型不同"。

**代价照实记:本批没有测「sonnet-5 + 开思考」的抽取上限。** 预算 $10 封顶,
默认设定实测约 $0.26/链 × 36 ≈ $9.4,加读者必超顶。这是本批最大的未覆盖格。

---

## 三、主表(全部限制在同 140 题)

| 臂 | 读者 | n | acc | change_count | count_before | first_vs_last | longest_tenure | in tok | out tok | 中位延迟 s | $/题 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **smoc(v47s,sonnet-5 建店)** | haiku-4-5 | 140 | **92.9%** | 88.9 | 86.1 | 100.0 | 96.9 | 2,644 | 465 | 5.46 | **$0.00497** |
| **smoc(v47s,sonnet-5 建店)** | sonnet-5 | 140 | **92.1%** | 86.1 | 94.4 | 97.2 | 90.6 | 3,465 | 772 | 7.29 | $0.01465 |
| smoc(v45,haiku 建店) | haiku-4-5 | 140 | 91.4% | 86.1 | 86.1 | 100.0 | 93.8 | 2,841 | 467 | 4.79 | $0.00518 |
| smoc(v45,haiku 建店) | sonnet-5 | 140 | 90.7% | 83.3 | 88.9 | 100.0 | 90.6 | 3,713 | 726 | 7.13 | $0.01469 |
| plainctx(全文,mt800) | sonnet-5 | 140 | 87.9% | 94.4 | 94.4 | 94.4 | 65.6 | 18,549 | 444 | 5.01 | $0.04154 |
| **plainctx(全文,截断校正 mt4000)** | sonnet-5 | 140 | **97.1%** | 100.0 | 97.2 | 100.0 | 90.6 | 18,549 | 469 | 4.88 | $0.04179 |
| plainctx(全文,mt800) | haiku-4-5 | 140 | 70.0% | 52.8 | 75.0 | 91.7 | 59.4 | 13,570 | 199 | 2.94 | $0.01456 |

四条对照臂的数字与批 36 / 36-B 归档**逐字复现**(91.4 / 90.7 / 87.9 / 70.0),
说明记分口径没有漂。

**成本读法**:换更强的抽取器**没有让读取侧变贵,反而变便宜**——
v47s 的账目比 v45 短(读者 in tok 2,841→2,644 / 3,713→3,465,−7%),
因为 sonnet-5 建的卡少 13%(同 36 链 1,743 vs 2,003 条)。
smoc(v47s)@haiku 是全表最便宜的臂($0.00497/题),
是 plainctx@sonnet-5 的 **1/8.4**,准确率 92.9% vs 97.1%。
写入侧的一次性代价另计:sonnet-5 建这 36 链 $4.83,haiku 建同 36 链 $2.12
(两家单价不同,金额不可直接相减比模型贵贱)。

---

## 四、配对比较(McNemar 精确二项符号检验,140 题)

**预注册的三条**

```
A=smoc_v47s@haiku    92.9%  B=smoc_v45@haiku    91.4%  Δ +1.43pp  A对B错10 / B对A错 8  p=0.8145
A=smoc_v47s@sonnet5  92.1%  B=smoc_v45@sonnet5  90.7%  Δ +1.43pp  A对B错11 / B对A错 9  p=0.8238
A=smoc_v47s@sonnet5  92.1%  B=plainctx@sonnet5  97.1%  Δ −5.00pp  A对B错 2 / B对A错 9  p=0.06543
```

**佐证的四条**

```
A=smoc_v47s@sonnet5  92.1%  B=smoc_v47s@haiku   92.9%  Δ −0.71pp  A对B错 6 / B对A错 7  p=1
A=smoc_v47s@haiku    92.9%  B=plainctx@sonnet5  97.1%  Δ −4.29pp  A对B错 4 / B对A错10  p=0.1796
A=smoc_v47s@sonnet5  92.1%  B=plainctx@sonnet5 mt800 87.9% Δ +4.29pp A对B错14 / B对A错 8 p=0.2863
A=smoc_v45@haiku     91.4%  B=smoc_v45@sonnet5  90.7%  Δ +0.71pp  A对B错 7 / B对A错 6  p=1
```

**读者不敏感性没变**:v47s 上换读者是 −0.71pp(p=1.00),
与 v45 上的 −0.71pp 一模一样。**把写入侧换强,并没有让账目臂"吃到读者升级的红利"**
——这条批 36-B 的观察在新店上原样复现。

---

## 五、逐链视图:v45 在两个读者下都输给 plainctx 的链,v47s 修好了吗?

判据:该链上存在题目,在 haiku 与 sonnet-5 **两个读者下** v45 都答错、
而 plainctx(校正)答对。符合的链 **3/36**。

| 链 | v45 两读者皆负的题 | v47s@haiku 修好 | v47s@sonnet5 修好 | v47s 新弄坏(任一读者) |
|---|---|---|---|---|
| wikiP54001-Q16225986 | 3(cb, cc, lt) | 3 | 3 | 0 |
| wikiP551002-Q107297 | 1(cc) | 1 | 1 | 0 |
| wikiP551003-Q20512700 | 2(cc, lt) | 2 | 2 | 0 |
| **合计** | **6** | **6** | **6** | **0** |

**6/6 全修好,0 新弄坏。** 这三条链正是 v45 有漏行的链
(如 wikiP54001 v45 漏 1 行金标 + 混进 1 条 `team_size` 干扰行,
v47s 4/0/0/0 干净命中)。**在"写入侧真的漏了"这一类失败上,
换强抽取器是完全有效的干预。**

但全局只 +1.43pp:因为 v45 只有 3 条链属于这一类,而 v47s 自己在**别的**
7 条链上引入了新的失败类型(下一节)。

---

## 六、写入侧诊断:编译账目 vs 金标链

口径:按 `repro_batch3.render_card_ledger` 的**同一套规则**取每条卡的日期
(`stated_date`,空则回落到来源 memory 的会话日期),再与语料
`chain[*].{value,date}` 做 1-1 匹配。
值匹配用归一后的相等或整词包含(刻意放宽:sonnet-5 会把 employer+job_title
合成 `faculty member at Tsinghua University`,严格相等会把它误记成"漏行")。

| 店 | 抽取器 | 金标行 | 精确命中 | 日期偏 | **漏行** | 多出 | 卡片总数 | 完美链 |
|---|---|---|---|---|---|---|---|---|
| v45 | claude-haiku-4-5 | 133 | 122(**91.7%**) | 0 | **11** | 13 | 2,003 | 31/36 |
| **v47s** | **claude-sonnet-5** | 133 | **133(100.0%)** | 0 | **0** | **4** | 1,743 | **36/36** |

**这是本批最硬的一个数字**:漏行 11 → 0,多出 13 → 4,卡片总数还少 13%。
36 条链**全部**完美复现金标链。11/36 条链两店不同,逐链表见
`results/b38_score_out.txt` §4。

---

## 七、为什么保真度 100% 却只换来 +1.43pp:两条新的写入侧退化

**以下为事后发现,不是预注册假设,须按探索性结论对待。**

### 7.1 槽位名碎片化(主因)

金标一个属性的取值,落到了**多于一个** `slot` 名下。账目渲染是逐行
`日期 | slot: value`,读者被问"我的 position 换过几次"时只数其中一条车道。

| 链 | 金标行 | v45 的 slot 名 | v47s 的 slot 名 |
|---|---|---|---|
| wikiP39000-Q4976518 | 3 | political_position | committee_membership, occupation_role |
| wikiP39017-Q24568849 | 5 | position | civic_role, parliament_membership |
| wikiP39023-Q18527003 | 5 | political_position | parliament_membership, public_office |
| wikiP39033-Q5331705 | 6 | political_position | civic_appointment, parliament_membership |
| wikiP39037-Q3525068 | 4 | occupation | occupation, parliament_membership |
| wikiP39039-Q11801709 | 8 | parliament_membership, position | civic_office, parliament_membership |
| wikiP551000-Q19845625 | 3 | europe_trip_destinations, residence_country | residence_country, upcoming_trip |

**金标取值被拆到 >1 个 slot 名的链:v45 2/36,v47s 7/36。**
**更强的抽取器用了语义更精确的槽位名,于是碎得更厉害。**

按碎片化切开看(**控制组才是关键**):

| 子集 | n | v47s@sonnet5 | v47s@haiku | v45@sonnet5 | v45@haiku | plainctx@sonnet5 |
|---|---|---|---|---|---|---|
| v47s 碎片化的 7 链 | 26 | **69.2%** | 88.5% | 88.5% | 88.5% | 92.3% |
| v47s 单槽位的 29 链 | 114 | **97.4%** | 93.9% | 91.2% | 92.1% | 98.2% |

```
单槽位 114 题:smoc_v47s@sonnet5 vs plainctx@sonnet5  翻转 1 正 / 2 负  p=1.00   ← 打平
碎片化  26 题:smoc_v47s@sonnet5 vs plainctx@sonnet5  翻转 1 正 / 7 负  p=0.0703
```

**混杂检查**:碎片化的链确实更长(金标均 4.9 行 vs 3.4 行),
但 plainctx 在**同样这 26 题**上拿 92.3%、v45@sonnet-5 拿 88.5% ——
所以这个子集**不是本质上答不了**,是**专门对 v47s 的账目难**。
碎片化是原因,链长不是。

### 7.2 日期粒度丢失(次因)

金标部分行带日精度(如 `1857-03-01`),卡片的 `stated_date` 可能只写到年。
按各店实际命中的金标行统计:

- **v45**:2 / 122 行丢日精度(1.6%)
- **v47s**:**24 / 133 行丢日精度(18.0%)**

这条直接打死 `wikiP551005-Q42324799_v2lt`:v45 写 `1857-03-01`,v47s 写 `1857`,
于是 Buddenbrookhaus(1835→1846)与 Amsterdam(1846→1857)在年粒度上
**并列 11 年**,两个读者都选错。金标是 Amsterdam,它只赢在那个月份上。

### 7.3 两个读者都还错的 4 题,全部由上面两条解释

```
wikiP39033_v2cc  [change_count]   gold=5  两读者答 3   v45 两读者都对  ← 【v47s 退化·碎片化】6 个取值拆成 civic_appointment(2)+parliament_membership(4),只数了后者 → 4 值 = 3 次变更
wikiP39039_v2cc  [change_count]   gold=7  两读者答 6   v45@haiku 对    ← 【v47s 退化·碎片化】8 个取值拆成 civic_office(1)+parliament_membership(7),只数了后者 → 7 值 = 6 次变更
wikiP551005_v2lt [longest_tenure] gold=Amsterdam      v45 两读者都对  ← 【v47s 退化·日期粒度】见 §7.2
wikiP54020_v2cb  [count_before]   gold=6  两读者答 5   v45@haiku 也错  ← 【非 v47s 退化】两店共有的既存失败:金标日期是 `2024-00-00`,账目渲染成 `2024`,读者无法判断它是否"严格早于 2024-06-29",于是保守排除。v45@sonnet-5 蒙对了这一题
```

**四题全部是 plainctx 答对的题**,即全部落在"账目 vs 全文"的差距里;
但**只有前三题是本批引入的退化**,第四题是 v45 也有的既存缺陷
(且它同样是日期粒度问题,只是发生在**金标侧**的年精度上)。

### 7.4 碎片化归因的直接证据

v47s@sonnet-5 在碎片化子集(26 题)上答错 8 题。这 8 题里:

- **7 题 v45@sonnet-5 是答对的**(同一读者、同一题、同一语料,只换了店);
- **7 题 plainctx@sonnet-5 是答对的**。

即这 8 处失败**几乎全部**是"v47s 这一店特有"的,不是题难、不是读者弱。
这是本批把"碎片化 ⇒ 失分"从相关性推到因果的最直接一条。

---

## 八、成本

| 项 | 值 |
|---|---|
| 建店(claude-sonnet-5,38 次调用含返工) | in 979,435 / out 338,575 tok = **$5.35** |
| 其中:默认设定冒烟(被截断,已丢弃) | $0.31 记账 + 约 $0.20 未计入 usage 的白烧 |
| 其中:一条链因 529 过载被碎片化,已删档重建 | $0.10 |
| 读者 smoc_v47s@haiku-4-5(140 题) | in 370,201 / out 65,168 = **$0.70** |
| 读者 smoc_v47s@sonnet-5(140 题) | in 485,116 / out 108,024 = **$2.05** |
| **本批合计(建店 + 读者,判官另计)** | **≈ $8.3**(封顶 $10) |

逐链建店:in 25,775 / out 8,910 tok = **$0.141/链**(sonnet-5,零思考)。

---

## 九、结论与下一步

1. **写入侧确实是账目的天花板,但瓶颈被定位错了。** 之前假定瓶颈是
   "抽取器不够强 → 漏事实";实测是抽取器一换就把漏行清零(11→0),
   端到端却只 +1.43pp(n.s.)。真正顶住天花板的是**槽位名与日期的规范性**,
   这是**契约/schema 问题,不是模型能力问题**。
2. **在规范没被打破的 29 条链上,QVF 账目与全文直读统计打平**
   (97.4% vs 98.2%,p=1.00),而单题成本是后者的 1/2.9(sonnet-5 读者)
   或 1/8.4(haiku 读者)。这是本批最值得进正文的一句,
   但**必须标注它是事后子集**。
3. **可直接动手的两条修复**(都不需要更强的模型):
   - 槽位归一:批 33-A §8 早就写过"建卡器应把 `slot_class` / `owner` 写回"
     (`QVF_CARD_KEYS=1`),v43/v44/v45/v45g/v47s 五代店全缺这两个字段。
     碎片化正是缺 `slot_class` 的直接后果——有闭集 `slot_class` 时,
     `civic_office` 与 `parliament_membership` 会归到同一个类。
     **这条修复的价值本批第一次有了量化上界:碎片化 26 题里的 8 处失分,
     其中 7 处在 v45(未碎片化)上本来是对的。**
   - 日期粒度:`QVF_DATE_STRICT` / `QVF_CARD_ABS_DATE` 两个既有旗标都碰这块,
     但本批(全默认)没开。24/133 行丢日精度是新测出的量。
4. **未验证 / 未覆盖**(照实列):
   - **sonnet-5 + 开思考的抽取上限没测**(预算原因,见 §二第 3 条)。
     本批只能说"零思考的 sonnet-5 抽取器";开思考是否还能再抬,未知。
   - 事后子集分析 **n=26 / n=114**,非预注册,无多重比较校正。
   - 只跑了 36 链 / 140 题(v45 是 144 链 / 576 题的店);
     v47s 的 144 链全量店没建。
   - 判官(ClaudeJudge)非确定性是既有噪声源,本批未复判。
   - **haiku 读者有 1 题被 `max_tokens=800` 截断**
     (`wikiP551009-Q5321987_v2cb`,`stop_reason=max_tokens`,判错)。
     未做批 36 式的截断校正重跑;校正后 v47s@haiku 至多从 92.9% 到 93.6%,
     不改任何一条结论(所有比较本就不显著)。对照店 `b33A_smoc_v45.jsonl`
     **没有落 `stop_reason` 字段**,故 v45 侧的截断率无法核对 —— 这是
     两侧口径的一处不对称,照实记。sonnet-5 读者(mt=4000)0 题截断。
   - v45 的**逐链** haiku 建店成本没有归档(批 33-A 只留 144 链分片日志),
     故 §八的两店金额是"同 36 链的卡片文件 usage 字段"口径,不是重建实测。
   - `QVF_CARD_KEYS=1` 是否真能消掉碎片化,本批**没有实测**,只是机制推断。

### 建议的下一批(最小实验)

在**同 36 链**上再建一店 `wt_cards_v47sk`:抽取器仍 claude-sonnet-5,
只加 `QVF_CARD_KEYS=1`(写回 `slot_class`/`owner`)与 `QVF_DATE_STRICT=1`。
预算约 $5 建店 + $2.8 读者。判据:碎片化链数从 7 降到多少、
碎片化 26 题的准确率从 69.2% 升到多少、以及 140 题总分能否越过 95%。
这是**唯一**能把"契约问题 vs 模型问题"这条分界轴钉死的一次跑。

---

## 十、精确命令(可重放)

```bash
# 0) 建店(4 分片并行;v45 全程只读)
for i in 0 1 2 3; do
  QVF_CARD_OWNER_GATE=0 QVF_CARD_MODEL=claude-sonnet-5 QVF_CARD_THINKING=off \
  QVF_CARD_TRACE=1 PYTHONUTF8=1 nohup python -u scripts/wt_qvf_prototype_b38.py \
    --phase write --data data/wikistate_full_ALL_v24.json \
    --cards-dir results/wt_cards_v47s --uids "$(cat scratchpad/b38/shard$i.txt)" &
done

# 1) 读店闸:36 文件齐 且 5 分钟无写入
until [ "$(find results/wt_cards_v47s -name '*.json' -newermt '-300 seconds' | wc -l)" -eq 0 ]; do sleep 30; done

# 2) 两个读者(批 36-B 原件,零改动)
PYTHONUTF8=1 python -u scripts/lb_reader_arm_b36b.py --reader anthropic:claude-haiku-4-5 \
  --arm smoc --cards-dir results/wt_cards_v47s --max-tokens 800 --workers 4 --budget 30 \
  --data data/wikistate_full_ALL_v24.json --questions results/b35_questions_sample36.jsonl \
  --out results/b38_smoc_v47s_haiku-4-5.jsonl
PYTHONUTF8=1 python -u scripts/lb_reader_arm_b36b.py --reader anthropic:claude-sonnet-5 \
  --arm smoc --cards-dir results/wt_cards_v47s --max-tokens 4000 --workers 4 --budget 30 \
  --data data/wikistate_full_ALL_v24.json --questions results/b35_questions_sample36.jsonl \
  --out results/b38_smoc_v47s_sonnet-5.jsonl

# 3) 记分与溯源(零 API)
PYTHONUTF8=1 python scripts/b38_score.py      > results/b38_score_out.txt
PYTHONUTF8=1 python scripts/b38_provenance.py > results/b38_provenance.txt
```

**本批未做**:任何 git add / commit / push;未改任何冻结件
(`scripts/wt_qvf_prototype.py` 与 `scripts/lb_reader_arm_b36b.py`
的 sha256 见 `results/b38_provenance.txt`);`results/wt_cards_v45`
与 `v45g` 全程只读。
