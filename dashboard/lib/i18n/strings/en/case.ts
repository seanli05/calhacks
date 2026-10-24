/** The live case view (/u/[userId]/cases/[caseId]). */
export const caseView = {
  yourLetter: "Your letter",
  stamp: "Verified",
  when: "When",
  where: "Where",
  kinds: { who_must_come: "Required", bring: "Bring", deadline: "Deadline" },
  agencyFallback: "the agency",
  refs: { receipt_number: "Receipt", a_number: "A-Number" } as Record<string, string>,
  verdict: {
    verified: "This letter is real",
    suspicious: "This letter might not be real",
    unknown: "We couldn't confirm this letter",
    pending: "Checking the letter",
  },
  officialSource: (domain: string) =>
    `We call the official number from ${domain}, never the one on the letter`,
  liveCall: "Call in progress",
  onHold: "on hold",
  hero: {
    received: { title: "We got your letter", sub: "We'll explain it in a moment." },
    explaining: {
      title: "Reading your letter",
      sub: "We'll send you the explanation on WhatsApp.",
    },
    needs_better_image: {
      title: "We need a clearer photo",
      sub: "Send another photo on WhatsApp, in good light, with the whole page.",
    },
    needs_answer: {
      title: "We need one answer from you",
      sub: "Check WhatsApp: we asked you a question about your letter.",
    },
    checking: {
      title: "Checking the letter is real",
      sub: "We compare it with official sources before calling anyone.",
    },
    suspicious: {
      title: "This letter might not be real",
      sub: "Don't call the numbers on it or send money. We'll explain why on WhatsApp.",
    },
    unknown: {
      title: "We couldn't confirm this letter",
      sub: "We won't call anyone until we're sure. We'll tell you what to do on WhatsApp.",
    },
    awaiting_consent: {
      title: (agency: string) => `Should we call ${agency} for you?`,
      sub: "Reply YES on WhatsApp. This is what we'll ask:",
    },
    dialing: {
      title: (agency: string) => `We're calling ${agency}`,
      sub: "We dialed the official number. We'll tell you when someone answers.",
    },
    menu: {
      title: (agency: string) => `We're calling ${agency}`,
      sub: "We're going through the phone menu.",
    },
    on_hold: {
      title: (agency: string) => `We're on hold with ${agency}`,
      sub: "We'll ring you when a person answers. Go on with your day.",
    },
    human: {
      title: "A person answered",
      sub: "We're calling you now to connect you.",
    },
    connected: {
      title: (agency: string) => `You're talking with ${agency}`,
      sub: "You can talk with the officer now.",
    },
    call_ended: { title: (agency: string) => `We spoke with ${agency}` },
    call_failed: {
      title: (agency: string) => `We couldn't reach a person at ${agency}`,
      sub: "We can try again whenever you want. Just say so on WhatsApp.",
    },
    call_unreachable: {
      title: "We couldn't reach you",
      sub: "A person answered, but your phone didn't pick up. We can try again.",
    },
    closed: { title: "This case is closed", sub: "Everything stays in your history." },
  },
  outcome: {
    resolved: "Resolved",
    partial: "Partly resolved",
    failed: "Not resolved",
    user_unreachable: "We couldn't reach you",
  },
  reference: (n: string) => `Reference number: ${n}`,
  viewTranscript: "View transcript",
  transcript: "Transcript",
  transcriptNote: "The call was in English. We don't keep the audio.",
  speakers: { agent: "[App]", agency: "Agency", user: "You" },
  live: {
    title: "Live translation",
    waiting: "Listening. What you and the officer say shows up here in your language.",
    tipsTitle: "What you can say",
    ask: "You could ask",
    yourself: "Answer this yourself",
    used: "You said it",
    book: "Translation book",
    search: "Search a word: interpreter, cita…",
    searchLabel: "Search the translation book",
    fromCall: "Words from this call",
    none: "No word like that in the book yet",
    trust: { official: "Official", community: "Community", machine: "Machine" },
  },
  close: "Close",
};

export type CaseStrings = typeof caseView;
