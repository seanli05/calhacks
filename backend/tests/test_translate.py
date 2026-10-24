"""Minimal two-way translation (Goal 5.1) on a fake Anthropic client."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
from app.translation.translate import Translator, _Labels, _Translated


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


def translator(client: _FakeAnthropic) -> Translator:
    fake: Any = client
    return Translator(fake, "model-fast")


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
