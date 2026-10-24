"use client";

import { useEffect, useState } from "react";

import { Icon, type IconName } from "@/components/Icon";
import { Tracker } from "@/components/Tracker";
import { useNow } from "@/lib/api/hooks";
import type { CaseStage } from "@/lib/api/types";
import { duration } from "@/lib/format";
import { useStrings } from "@/lib/i18n";

import styles from "./LiveCallDemo.module.css";

type Phase = "dialing" | "menu" | "hold" | "human";

/** The scripted loop. Not live data: the landing must look right with no case running. */
const SCRIPT: { phase: Phase; ms: number; stage: CaseStage }[] = [
  { phase: "dialing", ms: 2800, stage: "calling" },
  { phase: "menu", ms: 2800, stage: "calling" },
  { phase: "hold", ms: 6500, stage: "on_hold" },
  { phase: "human", ms: 5000, stage: "connected" },
];

/** Where the hold timer starts, in seconds: long enough to make the point. */
const HOLD_START_S = 47 * 60 + 12;

const FEED_ICONS: Record<"verified" | Phase, IconName> = {
  verified: "check",
  dialing: "phone",
  menu: "keypad",
  hold: "clock",
  human: "person",
};

/** The hero picture: a call card that plays dialing → menu → hold → a person answers, on loop. */
export function LiveCallDemo() {
  const t = useStrings().landing.demo;
  const [step, setStep] = useState(0);
  const [phaseStart, setPhaseStart] = useState(() => Date.now());
  const now = useNow(500);
  const { phase, stage } = SCRIPT[step];
  const human = phase === "human";

  useEffect(() => {
    const timer = setTimeout(() => {
      setStep((s) => (s + 1) % SCRIPT.length);
      setPhaseStart(Date.now());
    }, SCRIPT[step].ms);
    return () => clearTimeout(timer);
  }, [step]);

  const feedKeys: ("verified" | Phase)[] = ["verified", ...SCRIPT.slice(0, step + 1).map((s) => s.phase)];
  const title = { dialing: t.dialing, menu: t.menu, hold: t.hold, human: t.human }[phase];
  const held = HOLD_START_S + Math.max(0, Math.floor((now - phaseStart) / 1000));

  return (
    <div className={`${styles.card} ${human ? styles.moment : ""}`} aria-hidden="true">
      <div className={styles.top}>
        <span className={`pill ${styles.pill}`}>
          <span className={styles.dot} />
          {t.live}
        </span>
        <span className={styles.agency}>{t.agency}</span>
      </div>

      <div className={styles.row}>
        <div className={styles.headline}>
          <p className={styles.title} key={phase}>
            {title}
          </p>
          {human && <p className={styles.sub}>{t.humanSub}</p>}
        </div>
        {phase === "hold" && (
          <div className={styles.timer}>
            <span className={styles.t}>{duration(held)}</span>
            <span className={styles.tl}>{t.onHold}</span>
          </div>
        )}
        {human && (
          <span className={styles.ring}>
            <Icon name="phone" size={28} />
          </span>
        )}
      </div>

      <Tracker stage={stage} onDark={human} />

      <ol className={styles.feed}>
        {feedKeys.slice(-4).map((key, i, shown) => (
          <li key={key} className={styles.line}>
            <span className={styles.icon}>
              <Icon name={FEED_ICONS[key]} />
            </span>
            <span className={styles.text}>{t.feed[key]}</span>
            <span className={styles.ago}>{t.ago(shown.length - 1 - i)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
