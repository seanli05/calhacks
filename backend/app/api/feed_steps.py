"""The step logs behind a task, as short rows for the case view's live activity.

The research agent logs every lookup of its check (`research.search`, `.fetch`,
`.check`) and the phone agent every menu prompt it hears (`call.menu_heard`). The
feed hides them by default (`feed_templates.HIDDEN`); `?steps=true` sends them with a
`step`: what the agent did (localized), what it did it to (`detail`, English as
logged: a search query, a page, a check), and how it came out.

Only fixed text and the logged query, page and check names reach the screen;
`evidence` and model notes never do.
"""

from typing import Any
from urllib.parse import urlsplit

from app.api.common import localize
from app.api.models import FeedStep, Localized
from app.contracts import Event

STEP_TYPES = frozenset(
    {"research.search", "research.fetch", "research.check", "call.menu_heard"}
)

MAX_DETAIL = 90

Pair = tuple[str, str]
"""(English, Spanish). Other languages go through the translation cache, like the
feed templates."""

SEARCHING: Pair = ("Searching", "Buscando")
READING: Pair = ("Reading", "Leyendo")
CHECKING: Pair = ("Checking", "Comprobando")
LISTENING: Pair = ("Listening", "Escuchando")

FAILED: Pair = ("failed", "falló")
BLOCKED: Pair = ("blocked", "bloqueada")
READ: Pair = ("read", "leída")

STATES: dict[str, tuple[Pair, bool | None]] = {
    "match": (("matches", "coincide"), True),
    "not_found": (("not found", "no aparece"), None),
    "conflict": (("doesn't match", "no coincide"), False),
    "uncertain": (("unclear", "no está claro"), None),
}
VERDICTS: dict[str, tuple[Pair, bool | None]] = {
    "verified": (("real", "real"), True),
    "suspicious": (("suspicious", "sospechosa"), False),
    "unknown": (("unconfirmed", "sin confirmar"), None),
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
}
PHASES: dict[str, str] = {
    "menu": "phone menu",
    "hold": "hold music",
    "human": "a person's voice",
    "unclear": "the line",
}
ACTIONS: dict[str, Pair] = {
    "press": ("press a key", "marcar"),
    "say": ("answer", "responder"),
    "wait": ("wait", "esperar"),
    "ask_user": ("ask you", "preguntarte"),
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
        )
        ok = flags == 0
    elif name == "verdict" and data.get("status") in VERDICTS:
        result, ok = VERDICTS[data["status"]]
    elif name == "discovery":
        result, ok = ("stopped", "se detuvo"), False
    elif name in {"verify_cache", "seed_snapshot"}:
        used = data.get("ok", True) is not False
        result, ok = (("used", "usada"), True) if used else (("none", "no hay"), None)
    elif name == "submission":
        result, ok = ("received", "recibido"), None
    elif data.get("state") in STATES:
        result, ok = STATES[data["state"]]
    return _step(CHECKING, detail, result, ok, lang)


def _menu_heard(data: dict[str, Any], lang: str) -> FeedStep:
    detail = PHASES.get(_text(data.get("phase")) or "", "the line")
    action = ACTIONS.get(_text(data.get("action")) or "")
    return _step(LISTENING, detail, action, None, lang)


def _step(
    action: Pair, detail: str | None, result: Pair | None, ok: bool | None, lang: str
) -> FeedStep:
    return FeedStep(
        action=_localized(action, lang),
        detail=detail[:MAX_DETAIL] if detail else None,
        result=_localized(result, lang) if result else None,
        ok=ok,
    )


def _localized(pair: Pair, lang: str) -> Localized:
    en, es = pair
    if lang == "es":
        return Localized(text=es, en=en)
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
