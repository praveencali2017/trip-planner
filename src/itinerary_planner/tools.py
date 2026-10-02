"""The agent's tools: mine a YouTube video for its route, or research a destination online."""

import asyncio
import logging

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt.tool_node import ToolInvocationError
from youtube_transcript_api import CouldNotRetrieveTranscript

from itinerary_planner.schemas import VideoRoute
from itinerary_planner.youtube import fetch_transcript, parse_video_id

logger = logging.getLogger(__name__)

YOUTUBE_TOOL_NAME = "extract_route_from_youtube"
RESEARCH_TOOL_NAME = "research_destination"

# Account-level failures: the planner's own next call would fail the same way, so don't
# hand them to the LLM — let them end the run and surface as an error event.
UNRECOVERABLE_ERRORS = (openai.AuthenticationError, openai.RateLimitError)


def describe_tool_error(error: Exception) -> str:
    """Turn a tool failure into a ToolMessage for the planner, which explains it to the user.

    Passed to ToolNode(handle_tool_errors=...); its default re-raises anything but bad
    arguments, which would crash the run and leave an unanswered tool call in the thread.
    """
    if isinstance(error, UNRECOVERABLE_ERRORS):
        raise error
    if isinstance(error, ToolInvocationError):
        return error.message
    logger.warning("Tool call failed: %r", error)
    if isinstance(error, CouldNotRetrieveTranscript):
        reason = f"could not get a transcript for this video ({type(error).__name__})"
    elif isinstance(error, ValueError):
        reason = str(error)
    else:
        reason = f"unexpected {type(error).__name__}"
    return f"TOOL ERROR: {reason}."


def build_tools(llm: BaseChatModel, model_name: str) -> list[BaseTool]:
    """Create the tools, bound to the given models (so importing this module needs no API key)."""
    route_extractor = llm.with_structured_output(VideoRoute)
    web_researcher = ChatOpenAI(model=model_name, use_responses_api=True).bind_tools(
        [{"type": "web_search"}]
    )

    @tool(YOUTUBE_TOOL_NAME)
    async def extract_route_from_youtube(youtube_url: str, current_location: str) -> str:
        """Extract the region, the ordered stops and the travel tips from a YouTube travel video.

        Use this whenever the user shared a YouTube URL. Returns JSON describing the route
        taken in the video, which you then adapt into an itinerary starting from current_location.
        """
        transcript_text = await asyncio.to_thread(fetch_transcript, parse_video_id(youtube_url))
        route = await route_extractor.ainvoke(
            [
                SystemMessage(
                    "You extract travel routes from video transcripts. List only places actually "
                    "visited in the video, in the order they were visited."
                ),
                HumanMessage(
                    f"The viewer will travel from {current_location}.\n\nTranscript:\n{transcript_text}"
                ),
            ]
        )
        return route.model_dump_json()

    @tool(RESEARCH_TOOL_NAME)
    async def research_destination(current_location: str, destination: str) -> str:
        """Research a destination on the web to plan a trip there from current_location.

        Use this only when the user did NOT share a YouTube URL. Returns a research summary:
        how to get there, the must-see places, a sensible order to visit them, and practical notes.
        """
        response = await web_researcher.ainvoke(
            f"I am travelling from {current_location} to {destination}. Search the web and summarise:\n"
            "1. How to get there from my location (transport options, rough travel time).\n"
            "2. The top places to visit and what each is known for.\n"
            "3. A sensible order to visit them, grouped by area.\n"
            "4. Current practical notes: best season, local transport, bookings, costs."
        )
        return response.text

    return [extract_route_from_youtube, research_destination]
