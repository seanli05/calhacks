"use client";

import type { LiveCall } from "@/lib/api/hooks";
import { stringsFor, useLang } from "@/lib/i18n";
import { englishBelow } from "@/lib/localized";

import styles from "./LiveTips.module.css";

/**
 * What the user could say next, newest first: English to read out loud with its
 * meaning, or a plain "answer this yourself" when the officer asks something only
 * the user may answer (rule 3). Tips the user already said fade back.
 */
export function LiveTips({ tips }: { tips: LiveCall["tips"] }) {
  const { lang } = useLang();
  const t = stringsFor(lang).case.live;

  return (
    <section className={`card ${styles.tips}`} aria-labelledby="tips-title">
      <div className="label" id="tips-title">
        {t.tipsTitle}
      </div>
      {[...tips].reverse().map((tip) => (
        <article
          key={tip.id}
          className={`${styles.tip} ${tip.kind === "yourself" ? styles.yourself : ""} ${tip.used ? styles.used : ""}`}
        >
          <span className={styles.kind}>{tip.used ? `✓ ${t.used}` : tip.kind === "ask" ? t.ask : t.yourself}</span>
          {tip.say_en && <p className={styles.say}>“{tip.say_en}”</p>}
          {(!tip.say_en || englishBelow(tip.meaning, lang)) && <p className={styles.meaning}>{tip.meaning.text}</p>}
        </article>
      ))}
    </section>
  );
}
