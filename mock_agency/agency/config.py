"""Settings for the mock agency line, read from environment variables.

The line deploys to Cartesia on its own, so it reads its own env instead of
the backend's settings object. Set these with `cartesia env set`.
"""

import os

from pydantic import BaseModel


class MockAgencySettings(BaseModel):
    anthropic_api_key: str
    officer_model: str
    officer_name: str = "Daniel Reyes"
    hold_seconds: float = 45.0
    hold_announce_every_s: float = 15.0
    no_input_seconds: float = 12.0
    ivr_voice_id: str | None = None
    officer_voice_id: str | None = None

    @classmethod
    def from_env(cls) -> "MockAgencySettings":
        env = {
            "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY"),
            "officer_model": os.environ.get("MOCK_AGENCY_OFFICER_MODEL"),
            "officer_name": os.environ.get("MOCK_AGENCY_OFFICER_NAME"),
            "hold_seconds": os.environ.get("MOCK_AGENCY_HOLD_SECONDS"),
            "hold_announce_every_s": os.environ.get(
                "MOCK_AGENCY_HOLD_ANNOUNCE_EVERY_S"
            ),
            "no_input_seconds": os.environ.get("MOCK_AGENCY_NO_INPUT_SECONDS"),
            "ivr_voice_id": os.environ.get("MOCK_AGENCY_IVR_VOICE_ID"),
            "officer_voice_id": os.environ.get("MOCK_AGENCY_OFFICER_VOICE_ID"),
        }
        return cls(**{key: value for key, value in env.items() if value})
