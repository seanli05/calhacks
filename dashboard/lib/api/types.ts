/**
 * Response shapes of the dashboard API (`backend/app/api/`). This file is the
 * contract between the dashboard and the API: the backend's Pydantic response
 * models mirror it field for field. Change both sides in the same commit
 * (docs/specs/dashboard-api.md).
 *
 * Conventions:
 * - Times are ISO 8601 UTC strings; dates are `YYYY-MM-DD`.
 * - Every route that returns user-facing text takes `?lang=xx` (default: the
 *   user's language) and returns it as `Localized`.
 * - Sensitive refs (receipt number, A-Number) arrive already masked. The full
 *   values never reach the browser.
 */

export type LanguageCode = string;

/** Text in the requested language, plus the English it came from. `text` falls
 * back to English when no translation exists yet. */
export interface Localized {
  text: string;
  en: string;
}

export type CaseStage =
  | "received"
  | "explaining"
  | "needs_better_image"
  | "needs_answer"
  | "checking"
  | "suspicious"
  | "unknown"
  | "awaiting_consent"
  | "calling"
  | "on_hold"
  | "connected"
  | "call_ended"
  | "closed";

export type CallState =
  | "dialing"
  | "menu"
  | "hold"
  | "human_detected"
  | "bridging"
  | "connected"
  | "wrap_up"
  | "ended";

export type CallOutcome = "resolved" | "partial" | "failed" | "user_unreachable" | "cancelled";
export type VerificationStatus = "pending" | "verified" | "suspicious" | "unknown";
export type Urgency = "low" | "medium" | "high";
export type ChecklistKind = "who_must_come" | "bring" | "deadline";

/** GET /api/demo: the seeded user and their newest case, for the landing page link. */
export interface DemoInfo {
  user_id: string;
  case_id: string | null;
}

/** GET /api/config: what the landing QR and the wa.me links need. */
export interface PublicConfig {
  /** E.164, e.g. "+14155238886" (from TWILIO_WHATSAPP_FROM). */
  whatsapp_number: string;
  /** The Twilio sandbox join code, e.g. "join purple-tiger"; null if unset. */
  sandbox_join_message: string | null;
}

/** GET /api/users/{user_id} */
export interface UserInfo {
  id: string;
  /** ISO 639-1; null until the user picks one. */
  language: LanguageCode | null;
}

/** GET /api/users/{user_id}/feed?since=<iso>&lang=xx: oldest first, `since` exclusive. */
export interface FeedItem {
  id: string;
  at: string;
  /** Dotted event type, e.g. "call.on_hold" (backend/app/contracts/events.py). */
  type: string;
  case_id: string | null;
  call_id: string | null;
  job_id: string | null;
  text: Localized;
  /** Set when the fact or document this event refers to has been deleted (C27). */
  deleted_at: string | null;
  /** Only with `?steps=true`: one lookup inside a task (research or the call). */
  step?: FeedStep | null;
}

/** A step row (backend/app/api/feed_steps.py). `detail` is English as logged. */
export interface FeedStep {
  action: Localized;
  detail: string | null;
  result: Localized | null;
  /** False: the step went wrong. Null: neither good nor bad. */
  ok: boolean | null;
  /** Why it came out that way, English as written by the backend. */
  reason?: string | null;
}

/** GET /api/users/{user_id}/cases?lang=xx: active cases, newest first. */
export interface CaseSummary {
  id: string;
  doc_type: string | null;
  stage: CaseStage;
  deadline: string | null;
  appointment: Appointment | null;
  latest_call: CallSummary | null;
  /** First page of the letter, if a photo exists. */
  thumbnail_media_id: string | null;
  created_at: string;
}

export interface Appointment {
  date: string;
  /** Local time at the location, "HH:MM"; null when the letter gives only a date. */
  time: string | null;
  /** The office (not an identifier, so shown in full). */
  location: string | null;
}

export interface ChecklistEntry {
  kind: ChecklistKind;
  item: Localized;
}

export interface MaskedRef {
  /** e.g. "receipt_number", "a_number". */
  name: string;
  /** e.g. "•••• 2345". */
  masked: string;
}

export interface VerificationInfo {
  status: VerificationStatus;
  /** Source URLs, e.g. "https://www.uscis.gov/contactcenter". */
  evidence: string[];
  red_flags: Localized[];
}

export interface BriefInfo {
  call_goal: Localized | null;
  questions_to_ask: Localized[];
}

export interface CallReportInfo {
  outcome: CallOutcome;
  /** How the call went; null when the call never reached a person. */
  summary: Localized | null;
  reference_number: string | null;
  rep_name: string | null;
  next_steps: Localized[];
  new_deadlines: string[];
  followup_needed: boolean;
}

export interface CallSummary {
  id: string;
  state: CallState;
  outcome: CallOutcome | null;
  started_at: string;
  ended_at: string | null;
  /** When the latest `call.on_hold` event for this call happened; drives the hold timer. */
  hold_started_at: string | null;
  report: CallReportInfo | null;
  /** Null when there is no transcript or it was deleted. */
  transcript_id: string | null;
}

/** GET /api/cases/{case_id}?lang=xx */
export interface CaseDetail {
  id: string;
  user_id: string;
  doc_type: string | null;
  /** Short agency name, e.g. "USCIS". */
  issuer: string | null;
  stage: CaseStage;
  deadline: string | null;
  urgency: Urgency | null;
  document_id: string | null;
  page_media_ids: string[];
  explanation: Localized | null;
  what_is_asked: Localized | null;
  appointment: Appointment | null;
  checklist: ChecklistEntry[];
  refs: MaskedRef[];
  verification: VerificationInfo | null;
  brief: BriefInfo | null;
  /** Oldest first. */
  calls: CallSummary[];
}

export type Speaker = "agent" | "agency" | "user";

export interface TranscriptLine {
  at: string;
  speaker: Speaker;
  text: string;
}

/** GET /api/calls/{call_id}/transcript: lines stay in the call's language (English). */
export interface Transcript {
  id: string;
  call_id: string;
  lines: TranscriptLine[];
}

export type FactSource = "user_said" | "from_document" | "from_call" | "inferred";
export type FactStatus = "active" | "pending_consent" | "superseded";

export interface FactInfo {
  id: string;
  fact: Localized;
  category: string;
  source: FactSource;
  sensitivity: "normal" | "sensitive";
  status: FactStatus;
  recorded_at: string;
}

export interface DocumentInfo {
  id: string;
  doc_type: string | null;
  case_id: string | null;
  page_media_ids: string[];
  created_at: string;
}

export interface TranscriptInfo {
  id: string;
  call_id: string;
  case_id: string;
  created_at: string;
}

/** GET /api/users/{user_id}/memory?lang=xx */
export interface Memory {
  /** Profile fields as label/value pairs, e.g. {"county": "Los Angeles"}. */
  profile: Record<string, string>;
  facts: FactInfo[];
  documents: DocumentInfo[];
  transcripts: TranscriptInfo[];
}

/** GET /api/users/{user_id}/messages: the WhatsApp thread, oldest first. */
export interface Message {
  id: string;
  at: string;
  direction: "in" | "out";
  sender: "user" | "orchestrator" | "relay";
  /** As sent or received, in `language`. */
  body: string;
  body_en: string | null;
  language: LanguageCode;
  media_ids: string[];
  case_id: string | null;
}

export type SuggestionKind = "countdown" | "glossary" | "checklist";

/** GET /api/users/{user_id}/suggestions?lang=xx: at most three, rule-based. */
export interface Suggestion {
  id: string;
  kind: SuggestionKind;
  case_id: string | null;
  title: Localized;
  detail: Localized;
  /** Button label, e.g. "Prepare". */
  action: Localized;
  /** Text prefilled into WhatsApp, in the user's language. */
  prefill: string;
}

/** POST /api/users/{user_id}/delete-everything */
export type DeleteCounts = Record<string, number>;

/**
 * GET /api/calls/{call_id}/live?lang=xx (server-sent events): the bridged call as it
 * happens, both legs, in the viewer's language. Lines appear as the phone agent
 * saves them to the transcript.
 */
export type LiveCallEvent =
  /** A finished turn was heard; its translation streams next as `delta`s. */
  | { type: "line"; id: string; at: string; speaker: Speaker; en: string }
  /** The next piece of the line's translation, appended to what came before. */
  | { type: "delta"; id: string; text: string }
  | { type: "done"; id: string }
  | { type: "tip"; tip: LiveTip }
  /** The user said what a tip suggested. */
  | { type: "tip_used"; id: string };

/**
 * Something the user could say next. `ask` gives English to read out loud;
 * `yourself` marks a question only the user may answer (rule 3), so it never
 * carries an answer.
 */
export interface LiveTip {
  id: string;
  kind: "ask" | "yourself";
  /** The line that prompted it. */
  line_id: string;
  /** English to read out loud; null for `yourself`. */
  say_en: string | null;
  meaning: Localized;
}

export type TrustLevel = "official" | "community" | "machine";

/** GET /api/glossary?lang=xx: the translation book for one language. */
export interface GlossaryEntry {
  term: string;
  translation: string;
  trust_level: TrustLevel;
  source_url: string | null;
}
