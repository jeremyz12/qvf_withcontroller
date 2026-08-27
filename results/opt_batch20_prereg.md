# 预注册:批 20——条件绑定盲区治疗(条件保值建卡变体,MemConflict conditional)

日期:2026-08-28。动因:批 17 解剖——conditional 8:14 大幅落后,归因"卡片把
'如果 X 则 Y'压平成 Y,绑定条件丢失"(结构性边界)。本批测**最小治疗**:
建卡提示词追加条件保值规则(QVF_CARD_CONDVAL=1,env 门控,默认 0 逐字节
不变;条件留在 value 内,异条件并存不互替),不改 schema、不动冻结配置。

## 设计(三臂同题配对,40 题新鲜 conditional)

- 题:MemConflict 已建卡 10 店内新鲜 conditional 40 题(seed=20,排除批 17
  已用 qid;协议同批 17:cutoff 切断 + Today 注入);
- **A direct** top-10(对照,探针里的强臂);
- **B smoc 原卡**(results/ext_cards_memconflict,探针里的弱臂);
- **C smoc 条件卡**(QVF_CARD_CONDVAL=1 重建同 10 店 →
  results/ext_cards_memconflict_cond);
- 判分:ClaudeJudge 代理口径(与批 17 memconflict 同,分数可与探针并读)。

## 判据(写死)

- **采纳**:C ≥ B + 15pp 且 C ≥ A − 10pp → QVF_CARD_CONDVAL 转正为
  受控场景旗标(条件类语料建议开),入旗标表;WikiState 冻结配置零影响
  by construction(默认 0);
- C − B ∈ (0, +15pp):方向正但不足,入档不采纳;
- C ≤ B:判负——条件保值提示词治不了,盲区归 schema 本质,limitations
  原句保留并加"提示词级治疗已试"一句;
- 附带记录:A/B 新鲜复测与探针 14:8 方向是否一致(采样稳定性)。

## 预算

变体建卡 10 店 ≈$5 + 三臂 120 行 ≈$2.5 ≈ **$8**;跑前本文件先提交。
