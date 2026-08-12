# 冻结版全量补跑清单(freeze-20260805 = ecac890)

规则:direct 臂不受裁决代码影响可复用;species2/组合臂一律冻结版重跑;gpt 栈缺什么补什么。

| # | 基准 | 栈 | 臂 | 输出 | 状态 |
|---|---|---|---|---|---|
| A1 | STALE-400 (1200) | haiku | species2 | final_h45_{off}.jsonl | wave1 |
| A2 | STALE-400 (1200) | gpt | species2 | final_gpt_{off}.jsonl | wave1(最长杆) |
| B1 | STALE-Chain 212 | haiku | species2(top-10) | final_chain_h45.jsonl | wave1 |
| B1b | STALE-Chain 212 | haiku | 组合(fullctx+QVF) | chainfull_fullctx_qvf.jsonl | ✓ 已是冻结版 |
| B2 | STALE-Chain 212 | gpt | direct + species2 | final_chain_gpt_*.jsonl | wave1 |
| C1 | TempReason 干净+原文 n=200 | haiku | species2 ×2 | final_tr{c,r}_h45.jsonl | wave2 |
| C2 | TempReason 干净+原文 n=200 | gpt | direct ×2 + species2 ×2 | final_tr{c,r}_gpt_*.jsonl | wave2 |
| D1 | HoH n=200 (202608) | haiku | species2 | final_hoh_h45.jsonl | wave2 |
| D2 | HoH n=200 | gpt | direct + species2 | final_hoh_gpt_*.jsonl | wave2 |
| E1 | LoCoMo 对抗+单跳 n=50 | haiku | abstain ×2 | final_lc{a,s}_h45.jsonl | wave3 |
| E2 | LoCoMo 对抗+单跳 n=50 | gpt | direct ×2 + abstain ×2 | final_lc{a,s}_gpt_*.jsonl | wave3 |
| F1 | MemConflict fresh150 (20260805) | haiku | species2 | final_mc_h45.jsonl | wave3 |
| F2 | MemConflict fresh150 | gpt | direct + species2 | final_mc_gpt_*.jsonl | wave3 |
| G1 | LME TR133 + KU50 | haiku | species2 ×2 | final_lme{t,k}_h45.jsonl | wave3 |
| G2 | LME TR133 + KU50 | gpt | direct ×2 + species2 ×2 | final_lme{t,k}_gpt_*.jsonl | wave3 |

direct 复用:STALE-400 双栈(full400_*)、chain haiku(chainfull_s* dense_direct)、TempReason/HoH/LoCoMo/MC/LME 的 haiku direct 均已有。
