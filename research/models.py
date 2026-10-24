# These move to the team's shared contracts module once it exists.
"""Research agent contracts: R1, R2, CaseBrief, and the internal pass outputs.

Formats follow Plan.md: prefixed IDs and E.164 phones (C19), ISO dates, fact
sources (C4), verification statuses (C18). Sensitive values never appear in
R1/R2/CaseBrief; they travel as `<ref:field>` placeholders (C11, C34).
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CaseId = Annotated[str, Field(pattern=r"^case_\w+$")]
UserId = Annotated[str, Field(pattern=r"^user_\w+$")]
DocumentId = Annotated[str, Field(pattern=r"^doc_\w+$")]
BriefId = Annotated[str, Field(pattern=r"^brief_\w+$")]
E164 = Annotated[str, Field(pattern=r"^\+[1-9]\d{1,14}$")]
Ref = Annotated[str, Field(pattern=r"^<ref:[a-z0-9_]+>$")]

FactSource = Literal["user_said", "from_document", "from_call", "inferred"]
VerificationStatus = Literal["pending", "verified", "suspicious", "unknown"]
Sensitivity = Literal["normal", "high"]
Urgency = Literal["low", "medium", "high"]
R1Status = Literal["ok", "needs_better_image", "needs_user_input"]
KeyDateType = Literal[
    "notice_date", "received_date", "deadline", "appointment", "other"
]
ChecklistKind = Literal["who_must_come", "bring", "deadline"]
SignalState = Literal["match", "not_found", "conflict", "uncertain"]

# Always in a brief's must_not_do (C34, C35).
REQUIRED_MUST_NOT_DO: tuple[str, ...] = (
    "Never give the A-Number, receipt number, or date of birth",
    "Never discuss the asylum claim",
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KeyDate(Contract):
    type: KeyDateType
    raw: str
    iso: date | None = None


class KeyFact(Contract):
    """One extracted fact. Sensitive facts carry `ref` and no `value` or `quote`."""

    field: str
    value: str | None = None
    ref: Ref | None = None
    quote: str | None = None
    page: int = Field(ge=1)

    @model_validator(mode="after")
    def _value_xor_ref(self) -> "KeyFact":
        if (self.value is None) == (self.ref is None):
            raise ValueError("KeyFact needs exactly one of value or ref")
        if self.ref is not None and self.quote is not None:
            raise ValueError(
                "a ref'd KeyFact must not quote the letter (it holds the value)"
            )
        return self


class Appointment(Contract):
    date: date
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    location_ref: Ref | None = None
    citation: str


class ChecklistItem(Contract):
    kind: ChecklistKind
    item: str
    citation: str


class ProposedFact(Contract):
    fact: str
    source: FactSource
    sensitivity: Sensitivity = "normal"


class R1(Contract):
    """Fast-pass result: the `result` of a `research_fast` job."""

    case_id: CaseId
    status: R1Status
    image_issue: str | None = None
    question_en: str | None = None
    doc_type: str | None = None
    issuer: str | None = None
    deadline: date | None = None
    key_dates: list[KeyDate] = []
    what_is_asked: str | None = None
    appointment: Appointment | None = None
    checklist_en: list[ChecklistItem] = []
    key_facts: list[KeyFact] = []
    explanation_en: str | None = None
    urgency: Urgency | None = None
    verification: VerificationStatus = "pending"
    proposed_facts: list[ProposedFact] = []

    @model_validator(mode="after")
    def _status_fields(self) -> "R1":
        if self.status == "needs_better_image" and not self.image_issue:
            raise ValueError("needs_better_image requires image_issue")
        if self.status == "needs_user_input" and not self.question_en:
            raise ValueError("needs_user_input requires question_en")
        if self.status == "ok" and not (self.doc_type and self.explanation_en):
            raise ValueError("ok requires doc_type and explanation_en")
        return self


class LetterPhone(Contract):
    number: E164
    label: str | None = None
    quote: str


class LegitimacySignals(Contract):
    """What the deep pass may see. Never names, case numbers, or the user's address."""

    letterhead: str | None = None
    sub_agency: str | None = None
    county: str | None = None
    return_address: str | None = None
    phones: list[LetterPhone] = []
    urls: list[str] = []
    form_ids: list[str] = []
    case_number_format: str | None = Field(
        default=None,
        description="Shape of the case number (e.g. 3 letters + 10 digits), never the value",
    )
    payment_instructions: str | None = None
    signature_block: str | None = None


class SignalResult(Contract):
    signal: str
    state: SignalState
    evidence: list[str] = []


class Verification(Contract):
    status: VerificationStatus
    official_phone: E164 | None = None
    letter_phone_matches: bool | None = None
    evidence: list[str] = []
    red_flags: list[str] = []
    signals: list[SignalResult] = []


class AlternativeContact(Contract):
    name: str
    purpose: str
    phone: E164 | None = None
    url: str | None = None


class R2(Contract):
    """Deep-pass result: the `result` of a `research_deep` job."""

    case_id: CaseId
    verification: Verification
    official_phone_purpose: str | None = None
    alternative_contacts: list[AlternativeContact] = []
    call_recommended: bool
    brief_id: BriefId | None = None
    call_goal_en: str | None = None

    @model_validator(mode="after")
    def _call_needs_verified_number(self) -> "R2":
        if self.call_recommended and not (
            self.verification.status == "verified" and self.verification.official_phone
        ):
            raise ValueError("call_recommended requires a verified official_phone")
        return self


class RepQuestion(Contract):
    question: str
    answer_source: str


class CaseBrief(Contract):
    """Stored in `case_briefs`; read by the phone agent."""

    brief_id: BriefId
    case_id: CaseId
    doc_type: str
    issuer: str
    deadline: date | None = None
    appointment: Appointment | None = None
    call_goal_en: str
    expected_menu_path: list[str] = []
    questions_to_ask: list[str] = []
    must_not_do: list[str] = Field(default_factory=lambda: list(REQUIRED_MUST_NOT_DO))
    glossary_terms: list[str] = []
    facts: list[KeyFact] = []
    handoff_note: str
    likely_rep_questions: list[RepQuestion] = []
    contingencies: list[str] = []
    open_uncertainties: list[str] = []

    @model_validator(mode="after")
    def _required_must_not_do(self) -> "CaseBrief":
        missing = [
            rule for rule in REQUIRED_MUST_NOT_DO if rule not in self.must_not_do
        ]
        if missing:
            raise ValueError(f"must_not_do is missing required rules: {missing}")
        return self


class ResearchFastPayload(Contract):
    """H1 job payload."""

    job: Literal["research_fast"] = "research_fast"
    case_id: CaseId
    user_id: UserId
    document_ids: list[DocumentId] = Field(min_length=1)
    user_language: str = Field(pattern=r"^[a-z]{2}$")
    user_note_en: str | None = None


class ResearchDeepPayload(Contract):
    """research_deep job payload. `answers` carries replies to a needs_user_input question."""

    job: Literal["research_deep"] = "research_deep"
    case_id: CaseId
    user_id: UserId
    document_ids: list[DocumentId] = Field(min_length=1)
    answers: dict[str, str] = {}


QuestionStatus = Literal[
    "answered",
    "not_confirmed",
    "declined_legal_advice",
    "declined_asylum_claim",
    "out_of_scope",
]


class ResearchQuestionPayload(Contract):
    """research_question job payload. The orchestrator sends the question already in English."""

    job: Literal["research_question"] = "research_question"
    user_id: UserId
    case_id: CaseId | None = None
    question_en: str = Field(min_length=1, max_length=2000)


class QuestionSource(Contract):
    """An official page the answer rests on, with a quote code found on that page."""

    url: str
    quote: str = Field(min_length=1)


class QuestionAnswer(Contract):
    """research_question result. Only `answered` carries an answer, always with sources."""

    status: QuestionStatus
    answer_en: str | None = None
    sources: list[QuestionSource] = []
    reason_en: str | None = None

    @model_validator(mode="after")
    def _answer_has_sources(self) -> "QuestionAnswer":
        if self.status == "answered" and not (self.answer_en and self.sources):
            raise ValueError("an answered question needs answer_en and sources")
        if self.status != "answered" and (self.answer_en or self.sources):
            raise ValueError(f"status {self.status} carries no answer or sources")
        return self


# --- Internal to the research agent ---


class SensitiveValue(Contract):
    """Real value behind a ref. Only jobs.py reads it, to write `case_refs`."""

    field: str
    ref: Ref
    value: str = Field(repr=False)


class FastPassOutput(Contract):
    r1: R1
    signals: LegitimacySignals
    call_purpose: str | None = None
    unknown_terms: list[str] = []
    sensitive_values: list[SensitiveValue] = []


class DeepFindings(Contract):
    verification: Verification
    official_phone_purpose: str | None = None
    alternative_contacts: list[AlternativeContact] = []
    trust_chain: list[str] = Field(
        default=[], description="URLs from anchor to the page holding official_phone"
    )
    call_goal_en: str | None = None
