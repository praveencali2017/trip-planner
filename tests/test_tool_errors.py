import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from youtube_transcript_api import TranscriptsDisabled

from itinerary_planner.graph import drop_unanswered_tool_calls
from itinerary_planner.tools import describe_tool_error


@tool
def no_transcript_tool(youtube_url: str) -> str:
    """Stand-in for the YouTube tool on a video without captions."""
    raise TranscriptsDisabled("abc123")


@tool
def bad_url_tool(youtube_url: str) -> str:
    """Stand-in for the YouTube tool given a non-YouTube URL."""
    raise ValueError(f"Not a recognised YouTube video URL: {youtube_url!r}")


@tool
def quota_tool(youtube_url: str) -> str:
    """Stand-in for a tool whose inner LLM call hits the quota."""
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    raise openai.RateLimitError("insufficient_quota", response=response, body=None)


def call(tool_name: str, call_id: str = "call-1") -> dict:
    message = AIMessage("", tool_calls=[{"name": tool_name, "args": {"youtube_url": "u"}, "id": call_id}])
    return {"messages": [message]}


async def run_tool_node(tool_obj, tool_name: str) -> ToolMessage:
    builder = StateGraph(MessagesState)
    builder.add_node("tools", ToolNode([tool_obj], handle_tool_errors=describe_tool_error))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    result = await builder.compile().ainvoke(call(tool_name))
    return result["messages"][-1]


async def test_transcript_failure_is_returned_to_the_llm() -> None:
    message = await run_tool_node(no_transcript_tool, "no_transcript_tool")

    assert message.status == "error"
    assert message.tool_call_id == "call-1"
    assert message.content.startswith("TOOL ERROR: could not get a transcript")


async def test_bad_url_is_returned_to_the_llm() -> None:
    message = await run_tool_node(bad_url_tool, "bad_url_tool")

    assert message.status == "error"
    assert "Not a recognised YouTube video URL" in message.content


async def test_quota_errors_are_not_handed_to_the_llm() -> None:
    with pytest.raises(openai.RateLimitError):
        await run_tool_node(quota_tool, "quota_tool")


def test_drop_unanswered_tool_calls_repairs_a_crashed_thread() -> None:
    dangling = AIMessage("", tool_calls=[{"name": "t", "args": {}, "id": "lost"}])
    answered = AIMessage("", tool_calls=[{"name": "t", "args": {}, "id": "ok"}])
    reply = ToolMessage("result", tool_call_id="ok")
    history = [HumanMessage("plan"), dangling, HumanMessage("again"), answered, reply]

    assert drop_unanswered_tool_calls(history) == [history[0], history[2], answered, reply]
