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

  features: {
    explain: {
      kicker: "1 · Send a photo",
      title: "Every letter, in words you know.",
      body: "Send a photo of your letter on WhatsApp. We tell you what it is, what you need to do, and by when, in your language.",
      docType: "Asylum interview notice",
      bubble: "This is your asylum interview. It's on Thursday, November 12, at 9:00 AM. Bring your passport and an interpreter.",
    },
    verify: {
      kicker: "2 · We check it's real",
      title: "Scams copy real letters. We check.",
      body: "We compare the letter with official sources. When we call, we use the number from the agency's own website, never the one printed on the letter.",
      real: "This letter is real",
      official: "Official number, from uscis.gov",
      officialNote: "We call this one",
      printed: "Number printed on the letter",
      printedNote: "Never dialed",
    },
    hold: {
      kicker: "3 · We wait on hold",
      title: "Hours on hold. Not yours.",
      body: "We call the agency, get through the menu, and wait. When a real person picks up, your phone rings and you join the call.",
      waited: "We waited",
      answered: "A person answered",
      ringing: "Your phone is ringing",
    },
  },

  promises: {
    title: "What we'll never do.",
    items: [
      { title: "Call a number from your letter", body: "Only the official number from the agency's own site." },
      { title: "Speak for you", body: "When they ask who you are, you answer. Not us." },
      { title: "Call without your OK", body: "We ask first, every time, and keep your answer." },
      { title: "Keep what you want gone", body: "See everything we know about you. Delete it in one tap." },
    ],
  },

  closing: {
    title: ["Got a letter?", "Send us a photo."],
    sub: "All it takes is one photo. Spanish and English today.",
  },
};

export type LandingStrings = typeof landing;
