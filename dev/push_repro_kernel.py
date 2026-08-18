"""Push the Phase-2 repro/observability notebook to Kaggle via REST kernels/push.

This is NOT the competition submission. It writes no submission.csv and must never
be submitted -- it exists only to run the repro harness under our own control and
return per-candidate observability JSON in /kaggle/working.

The notebook body comes from dev/repro/build_repro_notebook.py (which base64-embeds
the repro package plus its runtime deps), so nothing is hand-transcribed and no
homoglyph/newline corruption is possible -- see the push_kernel.py sibling.

Usage:
    python dev/push_repro_kernel.py                      # deterministic self-check
    python dev/push_repro_kernel.py --model gemma --gpu --weights gemma=/kaggle/input/...
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev" / "repro"))

import build_repro_notebook as brn  # noqa: E402

CRED = Path.home() / ".claude" / ".credentials.json"
CRED_KEY = "kaggle|43f49c16a482634f"
SLUG = "adostie3/jed-repro-harness"
TITLE = "JED Repro Harness"  # Kaggle caps titles at 50 chars
COMPETITION = "ai-agent-security-multi-step-tool-attacks"


def _token() -> str:
    return json.loads(CRED.read_text(encoding="utf-8"))["mcpOAuth"][CRED_KEY]["accessToken"]


def _parse_weights(pairs: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--weights expects row=path, got {p!r}")
        row, path = p.split("=", 1)
        out[row] = path
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="deterministic", choices=["deterministic", "gpt_oss", "gemma"])
    ap.add_argument("--candidates", type=int, default=8)
    ap.add_argument("--weights", nargs="*", default=None, help="row=path")
    ap.add_argument("--gpu", action="store_true", help="request a T4 (needed for real models)")
    ap.add_argument("--models-datasource", nargs="*", default=None,
                    help="Kaggle model refs to attach, e.g. owner/model/Transformers/variation/1")
    ap.add_argument("--dry-run", action="store_true", help="build and validate, do not push")
    args = ap.parse_args()

    nb = brn.build(model=args.model, n_candidates=args.candidates,
                   weights=_parse_weights(args.weights))
    # Kaggle-side execution settings live in the notebook metadata as well as the
    # request body; the body is authoritative for machineShape (see push_kernel.py).
    nb["metadata"]["kaggle"] = {
        "accelerator": "nvidiaTeslaT4" if args.gpu else "none",
        "dataSources": [{"sourceId": 134815, "sourceType": "competition"}],
        "isGpuEnabled": bool(args.gpu),
        "isInternetEnabled": False,
        "language": "python",
        "sourceType": "notebook",
    }
    notebook_source = json.dumps(nb)
    json.loads(notebook_source)  # fail loudly here rather than as papermill NotJSONError

    body = {
        "slug": SLUG,
        "newTitle": TITLE,
        "text": notebook_source,
        "language": "python",
        "kernelType": "notebook",
        "isPrivate": True,
        "enableGpu": bool(args.gpu),
        "enableTpu": False,
        "enableInternet": False,
        "datasetDataSources": [],
        "competitionDataSources": [COMPETITION],
        "kernelDataSources": [],
        "modelDataSources": args.models_datasource or [],
        "categoryIds": [],
    }
    if args.gpu:
        body["machineShape"] = "NvidiaTeslaT4"

    print(f"model={args.model} candidates={args.candidates} gpu={args.gpu} "
          f"cells={len(nb['cells'])} bytes={len(notebook_source)}")
    if args.dry_run:
        print("dry run; not pushed")
        return 0

    req = urllib.request.Request(
        "https://www.kaggle.com/api/v1/kernels/push",
        data=notebook_source and json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Authorization": "Bearer " + _token(),
                 "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            print("PUSH RESPONSE:", r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print("HTTP ERROR", e.code)
        print(e.read().decode("utf-8", "replace")[:800])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
