# Re-pointing the repro harness onto the evaluator's GGUF backend

**Date:** 2026-08-18 · **Status:** approved design, not yet implemented
**Supersedes the open item in** `dev/repro/README.md` ("whether to re-point this harness
at the mounted `gguf_model_server` specs").

## Problem

`dev/repro/` runs attack candidates through the real SDK environment, guardrail and
scoring, and dumps per-candidate observability JSON. But it builds its agents with
`aicomp_sdk.agents.factory.build_agent_factory`, which constructs **HF Transformers**
backends. The deployed evaluator does not: `jed_attack_gateway.py` routes both scored
rows to dedicated `GgufModelServer`s running **llama.cpp on Q4_K_M GGUF weights**, and
falls back to `build_agent_factory` only for `deterministic`.

So the harness currently measures a stack the competition does not use.

## What is already verified

Measured in kernel `adostie3/jed-gguf-feasibility-probe` (2026-08-17), not inferred:

| Fact | Value |
|---|---|
| `llama_cpp` on the Kaggle GPU image | **absent**; `pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124` installs in 71 s |
| GPU offload after that install | `llama_cpp 0.3.35`, `llama_supports_gpu_offload() == True` |
| Kernel environment | Python 3.12.13, torch 2.10.0+cu128, Tesla T4 15.6 GB, `/kaggle/temp` ~1.1 TB free |
| `GgufModelServer(SPEC).load_model()` | 48 s (`gpt_oss`), 125 s (`gemma`) — download *and* llama.cpp load |
| Generation at the spec's real `max_new_tokens=1024` | ~1–2 s (`gpt_oss`), ~0.7–0.9 s (`gemma`) |
| Weights on disk | `gpt-oss-20b-Q4_K_M.gguf` 11.62 GB · `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf` 16.95 GB |
| Resident VRAM after gemma load at `n_gpu_layers=-1` | **9.8 GB of 15.4 GB** — both rows fit a T4 |
| Structured `tool_calls` from llama.cpp | **none** on either row; the agent's *text parser* recovers every call |

### The four fidelity gaps, re-ranked by this evidence

1. **Request construction** (not in the original spec). `Gemma4Agent.__init__` swaps its
   request builder when the backend is a `LlamaCppChatTemplateBackend`
   (`gemma4_agent.py:280`, `_build_gemma4_request` → `_build_default_hf_request`). This
   fires on *every* call, making it the widest-acting gap.
2. **Quantization.** HF bf16/auto vs llama.cpp Q4_K_M — different generations.
3. **Weight-path env vars.** The harness sets `GEMMA4_MODEL_PATH`; the evaluator reads
   `GEMMA_MODEL_PATH`. `GPT_OSS_MODEL_PATH` collides by name but means a *directory* to
   the HF builder and a *`.gguf` file* to the server.
4. **`gemma` tool-call parsing.** Real but narrower than first believed.
   `KaggleGemma4ToolCallParser` differs from the SDK parser in exactly one branch: an
   arguments blob starting with `{` goes to `normalize_tool_arguments` (`json.loads`)
   instead of `_parse_gemma4_arguments`. Since `_GEMMA4_TOOL_CALL_PATTERN` consumes the
   braces, that only happens on *doubled* braces (`call:f{{"a":1}}`). On gemma's observed
   native format both parsers agree exactly. It flips the sign when it fires; it does not
   fire on every call.

## Goals

- Run the two scored rows through the evaluator's own `GgufModelServer` / `GgufModelSpec`,
  so results carry the same quantization, parser, request builder and weight paths.
- Load the llama.cpp backend **once per run**, not once per candidate.
- Preserve today's per-candidate `candidate_i.debug.jsonl` output.
- Keep the HF path available for side-by-side comparison.
- Keep the module importable, and its tests runnable, on a dev box with no mount, no
  weights and no `llama_cpp`.

## Non-goals

- Reproducing the gateway's `remote_agent` serialize/deserialize hop. Every gap measured
  lives below that transport; an adapter for it is unjustified complexity today.
- Changing `attack.py` or the competition submission notebook. Different artifact,
  different rules.
- Submitting anything. This harness writes no `submission.csv` and must never be submitted.

## Design

### 1. `models.py` — `ModelSession`

```python
GGUF_SERVER_MODULES = {
    "gpt_oss": "kaggle_evaluation.jed_attack_134815.gpt_oss_model_server",
    "gemma":   "kaggle_evaluation.jed_attack_134815.gemma_model_server",
}

class ModelSession:
    def __init__(self, row_id: str, backend: str = "gguf", *, server_factory=None): ...
    def open(self) -> "ModelSession": ...
    def agent_factory(self, debug_sink) -> Callable[[], Any]: ...
    def close(self) -> None: ...
    def __enter__(self); def __exit__(self, *exc)
```

`open()` on the GGUF path imports the row's server module, reads its `SPEC`, constructs
`GgufModelServer(spec)` and calls `load_model()`. **Every `kaggle_evaluation` import
happens inside the method**, never at module scope — the package does not exist on the
dev box and a top-level import would break the entire local test suite.

`agent_factory(sink)` returns a zero-arg callable that builds a *fresh* agent via
`spec.create_agent(llm_backend)`, where `llm_backend` is the already-loaded
`LlamaCppChatTemplateBackend` object. Note the two senses of "backend" in this
document: the `backend` *argument* is the `gguf`/`hf` selector, while `llm_backend`
is the loaded llama.cpp object. They are never the same thing.

Backend selection:

| row | `--backend gguf` (default) | `--backend hf` |
|---|---|---|
| `gpt_oss` | mounted `GgufModelSpec` | `build_agent_factory("gpt_oss")` |
| `gemma` | mounted `GgufModelSpec` | `build_agent_factory("gemma_4")` |
| `deterministic` | `build_agent_factory("deterministic")` | same |

`deterministic` has no GGUF spec and always uses `build_agent_factory`, mirroring the
evaluator's own dispatch.

**One documented private access.** To build a fresh agent per candidate we need the
*backend* object, but `GgufModelServer` exposes only `load_model()`, which returns the
`llm`. `open()` therefore reads `server._backend` after loading, guarded by an explicit
error if it is `None`. The alternative — re-implementing `_resolve_model_path`'s env
override and `hf_hub_download` logic locally — would recreate exactly the drift this
re-point exists to remove. One private read is the smaller cost, and the guard turns a
future SDK change into a clear message instead of an `AttributeError` on `None`.

`WEIGHT_ENV` stays as-is for the HF path. The GGUF path never restates env-var names: it
reads `spec.model_path_env_var` / `repo_env_var` / `file_env_var` from the mounted spec,
so it cannot drift from the evaluator.

### 2. `debug_sink.py` — inject a caller-supplied sink

`SPEC.create_agent` is a lambda taking no `debug_sink`, so the sink cannot be passed as an
argument on the GGUF path. The existing monkeypatch is the only injection point, but today
it installs only a sink it constructs itself from a path. Split it:

```python
def install_sink(sink) -> None:          # NEW: patch targets to use THIS sink object
def install_default_sink(path=None):     # unchanged behavior, reimplemented on install_sink
def uninstall_default_sink() -> None:    # unchanged
```

`agent_factory(sink)` calls `install_sink(sink)` and then constructs, so each candidate
still writes its own `candidate_i.debug.jsonl`. `close()` calls `uninstall_default_sink()`.

### 3. `runner.py` — session around the loop

`run_repro` gains `backend: str = "gguf"`. When no `resolve` is injected it opens a single
`ModelSession` for the whole candidate loop and uses `session.agent_factory`; the session
is closed in a `finally`. The existing `resolve` injection seam is unchanged, so every
current CPU test keeps working without modification.

This is the change that makes the re-point viable: `runner.py` calls `resolve` once per
candidate, so a naive re-point would reload 11–17 GB of weights per candidate.

### 4. Notebook and push script

- `build_repro_notebook.py`: prepend a cell that sets `HF_HOME=/kaggle/temp/hf` and
  pip-installs the cu124 wheel when `llama_cpp` is missing. `HF_HOME` must not point
  inside `/kaggle/working` — that directory is committed as kernel output and these files
  exceed 11 GB.
- `push_repro_kernel.py`: add `--backend`; set `enableInternet: true` for GGUF runs (pip
  install + HF download). `--weights` continues to work, now writing the spec's
  `model_path_env_var`, which is the route that keeps internet off when weights are
  pre-staged as a data source.

### 5. Error handling

Every failure mode gets an actionable message rather than a raw traceback:

| Condition | Message |
|---|---|
| `llama_cpp` missing | the exact `pip install ... --extra-index-url ...cu124` command |
| `kaggle_evaluation` not importable | competition data source is not attached to this kernel |
| `server._backend` is `None` after `load_model()` | `GgufModelServer` shape changed; re-read the mounted source |
| unknown `row_id` or `backend` | list the valid values |

## Testing

TDD. The `server_factory` seam lets every test run locally with no mount, no weights and
no `llama_cpp`.

New tests in `dev/repro/test_models.py`:

1. the llama.cpp backend is loaded **exactly once** across N `agent_factory` calls
2. each `agent_factory` call yields a **distinct** agent instance
3. the constructed agent receives the sink that was passed to `agent_factory`
4. `close()` calls `server.unload()` and restores the patched `__init__`s
5. `--backend hf` still routes to `build_agent_factory` with today's selections
6. row → server-module mapping asserted as strings, with no import attempted
7. unknown row id and unknown backend both raise, listing the valid values

New test in `dev/repro/test_debug_sink.py`:

8. `install_sink(sink)` causes an agent constructed with no `debug_sink` to use `sink`

Regression: all 8 existing test scripts must still pass (`dev/repro/test_*.py` ×5,
`dev/test_fill.py`, `dev/test_agents.py`, `dev/test_trace.py`), run one at a time — the
full sweep exceeds a 2-minute tool timeout.

## Acceptance

Local tests are necessary but **not** sufficient: this repo has twice shipped locally
green code that failed in-kernel (a `PYTHONPATH` that existed only in the parent process,
and a poll loop that exited on a status-case mismatch). Acceptance therefore requires a
real Kaggle run:

- `python dev/push_repro_kernel.py --model gpt_oss --backend gguf --gpu --candidates 4`
- the kernel returns `candidate_*.json`, `candidate_*.debug.jsonl` and `summary.json`
- the log shows the llama.cpp backend loaded **once**, not four times
- each candidate's debug JSONL is non-empty and distinct

## Risks

- **Kernel wall-clock.** ~1–2 s per generation × up to 8 tool hops × N candidates, plus a
  48–125 s load. Fine at the small N used for validation; size deliberately before any
  large run.
- **Comparisons move two variables.** Reproducing the llama.cpp request builder is
  automatic (it keys off backend type), so an HF-vs-GGUF side-by-side differs by both
  quantization and prompt construction. Read those results accordingly.
- **Private attribute.** `server._backend` is guarded, but a future SDK re-sync could
  still require a one-line fix.
