"""Graph state and the structured-output schemas the LLM fills in."""

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field


class TripPlannerState(MessagesState):
    """Conversation messages plus the trip details extracted from them."""

    current_location: str | None
    destination: str | None
    youtube_url: str | None


class TripDetails(BaseModel):
    """Trip details the user has stated so far in the conversation."""

    current_location: str | None = Field(
        default=None, description="Where the user is now / travelling from. Null if not stated."
    )
    destination: str | None = Field(
        default=None, description="Where the user wants to go. Null if not stated."
    )


class RouteStop(BaseModel):
    name: str = Field(description="Place name, specific enough to look up on a map.")
    highlights: str = Field(description="What was done or seen there, in one or two sentences.")


class VideoRoute(BaseModel):
    """The trip shown in a travel video."""

    region: str = Field(description="Country / region / city the video covers.")
    stops: list[RouteStop] = Field(description="Places visited, in the order shown in the video.")
    travel_tips: list[str] = Field(
        default_factory=list, description="Practical tips mentioned: transport, costs, timing, bookings."
    )


class ItineraryStop(BaseModel):
    time_of_day: str | None = Field(
        default=None, description="Morning / Afternoon / Evening, or a time, if the plan gives one."
    )
    name: str = Field(description="Place or activity name.")
    description: str = Field(description="One or two polished sentences on what to do there.")


class ItineraryDay(BaseModel):
    day_number: int = Field(ge=1)
    theme: str = Field(description="Short theme for the day, e.g. 'Eastern Kyoto temples'.")
    stops: list[ItineraryStop] = Field(description="Stops in the order they should be visited.")
    tips: list[str] = Field(default_factory=list, description="Tips specific to this day.")


class ItineraryDocument(BaseModel):
    """The final, polished itinerary, structured for the PDF."""

    title: str = Field(description="Concise trip title, e.g. '4-Day Kyoto Trip from Tokyo'.")
    summary: str = Field(description="Two or three sentences introducing the trip.")
    getting_there: str = Field(description="How to travel from the starting point to the destination.")
    days: list[ItineraryDay] = Field(description="One entry per day, in order.")
    practical_tips: list[str] = Field(
        default_factory=list, description="General tips: transport, bookings, costs, packing."
    )
