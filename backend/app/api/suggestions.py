"""Up to three rule-based suggestion cards for the newest active case. No model call:
countdown, then glossary practice, then a checklist reminder. A rule whose data is
missing is skipped."""

from datetime import UTC, date, datetime

from fastapi import APIRouter

from app.api.case_views import fast_result_of
from app.api.common import LangQuery, resolve_language
from app.api.models import Localized, Suggestion
from app.api.suggestion_templates import TEXTS
from app.contracts import ChecklistKind, FastResult
from app.db import reads, tables

router = APIRouter()

MAX_GLOSSARY_TERMS = 3


def today() -> date:
    return datetime.now(UTC).date()


@router.get("/users/{user_id}/suggestions")
async def suggestions(user_id: str, lang: LangQuery = None) -> list[Suggestion]:
    lang = await resolve_language(user_id, lang)
    cases = await reads.list_active_cases(user_id)
    if not cases:
        return []
    case = cases[0]
    fast = fast_result_of(case)
    cards = [
        _countdown(case, fast, lang),
        await _glossary(case, lang),
        _checklist(case, fast, lang),
    ]
    return [card for card in cards if card is not None]


class _Texts:
    def __init__(self, lang: str) -> None:
        self.lang = lang

    def get(self, key: str, **values: str) -> Localized:
        return Localized(
            text=self.raw(key, **values), en=TEXTS["en"][key].format(**values)
        )

    def raw(self, key: str, **values: str) -> str:
        texts = TEXTS.get(self.lang, TEXTS["en"])
        return texts.get(key, TEXTS["en"][key]).format(**values)


def _countdown(
    case: tables.Case, fast: FastResult | None, lang: str
) -> Suggestion | None:
    target = fast.appointment.date if fast and fast.appointment else case.deadline
    if target is None:
        return None
    days = (target - today()).days
    if days <= 0:
        return None
    noun = "interview" if "interview" in (case.doc_type or "") else "appointment"
    texts = _Texts(lang)
    title_key = f"countdown_title_{noun}" + ("_1" if days == 1 else "")
    return Suggestion(
        id=f"countdown_{case.id}",
        kind="countdown",
        case_id=case.id,
        title=texts.get(title_key, days=str(days)),
        detail=texts.get("countdown_detail"),
        action=texts.get("countdown_action"),
        prefill=texts.raw(f"countdown_prefill_{noun}"),
    )


async def _glossary(case: tables.Case, lang: str) -> Suggestion | None:
    """The brief's `glossary_terms` that the glossary has in the user's language.
    The brief's shape is provisional, so the field is read defensively."""
    brief = await reads.latest_brief(case.id)
    terms = brief.brief.get("glossary_terms") if brief else None
    if not isinstance(terms, list):
        return None
    known = {row.term.lower() for row in await reads.get_glossary(lang)}
    matched = [t for t in terms if isinstance(t, str) and t.lower() in known]
    if not matched:
        return None
    detail = " · ".join(matched[:MAX_GLOSSARY_TERMS])
    texts = _Texts(lang)
    return Suggestion(
        id=f"glossary_{case.id}",
        kind="glossary",
        case_id=case.id,
        title=texts.get("glossary_title"),
        detail=Localized(text=detail, en=detail),
        action=texts.get("glossary_action"),
        prefill=texts.raw("glossary_prefill"),
    )


def _checklist(
    case: tables.Case, fast: FastResult | None, lang: str
) -> Suggestion | None:
    """The first thing to bring, else the first person who must come."""
    items = fast.checklist_en if fast else []
    for kind in (ChecklistKind.BRING, ChecklistKind.WHO_MUST_COME):
        entry = next((i for i in items if i.kind == kind), None)
        if entry is not None:
            break
    else:
        return None
    item = _lower_first(entry.item)
    texts = _Texts(lang)
    return Suggestion(
        id=f"checklist_{case.id}",
        kind="checklist",
        case_id=case.id,
        title=texts.get("checklist_title", item=item),
        detail=texts.get("checklist_detail"),
        action=texts.get("checklist_action"),
        prefill=texts.raw("checklist_prefill", item=item),
    )


def _lower_first(text: str) -> str:
    """`A qualified interpreter` → `a qualified interpreter`; leaves `ID …` alone."""
    word = text.split(" ", 1)[0]
    if word[:1].isupper() and (len(word) == 1 or word[1:].islower()):
        return text[0].lower() + text[1:]
    return text
