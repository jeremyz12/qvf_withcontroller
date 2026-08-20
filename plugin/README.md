# qvf_plugin — 即插即用的查询条件化记忆层

QVF(Query-conditioned Validity Filtering)研究原型的**单文件可分发版**。
只依赖 `anthropic`,零仓库耦合;把评测过的六个机制打包成一个类。

## 快速开始

```bash
pip install anthropic
set ANTHROPIC_API_KEY=sk-ant-...   # 或写进环境
python demo.py                      # 6 个会话进,4 类问题出
```

```python
from qvf_plugin import QVFMemory

mem = QVFMemory()                                   # model 默认 claude-haiku-4-5
mem.ingest("Officially started at CERN today ...", date="1989-06-01")
out = mem.ask("Which employer did I hold the longest?", today="1998-09-01")
print(out["route"])     # qvf(longest_tenure)
print(out["answer"])    # ... CERN ...
mem.save("store.json"); mem.load("store.json")      # 持久化
```

## 里面是什么(机制 → 研究仓库中的实测依据)

| 机制 | 做什么 | 依据(同题配对) |
|---|---|---|
| 写入建卡 | 会话→带日期状态卡,逐字锚点机械校验,钉不上即弃 | 锚点契约;时序外置化:乱序呈现下卡片路径 +0.9 不变(基线 −48.2) |
| 选择+规范化 | 槽位选池→按日期排序→相邻同值合并 | 纯选择 +17.0pp;规范化再 +9.0 |
| 成员过滤 | LLM 判语义角色,**代码做确定性授权**(引文⊆锚点⊆原文) | 链精度 0.56→0.88;污染语料端到端 +21.8pp |
| 认证行 | 逐条标 current/superseded/not-yet-active,不含聚合结果 | 认证段 +11.2pp(p≈5e-8) |
| 代码计算 | 计数/点查/最长任期/首末/轨迹;集合槽位走集合分支 | 计算段 +6.5pp(p=4.9e-5,时长类 +28.2) |
| 路由回退 | 单值当前值题→直读;空证据→直读 | 冻结规则跨语料 +5~7pp;组合策略三种子 +5.1/+5.6/+5.6 |

## 诚实边界

- 上表数字来自研究仓库的冻结评测管线;本文件是**同机制的重新打包**,追求可读可分发,
  未逐字节复刻评测代码(评测复现请用仓库脚本);
- 在"当前值"类问题上本层主动让位给直读——有损中间层在该题型只有下行风险(−4.9pp 实测);
- 自然人写对话上的编译路径尚未验证(缺状态链标注,研究路线图第一项);
- demo 数据:真实人物履历取自 Wikidata(CC0),对话载体为合成。

## 文件

- `qvf_plugin.py` — 全部实现(约 350 行)
- `demo.py` + `demo_sessions.json` — 端到端演示(4/4 题型冒烟通过,2026-08-20)
