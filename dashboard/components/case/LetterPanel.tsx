"use client";

import type { CaseDetail } from "@/lib/api/types";
import { clockTime, domainOf, longDate } from "@/lib/format";
import { useLang, useStrings } from "@/lib/i18n";

import styles from "./LetterPanel.module.css";

/** How the paper header reads for known letter types. Anything else gets a plain page. */
const LETTER_HEADS: Record<string, { agency: string[]; form: string; title: string; notice: string; caseType?: string }> = {
  uscis_i797c_asylum_interview: {
    agency: ["Department of Homeland Security", "U.S. Citizenship and Immigration Services"],
    form: "I-797C",
    title: "Notice of Action",
    notice: "Asylum Interview Appointment",
    caseType: "I-589",
  },
};

/**
 * Left column of the case view: the letter as a marked-up paper object (the
 * "document-native" detail), then the same facts in plain language with matching
 * numbered pins, the verdict, and masked refs. `compact` (during the call, above the
 * translation book) keeps only the paper's header, the stamp and the facts: enough
 * to see which case this is.
 */
export function LetterPanel({ detail, compact = false }: { detail: CaseDetail; compact?: boolean }) {
  const { lang } = useLang();
  const s = useStrings();
  const t = s.case;
  const head = detail.doc_type ? LETTER_HEADS[detail.doc_type] : undefined;
  const appt = detail.appointment;
  const refs = Object.fromEntries(detail.refs.map((r) => [r.name, r.masked]));
  const verified = detail.verification?.status === "verified";
  // Pins: 1 = date and time, 2 = place, then one per checklist item.
  const firstChecklistPin = appt?.location ? 3 : 2;

  return (
    <section className={`${compact ? styles.compact : "card"} ${styles.panel}`} aria-labelledby="letter-title">
      <div className={styles.top}>
        <div className="label" id="letter-title">
          {t.yourLetter}
        </div>
        {head && <span className={`mono ${styles.code}`}>{head.form}</span>}
      </div>

      <div className={styles.paper} aria-hidden="true" dir="ltr">
        <div className={styles.pHead}>
          <span className={styles.seal} />
          <span className={styles.agency}>
            {head ? head.agency.map((a) => <span key={a}>{a}</span>) : (detail.issuer ?? "")}
          </span>
          {head && (
            <span className={styles.pTitle}>
              {head.form}
              <br />
              {head.title}
            </span>
          )}
        </div>
        <div className={styles.pGrid}>
          {refs.receipt_number && (
            <div>
              <span className={styles.k}>Receipt Number</span>
              <span className={styles.v}>{refs.receipt_number}</span>
            </div>
          )}
          {head?.caseType && (
            <div>
              <span className={styles.k}>Case Type</span>
              <span className={styles.v}>{head.caseType}</span>
            </div>
          )}
          {refs.a_number && (
            <div>
              <span className={styles.k}>A-Number</span>
              <span className={styles.v}>{refs.a_number}</span>
            </div>
          )}
        </div>
        <div className={styles.pBody}>
          {head && (
            <p>
              <b>Notice Type: {head.notice}</b>
            </p>
          )}
          {appt && (
            <p>
              You are scheduled for an interview on{" "}
              <span className="mark">
                {longDate(appt.date, "en")}
                {appt.time && ` at ${clockTime(appt.time, "en")}`}
              </span>
              <span className="pin">1</span>
              {appt.location && (
                <>
                  {" "}
                  at the <span className="mark">{appt.location}</span>
                  <span className="pin">2</span>
                </>
              )}
              .
            </p>
          )}
          {detail.checklist.map((c, i) => (
            <p key={i}>
              <span className={`mark ${c.kind === "who_must_come" ? "warn" : ""}`}>{c.item.en}</span>
              <span className={`pin ${c.kind === "who_must_come" ? "warn" : ""}`}>{firstChecklistPin + i}</span>
            </p>
          ))}
          <div className={styles.line} />
          <div className={styles.line} style={{ width: "80%" }} />
        </div>
        {verified && <span className={styles.stamp}>{t.stamp}</span>}
      </div>

      <ol className={styles.facts}>
        {appt && (
          <li>
            <span className="pin">1</span>
            <span>
              <span className={styles.fk}>{t.when}</span>
              <span className={styles.fv}>
                {longDate(appt.date, lang)}
                {appt.time && `, ${clockTime(appt.time, lang)}`}
              </span>
            </span>
          </li>
        )}
        {appt?.location && (
          <li>
            <span className="pin">2</span>
            <span>
              <span className={styles.fk}>{t.where}</span>
              <span className={styles.fv}>{appt.location}</span>
            </span>
          </li>
        )}
        {detail.checklist.map((c, i) => (
          <li key={i} className={c.kind === "who_must_come" ? styles.warn : ""}>
            <span className={`pin ${c.kind === "who_must_come" ? "warn" : ""}`}>{firstChecklistPin + i}</span>
            <span>
              <span className={styles.fk}>{t.kinds[c.kind]}</span>
              <span className={styles.fv}>{c.item.text}</span>
            </span>
          </li>
        ))}
      </ol>

      {!compact && detail.verification && (
        <div className={styles.verdict}>
          <span
            className={`pill ${detail.verification.status === "suspicious" ? "bad" : detail.verification.status === "verified" ? "" : "warn"}`}
          >
            {verified ? "✓ " : ""}
            {t.verdict[detail.verification.status]}
          </span>
          <ul>
            {verified && detail.verification.evidence[0] && (
              <li>{t.officialSource(domainOf(detail.verification.evidence[0]))}</li>
            )}
            {detail.verification.red_flags.map((f, i) => (
              <li key={i}>{f.text}</li>
            ))}
          </ul>
        </div>
      )}

      {!compact && detail.refs.length > 0 && (
        <dl className={styles.refs}>
          {detail.refs.map((r) => (
            <div key={r.name}>
              <dt>{t.refs[r.name] ?? r.name}</dt>
              <dd className="mono">{r.masked}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
