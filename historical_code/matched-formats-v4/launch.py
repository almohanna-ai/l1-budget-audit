"""Linux launcher for Colab and AutoDL, using an isolated inference environment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def execute(command: list[str], logs: Path, gpu: bool, executable_path: Path | None = None) -> None:
    """Stream a child process and preserve its complete log on disk."""
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".txt")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONHASHSEED"] = "20260920"
    env["TOKENIZERS_PARALLELISM"] = "false"
    if executable_path is not None:
        env["PATH"] = str(executable_path) + os.pathsep + env.get("PATH", "")
    if not gpu:
        env["CUDA_VISIBLE_DEVICES"] = ""
    with path.open("x", encoding="utf-8") as stream:
        stream.write("COMMAND: " + json.dumps(command) + "\n")
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", env=env) as process:
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                stream.write(line)
                stream.flush()
            status = process.wait()
        stream.write(f"\nEXIT: {status}\n")
    if status:
        raise RuntimeError(f"Command failed ({status}). Preserved log: {path}")


def environment(path: Path, logs: Path) -> Path:
    """Install vLLM in a clean venv, avoiding notebook TorchAudio conflicts."""
    python = path / "bin" / "python"
    if not python.exists():
        # Colab may omit ensurepip. Its host pip can bootstrap this empty venv
        # without changing any notebook packages (pip --python, supported >=22.3).
        venv.EnvBuilder(with_pip=False, system_site_packages=False).create(path)
    has_pip = subprocess.run([str(python), "-m", "pip", "--version"], capture_output=True)
    if has_pip.returncode:
        execute([sys.executable, "-m", "pip", "--python", str(python), "install", "pip"], logs, False)
    check = subprocess.run([str(python), "-c",
                            "from importlib.metadata import version; assert version('vllm') == '0.28.0'"],
                           capture_output=True)
    if check.returncode:
        execute([str(python), "-m", "pip", "install", "vllm==0.28.0"], logs, gpu=False)
    execute([str(python), "-m", "pip", "check"], logs, gpu=False)
    return python


def main() -> None:
    """Run the full pilot with restartable stages, durable backups, and CPU review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["small", "large"], required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--venv", type=Path, default=Path.home() / ".venvs" / "l1-probe-vllm028")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--cpu-only", action="store_true", help="Analyze/export existing batches without a GPU")
    args = parser.parse_args()
    if not (3, 10) <= sys.version_info[:2] <= (3, 13):
        raise RuntimeError("Use Python 3.10-3.13; recommended AutoDL image: Python 3.11")
    run = args.run.resolve()
    logs = run / "logs"
    backup = ["--backup-dir", str(args.backup_dir.resolve())] if args.backup_dir else []
    if backup and not (run / "plan.json").exists():
        execute([sys.executable, str(ROOT / "probe.py"), "restore", "--run", str(run), *backup], logs, False)
    if args.cpu_only:
        execute([sys.executable, str(ROOT / "probe.py"), "analyze", "--run", str(run)], logs, False)
        execute([sys.executable, str(ROOT / "probe.py"), "export", "--run", str(run), *backup], logs, False)
        return
    if shutil.which("nvidia-smi") is None:
        raise RuntimeError("No NVIDIA runtime. In Colab select Runtime > Change runtime type > GPU")
    execute(["nvidia-smi"], logs, gpu=True)
    python = environment(args.venv.resolve(), logs)
    bin_dir = python.parent
    execute([str(python), str(ROOT / "probe.py"), "prepare", "--model", args.model,
             "--run", str(run)], logs, gpu=False, executable_path=bin_dir)
    try:
        execute([str(python), str(ROOT / "probe.py"), "collect", "--run", str(run), *backup],
                logs, True, executable_path=bin_dir)
    finally:
        # Export partial batches and failure logs, too. A hard runtime termination
        # may bypass finally; per-batch backups protect the last committed batch.
        execute([sys.executable, str(ROOT / "probe.py"), "export", "--run", str(run), *backup], logs, False)
    execute([sys.executable, str(ROOT / "probe.py"), "analyze", "--run", str(run)], logs, False)
    execute([sys.executable, str(ROOT / "probe.py"), "export", "--run", str(run), *backup], logs, False)


if __name__ == "__main__":
    main()
