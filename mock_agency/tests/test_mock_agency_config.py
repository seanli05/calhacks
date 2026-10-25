import pytest
from agency.case_record import DEMO_CASE, SF_DEMO_CASE
from agency.config import IVR_VOICE_ID, OFFICER_VOICE_ID, MockAgencySettings, Mode
from pydantic import ValidationError

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


def test_mode_defaults_to_the_demo_path(env: pytest.MonkeyPatch) -> None:
    env.delenv("MOCK_AGENCY_MODE", raising=False)
    assert MockAgencySettings.from_env().mode is Mode.DEMO


def test_env_var_picks_quick_mode(env: pytest.MonkeyPatch) -> None:
    env.setenv("MOCK_AGENCY_MODE", "quick")
    assert MockAgencySettings.from_env().mode is Mode.QUICK


def test_unknown_mode_fails_at_startup(env: pytest.MonkeyPatch) -> None:
    env.setenv("MOCK_AGENCY_MODE", "quik")
    with pytest.raises(ValidationError):
        MockAgencySettings.from_env()


def test_case_defaults_to_the_original_demo_case(env: pytest.MonkeyPatch) -> None:
    env.delenv("MOCK_AGENCY_CASE", raising=False)
    assert MockAgencySettings.from_env().case_record == DEMO_CASE


def test_env_var_picks_the_sf_demo_case(env: pytest.MonkeyPatch) -> None:
    env.setenv("MOCK_AGENCY_CASE", "sf_demo")
    case = MockAgencySettings.from_env().case_record
    assert case == SF_DEMO_CASE
    assert case.applicant_name == "Mariam Namuna"
    assert case.interview_office == "San Francisco Asylum Office"


def test_unknown_case_fails_at_startup(env: pytest.MonkeyPatch) -> None:
    env.setenv("MOCK_AGENCY_CASE", "sf")
    with pytest.raises(ValidationError, match="sf_demo"):
        MockAgencySettings.from_env()


def test_same_voice_for_menu_and_officer_fails_at_startup(
    env: pytest.MonkeyPatch,
) -> None:
    env.setenv("MOCK_AGENCY_IVR_VOICE_ID", OFFICER_VOICE_ID)
    with pytest.raises(ValidationError):
        MockAgencySettings.from_env()


def test_short_mode_holds_for_the_short_hold(env: pytest.MonkeyPatch) -> None:
    env.setenv("MOCK_AGENCY_MODE", "short")
    env.setenv("MOCK_AGENCY_HOLD_SECONDS", "45")
    env.delenv("MOCK_AGENCY_SHORT_HOLD_SECONDS", raising=False)
    settings = MockAgencySettings.from_env()
    assert settings.mode is Mode.SHORT
    assert settings.call_hold_seconds == 15.0


def test_demo_mode_keeps_the_full_hold(env: pytest.MonkeyPatch) -> None:
    env.setenv("MOCK_AGENCY_MODE", "demo")
    env.setenv("MOCK_AGENCY_HOLD_SECONDS", "45")
    assert MockAgencySettings.from_env().call_hold_seconds == 45.0
