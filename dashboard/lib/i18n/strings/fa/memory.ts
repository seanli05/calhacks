import type { MemoryStrings } from "../en/memory";

const n = (count: number) => count.toLocaleString("fa-AF");

export const memoryPage: MemoryStrings = {
  title: "پروفایل",
  subtitle: "این‌ها چیزهایی است که Avocado برای کمک به قضیهٔ شما ذخیره می‌کند. هر وقت بخواهید، هر چیزی را می‌توانید حذف کنید.",
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
  } as Record<string, string>,
  sources: {
    user_said: "خودتان گفتید",
    from_document: "از نامهٔ شما",
    from_call: "از یک تماس",
    inferred: "هنوز تأیید نشده",
  },
  sensitive: "خصوصی",
  pendingConsent: "به اجازهٔ شما ضرورت دارد",
  saved: (when: string) => `ذخیره شد ${when}`,
  received: (when: string) => `رسید ${when}`,
  pages: (count: number) => `${n(count)} صفحه`,
  transcript: (date: string) => `تماس در ${date}`,
  empty: {
    profile: "نام، زبان و شهر شما وقتی آن‌ها را بگویید اینجا نشان داده می‌شود.",
    facts: "چیزهایی که در واتس‌اپ به Avocado می‌گویید اینجا نشان داده می‌شود.",
    documents: "نامه‌هایی که عکس آن‌ها را می‌فرستید اینجا نشان داده می‌شود.",
    calls: "تماس‌هایی که Avocado برای شما می‌گیرد اینجا نشان داده می‌شود.",
  },
  delete: "حذف",
  removeItem: (what: string) => `حذف: ${what}`,
  deleteFailed: "انجام نشد. دوباره کوشش کنید.",
  deleteEverything: "پاک کردن پروفایل من",
  privacy: {
    title: "حریم خصوصی",
    note: "شما تصمیم می‌گیرید Avocado چه چیزی را نگه دارد. با پاک کردن پروفایل، همه چیزهای این صفحه حذف می‌شود.",
  },
  confirm: {
    title: "تمام پروفایل شما پاک شود؟",
    body: "این کار همه چیزهای ذخیره‌شده را پاک می‌کند: معلومات شما، نامه‌ها، یادداشت‌های تماس و پیام‌های واتس‌اپ. دوباره برگردانده نمی‌شود.",
    cancel: "بماند",
    yes: "بلی، پاک شود",
  },
  deleting: "در حال پاک کردن…",
  allDeleted: "پروفایل شما پاک شد.",
  nothingSaved: "هنوز چیزی ذخیره نشده. هر چیزی که با Avocado شریک بسازید، اینجا نشان داده می‌شود.",
  history: "به تازگی حذف شده",
};
