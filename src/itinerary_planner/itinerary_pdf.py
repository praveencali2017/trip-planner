"""Turn the itinerary discussed in a conversation into a polished, structured PDF.

Pipeline: select the relevant messages → LLM polishes them into an ItineraryDocument
(structured output, i.e. a tool call fixed in advance) → deterministic PDF rendering.
"""

import asyncio
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

import pymupdf
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage

from itinerary_planner.graph import REQUEST_DETAILS_NODE
from itinerary_planner.schemas import ItineraryDay, ItineraryDocument

POLISH_PROMPT = """You turn a travel-planning conversation into the final itinerary document.

- Reflect the user's latest requests: later changes override earlier versions of the plan.
- Use only places and facts that appear in the conversation. Do not invent anything.
- Polish the wording: clear, friendly and concise. Keep the stops in a sensible order."""

PAGE_RECT = pymupdf.paper_rect("a4")
CONTENT_RECT = PAGE_RECT + (54, 54, -54, -54)  # 0.75in margins

PDF_CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1c2330; }
h1 { font-size: 20pt; color: #1f4fbf; margin-bottom: 4pt; }
h2 { font-size: 13.5pt; color: #1f4fbf; margin-top: 16pt; border-bottom: 1px solid #c9d3e6; }
h3 { font-size: 11pt; margin: 8pt 0 2pt 0; }
p.summary { font-size: 11pt; color: #3b4658; }
p.stop { margin: 3pt 0; }
span.time { color: #677386; font-weight: bold; }
li { margin-bottom: 2pt; }
"""


@dataclass(frozen=True)
class PdfFile:
    filename: str
    content: bytes


def is_itinerary_reply(message: AnyMessage) -> bool:
    """A final planner answer: AI text that isn't a tool call or the missing-details prompt."""
    return (
        isinstance(message, AIMessage)
        and not message.tool_calls
        and message.name != REQUEST_DETAILS_NODE
        and bool(message.text.strip())
    )


def select_itinerary_messages(messages: Sequence[AnyMessage]) -> list[AnyMessage]:
    """Keep only the turns that produced an itinerary reply: the user's request and the reply.

    Drops intake turns (missing-details exchanges), tool calls and raw tool output.
    """
    turns: list[list[AnyMessage]] = []
    for message in messages:
        if isinstance(message, HumanMessage) or not turns:
            turns.append([])
        turns[-1].append(message)

    selected: list[AnyMessage] = []
    for turn in turns:
        replies = [m for m in turn if is_itinerary_reply(m)]
        if not replies:
            continue
        selected.extend(m for m in turn[:1] if isinstance(m, HumanMessage))
        selected.append(replies[-1])
    return selected


class ItineraryPolisher:
    def __init__(self, llm: BaseChatModel) -> None:
        self._structured_llm = llm.with_structured_output(ItineraryDocument)

    async def polish(self, messages: Sequence[AnyMessage]) -> ItineraryDocument:
        return await self._structured_llm.ainvoke([SystemMessage(POLISH_PROMPT), *messages])


def pdf_filename(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80].strip("-")
    return f"{slug or 'itinerary'}.pdf"


def _bullet_list(items: Sequence[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def _day_html(day: ItineraryDay) -> str:
    parts = [f"<h2>Day {day.day_number}: {escape(day.theme)}</h2>"]
    for stop in day.stops:
        time = f'<span class="time">{escape(stop.time_of_day)} · </span>' if stop.time_of_day else ""
        parts.append(
            f'<p class="stop">{time}<b>{escape(stop.name)}</b> — {escape(stop.description)}</p>'
        )
    if day.tips:
        parts.append("<h3>Tips</h3>" + _bullet_list(day.tips))
    return "".join(parts)


def itinerary_html(document: ItineraryDocument) -> str:
    """Escaped HTML for the document; every field is user/LLM text, never markup."""
    parts = [
        f"<h1>{escape(document.title)}</h1>",
        f'<p class="summary">{escape(document.summary)}</p>',
        f"<h2>Getting there</h2><p>{escape(document.getting_there)}</p>",
        *(_day_html(day) for day in document.days),
    ]
    if document.practical_tips:
        parts.append("<h2>Practical tips</h2>" + _bullet_list(document.practical_tips))
    return f"<body>{''.join(parts)}</body>"


def render_itinerary_pdf(document: ItineraryDocument) -> bytes:
    """Lay the document out on A4 pages (CPU-bound; call via asyncio.to_thread)."""
    story = pymupdf.Story(html=itinerary_html(document), user_css=PDF_CSS)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    has_more = True
    while has_more:
        device = writer.begin_page(PAGE_RECT)
        has_more, _ = story.place(CONTENT_RECT)
        story.draw(device)
        writer.end_page()
    writer.close()
    return buffer.getvalue()


async def build_itinerary_pdf(polisher: ItineraryPolisher, document_messages: Sequence[AnyMessage]) -> PdfFile:
    document = await polisher.polish(document_messages)
    content = await asyncio.to_thread(render_itinerary_pdf, document)
    return PdfFile(filename=pdf_filename(document.title), content=content)
