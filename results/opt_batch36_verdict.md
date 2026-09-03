# 批 36 —— “现实直读”基线(plainctx):整库原始记忆入提示、普通一次调用

用户要的基线:**把全部原始记忆原样塞进提示,普通提问,不检索、不上协议、
不说“这是从记忆里检索到的摘录”、不限答复长度**。本批把它跑出来,并与批 33-A
四条档案臂在**同 140 题**上做配对比较。

- 跑批脚本:`scripts/b36_plain_fullctx.py`
- 记分脚本:`scripts/b36_score.py` → `results/b36_score_out.txt`
- 产物:`results/b36_plainctx_haiku-4-5.jsonl`、`results/b36_plainctx_sonnet-5.jsonl`
  (灵敏度:`*_mt4000.jsonl`,只含被 800 token 上限截断的题)
- 语料 `data/wikistate_full_ALL_v24.json`(v2.4);题集 `results/b35_questions_sample36.jsonl`
  (140 题 / 36 链);判官 `qvf.judge.ClaudeJudge()` 默认 claude-opus-5,与
  `scripts/lb_reader_arm.py` 同一调用式
- 读者花费实测 **$8.81**(闸口 $12,未触发);零重试、零读者报错、零判官回退

---

## 一、判决

1. **“把整库塞进上下文的朴素直读很弱”这个猜想,在小读者上被证实,在大读者上被否定。**
   同一份全文、同一个裸提示,只换读者:haiku-4-5 得 **70.0%**,claude-sonnet-5 得
   **87.9%**(截断校正后 **97.1%**)。读者内配对差 +17.86pp,McNemar p=1.7e-04。
   基线的强弱**主要由读者决定**,不由“有没有给全文”决定。

2. **框定本身值 +11.4pp:同样的全文,换掉任务化措辞就涨分。**
   plainctx(haiku)70.0% vs 档案臂 smwplain(同一 `render_transcript` 全文 +
   `PLAIN_PROMPT` “Answer the question ... Reply with only the answer.”)58.6%,
   配对 +11.43pp,p=0.0195,翻转 29 正 / 13 负。两臂**上下文逐字节相同**,
   差别只有提示词。所以“朴素全文直读 = 58.6%”这个旧数字是**被提示词压低的**,
   不是全文入上下文的真实上限。

3. **对 QVF 的结论按读者分档,必须分开说:**
   - **haiku-4-5 读者(与 33-A 主表同读者):结构化仍显著领先。**
     smoc_v45 91.4% vs plainctx 70.0%,配对 **−21.43pp**,p=5.3e-06(37 题
     账目对/直读错,仅 7 题反向)。且 smoc 只花 2,841 in-token / $0.00518 一题,
     plainctx 花 13,570 / $0.01456 —— 结构化**又准又便宜 2.8 倍**。
   - **claude-sonnet-5 读者:优势消失,方向甚至反转。**
     按协调员口径(max_tokens 800)plainctx 87.9% vs smoc(haiku)91.4%,
     差 −3.57pp,**p=0.44,不显著**;截断校正后 plainctx 97.1% vs 91.4%,
     **+5.71pp,p=0.077**,仍未过 0.05,但方向已经翻过来。
     对 smw(全文 + F.1 协议,92.9%)同理:800 口径 −5.00pp(p=0.23)、
     校正后 +4.29pp(p=0.15),两侧都不显著。
   → **判决:“QVF 账目相对全量上下文的准确率优势”在 haiku 级读者上成立且很大,
     在 sonnet-5 级读者上不成立(统计上打平)。此时 QVF 剩下的主张只有成本
     —— $0.00518 vs $0.04179 一题,便宜 8.1 倍。**

4. **和“检索式直读”比,现实直读稳赢。**
   plainctx(haiku)70.0% vs b33A_direct(稠密 top-10 + “excerpts/1-3 sentences”
   框定)50.7%,+19.29pp,p=8.98e-04;sonnet-5 更是 +37.14pp(p=5.7e-11)。
   代价是 15.7 倍 in-token。**“检索式直读”不是全上下文的合格代理**,
   拿它当唯一 direct 基线会系统性高估任何记忆机制。

**置信标签**:1–2、4 为**已证实**(配对显著、n=140);3 的 haiku 档为**已证实**,
sonnet-5 档为**未被证实的打平**(p=0.077 / 0.44,n=140,不能宣称任一方更强)。

---

## 二、主表(同 140 题,max_tokens 800 协调员口径)

| 臂 | 读者 | n | 准确率 | change_count | count_before | first_vs_last | longest_tenure | 均 in tok | 均 out tok | 中位延迟 s | $/题 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **plainctx**(本批) | haiku-4-5 | 140 | **70.0%** | 52.8 | 75.0 | 91.7 | 59.4 | 13,570 | 199 | 2.94 | $0.01456 |
| **plainctx**(本批) | sonnet-5 | 140 | **87.9%** | 94.4 | 94.4 | 94.4 | 65.6 | 18,549 | 444 | 5.01 | $0.04154 |
| b33A_smwplain(全文 + 裸问答提示) | haiku-4-5 | 140 | 58.6% | 33.3 | 66.7 | 80.6 | 53.1 | 13,568 | 133 | 5.39 | $0.01423 |
| b33A_smw(全文 + F.1 两段式协议) | haiku-4-5 | 140 | 92.9% | 83.3 | 94.4 | 100.0 | 93.8 | 13,817 | 441 | 7.77 | $0.01602 |
| b33A_direct(稠密 top-10 + 摘录框定) | haiku-4-5 | 140 | 50.7% | 47.2 | 36.1 | 88.9 | 28.1 | 862 | 84 | 1.57 | $0.00128 |
| b33A_smoc_v45(QVF 卡片账目 + F.1) | haiku-4-5 | 140 | 91.4% | 86.1 | 86.1 | 100.0 | 93.8 | 2,841 | 467 | 4.79 | $0.00518 |

计价:haiku-4-5 $1.00/M in、$5.00/M out;claude-sonnet-5 $2.00/M in、$10.00/M out。
只计读者,判官另计。

**题型读法**:plainctx 的短板集中在 `longest_tenure`(haiku 59.4%、sonnet 65.6%,
截断校正后 sonnet 该型才补齐)——最长任期要跨全篇算区间,是全文直读最吃亏的一型;
`first_vs_last` 两个读者都 ≥91.7%,因为只需首尾两点。

---

## 三、配对比较(McNemar 精确二项;test = 本批 plainctx)

**plainctx : haiku-4-5(n=140)**

```
vs b33A_smwplain   58.6% -> 70.0%  delta +11.43pp  翻转 13 负 / 29 正  p=0.01952
vs b33A_smw        92.9% -> 70.0%  delta -22.86pp  翻转 33 负 /  1 正  p=4.075e-09
vs b33A_direct     50.7% -> 70.0%  delta +19.29pp  翻转 18 负 / 45 正  p=0.000898
vs b33A_smoc_v45   91.4% -> 70.0%  delta -21.43pp  翻转 37 负 /  7 正  p=5.3e-06
```

**plainctx : claude-sonnet-5(n=140,max_tokens 800)**

```
vs b33A_smwplain   58.6% -> 87.9%  delta +29.29pp  翻转  8 负 / 49 正  p=2.717e-08
vs b33A_smw        92.9% -> 87.9%  delta  -5.00pp  翻转 16 负 /  9 正  p=0.2295
vs b33A_direct     50.7% -> 87.9%  delta +37.14pp  翻转  8 负 / 60 正  p=5.748e-11
vs b33A_smoc_v45   91.4% -> 87.9%  delta  -3.57pp  翻转 16 负 / 11 正  p=0.4421
```

**读者内对照**:plainctx haiku 70.0% → plainctx sonnet-5 87.9%,+17.86pp,
翻转 9 负 / 34 正,p=1.702e-04。

(“负”= 对照臂对、本臂错;“正”= 对照臂错、本臂对。)

---

## 四、上下文长度与“助手轮是否入档”

`render_transcript`(逐字复用 `scripts/repro_batch3.py`;已按 AST 断言与
`scripts/repro_batch3_b33.py` 内那份**字节等价**,即 33-A 的 smw/smwplain 看的是
**同一段文本**)。

| 指标 | min | 中位 | 均值 | max |
|---|---|---|---|---|
| 字符 / 库 | 49,906 | 51,793 | 52,074 | 53,980 |
| 会话 / 库 | 33 | 33 | 33.7 | 38 |
| 轮次 / 库 | 161 | 162 | 164.6 | 182 |
| 实测 in token / 题(haiku) | — | — | 13,570 | — |
| 实测 in token / 题(sonnet-5) | — | — | 18,549 | — |

**助手轮确认入档**:36 库共 5,926 轮,构成为 **user 3,237 / assistant 2,160 /
无角色前缀的链注入轮 529**。全部按日期序渲染,每个会话前有
`--- session date: YYYY-MM-DD ---` 行,轮次全局连续编号 `[turn N]`。

**必须说明的口径瑕疵(不是本批引入,33-A 的 smw/smwplain 同样如此)**:
v2.4 语料把助手轮以 **400 字符截断的 Python dict repr 字符串**存盘,
2,160 条助手轮中 **2,156 条**因此 `eval` 失败,渲染成原样的
`{'role': 'assistant', 'content': "…`(残句),而不是漂亮的 `assistant: …`。
**没有任何内容被丢弃**——那就是语料里存的全部字节——但助手回复在**语料层面**
本来就是断句的。若要一份真正“助手轮完整”的现实直读基线,需先修语料,不是修渲染。

**另一处不可忽略的口径差**:同一段字节完全相同的提示,claude-sonnet-5 报的
input token 比 haiku-4-5 高 **1.37 倍**(18,549 vs 13,570,逐题比值 1.35–1.38)。
两者分词不同,跨读者的 $/题 比较里这一项**不是**上下文变长造成的。

---

## 五、截断灵敏度(非主表)

claude-sonnet-5 默认开思考,`max_tokens` 同时封顶“思考 + 可见输出”。
按协调员口径的 800,**20 题打满 800、其中 14 题只返回空文本**(全部判错)。
这是上限artefact,不是推理失败。把这 20 题以 `max_tokens=4000` 原样重跑:

| 臂 | 重跑题数 | 这些题正确数 | 空答 | 臂准确率 800 → 校正 | $/题 800 → 校正 |
|---|---|---|---|---|---|
| plainctx:haiku-4-5 | 1 | 0/1 → 1/1 | 0 → 0 | 70.0% → **70.7%** | $0.01456 → $0.01457 |
| plainctx:sonnet-5 | 20 | 5/20 → 18/20 | 14 → 0 | 87.9% → **97.1%** | $0.04154 → $0.04179 |

校正后的配对行:

```
sonnet-5 校正 vs b33A_smwplain   58.6% -> 97.1%  +38.57pp  翻转 3 负 / 57 正  p=6.254e-14
sonnet-5 校正 vs b33A_smw        92.9% -> 97.1%   +4.29pp  翻转 3 负 /  9 正  p=0.146
sonnet-5 校正 vs b33A_direct     50.7% -> 97.1%  +46.43pp  翻转 2 负 / 67 正  p=8.186e-18
sonnet-5 校正 vs b33A_smoc_v45   91.4% -> 97.1%   +5.71pp  翻转 4 负 / 12 正  p=0.07681
haiku    校正 vs b33A_smoc_v45   91.4% -> 70.7%  -20.71pp  翻转 36 负 / 7 正  p=8.963e-06
```

**主表仍以 800 口径为准**(协调员指定);本节只用来界定该口径给 sonnet-5 造成的
低估幅度(9.2pp)。若论文要引 sonnet-5 的现实直读上限,应引 **97.1%** 并注明
max_tokens=4000,否则等于拿一个被参数掐掉的数字去打自家基线。

---

## 六、无法核实 / 需协调员定夺

1. **协调员对 `b33A_smwplain` 的描述有误。** 任务书写它是“带 excerpts / 1-3
   sentences 框定的全文臂”。核对 `scripts/repro_batch3_b33.py`:smwplain 用的是
   `PLAIN_PROMPT`(“Answer the question based on the conversation transcript.
   Reply with only the answer.”),**系统提示为空,没有 excerpts 也没有句数限制**。
   带 “excerpts … retrieved from memory / 1-3 sentences” 的是
   `ext_direct_arm.READER_SYSTEM`,只有 **`b33A_direct`** 用它。
   本报告按代码实际口径标注,未按任务书描述标注。
2. **33-A 四臂的读者未在行内落盘。** 四个 jsonl 都没有 `reader_model` 字段;
   我据 `repro_batch3_b33.READER_MODEL` 默认值与 `mode` 串
   (`direct:anthropic:claude-haiku-4-5`)判定为 haiku-4-5。若当时设过
   `QVF_READER_MODEL` 覆盖,本报告的跨臂比较需重标——**这一条我无法从产物核实**。
3. **本批只跑 36/144 链、140/576 题**,与批 35 同一抽样。未做链簇自助 CI
   (任务书只要 McNemar);要 CI 可直接复用 `b35_score.compare` 的自助口径。
4. **未跑**:plainctx × 其它读者、plainctx × v2.5 语料、以及 smwplain/smw 在
   sonnet-5 上的对照(那需要重跑 33-A 两臂,任务书未授权)。因此“sonnet-5 下
   QVF 与全上下文打平”这一条,是**跨读者比较**(plainctx@sonnet-5 vs
   smoc@haiku),不是同读者比较 —— 这是本批最大的口径弱点,若要下硬结论,
   下一轮必须把 smoc/smw 也用 sonnet-5 跑一遍。
