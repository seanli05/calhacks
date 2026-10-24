# Preset glossary: overnight report

## Term list (75 core terms)

Taken from the USCIS pages the I-797C points to (The Affirmative Asylum Process, Preparing for Your Affirmative Asylum Interview, Types of Asylum Decisions, Interview Scheduling), the demo brief in `app/db/reset.py`, and Plan.md C30–C35. Spelled as USCIS writes them, lowercase.

| Term | Why |
|---|---|
| asylum | The subject of the notice |
| affirmative asylum | USCIS's name for the process this notice belongs to |
| asylum interview | The appointment the notice schedules (seed term) |
| asylum office | Where the interview happens; named on the notice |
| asylum officer | Who interviews the applicant |
| asylum application | How the family will refer to their I-589 |
| application for asylum and for withholding of removal | The I-589's full title, printed on the notice |
| withholding of removal | Part of that title; a family will ask what it means |
| convention against torture | Protection claimed on the same form |
| grant of asylum | The positive outcome USCIS describes |
| applicant | Who the notice is addressed to |
| principal applicant | Distinguishes the main applicant from family on the case |
| dependent | Family members on the case (seed term) |
| derivative | USCIS's word for spouse/children included on the application |
| spouse | Must attend if included |
| unmarried child | Children under 21 included must attend |
| family member | Each gets their own biometrics appointment |
| interpreter | Applicant must bring one (seed term) |
| qualified interpreter | The notice's rules on who may interpret (Plan.md C31/C33) |
| contract interpreter | The phone interpreter USCIS uses to monitor; families confuse it with their own |
| interview notice | What the I-797C is |
| appointment notice | USCIS's word for the I-797C appointment letter |
| notice of action | The I-797C's form title |
| receipt notice | Earlier I-797C the family received after filing |
| receipt number | On the notice; needed when calling (always a ref) |
| a-number | On the notice; the agent never says it (C35) |
| case status | What the family checks online or asks on the phone |
| failure to appear | Consequence of missing the interview or coming without an interpreter |
| exceptional circumstances | USCIS's standard for rescheduling after a missed interview (replaces "good cause", which USCIS's pages don't use here) |
| reschedule | The main reason to call the Contact Center |
| reschedule request | USCIS's phrase for that request |
| biometrics | Fingerprints/photo step before the interview |
| biometric services appointment | USCIS's full name (replaces "biometrics appointment") |
| application support center | Where biometrics happen (ASC) |
| fingerprints | Part of biometrics; named on the notices |
| identity document | What to bring (replaces "government-issued identification") |
| passport | What to bring |
| travel document | What to bring |
| arrival-departure record | Form I-94, what to bring |
| original document | Bring originals of what was filed |
| birth certificate | Typical original to bring |
| marriage certificate | Typical original to bring |
| certified translation | Required for non-English documents |
| evidence | Asked for in reschedule requests and at the interview |
| oath | Applicant and interpreter are sworn in (replaces "sworn statement") |
| witness | May be brought; may not interpret |
| confidential | USCIS's assurance about what the applicant says |
| attorney | May attend; may not interpret |
| accredited representative | Same; C33 legal-help pointer |
| free legal help | Where the agent points users (C33, stretch #14) |
| legal advice | What the agent says it can't give (C33) |
| notario | Classic scam red flag (C32) |
| fraud | Scam warnings (C32) |
| scam | Scam warnings (C32) |
| contact center | The number the agent calls (USCIS Contact Center) |
| field office | Alternate interview location |
| immigration court | Where a referred case goes |
| immigration judge | Who decides a referred case |
| hearing | Immigration court appointment |
| referral to immigration court | Outcome of a missed interview without lawful status |
| removal proceedings | What a referral starts |
| deportation | The word families use for removal |
| employment authorization document | EAD; rescheduling can affect it |
| work permit | Everyday word for the EAD |
| parole | Many Afghan applicants are parolees; missing the interview can end parole |
| deadline | 10-day reschedule window, other deadlines in R1 |
| mailing address | Notices go there; wrong address excuses a missed interview |
| change of address | Must be reported to USCIS |
| decision | What comes after the interview |
| approval | Generic notice outcome |
| denial | Generic notice outcome |
| dismissal | What a failure to appear can lead to |
| security check | Pending checks delay decisions |
| check-in | Arriving at the asylum office for the appointment |
| disability accommodation | The only case where USCIS provides the interpreter (deaf or hard of hearing) |

Dropped from the starting list: `case number` (USCIS uses receipt number), `good cause` (see exceptional circumstances), `telephonic interpreter` (→ contract interpreter), `rescheduling request` (→ reschedule request), `biometrics appointment` (→ biometric services appointment), `government-issued identification` (→ identity document), `sworn statement` (→ oath), `legal representative` (ambiguous with the phone representative; attorney and accredited representative cover it), `remote participation` (not on USCIS's affirmative-asylum pages), `security screening` (→ security check), `application for asylum` (→ asylum application and the full form title).

## Judgment calls

- Branch is `lauren-glossary`, not `lauren/glossary`: a local branch named `lauren` already exists, so git can't create `lauren/<anything>`. The hyphen form matches the repo's other branches (`lauren-goal6-consent-call`, …).

## Progress log

- Setup: worktree `../calhacks-glossary` on `lauren-glossary` from `origin/main` (e188693). Read CLAUDE.md, AGENTS.md, Plan.md glossary lines, writer, table, seed, suggestions, translation.
- Phase 1 (sources): downloaded court glossaries (Judicial Council 2025 es; Contra Costa/Sacramento set), USCIS en/es page pairs, USCIS Dari/Pashto Afghan pages and PDFs, NYC MOIA Immigration Court 101 in 10 languages. Most Sacramento glossaries are legacy-font or definition-only; see SOURCES.md. Extraction tools in `tools/`.
- Phase 2 (terms): 75 core terms, list and reasons above.
- Phase 3 (es): 75 rows, 69 official (USCIS en/es page twins + Judicial Council 2025 glossary), 6 machine. Each official translation checked against the downloaded source text.
- Phase 4 (fa = Dari): 75 rows, 36 official (USCIS Dari page and flyers, 2 from NYC MOIA's Farsi flyer where Dari is identical), 39 machine. Farsi variant for every row in review_fa.csv (machine rows first). Generator: tools/review_sheet.py.
- Phase 5 (ne): 75 rows, 8 official (NYC MOIA Immigration Court 101, Nepali; only words that extracted clean), 67 machine. review_ne.csv written.
