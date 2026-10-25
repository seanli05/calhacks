"use client";

import type { GlossaryEntry } from "@/lib/api/types";
import { domainOf } from "@/lib/format";
import { searchGlossary } from "@/lib/glossary";
import { useStrings } from "@/lib/i18n";

import styles from "./WordsView.module.css";

/**
 * The Key words tab: the translation book as cards. Words from this letter come
 * first (and words heard on the call, while there is one), then the whole book.
 * Each card says where its translation comes from, so official wording reads as one.
 */
export function WordsView({
  entries,
  inLetter,
  heard,
  query,
  onQuery,
}: {
  entries: GlossaryEntry[];
  inLetter: GlossaryEntry[];
  heard: GlossaryEntry[];
  query: string;
  onQuery: (query: string) => void;
}) {
  const t = useStrings().case;
  const searching = query.trim().length > 0;
  const results = searching ? searchGlossary(entries, query) : [];
  const shown = new Set([...heard, ...inLetter]);
  const rest = entries.filter((e) => !shown.has(e));

  return (
    <div className={styles.wrap}>
      <input
        type="search"
        className={styles.search}
        placeholder={t.live.search}
        aria-label={t.live.searchLabel}
        value={query}
        onChange={(e) => onQuery(e.target.value)}
      />
      {searching ? (
        results.length ? (
          <Section entries={results} />
        ) : (
          <p className={styles.none}>{t.live.none}</p>
        )
      ) : (
        <>
          {heard.length > 0 && <Section title={t.words.onCall} entries={heard} />}
          {inLetter.length > 0 && <Section title={t.words.inLetter} entries={inLetter} featured />}
          <Section title={t.words.all} entries={rest} />
        </>
      )}
    </div>
  );
}

function Section({
  title,
  entries,
  featured = false,
}: {
  title?: string;
  entries: GlossaryEntry[];
  featured?: boolean;
}) {
  if (!entries.length) return null;
  return (
    <section className={styles.section}>
      {title && <h2 className="label">{title}</h2>}
      <ul className={`${styles.cards} ${featured ? styles.featured : ""}`}>
        {entries.map((e) => (
          <WordCard key={e.term} entry={e} />
        ))}
      </ul>
    </section>
  );
}

export function WordCard({ entry }: { entry: GlossaryEntry }) {
  const t = useStrings().case.live;
  return (
    <li className={styles.card}>
      <span className={styles.translation}>{entry.translation}</span>
      <span className={styles.term} lang="en">
        {entry.term}
      </span>
      <span className={styles.foot}>
        <span className={`${styles.trust} ${styles[entry.trust_level]}`}>{t.trust[entry.trust_level]}</span>
        {entry.source_url && (
          <a href={entry.source_url} target="_blank" rel="noopener noreferrer">
            {domainOf(entry.source_url)} ↗
          </a>
        )}
      </span>
    </li>
  );
}
