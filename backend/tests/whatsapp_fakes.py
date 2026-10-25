"""Fakes for the WhatsApp side: an in-memory stand-in for the DB helpers the pipe
and the relay call, a fake Twilio, and inbound-message builders. Fixtures that
install them are in conftest.py."""

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.contracts import (
    AskUserRequest,
    CaseBrief,
    Component,
    Event,
    EventType,
    FactSource,
    FactStatus,
    FastResult,
    FastResultStatus,
    JobPayload,
    JobStatus,
    JobType,
    MessageDirection,
    MessageSender,
    QuestionStatus,
    Sensitivity,
    Verification,
    VerificationStatus,
)
from app.db import tables
from app.db.errors import UnverifiedNumber
from app.db.progress import CaseStage, compute_stage
from app.db.tables import utcnow
from app.relay.inbound import InboundMedia, InboundMessage
from app.relay.media import DownloadedMedia, MediaDownloadError
from app.relay.whatsapp import WhatsAppSendError
from pydantic import BaseModel

NUMBER = "+15105550123"
QUIET_S = 0.05


class FakeDB:
    """Just enough of the DB helpers for the pipe and the relay, keyed like the real
    tables. Question reads return copies, as a real read would, so a test can hold
    a stale "open" row while the stored one changes."""

    def __init__(self) -> None:
        self.users: dict[str, tables.User] = {}
        self.messages: list[tables.Message] = []
        self.media: list[tables.Media] = []
        self.documents: list[tables.Document] = []
        self.cases: list[tables.Case] = []
        self.calls: dict[str, tables.Call] = {}
        self.questions: dict[str, tables.Question] = {}
        self.events: list[Event] = []
        self.jobs: dict[str, tables.Job] = {}
        self.verifications: dict[str, tables.Verification] = {}
        self.briefs: dict[str, tables.CaseBrief] = {}
        self.profiles: dict[str, tables.Profile] = {}
        self.facts: list[tables.Fact] = []

    # Relay: questions (race-safe like the real helpers: only an open row closes)

    async def create_question(
        self, request: AskUserRequest, user_id: str
    ) -> tables.Question:
        question = tables.Question(
            id=request.question_id,
            call_id=request.call_id,
            user_id=user_id,
            template=request.template,
            options_en=request.options_en,
            default_option=request.default_option,
            timeout_s=request.timeout_s,
        )
        self.questions[question.id] = question
        return _copy(question)

    async def _close_if_open(
        self, question_id: str, **values: Any
    ) -> tables.Question | None:
        question = self.questions[question_id]
        if question.status != QuestionStatus.OPEN:
            return None
        for key, value in values.items():
            setattr(question, key, value)
        return _copy(question)

    async def answer_question(
        self, question_id: str, choice: int
    ) -> tables.Question | None:
        return await self._close_if_open(
            question_id, status=QuestionStatus.ANSWERED, choice=choice
        )

    async def time_out_question(self, question_id: str) -> tables.Question | None:
        return await self._close_if_open(question_id, status=QuestionStatus.TIMED_OUT)

    async def record_late_reply(self, question_id: str) -> tables.Question:
        self.questions[question_id].late_reply_at = utcnow()
        return _copy(self.questions[question_id])

    async def get_open_question(self, user_id: str) -> tables.Question | None:
        open_questions = [
            q
            for q in self.questions.values()
            if q.user_id == user_id and q.status == QuestionStatus.OPEN
        ]
        return _copy(open_questions[-1]) if open_questions else None

    async def get_call(self, call_id: str) -> tables.Call | None:
        return self.calls.get(call_id)

    async def get_case(self, case_id: str) -> tables.Case | None:
        return next((c for c in self.cases if c.id == case_id), None)

    async def get_user(self, user_id: str) -> tables.User | None:
        return next((u for u in self.users.values() if u.id == user_id), None)

    async def append_event(self, event: Event) -> Event:
        self.events.append(event)
        return event

    async def list_events(
        self, user_id: str, since: datetime | None = None
    ) -> list[Event]:
        return [
            e
            for e in self.events
            if e.user_id == user_id and (since is None or e.created_at > since)
        ]

    def event_types(self) -> list[str]:
        return [e.type for e in self.events]

    def add_call(self, user: tables.User) -> tables.Call:
        """A case and a call in progress for `user`, as the phone agent would have."""
        case = tables.Case(user_id=user.id)
        self.cases.append(case)
        call = tables.Call(
            case_id=case.id,
            job_id="job_1",
            brief_id="brief_1",
            consent_message_id="msg_1",
        )
        self.calls[call.id] = call
        return call

    # Jobs

    async def enqueue(
        self,
        payload: JobPayload,
        created_by: Component,
        user_id: str,
        case_id: str | None = None,
    ) -> tables.Job:
        job = tables.Job(
            type=JobType(payload.job),
            created_by=created_by,
            user_id=user_id,
            case_id=case_id,
            payload=payload.model_dump(mode="json"),
        )
        self.jobs[job.id] = job
        return job

    async def get_job(self, job_id: str) -> tables.Job | None:
        job = self.jobs.get(job_id)
        return tables.Job(**job.model_dump()) if job else None

    async def claim_next(self, job_type: JobType) -> tables.Job | None:
        for job in self.jobs.values():
            if job.type == job_type and job.status == JobStatus.QUEUED:
                job.status = JobStatus.RUNNING
                return tables.Job(**job.model_dump())
        return None

    async def finish(self, job_id: str, result: BaseModel) -> None:
        self.finish_job(job_id, result)

    async def fail(self, job_id: str, error: str) -> None:
        self.fail_job(job_id, error)

    def jobs_of(self, job_type: JobType) -> list[tables.Job]:
        return [j for j in self.jobs.values() if j.type == job_type]

    def finish_job(self, job_id: str, result: BaseModel | None = None) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.DONE
        job.result = result.model_dump(mode="json") if result else {}

    def fail_job(self, job_id: str, error: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.FAILED
        job.error = error

    # Orchestrator: users, media, letters

    async def get_or_create_user(self, whatsapp_number: str) -> tables.User:
        return self.users.setdefault(
            whatsapp_number, tables.User(whatsapp_number=whatsapp_number)
        )

    async def set_language(self, user_id: str, lang: str) -> tables.User:
        user = next(u for u in self.users.values() if u.id == user_id)
        user.language = lang
        return user

    async def save_media(
        self, user_id: str, content_type: str, data: bytes, url: str | None = None
    ) -> tables.Media:
        row = tables.Media(user_id=user_id, content_type=content_type, data=data)
        self.media.append(row)
        return row

    async def create_document(
        self, user_id: str, media_ids: Sequence[str]
    ) -> tables.Document:
        doc = tables.Document(
            user_id=user_id, pages=[{"media_id": m} for m in media_ids]
        )
        self.documents.append(doc)
        return doc

    async def add_pages(self, document_id: str, media_ids: Sequence[str]) -> None:
        doc = next(d for d in self.documents if d.id == document_id)
        doc.pages = [*doc.pages, *({"media_id": m} for m in media_ids)]

    async def append_message(
        self,
        user_id: str,
        direction: MessageDirection,
        sender: MessageSender,
        body_original: str,
        lang: str,
        **fields: Any,
    ) -> tables.Message:
        fields["media_ids"] = list(fields.get("media_ids", ()))
        row = tables.Message(
            user_id=user_id,
            direction=direction,
            sender=sender,
            body_original=body_original,
            language=lang,
            **fields,
        )
        self.messages.append(row)
        return row

    async def list_messages(self, user_id: str) -> list[tables.Message]:
        return [m for m in self.messages if m.user_id == user_id]

    def _closed(self, case_id: str) -> bool:
        return any(
            e.type == EventType.CASE_CLOSED and e.case_id == case_id
            for e in self.events
        )

    async def list_active_cases(self, user_id: str) -> list[tables.Case]:
        return [
            c
            for c in reversed(self.cases)
            if c.user_id == user_id and not self._closed(c.id)
        ]

    async def case_progress(self, case_id: str) -> CaseStage:
        case = next(c for c in self.cases if c.id == case_id)
        verification = self.verifications.get(case_id)
        return compute_stage(
            closed=self._closed(case_id),
            latest_call_state=None,
            latest_verification=verification.status if verification else None,
            fast_job=None,
            deep_job=None,
            fast_result=(case.fast_result or {}).get("status"),
        )

    async def latest_verification(self, case_id: str) -> tables.Verification | None:
        return self.verifications.get(case_id)

    async def official_dial_number(self, case_id: str) -> str:
        """Refuses like the real helper (rule 2)."""
        verification = self.verifications.get(case_id)
        if verification is None or verification.status != VerificationStatus.VERIFIED:
            raise UnverifiedNumber(f"case {case_id} is not verified")
        if not verification.official_phone:
            raise UnverifiedNumber(f"case {case_id} has no official phone")
        return verification.official_phone

    async def latest_brief(self, case_id: str) -> tables.CaseBrief | None:
        return self.briefs.get(case_id)

    async def list_calls(self, case_id: str) -> list[tables.Call]:
        return [c for c in self.calls.values() if c.case_id == case_id]

    def add_verified_case(
        self,
        user: tables.User,
        status: VerificationStatus = VerificationStatus.VERIFIED,
        official_phone: str | None = "+15105550199",
    ) -> tables.Case:
        """A case research has finished: R1 saved, a verdict, and a brief, stored as
        research's writers store them (contract models dumped to JSON)."""
        doc_type = "uscis_i797c_asylum_interview"
        case = tables.Case(user_id=user.id, doc_type=doc_type)
        case.fast_result = FastResult(
            case_id=case.id,
            status=FastResultStatus.OK,
            doc_type=doc_type,
            issuer="USCIS",
            explanation_en="An asylum interview notice.",
        ).model_dump(mode="json")
        self.cases.append(case)
        verification = Verification(
            status=status,
            official_phone=official_phone,
            letter_phone_matches=None,
            evidence=["https://www.uscis.gov/contactcenter"],
            red_flags=[],
        )
        self.verifications[case.id] = tables.Verification(
            case_id=case.id,
            status=status,
            official_phone=official_phone,
            result=verification.model_dump(mode="json"),
        )
        brief = tables.CaseBrief(case_id=case.id, brief={}, handoff_note="test brief")
        brief.brief = CaseBrief(
            brief_id=brief.id,
            case_id=case.id,
            doc_type=doc_type,
            issuer="USCIS",
            call_goal_en="Confirm the interview is still on",
            handoff_note=brief.handoff_note,
        ).model_dump(mode="json")
        self.briefs[case.id] = brief
        return case

    async def get_profile(self, user_id: str) -> tables.Profile | None:
        return self.profiles.get(user_id)

    async def list_facts(
        self, user_id: str, statuses: Sequence[FactStatus] | None = None
    ) -> list[tables.Fact]:
        return [
            f
            for f in self.facts
            if f.user_id == user_id and (statuses is None or f.status in statuses)
        ]

    # Memory writer: facts and profile

    async def add_fact(
        self,
        user_id: str,
        fact: str,
        category: str,
        source: FactSource,
        sensitivity: Sensitivity,
        status: FactStatus,
        source_ref: str | None = None,
        supersedes: str | None = None,
    ) -> tables.Fact:
        row = tables.Fact(
            user_id=user_id,
            fact=fact,
            category=category,
            source=source,
            sensitivity=sensitivity,
            status=status,
            source_ref=source_ref,
            supersedes=supersedes,
        )
        self.facts.append(row)
        return row

    async def set_fact_status(self, fact_id: str, status: FactStatus) -> tables.Fact:
        fact = next(f for f in self.facts if f.id == fact_id)
        fact.status = status
        return fact

    async def delete_fact(self, fact_id: str) -> None:
        self.facts = [f for f in self.facts if f.id != fact_id]

    async def upsert_profile(
        self, user_id: str, fields: dict[str, Any]
    ) -> tables.Profile:
        profile = self.profiles.setdefault(
            user_id, tables.Profile(user_id=user_id, fields={})
        )
        profile.fields = {**profile.fields, **fields}
        return profile

    def outbound_templates(self) -> list[str | None]:
        return [m.template for m in self.messages if m.direction == "out"]


class FakeWhatsApp:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.typing_sids: list[str] = []
        self.broken_urls: set[str] = set()
        self.fail_sends = False

    async def send(self, to_number: str, body: str) -> list[str]:
        assert to_number == NUMBER
        if self.fail_sends:
            raise WhatsAppSendError("Twilio send failed after 0 parts: error 63016")
        self.sent.append(body)
        return [f"SM{len(self.sent)}"]

    async def download(self, media: InboundMedia, message_sid: str) -> DownloadedMedia:
        if media.url in self.broken_urls:
            raise MediaDownloadError(f"Media download failed for {message_sid}")
        return DownloadedMedia(content_type=media.content_type, data=b"jpeg")

    async def typing(self, message_sid: str) -> None:
        self.typing_sids.append(message_sid)


class FakeTranslator:
    """Marks what it translated, so a test can tell translated text from English."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []
        self.contexts: list[str | None] = []

    async def from_english(
        self, text_en: str, language: str, *, context: str | None = None
    ) -> str | None:
        self.calls.append(text_en)
        self.contexts.append(context)
        return None if self.fail else f"[{language}] {text_en}"

    async def to_english(self, text: str, language: str) -> str | None:
        return None if self.fail else f"[en] {text}"


def _copy(question: tables.Question) -> tables.Question:
    return tables.Question(**question.model_dump())


_sid = 0


def inbound(body: str = "", photos: int = 0) -> InboundMessage:
    global _sid
    _sid += 1
    form = {
        "MessageSid": f"SM{_sid}",
        "From": f"whatsapp:{NUMBER}",
        "To": "whatsapp:+14155238886",
        "Body": body,
        "NumMedia": str(photos),
    }
    for i in range(photos):
        form[f"MediaUrl{i}"] = f"https://api.twilio.com/media/{_sid}/{i}"
        form[f"MediaContentType{i}"] = "image/jpeg"
    return InboundMessage.from_form(form)


async def wait_for_batches() -> None:
    await asyncio.sleep(QUIET_S * 3)


async def use_spanish(db: FakeDB) -> tables.User:
    user = await db.get_or_create_user(NUMBER)
    user.language = "es"
    return user
