"""Verify bundled file hashes using only the Python standard library.

Hashes detect accidental changes; they do not authenticate authorship. The optional
publication check also requires the author-approved names and license choices.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    """Hash one file without loading its entire contents into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_files(root: Path) -> dict[str, Any]:
    """Check every manifest entry, rejecting missing, changed, or unsafe paths."""
    root = root.resolve()
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("MANIFEST.json must contain a nonempty files mapping")
    failures: list[str] = []
    for name, expected in sorted(files.items()):
        relative = PurePosixPath(name)
        if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                or ":" in name or not relative.parts):
            failures.append(f"Unsafe manifest path: {name}")
            continue
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            failures.append(f"Manifest path escapes release: {name}")
        elif not path.is_file():
            failures.append(f"Missing file: {name}")
        elif sha256(path) != expected:
            failures.append(f"SHA256 mismatch: {name}")
    if failures:
        raise ValueError("Release integrity check failed:\n" + "\n".join(failures))
    return {"status": "passed", "checked_files": len(files)}


def publication_issues(root: Path) -> list[str]:
    """Return explicitly unresolved author and rights metadata, without guessing."""
    metadata = json.loads((root / "release-metadata.json").read_text(encoding="utf-8"))
    issues: list[str] = []
    authors = metadata.get("authors")
    if not isinstance(authors, list) or not authors or any(
        not isinstance(author, dict) or not str(author.get("name", "")).strip()
        for author in authors
    ):
        issues.append("Author-approved author names have not been supplied")
    for field in ("code_license", "data_license"):
        if not metadata.get(field):
            issues.append(f"Author-approved {field} has not been selected")
    if metadata.get("third_party_rights_reviewed") is not True:
        issues.append("Third-party attribution and redistribution review is pending")
    return issues


def main() -> int:
    """Print integrity status and optionally fail on incomplete publication metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-ready", action="store_true",
                        help="Also check whether author and rights metadata are complete")
    args = parser.parse_args()
    try:
        report = verify_files(ROOT)
        if args.publication_ready:
            issues = publication_issues(ROOT)
            report["publication_issues"] = issues
            if issues:
                report["status"] = "metadata_pending"
                print(json.dumps(report, indent=2))
                return 2
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
