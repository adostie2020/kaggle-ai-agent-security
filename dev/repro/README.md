# Real-model repro harness (Phase 2)

Phase 1 (`dev/trace.py`) drives the real SDK env/guardrail/scoring turn-by-turn but
only with the deterministic or mock agents. Phase 2 runs the **real** `gpt_oss` /
`gemma` agents under that same tracer and dumps per-candidate observability JSON to a
location we actually get back — so we can finally see what the real model does with
each attack candidate, which the hidden rerun hides (it returns only `submission.csv`).

This harness is **not** a competition submission. It writes no `submission.csv`.

## Pieces
- `debug_sink.py`  — JSONL sink helpers + `install_default_sink()`, a durable monkeypatch
  that makes the SDK debug sink fire even when an agent is built with `debug_sink=None`
  (driven by `AICOMP_DEBUG_SINK_PATH`). This is the re-sync-proof version of hand-editing
  the vendored agent's `debug_sink` default, and it covers both real agents.
- `models.py`      — maps a Kaggle row id (`gpt_oss`, `gemma`) to the SDK agent factory,
  wires local HF Transformers model-directory paths (`GPT_OSS_MODEL_PATH` /
  `GEMMA4_MODEL_PATH`), and fail-fast validates the backend. `gemma` defaults to the
  SDK's `gemma_4` selection.
- `runner.py`      — runs each attack candidate through `trace.trace_chain` and writes
  `candidate_i.json` + `summary.json` (+ optional raw model debug JSONL).
- `run_repro.py`   — CLI.
- `build_repro_notebook.py` — builds `repro_notebook.ipynb` for a Kaggle GPU kernel; also base64-embeds runtime dependencies (`dev/oracle.py`, `dev/trace.py`, `dev/agents.py`, `attack.py`) into the notebook so they are available in-kernel.

## Local (CPU, weights-free) smoke
```
python dev/repro/run_repro.py --self-check --candidates 3 --out dev/repro/_smoke
```
Forces the deterministic agent (no weights); proves the whole dump pipeline end to end.

## Real models — TWO BACKEND LAYERS, and this harness currently uses the wrong one

Read off the mounted competition harness (probe kernel `adostie3/jed-harness-probe` v2),
so this is measured, not inferred:

**What the evaluator actually runs.** `jed_attack_gateway.py` routes both scored rows
through dedicated model servers — `REMOTE_MODEL_SERVER_MODULES = {"gemma": …
gemma_model_server, "gpt_oss": …gpt_oss_model_server}` — and falls back to
`build_agent_factory()` only for everything else (i.e. `deterministic`). Each server is a
`GgufModelServer` wrapping `LlamaCppChatTemplateBackend.from_model_path(model_path,
n_ctx=8192, n_gpu_layers=-1)`. So the scored path is **llama.cpp GGUF, Q4_K_M**:

| row | GGUF repo / file | local override env | agent |
|-----|------------------|--------------------|-------|
| `gpt_oss` | `unsloth/gpt-oss-20b-GGUF` / `gpt-oss-20b-Q4_K_M.gguf` | `GPT_OSS_MODEL_PATH` | `GPTOSSAgent(backend)` |
| `gemma` | `unsloth/gemma-4-26B-A4B-it-GGUF` / `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf` | `GEMMA_MODEL_PATH` | `Gemma4Agent(backend, parser=KaggleGemma4ToolCallParser())` |

Both overrides take a **`.gguf` file path** (`os.path.exists`-checked), not a directory.

**What this harness runs.** `models.py` calls `build_agent_factory`, whose `gpt_oss` /
`gemma_4` branches build HF `AutoModelForCausalLM` backends
(`HF(Processor)ChatTemplateBackend.from_pretrained`, `local_files_only=True` hardcoded)
and never construct a `LlamaCppChatTemplateBackend`. On that path `*_MODEL_PATH` must be
a snapshot **directory** (`config.json`, tokenizer, `.safetensors`), and
`GEMMA4_MODEL_PATH` is the env var — note the evaluator reads `GEMMA_MODEL_PATH` instead.

**Consequences for fidelity — do not read this harness's real-model numbers as evaluator
parity until they are closed:** (1) different quantization (HF bf16/auto vs llama.cpp
Q4_K_M) means different generations; (2) for `gemma` the evaluator wraps the agent in
`KaggleGemma4ToolCallParser`, which parses `{`-prefixed tool arguments differently and so
changes whether a tool call is recognized at all — i.e. whether an attack scores; (3) the
weight-path env vars disagree. Closing the gap means importing the mounted
`gguf_model_server` specs directly instead of calling `build_agent_factory`.

Locally, either path needs a ≥16 GB GPU and weights (neither is present on the dev box).
On Kaggle:
```
python dev/repro/build_repro_notebook.py       # writes repro_notebook.ipynb
python dev/push_repro_kernel.py --model deterministic --candidates 8
# add --gpu --weights row=path --models-datasource <ref> for a real-model run;
# the competition data source is attached automatically.
```
Pushes to the private, non-submission kernel `adostie3/jed-repro-harness`. Verified there
2026-08-17: the deterministic 8-candidate run returns `candidate_*.json`, the per-candidate
debug JSONL and `summary.json` from `/kaggle/working`.

## Open items — RESOLVED in-kernel 2026-08-17 (probe kernel `jed-harness-probe` v2)
- ~~Exact GGUF source / quantization~~ → `unsloth/gpt-oss-20b-GGUF` /
  `gpt-oss-20b-Q4_K_M.gguf` and `unsloth/gemma-4-26B-A4B-it-GGUF` /
  `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf`, loaded with `n_ctx=8192, n_gpu_layers=-1`.
- ~~Whether the `gemma` row is SDK `gemma` or `gemma_4`~~ → **`gemma_4`**
  (`gemma_model_server.py` sets `backend_label="gemma_4"`, model id
  `google/gemma-4-26B-A4B-it`), so `REPRO_MODELS["gemma"] = "gemma_4"` is correct.
- ~~The `AICOMP_MODEL_NAMES` → backend wiring~~ → `jed_attack_gateway.py` reads
  `AICOMP_MODEL_NAMES` (default `gpt_oss,gemma`) and dispatches each name to a remote
  GGUF model server, using `build_agent_factory` only for names without one.
- Still open: whether to re-point this harness at the mounted `gguf_model_server` specs
  for true parity (see the fidelity gaps above).

## Honesty note on the hidden rerun
`install_default_sink()` *can* instrument agent construction we don't control, but the
spec establishes the hidden rerun returns only `submission.csv` — so debug files written
during the *hidden* rerun are not known to be retrievable. The reliable value is the
**self-controlled** run (local or our own Kaggle notebook), whose `/kaggle/working` we do
get back at commit. Treat hidden-rerun retrieval as an unverified experiment.
