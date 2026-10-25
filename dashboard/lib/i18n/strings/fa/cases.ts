import type { CasesStrings } from "../en/cases";

export const casesPage: CasesStrings = {
  title: "دوسیه‌های من",
  sub: "نامه‌هایی که در آن‌ها به شما کمک می‌کنیم.",
  empty: "هنوز نامه‌ای نیست. برای شروع، عکس یک نامه را در واتس‌اپ بفرستید.",
  received: (when: string) => `رسید ${when}`,
  appointment: "وقت ملاقات",
  onHold: "در انتظار",
  scam: "احتمالاً کلاهبرداری",
  scamSub: "پول ندهید و به شماره‌های روی نامه زنگ نزنید. برای دیدن دلیل باز کنید.",
  open: "باز کردن",
};
