"""Combine two completed/partial model reports without loading GPU packages."""
from __future__ import annotations
import argparse
import csv
import io
from pathlib import Path
from probe import publish, read, sha, stamp


def combine(root: Path) -> Path:
    """Publish paired model summaries, provenance and per-problem token means."""
    rows, models, per_problem = [], {}, []
    protocol = None
    for model in ("small", "large"):
        run = root / ("run-" + model)
        reports = sorted((run / "reports").glob("report-*.json"))
        if not reports:
            raise ValueError(f"No CPU report for {model}")
        plan, report = read(run / "plan.json"), read(reports[-1])
        if protocol is not None and protocol != plan["protocol_sha256"]:
            raise ValueError("Models used different protocols")
        protocol = plan["protocol_sha256"]
        models[model] = {"model_id": plan["model_id"], "revision": plan["model_revision"],
                         "complete": report["complete"], "source_report": str(reports[-1]),
                         "source_sha256": sha(reports[-1].read_bytes())}
        rows += [{"model": model, **r} for r in report["summary"]]
        for p in plan["spec"]["problems"]:
            for c in plan["spec"]["conditions"]:
                subset = [r for r in report["records"] if r["problem_id"] == p["problem_id"] and r["condition_id"] == c["id"]]
                lengths = [r["think_tokens"] for r in subset if r["think_tokens"] is not None]
                per_problem.append({"model": model, "problem_id": p["problem_id"], "condition": c["id"],
                                    "n": len(subset), "valid_thinking_lengths": len(lengths),
                                    "mean_think_tokens": sum(lengths)/len(lengths) if lengths else None,
                                    "mean_total_tokens": sum(r["total_tokens"] for r in subset)/len(subset) if subset else None})
    target = root / "combined" / ("summary-" + stamp() + ".json")
    publish(target, {"protocol_sha256": protocol, "models": models, "rows": rows,
                     "per_problem": per_problem, "note": "Accuracy bounds reflect unresolved answers, not confidence intervals."})
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    publish(target.with_suffix(".csv"), buffer.getvalue().encode("utf-8-sig"))
    print("COMBINED REPORT:", target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    combine(parser.parse_args().root)
