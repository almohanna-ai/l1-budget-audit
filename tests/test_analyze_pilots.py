"""CPU-only checks of the supplemental pilot reproduction contract."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("analyze_pilots", ROOT / "scripts" / "analyze_pilots.py")
assert SPEC is not None and SPEC.loader is not None
PILOTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PILOTS)


class PilotTests(unittest.TestCase):
    """Exercise genuine grid, grade-denominator, and immutability risks."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.input_dir = ROOT / "experiments"
        cls.records, cls.protocol = PILOTS.load_experiment(
            cls.input_dir / "comprehensive_v3_two_models", PILOTS.EXPERIMENTS["comprehensive_v3_two_models"])

    def test_duplicate_grid_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate grid"):
            PILOTS.analyze_records(self.records + [copy.deepcopy(self.records[0])], self.protocol)

    def test_incomplete_grid_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Incomplete grid"):
            PILOTS.analyze_records(self.records[:-1], self.protocol)

    def test_unresolved_kept_in_denominator(self) -> None:
        records = copy.deepcopy(self.records)
        selected = [row for row in records if row["model"] == "small" and row["condition_id"] == "l1-budget-256"]
        for row in selected:
            row["grading_status"] = "incorrect"
        selected[0]["grading_status"] = "correct"
        selected[1]["grading_status"] = "unresolved"
        summary = PILOTS.analyze_records(records, self.protocol)["rows"][0]
        self.assertEqual(summary["collected"], 20)
        self.assertEqual(summary["lower_bound_pct"], 5.0)
        self.assertEqual(summary["upper_bound_pct"], 10.0)
        self.assertIsNone(summary["accuracy_pct"])

    def test_both_frozen_summaries_reproduced_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "new-results"
            validation = PILOTS.reproduce(self.input_dir, output)
            self.assertEqual(validation["status"], "passed")
            self.assertEqual(validation["record_count"], 720)
            for folder in PILOTS.EXPERIMENTS:
                self.assertEqual((output / folder / "summary.json").read_bytes(),
                                 (self.input_dir / folder / "frozen_summary.json").read_bytes())
                self.assertEqual((output / folder / "summary.csv").read_bytes(),
                                 (self.input_dir / folder / "frozen_summary.csv").read_bytes())

    def test_no_overwrite_even_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileExistsError):
                PILOTS.reproduce(self.input_dir, Path(temp))
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_no_overwrite_published_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "new-results"
            PILOTS.reproduce(self.input_dir, output)
            before = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
            with self.assertRaises(FileExistsError):
                PILOTS.reproduce(self.input_dir, output)
            after = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
