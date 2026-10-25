import type { FactSource } from "@/lib/api/types";

/** Profile page (/u/[userId]/memory). Owned by the memory-page agent; extend freely. */
export const memoryPage = {
  title: "Profile",
  subtitle: "This is what Avocado saves to help with your case. You can remove anything, any time.",
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
    profile: "Nothing here yet.",
    facts: "Nothing here yet.",
    documents: "Nothing here yet.",
    calls: "Nothing here yet.",
  },
  delete: "Remove",
  deleteFailed: "That didn't go through. Try again.",
  deleteEverything: "Clear my profile",
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
