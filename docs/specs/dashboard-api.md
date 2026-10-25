# Spec: dashboard API

Owner: person 1 · Implements: task C step 2 ([task-c-dashboard.md](task-c-dashboard.md)), Plan.md C23, C26, C27 · Frontend: [dashboard-build.md](dashboard-build.md)

The JSON routes the Next.js dashboard reads, under `/api`, in `backend/app/api/`. The dashboard proxies `/api` to `http://localhost:8000`, so no CORS.

## The contract

**[`dashboard/lib/api/types.ts`](../../dashboard/lib/api/types.ts) is the response contract.** The Pydantic response models in `backend/app/api/models.py` mirror it field for field (same names, same nullability). [`dashboard/lib/api/fixtures.ts`](../../dashboard/lib/api/fixtures.ts) shows a realistic value for every field; match it.

If a shape has to change, change `types.ts`, `fixtures.ts` and the Pydantic model in the same commit, and run `npm run build` in `dashboard/` (it type-checks every page against the new shape).

Conventions:
- Response bodies are Pydantic models defined in `api/`, never table rows. Never put media bytes or `data` blobs in JSON.
- Times are ISO 8601 UTC; dates are `YYYY-MM-DD`.
- `NotFound` from the DB helpers becomes 404.
- **`?lang=xx`** on every route that returns user-facing text. Default: the user's language, else `en`. That text comes back as `Localized` (`{"text": …, "en": …}`): `text` in the requested language, `en` the English it came from. With no translation available, `text` equals `en`. The seed's strings come from a fixed Spanish table (`stand_in_es.py`); any other free text is translated in the background by `translation/`'s translator, once per string and language, and cached in memory (`translations.py`), so it reads in English until a later poll. Without `ANTHROPIC_API_KEY` it stays English.
- **Masking.** Identifiers (receipt number, A-Number) are masked server-side as `"•••• " + last 4 characters` (`ZLA2690012345` → `•••• 2345`). Full values never reach the browser. The date of birth is never sent. The interview location is not an identifier and is sent in full (`Appointment.location`), resolved through `reads.resolve_ref`.

## Routes

| Route | Returns (`types.ts`) | Notes |
|---|---|---|
| `GET /api/demo` | `DemoInfo` | The first user by `created_at` and their newest active case. Powers the landing page's "open the dashboard" link. |
| `GET /api/config` | `PublicConfig` | `whatsapp_number` from `TWILIO_WHATSAPP_FROM` without `whatsapp:`. `sandbox_join_message` = `"join " + TWILIO_SANDBOX_JOIN_CODE`, or null when unset (new setting, see below). |
| `GET /api/users/{user_id}` | `UserInfo` | |
| `GET /api/users/{user_id}/feed?since=&lang=&steps=` | `FeedItem[]` | Oldest first, `since` exclusive (`reads.list_events`). `steps=true` adds the step logs behind each task. See [Feed rendering](#feed-rendering). |
| `GET /api/users/{user_id}/cases?lang=` | `CaseSummary[]` | Active cases, newest first, with `case_progress`, the appointment, and the latest call. |
| `GET /api/cases/{case_id}?lang=` | `CaseDetail` | See [Case detail](#case-detail). |
| `GET /api/calls/{call_id}/transcript` | `Transcript` | Lines as stored (English). 404 when deleted. |
| `GET /api/calls/{call_id}/live?lang=` | `LiveCallEvent` stream | Server-sent events. See [Live call](#live-call). |
| `GET /api/glossary?lang=` | `GlossaryEntry[]` | `reads.get_glossary(lang)`, by term. The dashboard asks for the user's language. |
| `GET /api/users/{user_id}/memory?lang=` | `Memory` | Profile fields, active and pending facts (`fact` localized), documents, transcripts. |
| `GET /api/users/{user_id}/messages` | `Message[]` | `reads.list_messages`: `body` = `body_original`. |
| `GET /api/users/{user_id}/suggestions?lang=` | `Suggestion[]` | See [Suggestions](#suggestions). |
| `GET /api/media/{media_id}` | image bytes | `Response(content=…, media_type=row.content_type)`. |
| `DELETE /api/facts/{id}` · `/api/documents/{id}` · `/api/transcripts/{id}` | 204 | `app.db.deletes`; they write the `*.deleted` events. |
| `POST /api/users/{user_id}/delete-everything` | `DeleteCounts` | `deletes.delete_everything`. |

### Case detail

- `explanation`, `what_is_asked`, `checklist`, `appointment` come from `cases.fast_result` (R1). Localize `explanation_en`, `what_is_asked`, and each `checklist_en[].item`.
- `issuer` from R1 (`"USCIS"`). `page_media_ids` from the case's first document's `pages`.
- `refs`: every `case_refs` row except `date_of_birth` and `interview_location`, masked.
- `verification`: the latest verification. `evidence` and `red_flags` from its `result` JSON (R2 `Verification`); localize `red_flags`.
- `brief`: the newest brief for the case. The brief JSON is still provisional (`backend/app/contracts/brief.py`), so read `call_goal_en` and `questions_to_ask` defensively and return null fields if they're missing.
- `calls`: every call for the case, oldest first. `hold_started_at` is the `created_at` of the first `call.on_hold` event for that call (the phone agent repeats it while waiting). `report` is from `calls.report` (P3) with `next_steps_en` and `summary_en` localized (`summary` is null when the call never reached a person). `transcript_id` is null when no transcript exists.

### Live call

`api/live.py`. Follows the call's transcript (the phone agent's `transcripts` row) every 0.5 s from the last `call.human_detected` event until the call is `ended`, so the view is up while the user's phone rings to join; nothing is sent before a person answers, and the agent's lines holding the line are included. The response sends `Cache-Control: no-cache, no-transform`: without `no-transform`, the dashboard's Next.js `/api` proxy gzips it, and gzip holds an open stream's events back until the call ends.

- Each new agency or user line: `line` (the English as heard), then `delta`s with its translation streamed from `MODEL_FAST` (prompt in `live_prompts.py`, grounded in the glossary terms it uses), then `done`. English, no key, or a failure before the first token sends the line as heard in one `delta`.
- Tips (`live_tips.py`) are rule-based, no model call, so rule 1 holds: `ask` is the next of the brief's `questions_to_ask`, one open at a time, after an agency line; `yourself` follows an agency line that asks about the applicant's identity and never carries an answer (rule 3). `tip_used` when the user's line says most of the question's words (any reply, for `yourself`).
- A reconnect replays the call from the start; finished translations are cached in memory, so the replay makes no model calls. The dashboard folds replayed lines into what it has.
- Lines only appear as the phone agent saves them. From `bridging` on it saves the transcript in the background as each line is heard, then once more in full at wrap-up.

### Feed rendering

Server-side, so the dashboard stays simple (C23, C27).

- **`api/feed_templates.py`:** a template per language for each event type shown on the demo screen, filled from the event's `data`. At minimum `case.created`, `research.fast_done`, `verification.*`, `consent.*`, every `call.*` type, `memory.fact_*`, the four delete types. Spanish and English first.
- **Missing `data` fields never break the feed.** Each type has a variant with no variables. For example, `call.menu_choice` renders "We chose option {option} in the menu" when `data.option` exists and "We chose an option in the menu" when it doesn't. Other components emit these events, so don't assume their `data`.
- **Other types:** `summary_en`, translated the same way (English until the translation lands).
- **References (C27):** an event whose `data` has `fact_id` or `document_id` shows that row's text, looked up at render time. Once the row is gone, set `deleted_at` (the time of the matching `fact.deleted` / `document.deleted` event) and render the text without the content. Event rows never contain the content itself.
- Write down which `data` fields each template expects in a table at the top of `feed_templates.py`, and report it to Chris so the team can emit them.
- **Steps (`api/feed_steps.py`):** the step logs (`research.search`, `.fetch`, `.check`, `call.menu_heard`) are hidden unless `steps=true`, which the case view's live activity asks for. Each then carries `step`: `action` (localized: "Searching", "Reading", "Checking", "Listening"), `detail` (English as logged: the query, the page as `host/path`, a plain name for the check, what was heard), `result` (localized, or null) and `ok` (false when it went wrong). `evidence` and model notes never reach it. Every item also carries `job_id`, which the dashboard groups research steps by (calls group by `call_id`).

### Suggestions

Rule-based, no model call, at most three, in this order. Templates per language in `api/suggestion_templates.py`. `prefill` is what WhatsApp opens with, in the user's language.

1. **countdown:** the newest active case has an appointment or deadline in the future. Title "Your interview is in N days" (by `doc_type`; generic "Your appointment is in N days"), detail "Review what to bring", action "Prepare", prefill "What do I need to bring to my interview?".
2. **glossary:** glossary terms for the case. Use the brief's `glossary_terms` (provisional field, read defensively) looked up with `reads.get_glossary(lang)`. Detail lists up to three English terms joined with " · ", action "Practice", prefill "I want to practice the English words for my interview".
3. **checklist:** the first R1 checklist item of kind `bring` or `who_must_come`. Title "Don't forget: {item}", detail "We can help", action "Ask", prefill "How do I get {item}?".

Skip any rule whose data is missing.

## New reads (`app.db.reads`)

Same style as the existing ones: one `select`, explicit args, return table rows. Likely: `list_calls(case_id)`, `latest_brief(case_id)`, `list_case_refs(case_id)`, `list_documents(user_id)`, `list_transcripts(user_id)` (join through calls and cases), `first_user()`, `first_event(call_id, type)`.

## Settings

Add `twilio_sandbox_join_code: str = ""` to `app/settings.py` and `TWILIO_SANDBOX_JOIN_CODE=` to `.env.example` (with a comment: the code shown on Twilio's sandbox page, without "join").

## Seed (`app/db/reset.py`)

Fictional values only. **The default seed must stay at `awaiting_consent`**, so the live demo call starts from a clean case. Add to it:
- an R1 checklist item `{"kind": "bring", "item": "A qualified interpreter if you are not fluent in English", "citation": "p1 §III"}`;
- a WhatsApp exchange in Spanish (`messages`): the letter photo (a small generated placeholder image in `media`), the explanation, the consent question;
- a profile and two or three facts (one `sensitive`), with their `memory.fact_saved` events carrying `fact_id`;
- the events up to `consent.requested`, with the `data` fields the templates expect.

Add a flag `--after-call` that also seeds a finished call (`calls` row with a P3 report, transcript, and the `call.*` events), so the ended screens can be checked without running the phone agent.

## Tests (`backend/tests/test_api_*.py`)

With `fastapi.testclient` and the DB helpers monkeypatched (no network):
- the feed renders a template in Spanish, and a template with missing `data` falls back to its no-variable variant;
- an event for a deleted fact renders with `deleted_at` and without the fact's text;
- refs come back masked, and the date of birth is never in the response;
- delete routes call the right helper; `NotFound` becomes 404.

One DB-backed test (gated on `TEST_DATABASE_URL`) seeds and fetches `/api/cases/{id}` end to end.
