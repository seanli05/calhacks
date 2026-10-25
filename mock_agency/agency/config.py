"""Settings for the mock agency line, read from environment variables.

The line deploys to Cartesia on its own, so it reads its own env instead of
the backend's settings object. Set these with `cartesia env set`.
"""

import os
from enum import StrEnum

from pydantic import BaseModel, model_validator

# Two clearly different voices, so the officer picking up sounds like a new person,
# as on a real line. Both English Cartesia voices; override with the env vars.
IVR_VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"
"""Skylar - Friendly Guide: the phone tree and hold announcements."""
OFFICER_VOICE_ID = "a5136bf9-224c-4d76-b823-52bd5efcffcc"
"""Jameson - Easygoing Support: Officer Daniel Reyes."""


class Mode(StrEnum):
    """Which call the line plays. One per deploy, set with MOCK_AGENCY_MODE."""

    DEMO = "demo"
    """The full phone tree, hold, then the officer: the demo path."""
    QUICK = "quick"
    """A short greeting, then the officer at once: for testing live calls."""


class MockAgencySettings(BaseModel):
    anthropic_api_key: str
    officer_model: str
    mode: Mode = Mode.DEMO
    officer_name: str = "Daniel Reyes"
    hold_seconds: float = 45.0
    hold_announce_every_s: float = 15.0
    no_input_seconds: float = 12.0
    ivr_voice_id: str = IVR_VOICE_ID
    officer_voice_id: str = OFFICER_VOICE_ID

    @model_validator(mode="after")
    def _voices_differ(self) -> "MockAgencySettings":
        """The officer picking up must sound like a new person, as on a real line."""
        if self.ivr_voice_id == self.officer_voice_id:
            raise ValueError("the phone tree and the officer need different voices")
        return self

    @classmethod
    def from_env(cls) -> "MockAgencySettings":
        env = {
            "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY"),
            "officer_model": os.environ.get("MOCK_AGENCY_OFFICER_MODEL"),
            "mode": os.environ.get("MOCK_AGENCY_MODE"),
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
