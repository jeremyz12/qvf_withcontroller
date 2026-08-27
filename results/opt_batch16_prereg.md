# 预注册:批 16——读者升级头条(sonnet-5 读账目,v1 418 全量)

日期:2026-08-27。动因:跨模型探针中 sonnet-5 读账目 96.7%(60 题易样本,
+5~11pp 易样本偏差在案);全量证实与否决定"强读者配置"能否入册。
易样本教训在前:**60 题数字不得外推,本批以 418 全量为准**。

## 配置(冻结 harness,读者一处替换)

- `QVF_READER_MODEL=claude-sonnet-5 QVF_READER_MAXTOK=1500
  python scripts/repro_batch3.py --system smoc --full
  --out results/wsc_s5_smoc_sonnet5.jsonl`;
- 判官、卡店、提示词、题集(v1 418)全部不变;sonnet-5 拒收 temperature,
  该参数按已存档陷阱移除(haiku 臂仍显式 t=0);
- max_tokens 800→1500 是读者侧防截断适配(gpt-5-mini 截断判废教训),
  非证据结构改动;**截断自查**:usage_output_tokens ≥ 1495 的行占比 ≥2%
  即本批判废,升上限重跑。

## 判据(写死)

- 配对对象:run1 results/wsc_s5_smoc.jsonl(87.80)与
  run2 results/wsc_smoc418_rerun_20260826.jsonl(89.00),同 418 题;
- **采纳"强读者可选配置"**:acc ≥ 90.4(= 88.4 + 2pp)且对 run1、run2
  的配对 McNemar 至少一个 p < 0.05 → master/讲稿加"读者升级"行,
  双读者并报;**头条仍以 haiku 88.4 为主**(成本口径与全表一致性);
- acc ∈ [86.4, 90.4):中性入档,口径不动;
- acc < 86.4:判负入档——"强读者不增益账目"本身是可写边界
  (与证据饥饿论并置:强读者救不了穷证据,也未必增益富证据);
- 成本三项(token/$/延迟)照记,与 haiku 行并列进成本表。

## 预算

418 题 sonnet-5 读者 + Claude 判官 ≈ **$5-8**;后台 ~1-1.5 小时。
