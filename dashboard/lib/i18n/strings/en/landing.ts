/** Landing page (/). Owned by the landing agent; extend freely. */
export const landing = {
  headline: ["Hi, I'm Avocado.", "Documents, made easy."],
  sub: "Navigating the early stages of life, and all the forms, in a new country is difficult. With Avocado, you can chat on WhatsApp in your native language, send forms that are confusing at first, and have representatives called for you. All done in your native language!",
  tryIt: "Try it on WhatsApp",
  watch: "See an example",
  scan: "On a computer? Scan this with your phone.",
  thenSend: "The message is already written. Just press send:",
  /** Quiet reassurances under the buttons. */
  perks: ["No new app: it's on WhatsApp", "Español · English · دری", "Nothing happens without your OK"],
  loading: "Getting ready…",

  /** The WhatsApp chat in the hero. Scripted, not live data. */
  chat: {
    name: "Avocado",
    status: "Replies in about a minute",
    user: "Can you help me with this letter?",
    explain: "This is your asylum interview notice. It's on Thursday, November 12, at 9:00 AM. Bring your passport and an interpreter.",
    real: "This letter is real. We checked it on uscis.gov.",
    ask: "Want us to call USCIS for you? We'll wait on hold and ring you when a person answers.",
    yes: "Yes, please",
    calling: "Great. We're calling USCIS now. We'll ring you when a person picks up.",
    typing: "typing",
  },

  /** Three steps in place of the ticker and bento. */
  steps: {
    says: ["Got it! Let me take a look.", "It's real. Here's what it means.", "I'll ring you when someone picks up."],
    sub: "Three steps. You only do the first one.",
    title: "How it works",
    items: [
      { title: "Send a photo", body: "Take a picture of the letter and send it to us on WhatsApp." },
      { title: "We explain and check it", body: "What it says, the date, what to bring, and whether it's real." },
      { title: "We call for you", body: "If you say yes, we wait on hold and ring you when a person picks up." },
    ],
  },

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
      rest: " See what's saved. Remove anything.",
      facts: ["Prefers Spanish", "Has two children", "Interview on Nov 12", "Needs an interpreter", "Asked to be called after 5 PM"],
      deleteAll: "Clear my profile",
      delete: "Remove",
      deleted: "(removed)",
      cta: "See your profile",
    },
  },

  promises: {
    title: "Our promise to you",
    greeting: "Hi there,",
    sub: "You're always the one in charge. Avocado keeps these promises on every letter and every call.",
    signoff: "With care,",
    items: [
      { title: "We only dial official numbers", body: "The number we call always comes from the office's own website, never from the letter." },
      { title: "You speak for yourself", body: "We never say your A-Number, receipt number or birth date. You answer those." },
      { title: "We ask before every call", body: "Nothing happens until you say yes." },
      { title: "Delete anything, anytime", body: "See what we remember about you, and remove one thing or everything." },
    ],
  },

  /** The "See an example" tour: snapshots of a real case, playing on their own. */
  example: {
    back: "Back to home",
    title: "See how Avocado helps",
    sub: "One letter, from photo to phone call. It plays by itself.",
    pause: "Pause",
    play: "Play",
    prev: "Previous",
    next: "Next",
    step: (n: number, total: number) => `Step ${n} of ${total}`,
    alt: "Avocado's page for this letter",
    done: "Ready to try it with your own letter?",
    slides: [
      { title: "Your letter, explained", body: "Avocado reads the letter, explains it in your language, and checks that it's real on the official website. Then it asks if you'd like a call." },
      { title: "You say yes, Avocado calls", body: "With your OK, Avocado calls the official number and gets through the phone menu for you." },
      { title: "Avocado waits on hold", body: "You don't have to wait by the phone. You can see what's happening, live." },
      { title: "Your phone rings", body: "When a person answers, Avocado rings you to join, and translates what they say, live." },
      { title: "You get a summary", body: "After the call, you get what was said and your next steps, in your language." },
    ],
  },

  closing: {
    title: ["Got a letter?", "Send us a photo."],
    sub: "One photo is all it takes. In Spanish, English or Dari.",
  },
};

export type LandingStrings = typeof landing;
