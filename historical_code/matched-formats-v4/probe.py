"""Restartable L1 format-calibration probe; analysis uses only the CPU.

Run ``prepare``, ``collect``, then ``analyze`` in separate processes. Raw token
IDs are authoritative. Automated style measures are proxies, not verdicts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parent
MODELS = {
    "small": ("l3lab/L1-Qwen-1.5B-Exact", "b1fa57f192f0b14bd033d0085faaa80cdc39694b"),
    "large": ("l3lab/L1-Qwen-7B-Exact", "faddca9"),
}
BACKEND = "0.28.0"


def read(path: Path) -> Any:
    """Load a UTF-8 JSON artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def encode(value: Any) -> bytes:
    """Return the canonical JSON encoding used for content hashes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data: bytes) -> str:
    """Hash bytes using SHA-256."""
    return hashlib.sha256(data).hexdigest()


def stamp() -> str:
    """Return a UTC timestamp suitable for immutable artifact names."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def publish(path: Path, value: Any) -> None:
    """Atomically publish locally; never replace differing existing content."""
    data = value if isinstance(value, bytes) else encode(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Immutable artifact differs: {path}")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()


def backup(run: Path, destination: Path | None) -> Path:
    """Commit a ZIP and SHA receipt; receipts appear only after verified copying.

    Backup folders must be outside the run folder. No archive is overwritten.
    A receipt certifies file integrity, not that GPU inference is complete.
    """
    target = destination or run.parent / "exports"
    if target.resolve().is_relative_to(run.resolve()):
        raise ValueError("Backup destination must be outside the run folder")
    target.mkdir(parents=True, exist_ok=True)
    name = run.name + "-" + stamp()
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / (name + ".zip")
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(run.rglob("*")):
                if path.is_file() and not path.name.startswith("tmp"):
                    bundle.write(path, Path(run.name) / path.relative_to(run))
        payload = archive.read_bytes()
    output = target / archive.name
    with output.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if sha(output.read_bytes()) != sha(payload):
        raise OSError("Backup hash verification failed")
    receipt = {"archive": output.name, "sha256": sha(payload), "bytes": len(payload)}
    with (target / (name + ".ready.json")).open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream)
    print("BACKUP VERIFIED:", output, flush=True)
    return output


def load_spec() -> dict[str, Any]:
    """Validate the matched five-format calibration protocol."""
    spec = read(ROOT / "experiment.json")
    if (len(spec["problems"]) != 5 or len(spec["conditions"]) != 5
            or len({p["problem_id"] for p in spec["problems"]}) != 5 or spec["samples"] != 4):
        raise ValueError("Expected five unique questions, five conditions, four samples")
    expected = {"cot-8shot-v2", "concise-8shot-v2", "cod-8shot-v2",
                "sot-8shot-v2", "symbolic-8shot-v2"}
    if {c["id"] for c in spec["conditions"]} != expected:
        raise ValueError("Condition set differs from the five-format protocol")
    if any(c["group"] != "format" or c["budget"] is not None or not c["demo_style"]
           for c in spec["conditions"]):
        raise ValueError("Every calibration condition must be an eight-shot format arm")
    demos = spec["demonstrations"]
    if len(demos) != 8 or len({d["question"] for d in demos}) != 8:
        raise ValueError("Eight unique matched examples are required")
    if {d["question"] for d in demos} & {p["question"] for p in spec["problems"]}:
        raise ValueError("Demonstrations must not include evaluation questions")
    for demo in demos:
        if set(demo["reasoning"]) != {"cot", "concise", "cod", "sot", "symbolic"}:
            raise ValueError("Each example needs all five matched renderings")
    return spec


def restore(run: Path, destination: Path) -> None:
    """Recover the latest hash-verified matching backup without unsafe ZIP extraction."""
    if (run / "plan.json").exists():
        return
    for receipt_path in sorted(destination.glob(run.name + "-*.ready.json"), reverse=True):
        receipt = read(receipt_path)
        if Path(receipt["archive"]).name != receipt["archive"]:
            raise ValueError("Unsafe archive name in backup receipt")
        archive = destination / receipt["archive"]
        data = archive.read_bytes()
        if sha(data) != receipt["sha256"] or len(data) != receipt["bytes"]:
            raise ValueError(f"Backup checksum mismatch: {archive}")
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            prefix = run.name + "/"
            if prefix + "plan.json" not in names:
                continue  # A backup made before preparation contains only logs.
            plan = json.loads(bundle.read(prefix + "plan.json"))
            if plan["spec"] != load_spec():
                raise ValueError("Backup protocol differs from this pilot")
            if bundle.testzip() is not None:
                raise ValueError("Backup ZIP CRC verification failed")
            for name in names:
                if not name.startswith(prefix) or "\\" in name:
                    raise ValueError("Unsafe ZIP member")
                relative = Path(name[len(prefix):])
                target = run / relative
                if relative.is_absolute() or ".." in relative.parts or not target.resolve().is_relative_to(run.resolve()):
                    raise ValueError("Unsafe ZIP path")
            for name in names:
                if not name.endswith("/"):
                    publish(run / name[len(prefix):], bundle.read(name))
        validate_batches(run, plan)
        print("RESTORED VERIFIED BACKUP:", archive, flush=True)
        return
    print("No earlier prepared backup; starting a new run", flush=True)


def prompt(spec: dict[str, Any], problem: dict[str, Any], condition: dict[str, Any]) -> str:
    """Compose one user message with condition-specific matched demonstrations.

    All demonstration variants share questions, order and final answers. Target
    reference answers never enter this function's rendered prompt.
    """
    style = condition["demo_style"]
    examples = ""
    if style is not None:
        parts = [f"Example {i+1}\nProblem:\n{d['question']}\nSolution:\n"
                 f"{d['reasoning'][style]}\nAnswer: {d['answer']}"
                 for i, d in enumerate(spec["demonstrations"])]
        examples = "\n\nWorked examples:\n" + "\n\n".join(parts)
    return ("Solve the following mathematics problem.\n" + condition["instruction"]
            + "\nPut only the final answer on the last line, prefixed by 'Answer:'."
            + examples + "\n\nNow solve this problem only:\n" + problem["question"])


def seed_for(problem_id: str, condition_id: str, sample: int) -> int:
    """Derive request seeds independently of model, host, and run order."""
    return int(sha(encode([20260920, problem_id, condition_id, sample]))[:8], 16) % (2**31)


def prepare(run: Path, model_key: str) -> None:
    """Resolve immutable model revisions and freeze prompts on CPU only."""
    from huggingface_hub import HfApi
    from transformers import AutoTokenizer

    spec = load_spec()
    plan_path = run / "plan.json"
    if plan_path.exists():
        plan = read(plan_path)
        if plan["spec"] != spec or plan["model_key"] != model_key:
            raise ValueError("Existing plan differs; choose a new run directory")
        if plan["code_sha256"] != sha(Path(__file__).read_bytes()):
            raise ValueError("Collector code changed; choose a new run directory")
        validate_batches(run, plan)
        print("Existing plan verified; no preparation repeated", flush=True)
        return
    model_id, requested_revision = MODELS[model_key]
    revision = HfApi().model_info(model_id, revision=requested_revision).sha
    if not revision or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Model revision did not resolve to a complete commit SHA")
    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision, trust_remote_code=False)
    jobs = []
    for problem in spec["problems"]:
        for condition in spec["conditions"]:
            user = prompt(spec, problem, condition)
            rendered = tokenizer.apply_chat_template(
                [{"role": "user", "content": user}], tokenize=False, add_generation_prompt=True)
            ids = tokenizer.encode(rendered, add_special_tokens=False)
            if len(ids) + spec["max_new_tokens"] > spec["max_model_len"]:
                raise ValueError("Prompt plus output cap exceeds context; no silent truncation")
            for sample in range(spec["samples"]):
                jobs.append({"record_id": f"{len(jobs):03d}", "problem_id": problem["problem_id"],
                             "condition_id": condition["id"], "sample_index": sample,
                             "requested_budget": condition["budget"], "condition_group": condition["group"],
                             "shots": len(spec["demonstrations"]) if condition["demo_style"] else 0,
                             "generation_seed": seed_for(problem["problem_id"], condition["id"], sample),
                             "user_prompt": user, "rendered_prompt": rendered,
                             "prompt_sha256": sha(rendered.encode()), "prompt_token_ids": ids})
    plan = {"schema_version": "1.0", "experiment_id": spec["experiment_id"],
            "protocol_sha256": sha(encode(spec)), "spec": spec,
            "model_key": model_key, "model_id": model_id, "model_revision": revision,
            "requested_revision": requested_revision, "backend_version": BACKEND,
            "code_sha256": sha(Path(__file__).read_bytes()),
            "chat_template": tokenizer.chat_template, "eos_token_id": tokenizer.eos_token_id,
            "think_open_ids": tokenizer.encode("<think>", add_special_tokens=False),
            "think_close_ids": tokenizer.encode("</think>", add_special_tokens=False),
            "jobs": jobs}
    publish(plan_path, plan)
    publish(run / "source" / "probe.py", Path(__file__).read_bytes())
    publish(run / "source" / "grading.py", (ROOT / "grading.py").read_bytes())
    publish(run / "source" / "experiment.json", (ROOT / "experiment.json").read_bytes())
    print(f"Prepared {len(jobs)} requests for {model_id}@{revision}", flush=True)


def validate_batches(run: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Reject foreign, duplicated, incomplete, or corrupted checkpoint batches."""
    rows = []
    expected = {j["record_id"]: j for j in plan["jobs"]}
    seen: set[str] = set()
    for path in sorted((run / "raw").glob("batch-*.json")):
        envelope = read(path)
        batch = envelope["payload"]
        if sha(encode(batch)) != envelope["sha256"] or batch["plan_sha256"] != sha(encode(plan)):
            raise ValueError(f"Batch integrity/lineage mismatch: {path}")
        index = int(path.stem.split("-")[1])
        wanted = plan["jobs"][index * 4:(index + 1) * 4]
        if [r["record_id"] for r in batch["records"]] != [j["record_id"] for j in wanted] or len(wanted) != 4:
            raise ValueError(f"Batch membership mismatch: {path}")
        for row in batch["records"]:
            key = row["record_id"]
            if key in seen or any(row[k] != v for k, v in expected[key].items()):
                raise ValueError(f"Duplicate or changed record: {key}")
            if row["total_tokens"] != len(row["output_token_ids"]):
                raise ValueError(f"Token count mismatch: {key}")
            seen.add(key)
            rows.append(row)
    return rows


def collect(run: Path, backup_dir: Path | None) -> None:
    """Generate fixed batches of four; resume only within the same runtime identity."""
    plan = read(run / "plan.json")
    if plan["code_sha256"] != sha(Path(__file__).read_bytes()):
        raise ValueError("Code differs from the prepared run")
    completed = validate_batches(run, plan)
    if len(completed) == len(plan["jobs"]):
        print(f"All {len(plan['jobs'])} records already complete; GPU not loaded", flush=True)
        return
    if metadata.version("vllm") != BACKEND:
        raise RuntimeError(f"Required vllm=={BACKEND}; use the supplied isolated launcher")
    os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    import torch
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Select a GPU runtime; exactly one CUDA GPU must be visible")
    runtime = {"python_version": platform.python_version(), "platform": platform.platform(),
               "hostname": platform.node(), "torch_version": torch.__version__,
               "cuda_version": torch.version.cuda, "gpu_name": torch.cuda.get_device_name(0),
               "gpu_memory_bytes": torch.cuda.get_device_properties(0).total_memory,
               "driver": subprocess.check_output(
                   ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], text=True).strip(),
               "packages": sorted((d.metadata["Name"], d.version) for d in metadata.distributions()
                                  if d.metadata["Name"])}
    # Hostname/platform are descriptive; numerically relevant fields guard resume.
    numerical = {k: v for k, v in runtime.items() if k not in {"hostname", "platform"}}
    publish(run / "runtime-identity.json", numerical)
    publish(run / "runtime" / (stamp() + ".json"), runtime)
    backup(run, backup_dir)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)
    from vllm import LLM, SamplingParams
    spec = plan["spec"]
    llm = LLM(model=plan["model_id"], revision=plan["model_revision"],
              tokenizer=plan["model_id"], tokenizer_revision=plan["model_revision"],
              trust_remote_code=False, dtype="float16", tensor_parallel_size=1,
              max_model_len=spec["max_model_len"], max_num_seqs=4, max_num_batched_tokens=8192,
              gpu_memory_utilization=0.90, enforce_eager=True,
              enable_prefix_caching=False, enable_chunked_prefill=False,
              seed=20260920, generation_config="vllm")
    done = len(completed)
    for offset in range(0, len(plan["jobs"]), 4):
        path = run / "raw" / f"batch-{offset // 4:03d}.json"
        if path.exists():
            continue
        jobs = plan["jobs"][offset:offset + 4]
        params = [SamplingParams(n=1, temperature=0.6, top_p=0.95, top_k=-1,
                                 max_tokens=spec["max_new_tokens"], seed=j["generation_seed"],
                                 stop=[], stop_token_ids=[], ignore_eos=False,
                                 skip_special_tokens=False, spaces_between_special_tokens=False,
                                 repetition_penalty=1.0, presence_penalty=0.0, frequency_penalty=0.0)
                  for j in jobs]
        outputs = llm.generate([{"prompt_token_ids": j["prompt_token_ids"]} for j in jobs],
                               sampling_params=params, use_tqdm=False)
        if len(outputs) != 4:
            raise RuntimeError("Backend returned an unexpected batch size")
        records = []
        for job, output in zip(jobs, outputs):
            if not output.finished or len(output.outputs) != 1 or list(output.prompt_token_ids) != job["prompt_token_ids"]:
                raise RuntimeError("Backend output/prompt mismatch")
            result = output.outputs[0]
            ids = list(result.token_ids)
            records.append({**job, "run_id": run.name, "model_id": plan["model_id"],
                            "model_revision": plan["model_revision"],
                            "output_token_ids": ids, "full_output": result.text,
                            "total_tokens": len(ids), "finish_reason": result.finish_reason,
                            "stop_reason": result.stop_reason, "hit_cap": result.finish_reason == "length",
                            "created_at": stamp()})
        payload = {"plan_sha256": sha(encode(plan)), "records": records}
        publish(path, {"sha256": sha(encode(payload)), "payload": payload})
        done += 4
        print(f"Saved {done}/{len(plan['jobs'])} | {jobs[0]['problem_id']} | {jobs[0]['condition_id']}", flush=True)
        backup(run, backup_dir)
    publish(run / "collection-complete.json", {"records": len(validate_batches(run, plan)),
                                              "plan_sha256": sha(encode(plan))})


def positions(ids: list[int], pattern: list[int]) -> list[int]:
    """Find every occurrence of an original-token delimiter sequence."""
    if not pattern:
        raise ValueError("Empty token delimiter")
    return [i for i in range(len(ids) - len(pattern) + 1) if ids[i:i + len(pattern)] == pattern]


def regions(row: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Separate a unique closed trace; ambiguous boundaries remain unresolved."""
    ids, text = row["output_token_ids"], row["full_output"]
    starts = positions(ids, plan["think_open_ids"])
    ends = positions(ids, plan["think_close_ids"])
    if len(ends) != 1 or len(starts) > 1 or (starts and starts[0] >= ends[0]):
        return {"boundary_status": "missing_or_ambiguous", "think_tokens": None,
                "thinking_text": None, "final_text": None}
    if text.count("</think>") != 1 or text.count("<think>") != len(starts):
        return {"boundary_status": "text_id_disagreement", "think_tokens": None,
                "thinking_text": None, "final_text": None}
    before, after = text.split("</think>")
    start = starts[0] + len(plan["think_open_ids"]) if starts else 0
    return {"boundary_status": "explicit_open" if starts else "implicit_open_before_unique_close",
            "think_tokens": ends[0] - start,
            "thinking_text": before.split("<think>")[-1], "final_text": after}


def style_proxies(text: str | None) -> dict[str, Any]:
    """Measure line brevity and alphabetic runs; never label these as compliance.

    Whitespace-delimited units approximate words and count mathematics imperfectly.
    Lines approximate steps; an alphabetic run may be prose or a math identifier.
    Empty traces have undefined, not perfect, compliance measures.
    """
    if text is None:
        return {"nonempty_lines": None, "short_line_fraction": None, "alphabetic_runs": None}
    lines = [re.sub(r"^\s*(?:\d+[.)]|[-*])\s*", "", x).strip()
             for x in text.splitlines() if x.strip()]
    return {"nonempty_lines": len(lines),
            "short_line_fraction": sum(len(x.split()) <= 5 for x in lines) / len(lines) if lines else None,
            "alphabetic_runs": len(re.findall(r"[A-Za-z]{2,}", re.sub(r"\\[A-Za-z]+", "", text)))}


def analyze(run: Path) -> Path:
    """Write immutable CPU summaries and a complete escaped HTML review sheet."""
    plan = read(run / "plan.json")
    from grading import grade
    rows = validate_batches(run, plan)
    if not rows:
        raise ValueError("No complete raw batches available yet")
    evaluated = []
    lookup = {p["problem_id"]: p for p in plan["spec"]["problems"]}
    for row in rows:
        split = regions(row, plan)
        score = grade(row["full_output"], split["final_text"],
                      lookup[row["problem_id"]]["reference_answers"], row["hit_cap"])
        evaluated.append({**row, **split, "grading": score, "thinking_style_proxies": style_proxies(split["thinking_text"]),
                          "final_style_proxies": style_proxies(split["final_text"]),
                          "reference_answers": lookup[row["problem_id"]]["reference_answers"],
                          "manual_review": {"reasoning_compliance": None, "answer_correct": None,
                                            "notes": None}})
    summary = []
    for condition in plan["spec"]["conditions"]:
        selected = [r for r in evaluated if r["condition_id"] == condition["id"]]
        lengths = [r["think_tokens"] for r in selected if r["think_tokens"] is not None]
        total = [r["total_tokens"] for r in selected]
        outcomes = Counter(r["grading"]["status"] for r in selected)
        n = len(selected)
        budget = condition["budget"]
        error = [abs(x - budget) for x in lengths] if budget is not None else []
        ordered = sorted(lengths)
        def percentile(q: float) -> float | None:
            """Compute a linearly interpolated percentile over valid trace lengths."""
            if not ordered:
                return None
            position = (len(ordered)-1) * q
            low = int(position)
            high = min(low+1, len(ordered)-1)
            return ordered[low] + (ordered[high]-ordered[low]) * (position-low)
        summary.append({"condition": condition["id"], "condition_group": condition["group"],
                        "requested_budget": budget, "collected": n, "expected": 20,
                        "mean_total_tokens": statistics.mean(total) if total else None,
                        "median_total_tokens": statistics.median(total) if total else None,
                        "median_think_tokens": statistics.median(lengths) if lengths else None,
                        "mean_think_tokens": statistics.mean(lengths) if lengths else None,
                        "think_p10": percentile(.10), "think_p90": percentile(.90),
                        "mean_abs_budget_error": statistics.mean(error) if error else None,
                        "mean_signed_budget_error": statistics.mean(x-budget for x in lengths) if lengths and budget else None,
                        "correct": outcomes["correct"], "incorrect": outcomes["incorrect"],
                        "unresolved": outcomes["unresolved"],
                        "accuracy_pct": 100*outcomes["correct"]/n if n and not outcomes["unresolved"] else None,
                        "lower_bound_pct": 100*outcomes["correct"]/n if n else None,
                        "upper_bound_pct": 100*(outcomes["correct"]+outcomes["unresolved"])/n if n else None,
                        "valid_thinking_boundaries": len(lengths),
                        "hit_cap": sum(r["hit_cap"] for r in selected)})
    report = {"schema_version": "1.0", "plan_sha256": sha(encode(plan)),
              "measures_accuracy": True, "grading_policy": "conservative-literals-v1",
              "grading_code_sha256": sha((ROOT / "grading.py").read_bytes()),
              "automatic_compliance_verdict": False,
              "expected_records": len(plan["spec"]["problems"]) * len(plan["spec"]["conditions"]) * plan["spec"]["samples"],
              "complete": len(rows) == len(plan["spec"]["problems"]) * len(plan["spec"]["conditions"]) * plan["spec"]["samples"],
              "summary": summary, "records": evaluated}
    path = run / "reports" / ("report-" + stamp() + ".json")
    publish(path, report)
    sections = []
    for r in evaluated:
        sections.append("<article><h2>" + html.escape(f"{r['record_id']} | {r['condition_id']} | {r['problem_id']}")
                        + "</h2><p>Reference: " + html.escape(str(r["reference_answers"]))
                        + "</p><p>Boundary: " + html.escape(r["boundary_status"])
                        + f" | total={r['total_tokens']} | thinking={r['think_tokens']} | cap={r['hit_cap']}</p>"
                        + "<h3>Question</h3><pre>" + html.escape(lookup[r["problem_id"]]["question"])
                        + "</pre><h3>Full original output</h3><pre>" + html.escape(r["full_output"])
                        + "</pre></article>")
    document = ("<!doctype html><html lang='en'><meta charset='utf-8'><title>L1 review</title>"
                "<style>body{max-width:1050px;margin:30px auto;font:16px sans-serif}"
                "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:16px}"
                "article{border-top:2px solid #ddd;margin:35px 0}</style><h1>L1 compliance pilot</h1>"
                "<p>Manual review required. Short-line and prose counts are proxies, not compliance verdicts. "
                "Accuracy uses conservative literal grading; unsupported cases stay unresolved. Bounds are not confidence intervals. "
                "All records, including capped outputs, are retained.</p><pre>"
                + html.escape(json.dumps(summary, indent=2)) + "</pre>" + "".join(sections) + "</html>")
    publish(path.with_suffix(".html"), document.encode())
    print(json.dumps(summary, indent=2), flush=True)
    print("REVIEW:", path.with_suffix(".html"), flush=True)
    return path


def main() -> None:
    """Dispatch independent preparation, inference, analysis, and export stages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "collect", "analyze", "export", "restore"])
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--model", choices=MODELS, default="small")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.run, args.model)
    elif args.stage == "collect":
        collect(args.run, args.backup_dir)
    elif args.stage == "analyze":
        analyze(args.run)
    elif args.stage == "restore":
        if args.backup_dir is None:
            parser.error("restore requires --backup-dir")
        restore(args.run, args.backup_dir)
    else:
        backup(args.run, args.backup_dir)


if __name__ == "__main__":
    main()
