"use client";

import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";

import { Header } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { api } from "@/lib/api/client";
import { usePoll } from "@/lib/api/hooks";
import { useStrings } from "@/lib/i18n";
import { waLink } from "@/lib/whatsapp";

import styles from "./Landing.module.css";

/** Square QR in forest on white; hex because the SVG attributes can't read CSS vars. */
const QR_FG = "#0e3b2c";

/**
 * The page judges see first: what the product does, a QR that opens WhatsApp with
 * the sandbox join message prefilled, and a link into the live dashboard.
 */
export function Landing() {
  const t = useStrings().landing;
  const config = usePoll(() => api.config(), "config", 60_000).data;
  const demo = usePoll(() => api.demo(), "demo", 10_000).data;
  const join = config ? waLink(config.whatsapp_number, config.sandbox_join_message ?? "") : null;
  const demoHref = demo ? (demo.case_id ? `/u/${demo.user_id}/cases/${demo.case_id}` : `/u/${demo.user_id}`) : null;

  return (
    <div className={styles.page}>
      <Header />
      <main className={styles.main}>
        <section className={styles.hero}>
          <div className={styles.copy}>
            <h1 className={styles.headline}>
              <span>{t.headline[0]}</span> <span className="mark">{t.headline[1]}</span>
            </h1>
            <p className={styles.sub}>{t.sub}</p>
            {demoHref && (
              <Link href={demoHref} className={`btn primary ${styles.cta}`}>
                {t.openDemo}
                <Icon name="arrow" />
              </Link>
            )}
          </div>

          <div className={`card ${styles.try}`}>
            <div className={styles.qr} aria-hidden={!join}>
              {join && <QRCodeSVG value={join} size={232} fgColor={QR_FG} bgColor="#ffffff" level="M" title={t.scan} />}
            </div>
            <div className={styles.tryText}>
              <p className={styles.scan}>{t.scan}</p>
              {config?.sandbox_join_message && (
                <>
                  <p className={styles.then}>{t.thenSend}</p>
                  <p className={`mono ${styles.code}`}>{config.sandbox_join_message}</p>
                </>
              )}
              {join && (
                <a href={join} className={`btn ${styles.phone}`} target="_blank" rel="noreferrer">
                  <Icon name="chat" />
                  {t.openOnPhone}
                </a>
              )}
            </div>
          </div>
        </section>

        <section aria-label={t.stepsLabel}>
          <p className="label">{t.stepsLabel}</p>
          <ol className={styles.steps}>
            {t.steps.map((step, i) => (
              <li key={i} className={styles.step}>
                <span className={styles.num}>{i + 1}</span>
                <h2>{step.title}</h2>
                <p>{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <p className={styles.privacy}>
          <Icon name="memory" />
          {t.privacy}
        </p>
      </main>
    </div>
  );
}
