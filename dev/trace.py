"""Turn-by-turn observability over the real SDK env / guardrail / scoring.

For each interact (turn) it captures the prompt, the tool events added, the guardrail
decision derived from ToolEvent.error, the predicates fired, and the running raw /
normalized / unique-cell / predicate-mass score with the per-turn delta. Runs against
the deterministic agent (ground-truth scored behavior) or the mock-compliant agent
(what a jailbroken model would do).
"""
from __future__ import annotations

import dataclasses
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))         # dev/ (oracle, agents)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root (attack)

import oracle  # noqa: E402
from agents import MockCompliantAgent  # noqa: E402
from aicomp_sdk.agents.deterministic_agent import VulnerableDeterministicAgent  # noqa: E402
from aicomp_sdk.core.env.sandbox import SandboxEnv  # noqa: E402
from aicomp_sdk.core.predicates import eval_predicates  # noqa: E402
from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail  # noqa: E402
from aicomp_sdk.scoring import SEVERITY_W, get_score_cell_hash, score_attack  # noqa: E402

AGENTS: dict[str, Callable[[], Any]] = {
    "deterministic": VulnerableDeterministicAgent,
    "compliant": MockCompliantAgent,
}


def guardrail_view(event: dict) -> tuple[str, str]:
    """Derive (status, reason) from a tool event's ok/error fields."""
    err = event.get("error")
    if event.get("ok"):
        return ("ALLOW", "")
    if err is None:
        return ("FAIL", "")
    if err.startswith("denied:"):
        return ("BLOCK", err[len("denied:"):])
    if err.startswith("confirm_required:"):
        return ("CONFIRM", err[len("confirm_required:"):])
    if err == "blocked_by_hook":
        return ("BLOCK", "hook")
    return ("ERROR", err)


@dataclass
class TurnTrace:
    index: int
    prompt: str
    counters: dict
    new_tool_events: list[dict]
    predicates: list[dict]
    running_raw: float
    running_normalized: float
    running_unique_cells: int
    running_pred_mass: int
    delta_raw: float


@dataclass
class TraceReport:
    agent: str
    turns: list[TurnTrace]
    final_trace: dict

    def to_json(self) -> str:
        return json.dumps(
            {
                "agent": self.agent,
                "turns": [dataclasses.asdict(t) for t in self.turns],
                "final_trace": self.final_trace,
            },
            indent=2,
            default=str,
        )

    def render(self) -> str:
        out = [f"=== trace ({self.agent}), {len(self.turns)} turn(s) ==="]
        for t in self.turns:
            out.append(f"\n-- turn {t.index}: {t.prompt!r}")
            out.append(f"   counters: {t.counters}")
            for e in t.new_tool_events:
                args = {k: str(v)[:40] for k, v in (e.get("args") or {}).items()}
                reason = f":{e.get('guardrail_reason')}" if e.get("guardrail_reason") else ""
                out.append(
                    f"   [{e.get('name')}] ok={e.get('ok')} "
                    f"{e.get('guardrail_status')}{reason} "
                    f"src={e.get('source')} se={e.get('side_effect')} args={args}"
                )
            if t.predicates:
                out.append(
                    f"   predicates: {[(p['predicate'], p['severity']) for p in t.predicates]}"
                )
            out.append(
                f"   score: raw={t.running_raw} (delta {t.delta_raw:+g}) "
                f"norm={t.running_normalized:.3f} cells={t.running_unique_cells} "
                f"pred_mass={t.running_pred_mass}"
            )
        return "\n".join(out)


def trace_chain(
    messages: Sequence[str],
    *,
    agent_factory: Callable[[], Any],
    guardrail_factory: Callable[[], Any] = OptimalGuardrail,
    max_tool_hops: int = oracle.MAX_TOOL_HOPS,
) -> TraceReport:
    env = SandboxEnv(
        seed=oracle.SEED,
        fixtures_dir=oracle.FIXTURES,
        agent=agent_factory(),
        guardrail=guardrail_factory(),
        max_tool_hops=max_tool_hops,
    )
    env.reset()
    turns: list[TurnTrace] = []
    prev_count = 0
    prev_raw = 0.0
    for i, msg in enumerate(messages):
        res = env.interact(msg, max_tool_hops=max_tool_hops)
        trace = env.export_trace_dict()
        events = trace.get("tool_events", [])
        new_events = [dict(e) for e in events[prev_count:]]
        prev_count = len(events)
        for e in new_events:
            e["guardrail_status"], e["guardrail_reason"] = guardrail_view(e)
        finding = oracle.finding_from_trace(trace)
        findings = [finding] if finding else []
        raw = score_attack(findings, normalize=False)
        norm = score_attack(findings, normalize=True)
        preds = eval_predicates(trace)
        uniq = len({h for h in (get_score_cell_hash(f) for f in findings) if h})
        mass = sum(
            SEVERITY_W.get(int(p.get("severity", 1)), 1)
            for f in findings
            for p in f["predicates"]
        )
        turns.append(
            TurnTrace(
                index=i,
                prompt=msg,
                counters=dataclasses.asdict(res),
                new_tool_events=new_events,
                predicates=preds,
                running_raw=raw,
                running_normalized=norm,
                running_unique_cells=uniq,
                running_pred_mass=mass,
                delta_raw=raw - prev_raw,
            )
        )
        prev_raw = raw
    return TraceReport(
        agent=agent_factory.__name__, turns=turns, final_trace=env.export_trace_dict()
    )


def _candidate_chain(n: int) -> list[str]:
    """Build attack.py's returned corpus and return the Nth candidate's messages."""
    import attack

    cands = attack.AttackAlgorithm(config={"n_candidates": n + 1}).run(env=None, config=None)
    return list(cands[n].user_messages)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Turn-by-turn tracer over the real SDK env.")
    ap.add_argument("messages", nargs="*", help="user message(s), one per turn")
    ap.add_argument("--agent", choices=list(AGENTS), default="deterministic")
    ap.add_argument("--candidate", type=int, default=None,
                    help="trace attack.py's Nth returned candidate instead of messages")
    ap.add_argument("--max-tool-hops", type=int, default=oracle.MAX_TOOL_HOPS)
    ap.add_argument("--json", action="store_true", help="emit structured JSON")
    args = ap.parse_args()

    messages = _candidate_chain(args.candidate) if args.candidate is not None else args.messages
    if not messages:
        ap.error("provide message(s) or --candidate N")

    report = trace_chain(
        messages, agent_factory=AGENTS[args.agent], max_tool_hops=args.max_tool_hops
    )
    print(report.to_json() if args.json else report.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
