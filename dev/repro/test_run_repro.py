"""End-to-end CLI test for dev/repro/run_repro.py on the weights-free path."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYEXE = sys.executable


def main() -> int:
    # Test 1: Basic weights-free run
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

    # Test 2: --sink-dir is honored (debug JSONL appears in specified dir)
    out = HERE / "_run_repro_out"
    sink_dir = HERE / "_run_repro_sink"

    if out.exists():
        shutil.rmtree(out)
    if sink_dir.exists():
        shutil.rmtree(sink_dir)

    cmd = [
        PYEXE, str(HERE / "run_repro.py"),
        "--self-check", "--candidates", "2", "--out", str(out),
        "--sink-dir", str(sink_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)

    # Verify debug JSONL files were created in the sink directory
    debug_0 = sink_dir / "candidate_0.debug.jsonl"
    debug_1 = sink_dir / "candidate_1.debug.jsonl"
    assert debug_0.exists(), f"Expected {debug_0} to exist"
    assert debug_1.exists(), f"Expected {debug_1} to exist"

    # Clean up
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(sink_dir, ignore_errors=True)

    # Test 3: Precedence fix - explicit --sink-dir overrides AICOMP_DEBUG_SINK_PATH
    out = HERE / "_run_repro_out"
    sink_dir = HERE / "_run_repro_sink"
    decoy_dir = HERE / "_run_repro_decoy"

    if out.exists():
        shutil.rmtree(out)
    if sink_dir.exists():
        shutil.rmtree(sink_dir)
    if decoy_dir.exists():
        shutil.rmtree(decoy_dir)

    # Set up env with decoy AICOMP_DEBUG_SINK_PATH
    env = os.environ.copy()
    env["AICOMP_DEBUG_SINK_PATH"] = str(decoy_dir / "decoy.jsonl")

    cmd = [
        PYEXE, str(HERE / "run_repro.py"),
        "--self-check", "--candidates", "2", "--out", str(out),
        "--sink-dir", str(sink_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)

    # Verify sink_dir was used (not decoy)
    debug_0 = sink_dir / "candidate_0.debug.jsonl"
    assert debug_0.exists(), f"Expected {debug_0} to exist (--sink-dir not honored)"

    # Verify decoy was NOT created (no file in decoy_dir)
    assert not (decoy_dir / "decoy.jsonl").exists(), \
        f"Decoy AICOMP_DEBUG_SINK_PATH was used; --sink-dir precedence broken"

    # Clean up
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(sink_dir, ignore_errors=True)
    if decoy_dir.exists():
        shutil.rmtree(decoy_dir, ignore_errors=True)

    print("test_run_repro: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
