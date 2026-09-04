# 预注册:批 46c——run-to-run jitter 从"3–4pp 说法"变成实测量(2/3 runs,预算硬顶强制减档)

日期:2026-09-04。动因:讲稿引用"run 间抖动 3–4pp"(`environment-limits.md`)一直是
单次观测的经验说法,没有真正跑过重复实验去测。本批目标:对讲稿引用的六个
臂/读者组合,在同一 140 题样本(`results/b35_questions_sample36.jsonl`,
36 店,语料 `data/wikistate_full_ALL_v24.json`)上补跑独立重复,把"3–4pp"
变成有 mean±sd 支撑的实测量。

## 零、开工前核验:预算($12 硬顶 vs 任务书字面需求)——严重超支,必须减档

任务书字面要求"再跑两轮"(run2 + run3)覆盖六个臂/读者组合。开工前用
run1 现有产物的真实 token 用量(而非猜测)逐臂核算重跑成本(单价表与
`scripts/lb_reader_arm_b36b.py`/`scripts/b36_plain_fullctx.py` 逐字同源:
haiku-4-5 $1/$5,sonnet-5 $2/$10,每百万 token):

| 臂/读者 | run1 真实成本($) | ×2(run2+run3) | ×1(仅 run2) |
|---|---|---|---|
| smoc_v47skf2 @ haiku | 0.652 | 1.304 | 0.652 |
| smoc_v47skf  @ haiku | 0.631 | 1.262 | 0.631 |
| plainctx     @ haiku(mt800+mt4000 校正口径) | 2.040 | 4.080 | 2.040 |
| direct       @ haiku(140 子集) | 0.180 | 0.360 | 0.180 |
| smoc_v47skf2 @ sonnet-5 | 1.826 | 3.652 | 1.826 |
| plainctx     @ sonnet-5(mt4000 口径) | 5.850 | 11.700 | 5.850 |
| **合计** | **11.179** | **22.358** | **11.179** |

字面任务(六臂各补跑 2 轮)实测需要 **≈$22.36**,是任务书写死的 $12 读者
预算硬顶的 **187%**——超支约 $10.4,单一大头是 `plainctx@sonnet-5`
(整库原文誊录,每题均值 ≈18.5K input token,一项就要 $11.7,占字面总需求
的 52%)。即使只跑另外 5 个臂各 2 轮($10.658)也已经吃掉硬顶的 89%,
`plainctx@sonnet-5` 补跑 2 轮无论如何塞不进剩余的 $1.34。

**减档决定(先判决,后执行,不悄悄超支也不悄悄砍臂)**:六个臂/读者组合
统一**只补跑一轮(run2),不跑 run3**——预算测算 $11.179,在 $12 硬顶内
留 ≈7% 缓冲。理由:
1. 均匀减档(而非挑着砍某个臂)对六个臂公平,H1(每臂测抖动)、
   H2(haiku 排序)、H3(sonnet-5 CI)三条假设都能拿到"至少 2 轮"的真实
   重复数据,好过"5 臂 3 轮 + 1 臂 0 轮"这种让 H3 完全测不了的方案(算过,
   见下)。
2. 曾比较过的替代方案,均被拒绝并记录在此(可复核):
   - 5 臂 3 轮 + `plainctx@sonnet-5` 0 轮补跑(成本 $10.658,预算内),
     但 H3 唯一关心的臂拿不到任何新数据,直接违背任务书"H3 sonnet-5"的
     字面目标,拒绝。
   - 缩样本(如 `plainctx@sonnet-5` 只在 140 题里抽 20-50 题重跑)能压成本,
     但会人为削弱该臂的统计功效,而 H3 的预判恰好是"差值 CI 包含 0"——
     低功效会机械地更容易得到"CI 含 0"的结果,等于用抽样噪声去帮预判
     "作弊",拒绝(与 `epistemic-discipline.md` "主动找最强反例"冲突)。
   - 给 `plainctx@sonnet-5` 用 prompt caching 省成本:技术上可行(该臂
     input token 占比最大且同店 3.9 题共享同一段誊录),但会让本批 run2
     的成本口径与 run1(无缓存)不可比,且需要改脚本(偏离任务书"同命令/
     同配置"的字面要求),工程改动风险与本批时间预算不成比例,拒绝——
     留作后续如果要专门补 `plainctx@sonnet-5` run3 时的成本优化选项。
3. **本批交付的是 n=2(run1 existing + run2 new)的 mean/sd/range,不是
   任务书字面要求的 n=3**。H1 的判据文本相应改写为"run1–run2 两点样本 sd"
   (等价于 |Δ|/√2),H3 的"95% CI"改写为"两点差值 + 说明置信区间在 n=2
   下宽且不稳,仅作方向性参考,不做强判决"。所有改写在下面 §一 逐条标注,
   不是执行完才追加的补丁。
4. **如果用户希望补齐 run3**(尤其是 `plainctx@sonnet-5` 一项,单独补
   run3 预算 ≈$5.85,超出本批硬顶但可作为独立后续批次),留在 §九 作为
   明确的下一步建议,附精确成本。

判官成本("judge 另计",不计入 $12 硬顶):按批 41 记录(2 臂×140 题
≈$0.456)线性外推六臂×140 题 ≈$1.4,量级远小于读者成本,不是本批的
预算瓶颈。

## 一、假设(H1–H3,均已按 §零 的 n=2 减档改写)

- **H1(抖动量级)**:六个臂各自的 run1↔run2 两点 sd(=|acc_run1 -
  acc_run2| / √2,百分点)**≤ 2pp** 记"证实"(与 `environment-limits.md`
  记载的"3–4pp"矛盾,判"被否定,实测抖动更小");**> 4pp** 记"证实且
  超出既往记录的上限"(抖动比经验说法还大);**2–4pp 区间**记"与既往
  经验一致,证实"。逐臂分别判,不合并判一个总判决。
- **H2(haiku 排序)**:`smoc(v47skf2 或 v47skf) > plainctx > direct`
  这个准确率排序在 run1 和 run2 **两轮都成立**(用当轮各臂准确率比较,
  非跨轮混用)记"证实";任一轮排序翻转记"被否定,标出翻转发生在哪两臂
  之间"。ledger 用 `v47skf2`(本批"主口径"店,批 41 判定 H1/H2 双双
  触顶)代表"ledger"一侧;`v47skf` 数字同表并列作参照,不单独判正误。
- **H3(sonnet-5 plainctx vs ledger)**:`plainctx@sonnet5 − smoc_v47skf2@sonnet5`
  的差值,在 run1、run2 两轮分别算,再取两轮差值的均值与两点展开的
  近似 95% CI(**t 分布 df=1**,如实标注"n=2 下 CI 极宽,仅方向性参考,
  不做强判决";若要稳健 CI 需要 run3,见 §零.4 的后续建议)。
  **预判:CI 包含 0**(即"追平,不是 plainctx 显著领先")——与批 38-E/41
  两次单轮观测(-2.14pp、-3.57pp,均不显著)方向一致。若两轮差值方向不
  一致(一轮 plainctx 领先、一轮 ledger 领先)记"证实预判(不稳定的小
  差异,与'追平'口径一致)";若两轮方向一致且都朝 ledger 领先记"意外
  证据,标注但不升级为强判决(n=2 功效不足以下强结论)"。

## 二、方法(逐步骤)

1. **读者重跑**(执行顺序按成本从低到高,任何一步撞见异常预算超支立刻
   停止并如实入档,不静默跳过):
   - `direct@haiku`、`smoc_v47skf@haiku`、`smoc_v47skf2@haiku`、
     `plainctx@haiku`、`smoc_v47skf2@sonnet5`、`plainctx@sonnet5`。
   - smoc/direct 用 `scripts/lb_reader_arm_b36b.py`(参数与 run1 逐字同源:
     `--questions results/b35_questions_sample36.jsonl --data
     data/wikistate_full_ALL_v24.json`,haiku `--max-tokens 800`、sonnet-5
     `--max-tokens 4000`,`--cards-dir` 对应 v47skf2 / v47skf);
     plainctx 用 `scripts/b36_plain_fullctx.py`(同一 `--reader`,haiku
     mt800、sonnet-5 mt4000)。
   - 输出 `results/b46c_<arm>_<reader>_run2.jsonl`(不产出 `_run3`,见 §零)。
   - haiku 臂:凡 `stop_reason=="max_tokens"` 的行,用同一脚本对该子集单独
     以 `--max-tokens 4000` 补跑一遍,写 `_run2_mt4000.jsonl`,记分时按
     qid 覆盖合并(与 run1 `b36_plainctx_*_mt4000.jsonl` 口径同源)。
   - temperature:haiku 发 0.0(脚本原生行为);sonnet-5 不发该参数(收到
     会 400,与 run1 一致)——**同一温度设置下重复调用依然会有输出方差**,
     这正是本批要测的"jitter"本身,不是需要消除的噪声源。
2. **记分**(新脚本 `scripts/b46c_score.py`):对六个臂,汇总 run1(既有
   产物)+ run2(本批新产物,mt4000 校正合并后)两轮:
   - 逐臂 mean、sd(n=2)、range;
   - 逐题两轮一致率(judge_correct 在两轮相同的题目占比,逐臂);
   - run-averaged correctness(每题两轮 judge_correct 的均值,0/0.5/1)
     做配对比较(H2 用当轮不跨轮比较;H3 用 run-averaged 差值 + 两点 CI);
   - 成本(读者 + 判官,逐臂逐轮);
   - H1–H3 判决。
   产出 `results/b46c_score_out.txt`、`results/opt_batch46c_verdict.md`。
3. **只读约束**:`results/wt_cards_v47skf2`、`results/wt_cards_v47skf`
   全程只读(建店前后目录内容不变,本批不重建店,只重跑读者)。

## 三、预算

$11.179(读者,§零 表)+ ≈$1.4(判官,另计,不计入硬顶)≈ **$12.6 总计**,
读者侧硬顶 $12 内(留 ≈7% 缓冲);若中途某一臂实测成本明显偏离 run1 基线
(如撞 mt4000 校正题数异常多),优先削减尚未执行的最贵臂
(`plainctx@sonnet5`,排在执行顺序最后)而不是超支。实际花费见
`results/opt_batch46c_verdict.md` §成本。

## 四、后续建议(不在本批预算内,先记录判据)

若要把 H1/H3 补齐到任务书字面要求的 n=3:
- 六臂各补 run3:预算 ≈$11.18(与本批 run2 同量级);
- 只给 `plainctx@sonnet5` 单独补 run3(H3 最需要第三个点):预算
  ≈$5.85,可作为最小追加实验独立提交。
