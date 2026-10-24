"""Fast pass: letter pages -> R1, legitimacy signals, and sensitive values.

The model only reads the letter. Every safety rule (which values become refs,
what the deep pass may see, date sanity, urgency, the leak guard) runs here in
code, so a model mistake can't push a sensitive value into R1 or the signals.
"""

import logging
import re
import time
from datetime import date
from typing import Literal

import phonenumbers
from anthropic import AsyncAnthropic, transform_schema
from anthropic.types import MessageParam, TextBlockParam
from pydantic import ValidationError

from research.checks import deadline_sane
from research.extraction import Extraction
from research.models import (
    R1,
    Appointment,
    ChecklistItem,
    FastPassOutput,
    KeyDate,
    KeyFact,
    LegitimacySignals,
    LetterPhone,
    ProposedFact,
    SensitiveValue,
    Urgency,
)
from research.preprocess import ContentBlock
from research.prompts import FAST_PASS_SYSTEM

log = logging.getLogger(__name__)

MAX_TOKENS = 16000
EFFORT = "low"
EXTRACTION_SCHEMA = transform_schema(Extraction)

# Always refs, whatever the model says (C34). The model may flag more.
SENSITIVE_FIELDS = frozenset(
    {
        "receipt_number",
        "a_number",
        "interview_location",
        "date_of_birth",
        "recipient_name",
        "recipient_address",
        "case_number",
        "ssn",
    }
)
SHORT_VALUE_LEN = 12
"""Values this short (a first name, a city) match on word boundaries only."""
# What a sensitive value becomes in prose; other fields get "a private detail".
DESCRIPTIONS = {
    "recipient_name": "the person named on the letter",
    "recipient_address": "your address",
    "interview_location": "the interview location",
    "a_number": "your A-Number",
    "receipt_number": "your receipt number",
    "case_number": "your case number",
    "date_of_birth": "your date of birth",
    "ssn": "your Social Security number",
}
PRIVACY_FALLBACK = "Some details of this letter were left out to protect your privacy."
APPOINTMENT_LOCATION_FIELD = "interview_location"
CASE_NUMBER_FIELDS = ("receipt_number", "case_number")
SENSITIVE_CATEGORIES = frozenset({"immigration", "income", "health"})  # C25

# Asylum-claim details are never extracted (C34). Lowercase substrings.
ASYLUM_CLAIM_MARKERS = (
    "nationality",
    "citizenship",
    "citizen of",
    "home country",
    "country of origin",
    "reason for leaving",
    "reasons for leaving",
    "fled",
    "flee",
    "persecut",
    "torture",
    "political opinion",
    "religio",
    "social group",
    "ethnic",
)

# Interviews can be months out; other deadlines use checks.deadline_sane's default.
APPOINTMENT_MAX_DAYS = 365
DEADLINE_MAX_DAYS = 120
DateProblem = Literal["unparseable", "in_the_past", "too_far"]

URGENT_DAYS = 14
SOON_DAYS = 45

DEFAULT_IMAGE_TIP = "Please retake the photo in good light with the whole page in view."
DIFFERENT_LETTERS_QUESTION = (
    "These photos look like they come from different letters. "
    "Which letter should I look at first?"
)
DATE_PROBLEM_TEXT: dict[DateProblem, str] = {
    "unparseable": "could not be read clearly",
    "in_the_past": "seems to be in the past",
    "too_far": "is more than a year away, which is unusual",
}


class FastPassError(RuntimeError):
    """The fast pass can't produce a trustworthy R1 (refusal, truncation, bad output)."""


class SensitiveLeak(FastPassError):
    """A sensitive value ended up in R1 or the signals. Never shipped."""


async def run_fast_pass(
    blocks: list[ContentBlock],
    *,
    case_id: str,
    client: AsyncAnthropic,
    model: str,
    profile_county: str | None = None,
    today: date | None = None,
) -> FastPassOutput:
    """Extract the letter with structured outputs (no citations; quotes live in the schema).

    `profile_county` is a fallback when the letter names no county and a
    cross-check against scams. Sensitive values come back only in
    `sensitive_values`; R1 carries their refs. Caller enforces the 45 s timeout.
    """
    today = today or date.today()
    extraction = await extract(
        blocks, case_id=case_id, client=client, model=model, today=today
    )
    return build_output(
        extraction, case_id=case_id, profile_county=profile_county, today=today
    )


async def extract(
    blocks: list[ContentBlock],
    *,
    case_id: str,
    client: AsyncAnthropic,
    model: str,
    today: date,
) -> Extraction:
    """One structured-output call over all pages. Raises FastPassError on refusal or truncation."""
    if not blocks:
        raise FastPassError("no pages to read")
    content: list[TextBlockParam | ContentBlock] = []
    for page, block in enumerate(blocks, start=1):
        label = f"Page {page}"
        if block["type"] == "document":
            label += f" (a PDF: number its pages {page}, {page + 1}, ... in order)"
        content.append(TextBlockParam(type="text", text=label))
        content.append(block)
    content.append(
        TextBlockParam(
            type="text",
            text=f"Today's date is {today.isoformat()}. Fill the schema for this letter.",
        )
    )
    messages: list[MessageParam] = [{"role": "user", "content": content}]

    started = time.monotonic()
    response = await client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": FAST_PASS_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        thinking={"type": "adaptive"},
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA},
        },
        messages=messages,
    )
    log.info(
        "fast pass model call case_id=%s request_id=%s stop_reason=%s latency_s=%.1f",
        case_id,
        getattr(response, "_request_id", None),
        response.stop_reason,
        time.monotonic() - started,
    )

    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None)
        raise FastPassError(f"model refused the letter (category={category})")
    if response.stop_reason == "max_tokens":
        raise FastPassError("model output hit max_tokens; not parsing a partial result")
    if response.stop_reason != "end_turn":
        raise FastPassError(f"unexpected stop_reason {response.stop_reason!r}")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise FastPassError("model returned no text block")
    try:
        return Extraction.model_validate_json(text)
    except ValidationError as e:
        raise FastPassError(
            f"model output did not match the schema: {e.error_count()} errors"
        ) from e


def build_output(
    ex: Extraction, *, case_id: str, profile_county: str | None, today: date
) -> FastPassOutput:
    """Turn the model's extraction into R1 + signals + sensitive values, applying the safety rules."""
    if not ex.readable:
        r1 = R1(
            case_id=case_id,
            status="needs_better_image",
            image_issue=ex.image_issue or DEFAULT_IMAGE_TIP,
        )
        return FastPassOutput(r1=r1, signals=LegitimacySignals())
    if ex.pages_from_different_letters:
        r1 = R1(
            case_id=case_id,
            status="needs_user_input",
            question_en=DIFFERENT_LETTERS_QUESTION,
        )
        return FastPassOutput(r1=r1, signals=LegitimacySignals())

    sensitive: list[SensitiveValue] = []

    # (a) Sensitive split. Facts are collected first so quotes can be scrubbed after.
    fact_rows: list[tuple[str, str, str, int, bool]] = []
    for fact in ex.facts:
        field = _slug(fact.field)
        if _mentions_asylum_claim(f"{field} {fact.value}"):
            continue
        is_sensitive = fact.sensitive or field in SENSITIVE_FIELDS
        fact_rows.append(
            (field, fact.value, fact.quote, max(fact.page, 1), is_sensitive)
        )
        if is_sensitive:
            _add_sensitive(sensitive, field, fact.value)

    # (g) Dates.
    hedges: list[str] = []
    appointment = None
    appointment_date = None
    if ex.appointment:
        appt = ex.appointment
        appointment_date, problem = check_date(
            appt.date_iso, today, APPOINTMENT_MAX_DAYS
        )
        if problem:
            hedges.append(_hedge(appt.date_raw, problem))
        location_ref = None
        if appt.location_text and appt.location_text.strip():
            location_ref = _add_sensitive(
                sensitive, APPOINTMENT_LOCATION_FIELD, appt.location_text.strip()
            )
        if appointment_date:
            appointment = Appointment(
                date=appointment_date,
                time=_hhmm(appt.time_24h),
                location_ref=location_ref,
                citation=f"p{max(appt.page, 1)}",
            )

    deadline = None
    if ex.deadline_raw or ex.deadline_iso:
        same_as_appointment = (
            ex.appointment and ex.deadline_iso == ex.appointment.date_iso
        )
        max_days = APPOINTMENT_MAX_DAYS if same_as_appointment else DEADLINE_MAX_DAYS
        deadline, problem = check_date(ex.deadline_iso, today, max_days)
        hedge = (
            _hedge(ex.deadline_raw or ex.deadline_iso or "", problem)
            if problem
            else None
        )
        if hedge and hedge not in hedges:
            hedges.append(hedge)
    earliest = min((d for d in (deadline, appointment_date) if d), default=None)

    key_dates = [_key_date(d.type, d.raw, d.iso, today) for d in ex.key_dates]

    key_facts: list[KeyFact] = []
    for field, value, quote, page, is_sensitive in fact_rows:
        if is_sensitive:
            ref = _add_sensitive(sensitive, field, value)
            key_facts.append(KeyFact(field=field, ref=ref, page=page))
        else:
            # A quote may sit next to a sensitive value on the page; drop the quote, keep the value.
            safe_quote = None if _contains_any(quote, sensitive) else quote
            key_facts.append(
                KeyFact(field=field, value=value, quote=safe_quote, page=page)
            )

    # (d, e) Proposed facts: no asylum-claim details, no values, C25 sensitivity.
    proposed = [
        ProposedFact(
            fact=pf.fact,
            source="from_document",
            sensitivity="high"
            if pf.sensitive or pf.category in SENSITIVE_CATEGORIES
            else "normal",
        )
        for pf in ex.proposed_facts
        if not _mentions_asylum_claim(pf.fact) and not _contains_any(pf.fact, sensitive)
    ]

    # (h) Explanation, hedged when a date failed the sanity check.
    explanation = (ex.explanation_en or "").strip()
    if not explanation:
        raise FastPassError("model returned a readable letter with no explanation")
    if hedges:
        explanation = " ".join([explanation, *hedges])

    r1 = R1(
        case_id=case_id,
        status="ok",
        doc_type=_slug(ex.doc_type or "") or "other_letter",
        issuer=ex.issuer,
        deadline=earliest,
        key_dates=key_dates,
        what_is_asked=ex.what_is_asked,
        appointment=appointment,
        checklist_en=[
            ChecklistItem(kind=c.kind, item=c.item, citation=c.citation)
            for c in ex.checklist
        ],
        key_facts=key_facts,
        explanation_en=explanation,
        urgency=_urgency(earliest, today, ex.urgency),
        verification="pending",
        proposed_facts=proposed,
    )
    signals = build_signals(ex, sensitive, profile_county)

    # (c) Scrub every text field, then the leak guard: the last word, after everything above.
    r1, signals = scrub_output(r1, signals, sensitive)
    call_purpose = _scrub(ex.call_purpose, sensitive) if ex.call_purpose else None
    unknown_terms = [t for t in ex.unknown_terms if not _contains_any(t, sensitive)]
    assert_no_leaks(
        [
            r1.model_dump_json(),
            signals.model_dump_json(),
            call_purpose or "",
            *unknown_terms,
        ],
        sensitive,
        case_id=case_id,
    )
    return FastPassOutput(
        r1=r1,
        signals=signals,
        call_purpose=call_purpose,
        unknown_terms=unknown_terms,
        sensitive_values=sensitive,
    )


def scrub_output(
    r1: R1, signals: LegitimacySignals, sensitive: list[SensitiveValue]
) -> tuple[R1, LegitimacySignals]:
    """Take every sensitive value out of R1 and the signals, so a letter with personal data still processes.

    Prose fields get the value replaced by a plain description ("your address").
    Identifier-like fields (fact values, URLs, form IDs, the issuer) and key dates
    are dropped instead: a description there would be false data, and a date's
    `iso` would still carry the value. The explanation drops only the sentences
    that can't be cleaned.
    """

    def prose(text: str | None) -> str | None:
        return _scrub(text, sensitive) if text else text

    def ident(text: str | None) -> str | None:
        return None if text and _contains_any(text, sensitive) else text

    sentences = re.split(r"(?<=[.!?])\s+", r1.explanation_en or "")
    clean = [s for s in (_scrub(s, sensitive) for s in sentences if s) if s]
    key_facts = [
        f if f.ref is not None else f.model_copy(update={"quote": ident(f.quote)})
        for f in r1.key_facts
        if f.ref is not None or ident(f.value) is not None
    ]
    r1 = r1.model_copy(
        update={
            "doc_type": ident(r1.doc_type) or "other_letter",
            "issuer": ident(r1.issuer),
            "what_is_asked": prose(r1.what_is_asked),
            "explanation_en": " ".join(clean) or PRIVACY_FALLBACK,
            "key_dates": [d for d in r1.key_dates if ident(d.raw) is not None],
            "checklist_en": [
                c.model_copy(
                    update={"item": item, "citation": ident(c.citation) or "the letter"}
                )
                for c in r1.checklist_en
                if (item := prose(c.item))
            ],
            "key_facts": key_facts,
        }
    )
    signals = signals.model_copy(
        update={
            "letterhead": ident(signals.letterhead),
            "sub_agency": ident(signals.sub_agency),
            "county": ident(signals.county),
            "return_address": ident(signals.return_address),
            "phones": [
                p.model_copy(
                    update={"label": prose(p.label), "quote": prose(p.quote) or ""}
                )
                for p in signals.phones
            ],
            "urls": [u for u in signals.urls if ident(u)],
            "form_ids": [f for f in signals.form_ids if ident(f)],
            "payment_instructions": prose(signals.payment_instructions),
            "signature_block": prose(signals.signature_block),
        }
    )
    return r1, signals


def build_signals(
    ex: Extraction, sensitive: list[SensitiveValue], profile_county: str | None
) -> LegitimacySignals:
    """(b) What the deep pass may see: sender details only, never PII."""
    return_address = ex.return_address
    if return_address and _contains_any(return_address, sensitive):
        return_address = (
            None  # the model gave the recipient's address, or the interview office
        )

    phones: list[LetterPhone] = []
    for phone in ex.phones:
        number = to_e164(phone.raw)
        if number and number not in {p.number for p in phones}:
            phones.append(
                LetterPhone(number=number, label=phone.label, quote=phone.quote)
            )

    urls: list[str] = []
    for url in ex.urls:
        cleaned = url.strip().rstrip(".,;:)")
        if cleaned and cleaned not in urls:
            urls.append(cleaned)

    # Forms the body only mentions (I-765, G-28...) say nothing about legitimacy.
    form_ids = [
        f"{f.form_id.strip()} (edition {f.edition.strip()})"
        if f.edition
        else f.form_id.strip()
        for f in ex.form_ids
        if f.identifies_this_document
    ]
    case_number = next(
        (
            sv.value
            for field in CASE_NUMBER_FIELDS
            for sv in sensitive
            if sv.field == field
        ),
        None,
    )
    return LegitimacySignals(
        letterhead=ex.letterhead,
        sub_agency=ex.sub_agency,
        county=ex.county or profile_county,
        return_address=return_address,
        phones=phones,
        urls=urls,
        form_ids=form_ids,
        case_number_format=shape_of(case_number) if case_number else None,
        payment_instructions=ex.payment_instructions,
        signature_block=ex.signature_block,
    )


def assert_no_leaks(
    texts: list[str], sensitive: list[SensitiveValue], *, case_id: str
) -> None:
    """Raise SensitiveLeak if any sensitive value appears in any of `texts`."""
    for text in texts:
        for sv in sensitive:
            if _contains(text, sv.value):
                log.error("sensitive value leaked case_id=%s ref=%s", case_id, sv.ref)
                raise SensitiveLeak(f"{sv.ref} appeared in the fast-pass output")


def check_date(
    iso: str | None, today: date, max_days: int
) -> tuple[date | None, DateProblem | None]:
    """Parse a model-read YYYY-MM-DD date and run checks.deadline_sane on it.

    Returns (date, None) if sane, else (None, why) so the explanation can hedge.
    """
    try:
        parsed = date.fromisoformat((iso or "").strip())
    except ValueError:
        return None, "unparseable"
    if deadline_sane(parsed, today, max_days):
        return parsed, None
    return None, "in_the_past" if parsed < today else "too_far"


def to_e164(raw: str) -> str | None:
    """Normalize a printed phone number to E.164 (US default), or None if it isn't valid."""
    try:
        parsed = phonenumbers.parse(raw, "US")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def shape_of(value: str) -> str:
    """Describe a case number's shape without its value: 'IOE0123456789' -> '3 letters + 10 digits'."""
    parts: list[str] = []
    for run in re.finditer(r"[A-Za-z]+|\d+|\s+|.", value.strip()):
        token = run.group()
        if token.isalpha():
            parts.append(f"{len(token)} letter{'s' if len(token) > 1 else ''}")
        elif token.isdigit():
            parts.append(f"{len(token)} digit{'s' if len(token) > 1 else ''}")
        elif token.isspace():
            parts.append("space")
        else:
            parts.append(f"'{token}'")
    return " + ".join(parts)


def _add_sensitive(sensitive: list[SensitiveValue], field: str, value: str) -> str:
    """Return the ref for (field, value), adding a SensitiveValue if it's new."""
    for sv in sensitive:
        if sv.field == field and sv.value == value:
            return sv.ref
    name, n = field, 2
    while any(sv.ref == f"<ref:{name}>" for sv in sensitive):
        name, n = f"{field}_{n}", n + 1
    ref = f"<ref:{name}>"
    sensitive.append(SensitiveValue(field=field, ref=ref, value=value))
    return ref


def _value_pattern(value: str) -> re.Pattern[str]:
    """Case-insensitive; short values only as whole words, so "Ana" doesn't hit "Analysis"."""
    escaped = re.escape(value)
    if len(value) <= SHORT_VALUE_LEN:
        escaped = rf"(?<!\w){escaped}(?!\w)"
    return re.compile(escaped, re.IGNORECASE)


def _scrub(text: str, sensitive: list[SensitiveValue]) -> str | None:
    """Replace each sensitive value with a description; None if one still shows (e.g. odd spacing)."""
    for sv in sorted(sensitive, key=lambda s: len(s.value), reverse=True):
        value = sv.value.strip()
        if value:
            description = DESCRIPTIONS.get(sv.field, "a private detail")
            text = _value_pattern(value).sub(lambda _, d=description: d, text)
    return None if _contains_any(text, sensitive) else text


def _contains(text: str, value: str) -> bool:
    """Case-insensitive match (whole words for short values), plus a spacing-insensitive match for ID-like values."""
    value = value.strip()
    if not value:
        return False
    if _value_pattern(value).search(text):
        return True
    compact = re.sub(r"[^0-9a-z]", "", value.casefold())
    if len(compact) >= 6 and sum(c.isdigit() for c in compact) >= 4:
        return compact in re.sub(r"[^0-9a-z]", "", text.casefold())
    return False


def _contains_any(text: str, sensitive: list[SensitiveValue]) -> bool:
    return any(_contains(text, sv.value) for sv in sensitive)


def _mentions_asylum_claim(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in ASYLUM_CLAIM_MARKERS)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", text.strip().lower()).strip("_")


def _hhmm(text: str | None) -> str | None:
    if text and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", text.strip()):
        return text.strip()
    return None


def _hedge(raw: str, problem: DateProblem) -> str:
    return (
        f'The date "{raw}" on the letter {DATE_PROBLEM_TEXT[problem]}, '
        "so please check it on the letter itself."
    )


def _key_date(kind: str, raw: str, iso: str | None, today: date) -> KeyDate:
    """Deadlines and appointments get the sanity check; other dates (notice dates) may be past."""
    if kind in ("deadline", "appointment"):
        max_days = APPOINTMENT_MAX_DAYS if kind == "appointment" else DEADLINE_MAX_DAYS
        parsed, _ = check_date(iso, today, max_days)
    else:
        try:
            parsed = date.fromisoformat((iso or "").strip())
        except ValueError:
            parsed = None
    return KeyDate(type=kind, raw=raw, iso=parsed)


def _urgency(
    earliest: date | None, today: date, model_urgency: Urgency | None
) -> Urgency | None:
    """(i) Within 14 days is always high. Otherwise the date rule (within 45 days is
    medium) or the model's reading of the consequences, whichever is higher."""
    if earliest is None:
        return model_urgency
    days = (earliest - today).days
    if days <= URGENT_DAYS:
        return "high"
    by_date: Urgency = "medium" if days <= SOON_DAYS else "low"
    order: list[Urgency] = ["low", "medium", "high"]
    if model_urgency and order.index(model_urgency) > order.index(by_date):
        return model_urgency
    return by_date
