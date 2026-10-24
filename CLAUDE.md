# CLAUDE.md

Guidance for anyone (human or Claude) writing code in this repo.

## What this is

A Cal Hacks project: a WhatsApp agent that helps immigrant families with immigration letters (core document: the USCIS I-797C asylum interview notice). It explains the letter in the user's language, checks that it's legitimate, calls the agency, waits on hold, and rings the user when a human picks up.

Three agents (orchestrator, research, phone) plus shared modules (translation, memory writer, message relay, glossary worker), coordinated through Postgres. The full spec (data model, handoff payloads, failure rules) lives in [Plan.md](Plan.md). Treat it as the source of truth and don't restate it here.

Four people build this in parallel over one weekend. Everything below exists so we can do that without stepping on each other.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # fill in keys; never commit .env
```

Before pushing:

```bash
ruff format . && ruff check --fix . && pytest
```

## Non-negotiable product rules

Every change must keep these true. If one would be broken, stop and raise it with the team.

1. **Only the orchestrator talks to the user free-form.** Other components send messages only through the relay's templates.
2. **Never dial an unverified number.** The number dialed always comes from the verified official number, never from the letter or from model output.
3. **Never impersonate the user.** The agent never answers identity or verification questions on the user's behalf.
4. **No call without explicit, recorded consent.**
5. **Each table has exactly one writer.** Read what you like through helpers; write only to the tables your component owns.
6. **English inside, user's language only at the edges.**

## Engineering practices

### Contracts first, then code
- Shared payloads (job payloads, results, case brief, call report, events) are **Pydantic models in one shared module**. Every component imports them from there; nobody redefines or hand-builds those dicts.
- Changing a shared contract is a team decision. Tell the owners of both sides, update the model, and fix every caller in the same PR.
- Agents talk to each other through `jobs` and `events` in Postgres, passing IDs and short fields. Don't import another component's internals or call its functions directly.

### Ownership and boundaries
- Each person owns one area (see the spec's team split). Work mainly in your own package.
- Layout: all Python runs in one FastAPI app under `backend/app/`. Each component has its own package there (`orchestrator/`, `relay/`, `memory/`, `translation/`, `research/`, `glossary/`, `phone/`, `db/`, `api/`), with its owner in the package docstring. Shared payloads live in `backend/app/contracts/`. The dashboard goes in `dashboard/`; `mock_agency/` deploys on its own and imports nothing from the backend.
- Build specs (columns, helper signatures, API shapes) live in `docs/specs/`. They implement Plan.md; they don't change it. If you need to change someone else's code, tell them first.
- Keep modules small with one job each. If a file is growing past a few hundred lines or doing two things, split it.
- Database access goes through shared DB helpers, not raw SQL scattered across agents. How to use them and the contracts: [docs/data-layer-guide.md](docs/data-layer-guide.md).

### Every piece runs alone
- Each component needs a way to run with fake inputs: a stub job, a canned letter, a fake call report. Nobody should need the whole system running to work on their part.
- External services (Twilio, Cartesia, Anthropic, web) sit behind thin wrappers so they can be faked in tests and local runs.
- `main` must always start. Integration breaks get fixed before new features land.

### Thin harness
- Use the official SDKs (Anthropic, Twilio, Cartesia) and Pipecat. **No LangChain, LangGraph, CrewAI, or similar frameworks.**
- Prefer the SDK's built-in features (tool runner, structured outputs, prompt caching) over hand-rolled versions.
- Don't add a dependency for something a few lines of code can do. New dependencies go into `requirements.txt` pinned, in the same PR that uses them.

### Configuration and secrets
- All config (API keys, model IDs, phone numbers, URLs) comes from environment variables through a single settings object. No hard-coded keys, numbers, or model names in the code.
- Never log or commit secrets, real letters, personal phone numbers, or personal data. Use placeholder refs for sensitive values in payloads and logs. Our own demo service numbers (the mock agency line) may go in `.env.example`, never in code.
- Prompts live in their own files or constants next to the agent that uses them, not inline inside long functions.

### Async and latency
- The backend is async end to end. Don't call blocking I/O (sync HTTP, `time.sleep`, sync DB drivers) inside the event loop.
- Anything user-facing must be fast. Slow work runs in the background, and the user gets a status message while they wait.
- Put explicit timeouts on every external call and on every wait for the user.

### Errors and observability
- Follow the spec's failure rules exactly; don't improvise new behavior in the moment.
- No bare `except:` and no silently swallowed errors. Catch specific exceptions, log them with context (case_id, call_id, job_id), and either recover per the rules or fail loudly.
- Write every significant agent decision to `events`. The dashboard timeline depends on it, and it's how we debug a call after it happens.

### Code style
- Type hints on all function signatures. Pydantic models for structured data, not loose dicts.
- Names should say what a thing is. Write a short docstring wherever the *why* isn't obvious, and skip comments that restate the code.
- `ruff` handles formatting and linting. Don't argue style in review.

### Tests
- Test what would hurt in the demo: contract models (serialize and validate), the safety rules above, state-machine transitions, and failure-rule handling.
- Tests must not hit real external services. Use fakes.
- Don't chase coverage. A few tests on critical paths beat many shallow ones.

### Git workflow
- Branch per feature (`<name>/<short-topic>`), small PRs, merge to `main` often (several times a day). Long-lived branches will not merge cleanly on Saturday night.
- Pull `main` before starting work and before opening a PR.
- Commit messages are one short line in the imperative ("Add hold detection timeout"). No body unless the why isn't obvious.
- No Claude or AI attribution in commits or PRs (no `Co-Authored-By` trailers, no "Generated with" lines).
- At feature freeze, `main` gets bug fixes only.

### Scope discipline
- The MVP demo path comes first, especially the call flow (dial → menu → hold → human detected → user bridged). Stretch goals wait until that works end to end.
- Build the simplest thing that meets the spec. No speculative abstractions, plugin systems, or "we might need this later" code.
- If something in the spec is ambiguous, ask the owner or the team. Don't guess and build around the guess.

### Keep the docs current
- **Update `CLAUDE.md` and `README.md` often, in the same PR as the change that needs it.** Stale docs mislead both teammates and Claude.
- Update `README.md` when setup steps, run commands, env vars, or the repo layout change. If someone can't get your component running from the README alone, it's out of date.
- Update `CLAUDE.md` when a team-wide convention or rule is added or changed. Keep it about practices and rules, not small design details.

## Notes for Claude

- Start with [backend/AGENTS.md](backend/AGENTS.md): a map of the code, the docs, and what's built so far.
- Read the relevant part of the spec and the existing code before writing new code, and match the conventions already in use.
- Stay inside the area the current task is about. Ask before editing shared contracts, the DB schema, or another person's component.
- Never weaken a non-negotiable rule to make something work, even temporarily.
- Keep changes small and reviewable. Run `ruff` and `pytest` before calling a task done, and report failures honestly.
- After finishing a task, check whether `README.md` or `CLAUDE.md` needs an update, and make it as part of the same change.
