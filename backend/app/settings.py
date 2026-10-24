"""The single settings object. All config comes from env vars, or the repo-root
.env and .env.local (written by `neon env pull`; it wins over .env)."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# libpq-style params asyncpg rejects; sslmode is translated to ssl.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding"}


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

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    twilio_agent_number: str = ""
    twilio_mock_agency_number: str = ""

    # Database. Neon provides both; the unpooled one is preferred because
    # asyncpg's prepared statements don't survive Neon's transaction pooler.
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/calhacks"
    database_url_unpooled: str = ""

    # Public URL from ngrok, used for Twilio webhooks
    public_base_url: str = ""

    @property
    def async_database_url(self) -> str:
        return to_asyncpg_url(self.database_url_unpooled or self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
