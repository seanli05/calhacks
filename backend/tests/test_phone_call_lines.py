"""The applicant's join prompt (`call_lines.JOIN_PROMPTS`): one per language we talk
to users in (rule 6), and fixed text with nothing about them in it."""

import pytest
from app.phone.call_lines import JOIN_PROMPTS, JoinPrompt, join_prompt
from app.relay.templates import LANGUAGES


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_language_users_write_in_has_a_join_prompt(language: str) -> None:
    assert language in JOIN_PROMPTS


def test_spanish_is_spoken_by_a_spanish_voice() -> None:
    prompt = join_prompt("es")
    assert prompt.say_language == "es-US"
    assert "tecla" in prompt.text


def test_a_language_with_no_prompt_yet_gets_english() -> None:
    assert join_prompt("fa") == JOIN_PROMPTS["en"]


@pytest.mark.parametrize("prompt", JOIN_PROMPTS.values())
def test_the_prompt_carries_no_digits(prompt: JoinPrompt) -> None:
    """Nothing case-specific: no numbers of any kind (C35)."""
    assert not any(ch.isdigit() for ch in prompt.text)
