/**
 * Afghan Dari for the fixtures' fake data, keyed by its English. Terms follow the
 * official Dari glossary (backend/app/glossary/terms.csv) so underlined words in the
 * live call match the translation book. All fictional, like the rest of the fixtures.
 */

const FA: Record<string, string> = {
  // Deletes
  "You deleted a fact": "یک معلومات را پاک کردید",
  "You deleted the letter": "نامه را پاک کردید",
  "You deleted a transcript": "متن یک تماس را پاک کردید",
  "You deleted everything": "همه چیز را پاک کردید",

  // Call reports
  "Officer Lee confirmed your interview and explained that you must bring your own interpreter.":
    "کارمند لی مصاحبهٔ شما را تأیید کرد و گفت که باید ترجمان خود را با خود بیاورید.",
  "Your interview is still on November 12 at 8:30 AM": "مصاحبهٔ شما هنوز هم در ۱۲ نومبر، ساعت ۸:۳۰ صبح است",
  "You must bring your own interpreter; USCIS doesn't provide one":
    "باید ترجمان خود را بیاورید؛ ادارهٔ USCIS ترجمان نمی‌دهد",
  "If your interpreter can't come, tell USCIS in writing before the appointment":
    "اگر ترجمان شما نتواند بیاید، پیش از وقت ملاقات به‌طور کتبی به USCIS خبر بدهید",
  "Agent Ruiz confirmed where to mail the evidence and that they can't give more time.":
    "کارمند رویز تأیید کرد که شواهد را به کجا بفرستید و گفت که وقت بیشتر داده نمی‌شود.",
  "Mail the evidence to the address printed on the letter, with the letter on top":
    "شواهد را به آدرسی که روی نامه چاپ شده بفرستید، و نامه را بالای همه بگذارید",
  "It has to arrive by December 4; they don't give extensions": "باید تا ۴ دسمبر برسد؛ مهلت را تمدید نمی‌کنند",
  "If a document is missing, send what you have and explain in writing why":
    "اگر یک سند کم است، آنچه دارید بفرستید و دلیلش را به‌طور کتبی بنویسید",

  // Request for Evidence letter
  "USCIS needs more evidence for your work permit. You have to mail it before December 4, or they may deny the application.":
    "ادارهٔ USCIS برای مجوز کار شما شواهد بیشتر می‌خواهد. باید آن را پیش از ۴ دسمبر از طریق پست بفرستید، ورنه ممکن است درخواست شما رد شود.",
  "Mail the requested evidence, with this letter on top":
    "شواهدی را که خواسته‌اند از طریق پست بفرستید، و این نامه را بالای همه بگذارید",
  "It must reach USCIS by December 4": "باید تا ۴ دسمبر به USCIS برسد",
  "A copy of your passport or ID": "کاپی پاسپورت یا سند هویت شما",
  "Proof of your entry to the U.S. (Form I-94)": "سند ورود شما به امریکا (فورم I-94)",
  "This letter, on top of everything you send": "همین نامه، بالای همه چیزهایی که می‌فرستید",
  "Confirm which address to mail the evidence to and whether a mailing receipt is enough":
    "تأیید کنیم که شواهد به کدام آدرس فرستاده شود و آیا رسید پستی کافی است",
  "Which address should the evidence go to?": "شواهد به کدام آدرس فرستاده شود؟",
  "Can I ask for more time if a document is missing?": "اگر یک سند کم باشد، می‌توانم وقت بیشتر بخواهم؟",

  // Scam letter
  "It asks you to pay a fine with gift cards. USCIS never takes gift cards.":
    "از شما می‌خواهد که جریمه را با کارت هدیه بپردازید. ادارهٔ USCIS هرگز کارت هدیه قبول نمی‌کند.",
  "The phone number on the letter isn't a USCIS number.": "شمارهٔ تیلفون روی نامه، شمارهٔ USCIS نیست.",
  "It threatens deportation within 48 hours if you don't pay.":
    "تهدید می‌کند که اگر پول ندهید، در ۴۸ ساعت اخراج (دیپورت) می‌شوید.",
  "The receipt number doesn't match the USCIS format.": "شماره رسید با شکل شماره‌های USCIS مطابقت ندارد.",

  // Asylum interview letter
  "This is your asylum interview appointment. You must go with your children and an interpreter.":
    "این وقت ملاقات برای مصاحبهٔ پناهندگی شماست. باید با اولادهای خود و یک ترجمان بروید.",
  "Attend asylum interview with dependents and a qualified interpreter":
    "با وابستگان خود و یک ترجمان واجد شرایط به مصاحبهٔ پناهندگی بروید",
  "All dependents listed on the I-589": "همهٔ وابستگانی که نام‌شان در فورم I-589 آمده",
  "A qualified interpreter if you are not fluent in English": "یک ترجمان واجد شرایط، اگر انگلیسی را روان صحبت نمی‌کنید",
  "ID for you and each dependent": "سند هویت برای خود شما و هر وابسته",
  "Confirm the asylum interview is still scheduled; ask what to do if the interpreter can't come":
    "تأیید کنیم که مصاحبهٔ پناهندگی هنوز سر وقت است؛ بپرسیم اگر ترجمان نتواند بیاید چه باید کرد",
  "Is the interview on November 12 at 8:30 AM still scheduled?":
    "آیا مصاحبهٔ ۱۲ نومبر، ساعت ۸:۳۰ صبح هنوز سر وقت است؟",
  "If the interpreter can't come, what should the applicant do before the interview?":
    "اگر ترجمان نتواند بیاید، متقاضی پیش از مصاحبه چه باید بکند؟",

  // Assistant suggestions
  "Your interview is in 20 days": "مصاحبهٔ شما ۲۰ روز بعد است",
  "Review what to bring": "ببینید چه با خود ببرید",
  Prepare: "آماده شوید",
  "Key English words": "کلمه‌های کلیدی انگلیسی",
  Practice: "تمرین",
  "Don't forget: an interpreter": "فراموش نکنید: یک ترجمان",
  "We can help": "کمک می‌کنیم",
  Ask: "بپرسید",

  // Activity
  "Heard the phone menu": "مینوی تیلفون را شنیدیم",
  "We received your letter": "نامهٔ شما را گرفتیم",
  "We explained the letter in your language": "نامه را به زبان شما توضیح دادیم",
  "Saved: you have two children on your application": "ذخیره شد: در درخواست شما دو اولاد هستند",
  "We're checking that the letter is real": "بررسی می‌کنیم که نامه اصلی است",
  "We confirmed the letter is real (uscis.gov)": "تأیید کردیم که نامه اصلی است (uscis.gov)",
  "We asked if you want us to call USCIS": "پرسیدیم که آیا می‌خواهید به USCIS زنگ بزنیم",
  "You said yes to the call": "شما به تماس «بلی» گفتید",
  "We called the official USCIS number": "به شمارهٔ رسمی USCIS زنگ زدیم",
  "We chose option 2: appointments and interviews": "گزینهٔ ۲ را انتخاب کردیم: وقت ملاقات و مصاحبه",
  "We chose option 2: asylum interview": "گزینهٔ ۲ را انتخاب کردیم: مصاحبهٔ پناهندگی",
  "We finished checking your letter": "بررسی نامهٔ شما تمام شد",
  "We're on hold": "در انتظار هستیم",
  "A person from USCIS answered": "یک شخص از USCIS جواب داد",
  "We're calling you to connect you": "به شما زنگ می‌زنیم تا وصل شوید",
  "We connected you with USCIS": "شما را با USCIS وصل کردیم",
  "The call ended": "تماس ختم شد",
  "We chose option 1: a case you already filed": "گزینهٔ ۱ را انتخاب کردیم: دوسیه‌ای که قبلاً درج کرده‌اید",
  "We chose option 3: a letter asking for evidence": "گزینهٔ ۳ را انتخاب کردیم: نامه‌ای که شواهد می‌خواهد",
  Searching: "جستجو",
  Reading: "خواندن",
  Checking: "بررسی",
  Listening: "گوش دادن",
  read: "خوانده شد",
  "press a key": "فشار یک دکمه",
  "0 red flags": "۰ نشانهٔ خطر",
  matches: "مطابقت دارد",
  real: "اصلی",

  // Profile facts
  "Has two children on the asylum application": "در درخواست پناهندگی دو اولاد دارد",
  "Lives in Los Angeles County": "در ولسوالی لاس انجلس زندگی می‌کند",
  "Prefers voice notes": "پیام صوتی را ترجیح می‌دهد",

  // WhatsApp thread
  "It's your asylum interview appointment: Thursday, November 12 at 8:30 AM. You must go with your children and bring your own interpreter.":
    "وقت ملاقات مصاحبهٔ پناهندگی شما: پنجشنبه ۱۲ نومبر، ساعت ۸:۳۰ صبح. باید با اولادهای خود بروید و ترجمان خود را بیاورید.",
  "We confirmed the letter is real. Want us to call USCIS and ring you when a person answers? Reply YES or NO.":
    "تأیید کردیم که نامه اصلی است. می‌خواهید به USCIS زنگ بزنیم و وقتی یک شخص جواب داد، به شما زنگ بزنیم؟ «بلی» یا «نخیر» بنویسید.",
  "Yes, please": "بلی، لطفاً",
  "We're calling USCIS. We'll let you know when someone answers.":
    "به USCIS زنگ می‌زنیم. وقتی کسی جواب داد، به شما خبر می‌دهیم.",
  "We're on hold with USCIS. We'll call you when a person answers.":
    "پشت خط USCIS منتظر هستیم. وقتی یک شخص جواب داد، به شما زنگ می‌زنیم.",
  "A person answered! We're calling you now.": "یک شخص جواب داد! حالا به شما زنگ می‌زنیم.",
  "Done. Your interview is still November 12 at 8:30 AM. Remember to bring your own interpreter.":
    "تمام شد. مصاحبهٔ شما هنوز هم ۱۲ نومبر، ساعت ۸:۳۰ صبح است. یادتان باشد که ترجمان خود را بیاورید.",

  // What the assistant suggestions prefill in WhatsApp
  "What do I need to bring to my asylum interview?": "به مصاحبهٔ پناهندگی خود چه چیزهایی ببرم؟",
  "I want to practice the English words for my interview": "می‌خواهم کلمه‌های انگلیسی مصاحبهٔ خود را تمرین کنم",
  "How do I find a qualified interpreter?": "یک ترجمان واجد شرایط را از کجا پیدا کنم؟",

  // Live call: asylum interview
  "Okay, I have the case open. Can you confirm your full name and date of birth for me?":
    "خوب، دوسیه را باز کرده‌ام. لطفاً نام کامل و تاریخ تولد خود را تأیید کنید؟",
  "They're asking your name and date of birth. Answer yourself; we never answer for you.":
    "نام و تاریخ تولد شما را می‌پرسند. خودتان جواب بدهید؛ ما هرگز به جای شما جواب نمی‌دهیم.",
  "Ana Morales, March 14, 1988.": "آنا مورالس، ۱۴ مارچ ۱۹۸۸.",
  "Thank you. Your asylum interview is still scheduled for November 12 at 8:30 AM at the asylum office in Tustin.":
    "تشکر. مصاحبه پناهندگی شما هنوز هم برای ۱۲ نومبر، ساعت ۸:۳۰ صبح در دفتر پناهندگی تاستن تعیین شده است.",
  "My interpreter may not be able to come. What should I do?": "شاید ترجمان من نتواند بیاید. چه کار کنم؟",
  "You have to bring your own interpreter; we don't provide one. If they can't come, send a reschedule request in writing before your appointment.":
    "شما باید ترجمان خود را بیاورید؛ ما ترجمان نمی‌دهیم. اگر نتواند بیاید، پیش از وقت ملاقات خود یک درخواست تعیین وقت مجدد را به‌طور کتبی بفرستید.",
  "Do my children need to come to the interview too?": "آیا اولادهای من هم باید به مصاحبه بیایند؟",
  "Yes. Every dependent on your application has to attend, and bring an identity document for each of them.":
    "بلی. هر وابسته‌ای که در درخواست شما است باید حاضر شود، و برای هر کدام یک سند هویت بیاورید.",
  "Can I have a reference number for this call?": "می‌توانید برای این تماس یک شمارهٔ مرجع به من بدهید؟",

  // Live call: Request for Evidence
  "I can help with that. What's the receipt number on the letter?":
    "می‌توانم در این مورد کمک کنم. شماره رسید روی نامه چیست؟",
  "They're asking for the receipt number. It's at the top of your letter; read it yourself.":
    "شماره رسید را می‌پرسند. بالای نامهٔ شما نوشته شده؛ خودتان آن را بخوانید.",
  "Yes, it starts with I-O-E and ends in seven seven eight one.":
    "بلی، با I-O-E شروع می‌شود و به هفت هفت هشت یک ختم می‌شود.",
  "Thank you. I see the request for evidence for your work permit. It's due December 4.":
    "تشکر. درخواست شواهد را برای مجوز کار شما می‌بینم. مهلت آن ۴ دسمبر است.",
  "Which address should I mail the evidence to?": "شواهد را به کدام آدرس بفرستم؟",
  "Use the address printed on the letter, and put the letter on top of your documents.":
    "از آدرسی که روی نامه چاپ شده استفاده کنید، و نامه را بالای اسناد خود بگذارید.",
  "Can I get more time if a document is missing?": "اگر یک سند کم باشد، می‌توانم وقت بیشتر بگیرم؟",
  "We can't extend the deadline. Send what you have, and explain in writing why the missing document isn't included.":
    "نمی‌توانیم مهلت را تمدید کنیم. آنچه دارید بفرستید، و به‌طور کتبی توضیح بدهید که چرا آن سند شامل نیست.",
};

/** The fixture text for `lang`: the Spanish, the Dari for this English, or the English. */
export function pick(lang: string, es: string, en: string): string {
  if (lang === "es") return es;
  if (lang === "fa") return FA[en] ?? en;
  return en;
}

