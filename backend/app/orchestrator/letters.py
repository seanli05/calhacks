"""Starting research on a letter (Plan.md → H1, C20) and noticing when the fast pass
finishes (the reaction is letter_result.py).

The orchestrator mints the `case_id` and queues `research_fast`; research creates the
`cases` row only when its fast pass finishes, and not at all for an unreadable photo.
Until then the only record that a letter is being read is here, in memory, so "same
letter or new?" can be asked from the first photo on (whatsapp-pipe.md, concern 1).
A restart forgets letters still being read: a photo sent then becomes a new letter.
"""

import logging
from dataclasses import dataclass

from app.contracts import Component, JobStatus, ResearchFastJob
from app.contracts.common import CaseId, DocumentId, JobId, UserId
from app.db import jobs, reads, tables
from app.db.ids import new_id
from app.orchestrator.job_watch import JobWatcher
from app.orchestrator.letter_result import LetterResults
from app.relay.outbound import send_template
from app.relay.whatsapp import WhatsApp, WhatsAppSendError

logger = logging.getLogger(__name__)

# Plan.md → Failure rules: past this, say it's taking longer and keep waiting.
FAST_SLOW_AFTER_S = 45.0


@dataclass(frozen=True)
class _Letter:
    document_id: DocumentId
    case_id: CaseId


class Letters:
    def __init__(
        self,
        whatsapp: WhatsApp,
        watcher: JobWatcher,
        results: LetterResults,
        slow_after_s: float = FAST_SLOW_AFTER_S,
    ) -> None:
        self._whatsapp = whatsapp
        self._watcher = watcher
        self._results = results
        self._slow_after_s = slow_after_s
        # The letter each user is waiting on a fast pass for.
        self._reading: dict[UserId, _Letter] = {}
        # The newest fast job per case; an older one's result is stale.
        self._latest_fast: dict[CaseId, JobId] = {}

    async def start(self, user_id: UserId, document_id: DocumentId) -> CaseId:
        """A new letter: mint its case and queue the fast pass."""
        user = await reads.get_user(user_id)
        if user is None or user.language is None:
            # The pipe holds photos until the language is picked, so this is a bug.
            raise ValueError(f"user {user_id} has no language; can't start research")
        case_id = new_id("case")
        await self._queue_fast(user, _Letter(document_id, case_id))
        return case_id

    async def pages_added(self, user: tables.User, document_id: DocumentId) -> None:
        """Pages joined a letter: re-run the fast pass on it, in the same case. If the
        last fast job hasn't been claimed yet, research will read the new pages
        anyway, so nothing more is queued."""
        case_id = await self._case_of(user.id, document_id)
        if case_id is None:
            logger.warning(
                "Pages added but no case found user_id=%s document_id=%s",
                user.id,
                document_id,
            )
            return
        latest = self._latest_fast.get(case_id)
        if latest is not None:
            job = await reads.get_job(latest)
            if job is not None and job.status == JobStatus.QUEUED:
                return
        await self._queue_fast(user, _Letter(document_id, case_id))

    def question_pending(self, user_id: UserId) -> bool:
        """Research asked something about the user's letter (C39)."""
        return self._results.question(user_id) is not None

    async def answer_question(self, user: tables.User, answer_en: str) -> bool:
        """C39: the user's answer re-runs the fast pass on the same case, with the
        answer as `user_note_en`. False if no question was open."""
        question = self._results.take_question(user.id)
        if question is None:
            return False
        if not question.document_ids:
            logger.error(
                "Letter question without a document case_id=%s", question.case_id
            )
            return False
        letter = _Letter(question.document_ids[0], question.case_id)
        await self._queue_fast(user, letter, user_note_en=answer_en)
        return True

    async def active_letter(self, user_id: UserId) -> DocumentId | None:
        """The letter new photos might belong to: the one being read now, else the
        newest document of the newest active case."""
        if (letter := self._reading.get(user_id)) is not None:
            return letter.document_id
        for case in await reads.list_active_cases(user_id):
            if case.document_ids:
                return case.document_ids[-1]
        return None

    async def _case_of(self, user_id: UserId, document_id: DocumentId) -> CaseId | None:
        letter = self._reading.get(user_id)
        if letter is not None and letter.document_id == document_id:
            return letter.case_id
        for case in await reads.list_active_cases(user_id):
            if document_id in case.document_ids:
                return case.id
        return None

    async def _queue_fast(
        self, user: tables.User, letter: _Letter, user_note_en: str | None = None
    ) -> None:
        assert user.language is not None
        job = await jobs.enqueue(
            ResearchFastJob(
                case_id=letter.case_id,
                user_id=user.id,
                document_ids=[letter.document_id],
                user_language=user.language,
                user_note_en=user_note_en,
            ),
            Component.ORCHESTRATOR,
            user.id,
            letter.case_id,
        )
        self._reading[user.id] = letter
        self._latest_fast[letter.case_id] = job.id
        logger.info(
            "Research queued user_id=%s case_id=%s document_id=%s job_id=%s",
            user.id,
            letter.case_id,
            letter.document_id,
            job.id,
        )
        self._watcher.watch(
            job.id,
            self._fast_finished,
            slow_after_s=self._slow_after_s,
            on_slow=self._fast_slow,
        )

    def _is_latest(self, job: tables.Job) -> bool:
        return job.case_id is not None and self._latest_fast.get(job.case_id) == job.id

    async def _fast_slow(self, job: tables.Job) -> None:
        if not self._is_latest(job):
            return
        user = await reads.get_user(job.user_id)
        if user is None:
            return
        try:
            await send_template(
                self._whatsapp, user, "research.slow", case_id=job.case_id
            )
        except WhatsAppSendError as exc:
            logger.error(
                "Taking-longer message not sent case_id=%s job_id=%s: %s",
                job.case_id,
                job.id,
                exc,
            )

    async def _fast_finished(self, job: tables.Job) -> None:
        if not self._is_latest(job):
            logger.info(
                "Stale fast pass ignored case_id=%s job_id=%s", job.case_id, job.id
            )
            return
        letter = self._reading.get(job.user_id)
        if letter is not None and letter.case_id == job.case_id:
            del self._reading[job.user_id]
        if job.status == JobStatus.FAILED:
            # Plan.md has no failure rule for a failed fast pass yet (Goal 8).
            logger.error(
                "Fast pass failed case_id=%s job_id=%s: %s",
                job.case_id,
                job.id,
                job.error,
            )
            return
        logger.info("Fast pass done case_id=%s job_id=%s", job.case_id, job.id)
        await self._results.fast_done(job)
