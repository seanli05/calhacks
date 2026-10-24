"""Helpers every route module shares: `?lang=`, localizing, 404s."""

from typing import Annotated

from fastapi import HTTPException, Query

from app.api.models import Localized
from app.contracts.common import UserId
from app.db import reads

DEFAULT_LANGUAGE = "en"

LangQuery = Annotated[str | None, Query(pattern=r"^[a-z]{2}$")]


def found[Row](row: Row | None, what: str) -> Row:
    if row is None:
        raise HTTPException(status_code=404, detail=f"{what} not found")
    return row


async def resolve_language(user_id: UserId, lang: str | None) -> str:
    """The requested language, else the user's, else English."""
    if lang:
        return lang
    user = await reads.get_user(user_id)
    return (user.language if user else None) or DEFAULT_LANGUAGE


def localize(en: str, lang: str) -> Localized:
    """Free text (explanations, checklist items, report steps) in `lang`. The
    translation module doesn't exist yet, so `text` falls back to English."""
    return Localized(text=en, en=en)


def mask(value: str) -> str:
    """Identifiers never reach the browser in full: `ZLA2690012345` → `•••• 2345`."""
    return "•••• " + value[-4:]
