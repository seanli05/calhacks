# Glossary sources

Every source looked at for `terms.csv`, used or not. Files were downloaded into `_sources/` (git-ignored) and turned into text with `tools/extract_pdf.py` (PDFs) or `tools/html_text.py` (HTML). Only term pairs were taken, never definitions or sentences. Accessed 2026-10-24.

A row is `official` only if the exact pair is in the source: the same entry in a glossary, or the same sentence in an English page and its official translation (the row's `locator` quotes the English). Allowed differences, each noted in the row: a plural in the source given in the singular (Spanish, Dari), and Russian phrases given in their dictionary form.

## Cited by `official` rows

| Source | Publisher | URL | Languages | Format, date | Notice | Rows |
|---|---|---|---|---|---|---|
| Information for Afghan Nationals, Dari page, compared with the English page | USCIS | https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari (English: https://www.uscis.gov/humanitarian/information-for-afghans) | fa (Dari) | HTML, live | U.S. government work | 31 `fa` |
| Information for Afghan Nationals, Pashto page | USCIS | https://www.uscis.gov/humanitarian/information-for-afghans-pashto-translation | ps | HTML, live | U.S. government work | 9 `ps` |
| Avoid Scams flyer for Afghan Nationals (Dari, with the English flyer) | USCIS | https://www.uscis.gov/sites/default/files/document/flyers/AvoidScamsFlyerAfghanNationalsDr.pdf (English: …/AvoidScamsFlyerAfghanNationalsEn.pdf) | fa (Dari) | PDF, 2 pp. | U.S. government work. Text extracts with split lam-alef (`کالهبرداری`); only clean words used | 3 `fa` |
| USCIS Spanish versions (`hreflang="es"`) of: Preparing for Your Affirmative Asylum Interview; The Affirmative Asylum Process; Types of Asylum Decisions; Obtaining Asylum in the United States; Asylum; Preparing for Your Biometric Services Appointment; Common Scams; I-589; Employment Authorization Document; Change of Address; Glossary | USCIS | e.g. https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo (each row has its own URL) | es | HTML, live | U.S. government work | 61 `es` |
| Legal Glossary English–Spanish | Judicial Council of California (Language Access) | https://languageaccess.courts.ca.gov/system/files/2025-05/Legal%20Glossary%20English%20Spanish.pdf | es | PDF term list, May 2025, 14 pp. | Site links Terms of Use (courts.ca.gov/about/terms-use) and a disclaimer | 7 `es` |
| Immigration Court 101 (2026), compared with the English flyer | NYC Mayor's Office of Immigrant Affairs (city government) | https://www.nyc.gov/assets/immigrants/downloads/pdf/Immigration-Court-101-2026-English.pdf (swap the language name: Nepali, Farsi-Persian, Russian, Vietnamese, Arabic) | ne, fa (Farsi), ru, vi, ar | PDF flyer, 2 pp. | "General information … not legal advice" | 8 `ne`, 2 `fa`, 8 `ru`, 9 `vi`, 6 `ar` |

The Farsi flyer is Iranian Farsi. It's cited for a `fa` (Dari) row only where the Dari words are the same (`قاضی مهاجرت`, `اخراج (دیپورت)`); elsewhere it supplies the `farsi:` variant in the note.

## Consulted, quoted only in notes

| Source | Why only in notes |
|---|---|
| USCIS, Applying for Asylum as an Afghan National (English and Dari, rev. 09/09/2022), …/guides/Applying_For_Asylum_as_an_Afghan_National_DARI_FINAL.pdf | PDF text has broken joins; "asylum officer" is split across a line. Used for cautions (`اقامت مشروط` for parole, `شرایط فوق العاده` for *extraordinary* circumstances) |
| USCIS, Immigration Legal Services for Afghan Arrivals (English and Dari), …/flyers/Immigration%20Legal%20Services%20for%20Afghan%20Arrivals%20%28Dari%29.pdf | No exact pair for a core term; shows `اقامه موقت` for humanitarian parole and the Dari for free legal services |
| USCIS, Tips to Help You Through the Asylum Process (Dari), …/flyers/TipSheetAsylumProcessingDari.pdf | English original not found (guessed URLs 404) |
| USCIS Find Legal Services and Contact Center pages (en/es) | Fetched; pairs came from other pages |

## Downloaded, not used

| Source | Why not |
|---|---|
| Sacramento Superior Court legal glossaries (2005–2007), republished at https://contracosta.courts.ca.gov/legal-glossaries: Arabic, Western Armenian, Punjabi, Hindi (4 vols), Vietnamese | Built with legacy non-Unicode fonts (glyph-mapped Arabic and Armenian, Kruti Dev Hindi, AnmolLipi Punjabi, VNI Vietnamese): text extracts as Latin junk. Converting would be a guess |
| Same set: Russian, Romanian | Only the definitions are translated; headwords stay in English, so no term pairs |
| Same set: Urdu parts 1–6 | Part 1 is the English half; parts 2–6 (the Urdu) are scanned images with no text layer |
| Same set: Spanish (2006) | Readable, but every pair it has was also in the newer Judicial Council glossary or on USCIS pages |
| NYC MOIA Immigration Court 101, "Hindi" file | The file labeled Hindi is in Igbo (publisher mix-up) |
| NYC MOIA Immigration Court 101, Urdu and Punjabi | Urdu extracts broken; Punjabi has doubled vowel signs and stray Latin letters in key words |
| NYC MOIA Immigration Court 101, Spanish | Not needed; USCIS Spanish covers the same terms |
| USCIS Dari: Lawful Immigration Pathways, Information Sheet for Afghan Parole, How to Create a USCIS Online Account | English originals not found or not relevant |

## Dead ends

| Where | What happened |
|---|---|
| saccourt.ca.gov legal glossaries page | TLS certificate expired; not worked around (the PDFs were taken from Contra Costa's copy) |
| uscis.gov/forms/all-forms/form-i-797-types-and-functions, uscis.gov/scams-fraud-and-misconduct/avoid-scams | 404 at these URLs |
| ilsaa.acf.hhs.gov (HHS Afghan resources) | DNS lookup failed |
| USCIS Multilingual Resource Center | Links only to Spanish now; no Nepali or Dari pages there |
| New York State courts glossaries | No Nepali, Dari, or Farsi glossary found |
| EOIR (justice.gov/eoir) | No published Dari/Farsi or Nepali glossary found |
| A government Nepali immigration glossary | None found. Kent State GURI's English/Nepali legal glossary is a university project, so not used for `official` |
