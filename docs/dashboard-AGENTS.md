# AGENTS.md: making your component show up on the dashboard

For an agent (or human) on persons 2, 3 or 4's side. The dashboard reads only the database, through `backend/app/api/`. It never calls your code and you never call it. If your component writes its rows and events the way this doc says, the dashboard shows them in the user's language with no change on person 1's side.

Most of this is already enforced by the contracts in `app.contracts`. This doc lists **what the types don't enforce**: free-form `data` fields, the provisional brief's keys, the order of call states, and so on. Those are the things that silently break the screen.

## Read first

1. [CLAUDE.md](../CLAUDE.md) and [backend/AGENTS.md](../backend/AGENTS.md).
2. [data-layer-guide.md](data-layer-guide.md): the recipe for your component, and **Case stage** (the dashboard's headline comes from `reads.case_progress`).
3. Your section below. Don't read the dashboard's TypeScript; the API in `backend/app/api/` is the boundary.

## Rules for everyone

- **Events go through `append_event(Event(...))`** with `user_id`, and `case_id` and `call_id` whenever they exist. The feed is per user; the case view filters by case; call events without `call_id` don't reach the call panel.
- **`summary_en` is a fallback, not the feed text.** The feed shows a pre-translated template per event type. The template is specific only when `data` has the fields below; otherwise it's a generic line ("We called the office"). Types without a template show `summary_en` in English, so keep it short and plain.
- **`data` carries IDs and short values, never content.** No letter text, names, numbers or fact text (C27). The feed looks fact text up by `fact_id` itself.
- **English inside.** Every `*_en` field and every list the dashboard localizes (`checklist_en`, `next_steps_en`, `red_flags`, the brief's questions) is English. The dashboard translates at the edge.

### Event `data` the feed expects

The source of truth is the table at the top of [`backend/app/api/feed_templates.py`](../backend/app/api/feed_templates.py). As of Oct 24:

| Event type | Who emits | `data` | Example |
|---|---|---|---|
| `verification.verified` | 3 | `source`: the official domain checked | `"uscis.gov"` |
| `consent.requested` | 2 | `agency`* | `"USCIS"` |
| `call.dialing` | 4 | `agency`* | `"USCIS"` |
| `call.menu_choice` | 4 | `digit`: the key pressed | `"2"` |
| `call.ask_user_answered` | 2 (relay) | `choice`: 1-based option | `1` |
| `call.ask_user_timeout` | 2 (relay) | `default_option` | `1` |
| `call.on_hold` | 4 | `agency`* | `"USCIS"` |
| `call.human_detected` | 4 | `agency`* | `"USCIS"` |
| `call.user_joined` | 4 | `agency`* | `"USCIS"` |
| `call.ended` | 4 | `minutes`: whole minutes | `6` |
| `memory.fact_saved` / `fact_superseded` / `fact_pending_consent` | 2 (memory) | `fact_id` | `"fact_…"` |
| `case.document_added` | 2 | `document_id` | `"doc_…"` |

\* `agency` falls back to the case's `issuer` from R1, so it's optional when R1 has one.

## Person 2: orchestrator, relay, memory, translation

**WhatsApp mirror** (right rail on every page) reads `messages` through `GET /api/users/{id}/messages`:
- `body_original` is shown; `body_en` is shown muted under it when the language isn't English. `send_template` fills both already. **`send_text` (orchestrator free text) needs `body_en` passed** whenever the language isn't English, or the mirror shows no English line.
- `language` on every row; `media_ids` on photo messages (the mirror draws the letter thumbnail from the first one).
- Inbound messages are logged too (the pipe already does).

**User language:** `users.language` drives the dashboard's language on first load. Set it as soon as the user picks.

**Consent:** emit `consent.requested` (with `agency`) when you ask, and keep the YES as the `messages` row you put in `CallJob.consent_message_id`. The case view shows the brief's questions while the stage is `awaiting_consent`.

**Memory** (`/u/{id}/memory` page) reads `facts` with `reads.list_facts`: `fact` (English), `category`, `status`, `sensitivity`, `source`. Pending immigration facts show as "waiting for your OK". The profile card shows every key of `upsert_profile`'s dict as label and value, so keep keys short and values plain. Emit `memory.fact_*` with `fact_id` for each change. Deletes are the dashboard's job (`app.db.deletes`); don't write them.

**Translation:** today `app/api/common.py: localize(en, lang)` uses a hard-coded Spanish table for the seed's strings (`app/api/stand_in_es.py`). When `translation/` exists, the dashboard needs **a fast, sync lookup** (the API polls every 1–3 s), not an LLM call per request. Agree the interface with person 1 before building: likely translate at write time and cache by `(text_en, lang)`, with the API reading the cache. Person 1 then swaps `localize` and deletes the stand-in.

**Already right on `main`:** `/dev/fake-call` emits the call events with the fields above. ask_user logs its events with `choice` and `default_option`.

## Person 3: research agent

The **case view's letter panel** and the **My cases** page read R1, R2 and the brief.

**R1 (`save_fast_result`)**, `FastResult` from `app.contracts`:
- `issuer` is the headline's agency name ("Calling USCIS…") and the feed's `agency` fallback.
- `doc_type`, `deadline`, `urgency`, `explanation_en`, `what_is_asked`, `checklist_en` (each with `kind`), `appointment` (`location_ref` resolves server-side).
- Every sensitive value goes in `put_ref(case_id, name, value)` and travels as `<ref:name>`. The dashboard shows refs masked as `•••• 2345`. It never shows the date of birth, and shows the location only inside the appointment.

**Verification (`save_verification`)**: `status`; `evidence` URLs, **official source first** (the panel shows its domain as "Checked against uscis.gov"); `red_flags` in English. Emit `verification.verified` with `source`.

**Brief (`save_brief`)**: the shape is still provisional, so the dashboard reads exactly two keys from the dict: **`call_goal_en`** (str) and **`questions_to_ask`** (list of English strings). Use those names or the panel is empty.

**Events:** `case.created`, `research.fast_started/done`, `research.deep_started/done`, `verification.*`.

**Open issue:** the `research_agent` branch has its own models that don't match `app.contracts` yet (data-layer guide → Open issues). Writing through `writes.research` with the contract models is what makes the dashboard work.

## Person 4: phone agent

The **call panel** at the top of the case view is driven by the `calls` row and the call events.

**States:** `create_call(...)`, then `set_call_state` through `dialing → menu → hold → human_detected → bridging → connected → wrap_up → ended`. The headline and the tracker come from these (via `case_progress`). The panel turns solid green at `human_detected`, which is the big moment in the video, so set it the moment a person is detected, before bridging.

**Hold timer:** starts at the **first** `call.on_hold` event of the call. Emit `call.on_hold` when hold begins; repeating it is fine (the orchestrator throttles messages to the user).

**Events:** the call rows of the table above, each with `call_id`. Also `call.user_dialed` and `call.user_unreachable`. `call.menu_heard` is logged for debugging but kept out of the feed, since it fires on every menu prompt.

**After the call:**
- `save_transcript(call_id, lines)`: each line `{"at", "speaker": "agent" | "agency" | "user", "text"}`. Any other speaker breaks the transcript sheet.
- `save_call_report(call_id, report)`: `outcome`, `summary_en` (shown above the steps), `next_steps_en` (English list, shown as checkmarks), `reference_number`, `transcript_id`. The panel switches to the report at `ended`.
- `set_call_state(..., ENDED)` sets `ended_at`.

## Check your work against the dashboard

```bash
uvicorn app.main:app --app-dir backend --port 8000               # repo root
cd dashboard && npm install && npm run dev  # http://localhost:3000, live data by default
```

- `curl localhost:8000/api/demo` gives the user and the open case. The pages are `/u/<user>/cases/<case>`, `/u/<user>/cases` and `/u/<user>/memory`.
- `curl localhost:8000/api/users/<user>/feed?lang=es`: every line you emitted should read as a specific Spanish sentence, not a generic one or your `summary_en`.
- `curl localhost:8000/api/cases/<case>?lang=es`: your fields are there.
- No phone agent yet? `DEV_ENDPOINTS=true` and `POST /dev/fake-call` (person 2's, see [whatsapp-pipe.md](whatsapp-pipe.md)) plays a scripted call through the real tables. It creates its own throwaway case.
- **Test against your own Neon branch** (ask person 1) or ask before writing to the shared database; it's what the demo runs on. Against the shared database, run with `RESEARCH_WORKER=false`, `MEMORY_WORKER=false` and `DEV_ENDPOINTS` off: only the deployed backend claims jobs there.

Something the dashboard should show but can't? Ask person 1. Don't edit `app/api/` or `dashboard/`.
