"""Two-way translation (Goal 5.1) and glossary grounding (5.3) on a fake Anthropic
client and a fake glossary read."""

import asyncio
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
from app.translation.glossary import Glossary
from app.translation.translate import Translator, _Labels, _Translated
from sqlalchemy.exc import OperationalError


class _FakeAnthropic:
    def __init__(
        self,
        text: str | None = None,
        fail: bool = False,
        labels: list[str] | None = None,
    ) -> None:
        self.messages = self
        self.requests: list[dict[str, Any]] = []
        self._text = text
        self._fail = fail
        self._labels = labels

    async def parse(self, **request: Any) -> SimpleNamespace:
        self.requests.append(request)
        if self._fail:
            raise anthropic.APITimeoutError(
                request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            )
        if self._labels is not None:
            return SimpleNamespace(parsed_output=_Labels(labels=self._labels))
        parsed = _Translated(text=self._text) if self._text is not None else None
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
