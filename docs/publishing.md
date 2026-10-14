# Publication status and handoff

Version 1.0.0 (14 October 2026) is the public release. Repository: https://github.com/almohanna-ai/l1-budget-audit.
Paper: https://doi.org/10.5281/zenodo.23355265. The checklist below documents how the release was prepared.

## Before making the repository public

1. Confirm the author name and contact address in `release-metadata.json` and
   `CITATION.cff`; add the affiliation/ORCID if desired.
2. The author has approved broad reuse of original software under MIT and
   original data, figures, and documentation under CC BY 4.0. The paper
   citation is requested for scholarly use but is not an extra MIT condition.
   Third-party material keeps its upstream terms. The 1.5B pinned model declares
   MIT, the 7B model declares Apache-2.0, and no MATH-500 question/answer text
   is redistributed. See `THIRD-PARTY-NOTICES.md`.
3. Review the README and the limited scope: this package reproduces the final
   main analysis and two completed two-model pilots conditional on stored labels,
   not generation or regrading. Original pilot code and authored prompt assets
   are preserved separately as historical source.
4. Rebuild the file manifest and checksums after any edits. Run file verification,
   unit tests, and numerical reproduction again if source/data have changed.

`python verify_release.py --publication-ready` checks declared author and rights
metadata. A passing status is not a legal opinion, proof of public upload, or
scientific review.

## Intended release order

Upload this successor to the existing GitHub repository and make a versioned release.
Optionally archive that exact code/data release on Zenodo as a software/data
artifact and record the resulting real DOI. Add the live repository link and
artifact DOI, if assigned, to the separately maintained manuscript. Submit the
manuscript through the chosen preprint route, then cross-link its identifier
from this repository. ResearchGate, Hugging Face, and social posts can point to
these canonical records later; no duplicate paper DOI is needed just to create
a code archive.

The candidate omits the manuscript PDF and LaTeX source intentionally. The code
archive and manuscript are different scholarly objects and should be described
as such when connecting their identifiers. Do not invent a URL while waiting
for the actual repository or archive to exist.

## Updating candidate fingerprints

`MANIFEST.json` maps every distributed file except itself and `SHA256SUMS.txt`
to its SHA256. `SHA256SUMS.txt` covers the same files plus `MANIFEST.json`.
Files are stored with preserved line endings (`.gitattributes`) so a normal Git
checkout does not invalidate the original JSON/CSV fingerprints. Generated runs,
caches, virtual environments, and raw/private material are excluded from Git.

Change the version/date/status when preparing a subsequent release. Rebuild a
new candidate from an explicit file inventory; do not silently alter a published
version or replace archived research outputs. A changed provenance hash is
expected after a portability or documentation change, but scientific equality
must be checked separately.
