"""The live feed: the user's events rendered in their language (C23, C27)."""

from datetime import datetime

from fastapi import APIRouter

from app.api import feed_templates
from app.api.case_views import fast_result_of
from app.api.common import LangQuery, localize, resolve_language
from app.api.models import FeedItem, Localized
from app.contracts import Event, EventType
from app.db import reads

router = APIRouter()

# These carry the deleted row's ID; they are the deletion, not a reference to it.
_DELETE_TYPES = {
    EventType.FACT_DELETED,
    EventType.DOCUMENT_DELETED,
    EventType.TRANSCRIPT_DELETED,
    EventType.USER_DELETED_ALL,
}


@router.get("/users/{user_id}/feed")
async def feed(
    user_id: str, since: datetime | None = None, lang: LangQuery = None
) -> list[FeedItem]:
    lang = await resolve_language(user_id, lang)
    events = await reads.list_events(user_id, since)
    refs = _References(user_id)
    issuers: dict[str, str | None] = {}
    items = []
    for event in events:
        values = _scalars(event.data)
        deleted_at = None
        if event.type not in _DELETE_TYPES:
            text, deleted_at = await refs.lookup(event)
            if text is not None:
                values["fact"] = text
        if "agency" not in values and event.case_id:
            if event.case_id not in issuers:
                issuers[event.case_id] = await _issuer(event.case_id)
            if issuers[event.case_id]:
                values["agency"] = issuers[event.case_id]
        items.append(
            FeedItem(
                id=event.event_id,
                at=event.created_at,
                type=event.type,
                case_id=event.case_id,
                call_id=event.call_id,
                text=_text(event, lang, values),
                deleted_at=deleted_at,
            )
        )
    return items


def _text(event: Event, lang: str, values: dict[str, str]) -> Localized:
    rendered = feed_templates.render(event.type, lang, values)
    if rendered is None:
        return localize(event.summary_en, lang)
    text, en = rendered
    return Localized(text=text, en=en)


def _scalars(data: dict) -> dict[str, str]:
    """Only plain values fill templates. `fact` is never taken from `data` (C27)."""
    return {
        key: str(value)
        for key, value in data.items()
        if key != "fact"
        and isinstance(value, str | int | float)
        and not isinstance(value, bool)
        and str(value).strip()
    }


async def _issuer(case_id: str) -> str | None:
    case = await reads.get_case(case_id)
    fast = fast_result_of(case) if case else None
    return fast.issuer if fast else None


class _References:
    """Looks up the fact or document an event points at, at render time (C27).
    Each table is read at most once per request, and only if an event needs it."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.facts: dict[str, str] | None = None
        self.documents: set[str] | None = None
        self.deleted: dict[str, datetime] | None = None
        self.deleted_all: datetime | None = None

    async def lookup(self, event: Event) -> tuple[str | None, datetime | None]:
        """`(fact text or None, deleted_at)` for the row the event refers to."""
        fact_id = event.data.get("fact_id")
        if isinstance(fact_id, str):
            if self.facts is None:
                rows = await reads.list_facts(self.user_id)
                self.facts = {row.id: row.fact for row in rows}
            if fact_id in self.facts:
                return self.facts[fact_id], None
            return None, await self._deleted_at(fact_id)
        document_id = event.data.get("document_id")
        if isinstance(document_id, str):
            if self.documents is None:
                rows = await reads.list_documents(self.user_id)
                self.documents = {row.id for row in rows}
            if document_id not in self.documents:
                return None, await self._deleted_at(document_id)
        return None, None

    async def _deleted_at(self, row_id: str) -> datetime | None:
        """When the row's delete event happened; "delete everything" removes rows
        without one per row, so fall back to that."""
        if self.deleted is None:
            self.deleted = {}
            for event in await reads.list_events(self.user_id):
                if event.type == EventType.USER_DELETED_ALL:
                    self.deleted_all = event.created_at
                elif event.type in _DELETE_TYPES:
                    for key in ("fact_id", "document_id"):
                        if isinstance(event.data.get(key), str):
                            self.deleted[event.data[key]] = event.created_at
        return self.deleted.get(row_id, self.deleted_all)
