"""Guard against wrong automatic resolutions in the limited pilot grader."""
import unittest
from grading import grade
from probe import load_spec, prompt


class GradingTests(unittest.TestCase):
    """Check caps, conflicting answers, symbolic uncertainty and interval endpoints."""

    def test_numeric(self) -> None:
        """Resolve exact rational literals but never evaluate arbitrary expressions."""
        self.assertEqual(grade("", "Answer: 240", ["240"], False)["status"], "correct")
        self.assertEqual(grade("", r"\boxed{241}", ["240"], False)["status"], "incorrect")
        self.assertEqual(grade("", "Answer: 2+1", ["3"], False)["status"], "unresolved")
        self.assertEqual(grade("", "Answer: 3\nAnswer: 4", ["3"], False)["status"], "unresolved")
        self.assertEqual(grade("", "Answer: 3", ["3"], True)["status"], "unresolved")

    def test_intervals(self) -> None:
        """Preserve open versus closed endpoints in the domain question."""
        reference = [r"(-\infty, 2) \cup (3, \infty)"]
        self.assertEqual(grade("", r"Answer: (3,\infty)\cup(-\infty,2)", reference, False)["status"], "correct")
        self.assertEqual(grade("", r"Answer: (-\infty,2]\cup(3,\infty)", reference, False)["status"], "incorrect")

    def test_direct_answer(self) -> None:
        """NoCoT direct answers may be graded without inventing thinking boundaries."""
        self.assertEqual(grade("Answer: 3", None, ["3"], False)["status"], "correct")
        self.assertEqual(grade("<think>Answer: 3", None, ["3"], False)["status"], "unresolved")

    def test_matched_format_arms(self) -> None:
        """Every calibration arm is an eight-shot format with no length budget."""
        spec = load_spec()
        self.assertEqual({c["demo_style"] for c in spec["conditions"]},
                         {"cot", "concise", "cod", "sot", "symbolic"})
        for condition in spec["conditions"]:
            self.assertEqual(condition["group"], "format")
            self.assertIsNone(condition["budget"])
            rendered = prompt(spec, spec["problems"][0], condition)
            self.assertEqual(rendered.count("Example "), 8)


if __name__ == "__main__":
    unittest.main()
