"""Recompute the reviewed run's descriptive results and problem-cluster intervals.

CPU only. This script reads the reviewed, immutable generation records and their
summary; it never writes to an experiment artifact or a previous paper package.
It writes new JSON/CSV and PDF/PNG artifacts, refusing to overwrite any result.
Run with a Python runtime; numpy and matplotlib are the only non-stdlib
dependencies. The 95% bootstrap intervals are a similar-problem-population
heuristic, not uncertainty about an observed fixed benchmark or grading error.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE
INPUT = HERE / "data/analysis-records.json"
SUMMARY = HERE / "data/analysis-summary.json"
PREVIOUS_ANALYSIS = HERE / "analysis/publication-analysis.json"
ANALYSIS = HERE / "analysis"
FIGURES = HERE / "figures"
BUDGETS = (512, 1024, 2048, 3600)
CONTRASTS = ((512, 1024), (1024, 2048), (2048, 3600), (512, 3600))
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20260927
NAVY = "#263B52"
BLUE = "#3471B2"
TEAL = "#1B8B80"
ORANGE = "#C15F38"
GOLD = "#AF8421"
PURPLE = "#7566A9"

# These 14 records were identified in the archived rule-5 and qualifier review.
# This targeted sensitivity is not an audit estimate of an overall judge error.
RUBRIC_IDS = (
    "raw-record-027f8109f40d9e1cff53f6deaf590d7794feda20f8f707d92c315d370701423b",
    "raw-record-0ee25afe72974b8d26f3a8ce90dbc4f3b8acde64c07f2fc59caf907ada32ae83",
    "raw-record-17dd3d97ded7eea54b936154a885cce3bbf2c03c5530f56ff64c98e26645dd53",
    "raw-record-536da90f060881747de38b946262e40e87c9db9a620fa79e0593cd00245affb2",
    "raw-record-88ae3b442a4da9aa2101a83888bc9399f14bc95c9d4406eb84a206e7562fff8f",
    "raw-record-ae6de809ca8e6969f0b87693a8da6a32152cc2c10d61919898f958a6893adfca",
    "raw-record-c14a71271868d2ad88e0f7e0e56379b1f61e9f608a76c622651928f37d66cd5e",
    "raw-record-cf014d41559e85665d1911d58818d52159b263438d482db9fa34a4289b0dee1a",
    "raw-record-f776ce34c3c2c6aec718073641b2cbf83b806966e34cf74017a4b1c2549174bd",
    "raw-record-bb4de8d23b994615cdb8412d5e432ef08f227cc132e311f7e0be00167a609681",
    "raw-record-cb35edb030663e9d897924b2a31a7c9d7cef0c9edb47675c405678d84a4e0f82",
    "raw-record-d47be144d3b3cf2cbc3e6310433660e127721f67c47c8d619ed1a2d300d70a69",
    "raw-record-ea2ad3cb36720c0955aea8169ff7e12f17b6ad200f671ca6c58c3a83437780d5",
    "raw-record-b29826d1de880a3949752d5f47e059ae4bb8f14b1c81a01b41a6a323927849b4",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def dump_new(path: Path, payload: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2,
                  allow_nan=False)
        stream.write("\n")


def describe(values: Iterable[int | float | None]) -> dict[str, Any]:
    clean = np.asarray([float(x) for x in values if x is not None], dtype=float)
    if not len(clean) or not np.isfinite(clean).all():
        raise ValueError("Expected non-empty, finite token measurements")
    q = np.quantile(clean, (0.1, 0.25, 0.5, 0.75, 0.9), method="linear")
    return {"n": int(len(clean)), "sum": int(clean.sum()),
            "mean": statistics.fmean(clean), "median": float(q[2]),
            "p10": float(q[0]), "p25": float(q[1]), "p75": float(q[3]),
            "p90": float(q[4]), "iqr": float(q[3] - q[1]),
            "minimum": float(clean.min()), "maximum": float(clean.max())}


def accepted_correct(record: dict[str, Any]) -> bool:
    return record["final_comparison"]["status"] == "correct"


def completed_final_correct(record: dict[str, Any]) -> bool:
    # An explicitly stricter reporting convention, not a replacement judgment.
    return accepted_correct(record) and bool(record["closed"])


def scoring_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(record["final_comparison"]["status"] for record in records)
    n = len(records)
    if set(counts) - {"correct", "incorrect"}:
        raise ValueError("Reviewed scoring is not fully resolved")
    correct = counts["correct"]
    strict_correct = sum(completed_final_correct(record) for record in records)
    return {"n": n, "correct": correct, "incorrect": counts["incorrect"],
            "unresolved": 0, "accuracy": correct / n,
            "accuracy_pct": 100 * correct / n,
            "strict_completed_final": {
                "n": n, "correct": strict_correct,
                "incorrect": n - strict_correct,
                "accuracy": strict_correct / n,
                "accuracy_pct": 100 * strict_correct / n},
            "accepted_correct_unclosed": correct - strict_correct,
            "accepted_minus_strict_pp": 100 * (correct - strict_correct) / n}


def rubric_sensitivity(records: list[dict[str, Any]]) -> dict[str, Any]:
    ids = set(RUBRIC_IDS)
    found = [r for r in records if r["raw_record_id"] in ids]
    if len(found) != 14:
        raise ValueError("The 14 identified rubric-sensitive IDs are not present")
    rows = []
    for budget in BUDGETS:
        group = [r for r in records if r["requested_budget"] == budget]
        affected = [r for r in group if r["raw_record_id"] in ids]
        correct = sum(accepted_correct(r) for r in group if r["raw_record_id"] not in ids)
        n, unresolved = len(group), len(affected)
        rows.append({"budget": budget, "n": n, "correct": correct,
                     "incorrect": n - correct - unresolved, "unresolved": unresolved,
                     "accepted_correct_among_identified": sum(accepted_correct(r) for r in affected),
                     "accuracy_lower": correct / n,
                     "accuracy_upper": (correct + unresolved) / n,
                     "accuracy_lower_pct": 100 * correct / n,
                     "accuracy_upper_pct": 100 * (correct + unresolved) / n})
    return {
        "identified_records": 14, "raw_record_ids": list(RUBRIC_IDS),
        "identified_case_categories": {"non_simplified_expression": 9,
                                        "non_determined_set": 4,
                                        "qualifier_before_box": 1},
        "by_budget": rows,
        "convention": "Treat only these 14 archived, identified rubric-sensitive records as unresolved; retain every generation in its 8,000-row budget denominator. Logical lower bound assigns them incorrect and upper bound assigns them correct. These bounds are not confidence intervals, and the subset was not randomly sampled.",
        "evidence": {
            "publication_work/adjudication_review/ai_triage_first20_b.json": "0cee6967f5691d0e8542c7c121174f0cc83350b3349c6b4d2c53d33c74880a6c",
            "publication_work/adjudication_review/external_ai_round04_20260928_v1/math-spot-check.json": "fb62f4458b22e5168a59d484bf734b1924fce587b2d9e8eb4ddce2f3c467ef15"},
        "selection_provenance": "IDs for 13 rule-5 cases reconstructed from archived first-20 AI triage groups 3 and 6, consistent with the explicit 9+4 category counts in the math spot check; the qualifier record ID is explicit in that spot check. No new grading judgments were applied.",
        "scope": "A targeted policy sensitivity for identified cases only; not a random or comprehensive judge-error audit.",
    }


def adherence(values: Iterable[int | None], budget: int, tolerance: float) -> dict[str, Any]:
    clean = [x for x in values if x is not None]
    # Inclusive interval. Multiplication by 10 prevents floating-point ambiguity
    # for the primary tolerance, including at integer endpoints.
    if tolerance == 0.1:
        count = sum(9 * budget <= 10 * x <= 11 * budget for x in clean)
    else:
        count = sum((1 - tolerance) * budget <= x <= (1 + tolerance) * budget
                    for x in clean)
    return {"count": count, "n_available": len(clean),
            "fraction": count / len(clean), "pct": 100 * count / len(clean),
            "interval_inclusive": [(1 - tolerance) * budget, (1 + tolerance) * budget]}


def make_budget_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for budget in BUDGETS:
        group = [r for r in records if r["requested_budget"] == budget]
        row = {"budget": budget, **scoring_counts(group)}
        for field in ("reasoning_tokens", "total_output_tokens", "final_response_tokens"):
            row[field] = describe(r[field] for r in group)
        for short, field in (("reasoning", "reasoning_tokens"), ("total", "total_output_tokens")):
            mean = row[field]["mean"]
            row[f"{short}_mean_signed_error_tokens"] = mean - budget
            row[f"{short}_mean_signed_error_pct"] = 100 * (mean - budget) / budget
            row[f"{short}_within_10pct"] = adherence((r[field] for r in group), budget, 0.1)
            clean = [r[field] for r in group if r[field] is not None]
            row[f"{short}_abs_error_over_500_count"] = sum(abs(x - budget) > 500 for x in clean)
            row[f"{short}_abs_error_over_500_fraction"] = sum(abs(x - budget) > 500 for x in clean) / len(clean)
        row["closed"] = sum(bool(r["closed"]) for r in group)
        row["unclosed"] = len(group) - row["closed"]
        row["missing_reasoning"] = len(group) - row["reasoning_tokens"]["n"]
        row["hit_cap"] = sum(bool(r["hit_cap"]) for r in group)
        row["hit_cap_closed"] = sum(bool(r["hit_cap"] and r["closed"]) for r in group)
        row["origin_counts"] = dict(sorted(Counter(r["final_comparison"]["origin"] for r in group).items()))
        rows.append(row)
    return rows


def make_subgroup_rows(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        groups[(r["requested_budget"], str(r[field]))].append(r)
    return [{"budget": budget, field: value,
             "problems": len({r["problem_id"] for r in group}),
             **scoring_counts(group)}
            for (budget, value), group in sorted(groups.items())]


def validate(records: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if len(records) != 32_000 or len({r["raw_record_id"] for r in records}) != 32_000:
        raise ValueError("Expected exactly 32,000 unique original generation rows")
    if {r["requested_budget"] for r in records} != set(BUDGETS):
        raise ValueError("Unexpected requested budget set")
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        groups[(r["problem_id"], r["requested_budget"])].append(r)
        if r["final_comparison"]["status"] not in {"correct", "incorrect"}:
            raise ValueError("An unresolved reviewed decision was found")
        if r["closed"] != (r["boundary_status"] == "resolved"):
            raise ValueError("Closure and original-ID boundary status disagree")
        if (r["reasoning_tokens"] is not None) != r["closed"]:
            raise ValueError("Reasoning boundary missingness changed")
        if (r["final_response_tokens"] is not None) != r["closed"]:
            raise ValueError("Final-response boundary missingness changed")
        if r["closed"] and r["total_output_tokens"] != r["reasoning_tokens"] + r["final_response_tokens"] + 1:
            raise ValueError("Original-token accounting is inconsistent")
        if not r["closed"] and not r["hit_cap"]:
            raise ValueError("An unexpected non-capped unclosed output was found")
    problems = sorted({r["problem_id"] for r in records})
    if len(problems) != 500 or len(groups) != 2000:
        raise ValueError("Incomplete paired problem-by-budget grid")
    for problem in problems:
        for budget in BUDGETS:
            group = groups[(problem, budget)]
            if len(group) != 16 or {r["sample_index"] for r in group} != set(range(16)):
                raise ValueError("Each grid cell must contain sample indices 0 through 15")
        problem_rows = [r for budget in BUDGETS for r in groups[(problem, budget)]]
        for field in ("subject", "difficulty"):
            if len({r[field] for r in problem_rows}) != 1:
                raise ValueError("Problem metadata vary across generations")
    for group in summary["groups"]:
        got = scoring_counts([r for r in records if r["requested_budget"] == group["budget"]])
        for key in ("n", "correct", "incorrect", "unresolved"):
            if got[key] != group[key]:
                raise ValueError(f"The supplied review summary disagrees on {key}")
    origin_counts = Counter(r["final_comparison"]["origin"] for r in records)
    if dict(origin_counts) != summary["effective_origin_counts"]:
        raise ValueError("The supplied review summary has different scoring origins")
    if origin_counts != {"rule_based": 31567, "AI_adjudication": 405, "human_adjudication": 28}:
        raise ValueError("Unexpected review-origin totals")
    if sum(accepted_correct(r) and not r["closed"] for r in records) != 27:
        raise ValueError("Unexpected accepted-correct unclosed count")
    if sum(not r["closed"] for r in records) != 39:
        raise ValueError("Unexpected original boundary count")
    return problems


def bootstrap(records: list[dict[str, Any]], problems: list[str]) -> dict[str, Any]:
    index = {problem: i for i, problem in enumerate(problems)}
    accepted = np.zeros((500, 4), dtype=np.int64)
    strict = np.zeros((500, 4), dtype=np.int64)
    for r in records:
        i, j = index[r["problem_id"]], BUDGETS.index(r["requested_budget"])
        accepted[i, j] += int(accepted_correct(r))
        strict[i, j] += int(completed_final_correct(r))
    rng = random.Random(BOOTSTRAP_SEED)
    # This deliberately uses the historical random.Random/randrange draw stream.
    # Every resample contains 500 complete problems, preserving their 4 budgets
    # and all 16 within-condition generations. Rows are never sampled IID.
    draws = np.asarray([[rng.randrange(500) for _ in range(500)]
                        for _ in range(BOOTSTRAP_REPLICATES)], dtype=np.int16)
    endpoints = {}
    for name, counts in (("accepted_correctness", accepted),
                         ("strict_completed_final", strict)):
        replicates = counts[draws].sum(axis=1) / 8000
        observed = counts.sum(axis=0) / 8000
        interval = np.quantile(replicates, (0.025, 0.975), axis=0, method="linear")
        budget_rows = [{"budget": budget, "observed_accuracy": float(observed[j]),
                        "percentile_95": [float(interval[0, j]), float(interval[1, j])]}
                       for j, budget in enumerate(BUDGETS)]
        contrast_rows = []
        for before, after in CONTRASTS:
            j, k = BUDGETS.index(before), BUDGETS.index(after)
            delta = replicates[:, k] - replicates[:, j]
            ci = np.quantile(delta, (0.025, 0.975), method="linear")
            contrast_rows.append({"from_budget": before, "to_budget": after,
                                  "observed_gain": float(observed[k] - observed[j]),
                                  "observed_gain_pp": float(100 * (observed[k] - observed[j])),
                                  "percentile_95": [float(ci[0]), float(ci[1])],
                                  "percentile_95_pp": [float(100 * ci[0]), float(100 * ci[1])]})
        endpoints[name] = {"by_budget": budget_rows, "paired_contrasts": contrast_rows}
    endpoints["settings"] = {
        "unit": "problem", "original_problem_clusters": 500,
        "clusters_drawn_per_replicate": 500, "with_replacement": True,
        "samples_preserved_per_problem_budget": 16,
        "paired_across_budgets": True, "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
        "rng": "Python random.Random (MT19937), randrange(500), sorted problem IDs",
        "percentiles": [0.025, 0.975], "quantile_method": "linear interpolation",
        "interval_scope": "pointwise, unadjusted percentile 95% intervals",
        "sampling_interpretation": "A heuristic for a population of similar problems when the 500 benchmark problems are treated as exchangeable clusters. The fixed-benchmark observed rates themselves are exact conditional summaries.",
        "exclusions": "Does not estimate judge error or include a second-stage resampling of generations; not an IID 32,000-row interval.",
        "draw_matrix_sha256": hashlib.sha256(draws.astype("<i2").tobytes()).hexdigest(),
        "contrasts": [list(pair) for pair in CONTRASTS],
    }
    return endpoints


def write_csv_new(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def style() -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.titlesize": 10, "axes.labelsize": 9,
                         "axes.edgecolor": NAVY, "text.color": NAVY,
                         "axes.labelcolor": NAVY, "xtick.color": NAVY,
                         "ytick.color": NAVY, "legend.frameon": False,
                         "axes.grid": True, "grid.color": "#D9DEE5",
                         "grid.linewidth": 0.55, "grid.alpha": 0.7,
                         "axes.axisbelow": True, "figure.facecolor": "white",
                         "savefig.facecolor": "white", "pdf.fonttype": 42,
                         "ps.fonttype": 42})


def save_figure(fig: plt.Figure, stem: str) -> None:
    for suffix in ("png", "pdf"):
        if (FIGURES / f"{stem}.{suffix}").exists():
            raise FileExistsError("Refusing to overwrite an existing figure")
    fig.savefig(FIGURES / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIGURES / f"{stem}.pdf", bbox_inches="tight",
                metadata={"Title": stem, "Creator": "recompute_analysis.py",
                          "CreationDate": None, "ModDate": None})
    plt.close(fig)


def make_figures(analysis: dict[str, Any]) -> None:
    style()
    rows = analysis["budgets"]
    x = np.asarray(BUDGETS)
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.7), layout="constrained")
    ax = axes[0]
    observed = np.asarray([row["accuracy_pct"] for row in rows])
    intervals = 100 * np.asarray([row["accuracy_bootstrap_95"] for row in rows])
    ax.errorbar(x, observed, yerr=np.vstack((observed - intervals[:, 0], intervals[:, 1] - observed)),
                color=BLUE, marker="o", markersize=4.5, lw=1.8, capsize=3,
                label="Accepted correctness; 95% cluster interval")
    for budget, value in zip(x, observed):
        ax.annotate(f"{value:.2f}%", (budget, value), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=8)
    ax.set_title("(a) Accuracy at requested budgets", loc="left")
    ax.set_ylabel("Accepted generation accuracy (%)")
    ax.set_ylim(63, 88)
    ax.set_xlim(260, 3850)
    ax.legend(loc="lower right", fontsize=7.5)
    ax = axes[1]
    reason = np.asarray([row["reasoning_tokens"]["mean"] for row in rows])
    total = np.asarray([row["total_output_tokens"]["mean"] for row in rows])
    ax.plot(x, x, color="#78818A", ls="--", lw=1.1, label="Measured = requested")
    ax.plot(x, reason, color=ORANGE, marker="s", markersize=4, lw=1.8,
            label="Reasoning block (available boundaries)")
    ax.plot(x, total, color=TEAL, marker="o", markersize=4, lw=1.8,
            label="Total output (all generations)")
    for budget, value in zip(x, reason):
        ax.annotate(f"{value:,.0f}", (budget, value), textcoords="offset points",
                    xytext=(0, -15), ha="center", fontsize=8, color=ORANGE)
    ax.set_title("(b) Actual length versus request", loc="left")
    ax.set_ylabel("Original generated tokens (mean)")
    ax.set_ylim(0, 4000)
    ax.set_xlim(260, 3850)
    ax.legend(loc="upper left", fontsize=7.5)
    for ax in axes:
        ax.set_xticks(x, [f"{b:,}" for b in BUDGETS])
        ax.set_xlabel("Requested budget (tokens)")
        ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, "figure-1-budget-accuracy-and-length")

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.4), layout="constrained")
    positions = np.arange(4)
    ax = axes[0]
    width = 0.31
    ax.bar(positions - width / 2, [row["reasoning_within_10pct"]["pct"] for row in rows],
           width, color=ORANGE, label="Reasoning block")
    ax.bar(positions + width / 2, [row["total_within_10pct"]["pct"] for row in rows],
           width, color=TEAL, label="Total output")
    ax.set_title("(a) Within ±10% of requested budget", loc="left")
    ax.set_ylabel("Available measurements within interval (%)")
    ax.set_ylim(0, 106)
    ax.legend(loc="upper left", fontsize=8)
    ax = axes[1]
    change = [row["accepted_minus_strict_pp"] for row in rows]
    ax.bar(positions, change, color=BLUE, width=0.52)
    for position, value, row in zip(positions, change, rows):
        ax.text(position, value + 0.014, f"{row['accepted_correct_unclosed']} / 8,000\n{value:.3f} pp",
                ha="center", va="bottom", fontsize=8)
    ax.set_title("(b) Accepted versus completed-final scoring", loc="left")
    ax.set_ylabel("Accepted accuracy minus strict diagnostic (pp)")
    ax.set_ylim(0, 0.31)
    for ax in axes:
        ax.set_xticks(positions, [f"{b:,}" for b in BUDGETS])
        ax.set_xlabel("Requested budget (tokens)")
        ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, "figure-2-adherence-and-boundary-sensitivity")

    fig, ax = plt.subplots(figsize=(6.2, 3.7), layout="constrained")
    colors = (BLUE, TEAL, GOLD, ORANGE)
    for color, budget in zip(colors, BUDGETS):
        group = sorted((row for row in analysis["by_difficulty"] if row["budget"] == budget),
                       key=lambda row: int(row["difficulty"]))
        ax.plot([int(row["difficulty"]) for row in group],
                [row["accuracy_pct"] for row in group], marker="o", lw=1.7,
                color=color, markersize=4, label=f"{budget:,} tokens")
    ax.set_xlabel("Published MATH difficulty level")
    ax.set_ylabel("Accepted generation accuracy (%)")
    ax.set_xticks((1, 2, 3, 4, 5))
    ax.set_ylim(30, 101)
    ax.legend(ncol=2, loc="lower left", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, "figure-3-accuracy-by-difficulty")


def main() -> None:
    """Recompute the frozen main experiment in a new, portable output directory."""
    global INPUT, SUMMARY, ANALYSIS, FIGURES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT,
                        help="Reviewed original JSON or a projection retaining the required analysis fields")
    parser.add_argument("--summary", type=Path, default=SUMMARY,
                        help="Reviewed summary; reviewer identity and source-output text are not needed")
    parser.add_argument("--output", type=Path, required=True,
                        help="New version root containing analysis/ and figures/; existing artifacts are never replaced")
    parser.add_argument("--previous-analysis", type=Path,
                        default=PREVIOUS_ANALYSIS if PREVIOUS_ANALYSIS.exists() else None,
                        help="Optional prior analysis used solely to verify unchanged length summaries")
    args = parser.parse_args()
    INPUT, SUMMARY = args.input.resolve(), args.summary.resolve()
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    ANALYSIS, FIGURES = output_root / "analysis", output_root / "figures"
    for directory in (ANALYSIS, FIGURES):
        directory.mkdir(exist_ok=False)
    records = json.loads(INPUT.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    previous = json.loads(args.previous_analysis.read_text(encoding="utf-8")) if args.previous_analysis else None
    problems = validate(records, summary)
    rows = make_budget_rows(records)
    intervals = bootstrap(records, problems)
    for row, accepted, strict in zip(rows, intervals["accepted_correctness"]["by_budget"],
                                     intervals["strict_completed_final"]["by_budget"]):
        row["accuracy_bootstrap_95"] = accepted["percentile_95"]
        row["strict_completed_final"]["accuracy_bootstrap_95"] = strict["percentile_95"]
    length_preserved = None
    if previous:
        length_preserved = True
        for new, old in zip(rows, previous["budgets"]):
            for field in ("reasoning_tokens", "total_output_tokens", "final_response_tokens"):
                for key, value in old[field].items():
                    if not np.isclose(new[field][key], value, rtol=1e-12, atol=1e-12):
                        length_preserved = False
    if length_preserved is False:
        raise ValueError("Length statistics changed from the original experiment")
    final_rows = [r for r in records if r["final_comparison"]["origin"] == "human_adjudication"]
    analysis = {
        "kind": "reviewed-publication-analysis-v1", "records": 32_000,
        "problems": 500, "samples_per_problem_budget": 16,
        "budgets": rows, "overall": scoring_counts(records),
        "paired_contrasts": intervals["accepted_correctness"]["paired_contrasts"],
        "strict_completed_final_paired_contrasts": intervals["strict_completed_final"]["paired_contrasts"],
        "bootstrap": intervals["settings"],
        "by_difficulty": make_subgroup_rows(records, "difficulty"),
        "by_subject": make_subgroup_rows(records, "subject"),
        "identified_rubric_case_sensitivity": rubric_sensitivity(records),
        "adjudication": {
            "decision_field": "final_comparison.status",
            "effective_origin_counts": dict(sorted(Counter(r["final_comparison"]["origin"] for r in records).items())),
            "human_reviewed": len(final_rows), "human_correct": sum(accepted_correct(r) for r in final_rows),
            "human_incorrect": sum(not accepted_correct(r) for r in final_rows),
            "human_boundary_decisions": dict(sorted(Counter(
                f"{'closed' if r['closed'] else 'unclosed'}:{r['final_comparison']['status']}" for r in final_rows).items())),
            "remaining_unresolved": 0, "all_generations_human_reviewed": False,
            "independent_human_reviewer_count": summary["independent_human_reviewer_count"],
            "two_reviewer_consensus": summary["two_reviewer_consensus"],
            "review_scope": summary["human_review_scope"],
        },
        "boundary_counts": {
            "closed": sum(r["closed"] for r in records), "unclosed": sum(not r["closed"] for r in records),
            "cap_hits": sum(r["hit_cap"] for r in records),
            "cap_hits_closed": sum(r["hit_cap"] and r["closed"] for r in records),
            "unclosed_accepted_correct": sum(accepted_correct(r) and not r["closed"] for r in records),
            "unclosed_accepted_incorrect": sum(not accepted_correct(r) and not r["closed"] for r in records),
            "all_unclosed_hit_cap": True,
            "closing_marker_tokens_among_closed": dict(sorted(Counter(
                str(r["total_output_tokens"] - r["reasoning_tokens"] - r["final_response_tokens"])
                for r in records if r["closed"]).items())),
        },
        "estimands_and_conventions": {
            "accepted_accuracy": "Fraction of all 8,000 generations at a requested budget with final_comparison.status=correct; equal to the mean of 500 per-problem rates because every cell has 16 generations. No majority vote, pass@k, or best-of-16 selection.",
            "strict_completed_final_diagnostic": "Accepted correct AND closed=true. Every unclosed generation is incorrect under this explicitly stricter completion convention. This is a diagnostic endpoint, not a rejection of the accepted human judgments.",
            "paired_gain": "Later-budget accepted accuracy minus earlier-budget accepted accuracy, preserving problem pairing. Reported in fractions and percentage points; existing four contrasts retained.",
            "reasoning_length": "Original generated token IDs before the unique closing reasoning marker. Descriptions use only closed boundaries; the 39 missing boundaries are not imputed as short or long reasoning blocks.",
            "final_length": "Original generated token IDs after the unique closing reasoning marker, among closed boundaries. The single closing marker token is excluded from both blocks.",
            "boundary_formula": "For each closed row, T=R+m+F with m=1 closing-marker token in this run. Mean T over all rows minus mean R over closed rows is not exactly mean F over closed rows because their denominators differ. Any generated opening reasoning-marker IDs remain inside R; no stripping was applied.",
            "total_length": "All original generated token IDs including the closing marker and final response, including all capped generations.",
            "quantiles": "Linearly interpolated order-statistic quantiles, NumPy method=linear; IQR=p75-p25.",
            "adherence": "Descriptive ±10% inclusive interval around requested budget, used for both token boundaries. Reasoning denominator is the available boundary count; total denominator is all 8,000 generations. This is an analysis convention, not a training target inferred from the model paper.",
            "signed_error": "100*(mean actual tokens-requested budget)/requested budget. Positive means overshoot, negative means undershoot.",
            "subgroups": "Published difficulty and subject labels; descriptive, exploratory, no confidence intervals, no multiple-testing or subgroup-selected causal claims.",
            "scope": "A descriptive four-condition audit of one pinned model/sampler and all MATH-500 problems. No causal effect of observed reasoning length, global curve law, novelty, or model-general claim is identified.",
        },
        "provenance": {
            "input_hashes": {label(p): sha256(p) for p in
                             (INPUT, SUMMARY, *([args.previous_analysis] if args.previous_analysis else []))},
            "builder": label(Path(__file__)), "builder_sha256": sha256(Path(__file__)),
            "model_ids": sorted({r["model_id"] for r in records}),
            "model_revisions": sorted({r["model_revision"] for r in records}),
            "boundary_policy_versions": sorted({r["boundary_policy_version"] for r in records}),
            "condition_ids": sorted({r["condition_id"] for r in records}),
            "collection_environments": sorted({r["collection_environment"] for r in records}),
            "length_statistics_preserved_from_previous_analysis": length_preserved,
            "execution": "CPU-only local postprocessing; no inference and no GPU calls",
            "python": platform.python_version(), "numpy": np.__version__, "matplotlib": matplotlib.__version__,
        },
    }
    dump_new(ANALYSIS / "publication-analysis.json", analysis)
    flat = []
    for row in rows:
        entry = {k: row[k] for k in ("budget", "n", "correct", "incorrect", "unresolved", "accuracy_pct", "closed", "unclosed", "hit_cap", "accepted_correct_unclosed", "accepted_minus_strict_pp")}
        entry.update({"accuracy_ci_low_pct": 100 * row["accuracy_bootstrap_95"][0],
                      "accuracy_ci_high_pct": 100 * row["accuracy_bootstrap_95"][1],
                      "strict_completed_final_correct": row["strict_completed_final"]["correct"],
                      "strict_completed_final_accuracy_pct": row["strict_completed_final"]["accuracy_pct"]})
        for short, field in (("reasoning", "reasoning_tokens"), ("total", "total_output_tokens"), ("final", "final_response_tokens")):
            for statistic in ("n", "mean", "median", "p25", "p75", "iqr"):
                entry[f"{short}_{statistic}"] = row[field][statistic]
        for short in ("reasoning", "total"):
            entry[f"{short}_mean_signed_error_pct"] = row[f"{short}_mean_signed_error_pct"]
            for statistic in ("count", "n_available", "pct"):
                entry[f"{short}_within_10pct_{statistic}"] = row[f"{short}_within_10pct"][statistic]
        flat.append(entry)
    write_csv_new(ANALYSIS / "budget-summary.csv", flat)
    for field in ("difficulty", "subject"):
        subgroup = [{k: row[k] for k in ("budget", field, "problems", "n", "correct", "incorrect", "accuracy_pct", "accepted_correct_unclosed")}
                    | {"strict_completed_final_accuracy_pct": row["strict_completed_final"]["accuracy_pct"]}
                    for row in analysis[f"by_{field}"]]
        write_csv_new(ANALYSIS / f"accuracy-by-{field}.csv", subgroup)
    write_csv_new(ANALYSIS / "paired-contrasts.csv", [
        {"from_budget": row["from_budget"], "to_budget": row["to_budget"],
         "gain_pp": row["observed_gain_pp"], "ci_low_pp": row["percentile_95_pp"][0],
         "ci_high_pp": row["percentile_95_pp"][1]} for row in analysis["paired_contrasts"]])
    make_figures(analysis)
    captions = {
        "figure-1-budget-accuracy-and-length": "(a) Accepted generation-level correctness under mixed rule-based, AI, and single-human scoring. Bars are pointwise 95% percentile intervals from 10,000 paired problem-cluster resamples of 500 clusters, a similar-problem-population heuristic rather than uncertainty about the fixed benchmark or judge error. (b) Original-ID mean reasoning-block and total-output length versus requested budget. Reasoning summaries use 8000, 7999, 7991, and 7971 available boundaries; total summaries include all 8000 outputs at each budget, including caps. Lines connect four observed conditions and do not identify a fitted or global curve.",
        "figure-2-adherence-and-boundary-sensitivity": "(a) Descriptive adherence within an inclusive ±10% interval of the request. Reasoning denominators are available boundaries and total denominators are all outputs. (b) Accepted correctness minus the strict diagnostic that requires both accepted correctness and a closed reasoning boundary. The 27 accepted-correct unclosed outputs cause differences of 0, 0, 0.100, and 0.2375 percentage points; all 39 unclosed outputs are incorrect under the strict diagnostic.",
        "figure-3-accuracy-by-difficulty": "Descriptive accepted generation-level accuracy by published MATH difficulty level. Difficulty groups contain 43, 90, 105, 128, and 134 problems, with 16 generations per problem and budget. Curves are exploratory summaries with no inferential subgroup selection or causal interpretation.",
    }
    dump_new(FIGURES / "figure-captions.json", captions)
    dump_new(FIGURES / "figure-manifest.json", {
        "analysis_sha256": sha256(ANALYSIS / "publication-analysis.json"),
        "builder_sha256": sha256(Path(__file__)),
        "formats": {"pdf": "scientific vector figures with embedded TrueType fonts", "png": "300 dpi"},
        "files": {path.name: sha256(path) for path in sorted(FIGURES.iterdir()) if path.is_file()}})
    dump_new(ANALYSIS / "analysis-manifest.json", {
        "files": {path.name: sha256(path) for path in sorted(ANALYSIS.iterdir()) if path.is_file()},
        "immutable_output_policy": "Exclusive file creation; reruns require a new version directory"})
    print(json.dumps({"analysis": str(ANALYSIS / "publication-analysis.json"),
                      "figures": str(FIGURES), "records": len(records),
                      "accepted_accuracy_pct": [row["accuracy_pct"] for row in rows],
                      "paired_gain_pp": analysis["paired_contrasts"],
                      "length_preserved": length_preserved}, indent=2))


if __name__ == "__main__":
    main()
