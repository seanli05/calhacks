# Handoff: shorter WhatsApp messages (research changes)

**For:** person 3 (research) and their agent. Task 1 changes a shared contract, so it needs a quick OK from the team first (CLAUDE.md → Contracts first).
**From:** person 2, Oct 24. Person 2 OKs the small edits to `orchestrator/` named below, so each change lands with every caller in one PR.

## Why

On a real phone the letter explanation came out as one ~250-word message. It repeats itself in three places:

- `explanation_en` (3–6 sentences) already covers who must come, the interpreter and the date.
- The checklist printed under it lists the same items again.
- The date line (a template with the date formatted in code) states the date a third time.

The consent question also carries a long call goal. Person 2 already fixed the pacing on branch `lauren/orchestrator-pacing`: one numbered question at a time, the verdict and the call question in one message, a terser turn prompt. What's left comes from research's output.

The full explanation stays as it is: the dashboard shows `explanation_en` ([backend/app/api/cases.py:105](../backend/app/api/cases.py#L105)). WhatsApp needs a second, short field next to it.

## Task 1: add `summary_en` to R1

1. **Contract.** In [backend/app/contracts/results.py](../backend/app/contracts/results.py), add `summary_en: str | None = None` to `FastResult`, right after `explanation_en`. Docstring: "Two short sentences for WhatsApp; `explanation_en` stays the full version (dashboard)." Keep it optional so stored R1 rows still validate. Don't add it to the `ok` validator.
2. **Prompt.** In [backend/app/research/prompts.py](../backend/app/research/prompts.py), add a `## Summary (summary_en)` section after `## Explanation`:
   - Two sentences, at most 40 words, same reading level as the explanation.
   - Sentence 1: what the letter is and who sent it. Sentence 2: what the person must do, and what happens if they don't (e.g. "Missing it can get your application dismissed.").
   - **Leave out** the date, time and place (WhatsApp sends them from `appointment`, formatted in code) and anything in `checklist_en` (who must come, interpreter rules, what to bring): WhatsApp prints the checklist right under the summary.
   - The explanation's rules apply unchanged: no sensitive values, no asylum claim details, no advice, and the scam warning when there are warning signs.
   - Leave `explanation_en` unchanged.
3. **Scrub.** Whatever [backend/app/research/fast_pass.py](../backend/app/research/fast_pass.py) does to `explanation_en` around line 391 (dropping sentences that carry sensitive values), do to `summary_en` too.
4. **Fixtures and tests.** Add a `summary_en` to [backend/tests/fixtures/contracts/fast_result.json](../backend/tests/fixtures/contracts/fast_result.json) and to any research fixtures and fakes that build R1 (`research/fake.py`). Contract tests: it round-trips, and a stored R1 without it still validates.
5. **Caller (person 2's file, OK'd).** In [backend/app/orchestrator/letter_result.py](../backend/app/orchestrator/letter_result.py), `LetterResults._explain`:

   ```python
   explanation_en = result.summary_en or result.explanation_en or ""
   ```

   Then update `test_explanation_carries_the_date_checklist_and_closing` in [backend/tests/test_orchestrator_results.py](../backend/tests/test_orchestrator_results.py): it asserts the body starts with the fixture's explanation, which should now be its summary. Add one test that an R1 without `summary_en` still sends `explanation_en`.
6. **Docs.** Add `summary_en` to the R1 example and field notes in [Plan.md](../Plan.md) with a new C-tag (C41 is next), and to [docs/specs/case-brief.md](specs/case-brief.md) if it lists R1 fields.

## Task 2: a short call goal in R2

The consent question shows R2's `call_goal_en` after "What for:". Today that's e.g. "Ask the local asylum office or USCIS Contact Center about the interview, rescheduling, or attorney remote participation." It's too long to read on a phone.

- [backend/app/research/jobs.py](../backend/app/research/jobs.py) (~line 296) copies the brief's `call_goal_en` into R2. Instead, give R2 a short, user-facing goal: one clause, at most 12 words, starting with a verb, no trailing period. Example: "Confirm your interview is still scheduled".
- **Don't shorten the brief's `call_goal_en`.** The phone agent's menu decider reads it ([backend/app/phone/menu.py:283](../backend/app/phone/menu.py#L283)), and so does the dashboard. Changing that one is a conversation with person 4.
- No contract change: `DeepResult.call_goal_en` keeps its type. If it's empty, the orchestrator falls back to the brief's goal, then to a generic question.

## Done when

- A real letter's WhatsApp explanation has the summary (2 sentences), the date line, the checklist, and the "checking" line. No point appears twice.
- The consent question's "What for:" line fits on one phone line.
- `ruff format . && ruff check --fix . && pytest` pass. Tell person 2 when it's on `main`.
