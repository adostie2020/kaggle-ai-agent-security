"""Map repro row ids to the real SDK agent factory, with weight-path wiring.

Row ids match the Kaggle submission's Id column (gpt_oss, gemma). The gemma row
defaults to the SDK's `gemma_4` selection (google/gemma-4-26B-A4B-it), per the
spec's model identification; confirm against the mounted competition harness in a
kernel before trusting scores, and override REPRO_MODELS["gemma"] if it disagrees.
"""
from __future__ import annotations

import os
from typing import Any, Callable

from aicomp_sdk.agents.factory import (
    build_agent_factory,
    coerce_agent_selection,
    require_agent_selection_configuration,
)

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
