"use client";

import { useEffect, useState } from "react";

import { DATA_MODE } from "@/lib/api/client";
import { getStep, setStep, STEPS, subscribe } from "@/lib/api/fixtures";

import styles from "./FixtureBar.module.css";

/**
 * Fixture mode only: steps the fake demo call through its states (◀ ▶ or the
 * arrow keys), so pages can be built and checked without the backend.
 */
export function FixtureBar() {
  const [step, setLocal] = useState(getStep);

  useEffect(() => subscribe(() => setLocal(getStep())), []);

  useEffect(() => {
    // `?step=5` opens the fixtures at that step (0-based), e.g. to share a screen.
    const param = Number(new URLSearchParams(window.location.search).get("step"));
    if (DATA_MODE === "fixtures" && Number.isInteger(param) && param > 0) setStep(param);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
      if (e.key === "ArrowRight") setStep(getStep() + 1);
      if (e.key === "ArrowLeft") setStep(getStep() - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (DATA_MODE !== "fixtures") return null;
  return (
    <div className={styles.bar}>
      <span className={styles.tag}>Fixtures</span>
      <button type="button" onClick={() => setStep(step - 1)} disabled={step === 0} aria-label="Previous step">
        ◀
      </button>
      <span className={styles.name}>
        {step + 1}/{STEPS.length} · {STEPS[step].name}
      </span>
      <button
        type="button"
        onClick={() => setStep(step + 1)}
        disabled={step === STEPS.length - 1}
        aria-label="Next step"
      >
        ▶
      </button>
    </div>
  );
}
