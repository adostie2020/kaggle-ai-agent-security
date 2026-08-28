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

    if model != "deterministic" and not args.no_validate:
        models.validate_selection(model)  # raises fast if weights/config missing

    result = runner.run_repro(
        model=model,
        n_candidates=args.candidates,
        out_dir=args.out,
        backend=args.backend,
        sink_dir=args.sink_dir,
    )
    print(f"repro done: model={result.model} candidates={result.n_candidates} "
          f"total_raw={result.total_raw} total_norm={result.total_normalized:.3f} "
          f"-> {result.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
