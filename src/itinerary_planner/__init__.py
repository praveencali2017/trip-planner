import uvicorn

from itinerary_planner.config import load_server_settings


def main() -> None:
    """Run the API server. HOST, PORT and RELOAD=1 can be set in the environment or .env."""
    server = load_server_settings()
    uvicorn.run(
        "itinerary_planner.api:create_app",
        factory=True,
        host=server.host,
        port=server.port,
        reload=server.reload,
    )
