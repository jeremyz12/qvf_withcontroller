# 批 29 预注册:ElephantBench 互证双子实验(2026-08-31)

动因:七镜精读(study_logs/lit_elephantbench_20260831.md)G1/G4 两条扩展。
前提披露:ElephantBench 发布**未含**论文承诺的源网页文本(HF+GitHub 均查证,
仅 1,094 QA;行数与论文一致,此前"1,090 vs 1,094"系 HF 取整显示误读,勘销
七镜未核实清单该条)。故 29-OB 采用**合成开卷变体**,明标不测"真实源治愈
参数短视",只测**存储结构是否保值冲突**。

## 29-OB:ElephantBench 合成开卷(写侧冲突保值探针)

- 样本:120 个唯一 item_group(seed 26,每组取 benchmark_id 最小者,规避
  同事实多题非独立性——七镜 B 节发现的坑,我们自己先躲开);
- 底料:每账目一份伪文档(haiku 生成,2-3 句,**金标值逐字闸**,重试 2 次,
  兜底模板句);两文档署名不同虚拟来源;
- 写侧:haiku 从每文档抽状态卡(attribute|value|source|span),**不做机械
  注值**——双值卡覆盖率就是写侧保值的直接测量;
- 三臂(读者 haiku-4.5,判官 gpt-5-mini,ElephantBench 四步 rubric 三档):
  closedbook(其 Fig12a 指令逐字)/ fullplain(双文档入上下文)/
  qvf(卡→账目→读);
- 判据(写死):
  P1 主判据:qvf C ≥ fullplain C − 10pp ⇒ **写侧保值冲突成立**;
  P2 qvf C < fullplain C − 20pp 且双值卡覆盖 < 80% ⇒ **冲突坍缩证实**
     (负结果照记,连 MemConflict conditional 盲区叙事);
  P3 closedbook C 为 haiku 档短视基线(预期 <25,记录不判);
  P4 双值卡覆盖率照报;
- 预算 ≤$5。产物 results/ext_elephant_{docs,cards}.json、
  ext_elephant_{closedbook,fullplain,qvf}.jsonl。

## 29-K:条件完整度 K 移植(记忆系统偏召的统一度量)

- 输入(全部既有存档,零新推理跑):
  STALE:ext_stale_{smoc,direct}_b19.rejudged.jsonl(120×2),双账目 =
  源档 M_old/M_new(data/stale_T1_T2_400_FULL.json 经 probing_query 文本回连);
  COND:ext_memconflict_smoc_b20_cond.jsonl + ext_memconflict_direct_b20.jsonl
  (40×2),账目 = 条件分支结构;
- 三档重判(判官 gpt-5-mini):
  STALE:complete=现值对**且明确承认变更/旧态**;partial=仅现值;
  failed=以陈值为现值或答错;
  COND:complete=条件结构完整(条件+各分支值);partial=值对但条件丢/只报
  一支;failed=违金标;
- 判据(写死):
  K1 主判据:smoc K ≥ direct K + 10pp ⇒ "账目降低记忆系统偏召"成立;
  K2 无论方向,C/P/F/K 四元组双臂照报,conditional 盲区(−32.5)以 K 语言
  重述入档;
- 预算 ≤$2。产物 results/ext_k_rescore_20260831.jsonl + 汇总。

两实验判官均为 gpt-5-mini(与读者 haiku 异家族);统计:双臂配对 McNemar
(以 complete 为二值事件);60/120/40 均探针帽,不外推。

## 29c 修正案(2026-08-31,发跑前注册):表达轴读法修复

- 干预:ext_smoc_arm 读法加环境门控 QVF_LEDGER_CITE=1,在 F.1 协议后追加
  一句:"引述支持答案的账目行;若相关状态随时间变化,同时给出早先值与当前
  值('previously X, now Y')"。冻结件 repro_batch3 不动。
- 重跑:STALE b19 smoc 120 + COND b20 smoc 40(同店同题同读者);
- 判据(写死):C1 表达轴 = 修后 smoc K ≥ direct K − 5pp(STALE);
  C2 正确轴不回退 = arena 判官通过率 ≥ 61.7 − 5pp;两条都过才算修复成立;
  COND C 改善幅度照报不设线。预算 ≤$3。
