"use client";

import type { GlossaryEntry } from "@/lib/api/types";
import { searchGlossary } from "@/lib/glossary";
import { stringsFor, useLang } from "@/lib/i18n";

import styles from "./GlossaryBook.module.css";

const MAX_ROWS = 6;

function domain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/**
 * The translation book under the live call: search it in either language, or see
 * the words the call has used so far, newest first. Each entry says where its
 * translation comes from, so an official USCIS wording reads as one.
 */
export function GlossaryBook({
  entries,
  seen,
  query,
  onQuery,
}: {
  entries: GlossaryEntry[];
  seen: GlossaryEntry[];
  query: string;
  onQuery: (query: string) => void;
}) {
  const { lang } = useLang();
  const t = stringsFor(lang).case.live;
  const rows = (query.trim() ? searchGlossary(entries, query) : seen).slice(0, MAX_ROWS);

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
      {!query.trim() && seen.length > 0 && <p className={styles.sub}>{t.fromCall}</p>}
      {query.trim() && rows.length === 0 && <p className={styles.sub}>{t.none}</p>}
      <ul className={styles.rows}>
        {rows.map((e) => (
          <li key={e.term} className={styles.row}>
            <b>{e.translation}</b>
            <span className={styles.term}>{e.term}</span>
            <span className={`${styles.trust} ${styles[e.trust_level]}`}>
              {t.trust[e.trust_level]}
              {e.source_url && (
                <a href={e.source_url} target="_blank" rel="noopener noreferrer">
                  {domain(e.source_url)}
                </a>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
