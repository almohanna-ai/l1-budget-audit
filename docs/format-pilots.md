# Exploratory format pilots on the 1.5B and 7B models

Both completed pilots are included in this expanded release, separately from
the 32,000-generation main campaign. The previous v1 GitHub candidate contained
only the main campaign; v2 corrects that omission for the two-model format work.

| Experiment | Problems | Conditions per model | Repetitions | Total outputs |
| --- | ---: | ---: | ---: | ---: |
| Comprehensive v3 | 5 | 5 budgets + 8 format conditions | 4 | 520 |
| Matched-format v4 | The same 5 | 5 formats, each with 8 demonstrations | 4 | 200 |

The pinned models are `l3lab/L1-Qwen-1.5B-Exact` at
`b1fa57f192f0b14bd033d0085faaa80cdc39694b` and `l3lab/L1-Qwen-7B-Exact` at
`faddca9f863ea15295cd6600d64593f26b8c5086`. The selected development problems are
reused across these experiments; 720 outputs do not represent 720 independent
problems or a held-out benchmark evaluation.

## Seven format families and eight conditions

The comprehensive pilot used seven named families. CoT was run in two example
settings, giving eight experimental format conditions:

| Family | Stored condition | Demonstrations |
| --- | --- | ---: |
| CoT | `cot-zero-shot` | 0 |
| CoT | `cot-8shot` | 8 |
| BeConcise | `be-concise-zero-shot` | 0 |
| OnlyNumbers | `only-numbers-zero-shot` | 0 |
| NoProperGrammar | `no-proper-grammar-zero-shot` | 0 |
| NoCoT | `no-cot-zero-shot` | 0 |
| CoD | `cod-style-8shot` | 8 |
| SoT | `sot-chunked-symbolism-8shot` | 8 |

Five separate budget arms requested 256, 512, 1,024, 2,048, and 3,600 tokens.
This was **13 separate conditions**, not a budget-by-format factorial design.
For the 7B model alone there are 160 format outputs and 100 budget outputs.
The smaller model contributes the same counts. The demonstrations are not
matched across all eight format conditions, so results cannot isolate style
from example effects across the whole table.

The follow-up v4 used five conditions: CoT, concise, CoD, SoT, and symbolic.
All used eight authored examples with matched questions, mathematical content,
order, and final answers. Both pilots retain the original 6,000-token output
cap, temperature 0.6, top-p 0.95, and four samples per problem/condition.

## Results and their limits

See [the full format comparison tables](format-results.md) for reasoning-token
means and accuracy/bounds for every format condition in both models.

| Pilot | Model | Correct | Incorrect | Unresolved |
| --- | --- | ---: | ---: | ---: |
| Comprehensive v3 | 1.5B | 241 | 17 | 2 |
| Comprehensive v3 | 7B | 259 | 0 | 1 |
| Matched-format v4 | 1.5B | 94 | 4 | 2 |
| Matched-format v4 | 7B | 100 | 0 | 0 |

These are completeness checks across different conditions, not a pooled
scientific comparison. Use per-condition tables for interpretation. Scores come
from the archived conservative literal grader; the five unresolved pilot
answers stay in the denominator and are not adjudicated by this release.
Their lower/upper accuracy bounds are not confidence intervals.

For example, v3 mean reasoning length on the 7B model is 722.5 tokens for
eight-shot CoT and 401.45 for eight-shot CoD. In v4 these means are 647.1 and
438.9. The corresponding v4 conditions each have 20/20 accepted-correct outputs.
These small development samples cannot establish a general accuracy advantage
or rank methods. Numeric style proxies, when retained, do not establish prompt
compliance; no completed independent human compliance audit is present.

## Included evidence and reproduction

`experiments/` holds per-generation projections, protocols, frozen aggregate
tables, and source manifests for both completed runs. `historical_code/` holds
the exact original Python files and full authored demonstration assets. Raw
model responses, original token-ID arrays, and benchmark questions/references
are retained in the project's private source archives, not this public candidate.

```sh
python scripts/analyze_pilots.py --input-dir experiments --output outputs/pilots-001
```

This CPU-only command recomputes condition-level results and per-problem length
means and checks them against the archived combined reports. It does not rerun
models, infer new labels, or audit the wording of model outputs. The main
`reproduce.py` wrapper also executes this stage and includes its verdict in the
combined verification report.

The earlier 7B compliance smoke run collected only 140 of 160 planned outputs
and had no final report. It is an incomplete, superseded run and is not added to
these completed totals. Other earlier diagnostics and the 30-problem pilot
remain documented in the private project archive; this addition specifically
releases the completed two-model calibrations discussed in the manuscript.
