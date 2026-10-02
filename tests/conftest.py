"""Shared test doubles. The only thing faked is the OpenAI boundary; the graph, ToolNode,
checkpointer and streaming code under test are all real."""

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

import itinerary_planner.graph
import itinerary_planner.tools

ScriptedResponse = AIMessage | Exception
StructuredResponder = Callable[[list[BaseMessage]], BaseModel]


class ScriptedChatModel(BaseChatModel):
    """Chat model that replays scripted replies, streaming them token by token like a real one.

    - `responses` are consumed in order by plain/tool-bound calls; an Exception is raised instead.
    - `structured` maps a schema to a function building the structured result from the prompt.
    - Every prompt it receives is recorded in `calls` / `structured_calls` for assertions.
    """

    responses: list[ScriptedResponse] = []
    structured: dict[type, StructuredResponder] = {}
    calls: list[list[BaseMessage]] = []
    structured_calls: list[tuple[type, list[BaseMessage]]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _next_response(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(list(messages))
        if not self.responses:
            raise AssertionError("ScriptedChatModel ran out of scripted responses")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next_response(messages))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop=None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        response = self._next_response(messages)
        if response.tool_calls:
            tool_call_chunks = [
                {"name": call["name"], "args": json.dumps(call["args"]), "id": call["id"], "index": index}
                for index, call in enumerate(response.tool_calls)
            ]
            chunks = [AIMessageChunk(content="", tool_call_chunks=tool_call_chunks)]
        else:
            chunks = [AIMessageChunk(content=token) for token in re.findall(r"\S+\s*", response.text)]
        for chunk in chunks:
            generation = ChatGenerationChunk(message=chunk)
            if run_manager:
                run_manager.on_llm_new_token(chunk.text, chunk=generation)
            yield generation

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> RunnableLambda:
        def respond(messages: list[BaseMessage]) -> BaseModel:
            self.structured_calls.append((schema, list(messages)))
            return self.structured[schema](messages)

        return RunnableLambda(respond)


@pytest.fixture
def chat_model(monkeypatch: pytest.MonkeyPatch) -> ScriptedChatModel:
    """The model behind extraction, the planner and the video tool (graph.py's ChatOpenAI)."""
    model = ScriptedChatModel(responses=[], structured={}, calls=[], structured_calls=[])
    monkeypatch.setattr(itinerary_planner.graph, "ChatOpenAI", lambda **_: model)
    return model


@pytest.fixture
def web_researcher(monkeypatch: pytest.MonkeyPatch) -> ScriptedChatModel:
    """The web-search model created inside tools.py."""
    model = ScriptedChatModel(responses=[], structured={}, calls=[], structured_calls=[])
    monkeypatch.setattr(itinerary_planner.tools, "ChatOpenAI", lambda **_: model)
    return model
