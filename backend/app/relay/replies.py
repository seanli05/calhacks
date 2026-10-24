"""Parse numbered WhatsApp replies ("1", "2.", " 2 "). Options are 1-based (C5)."""

import re

_CHOICE = re.compile(r"^(\d{1,2})[.)]?$")
# Yes/no words accepted for a two-option "1 yes / 2 no" question, in every supported
# language: a relative may answer in English for the parent.
_YES = {"si", "sí", "yes"}
_NO = {"no"}
_TRIM = " .!¡?¿"


def parse_choice(text: str, n_options: int) -> int | None:
    """A numbered reply within 1..n_options, else None."""
    match = _CHOICE.match(text.strip())
    if match is None:
        return None
    choice = int(match.group(1))
    return choice if 1 <= choice <= n_options else None


def parse_yes_no(text: str) -> int | None:
    """1 for "1" or a yes word, 2 for "2" or a no word, else None."""
    word = text.strip().strip(_TRIM).strip().lower()
    if word in _YES:
        return 1
    if word in _NO:
        return 2
    return parse_choice(text, 2)
