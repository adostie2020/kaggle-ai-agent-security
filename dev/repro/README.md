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

## Real models
Locally needs a ≥16 GB GPU + a local HF Transformers snapshot + `transformers` (none
present on the dev box). The `gpt_oss`/`gemma_4` backends are HF `AutoModelForCausalLM`-
based (`HFChatTemplateBackend`/`HFProcessorChatTemplateBackend.from_pretrained`); they
never construct a `LlamaCppChatTemplateBackend`, so no GGUF file is ever loaded on this
path. `*_MODEL_PATH` must point at a local directory holding a full snapshot
(`config.json`, tokenizer files, `.safetensors`/`.bin` shards) — every backend builder
hardcodes `local_files_only=True`, not overridable anywhere in `dev/repro/`, so setting
only `*_MODEL_ID` will not fall back to a Hub download (Kaggle has internet off at
commit anyway). Practically: attach a Kaggle Dataset/Model containing the full snapshot
directory and point `*_MODEL_PATH` at it. On Kaggle:
```
python dev/repro/build_repro_notebook.py   # writes repro_notebook.ipynb
# push with dev/push_kernel.py (adapted: GPU accelerator + weight dataset sources),
# attach the competition data source, run, then read /kaggle/working/repro/summary.json.
```

## Open items resolved *in-kernel*, not guessed here
- Exact HF snapshot (revision, dtype) Kaggle uses, and the `transformers` version → set
  via the weight datasets you attach + the SDK's backend; confirm against the mounted
  harness.
- Whether the `gemma` row is SDK `gemma` or `gemma_4` → read the mounted
  `kaggle_evaluation` harness in the kernel; override `REPRO_MODELS["gemma"]` if it differs.

## Honesty note on the hidden rerun
`install_default_sink()` *can* instrument agent construction we don't control, but the
spec establishes the hidden rerun returns only `submission.csv` — so debug files written
during the *hidden* rerun are not known to be retrievable. The reliable value is the
**self-controlled** run (local or our own Kaggle notebook), whose `/kaggle/working` we do
get back at commit. Treat hidden-rerun retrieval as an unverified experiment.
