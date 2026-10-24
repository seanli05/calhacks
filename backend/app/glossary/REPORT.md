# Preset glossary: overnight report

## Summary

- Branch `lauren-glossary` (pushed, not merged): `terms.csv` (257 rows: 75 English terms in Spanish, Dari, and Nepali, plus 32 official-only rows in Pashto, Russian, Vietnamese, Arabic), each row with a source and trust level.
- `load.py` validates the file and writes it through `writes.glossary.add_term` (`--dry-run`, `--language`); 14 offline tests in `backend/tests/test_glossary.py`. Full suite: 557 passed, 17 skipped (DB tests; no database was touched).
- `SOURCES.md` lists every source and dead end; `review_fa.csv` and `review_ne.csv` are ready for the human checkers.

## Coverage

| Language | official | machine | total |
|---|---|---|---|
| es Spanish | 68 | 7 | 75 |
| fa Dari (Farsi in notes) | 36 | 39 | 75 |
| ne Nepali | 8 | 67 | 75 |
| ps Pashto | 9 | 0 | 9 |
| vi Vietnamese | 9 | 0 | 9 |
| ru Russian | 8 | 0 | 8 |
| ar Arabic | 6 | 0 | 6 |
| **all** | **144** | **113** | **257** |

75 core terms. No `community` rows.

## Sources used (details in SOURCES.md)

- USCIS English pages and their official Spanish versions: 61 `es` pairs, each checked against the downloaded text.
- Judicial Council of California English–Spanish legal glossary (2025): 7 `es` pairs.
- USCIS "Information for Afghan Nationals" in Dari and Pashto (HTML), and the USCIS Dari scam flyer: 34 `fa`, 9 `ps`.
- NYC Mayor's Office of Immigrant Affairs "Immigration Court 101" (2026) in Nepali, Farsi, Russian, Vietnamese, Arabic: 8 `ne`, 2 `fa`, 23 Tier 2.
- Dead ends: Sacramento court glossaries are mostly legacy-font PDFs (Arabic, Armenian, Hindi, Punjabi, Vietnamese) or definition-only (Russian, Romanian) or scanned (Urdu); saccourt.ca.gov has an expired certificate; no government Nepali or Dari glossary exists that I could find; NYC's "Hindi" flyer is actually in Igbo.

## Needs a human

**Dari (`review_fa.csv`, machine rows first).** Review these first:
1. **interpreter** (`ترجمان`, a seed term) and its two compounds. USCIS's Dari uses `مترجم` (translator); `ترجمان` is my choice for a spoken interpreter.
2. **parole** (`پیرول`). USCIS's Dari uses three different renderings (`پیرول`, `اقامت مشروط`, `اقامه موقت`). The demo audience is Afghan parolees, so this one matters.
3. **application for asylum and for withholding of removal** / **withholding of removal**. USCIS's Dari page itself is inconsistent (`عدم اخراج` vs `حذف اخراج`).
4. **affirmative asylum** (`پناهندگی ایجابی`). USCIS's Dari rendering reads as "general asylum approval", so I made my own; it needs a native eye.
5. **dismissal** (`لغو درخواست`) vs **denial** (`رد`): two different outcomes. A family must not confuse them.
6. **derivative** (`مشتق`): official, but opaque on its own. Consider the plainer phrase in the note.
7. **marriage certificate** (`نکاح خط`), **birth certificate**, **identity document** (not `تذکره`): Afghan-specific choices.
8. **exceptional circumstances** (`شرایط استثنایی`): must stay distinct from *extraordinary* circumstances (`شرایط فوق العاده`).
Also: the Dari HTML page mixes Afghan and Iranian forms; the checker should flag any official row that reads as Iranian.

**Nepali (`review_ne.csv`).** Only 8 rows are official, all court terms. Review first:
1. **interpreter** (`दोभाषे`, a seed term; the NYC flyer spells it `दोभासे`).
2. **parole** (`प्यारोल (अस्थायी प्रवेश अनुमति)`): `प्यारोल` alone can mean release from prison.
3. **affirmative asylum**, **derivative**, **withholding of removal**, **dismissal** vs **denial**: legal concepts with no settled Nepali term.
4. **work permit** (avoid `श्रम स्वीकृति`, Nepal's permit to work abroad), **case status** (`केस` vs `मुद्दा`).

**Tier 2.** No one on the team reads these languages; every row is official, from a source quoted in its locator. The Pashto `accredited representative` (`باوري استازي`) is taken as written in the source and may be an inflected form.

## Morning to-dos for person 2

1. Review and merge `lauren-glossary`.
2. Ask person 1 to call the loader from `app.db.reset` (e.g. `await load.load(load.read_rows())` after seeding). A reset drops the glossary table, and the seed's three Spanish rows are a subset of `terms.csv`.
3. Ask person 3 to have the deep pass pick the brief's `glossary_terms` from `terms.csv`'s English terms, spelled exactly: the dashboard matches by exact lowercase string (`api/suggestions.py`).
4. Run `python -m app.glossary.load` against the shared database only after telling the team. A dry run first: `python -m app.glossary.load --dry-run`.
5. Send `review_fa.csv` and `review_ne.csv` to the checkers. After checking, copy fixes into `terms.csv`, mark checked rows `community`, and regenerate the sheets with `tools/review_sheet.py`.

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
- **What counts as an exact pair.** Besides glossary entries, a pair counts as `official` when an English USCIS/NYC page and its official translation render the term in the same sentence; the locator quotes the English. A plural in the source was recorded in the singular (noted on the row), and Russian phrases in their dictionary form (source form in the locator). Those Russian rows are the loosest official entries; downgrade them if you disagree.
- **Farsi sources for Dari rows.** A Farsi government pair is cited for a `fa` row only where the Dari words are identical (2 rows). Everywhere else the Farsi goes into `note`.
- **Right-to-left PDFs.** Dari PDF text with split lam-alef or words split across lines was not used for `official` (`scam` and `asylum officer` are machine, "extraction uncertain"). The Farsi and Arabic NYC flyers extract clean letters in visual order; I rebuilt word order for 2 Farsi and used 6 Arabic phrases already in reading order, skipping any that needed affixes removed.
- **Exact phrase over a parenthetical.** The Arabic A-number row keeps only `رقم تعريف الأجنبي`, because bidi reordering in the PDF separates the `(A-number)` from it.
- **Terms not on the starting list** (exceptional circumstances, contract interpreter, derivative, etc.) and the dropped ones are explained under the term list. "Good cause" was replaced by "exceptional circumstances" because that is USCIS's rescheduling standard.
- **`notario`** is `machine` in every language: the sources pair "notario público", not the bare term.
- **PDF extraction** ran in a throwaway venv in my scratch folder, not the shared `.venv`, so no one else's environment changed. `tools/` holds the scripts.
- **`backend/AGENTS.md`**: `glossary/` shared a row with `research/` (owner 3). I removed `glossary/` from that row and gave it its own row; the research row is otherwise unchanged.
- **Package docstring** `glossary/__init__.py` now names person 2 as owner (was person 3).
- **Review sheet order**: machine rows first, since they need a checker most.

## Progress log

- Setup: worktree `../calhacks-glossary` on `lauren-glossary` from `origin/main` (e188693). Read CLAUDE.md, AGENTS.md, Plan.md glossary lines, writer, table, seed, suggestions, translation.
- Phase 1 (sources): downloaded court glossaries (Judicial Council 2025 es; Contra Costa/Sacramento set), USCIS en/es page pairs, USCIS Dari/Pashto Afghan pages and PDFs, NYC MOIA Immigration Court 101 in 10 languages. Most Sacramento glossaries are legacy-font or definition-only; see SOURCES.md. Extraction tools in `tools/`.
- Phase 2 (terms): 75 core terms, list and reasons above.
- Phase 3 (es): 75 rows, 68 official (USCIS en/es page twins + Judicial Council 2025 glossary), 7 machine. Each official translation checked against the downloaded source text.
- Phase 4 (fa = Dari): 75 rows, 36 official (USCIS Dari page and flyers, 2 from NYC MOIA's Farsi flyer where Dari is identical), 39 machine. Farsi variant for every row in review_fa.csv (machine rows first). Generator: tools/review_sheet.py.
- Phase 5 (ne): 75 rows, 8 official (NYC MOIA Immigration Court 101, Nepali; only words that extracted clean), 67 machine. review_ne.csv written.
- Phase 6 (Tier 2, official only): ps 9 (USCIS Pashto page), vi 9, ru 8, ar 6 (NYC MOIA Immigration Court 101). Russian rows use the dictionary form of inflected source phrases (locator gives the source form). Left out: Punjabi, Urdu, Hindi (see SOURCES.md).
- Phase 7 (loader): `load.py` validates every row (Pydantic), refuses community rows and official rows without a source, lists all bad rows; `--dry-run` and `--language`. Dry run: 257 rows, 75 terms. Never run without --dry-run tonight.
- Phase 8 (tests): `backend/tests/test_glossary.py`, 14 tests, offline (`add_term` faked; dry run asserts settings are never read).
- Phase 9 (docs): `glossary/` row in backend/AGENTS.md (owner 2, contents, load command); one line in docs/whatsapp-pipe.md's file table.
- Phase 10 (gate): `ruff format . && ruff check --fix . && pytest` from the worktree root: ruff reformatted only `load.py`; 557 passed, 17 skipped (DB tests skip without TEST_DATABASE_URL). No failures in anyone's code.
- Phase 11: pushed `lauren-glossary` to origin. Not merged.
