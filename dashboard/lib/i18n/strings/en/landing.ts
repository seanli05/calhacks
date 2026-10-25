/** Landing page (/). Owned by the landing agent; extend freely. */
export const landing = {
  headline: ["Your letter, explained.", "Your call, made."],
  sub: "We read immigration letters in your language, check they're real, and wait on hold with the agency for you.",
  tryIt: "Try it on WhatsApp",
  watch: "Watch a live call",
  scan: "Or scan with your phone",
  thenSend: "The message is already written. Just press send:",

  /** The looping call in the hero. Scripted, not live data. */
  demo: {
    live: "Call in progress",
    agency: "USCIS",
    onHold: "on hold",
    dialing: "Calling USCIS",
    menu: "Getting through the phone menu",
    hold: "We're on hold with USCIS",
    human: "A person answered",
    humanSub: "We're calling you now to join.",
    feed: {
      verified: "We confirmed the official number on uscis.gov",
      dialing: "We called USCIS",
      menu: "We chose option 2 in the menu",
      hold: "We're on hold. You don't have to wait.",
      human: "A person answered. Calling you now.",
    },
    ago: (min: number) => (min === 0 ? "now" : `${min} min ago`),
  },

  /** The strip under the hero, like a spec sheet for every call. */
  ticker: {
    label: "On every call",
    items: [
      { k: "Number dialed", v: "verified on uscis.gov" },
      { k: "Phone menu", v: "we get through it" },
      { k: "Time on hold", v: "ours, not yours" },
      { k: "Your OK", v: "asked first, every time" },
      { k: "Your A-Number", v: "never said" },
      { k: "Languages", v: "Español · English · دری" },
    ],
  },

  bento: {
    title: ["Everything a letter asks of you.", "Handled on WhatsApp."],
    explain: {
      lead: "Your letter, explained",
      rest: " in your language: the date, the place, and what to bring.",
      docType: "Asylum interview notice",
      bubble: "This is your asylum interview: Thursday, November 12, at 9:00 AM. Bring your passport and an interpreter.",
      ask: "Want us to call USCIS for you?",
      yes: "Yes, please",
    },
    verify: {
      lead: "Checked against USCIS",
      rest: " before we trust a single line.",
      verdict: "This letter is real",
      checks: [
        "Form I-797C, current edition",
        "Every link is on uscis.gov",
        "Receipt number has the right format",
        "No demands for payment or gift cards",
        "No threats of arrest or deportation",
        "No \"notario\" offers",
      ],
      official: "Official number found on uscis.gov",
    },
    menu: {
      lead: "Phone menus,",
      rest: " handled. We press the right buttons.",
      prompt: "“To speak with a representative, press 2.”",
      options: [
        { key: "1", text: "Case status" },
        { key: "2", text: "Speak with a representative" },
        { key: "3", text: "Change of address" },
      ],
      chosen: 1,
    },
    hold: {
      lead: "We wait on hold.",
      rest: " You get on with your day.",
      onHold: "on hold",
    },
    ring: {
      lead: "Your phone rings",
      rest: " the moment a person picks up.",
      answered: "A person answered",
      calling: "Calling you now",
      cta: "Watch a live call",
    },
    prep: {
      lead: "Ready for the interview.",
      rest: " Key English words and what to bring.",
      days: "days until your interview",
      words: [
        { term: "interpreter", meaning: "someone who translates for you" },
        { term: "receipt notice", meaning: "the letter that proves we got your form" },
      ],
      checklist: ["Bring your passport", "Bring an interpreter", "Your spouse and children must come"],
    },
    memory: {
      lead: "Your data, your call.",
      rest: " See what we know. Delete anything.",
      facts: ["Prefers Spanish", "Has two children", "Interview on Nov 12", "Needs an interpreter", "Asked to be called after 5 PM"],
      deleteAll: "Delete everything",
      delete: "Delete",
      deleted: "(deleted)",
      cta: "What we know about you",
    },
  },

  promises: {
    title: "What we'll never do.",
    sub: "These are rules in our code, not settings.",
    items: [
      { title: "Dial a number we haven't checked", body: "Only the official number, found on the agency's own site." },
      { title: "Speak for you", body: "We never say your A-Number, receipt number or birth date. You answer for yourself." },
      { title: "Call without your OK", body: "We ask before every call and keep your answer." },
      { title: "Keep what you delete", body: "Delete anything, or everything, any time." },
    ],
  },

  closing: {
    title: ["Got a letter?", "Send us a photo."],
    sub: "All it takes is one photo. Spanish, English and Dari today.",
  },
};

export type LandingStrings = typeof landing;
