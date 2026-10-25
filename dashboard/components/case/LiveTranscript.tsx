"use client";

import { useEffect, useRef } from "react";

import type { LiveLine } from "@/lib/api/hooks";
import type { GlossaryEntry } from "@/lib/api/types";
import { findTerms } from "@/lib/glossary";
import { stringsFor, useLang } from "@/lib/i18n";

import styles from "./LiveTranscript.module.css";

/**
 * Both legs of the bridged call in the viewer's language, each line streaming in a
 * word or two at a time with the English it came from muted below. Words in the
 * translation book are underlined; picking one opens it in the book.
 */
export function LiveTranscript({
  lines,
  glossary,
  onTerm,
}: {
  lines: LiveLine[];
  glossary: GlossaryEntry[];
  onTerm: (entry: GlossaryEntry) => void;
}) {
  const { lang } = useLang();
  const t = stringsFor(lang).case;
  const scrollRef = useRef<HTMLDivElement>(null);
  const last = lines[lines.length - 1];

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [lines.length, last?.text]);

  return (
    <div className={styles.wrap} ref={scrollRef} aria-live="polite">
      <div className={styles.head}>
        <span className={styles.wave} aria-hidden>
          <i />
          <i />
          <i />
          <i />
        </span>
        <span className="label">{t.live.title}</span>
      </div>
      {lines.length === 0 && <p className={styles.waiting}>{t.live.waiting}</p>}
      {lines.map((line) => (
        <div key={line.id} className={`${styles.line} ${styles[line.speaker] ?? ""}`}>
          <span className={styles.who}>{t.speakers[line.speaker]}</span>
          <div className={styles.body}>
            <p className={styles.text}>
              {findTerms(line.text, glossary, lang === "en" ? "term" : "translation").map((seg, i) =>
                seg.entry ? (
                  <button key={i} type="button" className={styles.term} onClick={() => onTerm(seg.entry!)}>
                    {seg.text}
                  </button>
                ) : (
                  <span key={i}>{seg.text}</span>
                ),
              )}
              {!line.done && <span className={styles.caret} aria-hidden />}
            </p>
            {lang !== "en" && <p className={styles.en} lang="en">{line.en}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}
