"""FastAPI app: a streaming chat endpoint over the itinerary-planner graph."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from itinerary_planner.config import Settings, load_settings
from itinerary_planner.graph import build_graph
from itinerary_planner.itinerary_pdf import (
    ItineraryPolisher,
    build_itinerary_pdf,
    select_itinerary_messages,
)
from itinerary_planner.streaming import describe_error, stream_reply

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000
NO_ITINERARY_DETAIL = "There's no itinerary in this conversation yet — plan a trip first."


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class PdfRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)


def create_app(
    settings: Settings | None = None,
    graph: CompiledStateGraph | None = None,
    polisher: ItineraryPolisher | None = None,
) -> FastAPI:
    """Build the app. Tests pass stubs for `graph`/`polisher`; normally they're built from settings."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.graph = graph or build_graph(settings, InMemorySaver())
        app.state.polisher = polisher or ItineraryPolisher(ChatOpenAI(model=settings.model_name))
        yield

    app = FastAPI(title="Itinerary planner", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/chat")
    async def chat(chat_request: ChatRequest, request: Request) -> StreamingResponse:
        events = stream_reply(request.app.state.graph, chat_request.thread_id, chat_request.message)

        async def sse_frames() -> AsyncIterator[str]:
            async for event in events:
                yield event.to_sse()

        return StreamingResponse(
            sse_frames(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/itinerary-pdf")
    async def itinerary_pdf(pdf_request: PdfRequest, request: Request) -> Response:
        config = {"configurable": {"thread_id": pdf_request.thread_id}}
        snapshot = await request.app.state.graph.aget_state(config)
        relevant_messages = select_itinerary_messages(snapshot.values.get("messages", []))
        if not relevant_messages:
            raise HTTPException(status_code=409, detail=NO_ITINERARY_DETAIL)

        try:
            pdf = await build_itinerary_pdf(request.app.state.polisher, relevant_messages)
        except Exception as error:
            logger.exception("PDF export failed for thread %s", pdf_request.thread_id)
            raise HTTPException(status_code=502, detail=describe_error(error)) from error

        return Response(
            content=pdf.content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{pdf.filename}"'},
        )

    return app
