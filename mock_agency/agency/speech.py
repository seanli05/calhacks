"""Turn speech-to-text transcripts into menu choices and topics.

Transcripts come from Cartesia Ink listening to our own phone agent's TTS, so
expect forms like "press two" or "two".
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


def asks_for_human(text: str) -> bool:
    return bool(_HUMAN_REQUEST.search(text.lower()))


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
