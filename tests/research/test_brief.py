from datetime import date

from research.brief import USER_ANSWERS, build_brief
from research.fake import fake_deep_findings, fake_fast_pass_output
from research.models import (
    REQUIRED_MUST_NOT_DO,
    Appointment,
    ChecklistItem,
    KeyFact,
)
from research.sim.store import CaseRecord


def case(**r1_updates: object) -> CaseRecord:
    out = fake_fast_pass_output("case_1")
    return CaseRecord(
        case_id="case_1",
        user_id="user_1",
        document_ids=["doc_1"],
        r1=out.r1.model_copy(update=r1_updates),
        signals=out.signals,
        call_purpose=out.call_purpose,
    )


def test_brief_has_required_rules_and_user_answers_identity() -> None:
    brief = build_brief(case(), fake_deep_findings())

    assert brief.case_id == "case_1" and brief.brief_id.startswith("brief_")
    assert all(rule in brief.must_not_do for rule in REQUIRED_MUST_NOT_DO)
    assert brief.call_goal_en == "Confirm the form was received"
    assert brief.likely_rep_questions
    assert all(q.answer_source == USER_ANSWERS for q in brief.likely_rep_questions)
    assert any("ask_user" in c for c in brief.contingencies)
    assert brief.open_uncertainties == [
        "Signal 'phones' was not found during verification"
    ]
    secret = fake_fast_pass_output().sensitive_values[0].value
    assert secret not in brief.model_dump_json()


def test_questions_from_appointment_and_interpreter_rule() -> None:
    appointment = Appointment(
        date=date(2030, 2, 1),
        time="08:30",
        location_ref="<ref:interview_location>",
        citation="p1",
    )
    checklist = [
        ChecklistItem(
            kind="who_must_come",
            item="An interpreter if you are not fluent",
            citation="p1",
        )
    ]
    brief = build_brief(
        case(appointment=appointment, checklist_en=checklist), fake_deep_findings()
    )

    assert "Is the appointment on 2030-02-01 still scheduled?" in brief.questions_to_ask
    assert "What should we do if the interpreter can't come?" in brief.questions_to_ask
    assert brief.appointment == appointment


def test_facts_keep_refs_and_drop_unsafe_values() -> None:
    facts = [
        KeyFact(field="receipt_number", ref="<ref:receipt_number>", page=1),
        KeyFact(field="a_number", value="A123456789", page=1),
        KeyFact(field="country_of_nationality", value="X", page=1),
        KeyFact(field="form_id", value="I-797C", page=1),
    ]
    brief = build_brief(case(key_facts=facts), fake_deep_findings())

    assert [f.field for f in brief.facts] == ["receipt_number", "form_id"]
    assert "What is the receipt number?" in [
        q.question for q in brief.likely_rep_questions
    ]
