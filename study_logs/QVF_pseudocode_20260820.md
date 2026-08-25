# QVF 分步伪代码(导师要求:每一步可逐行检查)

> 2026-08-20 初稿。每个算法框忠实对应仓库实现,标注源文件;
> 叙事框架:**现有记忆模块对时序感知不敏感**——QVF 的每一步都是把"时序感知"
> 从读者的隐性能力,变成显式的数据结构与代码操作。

---

## 算法 1 · 写入:对话 → 带日期状态卡片
(`scripts/wt_qvf_prototype.py` write 阶段;`qvf/engine_bridge.py` 卡片契约)

```
输入: 用户会话序列 sessions = [(date_i, turns_i)]
输出: 卡片库 records

for (date, turns) in sessions:                # 逐会话,只见文本+日期
    payload ← {memory_id, date, text(turns)}  # 不含链、不含金答案(无泄露)
    cards ← LLM_extract(payload, 契约)        # 温度0;契约字段:
        # value 值 / stated_date 宣告日期 / source_span 逐字锚点
        # / owner 归属 / slot_class 槽位类 / slot_cardinality 单值|集合
        # / replaces 替换边(指向被取代记录)
    for c in cards:
        assert c.source_span ⊆ text(turns)    # 锚点必须逐字在原文
        records.append(c)
```
**时序感知点**:日期在写入时钉进卡片,读取侧不再依赖读者"感觉"先后。

## 算法 2 · 筛选:query 条件下的记录选择
(`scripts/complex_query_arm.py` `_select_pool` / `_chain`)

```
输入: records, 槽位 slot, 问题 q
输出: 有序状态链 chain

pool ← [r ∈ records : r.slot_class ≈ slot 或 词面重叠(r, slot, q)]
chain ← sort(pool, key = 生效日期(r))         # 时序显式化:排序是代码做的
chain ← 合并相邻同值(chain)                   # 一行 = 一次真实转移
if 计数类(q): chain ← 卫生化(chain)           # 去重复宣告
return chain[:12]                             # 证据上限
```

## 算法 3 · 成员过滤:语义角色判断 + 确定性授权
(`scripts/chain_membership_filter.py`;修复"同主题错属性"污染)

```
输入: 库 pool(算法2 同口径), 槽位 slot, 库原文 blob
输出: 过滤后 pool'

decisions ← LLM_judge(slot, pool)             # 每库一次调用,问句:
    # "这张卡的值是不是 slot 本身的一次状态宣告?"
    # 规则: 主题相邻≠成员(never-infer);member=true 必须附逐字引文
for (r, d) in zip(pool, decisions):           # ―― 确定性授权,代码说了算 ――
    keep(r) ⟺ d.member
             ∧ d.evidence ⊆ r.source_span     # 引文钉回该卡自己的锚点
             ∧ r.source_span ⊆ blob           # 锚点真的在库原文里
    # 任何一步失败 → 剔除(fail-closed);解析失败 → 整池剔除
```
**要点**:模型只提议,授权是三条机械包含检查——不可被话术绕过。

## 算法 4 · 认证:逐条证据的时序角色标注
(`scripts/complex_query_arm.py` `usability_lines`;防泄露断言 `_assert_no_leak`)

```
输入: chain, 问题日期 t_q
输出: 标注行 lines(交给读者,不含任何聚合结果)

for r_i in chain:
    生效区间 ← [date_i, date_{i+1})           # 末段右端 = 开放
    role ← "current"        if t_q ∈ 末段区间
         ← "superseded"     if 区间在 t_q 之前结束(并注明被谁取代)
         ← "not-yet-active" if date_i > t_q
         ← "transition-evidence" (计数/历程类问题下)
    lines += f"[{date_i}] {r_i.value} — {role}"
assert 无答案泄露(lines)                       # 机械正则:出现计数/时长/结论即抛异常
```
**时序感知点**:读者拿到的不是"一堆过去的话",是每条带区间角色的账目。

## 算法 5 · 计算:聚合量由代码算,不让读者做算术
(`scripts/complex_query_arm.py` `execute_plan`,11 算子举 3 例)

```
op = compile(q)                               # 问题 → {op, slot, 参数}(一次 LLM 编译)
switch op:
  case change_count:   ans ← len(chain) − 1
  case point_in_time(t): ans ← r_i 使 date_i ≤ t < date_{i+1}
  case longest_tenure: per_value[v] ← Σ (date_{i+1} − date_i) over r_i.value=v
                       ans ← argmax(per_value)   # 闭区间;末段=0(约定入档)
  case 集合槽位(slot_cardinality=set):           # 集合语义分叉
       current → 列全部未撤销值;count → |distinct|
输出: 证据行 + 结论行(结论行可关,即 filter/usability 消融臂)
```

## 算法 6 · 路由与回退:知道自己什么时候没用
(`QVF_OP_ROUTE` / `QVF_EMPTY_EVIDENCE_DIRECT`,规则冻结后跨语料 +5~7pp)

```
if op ∈ {current, premise_check}: return 直读(q)   # 当前值类:有损中间层只有下行风险
ev ← 算法2..5
if ev = ∅: return 直读(q)                          # 空证据不硬答,整题回退
return 读者(ev)
```

---

## 每步对应的消融臂(伪代码 ↔ 实验的映射,备导师追问)

| 算法 | 关掉它 = 哪个臂 | 单独价值 |
|---|---|---|
| 2 筛选 | raw_select(同选集原文轮) | 纯选择 +12.7(p<1e-5,全 418) |
| 2 规范化 | filter-only vs raw_select | +5.7(p=0.008,全 418) |
| 3 过滤 | 编译臂(未过滤) vs 过滤后 | 污染语料 +21.8(干净条目 +34.7) |
| 4 认证 | usability vs filter-only | +11.2(p≈5e-8) |
| 5 计算 | 编译 vs usability | +6.5(p=4.9e-5,集中时长类 +28.2) |
| 6 路由 | 冻结规则重放 | 跨语料 +5~7 |

## 算法 7 · 账目读法(smoc,2026-08-24 新增,当前最优配置)
(`scripts/repro_batch3.py` render_card_ledger + SMW 读法提示)

```
输入: 卡片库 records, 问题 q
输出: 答案

ledger ← []
for r in sort(records, key=日期(r)):          # 日期缺失时经会话日期映射回填
    ledger += f"[entry N] {日期} | {r.slot}: {r.value} — \"{r.source_span}\""
prompt ← 状态读法指令(两段式:先写状态追踪再按四条优先规则作答)
    # 规则: 后者取代前者 / 常设规则压一次性实例 /
    #       派生值重算不引用缓存 / 事实只因被取代或过期而退休
answer ← LLM(prompt, ledger, q)               # 单次调用,~2.5k token
```
**定位**:账目是写入侧(算法 1)的压缩产物;同一读法吃原文要 13.9k token 才到
84.5,吃账目 2.5k 到 87.8(v1)/82.6(v2)——写入侧价值的直接价格。
读法指令引用 StateMem(arXiv 2608.19652)附录 F.1,按创新性防线以"读法协议"
身份从属于我方账目结构。

## 配置演进注记(2026-08-24 批 4-7 后的默认推荐)

| 机制 | 旗标 | 依据 |
|---|---|---|
| 空证据回退(算法 6 第 2 行) | QVF_EMPTY_EVIDENCE_DIRECT=1 **常开** | 两考场 10 胜 0 负 |
| 末段计入约定(算法 5 longest) | QVF_TENURE_ASOF=1(v2 考场配套) | 链尾题 85.7 自检过 |
| 受控槽位词表(算法 1 建卡) | QVF_SLOT_VOCAB=<词表> | 孪生 +18.2,ev0 6→2 |
| 成员过滤(算法 3) | 修复环组件 | 受控污染:识破 100%/误删 0.7%/p=0.019 |

## 映射表补充(v2 考场口径,576 题)

| 比较 | v2 数值 |
|---|---|
| 结构价(编译+回退+ASOF − 直读) | **+27.3(p=2.2e-25)** |
| 账目读法 − 编译臂 | +6.8(p=1.3e-4);唯 longest_tenure 编译反超 |
| majority 基线 | 30.6 / 20.8(全臂远高于之) |
