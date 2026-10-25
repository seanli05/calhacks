"""The live call view: the translation book, and the bridged call as a stream.

`GET /api/calls/{call_id}/live?lang=xx` is server-sent events. It follows the call's
transcript (written by the phone agent) from the moment a person answered, so the
view is up while the user's phone rings to join: each new line is sent as heard, then its translation streams in token by token
from the model, grounded in the glossary like every other translation. Rule-based
tips (`live_tips.py`) follow the lines that prompt them. The stream ends when the
call does.

A reconnect replays the call from the start; finished translations are kept in
memory, so the replay costs no model calls.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timedelta
from functools import lru_cache

import anthropic
from anthropic import AsyncAnthropic
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.api import live_tips
from app.api.common import (
    DEFAULT_LANGUAGE,
    LangQuery,
    found,
    localize,
    resolve_language,
)
from app.api.live_prompts import LIVE_LINE_SYSTEM, SPEAKERS
from app.api.models import (
    GlossaryEntry,
    LiveCallEvent,
    LiveDelta,
    LiveLineDone,
    LiveLineHeard,
    LiveTip,
    LiveTipShown,
    LiveTipUsed,
    Localized,
    TranscriptLine,
)
from app.contracts import CallState, EventType, LanguageCode
from app.db import reads, tables
from app.settings import get_settings
from app.translation.glossary import Glossary
from app.translation.translate import LANGUAGE_NAMES, REGISTERS

logger = logging.getLogger(__name__)

router = APIRouter()

POLL_S = 0.5
HEARTBEAT_S = 15.0
MAX_STREAM_S = 3 * 60 * 60
STREAM_TIMEOUT_S = 15.0
ANSWER_SKEW = timedelta(seconds=1)
"""Lines a moment before the answer event still count: clocks differ a little."""
MAX_CACHED = 5000

_DEFAULT_REGISTER = "Write simple, polite language. Short sentences."

_translated: dict[tuple[str, LanguageCode], str] = {}


@router.get("/glossary")
async def glossary(lang: LangQuery = None) -> list[GlossaryEntry]:
    rows = await reads.get_glossary(lang or DEFAULT_LANGUAGE)
    return [
        GlossaryEntry(
            term=row.term,
            translation=row.translation,
            trust_level=row.trust_level,
            source_url=row.source_url,
        )
        for row in rows
    ]


@router.get("/calls/{call_id}/live")
async def live_call(
    call_id: str, request: Request, lang: LangQuery = None
) -> StreamingResponse:
    call = found(await reads.get_call(call_id), "call")
    case = found(await reads.get_case(call.case_id), "case")
    lang = await resolve_language(case.user_id, lang)
    questions = _questions(await reads.get_brief(call.brief_id))
    events = follow(call.id, case.user_id, lang, questions, request.is_disconnected)
    return StreamingResponse(
        _sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _sse(events: AsyncIterator[LiveCallEvent | None]) -> AsyncIterator[str]:
    async for event in events:
        yield ": ping\n\n" if event is None else f"data: {event.model_dump_json()}\n\n"


async def follow(
    call_id: str,
    user_id: str,
    lang: LanguageCode,
    questions: list[str],
    disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[LiveCallEvent | None]:
    """The call's events from a person answering until it ends; None is a heartbeat."""
    tips = live_tips.Tips(call_id, questions)
    answered_at: datetime | None = None
    sent = 0
    started = last_sent = time.monotonic()
    while time.monotonic() - started < MAX_STREAM_S and not await disconnected():
        # Read the state first: a line saved during wrap-up is still sent below.
        call = await reads.get_call(call_id)
        over = call is None or call.state == CallState.ENDED
        if answered_at is None:
            answered_at = await _answered_at(user_id, call_id)
        lines = _since(await reads.get_transcript(call_id), answered_at)
        for index in range(sent, len(lines)):
            async for event in _line_events(call_id, index, lines[index], lang, tips):
                yield event
            last_sent = time.monotonic()
        sent = max(sent, len(lines))
        if over:
            return
        if time.monotonic() - last_sent > HEARTBEAT_S:
            yield None
            last_sent = time.monotonic()
        await asyncio.sleep(POLL_S)


async def _line_events(
    call_id: str,
    index: int,
    line: TranscriptLine,
    lang: LanguageCode,
    tips: live_tips.Tips,
) -> AsyncIterator[LiveCallEvent]:
    line_id = f"{call_id}_line{index}"
    yield LiveLineHeard(id=line_id, at=line.at, speaker=line.speaker, en=line.text)
    if line.speaker == "user":
        for tip_id in tips.after_user(line.text):
            yield LiveTipUsed(id=tip_id)
    async for piece in _translate(line_id, line, lang):
        yield LiveDelta(id=line_id, text=piece)
    yield LiveLineDone(id=line_id)
    if line.speaker == "agency":
        for tip in tips.after_agency(line.text, line_id):
            yield LiveTipShown(tip=_live_tip(tip, lang))


async def _translate(
    line_id: str, line: TranscriptLine, lang: LanguageCode
) -> AsyncIterator[str]:
    """The line's translation in pieces. English, or no way to translate, sends the
    line as heard in one piece; so does a failure before the first token."""
    key = (line_id, lang)
    if lang == "en":
        yield line.text
        return
    if (done := _translated.get(key)) is not None:
        yield done
        return
    streamer = get_streamer()
    if streamer is None:
        yield line.text
        return
    parts: list[str] = []
    try:
        async with asyncio.timeout(STREAM_TIMEOUT_S):
            async for piece in streamer.stream(line.text, line.speaker, lang):
                parts.append(piece)
                yield piece
    except (anthropic.APIError, TimeoutError) as exc:
        logger.warning(
            "live translation failed line=%s language=%s: %s",
            line_id,
            lang,
            type(exc).__name__,
        )
    if not parts:
        yield line.text
    elif len(_translated) < MAX_CACHED:
        _translated[key] = "".join(parts)


def _live_tip(tip: live_tips.Tip, lang: LanguageCode) -> LiveTip:
    if tip.say_en is None:
        en = live_tips.text("yourself", "en")
        meaning = (
            Localized(text=live_tips.text("yourself", lang), en=en)
            if lang in live_tips.TEXTS
            else localize(en, lang)
        )
    else:
        meaning = localize(tip.say_en, lang)
    return LiveTip(
        id=tip.id,
        kind=tip.kind,
        line_id=tip.line_id,
        say_en=tip.say_en,
        meaning=meaning,
    )


async def _answered_at(user_id: str, call_id: str) -> datetime | None:
    """The last time a person answered: a false alarm goes back to hold, and the
    next answer starts the view again."""
    answered = [
        e.created_at
        for e in await reads.list_events(user_id)
        if e.type == EventType.CALL_HUMAN_DETECTED and e.call_id == call_id
    ]
    return answered[-1] if answered else None


def _since(
    row: tables.Transcript | None, answered_at: datetime | None
) -> list[TranscriptLine]:
    """Every line since a person answered, the agent's included (it holds the line
    while the user's phone rings); none before."""
    if row is None or answered_at is None:
        return []
    lines = []
    for raw in row.lines:
        try:
            line = TranscriptLine.model_validate(raw)
        except ValidationError as exc:
            logger.warning("transcript %s: skipping invalid line (%s)", row.id, exc)
            continue
        if line.at >= answered_at - ANSWER_SKEW:
            lines.append(line)
    return lines


def _questions(row: tables.CaseBrief | None) -> list[str]:
    """The brief's shape is still provisional (contracts/brief.py): read defensively."""
    questions = row.brief.get("questions_to_ask") if row else None
    return (
        [q for q in questions if isinstance(q, str) and q]
        if isinstance(questions, list)
        else []
    )


class LineStreamer:
    """Streams one call line's translation from the model, glossary-grounded."""

    def __init__(self, client: AsyncAnthropic, model: str, glossary: Glossary) -> None:
        self._client = client
        self._model = model
        self._glossary = glossary

    async def stream(
        self, text_en: str, speaker: str, language: LanguageCode
    ) -> AsyncIterator[str]:
        system = LIVE_LINE_SYSTEM.format(
            language=LANGUAGE_NAMES.get(
                language, f"the language with ISO 639-1 code {language}"
            ),
            register=REGISTERS.get(language, _DEFAULT_REGISTER),
            speaker=SPEAKERS.get(speaker, speaker),
        )
        system += await self._glossary.section(
            text_en, language, source_is_english=True
        )
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": text_en}],
            timeout=STREAM_TIMEOUT_S,
        ) as stream:
            async for piece in stream.text_stream:
                yield piece


@lru_cache
def get_streamer() -> LineStreamer | None:
    """The live translator, or None without an Anthropic key."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    return LineStreamer(
        AsyncAnthropic(api_key=settings.anthropic_api_key),
        settings.model_fast,
        Glossary(),
    )
