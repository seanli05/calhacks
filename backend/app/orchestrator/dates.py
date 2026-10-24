"""Dates and times written the way the user reads them (Goal 5.4).

The interview date is the one fact a translation must never garble, so messages
format it here, in code, and put it in a relay template, rather than leave it to a
model. A language without names here gets ISO dates (no wrong month names).
"""

import datetime as dt

from app.contracts.common import LanguageCode

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
}


def format_date(date: dt.date, language: LanguageCode) -> str:
    """E.g. "Wednesday, November 18, 2026" or "miércoles 18 de noviembre de 2026"."""
    if language not in _MONTHS:
        return date.isoformat()
    weekday = _WEEKDAYS[language][date.weekday()]
    month = _MONTHS[language][date.month - 1]
    if language == "es":
        return f"{weekday} {date.day} de {month} de {date.year}"
    return f"{weekday}, {month} {date.day}, {date.year}"


def format_time(hh_mm: str, language: LanguageCode) -> str:
    """E.g. "08:30" is "8:30 AM" or "8:30 a. m."; other languages keep 24-hour time."""
    hour, minute = (int(part) for part in hh_mm.split(":"))
    if language not in ("en", "es"):
        return f"{hour:02d}:{minute:02d}"
    suffix = ("AM", "PM") if language == "en" else ("a. m.", "p. m.")
    twelve = hour % 12 or 12
    return f"{twelve}:{minute:02d} {suffix[hour >= 12]}"
