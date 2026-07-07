# QVF public answer evaluation

- Answer model: `gpt-4o-mini`
- Judge model: `gpt-4o-mini`
- Cases: 79
- QVF context variant: `post_answer_audit_controller`
- API calls: 230
- Reused target/judge rows: 43/43
- Estimated total USD: 0.091720

| Method | Accuracy | Correct | API calls | Mean target latency | Target tokens | Judge tokens | Estimated USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| `direct_extracted_memories` | 51.9% | 41/79 | 158 | 2.19s | 73358 | 86092 | $0.029956 |
| `qvf_validity_packed_context` | 58.2% | 46/79 | 72 | 3.23s | 206069 | 185495 | $0.061763 |

This is a public-slice pilot over extracted candidate memories. Treat failures as a mix of extraction recall, QVF packing, and answer-model behavior.
