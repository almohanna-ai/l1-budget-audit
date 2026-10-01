# Main campaign data dictionary

This dictionary describes `data/analysis-records.json`, the 32,000-row main
campaign projection. The separate two-model pilot projections under
`experiments/` retain their own fields and scoring policy; consult each
`source_manifest.json` and `protocol.json` plus `docs/format-pilots.md`.

`data/analysis-records.json` is a JSON array of 32,000 analysis records: 500
MATH-500 problems × four requested budgets × 16 samples. Each record has the
19 top-level fields below. Values were copied from the accepted scored export;
this projection does not contain question text, response text, original token
IDs, or reviewer identities.

| Field | Type | Meaning and values in this release |
| --- | --- | --- |
| `raw_record_id` | string | Unique opaque identifier for the original generation; retained for traceability and the identified-case sensitivity analysis. |
| `problem_id` | string | Dataset problem identifier, such as `test/algebra/1349.json`; a dataset reference, not a bundled file path. There are 500 unique problems. |
| `requested_budget` | integer | Requested reasoning budget: `512`, `1024`, `2048`, or `3600`. This is a prompt request, not the hard output cap. |
| `sample_index` | integer | Within-problem, within-budget repetition index, from `0` to `15`. Equal indices across budgets do not imply matched random seeds. |
| `difficulty` | string | Published MATH difficulty label, from `"1"` to `"5"`. |
| `subject` | string | Published subject: Algebra, Intermediate Algebra, Number Theory, Prealgebra, Precalculus, Geometry, or Counting & Probability. |
| `closed` | boolean | Whether the original-token boundary procedure identified a unique closing reasoning marker. |
| `boundary_status` | string | `resolved` for closed boundaries, otherwise `missing`. |
| `reasoning_tokens` | integer or null | Number of original generated token IDs before the closing marker; null when the boundary is unavailable. |
| `final_response_tokens` | integer or null | Number of original generated token IDs after the closing marker; null when the boundary is unavailable. |
| `total_output_tokens` | integer | Count of all original generated token IDs, including the closing marker and final-response portion when present. Available for every record. |
| `hit_cap` | boolean | Whether generation reached the configured hard cap of 6,000 output tokens. |
| `finish_reason` | string | Archived termination reason: `eos` or `length`. |
| `model_id` | string | `l3lab/L1-Qwen-1.5B-Exact`. |
| `model_revision` | string | Pinned model revision, `b1fa57f192f0b14bd033d0085faaa80cdc39694b`. |
| `boundary_policy_version` | string | `original-ids-unique-close-v1`, the archived original-token boundary convention. |
| `condition_id` | string | `l1-paper-math-curve-b16-v1`, the archived collection condition. |
| `collection_environment` | string | Recorded collection hardware: `Tesla T4`. Recomputing this release's analyses uses CPU. |
| `final_comparison` | object | Accepted grading result, containing only `status` and `origin`, described below. |

## Outcomes and grading origins

`final_comparison.status` is `correct` or `incorrect`. There are 24,757 accepted
correct and 7,243 incorrect records, with no unresolved decisions.

| `final_comparison.origin` | Records | Interpretation |
| --- | ---: | --- |
| `rule_based` | 31,567 | Deterministic comparison supplied the effective accepted decision. |
| `AI_adjudication` | 405 | An externally supplied AI judgment supplied the effective accepted decision. |
| `human_adjudication` | 28 | One human reviewer's judgment supplied the effective accepted decision. |

Origins describe the effective accepted labels, not independent assessments of
every answer. Only the 28 then-pending generations received the recorded human
review. This was not a two-reviewer consensus or a full human audit.

## Boundary and denominator conventions

For each closed record, `total_output_tokens = reasoning_tokens + 1 +
final_response_tokens`. The one closing-marker token is excluded from both
component counts. Any generated opening-marker IDs remain in the reasoning
prefix; no stripping was applied.

There are 31,961 closed and 39 unclosed records. All 39 unclosed records hit the
cap. There are 40 cap hits in total, because one capped output has a resolved
boundary. Reasoning and final-response length summaries exclude unavailable
boundaries; total-output summaries include all records. Null reasoning lengths
must not be replaced with zero or with the total-output count.

Accepted correctness uses the stored grade regardless of closure. The separate
strict completed-final diagnostic requires both accepted correctness and a
closed boundary. It excludes 27 accepted-correct unclosed outputs without
changing their stored grades. In this run, every accepted-correct closed output
also terminates at EOS without hitting the cap.

## Companion files

`data/analysis-summary.json` supplies per-budget counts, effective grading-origin
counts, and the scope of human review. `data/projection-manifest.json` records
the projection's fields and SHA-256 hashes, including hashes of the original
scored export and summary. Those original source files are not distributed here.
Their hashes establish provenance references; they do not provide access to the
omitted text or token IDs.
