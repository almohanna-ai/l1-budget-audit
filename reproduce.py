"""Recompute the main experiment, overlap, five figures, and two-model pilots.

Run on a CPU with Python 3.11 and requirements.txt. All inputs are bundled JSON.
No model download, GPU, API key, network, or inference dependency is used.
Each invocation requires a new output directory; failed attempts are retained.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from verify_release import sha256, verify_files

ROOT = Path(__file__).resolve().parent
MAIN_MUTABLE_PROVENANCE = frozenset({
    "input_hashes", "builder", "builder_sha256", "python", "numpy", "matplotlib",
})
OVERLAP_MUTABLE_METADATA = frozenset({"builder_sha256", "python", "numpy", "matplotlib"})
CSV_PAIRS = (
    ("main/analysis/budget-summary.csv", "analysis/budget-summary.csv"),
    ("main/analysis/paired-contrasts.csv", "analysis/paired-contrasts.csv"),
    ("main/analysis/accuracy-by-difficulty.csv", "analysis/accuracy-by-difficulty.csv"),
    ("main/analysis/accuracy-by-subject.csv", "analysis/accuracy-by-subject.csv"),
    ("length-overlap/length-summary.csv", "analysis/length-overlap/length-summary.csv"),
    ("length-overlap/same-question-comparisons.csv", "analysis/length-overlap/same-question-comparisons.csv"),
)


def read_json(path: Path) -> Any:
    """Read UTF-8 JSON without changing the source artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_new(path: Path, payload: Any) -> None:
    """Write a finite JSON artifact exclusively, preserving previous files."""
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def comparable_analysis(payload: dict[str, Any], *, overlap: bool = False) -> dict[str, Any]:
    """Remove only enumerated runtime/path provenance, retaining scientific fields."""
    result = copy.deepcopy(payload)
    group = "metadata" if overlap else "provenance"
    excluded = OVERLAP_MUTABLE_METADATA if overlap else MAIN_MUTABLE_PROVENANCE
    for key in excluded:
        result[group].pop(key, None)
    return result


def reserve_output(output: Path) -> Path:
    """Create a fresh output root outside the release's frozen input directories."""
    output = output.resolve()
    protected = [ROOT] + [ROOT / name for name in (
        "data", "analysis", "figures", "protocol", "docs", "tests", "research_tools", "verification",
        "experiments", "scripts", "historical_code",
    )]
    if output == ROOT or any(output.is_relative_to(path) for path in protected[1:]):
        raise ValueError("Choose a new directory outside the release's frozen inputs")
    output.mkdir(parents=True, exist_ok=False)
    return output


def run_stage(name: str, arguments: list[str], output: Path) -> None:
    """Run one CPU stage and retain its complete console log on success or failure."""
    environment = dict(os.environ)
    environment.update({"CUDA_VISIBLE_DEVICES": "", "PYTHONHASHSEED": "0",
                        "MPLBACKEND": "Agg", "MPLCONFIGDIR": str(output / ".matplotlib")})
    log_path = output / "logs" / f"{name}.txt"
    print(f"Running {name} (CPU)...", flush=True)
    with log_path.open("x", encoding="utf-8") as log:
        completed = subprocess.run([sys.executable, *arguments], cwd=ROOT,
                                   env=environment, stdout=log, stderr=subprocess.STDOUT,
                                   check=False)
    if completed.returncode:
        raise RuntimeError(f"Stage {name} failed ({completed.returncode}); see {log_path}")


def compare_results(output: Path) -> dict[str, Any]:
    """Compare all scientific JSON fields and six CSV files to the frozen results."""
    main = read_json(output / "main/analysis/publication-analysis.json")
    overlap = read_json(output / "length-overlap/overlap-analysis.json")
    checks = {
        "main_scientific_json_equal": comparable_analysis(main) == comparable_analysis(
            read_json(ROOT / "analysis/publication-analysis.json")),
        "overlap_scientific_json_equal": comparable_analysis(overlap, overlap=True) == comparable_analysis(
            read_json(ROOT / "analysis/length-overlap/overlap-analysis.json"), overlap=True),
    }
    csv_checks = {generated: sha256(output / generated) == sha256(ROOT / expected)
                  for generated, expected in CSV_PAIRS}
    figures = [output / "main/figures" / f"{name}.{extension}"
               for name in ("figure-1-budget-accuracy-and-length",
                            "figure-2-adherence-and-boundary-sensitivity",
                            "figure-3-accuracy-by-difficulty")
               for extension in ("png", "pdf")]
    figures += [output / "length-figures" / f"{name}.{extension}"
                for name in ("length-ranges", "length-distributions")
                for extension in ("png", "pdf")]
    checks["five_figures_in_two_formats"] = all(path.is_file() and path.stat().st_size > 0 for path in figures)
    pilot_validation = read_json(output / "pilots/validation.json")
    checks["two_model_pilot_reproduction"] = pilot_validation["status"] == "passed"
    success = all(checks.values()) and all(csv_checks.values())
    return {
        "status": "passed" if success else "failed", "checks": checks, "csv_checks": csv_checks,
        "records": main["records"], "problems": main["problems"],
        "pilot_validation": pilot_validation,
        "accuracy_pct": {str(row["budget"]): row["accuracy_pct"] for row in main["budgets"]},
        "bootstrap_draw_matrix_sha256": main["bootstrap"]["draw_matrix_sha256"],
        "runtime": {"python": platform.python_version(), "numpy": main["provenance"]["numpy"],
                    "matplotlib": main["provenance"]["matplotlib"]},
        "comparison_policy": {
            "json": "Exact equality of scientific fields; no numeric tolerance or changed label exceptions",
            "main_provenance_exclusions": sorted(MAIN_MUTABLE_PROVENANCE),
            "overlap_metadata_exclusions": sorted(OVERLAP_MUTABLE_METADATA),
            "csv": "Exact byte hashes", "figures": "Existence checks; rendering bytes can differ across platforms",
        },
    }


def reproduce(output: Path) -> dict[str, Any]:
    """Verify inputs, run independent stages, and write an immutable comparison report."""
    integrity = verify_files(ROOT)
    output = reserve_output(output)
    (output / "logs").mkdir()
    write_json_new(output / "inputs.json", {
        "integrity": integrity, "input_sha256": sha256(ROOT / "data/analysis-records.json"),
        "summary_sha256": sha256(ROOT / "data/analysis-summary.json"),
        "script_sha256": sha256(Path(__file__)),
    })
    run_stage("main-analysis", [str(ROOT / "recompute_analysis.py"), "--output", str(output / "main")], output)
    run_stage("length-overlap", [str(ROOT / "research_tools/length_overlap.py"),
                                "--output", str(output / "length-overlap")], output)
    run_stage("length-figures", [str(ROOT / "research_tools/paper_length_figures.py"),
                                "--audit", str(output / "length-overlap/overlap-analysis.json"),
                                "--output", str(output / "length-figures")], output)
    run_stage("pilot-analysis", [str(ROOT / "scripts/analyze_pilots.py"),
                                 "--input-dir", str(ROOT / "experiments"),
                                 "--output", str(output / "pilots")], output)
    report = compare_results(output)
    write_json_new(output / "reproduction-check.json", report)
    if report["status"] != "passed":
        raise RuntimeError("Recomputed results differ; inspect reproduction-check.json and retain this attempt")
    return report


def main() -> int:
    """Expose a single-command, immutable CPU reproduction workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory, e.g. outputs/run-001")
    args = parser.parse_args()
    try:
        report = reproduce(args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
