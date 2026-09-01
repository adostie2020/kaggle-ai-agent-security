"""CPU probe: dump the DEPLOYED evaluator's gateway + remote model-server source from
the mount, to understand why the Harmony forge (2.26x faster, 100% re-fire in in-process
eval_attack) UNDERPERFORMED in the real scored rerun (v18: 68.3 vs v15 plain 73.3).

The only structural difference between our faithful in-process eval_attack probe and the
scored rerun is that production drives the model through a REMOTE model-server subprocess
(serialized requests). This probe reads exactly how the gateway builds the replay
agent_factory and how user messages (and any control tokens in them) are serialized and
re-templated on the remote path.

Throwaway diagnostic: own slug, CPU-only, fast, never submitted.

Usage:
    python dev/push_gateway_probe.py
    python dev/push_gateway_probe.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

CRED = Path.home() / ".claude" / ".credentials.json"
CRED_KEY = "kaggle|43f49c16a482634f"
SLUG = "adostie3/jed-gateway-probe"
TITLE = "JED Gateway Probe"
COMPETITION = "ai-agent-security-multi-step-tool-attacks"


def _token() -> str:
    return json.loads(CRED.read_text(encoding="utf-8"))["mcpOAuth"][CRED_KEY]["accessToken"]


PROBE = r'''
import os, sys, glob, pathlib, traceback

def hdr(s):
    print("\n" + "=" * 78); print("==", s); print("=" * 78, flush=True)

roots = sorted({str(pathlib.Path(c).parent) for c in
                glob.glob('/kaggle/input/**/kaggle_evaluation', recursive=True)})
root = roots[0] if roots else None
print("mount root:", root, flush=True)
if root and root not in sys.path:
    sys.path.insert(0, root)

pkg = pathlib.Path(root) / "kaggle_evaluation" if root else None
hdr("FILE TREE of kaggle_evaluation")
if pkg and pkg.exists():
    for p in sorted(pkg.rglob("*.py")):
        print("  ", p.relative_to(pkg), p.stat().st_size, "bytes")
else:
    print("  kaggle_evaluation not found")

def dump(relpath, grep=None):
    hdr("SOURCE: " + relpath + (f"   (grep={grep})" if grep else ""))
    f = pkg / relpath if pkg else None
    if not f or not f.exists():
        # try to find by basename anywhere under mount
        base = pathlib.Path(relpath).name
        hits = list(pkg.rglob(base)) if pkg else []
        if not hits:
            print("  NOT FOUND:", relpath); return
        f = hits[0]; print("  (resolved to", f, ")")
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        print("  read failed"); traceback.print_exc(); return
    if grep:
        for i, line in enumerate(text.splitlines(), 1):
            if any(g.lower() in line.lower() for g in grep):
                print(f"  {i:4d}: {line}")
    else:
        print(text)

# The interesting files (names inferred from repro/README; resolve by basename if moved).
dump("jed_attack_134815/jed_attack_gateway.py")
dump("jed_attack_134815/jed_attack_inference_server.py")
dump("jed_attack_134815/gguf_model_server.py")
dump("jed_attack_134815/gpt_oss_model_server.py")
dump("jed_attack_134815/gemma_model_server.py")

# SAMPLING PARAMS are the crux: does production decode GREEDILY (== our probes) or SAMPLE
# (temp>0 => more rambling => more hops => higher cost)? Grep every file for the knobs.
hdr("GREP whole package for SAMPLING / decode params")
if pkg:
    sneedles = ["temperature", "temp=", "top_p", "top_k", "do_sample", "sample", "greedy",
                "max_tokens", "max_new_tokens", "n_predict", "num_predict", "seed",
                "SamplingParams", "GenerationConfig", "generate(", "predict("]
    for p in sorted(pkg.rglob("*.py")):
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if any(n.lower() in line.lower() for n in sneedles):
                    print(f"  {p.relative_to(pkg)}:{i}: {line.strip()[:180]}")
        except Exception:
            pass

# Any remote-agent / serialization glue: grep the whole package for the request path.
hdr("GREP whole package for remote/serialize/create_agent/user_message/interact + hop/budget config")
if pkg:
    needles = ["remote", "serialize", "create_agent", "agent_factory", "user_message",
               "def interact", "next_action", "RemoteAgent", "proto", "grpc", "pickle",
               "json.dumps", "build_request", "chat_template", "apply_chat_template",
               "eval_attack", "evaluate_redteam", "evaluate_dual",
               "max_tool_hops", "MAX_TOOL_HOPS", "time_budget", "DEFAULT_BUDGET",
               "AttackRunConfig", "config.max", "run(", ".run("]
    for p in sorted(pkg.rglob("*.py")):
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if any(n.lower() in line.lower() for n in needles):
                    print(f"  {p.relative_to(pkg)}:{i}: {line.strip()[:160]}")
        except Exception:
            pass

hdr("PROBE COMPLETE")
'''


def cc(s: str) -> dict:
    return {"cell_type": "code", "source": s, "metadata": {}, "outputs": [], "execution_count": None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    nb = {
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "kaggle": {
                "dataSources": [{"sourceId": 134815, "sourceType": "competition"}],
                "isGpuEnabled": False,
                "isInternetEnabled": False,
                "language": "python",
                "sourceType": "notebook",
            },
        },
        "nbformat": 4, "nbformat_minor": 4, "cells": [cc(PROBE)],
    }
    notebook_source = json.dumps(nb)
    json.loads(notebook_source)

    body = {
        "slug": SLUG, "newTitle": TITLE, "text": notebook_source,
        "language": "python", "kernelType": "notebook", "isPrivate": True,
        "enableGpu": False, "enableTpu": False, "enableInternet": False,
        "datasetDataSources": [], "competitionDataSources": [COMPETITION],
        "kernelDataSources": [], "modelDataSources": [], "categoryIds": [],
    }
    print(f"slug={SLUG} bytes={len(notebook_source)}")
    if args.dry_run:
        print("dry run; not pushed"); return 0

    req = urllib.request.Request(
        "https://www.kaggle.com/api/v1/kernels/push",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + _token(),
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            print("PUSH RESPONSE:", r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print("HTTP ERROR", e.code); print(e.read().decode("utf-8", "replace")[:800]); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
