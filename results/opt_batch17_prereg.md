# 预注册:批 17——外部考场三连探针(MemConflict / STALE / MemOps,抽样先行)

日期:2026-08-28。动因:用户指令"外部考场要跑"。三考场已逐文件验真并转统一
店格式(舰队报告存 tasks/wn1mltb01.output;转换器 scripts/ext_convert_*.py)。
按 token 纪律探针先行,全量另批预注册。

## 考场与采样(seed=17,写死)

| 考场 | 店采样 | 题采样(共 60/场) | 切断/口径要点 |
|---|---|---|---|
| MemConflict(30 店,~25 万 tok/店) | 10 店 | dynamic 30 / static 15 / conditional 15 | **两臂记忆视图按题面 session_date 切断**(官方增量协议,防未来泄漏);TODAY=cutoff |
| STALE(400 店,~17 万 tok/店) | 20 店 | 每店 dim1/2/3 各 1 = 60 | 无切断(题在全部会话后);另设 20 题全文直读参考臂(官方喂法,分层 7/7/6) |
| MemOps(403 店,~8.5 万 tok/店,**无日期**) | 20 店(5 操作类各 4) | 每店 3 probe,按 probe 类型分层 | 只取 evaluation_setting=longitudinal(去除官方 adjacent 重复);无日期=账目退化为序保持,如实测 |

## 臂(每场同题配对)

- **direct**:top-10 稠密检索基线(ext_direct_arm.py,与 WikiState 48.61 臂同口径;
  MemConflict 加 cutoff 过滤后再检索);
- **smoc**:冻结建卡(write_phase 原样,卡店 results/ext_cards_*)+ 账目读法
  (ext_smoc_arm.py,渲染/提示词/读者 import 冻结原件;MemConflict 账目行按
  cutoff 过滤重编号);
- **stale-fullctx 参考臂**:QVF_FULL_CONTEXT=1 直读(20 题),对齐官方全文喂法。

## 判分(主指标写死)

- MemConflict:ClaudeJudge 默认规则对其自然语言参考答案(**代理口径**,引用时
  注明非官方 rubric;分 dim 报);
- STALE:**场判官**——按官方三维二元判据重建(meta 内 M_old/M_new/explanation/
  judge_criterion;haiku 判官,pass/fail),ClaudeJudge 行保留仅作附注;
- MemOps:**场判官**——按官方 rubric(must_include/must_not_include/leakage;
  Forget 类"说了=错"),同上双轨。

## 升级判据(每场独立,写死)

- smoc − direct ≥ **+10pp** 且 McNemar p<0.1 → 该场排全量(另批预注册);
- (−10, +10) → 中性入档,**全量确认前不得对外引用**;
- ≤ −10pp → 判负如实入档(外场失败也是边界数据)。
- 附加记录项(不设门槛):建卡压缩率(外语料 卡数/字符;WikiState 先例 50K 字符
  →78 卡→2.5K tok),MemOps 无日期退化幅度,STALE dim3(隐式查询)检索劣势
  是否由账目补偿。

## 预算与纪律

建卡 50 店(外语料压缩率未知,估 $8-18,记实际)+ 双臂 180 题 + 参考臂 20 题
+ 场判官 ≈ **总预算 ≤$30**;超支中止入档。数据不入 git(unified 文件 155-292MB,
MemConflict 无 LICENSE 不得再分发);概率性结论一律带"探针 n=60"帽。
