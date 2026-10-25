import type { FactSource } from "@/lib/api/types";

/** Profile page (/u/[userId]/memory). Owned by the memory-page agent; extend freely. */
export const memoryPage = {
  title: "Profile",
  subtitle: "This is what Avocado saves to help with your case. You can remove anything, any time.",
  /** Between items on one line (summary, "where it came from · when"). */
  separator: " · ",
  /** Counts in the summary line under the title; zero counts are left out. */
  counts: {
    facts: (n: number) => (n === 1 ? "1 thing you've shared" : `${n} things you've shared`),
    documents: (n: number) => (n === 1 ? "1 letter" : `${n} letters`),
    calls: (n: number) => (n === 1 ? "1 call" : `${n} calls`),
  },
  sections: {
    profile: "About you",
    facts: "Things you've shared",
    documents: "Your letters",
    calls: "Your calls",
  },
  /** Labels for profile keys; unknown keys show as-is. */
  profileFields: {
    name: "Name",
    language: "Language",
    city: "City",
    county: "County",
    household_size: "People in your home",
    contact_preference: "Best way to reach you",
  } as Record<string, string>,
  sources: {
    user_said: "You shared this",
    from_document: "From your letter",
    from_call: "From a call",
    inferred: "Not confirmed yet",
  } satisfies Record<FactSource, string>,
  sensitive: "Private",
  pendingConsent: "Needs your OK",
  saved: (when: string) => `Saved ${when}`,
  received: (when: string) => `Received ${when}`,
  pages: (n: number) => (n === 1 ? "1 page" : `${n} pages`),
  transcript: (date: string) => `Call on ${date}`,
  empty: {
    profile: "Your name, language and city show up here once you share them.",
    facts: "Things you tell Avocado on WhatsApp show up here.",
    documents: "Letters you send a photo of show up here.",
    calls: "Calls Avocado makes for you show up here.",
  },
  delete: "Remove",
  removeItem: (what: string) => `Remove: ${what}`,
  deleteFailed: "That didn't go through. Try again.",
  deleteEverything: "Clear my profile",
  privacy: {
    title: "Privacy",
    note: "You decide what Avocado keeps. Clearing your profile removes everything on this page.",
  },
  confirm: {
    title: "Clear your whole profile?",
    body: "This removes everything saved: your details, letters, call notes and WhatsApp messages. You can't undo this.",
    cancel: "Keep it",
    yes: "Yes, clear it",
  },
  deleting: "Clearing…",
  allDeleted: "Your profile is cleared.",
  nothingSaved: "Nothing saved yet. As you share things with Avocado, they'll show up here.",
  history: "Recently removed",
};

export type MemoryStrings = typeof memoryPage;
