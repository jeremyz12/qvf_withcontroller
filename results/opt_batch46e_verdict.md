# 批 46e 终判:根因是 08-28 建店时"默认旗标"配置选择,不是代码逻辑缺陷——派生店工作区可退役

**一句话判决**:任务书猜想("建卡器代码在 v42→v43 之间丢了 slot_class/owner
的写入逻辑")被**部分否定,部分证实**——写这两个字段的**代码路径从未删除**,
它从 2026-08-13 起就一直在(`QVF_CARD_KEYS` 旗标门控),v42 能有这两个字段
是因为建店时**显式传了 `QVF_CARD_KEYS=1`**;真正的回归是 2026-08-28 批
22/23 全店重建时把配置写成"冻结建卡器、**默认旗标**",即**没有**再传这个
旗标——代码零改动,是**建店调用约定**丢了。修复(`scripts/wt_qvf_
prototype_v49.py`)据此选择了正确的介入点:不碰旗标/提示词,在写入收尾处
对已抽取的 records 做确定性零 LLM 后处理。三项回归测试全过,干跑重建店与
批 33-A 派生店 `wt_cards_v45k` **8,288 条记录、slot_class/owner 两键零
差异**(逐字节相同)。成本:**$0.00,0 次 LLM/API 调用**(全程确定性映射
+ 本地 JSON 读写)。

## 一、根因:代码从 08-13 起就没变过,变的是 08-28 的建店调用

### 1.1 两处旗标门控(现状,冻结文件 `scripts/wt_qvf_prototype.py` 与
`qvf/engine_bridge.py`,自 commit `c87234a5`(2026-08-13 17:42,"QVF v4.1 +
S5-S7 complex-query extension")起未再改动过默认值——`git log -S
"_CARD_KEYS ="` 对 `scripts/wt_qvf_prototype.py` 只命中这一个 commit):

- `scripts/wt_qvf_prototype.py:44`:`_CARD_KEYS = int(os.environ.get
  ("QVF_CARD_KEYS", "0") or 0)`——默认 **0**;=1 时建卡提示词从
  `CATALOG_PROMPT` 换成追加了 owner/slot_class 两条规则的
  `CATALOG_PROMPT_V4`。
- `qvf/engine_bridge.py:194-208`:`ExtractedRecord` 的 `owner`/`slot_class`
  字段本身写在 `if _CARD_KEYS:` 缩进块里——**旗标关时这两个字段根本不存在
  于 pydantic 模型上**,不是"LLM 输出了但没存",是"模型定义里压根没有这两
  个字段可接"。

即:这从来不是一条"默认行为",而是一条从建库脚本诞生起就存在的**显式
opt-in**。

### 1.2 v42 之所以有这两个字段,是因为建店时显式传了旗标

- commit `68122bdd`(2026-08-15)已确认 v4.2 新域卡片"含 owner/slot_class
  规范键(KEYS=1 的输出特征,抽查 wt_cards_newdom 卡片证实)"。
- commit `a5a4d269`(2026-08-16 14:44)把当时的生产建卡口径写死为
  `QVF_CARD_STRICT=1, QVF_CARD_KEYS=1, QVF_CARD_V5=0`,并明确"与
  `results/wt_cards_v42` 建卡时使用的旗标组合一致"。
- commit `df59b5ff`/`7ac80d72`/`c23b4c4a`(2026-08-18)记录了一次**前车之
  鉴**:一次 opus 对比重建**漏传** `QVF_CARD_KEYS=1`,卡片无 slot_class,
  评测器把对的卡片误判成 `0/8`——事故被抓到、加了"跨配方比较前核对建卡
  旗标"的检查项,但这次事故没有产出任何生产店,不是本次回归的源头。

### 1.3 真正的回归事件:2026-08-28,批 22/23 全店重建"默认旗标"

- `results/opt_batch22_prereg.md`(commit 邻近 `f8bca8a8`,2026-08-28
  10:08,"批22预注册+写入侧三补丁")把同日重建对照臂 **A1** 定义为
  "现行批量打包(**默认旗标**)"——即刻意**不传** `QVF_CARD_KEYS=1`,目的
  是隔离"店龄效应"(建卡模型代际进步),与 owner/slot_class 无关,15 店试
  跑测得 +8.3pp。
- `results/opt_batch23_prereg.md` 同日把这个"默认旗标"配置原样放大到全量
  **144 店**生产重建:"重建:冻结建卡器、**默认旗标**(与 A1 完全同配置)
  → `results/wt_cards_v43`"(后因目录名与 08-16 遗留店冲突改名
  `wt_cards_v43_20260828`)。
- `results/opt_batch23_verdict.md` 判定升版双过(smoc 82.64→86.28,
  p=0.042),**v43 店当场被采纳为新的 v2 主口径**("对外一切卡店数字必挂
  店版本")——回归就此从一次孤立配置选择变成生产基线,后续 v44/v45/v45g/
  v47s 等历次重建/复用均未再补回 `QVF_CARD_KEYS=1`,字段缺失静默传播,直到
  批 33-A(commit `342c50a4`,2026-09-02)用隔离探针查出、定量为
  **−16.67pp**(`results/opt_batch33_A_rebuild_verdict.md` §8)并用
  `scripts/b33A_backfill_slot_class.py` 建了派生店 `wt_cards_v45k` 过渡。

### 1.4 措辞更正(相对任务书前提)

任务书原述"builder scripts/wt_qvf_prototype.py no longer emits slot_class
and owner fields"暗示这是一次**代码**回归。核验后更正:**代码从未失去写这
两个字段的能力**(旗标一直在、逻辑一直对),丢的是**建店调用时的旗标传
参**——一次实验配置("默认旗标"隔离店龄效应)被原样放大为生产重建配置,
而"默认"从旗标引入的第一天起就是关。这个更正不改变下游后果(中间三段
确实整段走无键回退),但决定了正确的修复形态:见第二节。

## 二、修复:`scripts/wt_qvf_prototype_v49.py`(新文件,冻结文件未改一字节)

### 2.1 为什么不是"把 QVF_CARD_KEYS 默认值改成 1"

那等价于把 `CATALOG_PROMPT` 换成 `CATALOG_PROMPT_V4`——**改变发给 LLM 的
提示词字节**,进而可能改变模型的抽取行为/token 用量,不满足任务书"keep
every other byte of behavior identical"。且该路径依赖 LLM 自己吐出合规的
`owner`/`slot_class`,不是确定性的。

### 2.2 实际做法:复用批 33-A 已验证的确定性零 LLM 映射,搬到写入收尾处

`scripts/b33A_backfill_slot_class.py` 已经证明了一套纯代码、零 LLM 的
`slot → slot_class` 映射(与 `scripts/complex_query_arm.SLOT_ALIASES` 同表,
最长别名优先,未命中记 `other:<归一名>`)和 `entity → owner` 抄写规则,并
在派生店 `wt_cards_v45k` 上把中间三段的分数拉回与 v2.0 存档不可分的水平
(§8.3)。v49 把这套逻辑原样搬进 `write_phase()`:

- **提示词/API 调用不变**:`CATALOG_PROMPT`、`_catalog()`、`MODEL`、
  `_CARD_TEMP0` 等一律不动,LLM 收到的每一个字节与冻结版相同。
- **落盘前一步纯代码后处理**:`_catalog()` 返回的 `recs` 列表在写文件之前,
  经 `_apply_card_keys(recs)` 就地补两个键(不改任何既有键值):
  - `slot_class = classify_slot(record["slot"])[0]`——与
    `complex_query_arm.SLOT_ALIASES` 同表、同最长别名优先规则;
  - `owner = record["entity"].strip()`——原样抄写,`"user"` 保持
    `"user"`,其余(第三方姓名/关系词,如 `"cousin_rachel"`)原样保留,
    **不做 self/other 二值化**。这一点特意对齐 `complex_query_arm.
    _select_pool` 里已有的判断 `r.get("owner") in ("", "user")`(该式
    把 `""`/`"user"` 当"本人状态"、其余任意字符串当"他人状态"——这正是
    概念上的 self/other 区分,只是不落成一个字面量);二值化会让这条既有
    判断失配,读取侧反而要跟着改。
- **`git diff` 只有五处**:文档串/用法说明、`Tuple` 类型导入、
  `SLOT_ALIASES` 导入、`write_phase()` 里一行 `_apply_card_keys(recs)` 调
  用、以及文件尾新增的 `classify_slot()`/`_apply_card_keys()`/
  `backfill_store()` 三个函数 + `main()` 里新增的 `backfill` 子命令。其余
  943 行与冻结文件逐字节相同(已用 `diff` 核对)。

### 2.3 干跑模式(零 API,给已建成的旧店补字段用)

```
python scripts/wt_qvf_prototype_v49.py --phase backfill \
    --src results/wt_cards_v45 --dst results/wt_cards_v45k2
```

`backfill_store(src, dst)` 与 `b33A_backfill_slot_class.py` 的
`main()` 同逻辑(同一个 `classify_slot()`/`_apply_card_keys()`),只读
`src`、只写 `dst`,零 LLM、可反复重跑幂等。

## 三、测试:`scripts/test_card_schema_v49.py`(零 API)

三项断言,`python scripts/test_card_schema_v49.py` 与
`python -m pytest scripts/test_card_schema_v49.py -q` 均全过:

| 测试 | 断言 | 结果 |
|---|---|---|
| `test_known_good_store_v45k_passes_schema` | 已知修复店 `wt_cards_v45k`(8,288 条)整店 0 违规 | **PASS** |
| `test_known_bad_store_v45_fails_schema` | 反例:冻结建卡器建的 `wt_cards_v45` 两字段 **0/8288** 覆盖(把根因判决固化进代码) | **PASS** |
| `test_v49_dry_run_reproduces_v45k` | `backfill_store()` 现场重建 `wt_cards_v45k2`,整店 0 违规,且与 `wt_cards_v45k` 逐条 `(uid, record_id)` 对齐后 slot_class/owner **零差异** | **PASS** |

```
PASS  test_known_bad_store_v45_fails_schema
PASS  test_known_good_store_v45k_passes_schema
PASS  test_v49_dry_run_reproduces_v45k
ALL TESTS PASSED
```

`check_store_schema()` 的"合法取值"定义(供复核):`slot_class` 必须是
`SLOT_ALIASES` 七个闭集类目之一(position/employer/team/residence/device/
location/relationship)或 `other:<...>` 前缀——**七类 + 开放前缀**,比任务
书描述的"employer/position/team/residence/other"更宽(任务书列举显然是简写;
`SLOT_ALIASES` 实际还含 device/location/relationship,`classify_slot()`
严格复刻该表,视为口径来源)。`owner` 只强制类型是字符串(存在即合法),不
限定取值集合——理由见 2.2。

### 3.1 干跑数字复核(`--phase backfill` 实跑,非估算)

```
files=144 records=8288
mapped to a SLOT_ALIASES class: 1494 (18.0%)
left as other:*            : 6794 (82.0%)
wrote results/wt_cards_v45k2
```

与 `results/b33A_v45k_mapping.json`(`n_records=8288, mapped=1494,
other=6794`)逐位相同;`diff -rq results/wt_cards_v45k
results/wt_cards_v45k2` 输出为空——两个目录**全部 144 个文件逐字节相同**
(不只是 slot_class/owner 相同,整份 JSON 相同),说明 v49 的映射逻辑与
批 33-A 的派生脚本完全等价,不只是"两键恰好一致"的弱证据。

`results/wt_cards_v45`、`results/wt_cards_v45k` 全程只读,`git status`
确认未被本批触碰;新产物只写入 `results/wt_cards_v45k2`(新目录)。

## 四、下一个店怎么建

**写新店**(建库阶段自动带两个字段,不需要任何额外旗标/后处理步骤):

```
python scripts/wt_qvf_prototype_v49.py --phase write \
    --data <data.json> --cards-dir results/wt_cards_<new>
```

**给已有的冻结版旧店补字段**(零 API,产物落新目录,旧店不动):

```
python scripts/wt_qvf_prototype_v49.py --phase backfill \
    --src results/wt_cards_<old> --dst results/wt_cards_<old>k
```

**回归门禁**(建店/补字段后建议照跑一次):

```
PYTHONUTF8=1 python scripts/test_card_schema_v49.py
```

## 五、遗留与限定

1. **本批不重建任何生产店**——`wt_cards_v43/v44/v45/v45g/v47s` 现有产物
   原样保留;`wt_cards_v45k` 派生店workaround 在**代码层面**已可退役(v49
   证明了同一套逻辑挪到写入侧零差异),但**已发生的评测数字**是否要挂到
   v49 新建的店上,是后续批次的口径决定,不在本批范围。
2. `classify_slot()` 的 `other:*` 覆盖率仍是 82.0%(与批 33-A 一致)——
   这是 `SLOT_ALIASES` 词表本身的粒度上限,不是本批要修的问题;批 33-A
   §8.3 的在线验证已证明这个覆盖率足以让中间三段回到与 v2.0 存档不可分的
   水平。
3. `owner` 字段不做 self/other 二值化的决定(2.2 节)依赖
   `complex_query_arm._select_pool` 现有判断式 `r.get("owner") in
   ("", "user")` 保持不变;若该判断式未来改动,需要同步复核 v49 的
   `_apply_card_keys()` 是否还兼容。
4. 三项回归测试目前只覆盖"干跑重建"路径(读取一个已有 store、离线补字段),
   未覆盖"真实 `--phase write` 全流程"(需要真实 LLM 调用,与"ZERO API
   calls"约束冲突)——`_apply_card_keys()` 在 write_phase 里的调用点是纯
   代码(见 2.2 的 diff 位置),其正确性由同一个 `classify_slot()` 函数保
   证,与干跑路径共享实现,风险由此收窄,但不是逐字节意义上的端到端验证。
