# Harness observability & local turn-by-turn — design

**Date:** 2026-08-16
**Status:** Approved for planning
**Scope:** Developer tooling only. No change to `attack.py` scored behavior.

## Problem

Our only feedback from the real evaluator is what Kaggle returns per submission,
and that is almost nothing:

- A scored run yields **one float per `(model × guardrail)` row** on success.
- A failed run yields either a generic `"incorrect format…"` string, or — for the
  **private** phase — a bare `error` with **no reason field at all**. ("v13 private
  timed out" was *inferred*, never reported.)
- The hidden rerun's **stdout/logs are not returned** to us; only `submission.csv`.
- At commit time internet is off and we force the *deterministic* agent, so the real
  `gpt_oss` / `gemma` models **never run anywhere we can watch them**.

Submission history that establishes this (comp 134815,
`ai-agent-security-multi-step-tool-attacks`):

| Build | Date | Status | Feedback we got |
|-------|------|--------|-----------------|
| v14 (current) | 2026-08-16 | pending | none yet |
| v13 | 2026-08-04 | error | `publicScore 22.540`; private phase errored, no description |
| v12 | 2026-08-04 | error | generic "incorrect format" |
| probe v1 / v1 | 2026-08-03 | error | generic "incorrect format" |

We are effectively debugging blind. We want two things: a **fast local loop** that
runs the real env / guardrail / scoring turn by turn, and a way to see **real-model
prompt feedback** that the hidden rerun hides from us.

## Key facts the design rests on

1. **The local harness was already reverse-engineered once.** `.venv` still carries an
   *editable* install of `aicomp_sdk 3.1.2`, but it points at a previous session's
   scratchpad (`…/7bbe48d3-…/scratchpad/jed/aicomp_sdk`), which was cleaned up. The
   source is gone; the pointer is dangling. Re-establishing the source in a persistent
   location is the whole unblock — this is proven feasible, not a research question.
2. **The SDK is public and cloneable.** `github.com/mbhatt1/competitionscratch`,
   default branch `master` (there is no `main`), with `aicomp_sdk/` at the repo root, so
   `pip install -e <clone>` works directly.
3. **The evaluator evolves.** The repo carries branches like
   `fix/evaluator-scoring-fairness`, `ovallis/harden-eval-timeouts`,
   `ovallis/fix-secret-scoring`. Local parity with the *deployed* scorer therefore
   requires pinning a ref that matches the SDK version Kaggle runs (our wiped install
   was `3.1.2`), never floating on `master`.
4. **Both target models are open-weight GGUF.** `gpt_oss` = GPT-OSS 20B, `gemma` =
   Gemma 4 26B-A4B-it, both llama.cpp on a single T4 (≤16 GB). We can obtain the same
   weights and run the real agent ourselves — so real-model behavior does **not**
   require Kaggle's hidden rerun.
5. **The local SDK gives real env + real `OptimalGuardrail` + real predicate / cell /
   scoring logic, but not the real models.** Locally the agent is either the
   *deterministic* one (never complies) or our *mock-compliant* one (always complies).
   Real-model behavior is Phase 2's job.

## Approach (decisions locked)

- **SDK restore:** bootstrap script + git-ignored vendored clone, editable install.
  (Chosen over pip-from-git — which is non-editable and can't be instrumented — and
  over committing the third-party tree into git.)
- **Phasing:** design both phases in this spec; **build Phase 1 now**, leave Phase 2
  (real-weights reproduction) as the next plan item.

## Phase 1 — local turn-by-turn harness (built this pass)

### New files

```
vendor/jed/               git-ignored clone of the SDK (aicomp_sdk at root), pinned ref
dev/bootstrap_sdk.py      clone/fetch @ pinned ref, editable install, self-verify
dev/agents.py             shared mock-compliant agent (extracted from validate_probe.py)
dev/trace.py              turn-by-turn observability over the real env/guardrail/scoring
dev/notebooks/step.ipynb  optional interactive stepper (stretch)
```
Plus: add `vendor/` to `.gitignore`.

### Component: `dev/bootstrap_sdk.py`

Idempotent restore of the local SDK. Steps, in order:

1. Ensure `vendor/jed/` exists: `git clone` the SDK repo if absent, else `git fetch`.
2. `git checkout` a **pinned ref** — default is the commit/tag matching the deployed
   SDK version (`3.1.2`); overridable via `--ref <ref>` or an env var. The resolved ref
   is printed so drift is visible.
3. `pip install -e vendor/jed` into the active `.venv`.
4. Self-verify: import `aicomp_sdk`, assert `__version__` equals the expected version,
   and smoke-import the names the dev tools depend on — `SandboxEnv`,
   `OptimalGuardrail`, the deterministic agent, and the scoring functions.
5. Print a one-line ready/failed status. Exit non-zero on any failure.

Re-running re-syncs to the pinned ref. This is the single command that fixes the
"scratchpad got wiped" failure permanently.

### Component: `dev/trace.py`

The turn-by-turn observability layer. Core entry point:

```
trace_chain(messages, *, agent, guardrail=OptimalGuardrail,
            max_tool_hops=8) -> TraceReport
```

For **each turn** (each `env.interact`) it captures:

- the prompt sent;
- tool events: `name`, `args`, `ok`, `source`, `side_effect`, `error`;
- the guardrail decision (ALLOW / BLOCK) and reason, **if the SDK surfaces it** (to be
  confirmed against the vendored source; if it is not exposed, this field is omitted
  rather than faked);
- predicates fired: `name`, `severity`;
- the full cell signature and the score-cell signature;
- running totals — raw, normalized, unique cells, predicate mass — **and the delta
  contributed by this turn**.

Two output modes: a rich human printer (the existing `oracle.describe()` view, extended
to per-turn score deltas) and `--json` for diffing runs against each other. Runs against
both the **deterministic** agent (ground-truth scored behavior) and the
**mock-compliant** agent (what a jailbroken model would do).

CLI:

```
python dev/trace.py --agent {deterministic,compliant} [--json] "<msg>" ["<msg2>" …]
python dev/trace.py --candidate N        # trace attack.py's Nth returned candidate
```

`--candidate N` builds the corpus via `AttackAlgorithm(...).run(...)` and traces the
Nth candidate exactly as returned, so we can see what a shipped candidate actually does.

### Component: `dev/agents.py`

Lift the mock-compliant agent out of `dev/validate_probe.py` into `dev/agents.py` so
`trace.py`, `validate_probe.py`, and `oracle.py` share one implementation. This is the
only refactor; no other rewrite of the existing dev tools.

### Component: `dev/notebooks/step.ipynb` (stretch)

A thin Jupyter front-end that calls `trace.py` to step through a chain interactively.
Optional — cut without penalty if time is short.

## Phase 2 — real-model prompt feedback (designed only, next plan item)

`dev/repro/` — a **self-controlled reproduction notebook** that reproduces the hidden
rerun with full instrumentation:

1. Mount the real `gpt_oss` + `gemma` GGUF weights as a Kaggle Model / Dataset source.
2. Instantiate the **real** SDK agent factory (llama.cpp backend) + real guardrail +
   scoring.
3. Run each attack candidate and dump a per-candidate / per-turn observability JSON to
   `/kaggle/working` — which **is returned to us at commit time**, unlike the hidden
   rerun's output.
4. The same code path runs locally if a ≥16 GB GPU is present, removing the Kaggle
   round-trip entirely.

**Open items to resolve when building Phase 2** (each affects score parity with the real
evaluator, so they are settled then, not guessed now):

- the exact GGUF weight source and quantization Kaggle uses;
- the llama.cpp version;
- the `AICOMP_MODEL_NAMES` → backend wiring (the current serve cell sets
  `AICOMP_MODEL_NAMES='deterministic'` at commit, implying an env-var model registry).

Verification requires weight downloads plus a GPU run, which is why Phase 2 is a separate
plan item rather than part of this pass.

## Testing

- **`trace.py` cross-check:** trace a known-firing mock-compliant chain; assert the
  per-turn report shows an EXFILTRATION severity-5 predicate **and** that its running
  score equals `oracle.py`'s `score_corpus` for the same chain. This checks two
  independent code paths agree.
- **Fast loop stays SDK-free:** `dev/test_fill.py` (which stubs `aicomp_sdk`) must keep
  passing without the vendored SDK installed.
- **Post-restore regression:** after `bootstrap_sdk.py` runs, `oracle.py --sweep` and
  `validate_probe.py` execute clean again — confirming the restore worked end to end.
- **`bootstrap_sdk.py`** self-verifies (import + version + smoke imports) and exits
  non-zero on failure, so it doubles as its own test.

## Non-goals

- No change to `attack.py`'s scored behavior; this is observability only.
- Do not commit the SDK tree into git (it is third-party, large, and separately
  licensed); it lives in git-ignored `vendor/`.
- Do not attempt to read the hidden rerun's logs — proven unavailable. Phase 2
  reproduces the run under our control instead.

## Risks

- **Version drift:** if Kaggle updates the deployed SDK, the pinned ref makes local
  scores diverge silently. Mitigation: the ref is an explicit, printed config knob;
  re-running `bootstrap_sdk.py --ref <new>` re-syncs. Revisit the pin whenever a
  submission's behavior disagrees with local.
- **Guardrail-reason exposure:** the ALLOW/BLOCK *reason* may not be exposed by the SDK
  surface. Handled by omitting the field when absent rather than fabricating it;
  confirmed against the vendored source during implementation.
