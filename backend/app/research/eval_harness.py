"""Score the fast pass against fixture folders: `<fixture>/{page files, expected.json}`."""

import asyncio
import math
import mimetypes
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from anthropic import APIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.research.fast_pass import FastPassError
from app.research.models import FastPassOutput, R1Status
from app.research.preprocess import ContentBlock, UnsupportedMedia, to_content_blocks

PAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
P95_LIMIT_S = 30.0

RunFastPass = Callable[[list[ContentBlock]], Awaitable[FastPassOutput]]


class ChecklistMin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    who_must_come: int = 0
    bring: int = 0


class Expected(BaseModel):
    """expected.json. Every key but `status` is optional; missing keys aren't scored."""

    model_config = ConfigDict(extra="forbid")

    status: R1Status
    doc_type_prefix: str | None = None
    issuer_contains: list[str] | None = Field(
        default=None, description="Passes if the issuer contains any of these"
    )
    deadline: date | None = None
    appointment_date: date | None = None
    appointment_time: str | None = None
    form_ids_contains: list[str] | None = None
    url_domains: list[str] | None = None
    phones_e164: list[str] | None = None
    checklist_min: ChecklistMin | None = None
    sensitive_fields: list[str] | None = None
    forbidden_strings: list[str] | None = None
    payment_instructions_present: bool | None = None


@dataclass
class FieldResult:
    field: str
    passed: bool
    detail: str = ""


@dataclass
class FixtureRuns:
    name: str
    latencies: list[float] = field(default_factory=list)
    results: list[list[FieldResult]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def compare(out: FastPassOutput, exp: Expected) -> list[FieldResult]:
    """Check one fast-pass output against expected.json."""
    r1, signals = out.r1, out.signals
    results = [FieldResult("status", r1.status == exp.status, r1.status)]

    if exp.doc_type_prefix is not None:
        results.append(
            FieldResult(
                "doc_type_prefix",
                (r1.doc_type or "").startswith(exp.doc_type_prefix),
                str(r1.doc_type),
            )
        )
    if exp.issuer_contains is not None:
        results.append(
            FieldResult(
                "issuer_contains",
                any(
                    s.casefold() in (r1.issuer or "").casefold()
                    for s in exp.issuer_contains
                ),
                str(r1.issuer),
            )
        )
    if "deadline" in exp.model_fields_set:
        results.append(
            FieldResult("deadline", r1.deadline == exp.deadline, str(r1.deadline))
        )
    if "appointment_date" in exp.model_fields_set:
        got = r1.appointment.date if r1.appointment else None
        results.append(
            FieldResult("appointment_date", got == exp.appointment_date, str(got))
        )
    if exp.appointment_time is not None:
        got_time = r1.appointment.time if r1.appointment else None
        results.append(
            FieldResult(
                "appointment_time", got_time == exp.appointment_time, str(got_time)
            )
        )
    if exp.form_ids_contains is not None:
        got_forms = " ".join(signals.form_ids).casefold()
        missing = [f for f in exp.form_ids_contains if f.casefold() not in got_forms]
        results.append(
            FieldResult(
                "form_ids", not missing, f"missing {missing}" if missing else ""
            )
        )
    if exp.url_domains is not None:
        domains = {_domain(u) for u in signals.urls}
        missing = [
            d
            for d in exp.url_domains
            if not any(g == d.lower() or g.endswith("." + d.lower()) for g in domains)
        ]
        results.append(
            FieldResult(
                "url_domains",
                not missing,
                f"missing {missing}, got {sorted(domains)}" if missing else "",
            )
        )
    if exp.phones_e164 is not None:
        got_phones = {p.number for p in signals.phones}
        missing = [p for p in exp.phones_e164 if p not in got_phones]
        results.append(
            FieldResult(
                "phones_e164",
                not missing,
                f"missing {missing}, got {sorted(got_phones)}" if missing else "",
            )
        )
    if exp.checklist_min is not None:
        counts = {
            kind: sum(1 for c in r1.checklist_en if c.kind == kind)
            for kind in ("who_must_come", "bring")
        }
        ok = (
            counts["who_must_come"] >= exp.checklist_min.who_must_come
            and counts["bring"] >= exp.checklist_min.bring
        )
        results.append(FieldResult("checklist_min", ok, str(counts)))
    if exp.sensitive_fields is not None:
        refs_in_r1 = {f.ref for f in r1.key_facts if f.ref}
        if r1.appointment and r1.appointment.location_ref:
            refs_in_r1.add(r1.appointment.location_ref)
        held = {sv.field: sv.ref for sv in out.sensitive_values}
        missing = [
            f
            for f in exp.sensitive_fields
            if f not in held or held[f] not in refs_in_r1
        ]
        results.append(
            FieldResult(
                "sensitive_fields", not missing, f"missing {missing}" if missing else ""
            )
        )
    if exp.forbidden_strings is not None:
        shipped = (r1.model_dump_json() + signals.model_dump_json()).casefold()
        leaked = [s for s in exp.forbidden_strings if s.casefold() in shipped]
        # Never print the leaked value itself, only how many.
        results.append(
            FieldResult(
                "no_leaks",
                not leaked,
                f"{len(leaked)} forbidden string(s) found" if leaked else "",
            )
        )
    if exp.payment_instructions_present is not None:
        present = bool(signals.payment_instructions)
        results.append(
            FieldResult(
                "payment_instructions",
                present == exp.payment_instructions_present,
                "present" if present else "absent",
            )
        )
    return results


def find_fixtures(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.glob("*/expected.json"))


async def load_pages(folder: Path) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    for page in sorted(
        p for p in folder.iterdir() if p.suffix.lower() in PAGE_SUFFIXES
    ):
        content_type = mimetypes.guess_type(page.name)[0] or "application/octet-stream"
        blocks.extend(await to_content_blocks(page.read_bytes(), content_type))
    return blocks


async def run_eval(
    fixtures_dir: Path, run_fast_pass: RunFastPass, *, runs: int, timeout_s: float
) -> list[FixtureRuns]:
    """Run every fixture `runs` times. Errors and timeouts count as failed runs."""
    all_runs: list[FixtureRuns] = []
    for folder in find_fixtures(fixtures_dir):
        expected = Expected.model_validate_json((folder / "expected.json").read_text())
        fixture = FixtureRuns(folder.name)
        all_runs.append(fixture)
        try:
            blocks = await load_pages(folder)
        except UnsupportedMedia as e:
            fixture.errors.append(f"UnsupportedMedia: {e}")
            continue
        for _ in range(runs):
            started = time.monotonic()
            try:
                out = await asyncio.wait_for(run_fast_pass(blocks), timeout_s)
            except TimeoutError:
                fixture.errors.append(f"timed out after {timeout_s:.0f}s")
                fixture.latencies.append(time.monotonic() - started)
                continue
            except (FastPassError, APIError, ValidationError) as e:
                fixture.errors.append(f"{type(e).__name__}: {e}")
                fixture.latencies.append(time.monotonic() - started)
                continue
            fixture.latencies.append(time.monotonic() - started)
            fixture.results.append(compare(out, expected))
    return all_runs


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def report(all_runs: list[FixtureRuns], runs: int) -> tuple[str, bool]:
    """Return (table text, all passed). Latency over the limit counts as a failure."""
    lines: list[str] = []
    ok = True
    for fixture in all_runs:
        lines.append(f"\n{fixture.name}")
        for error in fixture.errors:
            ok = False
            lines.append(f"  ERROR  {error}")
        fields: dict[str, list[FieldResult]] = {}
        for run in fixture.results:
            for result in run:
                fields.setdefault(result.field, []).append(result)
        for name, results in fields.items():
            passes = sum(r.passed for r in results)
            failed = passes < runs
            ok = ok and not failed
            detail = next((r.detail for r in results if not r.passed), "")
            mark = "FAIL" if failed else "pass"
            lines.append(f"  {mark}  {name:<22} {passes}/{runs}  {detail}".rstrip())

    latencies = [lat for f in all_runs for lat in f.latencies]
    if latencies:
        p50, p95 = percentile(latencies, 50), percentile(latencies, 95)
        slow = p95 > P95_LIMIT_S
        ok = ok and not slow
        lines.append(
            f"\nlatency p50={p50:.1f}s p95={p95:.1f}s over {len(latencies)} runs"
            + (f"  FAIL (p95 over {P95_LIMIT_S:.0f}s)" if slow else "")
        )
    else:
        ok = False
        lines.append("\nno fixtures found")
    lines.append("\nRESULT: " + ("PASS" if ok else "FAIL"))
    return "\n".join(lines), ok


def _domain(url: str) -> str:
    host = urlparse(url if "//" in url else f"//{url}").hostname or ""
    return host.lower().removeprefix("www.")
