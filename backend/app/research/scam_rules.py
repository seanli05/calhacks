"""Deterministic scam red flags. Offline, no model.

Each flag is a plain-English sentence the orchestrator can relay as-is.
"""

import re

from app.research.fetch_tool import is_gov, registered_domain
from app.research.hints import Hint
from app.research.models import LegitimacySignals

# (pattern, what the letter asks for). Matched on payment text and signature.
_PAYMENT_RULES: tuple[tuple[str, str], ...] = (
    (
        r"gift ?cards?|itunes|google play cards?|steam cards?|prepaid cards?",
        "payment by gift card",
    ),
    (r"western union|moneygram", "payment through Western Union or MoneyGram"),
    (r"wire transfer|wire (the|your|a) (money|payment|fee)", "a wire transfer"),
    (r"bitcoin|crypto|btc\b|usdt|ethereum|tether", "payment in cryptocurrency"),
    (r"zelle|cash ?app|venmo", "payment through Zelle, Cash App, or Venmo"),
)
_THREAT = r"\b(arrest(ed)?|deport(ed|ation)?|jail|prison|warrant|police will)\b"
_NOTARIO = (
    r"\bnotari[oa]s?\b|\b(we|our office) (can|will) (file|prepare|submit)\b"
    r"|pay\b.{0,40}\b(to|for) (file|filing|process|expedite)"
)
_URGENCY = (
    r"\b(immediately|urgent|final (notice|warning)|within (24|48) hours"
    r"|today only|act now|right away)\b"
)
_SENSITIVE = r"social security|\bssn\b|bank account|routing number|card number|debit card|credit card"
_BY_PHONE = r"\b(phone|call|text|sms|whatsapp)\b"

# Category rules: they run only for hints of that category, on top of the rules above.
_UNRECOVERABLE = (
    r"wire|zelle|cash ?app|venmo|bitcoin|crypto|gift ?cards?|western union|moneygram"
)
_HOUSING_RULES: tuple[tuple[str, str], ...] = (
    (
        (
            rf"\b(deposit|first month|application fee|holding fee)\b.{{0,80}}({_UNRECOVERABLE})"
            rf"|({_UNRECOVERABLE}).{{0,80}}\b(deposit|first month|application fee|holding fee)\b"
        ),
        (
            "This letter asks for a rental deposit or fee by wire, payment app, gift card, "
            "or crypto. Scammers ask for deposits this way because the money can't be recovered."
        ),
    ),
    (
        r"\b(abroad|out of the country|overseas|missionary)\b|mail (you )?the keys",
        (
            "This letter says the landlord is away and can't show the home in person. "
            "This is a common rental scam."
        ),
    ),
    (
        (
            r"(section 8|voucher|wait(ing)? ?list)\b.{0,40}"
            r"\b(application|registration|sign.?up|processing|placement) fee\b"
            r"|\b(pay|fee)\b.{0,40}\b(join|get on|be added to|be placed on|move up)\b"
            r".{0,40}(section 8|voucher|wait(ing)? ?list)"
        ),
        (
            "This letter asks for a fee to join a Section 8 or housing waitlist. "
            "Applying for Section 8 is free."
        ),
    ),
)
_MEDICAL_RULES: tuple[tuple[str, str], ...] = (
    (
        r"\bfree\b.{0,40}\b(tests?|testing|genetic|dna|screenings?|kits?|braces?|equipment)\b",
        (
            "This letter offers free medical tests or equipment. Offers like this are a "
            "common way to steal Medicare or insurance numbers."
        ),
    ),
)
_MEDICAL_ID = (
    r"medicare (number|card|id)|\bmbi\b|member (id|number)|policy number"
    r"|insurance (id|card|number)"
)
_CATEGORY_WHO = {
    "housing": "a real landlord or housing agency",
    "medical": "a real hospital, health plan, or Medicare",
}


def _issuer(hint: Hint) -> str:
    who = hint.issuer_short or _CATEGORY_WHO.get(
        hint.category or "", "a real government agency"
    )
    return who[0].upper() + who[1:]


def scam_red_flags(signals: LegitimacySignals, hint: Hint) -> list[str]:
    """Red flags from payment demands, threats, and links. Empty if none."""
    text = " \n ".join(
        filter(
            None,
            [signals.payment_instructions, signals.signature_block],
        )
    ).lower()
    who = _issuer(hint)
    flags: list[str] = []

    for pattern, what in _PAYMENT_RULES:
        if re.search(pattern, text):
            flags.append(f"This letter asks for {what}. {who} never asks for that.")

    if re.search(_THREAT, text):
        flags.append(
            "This letter threatens arrest or deportation. "
            f"{who} does not threaten people in letters to get payment or information."
        )

    if re.search(_NOTARIO, text):
        flags.append(
            "This letter offers paid filing help or mentions a notario. "
            "Notarios are not lawyers and cannot give immigration legal advice."
        )

    if hint.federal:
        outside = sorted(
            {registered_domain(u) for u in signals.urls if u and not is_gov(u)}
        )
        if outside:
            flags.append(
                f"This letter links to {', '.join(outside)}, which is not a .gov website. "
                "Federal agencies use .gov websites."
            )

    if re.search(_URGENCY, text) and not signals.case_number_format:
        flags.append(
            "This letter pressures you to act right away but has no case or receipt number. "
            "Real agency notices identify your case."
        )

    for chunk in re.split(r"[.\n!?]", text):
        if re.search(_SENSITIVE, chunk) and re.search(_BY_PHONE, chunk):
            flags.append(
                "This letter asks you to give card numbers, your Social Security number, "
                "or bank details by phone or text. Do not share them."
            )
            break

    rules = {"housing": _HOUSING_RULES, "medical": _MEDICAL_RULES}.get(
        hint.category or "", ()
    )
    for pattern, flag in rules:
        if re.search(pattern, text):
            flags.append(flag)

    if hint.category == "medical":
        for chunk in re.split(r"[.\n!?]", text):
            if re.search(_MEDICAL_ID, chunk) and re.search(_BY_PHONE, chunk):
                flags.append(
                    "This letter asks for your Medicare or insurance number by phone "
                    "or text. Medicare and real insurers don't ask for it that way."
                )
                break

    return flags
