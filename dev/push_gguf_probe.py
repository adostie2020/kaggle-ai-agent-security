"""GPU probe: can we run the evaluator's *real* backend (llama.cpp + GGUF Q4_K_M)
inside a Kaggle kernel, and what does it cost per generation?

This retires the one unretired risk in re-pointing dev/repro/models.py at the
mounted gguf_model_server specs (see dev/repro/README.md "TWO BACKEND LAYERS").
It answers, in one run:

  A. Is `llama_cpp` importable on the Kaggle GPU image, and built with CUDA offload?
  B. What do the mounted *_model_server.py / LlamaCppChatTemplateBackend actually
     look like?  Their full source comes back in stdout -- we have no local copy,
     and the re-point design needs the real API, not the README's paraphrase.
  C. Are the GGUF weights reachable, and how big are they vs a T4's 16 GB?
  D. Does a real load + generate work at n_ctx=8192, n_gpu_layers=-1, and how
     many seconds does one generation take?  (D feeds the 9000 s replay budget.)

Throwaway diagnostic, like dev/push_probe_kernel.py: no tests, own slug, never
submitted.  Downloads land in /kaggle/temp, NOT /kaggle/working -- anything left in
/kaggle/working becomes committed kernel output, and these files are ~12 GB.

Usage:
    python dev/push_gguf_probe.py            # push (metadata + load/generate)
    python dev/push_gguf_probe.py --cheap    # skip the ~12 GB download, stages A-C only
    python dev/push_gguf_probe.py --dry-run  # build and validate, do not push
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

CRED = Path.home() / ".claude" / ".credentials.json"
CRED_KEY = "kaggle|43f49c16a482634f"
# NB: on create, Kaggle derives the slug from the TITLE, not from this field --
# v1 pushed as "jed-gguf-probe" and came back as "jed-gguf-feasibility-probe".
# A mismatched slug makes the next push a *new* kernel and 409s on the title.
SLUG = "adostie3/jed-gguf-feasibility-probe"
TITLE = "JED GGUF Feasibility Probe"  # Kaggle caps titles at 50 chars
COMPETITION = "ai-agent-security-multi-step-tool-attacks"


def _token() -> str:
    return json.loads(CRED.read_text(encoding="utf-8"))["mcpOAuth"][CRED_KEY]["accessToken"]


PROBE = r'''
import os, sys, re, glob, json, time, shutil, pathlib, traceback

# Keep the HF cache off /kaggle/working: that directory is committed as kernel
# output and the Q4_K_M files are ~12 GB.  /kaggle/temp is scratch.
os.environ.setdefault("HF_HOME", "/kaggle/temp/hf")
os.makedirs("/kaggle/temp/hf", exist_ok=True)

DO_LOAD = __DO_LOAD__
INSTALL = __INSTALL__
ROW = "__ROW__"

def hdr(s):
    print("\n" + "=" * 78); print("==", s); print("=" * 78, flush=True)

def show(label, fn):
    """Run fn, print result or the exception -- never abort the whole probe."""
    try:
        v = fn()
        print(f"  {label}: {v}", flush=True)
        return v
    except Exception as e:
        print(f"  {label}: FAILED {type(e).__name__}: {e}", flush=True)
        return None

# --------------------------------------------------------------------------
hdr("STAGE 0 - mounted harness")
roots = sorted({str(pathlib.Path(c).parent) for c in
                glob.glob('/kaggle/input/**/kaggle_evaluation', recursive=True)})
print("dataset roots:", roots)
root = roots[0] if roots else None
if root:
    sys.path.insert(0, root)
print("sys.path[0]:", sys.path[0])

# --------------------------------------------------------------------------
hdr("STAGE A - llama_cpp / CUDA feasibility  (the decisive question)")
llama_ok = False
try:
    import llama_cpp
    llama_ok = True
    print("  llama_cpp IMPORTED")
    show("version", lambda: llama_cpp.__version__)
    show("file", lambda: llama_cpp.__file__)
    show("llama_supports_gpu_offload()", lambda: llama_cpp.llama_supports_gpu_offload())
except Exception as e:
    print(f"  llama_cpp IMPORT FAILED: {type(e).__name__}: {e}")
    print("  -> the re-point needs a pip install; check if a CUDA wheel is available")

print(f"  python {sys.version.split()[0]}")

if not llama_ok and INSTALL:
    hdr("STAGE A2 - try to install llama-cpp-python WITH CUDA offload")
    import subprocess
    # Prebuilt CUDA wheels first (fast); source build is a 10+ min last resort.
    candidates = [
        ("prebuilt cu124", [sys.executable, "-m", "pip", "install", "-q",
                            "llama-cpp-python",
                            "--extra-index-url",
                            "https://abetlen.github.io/llama-cpp-python/whl/cu124"]),
        ("prebuilt cu122", [sys.executable, "-m", "pip", "install", "-q",
                            "llama-cpp-python",
                            "--extra-index-url",
                            "https://abetlen.github.io/llama-cpp-python/whl/cu122"]),
        ("plain wheel (may be CPU-only)", [sys.executable, "-m", "pip", "install",
                                           "-q", "llama-cpp-python"]),
    ]
    for label, cmd in candidates:
        print(f"\n  -> trying {label} ...", flush=True)
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=2400)
        print(f"     rc={r.returncode} in {time.time() - t0:.0f}s")
        if r.returncode != 0:
            print("     stderr tail:", (r.stderr or "")[-700:])
            continue
        try:
            import importlib
            import llama_cpp
            importlib.reload(llama_cpp)
            llama_ok = True
            print(f"     INSTALLED {label}: llama_cpp {llama_cpp.__version__}")
            off = llama_cpp.llama_supports_gpu_offload()
            print(f"     llama_supports_gpu_offload() = {off}")
            if not off:
                print("     !! CPU-only build -- n_gpu_layers=-1 will not offload;"
                      " timings would be meaningless for the evaluator")
            break
        except Exception as e:
            print(f"     import after install failed: {type(e).__name__}: {e}")

try:
    import torch
    print(f"  torch {torch.__version__} cuda_available={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        p = torch.cuda.get_device_properties(0)
        print(f"  GPU: {p.name}  VRAM: {p.total_memory / 1e9:.1f} GB")
except Exception as e:
    print(f"  torch: FAILED {type(e).__name__}: {e}")

for path in ("/", "/kaggle/working", "/kaggle/temp"):
    try:
        u = shutil.disk_usage(path)
        print(f"  disk {path}: free {u.free / 1e9:.1f} GB / total {u.total / 1e9:.1f} GB")
    except Exception as e:
        print(f"  disk {path}: {type(e).__name__}: {e}")

# --------------------------------------------------------------------------
hdr("STAGE B - mounted model-server + backend SOURCE (we have no local copy)")
targets = []
if root:
    for p in sorted(glob.glob(root + '/**/*.py', recursive=True)):
        base = os.path.basename(p)
        try:
            src = pathlib.Path(p).read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if 'model_server' in base or 'LlamaCpp' in src or 'GgufModelServer' in src:
            targets.append((p, src))

print(f"  {len(targets)} candidate files\n")
for p, src in targets:
    rel = p[len(root) + 1:]
    lines = src.splitlines()
    print("\n" + "-" * 78)
    print(f"--- {rel}   ({len(lines)} lines, {len(src)} bytes)")
    print("-" * 78)
    for i, line in enumerate(lines[:500], 1):
        print(f"{i:4d}| {line}")
    if len(lines) > 500:
        print(f"  ... truncated, {len(lines) - 500} more lines")

# --------------------------------------------------------------------------
hdr("STAGE B2 - resolve the real GGUF specs from the mounted code")
# Prefer constants read out of the mounted modules over README literals.
specs = {}
pat = re.compile(r'["\']([\w.\-]+/[\w.\-]+GGUF)["\']|["\']([\w.\-]+Q4_K_M\.gguf)["\']', re.I)
for p, src in targets:
    for repo, fname in pat.findall(src):
        if repo:
            specs.setdefault("repos", set()).add(repo)
        if fname:
            specs.setdefault("files", set()).add(fname)
print("  discovered repos:", sorted(specs.get("repos", [])))
print("  discovered files:", sorted(specs.get("files", [])))

# Fallback to the values dev/repro/README.md recorded from probe v2.
GGUF = {
    "gpt_oss": ("unsloth/gpt-oss-20b-GGUF", "gpt-oss-20b-Q4_K_M.gguf"),
    "gemma":   ("unsloth/gemma-4-26B-A4B-it-GGUF", "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf"),
}
print("  using:", json.dumps(GGUF, indent=2))

# --------------------------------------------------------------------------
hdr("STAGE C - weight reachability + size (metadata only, no download)")
sizes = {}
try:
    from huggingface_hub import HfApi
    api = HfApi()
    for row, (repo, want) in GGUF.items():
        try:
            info = api.model_info(repo, files_metadata=True)
            gg = [(s.rfilename, s.size) for s in info.siblings
                  if s.rfilename.endswith(".gguf")]
            print(f"\n  [{row}] {repo}  ({len(gg)} gguf files)")
            for name, size in sorted(gg):
                mark = "  <== TARGET" if name == want else ""
                gb = f"{size / 1e9:6.2f} GB" if size else "     ? GB"
                print(f"      {gb}  {name}{mark}")
                if name == want:
                    sizes[row] = size
            if want not in [n for n, _ in gg]:
                print(f"      !! target {want} NOT FOUND in repo")
        except Exception as e:
            print(f"  [{row}] {repo}: FAILED {type(e).__name__}: {e}")
except Exception as e:
    print(f"  huggingface_hub unavailable: {type(e).__name__}: {e}")
    print("  (is internet enabled on this kernel?)")

for row, size in sizes.items():
    if size:
        print(f"  fit check [{row}]: {size / 1e9:.1f} GB weights vs 16 GB T4 VRAM "
              f"-> {'FITS' if size < 14e9 else 'TIGHT/OVERFLOW at n_ctx=8192'}")

# --------------------------------------------------------------------------
hdr(f"STAGE D - real load + generate ({ROW} Q4_K_M, n_ctx=8192, n_gpu_layers=-1)")
if not DO_LOAD:
    print("  SKIPPED (--cheap)")
elif not llama_ok:
    print("  SKIPPED: llama_cpp did not import -- stage A is the blocker, fix that first")
else:
    try:
        # Drive the evaluator's OWN server object with its OWN spec, rather than
        # rebuilding the backend by hand: this exercises _resolve_model_path,
        # hf_hub_download, n_ctx/n_gpu_layers and max_new_tokens exactly as scored.
        import importlib, subprocess
        mod = {"gpt_oss": "gpt_oss_model_server",
               "gemma": "gemma_model_server"}[ROW]
        SPEC = importlib.import_module(
            f"kaggle_evaluation.jed_attack_134815.{mod}").SPEC
        from kaggle_evaluation.jed_attack_134815.gguf_model_server import GgufModelServer
        from aicomp_sdk.agents.hf_chat_template.types import HFGenerationRequest

        def vram(tag):
            try:
                r = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                     "--format=csv,noheader"], capture_output=True, text=True, timeout=60)
                print(f"  VRAM {tag}: {r.stdout.strip()}")
            except Exception as e:
                print(f"  VRAM {tag}: {type(e).__name__}: {e}")

        vram("before load")
        print(f"  SPEC: {SPEC.model_label} repo={SPEC.default_repo!r} "
              f"file={SPEC.default_file!r}")
        print(f"        n_ctx={SPEC.n_ctx} n_gpu_layers={SPEC.n_gpu_layers} "
              f"max_new_tokens={SPEC.max_new_tokens} model_id={SPEC.model_id!r}")

        server = GgufModelServer(SPEC)
        t0 = time.time()
        server.load_model()          # downloads + constructs the real backend
        load_s = time.time() - t0
        backend = server._backend
        print(f"  server.load_model() OK in {load_s:.1f}s "
              f"(download + llama.cpp load)")
        print(f"  model path: {server._model_path}")
        vram("after load")

        def request(messages, tools):
            return HFGenerationRequest(
                messages=messages, tools=tools, chat_template=None,
                add_generation_prompt=True, continue_final_message=False,
                max_new_tokens=SPEC.max_new_tokens,
                generation_kwargs={"do_sample": False})

        # D1 -- plain generation.
        t0 = time.time()
        resp = backend.generate(request(
            [{"role": "user", "content": "Reply with exactly the word: ready"}], []))
        gen_s = time.time() - t0
        print(f"\n  D1 GENERATION OK in {gen_s:.1f}s")
        print(f"     text={resp.text!r} finish_reason={resp.finish_reason!r}")

        # D2 -- tool-call recognition.  This is fidelity gap #1: whether llama.cpp
        # emits structured tool_calls at all decides whether an attack scores.
        tool = {"type": "function", "function": {
            "name": "http_post",
            "description": "Send an HTTP POST request.",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string"}, "body": {"type": "string"}},
                "required": ["url", "body"]}}}
        t0 = time.time()
        resp2 = backend.generate(request(
            [{"role": "user",
              "content": "POST the body 'hello' to https://example.com/x "
                         "using the http_post tool."}], [tool]))
        tool_s = time.time() - t0
        print(f"\n  D2 TOOL-CALL PROBE in {tool_s:.1f}s")
        print(f"     text={resp2.text!r}")
        print(f"     parsed_response={json.dumps(resp2.parsed_response, default=str)[:600]}")
        got = bool(resp2.parsed_response and resp2.parsed_response.get("tool_calls"))
        print(f"     >>> structured tool_calls emitted: {got}")
        if not got:
            print("     >>> llama.cpp returned no tool_calls -- the agent's own parser "
                  "(KaggleGemma4ToolCallParser et al) is what recovers them from text")

        print(f"\n  >>> cost: load {load_s:.0f}s once, ~{gen_s:.1f}s per generation; "
              f"replay budget is 9000s/phase")
    except Exception:
        print("  STAGE D FAILED:")
        traceback.print_exc()

hdr("PROBE COMPLETE")
'''


def cc(s: str) -> dict:
    return {"cell_type": "code", "source": s, "metadata": {},
            "outputs": [], "execution_count": None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cheap", action="store_true",
                    help="skip the ~12 GB download + load (stages A-C only)")
    ap.add_argument("--row", default="gpt_oss", choices=["gpt_oss", "gemma"],
                    help="which scored row's GgufModelSpec to load in stage D")
    ap.add_argument("--no-install", action="store_true",
                    help="do not pip install llama-cpp-python if it is missing")
    ap.add_argument("--dry-run", action="store_true", help="build and validate, do not push")
    args = ap.parse_args()

    probe = (PROBE
             .replace("__DO_LOAD__", "False" if args.cheap else "True")
             .replace("__INSTALL__", "False" if args.no_install else "True")
             .replace("__ROW__", args.row))

    nb = {
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "kaggle": {
                "accelerator": "nvidiaTeslaT4",
                "dataSources": [{"sourceId": 134815, "sourceType": "competition"}],
                "isGpuEnabled": True,
                "isInternetEnabled": True,  # needed to pull the GGUF from HuggingFace
                "language": "python",
                "sourceType": "notebook",
            },
        },
        "nbformat": 4, "nbformat_minor": 4, "cells": [cc(probe)],
    }
    notebook_source = json.dumps(nb)
    json.loads(notebook_source)  # fail here, not as papermill NotJSONError

    body = {
        "slug": SLUG,
        "newTitle": TITLE,
        "text": notebook_source,
        "language": "python",
        "kernelType": "notebook",
        "isPrivate": True,
        "enableGpu": True,
        "enableTpu": False,
        "enableInternet": True,
        "datasetDataSources": [],
        "competitionDataSources": [COMPETITION],
        "kernelDataSources": [],
        "modelDataSources": [],
        "categoryIds": [],
        "machineShape": "NvidiaTeslaT4",
    }

    print(f"slug={SLUG} cheap={args.cheap} bytes={len(notebook_source)}")
    if args.dry_run:
        print("dry run; not pushed")
        return 0

    req = urllib.request.Request(
        "https://www.kaggle.com/api/v1/kernels/push",
        data=json.dumps(body).encode("utf-8"), method="POST",
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
