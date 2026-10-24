"""Deterministic CaseBrief builder: R1 + deep findings -> what the phone agent reads.

No model call. Explains, never advises (C33); carries no asylum-claim details
(C34); identifiers stay refs and are only ever given by the user (rule 3, C35).
"""

import uuid

from app.contracts import (
    REQUIRED_MUST_NOT_DO,
    CaseBrief,
    KeyFact,
    RepQuestion,
)
from app.research.models import (
    CaseRecord,
    DeepFindings,
)

USER_ANSWERS = "the user, in their own voice, once bridged"

EXTRA_MUST_NOT_DO = (
    "Never answer identity or verification questions for the user",
    "Never enter identifiers in a phone menu",
    "Never give legal advice about the case",
)

# Must be refs if present at all (C34); a plain value here is dropped.
REF_ONLY_FIELDS = frozenset(
    {"a_number", "receipt_number", "date_of_birth", "interview_location"}
)
# Asylum-claim details never go in a brief, ref'd or not (C34).
CLAIM_FIELDS = frozenset(
    {"country_of_nationality", "nationality", "reasons_for_leaving", "asylum_claim"}
)

MAX_QUESTIONS = 4

# What the rep would call each ref field; others fall back to the field name.
FIELD_LABELS = {
    "a_number": "A-Number",
    "receipt_number": "receipt number",
    "interview_location": "interview location",
    "date_of_birth": "applicant's date of birth",
}

CONTINGENCIES = (
    (
        "If the menu asks for the receipt number, A-Number, or date of birth, take "
        "the speak-to-a-representative path, or ask_user which path to take"
    ),
    (
        "If the representative asks identity or verification questions, bridge the "
        "user so they answer in their own voice"
    ),
    (
        "If the representative asks for legal or case details, say the account "
        "holder will discuss that once bridged"
    ),
)


def build_brief(case: CaseRecord, findings: DeepFindings) -> CaseBrief:
    r1 = case.r1
    issuer = r1.issuer or "the issuing agency"
    doc_type = r1.doc_type or "unknown_notice"
    call_goal = (
        findings.call_goal_en
        or case.call_purpose
        or "Confirm the notice details and what the user needs to do next"
    )
    deadlines = [
        _strip_period(item.item) for item in r1.checklist_en if item.kind == "deadline"
    ]
    deadline_note = (
        f" Deadlines on the notice: {'; '.join(deadlines)}." if deadlines else ""
    )
    return CaseBrief(
        brief_id=f"brief_{uuid.uuid4().hex[:12]}",
        case_id=case.case_id,
        doc_type=doc_type,
        issuer=issuer,
        deadline=r1.deadline,
        appointment=r1.appointment,
        call_goal_en=call_goal,
        questions_to_ask=_questions(case),
        must_not_do=[*REQUIRED_MUST_NOT_DO, *EXTRA_MUST_NOT_DO],
        facts=_safe_facts(r1.key_facts),
        handoff_note=(
            f"Calling {issuer} about a {doc_type} notice. "
            f"Goal: {_strip_period(call_goal)}.{deadline_note} "
            "The user gives any identifiers in their own voice once bridged."
        ),
        likely_rep_questions=_rep_questions(r1.key_facts),
        contingencies=list(CONTINGENCIES),
        open_uncertainties=[
            f"Signal '{s.signal}' was {s.state.replace('_', ' ')} during verification"
            for s in findings.verification.signals
            if s.state in ("not_found", "uncertain")
        ],
    )


def _questions(case: CaseRecord) -> list[str]:
    """Plan.md demo goal first (interview still on, interpreter backup), capped."""
    r1 = case.r1
    questions: list[str] = []
    # An interview notice asks even when the date was unreadable; other letters say "appointment".
    if "interview" in f"{r1.doc_type or ''} {r1.what_is_asked or ''}".lower():
        questions.append("Is the interview still on?")
    elif r1.appointment:
        questions.append("Is the appointment still on?")
    if any(
        item.kind == "who_must_come" and "interpreter" in item.item.lower()
        for item in r1.checklist_en
    ):
        questions.append("What should we do if the interpreter can't come?")
    purpose = _strip_period(case.call_purpose or "")
    if purpose:
        if purpose.endswith("?"):
            questions.append(purpose)
        else:
            questions.append(f"Can you help us {purpose[0].lower()}{purpose[1:]}?")
    if any(item.kind == "bring" for item in r1.checklist_en):
        questions.append("Is there anything else we should bring?")
    return list(dict.fromkeys(questions))[:MAX_QUESTIONS]


def _strip_period(text: str) -> str:
    return text.strip().rstrip(".").rstrip()


def _safe_facts(facts: list[KeyFact]) -> list[KeyFact]:
    return [
        f
        for f in facts
        if f.field not in CLAIM_FIELDS
        and (f.ref is not None or f.field not in REF_ONLY_FIELDS)
    ]


def _rep_questions(facts: list[KeyFact]) -> list[RepQuestion]:
    fields = [
        f.field for f in facts if f.ref is not None and f.field not in CLAIM_FIELDS
    ]
    asked = [
        f"What is the {FIELD_LABELS.get(field, field.replace('_', ' '))}?"
        for field in fields
    ]
    asked += [
        "What is the applicant's full name?",
        "What is the applicant's date of birth?",
    ]
    return [
        RepQuestion(question=q, answer_source=USER_ANSWERS)
        for q in dict.fromkeys(asked)
    ]
