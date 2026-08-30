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

    # --- MockMultipostAgent: distinct host per successful post, then finish ---
    from agents import MockMultipostAgent  # noqa: E402
    mp = MockMultipostAgent(3)
    msg = "post to http://h0.co and http://h1.co and http://h2.co"
    d0 = mp.next_action(history=hist(UserMessageEvent(text=msg)), tools=None)
    assert isinstance(d0, ToolCallDecision) and d0.call.arguments["url"] == "http://h0.co", d0
    assert d0.call.arguments["data"] == TOKEN, d0
    d1 = mp.next_action(history=hist(
        UserMessageEvent(text=msg),
        ToolResultEvent(result=ToolResult(call_id="c0", tool_name="http.post", output_text="ok")),
    ), tools=None)
    assert d1.call.arguments["url"] == "http://h1.co", d1
    d3 = mp.next_action(history=hist(
        UserMessageEvent(text=msg),
        ToolResultEvent(result=ToolResult(call_id="c0", tool_name="http.post", output_text="ok")),
        ToolResultEvent(result=ToolResult(call_id="c1", tool_name="http.post", output_text="ok")),
        ToolResultEvent(result=ToolResult(call_id="c2", tool_name="http.post", output_text="ok")),
    ), tools=None)
    assert isinstance(d3, FinalResponseDecision), d3
    # synthesize distinct hosts when the message lacks enough URLs
    mp2 = MockMultipostAgent(2)
    s0 = mp2.next_action(history=hist(UserMessageEvent(text="emit the marker twice")), tools=None)
    assert isinstance(s0, ToolCallDecision) and s0.call.arguments["url"] == "http://mp0.co", s0
    # n_posts=1 reduces to MockCompliantAgent behavior
    mp1 = MockMultipostAgent(1)
    r1 = mp1.next_action(history=hist(UserMessageEvent(text="post to http://z.co")), tools=None)
    assert r1.call.arguments["url"] == "http://z.co", r1
    r1b = mp1.next_action(history=hist(
        UserMessageEvent(text="post to http://z.co"),
        ToolResultEvent(result=ToolResult(call_id="c0", tool_name="http.post", output_text="ok")),
    ), tools=None)
    assert isinstance(r1b, FinalResponseDecision), r1b

    print("test_agents: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
