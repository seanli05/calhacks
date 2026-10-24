"use client";

import Link from "next/link";

import { MiniLetter } from "@/components/MiniLetter";
import { Tracker } from "@/components/Tracker";
import { useNow } from "@/lib/api/hooks";
import type { CaseSummary } from "@/lib/api/types";
import { clockTime, daysUntil, duration, longDate, relativeTime } from "@/lib/format";
import { useLang, useStrings } from "@/lib/i18n";
import { isHumanMoment, isLive, isWarning } from "@/lib/stage";

import styles from "./CaseCard.module.css";

/** "in 20 days", "mañana": the appointment countdown, worded by `Intl`. */
function countdown(date: string, lang: string, now: number): string {
  return new Intl.RelativeTimeFormat(lang, { numeric: "auto" }).format(daysUntil(date, now), "day");
}

/**
 * One active case: letter thumb, stage, hold timer while on hold, the five-step
 * tracker, and the appointment. The whole card opens the case view. When a person
 * answers it turns forest, like the case view's hero.
 */
export function CaseCard({ userId, summary }: { userId: string; summary: CaseSummary }) {
  const { lang } = useLang();
  const s = useStrings();
  const t = s.cases;
  const now = useNow();
  const call = summary.latest_call;
  const live = isLive(summary.stage);
  const moment = summary.stage === "connected" && isHumanMoment(call?.state);
  const warning = isWarning(summary.stage);
  const holdStart = summary.stage === "on_hold" ? call?.hold_started_at : null;
  const outcome = summary.stage === "call_ended" ? (call?.report?.outcome ?? call?.outcome) : null;
  const appt = summary.appointment;
  const docType = (summary.doc_type && s.common.docTypes[summary.doc_type]) ?? s.common.docTypeFallback;

  return (
    <Link
      href={`/u/${userId}/cases/${summary.id}`}
      className={`card ${styles.card} ${moment ? styles.moment : ""} ${warning ? styles[warning] : ""}`}
    >
      <MiniLetter mediaId={summary.thumbnail_media_id} width={76} />

      <div className={styles.body}>
        <div className={styles.top}>
          <h2>{docType}</h2>
          <span className={styles.received}>{t.received(relativeTime(summary.created_at, lang, now))}</span>
        </div>

        <div className={styles.status}>
          <span className={`pill ${warning ?? ""} ${styles.pill}`}>
            {live && <span className={styles.dot} />}
            {s.common.stages[summary.stage]}
          </span>
          {outcome && (
            <span className={`pill ${outcome === "resolved" ? "" : "warn"}`}>{s.case.outcome[outcome]}</span>
          )}
          {holdStart && (
            <span className={styles.timer}>
              <span className={styles.t}>{duration((now - new Date(holdStart).getTime()) / 1000)}</span>
              <span className={styles.tl}>{t.onHold}</span>
            </span>
          )}
        </div>

        {appt && (
          <p className={styles.appt}>
            <span className={styles.k}>{t.appointment}</span>
            <span>
              <b>
                {longDate(appt.date, lang)}
                {appt.time && `, ${clockTime(appt.time, lang)}`}
              </b>{" "}
              · {countdown(appt.date, lang, now)}
              {appt.location && <span className={styles.loc}>{appt.location}</span>}
            </span>
          </p>
        )}

        <Tracker stage={summary.stage} onDark={moment} />
      </div>

      <span className={styles.open}>{t.open} →</span>
    </Link>
  );
}
