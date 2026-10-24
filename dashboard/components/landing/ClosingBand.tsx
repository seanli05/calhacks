"use client";

import { useStrings } from "@/lib/i18n";

import { TryActions } from "./TryActions";
import type { TryLinks } from "./useTryLinks";
import styles from "./ClosingBand.module.css";

/** The ask again at the bottom, over the mountain painting: headline on the sky, CTA card on the right. */
export function ClosingBand({ links }: { links: TryLinks }) {
  const t = useStrings().landing.closing;
  return (
    <section className={styles.band}>
      <div className={styles.copy}>
        <h2 className={styles.title}>
          <span>{t.title[0]}</span> <span className="mark">{t.title[1]}</span>
        </h2>
        <p className={styles.sub}>{t.sub}</p>
      </div>
      <div className={styles.cta}>
        <TryActions links={links} qrSize={150} />
      </div>
    </section>
  );
}
