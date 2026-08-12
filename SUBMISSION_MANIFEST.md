# 代码提交包清单(2026-08-11)

> 标准:审稿人凭本包 + API key 可复现论文任一表格数字;每个数字可回溯到 results/ 的逐题原始行。

## 一、代码(按角色分组)

### 核心包(方法本体)
| 路径 | 内容 |
|---|---|
| `qvf/engine_bridge.py` | 抽取契约(档案卡 schema + 规则提示词)、矛盾阅读器 |
| `qvf/retrieval.py` | BM25 / OpenAI 稠密双后端检索 |
| `qvf/judge.py` | opus 判官(LongMemEval 协议实现) |
| `qvf/generator.py` / `openai_bridge.py` | 读者封装(anthropic / openai) |
| `scripts/run_decisive_stale.py` | **读取时裁决层(~150 行核心)+ 30+ 条件注册表** |
| `scripts/wt_qvf_prototype.py` | **写入时档案卡库(建卡/聚焦/连通分量裁决)** |
| `scripts/qvf_router.py` | **整合路由器 v1.2(冻结)+ v1.1/v1.3 消融在版本史** |

### 数据集构建(WikiState 流水线)
`scripts/wikistate_scrape.py` → `wikistate_build.py`(参数泄漏过滤)→ `wikistate_render.py`(逐字/日期验证器);`scripts/gen_stale_chain.py`(合成链+确定性验证器)

### 实验臂(修正框定协议)
`scripts/framing_arm.py`(直读)/ `framing_tlcot_arm.py`(政策提示)/ `framing_qvf_arm.py`(读取时)/ `framing_fullctx_arm.py`(全上下文)/ `framing_bm25_arm.py`(稀疏检索)

### 基线系统
`scripts/run_mem0_baseline.py` / `graphiti_baseline.py`(Neo4j docker,端口 17687)/ `summary_memory_baseline.py`

### 适配器与分析
`scripts/adapt_stale_for_wt.py` / `adapt_lme_for_wt.py` / `adapt_locomo_for_wt.py` / `adapt_locomo_full.py`;`problem_align_slice.py`(问题含量分类)/ `mc_s3_recheck.py`(标签复核)/ `score_cc_harness.py`

## 二、数据(许可齐全)

- `data/wikistate_*`:WikiState 家族 311 条目/1244 问(Wikidata CC0 机械金答案;干扰会话 STALE CC BY 4.0 衍生,attribution 内嵌每条目)
- `data/stale_chain_full.json` / `stale_chain_confirm.json`(CC BY 衍生)
- 适配器产物(`stale400_s50_wt.json`、`lme_*_wt.json`、`locomo_*.json`)——由脚本一键再生,提交脚本即可
- **数据卡(待写)**:构建流水线、参数过滤统计、措辞对齐规程、许可声明

## 三、结果与档案(可审计层)

- `results/*.jsonl`:全部臂的逐题原始行(question/gold/answer/judge_correct/tokens)
- `results/wt_cards/`:692 条目档案卡库(读取阶段复现所需;或附建卡再生命令)
- `results/overnight_20260807_verdicts.md`:判决档案(§负十二 至 §六 全部判决)
- `study_logs/VERSION_LEDGER.md`:方法/数据/协议版本史(含证伪记录)
- `results/problem_labels.json` / `mc_labels_opus.json`:问题含量标签(haiku+opus 双分类)

## 四、复现手册(README 骨架,待展开)

```
安装:python -m pip install -r requirements.txt;cp .env.example .env 填入 ANTHROPIC/OPENAI key
表2(难度面板):python scripts/framing_arm.py --benchmark stale_chain --data data/wikistate_full.json --out ...
表3(wt 四域):python scripts/wt_qvf_prototype.py --phase write/read --data data/wikistate_full_P108_w2.json ...
表4(路由):python scripts/qvf_router.py
判官恒 claude-opus;全部臂 --resume 断点安全
```
(每张论文表 → 命令的完整映射写进 README;requirements.txt 待从环境导出)

## 五、提交前卫生检查单

| # | 项 | 状态 |
|---|---|---|
| 1 | `.env` 绝不入包;提供 `.env.example` 占位 | ⚠ 打包时执行 |
| 2 | **双盲脱敏**:`wikistate_scrape.py` UA 串内含真实邮箱 → 换占位符 | ⚠ 必改 |
| 3 | 判官/考卷答案键(`results/cc_harness_key*.json`)与答题产物分离说明 | ✓ 已分离 |
| 4 | Windows 编码:所有文本 IO 显式 UTF-8(GBK 事故教训) | ✓ 已遵守 |
| 5 | scratchpad/、memory/、PPT 生成器不入包 | ⚠ 打包时排除 |
| 6 | 冻结 tag:代码 freeze-20260805 + 本轮增量需打新 tag(如 freeze-20260811) | ⚠ 待打 |
| 7 | 文献 ⚠ 编号 12 处核对(REFERENCES_20260811.md) | ⚠ 写作期 |
| 8 | Graphiti 基线注明默认配置 + 公平性探针证据 | ✓ 档案在案 |

## 六、不提交的东西

scratchpad 临时件、PPT/演讲稿(汇报材料非论文附件)、memory 目录、失败首跑产物(gpt 路由错误 0/228 等——已在档案标注作废,文件可留可删)
