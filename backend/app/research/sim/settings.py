# SIM: replace with the team settings object when person 1 lands it
"""Research settings from environment variables. No defaults for models or keys."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ResearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    model_default: str
    model_deep: str
    anthropic_api_key: SecretStr
