"use client";

import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api/client";
import type { Transcript } from "@/lib/api/types";
import { useStrings } from "@/lib/i18n";

import styles from "./TranscriptSheet.module.css";

/** Slide-over with the call transcript. Lines stay in English, the call's language. */
export function TranscriptSheet({ callId, onClose }: { callId: string; onClose: () => void }) {
  const strings = useStrings();
  const t = strings.case;
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [failed, setFailed] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let alive = true;
    api.transcript(callId).then(
      (value) => alive && setTranscript(value),
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [callId]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className={styles.scrim} onClick={onClose} />
      <aside className={styles.sheet} role="dialog" aria-modal="true" aria-labelledby="transcript-title">
        <div className={styles.head}>
          <h2 id="transcript-title">{t.transcript}</h2>
          <button ref={closeRef} type="button" className="btn" onClick={onClose}>
            {t.close}
          </button>
        </div>
        <p className={styles.note}>{t.transcriptNote}</p>
        {failed && <p className={styles.note}>{strings.common.loadError}</p>}
        <div className={styles.lines}>
          {transcript?.lines.map((line, i) => (
            <div key={i} className={`${styles.line} ${styles[line.speaker] ?? ""}`}>
              <span className={styles.who}>{t.speakers[line.speaker]}</span>
              <span lang="en">{line.text}</span>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}
