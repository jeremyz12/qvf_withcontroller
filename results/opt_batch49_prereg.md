# 批 49 预注册 — 最新 QVF 配置是否只对 WikiState 特调:强读者格、104K 格、两个第三方考场

写于建店进行中、任何读者/判官调用之前(2026-09-04)。问题来自用户:"现在最新的 QVF 是不是只针对 WikiState 特调?"

## 配置

冻结配置(批 48):claude-sonnet-5,TEMP0=0,THINKING=off,SLIM=1,STAGE1_K=8,VALNORM=1;WikiState 上再加蕴含类型过滤。Stage 1 查询有两套:
- lane4:四个金标槽位类(employer / position / team / residence)——与 WikiState 题集同构,是"特调"嫌疑所在;
- general:15 类(lane4 + device / location / relationship / provider / health / habit / education / pet_family / finance / generic_change),每类 top-8。

## 四格补齐(WikiState)

- 强读者格:v51f × claude-sonnet-5,140 题(`results/b35_questions_sample36.jsonl`),max_tokens 4000;对照 v47skf@sonnet 95.0、v45@sonnet 90.7、全上下文 97.1(批 36b/38e)。
- 104K 格:`data/wikistate_long_L2_b33.json` 30 店 120 题,lane4 配置建店 v51L → 蕴含过滤 v51Lf;haiku 与 sonnet-5 各跑全账目与槽位投影(QVF_LEDGER_VIEW=slot);对照批 39/40/46b:haiku 全账目 54.2 / 投影 61.7,sonnet 全账目 73.3 / 投影 74.2 / 全上下文 65.8。

## 第三方考场(与批 19 逐字同口径:`scripts/ext_smoc_arm.py` haiku 读者 + `scripts/ext_arena_judge.py` haiku 判官,新鲜 b19 样本 40 店 120 题)

- STALE:新店 `results/ext_cards_stale_v51_lane4` 与 `..._general`;对照批 19:direct 46.7,smoc(旧建卡)61.7。
- MemOps:新店 `results/ext_cards_memops_v51_lane4` 与 `..._general`;对照:direct 48.3,smoc 52.5。

## 假设与判据

- H1(特调检验,主判据):lane4 配置在 STALE / MemOps 上相对旧 smoc 掉 ≥ 5pp,而 general 配置把损失收回到 ±3pp 内 → 判"Stage 1 的 lane4 查询是 WikiState 特调,general 查询可迁移"。若 lane4 本身不掉 → 判"未见特调"。若 general 也掉 ≥ 5pp → 判"两阶段抽取在非槽位化考场有损,须关 Stage 1"。
- H2:v51f@sonnet-5 ≥ 95.0(v47skf@sonnet)。
- H3:104K 投影/全账目 @haiku ≥ 61.7;@sonnet ≥ 74.2。
- H4:成本 ≤ $20(四店建店 + 四考场臂与判官 + 104K 四臂 + 强读者)。

## 修正(写于强读者格出结果之后、v52 建店之前)

强读者格先出:v51f@sonnet-5 = 88.6,对 v47skf@sonnet 95.0 掉 6.4(p = 0.049),掉分集中在 count_before(89 → 69)。原因查明:批 48 的冻结配置没有开 QVF_CARD_KEYS,精简契约下模型把"postdoc at X"整句塞进一张 job 卡(v51f 雇主链里 19/43 店只有 job 类卡),v47skf 因 KEYS 的闭集 slot_class 规则把 position 与 employer 分成两张卡。一店冒烟(SLIM+KEYS)证实分卡正常。**冻结配置改为 SLIM + KEYS + STAGE1_K=8 + VALNORM,重建 144 链为 v52 / v52f,重跑 haiku 两轮与 sonnet 140 题;v51 系列保留为"无 KEYS"对照。** 104K 与两个第三方考场的店已按无 KEYS 配置建好且读者已在跑,先按原样报告并注明差异;若预算允许再补 KEYS 版。

硬约束:既有店与既有结果文件只读;新店新目录;判官模型与批 19 同(haiku);不改题集与判官提示词。
