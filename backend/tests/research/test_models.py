from datetime import date

import pytest
from app.research.fake import fake_case_brief, fake_fast_pass_output, fake_r2
from app.research.models import (
    R1,
    R2,
    REQUIRED_MUST_NOT_DO,
    CaseBrief,
    DeepFindings,
    FastPassOutput,
    KeyFact,
    LegitimacySignals,
    LetterPhone,
    ProposedFact,
    ResearchDeepPayload,
    ResearchFastPayload,
    SensitiveValue,
    SignalResult,
    Verification,
)
from pydantic import BaseModel, ValidationError


def round_trip(model: BaseModel) -> None:
    cls = type(model)
    assert cls.model_validate_json(model.model_dump_json()) == model
    assert cls.model_validate(model.model_dump(mode="json")) == model


@pytest.mark.parametrize(
    "model",
    [
        fake_fast_pass_output(),
        fake_fast_pass_output().r1,
        fake_fast_pass_output().signals,
        fake_r2(),
        fake_case_brief(),
        DeepFindings(
            verification=fake_r2().verification,
            trust_chain=["https://www.example.gov/"],
        ),
        ResearchFastPayload(
            case_id="case_1",
            user_id="user_1",
            document_ids=["doc_1"],
            user_language="es",
        ),
        ResearchDeepPayload(
            case_id="case_1",
            user_id="user_1",
            document_ids=["doc_1"],
            answers={"county": "X"},
        ),
    ],
    ids=lambda m: type(m).__name__,
)
def test_round_trip(model: BaseModel) -> None:
    round_trip(model)


def test_dates_serialize_as_iso() -> None:
    dumped = fake_fast_pass_output().r1.model_dump(mode="json")
    assert dumped["deadline"] == "2030-01-15"
    assert dumped["key_dates"][0]["iso"] == "2029-12-01"


def test_r1_needs_better_image_requires_issue() -> None:
    R1(
        case_id="case_1",
        status="needs_better_image",
        image_issue="Too blurry; hold the phone steady",
    )
    with pytest.raises(ValidationError):
        R1(case_id="case_1", status="needs_better_image")


def test_r1_needs_user_input_requires_question() -> None:
    R1(
        case_id="case_1",
        status="needs_user_input",
        question_en="Which county do you live in?",
    )
    with pytest.raises(ValidationError):
        R1(case_id="case_1", status="needs_user_input")


def test_r1_ok_requires_content() -> None:
    with pytest.raises(ValidationError):
        R1(case_id="case_1", status="ok")


def test_r1_rejects_unprefixed_case_id() -> None:
    with pytest.raises(ValidationError):
        R1(case_id="123", status="needs_better_image", image_issue="x")


def test_r1_rejects_unknown_fields() -> None:
    data = fake_fast_pass_output().r1.model_dump(mode="json") | {"surprise": 1}
    with pytest.raises(ValidationError):
        R1.model_validate(data)


def test_key_fact_needs_exactly_one_of_value_or_ref() -> None:
    with pytest.raises(ValidationError):
        KeyFact(field="x", page=1)
    with pytest.raises(ValidationError):
        KeyFact(field="x", value="a", ref="<ref:x>", page=1)


def test_ref_key_fact_cannot_quote_the_letter() -> None:
    with pytest.raises(ValidationError):
        KeyFact(
            field="case_number",
            ref="<ref:case_number>",
            quote="Case EXA0000000000",
            page=1,
        )


def test_key_fact_ref_format() -> None:
    with pytest.raises(ValidationError):
        KeyFact(field="x", ref="ref:x", page=1)


def test_proposed_fact_source_and_sensitivity() -> None:
    assert ProposedFact(fact="f", source="from_document").sensitivity == "normal"
    with pytest.raises(ValidationError):
        ProposedFact(fact="f", source="document")
    with pytest.raises(ValidationError):
        ProposedFact(fact="f", source="from_document", sensitivity="secret")


@pytest.mark.parametrize(
    "number", ["5105550123", "+1 510 555 0123", "(510) 555-0123", "+0123"]
)
def test_phones_must_be_e164(number: str) -> None:
    with pytest.raises(ValidationError):
        LetterPhone(number=number, quote=number)
    with pytest.raises(ValidationError):
        Verification(status="verified", official_phone=number)


def test_signal_state_values() -> None:
    for state in ("match", "not_found", "conflict", "uncertain"):
        SignalResult(signal="urls", state=state)
    with pytest.raises(ValidationError):
        SignalResult(signal="urls", state="mismatch")


def test_verification_status_values() -> None:
    for status in ("pending", "verified", "suspicious", "unknown"):
        Verification(status=status)
    with pytest.raises(ValidationError):
        Verification(status="legit")


def test_r2_call_requires_verified_official_phone() -> None:
    with pytest.raises(ValidationError):
        R2(
            case_id="case_1",
            verification=Verification(status="unknown"),
            call_recommended=True,
        )
    with pytest.raises(ValidationError):
        R2(
            case_id="case_1",
            verification=Verification(status="verified"),
            call_recommended=True,
        )
    R2(
        case_id="case_1",
        verification=Verification(status="unknown"),
        call_recommended=False,
    )


def test_case_brief_defaults_include_required_must_not_do() -> None:
    brief = CaseBrief(
        brief_id="brief_1",
        case_id="case_1",
        doc_type="t",
        issuer="i",
        call_goal_en="g",
        handoff_note="n",
    )
    assert set(REQUIRED_MUST_NOT_DO) <= set(brief.must_not_do)


def test_case_brief_rejects_missing_must_not_do() -> None:
    with pytest.raises(ValidationError):
        CaseBrief(
            brief_id="brief_1",
            case_id="case_1",
            doc_type="t",
            issuer="i",
            call_goal_en="g",
            handoff_note="n",
            must_not_do=["Be polite"],
        )


def test_sensitive_value_hidden_from_repr() -> None:
    value = SensitiveValue(
        field="case_number", ref="<ref:case_number>", value="EXA0000000000"
    )
    assert "EXA0000000000" not in repr(value)


def test_fake_outputs_keep_sensitive_values_out_of_r1() -> None:
    out = fake_fast_pass_output()
    r1_json = out.r1.model_dump_json()
    signals_json = out.signals.model_dump_json()
    for sv in out.sensitive_values:
        assert sv.value not in r1_json
        assert sv.value not in signals_json
        assert sv.ref in r1_json


def test_fakes_are_consistent() -> None:
    out, r2, brief = (
        fake_fast_pass_output("case_x"),
        fake_r2("case_x", "brief_x"),
        fake_case_brief("case_x", "brief_x"),
    )
    assert out.r1.case_id == r2.case_id == brief.case_id == "case_x"
    assert r2.brief_id == brief.brief_id == "brief_x"
    assert out.r1.deadline == brief.deadline == date(2030, 1, 15)
    assert isinstance(out, FastPassOutput)
    assert isinstance(out.signals, LegitimacySignals)


def test_payloads_validate() -> None:
    with pytest.raises(ValidationError):
        ResearchFastPayload(
            case_id="case_1", user_id="user_1", document_ids=[], user_language="es"
        )
    with pytest.raises(ValidationError):
        ResearchFastPayload(
            case_id="case_1",
            user_id="user_1",
            document_ids=["doc_1"],
            user_language="spa",
        )
