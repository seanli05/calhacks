import type { CasesStrings } from "../en/cases";

export const casesPage: CasesStrings = {
  title: "Mis trámites",
  sub: "Las cartas con las que le estamos ayudando.",
  empty: "Todavía no hay cartas. Mande una foto de una carta por WhatsApp para empezar.",
  received: (when: string) => `Recibida ${when}`,
  appointment: "Cita",
  respondBy: "Responda antes del",
  onHold: "en espera",
  scam: "Probable estafa",
  scamSub: "No pague ni llame a los números de la carta. Ábrala para ver por qué.",
  open: "Abrir",
};
