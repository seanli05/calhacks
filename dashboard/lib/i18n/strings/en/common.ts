/** Labels shared by every page. The English file defines the shape; every other
 * language mirrors it (`CommonStrings`). */
export const common = {
  appName: "Avocado",
  nav: {
    cases: "My cases",
    memory: "Profile",
    back: "← My cases",
  },
  languageSwitch: "Language",
  docTypes: {
    uscis_i797c_asylum_interview: "Asylum interview",
    medi_cal_renewal: "Medi-Cal renewal",
    ice_ar11_violation: "Address violation notice",
  } as Record<string, string>,
  docTypeFallback: "Letter",
  stages: {
    received: "Letter received",
    explaining: "Reading your letter",
    needs_better_image: "Needs a clearer photo",
    needs_answer: "Needs one answer",
    checking: "Checking it's real",
    suspicious: "Might not be real",
    unknown: "Couldn't confirm",
    verified: "Letter is real",
    awaiting_consent: "Waiting for your OK",
    calling: "Calling",
    on_hold: "On hold",
    connected: "Talking to a person",
    call_ended: "Call ended",
    closed: "Closed",
  },
  trackerSteps: ["Letter", "Verified", "Calling", "On hold", "Person"],
  assistant: {
    title: "Assistant",
    viaWhatsApp: "via WhatsApp",
    placeholder: "Ask anything…",
    send: "Open in WhatsApp",
    you: "You",
  },
  deleted: (date: string) => `(deleted ${date})`,
  loading: "Loading…",
  loadError: "Can't reach the server. Retrying…",
  notFound: "We couldn't find that.",
};

export type CommonStrings = typeof common;
