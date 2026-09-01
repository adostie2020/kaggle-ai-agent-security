"""Build the Kaggle submission notebook that ships our attack.py.

Mirrors the official getting-started notebook structure (v20):
  cell 1: add competition dataset root (parent of kaggle_evaluation/) to sys.path
  cell 2: write /kaggle/working/attack.py  (our attack, base64-embedded)
  cell 3: import + serve JEDAttackInferenceServer

We base64-embed attack.py so no source escaping is needed, and we prepend a
sys.path preamble (dropping `from __future__ import annotations`, which must be
first and is unnecessary on Kaggle's Python 3.12).
"""
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ATTACK = (ROOT / "attack.py").read_text(encoding="utf-8")

PREAMBLE = (
    "import sys, glob\n"
    "from pathlib import Path as _Path\n"
    "for _c in glob.glob('/kaggle/input/**/kaggle_evaluation', recursive=True):\n"
    "    _root = str(_Path(_c).parent)\n"
    "    if _root not in sys.path:\n"
    "        sys.path.insert(0, _root)\n"
    "    break\n"
)

# Drop the __future__ import (must be first statement; unneeded on py3.12).
attack_body = "\n".join(
    ln for ln in ATTACK.splitlines() if ln.strip() != "from __future__ import annotations"
)
embedded = PREAMBLE + "\n" + attack_body
b64 = base64.b64encode(embedded.encode("utf-8")).decode("ascii")


def code_cell(src: str) -> dict:
    return {
        "cell_type": "code",
        "source": src,
        "metadata": {},
        "outputs": [],
        "execution_count": None,
    }


def md_cell(src: str) -> dict:
    return {"cell_type": "markdown", "source": src, "metadata": {}}


setup_src = (
    "import sys, glob\n"
    "from pathlib import Path\n"
    "sys.argv = [sys.argv[0]]  # avoid argparse conflicts in the SDK\n"
    "for candidate in glob.glob('/kaggle/input/**/kaggle_evaluation', recursive=True):\n"
    "    dataset_root = str(Path(candidate).parent)\n"
    "    if dataset_root not in sys.path:\n"
    "        sys.path.insert(0, dataset_root)\n"
    "    print('Dataset root:', dataset_root)\n"
    "    break\n"
    "print('Setup complete')\n"
)

write_src = (
    "import base64\n"
    f'ATTACK_B64 = "{b64}"\n'
    "with open('/kaggle/working/attack.py', 'w', encoding='utf-8') as f:\n"
    "    f.write(base64.b64decode(ATTACK_B64).decode('utf-8'))\n"
    "print('attack.py written to /kaggle/working/attack.py')\n"
    "# quick sanity: it imports and produces candidates\n"
    "import importlib.util, sys as _s\n"
    "spec = importlib.util.spec_from_file_location('attack', '/kaggle/working/attack.py')\n"
    "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
    "algo = m.AttackAlgorithm(); cands = algo.run(env=None, config=None)\n"
    "print('candidate count:', len(cands))\n"
)

serve_src = (
    "import os, csv\n"
    "RERUN = os.getenv('KAGGLE_IS_COMPETITION_RERUN') is not None\n"
    "# At commit (not the scored rerun) force the deterministic agent so the local\n"
    "# gateway needs no GGUF models/internet and still exercises the replay pipeline.\n"
    "# During the real rerun KAGGLE_IS_COMPETITION_RERUN is set; run() serves and the\n"
    "# hidden gateway uses the real models -- this env var is not touched there.\n"
    "if not RERUN:\n"
    "    os.environ['AICOMP_MODEL_NAMES'] = 'deterministic'\n"
    "import kaggle_evaluation.jed_attack_134815.jed_attack_inference_server as srv\n"
    "srv.JEDAttackInferenceServer().run()\n"
    "# The commit-time local gateway writes submission.csv with the single Id\n"
    "# 'deterministic_public', which fails Kaggle's submit-time format gate (it expects\n"
    "# gpt_oss_public/private and gemma_public/private). Overwrite with the four required\n"
    "# rows so the submission validates; the hidden rerun regenerates submission.csv with\n"
    "# real scores and skips this branch, so real scores are never clobbered.\n"
    "if not RERUN:\n"
    "    with open('/kaggle/working/submission.csv', 'w', newline='') as f:\n"
    "        w = csv.writer(f)\n"
    "        w.writerow(['Id', 'Score'])\n"
    "        for rid in ('gpt_oss_public', 'gpt_oss_private', 'gemma_public', 'gemma_private'):\n"
    "            w.writerow([rid, 0.0])\n"
    "    print('submission.csv overwritten with format-gate placeholder rows')\n"
)

nb = {
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12.12"},
        "kaggle": {
            "accelerator": "nvidiaTeslaT4",
            "dataSources": [
                {"sourceId": 134815, "sourceType": "competition"}
            ],
            "isGpuEnabled": True,
            "isInternetEnabled": False,
            "language": "python",
            "sourceType": "notebook",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 4,
    "cells": [
        md_cell("# JED Attack \u2014 SECRET_MARKER exfiltration probe (v1)\n"
                "Writes `attack.py` (blind guardrail-bypass exfil) and serves the JED inference server."),
        code_cell(setup_src),
        code_cell(write_src),
        code_cell(serve_src),
    ],
}

out = ROOT / "submission_notebook.ipynb"
out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print("wrote", out)
print("embedded attack.py bytes:", len(embedded), "| b64 len:", len(b64))
