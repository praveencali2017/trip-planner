"""Runtime settings, read from the environment (and the project's .env file)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_MODEL_NAME = "gpt-5.4-mini"
DEFAULT_FRONTEND_ORIGIN = "http://localhost:5173"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001


class MissingSettingError(RuntimeError):
    """A required environment variable is not set."""


class InvalidSettingError(RuntimeError):
    """An environment variable is set to an unusable value."""


@dataclass(frozen=True)
class Settings:
    model_name: str
    frontend_origin: str


def load_settings() -> Settings:
    """Load settings, failing fast if the OpenAI key is missing.

    The key itself is left in the environment for the OpenAI client to read; it is never
    stored on Settings so it can't leak through logging or repr.
    """
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        raise MissingSettingError("OPENAI_API_KEY is not set — add it to the project's .env file.")
    return Settings(
        model_name=os.environ.get("MODEL_NAME", DEFAULT_MODEL_NAME),
        frontend_origin=os.environ.get("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN),
    )


@dataclass(frozen=True)
class ServerSettings:
    host: str
    port: int
    reload: bool


def load_server_settings() -> ServerSettings:
    """Load how the API server listens. Reads .env first, so PORT/HOST/RELOAD there apply."""
    load_dotenv()
    raw_port = os.environ.get("PORT", str(DEFAULT_PORT))
    try:
        port = int(raw_port)
    except ValueError:
        raise InvalidSettingError(f"PORT must be a number, got {raw_port!r}.") from None
    return ServerSettings(
        host=os.environ.get("HOST", DEFAULT_HOST),
        port=port,
        reload=os.environ.get("RELOAD") == "1",
    )
