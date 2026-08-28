"""Unit test for dev/repro/models.py (CPU-local; no weights)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))       # dev/repro/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # dev/

import models  # noqa: E402


def main() -> int:
    tmp = Path(__file__).resolve().parent  # writable scratch dir for sink files

    # 1: row-id -> selection mapping (gemma defaults to gemma_4 per spec model id)
    assert models.selection_for("deterministic") == "deterministic"
    assert models.selection_for("gpt_oss") == "gpt_oss"
    assert models.selection_for("gemma") == "gemma_4"
    try:
        models.selection_for("nope")
        raise AssertionError("expected ValueError for unknown row id")
    except ValueError:
        pass

    # 2: deterministic needs no weights -> factory builds & runs
    f = models.resolve_agent_factory("deterministic")
    assert f().__class__.__name__ == "VulnerableDeterministicAgent"
    models.validate_selection("deterministic")  # must not raise

    # 3: gemma fail-fast when weights absent (verified SDK behavior on this box)
    os.environ.pop("GEMMA4_MODEL_PATH", None)
    try:
        models.validate_selection("gemma")
    except RuntimeError as e:
        assert "gemma" in str(e).lower() or "backend" in str(e).lower(), e
    else:
        raise AssertionError(
            "validate_selection('gemma') did not fail-fast with weights absent; "
            "the selection is probably not being coerced to AgentSelection"
        )

    # 4: weight-path wiring sets the SDK env var (paths are local HF Transformers
    # snapshot directories, not .gguf files -- this test only checks env-var
    # passthrough, so the exact path strings are documentation-only)
    models.wire_weight_paths({"gemma": "/kaggle/input/gemma/hf-snapshot",
                              "gpt_oss": "/kaggle/input/gptoss/hf-snapshot"})
    assert os.environ["GEMMA4_MODEL_PATH"] == "/kaggle/input/gemma/hf-snapshot"
    assert os.environ["GPT_OSS_MODEL_PATH"] == "/kaggle/input/gptoss/hf-snapshot"
    os.environ.pop("GEMMA4_MODEL_PATH", None)
    os.environ.pop("GPT_OSS_MODEL_PATH", None)

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

    print("test_models: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
