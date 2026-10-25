import type { CaseStrings } from "../en/case";

const n = (count: number) => count.toLocaleString("fa-AF");

export const caseView: CaseStrings = {
  yourLetter: "نامهٔ شما",
  stamp: "تأیید شد",
  when: "چه وقت",
  where: "کجا",
  kinds: { who_must_come: "ضروری", bring: "با خود بیاورید", deadline: "آخرین مهلت" },
  agencyFallback: "اداره",
  refs: { receipt_number: "رسید", a_number: "A-Number" } as Record<string, string>,
  verdict: {
    verified: "این نامه اصلی است",
    suspicious: "شاید این نامه اصلی نباشد",
    unknown: "نتوانستیم این نامه را تأیید کنیم",
    pending: "نامه را بررسی می‌کنیم",
  },
  officialSource: (domain: string) =>
    `ما به شمارهٔ رسمی از ${domain} زنگ می‌زنیم، هرگز به شماره‌ای که روی نامه است`,
  liveCall: "تماس جریان دارد",
  onHold: "در انتظار",
  hero: {
    received: { title: "نامهٔ شما رسید", sub: "چند لحظه بعد آن را برای شما توضیح می‌دهیم." },
    explaining: {
      title: "نامهٔ شما را می‌خوانیم",
      sub: "توضیح را در واتس‌اپ برای شما می‌فرستیم.",
    },
    needs_better_image: {
      title: "یک عکس واضح‌تر ضرورت است",
      sub: "در روشنی خوب، از تمام صفحه یک عکس دیگر در واتس‌اپ بفرستید.",
    },
    needs_answer: {
      title: "یک جواب از شما ضرورت است",
      sub: "واتس‌اپ را ببینید: دربارهٔ نامهٔ شما یک سوال پرسیدیم.",
    },
    checking: {
      title: "بررسی می‌کنیم که نامه اصلی است",
      sub: "پیش از تماس با کسی، آن را با معلومات رسمی مقایسه می‌کنیم.",
    },
    suspicious: {
      title: "شاید این نامه اصلی نباشد",
      sub: "به شماره‌های روی آن زنگ نزنید و پول نفرستید. دلیلش را در واتس‌اپ می‌گوییم.",
    },
    unknown: {
      title: "نتوانستیم این نامه را تأیید کنیم",
      sub: "تا مطمئن نشویم به کسی زنگ نمی‌زنیم. در واتس‌اپ می‌گوییم چه کار کنید.",
    },
    awaiting_consent: {
      title: (agency: string) => `آیا به جای شما به ${agency} زنگ بزنیم؟`,
      sub: "در واتس‌اپ «بلی» بنویسید. این‌ها را می‌پرسیم:",
    },
    dialing: {
      title: (agency: string) => `به ${agency} زنگ می‌زنیم`,
      sub: "به شمارهٔ رسمی زنگ زدیم. وقتی کسی جواب بدهد، به شما خبر می‌دهیم.",
    },
    menu: {
      title: (agency: string) => `به ${agency} زنگ می‌زنیم`,
      sub: "از مینوی تیلفون می‌گذریم.",
    },
    on_hold: {
      title: (agency: string) => `با ${agency} در انتظار هستیم`,
      sub: "وقتی یک شخص جواب بدهد، به شما زنگ می‌زنیم. به کارهای خود برسید.",
    },
    human: {
      title: "یک شخص جواب داد",
      sub: "حالا به شما زنگ می‌زنیم تا وصل شوید.",
    },
    connected: {
      title: (agency: string) => `شما با ${agency} صحبت می‌کنید`,
      sub: "حالا می‌توانید با کارمند صحبت کنید.",
    },
    call_ended: { title: (agency: string) => `با ${agency} صحبت کردیم` },
    call_failed: {
      title: (agency: string) => `نتوانستیم با یک شخص در ${agency} صحبت کنیم`,
      sub: "هر وقت بخواهید دوباره کوشش می‌کنیم. فقط در واتس‌اپ بگویید.",
    },
    call_cancelled: {
      title: "شما تماس را ختم کردید",
      sub: "هر وقت بخواهید دوباره زنگ می‌زنیم. فقط در واتس‌اپ بگویید.",
    },
    call_unreachable: {
      title: "نتوانستیم با شما تماس بگیریم",
      sub: "یک شخص جواب داد، اما تیلفون شما جواب نداد. می‌توانیم دوباره کوشش کنیم.",
    },
    closed: { title: "این دوسیه بسته شد", sub: "همه چیز در سابقهٔ شما می‌ماند." },
  },
  outcome: {
    resolved: "حل شد",
    partial: "تا اندازه‌ای حل شد",
    failed: "حل نشد",
    user_unreachable: "نتوانستیم با شما تماس بگیریم",
    cancelled: "شما ختم کردید",
  },
  reference: (ref: string) => `شمارهٔ مرجع: ${ref}`,
  viewTranscript: "دیدن متن تماس",
  transcript: "متن تماس",
  transcriptNote: "تماس به انگلیسی بود. ما صدا را نگه نمی‌داریم.",
  speakers: { agent: "Avocado", agency: "اداره", user: "شما" },
  live: {
    title: "ترجمهٔ زنده",
    waiting: "گوش می‌دهیم. آنچه شما و کارمند می‌گویید، این‌جا به زبان شما نشان داده می‌شود.",
    tipsTitle: "چه می‌توانید بگویید",
    ask: "می‌توانید بپرسید",
    yourself: "این را خودتان جواب بدهید",
    used: "گفتید",
    book: "کتاب ترجمه",
    search: "یک کلمه را جستجو کنید: interpreter، ترجمان…",
    searchLabel: "جستجو در کتاب ترجمه",
    fromCall: "کلمه‌های این تماس",
    none: "هنوز چنین کلمه‌ای در کتاب نیست",
    resize: "برای تغییر اندازهٔ کتاب ترجمه بکشید",
    details: "جزئیات",
    hide: "پنهان کردن",
    onCall: "در تماس",
    trust: { official: "رسمی", community: "جامعه", machine: "ماشینی" },
  },
  activity: {
    title: "فعالیت",
    working: "حالا کار می‌کنیم",
    steps: (count: number) => `${n(count)} قدم`,
    show: "دیدن قدم‌ها",
    hide: "پنهان کردن قدم‌ها",
    why: "چرا",
    showWhy: "دیدن دلیل‌ها",
    hideWhy: "پنهان کردن دلیل‌ها",
  },
  close: "بستن",
};
