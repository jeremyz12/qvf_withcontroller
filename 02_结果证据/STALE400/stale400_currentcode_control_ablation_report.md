# STALE400 Current-Code Control Ablation

Evidence label: sharded full benchmark aggregation for fresh current-code sidecar controls; saved replay labels for older direct/no-memory controls.

## Fresh Current-Code Results

| Variant | Correct | Accuracy | dim1 | dim2 | dim3 | Delta vs full QVF |
|---|---:|---:|---:|---:|---:|---:|
| `full_qvf_sidecar` | 1088/1200 | 90.67% | 380/400 (95.00%) | 338/400 (84.50%) | 370/400 (92.50%) | 0 (0.00 pp) |
| `annotation_only_qvf_sidecar` | 1054/1200 | 87.83% | 382/400 (95.50%) | 321/400 (80.25%) | 351/400 (87.75%) | -34 (-2.83 pp) |
| `no_stale_blocking_sidecar` | 1054/1200 | 87.83% | 375/400 (93.75%) | 312/400 (78.00%) | 367/400 (91.75%) | -34 (-2.83 pp) |

## Pairwise Against Full QVF

| Control | Full-QVF wins | Control wins | Net | Both correct | Both wrong |
|---|---:|---:|---:|---:|---:|
| `annotation_only_qvf_sidecar` | 83 | 49 | 34 | 1005 | 63 |
| `no_stale_blocking_sidecar` | 74 | 40 | 34 | 1014 | 72 |

## Interpretation

- Full QVF remains ahead of both fresh current-code controls by 34/1200 judged responses (+2.83 percentage points).
- annotation_only_qvf_sidecar and no_stale_blocking_sidecar tie overall at 1054/1200 but fail differently by dimension.
- Annotation-only preserves dim1 slightly better but loses more dim3/current-answer accuracy; no-stale-blocking loses most heavily on dim2 stale/current conflict handling.
- Saved direct/no-memory contamination controls remain labeled as saved replay controls, not fresh current-code API reruns.

## Saved Replay Controls

- `direct_unlabeled_memory`, `no_memory`, and `qvf_deidentified_sidecar` are retained as 2026-07-02 saved replay controls in this pack, not fresh current-code API reruns.
- The saved direct/no-memory controls show that raw stale/current mixtures and query-only answering do not solve STALE, but they should be labeled separately from the fresh current-code sidecar controls above.

## GO/NO-GO

- `GO_STALE400_CURRENTCODE_CONTROL_ABLATION_COMPLETE_FULL_QVF_BEST_FRESH_CONTROL`
- Rollback/quarantine: No rollback. No method/code/prompt/adapter change. Controls are report-only experiment evidence.
- Next recommendation: Use this control table to strengthen STALE contribution claims. Next experiment should be learned-router/no-API ablation or adapter-side LoCoMo coverage only if needed; no STALE method change is justified by these controls.
