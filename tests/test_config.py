import os
from pathlib import Path

import dotenv
import pytest

import itinerary_planner
import itinerary_planner.config
from itinerary_planner.config import (
    InvalidSettingError,
    MissingSettingError,
    load_server_settings,
    load_settings,
)


@pytest.fixture
def env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point config's load_dotenv at a temp .env (never the real one) and isolate os.environ.

    load_dotenv writes straight into os.environ, which monkeypatch can't undo, so the whole
    environment is snapshotted and restored around each test.
    """
    saved_environ = dict(os.environ)
    for name in ["OPENAI_API_KEY", "MODEL_NAME", "FRONTEND_ORIGIN", "HOST", "PORT", "RELOAD"]:
        os.environ.pop(name, None)
    path = tmp_path / ".env"
    path.write_text("")
    monkeypatch.setattr(itinerary_planner.config, "load_dotenv", lambda: dotenv.load_dotenv(path))
    yield path
    os.environ.clear()
    os.environ.update(saved_environ)


# --- server settings / main() -----------------------------------------------------------

def test_main_listens_on_host_and_port_from_dotenv(env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: main() read PORT before .env was loaded, so it always fell back to 8001."""
    env_file.write_text("PORT=9123\nHOST=0.0.0.0\nRELOAD=1\n")
    uvicorn_calls: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(itinerary_planner.uvicorn, "run", lambda *a, **kw: uvicorn_calls.append((a, kw)))

    itinerary_planner.main()

    assert uvicorn_calls == [
        (
            ("itinerary_planner.api:create_app",),
            {"factory": True, "host": "0.0.0.0", "port": 9123, "reload": True},
        )
    ]


def test_server_defaults_when_nothing_is_configured(env_file: Path) -> None:
    settings = load_server_settings()

    assert (settings.host, settings.port, settings.reload) == ("127.0.0.1", 8001, False)


def test_real_environment_variable_beats_dotenv(env_file: Path) -> None:
    env_file.write_text("PORT=9123\n")
    os.environ["PORT"] = "7000"

    assert load_server_settings().port == 7000


@pytest.mark.parametrize("raw_port", ["abc", "80.5", ""])
def test_non_numeric_port_fails_with_a_clear_message(env_file: Path, raw_port: str) -> None:
    env_file.write_text(f"PORT={raw_port}\n")

    with pytest.raises(InvalidSettingError, match=f"PORT must be a number, got '{raw_port}'"):
        load_server_settings()


@pytest.mark.parametrize(("raw_reload", "expected"), [("1", True), ("0", False), ("true", False), ("yes", False)])
def test_only_reload_1_enables_auto_reload(env_file: Path, raw_reload: str, expected: bool) -> None:
    # Documents current behaviour: "true"/"yes" are NOT accepted (see test report).
    env_file.write_text(f"RELOAD={raw_reload}\n")

    assert load_server_settings().reload is expected


# --- app settings ---------------------------------------------------------------------------

def test_missing_api_key_fails_fast(env_file: Path) -> None:
    with pytest.raises(MissingSettingError, match="OPENAI_API_KEY is not set"):
        load_settings()


def test_settings_from_dotenv_with_defaults(env_file: Path) -> None:
    env_file.write_text("OPENAI_API_KEY=sk-test-not-real\n")

    settings = load_settings()

    assert settings.model_name == "gpt-5.4-mini"
    assert settings.frontend_origin == "http://localhost:5173"


def test_settings_overrides_from_dotenv(env_file: Path) -> None:
    env_file.write_text(
        "OPENAI_API_KEY=sk-test-not-real\nMODEL_NAME=gpt-5.4\nFRONTEND_ORIGIN=http://localhost:3000\n"
    )

    settings = load_settings()

    assert (settings.model_name, settings.frontend_origin) == ("gpt-5.4", "http://localhost:3000")


def test_api_key_is_never_stored_on_settings(env_file: Path) -> None:
    env_file.write_text("OPENAI_API_KEY=sk-test-not-real\n")

    assert "sk-test-not-real" not in repr(load_settings())
