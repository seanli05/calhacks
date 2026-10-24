import type { CaseStrings } from "../en/case";

export const caseView: CaseStrings = {
  yourLetter: "Tu carta",
  stamp: "Verificada",
  when: "Cuándo",
  where: "Dónde",
  kinds: { who_must_come: "Obligatorio", bring: "Lleva", deadline: "Fecha límite" },
  agencyFallback: "la agencia",
  refs: { receipt_number: "Recibo", a_number: "A-Number" },
  verdict: {
    verified: "Es una carta real",
    suspicious: "Esta carta podría no ser real",
    unknown: "No pudimos confirmar esta carta",
    pending: "Verificando la carta",
  },
  officialSource: (domain: string) =>
    `Llamamos al número oficial de ${domain}, nunca al de la carta`,
  liveCall: "Llamada en curso",
  onHold: "en espera",
  hero: {
    received: { title: "Recibimos tu carta", sub: "Te la explicamos en un momento." },
    explaining: {
      title: "Leyendo tu carta",
      sub: "Te mandamos la explicación por WhatsApp.",
    },
    needs_better_image: {
      title: "Necesitamos una foto más clara",
      sub: "Manda otra foto por WhatsApp, con buena luz y la página completa.",
    },
    needs_answer: {
      title: "Necesitamos una respuesta tuya",
      sub: "Revisa WhatsApp: te hicimos una pregunta sobre tu carta.",
    },
    checking: {
      title: "Verificando que la carta es real",
      sub: "La comparamos con fuentes oficiales antes de llamar a nadie.",
    },
    suspicious: {
      title: "Esta carta podría no ser real",
      sub: "No llames a los números de la carta ni mandes dinero. Te explicamos por WhatsApp.",
    },
    unknown: {
      title: "No pudimos confirmar esta carta",
      sub: "No llamaremos a nadie hasta estar seguros. Te decimos qué hacer por WhatsApp.",
    },
    awaiting_consent: {
      title: (agency: string) => `¿Llamamos a ${agency} por ti?`,
      sub: "Responde SÍ en WhatsApp. Esto es lo que vamos a preguntar:",
    },
    dialing: {
      title: (agency: string) => `Estamos llamando a ${agency}`,
      sub: "Marcamos el número oficial. Te avisamos cuando conteste alguien.",
    },
    menu: {
      title: (agency: string) => `Estamos llamando a ${agency}`,
      sub: "Estamos pasando por el menú automático.",
    },
    on_hold: {
      title: (agency: string) => `Estamos en espera con ${agency}`,
      sub: "Te llamamos cuando conteste una persona. Puedes seguir con tu día.",
    },
    human: {
      title: "Contestó una persona",
      sub: "Te estamos llamando ahora para conectarte.",
    },
    connected: {
      title: (agency: string) => `Estás hablando con ${agency}`,
      sub: "Ya puedes hablar con el agente.",
    },
    call_ended: { title: (agency: string) => `Hablamos con ${agency}` },
    call_failed: {
      title: (agency: string) => `No pudimos hablar con una persona de ${agency}`,
      sub: "Podemos intentarlo de nuevo cuando quieras. Solo dínoslo por WhatsApp.",
    },
    call_unreachable: {
      title: "No pudimos contactarte",
      sub: "Contestó una persona, pero tu teléfono no respondió. Podemos intentarlo de nuevo.",
    },
    closed: { title: "Este caso está cerrado", sub: "Todo queda en tu historial." },
  },
  outcome: {
    resolved: "Resuelto",
    partial: "Resuelto en parte",
    failed: "No resuelto",
    user_unreachable: "No pudimos contactarte",
  },
  reference: (n: string) => `Número de referencia: ${n}`,
  viewTranscript: "Ver transcripción",
  transcript: "Transcripción",
  transcriptNote: "La llamada fue en inglés. No guardamos el audio.",
  speakers: { agent: "[App]", agency: "Agencia", user: "Tú" },
  close: "Cerrar",
};
