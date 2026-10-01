"""Audit empirical length ranges and overlap without inference or GPU calls.

Inputs are previously exported JSON records. The output directory must be new;
all results are created exclusively. No answer labels or token counts change.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import platform
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
METRICS = ("reasoning_tokens", "total_output_tokens")
COLORS = ("#3471B2", "#1B8B80", "#C15F38", "#7566A9")


@dataclass(frozen=True)
class AnalysisConfig:
    """Configuration belonging only to this descriptive analysis stage."""

    input_path: Path
    output_path: Path
    histogram_widths: tuple[int, ...] = (32, 64, 128)
    plot_bin_width: int = 64
    output_cap: int = 6000


def sha256(path: Path) -> str:
    """Fingerprint the exact bytes of one input or code file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    """Create a deterministic JSON artifact without overwriting anything."""
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Create a flat UTF-8 CSV artifact with a stable column order."""
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_records(config: AnalysisConfig) -> list[dict[str, Any]]:
    """Validate a complete question-budget grid and original length boundaries."""
    records = json.loads(config.input_path.read_bytes())
    if not isinstance(records, list) or not records:
        raise ValueError("Input must be a nonempty JSON array of generation records")
    identities: set[tuple[str, int, int]] = set()
    groups: dict[tuple[str, int], set[int]] = defaultdict(set)
    raw_ids: set[str] = set()
    for index, row in enumerate(records):
        for field in ("requested_budget", "sample_index", "total_output_tokens"):
            if type(row[field]) is not int or row[field] < 0:
                raise ValueError(f"records[{index}].{field} must be a nonnegative integer")
        if row["requested_budget"] == 0:
            raise ValueError(f"records[{index}].requested_budget must be positive")
        if type(row["closed"]) is not bool or type(row["hit_cap"]) is not bool:
            raise ValueError(f"records[{index}] has non-boolean boundary/cap flags")
        total = row["total_output_tokens"]
        if not 0 < total <= config.output_cap:
            raise ValueError(f"records[{index}] exceeds the declared output cap")
        if row["hit_cap"] and total != config.output_cap:
            raise ValueError(f"records[{index}] has inconsistent hit_cap/length")
        if row["closed"]:
            r, f = row["reasoning_tokens"], row["final_response_tokens"]
            if type(r) is not int or type(f) is not int or r < 0 or f < 0 or total != r + 1 + f:
                raise ValueError(f"records[{index}] violates the archived T=R+1+F boundary")
        elif row["reasoning_tokens"] is not None or row["final_response_tokens"] is not None:
            raise ValueError(f"records[{index}] has a length assigned to an unavailable boundary")
        key = (row["problem_id"], row["requested_budget"], row["sample_index"])
        if key in identities or row["raw_record_id"] in raw_ids:
            raise ValueError(f"records[{index}] duplicates a generation identity")
        identities.add(key)
        raw_ids.add(row["raw_record_id"])
        groups[key[:2]].add(key[2])
    problems = {row["problem_id"] for row in records}
    budgets = {row["requested_budget"] for row in records}
    samples = {row["sample_index"] for row in records}
    if len(budgets) < 2 or samples != set(range(max(samples) + 1)):
        raise ValueError("Expected at least two budgets and consecutive sample indices from zero")
    if len(groups) != len(problems) * len(budgets) or any(value != samples for value in groups.values()):
        raise ValueError("Input is not a complete balanced question-budget-sample grid")
    return records


def length_summary(values: Sequence[int]) -> dict[str, Any]:
    """Describe observed support and interpolated quantiles, without fitting tails."""
    if not values:
        raise ValueError("Cannot summarize an empty set of available lengths")
    q = np.quantile(values, (0, .05, .25, .5, .75, .95, 1), method="linear")
    return dict(zip(("minimum", "p05", "p25", "median", "p75", "p95", "maximum"),
                    [float(value) for value in q])) | {"n": len(values), "mean": float(np.mean(values))}


def interval_intersection(a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    """Return overlap or touching of two inclusive observed intervals."""
    lower, upper = max(a[0], b[0]), min(a[1], b[1])
    overlaps = lower <= upper
    return {"overlaps_or_touches": overlaps,
            "lower": lower if overlaps else None, "upper": upper if overlaps else None,
            "span_tokens": upper - lower if overlaps else 0.0}


def empirical_overlap(a: Sequence[int], b: Sequence[int]) -> float:
    """Compute overlap of empirical exact-integer point masses, not populations."""
    left, right = Counter(a), Counter(b)
    return math.fsum(min(left[value] / len(a), right[value] / len(b))
                     for value in sorted(left.keys() & right.keys()))


def histogram_overlap(a: Sequence[int], b: Sequence[int], width: int, cap: int) -> float:
    """Compute descriptive overlap on common bins; nearby distinct values can share a bin."""
    if width < 1:
        raise ValueError("Histogram width must be positive")
    edges = np.arange(0, math.ceil(cap / width) * width + width, width)
    left = np.histogram(a, bins=edges)[0]
    right = np.histogram(b, bins=edges)[0]
    if left.sum() != len(a) or right.sum() != len(b):
        raise ValueError("A histogram lost observations outside its declared support")
    return float(np.minimum(left / len(a), right / len(b)).sum())


def analyze(records: list[dict[str, Any]], config: AnalysisConfig) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compute marginal and same-question descriptions while preserving every input row."""
    budgets = sorted({row["requested_budget"] for row in records})
    problems = sorted({row["problem_id"] for row in records})
    summaries, comparisons, question_rows = [], [], []
    for metric in METRICS:
        group = {budget: [row[metric] for row in records if row["requested_budget"] == budget
                          and row[metric] is not None] for budget in budgets}
        by_question: dict[tuple[str, int], list[int]] = defaultdict(list)
        for row in records:
            if row[metric] is not None:
                by_question[(row["problem_id"], row["requested_budget"])].append(row[metric])
        statistics = {budget: length_summary(group[budget]) for budget in budgets}
        for budget in budgets:
            selected = [row for row in records if row["requested_budget"] == budget]
            summaries.append({"metric": metric, "budget": budget,
                              "input_n": len(selected), "unavailable": len(selected) - len(group[budget]),
                              "cap_hits_all_outputs": sum(row["hit_cap"] for row in selected),
                              **statistics[budget]})
        for lower, higher in combinations(budgets, 2):
            a, b = group[lower], group[higher]
            sa, sb = statistics[lower], statistics[higher]
            conditional = []
            for problem in problems:
                x, y = by_question[(problem, lower)], by_question[(problem, higher)]
                if not x or not y:
                    raise ValueError(f"No available {metric} for {problem}, budgets {lower}/{higher}")
                overlap = interval_intersection((min(x), max(x)), (min(y), max(y)))
                # All cross-repetition pairs are used. Sample indices do not identify
                # matched random seeds across budget conditions.
                le = sum(right <= left for left in x for right in y)
                conditional.append({"problem_id": problem, "metric": metric,
                                    "lower_budget": lower, "higher_budget": higher,
                                    "lower_n": len(x), "higher_n": len(y),
                                    "lower_min": min(x), "lower_max": max(x),
                                    "higher_min": min(y), "higher_max": max(y),
                                    "ranges_overlap_or_touch": overlap["overlaps_or_touches"],
                                    "higher_not_longer_cross_pairs": le,
                                    "cross_pairs": len(x) * len(y),
                                    "higher_not_longer_rate": le / (len(x) * len(y))})
            question_rows.extend(conditional)
            shared = sorted(Counter(a).keys() & Counter(b).keys())
            comparisons.append({
                "metric": metric, "lower_budget": lower, "higher_budget": higher,
                "range_intersection": interval_intersection((sa["minimum"], sa["maximum"]),
                                                           (sb["minimum"], sb["maximum"])),
                "central_90_intersection": interval_intersection((sa["p05"], sa["p95"]),
                                                                (sb["p05"], sb["p95"])),
                "higher_min_minus_lower_max_tokens": sb["minimum"] - sa["maximum"],
                "shared_observed_integer_lengths": len(shared),
                "empirical_exact_overlap_pct": 100 * empirical_overlap(a, b),
                "histogram_overlap_pct": {str(width): 100 * histogram_overlap(a, b, width, config.output_cap)
                                          for width in config.histogram_widths},
                "problems": len(problems),
                "same_question_ranges_overlap_or_touch": sum(row["ranges_overlap_or_touch"] for row in conditional),
                "same_question_range_overlap_pct": 100 * sum(row["ranges_overlap_or_touch"] for row in conditional) / len(problems),
                "same_question_higher_not_longer_pct": 100 * math.fsum(row["higher_not_longer_rate"] for row in conditional) / len(problems),
            })
    return {"summaries": summaries, "comparisons": comparisons}, question_rows


def save_figure(fig: plt.Figure, output: Path, name: str) -> None:
    """Save a vector PDF and a 220-dpi PNG with no timestamp-dependent PDF metadata."""
    for suffix in ("pdf", "png"):
        stream = io.BytesIO()
        options = {"metadata": {"CreationDate": None, "ModDate": None}} if suffix == "pdf" else {}
        fig.savefig(stream, format=suffix, dpi=220, facecolor="white", **options)
        with (output / f"{name}.{suffix}").open("xb") as target:
            target.write(stream.getvalue())
    plt.close(fig)


def plot_figures(records: list[dict[str, Any]], results: dict[str, Any], config: AnalysisConfig) -> None:
    """Plot full ranges, central distributions, and separate token-count boundaries."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False})
    budgets = sorted({row["requested_budget"] for row in records})
    titles = ("Reasoning prefix: available boundaries only", "Complete output: every generation, including caps")
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.4), sharex=True)
    for metric, title, ax in zip(METRICS, titles, axes):
        rows = [row for row in results["summaries"] if row["metric"] == metric]
        for y, row in enumerate(rows):
            color = COLORS[y % len(COLORS)]
            ax.hlines(y, row["minimum"], row["maximum"], color="#8895A5", lw=1.3)
            ax.vlines((row["minimum"], row["maximum"]), y - .09, y + .09, color="#8895A5", lw=1.2)
            ax.plot((row["p05"], row["p95"]), (y, y), color=color, lw=8, alpha=.48, solid_capstyle="butt")
            ax.plot((row["p25"], row["p75"]), (y, y), color=color, lw=13, solid_capstyle="butt")
            ax.plot(row["median"], y, "o", color="#172638", ms=4)
            ax.plot(row["budget"], y, "D", markerfacecolor="white", markeredgecolor=color, ms=6)
            label = f"{int(row['minimum']):,}-{int(row['maximum']):,}  |  n={row['n']:,}"
            ax.text(120, y + .32, label, color="#35465B", fontsize=9)
        ax.set_yticks(range(len(rows)), [f"{row['budget']:,}" for row in rows])
        ax.set_ylim(len(rows) - .45, -.65)
        ax.set_xlim(0, config.output_cap + 180)
        ax.set_title(title, fontsize=11, pad=12)
        ax.set_xlabel("Observed generated tokens")
        ax.set_ylabel("Requested budget")
        ax.grid(axis="x", color="#E2E7ED", lw=.7)
    legend = [Line2D([0], [0], color="#8895A5", lw=1.3, label="Observed min-max"),
              Line2D([0], [0], color=COLORS[0], alpha=.48, lw=8, label="5th-95th percentiles"),
              Line2D([0], [0], color=COLORS[0], lw=13, label="25th-75th percentiles"),
              Line2D([0], [0], color="#172638", marker="o", ls="none", label="Median"),
              Line2D([0], [0], color=COLORS[0], marker="D", markerfacecolor="white", ls="none", label="Requested budget")]
    fig.suptitle("Empirical audit of generation budgets and accuracy: observed length ranges", fontsize=14, y=.98)
    fig.legend(handles=legend, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(.5, .07), fontsize=9)
    fig.text(.5, .025, "500 questions x 16 generations x 4 budgets. Reasoning lengths unavailable for 39 outputs; total-output cap = 6,000.",
             ha="center", fontsize=9, color="#35465B")
    fig.subplots_adjust(left=.07, right=.98, bottom=.24, top=.85, wspace=.22)
    save_figure(fig, config.output_path, "length-ranges")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharex=True)
    edges = np.arange(0, math.ceil(config.output_cap / config.plot_bin_width) * config.plot_bin_width + config.plot_bin_width,
                      config.plot_bin_width)
    for metric, title, ax in zip(METRICS, titles, axes):
        for index, budget in enumerate(budgets):
            values = [row[metric] for row in records if row["requested_budget"] == budget and row[metric] is not None]
            count = np.histogram(values, bins=edges)[0]
            ax.stairs(100 * count / len(values), edges, color=COLORS[index % len(COLORS)], lw=1.7, label=f"Budget {budget:,}")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Observed generated tokens")
        ax.set_ylabel(f"Available generations per {config.plot_bin_width}-token bin (%)")
        ax.set_xlim(0, config.output_cap + 50)
        ax.grid(color="#E2E7ED", lw=.7)
        ax.legend(frameon=False, fontsize=9)
    fig.suptitle("Length distributions: common bins, without a smoothed density fit", fontsize=14, y=.97)
    fig.text(.5, .035, "Percentages normalize separately within each budget. Shared bins can contain different exact lengths; no population-overlap estimate is claimed.",
             ha="center", fontsize=8.5, color="#35465B")
    fig.subplots_adjust(left=.07, right=.98, bottom=.18, top=.82, wspace=.24)
    save_figure(fig, config.output_path, "length-distributions")


def main() -> None:
    """Read a frozen JSON export and create a new CPU-only descriptive audit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/analysis-records.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-cap", type=int, default=6000)
    args = parser.parse_args()
    config = AnalysisConfig(args.input.resolve(), args.output.resolve(), output_cap=args.output_cap)
    if config.output_path.exists():
        raise FileExistsError("Choose a new output directory; previous results are immutable")
    records = load_records(config)
    result, question_rows = analyze(records, config)
    result["metadata"] = {
        "study_description": "Empirical audit of generation budgets and accuracy",
        "record_count": len(records), "problem_count": len({row['problem_id'] for row in records}),
        "input_sha256": sha256(config.input_path), "builder_sha256": sha256(Path(__file__)),
        "python": platform.python_version(), "numpy": np.__version__, "matplotlib": matplotlib.__version__,
        "execution": "CPU-only; no inference, re-tokenization, or regrading",
        "reasoning_boundary": "Original-ID prefix before the unique closing marker; unavailable boundaries remain null",
        "total_boundary": "All generated token IDs; includes caps and the final answer",
        "quantiles": "NumPy linear interpolation; central 90% is p05-p95, not a confidence interval",
        "exact_overlap": "Sum of minimum empirical point-mass probabilities at shared observed integer lengths; finite-sample description, not population support",
        "histogram_overlap": "Sum of minimum normalized counts on common zero-origin bins. Width sensitivity is reported at 32,64,128 tokens; binning may create apparent overlap of distinct lengths",
        "conditional_comparison": "500 equally weighted question-specific cross-repetition comparisons; sample indices are not matched seeds across budgets",
        "closed_selection": "Reasoning summaries exclude missing boundaries; absence of observed overlap is not a guarantee for excluded, future, or out-of-distribution generations",
        "claims": "Post-hoc descriptive study; overlap alone does not demonstrate novelty, accuracy gain, or a causal effect of length",
    }
    config.output_path.mkdir(parents=True, exist_ok=False)
    write_json(config.output_path / "overlap-analysis.json", result)
    write_csv(config.output_path / "length-summary.csv", result["summaries"])
    write_csv(config.output_path / "same-question-comparisons.csv", question_rows)
    plot_figures(records, result, config)
    write_json(config.output_path / "manifest.json", {
        "files": {path.name: sha256(path) for path in sorted(config.output_path.iterdir()) if path.is_file()},
        "input_sha256": sha256(config.input_path), "builder_sha256": sha256(Path(__file__)),
        "immutable_output_policy": "Exclusive creation in a new directory",
    })
    print(json.dumps({"output": str(config.output_path), "records": len(records),
                      "comparisons": result["comparisons"]}, indent=2))


if __name__ == "__main__":
    main()
