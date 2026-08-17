"""Cross-check dev/trace.py against dev/oracle.py on a firing compliant chain.

Two independent code paths must agree: trace.py's per-turn score accumulation and
oracle.py's whole-corpus scoring, both driving the mock-compliant agent.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))         # dev/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root (attack)

import attack  # noqa: E402
import oracle  # noqa: E402
import trace as tracer  # noqa: E402  (dev/trace.py; shadows stdlib trace in-process, harmless)
from agents import MockCompliantAgent  # noqa: E402


def main() -> int:
    chain = [attack._msg(0)]  # a real firing single-post candidate message

    report = tracer.trace_chain(chain, agent_factory=MockCompliantAgent)
    final = report.turns[-1]

    # 1) the tracer shows the compliant agent firing a severity-5 (EXFILTRATION) predicate
    assert any(int(p["severity"]) == 5 for p in final.predicates), final.predicates

    # 2) per-turn accumulation agrees with oracle's whole-corpus scoring (same agent)
    oc = oracle.score_corpus([chain], agent_factory=MockCompliantAgent)
    assert final.running_raw == oc["raw"], (final.running_raw, oc["raw"])
    assert abs(final.running_normalized - oc["normalized"]) < 1e-9, (
        final.running_normalized, oc["normalized"])

    # 3) the successful post reads as an ALLOW in the guardrail view
    posts = [e for t in report.turns for e in t.new_tool_events if e["name"] == "http.post"]
    assert posts and posts[-1]["guardrail_status"] == "ALLOW", posts

    print("test_trace: PASS  raw=%s norm=%.3f preds=%s" % (
        final.running_raw, final.running_normalized,
        [(p["predicate"], p["severity"]) for p in final.predicates]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
