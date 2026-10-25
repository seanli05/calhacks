"use client";

import type { GlossaryEntry } from "@/lib/api/types";
import { searchGlossary } from "@/lib/glossary";
import { stringsFor, useLang } from "@/lib/i18n";

import styles from "./GlossaryBook.module.css";

function domain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/**
 * The translation book beside the live call: search it in either language, or see
 * the words the call has used so far, newest first. Each entry says where its
 * translation comes from, so an official USCIS wording reads as one. `flash` marks
 * the entry the user just picked in the transcript. `browse` (the Key terms tab)
 * lists the whole book when there's no search.
 */
export function GlossaryBook({
  entries,
  seen,
  query,
  flash,
  onQuery,
  browse = false,
}: {
  entries: GlossaryEntry[];
  seen: GlossaryEntry[];
  query: string;
  flash: GlossaryEntry | null;
  onQuery: (query: string) => void;
  browse?: boolean;
}) {
  const { lang } = useLang();
  const t = stringsFor(lang).case.live;
  const rows = query.trim() ? searchGlossary(entries, query) : browse ? entries : seen;

  return (
    <section className={styles.book} aria-labelledby="book-title">
      <div className={styles.head}>
        <span className="label" id="book-title">
          {t.book}
        </span>
        <input
          type="search"
          className={styles.search}
          placeholder={t.search}
          aria-label={t.searchLabel}
          value={query}
          onChange={(e) => onQuery(e.target.value)}
        />
      </div>
      {!query.trim() && !browse && seen.length > 0 && <p className={styles.sub}>{t.fromCall}</p>}
      {query.trim() && rows.length === 0 && <p className={styles.sub}>{t.none}</p>}
      <ul className={styles.rows}>
        {rows.map((e) => (
          <li key={e.term} className={`${styles.row} ${e === flash ? styles.flash : ""}`}>
            <b>{e.translation}</b>
            <span className={`${styles.trust} ${styles[e.trust_level]}`}>{t.trust[e.trust_level]}</span>
            {/* The source sits under the word, so a long domain never squeezes it. */}
            <span className={styles.term} lang="en">
              {e.term}
              {e.source_url && (
                <>
                  {" · "}
                  <a className={styles.source} href={e.source_url} target="_blank" rel="noopener noreferrer">
                    {domain(e.source_url)} ↗
                  </a>
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
