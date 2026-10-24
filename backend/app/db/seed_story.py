"""The demo seed's story around the case (app.db.reset): the WhatsApp exchange, the
memory, the feed events, and optionally a finished call. All fictional.

Event `data` carries exactly the fields app/api/feed_templates.py expects, so the
seeded feed reads the way the live one will.
"""

import struct
import zlib
from datetime import datetime, timedelta

from app.contracts import CallJob, CallReport
from app.contracts.common import (
    CallOutcome,
    CallState,
    Component,
    FactSource,
    FactStatus,
    JobStatus,
    JobType,
    MessageDirection,
    MessageSender,
    Sensitivity,
    TrustLevel,
)
from app.db import tables

LANGUAGE = "es"
AGENCY = "USCIS"


def placeholder_letter_png(width: int = 240, height: int = 310) -> bytes:
    """A blank "letter" (a header band and grey text lines) standing in for the
    photo of the I-797C, so the seed carries no real document."""
    white, header, line = b"\xff\xff\xff", b"\x28\x46\x78", b"\xc8\xc8\xc8"
    margin = 20
    rows = []
    for y in range(height):
        if 16 <= y < 40:
            pixels = white * margin + header * (width - 2 * margin) + white * margin
        elif 60 <= y < height - 30 and (y - 60) % 18 < 6:
            pixels = white * margin + line * (width - 2 * margin) + white * margin
        else:
            pixels = white * width
        rows.append(b"\x00" + pixels)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(tag + data))
        return struct.pack(">I", len(data)) + tag + data + crc

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


class Story:
    """Builds rows for one user and case, timed relative to `start` (the letter's
    arrival). Rows are returned, not written: the caller adds them in FK order."""

    def __init__(self, user_id: str, case_id: str, start: datetime) -> None:
        self.user_id = user_id
        self.case_id = case_id
        self.start = start

    def at(self, minutes: float) -> datetime:
        return self.start + timedelta(minutes=minutes)

    def event(
        self,
        event_type: str,
        source: Component,
        minutes: float,
        summary_en: str,
        call_id: str | None = None,
        /,
        **data: object,
    ) -> tables.Event:
        """Positional-only, so `data` may hold any key (`source`, for one)."""
        return tables.Event(
            created_at=self.at(minutes),
            type=event_type,
            source=source,
            user_id=self.user_id,
            case_id=self.case_id,
            call_id=call_id,
            summary_en=summary_en,
            data=data,
        )

    def message(
        self,
        minutes: float,
        direction: MessageDirection,
        sender: MessageSender,
        body: str,
        body_en: str | None,
        media_ids: list[str] | None = None,
    ) -> tables.Message:
        return tables.Message(
            created_at=self.at(minutes),
            user_id=self.user_id,
            case_id=self.case_id,
            direction=direction,
            sender=sender,
            body_original=body,
            body_en=body_en,
            language=LANGUAGE,
            media_ids=media_ids or [],
        )

    def before_call(self, media_id: str, document_id: str) -> list[object]:
        """Letter photo → explanation → facts → verified → consent asked."""
        facts = [
            tables.Fact(
                user_id=self.user_id,
                fact="Has two children on the asylum application",
                category="immigration",
                source=FactSource.FROM_DOCUMENT,
                source_ref=document_id,
                sensitivity=Sensitivity.SENSITIVE,
                # C15, C25: an immigration fact waits for the user's OK.
                status=FactStatus.PENDING_CONSENT,
                recorded_at=self.at(1),
            ),
            tables.Fact(
                user_id=self.user_id,
                fact="Lives in Los Angeles County",
                category="contact",
                source=FactSource.USER_SAID,
                sensitivity=Sensitivity.NORMAL,
                status=FactStatus.ACTIVE,
                recorded_at=self.at(1),
            ),
            tables.Fact(
                user_id=self.user_id,
                fact="Prefers voice notes",
                category="contact",
                source=FactSource.USER_SAID,
                sensitivity=Sensitivity.NORMAL,
                status=FactStatus.ACTIVE,
                recorded_at=self.at(1),
            ),
        ]
        out, inbound = MessageDirection.OUT, MessageDirection.IN
        orchestrator, user = MessageSender.ORCHESTRATOR, MessageSender.USER
        messages = [
            self.message(0, inbound, user, "", None, [media_id]),
            self.message(
                1,
                out,
                orchestrator,
                "Es la cita para tu entrevista de asilo: jueves 12 de noviembre a "
                "las 8:30 AM. Tienes que ir con tus hijos y llevar tu propio "
                "intérprete.",
                "It's your asylum interview appointment: Thursday, November 12 at "
                "8:30 AM. You must go with your children and bring your own "
                "interpreter.",
            ),
            self.message(
                4,
                out,
                orchestrator,
                "Confirmamos que la carta es real. ¿Quieres que llamemos a USCIS y "
                "te avisemos cuando conteste una persona? Responde SÍ o NO.",
                "We confirmed the letter is real. Want us to call USCIS and ring "
                "you when a person answers? Reply YES or NO.",
            ),
        ]
        research, memory = Component.RESEARCH_AGENT, Component.MEMORY_WRITER
        events = [
            self.event("case.created", research, 0, "Case created (seed)"),
            self.event("research.fast_started", research, 0.1, "Reading the letter"),
            self.event("research.fast_done", research, 1, "Letter explained"),
            *(
                self.event(
                    "memory.fact_pending_consent"
                    if f.status == FactStatus.PENDING_CONSENT
                    else "memory.fact_saved",
                    memory,
                    1.1 + i / 10,
                    "Saved a fact",
                    fact_id=f.id,
                )
                for i, f in enumerate(facts)
            ),
            self.event("research.deep_started", research, 1.5, "Verifying the letter"),
            self.event(
                "verification.verified",
                research,
                3,
                "Letter verified against uscis.gov (seed)",
                source="uscis.gov",
            ),
            self.event("research.deep_done", research, 3.1, "Verification finished"),
            self.event(
                "consent.requested",
                Component.ORCHESTRATOR,
                4,
                "Asked the user for consent to call USCIS",
                agency=AGENCY,
            ),
        ]
        profile = tables.Profile(
            user_id=self.user_id,
            fields={"county": "Los Angeles", "household_size": "3"},
        )
        glossary = [
            tables.GlossaryTerm(
                term=term,
                language=LANGUAGE,
                translation=translation,
                trust_level=TrustLevel.MACHINE,
            )
            for term, translation in (
                ("asylum interview", "entrevista de asilo"),
                ("interpreter", "intérprete"),
                ("dependent", "dependiente"),
            )
        ]
        return [profile, *facts, *messages, *events, *glossary]

    def consent(self, minutes: float) -> tuple[tables.Message, tables.Event]:
        message = self.message(
            minutes,
            MessageDirection.IN,
            MessageSender.USER,
            "Sí, por favor",
            "Yes, please",
        )
        event = self.event(
            "consent.given",
            Component.ORCHESTRATOR,
            minutes,
            "User consented to the call",
            message_id=message.id,
        )
        return message, event

    def finished_call(
        self, brief_id: str, consent: tables.Message, minutes: float
    ) -> tuple[tables.Job, tables.Call, list[object]]:
        """A resolved call starting `minutes` after the letter: the job, the call
        (added after the job), then its transcript, events, and messages."""
        job = tables.Job(
            type=JobType.CALL,
            status=JobStatus.DONE,
            created_by=Component.ORCHESTRATOR,
            user_id=self.user_id,
            case_id=self.case_id,
            payload=CallJob(
                case_id=self.case_id,
                user_id=self.user_id,
                brief_id=brief_id,
                user_language=LANGUAGE,
                consent_at=consent.created_at,
                consent_message_id=consent.id,
                max_hold_minutes=45,
            ).model_dump(mode="json"),
            created_at=self.at(minutes),
            started_at=self.at(minutes),
            finished_at=self.at(minutes + 14),
        )
        call = tables.Call(
            case_id=self.case_id,
            job_id=job.id,
            brief_id=brief_id,
            consent_message_id=consent.id,
            state=CallState.ENDED,
            outcome=CallOutcome.RESOLVED,
            started_at=self.at(minutes),
            ended_at=self.at(minutes + 14),
        )
        transcript = tables.Transcript(
            call_id=call.id, created_at=self.at(minutes + 14), lines=[]
        )
        lines = [
            (0, "agency", "Thank you for calling USCIS. For interview or appointment notices, press 2."),
            (1, "agent", "(pressed 2)"),
            (1, "agency", "For an asylum interview, press 2."),
            (1.5, "agent", "(pressed 2)"),
            (2, "agency", "All of our officers are busy. Please stay on the line."),
            (9, "agency", "USCIS, this is Officer Lee. How can I help?"),
            (9, "agent", "Hi, I'm an automated assistant calling for a family about an asylum interview notice. The applicant is joining the call now so they can answer your questions directly."),
            (9, "agency", "Sure, I'll hold."),
            (10, "user", "Hello, I want to confirm my interview on November 12 and ask about my interpreter."),
            (12, "agency", "Your interview is still scheduled. You must bring your own interpreter; if they can't come, tell us in writing before the appointment."),
        ]  # fmt: skip
        transcript.lines = [
            {"at": self.at(minutes + m).isoformat(), "speaker": who, "text": text}
            for m, who, text in lines
        ]
        call.report = CallReport(
            call_id=call.id,
            case_id=self.case_id,
            outcome=CallOutcome.RESOLVED,
            rep_name="Officer Lee",
            next_steps_en=[
                "Your interview is still on November 12 at 8:30 AM",
                "You must bring your own interpreter; USCIS doesn't provide one",
                (
                    "If your interpreter can't come, tell USCIS in writing before the "
                    "appointment"
                ),
            ],
            new_deadlines=[],
            transcript_id=transcript.id,
            proposed_facts=[],
            followup_needed=False,
        ).model_dump(mode="json")
        phone = Component.PHONE_AGENT

        def call_event(
            event_type: str, m: float, summary: str, **data: object
        ) -> tables.Event:
            return self.event(event_type, phone, minutes + m, summary, call.id, **data)

        events = [
            call_event("call.dialing", 0, "Dialing the official USCIS number", agency=AGENCY),
            call_event("call.menu_choice", 1, "Pressed 2 (Appointments)", digit="2"),
            call_event("call.menu_choice", 1.5, "Pressed 2 (Asylum interview)", digit="2"),
            call_event("call.on_hold", 2, "On hold", agency=AGENCY),
            call_event("call.human_detected", 9, "A person answered", agency=AGENCY),
            call_event("call.user_dialed", 9.1, "Ringing the user"),
            call_event("call.user_joined", 10, "User joined the call", agency=AGENCY),
            call_event("call.ended", 14, "Call ended", minutes=14),
        ]  # fmt: skip
        out = MessageDirection.OUT
        relay, orchestrator = MessageSender.RELAY, MessageSender.ORCHESTRATOR
        messages = [
            self.message(minutes, out, relay, "Estamos llamando a USCIS. Te avisamos cuando conteste alguien.", "We're calling USCIS. We'll let you know when someone answers."),
            self.message(minutes + 2, out, relay, "Estamos en espera con USCIS. Te llamamos cuando conteste una persona.", "We're on hold with USCIS. We'll call you when a person answers."),
            self.message(minutes + 9, out, relay, "¡Contestó una persona! Te estamos llamando ahora.", "A person answered! We're calling you now."),
            self.message(minutes + 14, out, orchestrator, "Listo. Tu entrevista sigue el 12 de noviembre a las 8:30 AM. Recuerda llevar tu propio intérprete.", "Done. Your interview is still November 12 at 8:30 AM. Remember to bring your own interpreter."),
        ]  # fmt: skip
        return job, call, [transcript, *events, *messages]
