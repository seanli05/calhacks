"""Turn speech-to-text transcripts into menu choices, receipt numbers, and topics.

Transcripts come from Cartesia Ink listening to our own phone agent's TTS, so
expect forms like "Z L A 2 6 9 0 0 1 2 3 4 5", "zee el ay two six nine...",
"ZLA-269-001-2345", or "press two".
"""

import re
from enum import StrEnum

_NUMBER_WORDS = {
    "zero": "0",
    "oh": "0",
    "one": "1",
    "two": "2",
    "to": "2",
    "too": "2",
    "three": "3",
    "four": "4",
    "for": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}

# Letter names STT tends to spell out instead of writing the letter.
_LETTER_WORDS = {
    "zee": "Z",
    "zed": "Z",
    "el": "L",
    "ell": "L",
    "ay": "A",
    "eh": "A",
    "bee": "B",
    "see": "C",
    "sea": "C",
    "dee": "D",
    "ee": "E",
    "eff": "F",
    "gee": "G",
    "jay": "J",
    "kay": "K",
    "em": "M",
    "en": "N",
    "pee": "P",
    "queue": "Q",
    "are": "R",
    "ess": "S",
    "tee": "T",
    "you": "U",
    "vee": "V",
    "ex": "X",
    "why": "Y",
}

_YES = {"yes", "yeah", "yep", "correct", "right", "affirmative", "sure", "yup"}
_NO = {"no", "nope", "incorrect", "wrong", "negative"}

_HUMAN_REQUEST = re.compile(
    r"\b(representative|operator|agent|officer|human|real person|someone)\b"
)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def spoken_digit(text: str) -> str | None:
    """Return the single menu digit in an utterance like "two" or "press 2".

    Returns None when there's no digit or more than one, so "one or two" doesn't
    pick an option by accident.
    """
    digits = []
    for word in _words(text):
        if word.isdigit():
            digits.extend(word)
        elif word in _NUMBER_WORDS and word not in {"to", "too", "for"}:
            digits.append(_NUMBER_WORDS[word])
    return digits[0] if len(digits) == 1 else None


def yes_or_no(text: str) -> bool | None:
    words = set(_words(text))
    if words & _YES and not words & _NO:
        return True
    if words & _NO and not words & _YES:
        return False
    return None


def asks_for_human(text: str) -> bool:
    return bool(_HUMAN_REQUEST.search(text.lower()))


def normalize_receipt(text: str) -> str:
    """Collapse a spoken receipt number into uppercase letters and digits.

    "Z L A two six nine..." -> "ZLA269...". Ordinary words are dropped, so a
    phrase like "my receipt number is" doesn't leak letters into the result.
    """
    out = []
    for word in _words(text):
        if word.isdigit():
            out.append(word)
        elif word in _NUMBER_WORDS:
            out.append(_NUMBER_WORDS[word])
        elif word in _LETTER_WORDS:
            out.append(_LETTER_WORDS[word])
        elif len(word) == 1 or re.fullmatch(r"[a-z]{3}\d+", word):
            out.append(word.upper())
    return "".join(out)


def extract_receipt(text: str) -> str | None:
    """Find a receipt number (3 letters + 10 digits) in a transcript.

    Falls back to a bare 10-digit run, since STT often garbles the letters but
    gets the digits right. The caller matches on digits.
    """
    normalized = normalize_receipt(text)
    match = re.search(r"[A-Z]{3}\d{10}", normalized)
    if match:
        return match.group(0)
    digits = re.search(r"\d{10}", normalized)
    return digits.group(0) if digits else None


def spell_out(value: str) -> str:
    """Space characters out so TTS reads "Z L A 2 6 9", not "zla two hundred"."""
    return " ".join(value)


class Topic(StrEnum):
    RESCHEDULE = "reschedule"
    INTERPRETER = "interpreter"
    DATE_AND_LOCATION = "date_and_location"
    DOCUMENTS = "documents"
    ATTORNEY = "attorney"
    OTHER = "other"


# Checked in order; the first topic with a matching keyword wins.
_TOPIC_KEYWORDS: list[tuple[Topic, tuple[str, ...]]] = [
    (
        Topic.RESCHEDULE,
        (
            "reschedul",
            "new date",
            "change the date",
            "change my date",
            "another date",
            "postpone",
            "can't make",
            "cannot make",
            "can't attend",
            "cannot attend",
            "move my interview",
            "move the interview",
        ),
    ),
    (Topic.INTERPRETER, ("interpret", "translat", "language", "spanish", "english")),
    (Topic.ATTORNEY, ("attorney", "lawyer", "accredited representative", "remote")),
    (Topic.DOCUMENTS, ("bring", "document", "identification", "paper", "evidence")),
    (
        Topic.DATE_AND_LOCATION,
        ("where", "location", "address", "what time", "when", "confirm", "date"),
    ),
]


def classify_reason(text: str) -> Topic | None:
    """Map a free-form reason for calling to a topic, or None if nothing matches."""
    lowered = text.lower().replace("’", "'")
    for topic, keywords in _TOPIC_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return topic
    return None
