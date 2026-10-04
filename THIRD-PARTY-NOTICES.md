# Upstream references and third-party material

These links identify experiment inputs; they do not imply endorsement or
transfer licensing rights. The archived 1.5B tokenizer template is attributed
to its upstream repository, whose pinned release declares MIT. The 7B model
repository declares Apache-2.0; no 7B weights or templates are distributed.
The pinned MATH-500 card does not state a license. This release excludes the
benchmark's question text and reference answers.

| Source | Pinned revision | Material in this package |
| --- | --- | --- |
| [L1-Qwen-1.5B-Exact](https://huggingface.co/l3lab/L1-Qwen-1.5B-Exact) (MIT declared) | `b1fa57f192f0b14bd033d0085faaa80cdc39694b` | Model/tokenizer identifiers and archived prompt/chat-template configuration; no weights. |
| [L1-Qwen-7B-Exact](https://huggingface.co/l3lab/L1-Qwen-7B-Exact) (Apache-2.0 declared) | `faddca9f863ea15295cd6600d64593f26b8c5086` | Two exploratory pilots' model identifiers and measurements; no weights. |
| [MATH-500](https://huggingface.co/datasets/HuggingFaceH4/MATH-500) | `6e4ed1a2a79af7d8630a6b768ec859cb5af4d3be` | Problem identifiers, subject/difficulty metadata, and experiment measurements; no problem statements or reference answers. |

The frozen `protocol/collect-config.json` includes a tokenizer chat template
derived from the experiment's pinned tokenizer. It is preserved as historical
protocol evidence, not claimed as original work. It must retain applicable
upstream rights and attribution. The project's MIT license is not a claim of
authorship or a relicense of that upstream template.

NumPy and Matplotlib are installed separately through `requirements.txt`; their
source or distributions are not vendored in this ZIP. Their licenses continue
to apply to their own software. Model-generated text is not included in the
analysis projection. Accepted label provenance is documented separately in
`docs/data-dictionary.md` and `docs/experiment-scope.md`.
