"use client";

import { Icon } from "@/components/Icon";
import type { CaseDetail } from "@/lib/api/types";
import { formatNumber } from "@/lib/format";
import { useLang, useStrings } from "@/lib/i18n";
import { englishBelow } from "@/lib/localized";

import styles from "./ScamView.module.css";

/** Where to report immigration scams: USCIS's own page and the FTC's. */
const REPORT_USCIS = "https://www.uscis.gov/report-fraud";
const REPORT_FTC = "https://reportfraud.ftc.gov";

/**
 * The overview of a letter research flagged as a scam: a clear warning, the red
 * flags it found (the reasoning), and what to do and not do. Nothing else from the
 * case shows, so there's nothing to act on by mistake.
 */
export function ScamView({ detail }: { detail: CaseDetail }) {
  const { lang } = useLang();
  const t = useStrings().case.scam;
  const flags = detail.verification?.red_flags ?? [];

  return (
    <section className={`card ${styles.scam}`} aria-labelledby="scam-title">
      <div className={styles.head}>
        <span className={styles.icon} aria-hidden="true">
          <Icon name="warn" size={26} />
        </span>
        <div>
          <h2 id="scam-title">{t.title}</h2>
          <p>{t.sub}</p>
        </div>
      </div>

      <div className={styles.body}>
        {flags.length > 0 && (
          <div className={styles.block}>
            <span className="label">{t.why}</span>
            <ol className={styles.flags}>
              {flags.map((f, i) => (
                <li key={i}>
                  <span className={styles.n}>{formatNumber(i + 1, lang)}</span>
                  <span dir="auto">
                    {f.text}
                    {englishBelow(f, lang) && <small>{f.en}</small>}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}

        <div className={styles.block}>
          <span className="label">{t.doNow}</span>
          <ul className={styles.dont}>
            {t.dont.map((d) => (
              <li key={d}>
                <Icon name="close" size={16} />
                <span>{d}</span>
              </li>
            ))}
          </ul>
          <div className={styles.report}>
            <a className="btn" href={REPORT_USCIS} target="_blank" rel="noopener noreferrer">
              {t.report} ↗
            </a>
            <a className="btn" href={REPORT_FTC} target="_blank" rel="noopener noreferrer">
              {t.reportFtc} ↗
            </a>
          </div>
        </div>
      </div>

      <p className={styles.foot}>
        <Icon name="shield" size={16} />
        <span>
          {t.real} {t.stopped}
        </span>
      </p>
    </section>
  );
}
