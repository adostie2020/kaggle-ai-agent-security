"""Map repro row ids to the real SDK agent factory, with weight-path wiring.

Row ids match the Kaggle submission's Id column (gpt_oss, gemma). The gemma row
defaults to the SDK's `gemma_4` selection (google/gemma-4-26B-A4B-it), per the
spec's model identification; confirm against the mounted competition harness in a
kernel before trusting scores, and override REPRO_MODELS["gemma"] if it disagrees.
"""
from __future__ import annotations

import importlib
import os
from typing import Any, Callable

from aicomp_sdk.agents.factory import (
    build_agent_factory,
    coerce_agent_selection,
    require_agent_selection_configuration,
)

from debug_sink import install_sink, uninstall_default_sink

# Kaggle Id row -> SDK AgentSelection value.
REPRO_MODELS: dict[str, str] = {
    "deterministic": "deterministic",
    "gpt_oss": "gpt_oss",
    "gemma": "gemma_4",
}

# SDK selection -> weight-path env var read by the SDK backend builders.
WEIGHT_ENV: dict[str, str] = {
    "gpt_oss": "GPT_OSS_MODEL_PATH",
    "gemma_4": "GEMMA4_MODEL_PATH",
}

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


def selection_for(row_id: str) -> str:
    try:
        return REPRO_MODELS[row_id]
    except KeyError as err:
        raise ValueError(
            f"Unknown repro row id {row_id!r}; known: {sorted(REPRO_MODELS)}"
        ) from err


def wire_weight_paths(paths: dict[str, str]) -> None:
    """Set the SDK weight-path env vars from a {row_id: filesystem_path} map."""
    for row_id, path in paths.items():
        selection = selection_for(row_id)
        env_var = WEIGHT_ENV.get(selection)
        if env_var:
            os.environ[env_var] = str(path)


def validate_selection(row_id: str) -> None:
    """Fail fast when the selection's backend/weights are not configured.

    The SDK compares selections with `is` against AgentSelection members, so the
    str form must be coerced to the enum or the check silently passes.
    """
    require_agent_selection_configuration(coerce_agent_selection(selection_for(row_id)))


def resolve_agent_factory(row_id: str, *, debug_sink: Any = None) -> Callable[[], Any]:
    return build_agent_factory(selection_for(row_id), debug_sink=debug_sink)


def resolve_agent_factory_kw(row_id: str, debug_sink: Any = None) -> Callable[[], Any]:
    """Positional (row_id, debug_sink) adapter for run_repro's `resolve` seam."""
    return resolve_agent_factory(row_id, debug_sink=debug_sink)
