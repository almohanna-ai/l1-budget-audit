"""Render the frozen length audit with legible labels at manuscript width."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from length_overlap import AnalysisConfig, COLORS, METRICS, load_records, save_figure, sha256, write_json
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def render_figures(records: list[dict[str, Any]], audit: dict[str, Any], output: Path, cap: int = 6000) -> None:
    """Render two vector figures without changing counts, labels, or analysis."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5,
                         "pdf.fonttype": 42, "axes.spines.top": False,
                         "axes.spines.right": False})
    titles = ("Reasoning prefix\nAvailable closing boundaries",
              "Complete output\nAll generations, including caps")
    budgets = sorted({row["requested_budget"] for row in records})
    formatter = FuncFormatter(lambda value, _: f"{value:,.0f}")
    fig, axes = plt.subplots(1, 2, figsize=(8.1, 4.9), sharex=True)
    for metric, title, ax in zip(METRICS, titles, axes):
        rows = [row for row in audit["summaries"] if row["metric"] == metric]
        for y, row in enumerate(rows):
            color = COLORS[y % len(COLORS)]
            ax.hlines(y, row["minimum"], row["maximum"], color="#8895A5", lw=1.2)
            ax.vlines((row["minimum"], row["maximum"]), y - .07, y + .07,
                      color="#8895A5", lw=1.1)
            ax.plot((row["p05"], row["p95"]), (y, y), color=color, lw=6.5,
                    alpha=.48, solid_capstyle="butt")
            ax.plot((row["p25"], row["p75"]), (y, y), color=color, lw=10,
                    solid_capstyle="butt")
            ax.plot(row["median"], y, "o", color="#172638", ms=3.8)
            ax.plot(row["budget"], y, "D", markerfacecolor="white",
                    markeredgecolor=color, ms=5.1)
            label = f"{int(row['minimum']):,}-{int(row['maximum']):,}; n={row['n']:,}"
            ax.text(110, y + .28, label, fontsize=9.8, color="#35465B")
        ax.set_yticks(range(len(rows)), [f"{row['budget']:,}" for row in rows])
        ax.set_ylim(len(rows) - .45, -.57)
        ax.set_xlim(0, cap + 180)
        ax.set_xticks((0, 2000, 4000, 6000))
        ax.xaxis.set_major_formatter(formatter)
        ax.set_title(title, fontsize=11.2, pad=11)
        ax.set_xlabel("Actual generated tokens", fontsize=10.5)
        ax.set_ylabel("Requested budget", fontsize=10.5)
        ax.grid(axis="x", color="#E2E7ED", lw=.6)
    keys = [Line2D([0], [0], color="#8895A5", lw=1.2, label="Observed range"),
            Line2D([0], [0], color=COLORS[0], alpha=.48, lw=6.5, label="5th-95th percentiles"),
            Line2D([0], [0], color=COLORS[0], lw=10, label="25th-75th percentiles"),
            Line2D([0], [0], color="#172638", marker="o", ls="none", label="Median"),
            Line2D([0], [0], color=COLORS[0], marker="D", markerfacecolor="white",
                   ls="none", label="Requested budget")]
    fig.legend(handles=keys, loc="lower center", ncol=3, frameon=False,
               bbox_to_anchor=(.5, .016), fontsize=9.5, columnspacing=1.25)
    fig.subplots_adjust(left=.09, right=.985, bottom=.22, top=.84, wspace=.34)
    save_figure(fig, output, "length-ranges")

    width = 64
    edges = np.arange(0, math.ceil(cap / width) * width + width, width)
    fig, axes = plt.subplots(1, 2, figsize=(8.1, 4.7), sharex=True)
    for metric, title, ax in zip(METRICS, titles, axes):
        for index, budget in enumerate(budgets):
            values = [row[metric] for row in records
                      if row["requested_budget"] == budget and row[metric] is not None]
            counts = np.histogram(values, bins=edges)[0]
            if counts.sum() != len(values):
                raise ValueError("Publication histogram lost an observation")
            ax.stairs(100 * counts / len(values), edges, color=COLORS[index % len(COLORS)],
                      lw=1.4, label=f"Budget {budget:,}")
        ax.set_title(title, fontsize=11.2, pad=11)
        ax.set_xlabel("Actual generated tokens", fontsize=10.5)
        ax.set_ylabel("Generations per bin (%)", fontsize=10.5)
        ax.set_xlim(0, cap + 70)
        ax.set_xticks((0, 2000, 4000, 6000))
        ax.xaxis.set_major_formatter(formatter)
        ax.grid(color="#E2E7ED", lw=.6)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False,
               bbox_to_anchor=(.5, .02), fontsize=9.5, columnspacing=1.2)
    fig.subplots_adjust(left=.09, right=.962, bottom=.21, top=.83, wspace=.35)
    save_figure(fig, output, "length-distributions")


def main() -> None:
    """Read frozen records and audit JSON, then create a new figure directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/analysis-records.json")
    parser.add_argument("--audit", type=Path, default=ROOT / "analysis/length-overlap/overlap-analysis.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("Choose a new output directory; earlier figures are immutable")
    records = load_records(AnalysisConfig(args.input.resolve(), output))
    audit = json.loads(args.audit.read_bytes())
    if audit["metadata"]["input_sha256"] != sha256(args.input):
        raise ValueError("Audit JSON fingerprint does not match the supplied records")
    output.mkdir(parents=True, exist_ok=False)
    render_figures(records, audit, output)
    write_json(output / "overlap-figure-manifest.json", {
        "input_sha256": sha256(args.input), "audit_sha256": sha256(args.audit),
        "builder_sha256": sha256(Path(__file__)), "layout": "8.1-inch canvas for manuscript-width rendering",
        "files": {path.name: sha256(path) for path in sorted(output.iterdir()) if path.is_file()},
        "statistical_changes": "None; frozen quantiles and original integer length observations",
    })


if __name__ == "__main__":
    main()
