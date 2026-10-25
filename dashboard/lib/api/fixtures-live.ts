/**
 * Fixture data for the live call view: the bridged part of the demo call, played
 * as a stream, and the Spanish translation book (backend/app/glossary/terms.csv).
 * All fictional, like the rest of the fixtures.
 */

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

const SCRIPT: ScriptLine[] = [
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

const tokens = (text: string): string[] => text.match(/\S+\s*/g) ?? [];
const jitter = (lo: number, hi: number) => lo + Math.random() * (hi - lo);

/**
 * Plays the script into `emit`: each line is heard, then its translation arrives a
 * word or two at a time, like a model streaming tokens. Returns stop.
 */
export function liveCall(callId: string, lang: string, emit: (event: LiveCallEvent) => void): () => void {
  const timers: ReturnType<typeof setTimeout>[] = [];
  let at = 900;
  const later = (ms: number, fn: () => void) => {
    at += ms;
    timers.push(setTimeout(fn, at));
  };

  SCRIPT.forEach((line, i) => {
    const id = `${callId}_live${i}`;
    later(i === 0 ? 0 : jitter(1600, 2600), () =>
      emit({ type: "line", id, at: new Date().toISOString(), speaker: line.speaker, en: line.en }),
    );
    if (line.uses != null) later(0, () => emit({ type: "tip_used", id: `${callId}_tip${line.uses}` }));
    at += jitter(350, 550); // the translation's first token
    const words = tokens(lang === "es" ? line.es : line.en);
    for (let w = 0; w < words.length; ) {
      const take = Math.random() < 0.3 ? 2 : 1;
      const text = words.slice(w, w + take).join("");
      w += take;
      later(jitter(40, 110), () => emit({ type: "delta", id, text }));
    }
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
            meaning: { text: lang === "es" ? tip.es : tip.en, en: tip.en },
          },
        }),
      );
    }
  });

  return () => timers.forEach(clearTimeout);
}

/** The demo user's book is Spanish whatever language the dashboard shows. */
export function glossary(_lang: string): GlossaryEntry[] {
  return GLOSSARY_ES;
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
