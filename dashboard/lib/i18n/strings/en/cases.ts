/** My cases (/u/[userId]). Owned by the My-cases agent; extend freely. */
export const casesPage = {
  title: "My cases",
  sub: "Letters we're helping you with.",
  empty: "No letters yet. Send a photo of a letter on WhatsApp to start.",
  received: (when: string) => `Received ${when}`,
  appointment: "Appointment",
  respondBy: "Respond by",
  onHold: "on hold",
  scam: "Likely a scam",
  scamSub: "Don't pay or call the numbers on it. Open to see why.",
  open: "Open",
};

export type CasesStrings = typeof casesPage;
