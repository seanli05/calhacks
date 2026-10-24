"""Writing-script details at the edges (rule 6): digits and text direction.

Dari is written right to left with Persian digits (USCIS's Dari pages write
"۳۰ سپتمبر ۲۰۲۲", but keep form and phone numbers in Latin: "فورمهٔ I-131",
"800-375-5283"). Latin fragments inside right-to-left text need Unicode direction
isolates (FSI … PDI): without them a phone shows "I-797C" as "797C-I", and a line
that starts with "USCIS" is laid out left to right.

The number check (5.4) compares digit values, whatever script they're written in, so
"November 18" and "۱۸ نومبر" agree.
"""

import re
from collections import Counter

from app.contracts.common import LanguageCode

RTL_LANGUAGES: frozenset[LanguageCode] = frozenset({"fa", "ar", "ps", "ur", "he"})

FSI = "\u2068"
"""First strong isolate: the text up to PDI takes its own direction."""
PDI = "\u2069"

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_TO_ASCII = str.maketrans(_PERSIAN_DIGITS + _ARABIC_INDIC_DIGITS, "0123456789" * 2)
_LOCAL_DIGITS: dict[LanguageCode, dict[int, int]] = {
    "fa": str.maketrans("0123456789", _PERSIAN_DIGITS)
}

# A Latin word, number, form name, URL or phone number; spaces may join several,
# so "Notice of Action" stays in order. It ends on a letter, digit or "/", so a
# sentence's closing period stays outside the isolate.
_LATIN_TOKEN = r"[A-Za-z0-9](?:[A-Za-z0-9\-_.:/@?=&%#+~]*[A-Za-z0-9/])?"
_LATIN_RUN = re.compile(rf"{_LATIN_TOKEN}(?: +{_LATIN_TOKEN})*")
_ISOLATES = re.compile(f"[{FSI}{PDI}]")
# After ascii_digits: a thousands separator (",", Persian "٬") belongs to the number.
_NUMBER = re.compile(r"\d+(?:[,٬]\d{3})*", re.ASCII)


def ascii_digits(text: str) -> str:
    """Persian and Arabic-Indic digits as 0-9."""
    return text.translate(_TO_ASCII)


def local_digits(text: str, language: LanguageCode) -> str:
    """0-9 in the digits `language` writes numbers in (Persian for Dari)."""
    table = _LOCAL_DIGITS.get(language)
    return text.translate(table) if table else text


def for_display(text: str, language: LanguageCode) -> str:
    """`text` ready to show in `language`: in a right-to-left language, every Latin
    run (USCIS, I-797C, a link, a phone number) wrapped in a direction isolate.
    Safe to apply twice."""
    if language not in RTL_LANGUAGES:
        return text
    plain = _ISOLATES.sub("", text)
    return _LATIN_RUN.sub(lambda match: f"{FSI}{match.group(0)}{PDI}", plain)


def numbers_kept(source: str, translated: str) -> bool:
    """The same numbers on both sides, in any digits: every number in `source` is in
    `translated` with the same value (as often), and `translated` has no number the
    source doesn't, so no date, time or phone number was changed, dropped or made up
    (a year added to "Nov 18"). A number the source spells out in English ("ten
    days") may come back in digits."""
    source_numbers, translated_numbers = _numbers(source), _numbers(translated)
    if source_numbers - translated_numbers:
        return False
    allowed = set(source_numbers) | _spelled_out(source)
    return set(translated_numbers) <= allowed


_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen"
)
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety"
_NUMBER_WORDS = {word: value for value, word in enumerate(_ONES.split())} | {
    word: 10 * value for value, word in enumerate(_TENS.split(), start=2)
}


def _spelled_out(text: str) -> set[int]:
    words = re.findall(r"[a-z]+", text.lower())
    return {_NUMBER_WORDS[word] for word in words if word in _NUMBER_WORDS}


def _numbers(text: str) -> Counter[int]:
    return Counter(
        int(re.sub(r"[,٬]", "", number))
        for number in _NUMBER.findall(ascii_digits(text))
    )
