"""The demo video's seed (`reset --story mariam`): Mariam Namuna, a Dari speaker in
Fremont, with one finished case already on her account, a Medi-Cal renewal notice
from Alameda County. All fictional.

Her I-797C is not seeded: she sends the printed letter (demo/letters/) on camera.
So the seed holds only what the video shows as history: the Medi-Cal case,
explained and checked, with no question left open, so the orchestrator has nothing
to pick up mid-demo; and a sensitive fact waiting for her OK, for the profile page.

`--with-scam` adds the scam letter (demo/letters/scam_ar11_mariam_namuna.png) as a
second finished case, flagged suspicious, for rehearsals and backup takes. Leave it
off when the scam letter is sent live.

The user's WhatsApp number is passed in at reset time (it's a real phone), so the
live messages from that phone land on this user.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from app.contracts.common import (
    Component,
    FactSource,
    FactStatus,
    JobStatus,
    JobType,
    MessageDirection,
    MessageSender,
    Sensitivity,
    VerificationStatus,
)
from app.db import tables
from app.db.seed_story import placeholder_letter_png
from app.db.tables import utcnow

LANGUAGE = "fa"
RENEWAL_DUE = date(2026, 12, 1)
DOC_TYPE = "medi_cal_renewal"
ISSUER = "Alameda County Social Services Agency"
COUNTY_SITE = "https://www.alamedacountysocialservices.org/"
STATE_SITE = "https://www.dhcs.ca.gov/keepyourcoverage"


def medi_cal_fast_result(case_id: str) -> dict:
    """An R1 payload for the renewal notice (form MC 216), as the fast pass writes it."""
    return {
        "case_id": case_id,
        "status": "ok",
        "image_issue": None,
        "doc_type": DOC_TYPE,
        "issuer": ISSUER,
        "deadline": RENEWAL_DUE.isoformat(),
        "what_is_asked": (
            "Fill in, sign and return the Medi-Cal annual renewal form with proof of "
            "income and address"
        ),
        "appointment": None,
        "checklist_en": [
            {
                "kind": "deadline",
                "item": "Return the signed form by December 1, 2026",
                "citation": "p1",
            },
            {
                "kind": "bring",
                "item": "Pay stubs from the last 30 days",
                "citation": "p2",
            },
            {"kind": "bring", "item": "Proof of your address", "citation": "p2"},
        ],
        "key_dates": [
            {
                "type": "deadline",
                "raw": "December 1, 2026",
                "iso": RENEWAL_DUE.isoformat(),
            }
        ],
        "key_facts": [
            {
                "field": "form_id",
                "value": "MC 216",
                "quote": "MC 216, Medi-Cal Annual Renewal",
                "page": 1,
            },
        ],
        "explanation_en": (
            "This is your yearly Medi-Cal renewal from Alameda County. To keep your "
            "health coverage, return the signed form with proof of income and address "
            "by December 1, 2026."
        ),
        "urgency": "medium",
        "verification": "verified",
        "proposed_facts": [],
    }


class CaseRows:
    """Rows for one finished case on `user`'s account, timed from `start` (the
    photo's arrival): the letter, the case, its two research jobs, and helpers for
    its events and messages. Returned, not written: the caller adds `rows()` in
    order, since each list points at the ones before it."""

    def __init__(
        self,
        user: tables.User,
        start: datetime,
        doc_type: str,
        letter_png: bytes,
        deadline: date | None = None,
    ) -> None:
        self.start = start
        self.user = user
        self.media = tables.Media(
            user_id=user.id, content_type="image/png", data=letter_png
        )
        self.document = tables.Document(
            user_id=user.id,
            pages=[{"media_id": self.media.id, "added_at": start.isoformat()}],
            created_at=start,
        )
        self.case = tables.Case(
            user_id=user.id,
            document_ids=[self.document.id],
            doc_type=doc_type,
            deadline=deadline,
            created_at=start,
        )
        self.fast_job = self._job(JobType.RESEARCH_FAST, 0, 0.8)
        self.deep_job = self._job(JobType.RESEARCH_DEEP, 0.9, 2.6)

    def rows(self) -> list[list[object]]:
        return [
            [self.case, self.media, self.document],
            [self.fast_job, self.deep_job],
            self.history(),
        ]

    def history(self) -> list[object]:
        """The verdict, messages, events and anything else the case needs."""
        raise NotImplementedError

    def at(self, minutes: float) -> datetime:
        return self.start + timedelta(minutes=minutes)

    def _job(self, job_type: JobType, start: float, end: float) -> tables.Job:
        return tables.Job(
            type=job_type,
            status=JobStatus.DONE,
            created_by=Component.ORCHESTRATOR,
            user_id=self.user.id,
            case_id=self.case.id,
            payload={"case_id": self.case.id, "seeded": True},
            created_at=self.at(start),
            started_at=self.at(start),
            finished_at=self.at(end),
        )

    def event(
        self,
        event_type: str,
        source: Component,
        minutes: float,
        summary_en: str,
        job: tables.Job | None = None,
        /,
        **data: object,
    ) -> tables.Event:
        return tables.Event(
            created_at=self.at(minutes),
            type=event_type,
            source=source,
            user_id=self.user.id,
            case_id=self.case.id,
            job_id=job.id if job else None,
            summary_en=summary_en,
            data=data,
        )

    def message(
        self,
        minutes: float,
        direction: MessageDirection,
        body: str,
        body_en: str | None,
        media_ids: list[str] | None = None,
    ) -> tables.Message:
        sender = (
            MessageSender.USER
            if direction == MessageDirection.IN
            else MessageSender.ORCHESTRATOR
        )
        return tables.Message(
            created_at=self.at(minutes),
            user_id=self.user.id,
            case_id=self.case.id,
            direction=direction,
            sender=sender,
            body_original=body,
            body_en=body_en,
            language=LANGUAGE,
            media_ids=media_ids or [],
        )


class MediCalCase(CaseRows):
    """The renewal notice: explained, verified, thanked. Also carries Mariam's
    profile and facts, which come from this letter."""

    def __init__(self, user: tables.User, start: datetime) -> None:
        super().__init__(
            user, start, DOC_TYPE, placeholder_letter_png(), deadline=RENEWAL_DUE
        )
        self.case.fast_result = medi_cal_fast_result(self.case.id)

    def history(self) -> list[object]:
        return [
            self.verification(),
            *self.profile_and_facts(),
            *self.messages(),
            *self.research_events(),
        ]

    def verification(self) -> tables.Verification:
        """Verified against the county's site. No official phone: no call was
        needed, so none is offered."""
        return tables.Verification(
            case_id=self.case.id,
            status=VerificationStatus.VERIFIED,
            official_phone=None,
            result={
                "status": "verified",
                "official_phone": None,
                "letter_phone_matches": None,
                "evidence": [COUNTY_SITE, STATE_SITE],
                "red_flags": [],
            },
            created_at=self.at(2.5),
        )

    def profile_and_facts(self) -> list[object]:
        profile = tables.Profile(
            user_id=self.user.id,
            fields={"name": "Mariam Namuna", "city": "Fremont", "county": "Alameda"},
        )
        facts = [
            tables.Fact(
                user_id=self.user.id,
                fact="Lives in Fremont, Alameda County",
                category="contact",
                source=FactSource.FROM_DOCUMENT,
                source_ref=self.document.id,
                sensitivity=Sensitivity.NORMAL,
                status=FactStatus.ACTIVE,
                recorded_at=self.at(1),
            ),
            tables.Fact(
                user_id=self.user.id,
                fact="Has Medi-Cal health coverage",
                category="health",
                source=FactSource.FROM_DOCUMENT,
                source_ref=self.document.id,
                sensitivity=Sensitivity.SENSITIVE,
                # C15, C25: a health fact waits for her OK.
                status=FactStatus.PENDING_CONSENT,
                recorded_at=self.at(1),
            ),
        ]
        memory = Component.MEMORY_WRITER
        events = [
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
        ]
        return [profile, *facts, *events]

    def messages(self) -> list[tables.Message]:
        """Photo → question → explanation → verified → thanks. Nothing left open."""
        inbound, out = MessageDirection.IN, MessageDirection.OUT
        return [
            self.message(0, inbound, "", None, [self.media.id]),
            self.message(0.1, inbound, "این نامه چیست؟", "What is this letter?"),
            self.message(
                1,
                out,
                "این نامهٔ تمدید سالانهٔ Medi-Cal از ادارهٔ خدمات اجتماعی کانتی "
                "Alameda است. برای این که بیمهٔ صحی شما ادامه پیدا کند، فورم را پُر "
                "کنید، صفحهٔ ۴ را امضا کنید و آن را تا ۱ دسمبر ۲۰۲۶ با رسیدهای معاش "
                "۳۰ روز گذشته و یک سند آدرس پس بفرستید.",
                "This is your yearly Medi-Cal renewal from Alameda County Social "
                "Services. To keep your health coverage, fill in the form, sign page "
                "4, and send it back by December 1, 2026 with pay stubs from the last "
                "30 days and a proof of address.",
            ),
            self.message(
                2.6,
                out,
                "این نامه را با ویب‌سایت رسمی کانتی مقایسه کردیم: اصلی است.",
                "We checked this letter against the county's official website: it's "
                "real.",
            ),
            self.message(4, inbound, "تشکر", "Thank you"),
            self.message(
                4.1,
                out,
                "خواهش می‌کنم. هر وقت سوالی داشتید، همین‌جا بپرسید.",
                "You're welcome. Ask here whenever you have a question.",
            ),
        ]

    def research_events(self) -> list[tables.Event]:
        """The fast and deep passes with their steps, as the activity feed shows them."""
        research = Component.RESEARCH_AGENT
        fast, deep = self.fast_job, self.deep_job

        def check(minutes: float, summary: str, **data: object) -> tables.Event:
            return self.event(
                "research.check", research, minutes, summary, deep, **data
            )

        def fetch(minutes: float, url: str) -> tables.Event:
            return self.event(
                "research.fetch",
                research,
                minutes,
                f"Read {url}",
                deep,
                url=url,
                status=200,
            )

        return [
            self.event(
                "case.created", Component.ORCHESTRATOR, 0, "Case created (seed)"
            ),
            self.event(
                "research.fast_started", research, 0.05, "Reading the letter", fast
            ),
            self.event(
                "research.check",
                research,
                0.7,
                "Letter read",
                fast,
                check="letter_read",
                status="ok",
                doc_type=DOC_TYPE,
            ),
            self.event("research.fast_done", research, 0.8, "Letter explained", fast),
            self.event(
                "research.deep_started", research, 0.9, "Verifying the letter", deep
            ),
            self.event(
                "research.search",
                research,
                1.0,
                "Searched the web",
                deep,
                query="Alameda County Medi-Cal renewal official site",
            ),
            fetch(1.3, COUNTY_SITE),
            fetch(1.6, STATE_SITE),
            check(1.9, "Form type matches", check="form_id", state="match"),
            check(2.0, "Issuer matches", check="issuer", state="match"),
            check(2.1, "Return address matches", check="return_address", state="match"),
            check(2.2, "No scam patterns", check="scam_rules", red_flags=[]),
            check(
                2.4,
                "Verdict: verified",
                check="verdict",
                status="verified",
                official_phone_found=False,
            ),
            self.event(
                "verification.verified",
                research,
                2.5,
                "Letter verified against the county's site (seed)",
                deep,
                source="alamedacountysocialservices.org",
            ),
            self.event(
                "research.deep_done", research, 2.6, "Verification finished", deep
            ),
        ]


SCAM_DOC_TYPE = "ice_ar11_violation"
SCAM_LETTER = (
    Path(__file__).resolve().parents[3]
    / "demo"
    / "letters"
    / "scam_ar11_mariam_namuna.png"
)
SCAM_RED_FLAGS = [
    # What scam_rules.py says for this letter's payment section and signature.
    "This letter asks for payment by gift card. USCIS never asks for that.",
    (
        "This letter threatens arrest or deportation. USCIS does not threaten people "
        "in letters to get payment or information."
    ),
    (
        "This letter links to uscis-ar11-verify.com, which is not a .gov website. "
        "Federal agencies use .gov websites."
    ),
    (
        "This letter asks you to give card numbers, your Social Security number, or "
        "bank details by phone or text. Do not share them."
    ),
]


def scam_fast_result(case_id: str) -> dict:
    return {
        "case_id": case_id,
        "status": "ok",
        "image_issue": None,
        "doc_type": SCAM_DOC_TYPE,
        "issuer": "Immigration and Customs Enforcement (as the letter claims)",
        "what_is_asked": (
            "Call a phone number and pay a $500 fine in gift cards within 48 hours"
        ),
        "checklist_en": [],
        "key_facts": [
            {
                "field": "form_id",
                "value": "AR-11-V",
                "quote": "Form AR-11-V 09/26",
                "page": 1,
            }
        ],
        "explanation_en": (
            "This letter says you broke the law by not reporting a change of "
            "address, and asks you to call a number and pay a fine in gift cards. "
            "It has many signs of a scam."
        ),
        "urgency": "high",
        "verification": "suspicious",
        "proposed_facts": [],
    }


class ScamCase(CaseRows):
    """The fake AR-11 violation notice: flagged by the scam rules and by the
    checks against uscis.gov, and she was told not to pay. No call is offered."""

    def __init__(self, user: tables.User, start: datetime) -> None:
        png = SCAM_LETTER.read_bytes() if SCAM_LETTER.exists() else None
        super().__init__(user, start, SCAM_DOC_TYPE, png or placeholder_letter_png())
        self.case.fast_result = scam_fast_result(self.case.id)

    def history(self) -> list[object]:
        verification = tables.Verification(
            case_id=self.case.id,
            status=VerificationStatus.SUSPICIOUS,
            official_phone=None,
            result={
                "status": "suspicious",
                "official_phone": None,
                "letter_phone_matches": False,
                "evidence": [
                    "https://www.uscis.gov/ar-11",
                    "https://www.uscis.gov/contactcenter",
                ],
                "red_flags": SCAM_RED_FLAGS,
            },
            created_at=self.at(2.5),
        )
        return [verification, *self.messages(), *self.research_events()]

    def messages(self) -> list[tables.Message]:
        """Photo → "is this real?" → the warning → she didn't pay. Nothing open."""
        inbound, out = MessageDirection.IN, MessageDirection.OUT
        return [
            self.message(0, inbound, "", None, [self.media.id]),
            self.message(
                0.1,
                inbound,
                "این نامه واقعی است؟ می‌ترسم",
                "Is this letter real? I'm scared",
            ),
            self.message(
                2.6,
                out,
                "این نامه به احتمال زیاد کلاه‌برداری است. ادارهٔ USCIS هرگز کارت تحفه "
                "نمی‌خواهد و در نامه تهدید به گرفتاری نمی‌کند. به شماره‌ای که در نامه "
                "است زنگ نزنید و هیچ پولی نپردازید. آدرس خود را می‌توانید رایگان در "
                "uscis.gov تغییر دهید.",
                "This letter is very likely a scam. USCIS never asks for gift cards or "
                "threatens arrest in a letter. Don't call the number on it and don't "
                "pay anything. You can change your address for free on uscis.gov.",
            ),
            self.message(3, inbound, "تشکر، پول ندادم", "Thanks, I didn't pay"),
            self.message(
                3.1,
                out,
                "خوب کردید. اگر نامهٔ دیگری گرفتید، عکس آن را بفرستید.",
                "Good. If you get another letter, send a photo.",
            ),
        ]

    def research_events(self) -> list[tables.Event]:
        research = Component.RESEARCH_AGENT
        fast, deep = self.fast_job, self.deep_job

        def step(event_type: str, minutes: float, **data: object) -> tables.Event:
            return self.event(event_type, research, minutes, event_type, deep, **data)

        return [
            self.event(
                "case.created", Component.ORCHESTRATOR, 0, "Case created (seed)"
            ),
            self.event(
                "research.fast_started", research, 0.05, "Reading the letter", fast
            ),
            self.event(
                "research.check",
                research,
                0.7,
                "Letter read",
                fast,
                check="letter_read",
                status="ok",
                doc_type=SCAM_DOC_TYPE,
            ),
            self.event("research.fast_done", research, 0.8, "Letter explained", fast),
            self.event(
                "research.deep_started", research, 0.9, "Verifying the letter", deep
            ),
            step("research.check", 0.95, check="scam_rules", red_flags=SCAM_RED_FLAGS),
            step(
                "research.search", 1.0, query="USCIS AR-11 change of address official"
            ),
            step("research.fetch", 1.3, url="https://www.uscis.gov/ar-11", status=200),
            step(
                "research.fetch",
                1.5,
                url="https://www.uscis.gov/contactcenter",
                status=200,
            ),
            step(
                "research.fetch",
                1.7,
                url="https://www.uscis-ar11-verify.com",
                refused="not an official site",
            ),
            step("research.check", 1.9, check="issuer", state="conflict"),
            step("research.check", 2.0, check="letter_phone", state="conflict"),
            step("research.check", 2.1, check="url_domains", state="conflict"),
            step(
                "research.check",
                2.4,
                check="verdict",
                status="suspicious",
                official_phone_found=True,
            ),
            self.event(
                "verification.suspicious",
                research,
                2.5,
                "Letter flagged as suspicious (seed)",
                deep,
            ),
            self.event(
                "research.deep_done", research, 2.6, "Verification finished", deep
            ),
        ]


@dataclass
class MariamSeed:
    user: tables.User
    cases: list[CaseRows]


def build(whatsapp_number: str, with_scam: bool = False) -> MariamSeed:
    """Mariam and her Medi-Cal case from yesterday; with `with_scam`, also the scam
    letter from this morning."""
    user = tables.User(whatsapp_number=whatsapp_number, language=LANGUAGE)
    now = utcnow()
    cases: list[CaseRows] = [MediCalCase(user, now - timedelta(days=1))]
    if with_scam:
        cases.append(ScamCase(user, now - timedelta(hours=5)))
    return MariamSeed(user, cases)
