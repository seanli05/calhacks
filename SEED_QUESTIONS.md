# Seed data questions

Person 1 is building the demo seed (`python -m app.db.reset`): the rows that exist before the demo starts, so every component can run against the same data. These questions collect what each component needs. **Answer only your own section, at the bottom of this file.**

## If you're an agent answering this

Your human pointed you here. Before writing anything:

1. **Find out which person you're working for** (2, 3, or 4; see the team table in README.md). If you can't tell, ask your human. Don't guess.
2. **Answer only the questions addressed to that person.** Leave every other section alone, including the "Person 1 decides" questions.
3. **Every answer needs a source.** Use exactly one of these tags:
   - `[human]`: your human told you, in this session.
   - `[code: path:line]`: it's in code or docs on a branch you can name. Add the branch if it isn't `main`.
   - `[unsure]`: you don't know, or the code doesn't settle it. Say who could decide. This is a good answer. A wrong guess ends up in the shared database and the demo.
4. **Don't invent values** (dates, names, wording, menu paths). If the code doesn't have it and your human hasn't said it, it's `[unsure]`.
5. **Never write real personal data or secrets here.** No real phone numbers, API keys, addresses, or real letters. If a question needs a real value, answer `sent to person 1 privately` and have your human send it.
6. **Don't change code, the schema, contracts, or Plan.md** as part of this. If answering reveals a problem, write it up as a note in your section.
7. **Ask your human before submitting** if any answer commits them to a decision (for example, "yes, the brief will look like this").

### How to submit

Edit only your section under [Answers](#answers). Then:

```bash
git pull --rebase origin main
git add SEED_QUESTIONS.md
git commit -m "Answer seed questions for person N"
git push origin main            # docs-only change; on rejection, pull --rebase and push again
```

Never force-push. If the rebase conflicts in this file, keep everyone's text and put yours back in your own section.

## What the seed has today

One user (fake WhatsApp number, language `es`), plus one I-797C case using the values in `mock_agency/agency/case_record.py`:
- **Values:** receipt `ZLA2690012345`, A-Number `A212345678`, date of birth 1988-03-14, interview 2026-11-12 at 8:30 AM, Los Angeles Asylum Office, Tustin.
- **Refs:** those values sit in `case_refs`.
- **R1 and verdict:** a short R1 is saved, and the case has a `verified` verification whose official phone comes from `TWILIO_MOCK_AGENCY_NUMBER`.
- **Events:** `case.created` and `verification.verified`.

Its stage is `awaiting_consent`. There's no brief, no profile, no facts, no messages, and no glossary yet. Full usage notes: [docs/data-layer-guide.md](docs/data-layer-guide.md).

## Questions

### Person 1 decides (don't answer these)
- **D1.** Does the demo start from a seeded case, or does the user send the letter live? Or both: a seeded case for development, a clean user for the take.
- **D2.** Who holds the demo phone, and which phone number is it?

### Person 2: orchestrator, WhatsApp, translation, memory writer, relay
- **P2-1.** Will the orchestrator store the user's number as plain E.164 (`+1…`), stripping Twilio's `whatsapp:` prefix before calling `get_or_create_user`? *(If not, the seeded user never matches the real phone, and the demo user shows up with no case.)*
- **P2-2.** Should the demo user be seeded with language `es` already set, or should the take show them choosing a language (C1)? *(Decides whether `users.language` is set or null.)*
- **P2-3.** Which profile keys will the orchestrator and memory writer read (e.g. `county`, `household_size`, contact preferences)? Give the exact key names, and demo values if decided.
- **P2-4.** Should any facts be pre-seeded, so the "What we know about you" page isn't empty? For each one: fact text, category, source, sensitivity, status. Immigration facts must be `pending_consent`.
- **P2-5.** Should the WhatsApp history start empty, or with earlier messages? If earlier messages, list them.
- **P2-6.** Anything else the orchestrator, relay, or memory writer needs to already exist in the database to run on its own?

### Person 3: research agent, glossary, mock agency line
- **P3-1.** Is `CaseBrief` in `research/models.py` (branch `research_agent`) the brief format the team will use? The shared contract is still a placeholder `dict`. Confirm with person 4 before answering yes.
- **P3-2.** What should the seeded brief contain for the demo case? `call_goal_en`, `expected_menu_path` (the mock line is now English-only: main menu 2 → appointment 2 → receipt prompt → reason → attendance → hold), `questions_to_ask`, `handoff_note`, `likely_rep_questions`, `contingencies`.
- **P3-3.** The mock line asks for the receipt number, but C35 says the agent never enters it. Should the brief tell the agent to let the receipt step time out (the line moves on after 3 tries), or something else?
- **P3-4.** Does the printed demo letter match `case_record.py` exactly (interview 2026-11-12 8:30 AM, notice date 2026-10-13)? What's the R1 `deadline`, the earliest date the user must act (C31)? Is it the interview, or the attorney election form 10 days before?
- **P3-5.** Should the seeded R1 (explanation, checklist, key facts) be the one in `backend/app/db/reset.py` (`demo_fast_result`)? If it should be your fast pass's real output for the demo letter, paste it with no sensitive values.
- **P3-6.** Which `case_refs` names will research write? Today: `receipt_number`, `a_number`, `date_of_birth`, `interview_location`. Is the applicant's name a ref too, or not stored at all?
- **P3-7.** For the seeded verification: which evidence URLs and checks should it list? The official number itself comes from env, not from here.
- **P3-8.** Glossary seed: where are the 20–30 terms, and in what format? For each term: English term, Spanish translation, source URL, trust level.
- **P3-9.** `research/models.py` differs from `app.contracts`:
  - It has a `needs_user_input` status and `key_dates`.
  - It uses `Sensitivity` `high` where the contracts use `sensitive`.
  - `KeyFact` uses `value`/`page` instead of `citation`.
  - It stores `signals`/`call_purpose` on the case.
  
  For each one, does your human want the shared contract changed, or will research move to the contract? Describe the plan only; don't change code.

### Person 4: phone agent
- **P4-1.** Which brief fields does the phone agent read, and which are required? *(So the seeded brief has them.)*
- **P4-2.** Do you want the seed to include a ready call: a "YES" consent message plus a queued `call` job? Then you can test calling the mock line without the orchestrator. If yes, what `max_hold_minutes`?
- **P4-3.** Can you confirm you'll get the number to dial only from `reads.official_dial_number(case_id)`, never from config or the brief? And does the number in `TWILIO_MOCK_AGENCY_NUMBER` ring the mock agency line? Answer yes or no; don't paste the number.
- **P4-4.** Should the seed include a finished earlier call (call row, transcript, report) so the dashboard has history to show? If yes, sketch it with no real data.

### Everyone
- **E-1.** Is there anything your component needs pre-existing in the database that isn't asked above?

---

## Answers

Write in your own section only. Keep each answer to a few lines: `**P2-1.** [code: backend/app/relay/inbound.py:12] …`

### Person 2 answers

*(not yet answered)*

---

### Person 3 answers

*(not yet answered)*

---

### Person 4 answers

*(not yet answered)*

---
