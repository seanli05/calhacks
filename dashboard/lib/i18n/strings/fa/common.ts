import type { CommonStrings } from "../en/common";

/**
 * Afghan Dari, in the register of `REGISTERS["fa"]` in
 * `backend/app/translation/translate.py` and the WhatsApp templates: دوسیه, تیلفون,
 * معلومات, ضرورت, «ادارهٔ USCIS», "on hold" as پشت خط منتظر, Persian digits.
 */
export const common: CommonStrings = {
  appName: "Avocado",
  nav: {
    cases: "دوسیه‌های من",
    memory: "پروفایل",
    back: "→ دوسیه‌های من",
  },
  languageSwitch: "زبان",
  docTypes: {
    uscis_i797c_asylum_interview: "مصاحبهٔ پناهندگی",
    medi_cal_renewal: "تمدید Medi-Cal",
    ice_ar11_violation: "اطلاعیهٔ تخلف آدرس",
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
    verified: "نامه تأیید شد",
    awaiting_consent: "منتظر اجازهٔ شما",
    calling: "در حال تماس",
    on_hold: "پشت خط منتظر",
    connected: "در حال صحبت با یک شخص",
    call_ended: "تماس ختم شد",
    closed: "بسته شد",
  },
  trackerSteps: ["نامه", "تأیید شد", "تماس", "پشت خط", "شخص"],
  assistant: {
    title: "دستیار",
    viaWhatsApp: "از طریق واتس‌اپ",
    placeholder: "هر سوالی دارید بپرسید…",
    send: "باز کردن در واتس‌اپ",
    you: "شما",
  },
  deleted: (date: string) => `(در ${date} پاک شد)`,
  quote: (text: string) => `«${text}»`,
  loading: "در حال بارگذاری…",
  loadError: "به سرور وصل نمی‌شود. دوباره کوشش می‌کنیم…",
  notFound: "آن را پیدا نکردیم.",
};
