"""One column of the selection matrix: per-family survival under a single profile.

Usage: _profile_col.py <profile> [k]
Writes dev/benchmark/_col_<profile>.json with per-family survival_mean/min + baseline_raw.
Deterministic (p=1.0) profiles are exact at k=1; k defaults from stochastic detection.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import oracle  # noqa: E402
import benchmark as B  # noqa: E402
import guardrails as G  # noqa: E402
from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail  # noqa: E402

FAMILIES = ["plain", "split_marker", "forge_multi",
            "cd_mono", "cd_domain_div", "cd_full_div", "cd_twomsg"]
CANDIDATES = 8
HOPS = 8


def _percentile(vals, q):
    return B._percentile(vals, q)


def main() -> int:
    profile = sys.argv[1]
    port = B.build_portfolio_corpus(CANDIDATES, FAMILIES)

    # per-family baseline (OptimalGuardrail) — the permissive reference
    baseline = {}
    for fam in FAMILIES:
        agent = B.ALL_FAMILIES[fam][1]
        baseline[fam] = oracle.score_corpus(port[fam], guardrail_factory=OptimalGuardrail,
                                             max_tool_hops=HOPS, agent_factory=agent)["raw"]

    if profile == "optimal":
        col = {fam: {"survival_mean": 1.0 if baseline[fam] else 0.0,
                     "survival_min": 1.0 if baseline[fam] else 0.0,
                     "baseline_raw": baseline[fam], "k": 1} for fam in FAMILIES}
    else:
        stochastic = any(r.block_prob < 1.0 for r in G._profile_rules(profile))
        k = int(sys.argv[2]) if len(sys.argv) > 2 else (12 if stochastic else 1)
        col = {}
        for fam in FAMILIES:
            agent = B.ALL_FAMILIES[fam][1]
            members = G.build_ensemble(profile, 0, k)
            raws = [B._run_corpus(port[fam], f, agent, HOPS)["raw"] for f in members]
            base = baseline[fam]
            col[fam] = {
                "survival_mean": (mean(raws) / base) if base else None,
                "survival_min": (min(raws) / base) if (base and raws) else None,
                "baseline_raw": base, "k": k,
            }

    out = Path(__file__).resolve().parent / f"_col_{profile}.json"
    out.write_text(json.dumps({"profile": profile, "col": col}, indent=2, default=str),
                   encoding="utf-8")
    print(f"[{profile}] " + " ".join(
        f"{fam}={'--' if col[fam]['survival_mean'] is None else format(col[fam]['survival_mean'], '.2f')}"
        for fam in FAMILIES))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
