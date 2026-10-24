from datetime import date

from research.eval_harness import Expected, FixtureRuns, compare, percentile, report
from research.fake import fake_fast_pass_output


def expected(**overrides: object) -> Expected:
    data: dict[str, object] = {
        "status": "ok",
        "doc_type_prefix": "generic_",
        "issuer_contains": ["Nope", "example agency"],
        "deadline": "2030-01-15",
        "url_domains": ["example.gov"],
        "phones_e164": [],
        "checklist_min": {"who_must_come": 0, "bring": 1},
        "sensitive_fields": ["case_number"],
        "forbidden_strings": ["EXA0000000000"],
        "payment_instructions_present": False,
    }
    data.update(overrides)
    return Expected.model_validate(data)


def test_passing_case() -> None:
    results = compare(fake_fast_pass_output(), expected())
    assert all(r.passed for r in results), [r for r in results if not r.passed]
    assert len(results) == 10


def test_failing_case() -> None:
    out = fake_fast_pass_output()
    results = compare(
        out,
        expected(
            deadline=date(2030, 2, 1),
            url_domains=["uscis.gov"],
            phones_e164=["+15105550142"],
            sensitive_fields=["case_number", "a_number"],
            forbidden_strings=["EX-100"],
            payment_instructions_present=True,
        ),
    )
    failed = {r.field for r in results if not r.passed}
    assert failed == {
        "deadline",
        "url_domains",
        "phones_e164",
        "sensitive_fields",
        "no_leaks",
        "payment_instructions",
    }
    leak = next(r for r in results if r.field == "no_leaks")
    assert "EX-100" not in leak.detail


def test_subdomain_matches_domain() -> None:
    out = fake_fast_pass_output()
    out.signals.urls = ["https://egov.uscis.gov/status"]
    [result] = [
        r
        for r in compare(out, expected(url_domains=["uscis.gov"]))
        if r.field == "url_domains"
    ]
    assert result.passed


def test_report_fails_on_error_and_slow_p95() -> None:
    good = compare(fake_fast_pass_output(), expected())
    fast_ok = FixtureRuns("a", latencies=[5.0], results=[good])
    table, ok = report([fast_ok], runs=1)
    assert ok and "RESULT: PASS" in table

    errored = FixtureRuns("b", latencies=[1.0], errors=["TimeoutError"])
    assert not report([fast_ok, errored], runs=1)[1]

    slow = FixtureRuns("c", latencies=[40.0], results=[good])
    assert not report([slow], runs=1)[1]


def test_percentile() -> None:
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10
