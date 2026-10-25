"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
import { MiniLetter } from "@/components/MiniLetter";
import { useNow } from "@/lib/api/hooks";
import type { CaseDetail } from "@/lib/api/types";
import { clockTime, daysUntil, intlLocale, longDate } from "@/lib/format";
import { useLang, useStrings } from "@/lib/i18n";
import { englishBelow } from "@/lib/localized";

import styles from "./TodoView.module.css";

/** The ticked checklist items live in this browser only: a convenience, not a record. */
function readTicked(key: string): number[] {
  try {
    const v = JSON.parse(window.localStorage.getItem(key) ?? "[]");
    return Array.isArray(v) ? v.filter((i) => typeof i === "number") : [];
  } catch {
    return [];
  }
}

function storeTicked(key: string, ticked: number[]): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(ticked));
  } catch {
    // Private windows can refuse storage; the ticks just aren't remembered.
  }
}

/**
 * The "What to do" tab: what the letter asks of the family. The first card adapts to
 * the letter: an appointment (when, where, a countdown and a map link), a deadline,
 * or just what the letter asks. Then a checklist to tick off, what the letter says
 * in plain words, the letter itself (opens in a drawer) and its masked numbers.
 */
export function TodoView({ detail, onViewLetter }: { detail: CaseDetail; onViewLetter: () => void }) {
  const { lang } = useLang();
  const s = useStrings();
  const t = s.case;
  const now = useNow(60_000);
  const appt = detail.appointment;
  const storageKey = `dashboard.checklist.${detail.id}`;
  const [ticked, setTicked] = useState<number[]>([]);

  useEffect(() => setTicked(readTicked(storageKey)), [storageKey]);

  const toggle = (i: number) => {
    const next = ticked.includes(i) ? ticked.filter((x) => x !== i) : [...ticked, i];
    setTicked(next);
    storeTicked(storageKey, next);
  };
  const countdown = (date: string) =>
    new Intl.RelativeTimeFormat(intlLocale(lang), { numeric: "auto" }).format(daysUntil(date, now), "day");
  const docType = (detail.doc_type && s.common.docTypes[detail.doc_type]) || s.common.docTypeFallback;
  const done = detail.checklist.filter((_, i) => ticked.includes(i)).length;

  return (
    <div className={styles.grid}>
      <div className={styles.col}>
        {appt ? (
          <section className={`card ${styles.when}`} aria-labelledby="when-title">
            <span className="label" id="when-title">
              {t.appt.title}
            </span>
            <p className={styles.date}>{longDate(appt.date, lang)}</p>
            <p className={styles.time}>
              {appt.time && <span>{clockTime(appt.time, lang)}</span>}
              <span className={`pill ${styles.countdown}`}>{countdown(appt.date)}</span>
            </p>
            {appt.location && (
              <p className={styles.place}>
                <span>{appt.location}</span>
                <a
                  href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(appt.location)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t.appt.maps} ↗
                </a>
              </p>
            )}
          </section>
        ) : detail.deadline ? (
          <section className={`card ${styles.when}`} aria-labelledby="when-title">
            <span className="label" id="when-title">
              {t.todo.deadline}
            </span>
            <p className={styles.date}>{longDate(detail.deadline, lang)}</p>
            <p className={styles.time}>
              <span className={`pill warn ${styles.countdown}`}>{countdown(detail.deadline)}</span>
            </p>
            {detail.what_is_asked && <p className={styles.place}>{detail.what_is_asked.text}</p>}
          </section>
        ) : (
          detail.what_is_asked && (
            <section className={`card ${styles.when}`} aria-labelledby="when-title">
              <span className="label" id="when-title">
                {t.todo.asks}
              </span>
              <p className={styles.asks}>{detail.what_is_asked.text}</p>
              {englishBelow(detail.what_is_asked, lang) && <small>{detail.what_is_asked.en}</small>}
            </section>
          )
        )}

        {detail.checklist.length > 0 && (
          <section className={`card ${styles.checklist}`} aria-labelledby="checklist-title">
            <div className={styles.listHead}>
              <span className="label" id="checklist-title">
                {t.appt.beforeYouGo}
              </span>
              <span className={styles.progress}>{t.appt.ready(done, detail.checklist.length)}</span>
            </div>
            <div className={styles.bar} aria-hidden="true">
              <span style={{ width: `${(done / detail.checklist.length) * 100}%` }} />
            </div>
            <ul>
              {detail.checklist.map((c, i) => {
                const on = ticked.includes(i);
                return (
                  <li key={i}>
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked={on}
                      className={`${styles.item} ${on ? styles.done : ""} ${c.kind === "who_must_come" ? styles.must : ""}`}
                      onClick={() => toggle(i)}
                    >
                      <span className={styles.box}>{on && <Icon name="check" size={14} />}</span>
                      <span className={styles.itemText}>
                        <span className={styles.kind}>{t.kinds[c.kind]}</span>
                        {c.item.text}
                        {englishBelow(c.item, lang) && <small>{c.item.en}</small>}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        )}
      </div>

      <div className={styles.col}>
        {detail.explanation && (
          <section className={`card ${styles.says}`} aria-labelledby="says-title">
            <span className="label" id="says-title">
              {t.appt.says}
            </span>
            <p>{detail.explanation.text}</p>
            {englishBelow(detail.explanation, lang) && <small>{detail.explanation.en}</small>}
          </section>
        )}

        <button type="button" className={`card ${styles.letter}`} onClick={onViewLetter}>
          <MiniLetter mediaId={detail.page_media_ids[0] ?? null} width={64} />
          <span className={styles.letterText}>
            <b>{docType}</b>
            {detail.issuer && <span>{detail.issuer}</span>}
          </span>
          <span className={styles.open}>{t.appt.viewLetter} →</span>
        </button>

        {detail.refs.length > 0 && (
          <section className={`card ${styles.numbers}`} aria-labelledby="numbers-title">
            <span className="label" id="numbers-title">
              {t.appt.numbers}
            </span>
            <dl>
              {detail.refs.map((r) => (
                <div key={r.name}>
                  <dt>{t.refs[r.name] ?? r.name}</dt>
                  <dd className="mono">{r.masked}</dd>
                </div>
              ))}
            </dl>
            <p>
              <Icon name="lock" size={14} /> {t.appt.numbersNote}
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
