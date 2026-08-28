"""Debug-sink plumbing for the real-model repro harness.

`make_jsonl_sink` builds the SDK's own JSONL sink. `install_default_sink`
monkeypatches the agent constructors so that a *None* debug_sink is replaced by a
shared JsonlAgentDebugSink -- this is the durable, re-sync-proof version of the
"default the debug_sink parameter" trick, and it fires even when construction
passes debug_sink=None explicitly (as build_agent_factory does). Driven by the
AICOMP_DEBUG_SINK_PATH env var so it can instrument construction we don't control.

NOT wired into the scored attack.py; import and call this only from repro tooling.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any, Callable

from aicomp_sdk.agents.debug import JsonlAgentDebugSink
from aicomp_sdk.agents.deterministic_agent import VulnerableDeterministicAgent
from aicomp_sdk.agents.gemma_agent import GemmaAgent
from aicomp_sdk.agents.gemma4_agent import Gemma4Agent
from aicomp_sdk.agents.gpt_oss_agent import GPTOSSAgent

DEFAULT_SINK_ENV = "AICOMP_DEBUG_SINK_PATH"

# Agents whose __init__ takes a keyword-only `debug_sink`.
_PATCH_TARGETS: tuple[type, ...] = (
    VulnerableDeterministicAgent,
    GPTOSSAgent,
    GemmaAgent,
    Gemma4Agent,
)
_ORIGINALS: dict[type, Callable[..., Any]] = {}


def resolve_sink_path(explicit: str | None = None) -> Path | None:
    """Path precedence: explicit arg > env var > None (disabled)."""
    if explicit:
        return Path(explicit)
    env = os.environ.get(DEFAULT_SINK_ENV)
    return Path(env) if env else None


def make_jsonl_sink(path: str | Path) -> JsonlAgentDebugSink:
    return JsonlAgentDebugSink(Path(path))


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


def uninstall_default_sink() -> None:
    """Restore the original agent __init__s (undo install_default_sink)."""
    for cls, original in _ORIGINALS.items():
        cls.__init__ = original  # type: ignore[assignment]
    _ORIGINALS.clear()
