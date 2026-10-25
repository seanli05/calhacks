# Dari review sheet

For the fluent Dari checker (build order 1.9). Generated from `backend/app/relay/templates.py` on branch `lauren-dari`; if a template changes, regenerate this sheet or check the code.

## How to check

1. Read the **open questions** below first and answer each one.
2. Read **every template** (section 2). For each: is it natural Afghan Dari (not Iranian Farsi)? Is it polite and simple enough for someone with little schooling? Does it say exactly what the English says, nothing more or less? Write fixes in the *Fix* column, or send them to Lauren.
3. Then on a **real phone** (WhatsApp, through the sandbox), with Dari picked: send a letter photo and go through the explanation, verdict, consent request, call and summary. Check right-to-left layout: "USCIS", "I-797C", "uscis.gov" and phone numbers must read left to right inside the Dari, and each line must start on the right.
4. Section 3 has **model translations** (explanation, checklist, red flags, call summary, a reply). These change every time; judge the style and the terms, and flag anything wrong or Iranian.

`{name}` is a placeholder filled in by code: `{date}` is a date like `چهارشنبه ۱۸ نومبر ۲۰۲۶`, `{time}` like `۸:۳۰ صبح`, `{goal}`, `{facts}`, `{tip}`, `{red_flags}` are model translations, `{options}` a numbered list, `{seconds}`/`{count}`/`{default}` numbers.

## 1. Open questions

| # | Question | Now | Alternatives | Why it matters |
|---|---|---|---|---|
| 1 | November | نومبر | نوامبر | The demo interview is in November. USCIS's Dari page uses Afghan forms (سپتمبر, اکتوبر, دسمبر) but also writes نوامبر once; no Dari source with نومبر was found. |
| 2 | February | فبروری | فیبروری | Same pattern as above; not found in a Dari source. |
| 3 | Times of day | ۸:۳۰ صبح, ۴:۳۰ بعد از ظهر, ۸:۰۰ شب | قبل از چاشت / بعد از چاشت; ۸ صبح without :۰۰ | From Da Afghanistan Bank ("۴:۳۰ بعد از ظهر") and USCIS Dari ("۸ شب"). |
| 4 | Interpreter | ترجمان | مترجم | Glossary seed term; USCIS's Dari uses مترجم for a written translator. Used in translations (not in templates). |
| 5 | Legal help line | یک وکیل یا یک نمایندهٔ معتبر وزارت عدلیهٔ امریکا (DOJ) |  | "A lawyer or a DOJ-accredited representative". Is it clear? (نمایندهٔ معتبر is USCIS's Dari for accredited representative.) |
| 6 | Yes/no words accepted | بلی, بله, آری, آره / نخیر, نه, نی | add ها? add Latin bale/bali/na? | A one-word yes starts a call, so only unambiguous words belong here. |
| 7 | Digits | Persian digits (۱, ۲, ۱۸ نومبر ۲۰۲۶) | Latin digits | USCIS's Dari page uses Persian digits for dates and counts, Latin for phone and form numbers. |
| 8 | Interpreter age (translations) | the model wrote بالای ۱۸ سال once and ۱۸ ساله یا بالاتر once |  | The English is "18 or older"; does بالای ۱۸ سال exclude 18-year-olds? |
| 9 | "Genuine" letter | نامهٔ شما اصلی است | واقعی / معتبر | The verdict users rely on before agreeing to a call. |

## 2. Every template

| Template | English | Dari | OK? | Fix |
|---|---|---|---|---|
| `language.menu` | Hola 👋 Hello 👋 سلام<br>¿En qué idioma prefiere que le escriba? / Which language would you like?<br>به کدام زبان برایتان بنویسم؟<br>Español · English · دری | <div dir="rtl">Hola 👋 Hello 👋 سلام<br>¿En qué idioma prefiere que le escriba? / Which language would you like?<br>به کدام زبان برایتان بنویسم؟<br>Español · English · دری</div> | | |
| `language.set` | Great, we'll continue in English. Send me a photo of your letter, or write me your question. | <div dir="rtl">خوب، به دری ادامه می‌دهیم. یک عکس از نامهٔ خود را برایم بفرستید، یا سوال خود را برایم بنویسید.</div> | | |
| `language.set_letter` | Thanks, I got your letter. I'll write in English; if another language is easier, just tell me. If it has more pages, send them now. | <div dir="rtl">تشکر، نامهٔ شما را گرفتم. به دری برایتان می‌نویسم؛ اگر زبان دیگری برایتان آسان‌تر است، فقط بگویید. اگر نامه صفحه‌های بیشتر دارد، حالا بفرستید.</div> | | |
| `letter.received` | Got it. If there are more pages, send them now. | <div dir="rtl">گرفتم. اگر صفحه‌های بیشتر دارد، حالا بفرستید.</div> | | |
| `letter.same_or_new` | Is this another page of the same letter, or a new letter?<br>1 Same letter<br>2 New letter | <div dir="rtl">آیا این یک صفحهٔ دیگر همان نامه است، یا یک نامهٔ نو؟<br>۱ همان نامه<br>۲ نامهٔ نو</div> | | |
| `letter.pages_added` | Thanks, I added the page to your letter. | <div dir="rtl">تشکر، صفحه را به نامهٔ شما اضافه کردم.</div> | | |
| `research.slow` | I'm still reading your letter. It's taking a little longer than usual; I'll write as soon as I'm done. | <div dir="rtl">هنوز نامهٔ شما را می‌خوانم. کمی بیشتر از معمول وقت می‌گیرد؛ وقتی تمام شد، برایتان می‌نویسم.</div> | | |
| `orchestrator.unavailable` | Sorry, I couldn't answer just now. Please write to me again in a few minutes. | <div dir="rtl">معذرت می‌خواهم، حالا نتوانستم جواب بدهم. لطفاً چند دقیقه بعد دوباره برایم بنویسید.</div> | | |
| `media.download_failed` | Sorry, I couldn't download that file. Could you send it again? | <div dir="rtl">معذرت می‌خواهم، نتوانستم آن فایل را باز کنم. می‌توانید دوباره بفرستید؟</div> | | |
| `ask_user.menu_choice` | I'm on the call with USCIS and the menu is giving me these options. Which one should I pick?<br>{options}<br>Reply with the number. If I don't hear back in {seconds} seconds, I'll pick option {default}, the safest one. | <div dir="rtl">من در تماس با ادارهٔ USCIS هستم و سیستم تیلفونی این گزینه‌ها را می‌دهد. کدام را انتخاب کنم؟<br>{options}<br>با شمارهٔ گزینه جواب بدهید. اگر تا {seconds} ثانیه جوابی نگیرم، گزینهٔ {default} را انتخاب می‌کنم، که مطمئن‌ترین گزینه است.</div> | | |
| `ask_user.reprompt` | Please reply with just a number from 1 to {count}. | <div dir="rtl">لطفاً فقط با یک شماره از ۱ تا {count} جواب بدهید.</div> | | |
| `ask_user.late_reply` | Thanks. I didn't get an answer in time, so I already picked option {default}: {default_option}. It was the safest choice, and the call went on with it. | <div dir="rtl">تشکر. چون به وقت جواب نگرفتم، گزینهٔ {default} را انتخاب کردم: {default_option}. این مطمئن‌ترین گزینه بود و تماس با همین گزینه ادامه پیدا کرد.</div> | | |
| `letter.appointment` | 📅 Your interview: {date}, at {time}. The address is on your letter. | <div dir="rtl">📅 مصاحبهٔ شما: {date}، ساعت {time}. آدرس در نامهٔ شما نوشته شده است.</div> | | |
| `letter.appointment_date` | 📅 Your interview: {date}. The details are on your letter. | <div dir="rtl">📅 مصاحبهٔ شما: {date}. جزئیات در نامهٔ شما نوشته شده است.</div> | | |
| `letter.deadline` | 📅 Deadline: {date}. | <div dir="rtl">📅 مهلت: {date}.</div> | | |
| `letter.double_checking` | Thank you, I've read your letter. I'm just double-checking that it really comes from USCIS. I'll write again in a moment. | <div dir="rtl">تشکر، نامهٔ شما را خواندم. فقط بررسی می‌کنم که واقعاً از طرف ادارهٔ USCIS باشد. چند لحظه بعد دوباره برایتان می‌نویسم.</div> | | |
| `letter.looks_like_scam` | Thank you for sending this. I'm worried this letter may be a scam: it has signs that real USCIS letters don't. Please don't pay anything, don't call any number on it, and don't give out your details. You did the right thing by checking first. Write to me if you have questions. | <div dir="rtl">تشکر که این را فرستادید. نگران هستم که این نامه کلاهبرداری باشد: نشانه‌هایی دارد که نامه‌های اصلی ادارهٔ USCIS ندارند. لطفاً هیچ پولی پرداخت نکنید، به هیچ شماره‌ای در نامه زنگ نزنید و معلومات شخصی خود را به کسی ندهید. خوب کردید که اول بررسی کردید. اگر سوالی دارید، برایم بنویسید.</div> | | |
| `letter.still_checking` | ⚠️ I'm still checking that this letter really comes from USCIS. Until I'm sure, please don't pay anything or call any number on it. I'll write again when I know. | <div dir="rtl">⚠️ هنوز بررسی می‌کنم که این نامه واقعاً از طرف ادارهٔ USCIS باشد. تا وقتی مطمئن نشده‌ام، لطفاً هیچ پولی پرداخت نکنید و به هیچ شماره‌ای در نامه زنگ نزنید. وقتی معلوم شد، دوباره برایتان می‌نویسم.</div> | | |
| `letter.explain_failed` | I read your letter, but I couldn't write up the explanation just now. Write me "what does my letter say?" and I'll explain it. | <div dir="rtl">نامهٔ شما را خواندم، اما حالا نتوانستم توضیح آن را بنویسم. برایم بنویسید «نامهٔ من چه می‌گوید؟» تا برایتان توضیح بدهم.</div> | | |
| `letter.which_letter` | Before I explain, I need one answer: these photos look like they come from different letters. Which letter should I read first? Reply in a few words. | <div dir="rtl">پیش از توضیح، به یک جواب ضرورت دارم: معلوم می‌شود که این عکس‌ها از نامه‌های مختلف هستند. اول کدام نامه را بخوانم؟ در چند کلمه جواب بدهید.</div> | | |
| `letter.reading_again` | Thanks. I'm reading that letter now and will write as soon as I'm done. | <div dir="rtl">تشکر. حالا همان نامه را می‌خوانم و وقتی تمام شد، برایتان می‌نویسم.</div> | | |
| `research_question.not_found` | I couldn't find an answer to your question in an official source. A lawyer or a DOJ-accredited representative can help. | <div dir="rtl">برای سوال شما در یک منبع رسمی جوابی پیدا نکردم. یک وکیل یا یک نمایندهٔ معتبر وزارت عدلیهٔ امریکا (DOJ) می‌تواند کمک کند.</div> | | |
| `research_question.legal_advice` | I can't give legal advice about your case. A lawyer or a DOJ-accredited representative can help, often for free. | <div dir="rtl">من نمی‌توانم دربارهٔ دوسیهٔ شما مشورهٔ حقوقی بدهم. یک وکیل یا یک نمایندهٔ معتبر وزارت عدلیهٔ امریکا (DOJ) می‌تواند کمک کند، اکثراً به شکل رایگان.</div> | | |
| `research_question.asylum_claim` | I don't discuss the details of your asylum claim. A lawyer or a DOJ-accredited representative can help with that. | <div dir="rtl">من دربارهٔ جزئیات درخواست پناهندگی شما صحبت نمی‌کنم. یک وکیل یا یک نمایندهٔ معتبر وزارت عدلیهٔ امریکا (DOJ) می‌تواند در این مورد کمک کند.</div> | | |
| `research_question.untranslated` | I found an answer in an official source but couldn't translate it. You can read it here:<br>{sources} | <div dir="rtl">در یک منبع رسمی جوابی پیدا کردم، اما نتوانستم آن را ترجمه کنم. می‌توانید آن را اینجا بخوانید:<br>{sources}</div> | | |
| `research_question.failed` | I couldn't look that up right now. Ask me again in a little while. | <div dir="rtl">حالا نتوانستم جواب را پیدا کنم. کمی بعد دوباره از من بپرسید.</div> | | |
| `letter.retake` | I couldn't read the photo well. Could you send another one? Put the letter on a table in good light, with the whole page in the photo and no shadows. | <div dir="rtl">نتوانستم عکس را خوب بخوانم. می‌توانید یک عکس دیگر بفرستید؟ نامه را در روشنی خوب روی یک میز بگذارید، طوری که تمام صفحه در عکس باشد و سایه نداشته باشد.</div> | | |
| `letter.retake_tip` | I couldn't read the photo well. {tip} Could you send another one? | <div dir="rtl">نتوانستم عکس را خوب بخوانم. {tip} می‌توانید یک عکس دیگر بفرستید؟</div> | | |
| `verification.verified` | ✅ Your letter is genuine: I checked it against official information on uscis.gov. | <div dir="rtl">✅ نامهٔ شما اصلی است: آن را با معلومات رسمی ویب سایت uscis.gov بررسی کردم.</div> | | |
| `verification.verified_no_call` | I checked your letter against official information on uscis.gov: it's genuine. ✅ There's no need to call USCIS for now. Write to me if you have questions. | <div dir="rtl">نامهٔ شما را با معلومات رسمی ویب سایت uscis.gov بررسی کردم: نامه اصلی است. ✅ فعلاً ضرورت به تماس با ادارهٔ USCIS نیست. اگر سوالی دارید، برایم بنویسید.</div> | | |
| `verification.suspicious` | ⚠️ Careful: this letter has signs of a scam:<br>{red_flags}<br>Don't call the numbers on the letter, don't pay anything, and don't give out your details. Write to me if you have questions. | <div dir="rtl">⚠️ احتیاط: این نامه نشانه‌های کلاهبرداری دارد:<br>{red_flags}<br>به شماره‌های داخل نامه زنگ نزنید، هیچ پولی پرداخت نکنید و معلومات شخصی خود را به کسی ندهید. اگر سوالی دارید، برایم بنویسید.</div> | | |
| `verification.suspicious_generic` | ⚠️ Careful: this letter has signs of a scam. Don't call the numbers on the letter, don't pay anything, and don't give out your details. Write to me if you have questions. | <div dir="rtl">⚠️ احتیاط: این نامه نشانه‌های کلاهبرداری دارد. به شماره‌های داخل نامه زنگ نزنید، هیچ پولی پرداخت نکنید و معلومات شخصی خود را به کسی ندهید. اگر سوالی دارید، برایم بنویسید.</div> | | |
| `verification.unknown` | I couldn't confirm that this letter really comes from USCIS, so I won't offer to call yet. To be safe, please don't pay anything or call any number on it. You can check your case at uscis.gov. | <div dir="rtl">نتوانستم تأیید کنم که این نامه واقعاً از طرف ادارهٔ USCIS است، به همین خاطر هنوز پیشنهاد تماس نمی‌کنم. برای احتیاط، لطفاً هیچ پولی پرداخت نکنید و به هیچ شماره‌ای در نامه زنگ نزنید. می‌توانید دوسیهٔ خود را در ویب سایت uscis.gov بررسی کنید.</div> | | |
| `consent.request` | Would you like me to call USCIS for you?<br>What for: {goal}<br>I'll wait on hold and call you when a person answers. I won't share your case numbers or date of birth.<br>1 Yes, call<br>2 No, thanks | <div dir="rtl">می‌خواهید از طرف شما با ادارهٔ USCIS تماس بگیرم؟<br>برای چه: {goal}<br>من پشت خط منتظر می‌مانم و وقتی یک شخص جواب داد، به شما زنگ می‌زنم. شماره‌های دوسیه و تاریخ تولد شما را به کسی نمی‌گویم.<br>۱ بلی، تماس بگیرید<br>۲ نخیر، تشکر</div> | | |
| `consent.request_generic` | Would you like me to call USCIS for you about this letter?<br>I'll wait on hold and call you when a person answers. I won't share your case numbers or date of birth.<br>1 Yes, call<br>2 No, thanks | <div dir="rtl">می‌خواهید دربارهٔ این نامه از طرف شما با ادارهٔ USCIS تماس بگیرم؟<br>من پشت خط منتظر می‌مانم و وقتی یک شخص جواب داد، به شما زنگ می‌زنم. شماره‌های دوسیه و تاریخ تولد شما را به کسی نمی‌گویم.<br>۱ بلی، تماس بگیرید<br>۲ نخیر، تشکر</div> | | |
| `consent.reprompt` | Please reply 1 if you'd like me to call USCIS, or 2 if not. | <div dir="rtl">لطفاً اگر می‌خواهید با ادارهٔ USCIS تماس بگیرم، ۱ را بفرستید، و اگر نه، ۲ را.</div> | | |
| `consent.given` | Thank you. I'm setting up the call and will let you know when I'm dialing. | <div dir="rtl">تشکر. تماس را آماده می‌کنم و وقتی شماره را گرفتم، به شما خبر می‌دهم.</div> | | |
| `consent.declined` | All right, I won't call. If you change your mind, write to me. | <div dir="rtl">خوب، تماس نمی‌گیرم. اگر نظر شما تغییر کرد، برایم بنویسید.</div> | | |
| `consent.unavailable` | Sorry, I can't make that call right now. Write to me if you'd like me to try later. | <div dir="rtl">معذرت می‌خواهم، حالا نمی‌توانم این تماس را بگیرم. اگر می‌خواهید بعداً دوباره کوشش کنم، برایم بنویسید.</div> | | |
| `summary.reference` | Reference number for the call: {reference} | <div dir="rtl">شمارهٔ مرجع این تماس: {reference}</div> | | |
| `summary.deadlines` | 📅 Important dates: {dates} | <div dir="rtl">📅 تاریخ‌های مهم: {dates}</div> | | |
| `summary.unavailable` | The call with USCIS is over. I couldn't write up the summary just now; write to me and I'll explain it. | <div dir="rtl">تماس با ادارهٔ USCIS تمام شد. حالا نتوانستم خلاصهٔ آن را بنویسم؛ برایم بنویسید تا برایتان توضیح بدهم.</div> | | |
| `summary.call_failed` | I couldn't complete the call with USCIS: the wait was too long or the call dropped. | <div dir="rtl">نتوانستم تماس با ادارهٔ USCIS را تمام کنم: انتظار خیلی طولانی شد یا تماس قطع شد.</div> | | |
| `summary.unreachable_followup` | If you'd like, I can call USCIS again and let you know when a person answers. | <div dir="rtl">اگر بخواهید، می‌توانم دوباره با ادارهٔ USCIS تماس بگیرم و وقتی یک شخص جواب داد، به شما خبر بدهم.</div> | | |
| `summary.suggest_close` | It looks like this letter is taken care of. If you don't need more help with it, write "close" and I'll close it. | <div dir="rtl">معلوم می‌شود که کار این نامه تمام شده است. اگر دیگر در مورد آن به کمک ضرورت ندارید، «بستن» بنویسید تا آن را ببندم.</div> | | |
| `call.dialing` | Calling USCIS now. | <div dir="rtl">حالا با ادارهٔ USCIS تماس می‌گیرم.</div> | | |
| `call.on_hold` | Still on hold with USCIS. I'll let you know when a person answers. | <div dir="rtl">هنوز پشت خط ادارهٔ USCIS منتظر هستم. وقتی یک شخص جواب داد، به شما خبر می‌دهم.</div> | | |
| `call.human_detected` | Someone picked up. I'm calling you now; please answer. | <div dir="rtl">یک شخص جواب داد. حالا به شما زنگ می‌زنم؛ لطفاً تیلفون را جواب بدهید.</div> | | |
| `call.user_unreachable` | I couldn't reach you, so I told USCIS you'd call back and ended the call. | <div dir="rtl">نتوانستم با شما تماس بگیرم، به همین خاطر به ادارهٔ USCIS گفتم که خود شما دوباره زنگ می‌زنید و تماس را ختم کردم.</div> | | |
| `memory.ask_save` | May I remember this, so I don't have to ask you again?<br>{facts}<br>I only use it to help you, and you can delete it any time.<br>1 Yes, save it<br>2 No, don't save it | <div dir="rtl">اجازه می‌دهید این را نگه دارم، تا دوباره از شما نپرسم؟<br>{facts}<br>فقط برای کمک به شما از آن استفاده می‌کنم، و هر وقت بخواهید، می‌توانید آن را پاک کنید.<br>۱ بلی، نگه دارید<br>۲ نخیر، نگه ندارید</div> | | |
| `memory.saved` | Done, I saved it. | <div dir="rtl">خوب، نگه داشتم.</div> | | |
| `memory.not_saved` | All right, I didn't save it. | <div dir="rtl">خوب، نگه نداشتم.</div> | | |

## 3. Model translations (samples)

From the real translator (`MODEL_FAST`, with the Dari glossary rows from `terms.csv`) on the contract fixtures, Oct 24. Direction isolates removed for reading.

### explanation (summary_en)

English:

```
This is a USCIS notice scheduling your asylum interview. You must go, or your application can be dismissed.
```

Dari:

<div dir="rtl">

این یک اعلان ادارهٔ USCIS است که مصاحبه پناهندگی شما را تعیین می‌کند. باید حتماً بروید، ورنه درخواست شما ممکن است لغو شود.

</div>

### checklist

English:

```
Who must come:
- All dependents listed on the I-589
- An interpreter if you are not fluent in English: 18 or older, not your attorney or a witness, not working for your country's government, no pending asylum case of their own

What to bring:
- ID for you and each dependent (name, date of birth, place of birth, nationality)
- Original and one copy of relationship documents (marriage or birth certificates)

Other deadlines:
- If your attorney will join remotely, their election form is due 10 days before the interview
```

Dari:

<div dir="rtl">

چه کسانی باید بیایند:
- تمام وابسته‌هایی که در I-589 ثبت شده‌اند
- یک ترجمان، اگر شما به انگلیسی مسلط نیستید: بالای ۱۸ سال، نه وکیل شما و نه شاهد، نه کارمند دولت کشور شما، و بدون دوسیهٔ پناهندگی فعال از خودش

چه چیزهایی باید بیاورید:
- سند هویت برای شما و هر وابسته (نام، تاریخ تولد، محل تولد، تابعیت)
- اصل و یک کاپی اسناد رابطه (سند نکاح یا سند تولد)

مهلت‌های دیگر:
- اگر وکیل شما از راه دور می‌پیوندد، فورمهٔ انتخاب آنها باید ۱۰ روز قبل از مصاحبه ارسال شود

</div>

### call goal (consent request)

English:

```
Confirm the interview is still scheduled
```

Dari:

<div dir="rtl">

تأیید اینکه مصاحبه هنوز تنظیم شده است

</div>

### scam red flags

English:

```
- The letter asks you to pay a fee by gift card
- The phone number on the letter is not a USCIS number
```

Dari:

<div dir="rtl">

- نامه از شما می‌خواهد که فیس را با کارت هدیه بپردازید
- شماره تیلفونی که در نامه است، شماره ادارهٔ USCIS نیست

</div>

### post-call next steps

English:

```
Here's how the call with USCIS went:
- Interview is still on for Nov 18
- If the interpreter can't come, contact the asylum office before the interview to ask to reschedule
```

Dari:

<div dir="rtl">

طرز صحبت شما با ادارهٔ USCIS به این شکل بود:
- مصاحبه هنوز سر وقت خود، ۱۸ نومبر، برقرار است
- اگر ترجمان نتواند بیاید، قبل از مصاحبه با دفتر پناهندگی تماس بگیرید و بپرسید که وقت مصاحبه را تعیین وقت مجدد کنند

</div>

### turn reply

English:

```
Yes. Bring your interpreter to the interview on November 18. USCIS won't provide one. Your interpreter must be 18 or older and can't be your lawyer or a witness.
```

Dari:

<div dir="rtl">

بلی. ترجمان خود را روز ۱۸ نومبر به مصاحبه بیاورید. ادارهٔ USCIS ترجمان نمی‌دهد. ترجمان شما باید ۱۸ ساله یا بالاتر باشد و نمی‌تواند وکیل شما یا شاهد باشد.

</div>

### facts to save

English:

```
• Lives in Sacramento
• Has a spouse and two children on the case
```

Dari:

<div dir="rtl">

• در ساکرامنتو زندگی می‌کند
• یک همسر و دو فرزند در این دوسیه دارد

</div>

## After the review

- Template fixes go into `backend/app/relay/templates.py` (the `"fa"` entries); then `ruff format . && ruff check --fix . && pytest`.
- Glossary fixes go into `backend/app/glossary/terms.csv` and `review_fa.csv` (see `glossary/REPORT.md`, "Morning to-dos" step 5).
- Register fixes (words the translator should prefer) go into `REGISTERS["fa"]` in `backend/app/translation/translate.py`.
