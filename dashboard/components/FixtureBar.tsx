"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { DATA_MODE } from "@/lib/api/client";
import { FIXTURE_CASE_ID, getStep, hasCall, setStep, STEPS, subscribe } from "@/lib/api/fixtures";

import styles from "./FixtureBar.module.css";

/**
 * Fixture mode only: steps a fake call through its states (◀ ▶ or the arrow keys),
 * so pages can be built and checked without the backend. On a case page it plays
 * that case's call; anywhere else, the demo case's. Each case keeps its own step.
 */
export function FixtureBar() {
  const pathname = usePathname();
  const caseId = pathname.match(/\/cases\/([^/?]+)/)?.[1] ?? FIXTURE_CASE_ID;
  const callable = hasCall(caseId);
  const [step, setLocal] = useState(() => getStep(caseId));
  const caseRef = useRef(caseId);
  caseRef.current = caseId;

  useEffect(() => {
    setLocal(getStep(caseId));
    return subscribe(() => setLocal(getStep(caseRef.current)));
  }, [caseId]);

  useEffect(() => {
    // `?step=5` opens the fixtures at that step (0-based), e.g. to share a screen.
    const param = Number(new URLSearchParams(window.location.search).get("step"));
    if (DATA_MODE === "fixtures" && Number.isInteger(param) && param > 0) setStep(param, caseRef.current);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
      const id = caseRef.current;
      if (e.key === "ArrowRight") setStep(getStep(id) + 1, id);
      if (e.key === "ArrowLeft") setStep(getStep(id) - 1, id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (DATA_MODE !== "fixtures") return null;
  return (
    <div className={styles.bar}>
      <span className={styles.tag}>Fixtures</span>
      <button
        type="button"
        onClick={() => setStep(step - 1, caseId)}
        disabled={!callable || step === 0}
        aria-label="Previous step"
      >
        ◀
      </button>
      <span className={styles.name}>{callable ? `${step + 1}/${STEPS.length} · ${STEPS[step].name}` : "No call"}</span>
      <button
        type="button"
        onClick={() => setStep(step + 1, caseId)}
        disabled={!callable || step === STEPS.length - 1}
        aria-label="Next step"
      >
        ▶
      </button>
    </div>
  );
}
