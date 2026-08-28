"""Unit test for dev/repro/models.py (CPU-local; no weights)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))       # dev/repro/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # dev/

import models  # noqa: E402


def main() -> int:
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

    print("test_models: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
