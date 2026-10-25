"use client";

import { Header } from "@/components/Header";
import { Icon, type IconName } from "@/components/Icon";
import { demoUsers } from "@/lib/demoUsers";
import { useStrings } from "@/lib/i18n";

import { ChatDemo } from "./ChatDemo";
import { ClosingBand } from "./ClosingBand";
import { Mascot } from "./Mascot";
import { Promises } from "./Promises";
import { Reveal } from "./Reveal";
import { Steps } from "./Steps";
import { TryActions } from "./TryActions";
import { useTryLinks } from "./useTryLinks";
import styles from "./Landing.module.css";

const PERK_ICONS: IconName[] = ["chat", "book", "shield"];

/**
 * The first page people see: one clear way in (WhatsApp), the chat they'll have,
 * how it works in three steps, our promises, and the ask again over a painting.
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
                <span>{t.headline[0]}</span> <span>
                  <span className="mark">{t.headline[1]}</span>
                </span>
              </h1>
              <p className={styles.sub}>{t.sub}</p>
              <TryActions links={links} qrSize={96} scan={false} dashboards={demoUsers()} />
              <ul className={styles.perks}>
                {t.perks.map((perk, i) => (
                  <li key={perk}>
                    <Icon name={PERK_ICONS[i] ?? "check"} size={16} />
                    {perk}
                  </li>
                ))}
              </ul>
            </div>
            <div className={styles.demo}>
              <ChatDemo />
              <div className={styles.buddy}>
                <Mascot size={124} wave />
              </div>
            </div>
          </section>
        </div>

        <div className={`${styles.wrap} ${styles.section}`}>
          <Reveal>
            <Steps />
          </Reveal>
        </div>

        {/* Full-width forest band: a clear break between "how" and "trust". */}
        <div className={styles.promiseBand}>
          <div className={styles.wrap}>
            <Reveal>
              <Promises />
            </Reveal>
          </div>
        </div>

        <div className={`${styles.wrap} ${styles.closing}`}>
          <Reveal>
            <ClosingBand links={links} />
          </Reveal>
        </div>
      </main>
    </div>
  );
}
