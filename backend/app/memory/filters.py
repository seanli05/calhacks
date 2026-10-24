"""What may be stored, and how (C25, C34): the memory writer's rules, in code.

Every fact passes through here, whoever proposed it. Asylum claim details and
identifiers are dropped outright; immigration, income and health facts are
sensitive and held as `pending_consent` (C15). The markers err toward dropping and
toward holding: a lost fact costs little, a leaked one can put someone at risk.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.contracts import FactSource, FactStatus, Sensitivity

SENSITIVE_CATEGORIES = frozenset({"immigration", "income", "health"})
DROPPED_CATEGORIES = frozenset({"asylum_claim", "identifier"})

# Details of the claim itself: origin, nationality, what happened, why they left.
_ASYLUM_CLAIM = re.compile(
    r"\b(?:persecut|tortur|fled\b|flee|escap|threat|kidnap|extort|gang|cartel|"
    r"militia|politic|religio|ethnic|nationality|citizenship|citizen of|"
    r"national of|native of|home country|country of origin|born in|"
    r"originally from|(?:is|are|comes?|came) from|"
    r"reasons? for (?:leaving|fleeing)|"
    r"left (?:my|his|her|their|the) country|social group|"
    r"fear of (?:return|going back)|afraid to (?:return|go back))",
    re.IGNORECASE,
)

# Identifiers live only in `case_refs` (C34); none of them belongs in a fact.
_IDENTIFIER = re.compile(
    r"<ref:|"
    r"\bA[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2,3}\b|"  # A-Number
    r"\b[A-Z]{3}\d{10}\b|"  # receipt number
    r"\b(?:date of birth|birth ?date|born on|dob|social security|ssn|passport|"
    r"a-number|alien number|receipt number)\b|"
    r"[\w.+-]+@[\w-]+\.[\w.]+",  # email
    re.IGNORECASE,
)
# Seven or more digits in a row (phone, SSN, case numbers), once dates are removed.
_LONG_NUMBER = re.compile(r"\d(?:[\s().-]*\d){6,}")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")

# Backstop for a model or a proposer that files an immigration fact elsewhere.
_IMMIGRATION = re.compile(
    r"\b(?:asylum|uscis|immigra|visa|green card|refugee|deport|removal|"
    r"work permit|ead|tps|daca|parole|i-\d{2,4}|interview|hearing|"
    r"immigration court|biometric)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Candidate:
    fact: str
    category: str
    source: FactSource
    sensitive: bool = False


@dataclass(frozen=True)
class Storable:
    fact: str
    category: str
    source: FactSource
    sensitivity: Sensitivity
    status: FactStatus


def forbidden(candidate: Candidate) -> bool:
    """True for asylum claim details and identifiers: never stored (C34)."""
    if candidate.category in DROPPED_CATEGORIES:
        return True
    text = candidate.fact
    if _ASYLUM_CLAIM.search(text) or _IDENTIFIER.search(text):
        return True
    return bool(_LONG_NUMBER.search(_DATE.sub(" ", text)))


def storable(candidate: Candidate) -> Storable | None:
    """How to store the candidate, or None if it must not be stored."""
    fact = " ".join(candidate.fact.split())
    if not fact or forbidden(candidate):
        return None
    category = candidate.category
    if category not in SENSITIVE_CATEGORIES and _IMMIGRATION.search(fact):
        category = "immigration"
    sensitive = candidate.sensitive or category in SENSITIVE_CATEGORIES
    if not sensitive:
        return Storable(
            fact, category, candidate.source, Sensitivity.NORMAL, FactStatus.ACTIVE
        )
    # C15: every sensitive fact waits for the user's OK; immigration always (C34).
    return Storable(
        fact,
        category,
        candidate.source,
        Sensitivity.SENSITIVE,
        FactStatus.PENDING_CONSENT,
    )


def normalized(fact: str) -> str:
    """The form two facts are compared in: case, spacing and punctuation ignored."""
    return " ".join(re.sub(r"[^\w\s]", " ", fact.casefold()).split())


def new_facts(facts: Iterable[Storable], known: Iterable[str]) -> list[Storable]:
    """`facts` minus any already known or repeated (supersede is post-MVP, C28)."""
    seen = {normalized(fact) for fact in known}
    fresh: list[Storable] = []
    for fact in facts:
        key = normalized(fact.fact)
        if key not in seen:
            seen.add(key)
            fresh.append(fact)
    return fresh
