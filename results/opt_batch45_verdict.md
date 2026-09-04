# 批 45 判决:判官同族偏置排除(gpt-5-mini 复判四臂归档答案)

预注册:results/opt_batch45_prereg.md(先于 scripts/b45_rejudge.py 运行提交)
记分产物:results/b45_score_out.txt(完整表格 + 10 例/臂消歧样本)
逐题产物:results/b45_rejudge_{direct,smoc_v45,smw,smwplain}.jsonl(各 576 行)

## 判决先行

- **H1(逐题一致性每臂 ≥90%):被否定。** direct 臂 88.89%(<90%);
  smoc_v45 97.05%、smw 96.35%、smwplain 95.66% 均通过。H1 整体 FAIL(因
  direct 一臂拖累)。
- **H2(headline 在 gpt 判官下落在克劳德判官 +41.49pp 的 ±5pp 内):被否
  定。** gpt 判官下 smoc_v45 − direct = **+48.61pp**,偏离克劳德判官
  headline **+7.12pp**,超出预注册的 ±5pp 窗口。
- **H3(单臂准确率漂移 ≤5pp):被否定。** direct 臂漂移 **−10.07pp**
  (47.57→37.50);smoc_v45(−2.95pp)、smw(−3.65pp)、smwplain(−3.99pp)
  均 ≤5pp 通过。H3 整体 FAIL(同一臂拖累)。

**关键限定,读三项 FAIL 前必须先看这条:三项假设失手的方向对 QVF 有利,
不是不利。** gpt-5-mini 判官相对克劳德判官,对 direct(最弱基线)明显更
严苛(−10.07pp),对三个 QVF 强臂(smoc_v45/smw/smwplain)只温和更严苛
(−3~−4pp)。净效应是 direct→smoc 的差值从 +41.49pp **扩大**到
+48.61pp,而不是"同族偏袒"担忧所指向的收窄或反转。四臂里没有一个显示
gpt 判官系统性偏向 QVF 的答案;唯一显著漂移的臂(direct)让基线更难看,
QVF 相对优势因此被放大而非制造出来。

**因此本批的判决要分两层说清楚:** 就"判官同族是否人为夸大了 QVF 的领
先幅度"这个原始动机问题——**猜想被否定**,证据方向相反(领先幅度换判官
族后更大而非更小)。就"绝对数字是否对判官族选择免疫"这个更弱、更严格
的预注册问题——**猜想被否定**,H1-H3 三项都没有严格通过,数字本身不是
免检的,direct 臂尤其对判官措辞解读敏感。

## 1. 逐臂准确率(两位判官,同一 576 行)

| arm | claude 判官 | gpt 判官 | delta(gpt−claude) |
|---|---|---|---|
| direct | 47.57 | 37.50 | **−10.07pp** |
| smoc_v45 | 89.06 | 86.11 | −2.95pp |
| smw | 85.59 | 81.94 | −3.65pp |
| smwplain | 53.47 | 49.48 | −3.99pp |

## 2. 逐题一致性 + Cohen's κ

| arm | 一致 | n | 一致率 | κ |
|---|---|---|---|---|
| direct | 512 | 576 | 88.89% | 0.775 |
| smoc_v45 | 559 | 576 | 97.05% | 0.865 |
| smw | 555 | 576 | 96.35% | 0.866 |
| smwplain | 551 | 576 | 95.66% | 0.913 |

κ 全部落在"实质一致"(0.61–0.80)到"近乎完全一致"(0.81–1.00)区间;
direct 臂虽未过 90% 一致率的预注册门槛,κ=0.775 仍属实质一致,不是随机
噪声。

## 3. 分歧方向 + 机制探查(定性读 10 例/臂,完整清单见 b45_score_out.txt §3)

| arm | claude 对 & gpt 错 | claude 错 & gpt 对 |
|---|---|---|
| direct | 61 | 3 |
| smoc_v45 | 17 | 0 |
| smw | 21 | 0 |
| smwplain | 24 | 1 |

分歧几乎全部单向(gpt 更严),且两个臂族的分歧机制不同:

- **direct 臂:** 分歧多数不是数值判断分歧,而是 gpt-5-mini 对答案里的
  **模糊限定语**读得更字面。direct 臂答案常见"看似给出最终数字但夹带
  限定"的句式(如"though I don't have enough information..."、"it
  appears you may have changed again"、"I can confirm at least 2 changes
  so far")。克劳德判官倾向抓住最终陈述的数字判对;gpt-5-mini 倾向因限
  定语判"未确定作答",或因答案里额外提及的日期与题目时间窗矛盾而判错。
- **smoc_v45/smw/smwplain 臂:** 分歧集中在 longest_tenure/first_vs_last
  类题目,机制是 gpt-5-mini 对答案括注的**持续时长做二次算术自洽性核
  查**,发现算出来的年数与题目要求的精确时点对不上(例:答案称"held for
  ~9 years(1997-06 至 2006-06)",gpt-5-mini 核对区间与雇主本身是否为金
  标匹配后仍判错,理由聚焦日期/时长自洽,而克劳德判官只核对"雇主/职位
  实体名称"是否匹配即判对)。

两种机制都指向同一结论:**这批分歧里 gpt-5-mini 整体比克劳德判官口径更
严,不是对 QVF 答案宽松**——与"同族偏袒"假说的方向相反。

## 4. 分题型一致性

| arm | change_count | count_before | first_vs_last | longest_tenure |
|---|---|---|---|---|
| direct | 88.19% | 89.58% | 95.83% | **81.94%** |
| smoc_v45 | 100.00% | 100.00% | 96.53% | 91.67% |
| smw | 99.31% | 99.31% | 97.92% | 88.89% |
| smwplain | 97.92% | 97.92% | 94.44% | 92.36% |

longest_tenure 是四臂里一致性最低的题型(81.94%–92.36%),与 §3 的机制
读法吻合(时长自洽性核查最容易在这个题型触发分歧)。

## 5. 阶梯差值:gpt 判官下重算(McNemar 精确二项符号检验)

| 阶梯 | n | delta(gpt 判官) | b/c | McNemar p | 克劳德判官原值(b33A) | 方向 |
|---|---|---|---|---|---|---|
| smoc_v45 − direct | 576 | **+48.61pp** | 17/297 | 3.22e-67 | +41.49pp | 一致,幅度更大 |
| smw − smwplain | 576 | **+32.47pp** | 26/213 | 1.07e-37 | +32.12pp("smwplain→smw"阵) | 一致,幅度几乎相同 |
| smoc_v45 − smw | 576 | **+4.17pp** | 55/79 | 0.0465 | +3.47pp("smw→smoc(v45)"阵) | 一致,幅度相近 |

三条阶梯在两位判官下方向、显著性判读完全一致;前两条幅度基本重现,第三
条(smoc−smw,本就是原表里最弱的一条,p=0.072 未显著)在 gpt 判官下反而
p=0.0465 转为压线显著——同向但不作为新增强主张,样本 b/c 结构接近临界。

## 6. 成本

| arm | in tok | out tok | $ |
|---|---|---|---|
| direct | 273,092 | 28,011 | $0.1243 |
| smoc_v45 | 235,274 | 22,705 | $0.1042 |
| smw | 235,667 | 23,134 | $0.1052 |
| smwplain | 242,779 | 24,681 | $0.1101 |
| **合计** | **986,812** | **98,531** | **$0.4438** |

gpt-5-mini $0.25/M in、$2.00/M out(口径同 results/ladder_decontamination_20260902.md）。
2304 次判官调用全部一次性成功,0 次回退(containment 兜底未触发)。远低
于本批 $6 预算上限,未接近预算约束。

## 7. 偏离(相对预注册,均已在 results/opt_batch45_prereg.md 中预先声明)

1. `temperature=0` 被 API 拒绝——`Unsupported value: 'temperature' does
   not support 0 with this model. Only the default (1) value is
   supported.`(2026-09-04 实测)。回退默认(不传该参数),与三份前例脚本
   (cross_judge_generic.py / cross_judge_chain.py / crossjudge_s5_twin.py)
   一致。
2. `reasoning_effort="minimal"`——前例脚本均未设置该参数(gpt-5-mini 默
   认可能是 medium)。为控制 2304 次调用的成本/延迟主动设置,冒烟测试确
   认 0 隐藏推理 token 下verdict 仍合理。是本批唯一"主动新增"而非"被动
   适配"的偏离,见下节未验证。
3. 结构化输出机制从 Anthropic `messages.parse(output_format=JudgeVerdict)`
   换成 OpenAI `response_format={"type":"json_object"}` + 提示词尾部追加
   一行 JSON 格式说明——只改变解析机制,评分规则文本(JUDGE_SYSTEM_PROMPT
   + `_judge_user_prompt`)逐字未变。

## 8. 未验证

- 未在 `reasoning_effort` 默认强度下对 direct 臂的 64 处分歧做消融重判,
  故不能完全排除"minimal 强度导致字面主义"是 direct 臂一致性偏低
  (88.89%<90%)的部分成因。但 §3 的定性读法显示分歧是稳定、可解释的评
  分口径差异(限定语解读、日期自洽性核查),不是随机噪声表现
  (κ=0.775,"实质一致"区间)——判断"口径差异"比"推理强度不足"更可能是
  主因,但未做对照实验,不作定论。
- 未跑 filter/usability/compile/summary/smoc_v45g 五臂(预注册已声明超
  出本批范围)。
- 未复算链级 TOST/144-簇自助 CI(预注册已声明超出本批范围;本批仅报臂
  级准确率、逐题一致性/κ、三条阶梯的 McNemar)。
- smoc_v45−smw 阶梯在 gpt 判官下压线显著(p=0.0465,克劳德判官下
  p=0.0721 不显著)——样本量小、b/c 结构接近临界,未做进一步稳健性检验
  (如 bootstrap),不作为新增强主张援引。
