# 批 38-B 预注册 —— 契约问题还是模型问题?写入侧"规范化"最小实验

**写作时间**:2026-09-03,**在任何建店 / 读者 API 调用之前**落盘。
本文件此后只增不改;实跑结果一律写进 `results/opt_batch38b_verdict.md`。

---

## 一、待验证猜想(承批 38 §九)

批 38 的判决是:**"账目的天花板在写入侧"成立,但瓶颈被定位错了**。
把抽取器从 claude-haiku-4-5 换成 claude-sonnet-5,编译账目对金标链从
122/133 升到 **133/133**(漏行 11→0),端到端却只从 91.4→92.9(haiku 读者)
/ 90.7→92.1(sonnet-5 读者),两条都 n.s.,与全文直读 97.1% 的 −5.0pp
差距没有关上。事后诊断把这笔红利的去向定位到**两条写入侧规范性退化**:

1. **槽位名碎片化**:金标一个属性的取值落到 >1 个 `slot` 名下
   (v45 2/36 链 → v47s **7/36**)。账目渲染逐行 `日期 | slot: value`,
   读者被问"position 换过几次"时只数其中一条车道。
2. **日期粒度丢失**:v47s **24/133** 命中金标行丢日精度(v45 只 2/122)。

在**没有**被这两条打到的 29 条链(114 题)上,v47s@sonnet-5 = 97.4%
vs 全文直读 98.2%,p=1.00 —— 统计打平。

**本批猜想**:上述两条是**契约 / schema 问题,不是模型能力问题**。
在**同一抽取器、同一 36 链**上只补两条规范化,就应当把碎片化与日期粒度
一并压掉,并把端到端分数抬到与全文直读打平的水平。

**这是唯一能把"契约问题 vs 模型问题"这条分界轴钉死的一次跑**:
自变量只有"规范化开关",抽取器、语料、题目、读者、跑批脚本全部不变。

---

## 二、预注册假设(四条,判据在跑之前定死)

| # | 假设 | 判据 | 批 38 实测基线 |
|---|---|---|---|
| H1 | 槽位名碎片化被压掉 | v47sk 碎片化链数 **≤ 2 / 36** | v47s 7/36;v45 2/36 |
| H2 | 碎片化子集的失分被收回 | 批 38 那 **26 道**碎片化题上 v47sk@sonnet-5 **≥ 88%** | v47s@sonnet-5 69.2% |
| H3 | 总分越过 95 且与全文直读打平 | v47sk@sonnet-5 **≥ 95%**,且 vs plainctx mt4000(97.1%)配对 McNemar **不显著**(p ≥ 0.05) | v47s@sonnet-5 92.1%,p=0.065 |
| H4 | 写入侧保真度不被规范化弄坏 | 编译账目 vs 金标 **仍 133/133**(漏行 0、日期偏 0) | v47s 133/133 |

**证否条件写在前面**(避免事后挑判据):

- H1 落在 3–6 之间 = **部分证实**;仍为 7 = **被否定**。
- H2 未过 88% 但显著高于 69.2% = 部分证实;≤ 76.9%(即只修好 ≤2 题)= 被否定。
- H3 只要 acc < 95% 即记 H3 被否定,**哪怕**与 plainctx 的 p 值不显著
  (不显著也可能只是 n=140 的检验力不足,不算证实)。
- H4 只要 missing > 0 或 date_off > 0 即记"规范化引入了新的保真度代价"。

**次要观测量(不设判据,只照实报)**:碎片化链数 v45 / v47s / v47sk 三店
并排;日期粒度丢失行数三店并排;fidelity 的 **extra**(同槽位车道、不对应
任何金标行的账目行)—— 这是本批归一化的**主要风险计量**,见 §四;
v47sk@haiku 的同批数字;两店成对 McNemar;成本。

---

## 三、口径(与批 38 逐字相同,不得漂)

| 项 | 值 |
|---|---|
| 题源 | `results/b35_questions_sample36.jsonl`,140 题 / 36 链 |
| 链集 | `results/b35_sample_uids.txt`(36 uid) |
| 语料 | `data/wikistate_full_ALL_v24.json`(v2.4) |
| 本批店 | `results/wt_cards_v47sk`(**新目录**) |
| 对照店 | `results/wt_cards_v45`、`results/wt_cards_v47s` —— **全程只读**,建店前后各算一次目录 sha256 |
| 抽取器 | `claude-sonnet-5`,不发 temperature,`thinking={"type":"disabled"}`,`max_tokens=16000`,一链一次调用 —— **与批 38 逐项相同** |
| 建卡器 | `scripts/wt_qvf_prototype_b38b.py`(b38 副本 **+172 行纯新增、0 行删改**) |
| 跑批脚本 | `scripts/lb_reader_arm_b36b.py`(**零改动**,与批 36-B / 38 同一文件) |
| 读者 | haiku-4-5 `--max-tokens 800`(命中上限的行按批 36 口径用 4000 重跑,两个数都报);sonnet-5 `--max-tokens 4000` |
| 产物 | `results/b38b_smoc_v47sk_haiku-4-5.jsonl`、`results/b38b_smoc_v47sk_sonnet-5.jsonl` |

**建店前的 v45 / v47s 目录 sha256(已记录,建店后须逐字相同)**

```
results/wt_cards_v45 : 144 文件 / 8,288 记录
                       bcb31a114dc27479326d981bbce9c6d906d7689c00e18b9d4371aeecf55589d4
results/wt_cards_v47s:  36 文件 / 1,743 记录
                       a80ea1f36554abff8964a1d536f911f613bac7e54200cfd9928b7fb946cdb3dd
```

(v45 的值与 `results/b33A_provenance.txt` 2026-09-02 的记录、v47s 的值与
`results/opt_batch38_verdict.md` §一的记录**逐字相同**。)

---

## 四、自变量:两处规范化 —— 与任务书的偏差**逐条照实**

任务书要求"只加 `QVF_CARD_KEYS=1` 与 `QVF_DATE_STRICT=1`"。两个旗标
**都真实存在**,但**实读源码核实后,两个都不足以完成任务书要它们完成的事**。
下面把偏差写在跑之前。

### 4.1 `QVF_CARD_KEYS=1`:开了,但它不归一 `slot` —— 故补一步

- 旗标位置:`scripts/wt_qvf_prototype_b38b.py:44`、`qvf/engine_bridge.py:38`。
  开启后建卡提示词换成 `CATALOG_PROMPT_V4`,`ExtractedRecord` 多出
  `owner` / `slot_class` 两个字段(闭集:position | employer | team |
  residence | device | location | relationship | other:&lt;short-noun&gt;)。
- **但**:smoc 账目渲染器 `scripts/repro_batch3.py:render_card_ledger`
  逐行输出的是 `r.get("slot")`,**不是 `slot_class`**(唯一读 slot_class
  的分支是 `QVF_LEDGER_VIEW=slot|slim`,本批与批 38 一样默认关)。
  所以 **KEYS=1 单开,对读者看到的账目零影响,消不掉碎片化**。
- **本批按任务书授权补的最小步骤**(新旗标 `QVF_CARD_SLOT_CANON=1`,
  抽取后纯代码,零 LLM,只改 `slot` 一个键,原值留 `slot_raw`):

  1. **主判据** = 抽取器自己给的 `slot_class`(靠 KEYS=1 才有)。
     若恰是四个考纲槽类之一 {employer, position, residence, team},
     则 `slot := slot_class`。
  2. **回退判据** = `scripts/b33A_backfill_slot_class.py:classify()`
     的同语义副本(SLOT_ALIASES 子串表,命中多类取最长别名),
     **仅当抽取器压根没给 slot_class(空串)时**才启用;命中四类之一则
     `slot :=` 该类。
  3. 其余一律不动(含 device / location / relationship / other:*)。

- **为什么把 b33A 的表降级为回退,而不是当主判据 —— 实测证据,不是偏好**:
  把 `classify()` 单独施加到 v47s 的槽位名上做过**离线对拍(零 API)**:
  碎片化链 7/36 → 3/36,**但**同车道非金标行(fidelity 的 `extra`)
  从 **4 暴涨到 21**,逐条看全是子串误并 ——
  `family_member`("older son Jack")、`household_member`("Anne")、
  `museum_membership`、`religious_group_membership` 经别名 `member` 并进
  position;`theater_role` / `academic_role` 经 `role` 并进 position;
  `home_office_desk`("new desk, 4 hours to assemble")经 `office`;
  `job_related_news` 经 `job`;`university_application_status` 经
  `university` 并进 employer。这些噪声行**正好灌进 change_count 要数的
  那条车道**,方向上会加重而不是缓解本批要治的病。
  语义闭集 `slot_class` 不会把 "older son Jack" 判成 position。
- **本函数的单元自测实际抓到过一次自己的 bug**:回退判据最初写成"主判据
  不落在四类之内就回退",于是 `family_member`(slot_class=`relationship`)
  仍被别名 `member` 误并进 position。已改成"**只在 slot_class 为空时**
  回退",即抽取器给出的任何有效判断都被尊重。
- **代价照实记**:这等于把归一的正确性押在抽取器的语义判断上。
  本批用 fidelity 的 `extra` 计数来量它,并把三店 `extra` 并排报。

### 4.2 `QVF_DATE_STRICT=1`:开了,但它对写入侧是**零作用** —— 故补一步

- 旗标位置:`scripts/wt_qvf_prototype_b38b.py:130`。但它**只作用于读取侧
  的 `_rec_date()`**(:727)与 `scripts/complex_query_arm` 的同名咽喉点,
  **`write_phase` 里一次都没有被引用**;而 smoc 账目由
  `render_card_ledger` 直接读卡片的 `stated_date`,**根本不经过
  `_rec_date`**。故 DATE_STRICT=1 对本批要治的病零作用。
  **本批仍照任务书把该环境变量设为 1 并记录在建店命令里**,以示未偷偷
  省略;但预期它不产生任何可观测差异 —— 这条会在终判里复核。
- 任务书的备选方案是"当来源 span 里含日精度日期时保住日精度"。
  **离线探针否定了这个诊断**(零 API,`scratchpad/b38b/probe_dates.py`):
  v47s 那 24 条丢精度的行里,**0 条**的 `source_span` 含任何可解析日期。
  它们全是 "as of today I'm officially on the faculty at ..." 这类句式 ——
  日精度不在 span 里,在**来源 memory 的会话日期**里。抽取器把散文里的
  "September 1985" 抄成 `1985-09`,而会话日期是 `1985-09-01`;
  v45 的 haiku 反而更常把 `stated_date` 留空 → 渲染器回落到会话日期 →
  **天然保住了日精度**。
- **本批补的最小规则**(新旗标 `QVF_CARD_DATE_REFINE=1`,抽取后纯代码,
  零 LLM,只改 `stated_date`,原值留 `stated_date_raw`):
  `stated_date` 非空、且是来源会话日期的**分量前缀**(年相同;若已写到月
  则月也须相同;自身尚无日分量;会话日期本身有日分量)时,
  `stated_date := 会话日期`。
  **只细化,绝不改年月,绝不凭空造日期,绝不动空值**(空值仍走渲染器的
  会话日期回落,与冻结行为同)。
- 离线对拍(零 API):该规则在 v47s 上修好 **24/24** 条丢精度行、
  在 v45 上修好 2/2 条,无一条不可修。
- **代价照实记**:全店 1,743 条里有 **376 条(21.6%)** 会被细化,
  其中绝大多数**不在**金标链上 —— 本规则的作用面远大于它被验证的那 24 行,
  未被验证的那部分是本批的一处**已知未知**。

### 4.3 偏差小结(一句话)

> 任务书点名的两个旗标都存在,但**一个只写字段不改渲染键、一个只管读取侧
> 不管写入侧**,单开两个旗标本批会得到一个与 v47s 几乎相同的店。
> 因此按任务书的授权条款,各补了一步**确定性、零 LLM、只改一个键、
> 原值留档**的抽取后规范化。两处补丁均为**纯新增**(+172 行、0 行删改),
> 旗标关时与批 38 副本逐字节等价。

---

## 五、精确命令(可重放)

```bash
# 0) 冒烟(1 链,验证旗标真的生效再烧全量)
QVF_CARD_OWNER_GATE=0 QVF_CARD_MODEL=claude-sonnet-5 QVF_CARD_THINKING=off \
QVF_CARD_KEYS=1 QVF_DATE_STRICT=1 QVF_CARD_SLOT_CANON=1 QVF_CARD_DATE_REFINE=1 \
QVF_CARD_TRACE=1 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype_b38b.py \
  --phase write --data data/wikistate_full_ALL_v24.json \
  --cards-dir results/wt_cards_v47sk_smoke --uids wikiP39033-Q5331705

# 1) 建店(4 分片并行;v45 / v47s 全程只读)
#    QVF_CARD_KEYS / QVF_DATE_STRICT 照任务书设 1;两处补丁旗标另设。

# 2) 读店闸:36 文件齐 且 5 分钟无写入

# 3) 两个读者(scripts/lb_reader_arm_b36b.py,零改动)
#    haiku-4-5 --max-tokens 800 / sonnet-5 --max-tokens 4000

# 4) 记分与溯源(零 API)
#    scripts/b38b_score.py > results/b38b_score_out.txt
```

完整逐字命令在终判 `results/opt_batch38b_verdict.md` §十 归档。

## 六、预算

建店约 $5.0–5.5(KEYS=1 多两个字段 → out token 略涨),读者约 $2.8,
合计约 **$8**,封顶 $10。判官另计。
若冒烟显示单链成本显著高于批 38 的 $0.141/链,先停下重估再决定是否全量。

---

## 七、附录(建店前追记,2026-09-03)—— 冒烟抓到的一处自身 bug

预注册正文写完后、全量建店**之前**,按 §五 第 0 步跑了 1 条链的冒烟
(`wikiP39033-Q5331705`,`results/wt_cards_v47sk_smoke`,一次调用、
`stop_reason=end_turn`、in 26,484 / out 8,623 = **$0.139/链**,与批 38 的
$0.141/链 同量级)。冒烟同时验收两处补丁,并**抓到日期规则的一处自身 bug**:

- **槽位归一按设计工作**:6 条被归一,**6 条全部走主判据 `slot_class`、
  0 条走 b33A 别名回退**。`parliament_membership` 与 `sheriff_position`
  双双并进 `position`(批 38 里这条链正是碎片化的
  `civic_appointment` + `parliament_membership`);
  而同店的 `museum_membership` **没有**被并进 position —— 这正是 b33A
  子串表会犯、语义 slot_class 不犯的那类误并。`slot_class` / `owner`
  两字段覆盖率 50/50 = 100%。
- **日期规则的 bug**:该链的两个会话日期字面就是 `1825-00-00` /
  `1831-00-00`(年精度用**零月零日**编码)。初版规则把 `1825`
  "细化"成 `1825-00-00` —— 那不是升精度,是把干净的年份换成一个非法
  日期串,与本规则"绝不凭空造日期"的自我约束直接冲突。
  **已修**:要求会话日期的月、日分量都是真实历法分量(非 00)才允许细化。
- **修后复核(零 API,拿归档的 `stated_date_raw` 与两个对照店回放)**:
  金标行的修复率不变 —— v47s 仍 **24/24**、v45 仍 2/2;
  而全店作用面从 376/1,743(21.6%)降到 **263/1,743(15.1%)**。
  即修 bug 同时**缩小**了未被验证的作用面,两个方向都变好。
- 冒烟店 `results/wt_cards_v47sk_smoke` 是**用带 bug 的规则建的**,
  故**作废、不进任何统计**,只作为上述 bug 的证据留档。
  正式店 `results/wt_cards_v47sk` 从零重建。

§二 的四条假设与判据**未作任何改动**。
