# QVF public answer evaluation

- Answer model: `gpt-4o-mini`
- Judge model: `gpt-4o-mini`
- Cases: 500
- QVF context variant: `post_answer_audit_controller`
- API calls: 1097
- Reused target/judge rows: 452/451
- Estimated total USD: 0.495350

| Method | Accuracy | Correct | API calls | Mean target latency | Target tokens | Judge tokens | Estimated USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| `direct_extracted_memories` | 40.0% | 200/500 | 1000 | 2.06s | 1200358 | 1284972 | $0.412341 |
| `qvf_validity_packed_context` | 40.6% | 203/500 | 97 | 2.35s | 274804 | 251047 | $0.083008 |

This is a public-slice pilot over extracted candidate memories. Treat failures as a mix of extraction recall, QVF packing, and answer-model behavior.
