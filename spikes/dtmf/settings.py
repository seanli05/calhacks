"""Spike config: the shared settings object plus the one spike-only var.

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
)


class SpikeSettings(Settings):
    # Cartesia voice for the spoken-"two" test. Pipecat's Cartesia TTS has no default voice.
    dtmf_spike_voice_id: str = ""


def load_settings(*, need_voice: bool = False) -> SpikeSettings:
    """Load settings, or exit naming (never printing) the env vars that are unset."""
    settings = SpikeSettings()
    missing = [name for name in REQUIRED if not getattr(settings, name)]
    if need_voice and not settings.dtmf_spike_voice_id:
        missing.append("dtmf_spike_voice_id")
    if missing:
        sys.exit(f"missing env vars: {', '.join(name.upper() for name in missing)}")
    return settings


def stream_url(settings: Settings) -> str:
    """The wss:// URL Twilio streams call audio to, from PUBLIC_BASE_URL's host."""
    host = urlsplit(settings.public_base_url).netloc
    return f"wss://{host}/ws"
