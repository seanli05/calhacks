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

export const FIXTURE_USER_ID = "user_demo000000000001";
export const FIXTURE_CASE_ID = "case_demo000000000001";
/** A second, made-up letter that research flagged as a scam. */
const SCAM_CASE_ID = "case_demo000000000002";
const CALL_ID = "call_demo000000000001";
const DOC_ID = "doc_demo0000000000001";
const TRANSCRIPT_ID = "transcript_demo000000001";
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

let step = START_STEP;
const listeners = new Set<() => void>();
/** When each later step was first shown, so its events get a real "now" time. */
const revealedAt = new Map<number, string>();
const deletedFacts = new Map<string, string>();
let deletedDocument: string | null = null;
let deletedTranscript: string | null = null;
let deletedAll: string | null = null;

export function getStep(): number {
  return step;
}

export function setStep(next: number): void {
  step = Math.max(0, Math.min(STEPS.length - 1, next));
  if (step > HOLD_STEP && !revealedAt.has(step)) revealedAt.set(step, new Date().toISOString());
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

const L = (lang: string, es: string, en: string): Localized => ({ text: lang === "es" ? es : en, en });

/** Time for an event that belongs to step `s`: fixed before the hold, "when shown" after. */
function atStep(s: number, fallbackMinutes: number): string {
  return revealedAt.get(s) ?? min(fallbackMinutes);
}

// ---------------------------------------------------------------------------

export function demo(): DemoInfo {
  return { user_id: FIXTURE_USER_ID, case_id: deletedAll ? null : FIXTURE_CASE_ID };
}

export function config(): PublicConfig {
  return { whatsapp_number: "+14155238886", sandbox_join_message: "join fixture-demo" };
}

export function user(userId: string): UserInfo {
  return { id: userId, language: "es" };
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
  { id: "event_f02", minStep: 0, at: () => min(-2 * 24 * 60 + 1), type: "research.fast_done", es: "Te explicamos la carta en español", en: "We explained the letter in Spanish" },
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
];

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
    : FEED.filter((e) => e.minStep <= step && (steps || !e.step)).map((e) => ({
        id: e.id,
        at: e.at(),
        type: e.type,
        case_id: FIXTURE_CASE_ID,
        call_id: e.call ? CALL_ID : null,
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

function call(lang: string): CallSummary | null {
  const s = STEPS[step];
  if (!s.callState) return null;
  const ended = s.callState === "ended";
  return {
    id: CALL_ID,
    state: s.callState,
    outcome: ended ? "resolved" : null,
    started_at: min(-15),
    ended_at: ended ? atStep(6, 6) : null,
    hold_started_at: step >= HOLD_STEP ? min(-13) : null,
    report: ended
      ? {
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
        }
      : null,
    transcript_id: ended && !deletedTranscript ? TRANSCRIPT_ID : null,
  };
}

const APPOINTMENT = { date: "2026-11-12", time: "08:30", location: "Los Angeles Asylum Office, Tustin, CA" };

export function cases(_userId: string, lang: string): CaseSummary[] {
  if (deletedAll) return [];
  return [
    {
      id: FIXTURE_CASE_ID,
      doc_type: "uscis_i797c_asylum_interview",
      stage: STEPS[step].stage,
      deadline: APPOINTMENT.date,
      appointment: APPOINTMENT,
      latest_call: call(lang),
      thumbnail_media_id: deletedDocument ? null : LETTER_MEDIA_ID,
      created_at: min(-2 * 24 * 60),
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
  const c = call(lang);
  return {
    id: caseId,
    user_id: FIXTURE_USER_ID,
    doc_type: "uscis_i797c_asylum_interview",
    issuer: "USCIS",
    stage: STEPS[step].stage,
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
    transcripts: step === STEPS.length - 1 && !deletedTranscript ? [{ id: TRANSCRIPT_ID, call_id: CALL_ID, case_id: FIXTURE_CASE_ID, created_at: atStep(6, 6) }] : [],
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
  return MESSAGES.filter((m) => m.minStep <= step).map((m, i) => ({
    id: `msg_demo${String(i).padStart(12, "0")}`,
    at: m.at(),
    direction: m.direction,
    sender: m.sender,
    body: m.es,
    body_en: m.media ? null : m.en,
    language: "es",
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
      prefill: "¿Qué tengo que llevar a mi entrevista de asilo?",
    },
    {
      id: "sug_glossary",
      kind: "glossary",
      case_id: FIXTURE_CASE_ID,
      title: L(lang, "Palabras clave en inglés", "Key English words"),
      detail: L(lang, "asylum · interpreter · dependent", "asylum · interpreter · dependent"),
      action: L(lang, "Practicar", "Practice"),
      prefill: "Quiero practicar las palabras en inglés para mi entrevista",
    },
    {
      id: "sug_checklist",
      kind: "checklist",
      case_id: FIXTURE_CASE_ID,
      title: L(lang, "No olvides: un intérprete", "Don't forget: an interpreter"),
      detail: L(lang, "Te ayudamos", "We can help"),
      action: L(lang, "Preguntar", "Ask"),
      prefill: "¿Cómo consigo un intérprete calificado?",
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
