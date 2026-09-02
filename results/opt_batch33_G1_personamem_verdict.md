# 批 33-G1 终判:PersonaMem-v2 外场——判据 G 判负,且**分层反号**暴露账目机制的适用边界

日期:2026-09-02。预注册 `results/opt_batch33_prereg.md` §33-G。
数据源 HF `bowen-upenn/PersonaMem-v2`(CC-BY-4.0,revision
`0622e56d1cc6f1bc990a5100a6ec4022a60e66a6`,2026-08-17),`benchmark/text/benchmark.csv`
5000 题 / 200 persona。全程实测成本 **$23.47**(上限 $25 内),git rev `7e9b9ea`。

## 判决

**猜想被否定。** 判据 G(smoc − direct > 0 且簇 CI 不跨零)**未过**:
全场 Δ = **−7.2pp**,簇 CI **[−11.0, −3.3]**(不含 0,方向为**负**)。
**PersonaMem-v2 不得写入外场表的正向栏**;它进入 limitations / 边界数据。

## 主表(600 题同题配对,100 persona 簇,读者 haiku-4.5,判官 ClaudeJudge=opus-5)

| 层 | n | smoc | direct | Δ | McNemar b/c | p | 簇自助 95% CI | 簇 W/L/T | 簇 p |
|---|---|---|---|---|---|---|---|---|---|
| **全场** | 600 | **31.7**(190) | **38.8**(233) | **−7.2** | 81/124 | 0.0033 | **[−11.0, −3.3]** | 23/50/27 | 0.0021 |
| ask_to_forget(=updated) | 200 | 28.0(56) | 42.0(84) | −14.0 | 23/51 | 0.0015 | [−22.5, −5.5] | 17/39/44 | 0.0046 |
| who=others | 200 | **20.5**(41) | **6.5**(13) | **+14.0** | 34/6 | 8.4e−06 | **[+9.0, +19.0]** | 31/3/66 | 7.7e−07 |
| self_standard(对照层) | 200 | 46.5(93) | 68.0(136) | −21.5 | 24/67 | 7.3e−06 | [−30.5, −12.5] | 15/48/37 | 3.8e−05 |

四选一题面,随机基线 25.0。**两臂在 who=others 层都远低于随机**
(direct 6.5、smoc 20.5)——该层金答案恰是"**不**按这条偏好个性化"的那个,
干扰项全是"按别人的偏好个性化"的漂亮回答;喂进原句的 direct 被钉死。

## 三条构造披露(不披露则数字不可用)

1. **预注册分层在本发布上退化。** v2 text benchmark 里 `updated=True`(1047 行)
   **⊂** `pref_type=='ask_to_forget'`(1048 行),交集 1047 —— 预注册的
   "updated 200 / ask_to_forget 200"是**同一个层**。按预注册
   "fallback to what exists"改为:ask_to_forget(=updated)200 /
   who=others 200 / self_standard(其余 who=self 且非 ask_to_forget)200。
   全库层计数:self_standard 3431 / ask_to_forget 1048 / who_other 521。
2. **日期是我们派生的,数据集不带任何时间戳。**
   `chat_history_32k/*.json` 的 metadata 只有 total_messages / final_token_count /
   persona_id;raw_data 亦无。按令用**固定 7 天步长**:会话序 j(0 起)→
   `2024-01-01 + 7j` 天。故本场的"时序"是构造出来的**顺序**,不是真实时刻;
   任何"日期推理"类结论不得从本场引用。direct 臂的 TODAY'S DATE =
   末会话日 + 1 月(`_query_date` 冻结算式,经 cardable 文件的占位 chain)。
3. **会话边界由 raw_data 反推。** chat_history 是 raw_data 各 scenario
   conversation block 的**连续拼接子集**。逐块在 chat_history 里定位并校验
   连续 → 一块 = 一会话;未进 32k 窗口的块丢弃。实测 100 店:
   平均 236.2 轮 / 80.2 会话,未匹配残留消息合计 331 条(3.3/店,按单条兜底
   会话保留,零丢数据)。**官方 32k 上下文首条 system 消息(persona 档案 JSON)
   原样保留为会话 0** —— 这是官方喂法的一部分,两臂同见。

另:题面 = 官方四选一协议(correct_answer + 3 个 incorrect_answers,seed=33
确定性洗牌贴标 A–D),gold = `<字母> — <正确选项原文>`。**判官口径自检:
ClaudeJudge 判定与"确定性字母匹配"一致率 smoc 591/591、direct 597/599
(未解析出字母者 9 / 1)——本场判官噪声≈0,Δ 不是判官抖动。**

## 病灶定位:输在**写侧留存**,不是读侧表达

**① 目标状态在原文里几乎都在,在账目里大半没了**(内容词命中 ≥50% 口径,
批 29 同法,零 API):

| 层 | 目标状态在**原文** | 在**账目** | 原文有而账目无 |
|---|---|---|---|
| ask_to_forget | 100.0% | 52.0% | 48.0% |
| who=others | 86.5% | 20.0% | 67.5% |
| self_standard | 93.5% | 27.0% | 67.0% |

撤销措辞本身("Do not remember 'X'")留在账目里的只有 82/200(41.0%)。
建卡压缩:236.2 轮 → **48.2 卡/店**(15–103),0.204 卡/轮 —— 而
WikiState 开发场是 5.2 万字符 → 78 卡。**PersonaMem 每 persona 携带 ~26 条
独立偏好,状态密度远超开发场,冻结建卡配置把它压没了。**

**② 条件化拆分:状态只要留在账目里,两臂打平。**

| 条件 | n | smoc | direct | Δ |
|---|---|---|---|---|
| 目标状态**在**账目 | 198 | 40.9 | 41.4 | **−0.5** |
| 目标状态**不在**账目 | 402 | 27.1 | 37.6 | −10.4 |

**③ direct 的检索比账目更能把目标状态摆到读者面前**:top-10 命中目标状态
64.3%(ask_to_forget 96.0% / who_other 44.0% / self_standard 53.0%),
对账目留存 33.0%(198/600)。撤销请求是**逐字可检索**的一句话
("Please forget that I enjoy puzzles and crosswords."),稠密检索几乎必中;
而 slot-value 卡片把它压成一条或干脆不压。

**④ 探索臂(未预注册):把写侧容量翻倍,差距没关上。**
`QVF_CATALOG_BUDGET=40000`(5 批/店,对冻结值 320000 的 1 批)重建 20 店,
卡 1019 → 1999,目标状态留存 41.7% → 54.2%,同 120 题:

| 同 120 题 | smoc(冻结 320k) | smoc(密 40k) | direct |
|---|---|---|---|
| 全部 | 30.8 | **31.7** | 34.2 |
| ask_to_forget | 25.0 | 30.0 | 35.0 |
| who=others | 17.5 | 7.5 | 0.0 |
| self_standard | 50.0 | 57.5 | 67.5 |

配对 dense vs frozen **b/c = 14/13,p = 1.0**(读取 tok/题 3050 → 5134,
建卡 $2.42)。**判读:②的条件化拆分是观察性的、有混杂(能被抽到的状态本就更显著);
干预性梯度说明"卡片密度"本身不是那根杠杆。** who=others 层反而更差
(17.5 → 7.5)——卡越多,读者越容易拿别人的偏好去个性化。

## 成本 / 延迟(全部来自实测 usage token,牌价 haiku $1/$5、opus-5 $5/$25、embed $0.02 /M)

| 项 | 实测 |
|---|---|
| 建卡(100 店,4816 卡) | in 4,712,581 / out 625,816 → **$7.84**($0.0784/店,摊到 600 题 $0.0131/题) |
| direct 嵌入(text-embedding-3-small) | ~4.02M tok(按 chars/4 估)→ $0.08 |
| smoc 读者 | in 1,699,820 / out 375,042 → **$0.00596/题**;延迟 mean 11.1s / median 10.7s |
| smoc 判官 | in 397,789 / out 25,470 → $0.00438/题 |
| direct 读者 | in 1,599,291 / out 86,786 → **$0.00339/题**;延迟 mean 6.3s / median 5.9s |
| direct 判官 | in 523,546 / out 27,146 → $0.00549/题 |
| **$/题(含摊销写侧,不含判官)** | **smoc 0.01903 vs direct 0.00352(5.4×)** |
| 探索臂 dense40k | 建卡 $2.42 + 臂 $1.54 |
| **本轨总支出** | **$23.47**(建卡 $10.26 + 读者 $6.62 + 判官 $6.45 + 嵌入 $0.08 + 冒烟 ~$0.06) |

延迟含判官调用(两臂同口径)。判官系统提示词走 ephemeral 缓存,其
cache token 不计入 `input_tokens`,故判官侧成本是**下界**(每次调用约少计
300 tok)。smoc 协议偏差(无 `ANSWER:` 行)54/600 = 9.0%,偏差题 acc 15/54
(27.8%)vs 合规题 175/546(32.1%)——不足以解释 −7.2pp。

## 判读与去向

1. **判据 G 判负,PersonaMem-v2 不进外场正向表。** 头条句(可对外):
   "在 PersonaMem-v2 的 600 题分层配对上,账目臂比稠密直读**低 7.2pp**
   (簇 CI [−11.0, −3.3]);逐层看,它在'用户要求遗忘'与常规召回两层落后,
   在'偏好属于他人'层领先 14.0pp。"
2. **这是与批 17 MemConflict conditional 盲区**(卡片压平条件绑定)**同族的
   第二次显形,但机制不同**:那次是 schema 缺字段,这次是**状态密度超出
   写侧容量**——每 persona 26 条偏好、236 轮,48 卡的账目装不下;而
   撤销请求恰恰是**逐字可检索**的一句话,是稠密检索的最优主场、结构化压缩的最劣主场。
   **边界句(入 limitations 候选)**:"QVF 的结构化账目在**状态少而链长**的
   语料上把杠杆放大;在**状态多而链短**(每状态只被提及 1–2 次、且撤销是
   一句原话)的语料上,结构化压缩是净损失,应路由到直读。"
3. **who=others 层的 +14.0pp 是本批唯一正向信号,且两臂都在随机线下**——
   它测的是"**不要**用检索到的东西个性化"。direct 6.5% 说明:把原句怼进
   上下文的基线在"该忍住"的题上被自己的证据害死;账目的有损压缩反而
   救了它。这与批 29-K"正确性与完整性是两根独立轴"同构:**证据可得性与
   证据克制是两根独立轴**。此句可入论文,但必须带"两臂皆低于随机 25"的帽。
4. 未做、留给后批的最小实验(不在本轨预算内):①**路由臂**——按题型把
   ask_to_forget/召回类路由到 direct、who=others 路由到 smoc,验证
   "分层反号"能否被路由吃成正和;②写侧 schema 加"撤销/否定"专用卡类型
   (本场 41.0% 的撤销措辞留存是可直接优化的靶子);③本场日期是派生的,
   不能测时序,故**不得**据此下"时序机制无效"的结论。

## 复现命令(逐字)

```bash
# ① 取数 + 转统一店 + 分层抽样(seed=33;HF 直下,不入 git)
PYTHONUTF8=1 python scripts/ext_convert_personamem.py --personas 100 --per-stratum 2

# ② 建卡(冻结 write_phase 原样调用;4 分片并行,uid 分片文件见下)
for k in 0 1 2 3; do PYTHONUTF8=1 python scripts/ext_build_cards.py \
    --data data/external/personamem/personamem_cardable.json \
    --cards-dir results/ext_cards_personamem \
    --uids-file <scratch>/pm_cards_shard$k.txt & done

# ③ smoc 臂(账目读法,读者 haiku-4-5,判官 ClaudeJudge)
for k in 0 1 2 3; do PYTHONUTF8=1 python scripts/ext_smoc_arm.py \
    --data data/external/personamem/personamem_cardable.json \
    --questions <scratch>/pm_probe_s$k.jsonl \
    --cards-dir results/ext_cards_personamem \
    --out results/ext_personamem_smoc_s$k.jsonl --resume & done

# ④ direct 臂(**必须** QVF_EMBED_BACKEND=openai)
for k in 0 1 2 3; do QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/ext_direct_arm.py \
    --data data/external/personamem/personamem_cardable.json \
    --questions <scratch>/pm_probe_s$k.jsonl \
    --out results/ext_personamem_direct_s$k.jsonl --resume & done

# ⑤ 统计(McNemar + persona 簇自助 CI + 成本 + 延迟)
PYTHONUTF8=1 python scripts/ext_personamem_stats.py \
    --smoc "results/ext_personamem_smoc_s*.jsonl" \
    --direct "results/ext_personamem_direct_s*.jsonl" \
    --probe data/external/personamem/personamem_probe.jsonl \
    --cards-dir results/ext_cards_personamem

# ⑥ 写侧留存诊断(零 API)
PYTHONUTF8=1 python scripts/ext_personamem_coverage.py

# ⑦ 探索臂(未预注册):写侧容量梯度,20 店
for k in 0 1 2 3; do QVF_CATALOG_BUDGET=40000 PYTHONUTF8=1 python scripts/ext_build_cards.py \
    --data data/external/personamem/personamem_cardable.json \
    --cards-dir results/ext_cards_personamem_dense40k \
    --uids-file <scratch>/pm_dense_uids$k.txt & done
for k in 0 1 2 3; do PYTHONUTF8=1 python scripts/ext_smoc_arm.py \
    --data data/external/personamem/personamem_cardable.json \
    --questions <scratch>/pm_dense_probe$k.jsonl \
    --cards-dir results/ext_cards_personamem_dense40k \
    --out results/ext_personamem_smoc_dense40k_s$k.jsonl --resume & done
```

分片文件由 `personamem_uids.txt` / `personamem_probe.jsonl` 按 `uids[k::4]`
(建卡)与"同 uid 同片"(题)切出,分片只影响并行度不影响结果;并行度全程 ≤4。

## 产出文件

**代码(可提交)**
- `scripts/ext_convert_personamem.py` — 新:HF 取数 → 统一店 + 分层抽样
- `scripts/ext_personamem_stats.py` — 新:配对统计 + 成本 + 延迟(统计函数
  直接 import `scripts/bootstrap_ci.py`,不复制实现)
- `scripts/ext_personamem_coverage.py` — 新:写侧留存诊断(零 API)
- `scripts/ext_smoc_arm.py` / `scripts/ext_direct_arm.py` — **仅追加两个记账
  字段** `judge_input_tokens` / `judge_output_tokens`(纯落盘,不改任何调用、
  提示词、模型或判分逻辑;此前判官侧 token 从不落盘,$/题 只覆盖读者侧)

**结果(可提交,共 5.7MB)**
- `results/ext_personamem_smoc_s{0..3}.jsonl`(600 行)
- `results/ext_personamem_direct_s{0..3}.jsonl`(600 行)
- `results/ext_personamem_smoc_dense40k_s{0..3}.jsonl`(120 行,探索臂)
- `results/ext_cards_personamem/`(100 卡店,3.0MB)
- `results/ext_cards_personamem_dense40k/`(20 卡店,1.2MB,探索臂)

**数据(130MB,\*\*不得提交\*\*;`.gitignore` 目前**不**覆盖 `data/external/`,
提交前须确认未 `git add`)**
- `data/external/personamem/v2/`(HF 原件 93MB:benchmark.csv + 100 persona 的
  chat_history_32k / raw_data)
- `data/external/personamem/personamem_unified.json`(18MB)/
  `personamem_cardable.json`(18MB)/ `personamem_probe.jsonl`(1.4MB)/
  `personamem_uids.txt` / `personamem_build_diag.json`
