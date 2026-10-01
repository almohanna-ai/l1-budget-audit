# Publication status and handoff

This is a locally prepared and tested release candidate, not evidence that
anything has been uploaded, assigned a DOI, or accepted by a repository.

## Before making the repository public

1. Supply the authors' preferred English names in order, affiliations, and an
   optional contact address/ORCID. Fill `release-metadata.json` and create a
   genuine `CITATION.cff` from those details.
2. Approve code and data licenses and the included third-party attribution.
   Add actual license texts; the current notice grants no license. Resolve the
   archived tokenizer-template terms before publishing that protocol file.
3. Review the README and the limited scope: this package reproduces the final
   main analysis and two completed two-model pilots conditional on stored labels,
   not generation or regrading. Original pilot code and authored prompt assets
   are preserved separately as historical source.
4. Rebuild the file manifest and checksums after any edits. Run file verification,
   unit tests, and numerical reproduction again if source/data have changed.

`python verify_release.py --publication-ready` intentionally returns a nonzero
status while names, licenses, or third-party review are incomplete. It is a
metadata check, not a guarantee of platform acceptance or scientific review.

## Intended release order

Publish the approved repository contents on GitHub and make a versioned release.
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
