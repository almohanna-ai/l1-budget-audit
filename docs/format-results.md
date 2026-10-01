# Archived format results by model

All means below count the stored reasoning block. Each cell contains 20 outputs from five fixed development problems with four repetitions. Accuracy ranges cover unresolved grades, not confidence intervals. These are exploratory calibration results, not a compliance judgment or a model ranking.

## Comprehensive v3: seven families, eight conditions

| Condition | Mean reasoning tokens: 1.5B | Mean reasoning tokens: 7B | Accuracy: 1.5B | Accuracy: 7B |
| --- | ---: | ---: | ---: | ---: |
| cot-zero-shot | 2944.15 | 764.90 | 95% | 100% |
| cot-8shot | 3071.55 | 722.50 | 90% | 100% |
| be-concise-zero-shot | 977.45 | 457.35 | 100% | 100% |
| only-numbers-zero-shot | 2413.00 | 741.35 | 95% | 100% |
| no-proper-grammar-zero-shot | 1210.30 | 566.95 | 95–100% | 95–100% |
| no-cot-zero-shot | 2753.25 | 623.60 | 100% | 100% |
| cod-style-8shot | 1003.35 | 401.45 | 95% | 100% |
| sot-chunked-symbolism-8shot | 1706.55 | 507.60 | 85–90% | 100% |

The complete JSON/CSV tables also retain medians, P10/P90, total output lengths, cap counts, boundary coverage, and per-problem means.

## Matched-format v4: five eight-shot conditions

| Condition | Mean reasoning tokens: 1.5B | Mean reasoning tokens: 7B | Accuracy: 1.5B | Accuracy: 7B |
| --- | ---: | ---: | ---: | ---: |
| cot-8shot-v2 | 2304.00 | 647.10 | 95% | 100% |
| concise-8shot-v2 | 2463.20 | 461.85 | 85–90% | 100% |
| cod-8shot-v2 | 1175.25 | 438.90 | 95–100% | 100% |
| sot-8shot-v2 | 1949.45 | 544.35 | 100% | 100% |
| symbolic-8shot-v2 | 2388.10 | 548.55 | 95% | 100% |

The complete JSON/CSV tables also retain medians, P10/P90, total output lengths, cap counts, boundary coverage, and per-problem means.

