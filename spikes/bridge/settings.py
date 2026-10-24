"""Spike config: the shared settings object plus the spike-only vars.

Run with `PYTHONPATH=backend` so `app.settings` imports.
"""

import sys
from urllib.parse import urlsplit

from app.settings import Settings

# Shared settings fields this spike can't run without.
REQUIRED = (
    "twilio_account_sid",
    "twilio_auth_token",
    "twilio_agent_number",
    "twilio_mock_agency_number",
    "cartesia_api_key",
    "public_base_url",
    "bridge_spike_user_number",
    "bridge_spike_voice_id",
)


class BridgeSpikeSettings(Settings):
    # Your own phone, rung as the "user". Only in your .env, never in code or .env.example.
    bridge_spike_user_number: str = ""
    # Cartesia voice for the intro and the "will call back" line.
    bridge_spike_voice_id: str = ""


def load_settings() -> BridgeSpikeSettings:
    """Load settings, or exit naming (never printing) the env vars that are unset."""
    settings = BridgeSpikeSettings()
    missing = [name for name in REQUIRED if not getattr(settings, name)]
    if missing:
        sys.exit(f"missing env vars: {', '.join(name.upper() for name in missing)}")
    return settings


def ws_url(settings: Settings, path: str) -> str:
    """The wss:// URL for one of our websockets, from PUBLIC_BASE_URL's host."""
    return f"wss://{urlsplit(settings.public_base_url).netloc}{path}"


def http_url(settings: Settings, path: str) -> str:
    """The https:// URL Twilio calls back on, from PUBLIC_BASE_URL."""
    return settings.public_base_url.rstrip("/") + path
