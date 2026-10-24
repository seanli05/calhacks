# Cal Hacks Agent System Spec (v3)

Oct 23, 2026 · @Sean Li · v3 edits by @Chris, for team sign-off

> **About this version.** This is Plan.txt (v2) restyled as Markdown, with fixes for contradictions and missing pieces found while planning the schema, plus the team's product decisions. Every change is tagged inline as **[C#]** and justified in [Changes from v2](#changes-from-v2). Untagged text is v2 unchanged apart from formatting. Once everyone signs off, this is the plan we build against.
>
> **Scope rule:** this is a hackathon project. When in doubt, build what is visible in the demo and skip edge cases the demo never hits.

## Overview

We're building a WhatsApp-based agent that helps limited-English families deal with government letters: it explains the letter in their language, checks that it's legitimate, then calls the agency, navigates the phone menu, waits on hold, and rings the user when a human picks up. Name still undecided (shortlist: Kinvoy, Unhold).

**Core loop:** letter photo on WhatsApp → explanation in the user's language → legitimacy check → user consents → agent calls the agency and holds → user's phone rings when a human answers → summary on WhatsApp.

### Design principles

- Anything user-facing is fast; deep work runs in the background.
- One agent converses with the user (the orchestrator); other agents never message the user free-form.
- Agents pass IDs and short JSON payloads plus a short handoff note, and pull details from Postgres through tools.
- English internally; the user's language only at the edges.
- The agent never impersonates the user and never dials a number that hasn't been verified.

### What changed since the first doc

- WhatsApp (Twilio sandbox) is the primary channel; the web app is a secondary dashboard for the call timeline and memory.
- Live translation during the call and the copilot screen are now stretch goals; the user handles the live conversation.
- Postgres instead of Convex.
- The "concierge" is now the orchestrator.
- Claude handles all decisions for now; Jev is a later swap if call latency is a problem.

## Changes from v2

| # | Change | Why |
|---|---|---|
| C1 | Add a `users` table (WhatsApp number, language), written by the orchestrator. Language moves here from `profile`. (Fallback language dropped by C28.) | The user picks a language before any profile exists, and the first reply must go out in under 2 s. The memory writer runs in the background after replies, so it can't be the source of something the very next reply needs. |
| C2 | The one-writer rule gets one exception: append-only logs (`messages`, `events`) may be inserted by several components, and rows are never updated. | v2 already lists two writers for `messages`, and every component is told to log its decisions to `events` (handoffs "go through … a jobs row plus events"). Insert-only rows can't conflict, so this keeps the rule's intent. |
| C3 | *Replaced by C26.* (Was: fact deletes from the dashboard go through the memory writer.) | v2 requires "let the user view and delete everything" and also makes the memory writer the only writer of `facts`. |
| C4 | One set of fact sources everywhere: `user_said`, `from_document`, `from_call`, `inferred`. | v2 payloads used `document` and `call`, while the facts table used `from_document` and `from_call`. |
| C5 | Option numbers in ask_user are 1-based everywhere (`default_option`, `choice`). | v2 had `default_option: 0` alongside `choice: 1` with no rule; a mismatch presses the wrong key on the call. 1-based matches what the user types. |
| C6 | H2 no longer carries `user_phone`; it carries `user_id`, and the phone agent reads the number through a helper. | Payloads carry IDs; agents pull details through tools (design principle). Keeps the user's phone number out of job rows and logs. |
| C7 | The phone agent creates the `calls` row and its `call_id`; H2 no longer carries `call_id`. | `calls` is owned by the phone agent; having the orchestrator mint its IDs splits ownership of one table. |
| C8 | H2 carries `consent_message_id`, pointing at the user's YES in `messages`. | "Explicit consent on WhatsApp before any call" needs a stored record, not just a timestamp. Pointing at the actual message gives an audit trail without a new table. |
| C9 | R1 gets `status: ok | needs_better_image` and `image_issue`. | The failure rules say research returns `needs_better_image`, but R1 had no field for it. |
| C10 | Add a `questions` table for ask_user, written by the relay. | The relay must map an inbound reply ("2") to a `question_id`. The in-memory future can't survive lookups from the webhook or show on the dashboard on its own. |
| C11 | Add a `case_refs` table holding the real values behind `<ref:...>` placeholders, written by the research agent, read only through a resolve helper. | v2 says sensitive values travel as `<ref:...>` but never says where the real values live or how they're resolved. |
| C12 | The call report (P3) is stored on the `calls` row. | v2 defines the report payload but no table holds it. |
| C13 | Define job types (`research_fast`, `research_deep`, `call`, `memory_write`, `glossary_lookup`) and job statuses. R1, R2, and P3 are the `result` of their jobs. | v2 only names `research_fast` and `call`. The deep pass ("starts automatically"), the memory writer ("runs after each reply"), and the glossary worker had no job type. |
| C14 | Define the event envelope, dotted event type names, and a starter type list, with the user-messaging events from P2 marked. | v2 lists the event format as a contract to agree (persons 1 and 4) but doesn't give one; the dashboard timeline depends on it. This is a starting proposal for that conversation. |
| C15 | Sensitive facts are saved as `pending_consent`; the orchestrator asks the user on its next turn, and the memory writer confirms or deletes the fact based on the answer. | v2 says "ask before saving sensitive facts", but the memory writer can't talk to the user (only the orchestrator can). |
| C16 | Facts get `status` (`active`, `pending_consent`, `superseded`). (Expiry dropped by C28.) | Needed by v2's own rules: supersede, ask before saving sensitive ones, and treat inferred facts as tentative. |
| C17 | No stored case status: a case's progress is computed from its verification, jobs, and calls. | `cases` is written only by research, but the orchestrator (consent) and phone agent (call) also move a case forward. Computing progress keeps one writer per table. |
| C18 | Verification status values: `pending`, `verified`, `suspicious`, `unknown`. | v2 uses all four across R1, R2, and the failure rules but never lists them together. |
| C19 | Shared formats: prefixed IDs, UTC ISO 8601 times, ISO 639-1 language codes, E.164 phone numbers. Example payloads updated to match. | Four people build against the same payloads; fixing formats now avoids cross-team format bugs. v2's examples (`c_123`, `u_9`) already hint at prefixed IDs. |
| C20 | A document is one letter with one or more page images. Several photos of one letter become one document. If the orchestrator can't tell whether a new photo is another page or a new letter, it asks by text. | Real letters run several pages; the demo letter may too. v2's `document_ids` list read as one image per document. |
| C21 | A YES covers exactly one call. Retrying (e.g., after hold exceeded max) asks for consent again, and the user is told why. | Team decision: consent is per call, and the user always knows a call is about to happen. |
| C22 | Add an orchestrator tool `close_case` and a `case.closed` event. A case is active until that event exists. The orchestrator suggests closing when a call resolves with no follow-up; the user decides. | Team decision: the user closes a letter. Using an event keeps `cases` single-writer (C17). |
| C23 | The dashboard shows a live feed in the user's language. Event types shown on the demo screen render from pre-translated templates (filled from the event's `data`); any other event's `summary_en` is translated on read and cached. The dashboard becomes a user of the translation module. | Team decision: the web app is a live feed in the user's language. Translating at write time would slow the phone agent mid-call; templates are instant and pre-checked for the demo. |
| C24 | If the user answers an ask_user question after it timed out, the relay replies with what the agent already chose and why, and logs `call.ask_user_late_reply` (shown in the feed). | Team decision: tell the user what happened, on WhatsApp and in the feed. |
| C25 | Sensitive categories for "ask before saving": immigration, income, health. | Team decision; v2 named the rule but not the categories. |
| C26 | User-initiated deletes are the second exception to the one-writer rule: one data-layer delete helper erases a fact, a document, or a transcript, or everything for a user. Each delete leaves a dated `*.deleted` event in the feed. | Team decision: delete facts, letters, and transcripts individually, plus delete everything. Routing each through its owning component would put three owners behind one button. |
| C27 | Events that concern facts or documents carry their IDs, never their content. The feed looks up the text when it renders and shows "(deleted [date])" once it's gone. | Events are never updated (C2), so an event holding a fact's text would keep showing data the user deleted, on screen in the memory demo. |
| C28 | Out of the MVP: fallback language, fact expiry (`expires_at`, `expired`, the v2 rule "expire stale facts"), supersede logic (the `supersedes` column stays), and the `glossary_lookup` job (moves with stretch goal #3; the hand-seeded glossary stays). **Needs Sean's OK:** supersede logic and expiry were v2 rules. | Scope rule: none of these is visible in the MVP demo. Supersede matters for stretch goal #5 (memory on a second visit). |
| C29 | The open questions are answered; see [Decisions](#decisions). The demo letter is always addressed to the user, the user's phone is always their WhatsApp number, the dashboard uses a plain link (no per-user access), and no call audio is stored. | Team decisions. |

## MVP and stretch goals

**MVP scope:** one document type (e.g., a Medi-Cal renewal letter) and one non-English language (e.g., Spanish), end to end.

### MVP

1. User sends a photo of the letter (optionally a voice note) on WhatsApp and picks their language.
2. Explanation in the user's language with key facts: deadline, case number, what's being asked.
3. Legitimacy check: letter's phone number vs. the agency's official number, with verdict and evidence.
4. Case brief: structured JSON plus handoff note.
5. Explicit consent on WhatsApp before any call.
6. Agent calls the mock agency line, navigates the menu, waits on hold.
7. At least one ask_user moment on WhatsApp when the agent is unsure.
8. Human detection, brief intro to the caseworker, then a regular phone call rings the user.
9. Post-call summary on WhatsApp: reference number, next steps, deadline.
10. Basic memory: profile plus extracted facts.
11. Web dashboard: live call timeline (a feed in the user's language **[C23]**), case view, "What we know about you" page.
12. Backup video of the full flow.

**Protect items 6–8 above everything else.**

### Stretch goals (in order of demo value)

1. Voice-note replies: transcribe the user's voice notes; reply with audio in their language.
2. Live captions of the caseworker, translated.
3. Automatic glossary research for new terms, with a visible log line.
4. A second language, ideally lower-resource, with a before/after translation comparison.
5. Memory in action on a second visit.
6. Scam letter demo flagged with clear reasons.
7. Suggested replies on a copilot screen during the call.
8. Requesting the agency's interpreter in the phone menu.
9. A second document type.
10. Live interpreter mode.
11. Jev for menu and hold decisions.
12. Browser use to check case status on an agency portal.

## Agents and shared modules

Three agents plus four shared modules. Only the orchestrator converses with the user.

### Orchestrator (Sonnet-class model)

**Does:**

- Runs the WhatsApp conversation: the only agent that converses with the user.
- Sends incoming messages through the translation module to English (keeping the original) and replies in the user's language.
- Answers questions from case state in Postgres.
- Starts the research agent when a document arrives.
- Asks for consent and starts the phone agent.
- Turns research results and call reports into user-facing messages.
- Creates the `users` row on first contact and records the user's language pick. **[C1]**
- Asks the user about sensitive facts the memory writer has held as `pending_consent`. **[C15]**
- Groups several photos of one letter into one document, asking by text when unsure. **[C20]**
- Asks for consent before every call, including retries. **[C21]**
- Suggests closing a case when a call resolves with no follow-up; closes it when the user agrees. **[C22]**

**Tools:** `start_research`, `get_case_status`, `request_consent`, `start_call`, `get_profile`, `list_active_cases`, `close_case` **[C22]**.

**Does not:** parse documents, browse the web, place calls, or write facts directly (the memory writer does that after each reply).

### Research agent

**Does:**

- **Fast pass** (fast model with vision, target under 30 s): letter → structured facts with citations → short English explanation → proposed document facts.
- **Deep pass** (most capable model, runs in the background): legitimacy check via web search/fetch on official domains, official phone lookup, case brief with handoff note, call plan.
- Queues unknown jargon terms for the glossary worker.
- Stores the real values behind `<ref:...>` placeholders in `case_refs`. **[C11]**

**Does not:** talk to the user, start calls, or write user facts directly (proposes them to the memory writer).

### Phone agent (fastest model for menu decisions)

**Does:**

- Runs the call state machine: dialing → menu → hold → human detected → bring in user → wrap-up.
- Menu decisions from the case brief, with an explicit "unsure" option that triggers ask_user.
- Hold vs. human detection: voice activity detection, then a quick Claude check when speech follows music.
- Briefly introduces itself to the caseworker, then calls the user into a conference.
- Writes every decision to the events table and produces the call report.

**Does not:** message the user free-form (status and questions go through the relay), reason about the user's wider situation beyond the brief, or dial any number other than the verified official one.

### Shared modules (not agents)

- **Translation:** two-way, glossary-grounded, with register instructions (e.g., warm, simple, formal usted). Used by the orchestrator, the relay's templates, summaries, and the dashboard's live feed **[C23]**.
- **Memory writer:** runs in the background after each orchestrator reply, research result, and call report. Extracts facts, deduplicates, and supersedes outdated ones (supersede logic is post-MVP **[C28]**). The only writer to profile and facts, apart from user-initiated deletes **[C26]**.
- **Message relay:** sends short templated WhatsApp messages instantly (acknowledgments, call status, ask_user) and routes replies back by `question_id`. Templates are pre-translated per language. Records each question and its answer in `questions` **[C10]**, and answers late replies with what was already chosen **[C24]**.
- **Glossary worker:** background job that finds official translations for unknown terms and records source and trust level. Seed 20–30 terms by hand first. The worker itself is stretch goal #3; the hand seed is MVP. **[C28]**

## Speed targets

User-facing steps are fast or templated; anything slow runs in the background with a status message.

| Moment | Target | How |
|---|---|---|
| Letter sent → first reply | < 2 s | Relay sends a templated acknowledgment |
| Letter → explanation | < 30 s | Research fast pass |
| Legitimacy verdict + call offer | 1–3 min | Research deep pass, background |
| ask_user reaches user | < 3 s | Relay, pre-translated template |
| Human answers → user's phone rings | < 5 s | Phone agent dials user directly |
| Call ends → summary | < 30 s | Call report → orchestrator |
| Normal chat reply | a few s | Orchestrator only; memory writer runs after |

## Handoffs

All handoffs go through Postgres: a `jobs` row (type, status, payload, result) plus events. Payloads carry IDs and short fields; agents pull everything else with tools. Sensitive values travel as `<ref:...>` placeholders.

### Shared formats [C19]

- **IDs:** prefixed strings, `<prefix>_<unique>`: `user_`, `case_`, `doc_`, `brief_`, `ver_`, `call_`, `job_`, `question_`, `msg_`, `fact_`, `event_`, `transcript_`.
- **Times:** UTC, ISO 8601 (`2026-10-25T10:02:00Z`). Dates without a time: `YYYY-MM-DD`.
- **Languages:** ISO 639-1 (`es`, `en`).
- **Phone numbers:** E.164 (`+15105550123`).
- **Refs:** `<ref:field_name>`, resolved within the case that holds them (see `case_refs`). **[C11]**

### Jobs [C13]

| Type | Created by | Handled by | Result |
|---|---|---|---|
| `research_fast` | Orchestrator | Research agent | R1 |
| `research_deep` | Research agent, after the fast pass | Research agent | R2 |
| `call` | Orchestrator, after consent | Phone agent | P3 |
| `memory_write` | Orchestrator (after each reply), research agent (with R1/R2), phone agent (with P3) | Memory writer | Facts saved, superseded, or held for consent |
| `glossary_lookup` (stretch **[C28]**) | Research agent | Glossary worker | Glossary entry |

**Statuses:** `queued` → `running` → `done` or `failed`. The handler moves the status and writes `result` (or an error). The orchestrator reacts when `research_fast`, `research_deep`, and `call` jobs for its cases finish.

### H1. Orchestrator → Research (fast pass)

Trigger: user sends a photo or PDF. Relay acknowledges immediately. Each document is one letter and may hold several page images. **[C20]**

```json
{ "job": "research_fast", "case_id": "case_123", "user_id": "user_9",
  "document_ids": ["doc_1"], "user_language": "es",
  "user_note_en": "I got this today, what does it mean?" }
```

### R1. Research → Orchestrator (fast result)

Trigger: parsing done. Orchestrator translates and sends the explanation, ending with "I'm checking that this letter is legitimate." Proposed facts go to the memory writer; the deep pass starts automatically.

If `status` is `needs_better_image`, the other fields are empty and the orchestrator asks for a new photo using `image_issue` as the tip. **[C9]**

```json
{ "case_id": "case_123", "status": "ok", "image_issue": null,
  "doc_type": "medi_cal_renewal", "issuer": "Alameda County SSA",
  "deadline": "2026-11-15", "what_is_asked": "Return renewal form + proof of income",
  "key_facts": [{ "field": "case_number", "ref": "<ref:case_number>", "citation": "p1" }],
  "explanation_en": "This is a Medi-Cal renewal notice...",
  "urgency": "high", "verification": "pending",
  "proposed_facts": [{ "fact": "Enrolled in Medi-Cal", "source": "from_document" }] }
```

### R2. Research → Orchestrator (deep result)

Trigger: verification and brief done.

```json
{ "case_id": "case_123",
  "verification": { "status": "verified", "official_phone": "+1...",
                    "letter_phone_matches": true, "evidence": ["https://..."], "red_flags": [] },
  "call_recommended": true, "brief_id": "brief_77",
  "call_goal_en": "Confirm renewal received; ask what's missing" }
```

Verification `status` is one of `pending`, `verified`, `suspicious`, `unknown`. **[C18]**

- **Verified + call recommended** → orchestrator asks for consent.
- **Suspicious** → warn the user; never offer a call to the letter's number.
- **Unknown** → explain and ask the user how to proceed.

The case brief (`brief_77`) stays in Postgres: JSON fields (doc type, issuer, deadline, call goal, expected menu path, questions to ask, must_not_do, glossary terms, `<ref:...>` facts) plus a handoff note, likely caseworker questions with where the answers live, contingencies, and open uncertainties.

### H2. Orchestrator → Phone

Trigger: user replies YES to consent. A YES covers this one call only; a retry asks again. **[C21]** The dialed number always comes from the verified official number. The phone agent creates the call and its `call_id` **[C7]**, and reads the user's phone number through a helper **[C6]**. `consent_message_id` points at the user's YES in `messages` **[C8]**.

```json
{ "job": "call", "case_id": "case_123", "user_id": "user_9", "brief_id": "brief_77",
  "user_language": "es", "consent_at": "2026-10-25T10:02:00Z", "consent_message_id": "msg_41",
  "max_hold_minutes": 60, "dial_number_source": "official_phone" }
```

### P1. Phone → User via relay (ask_user)

Trigger: menu decision returns "unsure." The relay records the question in `questions` **[C10]**, sends the pre-translated question, and routes the reply `{ "question_id": "question_3", "choice": 1 }` straight back to the waiting phone agent (an asyncio future keyed by `question_id`). On timeout, the agent uses the default, which is always the safest option. The orchestrator sees the exchange in message history but isn't in the loop.

Option numbers are 1-based: `choice: 1` is the first option, matching what the user types. **[C5]**

A reply that arrives after the timeout gets a templated answer saying which option the agent already chose and why, and is logged as `call.ask_user_late_reply`. **[C24]**

```json
{ "question_id": "question_3", "call_id": "call_5", "template": "menu_choice",
  "options_en": ["Renewals", "Report a change"], "default_option": 1, "timeout_s": 45 }
```

### P2. Phone → User via relay (status)

Only these events message the user; everything else goes to events and the dashboard only.

| Event | Message |
|---|---|
| `call.dialing` | "Calling Medi-Cal now." |
| `call.on_hold` | "On hold." At most every 10 minutes. |
| `call.human_detected` | "Someone picked up. I'm calling you now; please answer." |
| `call.user_unreachable` | Agent tells the caseworker the account holder will call back and ends the call; orchestrator follows up. |

### P3. Phone → Orchestrator (call report)

Trigger: call ends. Orchestrator sends the summary in the user's language; the memory writer stores proposed facts. The report is stored on the `calls` row. **[C12]**

```json
{ "call_id": "call_5", "case_id": "case_123",
  "outcome": "resolved | partial | failed | user_unreachable",
  "reference_number": "R-55821", "rep_name": "Maria",
  "next_steps_en": ["Upload pay stubs by Nov 10"],
  "new_deadlines": ["2026-11-10"], "transcript_id": "transcript_5",
  "proposed_facts": [{ "fact": "Renewal received Oct 20", "source": "from_call" }],
  "followup_needed": true }
```

### Other job payloads [C13]

```json
{ "job": "research_deep", "case_id": "case_123", "user_id": "user_9", "document_ids": ["doc_1"] }

{ "job": "memory_write", "user_id": "user_9", "source": "from_call", "source_ref": "call_5",
  "proposed_facts": [{ "fact": "Renewal received Oct 20", "source": "from_call" }] }

{ "job": "glossary_lookup", "term": "redetermination", "language": "es", "case_id": "case_123" }
```

### Events [C14]

Every event uses one envelope:

```json
{ "event_id": "event_88", "created_at": "2026-10-25T10:03:12Z",
  "type": "call.menu_choice", "source": "phone_agent",
  "case_id": "case_123", "call_id": "call_5", "job_id": "job_12",
  "summary_en": "Pressed 2 (Renewals)", "data": { "digit": "2", "heard": "..." } }
```

Starter type list (persons 1 and 4 finalize; the four in P2 are the only ones that message the user):

| Area | Types |
|---|---|
| Case | `case.created`, `case.document_added`, `case.closed` **[C22]** |
| Research | `research.fast_started`, `research.fast_done`, `research.deep_started`, `research.deep_done` |
| Verification | `verification.verified`, `verification.suspicious`, `verification.unknown` |
| Consent | `consent.requested`, `consent.given`, `consent.declined` |
| Call | `call.dialing`, `call.menu_heard`, `call.menu_choice`, `call.ask_user`, `call.ask_user_answered`, `call.ask_user_timeout`, `call.ask_user_late_reply` **[C24]**, `call.on_hold`, `call.human_detected`, `call.user_dialed`, `call.user_joined`, `call.user_unreachable`, `call.ended` |
| Memory | `memory.fact_saved`, `memory.fact_superseded`, `memory.fact_pending_consent` |
| Deletes **[C26]** | `fact.deleted`, `document.deleted`, `transcript.deleted`, `user.deleted_all` |
| Glossary | `glossary.term_added` |

**Live feed in the user's language [C23].** The dashboard shows events as a feed in the user's language. Event types that appear on the demo screen have a pre-translated feed template per language, filled from the event's `data`. Any other event's `summary_en` is translated when the dashboard reads it, and the translation is cached.

**No user data in events [C27].** Events that concern a fact or document carry its ID in `data`, never its content, and `summary_en` doesn't repeat it. The feed looks up the text when it renders and shows "(deleted [date])" once it's gone.

## Data model and memory

Each table has exactly one writer, so agents never conflict. Two exceptions:

- Append-only logs (`messages`, `events`): several components may insert rows, but rows are never updated. **[C2]**
- User-initiated deletes: one data-layer delete helper erases facts, documents, transcripts, or everything for a user, and logs a `*.deleted` event. **[C26]**

| Table | Written by | Holds |
|---|---|---|
| `users` **[C1]** | Orchestrator | WhatsApp number (also the number the user is rung on **[C29]**), language |
| `messages` | Orchestrator, relay (append-only) | Every WhatsApp message, original + English, direction, template used, linked question |
| `profile` | Memory writer | County, household size, contact prefs (language moved to `users` **[C1]**) |
| `facts` | Memory writer | Semi-structured facts (below) |
| `documents` | Orchestrator (on upload) | One letter per document: its page images in order, plus metadata **[C20]** |
| `cases`, `case_briefs`, `verifications` | Research agent | Parsed letter, brief, verdict + evidence |
| `case_refs` **[C11]** | Research agent | Real values behind `<ref:...>` placeholders, read only through a resolve helper |
| `glossary` | Glossary worker | Term, translation, language, source URL, trust level |
| `calls`, `transcripts` | Phone agent | Call state, call report **[C12]**, full transcript. A case can have several calls. No call audio is stored. **[C29]** |
| `events` | Every component (append-only) **[C2]** | Every decision, in the shared envelope **[C14]** |
| `questions` **[C10]** | Relay | Each ask_user question, its options and default, the answer or timeout |
| `jobs` | Creator; handler updates status | Handoffs between agents |

A case has no stored status; its progress is computed from its verification, jobs, and calls. **[C17]** It stays active until a `case.closed` event exists. **[C22]**

### Memory: three layers, all read through tools

- **Profile:** fixed fields every agent needs. A short summary goes in each agent's prompt.
- **Facts:** one record per fact with `fact`, `category`, `source` (`user_said`, `from_document`, `from_call`, `inferred`) **[C4]**, `source_ref`, `recorded_at`, `supersedes`, `sensitivity`, and `status` (`active`, `pending_consent`, `superseded`) **[C16]**. A user will have tens of facts, so put all current facts in the prompt; no vector database needed.
- **Raw sources:** letters, transcripts, call reports, re-readable when an agent needs exact wording.

### Rules

- Facts marked inferred are tentative; agents confirm them before acting.
- New facts supersede old ones rather than piling up (income, address). Post-MVP. **[C28]**
- Per-agent views: research sees the full profile; the phone agent sees only what the brief needs.
- Sensitive data: store less (e.g., "pending green card application," not full history), ask before saving sensitive facts, encrypt sensitive fields, expire stale facts (post-MVP **[C28]**), and let the user view and delete everything on the "What we know about you" page.
- Sensitive categories: immigration, income, health. **[C25]**
- Asking before saving: the memory writer holds a sensitive fact as `pending_consent`; the orchestrator asks the user on its next turn; the memory writer marks it `active` on yes and deletes it on no. **[C15]**
- Deleting: the user can delete any fact, letter, or transcript, or everything at once. Deletes erase the data and leave a dated line in the feed. **[C26]**

## Failure rules

Decided now so nobody improvises during the build.

| Situation | What happens |
|---|---|
| Fast pass takes over 45 s | Orchestrator says it's taking longer and keeps waiting |
| Unreadable photo | Research returns `needs_better_image`; orchestrator asks for a new photo with tips |
| Verification unknown | No automatic call offer; orchestrator explains and asks the user |
| Letter looks like a scam | Warn the user with reasons; never call the letter's number |
| ask_user times out | Use the default (safest) option and log it |
| Hold exceeds max | Hang up, report failed, offer to retry later (a retry asks for consent again **[C21]**) |
| ask_user answered after timeout | Tell the user what the agent already chose and why; show it in the feed **[C24]** |
| User doesn't answer bridged call in 30 s | `user_unreachable`: tell caseworker the account holder will call back, end call, orchestrator follows up |
| Caseworker asks for identity verification | The user handles it in their own voice; the agent never answers for them |

## Tech stack and sponsor tracks

Thin harness: official SDKs plus Pipecat for the call. No LangChain, LangGraph, or CrewAI.

| Layer | Choice | Notes |
|---|---|---|
| LLM | Claude via Anthropic Python SDK | Tool Runner for loops, structured outputs + Pydantic, citations, vision/PDF, web search/fetch, prompt caching |
| Model tiers | Haiku-class (menu), Sonnet-class (orchestrator, fast pass), Opus-class (deep pass) | Swap tiers if latency or quality is off |
| Voice / call | Pipecat + Pipecat Flows | Twilio serializer, Silero VAD, state machine |
| Speech | Cartesia | Ink (speech-to-text), Sonic (TTS) |
| Telephony | Twilio Voice | Outbound call, Media Streams, conference bridge |
| Messaging | Twilio WhatsApp Sandbox | 24-hour reply window; session expires 3 days after joining |
| Backend | FastAPI, Pydantic, SQLModel/SQLAlchemy + asyncpg | Webhooks, dashboard API, async background tasks |
| Database | Postgres | Dashboard updates via WebSocket/SSE or 1–2 s polling |
| Frontend | React/Next.js dashboard | Timeline, case view, memory page, WhatsApp mirror |
| Tunnel | ngrok | Public URLs for Twilio webhooks |

**Open technical risk:** sending key presses (DTMF) mid-call over Media Streams. Prove it on the mock line before kickoff; fallback is updating the call through Twilio's REST API.

### Sponsor tracks

- **Strong fits:** Cartesia (speech), Microsoft Built for the Real World / Customer Impact (theme).
- **Only if the feature is real in the demo:** Apify (bulk glossary crawling), Armadin (scam detection and data protection).
- Check the Cal Hacks rules for any cap on how many tracks one project can enter.

## Team split and timeline

| Person | Owns | Main tools |
|---|---|---|
| 1 | Postgres schema (incl. jobs), DB helpers, dashboard (timeline, case view, memory page, WhatsApp mirror), deployment | FastAPI, SQLModel, Next.js, ngrok |
| 2 | Orchestrator, WhatsApp webhook (media download), translation module, memory writer, message relay | Anthropic SDK, Twilio WhatsApp |
| 3 | Research agent (fast + deep pass), glossary seed + worker, mock agency line | Anthropic SDK (vision, citations, web tools), Twilio `<Gather>` |
| 4 | Phone agent: call state machine, menu decisions, hold/human detection, ask_user, bridge, call report | Pipecat, Twilio Media Streams, Cartesia, Anthropic SDK |

Person 2 has the most surface area; if it bottlenecks, move the message relay to person 1.

### Contracts to agree in the first hour

- Postgres schema: person 1.
- Case brief and call report JSON (as Pydantic models): persons 3 and 4.
- Tool signatures and job types (`start_research`, `start_call`, `ask_user(question, options, timeout)`): persons 2 and 4.
- Event format for the timeline and which events message the user: persons 1 and 4. (Starting proposal under [Events](#events-c14).)

### Timeline

- **First evening:** contracts agreed; each piece runs alone with fake inputs; mock line working.
- **Saturday midday:** first end-to-end run with stubs (WhatsApp letter → brief → call to mock line → summary).
- **Saturday night:** real integration, fix what breaks.
- **Sunday morning:** feature freeze, rehearse the demo, record the backup video, have every demo phone re-join the WhatsApp sandbox.

### Before kickoff

- [ ] Activate the Twilio WhatsApp sandbox and get an echo bot replying
- [ ] Two Twilio numbers: agent and mock agency
- [ ] Prove DTMF key presses mid-call on the mock line
- [ ] Anthropic and Cartesia API keys
- [ ] Pick the demo document and language; find the official translated version of that form
- [ ] Seed 20–30 glossary terms from it
- [ ] Check Cal Hacks track rules and caps
- [ ] Decide the project name

## Decisions

Product decisions made by the team while planning the schema **[C29]**:

| Topic | Decision |
|---|---|
| Scope | Build what the demo shows. The letter is always addressed to the user. |
| Language | The user selects their language. |
| Which phone we ring | Always the user's WhatsApp number. |
| Long letters | Several photos form one document **[C20]**. |
| Which letter a message is about | The orchestrator reasons from the conversation and asks by text if unsure. |
| Closing a letter | The user closes it; the agent suggests it when a call resolves **[C22]**. |
| Consent | Asked before every call, including retries; the user is notified **[C21]**. |
| Call history | A letter keeps every call attempt. |
| Late ask_user answers | Tell the user what happened, on WhatsApp and in the live feed **[C24]**. |
| Live feed | The web app shows what's happening in the user's language **[C23]**. |
| Recording | Transcripts and call records, no audio. |
| Sensitive facts | Immigration, income, health **[C25]**. |
| Deleting | Facts, letters, and transcripts individually, plus delete everything. Deletes erase the data and leave a dated line in the feed **[C26]**. |
| Stale facts | Ask whether a fact is still true; post-MVP **[C28]**. |
| Dashboard access | A plain link; no per-user access for the demo. |
