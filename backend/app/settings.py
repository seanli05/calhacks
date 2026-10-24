"""The single settings object. All config comes from env vars, or the repo-root
.env and .env.local (written by `neon env pull`; it wins over .env)."""

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# libpq-style params asyncpg rejects; sslmode is translated to ssl.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding"}

_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def to_asyncpg_url(url: str) -> str:
    """Rewrite a plain Postgres URL (as Neon prints it) for SQLAlchemy + asyncpg."""
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"
    params = dict(parse_qsl(parts.query))
    sslmode = params.get("sslmode")
    query = {k: v for k, v in params.items() if k not in _LIBPQ_ONLY_PARAMS}
    if sslmode and sslmode != "disable" and "ssl" not in query:
        query["ssl"] = "require"
    return urlunsplit(parts._replace(scheme=scheme, query=urlencode(query)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = ""
    model_fast: str = "claude-haiku-5-5"
    model_default: str = "claude-sonnet-5-5"
    model_deep: str = "claude-opus-5-5"

    # Cartesia
    cartesia_api_key: str = ""
    # The phone agent's voice on calls (Sonic) and its speech-to-text (Ink)
    cartesia_agent_voice_id: str = ""
    cartesia_stt_model: str = "ink-whisper"
    cartesia_tts_model: str = "sonic-3.6"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    twilio_agent_number: str = ""
    twilio_mock_agency_number: str = ""
    # The code on Twilio's WhatsApp sandbox page, without "join"; shown on the landing page.
    twilio_sandbox_join_code: str = ""

    # Database. Neon provides both; the unpooled one is preferred because
    # asyncpg's prepared statements don't survive Neon's transaction pooler.
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/calhacks"
    database_url_unpooled: str = ""
    # A separate Neon branch for DB tests; they drop every table. Never the shared one.
    test_database_url: str = ""

    # Public URL from ngrok, used for Twilio webhooks
    public_base_url: str = ""

    # Dev-only endpoints under /dev (e.g. the fake phone call); never on for the demo
    dev_endpoints: bool = False

    # Demo only (Plan.md C40): when set, the phone agent dials this instead of the
    # verified official number, so rehearsals never call a real agency.
    demo_dial_number: str = ""

    # Run the research agent's job worker in this process (needs ANTHROPIC_API_KEY).
    research_worker: bool = True
    # Run the memory writer's job worker in this process (needs ANTHROPIC_API_KEY).
    memory_worker: bool = True

    @field_validator("demo_dial_number")
    @classmethod
    def _e164(cls, value: str) -> str:
        if value and not _E164.match(value):
            raise ValueError("DEMO_DIAL_NUMBER must be E.164, e.g. +15551234567")
        return value

    @property
    def async_database_url(self) -> str:
        return to_asyncpg_url(self.database_url_unpooled or self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
