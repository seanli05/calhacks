from agency import prompts
from agency.case_record import DEMO_CASE


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


def test_officer_resolves_and_ends_the_call():
    prompt = officer_prompt()
    assert "sr123456" in prompt
    assert "end_call" in prompt
