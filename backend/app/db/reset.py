"""Drop and recreate every table, then seed the demo case.

    python -m app.db.reset --yes          # rebuild and seed
    python -m app.db.reset --yes --empty  # rebuild, no seed

The database is shared by the whole team, so this wipes everyone's data; it refuses
to run without --yes. It's a dev tool, so seeding writes several owners' tables.
Seed values match mock_agency/agency/case_record.py (DEMO_CASE). All fictional.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import date
from urllib.parse import urlsplit

from app.contracts.common import Component, VerificationStatus
from app.db import tables
from app.db.engine import get_engine, session
from app.db.schema import create_all, drop_all
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
    return parser.parse_args(argv)


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
                "item": "ID for you and each dependent",
                "citation": "p1 §II",
            },
        ],
        "key_facts": [
            {
                "field": "receipt_number",
                "ref": "<ref:receipt_number>",
                "citation": "p1",
            },
            {"field": "a_number", "ref": "<ref:a_number>", "citation": "p1"},
        ],
        "explanation_en": "This is a notice from USCIS scheduling your asylum interview.",
        "urgency": "high",
        "verification": "verified",
        "proposed_facts": [],
    }


async def seed() -> str:
    """Seed one user, one explained and verified case. Returns the case ID."""
    official_phone = get_settings().twilio_mock_agency_number or None
    user = tables.User(whatsapp_number=DEMO_WHATSAPP_NUMBER, language="es")
    case = tables.Case(
        user_id=user.id,
        doc_type="uscis_i797c_asylum_interview",
        deadline=DEMO_INTERVIEW_DATE,
    )
    case.fast_result = demo_fast_result(case.id)
    refs = [
        tables.CaseRef(case_id=case.id, name=name, value=value)
        for name, value in DEMO_REFS.items()
    ]
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
    events = [
        tables.Event(
            type="case.created",
            source=Component.RESEARCH_AGENT,
            user_id=user.id,
            case_id=case.id,
            summary_en="Case created (seed)",
        ),
        tables.Event(
            type="verification.verified",
            source=Component.RESEARCH_AGENT,
            user_id=user.id,
            case_id=case.id,
            summary_en="Letter verified against uscis.gov (seed)",
        ),
    ]
    async with session() as db:
        # The unit of work inserts in foreign-key order.
        db.add_all([user, case, *refs, verification, *events])
        await db.commit()
    if official_phone is None:
        print("TWILIO_MOCK_AGENCY_NUMBER is unset: the seed has no dialable number.")
    return case.id


async def reset(empty: bool) -> None:
    try:
        await drop_all()
        await create_all()
        if not empty:
            case_id = await seed()
            print(f"Seeded demo case {case_id}.")
    finally:
        await get_engine().dispose()


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    host = target_host()
    print(f"Target database: {host}")
    if not args.yes:
        print("This wipes every table on the shared database. Re-run with --yes.")
        return 2
    asyncio.run(reset(args.empty))
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
