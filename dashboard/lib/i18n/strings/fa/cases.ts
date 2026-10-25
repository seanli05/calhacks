import type { CasesStrings } from "../en/cases";

export const casesPage: CasesStrings = {
  title: "دوسیه‌های من",
  sub: "نامه‌هایی که در آن‌ها به شما کمک می‌کنیم.",
  history: "سابقه",
  historyEmpty: "هنوز چیزی نیست.",
  empty: "هنوز نامه‌ای نیست. برای شروع، عکس یک نامه را در واتس‌اپ بفرستید.",
  received: (when: string) => `رسید ${when}`,
  appointment: "وقت ملاقات",
  onHold: "در انتظار",
  open: "باز کردن",
};
