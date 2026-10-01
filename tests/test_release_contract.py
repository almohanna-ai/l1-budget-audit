"""Test integrity, immutable output, and scientific comparison contracts on CPU."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reproduce import comparable_analysis, reserve_output
from verify_release import publication_issues, sha256, verify_files


class ReleaseContractTests(unittest.TestCase):
    """Prevent corrupt inputs, overwritten runs, and hidden scientific differences."""

    def make_fixture(self, root: Path) -> None:
        """Create a minimal tracked file and its fingerprint manifest."""
        (root / "data.json").write_text('{"value": 1}', encoding="utf-8")
        (root / "MANIFEST.json").write_text(json.dumps({
            "files": {"data.json": sha256(root / "data.json")},
        }), encoding="utf-8")

    def test_valid_manifest(self) -> None:
        """An unchanged input passes its manifest check."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            self.assertEqual(verify_files(root)["checked_files"], 1)

    def test_tampered_file_rejected(self) -> None:
        """A changed byte fails validation before analysis."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            (root / "data.json").write_text('{"value": 2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                verify_files(root)

    def test_missing_file_rejected(self) -> None:
        """A missing manifest member cannot be silently skipped."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "MANIFEST.json").write_text(json.dumps({"files": {"missing": "0" * 64}}))
            with self.assertRaisesRegex(ValueError, "Missing file"):
                verify_files(root)

    def test_manifest_traversal_rejected(self) -> None:
        """A manifest may reference only paths within its own release."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "MANIFEST.json").write_text(json.dumps({"files": {"../outside": "0" * 64}}))
            with self.assertRaisesRegex(ValueError, "Unsafe manifest path"):
                verify_files(root)

    def test_existing_output_preserved(self) -> None:
        """A rerun cannot replace files in a previous run directory."""
        with tempfile.TemporaryDirectory() as directory:
            output = reserve_output(Path(directory) / "run")
            sentinel = output / "sentinel.txt"
            sentinel.write_text("retain", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                reserve_output(output)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "retain")

    def test_frozen_input_directory_rejected(self) -> None:
        """Generated artifacts cannot be placed inside bundled source data."""
        with self.assertRaisesRegex(ValueError, "frozen inputs"):
            reserve_output(ROOT / "data" / "forbidden-output")

    def test_scientific_provenance_retained(self) -> None:
        """Path/runtime differences are ignored, but model changes remain visible."""
        original = {"correct": 4, "provenance": {"builder": "old", "model_revisions": ["a"]}}
        portable = {"correct": 4, "provenance": {"builder": "new", "model_revisions": ["a"]}}
        self.assertEqual(comparable_analysis(original), comparable_analysis(portable))
        portable["provenance"]["model_revisions"] = ["b"]
        self.assertNotEqual(comparable_analysis(original), comparable_analysis(portable))
        self.assertEqual(original["provenance"]["builder"], "old")

    def test_changed_accuracy_detected(self) -> None:
        """Changed outcomes must never be hidden by provenance filtering."""
        self.assertNotEqual(comparable_analysis({"correct": 4, "provenance": {}}),
                            comparable_analysis({"correct": 3, "provenance": {}}))

    def test_pending_publication_metadata_detected(self) -> None:
        """Incomplete authorship or rights is clearly distinguished from integrity."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release-metadata.json").write_text(json.dumps({"authors": []}))
            self.assertEqual(len(publication_issues(root)), 4)


if __name__ == "__main__":
    unittest.main()
