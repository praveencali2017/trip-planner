"""The real compiled graph + checkpointer + ToolNode + stream_reply, with only OpenAI and the
YouTube transcript fetch faked. These pin the conversation flows end to end."""

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from youtube_transcript_api import TranscriptsDisabled

import itinerary_planner.tools
from itinerary_planner.config import Settings
from itinerary_planner.graph import REQUEST_DETAILS_NODE, build_graph
from itinerary_planner.schemas import RouteStop, TripDetails, VideoRoute
from itinerary_planner.streaming import ChatEvent, stream_reply
from itinerary_planner.tools import RESEARCH_TOOL_NAME, YOUTUBE_TOOL_NAME

SETTINGS = Settings(model_name="test-model", frontend_origin="http://localhost:5173")


def tool_call(name: str, args: dict, call_id: str = "call-1") -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": call_id}])


def quota_error() -> openai.RateLimitError:
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    return openai.RateLimitError("Error code: 429 - insufficient_quota", response=response, body=None)


def details(location: str | None = None, destination: str | None = None):
    return lambda _messages: TripDetails(current_location=location, destination=destination)


async def run_turn(graph, thread_id: str, message: str) -> list[ChatEvent]:
    return [event async for event in stream_reply(graph, thread_id, message)]


def reply_text(events: list[ChatEvent]) -> str:
    return "".join(event.data["text"] for event in events if event.name == "token")


def has_unanswered_tool_call(messages) -> bool:
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    return any(
        isinstance(m, AIMessage) and any(call["id"] not in answered for call in m.tool_calls)
        for m in messages
    )


@pytest.fixture
def graph(chat_model, web_researcher):
    return build_graph(SETTINGS, InMemorySaver())


async def test_missing_location_asks_and_skips_the_planner(graph, chat_model) -> None:
    chat_model.structured[TripDetails] = details(destination="Kyoto")

    events = await run_turn(graph, "t1", "Plan me 4 days in Kyoto")

    assert events == [
        ChatEvent("token", {"text": "To plan your itinerary I still need:\n"
                                    "- your current location (where you'll be travelling from)"}),
        ChatEvent("done"),
    ]
    assert chat_model.calls == []  # planner never ran
    state = await graph.aget_state({"configurable": {"thread_id": "t1"}})
    assert state.values["messages"][-1].name == REQUEST_DETAILS_NODE


async def test_follow_up_turn_researches_and_streams_the_itinerary(graph, chat_model, web_researcher) -> None:
    chat_model.structured[TripDetails] = details(destination="Kyoto")
    await run_turn(graph, "t1", "Plan me 4 days in Kyoto")

    chat_model.structured[TripDetails] = details(location="Tokyo", destination="Kyoto")
    chat_model.responses = [
        tool_call(RESEARCH_TOOL_NAME, {"current_location": "Tokyo", "destination": "Kyoto"}),
        AIMessage("Day 1: Kiyomizu-dera and Gion."),
    ]
    web_researcher.responses = [AIMessage("Kyoto research: Kiyomizu-dera, Gion.")]

    events = await run_turn(graph, "t1", "I'm in Tokyo")

    assert events[0] == ChatEvent("status", {"message": "Researching Kyoto on the web…"})
    assert reply_text(events) == "Day 1: Kiyomizu-dera and Gion."
    assert sum(event.name == "token" for event in events) > 1  # streamed, not one blob
    assert events[-1] == ChatEvent("done")

    # The extractor saw the whole thread, so the earlier "Kyoto" turn was still in context.
    _, extraction_prompt = chat_model.structured_calls[-1]
    assert any("Kyoto" in m.text for m in extraction_prompt)
    # The researcher was asked about the right trip, and its result reached the planner.
    assert "Tokyo" in web_researcher.calls[0][0].text and "Kyoto" in web_researcher.calls[0][0].text
    planner_system_prompt = chat_model.calls[0][0]
    assert isinstance(planner_system_prompt, SystemMessage)
    assert "Current location: Tokyo" in planner_system_prompt.text
    tool_results = [m for m in chat_model.calls[1] if isinstance(m, ToolMessage)]
    assert [m.text for m in tool_results] == ["Kyoto research: Kiyomizu-dera, Gion."]


async def test_youtube_video_route_is_extracted_and_returned_to_the_planner(
    graph, chat_model, monkeypatch
) -> None:
    fetched_ids: list[str] = []
    monkeypatch.setattr(
        itinerary_planner.tools, "fetch_transcript", lambda video_id: fetched_ids.append(video_id) or "We walked..."
    )
    route = VideoRoute(region="San Francisco", stops=[RouteStop(name="Lands End", highlights="Coastal walk")])
    chat_model.structured[TripDetails] = details(location="London")
    chat_model.structured[VideoRoute] = lambda _messages: route
    url = "https://youtu.be/abc123?si=share"
    chat_model.responses = [
        tool_call(YOUTUBE_TOOL_NAME, {"youtube_url": url, "current_location": "London"}),
        AIMessage("Day 1: Lands End."),
    ]

    events = await run_turn(graph, "yt", f"I'm in London, plan it like {url}")

    assert events[0] == ChatEvent("status", {"message": "Watching the YouTube video…"})
    assert reply_text(events) == "Day 1: Lands End."
    assert fetched_ids == ["abc123"]
    tool_result = next(m for m in chat_model.calls[1] if isinstance(m, ToolMessage))
    assert VideoRoute.model_validate_json(tool_result.text) == route
    assert "YouTube video: https://youtu.be/abc123?si=share" in chat_model.calls[0][0].text


async def test_video_without_transcript_is_explained_by_the_llm_not_raised(
    graph, chat_model, monkeypatch
) -> None:
    def no_transcript(video_id: str) -> str:
        raise TranscriptsDisabled(video_id)

    monkeypatch.setattr(itinerary_planner.tools, "fetch_transcript", no_transcript)
    chat_model.structured[TripDetails] = details(location="London")
    chat_model.responses = [
        tool_call(YOUTUBE_TOOL_NAME, {"youtube_url": "https://youtu.be/nope", "current_location": "London"}),
        AIMessage("That video has no transcript. Send another link or a destination."),
    ]

    events = await run_turn(graph, "yt", "I'm in London: https://youtu.be/nope")

    assert [event.name for event in events if event.name != "token"] == ["status", "done"]
    assert reply_text(events) == "That video has no transcript. Send another link or a destination."
    tool_result = next(m for m in chat_model.calls[1] if isinstance(m, ToolMessage))
    assert tool_result.status == "error"
    assert tool_result.text.startswith("TOOL ERROR: could not get a transcript")


async def test_thread_recovers_after_a_run_crashes_mid_tool_call(graph, chat_model, web_researcher) -> None:
    """Regression: a crash after the planner's tool call left it unanswered in the checkpoint,
    and every later turn on that thread failed with OpenAI's 400 'tool_calls must be followed'."""
    chat_model.structured[TripDetails] = details(location="Tokyo", destination="Kyoto")
    chat_model.responses = [tool_call(RESEARCH_TOOL_NAME, {"current_location": "Tokyo", "destination": "Kyoto"})]
    web_researcher.responses = [quota_error()]

    crashed = await run_turn(graph, "t1", "I'm in Tokyo, 4 days in Kyoto")

    assert crashed[-2].name == "error" and "run out of credits" in crashed[-2].data["message"]
    assert crashed[-1] == ChatEvent("done")
    state = await graph.aget_state({"configurable": {"thread_id": "t1"}})
    assert has_unanswered_tool_call(state.values["messages"])  # the poisoned checkpoint exists

    chat_model.responses = [AIMessage("Here is your Kyoto plan.")]
    retried = await run_turn(graph, "t1", "Try again please")

    assert reply_text(retried) == "Here is your Kyoto plan."
    assert not any(event.name == "error" for event in retried)
    _, extraction_prompt = chat_model.structured_calls[-1]
    assert not has_unanswered_tool_call(extraction_prompt)
    assert not has_unanswered_tool_call(chat_model.calls[-1])


async def test_threads_are_isolated(graph, chat_model) -> None:
    chat_model.structured[TripDetails] = lambda messages: TripDetails(
        current_location="Tokyo" if any("Tokyo" in m.text for m in messages) else None,
        destination="Kyoto",
    )
    chat_model.responses = [AIMessage("Plan for thread A.")]

    await run_turn(graph, "thread-a", "I'm in Tokyo, 4 days in Kyoto")
    other = await run_turn(graph, "thread-b", "4 days in Kyoto")

    assert "current location" in reply_text(other)
