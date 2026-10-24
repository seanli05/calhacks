# Glossary sources

Every source looked at for `terms.csv`, used or not. Files were downloaded into `_sources/` (git-ignored) and turned into text with `tools/extract_pdf.py` (PDFs) or `tools/html_text.py` (HTML). Only term pairs were taken, never definitions or sentences. Accessed 2026-10-24.

"Used" means at least one `official` row cites it. A row is `official` only if the exact pair is in the source: same entry in a glossary, or the same sentence in the English page and its official translation.

## Used

| Source | Publisher | URL | Languages | Format, date | Terms / notice | Used for |
|---|---|---|---|---|---|---|
| Legal Glossary English–Spanish | Judicial Council of California (Language Access) | https://languageaccess.courts.ca.gov/system/files/2025-05/Legal%20Glossary%20English%20Spanish.pdf | en, es | PDF, two-column term list, May 2025, 14 pp. | Site footer links Terms of Use (courts.ca.gov/about/terms-use) and a disclaimer; no copyright notice on the document | `es` legal terms |
| English/Spanish Legal Glossary (Sacramento Superior Court, rev. 08/06) | Superior Court of California, County of Sacramento, republished by Contra Costa Superior Court | https://contracosta.courts.ca.gov/system/files/general/spanish-legal-glossary.pdf | en, es | PDF, headword + definition in each language, 2006 | Disclaimer: "for general reference purposes only", a "work-in-progress", not legal advice | `es` cross-check, a few terms |
| USCIS English pages and their official Spanish versions (`hreflang="es"`): The Affirmative Asylum Process; Asylum; Obtaining Asylum in the United States; Affirmative Asylum Interview Scheduling; I-589; Common Scams; Find Legal Services; Preparing for Your Biometric Services Appointment; Employment Authorization Document; Change of Address; USCIS Contact Center | U.S. Citizenship and Immigration Services | https://www.uscis.gov/humanitarian/refugees-and-asylum/asylum/the-affirmative-asylum-process and the other pages under uscis.gov (Spanish twins under uscis.gov/es/…) | en, es | HTML, live pages | U.S. government work | `es` immigration terms (pair = same sentence in both versions) |
| Information for Afghan Nationals (English, Dari, Pashto pages) | USCIS | https://www.uscis.gov/humanitarian/information-for-afghans ; https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari ; https://www.uscis.gov/humanitarian/information-for-afghans-pashto-translation | en, fa (Dari), ps | HTML, live pages | U.S. government work | `fa` (Dari) and `ps` immigration terms |
| Applying for Asylum as an Afghan National (English and Dari, rev. 09/09/2022) | USCIS | https://www.uscis.gov/sites/default/files/document/guides/Applying_For_Asylum_as_an_Afghan_National_FINAL.pdf ; …/Applying_For_Asylum_as_an_Afghan_National_DARI_FINAL.pdf | en, fa (Dari) | PDF | U.S. government work. Dari PDF text extracts with split lam-alef (`اال` for `ال`) and stray spaces; only clean words were used | `fa` asylum terms |
| Avoid Scams flyer for Afghan Nationals (English and Dari) | USCIS | https://www.uscis.gov/sites/default/files/document/flyers/AvoidScamsFlyerAfghanNationalsEn.pdf ; …/AvoidScamsFlyerAfghanNationalsDr.pdf | en, fa (Dari) | PDF | as above | `fa` scam terms |
| Immigration Legal Services for Afghan Arrivals (English and Dari) | USCIS | https://www.uscis.gov/sites/default/files/document/flyers/Immigration%20Legal%20Services%20for%20Afghan%20Arrivals.pdf ; …(Dari).pdf | en, fa (Dari) | PDF | as above | `fa` legal-help terms |
| Tips to Help You Through the Asylum Process (Dari) | USCIS | https://www.uscis.gov/sites/default/files/document/flyers/TipSheetAsylumProcessingDari.pdf | fa (Dari) | PDF | English original not found (guessed URLs 404); used only to confirm a Dari word already paired elsewhere | `fa` cross-check |
| Immigration Court 101 (2026), in English, Spanish, Farsi-Persian, Nepali, Arabic, Russian, Vietnamese, Punjabi, Urdu, "Hindi" | NYC Mayor's Office of Immigrant Affairs (city government) | https://www.nyc.gov/assets/immigrants/downloads/pdf/Immigration-Court-101-2026-English.pdf (swap the language name) | as listed | PDF flyer, 2 pp., 2026 | "General information … not legal advice"; no copyright notice | `ne` (clean words only), Farsi variants in `fa` notes, Tier 2 `ar`, `ru`, `vi` |

## Downloaded, not used

| Source | Why not |
|---|---|
| Contra Costa / Sacramento legal glossaries: Arabic, Western Armenian, Punjabi, Hindi (4 vols), Vietnamese (2005–2007) | Built with legacy non-Unicode fonts (Arabic and Armenian glyph fonts, Kruti Dev Hindi, AnmolLipi Punjabi, VNI Vietnamese): text extracts as Latin junk. Converting would be a guess, so these were left out |
| Same set: Russian, Romanian | Only the definitions are translated; headwords stay in English, so there are no term pairs |
| Same set: Urdu parts 1–6 | Part 1 is the English half; parts 2–6 (the Urdu) are scanned images with no text layer |
| Same set: English monolingual | No translations |
| USCIS Spanish glossary (uscis.gov/es/herramientas/glosario) and English glossary (uscis.gov/tools/glossary) | Spanish entries have no English headword, so pairing them would be inference, not an exact pair |
| NYC MOIA Immigration Court 101, "Hindi" file | The file labeled Hindi is in Igbo (publisher mix-up) |
| NYC MOIA Immigration Court 101, Urdu and Punjabi | Urdu text extracts broken; Punjabi has doubled vowel signs and stray Latin letters in key words. Not trustworthy enough for official-only Tier 2 |
| NYC MOIA "Services for Recently Arrived Immigrants" (2019) | English only on the guessed URLs; translated versions 404 |
| USCIS: Lawful Immigration Pathways (Dari), Information Sheet for Afghan Parole (Dari), How to Create a USCIS Online Account (Dari/Pashto) | Downloaded; English originals not found or not relevant to the term list |

## Dead ends

| Where | What happened |
|---|---|
| saccourt.ca.gov legal glossaries page | TLS certificate expired; not worked around |
| uscis.gov/forms/all-forms/form-i-797-types-and-functions, uscis.gov/scams-fraud-and-misconduct/avoid-scams | 404 at these URLs |
| ilsaa.acf.hhs.gov (HHS Afghan resources) | DNS lookup failed |
| USCIS Multilingual Resource Center | Only links to Spanish now; no Nepali or Dari pages found there |
| New York State courts glossaries | No Nepali, Dari, or Farsi glossary found |
| EOIR (justice.gov/eoir) | No published Dari/Farsi or Nepali glossary found |
| Nepali government-published immigration glossary | None found. Kent State GURI's English/Nepali legal glossary exists but is a university project, not government, so not used for `official` |
