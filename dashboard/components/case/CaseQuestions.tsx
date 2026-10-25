"use client";

import { api } from "@/lib/api/client";
import { usePoll } from "@/lib/api/hooks";
import type { CaseDetail } from "@/lib/api/types";
import { useStrings } from "@/lib/i18n";
import { waLink } from "@/lib/whatsapp";

import styles from "./CaseQuestions.module.css";

/**
 * Two or three questions this case invites, so the user knows what they can ask.
 * Each opens WhatsApp with the question prefilled; the dashboard never sends (rule 1).
 */
export function CaseQuestions({ detail }: { detail: CaseDetail }) {
  const t = useStrings().case.ask;
  const config = usePoll(() => api.config(), "config", 60_000).data;
  const status = detail.verification?.status;
  const base =
    status === "suspicious"
      ? t.scam
      : status === "unknown"
        ? t.unknown
        : detail.appointment
          ? t.appointment
          : t.general;
  const questions = detail.stage === "call_ended" ? [t.afterCall, ...base.slice(0, 2)] : base;

  return (
    <section className={`card ${styles.ask}`} aria-labelledby="ask-title">
      <span className="label" id="ask-title">
        {t.title}
      </span>
      <ul>
        {questions.map((q) => (
          <li key={q}>
            <a
              href={config ? waLink(config.whatsapp_number, q) : undefined}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.q}
            >
              <span>{q}</span>
              <span className={styles.go} aria-hidden="true">
                ↗
              </span>
            </a>
          </li>
        ))}
      </ul>
      <p className={styles.note}>{t.note}</p>
    </section>
  );
}
