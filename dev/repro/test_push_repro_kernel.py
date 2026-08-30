"""Offline dry-run smoke for dev/push_repro_kernel.py --guardrail wiring.

`--dry-run` builds the notebook and returns BEFORE any Kaggle token read or POST, so this
needs no network or credentials. It proves the guardrail flags parse and thread into the
build. Run: python dev/repro/test_push_repro_kernel.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PUSH = Path(__file__).resolve().parents[1] / "push_repro_kernel.py"  # dev/push_repro_kernel.py
PYEXE = sys.executable


def main() -> int:
    # A stochastic --guardrail must parse and be reported (threaded into the build).
    cmd = [
        PYEXE, str(PUSH), "--model", "gpt_oss", "--backend", "gguf", "--gpu",
        "--guardrail", "strict_default", "--base-seed", "0", "--member", "1",
        "--candidates", "2", "--dry-run",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    assert "guardrail=strict_default" in proc.stdout, proc.stdout
    assert "dry run" in proc.stdout, proc.stdout

    # The default (no --guardrail) path still works and reports optimal.
    cmd2 = [PYEXE, str(PUSH), "--model", "deterministic", "--candidates", "2", "--dry-run"]
    proc2 = subprocess.run(cmd2, capture_output=True, text=True)
    assert proc2.returncode == 0, (proc2.returncode, proc2.stdout, proc2.stderr)
    assert "guardrail=optimal" in proc2.stdout, proc2.stdout

    print("test_push_repro_kernel: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
