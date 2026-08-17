"""Validate attack.py end-to-end with a mock *compliant* agent.

The deterministic agent never complies with natural-language post instructions,
so it can't tell us whether our probe's LOGIC is sound. This mock agent does what
a jailbroken gpt_oss/gemma would: given a user message naming a URL, it issues one
http.post(url, data="SECRET_MARKER"). Scoring our real attack.py candidates through
(mock agent + OptimalGuardrail) with the exact scoring functions proves the whole
pipeline: attack -> compliant model -> guardrail ALLOW -> EXFILTRATION -> score.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Sequence

import aicomp_sdk
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail
from aicomp_sdk.core.predicates import eval_predicates
from aicomp_sdk.core.cells import cell_signature
from aicomp_sdk.scoring import score_attack, get_score_cell_hash, SEVERITY_W

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import attack as attack_mod  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))  # dev/ for shared agents
from agents import MockCompliantAgent  # noqa: E402

FIXTURES = Path(aicomp_sdk.__file__).parent / "fixtures"
URL_RE = re.compile(r'https?://[^\s\'"<>]+')


def score(candidates, agent_factory, compliance: float = 1.0, max_tool_hops: int = 8):
    findings: list[dict[str, Any]] = []
    import random

    rng = random.Random(0)
    for cand in candidates:
        msgs: Sequence[str] = cand.user_messages
        # Simulate partial model compliance by skipping some candidates entirely.
        if rng.random() > compliance:
            continue
        env = SandboxEnv(
            seed=123, fixtures_dir=FIXTURES, agent=agent_factory(),
            guardrail=OptimalGuardrail(), max_tool_hops=max_tool_hops,
        )
        env.reset()
        for m in msgs:
            env.interact(m, max_tool_hops=max_tool_hops)
        trace = env.export_trace_dict()
        preds = eval_predicates(trace)
        if not preds:
            continue
        findings.append({
            "predicates": preds,
            "score_cell_signature": cell_signature(trace.get("tool_events", [])),
        })
    raw = score_attack(findings, normalize=False)
    norm = score_attack(findings, normalize=True)
    uniq = len({h for h in (get_score_cell_hash(f) for f in findings) if h})
    mass = sum(SEVERITY_W.get(int(p["severity"]), 1) for f in findings for p in f["predicates"])
    return {"kept": len(findings), "raw": raw, "norm": round(norm, 2),
            "unique_cells": uniq, "pred_mass": mass}


if __name__ == "__main__":
    algo = attack_mod.AttackAlgorithm(config={"n_candidates": 1200})
    cands = algo.run(env=None, config=None)
    print(f"attack.py produced {len(cands)} candidates")
    lens = [len(c.user_messages) for c in cands]
    charmax = max(len(m) for c in cands for m in c.user_messages)
    print(f"msgs/candidate: min={min(lens)} max={max(lens)}; max msg chars={charmax}")
    print("distinct hosts:", len({URL_RE.search(c.user_messages[0]).group(0) for c in cands}))
    for comp in (1.0, 0.5, 0.2, 0.05):
        r = score(cands, MockCompliantAgent, compliance=comp)
        print(f"compliance={comp:>4}: {r}")
