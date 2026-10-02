import pytest
from langchain_core.messages import AIMessage, HumanMessage

from itinerary_planner.graph import (
    PLANNER_NODE,
    REQUEST_DETAILS_NODE,
    find_latest_youtube_url,
    find_missing_details,
    route_after_extraction,
)


def make_state(location=None, destination=None, youtube_url=None) -> dict:
    return {
        "messages": [],
        "current_location": location,
        "destination": destination,
        "youtube_url": youtube_url,
    }


@pytest.mark.parametrize(
    ("state", "missing_count", "route"),
    [
        (make_state(), 2, REQUEST_DETAILS_NODE),
        (make_state(destination="Kyoto"), 1, REQUEST_DETAILS_NODE),
        (make_state(youtube_url="https://youtu.be/x"), 1, REQUEST_DETAILS_NODE),
        (make_state(location="Tokyo"), 1, REQUEST_DETAILS_NODE),
        (make_state(location="Tokyo", destination="Kyoto"), 0, PLANNER_NODE),
        (make_state(location="Tokyo", youtube_url="https://youtu.be/x"), 0, PLANNER_NODE),
    ],
)
def test_missing_details_and_routing(state: dict, missing_count: int, route: str) -> None:
    assert len(find_missing_details(state)) == missing_count
    assert route_after_extraction(state) == route


def test_latest_youtube_url_wins_and_ignores_ai_messages() -> None:
    state = {
        "messages": [
            HumanMessage("Like this: https://youtu.be/first"),
            AIMessage("Here is https://youtu.be/from-ai"),
            HumanMessage("Actually use https://youtu.be/second"),
            HumanMessage("I'm in Tokyo"),
        ]
    }
    assert find_latest_youtube_url(state) == "https://youtu.be/second"
