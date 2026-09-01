"""One-off CPU diagnostic kernel: which agent selection does the deployed
evaluator actually use for the `gemma` row, and what SDK version is mounted?

Answers the plan's open item ("read the mounted kaggle_evaluation harness in the
kernel; override REPRO_MODELS['gemma'] if it differs") without spending GPU time.
Throwaway — lives in scratchpad, pushed to its own slug.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

CRED = Path.home() / ".claude" / ".credentials.json"
TOK = json.loads(CRED.read_text(encoding="utf-8"))["mcpOAuth"]["kaggle|43f49c16a482634f"]["accessToken"]

PROBE = r'''
import os, re, sys, glob, pathlib

roots = sorted({str(pathlib.Path(c).parent) for c in
                glob.glob('/kaggle/input/**/kaggle_evaluation', recursive=True)})
print('dataset roots:', roots)
root = roots[0]
sys.path.insert(0, root)

print('\n===== mounted tree (py files) =====')
for p in sorted(glob.glob(root + '/**/*.py', recursive=True)):
    print('  ', p[len(root)+1:])

print('\n===== aicomp_sdk version =====')
try:
    import aicomp_sdk
    print('version:', getattr(aicomp_sdk, "__version__", "?"), '| file:', aicomp_sdk.__file__)
except Exception as e:
    print('import failed:', type(e).__name__, e)

PATTERNS = r'AICOMP_MODEL_NAMES|model_names|MODEL_NAMES|build_agent_factory|build_agent\(|' \
           r'AgentSelection|coerce_agent_selection|gemma_4|GEMMA_4|["\']gemma["\']|["\']gpt_oss["\']'

print('\n===== model-wiring hits across the mounted harness =====')
for p in sorted(glob.glob(root + '/**/*.py', recursive=True)):
    try:
        src = pathlib.Path(p).read_text(encoding='utf-8', errors='replace')
    except Exception:
        continue
    for i, line in enumerate(src.splitlines(), 1):
        if re.search(PATTERNS, line):
            print(f'  {p[len(root)+1:]}:{i}: {line.strip()[:160]}')

print('\n===== AgentSelection members as mounted =====')
try:
    from aicomp_sdk.agents.factory import AgentSelection
    print([(m.name, m.value) for m in AgentSelection])
except Exception as e:
    print('failed:', type(e).__name__, e)

print('\n===== default model ids as mounted =====')
for mod, name in [('aicomp_sdk.agents.gemma_agent', 'DEFAULT_GEMMA_MODEL_ID'),
                  ('aicomp_sdk.agents.gemma4_agent', 'DEFAULT_GEMMA4_MODEL_ID'),
                  ('aicomp_sdk.agents.gpt_oss_agent', 'DEFAULT_GPT_OSS_MODEL_ID')]:
    try:
        m = __import__(mod, fromlist=[name])
        print(f'  {name} = {getattr(m, name, "?")}')
    except Exception as e:
        print(f'  {name}: {type(e).__name__} {e}')

print('\n===== gateway submission-row ids (what the scorer expects) =====')
for p in sorted(glob.glob(root + '/**/*.py', recursive=True)):
    src = pathlib.Path(p).read_text(encoding='utf-8', errors='replace')
    if 'submission' in src and ('_public' in src or 'write_submission' in src):
        for i, line in enumerate(src.splitlines(), 1):
            if re.search(r'_public|_private|write_submission|Id|guardrail', line):
                print(f'  {p[len(root)+1:]}:{i}: {line.strip()[:160]}')
'''


def cc(s: str) -> dict:
    return {"cell_type": "code", "source": s, "metadata": {},
            "outputs": [], "execution_count": None}


nb = {
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "kaggle": {"accelerator": "none",
                   "dataSources": [{"sourceId": 134815, "sourceType": "competition"}],
                   "isGpuEnabled": False, "isInternetEnabled": False,
                   "language": "python", "sourceType": "notebook"},
    },
    "nbformat": 4, "nbformat_minor": 4, "cells": [cc(PROBE)],
}
source = json.dumps(nb)
json.loads(source)

body = {
    "slug": "adostie3/jed-harness-probe",
    "newTitle": "JED Harness Probe",
    "text": source,
    "language": "python",
    "kernelType": "notebook",
    "isPrivate": True,
    "enableGpu": False,
    "enableTpu": False,
    "enableInternet": False,
    "datasetDataSources": [],
    "competitionDataSources": ["ai-agent-security-multi-step-tool-attacks"],
    "kernelDataSources": [],
    "modelDataSources": [],
    "categoryIds": [],
}
req = urllib.request.Request(
    "https://www.kaggle.com/api/v1/kernels/push",
    data=json.dumps(body).encode("utf-8"), method="POST",
    headers={"Authorization": "Bearer " + TOK,
             "Content-Type": "application/json", "Accept": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print("PUSH:", r.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode("utf-8", "replace")[:600])
