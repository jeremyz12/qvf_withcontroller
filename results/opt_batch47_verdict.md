# 批 47 判词 — 评审意见的四项修复:精简 schema、两阶段抽取、语义蕴含校验、值规范化

来源:Notion 页《WikiState Chain》六条评审意见,核对报告见 `docs/notion_review_response_20260904.md`。本批把其中"能修"的四项做成建卡器旗标或派生店,并给出判据。全部产物在新目录,源店未改(店冻结纪律);派生店带 `derived_from` 与源目录 sha256。

## 0. 判决(先判决,后数字)

- **精简 schema(去 claim / 关系 / 种类字段)被证实无损且省 token。** 36 链 Sonnet 重建 v50s:金标行 133/133,车道多出行 4 → 2,编译上限 96.4 → 97.1(140 题),每店输出 token 8,262 → 5,513(−33%),每卡字符 504 → 330(−35%)。
- **两阶段抽取(嵌入定位 → 强抽取)被证实:在 WikiState 上无损、成本降一个量级。** Stage 1 用 text-embedding-3-small 对四个槽位类各取 top-8 轮次,542 条金标锚句召回 100%,只保留 11.7% 的轮次;Stage 2 只抽候选轮次,v50s2 金标行 133/133,多出行 1,编译上限 98.6%(138/140,四个店里最高),每店输入 25,787 → 2,496 token(−90%),输出 → 1,846(−78%),36 链建店 $0.84 对 $3.84。代价:每店卡片 49.8 → 17.0,非金标槽位(习惯、设备、家庭)的卡基本不再抽,这对 WikiState 的四类问题无影响,对通用记忆是覆盖损失,需按用途选择。
- **语义蕴含校验替换关键词规则被证实,且零误伤的写法找到了。** 144 链 v48 店只审四个金标槽位类的 925 张卡(haiku,$1.08):按断言类型丢 plan / task / other_person / hypothetical / ended 并丢 restate,金标行 521/542 不变(0 处 hit→miss),车道多出行 40 → 28,编译上限 91.4 → 93.8(560 题);同店关键词规则 92.7、多出行 36。若同时要求 entailed=true 会误删 1 条金标行(TotalEnergies 车队被判成雇主,是校验器用了外部知识),所以最终规则只看断言类型。
- **值规范化被证实无害、对读者无收益。** v48f 派生店 v48fc 改动 82/7,290 个值;haiku 读者 560 题 90.00,对 v48f 两轮 89.82 / 90.18,配对 McNemar p = 1.0;受影响 42 链 166 题上 90.4 对 89.8 / 91.0。longest_tenure 89.8 → 90.6,其余题型不变。它的作用是账目更干净,不是分数。
- **建卡器修复两个副作用。** sonnet-5 不接受 temperature 参数(400),v49 建卡必须 QVF_CARD_TEMP0=0;sonnet-5 默认开思考,输出 token 从 5.1K 涨到 15.9K 并逼近 16K 上限,v49 新增 QVF_CARD_THINKING=off。

## 1. 建卡器改动(`scripts/wt_qvf_prototype_v49.py`,旗标默认全关,关时逐字节不变;`scripts/test_card_schema_v49.py` 3/3 通过)

| 旗标 | 作用 | 默认 |
|---|---|---|
| QVF_CARD_SLIM=1 | SlimRecord 七字段契约(record_id、source_memory_id、source_span、entity、slot、value、stated_date);提示词由 CATALOG_PROMPT 机械去掉规则 3 派生 | 0 |
| QVF_CARD_VALNORM=1 | 落盘前 canon_value():employer/team 去尾部括注与公司后缀、residence 去尾部括注、去前置 the;原值存 value_raw | 0 |
| QVF_CARD_STAGE1_K=k | Stage 1 嵌入定位:四类各 top-k 用户轮次并集交给抽取器 | 0 |
| QVF_CARD_THINKING=off | 建卡调用传 thinking=disabled | 未设 |
| --phase valnorm --src --dst | 对既有店做值规范化派生(零 LLM,带溯源) | — |

## 2. 精简 schema 与两阶段(36 链,140 题,抽取器 claude-sonnet-5,thinking off,TEMP0=0)

| 店 | 配置 | 卡/店 | 字符/卡 | 建店 in/out per store | 金标行 | 多出行 | 编译上限 | 36 链成本 |
|---|---|---|---|---|---|---|---|---|
| v47s(批 38) | 完整 schema | 48.4 | 504 | 25,787 / 8,262 | 133/133 | 4 | 135/140 = 96.4% | — |
| v47skf(批 38e) | 完整 + 关键词过滤 | 39.9 | 556 | 25,787 / 8,742 | 131/133 | 2 | 137/140 = 97.9% | — |
| **v50s** | SLIM | 49.8 | 330 | 25,787 / 5,513 | 133/133 | 2 | 136/140 = 97.1% | $3.84 |
| **v50s2** | SLIM + STAGE1_K=8 | 17.0 | 323 | 2,496 / 1,846 | 133/133 | 1 | 138/140 = 98.6% | $0.84 |

Stage 1 定位器(`scripts/b47_embed_localizer.py`,144 店 15,114 个用户轮次,`results/b47_embed_localizer.json`):

| 每类 top-k | 四类并集召回(542 锚句) | 保留轮次 | 只用金标类查询的召回 |
|---|---|---|---|
| 3 | 87.8% | 6.3% | 77.1% |
| 5 | 97.2% | 10.4% | 94.1% |
| **8** | **100.0%** | **17.2%** | 100.0% |
| 12 | 100.0% | 26.0% | 100.0% |

对照:LoCoMo 正则定位器召回 12.5%,加 20 条线索后 64.9%(`docs/notion_review_response_20260904.md` §3.3)。

## 3. 语义蕴含校验(144 链,v48 店,560 题;`scripts/b47_entail_verify.py --lane-only`,判定模型 claude-haiku-4-5,925 张车道卡,836K 入 / 49K 出 token,$1.08)

| 过滤规则 | 保留卡 | 金标行 | 新增漏行 | 车道多出行 | 编译上限 |
|---|---|---|---|---|---|
| v48 不过滤 | 6,973 | 521/542 | — | 40 | 512/560 = 91.4% |
| 关键词规则(批 38e) | 6,062 | 521/542 | 0 | 36 | 519/560 = 92.7% |
| 蕴含:按类型丢 plan/task/other/hypo/ended | 6,884 | 521/542 | 0 | 35 | 519/560 = 92.7% |
| **蕴含:按类型再丢 restate(采用)** | 6,731 | 521/542 | 0 | 28 | **525/560 = 93.8%** |
| 蕴含:另要求 entailed=true | 6,711 | 520/542 | 1 | 28 | 524/560 = 93.6% |
| 蕴含 + 关键词同时保留 | 5,959 | 520/542 | 1 | 31 | 523/560 = 93.4% |

标签分布(车道卡):start 674、restate 153、task 50、other_person 20、plan 17、unclear 9、hypothetical 2;entailed=false 117。误判样例:"TotalEnergies is my new team as of today" 被判 entailed=false("是雇主不是车队"),这是校验器用了外部知识,违反提示词;按类型过滤不受此影响。派生店 `results/wt_cards_v48ef`(采用规则)、`results/wt_cards_v48e_ent`(全部卡 + 标签)、`results/wt_cards_v48e`(旧规则,含 entailed 要求,留作对照)。

## 4. 值规范化(144 链,560 题,haiku-4.5 读者,`results/b47_smoc_v48fc_haiku_run1.jsonl`,$2.90)

| 店 | 准确率 | change_count | count_before | first_vs_last | longest_tenure |
|---|---|---|---|---|---|
| v48f run1(批 46d) | 89.82 | 86.1 | 86.8 | 96.5 | 89.8 |
| v48f run2(批 46d) | 90.18 | 86.8 | 87.5 | 96.5 | 89.8 |
| **v48fc(值规范化)** | 90.00 | 86.1 | 86.8 | 96.5 | 90.6 |

配对:对 run1 +0.18(4 对 3,p = 1.0),对 run2 −0.18(3 对 4,p = 1.0);受影响 42 链 166 题:90.4 对 89.8 / 91.0。读者输入 2,750 token/题,撞上限 1 题。

## 5. 成本

| 项 | $ |
|---|---|
| 蕴含校验(925 卡,haiku) | 1.08 |
| 嵌入(两次 15K 轮次 + 查询) | ≈0.06 |
| v50s 建店(36 链 Sonnet) | 3.84 |
| v50s2 建店(36 链 Sonnet,两阶段) | 0.84 |
| v48fc 读者(560 题 haiku) | 2.90 |
| 报废:思考未关的 1 店 + 冒烟测试 | ≈0.26 |
| **合计** | **≈ 8.98** |

## 6. 已知偏离与未核实

- 蕴含校验只审了四个金标槽位类的卡(925/6,973),其余卡标 unjudged 并保留;全店审计约 $8,未做。
- v50s / v50s2 只在 36 链上,与 v47s 同抽样;144 链全量重建未做(约 $15 / $3.4)。
- 两阶段的 v50s2 编译上限 98.6% 高于 v50s 97.1%,差 2 题,不宣称显著;它比较的是同一抽取器在"少看无关轮次"下的行为,机制解释是干扰减少,未单独消融。
- 读者层面:所有写侧修复都沿用批 46d 的结论——账目更干净不等于读者分数上升;v50s / v50s2 没有跑读者。
- 值规范化的 82 处改动全部是 employer/team/residence 的括注与公司后缀;position 未动。
- 评审页首截图未读取。

## 7. 精确命令(可重放)

```bash
# 蕴含校验(车道卡)
PYTHONUTF8=1 python scripts/b47_entail_verify.py --src results/wt_cards_v48 --dst results/wt_cards_v48e --lane-only --workers 8 --tag b47
PYTHONUTF8=1 python scripts/b47_score.py --part entail
# Stage 1 定位器召回
PYTHONUTF8=1 python scripts/b47_embed_localizer.py
# 精简 schema / 两阶段(36 链)
QVF_CARD_SLIM=1 QVF_CARD_MODEL=claude-sonnet-5 QVF_CARD_TEMP0=0 QVF_CARD_THINKING=off PYTHONUTF8=1 python -u scripts/wt_qvf_prototype_v49.py --phase write --data data/wikistate_full_ALL_v24.json --cards-dir results/wt_cards_v50s --uids "$(cat results/b47_uids36.txt)"
QVF_CARD_SLIM=1 QVF_CARD_STAGE1_K=8 QVF_CARD_MODEL=claude-sonnet-5 QVF_CARD_TEMP0=0 QVF_CARD_THINKING=off PYTHONUTF8=1 python -u scripts/wt_qvf_prototype_v49.py --phase write --data data/wikistate_full_ALL_v24.json --cards-dir results/wt_cards_v50s2 --uids "$(cat results/b47_uids36.txt)"
PYTHONUTF8=1 python scripts/b47_score.py --part slim
# 值规范化派生店 + 读者
PYTHONUTF8=1 python scripts/wt_qvf_prototype_v49.py --phase valnorm --src results/wt_cards_v48f --dst results/wt_cards_v48fc
PYTHONUTF8=1 python -u scripts/lb_reader_arm_b36b.py --reader anthropic:claude-haiku-4-5 --arm smoc --questions data/wsc_s5_v25.jsonl --data data/wikistate_full_ALL_v24.json --cards-dir results/wt_cards_v48fc --out results/b47_smoc_v48fc_haiku_run1.jsonl --max-tokens 800 --workers 4 --budget 40
PYTHONUTF8=1 python scripts/b47_score.py --part valnorm
```
