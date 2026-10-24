# The case brief: research → phone contract

The case brief is research's instructions for one call. The research agent writes it and the phone agent follows it. The orchestrator and the dashboard read parts of it. It implements Plan.md → R2 ("The case brief stays in Postgres…"), C34 and C35.

- **Model:** `app.contracts.brief.CaseBrief` (with `RepQuestion` and `REQUIRED_MUST_NOT_DO`).
- **Example:** `backend/tests/fixtures/contracts/case_brief.json` (the demo brief).
- **Owner of the contract:** the team. Changing it follows "Changing the brief" below.

## Lifecycle

1. **Research writes it** in the deep pass, only when the verification is `verified`:
   - `build_brief(case, findings)` builds it (`app/research/brief.py`). It's deterministic: no model call.
   - `writes.research.save_brief(case_id, brief)` stores it in `case_briefs`. The row's ID is the brief's own `brief_id`, so R2 can name it, and `case_briefs.handoff_note` copies `brief.handoff_note`.
   - R2's `brief_id` points at it. A suspicious or unknown letter gets no brief, and R2's `brief_id` is `null`.
2. **The orchestrator** reads the case's latest brief (`reads.latest_brief`). It uses `call_goal_en` in the consent question, and puts `brief_id` in the `CallJob` (H2).
3. **The phone agent** reads it by `brief_id` through `CaseReader.get_brief`. The real adapter (`phone/adapters.py`) validates it against `CaseBrief`, so an invalid brief stops the call before it dials. Inside, the runner reads it as JSON, defensively.
4. **The dashboard** shows `call_goal_en` and `questions_to_ask` (`api/cases.py`) before the call.

The brief is never sent to the user, and it's immutable: a new verification writes a new brief.

## Fields

"Phone" means the phone agent's code today (`phone/menu.py` and the runner).

| Field | Type | Research writes | Who reads it, and for what |
|---|---|---|---|
| `brief_id` | str | A new ID; it also becomes the row's ID | Everyone, to find it. The phone agent logs it, never its contents |
| `case_id` | str | The case | Must equal the row's `case_id` (`save_brief` checks) |
| `doc_type` | str | R1's `doc_type` | Context for later phases |
| `issuer` | str | R1's `issuer` ("the issuing agency" if missing) | Context; the dashboard takes the issuer from R1 |
| `deadline` | date or null | R1's `deadline` | Context |
| `appointment` | `Appointment` or null | R1's `appointment`. The location stays a ref | Context. The phone agent never resolves `location_ref` (C35) |
| `call_goal_en` | str, required | The deep pass's goal, else the fast pass's call purpose, else a generic "confirm the notice details" | **Phone:** the CALL GOAL in every menu decision. **Orchestrator:** the consent question. **Dashboard:** the "why we're calling" line. One plain English sentence |
| `expected_menu_path` | list of str | Menu steps **by meaning**: what to choose and why, never key numbers | **Phone:** MENU HINTS for the decider. Any hint naming a key number is dropped, because real menus renumber (`phone/menu.py`) |
| `questions_to_ask` | list of str, at most 4 | Built from R1: is the appointment on, interpreter backup, the call purpose, what to bring | **Dashboard:** shown before the call. The user asks them once bridged; the phone agent doesn't speak them (rule 3) |
| `must_not_do` | list of str; always includes `REQUIRED_MUST_NOT_DO` | The two required rules (C34, C35), plus no answering identity questions, no identifiers in menus, no legal advice | **Phone:** MUST NOT DO in every menu decision. The model rejects a brief missing a required rule |
| `glossary_terms` | list of str | Terms to explain to the user | Glossary (stretch) |
| `facts` | list of `KeyFact` | R1's key facts, minus asylum-claim fields. Identifier fields only as refs | Later phases. Never spoken (C35) |
| `handoff_note` | str, required | One paragraph: who, why, deadlines, "the user gives identifiers in their own voice" | People reading the case; logs never include it |
| `likely_rep_questions` | list of `RepQuestion` | What a representative may ask, with `answer_source` (the user, once bridged) | Later phases (the human part of the call) |
| `contingencies` | list of str | What to do if a menu asks for an identifier, or a representative asks for identity, legal or case details | Later phases. Today the runner's fixed lines (`phone/call_lines.py`) cover these |
| `open_uncertainties` | list of str | Verification signals that were `not_found` or `uncertain` | People and later phases |

## Rules every brief keeps

- **No identifier values** (C11, C34). The receipt number, A-Number, date of birth and interview location appear only as `<ref:…>`. Research drops a plain value for those fields (`REF_ONLY_FIELDS`), and its `LeakGuard` checks the whole brief before saving.
- **No asylum-claim details** (C34): no nationality and no reasons for leaving, ref'd or not (`CLAIM_FIELDS`).
- **Nothing the agent would say for the user** (rule 3). Questions and identity answers come from the user, once bridged.
- **Menu hints by meaning.** No key numbers, and nothing taken from the mock line's tree. Hints come from how the agency's real line is organized. CLAUDE.md → "The mock agency is a test target".
- **English inside** (rule 6). Every text field is English; the dashboard translates at the edge.

## Changing the brief

The brief is a shared contract, so a change is a team decision (CLAUDE.md → Contracts first). In the same PR:
1. Update `CaseBrief`, `case_brief.json`, and this doc.
2. Update the producer (`research/brief.py`) and every reader:
   - `phone/menu.py`;
   - `orchestrator/consent.py`;
   - `api/cases.py` (`_brief_info`);
   - the seed (`db/reset.py` → `demo_brief`);
   - the dev stand-ins (`dev/fake_research.py`, `dev/fake_call.py`).
3. Tell persons 3 and 4.

## Not used yet

`facts`, `likely_rep_questions`, `contingencies` and `open_uncertainties` exist for the part of the call after a person answers. Today the runner says fixed lines there and bridges the user. When the phone agent starts using them, document it in the table above.
