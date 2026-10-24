import type { CasesStrings } from "../en/cases";

export const casesPage: CasesStrings = {
  title: "Mis trámites",
  sub: "Las cartas con las que te estamos ayudando.",
  history: "Historial",
  historyEmpty: "Todavía no hay nada.",
  empty: "Todavía no hay cartas. Manda una foto de una carta por WhatsApp para empezar.",
  received: (when: string) => `Recibida ${when}`,
  appointment: "Cita",
  onHold: "en espera",
  open: "Abrir",
};
