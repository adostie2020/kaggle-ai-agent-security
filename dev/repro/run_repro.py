"""CLI for the real-model repro harness.

    python dev/repro/run_repro.py --model gemma --candidates 8 \
        --out /kaggle/working/repro --sink-dir /kaggle/working/repro/debug \
        --weights gemma=/kaggle/input/gemma/hf-snapshot

    python dev/repro/run_repro.py --self-check          # weights-free deterministic smoke
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))       # dev/repro/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # dev/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repo root
# dev/benchmark holds the stochastic-guardrail `guardrails` module. Locally this is
# dev/benchmark; in-kernel run_repro.py lives in repro_pkg/ so this path won't exist
# (harmless insert) and the embedded guardrails.py is found co-located in repro_pkg/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmark"))

import models  # noqa: E402
import runner  # noqa: E402
from debug_sink import install_default_sink  # noqa: E402


def _parse_weights(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--weights expects row=path, got {p!r}")
        row, path = p.split("=", 1)
        out[row] = path
    return out


def resolve_guardrail(name: str, base_seed: int = 0, member: int = 0):
    """Map a guardrail NAME to a zero-arg guardrail factory for runner.run_repro.

    - ``optimal``  -> the permissive public OptimalGuardrail (default; today's behavior).
    - ``sdk_strict`` -> the SDK's fixed strict baseline (benchmark ``REFERENCE``).
    - a stochastic profile (``strict_default``/``paranoid``/``marker_only``) -> the
      member-``member`` factory of the seeded ensemble, closing over (base_seed, member).

    The rule LOGIC lives only in the benchmark ``guardrails`` module (committed there,
    embedded into the push-only notebook); this resolver references it by name so no rule
    content lands in the committed run/push wiring. The stochastic profiles are HELD-OUT
    hypotheses about the private guardrail -- their survival numbers are a train/test signal
    and must not be fed back into attack.py's design (see dev/repro/README.md).
    """
    if name == "optimal":
        import oracle  # permissive public baseline; needs no benchmark module
        return oracle.OptimalGuardrail
    import guardrails as _g  # benchmark module: dev/benchmark locally, repro_pkg/ in-kernel
    if name in _g.REFERENCE:            # sdk_strict (optimal handled above)
        return _g.REFERENCE[name]
    if name in _g.PROFILES:
        return _g.build_ensemble(name, base_seed, member + 1)[member]
    valid = sorted(set(_g.REFERENCE) | set(_g.PROFILES))
    raise ValueError(f"unknown guardrail {name!r}; valid: {valid}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Real-model repro observability runner.")
    ap.add_argument("--model", choices=list(models.REPRO_MODELS), default="gemma")
    ap.add_argument("--backend", choices=["gguf", "hf"], default="gguf",
                    help="gguf = evaluator's llama.cpp GGUF servers (scored parity); "
                         "hf = build_agent_factory HF Transformers backends")
    ap.add_argument("--candidates", type=int, default=8)
    ap.add_argument("--out", default="repro_out")
    ap.add_argument("--sink-dir", default=None,
                    help="dir for raw per-candidate model debug JSONL (optional)")
    ap.add_argument("--weights", nargs="*", default=None,
                    help="row=path weight paths, e.g. gemma=/kaggle/input/g/hf-snapshot. "
                         "These feed build_agent_factory's HF backends, so each is a model "
                         "DIRECTORY. Note the deployed evaluator instead runs llama.cpp GGUF "
                         "model servers keyed on GPT_OSS_MODEL_PATH / GEMMA_MODEL_PATH file "
                         "paths -- see README 'TWO BACKEND LAYERS'.")
    ap.add_argument("--guardrail", default="optimal",
                    choices=["optimal", "sdk_strict", "strict_default", "paranoid", "marker_only"],
                    help="scoring guardrail: optimal (permissive public baseline, default); "
                         "sdk_strict (SDK fixed-strict reference); or a HELD-OUT stochastic "
                         "strict profile (strict_default/paranoid/marker_only) at --base-seed/"
                         "--member. Survival under the stochastic profiles is a train/test "
                         "signal -- do NOT feed it into attack.py tuning (leakage).")
    ap.add_argument("--base-seed", type=int, default=0,
                    help="stochastic-guardrail ensemble base seed (ignored for optimal/sdk_strict)")
    ap.add_argument("--member", type=int, default=0,
                    help="stochastic-guardrail ensemble member index (ignored for optimal/sdk_strict)")
    ap.add_argument("--self-check", action="store_true",
                    help="force --model deterministic (weights-free smoke run)")
    ap.add_argument("--no-validate", action="store_true",
                    help="skip fail-fast backend validation")
    args = ap.parse_args()

    model = "deterministic" if args.self_check else args.model
    if args.weights:
        models.wire_weight_paths(_parse_weights(args.weights))

    # Belt-and-suspenders: also patch construction we don't control, if a sink dir
    # is set (harmless for the deterministic self-check).
    if args.sink_dir:
        install_default_sink(path=str(Path(args.sink_dir) / "default_sink.jsonl"))

    if model != "deterministic" and args.backend == "hf" and not args.no_validate:
        models.validate_selection(model)  # HF backend only; GGUF validates in ModelSession.open()

    result = runner.run_repro(
        model=model,
        n_candidates=args.candidates,
        out_dir=args.out,
        backend=args.backend,
        sink_dir=args.sink_dir,
        guardrail_factory=resolve_guardrail(args.guardrail, args.base_seed, args.member),
    )
    print(f"repro done: model={result.model} candidates={result.n_candidates} "
          f"guardrail={args.guardrail} total_raw={result.total_raw} "
          f"total_norm={result.total_normalized:.3f} -> {result.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
