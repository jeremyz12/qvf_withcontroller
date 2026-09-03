# 批 34 判决(滚动):WikiState v2.4 全面复审 → v2.5(2026-09-03)

预注册 results/opt_batch34_prereg.md。

## 一、扫描(Fable 5.1,144/144 链,严格规则"职位就是职位")
- 逐字核实标记 1,390 条(非逐字 0):年代错乱 1,014 / 其他 212 / 助手回声 69 / 同槽状态 42 / 金标议题 19 / 职衔晋升 14 / 链前历史 10 / 同槽转移 5 / 他人歧义 5。
- 542 锚句逐字命中、日期与会话一致、会话日期单调(机械检查);发现 7 条链各含 1 处逐字节重复的填充会话;8 道 longest_tenure 前两名任期差 ≤1%。
- 年代错乱 1,014 条不改任何金标,汇总入 results/b34_anachronism_summary.md(datasheet 已知瑕疵)。

## 二、裁决(Opus,按链,94 链 217 条槽位相关/可能影响金标的标记)
- **CONFIRMED 49**(助手回声 25 / 同槽状态 15 / 同槽转移 4 / 其他 3 / 链前历史 1 / 金标议题 1)、GOLD_ISSUE 2、BENIGN 166。
- 确认项集中在:wikiP551010(4)、wikiP108010(3,UBC/温哥华搬家)、wikiP108040(3),另 9 链各 2。
- 典型:助手回声"congratulations on impressing the VP of Marketing / your website launch"、用户"I've started a Slack group for freelance writers"、"classes start at UBC"(与 CERN 行冲突)。
- GOLD_ISSUE 两条**不改链**,入 datasheet:wikiP108026 两行 Weill Cornell Medical Center / Weill Cornell Medicine 为同机构家族的两个 Wikidata 项;wikiP39042 第 2 行无任期终止行——WikiState 链只建模起始/取代,不建模终止,属设计口径。

## 三、v2.5 构建(scripts/build_corpus_v25.py,双闸)
- 手术删除 47 处(整轮 22、句级 25);1 处**锚点保护**跳过(wikiP39039 确认句与金标锚句同句,不动);1 处因所在整轮已删而未再找到;
- 7 处重复填充会话去重(均为 FILLER,保留首次出现);
- 题集移除 8 道近平局 longest_tenure 题(576 → 568),链不动;
- 闸:542/542 锚逐字在;确认句残留 0;语料 7,850,483 → 7,826,845 字符(−0.30%),会话 4,862 → 4,855;sha256 8d179c4b…。

## 四、v25 评审链接
- 生成器 scripts/build_vX_full_items.py(修两处对照题泄漏:按植入后的链高亮、对照题 id 同形 145–149);149 题 = 144 链 + 5 植入,两位同题同序:reviewer-v25(真人)、opus5-agent-v25(机器)。
- 流程:机器先审,非对照题零报错 → 通知人工;否则修复出 v2.6。
