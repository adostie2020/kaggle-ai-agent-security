"""Run each attack candidate through the real-env tracer under the chosen model,
dumping per-candidate observability JSON (+ optional raw model debug JSONL) and an
aggregate summary to an output dir. The `resolve` seam is injected so the runner is
CPU-testable with the deterministic agent; production wires the real model.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))       # dev/repro/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # dev/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root (attack)

import oracle  # noqa: E402
import trace as tracer  # noqa: E402
import models  # noqa: E402
from debug_sink import make_jsonl_sink  # noqa: E402


def candidate_messages(n: int) -> list[list[str]]:
    """attack.py's first n returned candidates' user messages, as a list of chains."""
    import attack

    cands = attack.AttackAlgorithm(config={"n_candidates": n}).run(env=None, config=None)
    return [list(c.user_messages) for c in cands[:n]]


@dataclass
class ReproResult:
    model: str
    n_candidates: int
    per_candidate: list[dict]
    total_raw: float
    total_normalized: float
    out_dir: str


def run_repro(
    *,
    model: str,
    n_candidates: int,
    out_dir: str | Path,
    resolve: Callable[[str, Any], Callable[[], Any]] = models.resolve_agent_factory_kw,
    sink_dir: str | Path | None = None,
    guardrail_factory: Callable[[], Any] = oracle.OptimalGuardrail,
    max_tool_hops: int = oracle.MAX_TOOL_HOPS,
) -> ReproResult:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sink_root = Path(sink_dir) if sink_dir is not None else None
    if sink_root is not None:
        sink_root.mkdir(parents=True, exist_ok=True)

    chains = candidate_messages(n_candidates)
    per_candidate: list[dict] = []
    total_raw = 0.0
    total_norm = 0.0

    for i, messages in enumerate(chains):
        debug_path = None
        debug_sink = None
        if sink_root is not None:
            debug_path = sink_root / f"candidate_{i}.debug.jsonl"
            debug_sink = make_jsonl_sink(debug_path)

        factory = resolve(model, debug_sink)
        report = tracer.trace_chain(
            messages,
            agent_factory=factory,
            guardrail_factory=guardrail_factory,
            max_tool_hops=max_tool_hops,
        )
        # trace_chain labels the report `agent_factory.__name__`, which is always the
        # useless literal "<lambda>" on the production path -- build_agent_factory's
        # every branch returns a bare lambda. Relabel with the model row id on this
        # local report instance (TraceReport is a plain, non-frozen dataclass); do
        # NOT rename the factory/class itself, which would mutate SDK state process-wide.
        report.agent = model
        report_path = out / f"candidate_{i}.json"
        report_path.write_text(report.to_json(), encoding="utf-8")

        final = report.turns[-1] if report.turns else None
        raw = float(final.running_raw) if final else 0.0
        norm = float(final.running_normalized) if final else 0.0
        total_raw += raw
        total_norm += norm
        per_candidate.append(
            {
                "index": i,
                "messages": messages,
                "running_raw": raw,
                "running_normalized": norm,
                "report_path": str(report_path),
                "debug_path": str(debug_path) if debug_path else None,
            }
        )

    result = ReproResult(
        model=model,
        n_candidates=n_candidates,
        per_candidate=per_candidate,
        total_raw=total_raw,
        total_normalized=total_norm,
        out_dir=str(out),
    )
    (out / "summary.json").write_text(
        json.dumps(asdict(result), indent=2, default=str), encoding="utf-8"
    )
    return result
