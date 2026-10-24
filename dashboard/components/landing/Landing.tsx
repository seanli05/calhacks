"use client";

import { Header } from "@/components/Header";
import { useStrings } from "@/lib/i18n";

import { Bento } from "./Bento";
import { ClosingBand } from "./ClosingBand";
import { LiveCallDemo } from "./LiveCallDemo";
import { Promises } from "./Promises";
import { Ticker } from "./Ticker";
import { TryActions } from "./TryActions";
import { useTryLinks } from "./useTryLinks";
import styles from "./Landing.module.css";

/**
 * The page judges see first: a hero with a looping call, a ticker of what every call
 * guarantees, a bento of the product, our promises, and the ask again over a painting.
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
        <div className={styles.wrap}>
          <section className={styles.hero}>
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
          <Ticker />
        </div>

        <div className={`${styles.wrap} ${styles.section}`}>
          <Bento links={links} />
        </div>

        <div className={`${styles.wrap} ${styles.section}`}>
          <Promises />
        </div>

        <div className={`${styles.wrap} ${styles.closing}`}>
          <ClosingBand links={links} />
        </div>
      </main>
    </div>
  );
}
