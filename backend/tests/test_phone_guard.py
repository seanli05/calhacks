"""C35 at the line: identifiers never go out, however they're split or spelled."""

import pytest
from app.phone.fakes import (
    FakeClock,
    FakeNumberSource,
    FakeTelephony,
    PressedKeys,
    Said,
)
from app.phone.guard import BlockedIdentifier, GuardedTelephony, spoken_digits

RECEIPT = "ZLA2690012345"
A_NUMBER = "A212345678"
BIRTH_DATE = "1988-03-14"


async def _line() -> tuple[GuardedTelephony, FakeTelephony]:
    inner = FakeTelephony(
        FakeNumberSource(verified={"case_123": "+18005550100"}), FakeClock()
    )
    await inner.dial_agency("call_5", "case_123")
    return GuardedTelephony(inner, [RECEIPT, A_NUMBER, BIRTH_DATE]), inner


def test_spoken_digits_reads_digit_words_but_not_inside_words() -> None:
    assert spoken_digits("press two, then 4") == "24"
    assert spoken_digits("someone will be with you") == ""


@pytest.mark.parametrize(
    "text",
    [
        f"The receipt number is {RECEIPT}",
        "A as in apple, two one two three four five six seven eight",
        "born 1988 03 14",
    ],
)
async def test_blocks_identifiers_in_speech(text: str) -> None:
    line, inner = await _line()
    with pytest.raises(BlockedIdentifier) as raised:
        await line.say(text)
    assert inner.actions[1:] == []
    assert "212345678" not in str(raised.value)


async def test_blocks_an_identifier_keyed_a_few_digits_at_a_time() -> None:
    line, inner = await _line()
    await line.press_keys("1988")
    await line.press_keys("03")
    with pytest.raises(BlockedIdentifier):
        await line.press_keys("14")
    assert inner.actions[1:] == [PressedKeys("1988"), PressedKeys("03")]


async def test_menu_choices_go_through() -> None:
    line, inner = await _line()
    for _ in range(10):
        await line.say("two")
        await line.press_keys("2")
    await line.say("representative")
    assert inner.actions[-1] == Said("representative")


async def test_keys_must_be_keypad_keys() -> None:
    line, _ = await _line()
    with pytest.raises(ValueError):
        await line.press_keys("2w")


async def test_repr_hides_the_values() -> None:
    line, _ = await _line()
    assert RECEIPT not in repr(line)
