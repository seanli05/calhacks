"use client";

import { useStrings } from "@/lib/i18n";

import { TryActions } from "./TryActions";
import type { TryLinks } from "./useTryLinks";
import styles from "./ClosingBand.module.css";

/** Full-width forest band at the bottom: the ask again, with a big QR. */
export function ClosingBand({ links }: { links: TryLinks }) {
  const t = useStrings().landing.closing;
  return (
    <section className={styles.band}>
      <div className={styles.inner}>
        <div className={styles.copy}>
          <h2 className={styles.title}>
            <span>{t.title[0]}</span> <span className={`mark ${styles.mark}`}>{t.title[1]}</span>
          </h2>
          <p className={styles.sub}>{t.sub}</p>
        </div>
        <TryActions links={links} qrSize={168} onDark />
      </div>
    </section>
  );
}
