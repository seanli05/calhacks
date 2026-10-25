import type { MemoryStrings } from "../en/memory";

const n = (count: number) => count.toLocaleString("fa-AF");

/** "Save" is نگه داشتن and "remove" پاک کردن, as in the WhatsApp memory templates. */
export const memoryPage: MemoryStrings = {
  title: "پروفایل",
  subtitle: "این‌ها چیزهایی است که Avocado برای کمک به دوسیهٔ شما نگه می‌دارد. هر وقت بخواهید، می‌توانید هر کدام را پاک کنید.",
  separator: "، ",
  counts: {
    facts: (count: number) => `${n(count)} چیز که گفتید`,
    documents: (count: number) => `${n(count)} نامه`,
    calls: (count: number) => `${n(count)} تماس`,
  },
  sections: {
    profile: "دربارهٔ شما",
    facts: "چیزهایی که گفتید",
    documents: "نامه‌های شما",
    calls: "تماس‌های شما",
  },
  profileFields: {
    name: "نام",
    language: "زبان",
    city: "شهر",
    county: "ولسوالی (County)",
    household_size: "تعداد اعضای خانواده",
    contact_preference: "چطور با شما تماس بگیریم",
  } as Record<string, string>,
  sources: {
    user_said: "خودتان گفتید",
    from_document: "از نامهٔ شما",
    from_call: "از یک تماس",
    inferred: "هنوز تأیید نشده",
  },
  sensitive: "خصوصی",
  pendingConsent: "به اجازهٔ شما ضرورت دارد",
  saved: (when: string) => `${when} نگه داشته شد`,
  received: (when: string) => `${when} رسید`,
  pages: (count: number) => `${n(count)} صفحه`,
  transcript: (date: string) => `تماس ${date}`,
  empty: {
    profile: "وقتی نام، زبان و شهر خود را بگویید، این‌جا نشان داده می‌شود.",
    facts: "چیزهایی که در واتس‌اپ به Avocado می‌گویید، این‌جا نشان داده می‌شود.",
    documents: "نامه‌هایی که عکس آن‌ها را می‌فرستید، این‌جا نشان داده می‌شود.",
    calls: "تماس‌هایی که Avocado از طرف شما می‌گیرد، این‌جا نشان داده می‌شود.",
  },
  delete: "پاک کردن",
  removeItem: (what: string) => `پاک کردن: ${what}`,
  deleteFailed: "انجام نشد. دوباره کوشش کنید.",
  deleteEverything: "پاک کردن پروفایل من",
  privacy: {
    title: "حریم خصوصی",
    note: "شما تصمیم می‌گیرید Avocado چه چیزی را نگه دارد. با پاک کردن پروفایل، همه چیزهای این صفحه پاک می‌شود.",
  },
  confirm: {
    title: "تمام پروفایل شما پاک شود؟",
    body: "این کار همه چیزهای نگه داشته‌شده را پاک می‌کند: معلومات شما، نامه‌ها، یادداشت‌های تماس و پیام‌های واتس‌اپ. دوباره برگردانده نمی‌شود.",
    cancel: "نخیر، بماند",
    yes: "بلی، پاک شود",
  },
  deleting: "در حال پاک کردن…",
  allDeleted: "پروفایل شما پاک شد.",
  nothingSaved: "هنوز چیزی نگه داشته نشده. هر چیزی که به Avocado بگویید، این‌جا نشان داده می‌شود.",
  history: "تازه پاک شده",
};
