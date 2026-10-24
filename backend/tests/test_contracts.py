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
    DeepResult,
    Event,
    EventType,
    FastResult,
    FastResultStatus,
    GlossaryLookupJob,
    JobPayload,
    JobType,
    MemoryWriteJob,
    ResearchDeepJob,
    ResearchFastJob,
)
from pydantic import BaseModel, TypeAdapter, ValidationError

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"

FIXTURE_MODELS: dict[str, type[BaseModel]] = {
    "research_fast_job": ResearchFastJob,
    "research_deep_job": ResearchDeepJob,
    "call_job": CallJob,
    "memory_write_job": MemoryWriteJob,
    "glossary_lookup_job": GlossaryLookupJob,
    "fast_result": FastResult,
    "deep_result": DeepResult,
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
    data["key_facts"][0]["ref"] = "IOE0912345678"
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
