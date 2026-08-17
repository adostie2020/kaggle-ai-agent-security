"""End-to-end CLI test for dev/repro/run_repro.py on the weights-free path."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYEXE = sys.executable


def main() -> int:
    out = HERE / "_run_repro_out"
    # Clear any stale output dir before launching (R7)
    if out.exists():
        shutil.rmtree(out)

    cmd = [
        PYEXE, str(HERE / "run_repro.py"),
        "--self-check", "--candidates", "2", "--out", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["model"] == "deterministic"
    assert summary["n_candidates"] == 2

    # Clean up after successful test (R7)
    shutil.rmtree(out, ignore_errors=True)

    print("test_run_repro: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
