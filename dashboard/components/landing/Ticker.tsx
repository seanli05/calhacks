"use client";

import { useStrings } from "@/lib/i18n";

import styles from "./Ticker.module.css";

/** A slow marquee of what every call guarantees. The list is doubled so the loop is seamless. */
export function Ticker() {
  const t = useStrings().landing.ticker;
  const items = (hidden: boolean) =>
    t.items.map((item) => (
      <li key={`${hidden}-${item.k}`} aria-hidden={hidden || undefined}>
        <span className={styles.k}>{item.k}</span>
        <span className={`mono ${styles.v}`}>{item.v}</span>
      </li>
    ));
  return (
    <div className={styles.strip}>
      <span className={styles.label}>
        <span className={styles.dot} />
        {t.label}
      </span>
      <div className={styles.viewport}>
        <ul className={styles.track}>
          {items(false)}
          {items(true)}
        </ul>
      </div>
    </div>
  );
}
