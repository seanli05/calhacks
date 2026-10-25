"use client";

import type { CaseDetail } from "@/lib/api/types";
import { domainOf } from "@/lib/format";
import { useStrings } from "@/lib/i18n";

import styles from "./VerdictSummary.module.css";

/** The verdict beside the case's work on "Now": the status, the official source, and any red flags. */
export function VerdictSummary({ verification }: { verification: NonNullable<CaseDetail["verification"]> }) {
  const t = useStrings().case;
  const verified = verification.status === "verified";
  const tone = verification.status === "suspicious" ? "bad" : verified ? "" : "warn";

  return (
    <section className={`card ${styles.verdict}`}>
      <span className={`pill ${tone}`}>
        {verified ? "✓ " : ""}
        {t.verdict[verification.status]}
      </span>
      <ul>
        {verified && verification.evidence[0] && <li>{t.officialSource(domainOf(verification.evidence[0]))}</li>}
        {verification.red_flags.map((f, i) => (
          <li key={i}>{f.text}</li>
        ))}
      </ul>
    </section>
  );
}
