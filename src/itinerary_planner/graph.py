"""The itinerary-planner LangGraph: check the trip details, then plan with tools (ReAct)."""

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from itinerary_planner.config import Settings
from itinerary_planner.schemas import TripDetails, TripPlannerState
from itinerary_planner.tools import build_tools, describe_tool_error
from itinerary_planner.youtube import find_youtube_url

EXTRACT_DETAILS_NODE = "extract_trip_details"
REQUEST_DETAILS_NODE = "request_missing_details"
PLANNER_NODE = "planner"
TOOLS_NODE = "tools"

EXTRACTION_PROMPT = (
    "Extract the trip details the user has stated anywhere in this conversation. "
    "Use null for anything not stated; never guess."
)

PLANNER_PROMPT = """You are a travel itinerary planner.

Known trip details:
- Current location: {current_location}
- Destination: {destination}
- YouTube video: {youtube_url}

Gather information first:
- If a YouTube video is given, call extract_route_from_youtube and base the trip on the route in the video.
- Otherwise, call research_destination.

If a tool result starts with "TOOL ERROR":
- Tell the user plainly what went wrong (e.g. the video has no transcript), without technical jargon.
- If the destination is known, fall back to research_destination and still plan the trip.
- Otherwise, ask the user for another video or for their destination. Never make up a route.

Then write a day-by-day itinerary in Markdown: getting there from the current location, each day's
stops in a sensible order, and practical tips. Do not invent places the tools did not mention."""


def find_missing_details(state: TripPlannerState) -> list[str]:
    """Details required before planning: location always; destination only without a video."""
    missing = []
    if not state.get("current_location"):
        missing.append("your current location (where you'll be travelling from)")
    if not state.get("youtube_url") and not state.get("destination"):
        missing.append("your destination, or a YouTube travel video URL to base the trip on")
    return missing


def route_after_extraction(state: TripPlannerState) -> str:
    return REQUEST_DETAILS_NODE if find_missing_details(state) else PLANNER_NODE


def request_missing_details(state: TripPlannerState) -> dict:
    bullet_list = "\n".join(f"- {item}" for item in find_missing_details(state))
    message = AIMessage(
        f"To plan your itinerary I still need:\n{bullet_list}", name=REQUEST_DETAILS_NODE
    )
    return {"messages": [message]}


def find_latest_youtube_url(state: TripPlannerState) -> str | None:
    """The most recent YouTube URL the user shared, so a new video replaces an old one."""
    human_texts = (m.text for m in reversed(state["messages"]) if isinstance(m, HumanMessage))
    return next((url for text in human_texts if (url := find_youtube_url(text))), None)


def drop_unanswered_tool_calls(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Remove AI tool-call messages that have no ToolMessage reply.

    A run that crashes mid-tool leaves one in the checkpoint, and OpenAI rejects any
    history containing it — this keeps such a thread usable instead of failing forever.
    """
    answered_ids = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    return [
        m
        for m in messages
        if not (
            isinstance(m, AIMessage)
            and m.tool_calls
            and any(call["id"] not in answered_ids for call in m.tool_calls)
        )
    ]


def build_graph(settings: Settings, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    llm = ChatOpenAI(model=settings.model_name)
    tools = build_tools(llm, settings.model_name)
    details_extractor = llm.with_structured_output(TripDetails)
    planner_llm = llm.bind_tools(tools)

    async def extract_trip_details(state: TripPlannerState) -> dict:
        details = await details_extractor.ainvoke(
            [SystemMessage(EXTRACTION_PROMPT), *drop_unanswered_tool_calls(state["messages"])]
        )
        return {
            "current_location": details.current_location,
            "destination": details.destination,
            "youtube_url": find_latest_youtube_url(state),
        }

    async def planner(state: TripPlannerState) -> dict:
        system_prompt = PLANNER_PROMPT.format(
            current_location=state["current_location"],
            destination=state.get("destination") or "not given",
            youtube_url=state.get("youtube_url") or "not given",
        )
        history = drop_unanswered_tool_calls(state["messages"])
        response = await planner_llm.ainvoke([SystemMessage(system_prompt), *history])
        return {"messages": [response]}

    builder = StateGraph(TripPlannerState)
    builder.add_node(EXTRACT_DETAILS_NODE, extract_trip_details)
    builder.add_node(REQUEST_DETAILS_NODE, request_missing_details)
    builder.add_node(PLANNER_NODE, planner)
    builder.add_node(TOOLS_NODE, ToolNode(tools, handle_tool_errors=describe_tool_error))

    builder.add_edge(START, EXTRACT_DETAILS_NODE)
    builder.add_conditional_edges(
        EXTRACT_DETAILS_NODE, route_after_extraction, [REQUEST_DETAILS_NODE, PLANNER_NODE]
    )
    builder.add_edge(REQUEST_DETAILS_NODE, END)
    builder.add_conditional_edges(PLANNER_NODE, tools_condition)  # tool calls -> "tools", else END
    builder.add_edge(TOOLS_NODE, PLANNER_NODE)

    return builder.compile(checkpointer=checkpointer)
