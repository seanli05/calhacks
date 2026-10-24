"use client";

import { useStrings } from "@/lib/i18n";

import styles from "./Promises.module.css";

/** Our product rules, said as promises. The trust band in place of logos and quotes. */
export function Promises() {
  const t = useStrings().landing.promises;
  return (
    <section className={styles.band}>
      <h2 className={styles.title}>{t.title}</h2>
      <ol className={styles.grid}>
        {t.items.map((item, i) => (
          <li key={i} className={styles.item}>
            <span className={styles.x} aria-hidden="true">
              ✕
            </span>
            <h3>{item.title}</h3>
            <p>{item.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
