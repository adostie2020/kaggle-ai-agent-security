"""Restore the local aicomp_sdk harness: clone/pin the SDK source into a persistent,
git-ignored vendor/ dir and editable-install it into the active venv.

Fixes the recurring "scratchpad got wiped" failure: the previous editable install
pointed at a session scratchpad that was cleaned up, leaving a dangling pointer.
Re-run this any time `import aicomp_sdk` fails, or to re-sync to a new pinned ref.

Usage:
    python dev/bootstrap_sdk.py                  # default pinned ref (3.1.2 parity)
    python dev/bootstrap_sdk.py --ref <sha|tag>  # re-sync to another ref
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "jed"
SDK_REPO_URL = "https://github.com/mbhatt1/competitionscratch.git"
# Current master HEAD; its pyproject packages aicomp-sdk 3.1.2, matching the deployed
# Kaggle evaluator. Pinned (not floating on master) so local scoring stays in parity
# even after upstream moves. Re-pin with --ref when a submission disagrees with local.
DEFAULT_REF = "30c769419a09f3dc64d5606a0a097b8a2a61c110"
EXPECTED_VERSION = "3.1.2"

VERIFY_SNIPPET = (
    "import importlib.metadata as m;"
    "v = m.version('aicomp-sdk');"
    "import aicomp_sdk;"
    "from aicomp_sdk.core.env.sandbox import SandboxEnv;"
    "from aicomp_sdk.guardrails.optimal import Guardrail;"
    "from aicomp_sdk.agents.deterministic_agent import VulnerableDeterministicAgent;"
    "from aicomp_sdk.scoring import score_attack, SEVERITY_W;"
    "from aicomp_sdk.core.predicates import eval_predicates;"
    "from aicomp_sdk.core.cells import cell_signature;"
    "print('aicomp-sdk version:', v);"
    f"assert v == '{EXPECTED_VERSION}', 'VERSION DRIFT: got ' + v + ' expected {EXPECTED_VERSION}';"
    "print('READY: aicomp_sdk imports OK')"
)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=DEFAULT_REF)
    ap.add_argument("--repo", default=SDK_REPO_URL)
    args = ap.parse_args()

    VENDOR.parent.mkdir(parents=True, exist_ok=True)
    if not (VENDOR / ".git").exists():
        run(["git", "clone", args.repo, str(VENDOR)])
    else:
        run(["git", "fetch", "--all", "--tags"], cwd=VENDOR)
    run(["git", "checkout", args.ref], cwd=VENDOR)
    run([sys.executable, "-m", "pip", "install", "-e", str(VENDOR)])

    # Verify in a FRESH interpreter so a previously-failed import isn't cached.
    print("--- verifying install ---")
    proc = subprocess.run([sys.executable, "-c", VERIFY_SNIPPET])
    if proc.returncode != 0:
        print("FAILED: verification did not pass", file=sys.stderr)
        return 1
    print("bootstrap complete; ref:", args.ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
