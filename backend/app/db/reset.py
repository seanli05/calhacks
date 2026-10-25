"""Drop and recreate every table, seed the demo case, then load the preset glossary.

    python -m app.db.reset --yes               # rebuild and seed (awaiting consent)
    python -m app.db.reset --yes --after-call  # ...plus a finished call
    python -m app.db.reset --yes --empty       # rebuild, no seed
    python -m app.db.reset --yes --story mariam --number +1...  # the demo video

The default story is Ana (Spanish, an I-797C waiting for consent). `--story mariam`
seeds the demo video's user instead (`seed_mariam.py`): pass her real phone as
`--number`, so the letter she sends on camera lands on her seeded account.

The database is shared by the whole team, so this wipes everyone's data; it refuses
to run without --yes. It's a dev tool, so seeding writes several owners' tables. The glossary
(`app.glossary.load`) is reference data, so it's loaded even with --empty; without
it the translation book is empty and translations lose their USCIS wording.
Seed values match mock_agency/agency/case_record.py (DEMO_CASE). All fictional.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from urllib.parse import urlsplit

from app.contracts.common import VerificationStatus
from app.db import seed_mariam, tables
from app.db.engine import get_engine, session
from app.db.schema import create_all, drop_all
from app.db.seed_story import Story, placeholder_letter_png
from app.db.tables import utcnow
from app.glossary import load as glossary_load
from app.settings import get_settings

DEMO_WHATSAPP_NUMBER = "+15555550100"
DEMO_INTERVIEW_DATE = date(2026, 11, 12)
DEMO_REFS = {
    "receipt_number": "ZLA2690012345",
    "a_number": "A212345678",
    "date_of_birth": "1988-03-14",
    "interview_location": (
        "Los Angeles Asylum Office, 1585 Corporate Drive, Tustin, California"
    ),
}


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.db.reset")
    parser.add_argument(
        "--yes", action="store_true", help="confirm wiping the shared database"
    )
    parser.add_argument("--empty", action="store_true", help="skip the demo seed")
    parser.add_argument(
        "--after-call",
        action="store_true",
        help="also seed a finished call, to check the ended screens",
    )
    parser.add_argument(
        "--story",
        choices=["ana", "mariam"],
        default="ana",
        help="which demo user to seed (mariam: the demo video)",
    )
    parser.add_argument(
        "--number",
        help="with --story mariam: her WhatsApp number in E.164 (+1...)",
    )
    args = parser.parse_args(argv)
    if args.story == "mariam" and not (args.number or "").startswith("+"):
        parser.error("--story mariam needs --number in E.164, e.g. +15105550100")
    if args.story == "mariam" and args.after_call:
        parser.error("--after-call is for the ana story")
    return args


def target_host() -> str:
    return urlsplit(get_settings().async_database_url).hostname or "?"


def demo_fast_result(case_id: str) -> dict:
    """An R1 payload for the demo letter, so the case reads as already explained."""
    return {
        "case_id": case_id,
        "status": "ok",
        "image_issue": None,
        "doc_type": "uscis_i797c_asylum_interview",
        "issuer": "USCIS",
        "deadline": DEMO_INTERVIEW_DATE.isoformat(),
        "what_is_asked": "Attend asylum interview with dependents and a qualified interpreter",
        "appointment": {
            "date": DEMO_INTERVIEW_DATE.isoformat(),
            "time": "08:30",
            "location_ref": "<ref:interview_location>",
            "citation": "p1",
        },
        "checklist_en": [
            {
                "kind": "who_must_come",
                "item": "All dependents listed on the I-589",
                "citation": "p1 §I",
            },
            {
                "kind": "bring",
                "item": "A qualified interpreter if you are not fluent in English",
                "citation": "p1 §III",
            },
            {
                "kind": "bring",
                "item": "ID for you and each dependent",
                "citation": "p1 §II",
            },
        ],
        "key_dates": [
            {
                "type": "appointment",
                "raw": f"{DEMO_INTERVIEW_DATE:%B} {DEMO_INTERVIEW_DATE.day}, "
                f"{DEMO_INTERVIEW_DATE.year} at 8:30 AM",
                "iso": DEMO_INTERVIEW_DATE.isoformat(),
            }
        ],
        "key_facts": [
            {
                "field": "form_id",
                "value": "I-797C",
                "quote": "I-797C, Notice of Action",
                "page": 1,
            },
            {"field": "receipt_number", "ref": "<ref:receipt_number>", "page": 1},
            {"field": "a_number", "ref": "<ref:a_number>", "page": 1},
        ],
        "explanation_en": "This is a notice from USCIS scheduling your asylum interview.",
        "urgency": "high",
        "verification": "pending",
        "proposed_facts": [],
    }


def demo_brief(case_id: str, brief_id: str) -> dict:
    """A case brief for the demo call, as a `CaseBrief` (app.contracts.brief).

    Written as research would write it for the real USCIS Contact Center, not from
    the mock line's tree (CLAUDE.md → the mock agency is a test target): the menu
    path describes options by meaning, with no key numbers, since real menus
    change and the phone agent decides from what it hears."""
    return {
        "brief_id": brief_id,
        "case_id": case_id,
        "doc_type": "uscis_i797c_asylum_interview",
        "issuer": "USCIS",
        "deadline": DEMO_INTERVIEW_DATE.isoformat(),
        "appointment": {
            "date": DEMO_INTERVIEW_DATE.isoformat(),
            "time": "08:30",
            "location_ref": "<ref:interview_location>",
            "citation": "p1",
        },
        "call_goal_en": (
            "Confirm the asylum interview is still scheduled; ask what to do if "
            "the interpreter can't come"
        ),
        "expected_menu_path": [
            "If offered a language choice, choose English",
            (
                "Choose the option for an existing case, or for an interview or "
                "appointment notice"
            ),
            (
                "If asked for a receipt number, A-Number, or date of birth, don't "
                "give it (C35): say the caller doesn't have it, or pick the option "
                "for callers without one. Don't stay silent; menus hang up on silence"
            ),
            "If asked why you're calling, state the call goal plainly",
            (
                "If a choice would commit the applicant to something (such as "
                "rescheduling), ask the user first"
            ),
            (
                "Ask for a representative when the menu allows it; hold until a "
                "person answers, then bring in the user"
            ),
        ],
        "questions_to_ask": [
            (
                f"Is the interview on {DEMO_INTERVIEW_DATE:%B} "
                f"{DEMO_INTERVIEW_DATE.day} at 8:30 AM still scheduled?"
            ),
            (
                "If the interpreter can't come, what should the applicant do before "
                "the interview?"
            ),
        ],
        "must_not_do": [
            "Never give the A-Number, receipt number, or date of birth",
            "Never discuss the asylum claim",
        ],
        "glossary_terms": ["asylum interview", "interpreter", "dependent"],
        "facts": [
            {"field": "receipt_number", "ref": "<ref:receipt_number>", "page": 1},
            {"field": "a_number", "ref": "<ref:a_number>", "page": 1},
            {
                "field": "interview_location",
                "ref": "<ref:interview_location>",
                "page": 1,
            },
        ],
        "handoff_note": DEMO_HANDOFF_NOTE,
        "likely_rep_questions": [
            {
                "question": "What is the applicant's full name and date of birth?",
                "answer_source": "user, once bridged",
            },
            {
                "question": "What is the receipt number or A-Number?",
                "answer_source": "user, once bridged",
            },
            {
                "question": "What is the mailing address on file?",
                "answer_source": "user, once bridged",
            },
        ],
        "contingencies": [
            (
                "If the representative asks identity questions before the user "
                "joins, say the applicant will answer them and bring the user in"
            ),
            "If the interview was moved, ask for the new date and time",
            (
                "If the representative says interview questions go to the local "
                "asylum office, ask how to contact that office"
            ),
        ],
        "open_uncertainties": ["Whether the applicant's interpreter is available"],
    }


DEMO_HANDOFF_NOTE = (
    "Calling the USCIS Contact Center to confirm an asylum interview and ask "
    "about the interpreter. The applicant answers all identity questions in their "
    "own voice once bridged."
)


async def seed(after_call: bool = False) -> str:
    """Seed one user and one explained, verified case with a brief, ready for
    consent, plus the WhatsApp exchange, memory, and feed events that led there.
    With `after_call`, the user also consented and the call has ended. Returns the
    case ID."""
    official_phone = get_settings().twilio_mock_agency_number or None
    user = tables.User(whatsapp_number=DEMO_WHATSAPP_NUMBER, language="es")
    media = tables.Media(
        user_id=user.id, content_type="image/png", data=placeholder_letter_png()
    )
    story = Story(user.id, "", utcnow() - timedelta(days=2))
    document = tables.Document(
        user_id=user.id,
        pages=[{"media_id": media.id, "added_at": story.at(0).isoformat()}],
        created_at=story.at(0),
    )
    case = tables.Case(
        user_id=user.id,
        document_ids=[document.id],
        doc_type="uscis_i797c_asylum_interview",
        deadline=DEMO_INTERVIEW_DATE,
        created_at=story.at(0),
    )
    story.case_id = case.id
    case.fast_result = demo_fast_result(case.id)
    refs = [
        tables.CaseRef(case_id=case.id, name=name, value=value)
        for name, value in DEMO_REFS.items()
    ]
    brief = tables.CaseBrief(case_id=case.id, handoff_note=DEMO_HANDOFF_NOTE)
    brief.brief = demo_brief(case.id, brief.id)
    verification = tables.Verification(
        case_id=case.id,
        status=VerificationStatus.VERIFIED,
        official_phone=official_phone,
        result={
            "status": "verified",
            "official_phone": official_phone,
            "letter_phone_matches": None,
            "evidence": ["https://www.uscis.gov/contactcenter"],
            "red_flags": [],
        },
    )
    async with session() as db:
        # No ORM relationships, so flush parents before children ourselves.
        db.add(user)
        await db.flush()
        db.add_all([case, media, document])
        await db.flush()
        db.add_all(
            [*refs, brief, verification, *story.before_call(media.id, document.id)]
        )
        if after_call:
            consent, consented = story.consent(minutes=6)
            db.add_all([consent, consented])
            await db.flush()
            job, call, rest = story.finished_call(brief.id, consent, minutes=7)
            db.add(job)
            await db.flush()
            db.add(call)
            await db.flush()
            db.add_all(rest)
        await db.commit()
    if official_phone is None:
        print("TWILIO_MOCK_AGENCY_NUMBER is unset: the seed has no dialable number.")
    return case.id


async def seed_mariam_story(whatsapp_number: str) -> str:
    """Mariam and her finished Medi-Cal case. Returns her user ID."""
    story = seed_mariam.build(whatsapp_number)
    async with session() as db:
        db.add(story.user)
        await db.flush()
        db.add_all([story.case, story.media, story.document])
        await db.flush()
        db.add_all([story.fast_job, story.deep_job])
        await db.flush()
        db.add_all(
            [
                story.verification(),
                *story.profile_and_facts(),
                *story.messages(),
                *story.research_events(),
            ]
        )
        await db.commit()
    return story.user.id


async def reset(
    empty: bool, after_call: bool, story: str = "ana", number: str | None = None
) -> None:
    try:
        await drop_all()
        await create_all()
        if not empty and story == "mariam":
            assert number is not None
            user_id = await seed_mariam_story(number)
            print(f"Seeded Mariam ({user_id}).")
        elif not empty:
            case_id = await seed(after_call)
            print(f"Seeded demo case {case_id}.")
        # After the seed: the loader replaces the seed's few placeholder terms.
        terms = await glossary_load.load(glossary_load.read_rows())
        print(f"Loaded {terms} glossary terms.")
    finally:
        await get_engine().dispose()


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    host = target_host()
    print(f"Target database: {host}")
    if not args.yes:
        print("This wipes every table on the shared database. Re-run with --yes.")
        return 2
    asyncio.run(reset(args.empty, args.after_call, args.story, args.number))
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
