# 批 29 终判:ElephantBench 互证双子——存储恒完整,表达随提示词(2026-08-31)

预注册 results/opt_batch29_prereg.md;判官 gpt-5-mini(与读者 haiku 异家族);
成本 ≈$5(预算 7 内)。harness 勘误:①读者/建卡对真实伤亡类题触发内容过滤,
加容错(空答判 no_credit,共 1 行);②轻量抽卡器对敏感题软拒答致初版双值
覆盖 67.5% 假坍缩,重构提示后 95.8%(修复前后卡档均留存)。

## 29-OB:合成开卷三臂(120 唯一 item_group,读者 haiku-4.5)

| 臂 | C | P | F | K |
|---|---|---|---|---|
| 闭卷(其指令逐字) | 14.2 | 40.0 | 45.8 | 26.2 |
| 全文(双伪文档) | 100.0 | 0.0 | 0.0 | 100.0 |
| **QVF(卡→账目→读)** | **98.3** | 0.8 | 0.8 | **99.2** |

- **P1 成立**:qvf C = fullplain C − 1.7(b=2/c=0,p=0.5 n.s.),远优于
  预注册 −10pp 线——**写侧保值冲突成立**(双值卡覆盖 95.8%,P4);
- P2 坍缩线未触发;P3 短视基线 14.2 < 25(haiku 档参数短视,恰落其论文
  9B 开源与 12B 之间,外部一致性良好);
- qvf vs closedbook:+84.2pp(b=1/c=102,p=2.1e-29);
- 边界:底料为合成净文档(每账目一篇短文),主张仅为"**供给源文时,QVF
  写→账目→读全链保值并表达分歧账目**",不冒充"治愈真实语料参数短视"
  (官方源文本未随集发布,已在预注册披露)。

## 29-K:条件完整度 K 移植(既有外场答案三档重判)

| 场 | 臂 | C | P | F | K |
|---|---|---|---|---|---|
| STALE(120) | smoc | 23.3 | 30.8 | 45.8 | 43.1 |
| STALE(120) | direct | **42.5** | 15.8 | 41.7 | **72.9** |
| COND(40) | smoc | 32.5 | 15.0 | 52.5 | 68.4 |
| COND(40) | direct | **60.0** | 25.0 | 15.0 | 70.6 |

- **K1 主判据判负且方向显著反转**(STALE complete 配对 p=0.0008;COND
  p=0.0127);逐维拆分 direct 三维全胜(dim1 65:28 / dim2 32:28 / dim3 30:15);
- **病灶定位:读侧表达而非写侧存储**——37/40 STALE 卡店含现值内容(内容词
  命中 ≥50%);smoc 给"判断式"答案(二值对但不引述现值实质),direct 把原句
  怼进上下文自然复述双态。典型案:smoc 答"不再安静(因为加了播放列表)"
  ——判断对、实质错(真相:用户在喧闹市场);
- **与原主张不冲突**:arena 判官考"不踩陈值",smoc +15.0(p=0.0079)依然
  族存活;K 判官考"实质完整召回"。**正确性与完整性是两根独立轴:QVF 赢
  正确轴,输表达完整轴(STALE −19.2)**;
- K2 达成:conditional 盲区(−32.5)以 K 语言重述(C 32.5 vs 60.0)。

## 合并判读:统一律

29-OB(表达完整 99.2)与 29-K(表达完整 43.1)用的是**同一存储机制**——
差别只在读侧提示词:OB 的读法明示"来源不一致就全部列出",K 场景是自然
直问。故:**存储完整性由写侧结构保证(≈恒真:卡覆盖 95.8%/37/40);表达
完整性是读法提示词的函数**——这是协议适配律(读法提示词决定行为)的第三
次独立显形。修复候选批 29c(~$2):STALE/COND 读法加一句"引述支持答案的
账目行并说明变化",预期抹平表达轴;判据:smoc K 升至 ≥ direct K − 5pp。

## 论文可用句

"On a synthetic open-book variant of ElephantBench, the write-store-read
pipeline preserves 95.8% of divergent account pairs at write time and
surfaces both accounts on 98.3% of items at read time (vs 14.2% closed-book
for the same reader); transplanting ElephantBench's conditional-completeness
metric K onto STALE reveals that answer-completeness, unlike correctness,
is governed by the read-side prompt rather than the store."
