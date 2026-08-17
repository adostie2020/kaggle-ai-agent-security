"""Build a Kaggle notebook that runs the real-model repro harness on a GPU kernel
and dumps observability JSON to /kaggle/working/repro (which IS returned at commit,
unlike the hidden rerun). Mirrors dev/build_notebook.py: repro sources are
base64-embedded so no source escaping is needed.

This notebook is NOT a competition submission -- it writes no submission.csv.
Attach the competition data source + the GGUF weight dataset(s) when pushing.

`run_repro.py` imports `runner`, which in turn imports `oracle`, `trace`, and
(at call time) `attack` -- none of those live under dev/repro/. We embed them
alongside the repro sources (flat, all in the same /kaggle/working/repro_pkg/
directory) so the kernel doesn't need dev/ reconstructed separately or die on
an ImportError. oracle.py's FIXTURES path is derived from the installed
aicomp_sdk package (location-independent), and trace.py/runner.py/run_repro.py
each sys.path.insert(0, their own parent dir) -- once everything is co-located
in repro_pkg/, that self-referential insert is enough for `import oracle`,
`from agents import MockCompliantAgent`, and `import attack` to resolve, and
for `import trace` to pick up our trace.py (repro_pkg/ sorts first on
sys.path) instead of the stdlib `trace` module -- exactly how dev/ already
works today.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

REPRO_DIR = Path(__file__).resolve().parent
REPO_ROOT = REPRO_DIR.parent.parent
SRC_FILES = ["debug_sink.py", "models.py", "runner.py", "run_repro.py"]
DEP_FILES: dict[str, Path] = {
    "oracle.py": REPO_ROOT / "dev" / "oracle.py",
    "trace.py": REPO_ROOT / "dev" / "trace.py",
    "agents.py": REPO_ROOT / "dev" / "agents.py",
    "attack.py": REPO_ROOT / "attack.py",
}

PREAMBLE = (
    "import sys, glob\n"
    "from pathlib import Path as _Path\n"
    "for _c in glob.glob('/kaggle/input/**/kaggle_evaluation', recursive=True):\n"
    "    _root = str(_Path(_c).parent)\n"
    "    if _root not in sys.path:\n"
    "        sys.path.insert(0, _root)\n"
    "    break\n"
    "print('dataset root wired; /kaggle/input =', __import__('os').listdir('/kaggle/input'))\n"
)


def _code(src: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "outputs": [],
            "execution_count": None, "source": src}


def _markdown(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def _embed_sources() -> str:
    """Cell that writes the repro package into /kaggle/working/repro_pkg from base64.

    Embeds the dev/repro/*.py sources plus the Phase-1 dependencies they import
    at runtime (oracle, trace, agents, attack) -- all flattened into the same
    directory so the kernel's import graph resolves without dev/ on disk.
    """
    parts = ["import base64, os\n", "os.makedirs('/kaggle/working/repro_pkg', exist_ok=True)\n"]
    sources = {name: REPRO_DIR / name for name in SRC_FILES}
    sources.update(DEP_FILES)
    for name, path in sources.items():
        text = path.read_text(encoding="utf-8")
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        parts.append(
            f'open("/kaggle/working/repro_pkg/{name}","wb").write(base64.b64decode("{b64}"))\n'
        )
    parts.append("print('repro package written:', os.listdir('/kaggle/working/repro_pkg'))\n")
    return "".join(parts)


def build(model: str = "gemma", n_candidates: int = 8,
          weights: dict[str, str] | None = None) -> dict:
    weights = weights or {}
    weight_args = " ".join(f"{row}={path}" for row, path in weights.items())
    weight_flag = f" --weights {weight_args}" if weight_args else ""
    run_cell = (
        "import subprocess, sys\n"
        "cmd = [sys.executable, '/kaggle/working/repro_pkg/run_repro.py',\n"
        f"       '--model', '{model}', '--candidates', '{n_candidates}',\n"
        "       '--out', '/kaggle/working/repro',\n"
        "       '--sink-dir', '/kaggle/working/repro/debug']\n"
        f"extra = {weight_args!r}\n"
        "if extra:\n"
        "    cmd += ['--weights'] + extra.split()\n"
        "print('running:', ' '.join(cmd))\n"
        "proc = subprocess.run(cmd, capture_output=True, text=True)\n"
        "print('returncode:', proc.returncode)\n"
        "print('--- stdout ---')\n"
        "print(proc.stdout)\n"
        "print('--- stderr ---')\n"
        "print(proc.stderr)\n"
    )
    list_cell = (
        "import os, json\n"
        "root = '/kaggle/working/repro'\n"
        "for f in sorted(os.listdir(root)):\n"
        "    print(f)\n"
        "print('--- summary ---')\n"
        "print(open(os.path.join(root, 'summary.json')).read())\n"
    )
    cells = [
        _markdown("# JED real-model repro (Phase 2)\n"
                  "Runs the real agent under the SDK env/guardrail/scoring and dumps\n"
                  "per-candidate observability JSON to `/kaggle/working/repro`.\n"
                  "Not a submission — writes no `submission.csv`."),
        _code(PREAMBLE),
        _code("import importlib.util as u\n"
              "assert u.find_spec('aicomp_sdk'), 'aicomp_sdk not importable in kernel'\n"
              "print('aicomp_sdk OK')\n"),
        _code(_embed_sources()),
        _code(run_cell),
        _code(list_cell),
    ]
    return {
        "cells": cells,
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> int:
    nb = build()
    out = REPRO_DIR / "repro_notebook.ipynb"
    out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
