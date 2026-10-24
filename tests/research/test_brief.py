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
        case(
            doc_type="uscis_i797c_asylum_interview",
            appointment=appointment,
            checklist_en=checklist,
        ),
        fake_deep_findings(),
    )

    assert brief.questions_to_ask[:2] == [
        "Is the interview still on?",
        "What should we do if the interpreter can't come?",
    ]
    assert brief.appointment == appointment


def test_questions_capped_and_deadlines_go_in_handoff_note() -> None:
    checklist = [
        ChecklistItem(kind="who_must_come", item="An interpreter", citation="p1"),
        ChecklistItem(kind="bring", item="Passport", citation="p1"),
        ChecklistItem(
            kind="deadline", item="Send address changes within 10 days.", citation="p2"
        ),
    ]
    appointment = Appointment(date=date(2030, 2, 1), citation="p1")
    brief = build_brief(
        case(appointment=appointment, checklist_en=checklist), fake_deep_findings()
    )

    assert len(brief.questions_to_ask) <= 4
    assert not any("deadline" in q.lower() for q in brief.questions_to_ask)
    assert "Send address changes within 10 days." in brief.handoff_note
    text = " ".join([brief.handoff_note, *brief.questions_to_ask])
    assert ".." not in text and ".?" not in text


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


def test_rep_questions_use_human_labels() -> None:
    facts = [
        KeyFact(field="a_number", ref="<ref:a_number>", page=1),
        KeyFact(field="interview_location", ref="<ref:interview_location>", page=1),
    ]
    brief = build_brief(case(key_facts=facts), fake_deep_findings())

    asked = [q.question for q in brief.likely_rep_questions]
    assert "What is the A-Number?" in asked
    assert "What is the interview location?" in asked


def test_interview_question_without_readable_date_and_appointment_wording() -> None:
    interview = case(doc_type="uscis_i797c_asylum_interview", appointment=None)
    brief = build_brief(interview, fake_deep_findings())
    assert brief.questions_to_ask[0] == "Is the interview still on?"

    appointment = Appointment(date=date(2030, 2, 1), citation="p1")
    other = case(doc_type="housing_inspection_notice", appointment=appointment)
    brief = build_brief(other, fake_deep_findings())
    assert brief.questions_to_ask[0] == "Is the appointment still on?"


def test_punctuation_only_call_purpose_is_skipped() -> None:
    record = case().model_copy(update={"call_purpose": " . "})
    brief = build_brief(record, fake_deep_findings())
    assert not any(q.startswith("Can you help us") for q in brief.questions_to_ask)
