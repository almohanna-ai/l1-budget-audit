"""Check two-model report consolidation without inference or external packages."""
from pathlib import Path
import tempfile
import unittest
from combine import combine
from probe import encode, load_spec, publish, read, sha


class CombineTests(unittest.TestCase):
    """Verify the joint table and reject mismatched experiment protocols."""

    def test_two_models(self) -> None:
        """Publish all 10 summary rows and 50 per-question/condition rows."""
        spec = load_spec()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for model in ("small", "large"):
                plan = {"protocol_sha256": sha(encode(spec)), "spec": spec,
                        "model_id": model, "model_revision": "a"*40}
                records = [{"problem_id": p["problem_id"], "condition_id": c["id"],
                            "think_tokens": 10, "total_tokens": 15}
                           for p in spec["problems"] for c in spec["conditions"] for _ in range(4)]
                report = {"complete": True, "records": records,
                          "summary": [{"condition": c["id"], "collected": 20} for c in spec["conditions"]]}
                publish(root / ("run-"+model) / "plan.json", plan)
                publish(root / ("run-"+model) / "reports/report-001.json", report)
            result = read(combine(root))
            self.assertEqual(len(result["rows"]), 10)
            self.assertEqual(len(result["per_problem"]), 50)
            self.assertEqual(sum(r["collected"] for r in result["rows"]), 200)
            path = root / "run-large/plan.json"
            plan["protocol_sha256"] = "different"
            path.write_bytes(encode(plan))
            with self.assertRaises(ValueError):
                combine(root)


if __name__ == "__main__":
    unittest.main()
