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

    # Test 4: --backend hf self-check runs (backend threads through the CLI)
    out = HERE / "_run_repro_backend_out"
    if out.exists():
        shutil.rmtree(out)
    cmd = [
        PYEXE, str(HERE / "run_repro.py"),
        "--self-check", "--backend", "hf", "--candidates", "2", "--out", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["model"] == "deterministic"
    shutil.rmtree(out, ignore_errors=True)

    # Test 5: the fail-fast validation gate is backend-aware (in-process, no subprocess,
    # no weights). --backend gguf must NOT call models.validate_selection (the HF-only
    # check); --backend hf must call it exactly once. Import run_repro directly so we can
    # monkeypatch the modules it already imported at module scope.
    sys.path.insert(0, str(HERE))
    import run_repro  # noqa: E402 (path set up above, mirrors run_repro.py's own inserts)

    class _StubResult:
        def __init__(self, model):
            self.model = model
            self.n_candidates = 0
            self.total_raw = 0.0
            self.total_normalized = 0.0
            self.out_dir = str(HERE / "_gate_test_out")

    validate_calls = []

    def _spy_validate_selection(row_id):
        validate_calls.append(row_id)

    run_repro_calls = []

    def _fake_runner_run_repro(**kwargs):
        run_repro_calls.append(kwargs)
        return _StubResult(kwargs.get("model"))

    real_validate_selection = run_repro.models.validate_selection
    real_runner_run_repro = run_repro.runner.run_repro
    real_argv = sys.argv
    try:
        run_repro.models.validate_selection = _spy_validate_selection
        run_repro.runner.run_repro = _fake_runner_run_repro

        # gguf (default backend): HF gate must be skipped.
        validate_calls.clear()
        run_repro_calls.clear()
        sys.argv = [
            "run_repro.py", "--backend", "gguf", "--model", "gpt_oss",
            "--candidates", "0", "--out", str(HERE / "_gate_test_out"),
        ]
        rc = run_repro.main()
        assert rc == 0, f"gguf path: expected rc 0, got {rc}"
        assert validate_calls == [], (
            f"gguf backend must NOT call models.validate_selection; got {validate_calls}"
        )
        assert len(run_repro_calls) == 1, (
            f"expected runner.run_repro called once, got {run_repro_calls}"
        )
        assert run_repro_calls[0].get("backend") == "gguf"

        # hf (positive control): HF gate must fire exactly once with the model name.
        validate_calls.clear()
        run_repro_calls.clear()
        sys.argv = [
            "run_repro.py", "--backend", "hf", "--model", "gpt_oss",
            "--candidates", "0", "--out", str(HERE / "_gate_test_out"),
        ]
        rc = run_repro.main()
        assert rc == 0, f"hf path: expected rc 0, got {rc}"
        assert validate_calls == ["gpt_oss"], (
            f"hf backend must call models.validate_selection('gpt_oss') once; got {validate_calls}"
        )
        assert len(run_repro_calls) == 1, (
            f"expected runner.run_repro called once, got {run_repro_calls}"
        )
        assert run_repro_calls[0].get("backend") == "hf"
    finally:
        sys.argv = real_argv
        run_repro.models.validate_selection = real_validate_selection
        run_repro.runner.run_repro = real_runner_run_repro

    # Test 6: resolve_guardrail maps a NAME to a guardrail factory (the leakage-safe
    # --guardrail selector references guardrails by name only; the resolver builds the
    # factory). optimal -> oracle.OptimalGuardrail; a stochastic profile -> a factory
    # yielding a StochasticGuardrail closing over (base_seed, member); sdk_strict -> a
    # GuardrailBase; unknown -> ValueError listing valid names.
    import oracle  # noqa: E402

    assert run_repro.resolve_guardrail("optimal") is oracle.OptimalGuardrail, \
        "optimal must resolve to oracle.OptimalGuardrail"

    # guardrails is the benchmark module; run_repro puts dev/benchmark on sys.path.
    import guardrails as _G  # noqa: E402
    from aicomp_sdk.guardrails.base import GuardrailBase  # noqa: E402

    fac = run_repro.resolve_guardrail("strict_default", base_seed=0, member=2)
    g = fac()
    assert isinstance(g, _G.StochasticGuardrail), f"strict_default -> {type(g)}"
    assert g.base_seed == 0 and g.member_ix == 2, (g.base_seed, g.member_ix)

    sdk_fac = run_repro.resolve_guardrail("sdk_strict")
    assert isinstance(sdk_fac(), GuardrailBase), "sdk_strict must build a GuardrailBase"

    try:
        run_repro.resolve_guardrail("nope")
        assert False, "unknown guardrail must raise ValueError"
    except ValueError as e:
        assert "strict_default" in str(e) and "optimal" in str(e), str(e)

    # Test 7: --self-check --guardrail strict_default runs end-to-end (deterministic agent
    # under the stochastic guardrail). The deterministic agent never complies, so raw is 0
    # regardless -- this proves the guardrail wiring works without error, not the score.
    out = HERE / "_run_repro_gr_out"
    if out.exists():
        shutil.rmtree(out)
    cmd = [
        PYEXE, str(HERE / "run_repro.py"),
        "--self-check", "--guardrail", "strict_default", "--candidates", "2", "--out", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["model"] == "deterministic"
    shutil.rmtree(out, ignore_errors=True)

    print("test_run_repro: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
