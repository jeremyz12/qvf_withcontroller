# MemConflict100 Full Current-Code API Analysis (2026-07-06)

Evidence label: local main slice; API-backed MemConflict100 official answer-eval, not a full four-benchmark result.

## Key results

| metric | value |
|---|---:|
| cases | 100 |
| Direct accuracy | 57/100 = 57.00% |
| QVF accuracy | 71/100 = 71.00% |
| delta | +14.00% |
| QVF wins | 14 |
| QVF losses | 0 |
| both correct | 57 |
| both wrong | 29 |
| API calls | 368 |
| estimated USD | 0.201030 |

## Controller action counts

| action | count |
|---|---:|
| condition_scope_packet | 39 |
| raw_recall_with_annotations | 29 |
| timeline_or_conflict_packet | 32 |

## Retrieval feedback issue counts

| issue | count |
|---|---:|
| condition_scope_evidence_unsupported | 6 |
| missing_change_pair_evidence | 13 |
| missing_current_evidence | 2 |

## QVF loss taxonomy

| action / feedback / error | count |
|---|---:|
| none | 0 |

## Repaired case check

| case_id | direct | qvf | outcome | qvf answer excerpt |
|---|---:|---:|---|---|
| auto_memconflict_official_2e62aacf_70e2_3d5a_b6bd_6f9ad776893d_s008_q_001_dynamic_conflict_q_001 | True | True | both_correct | {   "answer": "Yes, the user's work status recently changed to 'busy' with a heavier load.",   "used_memory_ids": [     "auto_memconflict_official_2e62aacf_70e2_3d5a_b6bd_6f9ad776893d_s008_q_001_dynamic_conflict_q_001::e |
| auto_memconflict_official_5a40c38b_61aa_afc0_1837_4367df2efbc1_s008_q_001_dynamic_conflict_q_001 | True | True | both_correct | {   "answer": "Yes, the user's children status changed from not having children before May 2022 to having a baby named Christopher Moore.",   "used_memory_ids": [     "auto_memconflict_official_5a40c38b_61aa_afc0_1837_43 |
| auto_memconflict_official_75b15745_6d32_726b_be79_d765808bbfe7_s003_q_002_dynamic_conflict_q_002 | False | False | both_wrong | {   "answer": "User got married to Taylor Morgan on February 24, 2022.",   "used_memory_ids": [     "auto_memconflict_official_75b15745_6d32_726b_be79_d765808bbfe7_s003_q_002_dynamic_conflict_q_002::extracted_000_c69bac7 |
| auto_memconflict_official_9841f645_49ad_3de3_9010_cef938781102_s003_q_002_dynamic_conflict_q_002 | True | True | both_correct | {   "answer": "User's marital status changed from single to dating Michelle Williams.",   "used_memory_ids": [     "auto_memconflict_official_9841f645_49ad_3de3_9010_cef938781102_s003_q_002_dynamic_conflict_q_002::extrac |
| auto_memconflict_official_9841f645_49ad_3de3_9010_cef938781102_s008_q_001_dynamic_conflict_q_001 | True | True | both_correct | {   "answer": "Yes, the user's marital status changed recently to recently married.",   "used_memory_ids": [     "auto_memconflict_official_9841f645_49ad_3de3_9010_cef938781102_s008_q_001_dynamic_conflict_q_001::extracte |
