"use client";

import type { LiveCall } from "@/lib/api/hooks";
import { useLang, useStrings } from "@/lib/i18n";
import { englishBelow } from "@/lib/localized";

import styles from "./YourTurn.module.css";

/**
 * The bar under the live translation that says when the user is needed: pick up
 * the phone while we ring them, answer a question only they may answer (rule 3), or
 * a question they could ask. Otherwise it quietly says we're listening.
 */
export function YourTurn({ ringing, tip }: { ringing: boolean; tip: LiveCall["tips"][number] | null }) {
  const { lang } = useLang();
  const t = useStrings().case.turn;

  if (!ringing && !tip) {
    return (
      <div className={styles.idle} role="status">
        {t.listening}
      </div>
    );
  }

  const yourself = !ringing && tip?.kind === "yourself";
  return (
    <div
      key={ringing ? "ring" : tip?.id}
      className={`${styles.turn} ${yourself || ringing ? styles.urgent : ""}`}
      role="status"
      aria-live="assertive"
    >
      <span className={styles.badge}>
        <span className={styles.dot} aria-hidden="true" />
        {t.label}
      </span>
      {ringing ? (
        <div className={styles.text}>
          <b>{t.phone}</b>
          <span>{t.phoneSub}</span>
        </div>
      ) : tip?.say_en ? (
        <div className={styles.text}>
          <span className={styles.kind}>{t.ask}</span>
          <b lang="en">“{tip.say_en}”</b>
          {englishBelow(tip.meaning, lang) && <span>{tip.meaning.text}</span>}
        </div>
      ) : (
        <div className={styles.text}>
          <span className={styles.kind}>{t.yourself}</span>
          <b>{tip?.meaning.text}</b>
        </div>
      )}
    </div>
  );
}
