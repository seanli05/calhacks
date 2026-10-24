"""The dashboard's translation cache: English first, the translation on a later
poll, and no model call per poll when translating fails."""

import asyncio

import pytest
from app.api import translations
from app.api.common import localize
from app.api.stand_in_es import SPANISH


class FakeTranslator:
    def __init__(self, result: str | None = "Traído") -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    async def from_english(self, text_en: str, language: str) -> str | None:
        self.calls.append((text_en, language))
        return self.result


@pytest.fixture
def translator(monkeypatch: pytest.MonkeyPatch) -> FakeTranslator:
    fake = FakeTranslator()
    monkeypatch.setattr(translations, "get_translator", lambda: fake)
    return fake


async def _settle() -> None:
    while translations._tasks:
        await asyncio.gather(*translations._tasks)


async def test_english_first_then_the_translation(translator: FakeTranslator) -> None:
    first = localize("Bring your passport", "es")
    assert first.text == "Bring your passport"
    assert first.en == "Bring your passport"
    localize("Bring your passport", "es")  # a second poll before it lands
    await _settle()

    assert localize("Bring your passport", "es").text == "Traído"
    assert translator.calls == [("Bring your passport", "es")]


async def test_a_failure_isnt_retried_every_poll(translator: FakeTranslator) -> None:
    translator.result = None
    localize("Bring your passport", "es")
    await _settle()
    localize("Bring your passport", "es")
    await _settle()

    assert localize("Bring your passport", "es").text == "Bring your passport"
    assert len(translator.calls) == 1


async def test_seed_strings_and_english_skip_the_model(
    translator: FakeTranslator,
) -> None:
    seeded = next(iter(SPANISH))
    assert localize(seeded, "es").text == SPANISH[seeded]
    assert localize("Bring your passport", "en").text == "Bring your passport"
    await _settle()

    assert translator.calls == []


def test_outside_the_event_loop_it_stays_english(translator: FakeTranslator) -> None:
    assert localize("Bring your passport", "es").text == "Bring your passport"
    assert translator.calls == []
