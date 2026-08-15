# 改写题集编译重测:模板膨胀量测量(2026-08-15)

## 判决(预注册线:膨胀量 = 原题一致率 − 改写一致率 > 8pp 则须标注模板膨胀)

**猜想被否定:三方均无模板膨胀。** haiku 膨胀量 0.0pp、qwen3:8b +0.09pp、
qwen3:4b −0.27pp(改写反而略高),全部远低于 8pp 预注册线。**现有编译成绩
无须标注模板膨胀。**

**haiku 与本地模型不同型也不掉落:** 三方在改写集上都基本不掉。存在的少量
失败全部集中在 join_at_change 一个算子上,且 qwen3:4b 的改写失败题与其
阶段 0 原题失败题是同一题族(wikiM003/wikiM019 的 s6b 系,slot/slot2 锚向
互换同款错误)——这是该模型在最难算子上的既有能力短板的随机摆动,不是
改写诱发的模板失配。结论:没有"模型在做模板匹配"的证据,编译能力对句面
形变鲁棒。

## 总表(改写集 n=1107 = 369 题 × 3 改写;原题对照桥引阶段 0 已测数字)

| 模型 | 原题一致率(阶段 0) | 改写一致率 | 改写执行等价率 | 膨胀量(原−改写) |
|---|---|---|---|---|
| haiku(原编译线) | 369/369 = 100%(定义性,见口径注) | **1107/1107 = 100.0%** | 1107/1107 = 100.0% | **0.00pp** |
| qwen3:8b | 369/369 = 100% | **1106/1107 = 99.91%** | 1106/1107 = 99.91% | **+0.09pp** |
| qwen3:4b | 365/369 = 98.92% | **1098/1107 = 99.19%** | 1098/1107 = 99.19% | **−0.27pp** |

三方 compile_ok 均 1107/1107(无编译失败);计划一致的行执行等价也全数一致
(exec_equal = plan_agree,无"计划不同但执行撞同"或"计划同判但执行分歧")。

## 分算子(改写一致 / 总;括号内原题对照)

| 算子 | haiku | qwen3:8b | qwen3:4b |
|---|---|---|---|
| first_last | 222/222 | 222/222(74/74) | 222/222(74/74) |
| count_before | 219/219 | 219/219(73/73) | 219/219(73/73) |
| longest | 207/207 | 207/207(69/69) | 207/207(69/69) |
| count_changes | 198/198 | 198/198(66/66) | 198/198(66/66) |
| tag_trend | 150/150 | 150/150(50/50) | 150/150(50/50) |
| join_at_change | 63/63 | **62/63 = 98.4%**(21/21,−1.6pp) | **54/63 = 85.7%**(17/21 = 81.0%,+4.8pp) |
| tag_filter | 48/48 | 48/48(16/16) | 48/48(16/16) |

最差三算子:唯一有掉幅的算子是 join_at_change(8b −1.6pp);其余六算子
三方全对、零掉幅。4b 的 join_at_change 改写成绩(85.7%)反而高于其原题
成绩(81.0%)。

## 典型失败例(全部 10 例均为 join_at_change)

1. **qwen3:8b 唯一失败(op 误判)** wikiM019-Q13205835_s6b4#p3:
   "(Today is 1955-01-01.) I'd like to know what my employer was back when
   I moved to Samarkand." → 编译成 `point_in_time(slot=employer,
   date=1955-01-01)`,把"back when I moved…"从句误读为查询今日日期,
   丢失 join 锚。原题("When I moved to Samarkand, what was my employer at
   that time?")该模型编译正确;间接语域+从句后置的组合触发误判。
2. **qwen3:4b 锚向互换(9 例同款)** 例 wikiM003-Q106386024_s6b1#p1:
   "Who was I working for when I moved to Mexico City?" → `join_at_change`
   op 正确,但 slot=employer / slot2=residence(参考:slot=residence /
   slot2=employer),把被问属性当锚属性。执行输出随之不同(exec_equal
   False),非别名等价。
3. **qwen3:4b 从句前置同款** wikiM019-Q13205835_s6b3#p1:"At the time I
   relocated to Arkhangelsk, who was my employer?" → 同上 slot/slot2 互换。

qwen3:4b 逐题视角:9 例失败分布在 5 题(每题 3 改写中错 1-2 份),其中 4 题
(wikiM003_s6b2、wikiM019_s6b2/3/4)正是其阶段 0 原题失败的同 4 题,新增
wikiM003_s6b1 一题;同题族、同错误方向(residence↔employer 互换)。

## 口径与成本

- 参考计划按 question_id 连回原 369 参考集(改写不变量保证参考计划不变);
  plans_agree / SLOT_ALIASES / _norm 归一与阶段 0 逐字节同函数(import
  scripts/eval_local_compiler,未复制)。
- 执行等价:同 recs/mem_dates 双执行,双方均以**改写句**为 question 文本
  (唯一变量是计划本身),纯代码零 LLM,与阶段 0 同口径。
- haiku 口径注:参考计划即 haiku 在原题上的判对编译输出,故其"原题一致率
  100%"是定义性对照桥;有信息量的是改写 100%——直接测得原编译线对句面
  形变零敏感。参考集只含 haiku 原判对的 369 题,膨胀量测量范围限于
  haiku 可解题。
- 本地线:ollama,think:false、format=json、temperature 0、重试 ≤3、
  NUM_PREDICT 512,与阶段 0 完全一致;system 逐字节 import COMPILE_PROMPT。
- haiku 线:import complex_query_arm.compile_plan(冻结,未改),
  messages.parse + system ephemeral cache;先 20 条冒烟(20/20 对,27s)
  再放全量。1107 调用,墙钟 1190.6s;tokens_in 2,100,668 / tokens_out
  35,573,费用上界 ≈ $2.28(计费字段未拆缓存读,若缓存命中实际显著更低),
  在 ~$2 预算量级内。
- 本地墙钟:qwen3:8b 2617s,qwen3:4b 2571s(RTX 5090 本地,零 API 成本)。

## 落盘

- 逐题:results/para_compile_haiku_20260815.jsonl、
  results/para_compile_qwen3_8b_20260815.jsonl、
  results/para_compile_qwen3_4b_20260815.jsonl(各带 .meta.json)
- 冒烟:results/para_compile_haiku_smoke.jsonl(20 条,与全量重叠)
- 评测脚本:scripts/eval_paraphrase.py(复用冻结函数,只 import 不改)
- 改写集:results/paraphrase_set_20260815.jsonl(1107 条,生成侧盲性纪律
  与断言见改写集交付记录)
