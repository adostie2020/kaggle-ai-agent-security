"""Parallel selection-matrix sweep (STEP 1+2), 6-worker process pool over profiles.

Each worker computes one profile's per-family survival column (baseline reused within the
worker). Deterministic (p=1.0) profiles exact at k=1; stochastic at k=12. Writes
_selection_matrix.json and prints the grid.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

FAMILIES = ["plain", "split_marker", "forge_multi",
            "cd_mono", "cd_domain_div", "cd_full_div", "cd_twomsg"]
PROFILES = [
    "optimal",
    "marker_only", "det_marker_data", "det_marker_prompt",
    "det_cd_block", "det_cd_domain", "det_cd_wording", "det_cd_sharegate", "cd_strict",
    "strict_default", "paranoid",
    "joint_marker_share", "joint_marker_block",
]
CANDIDATES = 8
HOPS = 8
K_STOCHASTIC = 12


def compute_col(profile: str) -> tuple[str, dict]:
    """Worker: full per-family survival column for one profile (self-contained for spawn)."""
    import oracle
    import benchmark as B
    import guardrails as G
    from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail

    port = B.build_portfolio_corpus(CANDIDATES, FAMILIES)
    baseline = {}
    for fam in FAMILIES:
        agent = B.ALL_FAMILIES[fam][1]
        baseline[fam] = oracle.score_corpus(port[fam], guardrail_factory=OptimalGuardrail,
                                             max_tool_hops=HOPS, agent_factory=agent)["raw"]
    if profile == "optimal":
        col = {fam: {"survival_mean": 1.0 if baseline[fam] else 0.0,
                     "survival_min": 1.0 if baseline[fam] else 0.0,
                     "baseline_raw": baseline[fam], "k": 1} for fam in FAMILIES}
        return profile, col

    stochastic = any(r.block_prob < 1.0 for r in G._profile_rules(profile))
    k = K_STOCHASTIC if stochastic else 1
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
    return profile, col


def main() -> int:
    t0 = time.perf_counter()
    grid: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(compute_col, p): p for p in PROFILES}
        for fut in as_completed(futs):
            profile, col = fut.result()
            grid[profile] = col
            print(f"[done {time.perf_counter()-t0:5.0f}s] {profile}", flush=True)

    def fmt(x):
        return " ---" if x is None else f"{x:.2f}"

    colw = 14
    header = "profile".ljust(20) + "".join(f.ljust(colw) for f in FAMILIES)
    print("\n=== SURVIVAL GRID (survival_mean) ===")
    print(header)
    print("-" * len(header))
    for profile in PROFILES:
        row = profile.ljust(20)
        for fam in FAMILIES:
            row += fmt(grid[profile][fam]["survival_mean"]).ljust(colw)
        print(row)

    out = Path(__file__).resolve().parent / "_selection_matrix.json"
    out.write_text(json.dumps({
        "families": FAMILIES, "profiles": PROFILES,
        "candidates": CANDIDATES, "k_stochastic": K_STOCHASTIC, "hops": HOPS,
        "grid": grid,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out}  ({time.perf_counter()-t0:.0f}s total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
