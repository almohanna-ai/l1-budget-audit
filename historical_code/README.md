# Original pilot source and prompt assets

These two directories preserve the Python files found in the original completed
pilot archives without modification. Their archive/member hashes are in
`source-manifest.json`. This is historical source evidence; the CPU reproduction
entry point for this release is `scripts/analyze_pilots.py`.

- `comprehensive-v3/`: 5 requested-budget arms and 8 format conditions on 2 models.
- `matched-formats-v4/`: 5 format conditions, all with 8 demonstrations, on 2 models.

Each `prompt-assets.json` retains the exact condition instructions and the eight
authored demonstrations from that run. The `prompt()` function in its `probe.py`
shows how the system constructs the complete user message, including the answer
format and demonstration placement. The two pilots used controlled adaptations
of CoD/SoT, not verbatim reproductions of external papers. Authored demonstrations
are distinct from the five evaluation problems.

Benchmark question text and target reference answers in the original
`experiment.json` are omitted from this release. Their problem identifiers and
dataset revision are preserved in the corresponding `experiments/` protocol.
The original scripts expect the full original configuration and a matching
inference environment. They are not invoked by the CPU wrapper and are not
advertised as ready to start a new GPU campaign from this ZIP alone. Their tests
are also archived source; current release tests live in the root `tests/` folder.

Prompt assets and code are released under the licenses described in
`LICENSE-NOTICE.md`. This archive does not grant rights to third-party materials.
