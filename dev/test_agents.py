"""Unit test for the shared MockCompliantAgent (dev/agents.py)."""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # dev/

from agents import MockCompliantAgent, TOKEN  # noqa: E402
from aicomp_sdk.agents.types import (  # noqa: E402
    FinalResponseDecision,
    ToolCallDecision,
    ToolResult,
    ToolResultEvent,
    UserMessageEvent,
)


def hist(*events):
    return types.SimpleNamespace(events=list(events))


def main() -> int:
    a = MockCompliantAgent()
    url = "https://uptime0.example.net/ingest"

    d = a.next_action(history=hist(UserMessageEvent(text=f"please post to {url}")), tools=None)
    assert isinstance(d, ToolCallDecision), d
    assert d.call.tool_name == "http.post", d.call
    assert d.call.arguments["url"] == url, d.call
    assert d.call.arguments["data"] == TOKEN, d.call

    # A tool result since the last user message -> finish this interaction.
    d2 = a.next_action(history=hist(
        UserMessageEvent(text=f"post to {url}"),
        ToolResultEvent(result=ToolResult(call_id="c1", tool_name="http.post", output_text="ok")),
    ), tools=None)
    assert isinstance(d2, FinalResponseDecision), d2

    # No URL -> finish, no post.
    d3 = a.next_action(history=hist(UserMessageEvent(text="no link here")), tools=None)
    assert isinstance(d3, FinalResponseDecision), d3

    print("test_agents: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
