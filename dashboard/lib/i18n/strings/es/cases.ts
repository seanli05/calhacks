import type { CasesStrings } from "../en/cases";

export const casesPage: CasesStrings = {
  title: "Mis trámites",
  sub: "Las cartas con las que te estamos ayudando.",
  empty: "Todavía no hay cartas. Manda una foto de una carta por WhatsApp para empezar.",
  received: (when: string) => `Recibida ${when}`,
  appointment: "Cita",
  respondBy: "Responde antes del",
  onHold: "en espera",
  scam: "Probable estafa",
  scamSub: "No pagues ni llames a los números de la carta. Abre para ver por qué.",
  open: "Abrir",
};
