# 批 48 预注册 — 冻结"评审修复"配置全量落地:144 链重建 + 蕴含过滤 + 560 题两轮读者

写于任何建店/读者调用之前(2026-09-04)。

配置(冻结):抽取器 claude-sonnet-5,QVF_CARD_TEMP0=0,QVF_CARD_THINKING=off,QVF_CARD_SLIM=1,QVF_CARD_STAGE1_K=8,QVF_CARD_VALNORM=1 → 店 `results/wt_cards_v51`;再用 `scripts/b47_entail_verify.py --lane-only` 按断言类型过滤(丢 plan/task/other_person/hypothetical/ended/restate,不看 entailed 标志)→ `results/wt_cards_v51f`(全部标签在 `wt_cards_v51f_ent`)。读者 claude-haiku-4-5,smoc 臂,`data/wsc_s5_v25.jsonl` 560 题,两轮独立。

假设与判据(对照 v48f,批 46d):
- H1 编译上限(b46d 口径,560 题):v51f ≥ 92.5%(v48f)。预期 ≥ 93.8(批 47 蕴含过滤在 v48 上的数字)。
- H2 读者准确率两轮均值:与 v48f 两轮均值 90.00 的差在 ±3pp 内(等价);不预期上升(批 46d 经验)。配对 McNemar 对 v48f run1/run2,144 链簇自助 CI。
- H3 读者输入 token/题 ≤ 2,753(v48f);预期明显下降(卡/店 50 → 约 17)。
- H4 金标行:v51f 漏行 ≤ 14(v48f);全量 542 行零 hit→miss 相对 v51 未过滤。
- H5 成本:建店 + 蕴含 + 两轮读者 ≤ $14。

硬约束:v45/v48/v48f 等既有店只读;新店新目录;派生店带源 sha256;失败批不静默(QVF_CARD_FAIL_LOUD=2)。
