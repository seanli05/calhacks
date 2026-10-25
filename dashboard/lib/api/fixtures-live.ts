/**
 * Fixture data for the live call view: the bridged part of the demo call, played
 * as a stream, and the Spanish translation book (backend/app/glossary/terms.csv).
 * All fictional, like the rest of the fixtures.
 */

import { pick } from "./fixtures-fa";
import type { GlossaryEntry, LiveCallEvent, LiveTip, Speaker } from "./types";

interface ScriptLine {
  speaker: Speaker;
  en: string;
  es: string;
  /** A tip shown once this line is translated. */
  tip?: Omit<LiveTip, "id" | "line_id" | "meaning"> & { es: string; en: string };
  /** The tip (by line index) this line follows up on. */
  uses?: number;
}

/** The asylum interview call: confirming the interview and asking about the interpreter. */
const ASYLUM_SCRIPT: ScriptLine[] = [
  {
    speaker: "agency",
    en: "Okay, I have the case open. Can you confirm your full name and date of birth for me?",
    es: "Bien, tengo el caso abierto. ¿Puede confirmarme su nombre completo y su fecha de nacimiento?",
    tip: {
      kind: "yourself",
      say_en: null,
      es: "Le preguntan su nombre y fecha de nacimiento. Conteste usted; nosotros nunca respondemos por usted.",
      en: "They're asking your name and date of birth. Answer yourself; we never answer for you.",
    },
  },
  {
    speaker: "user",
    en: "Ana Morales, March 14, 1988.",
    es: "Ana Morales, 14 de marzo de 1988.",
    uses: 0,
  },
  {
    speaker: "agency",
    en: "Thank you. Your asylum interview is still scheduled for November 12 at 8:30 AM at the asylum office in Tustin.",
    es: "Gracias. Su entrevista de asilo sigue programada para el 12 de noviembre a las 8:30 AM en la oficina de asilo de Tustin.",
    tip: {
      kind: "ask",
      say_en: "My interpreter may not be able to come. What should I do?",
      es: "Puede que mi intérprete no pueda ir. ¿Qué debo hacer?",
      en: "My interpreter may not be able to come. What should I do?",
    },
  },
  {
    speaker: "user",
    en: "My interpreter may not be able to come. What should I do?",
    es: "Puede que mi intérprete no pueda ir. ¿Qué debo hacer?",
    uses: 2,
  },
  {
    speaker: "agency",
    en: "You have to bring your own interpreter; we don't provide one. If they can't come, send a reschedule request in writing before your appointment.",
    es: "Tiene que traer su propio intérprete; nosotros no lo proporcionamos. Si no puede ir, envíe una solicitud de reprogramación por escrito antes de su cita.",
    tip: {
      kind: "ask",
      say_en: "Do my children need to come to the interview too?",
      es: "¿Mis hijos también tienen que ir a la entrevista?",
      en: "Do my children need to come to the interview too?",
    },
  },
  {
    speaker: "user",
    en: "Do my children need to come to the interview too?",
    es: "¿Mis hijos también tienen que ir a la entrevista?",
    uses: 4,
  },
  {
    speaker: "agency",
    en: "Yes. Every dependent on your application has to attend, and bring an identity document for each of them.",
    es: "Sí. Cada dependiente de su solicitud tiene que asistir, y traiga un documento de identidad para cada uno.",
    tip: {
      kind: "ask",
      say_en: "Can I have a reference number for this call?",
      es: "¿Me puede dar un número de referencia de esta llamada?",
      en: "Can I have a reference number for this call?",
    },
  },
];

/** The Request for Evidence call: where to mail the evidence and whether there's more time. */
const RFE_SCRIPT: ScriptLine[] = [
  {
    speaker: "agency",
    en: "I can help with that. What's the receipt number on the letter?",
    es: "Puedo ayudarle con eso. ¿Cuál es el número de recibo de la carta?",
    tip: {
      kind: "yourself",
      say_en: null,
      es: "Le piden el número de recibo. Está arriba en su carta; léalo usted.",
      en: "They're asking for the receipt number. It's at the top of your letter; read it yourself.",
    },
  },
  {
    speaker: "user",
    en: "Yes, it starts with I-O-E and ends in seven seven eight one.",
    es: "Sí, empieza con I-O-E y termina en siete siete ocho uno.",
    uses: 0,
  },
  {
    speaker: "agency",
    en: "Thank you. I see the request for evidence for your work permit. It's due December 4.",
    es: "Gracias. Veo la solicitud de pruebas para su permiso de trabajo. Vence el 4 de diciembre.",
    tip: {
      kind: "ask",
      say_en: "Which address should I mail the evidence to?",
      es: "¿A qué dirección mando las pruebas?",
      en: "Which address should I mail the evidence to?",
    },
  },
  {
    speaker: "user",
    en: "Which address should I mail the evidence to?",
    es: "¿A qué dirección mando las pruebas?",
    uses: 2,
  },
  {
    speaker: "agency",
    en: "Use the address printed on the letter, and put the letter on top of your documents.",
    es: "Use la dirección impresa en la carta, y ponga la carta encima de sus documentos.",
    tip: {
      kind: "ask",
      say_en: "Can I get more time if a document is missing?",
      es: "¿Me pueden dar más tiempo si me falta un documento?",
      en: "Can I get more time if a document is missing?",
    },
  },
  {
    speaker: "user",
    en: "Can I get more time if a document is missing?",
    es: "¿Me pueden dar más tiempo si me falta un documento?",
    uses: 4,
  },
  {
    speaker: "agency",
    en: "We can't extend the deadline. Send what you have, and explain in writing why the missing document isn't included.",
    es: "No podemos extender la fecha límite. Mande lo que tenga, y explique por escrito por qué falta ese documento.",
    tip: {
      kind: "ask",
      say_en: "Can I have a reference number for this call?",
      es: "¿Me puede dar un número de referencia de esta llamada?",
      en: "Can I have a reference number for this call?",
    },
  },
];

/** Each demo call's script, by call id. */
const SCRIPTS: Record<string, ScriptLine[]> = {
  call_demo000000000001: ASYLUM_SCRIPT,
  call_demo000000000003: RFE_SCRIPT,
};

const tokens = (text: string): string[] => text.match(/\S+\s*/g) ?? [];

/** When each call's playback started and last stopped, so a quick restart resumes it. */
const playback = new Map<string, { startedAt: number; stoppedAt: number | null }>();

/** A restart this soon after a stop (e.g. a language switch) resumes the call. */
const RESUME_WITHIN_MS = 2000;

/**
 * Plays the script into `emit`: each line is heard, then its translation arrives a
 * word or two at a time, like a model streaming tokens. Returns stop. Restarting
 * right after a stop (the language switch) replays the lines already heard at once,
 * in the new language, and carries on from there, like the API's reconnect.
 */
export function liveCall(callId: string, lang: string, emit: (event: LiveCallEvent) => void): () => void {
  const now = Date.now();
  const last = playback.get(callId);
  const resume = last?.stoppedAt != null && now - last.stoppedAt < RESUME_WITHIN_MS;
  const state = { startedAt: resume ? last.startedAt : now, stoppedAt: null as number | null };
  playback.set(callId, state);
  const elapsed = now - state.startedAt;

  const timers: ReturnType<typeof setTimeout>[] = [];
  let at = 900;
  // Seeded per call, so a resumed call keeps the same timeline.
  let seed = [...callId].reduce((sum, c) => sum + c.charCodeAt(0), 0);
  const jitter = (lo: number, hi: number) => {
    seed = (seed * 9301 + 49297) % 233280;
    return lo + (seed / 233280) * (hi - lo);
  };
  const later = (ms: number, fn: () => void) => {
    at += ms;
    timers.push(setTimeout(fn, Math.max(0, at - elapsed)));
  };

  (SCRIPTS[callId] ?? ASYLUM_SCRIPT).forEach((line, i) => {
    const id = `${callId}_live${i}`;
    const text = pick(lang, line.es, line.en);
    later(i === 0 ? 0 : jitter(1600, 2600), () =>
      emit({ type: "line", id, at: new Date().toISOString(), speaker: line.speaker, en: line.en }),
    );
    if (line.uses != null) later(0, () => emit({ type: "tip_used", id: `${callId}_tip${line.uses}` }));
    at += jitter(350, 550); // the translation's first token
    const words = tokens(text);
    const deltas: { at: number; text: string }[] = [];
    for (let w = 0; w < words.length; ) {
      const take = jitter(0, 1) < 0.3 ? 2 : 1;
      at += jitter(40, 110);
      deltas.push({ at, text: words.slice(w, w + take).join("") });
      w += take;
    }
    // Words already heard come in one piece; the rest stream as before.
    const heard = deltas.filter((d) => d.at <= elapsed);
    if (heard.length) timers.push(setTimeout(() => emit({ type: "delta", id, text: heard.map((d) => d.text).join("") }), 0));
    for (const d of deltas.slice(heard.length)) timers.push(setTimeout(() => emit({ type: "delta", id, text: d.text }), d.at - elapsed));
    later(80, () => emit({ type: "done", id }));
    const tip = line.tip;
    if (tip) {
      later(500, () =>
        emit({
          type: "tip",
          tip: {
            id: `${callId}_tip${i}`,
            kind: tip.kind,
            line_id: id,
            say_en: tip.say_en,
            meaning: { text: pick(lang, tip.es, tip.en), en: tip.en },
          },
        }),
      );
    }
  });

  return () => {
    state.stoppedAt = Date.now();
    timers.forEach(clearTimeout);
  };
}

/** The demo user's book: Dari for a Dari user, Spanish otherwise. */
export function glossary(lang: string): GlossaryEntry[] {
  return lang === "fa" ? GLOSSARY_FA : GLOSSARY_ES;
}

const GLOSSARY_ES: GlossaryEntry[] = [
  { term: "asylum", translation: "asilo", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "affirmative asylum", translation: "asilo afirmativo", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "asylum interview", translation: "entrevista de asilo", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "asylum office", translation: "oficina de asilo", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "asylum officer", translation: "oficial de asilo", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "asylum application", translation: "solicitud de asilo", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "application for asylum and for withholding of removal", translation: "Solicitud de Asilo y de Suspensión de Remoción", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "withholding of removal", translation: "suspensión de remoción", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/obtener-asilo-en-los-estados-unidos" },
  { term: "convention against torture", translation: "Convención Contra la Tortura", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/obtener-asilo-en-los-estados-unidos" },
  { term: "grant of asylum", translation: "concesión de asilo", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "applicant", translation: "solicitante", trust_level: "official", source_url: "https://www.uscis.gov/es/humanitarios/asilo" },
  { term: "principal applicant", translation: "solicitante principal", trust_level: "machine", source_url: null },
  { term: "dependent", translation: "dependiente", trust_level: "official", source_url: "https://languageaccess.courts.ca.gov/system/files/2025-05/Legal%20Glossary%20English%20Spanish.pdf" },
  { term: "derivative", translation: "derivado", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "spouse", translation: "cónyuge", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "unmarried child", translation: "hijo soltero", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/tipos-de-decisiones-de-asilo-afirmativo" },
  { term: "family member", translation: "miembro de la familia", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "interpreter", translation: "intérprete", trust_level: "official", source_url: "https://languageaccess.courts.ca.gov/system/files/2025-05/Legal%20Glossary%20English%20Spanish.pdf" },
  { term: "qualified interpreter", translation: "intérprete calificado", trust_level: "machine", source_url: null },
  { term: "contract interpreter", translation: "intérprete contratado", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "interview notice", translation: "notificación de entrevista", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "appointment notice", translation: "notificación de cita", trust_level: "official", source_url: "https://www.uscis.gov/es/formularios/guias-para-presentacion-de-formularios/como-prepararse-para-su-cita-de-servicios-biometricos" },
  { term: "notice of action", translation: "Notificación de Acción", trust_level: "official", source_url: "https://www.uscis.gov/es/formularios/guias-para-presentacion-de-formularios/como-prepararse-para-su-cita-de-servicios-biometricos" },
  { term: "receipt notice", translation: "notificación de recibo", trust_level: "official", source_url: "https://www.uscis.gov/es/humanitarios/asilo" },
  { term: "receipt number", translation: "número de recibo", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "a-number", translation: "Número A", trust_level: "official", source_url: "https://www.uscis.gov/es/herramientas/glosario" },
  { term: "case status", translation: "estatus de caso", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "failure to appear", translation: "falta de comparecencia", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "exceptional circumstances", translation: "circunstancias excepcionales", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "reschedule", translation: "reprogramar", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "reschedule request", translation: "solicitud de reprogramación", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "biometrics", translation: "datos biométricos", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "biometric services appointment", translation: "cita de servicios biométricos", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "application support center", translation: "Centro de Asistencia en Solicitudes", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "fingerprints", translation: "huellas dactilares", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "identity document", translation: "documento de identidad", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "passport", translation: "pasaporte", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "travel document", translation: "documento de viaje", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "arrival-departure record", translation: "Documento de Entrada/Salida", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "original document", translation: "documento original", trust_level: "machine", source_url: null },
  { term: "birth certificate", translation: "certificado de nacimiento", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "marriage certificate", translation: "certificado de matrimonio", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "certified translation", translation: "traducción certificada", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "evidence", translation: "evidencia", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "oath", translation: "juramento", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "witness", translation: "testigo", trust_level: "official", source_url: "https://languageaccess.courts.ca.gov/system/files/2025-05/Legal%20Glossary%20English%20Spanish.pdf" },
  { term: "confidential", translation: "confidencial", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "attorney", translation: "abogado", trust_level: "official", source_url: "https://languageaccess.courts.ca.gov/system/files/2025-05/Legal%20Glossary%20English%20Spanish.pdf" },
  { term: "accredited representative", translation: "representante autorizado", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "free legal help", translation: "ayuda legal gratuita", trust_level: "machine", source_url: null },
  { term: "legal advice", translation: "asesoría legal", trust_level: "official", source_url: "https://www.uscis.gov/es/herramientas/glosario" },
  { term: "notario", translation: "notario", trust_level: "machine", source_url: null },
  { term: "fraud", translation: "fraude", trust_level: "official", source_url: "https://languageaccess.courts.ca.gov/system/files/2025-05/Legal%20Glossary%20English%20Spanish.pdf" },
  { term: "scam", translation: "estafa", trust_level: "official", source_url: "https://www.uscis.gov/es/fraude-estafas-y-fallas-en-el-desempeno/evite-las-estafas-de-inmigracion/estafas-comunes" },
  { term: "contact center", translation: "Centro de Contacto", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "field office", translation: "oficina local", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "immigration court", translation: "tribunal de inmigración", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "immigration judge", translation: "juez de inmigración", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "hearing", translation: "audiencia", trust_level: "official", source_url: "https://languageaccess.courts.ca.gov/system/files/2025-05/Legal%20Glossary%20English%20Spanish.pdf" },
  { term: "referral to immigration court", translation: "referido al tribunal de inmigración", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "removal proceedings", translation: "procedimientos de remoción", trust_level: "official", source_url: "https://www.uscis.gov/es/i-589" },
  { term: "deportation", translation: "deportación", trust_level: "official", source_url: "https://www.uscis.gov/es/herramientas/glosario" },
  { term: "employment authorization document", translation: "Documento de Autorización de Empleo", trust_level: "official", source_url: "https://www.uscis.gov/es/residencia-permanente-tarjeta-verde/procesos-y-procedimientos-para-la-residencia-permanente/documento-de-autorizacion-de-empleo" },
  { term: "work permit", translation: "permiso de trabajo", trust_level: "official", source_url: "https://www.uscis.gov/es/fraude-estafas-y-fallas-en-el-desempeno/evite-las-estafas-de-inmigracion/estafas-comunes" },
  { term: "parole", translation: "permiso de permanencia temporal", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "deadline", translation: "plazo límite", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "mailing address", translation: "dirección postal", trust_level: "machine", source_url: null },
  { term: "change of address", translation: "cambio de dirección", trust_level: "official", source_url: "https://www.uscis.gov/es/cambiodedireccion" },
  { term: "decision", translation: "decisión", trust_level: "official", source_url: "https://languageaccess.courts.ca.gov/system/files/2025-05/Legal%20Glossary%20English%20Spanish.pdf" },
  { term: "approval", translation: "aprobación", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/tipos-de-decisiones-de-asilo-afirmativo" },
  { term: "denial", translation: "denegación", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/tipos-de-decisiones-de-asilo-afirmativo" },
  { term: "dismissal", translation: "desestimación", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
  { term: "security check", translation: "verificación de seguridad", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/el-proceso-de-asilo-afirmativo" },
  { term: "check-in", translation: "registro de llegada", trust_level: "machine", source_url: null },
  { term: "disability accommodation", translation: "acomodo por discapacidad", trust_level: "official", source_url: "https://www.uscis.gov/es/programas-humanitarios/refugiados-y-asilo/asilo/como-prepararse-para-su-entrevista-de-asilo" },
];

/** The Dari rows of backend/app/glossary/terms.csv. */
const GLOSSARY_FA: GlossaryEntry[] = [
  { term: "asylum", translation: "پناهندگی", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "affirmative asylum", translation: "پناهندگی ایجابی (affirmative asylum)", trust_level: "machine", source_url: null },
  { term: "asylum interview", translation: "مصاحبه پناهندگی", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "asylum office", translation: "دفتر پناهندگی", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "asylum officer", translation: "افسر پناهندگی", trust_level: "machine", source_url: null },
  { term: "asylum application", translation: "درخواست پناهندگی", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "application for asylum and for withholding of removal", translation: "درخواست پناهندگی و عدم اخراج", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "withholding of removal", translation: "عدم اخراج", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "convention against torture", translation: "کنوانسیون منع شکنجه", trust_level: "machine", source_url: null },
  { term: "grant of asylum", translation: "اعطای پناهندگی", trust_level: "machine", source_url: null },
  { term: "applicant", translation: "متقاضی", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "principal applicant", translation: "متقاضی اصلی", trust_level: "machine", source_url: null },
  { term: "dependent", translation: "وابسته", trust_level: "machine", source_url: null },
  { term: "derivative", translation: "مشتق", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "spouse", translation: "همسر", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "unmarried child", translation: "فرزند مجرد", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "family member", translation: "عضو خانواده", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "interpreter", translation: "ترجمان", trust_level: "machine", source_url: null },
  { term: "qualified interpreter", translation: "ترجمان واجد شرایط", trust_level: "machine", source_url: null },
  { term: "contract interpreter", translation: "ترجمان قراردادی", trust_level: "machine", source_url: null },
  { term: "interview notice", translation: "اطلاعیه مصاحبه", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "appointment notice", translation: "اطلاعیه قرار ملاقات", trust_level: "machine", source_url: null },
  { term: "notice of action", translation: "اطلاعیه اقدام (Notice of Action)", trust_level: "machine", source_url: null },
  { term: "receipt notice", translation: "اطلاعیه رسید", trust_level: "machine", source_url: null },
  { term: "receipt number", translation: "شماره رسید", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "a-number", translation: "شماره A-Number", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "case status", translation: "وضعیت دوسیه", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "failure to appear", translation: "عدم حضور", trust_level: "machine", source_url: null },
  { term: "exceptional circumstances", translation: "شرایط استثنایی", trust_level: "machine", source_url: null },
  { term: "reschedule", translation: "تعیین وقت مجدد", trust_level: "machine", source_url: null },
  { term: "reschedule request", translation: "درخواست تعیین وقت مجدد", trust_level: "machine", source_url: null },
  { term: "biometrics", translation: "معلومات بایومتریک", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "biometric services appointment", translation: "قرار ملاقات خدمات بیومتریک", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "application support center", translation: "مرکز پشتیبانی درخواست (ASC)", trust_level: "machine", source_url: null },
  { term: "fingerprints", translation: "اثر انگشت", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "identity document", translation: "سند هویت", trust_level: "machine", source_url: null },
  { term: "passport", translation: "پاسپورت", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "travel document", translation: "سند سفر", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "arrival-departure record", translation: "سوابق ورود و خروج", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "original document", translation: "سند اصلی", trust_level: "machine", source_url: null },
  { term: "birth certificate", translation: "سند تولد", trust_level: "machine", source_url: null },
  { term: "marriage certificate", translation: "نکاح خط", trust_level: "machine", source_url: null },
  { term: "certified translation", translation: "ترجمهٔ تصدیق‌شده", trust_level: "machine", source_url: null },
  { term: "evidence", translation: "شواهد", trust_level: "machine", source_url: null },
  { term: "oath", translation: "سوگند", trust_level: "machine", source_url: null },
  { term: "witness", translation: "شاهد", trust_level: "machine", source_url: null },
  { term: "confidential", translation: "محرمانه", trust_level: "machine", source_url: null },
  { term: "attorney", translation: "وکیل", trust_level: "official", source_url: "https://www.uscis.gov/sites/default/files/document/flyers/AvoidScamsFlyerAfghanNationalsDr.pdf" },
  { term: "accredited representative", translation: "نماینده معتبر", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "free legal help", translation: "کمک حقوقی رایگان", trust_level: "machine", source_url: null },
  { term: "legal advice", translation: "مشوره حقوقی", trust_level: "official", source_url: "https://www.uscis.gov/sites/default/files/document/flyers/AvoidScamsFlyerAfghanNationalsDr.pdf" },
  { term: "notario", translation: "پابلک نوتری (notario)", trust_level: "machine", source_url: null },
  { term: "fraud", translation: "تقلب", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "scam", translation: "کلاهبرداری", trust_level: "machine", source_url: null },
  { term: "contact center", translation: "مرکز تماس", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "field office", translation: "دفتر ساحوی", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "immigration court", translation: "محکمهٔ مهاجرت", trust_level: "machine", source_url: null },
  { term: "immigration judge", translation: "قاضی مهاجرت", trust_level: "official", source_url: "https://www.nyc.gov/assets/immigrants/downloads/pdf/Immigration-Court-101-2026-Farsi-Persian.pdf" },
  { term: "hearing", translation: "جلسهٔ محکمه", trust_level: "machine", source_url: null },
  { term: "referral to immigration court", translation: "ارجاع به محکمهٔ مهاجرت", trust_level: "machine", source_url: null },
  { term: "removal proceedings", translation: "مراحل قانونی اخراج", trust_level: "machine", source_url: null },
  { term: "deportation", translation: "اخراج (دیپورت)", trust_level: "official", source_url: "https://www.nyc.gov/assets/immigrants/downloads/pdf/Immigration-Court-101-2026-Farsi-Persian.pdf" },
  { term: "employment authorization document", translation: "سند جواز کار", trust_level: "official", source_url: "https://www.uscis.gov/sites/default/files/document/flyers/AvoidScamsFlyerAfghanNationalsDr.pdf" },
  { term: "work permit", translation: "مجوز کار", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "parole", translation: "پیرول", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "deadline", translation: "مهلت", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "mailing address", translation: "آدرس پستی", trust_level: "machine", source_url: null },
  { term: "change of address", translation: "تغییر آدرس", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "decision", translation: "تصمیم", trust_level: "machine", source_url: null },
  { term: "approval", translation: "تایید", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "denial", translation: "رد", trust_level: "machine", source_url: null },
  { term: "dismissal", translation: "لغو درخواست (dismissal)", trust_level: "machine", source_url: null },
  { term: "security check", translation: "بررسی امنیتی", trust_level: "official", source_url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals-dari" },
  { term: "check-in", translation: "ثبت حضور", trust_level: "machine", source_url: null },
  { term: "disability accommodation", translation: "تسهیلات برای افراد دارای معلولیت", trust_level: "machine", source_url: null },
];
