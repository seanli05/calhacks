"""The live feed: the user's events rendered in their language (C23, C27)."""

import asyncio
from datetime import datetime

from fastapi import APIRouter

from app.api import feed_steps, feed_templates
from app.api.case_views import fast_result_of
from app.api.common import LangQuery, localize, resolve_language
from app.api.models import FeedItem, Localized
from app.contracts import Event, EventType
from app.db import reads, tables

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
    user_id: str,
    since: datetime | None = None,
    lang: LangQuery = None,
    steps: bool = False,
) -> list[FeedItem]:
    """`steps` adds the step logs behind each task (`feed_steps.py`), for the case
    view's live activity."""
    lang, events = await asyncio.gather(
        resolve_language(user_id, lang), reads.list_events(user_id, since)
    )
    hidden = (
        feed_templates.HIDDEN - feed_steps.STEP_TYPES
        if steps
        else feed_templates.HIDDEN
    )
    events = [e for e in events if e.type not in hidden]
    if not events:
        return []
    refs = _References()
    cases, _ = await asyncio.gather(
        reads.list_cases(user_id), refs.load(user_id, events)
    )
    issuers = {case.id: _issuer(case) for case in cases}
    return [_item(event, lang, refs, issuers) for event in events]


def _item(
    event: Event, lang: str, refs: "_References", issuers: dict[str, str | None]
) -> FeedItem:
    values = _scalars(event.data)
    if "agency" not in values and issuers.get(event.case_id or ""):
        values["agency"] = issuers[event.case_id]
    values_en = dict(values)
    deleted_at = None
    if event.type not in _DELETE_TYPES:
        fact, deleted_at = refs.lookup(event)
        if fact is not None:
            values_en["fact"] = fact
            values["fact"] = localize(fact, lang).text
    rendered = feed_templates.render(event.type, lang, values, values_en)
    step = feed_steps.step(event, lang)
    if rendered:
        text = Localized(text=rendered[0], en=rendered[1])
    elif step:
        # The row shows `step`; translating every lookup's summary would be waste.
        text = Localized(text=event.summary_en, en=event.summary_en)
    else:
        text = localize(event.summary_en, lang)
    return FeedItem(
        id=event.event_id,
        at=event.created_at,
        type=event.type,
        case_id=event.case_id,
        call_id=event.call_id,
        job_id=event.job_id,
        text=text,
        deleted_at=deleted_at,
        step=step,
    )


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


def _issuer(case: tables.Case) -> str | None:
    fast = fast_result_of(case)
    return fast.issuer if fast else None


class _References:
    """The facts and documents events point at, looked up at render time (C27).
    `load` reads only the tables the events need, all at once."""

    def __init__(self) -> None:
        self.facts: dict[str, str] = {}
        self.documents: set[str] = set()
        self.deleted: dict[str, datetime] = {}
        self.deleted_all: datetime | None = None

    async def load(self, user_id: str, events: list[Event]) -> None:
        referring = [e for e in events if e.type not in _DELETE_TYPES]
        need_facts = any(isinstance(e.data.get("fact_id"), str) for e in referring)
        need_docs = any(isinstance(e.data.get("document_id"), str) for e in referring)
        if not (need_facts or need_docs):
            return
        facts, documents, history = await asyncio.gather(
            reads.list_facts(user_id) if need_facts else _nothing(),
            reads.list_documents(user_id) if need_docs else _nothing(),
            # Delete events may predate `since`, so read the whole history.
            reads.list_events(user_id),
        )
        self.facts = {row.id: row.fact for row in facts}
        self.documents = {row.id for row in documents}
        for event in history:
            if event.type == EventType.USER_DELETED_ALL:
                self.deleted_all = event.created_at
            elif event.type in _DELETE_TYPES:
                for key in ("fact_id", "document_id"):
                    if isinstance(event.data.get(key), str):
                        self.deleted[event.data[key]] = event.created_at

    def lookup(self, event: Event) -> tuple[str | None, datetime | None]:
        """`(fact text or None, deleted_at)` for the row the event refers to. "Delete
        everything" removes rows without a delete event per row, so a missing row
        with no delete event of its own takes that time."""
        fact_id = event.data.get("fact_id")
        if isinstance(fact_id, str):
            if fact_id in self.facts:
                return self.facts[fact_id], None
            return None, self.deleted.get(fact_id, self.deleted_all)
        document_id = event.data.get("document_id")
        if isinstance(document_id, str) and document_id not in self.documents:
            return None, self.deleted.get(document_id, self.deleted_all)
        return None, None


async def _nothing() -> list:
    return []
