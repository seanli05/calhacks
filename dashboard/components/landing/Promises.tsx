"use client";

import { Icon } from "@/components/Icon";
import { useStrings } from "@/lib/i18n";

import { Mascot } from "./Mascot";
import styles from "./Promises.module.css";

/**
 * Our product rules, on the forest band (Landing): four short promises in one row,
 * signed by Avocado. Short enough to read in one glance.
 */
export function Promises() {
  const t = useStrings().landing.promises;
  return (
    <section className={styles.band}>
      <header className={styles.head}>
        <div>
          <h2 className={styles.title}>{t.title}</h2>
          <p className={styles.sub}>{t.sub}</p>
        </div>
        <div className={styles.sign}>
          <div>
            <p className={styles.signoff}>{t.signoff}</p>
            <p className={styles.name}>Avocado</p>
          </div>
          <span className={styles.buddy}>
            <Mascot size={52} />
          </span>
        </div>
      </header>
      <ul className={styles.list}>
        {t.items.map((item, i) => (
          <li key={i} className={styles.item}>
            <span className={styles.tick} aria-hidden="true">
              <Icon name="check" size={15} />
            </span>
            <h3>{item.title}</h3>
            <p>{item.body}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
