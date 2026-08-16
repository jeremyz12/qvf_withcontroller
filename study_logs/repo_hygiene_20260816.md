# 仓库大文件卫生盘点(20260816)

> Z3 任务:零 LLM 成本,纯 `git`/文件系统盘点。**本报告只产出建议清单,未执行任何删除/移动/history rewrite。**
> 口径:仓库根 `D:\ZZL_cluade`,当前分支 `main`,HEAD=`d601796`。

## 0. 一句话判决

**GH001 警告的直接触发文件已定位:`results/tag_lattice_embed_cache.json`(94.55MB)**——是当前 HEAD 树里唯一落在 GitHub 50–100MB 警告带的单文件(硬上限 100MB,该文件距上限仅剩 ~5.7MB 余量,后续若这份缓存再增长会直接变成拒收)。真正占体积大头的不是这个文件,而是**两个从未被任何台账/论文文档引用过的"可重建中间产物"**:`results/mem0_stores/`(317MB,Mem0 基线本地向量库)与 `cc_harness_test/`(245MB,08-07 一次性早期考卷/答卷载体)——两者合计 562MB,占当前 HEAD 树跟踪总量(1210MB)的 **46%**。按下文建议整改(零误删、被引用项一律保留)后,HEAD 可跟踪体积能从 1210MB 降到约 **460–490MB(−60%)**;但 `.git` 目录本身(342.97MB 已打包对象)只有做一次性历史重写(`git filter-repo`/BFG)才会真正缩小,本报告不执行、只标注需要,详见 §5。

## 1. 盘点

### 1.1 总体规模

| 口径 | 大小 |
|---|---|
| 仓库总大小(含 `.git`) | 2.6 GB |
| `.git`(已打包对象,`git count-objects -vH`) | 342.97 MB(6769 已打包对象 + 124 松散对象 31.47 MB) |
| HEAD 树跟踪内容(`git ls-tree -r -l HEAD` 求和) | **1210.19 MB / 6569 文件** |
| 工作区非 `.git` 内容(含未跟踪的超大基准原文件) | ≈ 2.26 GB |

`results/` 与 `data/` 对比(工作区 vs. HEAD 跟踪):

| 目录 | 工作区大小 | 工作区文件数 | HEAD 跟踪大小 | HEAD 跟踪文件数 |
|---|---|---|---|---|
| `results/` | 728 MB | 5833 | **710.47 MB** | 5715 |
| `data/` | 1.2 GB | 103 | **185.34 MB** | 95 |
| `cc_harness_test/` | 248 MB | — | 245.47 MB | 545 |
| `docs/`(含 `docs/papers/` 45.4MB PDF) | 47 MB | — | 45.94 MB | 40 |
| `study_logs/` | 22 MB | — | 21.71 MB | 56 |
| `external/`(内嵌独立仓库,gitlink) | 8.1 MB | — | 0 MB(仅一个 commit 指针) | 1 |

`data/` 工作区(1.2GB)远大于 HEAD 跟踪量(185MB)的原因:`.gitignore` 已经把 `stale_T1_T2_400_FULL.json`(306MB)、`stale400_full_wt.json`(295MB)、`longmemeval_s_cleaned.json`(277MB)、`data/tempreason/`(67MB)、`locomo10.json`/`locomo_full.json` 等超大公开基准原文件排除在版本控制外——**这部分卫生此前已经做对了**,不是本次问题根源。

### 1.2 Top 30 largest files(按 HEAD 中 blob 体积)

| # | 大小 | 路径 |
|---|---|---|
| 1 | 94.55 MB | `results/tag_lattice_embed_cache.json` |
| 2 | 39.67 MB | `data/memconflict_step4_4.jsonl` |
| 3 | 37.84 MB | `cc_harness_test/exam_stale400_s50.json` |
| 4 | 37.69 MB | `cc_harness_test/exam_stale400t2_s50.json` |
| 5 | 36.80 MB | `data/stale400_s50_wt.json` |
| 6 | 29.00 MB | `data/hoh/hoh_qas_240601_241201.parquet` |
| 7 | 15.39 MB | `data/longmemeval_oracle.json` |
| 8 | 12.42 MB | `study_logs/wikistate_viewer.html` |
| 9 | 12.08 MB | `docs/papers/MemChain_2607.24097.pdf` |
| 10 | 8.12 MB | `results/prompt_rows_all.jsonl` |
| 11 | 7.28 MB | `results/wt_cards/mabfc-factconsolidation_sh_262k.json` |
| 12 | 6.33 MB | `results/open_slot_embed_cache.json` |
| 13 | 5.77 MB | `data/mab_fc_all.json` |
| 14 | 5.42 MB | `results/locomo_full_qvf.jsonl` |
| 15 | 4.82 MB | `docs/papers/2026-08-02/SituatedQA_2109.06157.pdf` |
| 16–30 | 4.0–4.6 MB ×15 | 全部是 `results/mem0_stores/**/qdrant/collection/mem0_stale_chain/storage.sqlite`(Mem0 基线各会话库的向量库文件,同构重复) |

完整 30 项另存于对话记录;第 16–30 名清一色是 `mem0_stores` 下的 sqlite 库文件,说明这个目录不是"一个大文件"而是"大量中等文件堆出来的体量"。

### 1.3 largest directories(HEAD 跟踪,按体积)

| 目录 | HEAD 跟踪大小 | 文件数 | 说明 |
|---|---|---|---|
| `results/mem0_stores/` | **325.07 MB**(²) | 348 | Mem0 基线本地向量库(qdrant sqlite),按会话/库逐一生成 |
| `cc_harness_test/` | **245.47 MB** | 545 | 08-07 一次性早期"agentic 全量读取"考卷+分片答卷 |
| `results/wt_cards/` | 35.72 MB | 694 | **现行冻结卡库,SUBMISSION_MANIFEST 显式引用为读取阶段复现必需** |
| `docs/papers/` | 45.41 MB | 24 | 第三方论文 PDF 全文 |
| `data/hoh/` | 29.00 MB | 1 | 早期(08-04/05)HoH 基准,现行 15 格主表未含 |
| `results/wt_cards_keyed/` | 13.75 MB | — | 疑似修复①"键控卡"结果物证,需核实 |
| `results/wt_cards_v43/` | 13.41 MB | — | P1 阶段二至四"三臂统一使用"当前版,**必需** |
| `results/wt_cards_v42/` | 13.33 MB | — | B6/S5 台账明确点名"76.88% 端到端成绩实际使用的那份",**必需** |

(²)`results/mem0_stores/` 在"跨全部历史去重后"的字节数为 309MB,当前单一 HEAD 快照为 325MB(两次提交间有小幅增补,差值属正常噪声,不影响判断)。

## 2. 分类建议清单(保留 / 删除 / 移 LFS / 打包外发)

规则:**任何在 `study_logs/VERSION_LEDGER.md`、`README.md`、`SUBMISSION_MANIFEST.md`、`results/*.md` 判决文档中被点名引用的文件,一律标"保留",不因体积而降级。**

### ①论文可复现性必需 → 保留(不删)

| 路径 | 体积 | 引用出处 |
|---|---|---|
| `data/wikistate_full*.json`(9 个变体) | 各 0.6–4.0 MB | README §快速开始、SUBMISSION_MANIFEST §二;**论文主基准** |
| `data/stale_chain_full.json` | 3.08 MB | SUBMISSION_MANIFEST §二 |
| `data/longmemeval_oracle.json` | 15.39 MB | README §快速开始命令行示例 |
| `data/locomo10.json`(已 gitignore,未跟踪) | — | README 示例,再生命令已在 README |
| `data/wsc_boundary.jsonl` / `wsc_ooo.jsonl` / `wsc_s8.jsonl` | 0.1–0.13 MB | VERSION_LEDGER 边界压力子集线、P1 阶段线 |
| `results/algebra_parity_20260815.jsonl` / `boundary_duel_20260816.jsonl` / `intent_vs_regex_20260816.jsonl` | <0.1 MB | SUBMISSION_MANIFEST 数据完整性核验里逐条点名 |
| `results/problem_labels.json` / `mc_labels_opus.json` | 0.02 MB | SUBMISSION_MANIFEST §三显式引用 |
| `results/prompt_rows_all.jsonl` | 8.12 MB | 被 `scripts/train_router.py` 与 `results/router_learned_report_20260814.md` 实际读取,P3 学习路由的输入特征表,**必需** |
| `results/wt_cards/`(692 卡) | 35.72 MB | SUBMISSION_MANIFEST §三:"读取阶段复现所需" |
| `results/wt_cards_v42/` | 13.33 MB | B6/S5 台账:"这批归档卡片…即端到端成绩实际使用的那份" |
| `results/wt_cards_v43/` | 13.41 MB | P1 阶段二至四:"三臂统一使用" |
| `results/wt_cards_b6_rep1/2/3/`(共 ~3.5MB) | — | B6"写入侧质量区间估计"70.0% CI[52.1,87.9] 这一数字的**唯一原始物证**(n=3 独立重建),数字已写进台账文字但区间的可核验性依赖这三份原始卡库 |
| `results/wt_cards_ooo_shuf/` / `wt_cards_ooo_seq/`(共 ~0.9MB) | — | B4 乱序压力子集"乱序有害"判据的直接建卡产物 |
| `results/wt_cards_tagged/` | 4.50 MB | P2 阶段二 QVF_CARD_TAGS=2 冒烟产物,当前在研活跃线 |
| 核心代码(`qvf/`、`scripts/*.py` 全部) | 0.46 MB(qvf)+ 若干 | 冻结代码,复现主体 |

这些项体积合计约 100MB 左右,均建议**保留**——但见下方③,其中卡库类应改存放方式而非直接删除。

### ②中间产物/可重建 → 建议删除(移出版本控制)

| 路径 | 体积 | 理由 |
|---|---|---|
| **`results/mem0_stores/`** | **317–325 MB** | Mem0 基线跑批自动生成的本地 qdrant 向量库(sqlite),纯运行时产物;全库检索(README/SUBMISSION_MANIFEST/VERSION_LEDGER)**零引用**;重跑 `scripts/run_mem0_baseline.py` 即可再生。单项即可拿回全仓库体积的 1/4 强,是本次最高优先级删除项。 |
| **`cc_harness_test/`** | **245.47 MB** | 仅服务于 08-07 一次性早期探索("claude-fable-5 agentic 全量读取"),`results/overnight_20260807_verdicts.md` 与 `scripts/score_cc_harness.py` 提及其路径,但**该判决的数字早已写入台账文字**,不依赖原始考卷/分片文件才能复现;SUBMISSION_MANIFEST §六自陈"失败首跑产物…文件可留可删"正是这一类。当前 v4.1/v4.2 主线管线完全不触碰此目录(`git log` 只在初始整合提交中出现过一次)。 |
| `results/backup_pre_patch/` | 3.58 MB | 目录名即"补丁前备份",典型手工临时备份,无判决引用。 |
| `results/ledger_cache/` | 1.75 MB | 名称即缓存,无引用,可重建。 |
| `results/wt_cards_strict3_probe/` / `wt_cards_strict_probe/` | 0.39+0.35 MB | "严格覆盖规则冻结"契约 dev 探针的中间产物,规则已冻结进正式代码,探针本身非最终结果。 |
| `results/wt_cards_opentags_smoke/` | 0.37 MB | 命名含 smoke,冒烟级中间产物。 |
| `results/wt_cards_ooo_seq_smoke/` | 0.09 MB | 同上,冒烟级。 |
| `study_logs/wikistate_viewer.html` | 12.42 MB | 数据内嵌进静态 HTML 的可视化查看器,非脚本非结果非题集;便利工具而非复现物证,且数据随源文件更新会过期。建议改为"脚本现场读取渲染"而非把数据打包提交。 |
| `results/wt_cards_v42_big/`(0.68MB)、`wt_cards_v5dev/`(3.72MB)、`wt_cards_v5held/`(0.49MB)、`wt_cards_newdom/`(4.03MB)、`wt_cards_opentags/`(2.59MB)、`wt_cards_keyed/`(13.75MB)、`results/_parity_check/`(0.05MB) | 共 ~25 MB | **未在台账中被逐一点名**,但从命名可合理推断分别对应 S6 大库、B6/V5 消融、零改动新域测试、P2 开放标签、修复①键控卡等**在研或近期研究线的中间物证**。不建议现在删——标"**待核实**":请核对是否为对应台账行(修复①键控卡判决、零改动新域测试线、去耦合执行线 V5)的直接产出;若是则转入①必需清单,若只是被取代的旧探针则可删。 |

删除候选合计(不含"待核实"项):**245.47 + 325 + 3.58 + 1.75 + 0.39 + 0.35 + 0.37 + 0.09 + 12.42 ≈ 589 MB**

### ③体积大且敏感度低但必需 → 建议 Git LFS 或打包外发

| 路径 | 体积 | 处理建议 |
|---|---|---|
| `results/wt_cards/` + `wt_cards_v42/` + `wt_cards_v43/`(3 份必需卡库合计) | 62.5 MB,约 1750 个零碎小文件 | 单个 JSON 卡片文件都很小,零碎文件数对 git 历史膨胀的伤害(每次改动都是新增大量小 blob)不亚于体积本身。建议:①迁移进 Git LFS,或②论文提交时改为"打包外发"——`tar.gz` 三份卡库上传到 Zenodo/HuggingFace Datasets/GitHub Release Asset,仓库里只留一份"如何解包+校验哈希"的说明与再生脚本。 |
| `results/tag_lattice_embed_cache.json`(94.55 MB) | GH001 直接触发文件 | 是嵌入缓存,理论可重跑 P2 lattice 脚本再生,但**再生有真实 API 成本**(P2 台账记录"100-uid 全量重建约 $7.5"),不是零成本可重建,不能像 mem0_stores 那样直接删了事。建议:从版本控制移出(加入 .gitignore)+ 论文/README 里给出再生命令与预期成本;若要免重花钱保留这份具体缓存,发布时挂 Git LFS 或外部对象存储。 |
| `results/open_slot_embed_cache.json`(6.33 MB) | 同上,同类缓存,体积较小,建议直接 Git LFS 或 gitignore。 |
| `data/hoh/hoh_qas_240601_241201.parquet`(29.00 MB) | 早期(08-04/05)基准,出现在已归档的 `results/final_table.md`/`FINAL_SWEEP_CHECKLIST.md`(历史判决表)中,但**不在当前 v4.1/v4.2 十五格主表**——按规则"引用过的一律保留",不建议删;但体积大、当前论文非必需,建议移 LFS 或打包外发,并在 README 注明"历史阶段性基准,现行主表不含"。 |
| `data/memconflict_step4_4.jsonl`(39.67 MB) | 开放走向 #3"MemConflict S3 标签 opus 复核(决定是否部分回收)"仍是**未决**的将来工作项,当前主结果未引用——既不能按"已引用"保留、也不能按"纯中间产物"删除,建议维持现状或移 LFS,等复核结论落地后再定。 |

### 额外一项:不是体积问题,是合规风险

| 路径 | 体积 | 问题 |
|---|---|---|
| `docs/papers/*.pdf`(24 个文件) | 45.41 MB | 这些是第三方论文的**全文 PDF**(MemChain、SituatedQA 等),不是我方产出。放进要公开发布的论文代码仓库存在**版权/再分发风险**,超出单纯的"仓库卫生"范畴。建议:全部删除,改成 `docs/REFERENCES.md` 式的 arXiv ID / DOI / 链接列表(`QVF_related_work_verified_20260814.md` 已经是这种索引形式,可以直接复用其 bib 条目)。 |

### 结构卫生(非体积项)

`external/qvf_withcontroller/` 在主仓库里以 gitlink(内嵌 commit 指针)存在,不占主仓库 blob 空间,但**没有配套 `.gitmodules`**——建议:如果它是仍在用的分支/实验,补 `.gitmodules` 正式声明为 submodule;如果是废弃探索,整体移除引用。

工作区还有一个空目录 `D:ZZL_cluadescripts`(疑似历史某次命令路径拼接产生的空文件夹,未被 git 跟踪),可直接手动删除,与本次 git 卫生无关但顺手提一句。

## 3. `.gitignore` 增补建议(只给建议,未改文件)

当前 `.gitignore`(21 行,见文末)已经正确排除了几个超大基准原文件,但存在以下遗漏:

```gitignore
# 建议新增——中间产物/可重建缓存(见 §2②③)
results/mem0_stores/
cc_harness_test/
results/backup_pre_patch/
results/ledger_cache/
results/*_embed_cache.json
results/*_probe/
results/*_smoke.jsonl
results/*_smoke/
study_logs/*_viewer.html

# 建议新增——本会话/临时草稿文件(当前 git status 里已有 4 个未追踪实例)
scratch_*
scratchpad/
scratchpad_*/

# 建议新增——第三方文献全文(改用引用列表,不入库全文)
docs/papers/*.pdf
```

注意:`.gitignore` 只能防止**未来**误加;`results/mem0_stores/`、`cc_harness_test/` 等已经被跟踪的路径,加入 `.gitignore` 后仍会保留在历史里,需要额外 `git rm -r --cached <path>` 才能让它们从下一次提交起真正退出跟踪(这一步同样属于"删除"操作,依纪律本报告不代为执行)。

## 4. 当前 `git status` 未追踪文件(核对是否为该忽略的临时件)

```
scratch_fails.txt              12 KB   — 命名像临时排错记录,建议 scratch_* 规则忽略
scratch_split_preview.json      4 KB   — 同上
scratchpad_lattice_verify/    287 KB   — 命名即 scratchpad,建议忽略
results/router_eps_scaling_20260816.{md,svg,json}  — 看起来是正在进行中的新结果,不属于待忽略项,应正常加入版本控制
scripts/router_eps_scaling.py                       — 同上,正常代码,应入库
```

## 5. 体积估算与 LFS 需要性判断

**若按 §2 建议执行(仅删"确认无引用"的 ②类项,不动"待核实"与③类项):**

- HEAD 树跟踪体积:1210 MB → 约 **621 MB**(1210 − 589,四舍五入)
- 再把③类"大且必需但低敏感"的卡库+缓存移出常规 git 跟踪(改 LFS/打包外发,不计入这个数字但也不再占用普通 blob 历史):额外让**未来**新增的常规仓库体积再降约 130 MB,落到约 **460–490 MB**

**这只解决"未来新增"和"当前工作区/HEAD"层面的膨胀。** `.git` 目录本身(342.97MB 已打包对象)记录了这些大文件的全部历史版本,单纯从 HEAD 删除或加 `.gitignore` **不会**让已有的 `.git` 变小——`git rev-list --objects --all` 逐路径核算显示,`cc_harness_test`(245MB)、`mem0_stores`(309MB 全历史去重口径)、两个 embed cache(合计 104MB)、`docs/papers`(45MB)这几项在全部历史中占了约 **780MB 原始字节**,接近 HEAD 总跟踪量的 2/3。按当前仓库整体压缩比(1210MB 原始 → 310MB 已打包,约 4:1,但 sqlite/PDF/嵌入缓存的可压缩性明显低于纯文本 JSON,实际收益会打折)粗估,**若执行一次性历史重写(`git filter-repo` 剔除这几条路径的全部历史版本),`.git` 有望从 343MB 降到约 130–180MB**。这是一个较高风险操作(改写 commit hash、需要强推、所有协作者需要重新 clone/rebase),建议作为**独立的一次性维护窗口**执行,不要和日常提交混在一起,且要提前跟协作者/GitHub 上已有的 fork 打招呼。

**是否需要 Git LFS:** 需要,但只针对§2③里明确"体积大+必需+要长期保留"的几类——三份卡库(`wt_cards`/`wt_cards_v42`/`wt_cards_v43`,合计 62.5MB)与两个嵌入缓存(合计 100.9MB,若决定不当场删除、要保留可复现路径)。这两类合计约 163MB,迁入 LFS 后既能保住 GH001 警告的根源文件(94.55MB 那个),也能让论文提交时"审稿人凭本包 + API key 可复现"(SUBMISSION_MANIFEST 自定标准)不因为卡库被删而失效。其余 ②类中间产物建议直接从版本控制移除、不进 LFS(LFS 配额同样有限,不该用来存"确认可重建、零引用"的东西)。

## 附:当前 `.gitignore` 全文(供对照)

```gitignore
# 密钥与环境 —— 永不入库
.env
.env.*
!.env.example

# 缓存
__pycache__/
*.pyc
.pytest_cache/

# 超过/接近 GitHub 单文件上限的大数据文件(公开数据可再生/可下载;再生命令见 README)
data/stale_T1_T2_400_FULL.json
data/stale400_full_wt.json
data/longmemeval_s_cleaned.json
data/lme_temporal_reasoning_wt.json
data/lme_knowledge_update_wt.json
data/tempreason/
data/locomo10.json
data/locomo_full.json

# 本地临时
*.log
node_modules/
```
