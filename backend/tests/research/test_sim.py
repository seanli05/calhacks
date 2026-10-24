import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from app.research.fake import fake_fast_pass_output
from app.research.models import R1, FastPassOutput
from app.research.sim.memory import InMemoryStore
from app.research.sim.run import fake_deps, main, simulate


def run_sim(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 0


def test_fake_run_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "state.json"
    run_sim(["--fake", "anything.jpg", "--json-out", str(out)])

    state = json.loads(out.read_text())
    assert [e["type"] for e in state["events"]] == [
        "research.fast_started",
        "research.fast_done",
        "research.deep_started",
        "research.search",
        "research.fetch",
        "research.check",
        "verification.verified",
        "research.deep_done",
    ]
    assert [(j["type"], j["status"]) for j in state["jobs"]] == [
        ("research_fast", "done"),
        ("memory_write", "queued"),
        ("research_deep", "done"),
    ]
    assert len(state["case_briefs"]) == 1
    assert len(state["documents"][0]["pages"]) == 1

    secret = fake_fast_pass_output().sensitive_values[0].value
    printed = capsys.readouterr().out
    assert secret not in printed and secret not in out.read_text()
    assert "=== Timeline ===" in printed and "=== Rows written ===" in printed


def test_unreadable_photo_stops_before_deep(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "state.json"
    run_sim(["--fake", "letter.heic", "--json-out", str(out)])

    state = json.loads(out.read_text())
    assert [j["type"] for j in state["jobs"]] == ["research_fast"]
    assert "Tip:" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_needs_user_input_queues_deep_with_answers() -> None:
    async def asks(blocks: list[Any], *, case_id: str, **_: Any) -> FastPassOutput:
        out = fake_fast_pass_output(case_id)
        r1 = R1(case_id=case_id, status="needs_user_input", question_en="Which county?")
        return out.model_copy(update={"r1": r1})

    store = InMemoryStore()
    deps = dataclasses.replace(fake_deps(), fast_pass_fn=asks)
    await simulate(store, deps, [Path("p1.jpg")], {"county": "Alameda"}, lambda q: {})

    deep = next(j for j in store.jobs.values() if j.type == "research_deep")
    assert deep.payload["answers"] == {"county": "Alameda"}
    assert deep.status == "done"
