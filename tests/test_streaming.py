import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from itinerary_planner.api import MAX_MESSAGE_LENGTH, create_app
from itinerary_planner.config import Settings
from itinerary_planner.graph import EXTRACT_DETAILS_NODE, PLANNER_NODE, REQUEST_DETAILS_NODE, TOOLS_NODE
from itinerary_planner.streaming import (
    ChatEvent,
    describe_error,
    describe_tool_call,
    events_from_updates,
    stream_reply,
)
from itinerary_planner.tools import RESEARCH_TOOL_NAME, YOUTUBE_TOOL_NAME

TEST_SETTINGS = Settings(model_name="test-model", frontend_origin="http://localhost:5173")


class UnusedPolisher:
    """These tests never export a PDF; this keeps the app from building a real OpenAI client."""


def make_app(graph: "ScriptedGraph"):
    return create_app(TEST_SETTINGS, graph, UnusedPolisher())  # type: ignore[arg-type]


class ScriptedGraph:
    """Stands in for the compiled graph: replays (mode, payload) tuples, optionally then raises."""

    def __init__(self, script: list[tuple[str, Any]], error: Exception | None = None) -> None:
        self.script = script
        self.error = error
        self.calls: list[tuple[Any, Any]] = []

    async def astream(self, graph_input: Any, config: Any, stream_mode: Any) -> AsyncIterator[Any]:
        self.calls.append((graph_input, config))
        for item in self.script:
            yield item
        if self.error:
            raise self.error


def message_event(text: str, node: str) -> tuple[str, Any]:
    return ("messages", (AIMessageChunk(content=text), {"langgraph_node": node}))


async def collect(graph: ScriptedGraph) -> list[ChatEvent]:
    return [event async for event in stream_reply(graph, "thread-1", "hi")]  # type: ignore[arg-type]


async def test_streams_only_planner_text_and_reports_tool_calls() -> None:
    tool_call_message = AIMessage(
        content="",
        tool_calls=[{"name": RESEARCH_TOOL_NAME, "args": {"destination": "Kyoto"}, "id": "c1"}],
    )
    graph = ScriptedGraph(
        [
            message_event('{"destination": "Kyoto"}', EXTRACT_DETAILS_NODE),
            ("updates", {EXTRACT_DETAILS_NODE: {"destination": "Kyoto"}}),
            ("updates", {PLANNER_NODE: {"messages": [tool_call_message]}}),
            message_event("internal research text", TOOLS_NODE),
            message_event("", PLANNER_NODE),
            message_event("Day 1", PLANNER_NODE),
            message_event(": Fushimi Inari", PLANNER_NODE),
        ]
    )

    events = await collect(graph)

    assert events == [
        ChatEvent("status", {"message": "Researching Kyoto on the web…"}),
        ChatEvent("token", {"text": "Day 1"}),
        ChatEvent("token", {"text": ": Fushimi Inari"}),
        ChatEvent("done"),
    ]
    graph_input, config = graph.calls[0]
    assert config == {"configurable": {"thread_id": "thread-1"}}
    assert graph_input["messages"][0].content == "hi"


async def test_missing_details_reply_is_sent_once_as_a_token() -> None:
    reply = AIMessage("To plan your itinerary I still need:\n- your current location")
    graph = ScriptedGraph(
        [
            ("messages", (reply, {"langgraph_node": REQUEST_DETAILS_NODE})),
            ("updates", {REQUEST_DETAILS_NODE: {"messages": [reply]}}),
        ]
    )

    assert await collect(graph) == [ChatEvent("token", {"text": reply.text}), ChatEvent("done")]


async def test_quota_error_becomes_error_event_then_done() -> None:
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    quota_error = openai.RateLimitError(
        "Error code: 429 - insufficient_quota", response=response, body=None
    )
    graph = ScriptedGraph([message_event("Day 1", PLANNER_NODE)], error=quota_error)

    events = await collect(graph)

    assert events[0] == ChatEvent("token", {"text": "Day 1"})
    assert events[1].name == "error" and "run out of credits" in events[1].data["message"]
    assert events[2] == ChatEvent("done")


async def test_unexpected_error_hides_details() -> None:
    graph = ScriptedGraph([], error=RuntimeError("secret internal detail"))

    events = await collect(graph)

    assert events[0].name == "error"
    assert "secret internal detail" not in events[0].data["message"]


def parse_sse(body: str) -> list[tuple[str, dict]]:
    frames = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        frames.append((lines["event"], json.loads(lines["data"])))
    return frames


def test_chat_endpoint_streams_sse_frames() -> None:
    graph = ScriptedGraph([message_event("Hello", PLANNER_NODE), message_event(" there", PLANNER_NODE)])
    with TestClient(make_app(graph)) as client:
        response = client.post("/api/chat", json={"thread_id": "t1", "message": "hi"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert parse_sse(response.text) == [
        ("token", {"text": "Hello"}),
        ("token", {"text": " there"}),
        ("done", {}),
    ]


def test_chat_endpoint_rejects_empty_message() -> None:
    with TestClient(make_app(ScriptedGraph([]))) as client:
        response = client.post("/api/chat", json={"thread_id": "t1", "message": ""})

    assert response.status_code == 422


def test_health() -> None:
    with TestClient(make_app(ScriptedGraph([]))) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


# --- user-facing messages -----------------------------------------------------------------

def openai_error(error_type: type[openai.APIStatusError], status: int, message: str) -> openai.APIStatusError:
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    return error_type(message, response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (openai_error(openai.RateLimitError, 429, "insufficient_quota"), "run out of credits"),
        (openai_error(openai.RateLimitError, 429, "rate_limit_exceeded"), "rate limiting requests"),
        (openai_error(openai.AuthenticationError, 401, "invalid_api_key"), "API key was rejected"),
        (ValueError("boom"), "Something went wrong"),
    ],
)
def test_describe_error(error: Exception, expected: str) -> None:
    assert expected in describe_error(error)


@pytest.mark.parametrize(
    ("tool_call", "expected"),
    [
        ({"name": YOUTUBE_TOOL_NAME, "args": {}}, "Watching the YouTube video…"),
        ({"name": RESEARCH_TOOL_NAME, "args": {"destination": "Lisbon"}}, "Researching Lisbon on the web…"),
        ({"name": RESEARCH_TOOL_NAME, "args": {}}, "Researching your destination on the web…"),
        ({"name": "mystery_tool", "args": {}}, "Running mystery_tool…"),
    ],
)
def test_describe_tool_call(tool_call: dict, expected: str) -> None:
    assert describe_tool_call(tool_call) == expected


def test_updates_from_nodes_without_messages_emit_nothing() -> None:
    # Nodes like extract_trip_details return state fields only; some updates are None.
    assert events_from_updates({EXTRACT_DETAILS_NODE: {"destination": "Kyoto"}, TOOLS_NODE: None}) == []


# --- request validation & CORS ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"thread_id": "t1", "message": "x" * MAX_MESSAGE_LENGTH}, 200),
        ({"thread_id": "t1", "message": "x" * (MAX_MESSAGE_LENGTH + 1)}, 422),
        ({"thread_id": "t" * 100, "message": "hi"}, 200),
        ({"thread_id": "t" * 101, "message": "hi"}, 422),
        ({"thread_id": "", "message": "hi"}, 422),
        ({"message": "hi"}, 422),
        # Documents current behaviour: whitespace-only passes validation (see test report).
        ({"thread_id": "t1", "message": "   "}, 200),
    ],
)
def test_chat_request_limits(body: dict, status: int) -> None:
    with TestClient(make_app(ScriptedGraph([]))) as client:
        assert client.post("/api/chat", json=body).status_code == status


def test_cors_allows_only_the_configured_frontend_origin() -> None:
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    with TestClient(make_app(ScriptedGraph([]))) as client:
        allowed = client.options("/api/chat", headers={"Origin": "http://localhost:5173", **preflight})
        blocked = client.options("/api/chat", headers={"Origin": "https://evil.example", **preflight})

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert blocked.status_code == 400
    assert "access-control-allow-origin" not in blocked.headers
