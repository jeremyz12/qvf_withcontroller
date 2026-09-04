# 批 42 预注册:扩大冻结保留集(WikiState-holdout v2,+40 链 → 与既有 40 链池化 80 链)

写定时间:2026-09-04,**在任何读者臂开跑之前**。语料构造仍在进行(候选发现已完成,
见下表"探索性供给核验"),但读者臂(smoc/direct/plainctx)尚未触碰任何数据——本文件
锁定目标规模、构造规范、臂位定义与三条假设的数值判据。语料构造实况(达成的槽位/链长
直方图、双闸结果、成本)与实跑结果记入 `results/opt_batch42_verdict.md`。

## 零、动机与背景

`results/opt_batch33_C_holdout_verdict.md` 建立了首个冻结保留集(40 链,与 144 主链
零交集),证明"结构总价不是开发场过拟合"这条判决在从未碰过的 Wikidata 切片上原样成立
(smoc−direct 保留集 +43.12pp vs 开发场 +42.19pp,簇 CI 重叠)。但 40 链的簇自助 CI
仍偏宽([+34.38,+51.25]),该文件自己也承认"保留集不是开发场的等难度复制"
(fullplain 侧的迁移缺陷未解释清楚,§二 5)。批 42 的目的是把保留集扩到 80 链,让
"未过拟合"这条主张站在更宽的样本上,同时用一条**方法学不同**的"全文裸读"基线
(见下文臂位定义)重新检验第三臂是否仍然稳健。

## 一、语料构造(与批 33-C 保留集 v1、与开发场同一生成器,逐字规则不变)

| 环节 | 批 42 做法 | 与批 33-C 保留集 v1 的关系 |
|---|---|---|
| 实体来源 | 候选发现:WDQS(P39/P54/P551)或搜索 API `srsort=random`(P108 WDQS 504 后自动回退),链解析走 EntityData | 逐字同规则(`scripts/b42_holdout_scrape_v1.py` = `scripts/holdout_scrape_v1.py` 的忠实拷贝) |
| **排除集** | 仓库内出现过的全部 QID(144 主链 uid、L1/L2、历史 items/full/candidates 各档)**+ 既有 40 链保留集 v1 的全部 QID**(`data/wikistate_holdout_v1.json`) | **新增**:v1 脚本的 `known_qids()` 扫描模式不含 `wikistate_holdout*.json`,批 42 版本补上此项,实测排除集从 618 增至 **658** |
| 低知名度闸 | sitelinks ≤ 5;值去重后带 P580+P582 的段 ≥ 3 | 逐字同 |
| 链清洗 | 非重叠 + 起止齐全 + 值去重 ≥3 段 | 逐字同(`scripts/b42_holdout_build_v1.py`) |
| 参数泄漏闸 | haiku-4.5 裸答四问(dim1/2/4/5),ClaudeJudge(opus-5)判对任一 → 弃条目 | 逐字同 |
| 会话渲染 | claude-opus-5,同提示词、同 `RenderedState` 契约、同逐字锚点校验,失败重试 3 次后弃链 | 逐字同(`scripts/b42_holdout_render_v1.py`);uid 前缀改 `hold2<PROP>`(QID 已保证零交集,前缀只是双重防呆,便于池化分析时区分批次) |
| 填充干扰 | 复用**同一份**已审计填充池 `data/filler_pool_v23.json`(1,100 会话),池层面剔除 CONFIRMED + 复扫剔残留;每链 30 个 | 池本身不重新审计(与批 33-C 保留集共享同一干净资源池,符合"存量语料只读"约束);**抽样种子换新** |
| 装配后复扫 | 任一 CONFIRMED 逐字引文若仍出现在填充里 → ABORT 不落盘 | 逐字同 |
| 出题 | 四型 change_count / count_before / longest_tenure / first_vs_last,题面口径、锚点候选、贪心平衡、末段计入至今、1/4 库"链尾可反超"锚全部逐字同源 | 逐字同(`scripts/b42_holdout_questions_v1.py`) |
| **随机种子** | 渲染期填充采样与 uid 播种:`SEED = 20260904`(批 33-C 保留集 v1 为 20260902) | **新种子,已记录**;因 QID 集合本身与 v1 完全不同,种子差异只影响"同一 uid 若重复出现该抽到哪 30 条填充"这一理论情形,实际不会与 v1 冲突 |

### 槽位配额:目标 10/10/10/10(与批 33-C 保留集 v1 的比例配额不同,原因如下)

批 33-C 保留集 v1 按开发场 144 链的槽位比例(employer 51/position 44/team 38/residence 11)
最大余数法缩放到 40 链,得到 P108 14 / P39 12 / P54 11 / P551 3 ——当时 P551(居住地)
候选供给极度稀缺(仅发现 14 条通过闸,配额 3 已经是上限附近)。批 42 任务书要求
"10 per slot class if the pipeline supports all four; otherwise state the mix",
故先做**探索性供给核验**(排除集 658 QID 下,TARGET=60 试抓):

| 属性 | 探索性候选发现(排除 658 QID 后,sitelinks≤5、链≥3 段过滤后) | 结论 |
|---|---|---|
| P551(居住地) | 60/60(WDQS 路线,几乎无需扫描即触顶) | 供给充足,与 v1 的"仅 14 条"形成对比——v1 的稀缺是因为 v1 自己已经用掉了最容易找到的那批;双重排除后 WDQS 命中率对 60 目标仍轻松达标 |
| P54(队籍) | 60/60(WDQS 路线) | 供给充足 |
| P39(任职) | 60/60(WDQS 路线) | 供给充足 |
| P108(雇主) | WDQS 全局 GROUP BY 仍 504(与 v1 同样原因),回退搜索 API `srsort=random`;探索性抓取进行中,已观察到持续命中(非零) | 路线与 v1 相同,预期可达 60(供给核验详情记入 verdict) |

**判据(写死)**:若四个属性的"参数泄漏闸通过后"验证池(build 步产物)均 ≥10,
则采用 **10/10/10/10** 均衡配额(共 40 链);若某属性验证池 <10,则该属性配额下调至
其验证池实际大小,其余三属性维持 10,总链数相应低于 40,并在 verdict 中如实报告
"未达 40 链的属性与原因"。链长匹配变量维持 v1 的方法论(目标直方图 = 开发场 144 链
比例最大余数法缩放到 40:3:24/4:9/5:3/6:2/7:1/8:1),配额调整后按同一可行分配算法
重新求解(`scripts/b42_holdout_select_v1.py`)。

**与两个既有集合的零交集**(硬性判据,verdict 必须逐条核验):
1. 与 144 主链(`data/wikistate_full_ALL_v25.json` 等)QID 交集 = 0;
2. 与既有 40 链保留集 v1(`data/wikistate_holdout_v1.json`)QID 交集 = 0。
两项在 `scripts/b42_holdout_merge_v1.py` 里合并核验,任一非零则 ABORT 不落盘。

产物:`data/wikistate_holdout2_v1.json`、`data/wsc_holdout2_v1.jsonl`、
`data/wsc_holdout2_v1.keymap.json`、`data/holdout2_selection_v1.json`。

**语料冻结条款**(与 v1 同一纪律):第一次读者臂跑完之后,语料与题集一律不得再改。
若发现缺陷,只能作为 limitation 记入 verdict,不得重建后重跑。

## 二、臂位(跑前写死)

| 臂 | 命令口径 | 读者 | 判官 |
|---|---|---|---|
| smoc(账目) | `scripts/b42_lb_reader_arm.py --arm smoc --cards-dir results/wt_cards_holdout2` | anthropic:claude-haiku-4-5 | ClaudeJudge(claude-opus-5,冻结) |
| direct(top-10 检索直读) | 同脚本 `--arm direct`,**`QVF_EMBED_BACKEND=openai`**(text-embedding-3-small) | 同上 | 同上 |
| **plainctx(整库原文直读,b36 框定)** | `scripts/b36_plain_fullctx.py`(**沿用原脚本,不改代码,只改 `--data`/`--questions`/`--out` 指向批 42 语料**——即任务书所称"adapted") | 同上 | 同上(脚本内自建 `ClaudeJudge()`,同模型) |

`scripts/b42_lb_reader_arm.py` 是 `scripts/lb_reader_arm.py` 的逐字拷贝,唯一改动是
判官侧 token 逐行落盘 + 结束时打印 `judge.total_usage`(修复
`opt_batch33_C_holdout_verdict.md` §二 9 记录的遗留项:该文件的三臂判官成本此前是
估算而非实测)。臂位口径(smoc 用 `render_card_ledger` + 两段式协议提示词
`SMW_PROMPT`、direct 用稠密 top-10 检索 + `READER_SYSTEM`)与原脚本逐字相同。

**第三臂方法论声明(与保留集 v1 的差异,必须记录、不得混同)**:
保留集 v1 的第三臂是 `lb_reader_arm.py --arm fullplain`(整段对话原样入上下文 +
`repro_batch3.PLAIN_PROMPT`:"Answer the question based on the conversation
transcript. Reply with only the answer.",系统提示为空)。批 42 任务书明确指定
"plain whole-memory-in-prompt (scripts/b36_plain_fullctx.py adapted)"——即
`PLAINCTX_SYSTEM = "You are a helpful assistant."` + `PLAINCTX_USER` 框定
("Below is the complete record of my past conversations with you, in
chronological order... Question: {question}"),**没有"回答基于文字记录"这类任务
框定,也没有"只回复答案"的长度约束**。这是两个不同的提示词条件,不是同一基线的重跑。
**因此**:
- H3(plainctx 落在 direct 与 smoc 之间)只在批 42 新 40 链上检验,不与 v1 的
  fullplain 数字直接比较;
- H2 的"池化 80 链头条"**只池化 smoc 与 direct**(两批间字节级同一方法论);
  第三臂(fullplain vs plainctx)不池化,分开报告,verdict 中明记这条方法论边界。

建店:`scripts/wt_qvf_prototype.py --phase write --cards-dir results/wt_cards_holdout2`,
**`QVF_CARD_OWNER_GATE=0`,不设其余任何 `QVF_CARD_*` 环境变量**——与保留集 v1、与开发场
v2.4 头条同一配置(即除 `QVF_CARD_TEMP0` 默认值 1 外,`QVF_CARD_KEYS`/`QVF_CARD_TAGS`/
`QVF_CARD_BY_SESSION`/`QVF_CARD_INCR`/`QVF_CARD_ABS_DATE`/`QVF_CARD_RENUMBER`/
`QVF_CARD_VERIFY_SPAN`/`QVF_DATE_STRICT`/`QVF_SLOT_STRICT`/`QVF_CARD_STRICT`/
`QVF_FAIL_CLOSED`/`QVF_CARD_V5` 等全部保持默认关闭)。新建目录,建后只读,只建一次。
此为"同一建店配置"的具体所指,写在此处供 verdict 引用。

## 三、参照值(冻结,来自盘上实跑文件,跑前写死)

| 口径 | smoc | direct | 第三臂(全文/裸读类) | 出处 |
|---|---|---|---|---|
| 开发场 v2.4(144 链/576 题) | 90.45 | 48.26 | 52.26(fullplain,v2.0 语料)/53.47(v2.4 语料) | `opt_batch33_C_holdout_verdict.md` §一 3 |
| 保留集 v1(40 链/160 题) | 95.00 | 51.88 | 71.88(fullplain) | 同上 §三 2 |
| **主场头条(无闸/最新单店,144 链)** | **89.06** | **47.57** | — | `results/ladder_decontamination_20260902.md:106`:"smoc 89.06 vs direct 47.57,+41.49,b/c=22/261,p=5e-53,144 链簇 CI [+36.5,+46.4]" |

批 42 的"主场单店头条"比较对象 = **89.06 vs 47.57(Δ+41.49,四舍五入引用为 +41.5)**,
按任务书指定口径采用,不重新推导。

## 四、三条假设(跑前写死,数值判据)

- **H1**:新 40 链上,smoc − direct 的 40 链簇自助 95% CI **下界 > 0 且点估 Δ ≥ +30pp**。
  统计口径:配对 McNemar(题级,精确二项符号检验)+ 簇 = 链,自助 10,000 次,分位数法
  95% CI(种子 20260904,与本批渲染种子一致,记录可复现)。
- **H2**:池化 80 链(既有 40 链保留集 v1 + 批 42 新 40 链)的 smoc−direct 头条数字,
  与主场单店头条 **+41.49pp 相差 ≤ ±5pp**,即池化 Δ ∈ **[+36.49, +46.49]**。
  池化做法:两批的 smoc 行与 direct 行分别按 question_id 合并(80 链 × 4 题型 = 320 题
  每臂),链簇自助改为 80 个簇。
- **H3**:新 40 链上,plainctx 的点估准确率**介于 direct 与 smoc 之间**
  (direct ≤ plainctx ≤ smoc,允许链簇 CI 意义下的模糊地带,判读时报告点估与三者两两
  簇 CI 是否重叠,不强行二元判定)。

## 五、统计与成本口径

- 单臂 Wilson 95% CI(题级二项比例,z=1.96):新 40 链每臂单独报告;
- 单臂/对比链簇自助 95% CI:簇 = 链,自助 10,000 次,分位数法,种子 20260904;
  新 40 链(40 簇)与池化 80 链(80 簇)分别报告;
- 配对 McNemar:题级精确二项符号检验(与批 33-C 同一 `sign_p` 实现);
- 逐题型(change_count/count_before/longest_tenure/first_vs_last)准确率;
- 成本:读者 haiku-4.5 $0.80/M 输入、$4/M 输出(与批 33-C 保留集口径一致);
  判官 opus-5 $5/M 输入、$25/M 输出,**本批判官侧 token 逐行实测**(见 §二 的
  `b42_lb_reader_arm.py` 改动 + `b36_plain_fullctx.py` 本身已落盘判官 token),
  不再需要估算;
- **预算口径(任务书原文)**:$22 上限覆盖建店 + 三个读者臂;判官成本另计、不设同一
  上限,但仍逐笔记账。API 500/529 时等待 60 秒重试。

## 六、复现命令(占位,verdict 中补全实跑参数与耗时)

```bash
# 1 候选发现(已完成,探索性 TARGET=60;实际 build/select 用量见 verdict)
PYTHONUTF8=1 python -u scripts/b42_holdout_scrape_v1.py P551 60 8000
PYTHONUTF8=1 python -u scripts/b42_holdout_scrape_v1.py P54  60 6000
PYTHONUTF8=1 python -u scripts/b42_holdout_scrape_v1.py P39  60 6000
PYTHONUTF8=1 python -u scripts/b42_holdout_scrape_v1.py P108 60 4000
# 2 标签解析 + 链清洗 + 参数泄漏闸(第二参数 = keep 上限,目标 10)
PYTHONUTF8=1 python -u scripts/b42_holdout_build_v1.py P108 10
PYTHONUTF8=1 python -u scripts/b42_holdout_build_v1.py P39 10
PYTHONUTF8=1 python -u scripts/b42_holdout_build_v1.py P54 10
PYTHONUTF8=1 python -u scripts/b42_holdout_build_v1.py P551 10
# 2.5 合并条目池 + 按开发场链长直方图定选(配额 10/10/10/10,或按供给下调)
PYTHONUTF8=1 python -u scripts/b42_holdout_select_v1.py
# 3 渲染(SEED=20260904,分槽位四进程,可断点续跑)
QVF_HOLDOUT_QUOTA='{"P108":10}' QVF_HOLDOUT_OUT='data/holdout2_part_P108.json' PYTHONUTF8=1 python -u scripts/b42_holdout_render_v1.py
QVF_HOLDOUT_QUOTA='{"P39":10}'  QVF_HOLDOUT_OUT='data/holdout2_part_P39.json'  PYTHONUTF8=1 python -u scripts/b42_holdout_render_v1.py
QVF_HOLDOUT_QUOTA='{"P54":10}'  QVF_HOLDOUT_OUT='data/holdout2_part_P54.json'  PYTHONUTF8=1 python -u scripts/b42_holdout_render_v1.py
QVF_HOLDOUT_QUOTA='{"P551":10}' QVF_HOLDOUT_OUT='data/holdout2_part_P551.json' PYTHONUTF8=1 python -u scripts/b42_holdout_render_v1.py
# 4 合并 + 双闸 + 双重零交集核验 → data/wikistate_holdout2_v1.json
PYTHONUTF8=1 python -u scripts/b42_holdout_merge_v1.py
# 5 出题 + 答案键
PYTHONUTF8=1 python -u scripts/b42_holdout_questions_v1.py
# 6 建店(同批 33-C 保留集配置,新目录,建后只读)
QVF_CARD_OWNER_GATE=0 PYTHONUTF8=1 python -u scripts/wt_qvf_prototype.py --phase write \
  --data data/wikistate_holdout2_v1.json --cards-dir results/wt_cards_holdout2 --uids "<uids>"
# 7 三臂
PYTHONUTF8=1 python -u scripts/b42_lb_reader_arm.py --reader anthropic:claude-haiku-4-5 --arm smoc \
  --data data/wikistate_holdout2_v1.json --questions data/wsc_holdout2_v1.jsonl \
  --cards-dir results/wt_cards_holdout2 --out results/b42_smoc_holdout2.jsonl
QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python -u scripts/b42_lb_reader_arm.py --reader anthropic:claude-haiku-4-5 --arm direct \
  --data data/wikistate_holdout2_v1.json --questions data/wsc_holdout2_v1.jsonl \
  --cards-dir results/wt_cards_holdout2 --out results/b42_direct_holdout2.jsonl
PYTHONUTF8=1 python -u scripts/b36_plain_fullctx.py --reader anthropic:claude-haiku-4-5 \
  --data data/wikistate_holdout2_v1.json --questions data/wsc_holdout2_v1.jsonl \
  --out results/b42_plainctx_holdout2.jsonl --workers 4 --budget 20
# 8 统计(点估 + Wilson CI + 逐题型 + McNemar + 链簇自助(新 40 与池化 80)+ 成本)
PYTHONUTF8=1 python -u scripts/b42_stats.py | tee results/b42_score_out.txt
```

## 七、已知会记入 verdict 的偏差(提前声明)

1. 槽位配额从 v1 的比例配额(14/12/11/3)改为均衡配额(10/10/10/10 或按供给下调),
   原因见 §一;
2. 第三臂提示词框定与 v1 不同(plainctx vs fullplain),H2 池化只覆盖 smoc/direct,
   第三臂不跨批池化;
3. 判官侧 token 本批逐行落盘(`b42_lb_reader_arm.py` 的改动),v1/开发场同类数字为
   估算,不可逐笔对比,但汇总口径($/M token 单价)一致。
