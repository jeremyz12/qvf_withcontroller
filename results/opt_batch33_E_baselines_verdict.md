# 批 33-E 判决:更强检索基线(E1 交叉编码重排 / E2 TempRALM 时间融合)

预注册:`results/opt_batch33_prereg.md` §33-E。判据 E 写在跑前:
**若任一基线把 direct 抬 ≥ 10pp,结构总价改按最强基线报。**
参照臂口径:`results/ladder_decontamination_20260902.md` §四(direct 的隐藏配置 = 嵌入器)。

跑于 2026-09-02,语料 v2.4(`data/wikistate_full_ALL_v24.json`)、题集
`data/wsc_s5_v2.jsonl`(576 题,四型各 144)。

---

## 一、判决(三句)

1. **判据 E 未触发,且方向相反。** 两条"更强基线"都**显著低于** direct:
   E1 交叉编码重排 **35.07**(−13.19pp,McNemar b/c=128/52,p=1.4e-08);
   E2 TempRALM 时间融合 **23.44**(−24.83pp,b/c=161/18,p=6.7e-30)。
   **结构总价维持按 direct 定价:90.45 − 48.26 = +42.19pp,不改。**
2. **猜想"直读臂弱是因为检索弱"被否定。** 稠密 top-50 候选池已装下
   **97.7%** 的金 state_span(93.6% 的题整条链在池内),而把池交给
   bge-reranker-v2-m3 重排后 top-10 召回**掉到 0.573**——重排器不是没找到,
   是把找到的扔了。证据可用性不是直读臂的约束。
3. **机制被指认:重排器对本卷问题整体判"不相关"。** 576 题里 **99.8%**
   的 top-1 交叉编码分 < 0.1,**87.5%** < 0.01(中位数 0.00163)。
   聚合型问题("我换过几次雇主")在语料里没有任何一条"回答"它的段落,
   段落级 relevance 模型于是在地板上排序 = 噪声,毁掉稠密序的信号。

---

## 二、口径(全部冻结,与参照臂逐项对齐)

| 项 | 取值 |
|---|---|
| 语料 | `data/wikistate_full_ALL_v24.json`(144 条目 / 23,754 记忆单元) |
| 题集 | `data/wsc_s5_v2.jsonl`(576;change_count / count_before / first_vs_last / longest_tenure 各 144) |
| 嵌入器 | `QVF_EMBED_BACKEND=openai` → `text-embedding-3-small`(三臂共用一份缓存) |
| 读者 | `anthropic:claude-haiku-4-5`,temperature 0,max_tokens 800 |
| 提示词 | `READER_SYSTEM` + `reader_content`(逐字取自 `scripts/ext_direct_arm.py`,与 direct 臂同一函数对象) |
| 呈现顺序 | 选中集合按记忆流原序(时序),= `OllamaDenseRetriever.retrieve` 的 `sorted(top)` 口径 |
| 判官 | `qvf.judge.ClaudeJudge`,`claude-opus-5`(默认,未覆盖) |
| 参照 direct | `results/b33_direct_v24oai_shard*.jsonl` = **48.26**(278/576) |
| 并行 | ≤4 进程 |

**三臂唯一的差别是"选了哪 10 条"。** 为保证这一点,把检索从跑批器里剥出来:
`scripts/b33e_retrieval.py` 离线产出"每题选中记忆 id 有序表"(计划文件),
`scripts/lb_reader_arm_b33.py --arm plan` 照单渲染。原件
`scripts/lb_reader_arm.py` 未改动(按令冻结);b33 副本的增量只有三处
(plan 臂 / 判官 token 落盘 / 结果复用),已在文件头列明。

### 两道前置核验(都过)

- **缓存 = 现场**:用嵌入缓存复算的稠密 top-10 与现场 `OpenAIDenseRetriever`
  逐题比对 **20/20 完全一致**(`--mode verify`)。
- **plan 臂 = direct 臂**:把**稠密**计划喂给 plan 臂重跑 12 题,与存档 direct
  行比对——**判决一致 12/12,答案逐字节一致 10/12**(其余 2 条为同温度下的采样噪声)。
  文件:`results/b33e_dense_equivcheck.jsonl`。

---

## 三、E1 · bge-reranker-v2-m3 交叉编码重排(稠密 top-50 → top-10)

| 臂(576 题) | acc | Δdirect | McNemar b/c | p | 簇自助 95%CI |
|---|---|---|---|---|---|
| direct(参照) | 48.26 | — | — | — | — |
| **E1 重排** | **35.07**(202/576) | **−13.19** | 128/52 | 1.40e-08 | [−17.53, −8.51] pp |

逐题型(配对 McNemar,精确二项双尾):

| 题型 | E1 | direct | Δ | b/c | p |
|---|---|---|---|---|---|
| change_count | 13.89 | 34.72 | −20.83 | 44/14 | 1.0e-04 |
| count_before | 13.19 | 43.75 | −30.56 | 51/7 | 2.4e-09 |
| **first_vs_last** | **87.50** | 80.56 | **+6.94** | 10/20 | 9.9e-02 |
| longest_tenure | 25.69 | 34.03 | −8.33 | 23/11 | 5.8e-02 |

**唯一为正的是 first_vs_last(+6.94,p=0.099,未过 0.05)**——那类题只要找到首尾
两条,段落级 relevance 恰好对口;三个聚合型全线塌陷,因为它们要的不是"最相关
的一条",是"整条链一条不漏"。这与 `results/token_matched_prereg.md` 的分层结论
同向(预算/检索类干预只在"找对记录"型有效)。

## 四、E2 · TempRALM 式时间融合

打分:`score = cos(q, m) + alpha · exp(−|Δdays| / tau)`,
Δdays = `session_date` − 问题里的 `(Today is X.)` 日期;在**全库**记忆上打分
(嵌入已缓存,全量与池内同价)。

### 4.1 开发格(96 题 = `questions[0::6]`,预注册指定)

| alpha | tau | acc | Δdirect(该 shard 37.50) | b/c | p |
|---|---|---|---|---|---|
| **0.3** | **365** | **21.88** | **−15.62** | 19/4 | 2.6e-03 |
| 0.3 | 1825 | 15.62 | −21.88 | 27/6 | 3.2e-04 |
| 0.5 | 365 | 18.75 | −18.75 | 22/4 | 5.3e-04 |
| 0.5 | 1825 | 11.46 | −26.04 | 29/4 | 1.1e-05 |
| 1.0 | 365 | 16.67 | −20.83 | 21/1 | 1.1e-05 |
| 1.0 | 1825 | 9.38 | −28.12 | 30/3 | 1.4e-06 |

**网格在两个方向上单调**:固定 tau,acc 随 alpha 单调降;固定 alpha,acc 随 tau
单调降。**族内最优点在边界 alpha→0**,而 alpha=0 **就是 direct 本身**。
即:在本卷上,TempRALM 的时间项只能减分,"最佳配置"是退化到不做融合。
定盘取网格内最优 **alpha=0.3, tau=365**(按预注册执行)。

### 4.2 定盘后全量 576

| 臂 | acc | Δdirect | b/c | p | 簇自助 95%CI |
|---|---|---|---|---|---|
| **E2 alpha=0.3 tau=365** | **23.44**(135/576) | **−24.83** | 161/18 | 6.74e-30 | [−28.65, −20.83] pp |

| 题型 | E2 | direct | Δ | b/c | p |
|---|---|---|---|---|---|
| change_count | 12.50 | 34.72 | −22.22 | 39/7 | 1.8e-06 |
| count_before | 21.53 | 43.75 | −22.22 | 32/0 | 4.7e-10 |
| first_vs_last | 27.78 | 80.56 | −52.78 | 77/1 | 5.2e-22 |
| longest_tenure | 31.94 | 34.03 | −2.08 | 13/10 | 6.8e-01 |

first_vs_last 掉 52.78pp 是构造性的:近因加权把"第一个值"所在的早期会话挤出
top-10,而那正是该题必需的一半。

---

## 五、检索侧诊断($0,零 API):金证据召回

金证据 = `chain[i].state_span` 所在的记忆条(542/542 条全部可锚定)。

| 检索计划 | recall@10 | 整条链全进 top-10 的题比例 |
|---|---|---|
| 稠密 top-50(E1 候选池) | **0.977** | **93.6%** |
| 稠密 top-10(= direct) | 0.788 | 57.6% |
| E1 重排 50→10 | 0.573 | 35.6% |
| E2 alpha0.3 tau365 | 0.501 | 21.4% |

**准确率与召回同序**(0.977 未跑读者;0.788→48.26 / 0.573→35.07 / 0.501→23.44)。
两条更强基线都是**降召回**换来的,不是"更强",是**任务不匹配**。

### 交叉编码器为什么降召回:分数塌陷

576 题的 top-1 重排分:p50 = **0.00163**,p95 = 0.02166,max = 0.15966;
**99.8% 的题 top-1 < 0.1,87.5% < 0.01。** 即 bge-reranker-v2-m3 认为
**没有任何一条记忆与问题相关**。在地板上的排序不携带信息,于是它用噪声序
替换了带信息的余弦序。这是"通用 QA 重排器 ≠ 状态链检索器"的直接证据,
可作论文 limitations 的一条外部基线注记。

### 与既有"预算轴"证据的接口

`results/token_matched_prereg.md`(418 题、旧语料)已实测更深检索:
k=10 → 48.33 / k=24 → 51.67(n.s.)/ k=40 → 54.55(+6.22,p<0.05),曲线近乎平坦。
本轮把这条补齐到**证据侧**:k=50 的池已含 97.7% 金证据,
**"看得见"早就不是瓶颈,"数得对"才是**。两条独立轴指向同一处。

---

## 六、成本 / token / 延迟(全部由 usage 字段实测)

价目:haiku-4-5 读者 $1/M in、$5/M out;opus-5 判官 $5/M in、$25/M out;
text-embedding-3-small $0.02/M。

| 臂(576) | 读者 in tok | 读者 out | 判官 in+out | $/题 | 读者延迟 | 检索延迟 | 臂总 $ |
|---|---|---|---|---|---|---|---|
| direct(参照) | 877 | 86 | —(存档未落盘) | 0.00131(仅读者) | 1.67 s | ≈0(嵌入已摊销) | 0.754(仅读者) |
| **E1 重排** | 1,031 | 84 | 200+83 | **0.00451** | 1.73 s | **5.50 s/题(CPU)** | 2.598 |
| **E2 融合** | 903 | 82 | 198+88 | **0.00450** | 1.66 s | <0.002 s/题 | 2.592 |

- E1 的检索延迟 = 交叉编码器整轮 **3,167 s**(576 题 × 50 候选 = 28,800 对,
  9.1 对/秒),摊到每题 5.50 s——**比读者调用本身贵 3.2 倍**,却买到 −13.19pp。
- 嵌入侧一次性:语料 1,714,923 tok + 问题 16,848 tok = **$0.0346**(三臂共用)。

### 本轨实际花费

| 项 | $ |
|---|---|
| 读者 1,572,549 in / 136,994 out(1,644 次调用) | 2.258 |
| 判官 329,545 in / 143,382 out | 5.232 |
| 嵌入 | 0.035 |
| **usage 字段可核算合计** | **7.524** |
| 判官系统提示的缓存读(470 tok × 1,644,`ClaudeJudge` 未落盘 cache_read) | ≈ +0.39(估) |
| **总计** | **≈ 7.9 / 上限 15** |

---

## 七、限定与已知缺陷(不得省略)

1. **E1 跑在 CPU,不是 GPU。** 机器有 RTX 5080(nvidia-smi 可见),但环境里的
   torch 是 **2.9.1+cpu**(`torch.cuda.is_available() == False`),
   `sentence_transformers` 6.0.0。为不在跑批中途改动他轨正在使用的环境,
   本轨**未**安装 CUDA 版 torch,整轮在 16 线程 CPU 上跑完(3,167 s)。
   **这只影响延迟一栏,不影响任何准确率数字**(同一权重、同一 max_length=384、
   确定性前向)。若要把 E1 的延迟列做成可发表口径,须在 GPU 上重跑计时。
2. **预注册的开发格 shard 题型不均衡。** `questions[0::6]` 因题目按"条目 × 四型"
   排布,恰好只含 **change_count 48 + longest_tenure 48**,不含另两型。
   E2 的定盘因此是在 2/4 题型上选的。缓解:网格在两个超参方向上都单调,
   最优点落在边界(退化为 direct),换题型不会把最优点从边界推回格内;
   且全量 576 复核已给出四型完整结果。**但"dev 选参"这一步在本轨严格说只覆盖两型**。
3. **判官侧成本被 usage 低估约 $0.39**:`ClaudeJudge` 只累加 `input_tokens`/
   `output_tokens`,系统提示走 ephemeral 缓存读,不进这两个字段。已在上表单列。
4. **结果复用通道在本轨没被触发**(`reused_from` 全 0):E1/E2 的 top-10 与
   direct 的重合极低,`--cache-from` 未命中任何一行。所有 1,644 行都是真调用。
5. **只此语料。** 结论"通用重排器/时间融合在状态链聚合题上是负增益"限定在
   WikiState v2.4 合成域,不外推到自然语料或非聚合题型。
6. **未跑 alpha=0 一格**——它按定义等于 direct 臂,用存档参照替代;若审稿要求
   格内自洽,可用同一 plan 通道零成本补跑(计划文件即 `b33e_plan_dense.jsonl`)。

---

## 八、精确复现命令

`SP` = 嵌入缓存目录(本轮用会话 scratchpad;换目录不影响结果,缓存可重建)。

```bash
export SP="<scratchpad>"

# 0) 共享嵌入缓存(一次,$0.0346,15 s)
QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/b33e_embed_cache.py \
  --data data/wikistate_full_ALL_v24.json --out "$SP/b33e_emb_v24.npz" --workers 4

# 0b) 前置核验:缓存 top-10 == 现场检索 top-10
QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/b33e_retrieval.py --mode verify \
  --emb "$SP/b33e_emb_v24.npz" --qemb "$SP/b33e_qemb_v24.npz" --n 20

# 1) 检索计划
PYTHONUTF8=1 python scripts/b33e_retrieval.py --mode dense  --topk 10 \
  --emb "$SP/b33e_emb_v24.npz" --qemb "$SP/b33e_qemb_v24.npz" --out results/b33e_plan_dense.jsonl
PYTHONUTF8=1 python scripts/b33e_retrieval.py --mode dense  --topk 50 \
  --emb "$SP/b33e_emb_v24.npz" --qemb "$SP/b33e_qemb_v24.npz" --out results/b33e_plan_dense50.jsonl
PYTHONUTF8=1 HF_HUB_DISABLE_PROGRESS_BARS=1 python scripts/b33e_retrieval.py --mode rerank \
  --pool 50 --topk 10 --threads 16 \
  --emb "$SP/b33e_emb_v24.npz" --qemb "$SP/b33e_qemb_v24.npz" --out results/b33e_plan_rerank.jsonl
for A in 0.3 0.5 1.0; do for T in 365 1825; do
  PYTHONUTF8=1 python scripts/b33e_retrieval.py --mode temporal --alpha $A --tau $T --topk 10 \
    --shard 0/6 --emb "$SP/b33e_emb_v24.npz" --qemb "$SP/b33e_qemb_v24.npz" \
    --out "results/b33e_plan_temporal_a${A}_t${T}_dev.jsonl"; done; done
PYTHONUTF8=1 python scripts/b33e_retrieval.py --mode temporal --alpha 0.3 --tau 365 --topk 10 \
  --emb "$SP/b33e_emb_v24.npz" --qemb "$SP/b33e_qemb_v24.npz" \
  --out results/b33e_plan_temporal_a0.3_t365_full.jsonl

# 2) 读者 + 判官(≤4 路并行;S 为 shard)
QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/lb_reader_arm_b33.py \
  --reader anthropic:claude-haiku-4-5 --arm plan --plan results/b33e_plan_rerank.jsonl \
  --data data/wikistate_full_ALL_v24.json --questions data/wsc_s5_v2.jsonl \
  --shard $S/6 --out "results/b33e_rerank_shard${S}.jsonl"
# E2 dev 六格:--plan results/b33e_plan_temporal_a${A}_t${T}_dev.jsonl --shard 0/6
#              --out  results/b33e_temporal_a${A}_t${T}_dev.jsonl
# E2 全量:    --plan results/b33e_plan_temporal_a0.3_t365_full.jsonl --shard $S/6 (S=1..5)
#              --out  results/b33e_temporal_best_shard${S}.jsonl
# plan 臂等价性核验:--plan results/b33e_plan_dense.jsonl --shard 0/48
#              --out  results/b33e_dense_equivcheck.jsonl

# 3) 汇总与诊断
PYTHONUTF8=1 python scripts/b33e_report.py \
  --arm "E1 bge-reranker-v2-m3 (50->10)=results/b33e_rerank_shard*.jsonl" \
  --arm "E2 TempRALM a=0.3 tau=365=results/b33e_temporal_best_shard*.jsonl,results/b33e_temporal_a0.3_t365_dev.jsonl"
PYTHONUTF8=1 python scripts/b33e_recall.py \
  --plan "dense top-10=results/b33e_plan_dense.jsonl" \
  --plan "dense top-50=results/b33e_plan_dense50.jsonl" \
  --plan "E1 rerank=results/b33e_plan_rerank.jsonl" \
  --plan "E2 a0.3 t365=results/b33e_plan_temporal_a0.3_t365_full.jsonl"
```

## 九、文件清单

新增脚本(四份,均在 `scripts/`):

| 文件 | 作用 |
|---|---|
| `scripts/b33e_embed_cache.py` | 全库 text-embedding-3-small 嵌入缓存(三臂共用底座) |
| `scripts/b33e_retrieval.py` | 检索计划生成 + 缓存/现场一致性核验(dense / rerank / temporal / verify) |
| `scripts/lb_reader_arm_b33.py` | `lb_reader_arm.py` 副本 + plan 臂 + 判官 token 落盘 + 结果复用 + shard |
| `scripts/b33e_report.py` / `scripts/b33e_recall.py` | 汇总(acc/题型/McNemar/簇 CI/$/延迟)/ 金证据召回诊断 |

结果与计划(均在 `results/`):

| 文件 | 内容 |
|---|---|
| `b33e_plan_dense.jsonl` / `b33e_plan_dense50.jsonl` | 稠密 top-10 / top-50 计划 |
| `b33e_plan_rerank.jsonl` | E1 计划(含逐题 top-10 重排分) |
| `b33e_plan_temporal_a{0.3,0.5,1.0}_t{365,1825}_dev.jsonl` | E2 开发格六份计划 |
| `b33e_plan_temporal_a0.3_t365_full.jsonl` | E2 定盘后全量计划 |
| `b33e_rerank_shard{0..5}.jsonl` | **E1 结果 576 题** |
| `b33e_temporal_a{...}_t{...}_dev.jsonl` | E2 开发格六份结果(各 96) |
| `b33e_temporal_best_shard{1..5}.jsonl` | E2 定盘全量结果(480;shard0 用上表 a0.3_t365_dev) |
| `b33e_dense_equivcheck.jsonl` | plan 臂 vs direct 臂等价性核验(12 题) |

参照臂(未改动):`results/b33_direct_v24oai_shard{0..5}.jsonl`。
原件 `scripts/lb_reader_arm.py`、`scripts/ext_direct_arm.py` 均未修改。
