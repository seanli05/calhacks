import type { FactSource } from "@/lib/api/types";

/** What we know about you (/u/[userId]/memory). Owned by the memory-page agent; extend freely. */
export const memoryPage = {
  title: "What we know about you",
  subtitle: "You can delete anything, any time.",
  sections: {
    profile: "Profile",
    facts: "Facts",
    documents: "Letters",
    calls: "Calls",
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
    user_said: "You told us",
    from_document: "From your letter",
    from_call: "From the call",
    inferred: "We guessed this",
  } satisfies Record<FactSource, string>,
  sensitive: "Sensitive",
  pendingConsent: "Waiting for your OK",
  saved: (when: string) => `Saved ${when}`,
  received: (when: string) => `Received ${when}`,
  pages: (n: number) => (n === 1 ? "1 page" : `${n} pages`),
  transcript: (date: string) => `Transcript of the call on ${date}`,
  empty: {
    profile: "Nothing saved.",
    facts: "No facts saved.",
    documents: "No letters saved.",
    calls: "No call transcripts yet.",
  },
  delete: "Delete",
  deleteFailed: "That didn't delete. Try again.",
  deleteEverything: "Delete everything",
  confirm: {
    title: "Delete everything we know about you?",
    body: "This deletes your profile, facts, letters, call transcripts and WhatsApp messages. It can't be undone.",
    cancel: "Keep my data",
    yes: "Yes, delete everything",
  },
  deleting: "Deleting…",
  allDeleted: "Everything is deleted. We don't keep anything about you.",
  nothingSaved: "We don't have anything saved about you.",
  history: "What you deleted",
};

export type MemoryStrings = typeof memoryPage;
