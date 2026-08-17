"""Cross-check dev/repro/runner.py against oracle on the deterministic agent.

Runs the runner with an injected CPU agent factory (no weights), then asserts the
per-candidate JSON + summary are written and that totals equal oracle.score_corpus
for the same chains and agent.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))       # dev/repro/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # dev/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root (attack)

import oracle  # noqa: E402
import runner  # noqa: E402
from aicomp_sdk.agents.deterministic_agent import VulnerableDeterministicAgent  # noqa: E402


def _det_resolve(model, debug_sink=None):
    # Ignore `model`; always the CPU deterministic agent (weights-free).
    return VulnerableDeterministicAgent


def main() -> int:
    out = Path(oracle.FIXTURES).parent / "_repro_runner_out"
    if out.exists():
        shutil.rmtree(out)
    n = 2
    result = runner.run_repro(
        model="deterministic", n_candidates=n, out_dir=out, resolve=_det_resolve
    )

    # 1: files written
    assert (out / "summary.json").exists(), "summary.json missing"
    for i in range(n):
        assert (out / f"candidate_{i}.json").exists(), f"candidate_{i}.json missing"
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["model"] == "deterministic"
    assert summary["n_candidates"] == n
    assert len(summary["per_candidate"]) == n

    # 2: totals equal oracle's whole-corpus score for the same chains + agent
    chains = runner.candidate_messages(n)
    oc = oracle.score_corpus(chains, agent_factory=VulnerableDeterministicAgent)
    assert result.total_raw == oc["raw"], (result.total_raw, oc["raw"])
    assert abs(result.total_normalized - oc["normalized"]) < 1e-9, (
        result.total_normalized, oc["normalized"])

    print("test_runner: PASS  total_raw=%s norm=%.3f" % (
        result.total_raw, result.total_normalized))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
