# Reproducing the analysis

Run commands from the repository root. The recorded reference environment is
Python 3.11.4, NumPy 2.1.3, and Matplotlib 3.9.2. The analysis uses CPU and requires
neither a model download nor an inference framework.

```sh
python -m pip install -r requirements.txt
python verify_release.py
python reproduce.py --output outputs/run-001
```

The output directory must not already exist. Use a new name, such as
`outputs/run-002`, for another run. Input data and the supplied reference results
remain unchanged.

## Pipeline and outputs

The wrapper verifies the package manifest and runs four stages:

| Stage | Output directory | Result |
| --- | --- | --- |
| Main analysis | `outputs/run-001/main/analysis/` and `main/figures/` | JSON results, four CSV tables, paired bootstrap intervals, and three figures. |
| Length-overlap analysis | `outputs/run-001/length-overlap/` | JSON results, two CSV tables, and standalone overlap plots. |
| Publication-size overlap figures | `outputs/run-001/length-figures/` | Two overlap figures rendered from the same observations and audit, with a figure manifest. |
| Two-model exploratory pilots | `outputs/run-001/pilots/` | Recomputed condition summaries and per-problem lengths for the 520-output and 200-output pilots, checked against archived results. |

Each figure is exported as PDF and PNG. The three main figures cover accuracy
and length, adherence and boundary sensitivity, and difficulty-level accuracy.
The two overlap figures show length ranges and common-bin length distributions.
The standalone and publication-size overlap exports are alternate layouts of
the same two analyses, not additional experiments. Figure filenames retain
their analysis-stage numbering; they do not specify manuscript figure order.

The wrapper stores stage logs under `outputs/run-001/logs/` and writes the final
comparison to `outputs/run-001/reproduction-check.json`. It compares numerical
reference analyses and the exact bytes of all six CSV files. Only explicitly
selected mutable provenance fields are excluded from the JSON comparison;
scientific results remain part of the check.

## Running stages individually

These commands use separate new output directories and the bundled reference
analysis for the unchanged-length check:

```sh
python recompute_analysis.py --input data/analysis-records.json --summary data/analysis-summary.json --previous-analysis analysis/publication-analysis.json --output outputs/manual-main-001
python research_tools/length_overlap.py --input data/analysis-records.json --output outputs/manual-overlap-001
python research_tools/paper_length_figures.py --input data/analysis-records.json --audit outputs/manual-overlap-001/overlap-analysis.json --output outputs/manual-figures-001
```

The main script's `--previous-analysis` option checks length summaries against
the supplied reference; it is not by itself a complete comparison of every
result. Use the wrapper for the full reference comparison.

Run the package and overlap-semantics checks with:

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s research_tools -p test_length_overlap.py -v
```

`python verify_release.py` checks packaged file hashes. Its optional
`--publication-ready` mode also checks publication metadata and reports pending
author or license information. A metadata check is separate from numerical
reproduction.

The pilot stage can also run separately, using the standard library only:

```sh
python scripts/analyze_pilots.py --input-dir experiments --output outputs/pilots-001
```

It retains unresolved labels and checks the full model/problem/condition/sample
grid before aggregating. The original pilot source and demonstrations are in
`historical_code/`; those GPU/evaluation scripts are not executed by this wrapper.
Frozen hashes and main-only verification reports carried from v1 remain historical
evidence. The added v2 verification report covers the expanded wrapper and pilots.

## Numerical reproducibility and provenance

`analysis/` holds the supplied reference statistics and CSV tables. The data
projection preserves all 32,000 records and their accepted measurements and
grades. Reproduction recomputes these statistics; it does not infer or update
grades. The original token IDs are absent, so token accounting is checked for
internal consistency rather than remeasured from a token stream.

File hashes identify exact bytes. A new run may record different paths, builder
hashes, or runtime versions; rendered PDFs can also contain different metadata.
These differences must not be confused with numerical disagreement. The
reference comparisons and manifests serve different purposes: one checks the
scientific outputs, and the other checks file integrity. Historical provenance
references to unbundled source artifacts do not imply those artifacts can be
opened from this repository.

## Bootstrap interpretation

The main analysis uses 10,000 resamples with seed `20260927`. Each resample draws
500 problems with replacement, retaining all four budgets and all 16 recorded
generations within every selected problem-budget cell. The same selected
problems are used for paired budget contrasts. The draw stream uses Python
`random.Random`, `randrange(500)`, and sorted problem identifiers; the result
records a hash of the draw matrix. Percentile endpoints use linear
interpolation at 2.5% and 97.5%.

These pointwise, unadjusted intervals are a heuristic for a population of
similar problems when the benchmark problems are treated as exchangeable
clusters. The observed rates on the fixed benchmark are exact conditional
summaries. The intervals do not quantify grading error, do not independently
resample generations, and are not intervals based on 32,000 independent rows.

Overlap quantile ranges, such as the central 90% of observed lengths, are
descriptive ranges rather than confidence intervals. Difficulty and subject
summaries are exploratory, without subgroup confidence intervals or
multiple-comparison claims.
