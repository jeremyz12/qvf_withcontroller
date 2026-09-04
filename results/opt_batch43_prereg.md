# 批 43 预注册 —— 读者矩阵(五读者 × 三臂),同一 140 题定死"强读者也不吃亏"

**写作时间**:2026-09-04,**在三个新读者的任何 API / 本地调用之前**落盘。
本文件此后只增不改;实跑结果一律写进 `results/opt_batch43_verdict.md`。

---

## 一、动机与待验证主张

论文主张是:**结构(QVF 账目)帮弱/中档读者,强读者读全文本来就不差**。
迄今这条主张只压在两个读者身上——haiku-4.5(弱/中档)与 claude-sonnet-5
(强)——都是 Anthropic 一家的模型族,且批 33-K 已经证明"协议适配律"
在换厂商后不复现(gemini 中性,不是 haiku 的脚手架也不是 gpt 的税)。
两点撑不起"读者强度"这条轴的因果声称。本批把读者矩阵扩到五个:

| 读者 | 厂商 | 档位(先验,按 33-K 全文直读排名) | 状态 |
|---|---|---|---|
| claude-haiku-4-5 | Anthropic | 弱/中档,非推理 | 已有(批 35/36/38e),复用不重跑 |
| claude-sonnet-5 | Anthropic | 强,推理 | 已有(批 36b/38e),复用不重跑 |
| gpt-5-mini | OpenAI | 强,推理 | **本批新跑** |
| gemini-3.6-flash | Google | 强,推理(thinking_level=low) | **本批新跑** |
| qwen3:14b(本地 ollama) | 本地/零 API | 弱/中档,思考型,14B | **本批新跑** |

固定不变量(与既有两读者逐字同口径,保证五读者可同表比较):
- 题集 `results/b35_questions_sample36.jsonl`(140 题 / 36 链,四题型
  change_count/count_before/first_vs_last/longest_tenure)。
- 语料 `data/wikistate_full_ALL_v24.json`(v2.4)。
- 账目主店 `results/wt_cards_v47skf`(项目当前最优账目店,36 链)；
  预算允许则账目臂在 `results/wt_cards_v45`(论文主表用店,144 链但本
  批只取同 36 链)上再跑一遍,作为对照,不作为主判据来源。
- 判官:`qvf.judge.ClaudeJudge()`(`claude-opus-5`,冻结代码零改动)。

---

## 二、三臂定义(与既有两读者的产物逐字同口径)

| 臂 | 跑批器 | 提示词框定 | 备注 |
|---|---|---|---|
| **direct**(top-10 检索) | `scripts/lb_reader_arm_b43.py --arm direct`(direct 分支逐字复制自 `scripts/lb_reader_arm_b36b.py`) | `ext_direct_arm.READER_SYSTEM` + top-10 稠密检索摘录 | `QVF_EMBED_BACKEND=openai`(与既有两读者同嵌入器) |
| **plainctx**(全文裸读) | 同上 `--arm plainctx`(提示词模板逐字复制自 `scripts/b36_plain_fullctx.py` 的 `PLAINCTX_SYSTEM`/`PLAINCTX_USER`,该原件本身只认 anthropic,本批新脚本把它扩到 openai/gemini/ollama 三个读者,模板一个字不改) | "You are a helpful assistant." + 全量誊录(`repro_batch3.render_transcript`) | 三个新读者实测该 36 链誊录 chars: min 49,906 / median 51,829 / mean 52,075 / max 53,980 |
| **smoc**(QVF 账目 + F.1 协议) | 同上 `--arm smoc`(逐字复制自 `lb_reader_arm_b36b.py`) | `repro_batch3.SMW_PROMPT` + 账目誊录(`render_card_ledger`) | `--cards-dir results/wt_cards_v47skf`(主),`results/wt_cards_v45`(预算允许的对照) |

新脚本 `scripts/lb_reader_arm_b43.py`(本批新增,三份原件——`lb_reader_arm_b33k.py`
的 openai/gemini/ollama 三支 call_reader、`lb_reader_arm_b36b.py` 的 direct/smoc
提示词构造、`b36_plain_fullctx.py` 的 plainctx 两个模板——均未改动,只做零改写
的合并 + 纯增量扩展,增量逐条见脚本头注释)。

### 2.1 已知的一个技术偏差(冒烟阶段发现,跑批前修正,记录在案)

qwen3:14b 是思考型本地模型。plainctx 臂 36 链誊录中位数 ~52K 字符
(实测 `prompt_eval_count` 中位数约 1.28 万 token)。原有 ollama 分支
(`lb_reader_arm.py`/`b33k`/`b36b`)把 `num_ctx` 写死 **12288**、
`num_predict` 写死 **1200**——两者都不够:12288 < 誊录本身的 token 数,
会截断上下文；冒烟测试(`longest_tenure` 题型)在 `num_predict=4096` 上
实测 **命中 `stop=length`、思考耗尽全部预算、可见答案空字符串**
(3 题冒烟中的 1 题)。补测 `num_predict=10000` 该题正常收敛于
2,554 token(思考 + 正文)。故本批对 qwen3:14b 的 plainctx 臂使用
`--num-ctx 24576 --num-predict 8192`(GPU 冒烟确认 RTX 5080 16GB 在该
配置下模型 + KV cache 仍 100% 常驻显存,13GB/16GB,未溢出到 CPU);
direct/smoc 两臂誊录短(实测 in-token 875~3,060),沿用
`--num-ctx 20480 --num-predict 4096`(对齐既有 qwen3:14b 探针60"思考 +
4096 预算"配置,`results/QVF_results_compendium_20260830.md` 第47行)。
这是跑批前发现并修正的口径问题,不是跑批后挑参数——三个 API 读者
(gpt-5-mini/gemini-3.6-flash,含既有 haiku/sonnet-5)冒烟未见此问题
(`max_completion_tokens=4000` / `max_output_tokens=8192` 均未触顶)。

---

## 三、预注册假设(三条,判据在跑之前定死)

### H1 —— 账目对每个读者都是两位数结构总价

**判据**:五个读者里,**每一个**都满足 `smoc(v47skf) − direct ≥ 15pp`。

**证否条件**:只要有一个读者的 `smoc − direct < 15pp`,H1 即被否定
(不要求全否,记"N/5 读者过线"并点名哪个读者、差多少)。

**已有基线(批 35/36/38e,复用不重跑,140 题同口径)**:

| 读者 | smoc(v47skf) | direct | 结构总价 | 过 15pp? |
|---|---:|---:|---:|---|
| haiku-4.5 | 93.6 | 49.3 | **+44.3** | 是 |
| claude-sonnet-5 | 95.0 | 70.7 | **+24.3** | 是 |

两个已有读者都过线,且都有余量(sonnet-5 余量最小,+24.3 距 15pp 门槛还有
9.3pp 缓冲)。三个新读者是否复现是本批唯一悬置的部分。

### H2 —— 账目减全文裸读的差距随读者强度单调递减

**判据**:把五读者按各自 plainctx(全文裸读)分数从低到高排序(即由弱到
强),`smoc(v47skf) − plainctx` 这一列**单调不增**(允许相邻两点打平在
等价带内,即 |差之差| ≤ 3pp 记平,不破单调性;出现真实逆序 > 3pp 记
"违反单调性于第 k 名")。

**已有基线**:

| 读者(按 plainctx 分数排序) | plainctx | smoc(v47skf) | 差距(smoc−plainctx) |
|---|---:|---:|---:|
| haiku-4.5(弱/中档,#1) | 70.0 | 93.6 | **+23.6** |
| claude-sonnet-5(强,#2 暂列) | 87.9 | 95.0 | **+7.1** |

两点定不出"单调"(至少需要 3 个点才能谈论趋势是否被打破),本批三个新
读者插入这条序列后才真正检验 H2。**证否条件**:五点序列里出现任何一次
相邻差距的"差之差"> 3pp 的真实逆序(即弱读者差距反而更小、强读者差距
反而更大)。

### H3 —— 账目臂本身的分数对读者不敏感(< 5pp 跨读者变差)

**判据**:五个读者的 `smoc(v47skf)` 分数,`max − min < 5pp`。

**已有基线**:haiku 93.6、sonnet-5 95.0,极差 **1.4pp**(远在 5pp 内)。

**证否条件**:五读者极差 ≥ 5pp,即记 H3 被否定,并点名把极差拉大的是
哪个读者(读者矩阵设计的本意就是揪出"结构本身也认读者"的反例——
qwen3:14b 作为唯一非推理弱本地模型最可能是那个反例,批 33-K 附表里
qwen3:14b 探针60的 smoc 分数是 80.0,若在本题集上复现类似量级,H3
大概率被否定;此处不预判,留给实跑)。

---

## 四、次要观测量(不设判据,只照实报)

- gemini-3.6-flash 的"协议适配律"效应(smoc − ledgerplain,若时间/预算
  允许追加 ledgerplain 臂)是否在**本店(v47skf)**上复现批 33-K 的"中性"
  判决(该判决在 v44clean 店上得出,店不同,不能直接认定复现)。
- v45 店(预算允许时)与 v47skf 店的账目臂差距,三个新读者是否重复
  haiku/sonnet-5 已知的"v47skf ≥ v47sk ≥ v47s ≥ v45"排序。
- 五读者 × 三臂矩阵的 $/题、token、延迟(gpt-5-mini $0.25/$2.00 每
  Mtok、gemini-3.6-flash $0.75/$3.75 每 Mtok promo 价——见
  `results/opt_batch33_K_gemini_verdict.md` §一——本判决沿用同价目;
  qwen3:14b 本地零 API 成本,只记延迟)。
- qwen3:14b 逐题 `stop_reason` 分布(截断率),因为它是唯一非 API 读者、
  唯一可能真正撞到 token 预算上限的读者。

---

## 五、预算与执行顺序

- API 花费上限:读者侧(gpt-5-mini + gemini-3.6-flash 之和)$6.00,
  判官花费不计入此闸(项目口径:判官另计)。冒烟测试(2 读者 × 3 臂 ×
  3 题 = 18 次调用)已实跑,花费 < $0.10,计入下方 §六成本表但不计入
  正式九路读者臂产物(冒烟产物落在 scratchpad,不进 `results/b43_*`)。
- 执行顺序:三个新读者的核心九路(direct/plainctx/smoc(v47skf) ×
  gpt-5-mini/gemini-3.6-flash/qwen3:14b)先行;v45 对照臂(三读者)与
  gemini ledgerplain 协议探针为预算/时间允许下的追加项,不影响 H1–H3
  判决(H1–H3 判据只引用 v47skf)。
- 产物命名:`results/b43_<arm>_<reader>.jsonl`
  (`<arm>` ∈ {direct, plainctx, smoc};v45 对照臂命名
  `results/b43_smoc_v45_<reader>.jsonl`)。

---

## 六、既有基线复用清单(不重跑,本批直接读取)

| 读者 | direct | plainctx | smoc(v47skf) |
|---|---|---|---|
| haiku-4.5 | `results/b35_direct.jsonl` | `results/b36_plainctx_haiku-4-5.jsonl` | `results/b38e_smoc_v47skf_haiku-4-5.jsonl` |
| claude-sonnet-5 | `results/b36b_direct_sonnet5.jsonl` | `results/b36_plainctx_sonnet-5.jsonl` | `results/b38e_smoc_v47skf_sonnet-5.jsonl` |

四条文件已核过:与 `results/b35_questions_sample36.jsonl` 140 qid 交集
= 140(全覆盖),acc 分别为 haiku direct 49.3 / plainctx 70.0 / smoc
93.6;sonnet-5 direct 70.7 / plainctx 87.9 / smoc 95.0(见本文件 §三
两表,复算自 `scripts/b33A_score.py` 的 `load`/`acc`)。
