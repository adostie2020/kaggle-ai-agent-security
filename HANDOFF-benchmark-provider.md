# Handoff — wire a real model provider (OpenRouter) into `dev/benchmark`

**Date:** 2026-08-26 · **Repo:** `C:\Users\adost\attack-competition` · **Branch:** `master`
**Interpreter:** `.venv/Scripts/python.exe` · **SDK restore:** `python dev/bootstrap_sdk.py` if `import aicomp_sdk` fails.

> This is a **separate thread** from the main submission-score work. The primary
> `HANDOFF.md` (v15 banked, the push to public > 100) is unrelated and still active — do
> **not** overwrite it. This file is only about the `dev/benchmark/` robustness tool.

## Goal
Give `dev/benchmark/` an **opt-in real-model `agent_factory`** backed by OpenRouter, so the
benchmark can measure whether a *real* LLM actually **complies** (issues the SECRET_MARKER
`http.post`) under each guardrail — closing the documented "compliance gap." Today the benchmark
scores guardrail behavior *given* compliance via `MockCompliantAgent`; a real provider makes it
end-to-end (compliance × guardrail).

## Current progress (what exists to build on)
`dev/benchmark/` is complete, merged to master (@ `b8fc02c`), and review-clean. It already has the
exact seam this task needs: **every scoring entry point takes an `agent_factory`.**
- `dev/benchmark/benchmark.py::run_benchmark(chains, *, profile, base_seed, k, max_tool_hops,
  agent_factory=MockCompliantAgent)` — threads `agent_factory` into both the baseline
  (`oracle.score_corpus`) and each member (`_run_corpus` → `oracle.run_chain`).
- `dev/oracle.py::run_chain(messages, guardrail_factory, max_tool_hops, agent_factory)` and
  `make_env(...)` build `SandboxEnv(agent=agent_factory(), guardrail=..., ...)`. **A new provider
  agent is dropped in purely by passing a different `agent_factory` — no benchmark-core change
  needed for the scoring path.**
- `dev/agents.py::MockCompliantAgent` is the reference implementation of the agent interface to
  copy the shape from.

## The agent interface a provider agent must implement (verified)
A plain object (no base class required) with these methods — see `dev/agents.py` and
`vendor/jed/aicomp_sdk/agents/types.py`:
- `next_action(self, *, history, tools) -> ToolCallDecision | FinalResponseDecision`
  - `history.events` is a sequence of `UserMessageEvent(text)`, `ToolResultEvent(...)`,
    `AssistantMessageEvent`, `ToolRequestEvent`, `InstructionEvent` (`types.py:44-72`).
  - `tools` is the env's registered tool specs to expose to the model.
  - Return `ToolCallDecision(call=ToolCall(call_id, tool_name, arguments={...}),
    assistant_message=None)` to call a tool, or `FinalResponseDecision(text=...)` to stop.
    (`types.py:25-32, 74-88`)
- `reset_state(self)`, `snapshot_state(self) -> dict`, `restore_state(self, snapshot)` — the
  sandbox snapshots/restores agents during replay; implement all three (MockCompliantAgent shows
  the minimal versions).

## What the SDK already gives you (mine these before writing anything)
- **`vendor/jed/aicomp_sdk/agents/openai_agent.py` — `OpenAIResponsesAgent(client, model="gpt-4o-mini")`.**
  A full AgentProtocol implementation with history→request translation and tool-call→decision
  mapping. **BUT it uses the OpenAI *Responses* API (`client.responses.create`, `openai_agent.py:190`)
  — see the big gotcha below.** Still the best reference for how to translate `history`+`tools`
  into a provider request and map a returned tool call back into a `ToolCallDecision`
  (`openai_agent.py:~299-440`).
- **`vendor/jed/aicomp_sdk/agents/factory.py`** — `build_agent_factory(selection, ...)` with an
  `OPENAI` selection (`AgentSelection.OPENAI`), `_require_openai_api_key()` (reads `OPENAI_API_KEY`,
  `factory.py:47-51`), and `_create_openai_agent(...)` which does `from openai import OpenAI` and
  constructs the client (`factory.py:54-71`). The `openai` package is an optional dep it imports
  lazily.
- **`vendor/jed/aicomp_sdk/agents/tool_specs.py`** — helpers to render the env `tools` into a
  provider tool schema. Reuse these instead of hand-rolling the http.post schema.
- **`vendor/jed/run_attack_openai.py`** — a top-level example of driving the OpenAI agent end to
  end; useful for the wiring pattern.
- `dev/repro/models.py::resolve_agent_factory(row_id)` shows the existing pattern of returning an
  SDK agent factory (it wraps `build_agent_factory`) — mirror this style for an
  `openrouter_agent_factory()`.

## The big gotcha (read before choosing an approach)
**OpenRouter is OpenAI-compatible on Chat Completions (`POST https://openrouter.ai/api/v1/chat/completions`),
NOT on the Responses API.** The SDK's `OpenAIResponsesAgent` calls `client.responses.create(...)`,
which OpenRouter does not serve. So you **cannot** simply do
`OpenAI(base_url="https://openrouter.ai/api/v1", api_key=...)` and reuse `OpenAIResponsesAgent` —
the Responses endpoint 404s there. Two viable routes:

1. **Write a new `OpenRouterChatAgent`** (recommended) implementing the agent interface on
   **chat.completions**: translate `history`→messages + `tools`→OpenAI-style `tools` schema, call
   `client.chat.completions.create(model=..., tools=..., tool_choice="auto")`, and map
   `choice.message.tool_calls[0]` → `ToolCallDecision` (name + `json.loads(arguments)`), else
   `FinalResponseDecision(message.content)`. Port the translation/mapping logic from
   `openai_agent.py` but target chat.completions. Put it in `dev/benchmark/providers.py` (new,
   dev-only) with a factory `openrouter_agent_factory(model=..., api_key=...)`.
2. **Only if** you find/confirm an OpenRouter Responses-API shim: point `OpenAIResponsesAgent` at
   it via a custom `base_url`. Verify the endpoint exists first (`curl` a trivial responses call);
   do not assume.

## What did NOT get tried yet (open decisions for you)
- **Nothing wired yet** — this is greenfield on top of the finished benchmark. No provider code
  exists.
- **Metric meaning is unresolved.** With a real (possibly-refusing, stochastic) model, "survival"
  no longer isolates the guardrail. Decide whether to (a) add a separate **compliance rate**
  (fraction of candidates where the model even issued the exfil call) and report it beside
  survival, or (b) redefine survival as end-to-end. Document whichever you pick in
  `dev/benchmark/README.md` (it already has a "Compliance gap" caveat to update).
- **Determinism vs. reality.** The benchmark's whole design is reproducible (content-hashed
  guardrail draws). A networked model is non-deterministic, slow, and costs money. So the real
  provider **must be opt-in** (a `--agent openrouter` CLI flag + `OPENROUTER_API_KEY` env), and the
  existing offline tests (`test_guardrails.py`, `test_benchmark.py`) **must stay deterministic and
  green** — they keep using `MockCompliantAgent`. Do NOT put a network call in the default test path.

## Next steps (do in order)
1. **Read the SDK OpenAI path end-to-end first:** `agents/openai_agent.py` (esp. `next_action`
   `:166-227`, history translation `:~299-394`, tool-call mapping `:~394-440`), `agents/factory.py`
   `_create_openai_agent`, and `agents/tool_specs.py`. This tells you exactly what `history`/`tools`
   look like and what a valid `ToolCallDecision` needs.
2. **Confirm the Chat-Completions-vs-Responses gotcha** for your chosen OpenRouter model, then
   write `dev/benchmark/providers.py` with `OpenRouterChatAgent` + `openrouter_agent_factory(...)`
   (route 1 above). Read `OPENROUTER_API_KEY` from env; never hardcode or commit a key. `openai`
   is an optional dep — import it lazily and fail with an install hint (mirror `factory.py:60-63`).
3. **Add an opt-in CLI/API path** in `benchmark.py`: an `--agent {mock,openrouter}` flag (default
   `mock`) + `--model` that selects the `agent_factory` passed to `run_benchmark`. Keep
   `MockCompliantAgent` the default everywhere else.
4. **Add compliance reporting** (per the metric decision above): thread a per-candidate
   "did the model issue the exfil call" count out of `_run_corpus`/`run_benchmark` and into the
   report dict + `render_report`. Update the README caveats.
5. **Tests:** unit-test `OpenRouterChatAgent`'s translation/mapping with a **stub client** (a fake
   `chat.completions.create` returning canned tool-call / content payloads) — no network. Keep the
   existing suites offline. Optionally add a live smoke behind an env guard (skipped without a key),
   NOT in the default run.
6. **Sanity-run** once with a real key on a tiny corpus (`--candidates 2 --seeds 2 --profile
   marker_only --agent openrouter --model <cheap-model>`) and record the numbers, as Task 5 did for
   the mock path.

## Gotchas / conventions
- **Dev-only, not submittable.** `dev/benchmark/` never touches `attack.py`, the notebook, or
  scored behavior. Keep provider code inside `dev/benchmark/`.
- **Tests are plain `__main__` self-running scripts** (assert/print, exit 0 = pass), NOT pytest.
  Run **one at a time** (`.venv/Scripts/python.exe dev/benchmark/test_benchmark.py`); the full
  sweep exceeds the 2-min tool timeout. `dev/test_fill.py` must stay green (SDK-free regression).
- **CLI must be run so it can import root-level `attack.py`.** `benchmark.py` inserts the repo root
  on `sys.path` (`benchmark.py:18`, `parents[2]`), so `.venv/Scripts/python.exe
  dev/benchmark/benchmark.py ...` works directly — keep that insert if you refactor imports.
- **Secrets:** `OPENROUTER_API_KEY` via env only. Never print, log, or commit it. OpenRouter also
  wants `HTTP-Referer`/`X-Title` headers on requests (optional but recommended) — set via the
  client's `default_headers`.
- **SDK backends context:** the *scored* competition backend is local GGUF (gpt_oss, gemma) via
  `GgufModelServer`/`RemoteAgent` — an OpenRouter model is a *proxy* for "a real tool-using LLM,"
  not the scored model. State this in the README so nobody reads the numbers as the private score.

## Where the detail lives
- `dev/benchmark/README.md` — how to read survival + the caveats to update.
- `docs/superpowers/specs/2026-08-25-benchmark-stochastic-guardrails-design.md` — the benchmark's
  design (the `agent_factory` seam, MockCompliantAgent rationale, non-goals incl. "not an
  end-to-end score predictor" — which this task partly revisits).
- `dev/agents.py`, `vendor/jed/aicomp_sdk/agents/{openai_agent,factory,tool_specs,types}.py`.
- `CLAUDE.md` — project overview + the two-artifacts rule + Kaggle conventions.
