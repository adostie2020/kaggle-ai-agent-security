# Repro Harness GGUF Re-point Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the `dev/repro/` observability harness through the evaluator's own `GgufModelServer` (llama.cpp Q4_K_M GGUF) instead of HF Transformers, so real-model runs carry the same quantization, tool-call parser, request builder and weight paths as the scored competition backend — runnable on a free Kaggle T4, not a local rig.

**Architecture:** Add a `ModelSession` to `dev/repro/models.py` that loads one llama.cpp backend per run and builds a fresh agent per candidate via the mounted `SPEC.create_agent`; split `debug_sink.install_sink(sink)` out of `install_default_sink` so the caller's per-candidate sink can be injected on the GGUF path (where `create_agent` takes no `debug_sink`); wrap the `runner.run_repro` candidate loop in one session; teach the notebook/push scripts a `--backend` switch that pip-installs the cu124 llama.cpp wheel and enables internet for the HF GGUF download. Every `kaggle_evaluation` import happens inside a method — the package does not exist on the dev box — and a `server_factory` seam makes all logic testable locally with no mount, no weights and no `llama_cpp`.

**Tech Stack:** Python 3.12, `aicomp_sdk` (vendored, editable), `kaggle_evaluation.jed_attack_134815.*` (mounted in-kernel only), `llama-cpp-python` 0.3.35 cu124 (in-kernel only), Kaggle REST `kernels/push`.

**Spec:** `docs/superpowers/specs/2026-08-18-gguf-repoint-design.md` (approved design; supporting evidence in `dev/repro/README.md` § "TWO BACKEND LAYERS")

## Global Constraints

- **Interpreter:** always `.venv/Scripts/python.exe`. Restore the SDK with `python dev/bootstrap_sdk.py` if `import aicomp_sdk` fails.
- **Dev-only, never submitted.** This harness writes no `submission.csv`. Do not touch `attack.py`, `submission_notebook.ipynb`, or any scored path.
- **No top-level `kaggle_evaluation` / `llama_cpp` import.** Both are absent on the dev box; a module-scope import breaks the whole local test suite. Import them *inside* the method that needs them, on the GGUF path only.
- **Tests are plain `__main__` scripts** (assert/print, `exit 0` == pass), NOT pytest. Run **one at a time** — the full sweep exceeds the 2-min tool timeout.
- **Every existing test must stay green:** `dev/repro/test_*.py` (×5), `dev/test_fill.py`, `dev/test_agents.py`, `dev/test_trace.py`.
- **GGUF facts (verified in-kernel, do not re-derive):** `gpt_oss` = `unsloth/gpt-oss-20b-GGUF` / `gpt-oss-20b-Q4_K_M.gguf`; `gemma` = `unsloth/gemma-4-26B-A4B-it-GGUF` / `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf`; both `n_ctx=8192, n_gpu_layers=-1`; load 48 s / 125 s; both fit a T4 (9.8 GB resident for gemma). Wheel: `pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124` (71 s, GPU offload works).
- **Commit trailers** on every commit:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01PHmyFULkEi2zZLkX1cnHa8
  ```
- **The real SDK surface** (`SPEC.create_agent`, `server.load_model()`, `server._backend`, `server.unload()`, `spec.model_path_env_var`) is asserted from the spec's in-kernel probe findings and is only exercised for real at Task 9 (acceptance). Local tests use the `server_factory` fake. Guard `server._backend is None` with an explicit error.

---

### Task 1: `debug_sink.install_sink(sink)` split

Split the sink-object patching out of `install_default_sink` so the GGUF path can inject a caller-supplied sink (the path-based default keeps its behavior, re-implemented on the new primitive).

**Files:**
- Modify: `dev/repro/debug_sink.py:49-72`
- Test: `dev/repro/test_debug_sink.py` (add case 5)

**Interfaces:**
- Consumes: existing `_PATCH_TARGETS`, `_ORIGINALS`, `make_jsonl_sink`, `resolve_sink_path`.
- Produces: `install_sink(sink) -> None` (patches `_PATCH_TARGETS.__init__` so a `debug_sink=None` construction uses `sink`); `install_default_sink(path=None) -> Path | None` (unchanged behavior, now built on `install_sink`); `uninstall_default_sink() -> None` (unchanged).

- [ ] **Step 1: Write the failing test** — append case 5 to `dev/repro/test_debug_sink.py` before the final `print(...)`, and add `install_sink` to the import block at `:21-27`:

```python
    # --- 5: install_sink(sink) injects THIS sink under debug_sink=None ---
    from debug_sink import install_sink  # local import keeps case self-contained
    p5 = tmp / "_repro_test_install_sink.jsonl"
    p5.unlink(missing_ok=True)
    sink5 = make_jsonl_sink(p5)
    install_sink(sink5)
    try:
        _run_once(build_agent_factory("deterministic", debug_sink=None)())
        assert p5.exists() and _jsonl_lines(p5), "install_sink(sink) did not inject the sink"
    finally:
        uninstall_default_sink()
    p5.unlink(missing_ok=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe dev/repro/test_debug_sink.py`
Expected: `ImportError: cannot import name 'install_sink'`.

- [ ] **Step 3: Write minimal implementation** — replace the body of `install_default_sink` (`debug_sink.py:49-72`) with a new `install_sink` primitive plus a thin `install_default_sink`:

```python
def install_sink(sink) -> None:
    """Patch agent __init__s so a debug_sink=None construction uses THIS sink object.

    Idempotent: re-patching reuses the stored originals so uninstall fully restores.
    """
    for cls in _PATCH_TARGETS:
        original = _ORIGINALS.get(cls, cls.__init__)
        _ORIGINALS.setdefault(cls, original)

        def make_wrapper(orig: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(orig)
            def __init__(self, *args, debug_sink=None, **kwargs):  # noqa: N807
                orig(self, *args, debug_sink=debug_sink or sink, **kwargs)

            return __init__

        cls.__init__ = make_wrapper(original)  # type: ignore[assignment]


def install_default_sink(path: str | Path | None = None) -> Path | None:
    """Patch agent __init__s so debug_sink=None becomes a shared JSONL sink.

    Returns the resolved sink path, or None (no-op) if no path is configured.
    """
    resolved = resolve_sink_path(str(path) if path is not None else None)
    if resolved is None:
        return None
    install_sink(make_jsonl_sink(resolved))
    return resolved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe dev/repro/test_debug_sink.py`
Expected: `test_debug_sink: PASS`.

- [ ] **Step 5: Commit**

```bash
git add dev/repro/debug_sink.py dev/repro/test_debug_sink.py
git commit -m "refactor(repro): split install_sink(sink) out of install_default_sink"
```

---

### Task 2: `models.ModelSession` — construction, validation, HF/deterministic routing

Add the session object and its backend/row validation and the non-GGUF (`hf` / `deterministic`) `agent_factory` path. No `kaggle_evaluation` import yet — this task is the parts that run with no mount.

**Files:**
- Modify: `dev/repro/models.py` (add imports, `GGUF_SERVER_MODULES`, `ModelSession`)
- Test: `dev/repro/test_models.py` (add cases 5–8)

**Interfaces:**
- Consumes: `install_sink`, `uninstall_default_sink` from `debug_sink`; existing `selection_for`, `REPRO_MODELS`, `build_agent_factory`.
- Produces:
  - `GGUF_SERVER_MODULES: dict[str, str]` = `{"gpt_oss": "kaggle_evaluation.jed_attack_134815.gpt_oss_model_server", "gemma": "kaggle_evaluation.jed_attack_134815.gemma_model_server"}`
  - `class ModelSession(row_id: str, backend: str = "gguf", *, server_factory: Callable[[str], tuple[Any, Any]] | None = None, weight_path: str | None = None)` with `.open() -> ModelSession`, `.agent_factory(debug_sink) -> Callable[[], Any]`, `.close() -> None`, `__enter__`/`__exit__`.
  - `_VALID_BACKENDS = ("gguf", "hf")`; `_GGUF_ROWS = ("gpt_oss", "gemma")`.

- [ ] **Step 1: Write the failing test** — append to `dev/repro/test_models.py` before the final `print(...)`:

```python
    # 5: server-module mapping is plain strings, asserted WITHOUT importing anything
    assert models.GGUF_SERVER_MODULES["gpt_oss"] == \
        "kaggle_evaluation.jed_attack_134815.gpt_oss_model_server"
    assert models.GGUF_SERVER_MODULES["gemma"] == \
        "kaggle_evaluation.jed_attack_134815.gemma_model_server"

    # 6: unknown row id and unknown backend both raise, listing valid values
    for bad in [dict(row_id="nope", backend="gguf"), dict(row_id="gpt_oss", backend="vllm")]:
        try:
            models.ModelSession(**bad)
            raise AssertionError(f"expected ValueError for {bad}")
        except ValueError:
            pass

    # 7: deterministic routes to build_agent_factory on either backend (no weights)
    for be in ("gguf", "hf"):
        sess = models.ModelSession("deterministic", be).open()
        try:
            assert sess.agent_factory(None)().__class__.__name__ == "VulnerableDeterministicAgent"
        finally:
            sess.close()

    # 8: --backend hf on a real row still hits build_agent_factory (fail-fast, no weights)
    os.environ.pop("GPT_OSS_MODEL_PATH", None)
    try:
        models.ModelSession("gpt_oss", "hf").open().agent_factory(None)
        raise AssertionError("expected RuntimeError building hf gpt_oss without weights")
    except RuntimeError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe dev/repro/test_models.py`
Expected: `AttributeError: module 'models' has no attribute 'GGUF_SERVER_MODULES'`.

- [ ] **Step 3: Write minimal implementation** — add to `dev/repro/models.py`. Extend the top imports (`models.py:10-17`) with:

```python
import importlib
from debug_sink import install_sink, uninstall_default_sink
```

Then add after `WEIGHT_ENV` (`models.py:30`):

```python
GGUF_SERVER_MODULES: dict[str, str] = {
    "gpt_oss": "kaggle_evaluation.jed_attack_134815.gpt_oss_model_server",
    "gemma": "kaggle_evaluation.jed_attack_134815.gemma_model_server",
}
_VALID_BACKENDS = ("gguf", "hf")
_GGUF_ROWS = ("gpt_oss", "gemma")


def _default_server_factory(row_id: str) -> tuple[Any, Any]:
    """Import the mounted server module + GgufModelServer and return (spec, server).

    Only called on the GGUF path for a real model row; the kaggle_evaluation
    imports live here so the dev box (which lacks the package) never trips them.
    """
    module = importlib.import_module(GGUF_SERVER_MODULES[row_id])
    from kaggle_evaluation.jed_attack_134815.gguf_model_server import GgufModelServer
    spec = module.SPEC
    return spec, GgufModelServer(spec)


class ModelSession:
    """One llama.cpp backend loaded per run; a fresh agent built per candidate.

    `backend` is the 'gguf'/'hf' selector; `_llm_backend` is the loaded llama.cpp
    object — never the same thing. `server_factory(row_id) -> (spec, server)` is the
    test seam that replaces the kaggle_evaluation import.
    """

    def __init__(
        self,
        row_id: str,
        backend: str = "gguf",
        *,
        server_factory: Callable[[str], tuple[Any, Any]] | None = None,
        weight_path: str | None = None,
    ) -> None:
        if row_id not in REPRO_MODELS:
            raise ValueError(f"Unknown row_id {row_id!r}; valid: {sorted(REPRO_MODELS)}")
        if backend not in _VALID_BACKENDS:
            raise ValueError(f"Unknown backend {backend!r}; valid: {list(_VALID_BACKENDS)}")
        self.row_id = row_id
        self.backend = backend
        self.weight_path = weight_path
        self._server_factory = server_factory or _default_server_factory
        self._spec: Any = None
        self._server: Any = None
        self._llm_backend: Any = None

    def _is_gguf(self) -> bool:
        return self.backend == "gguf" and self.row_id in _GGUF_ROWS

    def open(self) -> "ModelSession":
        if not self._is_gguf():
            return self  # hf / deterministic: nothing to load
        self._spec, self._server = self._server_factory(self.row_id)
        if self.weight_path:
            os.environ[self._spec.model_path_env_var] = str(self.weight_path)
        self._server.load_model()
        backend = getattr(self._server, "_backend", None)
        if backend is None:
            raise RuntimeError(
                "GgufModelServer._backend is None after load_model(); the server "
                "shape changed — re-read the mounted gguf_model_server source."
            )
        self._llm_backend = backend
        return self

    def agent_factory(self, debug_sink: Any) -> Callable[[], Any]:
        if not self._is_gguf():
            return build_agent_factory(selection_for(self.row_id), debug_sink=debug_sink)
        spec, backend = self._spec, self._llm_backend

        def factory() -> Any:
            if debug_sink is not None:
                install_sink(debug_sink)  # create_agent takes no debug_sink; patch instead
            return spec.create_agent(backend)

        return factory

    def close(self) -> None:
        uninstall_default_sink()
        server = self._server
        if server is not None and hasattr(server, "unload"):
            server.unload()
        self._server = None
        self._llm_backend = None

    def __enter__(self) -> "ModelSession":
        return self.open()

    def __exit__(self, *exc: Any) -> bool:
        self.close()
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe dev/repro/test_models.py`
Expected: `test_models: PASS`.

- [ ] **Step 5: Commit**

```bash
git add dev/repro/models.py dev/repro/test_models.py
git commit -m "feat(repro): ModelSession construction + hf/deterministic routing"
```

---

### Task 3: `ModelSession` GGUF semantics — load-once, fresh agent, sink, weight override, unload

Exercise the GGUF path with a `server_factory` fake: one load per run, a distinct agent per `agent_factory` call, the sink forwarded via `install_sink`, an optional pre-staged weight path written to the spec's env var, and `close()` unloading + restoring patched `__init__`s.

**Files:**
- Modify: none (implementation landed in Task 2)
- Test: `dev/repro/test_models.py` (add cases 9–13)

**Interfaces:**
- Consumes: `models.ModelSession`, `models.install_sink` (spied), `debug_sink._ORIGINALS`, `debug_sink.make_jsonl_sink`.
- Produces: nothing new — this task is verification of Task 2's GGUF branch.

- [ ] **Step 1: Write the failing test** — append to `dev/repro/test_models.py` before the final `print(...)`. Add `import debug_sink` to the import block at `models.py`... (in the *test* file, add `import debug_sink` near `import models`):

```python
    # --- GGUF path via a fake server_factory (no mount, no weights, no llama_cpp) ---
    import debug_sink

    class _FakeSpec:
        def __init__(self):
            self.create_calls = 0
            self.model_path_env_var = "FAKE_GGUF_PATH"

        def create_agent(self, backend):
            self.create_calls += 1
            return object()  # a fresh, distinct "agent" each call

    class _FakeServer:
        def __init__(self, spec):
            self.spec = spec
            self.loads = 0
            self.unloads = 0
            self._backend = None

        def load_model(self):
            self.loads += 1
            self._backend = object()
            return self._backend

        def unload(self):
            self.unloads += 1

    created: list = []

    def _fake_factory(row_id):
        spec, server = _FakeSpec(), None
        server = _FakeServer(spec)
        created.append((spec, server))
        return spec, server

    # 9: backend loaded exactly once across N agent_factory calls; distinct agents
    sess = models.ModelSession("gpt_oss", "gguf", server_factory=_fake_factory).open()
    agents = [sess.agent_factory(None)() for _ in range(3)]
    spec, server = created[-1]
    assert server.loads == 1, server.loads
    assert spec.create_calls == 3, spec.create_calls
    assert len({id(a) for a in agents}) == 3, "agents not distinct"

    # 10: close() unloads and restores patched __init__s
    real_sink = debug_sink.make_jsonl_sink(tmp / "_repro_session_sink.jsonl")
    sess.agent_factory(real_sink)()          # triggers install_sink -> patches classes
    assert debug_sink._ORIGINALS, "install_sink did not patch"
    sess.close()
    assert not debug_sink._ORIGINALS, "close() did not restore patched __init__s"
    assert server.unloads == 1, server.unloads
    (tmp / "_repro_session_sink.jsonl").unlink(missing_ok=True)

    # 11: the sink passed to agent_factory is the one forwarded to install_sink
    seen: list = []
    orig_install = models.install_sink
    models.install_sink = lambda s: seen.append(s)
    try:
        sess2 = models.ModelSession("gemma", "gguf", server_factory=_fake_factory).open()
        sess2.agent_factory(real_sink)()
        assert seen == [real_sink], seen
        sess2.close()
    finally:
        models.install_sink = orig_install

    # 12: weight_path override writes the spec's model_path_env_var before load
    os.environ.pop("FAKE_GGUF_PATH", None)
    sess3 = models.ModelSession(
        "gpt_oss", "gguf", server_factory=_fake_factory, weight_path="/x/model.gguf"
    ).open()
    assert os.environ["FAKE_GGUF_PATH"] == "/x/model.gguf"
    sess3.close()
    os.environ.pop("FAKE_GGUF_PATH", None)

    # 13: _backend None after load_model -> actionable RuntimeError
    class _NullBackendServer(_FakeServer):
        def load_model(self):
            self.loads += 1
            self._backend = None
            return None

    def _null_factory(row_id):
        return _FakeSpec(), _NullBackendServer(_FakeSpec())

    try:
        models.ModelSession("gpt_oss", "gguf", server_factory=_null_factory).open()
        raise AssertionError("expected RuntimeError on None _backend")
    except RuntimeError as e:
        assert "_backend is None" in str(e), e
```

Also add near the top of `test_models.py` (after `import models`): the test already imports `os`; ensure `tmp` is defined — add at the start of `main()`:

```python
    tmp = Path(__file__).resolve().parent  # writable scratch dir for sink files
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe dev/repro/test_models.py`
Expected: FAIL — first new assertion to trip is case 9 (`server.loads`) only if Task 2 was skipped; if Task 2 landed, this should already pass. If it passes immediately, that is acceptable (Task 2's code covers this path) — proceed to Step 4.

- [ ] **Step 3: Write minimal implementation** — none required if Task 2 is complete. If case 12 fails, confirm `open()` sets `os.environ[self._spec.model_path_env_var]` *before* `load_model()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe dev/repro/test_models.py`
Expected: `test_models: PASS`.

- [ ] **Step 5: Commit**

```bash
git add dev/repro/test_models.py
git commit -m "test(repro): ModelSession GGUF load-once/distinct/sink/unload coverage"
```

---

### Task 4: `runner.run_repro` — one session around the candidate loop

Give `run_repro` a `backend` argument; when `resolve` is not injected, open one `ModelSession` for the whole loop and close it in `finally`. The injected-`resolve` seam is preserved so `test_runner.py` is unchanged.

**Files:**
- Modify: `dev/repro/runner.py:42-100`
- Test: `dev/repro/test_runner.py` (add a resolve=None deterministic case)

**Interfaces:**
- Consumes: `models.ModelSession`.
- Produces: `run_repro(*, model, n_candidates, out_dir, backend: str = "gguf", resolve: Callable[[str, Any], Callable[[], Any]] | None = None, sink_dir=None, guardrail_factory=..., max_tool_hops=...) -> ReproResult`. When `resolve is None`, factories come from `ModelSession(model, backend)`.

- [ ] **Step 1: Write the failing test** — append to `dev/repro/test_runner.py` before the final `print(...)`:

```python
    # 4: resolve=None (default) routes deterministic through ModelSession end-to-end
    out2 = Path(oracle.FIXTURES).parent / "_repro_runner_session_out"
    if out2.exists():
        shutil.rmtree(out2)
    res2 = runner.run_repro(
        model="deterministic", n_candidates=2, out_dir=out2, backend="hf", resolve=None
    )
    assert (out2 / "summary.json").exists()
    c0 = json.loads((out2 / "candidate_0.json").read_text(encoding="utf-8"))
    assert c0["agent"] == "deterministic", c0["agent"]
    assert res2.n_candidates == 2
    shutil.rmtree(out2, ignore_errors=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe dev/repro/test_runner.py`
Expected: FAIL — `run_repro()` has no `backend` kwarg (`TypeError`).

- [ ] **Step 3: Write minimal implementation** — edit `dev/repro/runner.py`. Change the signature (`:42-51`) so `resolve` defaults to `None` and add `backend`:

```python
def run_repro(
    *,
    model: str,
    n_candidates: int,
    out_dir: str | Path,
    backend: str = "gguf",
    resolve: Callable[[str, Any], Callable[[], Any]] | None = None,
    sink_dir: str | Path | None = None,
    guardrail_factory: Callable[[], Any] = oracle.OptimalGuardrail,
    max_tool_hops: int = oracle.MAX_TOOL_HOPS,
) -> ReproResult:
```

After `chains = candidate_messages(n_candidates)` (`:58`) and before the loop, add the session/factory-builder selection:

```python
    session = None
    if resolve is None:
        session = models.ModelSession(model, backend).open()
        build_factory = session.agent_factory
    else:
        build_factory = lambda ds: resolve(model, ds)  # noqa: E731
```

Wrap the existing `for i, messages in enumerate(chains):` loop body in `try:` and add a `finally:` that closes the session. Inside the loop, replace `factory = resolve(model, debug_sink)` (`:70`) with `factory = build_factory(debug_sink)`. Concretely, the loop becomes:

```python
    try:
        for i, messages in enumerate(chains):
            debug_path = None
            debug_sink = None
            if sink_root is not None:
                debug_path = sink_root / f"candidate_{i}.debug.jsonl"
                debug_sink = make_jsonl_sink(debug_path)

            factory = build_factory(debug_sink)
            report = tracer.trace_chain(
                messages,
                agent_factory=factory,
                guardrail_factory=guardrail_factory,
                max_tool_hops=max_tool_hops,
            )
            report.agent = model
            report_path = out / f"candidate_{i}.json"
            report_path.write_text(report.to_json(), encoding="utf-8")

            final = report.turns[-1] if report.turns else None
            raw = float(final.running_raw) if final else 0.0
            norm = float(final.running_normalized) if final else 0.0
            total_raw += raw
            total_norm += norm
            per_candidate.append(
                {
                    "index": i,
                    "messages": messages,
                    "running_raw": raw,
                    "running_normalized": norm,
                    "report_path": str(report_path),
                    "debug_path": str(debug_path) if debug_path else None,
                }
            )
    finally:
        if session is not None:
            session.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run both, one at a time:
`.venv/Scripts/python.exe dev/repro/test_runner.py` → `test_runner: PASS`
`.venv/Scripts/python.exe dev/repro/test_run_repro.py` → `test_run_repro: PASS` (CLI default path now goes through ModelSession(deterministic) and must still pass)

- [ ] **Step 5: Commit**

```bash
git add dev/repro/runner.py dev/repro/test_runner.py
git commit -m "feat(repro): run_repro opens one ModelSession per run (backend arg)"
```

---

### Task 5: `run_repro.py` CLI — `--backend`

Expose `--backend {gguf,hf}` (default `gguf`) and thread it into `runner.run_repro`. `--self-check` still forces `deterministic`, for which the backend is inert.

**Files:**
- Modify: `dev/repro/run_repro.py:34-70`
- Test: `dev/repro/test_run_repro.py` (add a `--backend hf` self-check assertion)

**Interfaces:**
- Consumes: `runner.run_repro(backend=...)`.
- Produces: CLI flag `--backend`.

- [ ] **Step 1: Write the failing test** — append to `dev/repro/test_run_repro.py` before the final `print(...)`:

```python
    # Test 4: --backend hf self-check runs (backend threads through the CLI)
    out = HERE / "_run_repro_backend_out"
    if out.exists():
        shutil.rmtree(out)
    cmd = [
        PYEXE, str(HERE / "run_repro.py"),
        "--self-check", "--backend", "hf", "--candidates", "2", "--out", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["model"] == "deterministic"
    shutil.rmtree(out, ignore_errors=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe dev/repro/test_run_repro.py`
Expected: FAIL — `run_repro.py: error: unrecognized arguments: --backend hf`.

- [ ] **Step 3: Write minimal implementation** — in `dev/repro/run_repro.py`, add the argument after `--model` (`:36`):

```python
    ap.add_argument("--backend", choices=["gguf", "hf"], default="gguf",
                    help="gguf = evaluator's llama.cpp GGUF servers (scored parity); "
                         "hf = build_agent_factory HF Transformers backends")
```

and pass it through in the `runner.run_repro(...)` call (`:65-70`):

```python
    result = runner.run_repro(
        model=model,
        n_candidates=args.candidates,
        out_dir=args.out,
        backend=args.backend,
        sink_dir=args.sink_dir,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run, one at a time:
`.venv/Scripts/python.exe dev/repro/test_run_repro.py` → `test_run_repro: PASS`

- [ ] **Step 5: Commit**

```bash
git add dev/repro/run_repro.py dev/repro/test_run_repro.py
git commit -m "feat(repro): run_repro.py --backend {gguf,hf}"
```

---

### Task 6: Notebook builder — GGUF setup cell + `--backend` wiring

Teach `build_repro_notebook.build` a `backend` parameter: thread `--backend` into the run cell, and for a real GGUF model row prepend a setup cell that sets `HF_HOME=/kaggle/temp/hf` and installs the cu124 llama.cpp wheel when missing. The setup cell must contain neither `b64decode` nor `subprocess.run`, so the existing "exactly one embed/run cell" assertions still hold.

**Files:**
- Modify: `dev/repro/build_repro_notebook.py:80-141`
- Test: `dev/repro/test_build_repro_notebook.py` (add GGUF/backend assertions)

**Interfaces:**
- Consumes: nothing new.
- Produces: `build(model="gemma", n_candidates=8, weights=None, backend="gguf") -> dict`; run cell carries `--backend <backend>`; a GGUF setup cell is present iff `backend == "gguf" and model in ("gpt_oss", "gemma")`.

- [ ] **Step 1: Write the failing test** — append to `dev/repro/test_build_repro_notebook.py` before the final `print(...)`:

```python
    # GGUF run: setup cell installs the cu124 wheel + sets HF_HOME; run cell carries --backend
    g = b.build(model="gpt_oss", n_candidates=2, backend="gguf")
    gsrc = "\n".join("".join(c["source"]) for c in g["cells"])
    assert "--backend" in gsrc and "gguf" in gsrc, "backend not wired into gguf run cell"
    assert "llama-cpp-python" in gsrc, "gguf setup cell missing llama.cpp install"
    assert "cu124" in gsrc, "gguf setup cell missing cu124 extra-index-url"
    assert "HF_HOME" in gsrc and "/kaggle/temp" in gsrc, "gguf setup cell missing HF_HOME"
    # setup cell must not masquerade as the embed or run cell
    assert "subprocess.run" not in "".join(
        c2 for c in g["cells"] if "llama-cpp-python" in "".join(c["source"])
        for c2 in c["source"]
    ), "setup cell must not contain subprocess.run"

    # hf run: no llama install cell, still carries --backend hf
    h = b.build(model="gpt_oss", n_candidates=2, backend="hf")
    hsrc = "\n".join("".join(c["source"]) for c in h["cells"])
    assert "--backend" in hsrc and "hf" in hsrc
    assert "llama-cpp-python" not in hsrc, "hf run should not install llama.cpp"

    # deterministic gguf: no llama install (deterministic needs no GGUF backend)
    d = b.build(model="deterministic", n_candidates=2, backend="gguf")
    dsrc = "\n".join("".join(c["source"]) for c in d["cells"])
    assert "llama-cpp-python" not in dsrc, "deterministic must not install llama.cpp"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe dev/repro/test_build_repro_notebook.py`
Expected: FAIL — `build()` has no `backend` kwarg.

- [ ] **Step 3: Write minimal implementation** — in `dev/repro/build_repro_notebook.py`:

Add a module-level constant near `PREAMBLE` (`:39`):

```python
GGUF_SETUP = (
    "import os, importlib.util, subprocess, sys\n"
    "os.environ.setdefault('HF_HOME', '/kaggle/temp/hf')  # NOT /kaggle/working (>11GB, committed)\n"
    "if importlib.util.find_spec('llama_cpp') is None:\n"
    "    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q',\n"
    "        'llama-cpp-python', '--extra-index-url',\n"
    "        'https://abetlen.github.io/llama-cpp-python/whl/cu124'])\n"
    "import llama_cpp\n"
    "print('llama_cpp', llama_cpp.__version__, 'gpu_offload',\n"
    "      llama_cpp.llama_supports_gpu_offload())\n"
)
```

Change the `build` signature (`:80`) and thread `backend` into the run cell and cell list:

```python
def build(model: str = "gemma", n_candidates: int = 8,
          weights: dict[str, str] | None = None, backend: str = "gguf") -> dict:
    weights = weights or {}
    weight_args = " ".join(f"{row}={path}" for row, path in weights.items())
    run_cell = (
        "import os, subprocess, sys\n"
        "cmd = [sys.executable, '/kaggle/working/repro_pkg/run_repro.py',\n"
        f"       '--model', '{model}', '--candidates', '{n_candidates}',\n"
        f"       '--backend', '{backend}',\n"
        "       '--out', '/kaggle/working/repro',\n"
        "       '--sink-dir', '/kaggle/working/repro/debug']\n"
        f"extra = {weight_args!r}\n"
        "if extra:\n"
        "    cmd += ['--weights'] + extra.split()\n"
        "print('running:', ' '.join(cmd))\n"
        "env = dict(os.environ)\n"
        "env['PYTHONPATH'] = os.pathsep.join(p for p in sys.path if p)\n"
        "proc = subprocess.run(cmd, capture_output=True, text=True, env=env)\n"
        "print('returncode:', proc.returncode)\n"
        "print('--- stdout ---')\n"
        "print(proc.stdout)\n"
        "print('--- stderr ---')\n"
        "print(proc.stderr)\n"
    )
```

Leave `list_cell` unchanged. Replace the `cells = [...]` list so the setup cell is inserted after PREAMBLE only for a real GGUF row:

```python
    needs_gguf = backend == "gguf" and model in ("gpt_oss", "gemma")
    cells = [
        _markdown("# JED real-model repro (Phase 2)\n"
                  "Runs the real agent under the SDK env/guardrail/scoring and dumps\n"
                  "per-candidate observability JSON to `/kaggle/working/repro`.\n"
                  "Not a submission — writes no `submission.csv`."),
        _code(PREAMBLE),
    ]
    if needs_gguf:
        cells.append(_code(GGUF_SETUP))
    cells += [
        _code("import importlib.util as u\n"
              "assert u.find_spec('aicomp_sdk'), 'aicomp_sdk not importable in kernel'\n"
              "print('aicomp_sdk OK')\n"),
        _code(_embed_sources()),
        _code(run_cell),
        _code(list_cell),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe dev/repro/test_build_repro_notebook.py`
Expected: `test_build_repro_notebook: PASS`.

- [ ] **Step 5: Commit**

```bash
git add dev/repro/build_repro_notebook.py dev/repro/test_build_repro_notebook.py
git commit -m "feat(repro): notebook GGUF setup cell + --backend wiring"
```

---

### Task 7: Push script — `--backend` + internet for GGUF download

Add `--backend {gguf,hf}` to `push_repro_kernel.py`, thread it into `brn.build`, and enable internet (pip install + HF GGUF download) only for a real GGUF model row. `--dry-run` proves the request body without pushing.

**Files:**
- Modify: `dev/push_repro_kernel.py:50-94`
- Test: `dev/push_repro_kernel.py` gains no unit file (it has none today); verify via `--dry-run` in Step 4.

**Interfaces:**
- Consumes: `brn.build(backend=...)`.
- Produces: CLI flag `--backend`; `isInternetEnabled` / `enableInternet` == `(backend == "gguf" and model in {gpt_oss, gemma})`.

- [ ] **Step 1: Write the failing check** — this script has no test harness; the failing state is that `--backend` is unrecognized. Confirm:

Run: `.venv/Scripts/python.exe dev/push_repro_kernel.py --model gpt_oss --backend gguf --gpu --dry-run`
Expected: FAIL — `error: unrecognized arguments: --backend gguf`.

- [ ] **Step 2: Write minimal implementation** — in `dev/push_repro_kernel.py`, add the argument after `--model` (`:52`):

```python
    ap.add_argument("--backend", choices=["gguf", "hf"], default="gguf",
                    help="gguf = evaluator llama.cpp GGUF servers (needs internet for the "
                         "HF download); hf = build_agent_factory HF backends")
```

Compute the internet flag after parsing (`:59`, before `nb = brn.build(...)`):

```python
    need_net = args.backend == "gguf" and args.model in ("gpt_oss", "gemma")
    if args.backend == "gguf" and args.model in ("gpt_oss", "gemma") and not args.gpu:
        print("WARNING: --backend gguf on a real model row without --gpu; the T4 is "
              "required for llama.cpp offload. Pass --gpu.")
```

Thread `backend` into the build call (`:61-62`):

```python
    nb = brn.build(model=args.model, n_candidates=args.candidates,
                   weights=_parse_weights(args.weights), backend=args.backend)
```

Set the internet flags — in `nb["metadata"]["kaggle"]` (`:69`) change `"isInternetEnabled": False,` to `"isInternetEnabled": need_net,` and in `body` (`:85`) change `"enableInternet": False,` to `"enableInternet": need_net,`.

- [ ] **Step 3: Verify the body via dry-run**

Run: `.venv/Scripts/python.exe dev/push_repro_kernel.py --model gpt_oss --backend gguf --gpu --dry-run`
Expected: PASS — prints `model=gpt_oss ... gpu=True cells=6 bytes=...` and `dry run; not pushed`, no traceback.

Run: `.venv/Scripts/python.exe dev/push_repro_kernel.py --model deterministic --dry-run`
Expected: PASS — deterministic, `need_net` False (unchanged internet-off behavior).

- [ ] **Step 4: Commit**

```bash
git add dev/push_repro_kernel.py
git commit -m "feat(repro): push_repro_kernel --backend + internet for GGUF download"
```

---

### Task 8: Regenerate notebook, full local regression, docs

Rebuild the committed `repro_notebook.ipynb`, run the entire regression suite one file at a time, and update `dev/repro/README.md` to record that the harness now defaults to the GGUF backend.

**Files:**
- Modify: `dev/repro/repro_notebook.ipynb` (regenerated), `dev/repro/README.md`
- Test: the full suite (below)

- [ ] **Step 1: Regenerate the notebook**

Run: `.venv/Scripts/python.exe dev/repro/build_repro_notebook.py`
Expected: `wrote .../dev/repro/repro_notebook.ipynb`.

- [ ] **Step 2: Run the full regression suite, one file at a time** — each must print its `PASS` line and exit 0:

```
.venv/Scripts/python.exe dev/repro/test_debug_sink.py
.venv/Scripts/python.exe dev/repro/test_models.py
.venv/Scripts/python.exe dev/repro/test_runner.py
.venv/Scripts/python.exe dev/repro/test_run_repro.py
.venv/Scripts/python.exe dev/repro/test_build_repro_notebook.py
.venv/Scripts/python.exe dev/test_fill.py
.venv/Scripts/python.exe dev/test_agents.py
.venv/Scripts/python.exe dev/test_trace.py
```

- [ ] **Step 3: Update the README** — in `dev/repro/README.md`, revise the "TWO BACKEND LAYERS" section so it states the harness now **defaults to `--backend gguf`** (the evaluator's llama.cpp GGUF servers) and keeps `--backend hf` for side-by-side comparison; move the old "Still open: whether to re-point…" bullet (`README.md:155-156`) to a "Done (2026-08-28): re-pointed onto GgufModelServer" note that points at this plan and the spec.

- [ ] **Step 4: Commit**

```bash
git add dev/repro/repro_notebook.ipynb dev/repro/README.md
git commit -m "chore(repro): regenerate GGUF notebook; README default backend + close open item"
```

---

### Task 9: Acceptance — real Kaggle T4 GGUF run

Local green is necessary but not sufficient (this repo has twice shipped locally-green code that failed in-kernel). Prove the re-point on the competition's own hardware.

**Files:** none (operational)

**Preconditions:**
- Kaggle OAuth token valid (`~/.claude/.credentials.json`; refresh per `CLAUDE.md` if expired — back it up first, never print/commit it).
- Kaggle GPU quota available (`mcp__kaggle__get_accelerator_quota`).

- [ ] **Step 1: Push a small real GGUF run**

Run: `.venv/Scripts/python.exe dev/push_repro_kernel.py --model gpt_oss --backend gguf --gpu --candidates 4`
Expected: `PUSH RESPONSE: {...}` with no HTTP error.

- [ ] **Step 2: Poll to completion** — status via `/api/v1/kernels/status` returns lowercase `"running"`/`"complete"` (case-sensitive — do not compare against the MCP tool's uppercase). Wait for terminal state.

- [ ] **Step 3: Pull output and verify parity signals**
- `candidate_0..3.json`, `candidate_*.debug.jsonl`, and `summary.json` are returned from `/kaggle/working/repro`.
- The log shows the llama.cpp backend loaded **once**, not four times (grep the run-cell stdout for the single `llama_cpp ... gpu_offload True` line and one `load_model` cost).
- Each candidate's debug JSONL is non-empty and distinct.
- The setup cell reported `llama_supports_gpu_offload() == True`.

- [ ] **Step 4: Record the result** — write the observed numbers (load time, per-candidate generation, whether any candidate fired, gpt_oss vs the earlier HF numbers) into `dev/repro/README.md` and/or a fresh `HANDOFF` note, and update memory (`jed-repro-harness-kernel`) to state the harness is GGUF-parity as of 2026-08-28.

- [ ] **Step 5: Commit**

```bash
git add dev/repro/README.md
git commit -m "docs(repro): record first real GGUF-parity Kaggle run numbers"
```

---

## Self-Review

**Spec coverage:**
- §1 `models.py` ModelSession → Tasks 2–3 (construction, routing, load-once, `_backend` guard, `server_factory` seam, `spec.model_path_env_var`). ✓
- §2 `debug_sink.install_sink` split → Task 1. ✓
- §3 `runner.py` session around loop (backend arg, `finally` close, resolve seam preserved) → Task 4. ✓
- §4 notebook `HF_HOME`+cu124 install; push `--backend`+internet → Tasks 6–7. ✓
- §5 error handling (llama_cpp missing → install cmd in setup cell; kaggle_evaluation not importable → surfaced by run-cell stderr + aicomp_sdk assert; `_backend` None → Task 2/3 guard; unknown row/backend → Task 2 ValueErrors). ✓
- Testing §: model tests 1–7 → Tasks 2–3 cases 5–13; debug_sink test 8 → Task 1 case 5; regression → Task 8. ✓
- Acceptance § (real Kaggle run, load-once, distinct JSONL) → Task 9. ✓
- Non-goal (no remote_agent hop, no attack.py/submission change) → respected; nothing in the plan touches those. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step carries real code and exact paths/line anchors. ✓

**Type consistency:** `ModelSession(row_id, backend, *, server_factory, weight_path)`, `.open()/.agent_factory(debug_sink)/.close()`, `GGUF_SERVER_MODULES`, `install_sink(sink)`, `run_repro(..., backend="gguf", resolve=None)`, `build(..., backend="gguf")` are used identically across Tasks 1–7. `server_factory(row_id) -> (spec, server)`; `spec.create_agent(backend)`, `spec.model_path_env_var`, `server.load_model()`, `server._backend`, `server.unload()` are consistent between the fake (Task 3) and the real `_default_server_factory` (Task 2). ✓

## Risks

- **Real SDK attribute names** (`SPEC`, `create_agent`, `_backend`, `unload`, `model_path_env_var`) are asserted from probe evidence, not exercised locally; a shape change surfaces as the guarded RuntimeError at Task 9, fixable in one line.
- **Kernel wall-clock:** ~1–2 s/gen × ≤8 hops × N candidates + 48–125 s load. Keep N small at acceptance; size deliberately before any large run.
- **Kaggle OAuth (~3 h TTL)** and GPU quota gate Task 9 only; Tasks 1–8 are fully local.
