"""Dates and times written the way the user reads them (Goal 5.4).

The interview date is the one fact a translation must never garble, so messages
format it here, in code, and put it in a relay template, rather than leave it to a
model. A language without names here gets ISO dates (no wrong month names); every
language in `relay.templates.LANGUAGES` has names (a test checks), so an ISO date
never lands inside Dari text.

Dari: Gregorian dates day first, with Afghan month names and Persian digits, as
USCIS's Dari page writes them ("۳۰ سپتمبر ۲۰۲۲"); the month names are the ones
USCIS's Dari page and UNAMA's Dari reports use (فبروری and نومبر by the same pattern;
the Dari checker confirms). Times read "۸:۳۰ صبح", "۴:۳۰ بعد از ظهر" (Da Afghanistan
Bank) and "۸:۰۰ شب" (USCIS's Dari page).
"""

import datetime as dt

from app.contracts.common import LanguageCode
from app.translation.script import local_digits

_WEEKDAYS: dict[LanguageCode, tuple[str, ...]] = {
    "en": (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ),
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
    "fa": ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"),
}
_MONTHS: dict[LanguageCode, tuple[str, ...]] = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "es": (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ),
    "fa": (
        "جنوری",
        "فبروری",
        "مارچ",
        "اپریل",
        "می",
        "جون",
        "جولای",
        "اگست",
        "سپتمبر",
        "اکتوبر",
        "نومبر",
        "دسمبر",
    ),
}
# Dari times of day: before noon, afternoon, evening (from 18:00).
_FA_DAY_PARTS = ("صبح", "بعد از ظهر", "شب")


def format_date(date: dt.date, language: LanguageCode) -> str:
    """E.g. "Wednesday, November 18, 2026", "miércoles 18 de noviembre de 2026" or
    "چهارشنبه ۱۸ نومبر ۲۰۲۶"."""
    if language not in _MONTHS:
        return date.isoformat()
    weekday = _WEEKDAYS[language][date.weekday()]
    month = _MONTHS[language][date.month - 1]
    if language == "es":
        return f"{weekday} {date.day} de {month} de {date.year}"
    if language == "fa":
        return local_digits(f"{weekday} {date.day} {month} {date.year}", language)
    return f"{weekday}, {month} {date.day}, {date.year}"


def format_time(hh_mm: str, language: LanguageCode) -> str:
    """E.g. "08:30" is "8:30 AM", "8:30 a. m." or "۸:۳۰ صبح"; other languages keep
    24-hour time."""
    hour, minute = (int(part) for part in hh_mm.split(":"))
    twelve = hour % 12 or 12
    if language == "fa":
        part = _FA_DAY_PARTS[0 if hour < 12 else 1 if hour < 18 else 2]
        return local_digits(f"{twelve}:{minute:02d}", language) + f" {part}"
    if language not in ("en", "es"):
        return f"{hour:02d}:{minute:02d}"
    suffix = ("AM", "PM") if language == "en" else ("a. m.", "p. m.")
    return f"{twelve}:{minute:02d} {suffix[hour >= 12]}"
