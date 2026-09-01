"""Push the CONFUSED_DEPUTY insurance build (cd_attack.py) as its OWN submission notebook/kernel
(Slot B), separate from the EXFIL Slot-A kernel jed-attack-probe-v1. Mirrors push_kernel.py exactly
(REST kernels/push, base64-embedded source written to /kaggle/working/attack.py, serve the JED
inference server, internet OFF, competition data source) but embeds cd_attack.py instead of attack.py
and targets slug jed-attack-cd-v1.
"""
import ast, base64, json, hashlib, urllib.request, urllib.error
from pathlib import Path

REPO = Path(r"C:\Users\adost\attack-competition")
CRED = r"C:\Users\adost\.claude\.credentials.json"
tok = json.load(open(CRED, encoding="utf-8"))["mcpOAuth"]["kaggle|43f49c16a482634f"]["accessToken"]

SLUG = "adostie3/jed-attack-cd-v1"
TITLE = "JED Attack CD v1"

# ---- Build minified-but-equivalent cd_attack.py embed (docstring/comments stripped) ----
src = (REPO / "cd_attack.py").read_text(encoding="utf-8")
lines = [l for l in src.splitlines() if l.strip() != "from __future__ import annotations"]
kept = [l for l in lines if not l.strip().startswith("#")]
body = "\n".join(kept)
mmod = ast.parse(body)
if (mmod.body and isinstance(mmod.body[0], ast.Expr)
        and isinstance(getattr(mmod.body[0], "value", None), ast.Constant)
        and isinstance(mmod.body[0].value.value, str)):
    b = body.splitlines(); del b[mmod.body[0].lineno - 1: mmod.body[0].end_lineno]
    body = "\n".join(b)
body = body.lstrip("\n")

PREAMBLE = ("import sys, glob\nfrom pathlib import Path as _Path\n"
    "for _c in glob.glob('/kaggle/input/**/kaggle_evaluation', recursive=True):\n"
    "    _root = str(_Path(_c).parent)\n    if _root not in sys.path:\n"
    "        sys.path.insert(0, _root)\n    break\n")
embedded = PREAMBLE + "\n" + body
b64 = base64.b64encode(embedded.encode("utf-8")).decode("ascii")
sha = hashlib.sha256(base64.b64decode(b64)).hexdigest()

# sanity: the embedded source parses + produces candidates env-free (the commit-time path)
ast.parse(base64.b64decode(b64).decode("utf-8"))
_ns = {}
exec(body, _ns)  # body == cd_attack.py minus docstring/comments (no /kaggle preamble)
assert len(_ns["AttackAlgorithm"]({"n_candidates": 3}).run(env=None, config=None)) == 3, \
    "embedded cd_attack.py smoke failed"

setup_src = ("import sys, glob\nfrom pathlib import Path\nsys.argv = [sys.argv[0]]\n"
    "for c in glob.glob('/kaggle/input/**/kaggle_evaluation', recursive=True):\n"
    "    r = str(Path(c).parent)\n    if r not in sys.path: sys.path.insert(0, r)\n    break\n"
    "print('Setup complete; /kaggle/input =', __import__('os').listdir('/kaggle/input'))\n")
write_src = ("import base64, hashlib\n" f'ATTACK_B64 = "{b64}"\n'
    "raw = base64.b64decode(ATTACK_B64)\n"
    f'assert hashlib.sha256(raw).hexdigest() == "{sha}", "integrity FAILED"\n'
    "open('/kaggle/working/attack.py','wb').write(raw)\n"
    "print('attack.py (CD build) written and verified,', len(raw), 'bytes')\n")
serve_src = ("import os, csv\n"
    "RERUN = os.getenv('KAGGLE_IS_COMPETITION_RERUN') is not None\n"
    "if not RERUN:\n"
    "    os.environ['AICOMP_MODEL_NAMES'] = 'deterministic'\n"
    "import kaggle_evaluation.jed_attack_134815.jed_attack_inference_server as srv\n"
    "srv.JEDAttackInferenceServer().run()\n"
    "if not RERUN:\n"
    "    with open('/kaggle/working/submission.csv', 'w', newline='') as f:\n"
    "        w = csv.writer(f)\n"
    "        w.writerow(['Id', 'Score'])\n"
    "        for rid in ('gpt_oss_public', 'gpt_oss_private', 'gemma_public', 'gemma_private'):\n"
    "            w.writerow([rid, 0.0])\n"
    "    print('submission.csv overwritten with format-gate placeholder rows')\n"
    "    print(open('/kaggle/working/submission.csv').read())\n"
    "print('working dir after run:', sorted(os.listdir('/kaggle/working')))\n")

def cc(s): return {"cell_type": "code", "source": s, "metadata": {}, "outputs": [], "execution_count": None}
nb = {"metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.12.12"},
    "kaggle": {"accelerator": "nvidiaTeslaT4",
               "dataSources": [{"sourceId": 134815, "sourceType": "competition"}],
               "isGpuEnabled": True, "isInternetEnabled": False,
               "language": "python", "sourceType": "notebook"}},
  "nbformat": 4, "nbformat_minor": 4, "cells": [cc(setup_src), cc(write_src), cc(serve_src)]}
notebook_source = json.dumps(nb)

body_req = {
    "slug": SLUG, "newTitle": TITLE, "text": notebook_source,
    "language": "python", "kernelType": "notebook", "isPrivate": True,
    "enableGpu": True, "enableTpu": False, "enableInternet": False,
    "machineShape": "NvidiaTeslaT4",
    "datasetDataSources": [], "competitionDataSources": ["ai-agent-security-multi-step-tool-attacks"],
    "kernelDataSources": [], "modelDataSources": [], "categoryIds": [],
}
data = json.dumps(body_req).encode("utf-8")
req = urllib.request.Request(
    "https://www.kaggle.com/api/v1/kernels/push",
    data=data, method="POST",
    headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json", "Accept": "application/json"})
print("slug:", SLUG, "| cd_attack.py sha:", sha, "| notebook bytes:", len(notebook_source))
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        print("PUSH RESPONSE:", r.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print("HTTP ERROR", e.code); print(e.read().decode("utf-8", "replace")[:800])
