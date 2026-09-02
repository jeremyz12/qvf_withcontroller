# 批 33-D 判决:规模轴 L2(30 店 / n=120)——账目在 104K 库上掉 30pp,槽位投影反超全账目

日期 2026-09-02。预注册见 `results/opt_batch33_prereg.md` §33-D;上游 `results/ladder_decontamination_20260902.md` §三及其 $1 探针补。
读者 `anthropic:claude-haiku-4-5`(temperature=0,max_tokens=800),判官 ClaudeJudge(`claude-opus-5`,冻结),
建卡器 `scripts/wt_qvf_prototype.py --phase write`(OWNER_GATE=0,`QVF_CARD_TEMP0` 默认 1),并行度 4。
计价:haiku $0.80/M in、$4.00/M out;gpt-5-mini $0.25/M in、$2.00/M out;逐行 usage token 求和,不用估算。

---

## 零、三条判决

1. **D1 被否定(点估计),但不是硬否定。** 30 店 L2 上全账目 smoc = **54.2**,同题小库(L0)= **84.2**,
   Δ = **−30.0pp**,越过预注册的 −20pp 闸;店级簇自助 95% CI **[−40.8, −19.2]** 的上界恰在 −20 之外 0.8pp,
   故判为"点估计判负、区间不判决"。批 27 的 10 店探针 80.0 **不能代表 L2**——它是一个系统性偏易的子集
   (同 10 店在小库上 smoc 95.0 / 投影 100.0,而 30 店口径只有 84.2 / 81.7)。
2. **D2、D3 被证实。** 账目读取 **20,855 tok**(闸 25K)通过;$/题对 haiku 全文 **4.47×**(投影 **9.26×**)通过。
   对 gpt-5-mini 全文只有 **1.37×**(投影 2.62×),且准确率上两者不可分——**"5× 成本优势"在 104K 上确定撤回**。
3. **新结论:槽位投影在 L2 上不再是全账目的廉价近似,而是更好的读法。** 投影 61.7 vs 全账目 54.2(+7.5,
   McNemar b/c=11/20,p=0.15;簇 CI [−4.2, +20.0]),同时读取量只有 42%。D1 在投影臂上**恰好通过**(−20.0pp)。
   这与 10 店探针给出的"投影 75.0 < 全账目 80.0"方向相反,原因是探针子集偏易且样本仅 40。

---

## 一、主表(30 店 × 4 题 = 120;L2 ≈ 440K 字符 ≈ 104K tok/店)

| 臂 | n | 准确率 | Wilson 95% | 均输入 tok | 均输出 tok | $/题 | 延迟 s |
|---|---|---|---|---|---|---|---|
| smoc(全账目) | 120 | **54.2** | [45.3, 62.8] | 20,855 | 546 | 0.0189 | 6.36 |
| **槽位投影**(`QVF_LEDGER_VIEW=slot`) | 120 | **61.7** | [52.7, 69.9] | **8,800** | 518 | **0.0091** | 5.84 |
| haiku 全文(fullplain) | 120 | **7.5** | [4.0, 13.6] | 103,780 | 340 | 0.0844 | 5.79 |
| gpt-5-mini 全文(批 27 存档,仅原 15 店 60 题) | 60 | 65.0 | — | 92,554 | 1,358 | 0.0259 | 19.31 |

逐题型(对/总):

| 臂 | change_count | count_before | first_vs_last | longest_tenure |
|---|---|---|---|---|
| smoc 全账目 | 15/30 | 14/30 | 17/30 | 19/30 |
| 槽位投影 | 19/30 | 17/30 | 19/30 | 19/30 |
| haiku 全文 | 2/30 | 1/30 | 4/30 | 2/30 |

配对 McNemar(同 120 题):

| 对比 | b/c | p | 店级簇自助 Δ 95% CI |
|---|---|---|---|
| 投影 vs 全账目 | 11/20 | 0.15 | +7.5 [−4.2, +20.0] |
| 全账目 vs haiku 全文 | 58/2 | 3.2e-15 | +46.7 [+34.2, +59.2] |
| 投影 vs haiku 全文 | 67/2 | 8.2e-18 | — |
| smoc @原15店 vs gpt-5-mini 全文 | 9/11 | 0.82 | — |
| 投影 @原15店 vs gpt-5-mini 全文 | 11/8 | 0.65 | — |
| haiku 全文 @原15店 vs gpt-5-mini 全文 | 0/33 | 2.3e-10 | — |

## 二、与同题小库(L0,v43 店)对照——衰减率

| 臂 | L0 acc | L0 in tok | L0 $/题 | L2 acc | L2 in tok | Δacc(簇 CI) | tok 倍数 |
|---|---|---|---|---|---|---|---|
| smoc 全账目 | 84.2 | 2,874 | 0.0043 | 54.2 | 20,855 | **−30.0** [−40.8, −19.2] | **7.26×** |
| 槽位投影 | 81.7 | 1,328 | 0.0030 | 61.7 | 8,800 | **−20.0** [−31.7, −9.2] | **6.62×** |
| haiku 全文 | —(小库无同臂存档) | — | — | 7.5 | 103,780 | — | — |

语料倍数 **7.4×**(L0→L2,承 `ladder_decontamination_20260902.md` §三口径)。**账目读取随库长增长的斜率 ≈ 语料斜率**(7.26× vs 7.4×),
不是"恒定 2.9K",也不是"比全文慢得多"——在本轮 30 店口径上账目读取几乎与语料同比例增长。
`ladder_decontamination_20260902.md` §三"读取量 6.8× / 准确率 −15"两个数都出自 10 店探针,**须按本表替换为 7.26× / −30.0**。

### 投影臂的真实机制:三成题目根本没投影成

槽位投影按 `slot`/`slot_class` 子串匹配挑行,命中 <2 行时**回退整本账目**。本轮 **36/120 题(9/30 店)回退**:

| 子集 | n | 投影 in tok | 投影 acc | 同题全账目 in tok | 同题全账目 acc | 同子集 L0 投影 in tok |
|---|---|---|---|---|---|---|
| 投影生效 | 84 | **2,266** | 72.6 | 19,487 | 65.5 | 701(**3.23×**) |
| 回退整本 | 36 | ≡ 全账目 | 36.1 | 同左 | 27.8 | — |

**判读**:投影一旦生效,104K 库上的读取量是 **2,266 tok**——与小库全账目(2,874)同量级,即"账目读取近似平坦"这句话
**只在投影生效的子集上成立**,代价是 30% 的题目投影不生效(槽位名不匹配),而这些题在两个臂上都最难(27.8 / 36.1)。
§7 的正确写法是"投影命中率 × 平坦读取 + 未命中回退",不是单一衰减率。

## 三、复现核对:批 27 的 10 店 smoc 探针不可逐字复现,已排除出头条

| 行 | 存档 | 本轮同配置重跑 | 判读 |
|---|---|---|---|
| smoc @10 店 40 题 | 80.0 @20,204 tok(`b27_smoc_L2probe.jsonl`,`repro_batch3.py --system smoc`,08-29) | **70.0 @22,130 tok**(`lb_reader_arm.py --arm smoc`) | b/c=7/3,p=0.344(准确率不可分);**输入 tok 逐店系统性 +7~12%**,原因未定位 |
| 槽位投影 @10 店 | 75.0 @9,020(`b33_smoc_L2probe_slot.jsonl`,09-02) | 单题探针 in=**1,576 = 存档 1,576** | **逐 token 一致**,存档行直接复用 |
| haiku 全文 @10 店 | 15.0 @103,815(`b27_full_haiku_L2.jsonl`,08-29) | 单题探针 in=**103,554 = 存档 103,554** | **逐 token 一致**,存档行直接复用 |

排查结论:卡片库文件(`results/wt_cards_b27_L2`,mtime 08-29 11:14–11:37,此后未改)与今日渲染器都正常——
**同一卡片库的投影视图今日逐 token 复现存档**,证明 `render_card_ledger` 与卡片本身都没变;
差异只出现在 08-29 那次 `repro_batch3` 全账目跑上(其 SMW_PROMPT、max_tokens、temperature 与今日逐字相同)。
**处理**:头条 smoc 的 120 行**全部来自本轮 `lb_reader_arm.py`**(10 店重跑 40 + 20 新店 80),存档 80.0 只作历史点列出,不入表。
投影与全文两臂的存档行(共 100 行)因逐 token 一致而复用。

**子集偏易的独立证据**(纯存档,$0):同 10 个 uid 在小库上 smoc 95.0 / 投影 100.0,而 30 uid 口径 84.2 / 81.7;
新建 15 店的 uid 在小库上就更难(smoc 80.0 / 投影 73.3,对原 15 店的 88.3 / 90.0)。**L2 上的分层与小库同向**:

| 臂 | 原 15 店(60 题) | 新 15 店(60 题) |
|---|---|---|
| smoc 全账目 | 61.7 @22,511 | 46.7 @19,198 |
| 槽位投影 | 70.0 @9,823 | 53.3 @7,777 |
| haiku 全文 | 10.0 @103,735 | 5.0 @103,825 |

新旧两半差 15pp 而两半的小库基线也差 8~17pp——**新建 15 店没有引入额外难度以外的系统偏差**;
店级「每店 4 题对几题」分布:smoc {0 题对:5 店, 1:6, 2:4, 3:9, 4:6},投影 {0:3, 1:4, 2:8, 3:6, 4:9}——失败仍聚集在少数店,不是逐题读者噪声。

## 四、判据逐条

| 判据 | 阈值 | 实测 | 判决 |
|---|---|---|---|
| D1 账目 acc ≥ 小库同题 −20pp | ≥ 64.2 | smoc **54.2**(Δ−30.0,簇 CI [−40.8,−19.2]) | **不通过**(点估计);区间上界 −19.2 含 −20,不构成硬否定 |
| D1(投影臂,附加) | ≥ 61.7 | 投影 **61.7**(Δ−20.0) | 恰好通过 |
| D2 账目读取 ≤ 25K tok | ≤ 25,000 | **20,855**(投影 8,800) | **通过** |
| D3 $/题 vs haiku 全文 ≥ 3× | ≥ 3× | **4.47×**(投影 9.26×) | **通过** |
| vs gpt-5-mini 全文(照报无阈值) | — | $/题 1.37×(投影 2.62×);acc 54.2/61.7 vs 65.0,配对 p=0.82 / 0.65 | 成本优势 1.4~2.6×,准确率不可分 |

## 五、须改的既有陈述

1. `ladder_decontamination_20260902.md` §三:"读取量 6.8×、准确率 −15" → **7.26×、−30.0**(30 店口径);
   "投影 −20(n=40 探针)" → 投影 −20.0(n=120,簇 CI [−31.7,−9.2])。
2. 同文 §三补表的 80.0 / 75.0 两格须标注"10 店偏易子集,30 店口径为 54.2 / 61.7"。
3. "账目恒定 2.9K" 已在 09-02 撤回;本轮进一步指出**平坦性只属于投影生效子集**(2,266 tok / 84 题),
   全账目在 L2 上按语料同比例增长。
4. "对 gpt-5-mini 全文 5× 成本优势" → **1.37×(全账目)/ 2.62×(投影)**,且准确率优势 +15 也不成立
   (30 店口径下 gpt-5-mini 只在原 15 店有存档,配对 p=0.82 / 0.65,不可分)。
5. 批 27 结论中凡引用 `b27_smoc_L2probe.jsonl` 80.0 的地方,须并注"本轮同配置重跑 70.0、输入 tok +9.5%、不可逐字复现"。

## 六、四象限

- **已知直接干**:建店 20 个、三臂补跑、复用逐 token 一致的存档行——已完成。
- **标注假设**:L2 由确定性填充构成(干扰会话来自他店、安全闸禁含任何店 state_span),
  新建 15 店与原 15 店同构造、同目标字符量(中位 440,827 vs 440,491;会话数 271 vs 272;锚点完好闸 0 违约、填充泄漏 0)。
- **主动补盲**:发现 `data/wikistate_long_L2.json` 只有 15 店(不是任务书假定的"≥30 个 uid 可选"),
  缺的 15 个必须新建;发现 10 店探针偏易;发现存档 smoc 探针不可复现;发现投影回退占 30%。
- **共同未知 → 最小实验**:(a) 08-29 全账目渲染为何比今日短 7~12%——建议对 `b27_smoc_L2probe` 逐题重渲染差分($0);
  (b) 投影回退的 9 店是否因槽位命名不一致(`slot_class` 缺失)——建议 `card_quality_eval` 四模式判写侧($0);
  (c) L1(160K)未跑,衰减曲线目前只有两点(L0、L2),第三点可把"斜率"从两点连线升为趋势(≈$8)。

## 七、成本与用时(全部来自逐行 usage token)

| 项 | 输入 tok | 输出 tok | 成本 |
|---|---|---|---|
| 建店 20 个(haiku 建卡) | 3,506,226 | 1,152,203 | **$7.41**($0.3707/店) |
| smoc 全账目 120 题(含 10 店重跑 40) | 2,502,544 | 65,478 | $2.26 |
| 槽位投影 80 题(新建 20 店) | 695,216 | 41,682 | $0.72 |
| haiku 全文 60 题(新建 15 店) | 6,229,516 | 21,279 | $5.07 |
| 复现探针 2 题 | 105,130 | 586 | $0.09 |
| **合计(读者 + 建店)** | | | **$15.55** |

判官 `claude-opus-5` 本轮新判 **262 次**,`ClaudeJudge` 不记 usage,**未计入上表**(如需入账须先给判官加 usage 记录)。
用时:建店 20 个并行 4 路约 **72 分钟**(单店 282–987 s,中位 647 s,均 2 批、0 次 batch FAILED);
三臂补跑(含 10 店重跑)并行 4 路,单题读者延迟 5.8–6.4 s,墙钟合计约 **15 分钟**(未逐秒记账)。

## 八、逐字命令与产出文件

### 语料扩建(确定性,$0)
```
PYTHONUTF8=1 python -u scripts/gen_wikistate_long_L2_b33.py
```
→ `data/wikistate_long_L2_b33.json`(30 店 = 原 `wikistate_long_L2.json` 15 店逐字节复制 + 新建 15 店,
RNG `random.Random(3327)`,目标 440,000 字符,干扰池 4,320 条,安全闸与批 27 逐字同一)。

### 建店(20 个,OWNER_GATE=0,并行 4 路)
```
PYTHONUTF8=1 QVF_CARD_OWNER_GATE=0 python -u scripts/wt_qvf_prototype.py --phase write \
  --data data/wikistate_long_L2_b33.json --cards-dir results/wt_cards_b33_L2 \
  --uids <shard i 的 5 个 uid 逗号列表>        # i = 0..3,见 scratchpad/b33d_shard{0..3}.txt
```

### 三臂(题源 `data/wsc_long_L1_questions.jsonl` = 120 题,覆盖全部 30 uid,与 L2 题集 60 行逐字节相同)
```
# smoc 全账目(20 新店 80 题;分片见 scratchpad/b33d_q_new20_s{0..3}.jsonl)
PYTHONUTF8=1 python -u scripts/lb_reader_arm.py --reader anthropic:claude-haiku-4-5 --arm smoc \
  --data data/wikistate_long_L2_b33.json --cards-dir results/wt_cards_b33_L2 \
  --questions scratchpad/b33d_q_new20_s$i.jsonl --out results/b33d_smoc_L2_new20_s$i.jsonl

# smoc 全账目(原 10 店 40 题重跑;分片见 scratchpad/b33d_q_old10_s{0..3}.jsonl)
PYTHONUTF8=1 python -u scripts/lb_reader_arm.py --reader anthropic:claude-haiku-4-5 --arm smoc \
  --data data/wikistate_long_L2_b33.json --cards-dir results/wt_cards_b27_L2 \
  --questions scratchpad/b33d_q_old10_s$i.jsonl --out results/b33d_smoc_L2_old10_repro_s$i.jsonl

# 槽位投影(20 新店 80 题)
PYTHONUTF8=1 QVF_LEDGER_VIEW=slot python -u scripts/lb_reader_arm.py --reader anthropic:claude-haiku-4-5 \
  --arm smoc --data data/wikistate_long_L2_b33.json --cards-dir results/wt_cards_b33_L2 \
  --questions scratchpad/b33d_q_new20_s$i.jsonl --out results/b33d_slot_L2_new20_s$i.jsonl

# haiku 全文(15 新店 60 题;分片见 scratchpad/b33d_q_new15_s{0..3}.jsonl)
PYTHONUTF8=1 python -u scripts/lb_reader_arm.py --reader anthropic:claude-haiku-4-5 --arm fullplain \
  --data data/wikistate_long_L2_b33.json \
  --questions scratchpad/b33d_q_new15_s$i.jsonl --out results/b33d_full_haiku_L2_new15_s$i.jsonl
```
(封装:`bash scripts/b33d_run_arms.sh smoc|slot|full`)

### 汇总
```
PYTHONUTF8=1 python -u scripts/b33d_scale_report.py
```

### 产出文件
- 语料:`data/wikistate_long_L2_b33.json`;生成器 `scripts/gen_wikistate_long_L2_b33.py`
- 卡片库(新建,只读):`results/wt_cards_b33_L2/`(20 店,220–562 卡/店)
- 逐行结果:`results/b33d_smoc_L2_new20.jsonl`(80)、`results/b33d_smoc_L2_old10_repro.jsonl`(40)、
  `results/b33d_slot_L2_new20.jsonl`(80)、`results/b33d_full_haiku_L2_new15.jsonl`(60)
  (各自的 `_s{0..3}` 分片文件保留)
- 复用存档:`results/b33_smoc_L2probe_slot.jsonl`(投影 40)、`results/b27_full_haiku_L2.jsonl`(全文 60)、
  `results/b27_full_gpt_L2.jsonl`(gpt-5-mini 全文 60,仅原 15 店)
- 历史点(不入表):`results/b27_smoc_L2probe.jsonl`
- 汇总器:`scripts/b33d_scale_report.py`;运行封装 `scripts/b33d_run_arms.sh`
- 小库对照(存档,$0):`results/wsc_v2_smoc_v43.jsonl`、`results/wsc_v2_smoc_v43_slot.jsonl`(各取同 30 uid 的 120 行)
