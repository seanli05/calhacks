import type { CaseStage, CallState } from "./api/types";

/**
 * The five-step tracker (Letter → Verified → Calling → On hold → Person) collapses
 * the 12 case stages. Returns the index of the current step; 5 means all done.
 */
export function trackerIndex(stage: CaseStage): number {
  switch (stage) {
    case "received":
    case "explaining":
    case "needs_better_image":
      return 0;
    case "checking":
    case "suspicious":
    case "unknown":
      return 1;
    case "awaiting_consent":
    case "calling":
      return 2;
    case "on_hold":
      return 3;
    case "connected":
      return 4;
    case "call_ended":
    case "closed":
      return 5;
  }
}

/** True while a call is in progress; the tracker pulses and the hero shows "live". */
export function isLive(stage: CaseStage): boolean {
  return stage === "calling" || stage === "on_hold" || stage === "connected";
}

/** A person answered: the hero switches to the solid forest "moment" look. */
export function isHumanMoment(callState: CallState | null | undefined): boolean {
  return (
    callState === "human_detected" ||
    callState === "bridging" ||
    callState === "connected" ||
    callState === "wrap_up"
  );
}

/** Stages that are a warning about the letter itself. */
export function isWarning(stage: CaseStage): "bad" | "warn" | null {
  if (stage === "suspicious") return "bad";
  if (stage === "unknown" || stage === "needs_better_image") return "warn";
  return null;
}
