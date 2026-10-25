import type { CommonStrings } from "../en/common";

/** Afghan Dari, following the register in `backend/app/translation/translate.py`. */
export const common: CommonStrings = {
  appName: "[App]",
  nav: {
    cases: "دوسیه‌های من",
    memory: "معلوماتی که از شما داریم",
    back: "→ دوسیه‌های من",
  },
  languageSwitch: "زبان",
  docTypes: {
    uscis_i797c_asylum_interview: "مصاحبهٔ پناهندگی",
  } as Record<string, string>,
  docTypeFallback: "نامه",
  stages: {
    received: "نامه رسید",
    explaining: "نامهٔ شما را می‌خوانیم",
    needs_better_image: "عکس واضح‌تر ضرورت است",
    needs_answer: "یک جواب ضرورت است",
    checking: "بررسی اصلی بودن نامه",
    suspicious: "شاید اصلی نباشد",
    unknown: "تأیید نشد",
    awaiting_consent: "منتظر اجازهٔ شما",
    calling: "در حال تماس",
    on_hold: "در انتظار",
    connected: "صحبت با یک شخص",
    call_ended: "تماس ختم شد",
    closed: "بسته شد",
  },
  trackerSteps: ["نامه", "تأیید شد", "تماس", "در انتظار", "شخص"],
  assistant: {
    title: "دستیار",
    viaWhatsApp: "از طریق واتس‌اپ",
    placeholder: "هر سوالی دارید بپرسید…",
    send: "باز کردن در واتس‌اپ",
    you: "شما",
  },
  deleted: (date: string) => `(در ${date} پاک شد)`,
  loading: "در حال بارگذاری…",
  loadError: "به سرور وصل نمی‌شود. دوباره کوشش می‌کنیم…",
  notFound: "آن را پیدا نکردیم.",
};
