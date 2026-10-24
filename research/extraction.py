"""The schema the model fills in the fast pass (structured outputs).

This is internal to the research agent: it holds real values, including
sensitive ones. `fast_pass.py` turns it into R1, LegitimacySignals and
SensitiveValues; nothing outside research ever sees this model.

The API caps structured-output schemas at 16 union-typed (nullable) fields, so
no field here is nullable on the wire: optional text is a plain string where
"" means "not on the letter" (OptStr turns it into None), and the appointment
is a list of zero or one.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, WithJsonSchema


def _blank_to_none(value: Any) -> Any:
    return (value.strip() or None) if isinstance(value, str) else value


OptStr = Annotated[
    str | None, BeforeValidator(_blank_to_none), WithJsonSchema({"type": "string"})
]


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedDate(_Schema):
    type: Literal["notice_date", "received_date", "deadline", "appointment", "other"]
    raw: str = Field(description="Exactly as printed")
    iso: OptStr = Field(description="YYYY-MM-DD, or empty if unsure")


class ExtractedAppointment(_Schema):
    date_raw: str = Field(description="Exactly as printed")
    date_iso: OptStr = Field(description="YYYY-MM-DD, or empty if unsure")
    time_24h: OptStr = Field(description="HH:MM in 24-hour time, or empty")
    location_text: OptStr = Field(
        description="Full place of the appointment as printed (office name and address)"
    )
    quote: str = Field(description="Verbatim sentence giving the date and time")
    page: int


class ExtractedFact(_Schema):
    field: str = Field(
        description="snake_case name, e.g. receipt_number, a_number, case_number, "
        "date_of_birth, recipient_name, recipient_address, form_id, program"
    )
    value: str = Field(description="Exactly as printed")
    quote: str = Field(description="Verbatim text from the letter containing the value")
    page: int
    sensitive: bool = Field(
        description="True for anything that identifies the person or their case"
    )


class ExtractedChecklistItem(_Schema):
    kind: Literal["who_must_come", "bring", "deadline"]
    item: str = Field(description="Plain English, one requirement per item")
    citation: str = Field(description="Where it is, e.g. 'p1 §II' or 'p2'")


class ExtractedPhone(_Schema):
    raw: str = Field(description="Exactly as printed")
    label: OptStr = Field(description="What the letter says the number is for")
    quote: str = Field(description="Verbatim text around the number")


class ExtractedFormId(_Schema):
    form_id: str = Field(description="e.g. I-797C")
    edition: OptStr = Field(description="Edition date as printed, or empty")


class ExtractedProposedFact(_Schema):
    fact: str = Field(description="Short English fact about the user worth remembering")
    category: Literal["immigration", "income", "health", "other"]
    sensitive: bool


class Extraction(_Schema):
    """Everything the fast pass reads off the letter."""

    readable: bool = Field(description="False if the text can't be read reliably")
    image_issue: OptStr = Field(
        description="If not readable: one specific retake tip in English"
    )
    pages_from_different_letters: bool = Field(
        description="True only if the pages clearly belong to different letters"
    )
    doc_type: OptStr = Field(
        description="snake_case, e.g. uscis_i797c_asylum_interview, or other_<short_name>"
    )
    issuer: OptStr = Field(
        description="The specific agency or company that sent the letter and handles "
        "the matter; the component, not its parent department"
    )
    sub_agency: OptStr = Field(
        description="If the issuer is a component of a larger department, the issuer's "
        "name as that component; empty otherwise"
    )
    letterhead: OptStr = Field(description="Letterhead text as printed")
    key_dates: list[ExtractedDate]
    deadline_raw: OptStr = Field(
        description="Earliest date the user must act by, as printed"
    )
    deadline_iso: OptStr = Field(description="YYYY-MM-DD, or empty if unsure")
    appointments: list[ExtractedAppointment] = Field(
        description="The appointment or interview, if any: zero or one item"
    )
    facts: list[ExtractedFact]
    checklist: list[ExtractedChecklistItem]
    what_is_asked: OptStr = Field(description="One short line: what the letter asks")
    explanation_en: OptStr = Field(
        description="3-6 plain English sentences; no sensitive values, no legal advice"
    )
    urgency: Literal["low", "medium", "high"]
    phones: list[ExtractedPhone] = Field(
        description="Phone numbers printed by the sender (not the recipient's)"
    )
    urls: list[str] = Field(description="Every web address printed, as printed")
    form_ids: list[ExtractedFormId]
    return_address: OptStr = Field(
        description="The sender's address, never the recipient's"
    )
    payment_instructions: OptStr = Field(
        description="Any request for money and how to pay, quoted; empty if none"
    )
    signature_block: OptStr
    county: OptStr = Field(description="County named on the letter, or empty")
    call_purpose: OptStr = Field(
        description="What a phone call to the sender would be about, one line"
    )
    unknown_terms: list[str] = Field(
        description="Official jargon a family may not know, as printed"
    )
    proposed_facts: list[ExtractedProposedFact]

    @property
    def appointment(self) -> ExtractedAppointment | None:
        return self.appointments[0] if self.appointments else None
