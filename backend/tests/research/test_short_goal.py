from types import SimpleNamespace
from typing import Any

import pytest
from app.research.short_goal import clean_goal, shorten_goal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Confirm your interview is still scheduled",
            "Confirm your interview is still scheduled",
        ),
        (
            '"Confirm your interview is still scheduled."\n',
            "Confirm your interview is still scheduled",
        ),
        ("Ask about your form\nBecause the letter says so", "Ask about your form"),
        (" ".join(["word"] * 13), None),
        ("", None),
        ("  .  ", None),
    ],
)
def test_clean_goal(raw: str, expected: str | None) -> None:
    assert clean_goal(raw) == expected


class FakeMessages:
    def __init__(self, stop_reason: str, text: str) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = SimpleNamespace(
            stop_reason=stop_reason,
            content=[SimpleNamespace(type="text", text=text)],
        )

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self._response


async def test_shorten_goal_sends_the_goal_and_cleans_the_answer() -> None:
    messages = FakeMessages("end_turn", "Confirm your interview is still scheduled.")
    client: Any = SimpleNamespace(messages=messages)

    goal = (
        "Ask the asylum office about the interview, rescheduling, or remote attorneys"
    )
    short = await shorten_goal(goal, client=client, model="fast")

    assert short == "Confirm your interview is still scheduled"
    [call] = messages.calls
    assert call["model"] == "fast"
    assert call["messages"] == [{"role": "user", "content": goal}]


async def test_shorten_goal_ignores_a_cut_off_answer() -> None:
    client: Any = SimpleNamespace(messages=FakeMessages("max_tokens", "Confirm your"))
    assert (
        await shorten_goal("Confirm the interview", client=client, model="fast") is None
    )
