"""Where the deep pass should look, by document type. Config, not letter-specific logic.

Never put a phone number here (C32): official numbers are looked up at run time.
"""

import re
from typing import Literal

from pydantic import BaseModel

from research.models import LegitimacySignals

# Sites that republish agency numbers. Their numbers can be stale or planted, so
# the fetch tool refuses them and web search never returns them.
BLOCKED_DOMAINS: tuple[str, ...] = (
    "gethuman.com",
    "800notes.com",
    "whocalled.us",
    "whocallsme.com",
    "callercenter.com",
    "whitepages.com",
    "yellowpages.com",
    "yelp.com",
    "customerservicenumbers.com",
    "customerservicenumber.org",
    "contactnumbers.org",
    "contacthelp.com",
    "customercarecontacts.com",
    "phonenumbers.how",
    "numberbarn.com",
    "usa-customer-service.com",
)

# Identifier shapes that must never leave in a URL (receipt number, A-Number, SSN).
ID_SHAPED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![a-z])[a-z]{3}\d{10}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![a-z])a-?\d{8,9}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
)


# Words in a number's label that mark a special-purpose line, never the main one.
SECONDARY_LINE_WORDS: tuple[str, ...] = (
    "tty",
    "tdd",
    "teletype",
    "relay",
    "military",
    "fax",
    "international",
    "overseas",
    "outside the u.s",
)


class PurposePage(BaseModel):
    """Which kind of official page answers a given call purpose."""

    keywords: list[str]
    page_kind: str


class Hint(BaseModel):
    depth: Literal["deep", "shallow", "unverifiable"]
    issuer_short: str | None = None
    federal: bool = False
    anchor_domains: list[str] = []
    issuer_domains: list[str] = []
    """When set, the official number must come from one of these domains. When
    empty, the issuer's own domain is discovered (e.g. a county office)."""
    issuer_names: list[str] = []
    """Official names of the issuer, used to check a directory page is about it."""
    directory_domains: list[str] = []
    """Official government directories (.gov) whose page for this issuer may stand in
    for the issuer's own site, only when that site can't be fetched."""
    search_terms: list[str] = []
    look_for: str = "the issuer's official contact page"
    purpose_pages: dict[str, PurposePage] = {}
    default_purpose: str = "general"
    known_forms: list[str] = []
    case_number_shape: tuple[int, int] | None = None
    """(letters, digits) of the case number, e.g. (3, 10)."""
    letterhead_keywords: list[str] = []
    alternatives: list[tuple[str, str]] = []
    """(name, purpose) suggestions offered when the letter can't be verified."""


HINTS: dict[str, Hint] = {
    "uscis": Hint(
        depth="deep",
        issuer_short="USCIS",
        federal=True,
        anchor_domains=["uscis.gov"],
        issuer_domains=["uscis.gov"],
        issuer_names=["U.S. Citizenship and Immigration Services"],
        directory_domains=["usa.gov"],
        search_terms=["USCIS Contact Center phone number site:uscis.gov"],
        look_for="the USCIS Contact Center page on uscis.gov",
        purpose_pages={
            "case_questions": PurposePage(
                keywords=[
                    "appointment",
                    "interview",
                    "reschedule",
                    "schedule",
                    "case",
                    "status",
                    "notice",
                    "interpreter",
                ],
                page_kind="the USCIS Contact Center page (uscis.gov/contactcenter), "
                "which lists the phone number for questions about an existing case or appointment",
            ),
        },
        default_purpose="case_questions",
        known_forms=["I-797", "I-797A", "I-797B", "I-797C", "I-797D", "I-589"],
        case_number_shape=(3, 10),
        letterhead_keywords=["citizenship and immigration", "uscis"],
        alternatives=[
            (
                "DOJ-recognized legal service providers (EOIR list)",
                "Free or low-cost immigration legal help",
            )
        ],
    ),
    "immigration_court": Hint(
        depth="deep",
        issuer_short="the Immigration Court (EOIR)",
        federal=True,
        anchor_domains=["justice.gov"],
        issuer_domains=["justice.gov"],
        search_terms=["EOIR immigration court contact site:justice.gov/eoir"],
        look_for="the EOIR pages on justice.gov/eoir (automated case information line or the court's page)",
        purpose_pages={
            "case_questions": PurposePage(
                keywords=["hearing", "court", "case", "judge", "status"],
                page_kind="the EOIR page with the automated case information line, "
                "or the specific immigration court's page",
            ),
        },
        default_purpose="case_questions",
        known_forms=["EOIR-26", "EOIR-28", "EOIR-33", "EOIR-42A", "EOIR-42B"],
        letterhead_keywords=["executive office for immigration review", "eoir"],
    ),
    "county_benefits": Hint(
        depth="shallow",
        search_terms=[
            "{county} county social services office phone site:.gov",
            "state list of county social services offices",
        ],
        look_for="the state's official .gov list of county offices, then the county office page it links to",
        purpose_pages={
            "renewal": PurposePage(
                keywords=["renew", "renewal", "redetermination", "benefits", "case"],
                page_kind="the county benefits office contact page",
            ),
        },
        default_purpose="renewal",
        letterhead_keywords=["county", "social services", "human services"],
    ),
    "housing": Hint(
        depth="shallow",
        anchor_domains=["hud.gov"],
        search_terms=[
            "{county} housing authority contact",
            "HUD public housing agency contact list",
        ],
        look_for="the local housing authority's page, reached from hud.gov or the city/county .gov site",
        purpose_pages={
            "housing_case": PurposePage(
                keywords=[
                    "voucher",
                    "section 8",
                    "recertification",
                    "housing",
                    "lease",
                ],
                page_kind="the housing authority's contact page",
            ),
        },
        default_purpose="housing_case",
        letterhead_keywords=["housing authority", "housing and urban development"],
    ),
    "private_landlord": Hint(
        depth="unverifiable",
        alternatives=[
            ("Local tenant rights organization", "Free advice on landlord notices"),
            ("City or county housing department", "Questions about tenant rights"),
        ],
    ),
}

DEFAULT_HINT = Hint(depth="shallow", search_terms=["{issuer} official contact"])

# doc_type prefixes Track A may emit, mapped to a hint key.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("uscis", "uscis"),
    ("dhs_uscis", "uscis"),
    ("immigration_court", "immigration_court"),
    ("eoir", "immigration_court"),
    ("county", "county_benefits"),
    ("medi_cal", "county_benefits"),
    ("benefits", "county_benefits"),
    ("housing", "housing"),
    ("hud", "housing"),
    ("private_landlord", "private_landlord"),
    ("landlord", "private_landlord"),
)


def hint_key(doc_type: str | None) -> str | None:
    """The HINTS key for `doc_type` by prefix, or None."""
    if not doc_type:
        return None
    normalized = doc_type.lower().replace("-", "_").replace(" ", "_")
    for prefix, key in _PREFIXES:
        if normalized.startswith(prefix):
            return key
    return None


def where_to_look(doc_type: str | None) -> Hint:
    """Return the search hint for `doc_type`; unknown types get a generic shallow hint."""
    key = hint_key(doc_type)
    return HINTS[key] if key else DEFAULT_HINT


def guess_doc_type(signals: LegitimacySignals) -> str | None:
    """Pick a hint key from the letterhead and form IDs when no doc_type is given."""
    header = " ".join(filter(None, [signals.letterhead, signals.sub_agency])).lower()
    forms = " ".join(signals.form_ids).upper()
    for key, hint in HINTS.items():
        if any(form in forms for form in hint.known_forms):
            return key
    for key, hint in HINTS.items():
        if any(word in header for word in hint.letterhead_keywords):
            return key
    return None


def purpose_key(hint: Hint, call_purpose: str | None) -> str:
    """The purpose_pages key whose keywords match `call_purpose`, else the default."""
    text = (call_purpose or "").lower()
    for key, page in hint.purpose_pages.items():
        if any(word in text for word in page.keywords):
            return key
    return hint.default_purpose
