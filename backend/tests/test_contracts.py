"""Contract models against Plan.md's example payloads.

The fixtures are those examples copied verbatim, with two fixes:
- call_report.json: Plan.md writes `outcome` as "resolved | partial | failed |
  user_unreachable"; the fixture uses "resolved".
- event.json: adds `user_id` (data-layer-schema.md, resolution 3).

Other components can load these fixtures as fake inputs, so keep them valid.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from app.contracts import (
    USER_MESSAGING_EVENTS,
    AskUserReply,
    AskUserRequest,
    CallJob,
    CallReport,
    CaseBrief,
    DeepResult,
    Event,
    EventType,
    FastResult,
    FastResultStatus,
    GlossaryLookupJob,
    JobPayload,
    JobType,
    KeyFact,
    MemoryWriteJob,
    ResearchDeepJob,
    ResearchFastJob,
    ResearchQuestionJob,
)
from app.contracts.results import QuestionAnswer
from pydantic import BaseModel, TypeAdapter, ValidationError

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"

FIXTURE_MODELS: dict[str, type[BaseModel]] = {
    "research_fast_job": ResearchFastJob,
    "research_deep_job": ResearchDeepJob,
    "call_job": CallJob,
    "memory_write_job": MemoryWriteJob,
    "glossary_lookup_job": GlossaryLookupJob,
    "research_question_job": ResearchQuestionJob,
    "fast_result": FastResult,
    "deep_result": DeepResult,
    "question_answer": QuestionAnswer,
    "case_brief": CaseBrief,
    "call_report": CallReport,
    "ask_user_request": AskUserRequest,
    "ask_user_reply": AskUserReply,
    "event": Event,
}

JOB_FIXTURES = [name for name in FIXTURE_MODELS if name.endswith("_job")]

job_payload = TypeAdapter(JobPayload)


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_every_fixture_has_a_model() -> None:
    assert {p.stem for p in FIXTURES.glob("*.json")} == set(FIXTURE_MODELS)


@pytest.mark.parametrize("name", FIXTURE_MODELS)
def test_plan_example_validates(name: str) -> None:
    FIXTURE_MODELS[name].model_validate(load(name))


@pytest.mark.parametrize("name", FIXTURE_MODELS)
def test_round_trip(name: str) -> None:
    model_cls = FIXTURE_MODELS[name]
    original = model_cls.model_validate(load(name))
    assert model_cls.model_validate(original.model_dump(mode="json")) == original


@pytest.mark.parametrize("name", JOB_FIXTURES)
def test_job_payload_picks_model_from_job(name: str) -> None:
    payload = job_payload.validate_python(load(name))
    assert type(payload) is FIXTURE_MODELS[name]


def test_job_literals_match_job_type() -> None:
    literals = {
        FIXTURE_MODELS[name].model_fields["job"].default for name in JOB_FIXTURES
    }
    assert literals == set(JobType)


def test_job_payload_rejects_unknown_job() -> None:
    with pytest.raises(ValidationError):
        job_payload.validate_python({**load("research_deep_job"), "job": "translate"})


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ResearchFastJob.model_validate(
            {**load("research_fast_job"), "user_langauge": "es"}
        )


def test_nested_unknown_field_rejected() -> None:
    data = load("fast_result")
    data["appointment"]["room"] = "4B"
    with pytest.raises(ValidationError):
        FastResult.model_validate(data)


@pytest.mark.parametrize("language", ["spa", "ES", "e", "es-MX", ""])
def test_bad_language_code_rejected(language: str) -> None:
    with pytest.raises(ValidationError):
        CallJob.model_validate({**load("call_job"), "user_language": language})


def test_call_job_rejects_user_phone() -> None:
    """C6: the phone agent reads the user's number through a helper, never the payload."""
    with pytest.raises(ValidationError):
        CallJob.model_validate({**load("call_job"), "user_phone": "+15105550123"})


def test_call_job_rejects_call_id() -> None:
    """C7: the phone agent creates the call and its ID."""
    with pytest.raises(ValidationError):
        CallJob.model_validate({**load("call_job"), "call_id": "call_5"})


def test_call_job_only_dials_official_phone() -> None:
    with pytest.raises(ValidationError):
        CallJob.model_validate({**load("call_job"), "dial_number_source": "letter"})


@pytest.mark.parametrize("default_option", [0, 3, -1])
def test_default_option_out_of_range_rejected(default_option: int) -> None:
    data = {**load("ask_user_request"), "default_option": default_option}
    with pytest.raises(ValidationError):
        AskUserRequest.model_validate(data)


def test_default_option_last_is_allowed() -> None:
    data = {**load("ask_user_request"), "default_option": 2}
    assert AskUserRequest.model_validate(data).default_option == 2


def test_ask_user_reply_is_one_based() -> None:
    with pytest.raises(ValidationError):
        AskUserReply.model_validate({"question_id": "question_3", "choice": 0})


def test_needs_better_image_needs_only_the_tip() -> None:
    result = FastResult.model_validate(
        {
            "case_id": "case_123",
            "status": "needs_better_image",
            "image_issue": "Too blurry",
        }
    )
    assert result.status is FastResultStatus.NEEDS_BETTER_IMAGE
    assert result.appointment is None
    assert result.checklist_en == []


def test_fast_result_refs_must_be_placeholders() -> None:
    """C34: receipt number, A-Number, and location are always refs, never raw values."""
    data = load("fast_result")
    data["key_facts"][1]["ref"] = "IOE0912345678"
    with pytest.raises(ValidationError):
        FastResult.model_validate(data)


def test_official_phone_must_be_e164() -> None:
    data = load("deep_result")
    data["verification"]["official_phone"] = "1-800-375-5283"
    with pytest.raises(ValidationError):
        DeepResult.model_validate(data)


def test_event_requires_user_id() -> None:
    data = load("event")
    del data["user_id"]
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_user_messaging_events_are_the_four_from_p2() -> None:
    assert USER_MESSAGING_EVENTS == {
        EventType.CALL_DIALING,
        EventType.CALL_ON_HOLD,
        EventType.CALL_HUMAN_DETECTED,
        EventType.CALL_USER_UNREACHABLE,
    }


def test_key_fact_holds_exactly_one_of_value_or_ref() -> None:
    with pytest.raises(ValidationError):
        KeyFact.model_validate({"field": "form_id", "page": 1})
    with pytest.raises(ValidationError):
        KeyFact.model_validate(
            {"field": "a_number", "value": "A1", "ref": "<ref:a_number>", "page": 1}
        )


def test_refd_key_fact_never_quotes_the_letter() -> None:
    """C11: the quote would hold the sensitive value the ref stands in for."""
    with pytest.raises(ValidationError):
        KeyFact.model_validate(
            {"field": "a_number", "ref": "<ref:a_number>", "quote": "A#", "page": 1}
        )


def test_needs_user_input_requires_a_question() -> None:
    data = {"case_id": "case_123", "status": "needs_user_input"}
    with pytest.raises(ValidationError):
        FastResult.model_validate(data)
    result = FastResult.model_validate({**data, "question_en": "Which letter first?"})
    assert result.status is FastResultStatus.NEEDS_USER_INPUT


def test_appointment_may_have_only_a_date() -> None:
    data = load("fast_result")
    data["appointment"] = {"date": "2026-11-18", "citation": "p1"}
    assert FastResult.model_validate(data).appointment.time is None


def test_suspicious_letter_has_no_brief() -> None:
    data = load("deep_result")
    data["verification"]["status"] = "suspicious"
    data.update(call_recommended=False, brief_id=None)
    assert DeepResult.model_validate(data).brief_id is None


def test_call_recommended_needs_a_verified_number() -> None:
    """Rule 2: research never recommends a call it couldn't dial."""
    data = load("deep_result")
    data["verification"]["status"] = "unknown"
    data["call_recommended"] = True
    with pytest.raises(ValidationError):
        DeepResult.model_validate(data)


def test_brief_must_keep_the_required_must_not_do() -> None:
    """C34, C35: the agent never gives identifiers or discusses the claim."""
    data = load("case_brief")
    data["must_not_do"] = ["Be polite"]
    with pytest.raises(ValidationError):
        CaseBrief.model_validate(data)


def test_answered_question_needs_sources() -> None:
    data = load("question_answer")
    with pytest.raises(ValidationError):
        QuestionAnswer.model_validate({**data, "sources": []})


def test_declined_question_carries_no_answer() -> None:
    with pytest.raises(ValidationError):
        QuestionAnswer.model_validate(
            {"status": "declined_legal_advice", "answer_en": "You should appeal."}
        )


def test_fast_result_from_before_c41_still_validates() -> None:
    stored = {k: v for k, v in load("fast_result").items() if k != "summary_en"}
    assert FastResult.model_validate(stored).summary_en is None
    assert FastResult.model_validate(load("fast_result")).summary_en


def test_deep_job_from_before_c41_still_validates() -> None:
    stored = load("research_deep_job")
    stored.pop("call_goal_short_en", None)
    assert ResearchDeepJob.model_validate(stored).call_goal_short_en is None
