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

---

# 36b 同读者 Sonnet 5

批 36 §六.4 把"跨读者比较"列为本轨最大的口径弱点:那一批拿
plainctx@**sonnet-5** 去比 smoc@**haiku**。本节把 QVF 账目臂与两条参照臂
用**同一个读者 claude-sonnet-5** 在**同 140 题**上重跑,消掉该弱点。

- 跑批脚本:`scripts/lb_reader_arm_b36b.py`(`scripts/lb_reader_arm.py` 的副本,
  原件全程只读)。相对原件的**全部**差异:`--max-tokens`(默认仍 800)、
  `--workers`(默认仍 1)、`--budget`、以及行 schema 增量字段;
  smoc / direct / fullplain 三臂的提示词构造**逐字复制**原件 `main()`。
- 记分脚本:`scripts/b36b_score.py` → `results/b36b_score_out.txt`
- 产物:`results/b36b_{smoc,direct,fullplain}_sonnet5.jsonl`(append + 跳过已完成)
- 语料 `data/wikistate_full_ALL_v24.json`(v2.4);店 `results/wt_cards_v45`
  (**只读,未重建**);题集 `results/b35_questions_sample36.jsonl`(140 题 / 36 链);
  判官 `qvf.judge.ClaudeJudge()` = claude-opus-5
- **max_tokens = 4000**(三臂全部;逐行落盘 `reader_max_tokens`)。
  结果:420 次读者调用**全部 `stop_reason=end_turn`**,零截断、零空答、
  零读者报错、零判官回退 —— 批 36 的截断 artefact 在本节不存在。
- **采样参数**:原件 `lb_reader_arm.py` 本来就只在
  `model.startswith("claude-haiku")` 时发 `temperature=0`,**从未给 sonnet-5
  发过 temperature**,所以不需要新增闸;副本只是把它写成显式的
  `_wants_temperature()` 并加注。已实测确认必要性:claude-sonnet-5 收到
  `temperature` 返回 `400 ... "\`temperature\` is deprecated for this model."`,
  收到 `top_p` 同样 400,两者都不发则正常返回。

---

## 一、判决

1. **"QVF 账目相对全量上下文的准确率优势"在 sonnet-5 级读者上被否定 —— 而且
   比批 36 说的更糟:不是打平,是被显著超越。**
   同读者 sonnet-5、max_tokens=4000:smoc **90.7%** vs plainctx **97.1%**,
   配对 **−6.43pp**,翻转 3 正 / 12 负,**McNemar p = 0.035**。
   批 36 §一.3 记的 "+5.71pp,p=0.077,方向已翻过来"是**跨读者**数;
   把读者对齐后,方向不变而显著性过线。**在强读者上,现实全上下文直读优于 QVF 账目。**

2. **"读者越强 QVF 越强"这个隐含假设被否定:账目臂对读者几乎不敏感。**
   同一店、同一提示、只换读者:smoc haiku **91.4%** → sonnet-5 **90.7%**,
   **−0.71pp,翻转 6/7,p = 1.00**。而同样换读者,
   direct **+20.00pp**(50.7 → 70.7,p=1.5e-05)、
   fullplain/smwplain **+26.81pp**(58.0 → 84.8,p=4.3e-07)、
   plainctx **+17.86pp**(批 36 实测)。
   → **只有账目臂吃不到读者升级的红利。** 推论(本节直接支持):smoc 的天花板
   由**账目内容**设定,不由读者的阅读能力设定 —— 账目里没有的东西,换多强的
   读者都补不回来。这既是 QVF 的卖点(小模型也能打到 91),也是它的封顶。
   佐证:smoc 的 13 个错题里 **6 个在两个读者上同时错**(change_count 3 /
   longest_tenure 2 / count_before 1),即近半错误与读者无关。

3. **批 36 那条跨读者比较,事后证明没有实质偏误 —— 但这是运气,不是方法。**
   因为 smoc 的读者效应是 −0.71pp(不显著),批 36 用 smoc@haiku 代替
   smoc@sonnet-5 只造成 0.71pp 的偏差,结论方向不变。**批 36 的数字不需要撤回**;
   但同一替换若发生在 direct 或 fullplain 上会造成 20–27pp 的偏差,
   跨读者比较仍应视为不可接受的口径。

4. **框定税在强读者上依然存在,且是同读者内测得的:+12.32pp。**
   同一读者、**同一段全文字节**,只换提示词:
   fullplain(`PLAIN_PROMPT`,"Reply with only the answer")**84.8%**
   vs plainctx(现实措辞,不限长度)**97.1%**,
   配对 **−12.32pp**,翻转 **0 正 / 17 负**(即 plainctx 对的题 fullplain 一题没赢),
   p = 1.5e-05。批 36 §一.2 在 haiku 上测得 +11.43pp,本节在 sonnet-5 上
   测得 +12.32pp —— **框定税与读者强弱基本无关,稳定在 11–12pp。**
   论文里任何"全文直读只有 58.6%"的引用都必须撤下,它测的是提示词,不是上下文。

5. **检索式直读在强读者上依然远逊于全上下文。**
   direct@sonnet5 **70.7%** vs plainctx@sonnet5(校正)**97.1%**,
   **−26.43pp**,翻转 1 正 / 38 负,p = 1.5e-10。
   换强读者把 direct 从 50.7 抬到 70.7(+20pp),但**没有缩小**它与全上下文的差距
   (haiku 上差 27.1pp,sonnet-5 上差 26.4pp)。**"稠密 top-10 直读"不是全上下文的
   合格代理,这一条在两个读者上各自成立。**

6. **QVF 在同读者上剩下的唯一主张是成本,且倍率被砍到 2.8×。**
   smoc@sonnet5 $0.01469/题 vs plainctx@sonnet5 $0.04179/题 = **0.35×**
   (输入 token 0.20×)。批 36 报的 "8.1× 便宜"是跨读者数
   (smoc@haiku $0.00518 vs plainctx@sonnet5 $0.04179);**同读者口径是 2.8×**。
   若允许 QVF 用小读者、基线用大读者,才回到 8.1×,但那时准确率差是
   −5.7pp(91.4 vs 97.1)。

**置信标签**:判决 1、2、4、5、6 为**已证实**(配对 n=140,p 见上;
判决 4/5 的 fullplain 侧 n=138,见 §五.1);判决 3 为**已证实的事后核验**。
本节**未做**链簇自助 CI(任务书只要 McNemar),故所有 |Δ| 均无区间估计。

---

## 二、主表(同 140 题,读者 claude-sonnet-5,max_tokens=4000)

| 臂 | 读者 | n | 准确率 | change_count | count_before | first_vs_last | longest_tenure | 均 in tok | 均 out tok | 中位延迟 s | $/题 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **smoc(QVF 账目 v45 + F.1)** | **sonnet-5** | 140 | **90.7%** | 83.3 | 88.9 | 100.0 | 90.6 | 3,713 | 726 | 7.13 | **$0.01469** |
| **direct(稠密 top-10 + 摘录框定)** | **sonnet-5** | 140 | **70.7%** | 66.7 | 50.0 | 88.9 | 78.1 | 1,149 | 266 | 3.40 | $0.00496 |
| **fullplain(全文 + 裸问答提示)** | **sonnet-5** | **138** | **84.8%** | 83.3 | 75.0 | 97.1 | 83.9 | 18,555 | 192 | 3.00 | $0.03903 |
| plainctx(全文 + 现实措辞,mt800) | sonnet-5 | 140 | 87.9% | 94.4 | 94.4 | 94.4 | 65.6 | 18,549 | 444 | 5.01 | $0.04154 |
| plainctx(同上,截断校正 mt4000) | sonnet-5 | 140 | **97.1%** | 100.0 | 97.2 | 100.0 | 90.6 | 18,549 | 469 | 4.88 | $0.04179 |
| smoc(QVF 账目 v45 + F.1) | haiku-4-5 | 140 | 91.4% | 86.1 | 86.1 | 100.0 | 93.8 | 2,841 | 467 | 4.79 | $0.00518 |
| direct | haiku-4-5 | 140 | 50.7% | 47.2 | 36.1 | 88.9 | 28.1 | 862 | 84 | 1.57 | $0.00128 |
| smwplain(= fullplain 同臂) | haiku-4-5 | 140 | 58.6% | 33.3 | 66.7 | 80.6 | 53.1 | 13,568 | 133 | 5.39 | $0.01423 |
| smw(全文 + F.1) | haiku-4-5 | 140 | 92.9% | 83.3 | 94.4 | 100.0 | 93.8 | 13,817 | 441 | 7.77 | $0.01602 |
| plainctx(全文 + 现实措辞,mt800) | haiku-4-5 | 140 | 70.0% | 52.8 | 75.0 | 91.7 | 59.4 | 13,570 | 199 | 2.94 | $0.01456 |

计价:claude-sonnet-5 $2.00/M in、$10.00/M out;claude-haiku-4-5 $1.00/M in、$5.00/M out。
只计读者,判官另计(本节判官 418 次 = in 64,309 / out 23,286 tok = **$0.90** @ opus-5 $5/$25)。

**臂同一性已核验**:fullplain(本节)与 33-A 的 smwplain 是**同一臂**——
`PLAIN_PROMPT` 逐字相同、`render_transcript` 输出逐字节相同、系统提示两侧皆空
(核验代码在 `scripts/b36b_score.py` §0,零 API)。故"fullplain@sonnet5 vs
smwplain@haiku"是纯读者对照。

**题型读法**:
- smoc 换读者后 `longest_tenure` 由 93.8 掉到 90.6、`count_before` 由 86.1 升到 88.9,
  四型全部在 ±4pp 内,与总分的 −0.71pp 一致 —— **账目臂对读者的不敏感是全题型的**。
- plainctx 校正后在四型上 97–100,**唯一还没满的是 `count_before`(97.2)**;
  批 36 记的"最长任期是全文直读的短板"是 800 上限造成的假象:
  mt4000 下 `longest_tenure` 由 65.6 直接补到 90.6。
- direct 的 `count_before` 只有 50.0 —— top-10 检索天然拿不全"某时点之前的全部取值"。

---

## 三、配对比较(McNemar 精确二项;delta 与翻转均以 A 为主语)

**同读者 sonnet-5(批 36 做不出的那一组)**

```
A=smoc@sonnet5      90.7%  B=plainctx@sonnet5 mt800   87.9%  delta  +2.86pp  A对B错16 / B对A错12  p=0.5716
A=smoc@sonnet5      90.7%  B=plainctx@sonnet5 mt4000  97.1%  delta  -6.43pp  A对B错 3 / B对A错12  p=0.03516
A=direct@sonnet5    70.7%  B=plainctx@sonnet5 mt800   87.9%  delta -17.14pp  A对B错13 / B对A错37  p=9.362e-04
A=direct@sonnet5    70.7%  B=plainctx@sonnet5 mt4000  97.1%  delta -26.43pp  A对B错 1 / B对A错38  p=1.455e-10
A=fullplain@sonnet5 84.8%  B=plainctx@sonnet5 mt800   87.7%  delta  -2.90pp  A对B错14 / B对A错18  p=0.5966   (n=138)
A=fullplain@sonnet5 84.8%  B=plainctx@sonnet5 mt4000  97.1%  delta -12.32pp  A对B错 0 / B对A错17  p=1.526e-05 (n=138)
```

**读者效应(臂不变,只换读者)**

```
A=smoc@sonnet5      90.7%  B=smoc@haiku               91.4%  delta  -0.71pp  A对B错 6 / B对A错 7  p=1.000
A=direct@sonnet5    70.7%  B=direct@haiku             50.7%  delta +20.00pp  A对B错35 / B对A错 7  p=1.510e-05
A=fullplain@sonnet5 84.8%  B=smwplain@haiku(同臂)     58.0%  delta +26.81pp  A对B错46 / B对A错 9  p=4.336e-07 (n=138)
```

**同读者阶梯(非任务书要求,但这才是同口径的阶梯)**

```
A=smoc@sonnet5           90.7%  B=direct@sonnet5      70.7%  delta +20.00pp  34 /  6  p=8.365e-06
A=smoc@sonnet5           90.6%  B=fullplain@sonnet5   84.8%  delta  +5.80pp  18 / 10  p=0.1849   (n=138)
A=plainctx@sonnet5 mt4000 97.1% B=fullplain@sonnet5   84.8%  delta +12.32pp  17 /  0  p=1.526e-05 (n=138)
```

**smoc 的 12 个"输给 plainctx"的题**按型分布:change_count 6 / count_before 4 /
longest_tenure 2;反向只赢 3 题(longest_tenure 2 / count_before 1)。
按链看,12 题里有 7 题集中在 3 条链(wikiP54001 三题、wikiP39039 两题、
wikiP551003 两题)—— 是**特定链的账目缺漏**,不是读者的普遍性弱点。

---

## 四、成本(同读者 claude-sonnet-5)

| 臂 | $/题 | 相对 plainctx(校正) | in tok/题 | in token 相对 plainctx |
|---|---|---|---|---|
| smoc@sonnet5 | $0.01469 | **0.35×** | 3,713 | **0.20×** |
| direct@sonnet5 | $0.00496 | 0.12× | 1,149 | 0.06× |
| fullplain@sonnet5 | $0.03903 | 0.93× | 18,555 | 1.00× |
| plainctx@sonnet5 mt800 | $0.04154 | 0.99× | 18,549 | 1.00× |
| plainctx@sonnet5 mt4000 | $0.04179 | 1.00× | 18,549 | 1.00× |

注:smoc 的 $/题 换读者后由 $0.00518 涨到 $0.01469(2.8×),其中一半来自
输出 token 由 467 涨到 726(sonnet-5 默认开思考)。**同读者的成本优势是 2.8×,
不是批 36 主表跨读者的 8.1×。** 本节不含建卡摊销;店为 33-A 遗留,未重建。

---

## 五、口径瑕疵与无法核实项

1. **fullplain@sonnet5 只跑到 138/140。** 缺
   `wikiP551009-Q5321987_v2fl`、`wikiP551009-Q5321987_v2lt`。
   原因:$8 读者花费闸在队列到 $7.95 时停发新题,已在途的调用把本节读者总花费
   带到 **$8.137**(超闸 $0.137,系并发在途所致,非有意)。补齐这 2 题约需 $0.08,
   **未执行**(不再追加花费)。凡涉及 fullplain 的配对行 n=138,已逐行标注;
   其余全部 n=140。
2. **33-A 的四条对照臂行内仍无 `reader_model` 字段**(批 36 §六.2 的遗留项)。
   本节 `results/b36b_*_sonnet5.jsonl` 已逐行落盘 `reader_model` /
   `reader_max_tokens` / `stop_reason` / `judge_input_tokens` /
   `judge_output_tokens` / `reader_error` / `cards_dir`,是 33-A schema 的**超集**;
   但 **33-A 那侧的读者身份依旧只能从 `mode` 串
   (`smoc:anthropic:claude-haiku-4-5`)与脚本默认值推定,无法从产物核实**。
   这一条与批 36 的结论相同,本节没有改善它。
3. **max_tokens 口径不对称,但已核验无实际影响**:本节 sonnet-5 三臂用 4000,
   33-A 的 haiku 臂当年用原件写死的 800。已逐行核查这 140 题:
   `b33A_smoc_v45` / `b33A_direct` / `b33A_smwplain` 三个进入配对的 haiku 臂
   **各有 0 题打满 800**(`b33A_smw` 有 1 题,未用于本节判决)。
   故 §三第二组的读者效应行**不含上限 artefact**。
   (haiku 不开思考,800 对它是宽松上限;sonnet-5 开思考才需要 4000。)
4. **本节未做**:链簇自助 CI、TOST 等价性、v2.5 语料、其它读者、
   以及 33-A 的 filter/usability/compile/smw/summary 五臂的 sonnet-5 版
   (任务书只授权 smoc / direct / fullplain)。
   因此"同读者阶梯"目前只有 direct → fullplain → smoc → plainctx 四点,
   中三段仍是 haiku 独有。
5. **店未重建**:`results/wt_cards_v45` 全程只读(mtime 未变),
   与 33-A 溯源块记的目录 sha256 同一份。建卡侧成本未计入本节 $/题。

---

## 六、精确命令(可重放)

```bash
# smoc(QVF 账目,读 33-A 遗留店 v45,只读)
PYTHONUTF8=1 python scripts/lb_reader_arm_b36b.py \
  --reader anthropic:claude-sonnet-5 --arm smoc \
  --cards-dir results/wt_cards_v45 --max-tokens 4000 --workers 6 --budget 8.0 \
  --data data/wikistate_full_ALL_v24.json \
  --questions results/b35_questions_sample36.jsonl \
  --out results/b36b_smoc_sonnet5.jsonl

# direct(必须 OpenAI 嵌入,与 33-A 同)
PYTHONUTF8=1 QVF_EMBED_BACKEND=openai python scripts/lb_reader_arm_b36b.py \
  --reader anthropic:claude-sonnet-5 --arm direct \
  --max-tokens 4000 --workers 6 --budget 8.0 \
  --data data/wikistate_full_ALL_v24.json \
  --questions results/b35_questions_sample36.jsonl \
  --out results/b36b_direct_sonnet5.jsonl

# fullplain(= 33-A 的 smwplain 同臂)
PYTHONUTF8=1 python scripts/lb_reader_arm_b36b.py \
  --reader anthropic:claude-sonnet-5 --arm fullplain \
  --max-tokens 4000 --workers 6 --budget 8.0 \
  --data data/wikistate_full_ALL_v24.json \
  --questions results/b35_questions_sample36.jsonl \
  --out results/b36b_fullplain_sonnet5.jsonl

# 记分
PYTHONUTF8=1 python scripts/b36b_score.py > results/b36b_score_out.txt
```
