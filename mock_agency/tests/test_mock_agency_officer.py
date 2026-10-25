import pytest
from agency import prompts
from agency.case_record import DEMO_CASE, SF_DEMO_CASE, MockCase


def officer_prompt() -> str:
    return prompts.officer_system_prompt(
        case=DEMO_CASE,
        officer="Daniel Reyes",
        reference_number="SR123456",
        ivr_summary=prompts.QUICK_IVR_SUMMARY,
    ).lower()


def test_officer_never_asks_the_caller_to_verify_identity():
    prompt = officer_prompt()
    assert "never ask for a name, date of birth" in prompt
    assert "identity verification" not in prompt
    assert "only share after verification" not in prompt


def test_officer_stays_english_only():
    assert "you speak only english" in officer_prompt()


@pytest.mark.parametrize(
    ("case", "office", "other_office"),
    [
        (DEMO_CASE, "Los Angeles Asylum Office", "San Francisco"),
        (SF_DEMO_CASE, "San Francisco Asylum Office", "Los Angeles"),
    ],
)
def test_officer_intro_names_the_selected_office(
    case: MockCase, office: str, other_office: str
) -> None:
    intro = prompts.officer_intro(case, "Daniel Reyes")
    assert office in intro
    assert other_office not in intro
    assert "Officer Daniel Reyes" in intro


def test_officer_resolves_and_ends_the_call():
    prompt = officer_prompt()
    assert "sr123456" in prompt
    assert "end_call" in prompt
