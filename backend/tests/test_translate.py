"""Two-way translation (Goal 5.1), glossary grounding (5.3), numbers surviving (5.4)
and right-to-left display, on a fake Anthropic client and a fake glossary read."""

import asyncio
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from app.translation.glossary import Glossary
from app.translation.translate import Translator, _Labels, _Translated
from sqlalchemy.exc import OperationalError


class _FakeAnthropic:
    def __init__(
        self,
        text: str | None = None,
        fail: bool = False,
        labels: list[str] | None = None,
        then: str | None = None,
    ) -> None:
        """`then`, if given, is the text of every reply after the first."""
        self.messages = self
        self.requests: list[dict[str, Any]] = []
        self._text = text
        self._fail = fail
        self._labels = labels
        self._then = then

    async def parse(self, **request: Any) -> SimpleNamespace:
        self.requests.append(request)
        if self._fail:
            raise anthropic.APITimeoutError(
                request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            )
        if self._labels is not None:
            return SimpleNamespace(parsed_output=_Labels(labels=self._labels))
        text = self._then if self._then is not None and len(self.requests) > 1 else None
        text = text or self._text
        parsed = _Translated(text=text) if text is not None else None
        return SimpleNamespace(parsed_output=parsed)


def translator(client: _FakeAnthropic, glossary: Glossary | None = None) -> Translator:
    fake: Any = client
    return Translator(fake, "model-fast", glossary=glossary)


async def test_english_needs_no_call() -> None:
    client = _FakeAnthropic("unused")

    assert await translator(client).to_english("hello", "en") == "hello"
    assert await translator(client).from_english("hello", "en") == "hello"
    assert client.requests == []


async def test_from_english_asks_for_formal_spanish() -> None:
    client = _FakeAnthropic("Su entrevista es el 18 de noviembre.")

    text = await translator(client).from_english(
        "Your interview is on November 18.", "es"
    )

    assert text == "Su entrevista es el 18 de noviembre."
    [request] = client.requests
    assert "Spanish" in request["system"]
    assert "usted" in request["system"]
    assert "<ref:receipt_number>" in request["system"]  # refs pass through
    assert request["timeout"] > 0


async def test_to_english_names_the_source_language() -> None:
    client = _FakeAnthropic("What does my letter say?")

    assert await translator(client).to_english("¿Qué dice mi carta?", "es") == (
        "What does my letter say?"
    )
    assert "written in Spanish" in client.requests[0]["system"]


async def test_failure_returns_none() -> None:
    assert await translator(_FakeAnthropic(fail=True)).to_english("hola", "es") is None
    assert await translator(_FakeAnthropic("  ")).from_english("hi", "es") is None


async def test_dari_asks_for_afghan_dari_not_iranian_farsi() -> None:
    client = _FakeAnthropic("مصاحبهٔ شما در ۱۸ نومبر ۲۰۲۶ است.")

    await translator(client).from_english(
        "Your interview is on November 18, 2026.", "fa"
    )

    system = client.requests[0]["system"]
    assert "Dari (Afghan Persian)" in system
    assert "not Iranian Farsi" in system
    assert "نومبر" in system  # Afghan month names
    assert "never move a date to another calendar" in system


async def test_dari_numbers_count_in_persian_digits() -> None:
    """5.4: "18" and "۱۸" are the same number; the translation is kept."""
    text = await translator(
        _FakeAnthropic("مصاحبهٔ شما ساعت ۸:۳۰ صبح، ۱۸ نومبر ۲۰۲۶ است.")
    ).from_english("Your interview is at 8:30 AM on November 18, 2026.", "fa")

    assert text == "مصاحبهٔ شما ساعت ۸:۳۰ صبح، ۱۸ نومبر ۲۰۲۶ است."


@pytest.mark.parametrize(
    ("english", "translated"),
    [
        ("Your interview is on November 18, 2026.", "مصاحبهٔ شما ۲۷ عقرب ۱۴۰۵ است."),
        ("Your interview is on November 18, 2026.", "مصاحبهٔ شما ۱۹ نومبر ۲۰۲۶ است."),
        ("Your interview is on November 18, 2026.", "مصاحبهٔ شما در ماه نومبر است."),
        ("The interview is still on for Nov 18.", "مصاحبه هنوز ۱۸ نومبر ۲۰۲۶ است."),
    ],
    ids=["solar-calendar", "wrong-day", "dropped", "made-up-year"],
)
async def test_a_translation_that_changes_a_date_is_not_used(
    english: str, translated: str
) -> None:
    """Retried once with a reminder; then the caller falls back to its template,
    which carries the date from code."""
    client = _FakeAnthropic(translated)

    assert await translator(client).from_english(english, "fa") is None
    first, retry = client.requests
    assert "changed, dropped, or added a number" in retry["system"]
    assert "changed, dropped, or added a number" not in first["system"]


async def test_a_retry_that_keeps_the_numbers_is_used() -> None:
    client = _FakeAnthropic(
        "مصاحبه هنوز ۱۸ نومبر ۲۰۲۶ است.", then="مصاحبه هنوز ۱۸ نومبر است."
    )

    text = await translator(client).from_english(
        "The interview is still on for Nov 18.", "fa"
    )

    assert text == "مصاحبه هنوز ۱۸ نومبر است."
    assert len(client.requests) == 2


async def test_a_number_spelled_out_in_english_may_come_back_in_digits() -> None:
    client = _FakeAnthropic("فورمه باید ۱۰ روز قبل از مصاحبه برسد.")

    assert await translator(client).from_english(
        "The form is due ten days before the interview.", "fa"
    ) == ("فورمه باید ۱۰ روز قبل از مصاحبه برسد.")
    assert len(client.requests) == 1


async def test_a_translation_that_drops_a_list_item_is_retried_then_not_used() -> None:
    """Seen live: the post-call summary came back without its second next step."""
    english = (
        "Here's how the call with USCIS went:\n"
        "- The interview is still on\n"
        "- If the interpreter can't come, contact the asylum office"
    )
    client = _FakeAnthropic("ادارهٔ USCIS گفت که مصاحبهٔ شما هنوز سر جایش است.")

    assert await translator(client).from_english(english, "fa") is None
    assert len(client.requests) == 2


async def test_context_says_what_a_fragment_is() -> None:
    client = _FakeAnthropic("تأیید اینکه مصاحبه هنوز سر جایش است")

    await translator(client).from_english(
        "Confirm the interview is still scheduled", "fa", context="a call's purpose"
    )

    assert "What the text is: a call's purpose" in client.requests[0]["system"]


async def test_an_inbound_translation_that_changes_a_number_is_not_used() -> None:
    assert (
        await translator(_FakeAnthropic("My interview is on the 19th.")).to_english(
            "مصاحبهٔ من ۱۸ است", "fa"
        )
        is None
    )


async def test_dari_output_isolates_its_latin_fragments() -> None:
    text = await translator(
        _FakeAnthropic("فورمهٔ I-797C از ادارهٔ USCIS است.")
    ).from_english("Form I-797C is from USCIS.", "fa")

    assert text == "فورمهٔ \u2068I-797C\u2069 از ادارهٔ \u2068USCIS\u2069 است."


async def test_spanish_output_gets_no_isolates() -> None:
    text = await translator(_FakeAnthropic("El formulario I-797C.")).from_english(
        "Form I-797C.", "es"
    )

    assert text == "El formulario I-797C."


async def test_labels_that_change_a_number_are_refused() -> None:
    client = _FakeAnthropic(labels=["گزینهٔ ۳", "وضعیت دوسیه"])

    assert (
        await translator(client).labels_from_english(["Press 2", "Case status"], "fa")
        is None
    )


OPTIONS = ["Speak to a representative", "Case status"]


async def test_labels_keep_their_order_and_count() -> None:
    client = _FakeAnthropic(labels=["Hablar con un representante", "Estado del caso"])

    labels = await translator(client).labels_from_english(OPTIONS, "es")

    assert labels == ["Hablar con un representante", "Estado del caso"]
    [request] = client.requests
    assert "usted" in request["system"]
    assert _Labels.model_validate_json(request["messages"][0]["content"]).labels == (
        OPTIONS
    )


async def test_labels_that_dont_line_up_are_refused() -> None:
    """A dropped or merged label would shift every number the user picks from."""
    assert (
        await translator(_FakeAnthropic(labels=["Uno"])).labels_from_english(
            OPTIONS, "es"
        )
        is None
    )
    assert (
        await translator(_FakeAnthropic(labels=["Uno", " "])).labels_from_english(
            OPTIONS, "es"
        )
        is None
    )
    assert (
        await translator(_FakeAnthropic(fail=True)).labels_from_english(OPTIONS, "es")
        is None
    )


async def test_english_labels_need_no_call() -> None:
    client = _FakeAnthropic(labels=["unused"])

    assert await translator(client).labels_from_english(OPTIONS, "en") == OPTIONS
    assert client.requests == []


TERMS = [
    ("asylum interview", "entrevista de asilo"),
    ("asylum", "asilo"),
    ("interpreter", "intérprete"),
    ("receipt number", "número de recibo"),
    ("case status", "estatus de caso"),
    ("deadline", "plazo límite"),
]


class _FakeGlossaryRead:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    async def __call__(self, language: str) -> list[SimpleNamespace]:
        self.calls.append(language)
        if self.fail:
            raise OperationalError("select", {}, OSError("connection refused"))
        return [SimpleNamespace(term=t, translation=tr) for t, tr in TERMS]


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_from_english_carries_only_the_terms_the_text_uses() -> None:
    client = _FakeAnthropic("Traiga un intérprete a su entrevista de asilo.")

    await translator(client, Glossary(_FakeGlossaryRead())).from_english(
        "Bring an interpreter to your asylum interview.", "es"
    )

    system = client.requests[0]["system"]
    assert "- asylum interview → entrevista de asilo" in system
    assert "- interpreter → intérprete" in system
    assert "- asylum → asilo" in system
    assert "plazo límite" not in system
    assert "estatus de caso" not in system


async def test_to_english_matches_without_accents_and_in_the_plural() -> None:
    """Users type "interpretes" for "intérpretes"; the term still applies."""
    client = _FakeAnthropic("Can I bring interpreters?")

    await translator(client, Glossary(_FakeGlossaryRead())).to_english(
        "¿Puedo llevar interpretes?", "es"
    )

    assert "- intérprete → interpreter" in client.requests[0]["system"]


async def test_an_english_verb_brings_in_its_noun_term() -> None:
    """ "Can be dismissed" must use the glossary's dismissal, not drift into the Dari
    word for a denial."""

    async def dari(language: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(term="dismissal", translation="لغو درخواست (dismissal)"),
            SimpleNamespace(term="denial", translation="رد"),
            SimpleNamespace(term="reschedule", translation="تعیین وقت مجدد"),
        ]

    client = _FakeAnthropic("درخواست شما لغو می‌شود.")

    await translator(client, Glossary(dari)).from_english(
        "Your application can be dismissed. Ask Denis about rescheduling.", "fa"
    )

    system = client.requests[0]["system"]
    assert "- dismissal → لغو درخواست (dismissal)" in system
    assert "- reschedule → تعیین وقت مجدد" in system
    assert "- denial" not in system


async def test_dari_matches_plurals_letter_forms_and_the_non_joiner() -> None:
    """Users write "متقاضیان" for applicants, Arabic ي for ی, and ‌ها plurals."""

    async def dari(language: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(term="applicant", translation="متقاضی"),
            SimpleNamespace(term="interpreter", translation="ترجمان"),
            SimpleNamespace(term="deadline", translation="مهلت"),
        ]

    client = _FakeAnthropic("The applicants need interpreters.")

    await translator(client, Glossary(dari)).to_english(
        "متقاضيان به ترجمان‌ها ضرورت دارند", "fa"
    )

    system = client.requests[0]["system"]
    assert "- متقاضی → applicant" in system
    assert "- ترجمان → interpreter" in system
    assert "مهلت" not in system


async def test_a_ref_placeholder_is_not_a_glossary_term() -> None:
    client = _FakeAnthropic("Su número es <ref:receipt_number>.")

    await translator(client, Glossary(_FakeGlossaryRead())).from_english(
        "Your number is <ref:receipt_number>.", "es"
    )

    assert "Glossary" not in client.requests[0]["system"]


async def test_labels_are_grounded_too() -> None:
    client = _FakeAnthropic(labels=["Hablar con un representante", "Estado"])

    await translator(client, Glossary(_FakeGlossaryRead())).labels_from_english(
        OPTIONS, "es"
    )

    assert "- case status → estatus de caso" in client.requests[0]["system"]


async def test_english_reads_no_glossary() -> None:
    read = _FakeGlossaryRead()

    await translator(_FakeAnthropic("unused"), Glossary(read)).from_english(
        "hello", "en"
    )

    assert read.calls == []


async def test_glossary_is_read_once_per_language_until_it_expires() -> None:
    read, clock = _FakeGlossaryRead(), _Clock()
    grounded = translator(_FakeAnthropic("ok"), Glossary(read, ttl_s=600, clock=clock))

    await grounded.from_english("asylum", "es")
    await grounded.to_english("asilo", "es")
    clock.now = 601
    await grounded.from_english("asylum", "es")

    assert read.calls == ["es", "es"]


async def test_a_failed_glossary_read_doesnt_stop_translation() -> None:
    read, clock = _FakeGlossaryRead(fail=True), _Clock()
    client = _FakeAnthropic("Su entrevista de asilo.")
    grounded = translator(client, Glossary(read, clock=clock))

    assert await grounded.from_english("Your asylum interview.", "es") == (
        "Su entrevista de asilo."
    )
    await grounded.from_english("Your asylum interview.", "es")

    assert "Glossary" not in client.requests[0]["system"]
    assert read.calls == ["es"]  # not retried on every translation


async def test_a_slow_glossary_read_times_out() -> None:
    async def hang(language: str) -> list[SimpleNamespace]:
        await asyncio.sleep(10)
        return []

    client = _FakeAnthropic("Hola.")

    assert await translator(client, Glossary(hang, timeout_s=0.01)).from_english(
        "Hello.", "es"
    ) == ("Hola.")
