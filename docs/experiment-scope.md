# Experiment and release scope

This release supports CPU recomputation of the main campaign's descriptive
statistics, paired problem-cluster intervals, length-overlap analysis, and five
scientific figures. The main campaign contains all 500 MATH-500 problems, four
requested budgets (512, 1024, 2048, and 3600), and 16 generations per
problem-budget cell: 32,000 generations in total.

The accepted per-budget correct counts are 5,533, 6,163, 6,419, and 6,642 out of
8,000, respectively. The corresponding accuracies are 69.1625%, 77.0375%,
80.2375%, and 83.0250%. These are conditional summaries of the accepted labels.

## Recorded collection protocol

`protocol/collect-config.json` preserves the archived model, tokenizer, dataset
revisions, prompt configuration, sampler settings, and fingerprints. The model
is `l3lab/L1-Qwen-1.5B-Exact`. The prompt's budget instruction is
`Think for {budget} tokens.`; the requested budget is distinct from the hard cap
of 6,000 new output tokens. The archived sampler uses temperature 0.6 and top-p
0.95, with 16 samples per problem and budget.

The configuration is a record of the original main run. This repository does not
contain that campaign's inference pipeline, model weights, full execution
environment, or the private collection archive. The pilot inference scripts are
separately preserved under `historical_code/`. Installing the analysis
dependencies does not recreate that collection environment.

## What the release can reproduce

- Budget-level accuracy, token-length summaries, adherence, cap and boundary
  counts, and descriptive difficulty and subject summaries.
- Paired problem-cluster bootstrap intervals for accepted correctness and the
  strict completed-final diagnostic.
- A targeted sensitivity calculation for 14 previously identified
  rubric-sensitive records. Their identifiers are preserved; their answers and
  the review evidence needed to reassess the judgments are not included.
- Observed length ranges, quantiles, exact-integer and common-bin overlap, and
  comparisons within the same problem across budgets.
- Three main-analysis figures and two length-overlap figures, in PDF and PNG.

The expanded release also supports CPU recomputation of two completed pilot
experiments on both the 1.5B and 7B checkpoints: 520 outputs from the 13-condition
calibration and 200 outputs from the five-format matched-example calibration.
See `format-pilots.md` for exact conditions and caveats. These are separate
development data, not additional independent benchmark replications. The
30-problem pilot, early diagnostics, incomplete runs, and hidden-state probes
remain outside this release's numerical reproduction scope. No manuscript or
manuscript source is included.

## Grading and interpretation limits

For the main campaign, the accepted labels combine 31,567 deterministic comparisons, 405 externally
supplied AI judgments, and 28 judgments from one human reviewer. No labels remain
unresolved. This does not make the labels error-free or establish independent
human verification of the whole benchmark. The intervals condition on these
labels and do not estimate grading error.

The analysis data omit benchmark question text, response text, original generated token
IDs, and review explanations. A reader can recompute statistics from the stored
measurements and decisions, but cannot independently regrade answers,
re-tokenize responses, verify the recorded boundaries from the original token
stream, or rerun inference using this bundle alone.

The study describes four requested-budget conditions for one pinned model and
sampler. It does not establish a causal effect of observed reasoning length, a
general law relating length and accuracy, or a result applying to other models.
The overlap analysis is post hoc and descriptive: finite observed ranges are
not population support, and histogram overlap depends on bin width. An absence
of observed overlap does not guarantee separation for missing boundaries or
future generations.
