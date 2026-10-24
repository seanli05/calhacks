"""research_question with a scripted fake client and a fake web. No network."""

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from research.fetch_tool import replay_resolver
from research.jobs import handle_research_question
from research.models import QuestionAnswer, QuestionSource
from research.question import answer_question, scrub_question
from research.sim.memory import InMemoryStore
from research.sim.run import fake_deps

GOV = "https://www.uscis.gov/interview"
NOT_GOV = "https://immigration-help.example.com/interview"
QUOTE = "You may bring an interpreter to your asylum interview."
PAGE = f"<html><body><h1>Asylum interviews</h1><p>{QUOTE}</p></body></html>"


def block(type_: str, **fields: Any) -> SimpleNamespace:
    return SimpleNamespace(type=type_, **fields)


def turn(stop_reason: str, *blocks: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


def fetch(url: str) -> SimpleNamespace:
    return block("tool_use", id="f1", name="fetch_page", input={"url": url})


def submit(
    status: str = "answered", url: str = GOV, quote: str = QUOTE
) -> SimpleNamespace:
    answered = status == "answered"
    payload = {
        "status": status,
        "answer_en": "Yes, you can bring an interpreter." if answered else None,
        "sources": [{"url": url, "quote": quote}] if answered else [],
    }
    return block("tool_use", id="s1", name="submit_answer", input=payload)


class FakeClient:
    """Plays scripted turns; records the messages sent on every call."""

    def __init__(self, turns: list[SimpleNamespace]) -> None:
        self._turns = list(turns)
        self.calls: list[list[dict[str, Any]]] = []
        self.beta = SimpleNamespace(messages=self)

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(list(kwargs["messages"]))
        if not self._turns:
            raise AssertionError("unexpected model call")
        return self._turns.pop(0)


def web(status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, html=PAGE)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def ask(
    turns: list[SimpleNamespace],
    question: str = "Can I bring an interpreter?",
    **kw: Any,
) -> tuple[QuestionAnswer, FakeClient]:
    client = FakeClient(turns)
    async with web(kw.pop("status", 200)) as http:
        answer = await answer_question(
            question,
            client=client,  # type: ignore[arg-type]
            model="m",
            http=http,
            resolve=replay_resolver,
            **kw,
        )
    return answer, client


async def test_quote_found_on_fetched_gov_page_is_answered() -> None:
    answer, _ = await ask([turn("tool_use", fetch(GOV)), turn("tool_use", submit())])

    assert answer.status == "answered"
    assert answer.sources == [QuestionSource(url=GOV, quote=QUOTE)]


async def test_quote_not_on_the_page_is_not_confirmed() -> None:
    answer, _ = await ask(
        [
            turn("tool_use", fetch(GOV)),
            turn("tool_use", submit(quote="Interpreters are free.")),
            turn("tool_use", submit(quote="Interpreters are free.")),
        ]
    )
    assert answer.status == "not_confirmed"
    assert answer.answer_en is None


async def test_unfetched_or_non_gov_source_is_not_confirmed() -> None:
    unfetched, client = await ask([turn("tool_use", submit())] * 2)
    assert unfetched.status == "not_confirmed"
    retry = client.calls[1][-1]["content"][0]
    assert retry["is_error"] and "cites the .gov search results" in retry["content"]

    not_gov, _ = await ask(
        [
            turn("tool_use", fetch(NOT_GOV)),
            turn("tool_use", submit(url=NOT_GOV)),
            turn("tool_use", submit(url=NOT_GOV)),
        ]
    )
    assert not_gov.status == "not_confirmed"


async def test_blocked_fetch_falls_back_to_server_web_fetch() -> None:
    fetched = block(
        "web_fetch_tool_result",
        content=block(
            "web_fetch_result",
            url=GOV,
            content=block(
                "document", source=block("text", data=f"Asylum interviews\n{QUOTE}")
            ),
        ),
    )
    turns = [
        turn("tool_use", fetch(GOV)),
        turn(
            "tool_use",
            block("server_tool_use", name="web_fetch", input={"url": GOV}),
            fetched,
            submit(),
        ),
    ]
    answer, client = await ask(turns, status=403)

    assert answer.status == "answered"
    blocked = client.calls[1][-1]["content"][0]
    assert blocked["is_error"] and "web_fetch" in blocked["content"]


async def test_model_declines_pass_through_without_an_answer() -> None:
    answer, _ = await ask([turn("tool_use", submit("declined_legal_advice"))])
    assert answer.status == "declined_legal_advice"
    assert answer.answer_en is None and answer.reason_en


async def test_asylum_claim_question_is_declined_before_any_model_call() -> None:
    answer, client = await ask([], question="What should I say about why I fled?")
    assert answer.status == "declined_asylum_claim"
    assert client.calls == []


async def test_case_values_and_ids_are_scrubbed_before_the_model_sees_them() -> None:
    question = "Ana Prueba here, A123456789, receipt IOE0912345678: can I reschedule?"
    _, client = await ask(
        [turn("tool_use", submit("not_confirmed"))],
        question=question,
        sensitive=["Ana Prueba"],
    )
    sent = client.calls[0][0]["content"]
    for value in ("Ana Prueba", "A123456789", "IOE0912345678"):
        assert value not in sent
    assert scrub_question("ana prueba", ["Ana Prueba"]) == "[redacted]"
    assert scrub_question("Analysis", ["Ana"]) == "Analysis"


def test_answer_contract_needs_sources_and_only_for_answered() -> None:
    with pytest.raises(ValidationError):
        QuestionAnswer(status="answered", answer_en="Yes.")
    with pytest.raises(ValidationError):
        QuestionAnswer(status="not_confirmed", answer_en="Yes.")


async def queue_question(
    store: InMemoryStore, question: str = "Can I bring an interpreter?"
) -> str:
    return await store.create_job(
        "research_question",
        {"job": "research_question", "user_id": "user_1", "question_en": question},
    )


async def test_handler_writes_result_and_keeps_question_out_of_events() -> None:
    store = InMemoryStore()
    job_id = await queue_question(store, "Secret question text?")
    await handle_research_question(store.jobs[job_id], store, fake_deps())

    job = store.jobs[job_id]
    assert job.status == "done"
    assert QuestionAnswer.model_validate(job.result).status == "answered"
    types = [e.type for e in store.events]
    assert types[0] == "research.question_started"
    assert types[-1] == "research.question_done"
    assert all("Secret question" not in e.model_dump_json() for e in store.events)


async def test_handler_timeout_is_not_confirmed() -> None:
    async def slow(*_: Any, **__: Any) -> QuestionAnswer:
        await asyncio.sleep(1)
        raise AssertionError("should have timed out")

    deps = fake_deps()
    deps.question_fn = slow
    deps.question_timeout_s = 0.01
    store = InMemoryStore()
    job_id = await queue_question(store)
    await handle_research_question(store.jobs[job_id], store, deps)

    result = QuestionAnswer.model_validate(store.jobs[job_id].result)
    assert result.status == "not_confirmed"
    assert "research.question_failed" in [e.type for e in store.events]


def cited(url: str, cited_text: str) -> SimpleNamespace:
    citation = block("web_search_result_location", url=url, cited_text=cited_text)
    return block("text", text="Yes.", citations=[citation])


async def test_quote_from_a_gov_search_citation_is_answered() -> None:
    answer, _ = await ask([turn("tool_use", cited(GOV, QUOTE), submit())])
    assert answer.status == "answered"


async def test_citation_from_a_non_gov_site_never_counts() -> None:
    answer, _ = await ask(
        [turn("tool_use", cited(NOT_GOV, QUOTE), submit(url=NOT_GOV))] * 2
    )
    assert answer.status == "not_confirmed"


def text(body: str) -> SimpleNamespace:
    return block("text", text=body, citations=None)


async def test_plain_text_answer_citing_gov_results_is_answered() -> None:
    answer, _ = await ask([turn("end_turn", text("Yes. "), cited(GOV, QUOTE))])

    assert answer.status == "answered"
    assert answer.answer_en == "Yes. Yes."
    assert answer.sources == [QuestionSource(url=GOV, quote=QUOTE)]


async def test_text_with_non_gov_citation_or_long_uncited_claim_is_not_answered() -> (
    None
):
    non_gov, _ = await ask(
        [
            turn("end_turn", cited(GOV, QUOTE), cited(NOT_GOV, "Anything.")),
            turn("tool_use", submit("not_confirmed")),
        ]
    )
    assert non_gov.status == "not_confirmed"

    uncited = text(
        "Interpreters are always provided free of charge by USCIS at every interview. "
    )
    unsupported, _ = await ask(
        [
            turn("end_turn", uncited, cited(GOV, QUOTE)),
            turn("tool_use", submit("not_confirmed")),
        ]
    )
    assert unsupported.status == "not_confirmed"


async def test_sim_report_summarizes_a_question_job() -> None:
    from research.sim.run import job_summary

    store = InMemoryStore()
    job_id = await queue_question(store)
    await handle_research_question(store.jobs[job_id], store, fake_deps())

    assert job_summary(store.jobs[job_id]) == "answer status=answered sources=1"
