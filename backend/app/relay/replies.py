"""Parse numbered WhatsApp replies ("1", "2.", " 2 ", "۱"). Options are 1-based (C5).

Dari keyboards type Persian digits (۱, ۲), and some type Arabic letter forms (ي, ك)
where Persian has ی, ک; both are read the same as the usual forms.
"""

import re

from app.translation.script import ascii_digits

_CHOICE = re.compile(r"^(\d{1,2})[.)]?$", re.ASCII)
# Yes/no words accepted for a two-option "1 yes / 2 no" question, in every supported
# language: a relative may answer in English for the parent. Dari: بلی is the Afghan
# yes (بله the Iranian one), آری/آره the plain one; نخیر the polite no, نی the
# spoken Afghan one.
_YES = {"si", "sí", "yes", "بلی", "بله", "آری", "آره", "اره"}
_NO = {"no", "نه", "نخیر", "نی"}
_TRIM = " .!¡?¿؟،"
_PERSIAN_LETTERS = str.maketrans(
    {"ي": "ی", "ى": "ی", "ك": "ک", "ـ": None, "\u200c": None}
)


def parse_choice(text: str, n_options: int) -> int | None:
    """A numbered reply within 1..n_options, else None."""
    match = _CHOICE.match(ascii_digits(text.strip()))
    if match is None:
        return None
    choice = int(match.group(1))
    return choice if 1 <= choice <= n_options else None


def parse_yes_no(text: str) -> int | None:
    """1 for "1" or a yes word, 2 for "2" or a no word, else None."""
    word = text.strip().strip(_TRIM).strip().lower().translate(_PERSIAN_LETTERS)
    if word in _YES:
        return 1
    if word in _NO:
        return 2
    return parse_choice(text, 2)
