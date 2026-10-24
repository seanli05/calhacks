"use client";

import { Header } from "@/components/Header";
import { useStrings } from "@/lib/i18n";

import { ClosingBand } from "./ClosingBand";
import { FeatureRows } from "./FeatureRows";
import { LiveCallDemo } from "./LiveCallDemo";
import { Promises } from "./Promises";
import { TryActions } from "./TryActions";
import { useTryLinks } from "./useTryLinks";
import styles from "./Landing.module.css";

/**
 * The page judges see first. Hero with a looping call, the three steps as feature
 * rows, our promises, and a closing band; both CTAs open WhatsApp or the live case.
 */
export function Landing() {
  const t = useStrings().landing;
  const links = useTryLinks();

  return (
    <div className={styles.page}>
      <div className={styles.wrap}>
        <Header />
      </div>
      <main>
        <section className={`${styles.wrap} ${styles.hero}`}>
          <div className={styles.copy}>
            <h1 className={styles.headline}>
              <span>{t.headline[0]}</span> <span className="mark">{t.headline[1]}</span>
            </h1>
            <p className={styles.sub}>{t.sub}</p>
            <TryActions links={links} qrSize={112} />
          </div>
          <div className={styles.demo}>
            <LiveCallDemo />
          </div>
        </section>

        <div className={`${styles.wrap} ${styles.section}`}>
          <FeatureRows />
        </div>

        <div className={`${styles.wrap} ${styles.section}`}>
          <Promises />
        </div>

        <ClosingBand links={links} />
      </main>
    </div>
  );
}
