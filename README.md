# Itinerary planner

A ReAct-style LangGraph agent that plans trips, with a FastAPI streaming backend and a React chat UI.

- Share a **YouTube travel video** → it mines the transcript for the route taken.
- Otherwise it **researches the destination** with OpenAI web search.
- It asks for your current location / destination if they're missing, and remembers the conversation per thread.

## Setup

```bash
cp .env.example .env          # add OPENAI_API_KEY (optional: MODEL_NAME, FRONTEND_ORIGIN)
uv sync
cd frontend && npm install
```

## Run

```bash
uv run itinerary-planner      # API on http://127.0.0.1:8001 (PORT=..., RELOAD=1 for auto-reload)
cd frontend && npm run dev    # UI on http://localhost:5173 (proxies /api to :8001)
```

## API

`POST /api/chat` with `{"thread_id": "...", "message": "..."}` returns `text/event-stream`:

| event    | data                  | meaning                                   |
|----------|-----------------------|-------------------------------------------|
| `token`  | `{"text": "..."}`     | next piece of the assistant's reply        |
| `status` | `{"message": "..."}`  | progress, e.g. "Researching Kyoto on the web…" |
| `error`  | `{"message": "..."}`  | the run failed (user-safe message)         |
| `done`   | `{}`                  | always sent last                           |

Conversation state lives in memory (`InMemorySaver`), so threads are lost when the server restarts.

## Layout

```
src/itinerary_planner/
  config.py     settings from env / .env
  schemas.py    graph state + structured-output models
  youtube.py    URL parsing, transcript fetching
  tools.py      the two agent tools + tool-error handling
  graph.py      nodes, routing, build_graph()
  streaming.py  graph run -> chat events (SSE)
  api.py        FastAPI app
frontend/src/
  api/streamChat.ts   fetch + SSE parser
  hooks/useChat.ts    conversation state, streaming, stop, new trip
  components/         MessageList, MessageBubble, StatusIndicator, Composer, EmptyState
notebooks/testing.ipynb  scratchpad for experimenting with the graph
tests/                   offline tests (uv run pytest)
```
