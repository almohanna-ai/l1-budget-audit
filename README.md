# L1 Budget Audit: Analysis Artifacts

CPU reproduction package for an **empirical audit of generation budgets and accuracy**:
32,000 generations from `l3lab/L1-Qwen-1.5B-Exact`, covering all 500 MATH-500
problems, four requested budgets, and 16 samples per problem and budget.
This expanded candidate also includes the two completed exploratory format
calibrations on **both L1-Qwen-1.5B-Exact and L1-Qwen-7B-Exact** (520 and 200
outputs), their analysis projections, frozen results, prompts, and original code.

**Release candidate:** scientific results are frozen; author names and reuse
licenses are awaiting owner confirmation. No public repository URL or DOI has
been assigned. See [publication status](docs/publishing.md) and
[rights notice](LICENSE-NOTICE.md) before publishing this candidate.

[التعليمات بالعربية](README_AR.md)

## Results included

| Requested budget | Generations | Accepted correct | Accepted accuracy |
| ---: | ---: | ---: | ---: |
| 512 | 8,000 | 5,533 | 69.1625% |
| 1,024 | 8,000 | 6,163 | 77.0375% |
| 2,048 | 8,000 | 6,419 | 80.2375% |
| 3,600 | 8,000 | 6,642 | 83.0250% |

"Accepted" refers to the stored final scoring policy: 31,567 rule-based
decisions, 405 AI-adjudicated decisions, and 28 human-adjudicated decisions.
There are no unresolved labels in the main campaign. One human reviewer handled only the 28 pending
cases; the complete dataset was **not independently human-verified**. These
rates are generation-level accuracy, not majority-vote accuracy or pass@16.

Requested budget is a prompt instruction, not an enforced reasoning-token
cap. The total generated output cap was 6,000 tokens. Reasoning length and
total output length are measured separately. There are 39 missing closing
boundaries and 40 cap stops; missing reasoning lengths remain null. The
length-overlap analysis distinguishes observed ranges, exact integer-length
overlap, and histogram overlap, including sensitivity to bin width.

## Reproduce on CPU

Reference environment: Python 3.11.4, NumPy 2.1.3, Matplotlib 3.9.2.
From this folder, in a Python environment:

```sh
python -m pip install -r requirements.txt
python verify_release.py
python reproduce.py --output outputs/run-001
```

No GPU, model download, API key, PyTorch, Transformers, or vLLM is required.
The dependency installation needs internet access; the reproduction itself
runs offline after installation. Output folders must be new. Another run can
use `outputs/run-002`; existing results are never overwritten.

A successful run writes `outputs/run-001/reproduction-check.json` with
`"status": "passed"`. It compares all scientific JSON fields and six CSV tables
against the frozen main results, and regenerates five figures in PNG and PDF.
It also recomputes both pilot summaries and per-problem length tables from
720 projected records, comparing them with the original archived pilot results.
Only enumerated path/runtime provenance fields are excluded from the numerical
comparison. Rendering bytes are not promised identical across platforms.

Recorded expanded-release checks are in
[the v2 reproduction report](verification/reproduction-check-v2.json) and
[the v2 verification record](verification/release-check-v2.json).

Tests:

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s research_tools -p test_length_overlap.py -v
```

For Google Colab, select a **CPU runtime**, upload and extract the ZIP, change
the working directory to the extracted `l1-budget-audit` folder, then run the
three reproduction commands with a leading `!`. Colab's Python/runtime versions
may differ from the reference; the comparison report will expose numerical
disagreement instead of silently accepting it.

## Contents

| Path | Purpose |
| --- | --- |
| `data/` | Final 32,000-row analysis projection, summary, and source hashes. |
| `analysis/` | Frozen JSON/CSV reference results and overlap audit. |
| `figures/` | Five publication-size figures in PDF/PNG, with captions/manifests. |
| `protocol/collect-config.json` | Historical model, dataset, prompt, sampling, and collection configuration. |
| `experiments/` | Two-model pilot records, protocols, frozen summaries, and archive provenance. |
| `historical_code/` | Exact original pilot Python scripts and authored prompt demonstrations. |
| `scripts/analyze_pilots.py` | CPU-only recomputation of the two exploratory pilot summaries. |
| `recompute_analysis.py` | Main descriptive analysis and paired problem bootstrap. |
| `research_tools/` | Overlap analysis, figure rendering, and semantic tests. |
| `reproduce.py` | Four-stage CPU workflow and numerical comparison. |
| `verify_release.py` | Standard-library file-integrity checker. |
| `verification/` | Recorded local release validation. |
| `docs/` | Data dictionary, scope, reproducibility, and publication status. |

Read [data contracts](docs/data-dictionary.md), [scope and limitations](docs/experiment-scope.md),
and [reproduction details](docs/reproducibility.md). The seven format families,
eight conditions, and larger-model results are described in [format pilots](docs/format-pilots.md).

## What this release can reproduce

It recomputes the main campaign's accuracy, bootstrap intervals, subgroup
summaries, length/adherence summaries, boundary sensitivity, and length overlap
from the accepted measurements and labels. It separately recomputes the two-model
format pilots; their unresolved answers remain unresolved. The main campaign's
later adjudication is not applied to the pilot records. The bundle omits model
weights, raw responses, benchmark question/answer text, and original token-ID
arrays. The original pilot inference/evaluation code is preserved as historical
source; its original execution environments and full benchmark configuration are
not supplied as a turnkey inference release.
Consequently, it cannot independently regrade responses, retokenize them, or
recreate the original model generations. The collection configuration records
the historical protocol; it is not an executable collection stage in this repo.

Bootstrap intervals are conditional on the stored generations and labels.
They do not cover judge error. This single-model descriptive audit establishes
neither a causal effect of observed length nor a universal length-accuracy law.
Some frozen manifests retain historical relative provenance labels for sources
not bundled here; those are not runtime dependencies.

## Citation and reuse

Use [release metadata](release-metadata.json) to track the current candidate.
A final `CITATION.cff`, author-approved licenses, and live repository/archive
links must be added before public release. The candidate deliberately provides
no fabricated author names, open-source license, or DOI. Upstream references
and third-party material are listed in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

The manuscript is maintained separately and is not included in this code/data
package. After the public links exist, add them to the manuscript's availability
statement and cross-link the manuscript from this README.
