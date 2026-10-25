# Cal Hacks Agent System Spec (v3)

Oct 23, 2026 · @Sean Li · v3 edits by @Chris, for team sign-off · use-case update (C30–C35) by @Sean Li

> **About this version.** This is Plan.txt (v2) restyled as Markdown, with fixes for contradictions and missing pieces found while planning the schema, plus the team's product decisions. Every change is tagged inline as **[C#]** and justified in [Changes from v2](#changes-from-v2). Untagged text is v2 unchanged apart from formatting. Once everyone signs off, this is the plan we build against.
>
> **Scope rule:** this is a hackathon project. When in doubt, build what is visible in the demo and skip edge cases the demo never hits.

## Overview

We're building a WhatsApp-based agent that helps immigrant families deal with immigration letters. It explains the notice in their language, says who has to show up, what to bring, and by when, and checks that the notice is really from USCIS. Then it calls the agency, navigates the phone menu, waits on hold, and rings the user when a human picks up. Name still undecided (shortlist: Kinvoy, Unhold). **[C30]**

**Core document [C30]:** USCIS Form I-797C, Notice of Action, scheduling an asylum interview (case type I-589, Application for Asylum and for Withholding of Removal). It carries a receipt number, the applicant's A-Number, the interview location, date, and time, and dense rules the family must follow. Missing the interview, or showing up without a qualified interpreter, can get the asylum application dismissed or referred to an immigration judge. Families who can't read English well are the ones most likely to miss those rules.

**Core loop:** notice photo on WhatsApp → explanation and checklist in the user's language → legitimacy check → user consents → agent calls the USCIS Contact Center and holds → user's phone rings when a human answers → summary on WhatsApp.

### Design principles

- Anything user-facing is fast; deep work runs in the background.
- One agent converses with the user (the orchestrator); other agents never message the user free-form.
- Agents pass IDs and short JSON payloads plus a short handoff note, and pull details from Postgres through tools.
- English internally; the user's language only at the edges.
- The agent never impersonates the user and never dials a number that hasn't been verified.
- Explain, don't advise: the agent explains what the notice says and what it requires. It never gives legal advice on the asylum case and never acts as the interview interpreter. **[C33]**

### What changed since the first doc

- Target users are immigrant families, and the core document is the USCIS I-797C asylum interview notice. **[C30]**
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
| C30 | Main use case changes to immigrant families. The core document is the USCIS Form I-797C asylum interview notice (I-589), replacing the Medi-Cal renewal letter in the MVP scope, examples, relay templates, glossary seed, and mock line. The mock line copies the USCIS Contact Center menu. | Team decision. The notice has high stakes (a missed interview or a missing interpreter can end the case), a hard date, and rules that are hard to follow in English. That makes the explanation and checklist matter. |
| C31 | R1 gains `appointment` (interview date, time, and location ref) and `checklist_en` (who must come, interpreter rules, what to bring, related deadlines, each with a citation). `deadline` stays as the earliest date the user must act. | The notice is an appointment, not a form to return, and most of what the family needs to do is in the "who should come" and "what to bring" sections. Without these fields the orchestrator would have to dig them out of `explanation_en`. |
| C32 | Verification adapts to USCIS notices. The I-797C prints no phone number (only `uscis.gov/contactcenter`), so `letter_phone_matches` can be `null`. Research checks the form number and edition, that every URL is on `uscis.gov`, and the receipt number's format, and looks up the official Contact Center number on `uscis.gov`. Immigration red flags: demands for payment, gift cards or wire transfers, threats of arrest or deportation, non-`.gov` links, "notario" offers. | The v2 check (letter phone vs. official phone) has nothing to compare on this notice. Immigration scams are common and target exactly this audience. |
| C33 | Explain, don't advise. The agent explains what the notice says and requires but gives no legal advice on the asylum case (eligibility, what to say at the interview, whether to hire someone). When asked, it says so and points to free legal help (stretch #14). The agent never offers to be the interview interpreter. **Needs team OK:** propose adding this to the non-negotiable rules in CLAUDE.md. | Advice on an asylum case is legal practice; a wrong answer can cost someone their case. The notice requires a human interpreter who meets specific rules. |
| C34 | Immigration data handling. Receipt number, A-Number, interview location, and date of birth are always `<ref:...>` values. Details of the asylum claim (country of nationality, reasons for leaving) are never extracted into facts, briefs, or events, even if the user mentions them. Immigration facts are always held as `pending_consent` (C15). | Asylum applicants can be put at risk if their data leaks. "Store less" from the memory rules becomes concrete. |
| C35 | The phone agent never types or says the A-Number, receipt number, or date of birth, in the phone menu or to the representative. The mock line's menu doesn't ask for them. If a real menu requires one, the agent takes the path that doesn't need it (e.g., "speak to a representative") or asks the user via ask_user which path to take; the user gives identifiers in their own voice once bridged. **Needs team decision:** whether entering the receipt number in a menu counts as answering a verification question (rule 3). | USCIS menus ask for these numbers, and they function as identity checks. Rule 3 forbids the agent answering for the user; this picks the strict reading until the team decides. |
| C36 | The phone agent logs every call event unfiltered; the orchestrator decides which reach the user (P2), by fixed rules in code, sent as relay templates. It owns the "On hold" limit (one per 10 minutes per call); `call.human_detected` is always sent at once. Person 2 agreed (Oct 23). | Keeps the phone agent transparent and puts all user-facing policy in one place. Rules instead of a model call, because the user has only seconds to answer once a human picks up. |
| C37 | The phone agent answers phone menus by speaking (TTS on the live stream), not with DTMF. For a menu step that only accepts the keypad, it updates the call through the REST API with `<Play digits>` and then a new `<Connect><Stream>`, batching digits so it reconnects as rarely as possible and carrying call state across the new stream. It never sends identifiers this way **[C35]**. | Twilio Media Streams can't send DTMF. In a spike call, Pipecat's in-band tones weren't registered as key presses; speaking and the REST update both worked, each in about 5 s ([spikes/dtmf/README.md](spikes/dtmf/README.md)). Speaking keeps one unbroken stream, which hold detection and the bridge depend on; the REST update drops the stream on every use. |
| C38 | A `research_question` job answers the user's factual questions about their letter or process from official sources only. The orchestrator queues it with the question in English (and the `case_id` when it's about a case; research then reads only that case's R1 and refs). The result is `answered` with quotes from the official pages, or a decline: `not_confirmed`, `declined_legal_advice`, `declined_asylum_claim` (C33, C34), or `out_of_scope`. The orchestrator relays it. | Users ask questions the letter doesn't answer. Answering from the model's memory risks wrong immigration information; grounding every answer in a quoted official page keeps it checkable. |
| C39 | R1 may be `needs_user_input` with `question_en`, when the pages look like different letters. The orchestrator asks the question, then queues `research_fast` again for the same case with the reply as `user_note_en`. The case stage is `needs_answer` meanwhile. | Photos sent within seconds become one letter, so two letters can land in one document. Only research can see that, and guessing would explain the wrong letter. |
| C40 | Demo exception to rule 2: while `DEMO_DIAL_NUMBER` is set, `official_dial_number` returns it (the mock agency line) instead of the verified official number. Every other check still applies: an unverified case gets no number. Research still saves the real official number, so verification and the dashboard stay truthful. Clear it before calling real agencies. | Research finds the real USCIS number, so without this a rehearsal would call USCIS. Keeping the swap inside the one helper keeps a single path to any dialed number. |
| C41 | Shorter WhatsApp messages, with no contract change. R1's `explanation_en` is two paragraphs separated by a blank line: a two-sentence summary (what the letter is and what the user must do, without the date, place or checklist items), then the details. WhatsApp sends only the first paragraph, followed by the date line and the checklist; the dashboard gets the whole text. An explanation without a blank line is sent whole. R2's `call_goal_en` is a short goal (one clause, at most 12 words) that the deep pass writes by rewriting the brief's goal with the fast model. The brief's `call_goal_en` stays the full goal the phone agent and the dashboard read. If the rewrite fails, R2's goal is empty and the consent question uses the brief's goal. | On a real phone the explanation came out as one ~250-word message that said the date and checklist three times, and the consent question's "What for:" line ran to several lines. The contracts stay as they are. |
| C42 | The user's phone rings for 15 s, not 30, and a missed ring rings once more before `user_unreachable` (the rep hears a fixed "calling them again" line; the user gets a WhatsApp nudge, `call.user_dialed`). The join gate (`PHONE_JOIN_GATE`) is on by default and off for the demo, where the user joins on pick-up. | Most carriers' voicemail answers after about 20–30 s, and Twilio reports that as answered: with no gate, the rep would be put through to voicemail. Ringing 15 s ends the ring first, and the second ring makes up for the shorter window. After a long hold, one missed ring shouldn't lose the call. Sean's call (Oct 24). |
| C44 | The verdict never offers a call. A verified letter gets "it's genuine" on its own; the orchestrator turn offers a call (`request_consent`) only when the user asks or their messages show a need only the agency can resolve (rescheduling, wrong details on the letter, an accommodation, a question official sources didn't answer). `get_case_status` says whether a call is available. R2's `call_recommended` keeps its contract and reads as "a call is possible". Retries after a failed call still ask again (C21). | Every verified letter has the Contact Center number, so `call_recommended` was always true and every user was pushed toward a call, even when the letter only needed explaining. |
| C43 | Consent to a call may be given in words ("yes, please call them"), not only as `1`/yes. The orchestrator turn relays it through a guarded tool (`answer_call_consent`); code checks that a consent request is open for that case, that the user's latest message is their own and came after the request, and that the words the model quotes are in that message. Only then is `consent.given` logged, with `consent_message_id` pointing at that message (C8) and `data.via = "words"`. A hedge or a question ("maybe", "what will you say?") is answered and the question asked again; an earlier message never counts. A bare `1`/yes is still answered in code with no model call. Rule 4's wording stays: consent is explicit and recorded. | On a real phone, "yes, call them" to the consent question got "reply 1 or 2", and the chat felt like a form. The model never answers for the user: it can only pass on what their latest message says, and code checks the quote. |
| C46 | Check the letter before explaining it. Right after the fast pass, research runs the checks that need no model and no web (the deep pass's scam rules: payment demands, threats, notario offers; and offline signal conflicts such as look-alike or non-`.gov` links on a federal notice). On a hit, R1's `verification` is `suspicious` (the existing field; no contract change), and the user gets a warm warning at once: no explanation of the letter and no call offer, ever. Otherwise the user hears "I'm just double-checking it's really from USCIS…", and the explanation goes out with the verdict, in one message: verified → the explanation and "it's genuine", with no call offer (C44); unknown (or the deep pass failed) → the explanation with a gentle caution; suspicious → the warning only. If no verdict comes within 60 s, the explanation goes out with "still checking, don't pay or call yet", and the verdict follows alone. **Needs team OK:** this changes the "Letter → explanation < 30 s" target. | A scam letter was explained in full before it was flagged, so the family read its demands as instructions. Waiting up to a minute keeps the warning ahead of the explanation, and the cap keeps a slow check from leaving the family with nothing. |

## MVP and stretch goals

**MVP scope:** one document type, the USCIS I-797C asylum interview notice **[C30]**, and one non-English language (Spanish), end to end. The demo notice is a sample with made-up values; never a real person's notice.

**Demo call goal:** confirm the interview appointment is still on, and ask what the family should do if their interpreter can't come. (The notice warns that showing up without a qualified interpreter counts as failing to appear.)

### MVP

1. User sends a photo of the notice (optionally a voice note) on WhatsApp and picks their language.
2. Explanation in the user's language: what the notice is, interview date, time, and place, and a checklist of who must come (dependents, an interpreter who meets the notice's rules), what to bring, and related deadlines. **[C31]**
3. Legitimacy check: form, URLs, and receipt number format checked against USCIS, official Contact Center number found on `uscis.gov`, with verdict and evidence. **[C32]**
4. Case brief: structured JSON plus handoff note.
5. Explicit consent on WhatsApp before any call.
6. Agent calls the mock USCIS Contact Center line, navigates the menu, waits on hold.
7. At least one ask_user moment on WhatsApp when the agent is unsure.
8. Human detection, brief intro to the representative, then a regular phone call rings the user.
9. Post-call summary on WhatsApp: reference number, next steps, deadline.
10. Basic memory: profile plus extracted facts.
11. Web dashboard: live call timeline (a feed in the user's language **[C23]**), case view, "What we know about you" page.
12. Backup video of the full flow.

**Protect items 6–8 above everything else.**

### Stretch goals (in order of demo value)

1. Voice-note replies: transcribe the user's voice notes; reply with audio in their language.
2. Live captions of the representative, translated.
3. Automatic glossary research for new terms, with a visible log line.
4. A second language, ideally lower-resource (e.g., Haitian Creole or Dari), with a before/after translation comparison.
5. Memory in action on a second visit.
6. Scam letter demo: a fake "USCIS" letter demanding a fee by phone, flagged with clear reasons. **[C32]**
7. Interview reminders on WhatsApp: the attorney remote-participation deadline (10 days before) and a day-before reminder with the checklist. Needs a pre-approved WhatsApp template, since it falls outside the 24-hour reply window.
8. Suggested replies on a copilot screen during the call.
9. Choosing the Contact Center's Spanish-language option in the phone menu.
10. A second document type (e.g., an I-797C biometrics appointment notice).
11. Live interpreter mode on agency calls (never at the asylum interview itself **[C33]**).
12. Jev for menu and hold decisions.
13. Browser use to check case status on `uscis.gov` with the receipt number, with the user's consent.
14. Pointing the user to free legal help nearby (DOJ-recognized organizations and accredited representatives). **[C33]**

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
- Reads every message it doesn't answer in code, including while a numbered question is open, and answers that question through guarded tools when the user answers in words (a call menu choice, consent, "same letter or new?", "may I save this?"). **[C43]**
- Suggests closing a case when a call resolves with no follow-up; closes it when the user agrees. **[C22]**
- Sends the interview checklist from R1 along with the explanation. **[C31]**
- Decides which call events reach the user, by fixed rules, sent as relay templates. **[C36]**

**Tools:** `start_research`, `get_case_status`, `request_consent`, `start_call`, `get_profile`, `list_active_cases`, `close_case` **[C22]**.

**Does not:** parse documents, browse the web, place calls, write facts directly (the memory writer does that after each reply), give legal advice on the asylum case, or offer to interpret at the interview. When asked for advice, it explains what the notice says, says it can't advise, and points to legal help. **[C33]**

### Research agent

**Does:**

- **Fast pass** (fast model with vision, target under 30 s): notice → structured facts with citations → appointment and checklist **[C31]** → short English explanation → proposed document facts.
- **Deep pass** (most capable model, runs in the background): legitimacy check via web search/fetch on `uscis.gov` **[C32]**, official Contact Center number lookup, case brief with handoff note, call plan.
- Never extracts details of the asylum claim (country of nationality, reasons for leaving) into facts, briefs, or events. **[C34]**
- Queues unknown jargon terms for the glossary worker.
- Stores the real values behind `<ref:...>` placeholders in `case_refs`. **[C11]**

**Does not:** talk to the user, start calls, or write user facts directly (proposes them to the memory writer).

### Phone agent (fastest model for menu decisions)

**Does:**

- Runs the call state machine: dialing → menu → hold → human detected → bring in user → wrap-up.
- Menu decisions from the case brief, with an explicit "unsure" option that triggers ask_user.
- Answers menu prompts by speaking the choice (the digit or the option name) once the prompt finishes. For a step that only accepts the keypad, it falls back to a Twilio REST call update with `<Play digits>`. **[C37]**
- Hold vs. human detection: voice activity detection, then a quick Claude check when speech follows music.
- Briefly introduces itself to the representative as an automated assistant calling for the applicant, then calls the user into a conference.
- Writes every decision to the events table and produces the call report.

**Does not:** message the user free-form (status and questions go through the relay), reason about the user's wider situation beyond the brief, dial any number other than the verified official one, or type or say the A-Number, receipt number, or date of birth **[C35]**.

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
| Letter → "double-checking" (or a scam warning) | < 30 s | Research fast pass + instant checks **[C46]** |
| Explanation with the verdict | ≤ 60 s after that; the verdict alone later if it takes longer | Research deep pass, background **[C46]** |
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
| `research_question` **[C38]** | Orchestrator, for a user's factual question | Research agent | Answer with official sources, or a decline |

**Statuses:** `queued` → `running` → `done` or `failed`. The handler moves the status and writes `result` (or an error). The orchestrator reacts when `research_fast`, `research_deep`, and `call` jobs for its cases finish.

### H1. Orchestrator → Research (fast pass)

Trigger: user sends a photo or PDF. Relay acknowledges immediately. Each document is one letter and may hold several page images. **[C20]**

```json
{ "job": "research_fast", "case_id": "case_123", "user_id": "user_9",
  "document_ids": ["doc_1"], "user_language": "es",
  "user_note_en": "I got this today, what does it mean?" }
```

### R1. Research → Orchestrator (fast result)

Trigger: parsing done. If research's instant checks found signs of a scam, `verification` is `suspicious` and the orchestrator warns the user without explaining the letter. Otherwise it says it's double-checking the letter and sends the translated explanation and checklist with the verdict (R2), or after 60 s with a caution not to pay or call yet **[C46]**. Proposed facts go to the memory writer; the deep pass starts automatically.

If `status` is `needs_better_image`, the other fields are empty and the orchestrator asks for a new photo using `image_issue` as the tip. **[C9]** If it's `needs_user_input`, `question_en` holds a question for the user and the deep pass waits for their answer. **[C39]**

`appointment` is `null` for notices with no appointment; its `time` and `location_ref` are `null` when the letter doesn't give them. `key_dates` lists every date the letter prints (`notice_date`, `received_date`, `deadline`, `appointment`, `other`), since many notices have an appointment but no deadline. `checklist_en` items have a `kind` of `who_must_come`, `bring`, or `deadline`. `deadline` is the earliest date the user must act. **[C31]** Receipt number, A-Number, and interview location are always refs. **[C34]** A key fact holds either a `ref` (sensitive) or a plain `value` with the letter's `quote` (public, like the form ID), plus its `page`. Proposed facts carry a `sensitivity` (`normal` or `sensitive`).

```json
{ "case_id": "case_123", "status": "ok", "image_issue": null,
  "doc_type": "uscis_i797c_asylum_interview", "issuer": "USCIS",
  "deadline": "2026-11-18", "what_is_asked": "Attend asylum interview with dependents and a qualified interpreter",
  "appointment": { "date": "2026-11-18", "time": "08:30",
                   "location_ref": "<ref:interview_location>", "citation": "p1" },
  "checklist_en": [
    { "kind": "who_must_come", "item": "All dependents listed on the I-589", "citation": "p1 §I" },
    { "kind": "who_must_come", "item": "An interpreter if you are not fluent in English: 18 or older, not your attorney or a witness, not working for your country's government, no pending asylum case of their own", "citation": "p1 §I" },
    { "kind": "bring", "item": "ID for you and each dependent (name, date of birth, place of birth, nationality)", "citation": "p1 §II" },
    { "kind": "bring", "item": "Original and one copy of relationship documents (marriage or birth certificates)", "citation": "p1 §II" },
    { "kind": "deadline", "item": "If your attorney will join remotely, their election form is due 10 days before the interview", "citation": "p1 §I" } ],
  "key_dates": [{ "type": "appointment", "raw": "November 18, 2026 at 8:30 AM", "iso": "2026-11-18" }],
  "key_facts": [{ "field": "form_id", "value": "I-797C", "quote": "I-797C, Notice of Action", "page": 1 },
                { "field": "receipt_number", "ref": "<ref:receipt_number>", "page": 1 },
                { "field": "a_number", "ref": "<ref:a_number>", "page": 1 }],
  "explanation_en": "This is a USCIS notice scheduling your asylum interview. You must go, or your application can be dismissed.\n\nThe interview is on November 18, 2026 at 8:30 AM...",
  "urgency": "high", "verification": "pending",
  "proposed_facts": [{ "fact": "Has an asylum interview scheduled", "source": "from_document" }] }
```

### R2. Research → Orchestrator (deep result)

Trigger: verification and brief done.

```json
{ "case_id": "case_123",
  "verification": { "status": "verified", "official_phone": "+18003755283",
                    "letter_phone_matches": null,
                    "evidence": ["https://www.uscis.gov/contactcenter"], "red_flags": [] },
  "official_phone_purpose": "USCIS Contact Center", "alternative_contacts": [],
  "call_recommended": true, "brief_id": "brief_77",
  "call_goal_en": "Confirm the interview is still scheduled" }
```

Verification `status` is one of `pending`, `verified`, `suspicious`, `unknown`. **[C18]** `verification.signals` records how each signal from the letter compared with the official source (`match`, `not_found`, `conflict`, `uncertain`). `brief_id` is `null` when there's no call to brief, such as a suspicious letter, and `call_recommended` requires a verified official phone. `alternative_contacts` lists verified places to turn when the sender can't be called.

`letter_phone_matches` is `null` when the letter prints no phone number, as on the I-797C. Checks for USCIS notices: form number and edition date, every URL on `uscis.gov`, receipt number format. Red flags: demands for payment, gift cards, or wire transfers; threats of arrest or deportation; non-`.gov` links; "notario" offers. The official number is always looked up on `uscis.gov` at run time, never taken from the letter or hard-coded. **[C32]**

- **Verified** → orchestrator explains the letter and says it's genuine, in one message **[C46]**. It offers a call (asks for consent) only when the user asks for one or shows a need only the agency can resolve, never because the letter checked out. `call_recommended` means a call is possible. **[C44]**
- **Suspicious** → warn the user; never explain the letter or offer a call to the letter's number **[C46]**.
- **Unknown** → explain the letter with a gentle caution (don't pay or call numbers on it); no call offer **[C46]**.

The case brief (`brief_77`, the `CaseBrief` contract) stays in Postgres: JSON fields (doc type, issuer, deadline, appointment, call goal, expected menu path, questions to ask, must_not_do, glossary terms, `<ref:...>` facts) plus a handoff note, likely representative questions with where the answers live, contingencies, and open uncertainties. `must_not_do` always includes: never give the A-Number, receipt number, or date of birth **[C35]**; never discuss the asylum claim **[C34]**.

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

If a menu asks for the A-Number, receipt number, or date of birth, the agent never enters it. It takes the path that doesn't need it or asks the user which path to take; the user gives identifiers in their own voice once bridged. **[C35]**

```json
{ "question_id": "question_3", "call_id": "call_5", "template": "menu_choice",
  "options_en": ["Speak to a representative about an appointment", "Case status"],
  "default_option": 1, "timeout_s": 45 }
```

### P2. Phone → User via relay (status)

The phone agent logs every call event and filters nothing. The orchestrator decides which events reach the user, by the fixed rules below (code, not a model call), and sends them through the relay's pre-translated templates so they go out instantly. **[C36]**

Only these events message the user; everything else goes to events and the dashboard only.

| Event | Message |
|---|---|
| `call.dialing` | "Calling USCIS now." |
| `call.on_hold` | "On hold." The orchestrator sends at most one every 10 minutes per call. |
| `call.human_detected` | "Someone picked up. I'm calling you now; please answer." Always sent at once, never held back (the user has 15 s to answer, C42). |
| `call.user_unreachable` | Agent tells the representative the account holder will call back and ends the call; orchestrator follows up. |

### P3. Phone → Orchestrator (call report)

Trigger: call ends. Orchestrator sends the summary in the user's language; the memory writer stores proposed facts. The report is stored on the `calls` row. **[C12]**

```json
{ "call_id": "call_5", "case_id": "case_123",
  "outcome": "resolved | partial | failed | user_unreachable | cancelled",
  "reference_number": "R-55821", "rep_name": "Maria",
  "next_steps_en": ["Interview is still on for Nov 18", "If the interpreter can't come, contact the asylum office before the interview to ask to reschedule"],
  "new_deadlines": ["2026-11-17"], "transcript_id": "transcript_5",
  "proposed_facts": [{ "fact": "Asylum interview confirmed for Nov 18", "source": "from_call" }],
  "followup_needed": true }
```

### Other job payloads [C13]

```json
{ "job": "research_deep", "case_id": "case_123", "user_id": "user_9", "document_ids": ["doc_1"] }

{ "job": "memory_write", "user_id": "user_9", "source": "from_call", "source_ref": "call_5",
  "proposed_facts": [{ "fact": "Asylum interview confirmed for Nov 18", "source": "from_call" }] }

{ "job": "glossary_lookup", "term": "withholding of removal", "language": "es", "case_id": "case_123" }
```

### Events [C14]

Every event uses one envelope:

```json
{ "event_id": "event_88", "created_at": "2026-10-25T10:03:12Z",
  "type": "call.menu_choice", "source": "phone_agent",
  "case_id": "case_123", "call_id": "call_5", "job_id": "job_12",
  "summary_en": "Pressed 2 (Appointments)", "data": { "digit": "2", "heard": "..." } }
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
- Sensitive data: store less (e.g., "has an asylum interview scheduled," not the claim or history), ask before saving sensitive facts, encrypt sensitive fields, expire stale facts (post-MVP **[C28]**), and let the user view and delete everything on the "What we know about you" page.
- Sensitive categories: immigration, income, health. **[C25]** Immigration facts are always held as `pending_consent`. Receipt number, A-Number, interview location, and date of birth live only in `case_refs`. Asylum claim details (country of nationality, reasons for leaving) are never stored as facts, even if the user says them. **[C34]**
- Asking before saving: the memory writer holds a sensitive fact as `pending_consent`; the orchestrator asks the user on its next turn; the memory writer marks it `active` on yes and deletes it on no. **[C15]**
- Deleting: the user can delete any fact, letter, or transcript, or everything at once. Deletes erase the data and leave a dated line in the feed. **[C26]**

## Failure rules

Decided now so nobody improvises during the build.

| Situation | What happens |
|---|---|
| Fast pass takes over 45 s | Orchestrator says it's taking longer and keeps waiting |
| Unreadable photo | Research returns `needs_better_image`; orchestrator asks for a new photo with tips |
| Verification unknown | No automatic call offer; orchestrator explains the letter with a caution **[C46]** |
| Letter looks like a scam | Warn the user, never explain the letter, never call the letter's number. Instant checks after the fast pass **[C46]**; USCIS-specific red flags in R2 **[C32]** |
| Verdict not back 60 s after the letter is read | Explain with "still checking, don't pay or call yet"; send the verdict when it comes **[C46]** |
| User asks for legal advice on their case | Explain what the notice says, say the agent can't give legal advice, point to legal help **[C33]** |
| User asks the agent to interpret at the interview | Explain that USCIS requires a human interpreter, repeat the notice's rules for who qualifies **[C33]** |
| Phone menu asks for A-Number, receipt number, or date of birth | Never enter it; take the path that doesn't need it or ask_user **[C35]** |
| ask_user times out | Use the default (safest) option and log it |
| Hold exceeds max | Hang up, report failed, offer to retry later (a retry asks for consent again **[C21]**) |
| ask_user answered after timeout | Tell the user what the agent already chose and why; show it in the feed **[C24]** |
| User doesn't answer bridged call in 15 s (twice) **[C42]** | `user_unreachable`: tell the representative the account holder will call back, end call, orchestrator follows up |
| User asks on WhatsApp to hang up | End every leg. If a representative is waiting for the user, tell them first that the applicant asked to end the call. Before the user joined: `cancelled`, confirmed on WhatsApp, no automatic retry offer. Once they're on: the report reads the call as usual |
| Representative asks for identity verification (A-Number, receipt number, date of birth) | The user handles it in their own voice; the agent never answers for them |

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

**Resolved risk: key presses over Media Streams [C37].** Twilio Media Streams can't send DTMF (a server can send only `media`, `mark`, `clear`). Pipecat falls back to playing the tones as audio, and in testing those weren't registered as key presses. The phone agent answers menus by speaking instead. For a step that only accepts the keypad, it updates the call through Twilio's REST API (`<Play digits>`, then a new `<Stream>`). Results: [spikes/dtmf/README.md](spikes/dtmf/README.md).

### Sponsor tracks

- **Strong fits:** Cartesia (speech), Microsoft Built for the Real World / Customer Impact (theme).
- **Only if the feature is real in the demo:** Apify (bulk glossary crawling), Armadin (scam detection and data protection; a closer fit now that immigration scams and asylum data handling are core **[C32] [C34]**).
- Check the Cal Hacks rules for any cap on how many tracks one project can enter.

## Team split and timeline

| Person | Owns | Main tools |
|---|---|---|
| 1 | Postgres schema (incl. jobs), DB helpers, dashboard (timeline, case view, memory page, WhatsApp mirror), deployment | FastAPI, SQLModel, Next.js, ngrok |
| 2 | Orchestrator, WhatsApp webhook (media download), translation module, memory writer, message relay | Anthropic SDK, Twilio WhatsApp |
| 3 | Research agent (fast + deep pass), glossary seed + worker, mock USCIS Contact Center line | Anthropic SDK (vision, citations, web tools), Twilio `<Gather>` |
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
- [x] Prove DTMF key presses mid-call on the mock line: in-stream DTMF doesn't work; speak menu choices instead **[C37]**
- [ ] Twilio account for calls: upgraded (trial blocks `<Stream>` and inline TwiML) and an approved Trust Hub Primary Compliance Profile (required to call +1 numbers)
- [ ] Anthropic and Cartesia API keys
- [ ] Make the demo notice: a sample I-797C asylum interview notice with made-up receipt number, A-Number, location, and date (never a real notice)
- [ ] Map the real USCIS Contact Center phone menu and copy it on the mock line (without receipt number entry **[C35]**)
- [ ] Find USCIS's official Spanish wording for the notice's terms
- [ ] Seed 20–30 glossary terms from it (e.g., asylum, withholding of removal, dependent, interpreter, accredited representative, A-Number, receipt number, parole, immigration judge)
- [ ] Check Cal Hacks track rules and caps
- [ ] Decide the project name

## Decisions

Product decisions made by the team while planning the schema **[C29]**:

| Topic | Decision |
|---|---|
| Target users | Immigrant families **[C30]**. |
| Core document | USCIS I-797C asylum interview notice (I-589) **[C30]**. |
| Scope | Build what the demo shows. The letter is always addressed to the user. |
| Legal advice | None. Explain what the notice says, point to legal help, never interpret at the interview **[C33]**. |
| Immigration identifiers | Always refs; the agent never gives them on a call **[C34] [C35]**. |
| Language | The user selects their language. A first message with text gets a one-tap confirm in the detected language ("¿Seguimos en español? 1 Sí · 2 Otro idioma"); a photo-only first message gets a short multilingual menu. No silent detection: short replies are ambiguous, and a relative may type for the parent. The user can switch any time by asking (Oct 23). |
| Which phone we ring | Always the user's WhatsApp number. |
| Long letters | Several photos form one document **[C20]**. Photos with no gap over ~6 s become one letter; the first gets an instant ack ("¿Tiene más páginas?"). A photo after research has started is asked about by text ("same letter or new? 1 · 2"), since the gap alone can't tell page 2 from a new letter (Oct 23). |
| Which letter a message is about | The orchestrator reasons from the conversation and asks by text if unsure. |
| Closing a letter | The user closes it; the agent suggests it when a call resolves **[C22]**. |
| Consent | Asked before every call, including retries; the user is notified **[C21]**. A `1`/yes or a clear yes in words in the user's latest message **[C43]**. |
| Call history | A letter keeps every call attempt. |
| Late ask_user answers | Tell the user what happened, on WhatsApp and in the live feed **[C24]**. |
| Live feed | The web app shows what's happening in the user's language **[C23]**. |
| Recording | Transcripts and call records, no audio. |
| Sensitive facts | Immigration, income, health **[C25]**. |
| Deleting | Facts, letters, and transcripts individually, plus delete everything. Deletes erase the data and leave a dated line in the feed **[C26]**. |
| Stale facts | Ask whether a fact is still true; post-MVP **[C28]**. |
| Dashboard access | A plain link; no per-user access for the demo. |
