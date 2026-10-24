"use client";

import type { CallSummary, CaseStage } from "@/lib/api/types";
import { useStrings } from "@/lib/i18n";
import { isLive, trackerIndex } from "@/lib/stage";

import styles from "./Tracker.module.css";

/**
 * Letter → Verified → Calling → On hold → Person. `onDark` for the forest hero.
 * Pass the latest `call` so an ended call marks only the steps it reached.
 */
export function Tracker({
  stage,
  call = null,
  onDark = false,
}: {
  stage: CaseStage;
  call?: CallSummary | null;
  onDark?: boolean;
}) {
  const steps = useStrings().common.trackerSteps;
  const current = trackerIndex(stage, call);
  const live = isLive(stage);
  // Once a call is over nothing is in progress, even if it stopped early.
  const over = stage === "call_ended" || stage === "closed";
  return (
    <ol className={`${styles.tracker} ${onDark ? styles.dark : ""}`}>
      {steps.map((name, i) => {
        const state = i < current ? "done" : i === current && !over ? "active" : "todo";
        return (
          <li
            key={name}
            className={`${styles[state]} ${state === "active" && live ? styles.pulse : ""}`}
            aria-current={state === "active" ? "step" : undefined}
          >
            <span className={styles.n}>{state === "done" ? "✓" : ""}</span>
            {name}
          </li>
        );
      })}
    </ol>
  );
}
