/** Landing page (/). Owned by the landing agent; extend freely. */
export const landing = {
  headline: ["Your letter, explained.", "Your call, made."],
  sub: "We read immigration letters in your language, check they're real, and wait on hold with the agency for you.",
  scan: "Scan to try it on WhatsApp",
  thenSend: "The message is already written. Just press send:",
  openOnPhone: "On this phone? Open WhatsApp",
  openDemo: "Open the live dashboard",
  stepsLabel: "How it works",
  steps: [
    { title: "Send a photo of your letter", body: "We explain it in your language, in plain words." },
    { title: "We check it's real", body: "Against official sources, never the number on the letter." },
    { title: "We call and ring you", body: "We wait on hold, then call you when a person picks up." },
  ],
  privacy: "You can see and delete everything we know about you, any time.",
};

export type LandingStrings = typeof landing;
