import type { CommonStrings } from "../en/common";

/** US Spanish with formal usted, the register of every WhatsApp template (Plan.md). */
export const common: CommonStrings = {
  appName: "Avocado",
  nav: {
    cases: "Mis trámites",
    memory: "Perfil",
    back: "← Mis trámites",
  },
  languageSwitch: "Idioma",
  docTypes: {
    uscis_i797c_asylum_interview: "Entrevista de asilo",
    uscis_i797e_request_for_evidence: "Solicitud de pruebas",
  },
  docTypeFallback: "Carta",
  stages: {
    received: "Carta recibida",
    explaining: "Leyendo su carta",
    needs_better_image: "Necesitamos otra foto",
    needs_answer: "Falta una respuesta",
    checking: "Verificando la carta",
    suspicious: "Podría no ser real",
    unknown: "No pudimos confirmarla",
    awaiting_consent: "Esperando su permiso",
    calling: "Llamando",
    on_hold: "En espera",
    connected: "Hablando con una persona",
    call_ended: "Llamada terminada",
    closed: "Cerrado",
  },
  trackerSteps: ["Carta", "Verificada", "Llamando", "En espera", "Persona"],
  assistant: {
    title: "Asistente",
    viaWhatsApp: "por WhatsApp",
    placeholder: "Pregunte lo que quiera…",
    send: "Abrir en WhatsApp",
    you: "Usted",
  },
  deleted: (date: string) => `(borrado el ${date})`,
  quote: (text: string) => `“${text}”`,
  loading: "Cargando…",
  loadError: "No podemos conectar con el servidor. Reintentando…",
  notFound: "No encontramos eso.",
};
