from datetime import UTC, datetime

from app.api.stand_in_es import SPANISH
from app.db import tables
from app.db.reset import demo_brief, demo_fast_result
from app.db.seed_story import Story


def _seed_strings() -> list[str]:
    """Every English string the seed writes that the API localizes."""
    fast = demo_fast_result("case_1")
    brief = demo_brief("case_1", "brief_1")
    story = Story("user_1", "case_1", datetime(2026, 10, 1, tzinfo=UTC))
    facts = [
        r.fact
        for r in story.before_call("media_1", "doc_1")
        if isinstance(r, tables.Fact)
    ]
    consent, _ = story.consent(6)
    _, call, _ = story.finished_call("brief_1", consent, 7)
    return [
        fast["explanation_en"],
        fast["what_is_asked"],
        *(item["item"] for item in fast["checklist_en"]),
        brief["call_goal_en"],
        *brief["questions_to_ask"],
        *facts,
        *call.report["next_steps_en"],
    ]


def test_every_seed_string_has_spanish() -> None:
    missing = [en for en in _seed_strings() if en not in SPANISH]
    assert missing == []
