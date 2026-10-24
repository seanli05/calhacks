"""The single settings object. All config comes from env vars (or the repo-root .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
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

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/calhacks"

    # Public URL from ngrok, used for Twilio webhooks
    public_base_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
