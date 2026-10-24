"""Models internal to the research agent: the pass outputs and the case it works on.

Everything shared (R1, R2, the brief, job payloads) lives in `app.contracts`.
Sensitive values never appear in those; they travel as `<ref:field>`
placeholders (C11, C34), and only `SensitiveValue` holds the real one.
"""

from pydantic import Field

from app.contracts import (
    AlternativeContact,
    Contract,
    FastResult,
    LegitimacySignals,
    RefPlaceholder,
    Verification,
)


class SensitiveValue(Contract):
    """Real value behind a ref. Only jobs.py reads it, to write `case_refs`."""

    field: str
    ref: RefPlaceholder
    value: str = Field(repr=False)


class FastPassOutput(Contract):
    r1: FastResult
    signals: LegitimacySignals
    call_purpose: str | None = None
    unknown_terms: list[str] = Field(default_factory=list)
    sensitive_values: list[SensitiveValue] = Field(default_factory=list)


class DeepFindings(Contract):
    verification: Verification
    official_phone_purpose: str | None = None
    alternative_contacts: list[AlternativeContact] = Field(default_factory=list)
    trust_chain: list[str] = Field(
        default=[], description="URLs from anchor to the page holding official_phone"
    )
    call_goal_en: str | None = None


class CaseRecord(Contract):
    """What the deep pass and the brief need about a case: R1 from `cases`, the
    signals and call purpose from the deep job's payload."""

    case_id: str
    user_id: str
    document_ids: list[str]
    r1: FastResult
    signals: LegitimacySignals
    call_purpose: str | None = None
