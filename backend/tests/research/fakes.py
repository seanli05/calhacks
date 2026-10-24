"""Fakes for research tests: an in-memory stand-in for the DB helpers research
calls, and canned passes so no API key, network, or real images are needed.

`FakeResearchDB.install(monkeypatch)` swaps the helpers in `app.db` for its own
methods; the handlers call them through their modules, so nothing else changes.
"""

import base64
from typing import Any

import pytest
from app.contracts import (
    CaseBrief,
    Event,
    JobStatus,
    JobType,
    QuestionAnswer,
    QuestionSource,
)
from app.contracts.jobs import JobPayload
from app.db import tables
from app.db.tables import utcnow
from app.research.deep_pass import LogFn
from app.research.fake import FAKE_URL, fake_deep_findings, fake_fast_pass_output
from app.research.jobs import ResearchDeps
from app.research.models import DeepFindings, FastPassOutput
from app.research.preprocess import ContentBlock, UnsupportedMedia
from app.settings import Settings
from pydantic import BaseModel

_READS = ("get_document", "get_media", "get_case", "list_case_refs")
_WRITES = (
    "create_case",
    "put_ref",
    "save_fast_result",
    "save_verification",
    "save_brief",
)


class FakeResearchDB:
    """Just the helpers research uses, keyed like the real tables."""

    def __init__(self) -> None:
        self.documents: dict[str, tables.Document] = {}
        self.media: dict[str, tables.Media] = {}
        self.cases: dict[str, tables.Case] = {}
        self.case_refs: dict[tuple[str, str], str] = {}
        self.verifications: dict[str, tables.Verification] = {}
        self.case_briefs: dict[str, tables.CaseBrief] = {}
        self.jobs: dict[str, tables.Job] = {}
        self.events: list[Event] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> "FakeResearchDB":
        for name in _READS:
            monkeypatch.setattr(f"app.db.reads.{name}", getattr(self, name))
        for name in _WRITES:
            monkeypatch.setattr(f"app.db.writes.research.{name}", getattr(self, name))
        for name in ("enqueue", "finish", "fail"):
            monkeypatch.setattr(f"app.db.jobs.{name}", getattr(self, name))
        monkeypatch.setattr("app.db.events.append_event", self.append_event)
        return self

    # --- Test setup (the orchestrator's side) ---

    def add_document(
        self, pages: list[tuple[str, bytes]], document_id: str = "doc_1"
    ) -> str:
        page_refs = []
        for i, (content_type, data) in enumerate(pages):
            media = tables.Media(
                id=f"media_{document_id}_{i}",
                user_id="user_1",
                content_type=content_type,
                data=data,
            )
            self.media[media.id] = media
            page_refs.append({"media_id": media.id, "added_at": utcnow().isoformat()})
        self.documents[document_id] = tables.Document(
            id=document_id, user_id="user_1", pages=page_refs
        )
        return document_id

    def add_claimed_job(self, payload: JobPayload, case_id: str | None) -> tables.Job:
        """A job as `claim_next` returns it: already running."""
        job = tables.Job(
            type=JobType(payload.job),
            status=JobStatus.RUNNING,
            created_by="test",
            user_id=payload.user_id,
            case_id=case_id,
            payload=payload.model_dump(mode="json"),
        )
        self.jobs[job.id] = job
        return job

    def job_types(self) -> list[str]:
        return [j.type for j in self.jobs.values()]

    def event_types(self) -> list[str]:
        return [e.type for e in self.events]

    # --- reads ---

    async def get_document(self, document_id: str) -> tables.Document | None:
        return self.documents.get(document_id)

    async def get_media(self, media_id: str) -> tables.Media | None:
        return self.media.get(media_id)

    async def get_case(self, case_id: str) -> tables.Case | None:
        return self.cases.get(case_id)

    async def list_case_refs(self, case_id: str) -> list[tables.CaseRef]:
        return [
            tables.CaseRef(case_id=c, name=name, value=value)
            for (c, name), value in self.case_refs.items()
            if c == case_id
        ]

    # --- writes.research ---

    async def create_case(
        self, case_id: str, user_id: str, document_ids: list[str]
    ) -> tables.Case:
        if case_id not in self.cases:
            self.cases[case_id] = tables.Case(
                id=case_id, user_id=user_id, document_ids=list(document_ids)
            )
        return self.cases[case_id]

    async def put_ref(self, case_id: str, name: str, value: str) -> None:
        assert case_id in self.cases, "a ref needs its case row first"
        self.case_refs[(case_id, name)] = value

    async def save_fast_result(self, case_id: str, result: BaseModel) -> tables.Case:
        case = self.cases[case_id]
        case.fast_result = result.model_dump(mode="json")
        return case

    async def save_verification(
        self, case_id: str, verification: BaseModel
    ) -> tables.Verification:
        dumped = verification.model_dump(mode="json")
        row = tables.Verification(
            case_id=case_id,
            status=dumped["status"],
            official_phone=dumped["official_phone"],
            result=dumped,
        )
        self.verifications[row.id] = row
        return row

    async def save_brief(
        self, case_id: str, brief: CaseBrief, handoff_note: str | None = None
    ) -> tables.CaseBrief:
        assert brief.case_id == case_id
        row = tables.CaseBrief(
            id=brief.brief_id,
            case_id=case_id,
            brief=brief.model_dump(mode="json"),
            handoff_note=handoff_note or brief.handoff_note,
        )
        self.case_briefs[row.id] = row
        return row

    # --- jobs, events ---

    async def enqueue(
        self,
        payload: JobPayload,
        created_by: str,
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

    async def finish(
        self, job_id: str, result: BaseModel | dict[str, Any]
    ) -> tables.Job:
        job = self.jobs[job_id]
        job.status = JobStatus.DONE
        job.result = (
            result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        )
        return job

    async def fail(self, job_id: str, error: str) -> tables.Job:
        job = self.jobs[job_id]
        job.status = JobStatus.FAILED
        job.error = error
        return job

    async def append_event(self, event: Event) -> Event:
        self.events.append(event)
        return event


# --- Fake passes ---


async def fake_to_blocks(data: bytes, content_type: str) -> list[ContentBlock]:
    """Pass-through: wraps the bytes as a block without decoding them."""
    encoded = base64.b64encode(data).decode()
    if content_type == "application/pdf":
        return [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": content_type,
                    "data": encoded,
                },
            }
        ]
    if content_type in ("image/jpeg", "image/png", "image/webp"):
        return [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": content_type,
                    "data": encoded,
                },  # type: ignore[typeddict-item]
            }
        ]
    raise UnsupportedMedia("Please send the letter as a JPG or PNG photo, or a PDF.")


async def fake_fast_pass(
    blocks: list[ContentBlock], *, case_id: str, **_: Any
) -> FastPassOutput:
    return fake_fast_pass_output(case_id)


async def fake_deep_pass(
    signals: Any,
    call_purpose: str | None,
    county: str | None,
    *,
    log: LogFn | None = None,
    **_: Any,
) -> DeepFindings:
    findings = fake_deep_findings()
    if log:
        url = findings.trust_chain[0]
        await log(
            "research.search",
            "Searched for the issuer's official site",
            {"query_count": 1},
        )
        await log("research.fetch", "Fetched the official contact page", {"url": url})
        await log(
            "research.check",
            "Official phone found on a trusted page",
            {"check": "phone_on_page", "passed": True},
        )
    return findings


async def fake_answer_question(
    question_en: str, *, log: LogFn | None = None, **_: Any
) -> QuestionAnswer:
    if log:
        await log("research.search", "Searched the web", {})
        await log("research.fetch", "Fetched the official page", {"url": FAKE_URL})
    return QuestionAnswer(
        status="answered",
        answer_en="Fake answer: bring the notice and photo ID to the interview.",
        sources=[QuestionSource(url=FAKE_URL, quote="Bring this notice.")],
    )


async def fake_short_goal(goal_en: str, **_: Any) -> str | None:
    return "Confirm your form was received"


def fake_deps() -> ResearchDeps:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        model_default="fake",
        model_fast="fake-fast",
        model_deep="fake",
        anthropic_api_key="fake",
    )
    return ResearchDeps(
        settings=settings,
        fast_pass_fn=fake_fast_pass,
        deep_pass_fn=fake_deep_pass,
        to_blocks_fn=fake_to_blocks,
        question_fn=fake_answer_question,
        short_goal_fn=fake_short_goal,
    )
