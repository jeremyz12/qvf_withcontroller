# 第二轮人工核验:设计与链接(2026-09-02)

## 为什么要第二轮

第一轮(v2.0 语料)已完成 senior2 84/84、author 8/149、senior1 0/85,并促成
金标污染的发现与三刀修复(批 31)。第二轮的目的变了:**不是再找一遍问题,
而是验证修复后的 v2.3 是否干净**,并把 κ 一致率补上。

## 题目构成(85 题,三人完全重叠)

| 组 | 题数 | 作用 |
|---|---|---|
| **cleaned** | 61 | 被三刀清洗过的链——验证修复是否到位 |
| **control** | 19 | 未被触及的链——测假阳性率(不该报错却报错) |
| **catch** | 5 | 全新植入错误(value_swap / date_shift / delete_row / fabricate_anchor / add_row)——测注意力 |

- 语料与链均取自 **data/wikistate_full_ALL_v23.json**(净化后);
- 三人同一套 85 题、同一随机顺序 → **κ 可在完整重叠集上计算**(第一轮因
  senior1 未作答而无法计算);
- 旧对照题对 senior2 已失效,故本轮全部重新植入;答案键
  **data/round2_keymap.json**(catch 标记 + 注入描述 + 分组)。

## 链接

| 评审人 | 链接 |
|---|---|
| author | http://149.28.167.100/r/r25DMUc7uwF5gEWX |
| senior1 | http://149.28.167.100/r/r24JsEmD7YGeTtHz |
| senior2 | http://149.28.167.100/r/r2gnZ8CjEafaEPL7 |

第一轮链接保持有效(author 149 题尚未做完),两轮数据分开存储、互不覆盖。

## 分析计划(收数后)

1. **修复验证**:cleaned 组的 errors 率应显著低于第一轮同批链;
2. **假阳性**:control 组 errors 率应接近 0;
3. **注意力**:catch 组应被判 errors(第一轮 senior2 为 2/3);
4. **κ**:senior1 × senior2 在 85 题上的 Cohen's κ —— 投稿必须件;
5. **人机对照**:与 results/machine_review_149.jsonl(机器复核)交叉,
   报人机一致率与各自的漏检。
