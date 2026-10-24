"""Canned research outputs for fake mode. Generic, not tied to any real letter."""

from datetime import date

from research.models import (
    R1,
    R2,
    AlternativeContact,
    CaseBrief,
    ChecklistItem,
    FastPassOutput,
    KeyDate,
    KeyFact,
    LegitimacySignals,
    ProposedFact,
    RepQuestion,
    SensitiveValue,
    SignalResult,
    Verification,
)

FAKE_OFFICIAL_PHONE = "+15555550100"
FAKE_URL = "https://www.example.gov/contact"


def fake_fast_pass_output(case_id: str = "case_fake") -> FastPassOutput:
    r1 = R1(
        case_id=case_id,
        status="ok",
        doc_type="generic_agency_notice",
        issuer="Example Agency",
        deadline=date(2030, 1, 15),
        key_dates=[
            KeyDate(type="notice_date", raw="December 1, 2029", iso=date(2029, 12, 1)),
            KeyDate(type="deadline", raw="January 15, 2030", iso=date(2030, 1, 15)),
        ],
        what_is_asked="Return the enclosed form by the deadline",
        checklist_en=[
            ChecklistItem(
                kind="bring", item="The enclosed form, signed", citation="p1"
            ),
            ChecklistItem(
                kind="deadline",
                item="Return the form by January 15, 2030",
                citation="p1",
            ),
        ],
        key_facts=[
            KeyFact(field="case_number", ref="<ref:case_number>", page=1),
            KeyFact(field="form_id", value="EX-100", quote="Form EX-100", page=1),
        ],
        explanation_en="This is a notice from Example Agency asking you to return a form by January 15, 2030.",
        urgency="medium",
        proposed_facts=[
            ProposedFact(
                fact="Has an open case with Example Agency", source="from_document"
            )
        ],
    )
    return FastPassOutput(
        r1=r1,
        signals=LegitimacySignals(
            letterhead="Example Agency",
            return_address="100 Main St, Springfield, ST 00000",
            urls=[FAKE_URL],
            form_ids=["EX-100"],
            case_number_format="3 letters + 10 digits",
        ),
        call_purpose="Confirm the form was received",
        unknown_terms=["notice of action"],
        sensitive_values=[
            SensitiveValue(
                field="case_number", ref="<ref:case_number>", value="EXA0000000000"
            )
        ],
    )


def fake_r2(case_id: str = "case_fake", brief_id: str = "brief_fake") -> R2:
    return R2(
        case_id=case_id,
        verification=Verification(
            status="verified",
            official_phone=FAKE_OFFICIAL_PHONE,
            letter_phone_matches=None,
            evidence=[FAKE_URL],
            signals=[
                SignalResult(signal="urls", state="match", evidence=[FAKE_URL]),
                SignalResult(signal="form_ids", state="match", evidence=[FAKE_URL]),
                SignalResult(signal="phones", state="not_found"),
            ],
        ),
        official_phone_purpose="General questions about existing cases",
        alternative_contacts=[
            AlternativeContact(name="Example Legal Aid", purpose="Free legal help")
        ],
        call_recommended=True,
        brief_id=brief_id,
        call_goal_en="Confirm the form was received",
    )


def fake_case_brief(
    case_id: str = "case_fake", brief_id: str = "brief_fake"
) -> CaseBrief:
    return CaseBrief(
        brief_id=brief_id,
        case_id=case_id,
        doc_type="generic_agency_notice",
        issuer="Example Agency",
        deadline=date(2030, 1, 15),
        call_goal_en="Confirm the form was received",
        expected_menu_path=["Existing case", "Speak to a representative"],
        questions_to_ask=[
            "Has the form been received?",
            "Is anything else needed before the deadline?",
        ],
        facts=[KeyFact(field="case_number", ref="<ref:case_number>", page=1)],
        handoff_note="Calling Example Agency to confirm a returned form was received. The user gives identifiers.",
        likely_rep_questions=[
            RepQuestion(
                question="What is the case number?", answer_source="user, once bridged"
            )
        ],
        contingencies=[
            "If the form was not received, ask how to resend it before the deadline"
        ],
    )
