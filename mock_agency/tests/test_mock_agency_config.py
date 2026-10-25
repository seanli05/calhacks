import pytest
from agency.config import IVR_VOICE_ID, OFFICER_VOICE_ID, MockAgencySettings

REQUIRED = {
    "ANTHROPIC_API_KEY": "test-key",
    "MOCK_AGENCY_OFFICER_MODEL": "anthropic/claude-haiku-5-5",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ("MOCK_AGENCY_IVR_VOICE_ID", "MOCK_AGENCY_OFFICER_VOICE_ID"):
        monkeypatch.delenv(name, raising=False)
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def test_the_menu_and_the_officer_get_different_voices_by_default(
    env: pytest.MonkeyPatch,
) -> None:
    settings = MockAgencySettings.from_env()
    assert settings.ivr_voice_id == IVR_VOICE_ID
    assert settings.officer_voice_id == OFFICER_VOICE_ID
    assert IVR_VOICE_ID != OFFICER_VOICE_ID


def test_env_vars_choose_other_voices(env: pytest.MonkeyPatch) -> None:
    env.setenv("MOCK_AGENCY_IVR_VOICE_ID", "voice-menu")
    env.setenv("MOCK_AGENCY_OFFICER_VOICE_ID", "voice-officer")
    settings = MockAgencySettings.from_env()
    assert (settings.ivr_voice_id, settings.officer_voice_id) == (
        "voice-menu",
        "voice-officer",
    )
