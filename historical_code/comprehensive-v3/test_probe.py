"""Offline regression checks; no model downloads or GPU initialization."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zipfile

import probe


class ProbeTests(unittest.TestCase):
    """Exercise lineage, token boundaries, immutable writes, and reports."""

    def test_protocol(self) -> None:
        """The protocol contains 260 unique requests and no target-answer injection."""
        spec = probe.load_spec()
        seeds = set()
        for problem in spec["problems"]:
            for condition in spec["conditions"]:
                altered = {**problem, "reference_answers": ["DO_NOT_LEAK"]}
                self.assertNotIn("DO_NOT_LEAK", probe.prompt(spec, altered, condition))
                for sample in range(4):
                    seeds.add(probe.seed_for(problem["problem_id"], condition["id"], sample))
        self.assertEqual(len(seeds), 260)

    def test_matched_examples(self) -> None:
        """Few-shot treatments use the same eight questions and final answers."""
        spec = probe.load_spec()
        for condition in spec["conditions"]:
            rendered = probe.prompt(spec, spec["problems"][0], condition)
            if condition["demo_style"] is None:
                self.assertNotIn("Worked examples:", rendered)
            else:
                self.assertEqual(rendered.count("Example "), 8)
                positions = [rendered.index(d["question"]) for d in spec["demonstrations"]]
                self.assertEqual(positions, sorted(positions))
                for demo in spec["demonstrations"]:
                    self.assertIn("Answer: " + demo["answer"], rendered)
        for demo in spec["demonstrations"]:
            self.assertTrue(all(len(line.split()) <= 5 for line in demo["reasoning"]["cod"].splitlines()))

    def test_regions(self) -> None:
        """Preserve implicit opens, multi-token boundaries, and missing-close uncertainty."""
        plan = {"think_open_ids": [90, 91], "think_close_ids": [98, 99]}
        row = {"output_token_ids": [90, 91, 1, 2, 98, 99, 3],
               "full_output": "<think>x y</think>Answer: 3"}
        self.assertEqual(probe.regions(row, plan)["think_tokens"], 2)
        row["output_token_ids"] = [1, 2, 98, 99, 3]
        row["full_output"] = "x y</think>Answer: 3"
        self.assertEqual(probe.regions(row, plan)["think_tokens"], 2)
        row["output_token_ids"] = [1, 2, 3]
        self.assertIsNone(probe.regions(row, plan)["think_tokens"])

    def test_no_vacuous_compliance(self) -> None:
        """No thinking text cannot become perfect compliance by an empty denominator."""
        self.assertIsNone(probe.style_proxies("")["short_line_fraction"])
        self.assertIsNone(probe.style_proxies(None)["short_line_fraction"])
        self.assertEqual(probe.style_proxies("x = 2\nthere are too many words in this line")["short_line_fraction"], .5)

    def test_immutable_publication(self) -> None:
        """Matching writes are idempotent and changed writes cannot overwrite."""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.json"
            probe.publish(path, {"a": 1})
            probe.publish(path, {"a": 1})
            with self.assertRaises(ValueError):
                probe.publish(path, {"a": 2})
            self.assertEqual(probe.read(path), {"a": 1})

    def test_checkpoint_report_backup(self) -> None:
        """A partial batch survives analysis/backup and corrupted resumes fail closed."""
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"
            spec = probe.load_spec()
            jobs = [{"record_id": str(i), "condition_id": spec["conditions"][0]["id"],
                     "problem_id": spec["problems"][0]["problem_id"], "sample_index": i} for i in range(4)]
            plan = {"jobs": jobs, "spec": spec, "think_open_ids": [90], "think_close_ids": [99]}
            probe.publish(run / "plan.json", plan)
            rows = [{**j, "output_token_ids": [1, 99, 3], "total_tokens": 3,
                     "full_output": "x</think><script>alert(1)</script>", "hit_cap": False} for j in jobs]
            payload = {"plan_sha256": probe.sha(probe.encode(plan)), "records": rows}
            batch = run / "raw" / "batch-000.json"
            probe.publish(batch, {"sha256": probe.sha(probe.encode(payload)), "payload": payload})
            self.assertEqual(len(probe.validate_batches(run, plan)), 4)
            report = probe.analyze(run)
            self.assertFalse(probe.read(report)["complete"])
            self.assertNotIn("<script>", report.with_suffix(".html").read_text())
            self.assertIn("&lt;script&gt;", report.with_suffix(".html").read_text())
            archive = probe.backup(run, Path(temp) / "backups")
            with zipfile.ZipFile(archive) as bundle:
                self.assertIsNone(bundle.testzip())
            receipt = probe.read(archive.with_suffix(".ready.json"))
            self.assertEqual(receipt["sha256"], probe.sha(archive.read_bytes()))
            restored = Path(temp) / "fresh" / "run"
            probe.restore(restored, Path(temp) / "backups")
            self.assertEqual(len(probe.validate_batches(restored, plan)), 4)
            changed = copy.deepcopy(plan)
            changed["jobs"][0]["sample_index"] = 9
            with self.assertRaises(ValueError):
                probe.validate_batches(run, changed)
            envelope = probe.read(batch)
            envelope["payload"]["records"][0]["total_tokens"] = 777
            batch.write_text(json.dumps(envelope))
            with self.assertRaises(ValueError):
                probe.validate_batches(run, plan)

    def test_collect_resume_160_requests(self) -> None:
        """Simulate an interrupted GPU backend; resume without repeating committed requests."""
        spec = probe.load_spec()
        jobs = []
        for problem in spec["problems"]:
            for condition in spec["conditions"]:
                for sample in range(4):
                    jobs.append({"record_id": f"{len(jobs):03d}",
                                 "condition_id": condition["id"], "problem_id": problem["problem_id"],
                                 "requested_budget": condition["budget"],
                                 "sample_index": sample, "generation_seed": len(jobs) + 10,
                                 "prompt_token_ids": [1, len(jobs) + 100]})
        plan = {"jobs": jobs, "spec": spec, "model_id": "fake/model", "model_revision": "a" * 40,
                "think_open_ids": [90], "think_close_ids": [99],
                "code_sha256": probe.sha(Path(probe.__file__).read_bytes())}
        generated = []
        state = {"calls": 0, "engines": 0}

        class FakeLLM:
            """Deterministic stand-in for an interrupted inference engine."""

            def __init__(self, **kwargs) -> None:
                state["engines"] += 1

            def generate(self, prompts, sampling_params, use_tqdm):
                """Fail once after one committed batch, then finish normally."""
                state["calls"] += 1
                if state["calls"] == 2:
                    raise RuntimeError("simulated interruption")
                generated.extend(p.seed for p in sampling_params)
                completion = SimpleNamespace(token_ids=[5, 99, 8], text="x</think>Answer: 3",
                                             finish_reason="stop", stop_reason=None)
                return [SimpleNamespace(finished=True, prompt_token_ids=p["prompt_token_ids"],
                                        outputs=[completion]) for p in prompts]

        torch = SimpleNamespace(__version__="test", version=SimpleNamespace(cuda="test"),
                                cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1,
                                                     get_device_name=lambda _: "fake GPU",
                                                     get_device_properties=lambda _: SimpleNamespace(total_memory=1)),
                                backends=SimpleNamespace(cuda=SimpleNamespace(matmul=SimpleNamespace()),
                                                         cudnn=SimpleNamespace()),
                                use_deterministic_algorithms=lambda *a, **kw: None)
        with tempfile.TemporaryDirectory() as temp, patch.dict("sys.modules", {
            "torch": torch, "vllm": SimpleNamespace(LLM=FakeLLM, SamplingParams=SimpleNamespace)
        }), patch.object(probe.metadata, "version", return_value="0.28.0"), patch.object(
            probe.metadata, "distributions", return_value=[]
        ), patch.object(probe.subprocess, "check_output", return_value="fake-driver"), patch.object(
            probe, "backup", return_value=Path(temp) / "unused.zip"
        ):
            run = Path(temp) / "run"
            probe.publish(run / "plan.json", plan)
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                probe.collect(run, None)
            self.assertEqual(len(probe.validate_batches(run, plan)), 4)
            probe.collect(run, None)
            self.assertEqual(len(probe.validate_batches(run, plan)), 260)
            self.assertEqual({r["requested_budget"] for r in probe.validate_batches(run, plan)},
                             {None, 256, 512, 1024, 2048, 3600})
            self.assertEqual(len(generated), 260)
            self.assertEqual(len(set(generated)), 260)
            probe.collect(run, None)
            self.assertEqual(state["engines"], 2)


if __name__ == "__main__":
    unittest.main()
