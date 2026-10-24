/** My cases (/u/[userId]). Owned by the My-cases agent; extend freely. */
export const casesPage = {
  title: "My cases",
  sub: "Letters we're helping you with.",
  history: "History",
  historyEmpty: "Nothing here yet.",
  empty: "No letters yet. Send a photo of a letter on WhatsApp to start.",
  received: (when: string) => `Received ${when}`,
  appointment: "Appointment",
  onHold: "on hold",
  open: "Open",
};

export type CasesStrings = typeof casesPage;
