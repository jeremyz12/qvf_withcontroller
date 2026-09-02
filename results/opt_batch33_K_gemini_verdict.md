# 批 33-K 判决:第三厂商读者(Google Gemini 3.6 Flash)

> 预注册判据(`results/opt_batch33_prereg.md` 33-K):**"协议适配律 / 读者双端定理是否在第三厂商上复现"**。
> 本判决按该判据逐条裁决,数字全部来自本轮实跑逐行归档,无一外推(判官侧美元除外,已明标口径)。

---

## 〇、判决先行

1. **协议适配律 —— 猜想被否定(在第三厂商上不复现)。**
   该律预测:F.1 两段式协议对强推理读者是**税**(负号,gpt-5-mini −3.5)、对中档 haiku 是**脚手架**(正号 +10.9)。
   Gemini 3.6 Flash 实测 **smoc 92.53 vs ledgerplain 92.19 = +0.35pp**,W/L/T=8/6/562,符号检验 **p=0.79**,
   144 链簇自助 95% CI **[−0.87, +1.56]**。该 CI 完整落在 ±3pp 等价带内(±2pp 亦过),
   **同时排除 haiku 的 +10.9 与 gpt 的 −3.5**。第三厂商给出的是第三种状态:**协议中性**。
   不是天花板伪影:协议救回 ledgerplain 45 道错题中的 8 道(17.8%),同时打坏 smoc 43 道错题里本来做对的 6 道(14.0%)——双向抵消,不是"无处可涨"。

2. **读者双端定理 —— 一半复现、一半被否定。**
   - **富结构端(收敛)复现**:三厂商账目臂落在 **90.45(haiku)/ 92.53(gemini)** 同一窄带,配对 Δ=+2.08pp、p=0.065、簇 CI [+0.00,+4.17]——换厂商换不出多少分,杠杆确实在证据结构一侧。
   - **贫证据端("强读者救不了")被否定**:同一 top-10 证据、同一嵌入器(`QVF_EMBED_BACKEND=openai`)、同一提示词下,
     **gemini direct 63.37 vs haiku 48.26 = +15.10pp,p=3.7e-13,簇 CI [+11.46,+18.92]**。
     而既有两个"强读者"(gpt-5-mini 42.88、sonnet-5 41.49)都比 haiku **更差**。
     所以"贫证据下强读者更差"不是读者强度的普遍规律,而是特定模型族的性质;
     **"证据饥饿"应从定理降格为按厂商成立的观察**。仍然成立的部分:即便如此,gemini 的 direct 仍比其账目臂低 **29.17pp**(p=3e-40,簇 CI [+24.13,+34.38])——结构总价在第三厂商上依然是两位数大额。

3. **附带改判(小库整库直塞)**:14K 小库上 gemini **整库直塞 95.49 > 账目 92.53**(Δ=−5.56,p=0.007,簇 CI [−10.42,−1.04])。
   "结构优于原文"在 14K 小库上**只对弱读者成立**;对第三厂商强读者,小库原文是更好的读法。规模轴上此结论翻转(见 §四)。

4. **污染:不触警。** 闭卷 **5.73%**(576),比 direct 低 57.64pp、比 smoc 低 86.81pp。
   命中全部集中在两类小整数计数题(change_count 12.5%、count_before 10.4%),
   两类需要具名取值的题(first_vs_last、longest_tenure)**0/288**——是猜小整数的基线命中,不是记住了语料。
   参照:haiku 闭卷 0.69、gpt-5-mini 闭卷 7.81。

---

## 一、读者与计价口径

| 项 | 值 |
|---|---|
| 模型 | **`gemini-3.6-flash`**(GA,非 preview;`client.models.list()` 实测在列,故未回退到次新 GA flash) |
| SDK | `google-genai` 2.20.0(已在项目 python 3.14 环境内,无需新装) |
| 采样 | `temperature=0.0`,`max_output_tokens=8192`,`thinking_level="low"`(**非厂商默认档,见 §六偏差①**) |
| 官方单价 | **输入 $0.75 / M,输出 $3.75 / M**(2026-12-31 前 promo 价;2027-01-01 起 $1.50 / $7.50)。出处:ai.google.dev/gemini-api/docs/pricing。thoughts token 按输出计价,本判决全部 `$/题` 已把 thoughts 计入输出 |
| 用量落盘 | 逐行记 `prompt_token_count` / `candidates_token_count` / `thoughts_token_count` / `total_token_count` / `finish_reason`(字段 `usage_meta`) |
| 重试 | 429 与 5xx 指数退避(4→8→16→32→60s,最多 6 次)。全程 **2,672 次调用只触发 1 次重试**(一次 503 UNAVAILABLE,退避后成功) |
| 判官 | `qvf.judge.ClaudeJudge`(`claude-opus-5`,冻结代码零改动,与全库同口径) |
| 语料/店 | v2.4 `data/wikistate_full_ALL_v24.json` + 卡店 `results/wt_cards_v44clean`;长店 `data/wikistate_long_L1.json` / `L2.json` |

**运行卫生(逐行核过,2,672 行)**:协议偏差 **0**、空答 **0**、`MAX_TOKENS` 截断 **0**。
对照:gpt-5-mini 账目臂空答 4%、sonnet-5 账目臂截断 5%——第三厂商读者在本任务上无格式性损耗。

---

## 二、逐臂结果(gemini-3.6-flash)

| 臂 | n | acc | Wilson 95% | in/题 | out/题(含 thoughts) | thoughts/题 | 读者 $/题 | 判官 $/题 | 合计 $/题 | 延迟/题 |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| **smoc(账目+F.1 协议)** | 576 | **92.53** | [90.1, 94.4] | 3,056 | 919 | 546 | 0.00574 | 0.00308 | 0.00882 | 6.3s |
| **ledgerplain(账目+裸提示)** | 576 | **92.19** | [89.7, 94.1] | 2,833 | 380 | 373 | 0.00355 | 0.00308 | 0.00663 | 3.3s |
| **direct top-10** | 576 | **63.37** | [59.4, 67.2] | 901 | 422 | 367 | 0.00226 | 0.00308 | 0.00534 | 3.7s |
| **fullplain(整库直塞,14K)** | 288† | **95.49** | [92.4, 97.3] | 13,366 | 601 | 594 | 0.01228 | 0.00308 | 0.01536 | 4.9s |
| **closedbook(闭卷)** | 576 | **5.73** | [4.1, 7.9] | 57 | 436 | 343 | 0.00168 | 0.00308 | 0.00476 | 4.1s |
| **fullplain @ L1(42K 店)** | 40 | **92.50** | [80.1, 97.4] | 41,473 | 931 | 923 | 0.03460 | 0.00308 | 0.03767 | 7.2s |
| **fullplain @ L2(102K 店)** | 40 | **77.50** | [62.5, 87.7] | 102,117 | 1,090 | 1,082 | 0.08067 | 0.00308 | 0.08375 | 8.9s |

† 预算约束下 fullplain 在 v2.4 上跑 **288 题(`--uid-stride 2`:144 链取 72 链,四题型天然 72/72/72/72 平衡)**,非 576。见 §六偏差②。

**逐题型**(正确数/题数)

| 臂 | change_count | count_before | first_vs_last | longest_tenure |
|---|---|---|---|---|
| smoc | 129/144 = 89.6 | 133/144 = 92.4 | 142/144 = 98.6 | 129/144 = 89.6 |
| ledgerplain | 128/144 = 88.9 | 132/144 = 91.7 | 141/144 = 97.9 | 130/144 = 90.3 |
| direct | 75/144 = 52.1 | 64/144 = 44.4 | 116/144 = 80.6 | 110/144 = 76.4 |
| fullplain(288) | 69/72 = 95.8 | 70/72 = 97.2 | 71/72 = 98.6 | 65/72 = 90.3 |
| closedbook | 18/144 = 12.5 | 15/144 = 10.4 | **0/144 = 0.0** | **0/144 = 0.0** |

---

## 三、三厂商同台(v2 主考场 576;acc / in-tok / $每题 / 延迟)

| 读者 | direct top-10 | 全文裸读 | 账目+协议(smoc) | 账目+裸提示(ledgerplain) | 闭卷 |
|---|---|---|---|---|---|
| haiku-4.5(非推理) | **48.26**<br>877 tok / $0.00131 / 1.7s | **52.26**(33-A 复跑 53.47)<br>13,671 tok / $0.01435 / 5.7s | **90.45**<br>2,950 tok / $0.00534 / 5.1s | **75.35**<br>2,664 tok / $0.00326 / 2.0s | 0.69 |
| gpt-5-mini(推理) | **42.88**<br>877 tok / $0.00169 / 16.2s | **85.76**<br>12,237 tok / $0.00471 / 10.9s | **78.65**(空答 4%)<br>2,542 tok / $0.00485 / 20.2s | **82.12**<br>2,331 tok / $0.00160 / 6.1s | 7.81 |
| **gemini-3.6-flash(推理,thinking=low)** | **63.37**<br>901 tok / $0.00226 / 3.7s | **95.49**(n=288)<br>13,366 tok / $0.01228 / 4.9s | **92.53**<br>3,056 tok / $0.00574 / 6.3s | **92.19**<br>2,833 tok / $0.00355 / 3.3s | **5.73** |

口径注:haiku 的 smoc / direct 行为 v2.4 语料 + v44clean 店(与 gemini 完全同底);haiku ledgerplain 与 gpt-5-mini 五臂为 v2 语料 + v43 店(项目既有归档,未重跑)。跨语料比较的绝对分差含 ±4pp 格式伪影与重建方差,**不作为本判决的判据来源**;三条判决全部建立在**同语料同店内部的配对差**上。
gpt-5-mini 单价按项目口径 $0.25 / $2.00 每 Mtok;haiku-4.5 $1.00 / $5.00。

### 3.1 协议效应(smoc − ledgerplain)三厂商对照

| 读者 | 协议效应 | 统计 | 解读 |
|---|---:|---|---|
| haiku-4.5 | **+10.9** | p<1e-06 | 脚手架 |
| gpt-5-mini | **−3.5** | p=0.012 | 税 |
| qwen3:14b【探针60】 | −3.3 | n.s. | 无影响 |
| qwen3:8b【探针60】 | +3.3 | n.s. | 无影响 |
| **gemini-3.6-flash** | **+0.35** | p=0.79,簇 CI [−0.87,+1.56] | **中性(等价带 ±3pp 内)** |

判据 K 第一问的答案:**协议适配律(以符号为预测内容)在第三厂商上不复现**;它在 576 题、144 簇的功效下被判为**中性**,而不是"未测出"。

### 3.2 跨读者配对差(同题、同证据、同判官)

| 对比 | n | 簇 | Δ | W/L | p(精确符号) | 簇自助 95% CI |
|---|---:|---:|---:|---|---|---|
| smoc:gemini vs haiku(v2.4/v44clean) | 576 | 144 | **+2.08** | 24/12 | 0.065 | [+0.00, +4.17] |
| direct:gemini vs haiku(同 top-10,openai 嵌入) | 576 | 144 | **+15.10** | 118/31 | **3.7e-13** | [+11.46, +18.92] |
| fullplain:gemini vs haiku | 288 | 72 | **+42.71** | 126/3 | **1.1e-33** | [+36.81, +48.61] |
| ledgerplain:gemini vs haiku(跨店,仅供参照) | 576 | 144 | +16.84 | 114/17 | 8.1e-19 | [+12.85, +20.83] |

### 3.3 gemini 内部臂间配对(簇 = 144 链)

| 对比 | n | Δ | W/L/T | p | 簇 CI |
|---|---:|---:|---|---|---|
| smoc − ledgerplain | 576 | **+0.35** | 8/6/562 | 0.79 | [−0.87, +1.56] |
| smoc − direct(**结构总价**) | 576 | **+29.17** | 179/11/386 | 2.9e-40 | [+24.13, +34.38] |
| ledgerplain − direct | 576 | +28.82 | 179/13/384 | 1.8e-38 | [+23.61, +34.20] |
| smoc − fullplain | 288 | **−5.56** | 8/24/256 | **0.007** | [−10.42, −1.04] |
| fullplain − direct | 288 | +32.29 | 97/4/187 | 3.4e-24 | [+25.69, +39.24] |
| smoc − closedbook | 576 | +86.81 | 504/4/68 | 6.6e-144 | [+83.16, +90.10] |
| direct − closedbook | 576 | +57.64 | 348/16/212 | 1.8e-82 | [+52.78, +62.50] |

对照:haiku 的结构总价(v2.4)= 90.45 − 48.26 = **+42.19**。**换成第三厂商强读者后,结构总价从 +42.2 收窄到 +29.2 —— 缩水约 13pp,但远未归零。**

---

## 四、规模轴:整库直塞的三厂商衰减(b27 十店探针,uid 完全一致,40 题同 qid)

| 店长 | gemini-3.6-flash | haiku-4.5 | gpt-5-mini |
|---|---|---|---|
| 14K(v2.4 主场,不同题) | 95.49(n=288) | 52.26 / 53.47 | 85.76 |
| **L1 ≈42K(同 40 题)** | **92.50**<br>41,473 tok / $0.03460 / 7.2s | **52.50**<br>42,286 tok / $0.04370 / 4.2s | **85.00**<br>37,693 tok / $0.01180 / 15.8s |
| **L2 ≈102K(同 40 题)** | **77.50**<br>102,117 tok / $0.08067 / 8.9s | **15.00**<br>103,815 tok / $0.10540 / 5.6s | **77.50**<br>92,606 tok / $0.02580 / 19.1s |
| L1→L2 配对掉幅 | **−15.00**(W/L=8/2,p=0.109) | **−37.50**(W/L=16/1,p=2.7e-04) | −7.50(W/L=6/3,p=0.508) |

同题配对跨读者:
- L1:gemini vs haiku **+40.00**(W/L=17/1,p=1.5e-04);gemini vs gpt-5-mini +7.50(4/1,p=0.375 n.s.)
- L2:gemini vs haiku **+62.50**(W/L=25/0,p=6.0e-08);gemini vs gpt-5-mini **0.00**(2/2,p=1.0)

**读法**:第三厂商没有推翻"整库直塞随店长衰减"——gemini 自己 42K→102K 掉 15pp(方向一致,n=40 未达显著)。
但它把"弱读者在 104K 上塌到 10-15"的场面彻底改写:**在 102K 上 gemini 与 gpt-5-mini 打平在 77.5**,
即 §四"三线两坠一平"的两条坠线里,**haiku 那条是模型族性质,不是长上下文的普遍性质**。
同时:L2 上整库直塞每题 **$0.0807**(gemini)/ **$0.1054**(haiku)/ **$0.0258**(gpt),而 v2.4 账目臂 gemini 每题 **$0.00574** ——
同读者下 L2 整库直塞 / v2.4 账目 = **14.1×**(L1 为 6.0×);账目臂的成本优势在第三厂商上照旧成立,
**但它现在换来的不是更高分而是更低价**(gemini 账目 92.53 vs 其 L2 整库直塞 77.50 分属不同题面,不可直接相减,此处只作成本对照)。

---

## 五、判据 K 逐条裁决

| 判据 | 裁决 | 依据 |
|---|---|---|
| 协议适配律(smoc − ledgerplain 的**符号**)在第三厂商复现? | **否** | +0.35pp,p=0.79,簇 CI [−0.87,+1.56] 落在 ±3pp 等价带内并排除 +10.9 / −3.5 |
| 读者双端定理:富结构端收敛? | **是** | gemini smoc 92.53 vs haiku 90.45,Δ=+2.08,CI 下界 +0.00 |
| 读者双端定理:贫证据端"强读者救不了"? | **否** | 同证据下 gemini +15.10pp 显著优于 haiku(p=3.7e-13),与 gpt/sonnet 的方向相反 |
| 结构总价在第三厂商仍为大额? | **是(但缩水)** | +29.17pp(簇 CI [+24.13,+34.38]),vs haiku +42.19 |
| 闭卷高 → 污染? | **否** | 5.73%,且全部落在两类小整数计数题;具名取值题 0/288 |

---

## 六、偏差、局限与如实声明

① **thinking_level = low,非厂商默认档。** 默认档在跑前用 4 题 × 4 臂实测:thoughts/题 = closedbook 927 / ledgerplain 773 / fullplain 846 / smoc 1,335;按默认档把整个 33-K 矩阵跑完 ≈ **$34(读者)+ $9(判官)**,**超 $25 上限**。故全部七臂统一改用 `thinking_level=low`(low 档实测 thoughts/题 = 496/335/426/589)。
  - 该设定**对全部臂一致**,因此 §三.3、§五 的**全部臂间配对差不受影响**;
  - 受影响的是**跨厂商绝对分**:gemini 的四个绝对分是"low 思考预算"下的值,若开默认档只会更高不会更低,故三条判决(协议中性 / 富端收敛 / 贫端反转)的方向都是**保守方向**——尤其"贫证据端强读者反而更好"这一否定性判决,在更高思考预算下只会更强。

② **fullplain 在 v2.4 上是 288 题不是 576。** 取法 `--uid-stride 2`(144 链按 uid 排序取偶数位 72 链),四题型天然 72/72/72/72 平衡,确定性可复现。原因:该臂单题输入 13.4K token,576 题读者侧要 $7.1,与 $25 上限冲突。所有涉及 fullplain 的配对比较都在这 288 题的配对子集上做(表内 n 已标)。

③ **判官侧美元是"实测均价 × 已知行数",不是本轮逐行实测。** 单价 $0.003078/次取自 `results/judge_cost_measured_20260816.md`(155 行真实重判的实测均价)。本轮脚本未落盘判官 usage(沿用冻结原件行为)。2,672 次 × $0.003078 = **$8.224**。

④ **跨语料/跨店的对照行**:haiku ledgerplain(75.35)与 gpt-5-mini 五臂是 v2 语料 + v43 店的既有归档;gemini 与 haiku 的 smoc/direct/fullplain 是 v2.4 + v44clean 同底。判决只用同底配对差,跨语料行只用于摆位置。

⑤ **L1/L2 为 n=40 探针**(10 店 × 4 题型),掉幅方向可读、显著性弱(gemini L1→L2 p=0.109)。不外推。

⑥ **本轮未跑**:L1/L2 上的 gemini 账目臂(prereg 33-K 只要求"整库直塞臂"用于长店,账目臂 L1/L2 由 33-D 覆盖);v2.4 上 haiku 的 ledgerplain 同底重跑(会使协议效应的三厂商对照更严格,约 $2)。两项均为已知缺口,不假装已覆盖。

⑦ **脚本改动纪律**:`scripts/lb_reader_arm.py` **逐字节未改**(git 工作区干净);全部改动在副本 `scripts/lb_reader_arm_b33k.py`。副本相对原件的唯一行为性改动是删掉 ollama 分支里的局部 `import os as _os`(它会把 `_os` 变成整个函数的局部名,令新增的 gemini 分支读不到模块级 `_os`),其余为纯新增(gemini 分支、`--uids`、`--uid-stride`、`usage_meta` 落盘)。

---

## 七、精确命令(全部可逐字复跑;工作目录 `D:\ZZL_cluade`,Git Bash)

```bash
# 0) 依赖(已在环境内,无需重装):google-genai 2.20.0;GEMINI_API_KEY 由环境提供

# 1) v2.4 主场 · 账目 + F.1 协议(576)
PYTHONUTF8=1 QVF_GEMINI_THINKING=low python scripts/lb_reader_arm_b33k.py \
  --reader gemini:gemini-3.6-flash --arm smoc \
  --data data/wikistate_full_ALL_v24.json \
  --cards-dir results/wt_cards_v44clean \
  --questions data/wsc_s5_v2.jsonl \
  --out results/b33k_gemini36f_smoc_v24.jsonl

# 2) v2.4 主场 · 账目 + 裸提示(576)
PYTHONUTF8=1 QVF_GEMINI_THINKING=low python scripts/lb_reader_arm_b33k.py \
  --reader gemini:gemini-3.6-flash --arm ledgerplain \
  --data data/wikistate_full_ALL_v24.json \
  --cards-dir results/wt_cards_v44clean \
  --questions data/wsc_s5_v2.jsonl \
  --out results/b33k_gemini36f_ledgerplain_v24.jsonl

# 3) v2.4 主场 · 直读 top-10(576)——嵌入器必须 openai
PYTHONUTF8=1 QVF_GEMINI_THINKING=low QVF_EMBED_BACKEND=openai python scripts/lb_reader_arm_b33k.py \
  --reader gemini:gemini-3.6-flash --arm direct \
  --data data/wikistate_full_ALL_v24.json \
  --questions data/wsc_s5_v2.jsonl \
  --out results/b33k_gemini36f_direct_v24.jsonl

# 4) v2.4 主场 · 整库直塞(288 = 144 链取 72 链)
PYTHONUTF8=1 QVF_GEMINI_THINKING=low python scripts/lb_reader_arm_b33k.py \
  --reader gemini:gemini-3.6-flash --arm fullplain \
  --data data/wikistate_full_ALL_v24.json \
  --questions data/wsc_s5_v2.jsonl --uid-stride 2 \
  --out results/b33k_gemini36f_fullplain_v24_s2.jsonl

# 5) v2.4 主场 · 闭卷(576)
PYTHONUTF8=1 QVF_GEMINI_THINKING=low python scripts/lb_reader_arm_b33k.py \
  --reader gemini:gemini-3.6-flash --arm closedbook \
  --data data/wikistate_full_ALL_v24.json \
  --questions data/wsc_s5_v2.jsonl \
  --out results/b33k_gemini36f_closedbook_v24.jsonl

# 6) L1 十店整库直塞(40)
PYTHONUTF8=1 QVF_GEMINI_THINKING=low python scripts/lb_reader_arm_b33k.py \
  --reader gemini:gemini-3.6-flash --arm fullplain \
  --data data/wikistate_long_L1.json \
  --questions data/wsc_long_L1_questions.jsonl \
  --uids data/b27_probe_uids.txt \
  --out results/b33k_gemini36f_fullplain_L1.jsonl

# 7) L2 十店整库直塞(40)
PYTHONUTF8=1 QVF_GEMINI_THINKING=low python scripts/lb_reader_arm_b33k.py \
  --reader gemini:gemini-3.6-flash --arm fullplain \
  --data data/wikistate_long_L2.json \
  --questions data/wsc_long_L2_questions.jsonl \
  --uids data/b27_probe_uids.txt \
  --out results/b33k_gemini36f_fullplain_L2.jsonl

# 8) 统计与成本($0,纯归档复算:acc / Wilson / 配对符号检验 / 144 链簇自助 CI / $每题)
PYTHONUTF8=1 python scripts/b33k_stats.py

# 9) 单文件快查(acc / token / $每题 / 延迟 / 空答 / 截断)
PYTHONUTF8=1 python scripts/b33k_summarize.py results/b33k_gemini36f_*.jsonl
```

并行度:全程 ≤4 个读者进程同时在跑(实际编排 smoc / ledgerplain / direct / fullplain → closedbook / L1 / L2)。
各臂对 `--out` 断点续跑(按 `question_id` 去重),中途被外部杀掉可原命令续跑,不重复计费。

---

## 八、产物文件

| 文件 | 内容 |
|---|---|
| `scripts/lb_reader_arm_b33k.py` | 33-K 读者器副本(新增 `gemini:<model>` 分支 / `--uids` / `--uid-stride` / `usage_meta` 落盘) |
| `scripts/b33k_stats.py` | 逐臂 acc + Wilson + 配对符号检验 + **144 链簇自助 CI** + 逐题美元 |
| `scripts/b33k_summarize.py` | 单文件快查(含 thoughts token、空答、`MAX_TOKENS` 计数) |
| `results/b33k_gemini36f_smoc_v24.jsonl` | 576 行 |
| `results/b33k_gemini36f_ledgerplain_v24.jsonl` | 576 行 |
| `results/b33k_gemini36f_direct_v24.jsonl` | 576 行 |
| `results/b33k_gemini36f_fullplain_v24_s2.jsonl` | 288 行(`--uid-stride 2`) |
| `results/b33k_gemini36f_closedbook_v24.jsonl` | 576 行 |
| `results/b33k_gemini36f_fullplain_L1.jsonl` | 40 行 |
| `results/b33k_gemini36f_fullplain_L2.jsonl` | 40 行 |
| `results/opt_batch33_K_gemini_verdict.md` | 本判决 |

对照用既有归档(本轮只读、未改动):`results/b33B_merged_v24.jsonl`(haiku smoc v2.4 90.45)、`results/b33_direct_v24oai_shard*.jsonl`(haiku direct v2.4 48.26)、`results/b33A_smwplain.jsonl`(haiku fullplain 53.47)、`results/wsc_v2_ledgerplain_haiku.jsonl`(75.35)、`results/wsc_v2_*_gpt5mini.jsonl`(gpt 五臂)、`results/b27_full_{haiku,gpt}_L{1,2}.jsonl`(长店对照)。

---

## 九、成本

| 项 | 金额 | 口径 |
|---|---:|---|
| Gemini 读者侧(2,672 次调用) | **$15.767** | 逐行 usage 实测 × 官方 promo 单价 $0.75 / $3.75 |
| 判官侧(2,672 次 opus-5) | **$8.224** | 实测均价 $0.003078/次 × 行数(非本轮逐行实测,见 §六③) |
| 跑前探针 + 被弃的默认档试跑 | ≈**$0.30** | 4 题×8 配置 token 画像 + 7 行默认档 smoc(已删) |
| direct 臂 OpenAI 嵌入 | ≈**$0.04** | text-embedding-3-small,144 店 + 576 查询 |
| **合计** | **≈$24.3** | **上限 $25,未超** |

---

## 十、建议入库口径(供总编 §三 / §四 更新)

1. §三 跨读者矩阵新增一行:`gemini-3.6-flash(推理,thinking=low)| 63.37 | 95.49(n=288)| 92.53 | 92.19 | 闭卷 5.73`。
2. §三"协议适配律"改写:三档 → **四档**,新增"gemini-3.6-flash **+0.35 n.s.**(簇 CI [−0.87,+1.56],±3pp 等价过线)= 中性";
   并把该律的表述从"协议对强推理读者是税"降级为"**协议效应按厂商而非按读者档位分布**(haiku +10.9 / gpt −3.5 / gemini 0 / qwen n.s.),F.1 协议不是通用增益也不是通用税"。
3. §三"读者双端定理"改写:富端收敛保留(新增 gemini 92.53 一档);**贫端"强读者救不了"加限定**——"在 claude/openai 两族成立(sonnet 41.49、gpt 42.88 均劣于 haiku 48.26),在 google 族反转(gemini 63.37,+15.1,p=3.7e-13)";结构总价随读者变强从 +42.2 收窄到 +29.2 一并入表。
4. §四 规模轴加第三条线:gemini 全文 L1 92.50 / L2 77.50(同 40 题),**"104K 上塌到 10-15"是 haiku 族性质而非长上下文普遍性质**;L2 上 gemini 与 gpt-5-mini 打平 77.50。
5. limitations 新增一条:**14K 小库上强读者整库直塞 95.49 > 账目 92.53(p=0.007)**——"结构优于原文"在小库对强读者不成立,QVF 在小库对强读者的主张应改为**成本主张**($0.0057 vs $0.0123/题)而非准确率主张。
