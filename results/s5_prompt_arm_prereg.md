# 预注册:S5 提示词臂(§5.3 实验缺口)

写于开跑前,不得挪动。

## 缺口
`prompt_rows_all.jsonl` 的 4,482 个 qid 与 S5 的 418 题交集为 **0**。
故"QVF 在复杂聚合上优于提示词基线"目前**只有跨卷比较,没有同题证据**。

## 臂定义(可比性要件)
`QVF_WARN_INSTRUCTION=1` 下的 `scripts/wsc_direct_arm.py`:
- 检索:与直读臂完全相同(dense,top-10,**用原问题检索**,指令不进检索)
- 读者:`claude-haiku-4-5`,temperature=0,仅问题后追加 `_WARN_INSTRUCTION`
- 指令文本:运行时用 AST 从 `scripts/run_decisive_stale.py` 取同名字面量,
  **构造上保证逐字节相同**(324 字节,已断言)
- 判官:与直读臂同一 `ClaudeJudge`
- 旗标关时与引入旗标前逐字节等价(`_rq = q["question"]`,mode 不变)

## 同题对照物(均在同一 418 题上)
| 臂 | 成绩 | 产物 |
|---|---|---|
| 直读 | 48.33% | `results/wsc_direct_s5_all_b1_union.jsonl` |
| QVF 编译臂 | 83.73% | 见 HANDOFF §七 |
| **提示词臂** | 待测 | `results/wsc_warned_s5_all_b1.jsonl` |

## 判据(先写死,不得放宽)
| 提示词臂成绩 | 判决 |
|---|---|
| **≤ 70.00%** | "QVF 在复杂聚合上优于提示词基线"**被证实**(同题,差距 ≥13.73pp) |
| **≥ 83.73%** | **被否定**——一条指令即可追平编译臂,该主张全面撤回 |
| 70.00–83.73% | 部分成立;此后 S5 的一切对外表述**必须以提示词臂为主基线**,不得再用直读 48.33% 作对照 |

## 必须同页报的
1. 418 全量 **与** 剔除 19 题 P551 后的 399 题两个数(P551 已被直读臂与编译臂消费过,
   本次不新烧持出集,但保纯度者用 399)
2. 四个题型各自的分层成绩(`change_count` / `count_before` / `first_vs_last` / `longest_tenure`)
3. token 与 $ 实测
4. `longest_tenure` 的 gold 已知有缺陷(HANDOFF §5.6:接回真实 end 后 55/92 gold 被推翻),
   故该题型的三臂比较只在"同一份有缺陷 gold"下有效,不得单独引用其绝对值

## 嵌入后端的实测确认(开跑前补,2026-08-18)
产物不记后端,而 `_retriever_cls()` 默认 `ollama`——若选错,对照即失效
(本项目实测换嵌入值 −2.67pp)。故用归档的 `retrieved_memory_ids` 反查:
以 `QVF_EMBED_BACKEND=openai` 复现直读臂的检索,4/4 题**顺序全同、10/10 命中**。
结论:直读臂使用 OpenAI 嵌入,本次提示词臂同样以 `QVF_EMBED_BACKEND=openai` 运行。
