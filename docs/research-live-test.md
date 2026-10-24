# Research: the live end-to-end test

For person 3 (or their agent). This is the one check left on research's integration: [research-integration.md](research-integration.md), status row 2. Everything else is merged and passing on `main`.

## What it does

`backend/tests/research/test_e2e_live.py` runs the demo letter (`backend/tests/fixtures/research/letters/i797c_asylum_interview`) through the real pieces:

1. It wipes and rebuilds the tables on **your** Neon branch, then creates a user, the letter's photo and a document, as the orchestrator would.
2. It queues `research_fast` and starts the real `ResearchWorker` with your key. The fast pass, the deep pass and verification run against the model and the web.
3. It waits up to 4 minutes for the deep job, then checks:
   - the case is at `awaiting_consent`;
   - R1 has a doc type, an explanation and key facts, each with exactly one of `value`/`ref`, and the identifiers are refs;
   - a valid `CaseBrief` is saved, with a call goal and questions;
   - the expected `research.*` and `verification.*` events are there, and `verification.verified` names its source;
   - the verified official phone is the number `official_dial_number` returns, and the `DEMO_DIAL_NUMBER` override works.
4. It queues a `research_question` and waits up to 90 s for an answer with sources, or one of the declines.
5. It checks that no sensitive value (A-number, receipt number, date of birth) appears in any event, job payload or result.
6. It calls the dashboard API (`/api/cases/{id}?lang=es`) and checks the issuer, the evidence URL, the masked refs and the brief's questions.

It takes a few minutes and costs a few cents.

## Before you run it

1. **Pull `main`** and install: `pip install -r requirements-dev.txt` (from the repo root, venv active).
2. **Your Neon branch URL.** Chris sends it privately; it's `research-int-p3`. Never use the shared database. The test refuses it, and it would wipe it for everyone.
3. **Your Anthropic key.**
4. Put both in the repo-root `.env.local` (git ignores it; never commit either value):

   ```
   ANTHROPIC_API_KEY=sk-ant-...
   TEST_DATABASE_URL=postgresql://...research-int-p3...
   ```

   Leave `DATABASE_URL` as it is. The test points the app at `TEST_DATABASE_URL` for its run.

## Run it

From the repo root:

```bash
RESEARCH_E2E=1 pytest backend/tests/research/test_e2e_live.py -v
```

On Windows PowerShell:

```powershell
$env:RESEARCH_E2E = "1"; pytest backend/tests/research/test_e2e_live.py -v
```

If it says `1 skipped`, either `RESEARCH_E2E` isn't `1` or `TEST_DATABASE_URL` is empty.

## If it fails

- **Timed out waiting for the deep job:** check the job's `error` in the output. Slow web fetches can push it past 4 minutes; run it once more before changing anything.
- **An assertion about R1, the brief or events:** that's a real gap between research and the contracts. Fix it in `backend/app/research/` and rerun. If the fix needs a contract change (`backend/app/contracts/`), ask Chris first.
- **"a sensitive value leaked":** stop and fix it before anything else (C34, C35). Find where the value was written from the events and job rows on your branch.
- **Anything about the database or the dashboard API:** tell Chris; those are his.

Before you push a fix, run the normal gate: `ruff format . && ruff check --fix . && pytest`.

## When it passes

In [research-integration.md](research-integration.md), update status row 2: replace "**Not yet run:** the live end-to-end test …" with the date, "live E2E passed on `research-int-p3`" and the time it took. Commit that one line and push to `main`.
