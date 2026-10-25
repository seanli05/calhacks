/**
 * Fake API responses for building pages without the backend (NEXT_PUBLIC_DATA=fixtures).
 * Values match the demo seed (backend/app/db/reset.py) and are all fictional.
 *
 * The scenario plays the demo call: `step` moves from "waiting for consent" to
 * "call ended", and every response is computed from it. The fixture bar
 * (components/FixtureBar.tsx) moves the step; deletes mutate this module's state.
 */

import type {
  CaseDetail,
  CaseStage,
  CaseSummary,
  CallState,
  CallSummary,
  DeleteCounts,
  DemoInfo,
  FeedItem,
  Localized,
  Memory,
  Message,
  PublicConfig,
  Suggestion,
  Transcript,
  UserInfo,
} from "./types";
import { pick } from "./fixtures-fa";

export const FIXTURE_USER_ID = "user_demo000000000001";
export const FIXTURE_CASE_ID = "case_demo000000000001";
/** A second, made-up letter that research flagged as a scam. */
const SCAM_CASE_ID = "case_demo000000000002";
/** A third, real letter with a deadline instead of an appointment: a Request for Evidence. */
const RFE_CASE_ID = "case_demo000000000003";
const RFE_DEADLINE = "2026-12-04";
const CALL_ID = "call_demo000000000001";
const RFE_CALL_ID = "call_demo000000000003";
const DOC_ID = "doc_demo0000000000001";
const TRANSCRIPT_ID = "transcript_demo000000001";
const RFE_TRANSCRIPT_ID = "transcript_demo000000003";
const LETTER_MEDIA_ID = "media_demo00000000001";

interface Step {
  name: string;
  stage: CaseStage;
  callState: CallState | null;
}

export const STEPS: Step[] = [
  { name: "Waiting for consent", stage: "awaiting_consent", callState: null },
  { name: "Dialing", stage: "calling", callState: "dialing" },
  { name: "Phone menu", stage: "calling", callState: "menu" },
  { name: "On hold", stage: "on_hold", callState: "hold" },
  { name: "Person answered", stage: "connected", callState: "human_detected" },
  { name: "Connected", stage: "connected", callState: "connected" },
  { name: "Call ended", stage: "call_ended", callState: "ended" },
];

const START_STEP = 3;
const HOLD_STEP = 3;

/** "Now" for the fixed part of the timeline: the moment the page loaded, on hold for 13 minutes. */
const T0 = Date.now();
const min = (n: number) => new Date(T0 + n * 60_000).toISOString();

/**
 * The cases whose call the fixture bar can play: their call, transcript and the step
 * each starts at. Each case keeps its own step; the bar moves the one on screen.
 */
const CALL_CASES: Record<string, { callId: string; transcriptId: string; start: number }> = {
  [FIXTURE_CASE_ID]: { callId: CALL_ID, transcriptId: TRANSCRIPT_ID, start: START_STEP },
  [RFE_CASE_ID]: { callId: RFE_CALL_ID, transcriptId: RFE_TRANSCRIPT_ID, start: 0 },
};

const steps = new Map<string, number>();
const listeners = new Set<() => void>();
/** When each case's later steps were first shown (`case:step`), so their events get a real "now" time. */
const revealedAt = new Map<string, string>();
const deletedFacts = new Map<string, string>();
let deletedDocument: string | null = null;
let deletedTranscript: string | null = null;
let deletedAll: string | null = null;

/** True when the fixture bar can play a call for this case (not the scam letter). */
export function hasCall(caseId: string): boolean {
  return caseId in CALL_CASES;
}

export function getStep(caseId: string = FIXTURE_CASE_ID): number {
  return steps.get(caseId) ?? CALL_CASES[caseId]?.start ?? 0;
}

export function setStep(next: number, caseId: string = FIXTURE_CASE_ID): void {
  if (!hasCall(caseId)) return;
  const step = Math.max(0, Math.min(STEPS.length - 1, next));
  steps.set(caseId, step);
  const key = `${caseId}:${step}`;
  if (step > CALL_CASES[caseId].start && !revealedAt.has(key)) revealedAt.set(key, new Date().toISOString());
  listeners.forEach((fn) => fn());
}

/** Called on every fixture change, so polling hooks refetch right away. */
export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function notify(): void {
  listeners.forEach((fn) => fn());
}

const L = (lang: string, es: string, en: string): Localized => ({ text: pick(lang, es, en), en });

/**
 * The demo user's language: Dari when the dashboard is switched to Dari, so the
 * WhatsApp thread and translation book match it; Spanish otherwise.
 */
function demoLanguage(): string {
  try {
    const picked = new URLSearchParams(window.location.search).get("lang") ?? window.localStorage.getItem("dashboard.lang");
    return picked === "fa" ? "fa" : "es";
  } catch {
    return "es";
  }
}

/** Time for an event that belongs to step `s` of a case's call: "when shown", or fixed if the case started past it. */
function atStep(s: number, fallbackMinutes: number, caseId: string = FIXTURE_CASE_ID): string {
  return revealedAt.get(`${caseId}:${s}`) ?? min(fallbackMinutes);
}

// ---------------------------------------------------------------------------

export function demo(): DemoInfo {
  return { user_id: FIXTURE_USER_ID, case_id: deletedAll ? null : FIXTURE_CASE_ID };
}

export function config(): PublicConfig {
  return { whatsapp_number: "+14155238886", sandbox_join_message: "join fixture-demo" };
}

export function user(userId: string): UserInfo {
  return { id: userId, language: demoLanguage() };
}

interface FeedSeed {
  id: string;
  minStep: number;
  at: () => string;
  type: string;
  call?: boolean;
  job?: string;
  es: string;
  en: string;
  factId?: string;
  /** Which case it belongs to; the demo case if not set. */
  caseId?: string;
  /** A step row, only served with `steps`: [action es, action en, detail, result es, result en, ok, reason]. */
  step?: [string, string, string, string | null, string | null, boolean | null, string?];
}

const DEEP_JOB = "job_fx_deep";
const D = -2 * 24 * 60 + 2;
const search = (id: string, m: number, query: string): FeedSeed => ({
  id, minStep: 0, at: () => min(D + m), type: "research.search", job: DEEP_JOB, es: `Searched: ${query}`, en: `Searched: ${query}`,
  step: ["Buscando", "Searching", `"${query}"`, null, null, null],
});
const read = (id: string, m: number, page: string): FeedSeed => ({
  id, minStep: 0, at: () => min(D + m), type: "research.fetch", job: DEEP_JOB, es: `Fetched ${page}`, en: `Fetched ${page}`,
  step: ["Leyendo", "Reading", page, "leída", "read", true],
});
const check = (id: string, m: number, what: string, es: string, en: string, ok: boolean | null, reason?: string): FeedSeed => ({
  id, minStep: 0, at: () => min(D + m), type: "research.check", job: DEEP_JOB, es: `${what}: ${en}`, en: `${what}: ${en}`,
  step: ["Comprobando", "Checking", what, es, en, ok, reason],
});
const heard = (id: string, minStep: number, m: number): FeedSeed => ({
  id, minStep, at: () => min(m), type: "call.menu_heard", call: true, es: "Heard the phone menu", en: "Heard the phone menu",
  step: ["Escuchando", "Listening", "phone menu", "marcar", "press a key", null, "Lists numbered options. Option 2 is for appointments and interviews."],
});

const FEED: FeedSeed[] = [
  { id: "event_f01", minStep: 0, at: () => min(-2 * 24 * 60), type: "case.created", es: "Recibimos tu carta", en: "We received your letter" },
  { id: "event_f02", minStep: 0, at: () => min(-2 * 24 * 60 + 1), type: "research.fast_done", es: "Te explicamos la carta en español", en: "We explained the letter in your language" },
  { id: "event_f03", minStep: 0, at: () => min(-2 * 24 * 60 + 1), type: "memory.fact_saved", es: "Guardamos: tienes dos hijos en tu solicitud", en: "Saved: you have two children on your application", factId: "fact_demo01" },
  { id: "event_s00", minStep: 0, at: () => min(D), type: "research.deep_started", job: DEEP_JOB, es: "Estamos revisando que la carta sea real", en: "We're checking that the letter is real" },
  check("event_s01", 0.02, "scam patterns", "0 alertas", "0 red flags", true, "No payment demands, threats, notario offers, or links outside official sites."),
  check("event_s02", 0.04, "form type", "coincide", "matches", true, "The form number is on an official page or the known form list."),
  check("event_s03", 0.06, "case number format", "coincide", "matches", true, "The case number has the letters and digits this kind of letter uses."),
  search("event_s04", 0.1, "USCIS I-797C asylum interview notice"),
  search("event_s05", 0.16, "Los Angeles Asylum Office Tustin CA"),
  read("event_s06", 0.2, "uscis.gov/forms/all-forms/form-i-797c"),
  read("event_s07", 0.26, "uscis.gov/about-us/find-a-uscis-office/field-offices"),
  search("event_s08", 0.32, "USCIS Contact Center phone number"),
  read("event_s09", 0.36, "uscis.gov/contactcenter"),
  check("event_s10", 0.42, "phone on the letter vs. the official site", "coincide", "matches", true, "The phone number on the letter is listed for the issuer on an official page."),
  check("event_s11", 0.46, "is the letter real?", "real", "real", true, "The letter's details matched the issuer's official site. The official phone number was found there too."),
  { id: "event_f04", minStep: 0, at: () => min(-2 * 24 * 60 + 3), type: "verification.verified", job: DEEP_JOB, es: "Confirmamos que la carta es real (uscis.gov)", en: "We confirmed the letter is real (uscis.gov)" },
  { id: "event_f05", minStep: 0, at: () => min(-20), type: "consent.requested", es: "Te preguntamos si quieres que llamemos a USCIS", en: "We asked if you want us to call USCIS" },
  { id: "event_f06", minStep: 1, at: () => min(-16), type: "consent.given", es: "Dijiste que sí a la llamada", en: "You said yes to the call" },
  { id: "event_f07", minStep: 1, at: () => min(-15), type: "call.dialing", call: true, es: "Llamamos al número oficial de USCIS", en: "We called the official USCIS number" },
  heard("event_m01", 2, -14.3),
  { id: "event_f08", minStep: 2, at: () => min(-14), type: "call.menu_choice", call: true, es: "Elegimos la opción 2: citas y entrevistas", en: "We chose option 2: appointments and interviews" },
  heard("event_m02", 2, -13.8),
  { id: "event_f09", minStep: 2, at: () => min(-13.5), type: "call.menu_choice", call: true, es: "Elegimos la opción 2: entrevista de asilo", en: "We chose option 2: asylum interview" },
  { id: "event_s12", minStep: 0, at: () => min(D + 1.02), type: "research.deep_done", job: DEEP_JOB, es: "Terminamos de revisar tu carta", en: "We finished checking your letter" },
  { id: "event_f10", minStep: 3, at: () => min(-13), type: "call.on_hold", call: true, es: "Estamos en espera", en: "We're on hold" },
  { id: "event_f11", minStep: 4, at: () => atStep(4, 0), type: "call.human_detected", call: true, es: "Contestó una persona de USCIS", en: "A person from USCIS answered" },
  { id: "event_f12", minStep: 4, at: () => atStep(4, 0), type: "call.user_dialed", call: true, es: "Te llamamos para conectarte", en: "We're calling you to connect you" },
  { id: "event_f13", minStep: 5, at: () => atStep(5, 1), type: "call.user_joined", call: true, es: "Te conectamos con USCIS", en: "We connected you with USCIS" },
  { id: "event_f14", minStep: 6, at: () => atStep(6, 6), type: "call.ended", call: true, es: "La llamada terminó", en: "The call ended" },
  { id: "event_r01", caseId: RFE_CASE_ID, minStep: 0, at: () => min(-26 * 60), type: "case.created", es: "Recibimos tu carta", en: "We received your letter" },
  { id: "event_r02", caseId: RFE_CASE_ID, minStep: 0, at: () => min(-26 * 60 + 1), type: "research.fast_done", es: "Te explicamos la carta en español", en: "We explained the letter in your language" },
  { id: "event_r03", caseId: RFE_CASE_ID, minStep: 0, at: () => min(-26 * 60 + 3), type: "verification.verified", es: "Confirmamos que la carta es real (uscis.gov)", en: "We confirmed the letter is real (uscis.gov)" },
  { id: "event_r04", caseId: RFE_CASE_ID, minStep: 0, at: () => min(-25 * 60), type: "consent.requested", es: "Te preguntamos si quieres que llamemos a USCIS", en: "We asked if you want us to call USCIS" },
  { id: "event_r05", caseId: RFE_CASE_ID, minStep: 1, at: () => rfeAt(1, -3), type: "consent.given", es: "Dijiste que sí a la llamada", en: "You said yes to the call" },
  { id: "event_r06", caseId: RFE_CASE_ID, minStep: 1, at: () => rfeAt(1, -3), type: "call.dialing", call: true, es: "Llamamos al número oficial de USCIS", en: "We called the official USCIS number" },
  { id: "event_r07", caseId: RFE_CASE_ID, minStep: 2, at: () => rfeAt(2, -2.5), type: "call.menu_heard", call: true, es: "Heard the phone menu", en: "Heard the phone menu",
    step: ["Escuchando", "Listening", "phone menu", "marcar", "press a key", null, "Lists numbered options. Option 1 is for a case you already filed."] },
  { id: "event_r08", caseId: RFE_CASE_ID, minStep: 2, at: () => rfeAt(2, -2.4), type: "call.menu_choice", call: true, es: "Elegimos la opción 1: un caso ya presentado", en: "We chose option 1: a case you already filed" },
  { id: "event_r09", caseId: RFE_CASE_ID, minStep: 2, at: () => rfeAt(2, -2.3), type: "call.menu_choice", call: true, es: "Elegimos la opción 3: una carta que pide pruebas", en: "We chose option 3: a letter asking for evidence" },
  { id: "event_r10", caseId: RFE_CASE_ID, minStep: 3, at: () => rfeAt(3, -2), type: "call.on_hold", call: true, es: "Estamos en espera", en: "We're on hold" },
  { id: "event_r11", caseId: RFE_CASE_ID, minStep: 4, at: () => rfeAt(4, 0), type: "call.human_detected", call: true, es: "Contestó una persona de USCIS", en: "A person from USCIS answered" },
  { id: "event_r12", caseId: RFE_CASE_ID, minStep: 4, at: () => rfeAt(4, 0), type: "call.user_dialed", call: true, es: "Te llamamos para conectarte", en: "We're calling you to connect you" },
  { id: "event_r13", caseId: RFE_CASE_ID, minStep: 5, at: () => rfeAt(5, 1), type: "call.user_joined", call: true, es: "Te conectamos con USCIS", en: "We connected you with USCIS" },
  { id: "event_r14", caseId: RFE_CASE_ID, minStep: 6, at: () => rfeAt(6, 6), type: "call.ended", call: true, es: "La llamada terminó", en: "The call ended" },
];

function rfeAt(s: number, fallbackMinutes: number): string {
  return atStep(s, fallbackMinutes, RFE_CASE_ID);
}

function deleteEvents(lang: string): FeedItem[] {
  const items: FeedItem[] = [];
  for (const [id, at] of deletedFacts) {
    items.push({ id: `event_del_${id}`, at, type: "fact.deleted", case_id: null, call_id: null, job_id: null, text: L(lang, "Borraste un dato", "You deleted a fact"), deleted_at: null });
  }
  if (deletedDocument) items.push({ id: "event_del_doc", at: deletedDocument, type: "document.deleted", case_id: null, call_id: null, job_id: null, text: L(lang, "Borraste la carta", "You deleted the letter"), deleted_at: null });
  if (deletedTranscript) items.push({ id: "event_del_tr", at: deletedTranscript, type: "transcript.deleted", case_id: null, call_id: null, job_id: null, text: L(lang, "Borraste una transcripción", "You deleted a transcript"), deleted_at: null });
  if (deletedAll) items.push({ id: "event_del_all", at: deletedAll, type: "user.deleted_all", case_id: null, call_id: null, job_id: null, text: L(lang, "Borraste todo", "You deleted everything"), deleted_at: null });
  return items;
}

export function feed(_userId: string, since: string | null, lang: string, steps = false): FeedItem[] {
  const items: FeedItem[] = deletedAll
    ? []
    : FEED.filter((e) => e.minStep <= getStep(e.caseId) && (steps || !e.step)).map((e) => ({
        id: e.id,
        at: e.at(),
        type: e.type,
        case_id: e.caseId ?? FIXTURE_CASE_ID,
        call_id: e.call ? CALL_CASES[e.caseId ?? FIXTURE_CASE_ID].callId : null,
        job_id: e.job ?? null,
        text: L(lang, e.es, e.en),
        deleted_at: e.factId ? (deletedFacts.get(e.factId) ?? null) : null,
        step: e.step
          ? {
              action: L(lang, e.step[0], e.step[1]),
              detail: e.step[2],
              result: e.step[3] && e.step[4] ? L(lang, e.step[3], e.step[4]) : null,
              ok: e.step[5],
              reason: e.step[6] ?? null,
            }
          : null,
      }));
  items.push(...deleteEvents(lang));
  items.sort((a, b) => a.at.localeCompare(b.at) || a.id.localeCompare(b.id));
  return since ? items.filter((i) => i.at > since) : items;
}

function call(lang: string, caseId: string = FIXTURE_CASE_ID): CallSummary | null {
  const step = getStep(caseId);
  const s = STEPS[step];
  if (!s.callState) return null;
  const ended = s.callState === "ended";
  const rfe = caseId === RFE_CASE_ID;
  return {
    id: CALL_CASES[caseId].callId,
    state: s.callState,
    outcome: ended ? "resolved" : null,
    started_at: rfe ? rfeAt(1, -3) : min(-15),
    ended_at: ended ? atStep(6, 6, caseId) : null,
    hold_started_at: step >= HOLD_STEP ? (rfe ? rfeAt(3, -2) : min(-13)) : null,
    report: ended ? (rfe ? rfeReport(lang) : asylumReport(lang)) : null,
    transcript_id: ended && !deletedTranscript ? CALL_CASES[caseId].transcriptId : null,
  };
}

function asylumReport(lang: string): CallSummary["report"] {
  return {
    outcome: "resolved",
    summary: L(
      lang,
      "El oficial Lee confirmó tu entrevista y explicó que debes llevar tu propio intérprete.",
      "Officer Lee confirmed your interview and explained that you must bring your own interpreter.",
    ),
    reference_number: null,
    rep_name: "Officer Lee",
    next_steps: [
      L(lang, "Tu entrevista sigue el 12 de noviembre a las 8:30 AM", "Your interview is still on November 12 at 8:30 AM"),
      L(lang, "Tienes que llevar tu propio intérprete; USCIS no lo da", "You must bring your own interpreter; USCIS doesn't provide one"),
      L(lang, "Si tu intérprete no puede ir, avisa por escrito antes de la cita", "If your interpreter can't come, tell USCIS in writing before the appointment"),
    ],
    new_deadlines: [],
    followup_needed: false,
  };
}

function rfeReport(lang: string): CallSummary["report"] {
  return {
    outcome: "resolved",
    summary: L(
      lang,
      "La agente Ruiz confirmó a qué dirección mandar las pruebas y que no pueden dar más tiempo.",
      "Agent Ruiz confirmed where to mail the evidence and that they can't give more time.",
    ),
    reference_number: "•••• 4410",
    rep_name: "Agent Ruiz",
    next_steps: [
      L(lang, "Manda las pruebas a la dirección impresa en la carta, con la carta encima", "Mail the evidence to the address printed on the letter, with the letter on top"),
      L(lang, "Tienen que llegar antes del 4 de diciembre; no dan más tiempo", "It has to arrive by December 4; they don't give extensions"),
      L(lang, "Si te falta un documento, manda lo que tengas y explica por escrito por qué falta", "If a document is missing, send what you have and explain in writing why"),
    ],
    new_deadlines: [],
    followup_needed: false,
  };
}

const APPOINTMENT = { date: "2026-11-12", time: "08:30", location: "Los Angeles Asylum Office, Tustin, CA" };

export function cases(_userId: string, lang: string): CaseSummary[] {
  if (deletedAll) return [];
  return [
    {
      id: FIXTURE_CASE_ID,
      doc_type: "uscis_i797c_asylum_interview",
      stage: STEPS[getStep()].stage,
      deadline: APPOINTMENT.date,
      appointment: APPOINTMENT,
      latest_call: call(lang),
      thumbnail_media_id: deletedDocument ? null : LETTER_MEDIA_ID,
      created_at: min(-2 * 24 * 60),
    },
    {
      id: RFE_CASE_ID,
      doc_type: "uscis_i797e_request_for_evidence",
      stage: STEPS[getStep(RFE_CASE_ID)].stage,
      deadline: RFE_DEADLINE,
      appointment: null,
      latest_call: call(lang, RFE_CASE_ID),
      thumbnail_media_id: null,
      created_at: min(-26 * 60),
    },
    {
      id: SCAM_CASE_ID,
      doc_type: null,
      stage: "suspicious",
      deadline: null,
      appointment: null,
      latest_call: null,
      thumbnail_media_id: null,
      created_at: min(-5 * 60),
    },
  ];
}

function rfeDetail(lang: string): CaseDetail {
  return {
    id: RFE_CASE_ID,
    user_id: FIXTURE_USER_ID,
    doc_type: "uscis_i797e_request_for_evidence",
    issuer: "USCIS",
    stage: STEPS[getStep(RFE_CASE_ID)].stage,
    deadline: RFE_DEADLINE,
    urgency: "medium",
    document_id: null,
    page_media_ids: [],
    explanation: L(
      lang,
      "USCIS necesita más pruebas para tu permiso de trabajo. Tienes que mandarlas por correo antes del 4 de diciembre, o pueden negar la solicitud.",
      "USCIS needs more evidence for your work permit. You have to mail it before December 4, or they may deny the application.",
    ),
    what_is_asked: L(
      lang,
      "Mandar por correo las pruebas que piden, con esta carta encima",
      "Mail the requested evidence, with this letter on top",
    ),
    appointment: null,
    checklist: [
      { kind: "deadline", item: L(lang, "Que llegue a USCIS antes del 4 de diciembre", "It must reach USCIS by December 4") },
      { kind: "bring", item: L(lang, "Copia de tu pasaporte o documento de identidad", "A copy of your passport or ID") },
      { kind: "bring", item: L(lang, "Prueba de que entraste a EE. UU. (formulario I-94)", "Proof of your entry to the U.S. (Form I-94)") },
      { kind: "bring", item: L(lang, "Esta carta, encima de todo lo que mandes", "This letter, on top of everything you send") },
    ],
    refs: [{ name: "receipt_number", masked: "•••• 7781" }],
    verification: { status: "verified", evidence: ["https://www.uscis.gov/contactcenter"], red_flags: [] },
    brief: {
      call_goal: L(
        lang,
        "Confirmar a qué dirección mandar las pruebas y si un recibo de envío basta",
        "Confirm which address to mail the evidence to and whether a mailing receipt is enough",
      ),
      questions_to_ask: [
        L(lang, "¿A qué dirección tengo que mandar las pruebas?", "Which address should the evidence go to?"),
        L(lang, "¿Puedo pedir más tiempo si me falta un documento?", "Can I ask for more time if a document is missing?"),
      ],
    },
    calls: (() => {
      const c = call(lang, RFE_CASE_ID);
      return c ? [c] : [];
    })(),
  };
}

function scamDetail(lang: string): CaseDetail {
  return {
    id: SCAM_CASE_ID,
    user_id: FIXTURE_USER_ID,
    doc_type: null,
    issuer: "USCIS",
    stage: "suspicious",
    deadline: null,
    urgency: "high",
    document_id: null,
    page_media_ids: [],
    explanation: null,
    what_is_asked: null,
    appointment: null,
    checklist: [],
    refs: [],
    verification: {
      status: "suspicious",
      evidence: ["https://www.uscis.gov/scams-fraud-and-misconduct/avoid-scams/common-scams"],
      red_flags: [
        L(lang, "Pide pagar una multa con tarjetas de regalo. USCIS nunca acepta tarjetas de regalo.", "It asks you to pay a fine with gift cards. USCIS never takes gift cards."),
        L(lang, "El teléfono de la carta no es un número de USCIS.", "The phone number on the letter isn't a USCIS number."),
        L(lang, "Amenaza con deportarte en 48 horas si no pagas.", "It threatens deportation within 48 hours if you don't pay."),
        L(lang, "El número de recibo no tiene el formato de USCIS.", "The receipt number doesn't match the USCIS format."),
      ],
    },
    brief: null,
    calls: [],
  };
}

export function caseDetail(caseId: string, lang: string): CaseDetail {
  if (caseId === SCAM_CASE_ID) return scamDetail(lang);
  if (caseId === RFE_CASE_ID) return rfeDetail(lang);
  const c = call(lang);
  return {
    id: caseId,
    user_id: FIXTURE_USER_ID,
    doc_type: "uscis_i797c_asylum_interview",
    issuer: "USCIS",
    stage: STEPS[getStep()].stage,
    deadline: APPOINTMENT.date,
    urgency: "high",
    document_id: deletedDocument ? null : DOC_ID,
    page_media_ids: deletedDocument ? [] : [LETTER_MEDIA_ID],
    explanation: L(
      lang,
      "Es la cita para tu entrevista de asilo. Tienes que ir con tus hijos y con un intérprete.",
      "This is your asylum interview appointment. You must go with your children and an interpreter.",
    ),
    what_is_asked: L(
      lang,
      "Ir a la entrevista de asilo con tus dependientes y un intérprete calificado",
      "Attend asylum interview with dependents and a qualified interpreter",
    ),
    appointment: APPOINTMENT,
    checklist: [
      { kind: "who_must_come", item: L(lang, "Todos los dependientes de tu solicitud I-589", "All dependents listed on the I-589") },
      { kind: "bring", item: L(lang, "Un intérprete calificado si no hablas inglés con fluidez", "A qualified interpreter if you are not fluent in English") },
      { kind: "bring", item: L(lang, "Identificación para ti y cada dependiente", "ID for you and each dependent") },
    ],
    refs: [
      { name: "receipt_number", masked: "•••• 2345" },
      { name: "a_number", masked: "•••• 5678" },
    ],
    verification: { status: "verified", evidence: ["https://www.uscis.gov/contactcenter"], red_flags: [] },
    brief: {
      call_goal: L(
        lang,
        "Confirmar que la entrevista sigue programada y preguntar qué hacer si el intérprete no puede ir",
        "Confirm the asylum interview is still scheduled; ask what to do if the interpreter can't come",
      ),
      questions_to_ask: [
        L(lang, "¿La entrevista del 12 de noviembre a las 8:30 AM sigue programada?", "Is the interview on November 12 at 8:30 AM still scheduled?"),
        L(lang, "Si el intérprete no puede ir, ¿qué debe hacer la persona antes de la entrevista?", "If the interpreter can't come, what should the applicant do before the interview?"),
      ],
    },
    calls: c ? [c] : [],
  };
}

export function transcript(callId: string): Transcript {
  if (callId === RFE_CALL_ID) {
    return {
      id: RFE_TRANSCRIPT_ID,
      call_id: callId,
      lines: [
        { at: rfeAt(2, -2.5), speaker: "agency", text: "Thank you for calling USCIS. For a case you already filed, press 1." },
        { at: rfeAt(2, -2.4), speaker: "agent", text: "(pressed 1)" },
        { at: rfeAt(2, -2.4), speaker: "agency", text: "If you received a request for evidence, press 3." },
        { at: rfeAt(2, -2.3), speaker: "agent", text: "(pressed 3)" },
        { at: rfeAt(3, -2), speaker: "agency", text: "All of our agents are busy. Please stay on the line." },
        { at: rfeAt(4, 0), speaker: "agency", text: "USCIS, this is Agent Ruiz. How can I help you?" },
        { at: rfeAt(4, 0), speaker: "agent", text: "Hi, I'm an automated assistant calling for a family about a request for evidence. The applicant is joining the call now so they can answer your questions directly." },
        { at: rfeAt(4, 0), speaker: "agency", text: "Okay, I'll wait." },
        { at: rfeAt(5, 1), speaker: "user", text: "Hello, I got a letter asking for more evidence for my work permit." },
      ],
    };
  }
  return {
    id: TRANSCRIPT_ID,
    call_id: callId,
    lines: [
      { at: min(-15), speaker: "agency", text: "Thank you for calling USCIS. For interview or appointment notices, press 2." },
      { at: min(-14), speaker: "agent", text: "(pressed 2)" },
      { at: min(-14), speaker: "agency", text: "For an asylum interview, press 2." },
      { at: min(-13.5), speaker: "agent", text: "(pressed 2)" },
      { at: min(-13), speaker: "agency", text: "All of our officers are busy. Please stay on the line." },
      { at: atStep(4, 0), speaker: "agency", text: "USCIS, this is Officer Lee. How can I help?" },
      { at: atStep(4, 0), speaker: "agent", text: "Hi, I'm an automated assistant calling for a family about an asylum interview notice. The applicant is joining the call now so they can answer your questions directly." },
      { at: atStep(4, 0), speaker: "agency", text: "Sure, I'll hold." },
      { at: atStep(5, 1), speaker: "user", text: "Hello, I want to confirm my interview on November 12 and ask about my interpreter." },
    ],
  };
}

export function memory(_userId: string, lang: string): Memory {
  if (deletedAll) return { profile: {}, facts: [], documents: [], transcripts: [] };
  const facts = [
    { id: "fact_demo01", es: "Tienes dos hijos en tu solicitud de asilo", en: "Has two children on the asylum application", category: "immigration", source: "from_document" as const, sensitivity: "sensitive" as const },
    { id: "fact_demo02", es: "Vives en el condado de Los Ángeles", en: "Lives in Los Angeles County", category: "contact", source: "user_said" as const, sensitivity: "normal" as const },
    { id: "fact_demo03", es: "Prefieres mensajes de voz", en: "Prefers voice notes", category: "contact", source: "user_said" as const, sensitivity: "normal" as const },
  ];
  return {
    profile: { county: "Los Angeles", household_size: "3" },
    facts: facts
      .filter((f) => !deletedFacts.has(f.id))
      .map((f) => ({ id: f.id, fact: L(lang, f.es, f.en), category: f.category, source: f.source, sensitivity: f.sensitivity, status: "active", recorded_at: min(-2 * 24 * 60 + 1) })),
    documents: deletedDocument
      ? []
      : [{ id: DOC_ID, doc_type: "uscis_i797c_asylum_interview", case_id: FIXTURE_CASE_ID, page_media_ids: [LETTER_MEDIA_ID], created_at: min(-2 * 24 * 60) }],
    transcripts: deletedTranscript
      ? []
      : Object.entries(CALL_CASES)
          .filter(([caseId]) => getStep(caseId) === STEPS.length - 1)
          .map(([caseId, c]) => ({ id: c.transcriptId, call_id: c.callId, case_id: caseId, created_at: atStep(6, 6, caseId) })),
  };
}

interface MessageSeed {
  minStep: number;
  maxStep?: number;
  at: () => string;
  direction: "in" | "out";
  sender: Message["sender"];
  es: string;
  en: string;
  media?: boolean;
}

const MESSAGES: MessageSeed[] = [
  { minStep: 0, at: () => min(-2 * 24 * 60), direction: "in", sender: "user", es: "", en: "", media: true },
  { minStep: 0, at: () => min(-2 * 24 * 60 + 1), direction: "out", sender: "orchestrator", es: "Es la cita para tu entrevista de asilo: jueves 12 de noviembre a las 8:30 AM. Tienes que ir con tus hijos y llevar tu propio intérprete.", en: "It's your asylum interview appointment: Thursday, November 12 at 8:30 AM. You must go with your children and bring your own interpreter." },
  { minStep: 0, at: () => min(-20), direction: "out", sender: "orchestrator", es: "Confirmamos que la carta es real. ¿Quieres que llamemos a USCIS y te avisemos cuando conteste una persona? Responde SÍ o NO.", en: "We confirmed the letter is real. Want us to call USCIS and ring you when a person answers? Reply YES or NO." },
  { minStep: 1, at: () => min(-16), direction: "in", sender: "user", es: "Sí, por favor", en: "Yes, please" },
  { minStep: 1, at: () => min(-15), direction: "out", sender: "relay", es: "Estamos llamando a USCIS. Te avisamos cuando conteste alguien.", en: "We're calling USCIS. We'll let you know when someone answers." },
  { minStep: 3, at: () => min(-13), direction: "out", sender: "relay", es: "Estamos en espera con USCIS. Te llamamos cuando conteste una persona.", en: "We're on hold with USCIS. We'll call you when a person answers." },
  { minStep: 4, at: () => atStep(4, 0), direction: "out", sender: "relay", es: "¡Contestó una persona! Te estamos llamando ahora.", en: "A person answered! We're calling you now." },
  { minStep: 6, at: () => atStep(6, 6), direction: "out", sender: "orchestrator", es: "Listo. Tu entrevista sigue el 12 de noviembre a las 8:30 AM. Recuerda llevar tu propio intérprete.", en: "Done. Your interview is still November 12 at 8:30 AM. Remember to bring your own interpreter." },
];

export function messages(_userId: string): Message[] {
  if (deletedAll) return [];
  const lang = demoLanguage();
  return MESSAGES.filter((m) => m.minStep <= getStep()).map((m, i) => ({
    id: `msg_demo${String(i).padStart(12, "0")}`,
    at: m.at(),
    direction: m.direction,
    sender: m.sender,
    body: pick(lang, m.es, m.en),
    body_en: m.media ? null : m.en,
    language: lang,
    media_ids: m.media && !deletedDocument ? [LETTER_MEDIA_ID] : [],
    case_id: FIXTURE_CASE_ID,
  }));
}

export function suggestions(_userId: string, lang: string): Suggestion[] {
  if (deletedAll) return [];
  return [
    {
      id: "sug_countdown",
      kind: "countdown",
      case_id: FIXTURE_CASE_ID,
      title: L(lang, "Tu entrevista es en 20 días", "Your interview is in 20 days"),
      detail: L(lang, "Repasa qué llevar", "Review what to bring"),
      action: L(lang, "Preparar", "Prepare"),
      prefill: pick(demoLanguage(), "¿Qué tengo que llevar a mi entrevista de asilo?", "What do I need to bring to my asylum interview?"),
    },
    {
      id: "sug_glossary",
      kind: "glossary",
      case_id: FIXTURE_CASE_ID,
      title: L(lang, "Palabras clave en inglés", "Key English words"),
      detail: L(lang, "asylum · interpreter · dependent", "asylum · interpreter · dependent"),
      action: L(lang, "Practicar", "Practice"),
      prefill: pick(demoLanguage(), "Quiero practicar las palabras en inglés para mi entrevista", "I want to practice the English words for my interview"),
    },
    {
      id: "sug_checklist",
      kind: "checklist",
      case_id: FIXTURE_CASE_ID,
      title: L(lang, "No olvides: un intérprete", "Don't forget: an interpreter"),
      detail: L(lang, "Te ayudamos", "We can help"),
      action: L(lang, "Preguntar", "Ask"),
      prefill: pick(demoLanguage(), "¿Cómo consigo un intérprete calificado?", "How do I find a qualified interpreter?"),
    },
  ];
}

export function deleteFact(factId: string): void {
  deletedFacts.set(factId, new Date().toISOString());
  notify();
}

export function deleteDocument(_documentId: string): void {
  deletedDocument = new Date().toISOString();
  notify();
}

export function deleteTranscript(_transcriptId: string): void {
  deletedTranscript = new Date().toISOString();
  notify();
}

export function deleteEverything(_userId: string): DeleteCounts {
  deletedAll = new Date().toISOString();
  notify();
  return { facts: 3, documents: 1, media: 1, transcripts: 1, messages: MESSAGES.length, events: FEED.length };
}
