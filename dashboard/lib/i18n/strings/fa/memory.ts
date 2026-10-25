import type { MemoryStrings } from "../en/memory";

const n = (count: number) => count.toLocaleString("fa-AF");

export const memoryPage: MemoryStrings = {
  title: "معلوماتی که از شما داریم",
  subtitle: "هر وقت بخواهید، هر چیزی را می‌توانید پاک کنید.",
  sections: {
    profile: "پروفایل",
    facts: "معلومات",
    documents: "نامه‌ها",
    calls: "تماس‌ها",
  },
  profileFields: {
    name: "نام",
    language: "زبان",
    city: "شهر",
    county: "ولسوالی (County)",
    household_size: "تعداد اعضای خانواده",
  } as Record<string, string>,
  sources: {
    user_said: "خودتان گفتید",
    from_document: "از نامهٔ شما",
    from_call: "از تماس",
    inferred: "ما حدس زدیم",
  },
  sensitive: "حساس",
  pendingConsent: "منتظر اجازهٔ شما",
  saved: (when: string) => `ذخیره شد ${when}`,
  received: (when: string) => `رسید ${when}`,
  pages: (count: number) => `${n(count)} صفحه`,
  transcript: (date: string) => `متن تماس در ${date}`,
  empty: {
    profile: "چیزی ذخیره نشده.",
    facts: "معلوماتی ذخیره نشده.",
    documents: "نامه‌ای ذخیره نشده.",
    calls: "هنوز متن تماسی نیست.",
  },
  delete: "پاک کردن",
  deleteFailed: "پاک نشد. دوباره کوشش کنید.",
  deleteEverything: "همه چیز را پاک کنید",
  confirm: {
    title: "همهٔ معلوماتی که از شما داریم پاک شود؟",
    body: "این کار پروفایل، معلومات، نامه‌ها، متن تماس‌ها و پیام‌های واتس‌اپ شما را پاک می‌کند. دوباره برگردانده نمی‌شود.",
    cancel: "معلوماتم بماند",
    yes: "بلی، همه چیز پاک شود",
  },
  deleting: "در حال پاک کردن…",
  allDeleted: "همه چیز پاک شد. ما هیچ معلوماتی از شما نگه نمی‌داریم.",
  nothingSaved: "ما هیچ معلوماتی از شما ذخیره نکرده‌ایم.",
  history: "چیزهایی که پاک کردید",
};
