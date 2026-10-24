"use client";

import { Tracker } from "@/components/Tracker";
import { useNow } from "@/lib/api/hooks";
import type { CallSummary, CaseDetail } from "@/lib/api/types";
import { duration } from "@/lib/format";
import { stringsFor, useLang } from "@/lib/i18n";
import type { CaseStrings } from "@/lib/i18n/strings/en/case";
import { isHumanMoment, isLive, isWarning } from "@/lib/stage";

import styles from "./CallHero.module.css";

interface Copy {
  title: string;
  sub?: string;
}

/** The headline for the case's current moment, in one language. */
function heroCopy(t: CaseStrings, detail: CaseDetail, call: CallSummary | null, agency: string): Copy {
  const h = t.hero;
  switch (detail.stage) {
    case "awaiting_consent":
      return { title: h.awaiting_consent.title(agency), sub: h.awaiting_consent.sub };
    case "calling":
      return call?.state === "menu"
        ? { title: h.menu.title(agency), sub: h.menu.sub }
        : { title: h.dialing.title(agency), sub: h.dialing.sub };
    case "on_hold":
      return { title: h.on_hold.title(agency), sub: h.on_hold.sub };
    case "connected":
      return call?.state === "human_detected" || call?.state === "bridging"
        ? h.human
        : { title: h.connected.title(agency), sub: h.connected.sub };
    case "call_ended":
      return { title: h.call_ended.title(agency) };
    default:
      return h[detail.stage];
  }
}

/**
 * The top of the live column: what's happening right now, the hold timer, and the
 * tracker. When a person answers it turns solid forest, the big moment in the demo.
 * After the call it becomes the call report.
 */
export function CallHero({ detail, onOpenTranscript }: { detail: CaseDetail; onOpenTranscript: (callId: string) => void }) {
  const { lang } = useLang();
  const t = stringsFor(lang).case;
  const en = stringsFor("en").case;
  const now = useNow();
  const call = detail.calls.length ? detail.calls[detail.calls.length - 1] : null;
  const agency = detail.issuer ?? t.agencyFallback;
  const copy = heroCopy(t, detail, call, agency);
  const copyEn = heroCopy(en, detail, call, detail.issuer ?? en.agencyFallback);
  const moment = detail.stage === "connected" && isHumanMoment(call?.state);
  const warning = isWarning(detail.stage);
  const showTimer = detail.stage === "on_hold" && call?.hold_started_at;
  const report = detail.stage === "call_ended" ? call?.report : null;

  return (
    <div className={`${styles.hero} ${moment ? styles.moment : ""} ${warning ? styles[warning] : ""}`}>
      {isLive(detail.stage) && (
        <span className={`pill ${styles.pill}`}>
          <span className={styles.dot} />
          {t.liveCall}
        </span>
      )}
      {report && <span className={`pill ${report.outcome === "resolved" ? "" : "warn"}`}>{t.outcome[report.outcome]}</span>}

      <div className={styles.row}>
        <div className={styles.headline}>
          <h1>{copy.title}</h1>
          {copy.sub && <p>{copy.sub}</p>}
          {lang !== "en" && (
            <p className={styles.en}>
              {copyEn.title}
              {copyEn.sub ? `. ${copyEn.sub}` : ""}
            </p>
          )}
        </div>
        {showTimer && (
          <div className={styles.timer}>
            <span className={styles.t}>{duration((now - new Date(call!.hold_started_at!).getTime()) / 1000)}</span>
            <span className={styles.tl}>{t.onHold}</span>
          </div>
        )}
      </div>

      {detail.stage === "awaiting_consent" && detail.brief && detail.brief.questions_to_ask.length > 0 && (
        <ul className={styles.list}>
          {detail.brief.questions_to_ask.map((q, i) => (
            <li key={i}>
              <span className={styles.bullet}>?</span>
              <span>
                {q.text}
                {lang !== "en" && <small>{q.en}</small>}
              </span>
            </li>
          ))}
        </ul>
      )}

      {report && (
        <>
          <ul className={styles.list}>
            {report.next_steps.map((step, i) => (
              <li key={i}>
                <span className={styles.bullet}>✓</span>
                <span>
                  {step.text}
                  {lang !== "en" && <small>{step.en}</small>}
                </span>
              </li>
            ))}
          </ul>
          {report.reference_number && <p className={styles.ref}>{t.reference(report.reference_number)}</p>}
          {call?.transcript_id && (
            <button type="button" className="btn primary" onClick={() => onOpenTranscript(call.id)}>
              {t.viewTranscript} →
            </button>
          )}
        </>
      )}

      <Tracker stage={detail.stage} onDark={moment} />
    </div>
  );
}
