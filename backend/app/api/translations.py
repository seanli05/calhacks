"""Free text for the dashboard in the viewer's language, without waiting on a model.

The API polls every 1–3 s, so a lookup must be instant. The first time a string is
asked for in a language, `cached` returns None (the caller shows English) and starts
translating it in the background with the shared translator; a later poll finds it.
Translations live in memory for the life of the process; a failure waits
`RETRY_AFTER_S` before the string is tried again, so a down API isn't hit per poll.
"""

import asyncio
import logging
import time

from app.contracts.common import LanguageCode
from app.translation.translate import Translator, get_translator

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 4
MAX_ENTRIES = 5000
"""Far above a demo's strings; past it, new strings stay English."""
RETRY_AFTER_S = 60.0

type _Key = tuple[str, LanguageCode]

_done: dict[_Key, str] = {}
_failed_at: dict[_Key, float] = {}
_pending: set[_Key] = set()
_tasks: set[asyncio.Task[None]] = set()
_limit: asyncio.Semaphore | None = None


def cached(text_en: str, language: LanguageCode) -> str | None:
    """The translation if there is one yet. Otherwise None, and (from inside the
    event loop, with a translator) the translation starts in the background."""
    key = (text_en, language)
    if (found := _done.get(key)) is not None:
        return found
    _start(key)
    return None


def _start(key: _Key) -> None:
    if key in _pending or len(_done) >= MAX_ENTRIES:
        return
    failed = _failed_at.get(key)
    if failed is not None and time.monotonic() - failed < RETRY_AFTER_S:
        return
    translator = get_translator()
    if translator is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _pending.add(key)
    task = loop.create_task(_translate(translator, key))
    # The loop holds tasks weakly; keep a reference until each one finishes.
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _translate(translator: Translator, key: _Key) -> None:
    global _limit
    if _limit is None:
        _limit = asyncio.Semaphore(MAX_CONCURRENT)
    text_en, language = key
    try:
        async with _limit:
            translated = await translator.from_english(text_en, language)
    except Exception:
        # The translator returns None for API errors; anything else is a bug, but
        # it mustn't take the dashboard down: the string just stays English.
        logger.exception("dashboard translation failed language=%s", language)
        translated = None
    finally:
        _pending.discard(key)
    if translated:
        _done[key] = translated
        _failed_at.pop(key, None)
    else:
        _failed_at[key] = time.monotonic()


def clear() -> None:
    """Forget every translation (tests)."""
    _done.clear()
    _failed_at.clear()
    _pending.clear()
