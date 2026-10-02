from types import SimpleNamespace

import pymupdf
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from itinerary_planner.api import create_app
from itinerary_planner.config import Settings
from itinerary_planner.graph import REQUEST_DETAILS_NODE
from itinerary_planner.itinerary_pdf import (
    pdf_filename,
    render_itinerary_pdf,
    select_itinerary_messages,
)
from itinerary_planner.schemas import ItineraryDay, ItineraryDocument, ItineraryStop

TEST_SETTINGS = Settings(model_name="test-model", frontend_origin="http://localhost:5173")

SAMPLE_DOCUMENT = ItineraryDocument(
    title="4-Day 京都 Trip from Tokyo",
    summary="Temples, food and café’s – day 1 starts early.",
    getting_there="Take the Tokaido Shinkansen to Kyoto Station.",
    days=[
        ItineraryDay(
            day_number=1,
            theme="Eastern Kyoto",
            stops=[
                ItineraryStop(time_of_day="Morning", name="Kiyomizu-dera", description="Arrive early."),
                ItineraryStop(name="Gion <script>alert(1)</script>", description="Evening stroll."),
            ],
            tips=["Wear comfortable shoes."],
        )
    ],
    practical_tips=["Get an ICOCA card."],
)


def pdf_text(content: bytes) -> str:
    return "".join(page.get_text() for page in pymupdf.open(stream=content, filetype="pdf"))


# --- selection -------------------------------------------------------------

def test_selects_only_itinerary_turns_including_refinements() -> None:
    intake_q = HumanMessage("Plan 4 days in Kyoto")
    intake_a = AIMessage("To plan your itinerary I still need: ...", name=REQUEST_DETAILS_NODE)
    plan_q = HumanMessage("I'm in Tokyo")
    tool_call = AIMessage("", tool_calls=[{"name": "research_destination", "args": {}, "id": "c1"}])
    tool_output = ToolMessage("raw web research", tool_call_id="c1")
    plan_a = AIMessage("# 4-Day Kyoto Trip ...")
    refine_q = HumanMessage("Make day 2 more relaxed")
    refine_a = AIMessage("# Updated 4-Day Kyoto Trip ...")
    history = [intake_q, intake_a, plan_q, tool_call, tool_output, plan_a, refine_q, refine_a]

    assert select_itinerary_messages(history) == [plan_q, plan_a, refine_q, refine_a]


def test_selection_is_empty_without_a_plan() -> None:
    history = [
        HumanMessage("Plan 4 days in Kyoto"),
        AIMessage("To plan your itinerary I still need: ...", name=REQUEST_DETAILS_NODE),
    ]
    assert select_itinerary_messages(history) == []
    assert select_itinerary_messages([]) == []


# --- rendering ---------------------------------------------------------------

def test_render_produces_structured_unicode_pdf() -> None:
    content = render_itinerary_pdf(SAMPLE_DOCUMENT)

    assert content.startswith(b"%PDF")
    text = pdf_text(content)
    for expected in ["4-Day 京都 Trip from Tokyo", "café’s – day 1", "Getting there", "Day 1: Eastern Kyoto",
                     "Kiyomizu-dera", "Practical tips", "Get an ICOCA card."]:
        assert expected in text


def test_render_escapes_markup_in_fields() -> None:
    assert "Gion <script>alert(1)</script>" in pdf_text(render_itinerary_pdf(SAMPLE_DOCUMENT))


@pytest.mark.parametrize(
    ("title", "filename"),
    [
        ("4-Day Kyoto Trip from Tokyo", "4-day-kyoto-trip-from-tokyo.pdf"),
        ("  Lisbon: 3 days!! ", "lisbon-3-days.pdf"),
        ("京都", "itinerary.pdf"),
        ("", "itinerary.pdf"),
    ],
)
def test_pdf_filename(title: str, filename: str) -> None:
    assert pdf_filename(title) == filename


# --- API -------------------------------------------------------------------------

class StateGraphStub:
    def __init__(self, messages: list) -> None:
        self.messages = messages
        self.requested_configs: list = []

    async def aget_state(self, config: dict) -> SimpleNamespace:
        self.requested_configs.append(config)
        return SimpleNamespace(values={"messages": self.messages})


class PolisherStub:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.received: list = []

    async def polish(self, messages: list) -> ItineraryDocument:
        self.received = list(messages)
        if self.error:
            raise self.error
        return SAMPLE_DOCUMENT


PLANNED_HISTORY = [HumanMessage("I'm in Tokyo, 4 days in Kyoto"), AIMessage("# 4-Day Kyoto Trip ...")]


def post_pdf(graph, polisher, body: dict | None = None):
    with TestClient(create_app(TEST_SETTINGS, graph, polisher)) as client:  # type: ignore[arg-type]
        return client.post("/api/itinerary-pdf", json=body if body is not None else {"thread_id": "t1"})


def test_pdf_endpoint_returns_attachment() -> None:
    graph, polisher = StateGraphStub(PLANNED_HISTORY), PolisherStub()

    response = post_pdf(graph, polisher)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="4-day-trip-from-tokyo.pdf"'
    assert response.content.startswith(b"%PDF")
    assert graph.requested_configs == [{"configurable": {"thread_id": "t1"}}]
    assert polisher.received == PLANNED_HISTORY


def test_pdf_endpoint_conflict_without_itinerary() -> None:
    polisher = PolisherStub()

    response = post_pdf(StateGraphStub([HumanMessage("hi")]), polisher)

    assert response.status_code == 409
    assert "no itinerary" in response.json()["detail"]
    assert polisher.received == []


def test_pdf_endpoint_reports_llm_failure() -> None:
    response = post_pdf(StateGraphStub(PLANNED_HISTORY), PolisherStub(error=RuntimeError("internal detail")))

    assert response.status_code == 502
    assert "internal detail" not in response.json()["detail"]


def test_pdf_endpoint_requires_thread_id() -> None:
    assert post_pdf(StateGraphStub([]), PolisherStub(), body={}).status_code == 422
