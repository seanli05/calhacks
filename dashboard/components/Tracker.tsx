"use client";

import type { CaseStage } from "@/lib/api/types";
import { useStrings } from "@/lib/i18n";
import { isLive, trackerIndex } from "@/lib/stage";

import styles from "./Tracker.module.css";

/** Letter → Verified → Calling → On hold → Person. `onDark` for the forest hero. */
export function Tracker({ stage, onDark = false }: { stage: CaseStage; onDark?: boolean }) {
  const steps = useStrings().common.trackerSteps;
  const current = trackerIndex(stage);
  const live = isLive(stage);
  return (
    <ol className={`${styles.tracker} ${onDark ? styles.dark : ""}`}>
      {steps.map((name, i) => {
        const state = i < current ? "done" : i === current ? "active" : "todo";
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
