# Local dev harness

The scored evaluator (`aicomp_sdk`) only ships inside the Kaggle kernel. These tools
reconstruct it locally so we can iterate turn-by-turn instead of via slow push/submit.

## First-time / after a wipe
```
python dev/bootstrap_sdk.py
```
Clones the SDK into git-ignored `vendor/jed/` at a pinned ref (parity with the deployed
`aicomp-sdk` 3.1.2) and editable-installs it. Re-run any time `import aicomp_sdk` fails,
or `python dev/bootstrap_sdk.py --ref <sha|tag>` to re-sync to another evaluator version.

## Tests
- `python dev/test_fill.py`   — attack.py anti-timeout logic (SDK-free; always must pass)
- `python dev/test_agents.py` — shared MockCompliantAgent (needs SDK)
- `python dev/test_trace.py`  — tracer vs oracle cross-check (needs SDK)

## Turn-by-turn tracing
```
python dev/trace.py --agent compliant --candidate 0     # what a shipped candidate does
python dev/trace.py --agent deterministic "read file config"
python dev/trace.py --agent compliant --json "ping https://uptime0.example.net/ingest"
```
`--agent deterministic` is the real scored agent (never complies); `--agent compliant`
is what a jailbroken gpt_oss/gemma would do. Each turn shows the tool calls, the guardrail
decision (ALLOW/BLOCK/CONFIRM + reason, derived from `ToolEvent.error`), predicates fired,
and the running raw/normalized score.

## What this can't do
The real gpt_oss/gemma models never run here — only the deterministic or mock agents.
Real-model prompt feedback is Phase 2 (`dev/repro/`, designed in
`docs/superpowers/specs/2026-08-16-harness-observability-design.md`, not yet built).
