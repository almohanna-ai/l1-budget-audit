"""Reproduce two completed pilot summaries on CPU using Python's standard library.

Consumes curated scalar records; never imports archived collection code, loads a
model, or regrades answers. Output must be a new directory. Historical accuracy
bounds treat unresolved grades as unknown; they are not confidence intervals.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import itertools
import json
from pathlib import Path
import statistics
from typing import Any

EXPERIMENTS = {
    "comprehensive_v3_two_models": ("l1-two-models-n5-c13-s4-v3", 13, 520),
    "matched_v4_two_models": ("l1-two-models-n5-c5-s4-format-calibration-v4", 5, 200),
}
MODEL_ORDER = ("small", "large")
VALID_BOUNDARIES = {"explicit_open", "implicit_open_before_unique_close"}
INVALID_BOUNDARIES = {"missing_or_ambiguous", "text_id_disagreement"}
FIELDS = {
    "model", "record_id", "model_id", "model_revision", "problem_id", "condition_id",
    "condition_group", "requested_budget", "sample_index", "shots", "generation_seed",
    "prompt_sha256", "total_tokens", "think_tokens", "boundary_status", "hit_cap",
    "finish_reason", "thinking_style_proxies", "final_style_proxies", "grading_status", "grading_reason",
}


def canonical(value: Any) -> bytes:
    """Match the original collector's canonical JSON encoding."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_json(path: Path) -> Any:
    """Load one JSON artifact without executing its contents."""
    return json.loads(path.read_text(encoding="utf-8"))


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Match historical CSV order, UTF-8 BOM, and CRLF line endings."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["model", *sorted(key for key in rows[0] if key != "model")])
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def validate_records(records: list[dict[str, Any]], protocol: dict[str, Any]) -> None:
    """Require the complete, unique model/problem/condition/repetition grid."""
    if protocol["samples"] != 4 or tuple(protocol["model_order"]) != MODEL_ORDER:
        raise ValueError("Pilot requires four repetitions and both models in historical order")
    problems = [problem["problem_id"] for problem in protocol["problem_metadata"]]
    condition_ids = [condition["id"] for condition in protocol["conditions"]]
    if len(problems) != 5 or len(set(problems)) != 5 or len(set(condition_ids)) != len(condition_ids):
        raise ValueError("Nonunique or incorrect problem/condition grid")
    if set(protocol["models"]) != set(MODEL_ORDER):
        raise ValueError("Both archived models are required")
    conditions = {condition["id"]: condition for condition in protocol["conditions"]}
    expected = set(itertools.product(MODEL_ORDER, problems, condition_ids, range(protocol["samples"])))
    seen: set[tuple[str, str, str, int]] = set()
    record_ids: set[tuple[str, str]] = set()
    for row in records:
        if set(row) != FIELDS:
            raise ValueError("Unexpected/missing projection fields; raw text and token arrays are not accepted")
        if type(row["sample_index"]) is not int:
            raise ValueError("Sample index must be an integer")
        key = (row["model"], row["problem_id"], row["condition_id"], row["sample_index"])
        if key in seen:
            raise ValueError(f"Duplicate grid entry: {key}")
        if key not in expected:
            raise ValueError(f"Unexpected grid entry: {key}")
        seen.add(key)
        record_key = (row["model"], row["record_id"])
        if record_key in record_ids:
            raise ValueError(f"Duplicate model-local record ID: {record_key}")
        record_ids.add(record_key)
        model = protocol["models"][row["model"]]
        condition = conditions[row["condition_id"]]
        if row["model_id"] != model["model_id"] or row["model_revision"] != model["model_revision"]:
            raise ValueError("Record model/revision differs from protocol")
        if (row["condition_group"] != condition["group"] or row["requested_budget"] != condition["budget"]
                or row["shots"] != (protocol["demonstrations"]["count"] if condition["demo_style"] else 0)):
            raise ValueError("Record condition metadata differs from protocol")
        total, think = row["total_tokens"], row["think_tokens"]
        if type(total) is not int or not 0 <= total <= protocol["max_new_tokens"]:
            raise ValueError("Invalid total token count")
        if think is not None and (type(think) is not int or not 0 <= think <= total):
            raise ValueError("Invalid thinking token count")
        boundary = row["boundary_status"]
        if boundary not in VALID_BOUNDARIES | INVALID_BOUNDARIES or (think is not None) != (boundary in VALID_BOUNDARIES):
            raise ValueError("Thinking length and boundary status disagree")
        if row["grading_status"] not in {"correct", "incorrect", "unresolved"}:
            raise ValueError("Unknown archived grading status")
        if type(row["hit_cap"]) is not bool or row["hit_cap"] != (row["finish_reason"] == "length"):
            raise ValueError("Cap and finish status disagree")
        expected_seed = int(hashlib.sha256(canonical([20260920, row["problem_id"], row["condition_id"], row["sample_index"]])).hexdigest()[:8], 16) % (2**31)
        if row["generation_seed"] != expected_seed:
            raise ValueError("Request seed differs from historical derivation")
        if not isinstance(row["prompt_sha256"], str) or len(row["prompt_sha256"]) != 64 or any(char not in "0123456789abcdef" for char in row["prompt_sha256"]):
            raise ValueError("Invalid archived prompt hash")
        for name in ("thinking_style_proxies", "final_style_proxies"):
            proxies = row[name]
            if set(proxies) != {"nonempty_lines", "short_line_fraction", "alphabetic_runs"}:
                raise ValueError("Unexpected style-proxy fields")
            for field, value in proxies.items():
                if value is not None and (type(value) not in (int, float) or value < 0):
                    raise ValueError("Style proxy must be a nonnegative numeric value or null")
                if field == "short_line_fraction" and value is not None and not 0 <= value <= 1:
                    raise ValueError("Style-proxy fraction outside [0, 1]")
    if seen != expected:
        raise ValueError(f"Incomplete grid: {len(seen)} of {len(expected)} records; {len(expected - seen)} missing")
    if len(records) != protocol["expected_records"]:
        raise ValueError("Projection count differs from protocol")


def percentile(values: list[int], quantile: float) -> float | None:
    """Use the archived linear interpolation over valid thinking lengths."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def analyze_records(records: list[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    """Validate and aggregate projected archived grades and token lengths."""
    validate_records(records, protocol)
    summary, per_problem = [], []
    for model in MODEL_ORDER:
        for condition in protocol["conditions"]:
            selected = [row for row in records if row["model"] == model and row["condition_id"] == condition["id"]]
            lengths = [row["think_tokens"] for row in selected if row["think_tokens"] is not None]
            total = [row["total_tokens"] for row in selected]
            outcomes = Counter(row["grading_status"] for row in selected)
            n, budget = len(selected), condition["budget"]
            error = [abs(value - budget) for value in lengths] if budget is not None else []
            summary.append({
                "model": model, "condition": condition["id"], "condition_group": condition["group"],
                "requested_budget": budget, "collected": n, "expected": 20,
                "mean_total_tokens": statistics.mean(total) if total else None,
                "median_total_tokens": statistics.median(total) if total else None,
                "median_think_tokens": statistics.median(lengths) if lengths else None,
                "mean_think_tokens": statistics.mean(lengths) if lengths else None,
                "think_p10": percentile(lengths, .10), "think_p90": percentile(lengths, .90),
                "mean_abs_budget_error": statistics.mean(error) if error else None,
                "mean_signed_budget_error": statistics.mean(value - budget for value in lengths) if lengths and budget else None,
                "correct": outcomes["correct"], "incorrect": outcomes["incorrect"], "unresolved": outcomes["unresolved"],
                "accuracy_pct": 100 * outcomes["correct"] / n if n and not outcomes["unresolved"] else None,
                "lower_bound_pct": 100 * outcomes["correct"] / n if n else None,
                "upper_bound_pct": 100 * (outcomes["correct"] + outcomes["unresolved"]) / n if n else None,
                "valid_thinking_boundaries": len(lengths), "hit_cap": sum(row["hit_cap"] for row in selected),
            })
        for problem in protocol["problem_metadata"]:
            for condition in protocol["conditions"]:
                selected = [row for row in records if row["model"] == model and row["problem_id"] == problem["problem_id"]
                            and row["condition_id"] == condition["id"]]
                lengths = [row["think_tokens"] for row in selected if row["think_tokens"] is not None]
                per_problem.append({"model": model, "problem_id": problem["problem_id"], "condition": condition["id"],
                                    "n": len(selected), "valid_thinking_lengths": len(lengths),
                                    "mean_think_tokens": sum(lengths) / len(lengths) if lengths else None,
                                    "mean_total_tokens": sum(row["total_tokens"] for row in selected) / len(selected) if selected else None})
    return {**protocol["historical_combined_metadata"], "rows": summary, "per_problem": per_problem}


def load_experiment(directory: Path, expected: tuple[str, int, int]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Check released input hashes, schema dimensions, and model provenance."""
    manifest = read_json(directory / "source_manifest.json")
    filenames = {"records.jsonl", "protocol.json", "frozen_summary.json", "frozen_summary.csv"}
    if set(manifest["public_files"]) != filenames:
        raise ValueError("Manifest must cover exactly the four pilot input artifacts")
    for filename in sorted(filenames):
        data = (directory / filename).read_bytes()
        receipt = manifest["public_files"][filename]
        if len(data) != receipt["bytes"] or hashlib.sha256(data).hexdigest() != receipt["sha256"]:
            raise ValueError(f"Input integrity mismatch: {directory.name}/{filename}")
    protocol = read_json(directory / "protocol.json")
    experiment_id, conditions, count = expected
    if (protocol["experiment_id"] != experiment_id or len(protocol["conditions"]) != conditions
            or protocol["expected_records"] != count or manifest["experiment_id"] != experiment_id):
        raise ValueError("Pilot protocol identity or dimensions differ from release specification")
    historical = protocol["historical_combined_metadata"]
    if historical["protocol_sha256"] != protocol["protocol_sha256"]:
        raise ValueError("Historical protocol hash differs")
    for model in MODEL_ORDER:
        metadata, archived = protocol["models"][model], historical["models"][model]
        if (metadata["source_complete"] is not True or archived["complete"] is not True
                or metadata["model_id"] != archived["model_id"] or metadata["model_revision"] != archived["revision"]):
            raise ValueError("Historical model provenance differs or collection incomplete")
    records = [json.loads(line) for line in (directory / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    return records, protocol


def reproduce(input_dir: Path, output: Path) -> dict[str, Any]:
    """Verify both pilots and publish results exclusively into a new directory."""
    input_dir, output = input_dir.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f"Output must be a new directory: {output}")
    if input_dir == output or input_dir in output.parents or output in input_dir.parents:
        raise ValueError("Output must be separate from the immutable input directory")
    results, validations = {}, {}
    for folder, expected in EXPERIMENTS.items():
        directory = input_dir / folder
        records, protocol = load_experiment(directory, expected)
        result = analyze_records(records, protocol)
        frozen = read_json(directory / "frozen_summary.json")
        checks = {"summary_rows_equal": result["rows"] == frozen["rows"],
                  "per_problem_equal": result["per_problem"] == frozen["per_problem"],
                  "complete_json_equal": result == frozen,
                  "summary_json_bytes_equal": canonical(result) == (directory / "frozen_summary.json").read_bytes(),
                  "csv_equal": csv_bytes(result["rows"]) == (directory / "frozen_summary.csv").read_bytes()}
        if not all(checks.values()):
            raise ValueError(f"Historical reproduction mismatch for {folder}: {checks}")
        results[folder] = result
        validations[folder] = {"status": "passed", "record_count": len(records), "complete_unique_grid": True,
                               "model_counts": dict(Counter(row["model"] for row in records)),
                               "unresolved_counts": {model: sum(row["grading_status"] == "unresolved" for row in records if row["model"] == model)
                                                     for model in MODEL_ORDER},
                               "summary_row_count": len(result["rows"]), "per_problem_row_count": len(result["per_problem"]), **checks}
    validation = {"status": "passed", "record_count": sum(item["record_count"] for item in validations.values()),
                  "experiments": validations, "gpu_used": False,
                  "scope": "Reaggregates frozen scalar lengths and archived automatic grades; does not rerun inference or raw-output grading.",
                  "accuracy_bounds": "Unresolved-answer bounds; not confidence intervals. All collected records remain in the denominator.",
                  "human_compliance": "No human decisions created; retained automated style proxies are not verdicts."}
    output.mkdir(parents=True, exist_ok=False)
    for folder, result in results.items():
        destination = output / folder
        destination.mkdir()
        with (destination / "summary.json").open("xb") as stream:
            stream.write(canonical(result))
        with (destination / "summary.csv").open("xb") as stream:
            stream.write(csv_bytes(result["rows"]))
    with (output / "validation.json").open("x", encoding="utf-8") as stream:
        json.dump(validation, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return validation


def main() -> None:
    """Run the standard-library-only CPU verification command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path(__file__).resolve().parents[1] / "experiments")
    parser.add_argument("--output", required=True, type=Path, help="Required new output directory; existing directories are refused")
    args = parser.parse_args()
    try:
        validation = reproduce(args.input_dir, args.output)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(2, f"Pilot reproduction failed: {error}\n")
    print(json.dumps({"status": validation["status"], "record_count": validation["record_count"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
