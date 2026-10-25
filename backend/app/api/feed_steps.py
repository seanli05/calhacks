"""The step logs behind a task, as short rows for the case view's live activity.

The research agent logs every lookup of its check (`research.search`, `.fetch`,
`.check`) and the phone agent every menu prompt it hears (`call.menu_heard`). The
feed hides them by default (`feed_templates.HIDDEN`); `?steps=true` sends them with a
`step`: what the agent did (localized), what it did it to (`detail`, English as
logged: a search query, a page, a check), and how it came out.

Each step also carries `reason`, why it came out that way, in English. For research
it's fixed text picked by the check's name and outcome (and the scam rules' own
red-flag sentences, which the user is sent anyway); `evidence` and the model's notes
still never reach the screen. For the call it's the phone agent's stated reasons,
which its menu guard already checked. Every reason is masked again here for refs
and digit runs.
"""

import re
from typing import Any
from urllib.parse import urlsplit

from app.api.common import localize
from app.api.models import FeedStep, Localized
from app.contracts import Event
from app.translation.script import local_digits

STEP_TYPES = frozenset(
    {"research.search", "research.fetch", "research.check", "call.menu_heard"}
)

MAX_DETAIL = 90
MAX_REASON = 280

_DIGIT_RUN = re.compile(r"\d[\d\s-]{5,}\d")
_REF = re.compile(r"<ref:[^>]*>")

Pair = tuple[str, str, str]
"""(English, Spanish, Dari). Other languages go through the translation cache, like
the feed templates."""

SEARCHING: Pair = ("Searching", "Buscando", "جستجو")
READING: Pair = ("Reading", "Leyendo", "خواندن")
CHECKING: Pair = ("Checking", "Comprobando", "بررسی")
LISTENING: Pair = ("Listening", "Escuchando", "شنیدن")

FAILED: Pair = ("failed", "falló", "ناکام شد")
BLOCKED: Pair = ("blocked", "bloqueada", "باز نشد")
READ: Pair = ("read", "leída", "خوانده شد")

STATES: dict[str, tuple[Pair, bool | None]] = {
    "match": (("matches", "coincide", "مطابقت دارد"), True),
    "not_found": (("not found", "no aparece", "پیدا نشد"), None),
    "conflict": (("doesn't match", "no coincide", "مطابقت ندارد"), False),
    "uncertain": (("unclear", "no está claro", "واضح نیست"), None),
}
VERDICTS: dict[str, tuple[Pair, bool | None]] = {
    "verified": (("real", "real", "اصلی"), True),
    "suspicious": (("suspicious", "sospechosa", "مشکوک"), False),
    "unknown": (("unconfirmed", "sin confirmar", "تأیید نشده"), None),
}
CHECKS: dict[str, str] = {
    "scam_rules": "scam patterns",
    "url_domains": "web addresses on the letter",
    "case_number_format": "case number format",
    "form_id": "form type",
    "issuer": "who sent the letter",
    "return_address": "return address",
    "letter_phone": "phone on the letter vs. the official site",
    "verdict": "is the letter real?",
    "verify_cache": "saved official page",
    "seed_snapshot": "saved copy of the official site",
    "submission": "what the search found",
    "discovery": "web search",
    "letter_read": "what kind of letter",
    "private_values": "private details",
    "urgency": "how urgent",
    "asylum_gate": "is it about the asylum claim?",
    "quote_on_page": "quote on the source page",
    "question_loop": "web search",
}
PHASES: dict[str, str] = {
    "menu": "phone menu",
    "hold": "hold music",
    "human": "a person's voice",
    "unclear": "the line",
}
ACTIONS: dict[str, Pair] = {
    "press": ("press a key", "marcar", "فشار دادن دکمه"),
    "say": ("answer", "responder", "جواب دادن"),
    "wait": ("wait", "esperar", "انتظار"),
    "ask_user": ("ask you", "preguntarle", "پرسیدن از شما"),
}

LETTER_READ: dict[str, tuple[Pair, bool | None]] = {
    "ok": (("read", "leída", "خوانده شد"), True),
    "needs_better_image": (
        ("needs a better photo", "necesita otra foto", "عکس بهتر ضرورت است"),
        False,
    ),
    "needs_user_input": (
        ("needs your answer", "necesita su respuesta", "جواب شما ضرورت است"),
        None,
    ),
}
URGENCY: dict[str, Pair] = {
    "high": ("high", "alta", "زیاد"),
    "medium": ("medium", "media", "متوسط"),
    "low": ("low", "baja", "کم"),
}

NO_RED_FLAGS = (
    "No payment demands, threats, notario offers, or links outside official sites."
)
VERDICT_REASONS: dict[str, str] = {
    "verified": "The letter's details matched the issuer's official site.",
    "suspicious": "Red flags, or details that conflict with the official site.",
    "unknown": "Not enough could be confirmed against official sites, either way.",
}
PHONE_FOUND = "The official phone number was found there too."
DISCOVERY_STOPS: dict[str, str] = {
    "refusal": "The model declined to keep searching.",
    "max_tokens": "The search ran out of room before it finished.",
}
QUESTION_STOPS = DISCOVERY_STOPS
CACHE_REJECTED = "A saved copy from an earlier check failed the checks again; not used."
QUOTE_MISSING = "The quoted text wasn't on the page, so this source was dropped."
SIGNAL_REASONS: dict[tuple[str, str], str] = {
    ("url_domains", "match"): "Every web address on the letter is .gov, the issuer's "
    "own site, or linked from an official page.",
    ("url_domains", "conflict"): "A web address on the letter isn't official, or "
    "imitates an official one.",
    ("url_domains", "uncertain"): "A web address on the letter looks close to an "
    "official one.",
    ("url_domains", "not_found"): "The letter has no web address, or one that couldn't "
    "be tied to an official site.",
    ("case_number_format", "match"): "The case number has the letters and digits this "
    "kind of letter uses.",
    ("case_number_format", "uncertain"): "The case number didn't have the expected "
    "shape; it may have been misread.",
    ("case_number_format", "not_found"): "No case number format could be read from "
    "the letter.",
    ("form_id", "match"): "The form number is on an official page or the known form "
    "list.",
    ("form_id", "not_found"): "No form number on the letter could be confirmed.",
    ("issuer", "match"): "The sender was found on its official site or in a "
    "government registry.",
    ("issuer", "not_found"): "The sender couldn't be confirmed on an official site.",
    ("return_address", "match"): "The return address is on an official page.",
    ("return_address", "not_found"): "The return address wasn't found on an official "
    "page.",
    ("letter_phone", "match"): "The phone number on the letter is listed for the "
    "issuer on an official page.",
    ("letter_phone", "conflict"): "The phone number on the letter appears on a site "
    "that isn't the issuer's.",
    ("letter_phone", "not_found"): "The letter has no phone number, or one that wasn't "
    "found on an official page.",
}
FIXED_REASONS: dict[str, str] = {
    "submission": "What the search found is not trusted yet: the code checks it "
    "against the pages it actually read.",
    "verify_cache": "The live check couldn't finish, so a saved copy of the official "
    "page from an earlier check was used.",
    "seed_snapshot": "The official site couldn't be reached, so a saved copy of it "
    "was used.",
    "private_values": "Names, numbers and addresses are stored apart and replaced "
    "with placeholders before anything else sees the letter.",
    "asylum_gate": "Questions about the asylum claim itself are never researched.",
    "quote_on_page": "The quoted text was found on the official page.",
}


def step(event: Event, lang: str) -> FeedStep | None:
    """The row for a step event, or None for any other event."""
    if event.type not in STEP_TYPES:
        return None
    data = event.data
    if event.type == "research.search":
        if "error" in data:
            return _step(SEARCHING, _text(data["error"]), FAILED, False, lang)
        return _step(SEARCHING, _quoted(data.get("query")), None, None, lang)
    if event.type == "research.fetch":
        page = _page(data.get("final_url") or data.get("url"))
        if "refused" in data:
            return _step(READING, page, BLOCKED, False, lang)
        status = data.get("status")
        if "error" in data or (isinstance(status, int) and status >= 400):
            return _step(READING, page, FAILED, False, lang)
        return _step(READING, page, READ, True, lang)
    if event.type == "research.check":
        return _check(data, lang)
    return _menu_heard(data, lang)


def _check(data: dict[str, Any], lang: str) -> FeedStep:
    name = _text(data.get("check")) or ""
    detail = CHECKS.get(name) or name.replace("_", " ") or None
    result: Pair | None = None
    ok: bool | None = None
    if name == "scam_rules" and isinstance(data.get("red_flags"), list):
        flags = len(data["red_flags"])
        result = (
            f"{flags} red flag{'' if flags == 1 else 's'}",
            f"{flags} alerta{'' if flags == 1 else 's'}",
            f"{local_digits(str(flags), 'fa')} نشانهٔ خطر",
        )
        ok = flags == 0
    elif name == "verdict" and data.get("status") in VERDICTS:
        result, ok = VERDICTS[data["status"]]
    elif name == "discovery":
        result, ok = ("stopped", "se detuvo", "متوقف شد"), False
    elif name in {"verify_cache", "seed_snapshot"}:
        used = data.get("ok", True) is not False
        result, ok = (
            (("used", "usada", "استفاده شد"), True)
            if used
            else (("none", "no hay", "نیست"), None)
        )
    elif name == "submission":
        result, ok = ("received", "recibido", "رسید"), None
    elif name == "letter_read" and data.get("status") in LETTER_READ:
        result, ok = LETTER_READ[data["status"]]
    elif name == "private_values" and isinstance(data.get("count"), int):
        count = data["count"]
        fa_count = local_digits(str(count), "fa")
        result = (f"{count} set aside", f"{count} apartados", f"{fa_count} جدا شد")
        ok = None
    elif name == "urgency" and data.get("urgency") in URGENCY:
        result, ok = URGENCY[data["urgency"]], None
    elif name == "asylum_gate":
        result, ok = ("declined", "no se investiga", "جستجو نمی‌شود"), None
    elif name == "quote_on_page" and isinstance(data.get("passed"), bool):
        passed = data["passed"]
        result = (
            ("found", "encontrada", "پیدا شد")
            if passed
            else ("not found", "no aparece", "پیدا نشد")
        )
        ok = passed
    elif name == "question_loop":
        result, ok = ("stopped", "se detuvo", "متوقف شد"), False
    elif data.get("state") in STATES:
        result, ok = STATES[data["state"]]
    return _step(CHECKING, detail, result, ok, lang, _check_reason(name, data))


def _check_reason(name: str, data: dict[str, Any]) -> str | None:
    """Why the check came out as it did: its own notes, or fixed text."""
    if name == "scam_rules" and isinstance(data.get("red_flags"), list):
        flags = [f for f in data["red_flags"] if isinstance(f, str)]
        return " ".join(flags) or NO_RED_FLAGS
    if name == "verdict":
        reason = VERDICT_REASONS.get(_text(data.get("status")) or "")
        if reason and data.get("official_phone_found") is True:
            reason += " " + PHONE_FOUND
        return reason
    if name == "discovery":
        return DISCOVERY_STOPS.get(_text(data.get("stop_reason")) or "")
    if name == "question_loop":
        return QUESTION_STOPS.get(_text(data.get("stop_reason")) or "")
    if name == "letter_read":
        doc_type = _text(data.get("doc_type"))
        return f"Read as: {doc_type.replace('_', ' ')}." if doc_type else None
    if name == "urgency" and isinstance(data.get("dates"), int):
        dates = data["dates"]
        return f"Based on {dates} date{'' if dates == 1 else 's'} on the letter."
    if name in FIXED_REASONS:
        if name == "verify_cache" and data.get("ok") is False:
            return CACHE_REJECTED
        if name == "quote_on_page" and data.get("passed") is False:
            return QUOTE_MISSING
        return FIXED_REASONS[name]
    return SIGNAL_REASONS.get((name, _text(data.get("state")) or ""))


def _menu_heard(data: dict[str, Any], lang: str) -> FeedStep:
    detail = PHASES.get(_text(data.get("phase")) or "", "the line")
    action = ACTIONS.get(_text(data.get("action")) or "")
    reasons = [_text(data.get("reading_reason_en")), _text(data.get("reason_en"))]
    reason = " ".join(r if r.endswith(".") else r + "." for r in reasons if r)
    return _step(LISTENING, detail, action, None, lang, reason or None)


def _step(
    action: Pair,
    detail: str | None,
    result: Pair | None,
    ok: bool | None,
    lang: str,
    reason: str | None = None,
) -> FeedStep:
    return FeedStep(
        action=_localized(action, lang),
        detail=detail[:MAX_DETAIL] if detail else None,
        result=_localized(result, lang) if result else None,
        ok=ok,
        reason=_masked(reason),
    )


def _masked(reason: str | None) -> str | None:
    """A second check at the edge: no refs, no runs of digits, a bounded length."""
    if not reason:
        return None
    reason = _DIGIT_RUN.sub("[number]", _REF.sub("[hidden]", reason))
    if len(reason) > MAX_REASON:
        reason = reason[: MAX_REASON - 1].rstrip() + "…"
    return reason


def _localized(pair: Pair, lang: str) -> Localized:
    en, es, fa = pair
    if lang == "es":
        return Localized(text=es, en=en)
    if lang == "fa":
        return Localized(text=fa, en=en)
    return localize(en, lang)


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _quoted(value: Any) -> str | None:
    text = _text(value)
    return f'"{text}"' if text else None


def _page(value: Any) -> str | None:
    """`uscis.gov/contactcenter` for `https://www.uscis.gov/contactcenter/`."""
    url = _text(value)
    if not url:
        return None
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    return (host + parts.path.rstrip("/")) or url
