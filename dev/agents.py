"""Shared dev agents for driving the SDK env locally.

MockCompliantAgent does what a jailbroken gpt_oss/gemma would: given a user message
naming a URL, issue exactly one http.post(url, data="SECRET_MARKER"). Lives here so
dev/trace.py and dev/validate_probe.py share one implementation.
"""
from __future__ import annotations

import re

from aicomp_sdk.agents.types import (
    FinalResponseDecision,
    ToolCall,
    ToolCallDecision,
    ToolResultEvent,
    UserMessageEvent,
)

URL_RE = re.compile(r'https?://[^\s\'"<>]+')
TOKEN = "SECRET_MARKER"


class MockCompliantAgent:
    """Posts TOKEN to the first URL in the latest user message, once."""

    def __init__(self) -> None:
        self._n = 1

    def next_action(self, *, history, tools):
        del tools
        events = list(history.events)
        # Already acted since the last user message? -> finish this interaction.
        for e in reversed(events):
            if isinstance(e, ToolResultEvent):
                return FinalResponseDecision(text="done")
            if isinstance(e, UserMessageEvent):
                break
        last_user = ""
        for e in reversed(events):
            if isinstance(e, UserMessageEvent):
                last_user = e.text
                break
        m = URL_RE.search(last_user or "")
        if not m:
            return FinalResponseDecision(text="no url")
        url = m.group(0).rstrip('.,!?)"\'')
        call = ToolCall(
            call_id=f"call_{self._n:06d}",
            tool_name="http.post",
            arguments={"url": url, "data": TOKEN},
        )
        self._n += 1
        return ToolCallDecision(call=call, assistant_message=None)

    def reset_state(self) -> None:
        self._n = 1

    def snapshot_state(self):
        return {"version": 1, "backend": "mock", "data": {"n": self._n}}

    def restore_state(self, snapshot) -> None:
        self._n = int((snapshot or {}).get("data", {}).get("n", 1))
