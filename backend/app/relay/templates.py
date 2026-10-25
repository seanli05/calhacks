"""Pre-translated WhatsApp templates: `template_id -> {language: text}`.

Spanish uses formal usted. Dari is Afghan Dari, not Iranian Farsi, with the polite
شما; its words follow the glossary (`glossary/terms.csv`) and USCIS's Dari pages
(ادارهٔ USCIS, معلومات, دوسیه, مشورهٔ حقوقی, نمایندهٔ معتبر), and it writes numbers in
Persian digits. Every template must exist in every language in LANGUAGES (a test
checks). Placeholders use str.format: `{name}`. `render` adds the direction isolates
right-to-left text needs (`translation/script.py`), so the texts here have none.
"""

from app.contracts.common import LanguageCode
from app.translation.script import for_display, local_digits

LANGUAGES: tuple[LanguageCode, ...] = ("es", "en", "fa")
"""Supported languages, in the order the language menu lists them."""

_MENU = (
    "Hola 👋 Hello 👋 سلام\n"
    "¿En qué idioma prefiere que le escriba? / Which language would you like?\n"
    "به کدام زبان برایتان بنویسم؟\n"
    "1 Español\n"
    "2 English\n"
    "3 دری"
)

# The end of every consent request: how the call works, then the choice.
_CALL_ASK = {
    "es": (
        "Yo espero en la línea y le llamo cuando conteste una persona. No daré sus "
        "números de caso ni su fecha de nacimiento.\n"
        "1 Sí, llame\n2 No, gracias"
    ),
    "en": (
        "I'll wait on hold and call you when a person answers. I won't share your "
        "case numbers or date of birth.\n"
        "1 Yes, call\n2 No, thanks"
    ),
    "fa": (
        "من پشت خط منتظر می‌مانم و وقتی یک شخص جواب داد، به شما زنگ می‌زنم. "
        "شماره‌های دوسیه و تاریخ تولد شما را به کسی نمی‌گویم.\n"
        "۱ بلی، تماس بگیرید\n۲ نخیر، تشکر"
    ),
}
_VERIFIED = {
    "es": "✅ Su carta es auténtica: la revisé con la información oficial de uscis.gov.",
    "en": "✅ Your letter is genuine: I checked it against official information on uscis.gov.",
    "fa": "✅ نامهٔ شما اصلی است: آن را با معلومات رسمی ویب سایت uscis.gov بررسی کردم.",
}
_WANT_CALL = {
    "es": "¿Quiere que llame a USCIS por usted?\nPara qué: {goal}\n",
    "en": "Would you like me to call USCIS for you?\nWhat for: {goal}\n",
    "fa": "می‌خواهید از طرف شما با ادارهٔ USCIS تماس بگیرم؟\nبرای چه: {goal}\n",
}
_WANT_CALL_GENERIC = {
    "es": "¿Quiere que llame a USCIS por usted sobre esta carta?\n",
    "en": "Would you like me to call USCIS for you about this letter?\n",
    "fa": "می‌خواهید دربارهٔ این نامه از طرف شما با ادارهٔ USCIS تماس بگیرم؟\n",
}
# Who to ask for legal help (C33): a lawyer or a DOJ-accredited representative.
_LEGAL_HELP_FA = "یک وکیل یا یک نمایندهٔ معتبر وزارت عدلیهٔ امریکا (DOJ)"

TEMPLATES: dict[str, dict[LanguageCode, str]] = {
    "language.confirm": {
        "es": "Parece que habla español. ¿Seguimos en español?\n1 Sí\n2 Otro idioma",
        "en": (
            "It looks like you're writing in English. Shall we continue in English?\n"
            "1 Yes\n2 Another language"
        ),
        "fa": (
            "معلوم می‌شود که شما به دری می‌نویسید. به دری ادامه بدهیم؟\n"
            "۱ بلی\n۲ زبان دیگر"
        ),
    },
    "language.menu": {"es": _MENU, "en": _MENU, "fa": _MENU},
    "language.set": {
        "es": (
            "Perfecto, seguimos en español. Envíeme una foto de su carta, "
            "o escríbame su pregunta."
        ),
        "en": (
            "Great, we'll continue in English. Send me a photo of your letter, "
            "or write me your question."
        ),
        "fa": (
            "خوب، به دری ادامه می‌دهیم. یک عکس از نامهٔ خود را برایم بفرستید، "
            "یا سوال خود را برایم بنویسید."
        ),
    },
    "language.set_letter": {
        "es": (
            "Perfecto, seguimos en español. Recibí su carta. Si tiene más páginas, "
            "envíelas ahora."
        ),
        "en": (
            "Great, we'll continue in English. I got your letter. If it has more "
            "pages, send them now."
        ),
        "fa": (
            "خوب، به دری ادامه می‌دهیم. نامهٔ شما را گرفتم. اگر صفحه‌های بیشتر دارد، "
            "حالا بفرستید."
        ),
    },
    # No question mark: a question invites a "no, that's it" that needs a turn.
    "letter.received": {
        "es": "Recibido. Si tiene más páginas, envíelas ahora.",
        "en": "Got it. If there are more pages, send them now.",
        "fa": "گرفتم. اگر صفحه‌های بیشتر دارد، حالا بفرستید.",
    },
    "letter.same_or_new": {
        "es": "¿Es otra página de la misma carta, o una carta nueva?\n1 Misma carta\n2 Carta nueva",
        "en": "Is this another page of the same letter, or a new letter?\n1 Same letter\n2 New letter",
        "fa": (
            "آیا این یک صفحهٔ دیگر همان نامه است، یا یک نامهٔ نو؟\n۱ همان نامه\n۲ نامهٔ نو"
        ),
    },
    "letter.pages_added": {
        "es": "Gracias, agregué la página a su carta.",
        "en": "Thanks, I added the page to your letter.",
        "fa": "تشکر، صفحه را به نامهٔ شما اضافه کردم.",
    },
    # Plan.md → Failure rules: the fast pass is past 45 s.
    "research.slow": {
        "es": (
            "Sigo leyendo su carta. Está tardando un poco más de lo normal; "
            "le escribo en cuanto termine."
        ),
        "en": (
            "I'm still reading your letter. It's taking a little longer than usual; "
            "I'll write as soon as I'm done."
        ),
        "fa": (
            "هنوز نامهٔ شما را می‌خوانم. کمی بیشتر از معمول وقت می‌گیرد؛ "
            "وقتی تمام شد، برایتان می‌نویسم."
        ),
    },
    # The orchestrator's turn failed (model or translation); never English instead.
    "orchestrator.unavailable": {
        "es": (
            "Lo siento, no pude responderle ahora. Por favor escríbame otra vez "
            "en unos minutos."
        ),
        "en": "Sorry, I couldn't answer just now. Please write to me again in a few minutes.",
        "fa": (
            "معذرت می‌خواهم، حالا نتوانستم جواب بدهم. لطفاً چند دقیقه بعد دوباره "
            "برایم بنویسید."
        ),
    },
    "media.download_failed": {
        "es": "Lo siento, no pude descargar ese archivo. ¿Me lo puede enviar otra vez?",
        "en": "Sorry, I couldn't download that file. Could you send it again?",
        "fa": "معذرت می‌خواهم، نتوانستم آن فایل را باز کنم. می‌توانید دوباره بفرستید؟",
    },
    # ask_user (P1). `options` is the numbered list; `default` is the option the
    # agent takes on timeout, always the safest (C5).
    "ask_user.menu_choice": {
        "es": (
            "Estoy en la llamada con USCIS y el menú me da estas opciones. "
            "¿Cuál elijo?\n{options}\n"
            "Responda con el número. Si no recibo respuesta en {seconds} segundos, "
            "elegiré la opción {default}, que es la más segura."
        ),
        "en": (
            "I'm on the call with USCIS and the menu is giving me these options. "
            "Which one should I pick?\n{options}\n"
            "Reply with the number. If I don't hear back in {seconds} seconds, "
            "I'll pick option {default}, the safest one."
        ),
        "fa": (
            "من در تماس با ادارهٔ USCIS هستم و سیستم تیلفونی این گزینه‌ها را می‌دهد. "
            "کدام را انتخاب کنم؟\n{options}\n"
            "با شمارهٔ گزینه جواب بدهید. اگر تا {seconds} ثانیه جوابی نگیرم، "
            "گزینهٔ {default} را انتخاب می‌کنم، که مطمئن‌ترین گزینه است."
        ),
    },
    "ask_user.reprompt": {
        "es": "Por favor responda solo con un número del 1 al {count}.",
        "en": "Please reply with just a number from 1 to {count}.",
        "fa": "لطفاً فقط با یک شماره از ۱ تا {count} جواب بدهید.",
    },
    "ask_user.late_reply": {
        "es": (
            "Gracias. Como no recibí respuesta a tiempo, ya elegí la opción "
            "{default}: {default_option}. Era la opción más segura, y la llamada "
            "siguió con ella."
        ),
        "en": (
            "Thanks. I didn't get an answer in time, so I already picked option "
            "{default}: {default_option}. It was the safest choice, and the call "
            "went on with it."
        ),
        "fa": (
            "تشکر. چون به وقت جواب نگرفتم، گزینهٔ {default} را انتخاب کردم: "
            "{default_option}. این مطمئن‌ترین گزینه بود و تماس با همین گزینه "
            "ادامه پیدا کرد."
        ),
    },
    # R1 (Goal 6.1). The explanation and checklist are translated free text; these
    # lines carry what must never be garbled, with dates formatted in code.
    "letter.appointment": {
        "es": "📅 Su entrevista: {date}, a las {time}. La dirección está en su carta.",
        "en": "📅 Your interview: {date}, at {time}. The address is on your letter.",
        "fa": "📅 مصاحبهٔ شما: {date}، ساعت {time}. آدرس در نامهٔ شما نوشته شده است.",
    },
    "letter.appointment_date": {
        "es": "📅 Su entrevista: {date}. Los detalles están en su carta.",
        "en": "📅 Your interview: {date}. The details are on your letter.",
        "fa": "📅 مصاحبهٔ شما: {date}. جزئیات در نامهٔ شما نوشته شده است.",
    },
    "letter.deadline": {
        "es": "📅 Fecha límite: {date}.",
        "en": "📅 Deadline: {date}.",
        "fa": "📅 مهلت: {date}.",
    },
    # C45: the letter is read; the explanation waits for the legitimacy check.
    "letter.double_checking": {
        "es": (
            "Gracias, ya leí su carta. Solo estoy verificando que de verdad venga "
            "de USCIS. Le escribo en un momento."
        ),
        "en": (
            "Thank you, I've read your letter. I'm just double-checking that it "
            "really comes from USCIS. I'll write again in a moment."
        ),
        "fa": (
            "تشکر، نامهٔ شما را خواندم. فقط بررسی می‌کنم که واقعاً از طرف ادارهٔ "
            "USCIS باشد. چند لحظه بعد دوباره برایتان می‌نویسم."
        ),
    },
    # C45: research's instant checks found signs of a scam. No explanation, never a
    # call; the reasons come from the deep pass only if the user asks.
    "letter.looks_like_scam": {
        "es": (
            "Gracias por enviármela. Me preocupa que esta carta sea una estafa: "
            "tiene señales que las cartas reales de USCIS no tienen. Por favor, no "
            "pague nada, no llame a ningún número de la carta y no dé sus datos. "
            "Hizo bien en consultarlo primero. Escríbame si tiene preguntas."
        ),
        "en": (
            "Thank you for sending this. I'm worried this letter may be a scam: it "
            "has signs that real USCIS letters don't. Please don't pay anything, "
            "don't call any number on it, and don't give out your details. You did "
            "the right thing by checking first. Write to me if you have questions."
        ),
        "fa": (
            "تشکر که این را فرستادید. نگران هستم که این نامه کلاهبرداری باشد: "
            "نشانه‌هایی دارد که نامه‌های اصلی ادارهٔ USCIS ندارند. لطفاً هیچ پولی "
            "پرداخت نکنید، به هیچ شماره‌ای در نامه زنگ نزنید و معلومات شخصی خود را "
            "به کسی ندهید. خوب کردید که اول بررسی کردید. اگر سوالی دارید، برایم "
            "بنویسید."
        ),
    },
    # C45: the end of an explanation sent before the verdict came.
    "letter.still_checking": {
        "es": (
            "⚠️ Todavía estoy verificando que esta carta de verdad venga de USCIS. "
            "Hasta confirmarlo, por favor no pague nada ni llame a ningún número de "
            "la carta. Le escribo cuando lo sepa."
        ),
        "en": (
            "⚠️ I'm still checking that this letter really comes from USCIS. Until "
            "I'm sure, please don't pay anything or call any number on it. I'll "
            "write again when I know."
        ),
        "fa": (
            "⚠️ هنوز بررسی می‌کنم که این نامه واقعاً از طرف ادارهٔ USCIS باشد. تا "
            "وقتی مطمئن نشده‌ام، لطفاً هیچ پولی پرداخت نکنید و به هیچ شماره‌ای در "
            "نامه زنگ نزنید. وقتی معلوم شد، دوباره برایتان می‌نویسم."
        ),
    },
    "letter.explain_failed": {
        "es": (
            "Leí su carta, pero no pude escribirle la explicación ahora. "
            "Escríbame «¿qué dice mi carta?» y se la explico."
        ),
        "en": (
            "I read your letter, but I couldn't write up the explanation just now. "
            'Write me "what does my letter say?" and I\'ll explain it.'
        ),
        "fa": (
            "نامهٔ شما را خواندم، اما حالا نتوانستم توضیح آن را بنویسم. "
            "برایم بنویسید «نامهٔ من چه می‌گوید؟» تا برایتان توضیح بدهم."
        ),
    },
    # Plan.md → Failure rules: unreadable photo (C9).
    "letter.which_letter": {
        "es": (
            "Antes de explicarle, necesito una respuesta: parece que las fotos son de "
            "cartas distintas. ¿Cuál carta leo primero? Respóndame en pocas palabras."
        ),
        "en": (
            "Before I explain, I need one answer: these photos look like they come "
            "from different letters. Which letter should I read first? Reply in a few "
            "words."
        ),
        "fa": (
            "پیش از توضیح، به یک جواب ضرورت دارم: معلوم می‌شود که این عکس‌ها از "
            "نامه‌های مختلف هستند. اول کدام نامه را بخوانم؟ در چند کلمه جواب بدهید."
        ),
    },
    "letter.reading_again": {
        "es": "Gracias. Ahora leo esa carta y le escribo en cuanto termine.",
        "en": "Thanks. I'm reading that letter now and will write as soon as I'm done.",
        "fa": "تشکر. حالا همان نامه را می‌خوانم و وقتی تمام شد، برایتان می‌نویسم.",
    },
    "research_question.not_found": {
        "es": (
            "No encontré una respuesta en una fuente oficial para su pregunta. "
            "Puede preguntarle a un abogado o a un representante acreditado por el DOJ."
        ),
        "en": (
            "I couldn't find an answer to your question in an official source. "
            "A lawyer or a DOJ-accredited representative can help."
        ),
        "fa": (
            "برای سوال شما در یک منبع رسمی جوابی پیدا نکردم. "
            + _LEGAL_HELP_FA
            + " می‌تواند کمک کند."
        ),
    },
    "research_question.legal_advice": {
        "es": (
            "No puedo darle consejos legales sobre su caso. Un abogado o un "
            "representante acreditado por el DOJ puede ayudarle, muchas veces gratis."
        ),
        "en": (
            "I can't give legal advice about your case. A lawyer or a DOJ-accredited "
            "representative can help, often for free."
        ),
        "fa": (
            "من نمی‌توانم دربارهٔ دوسیهٔ شما مشورهٔ حقوقی بدهم. "
            + _LEGAL_HELP_FA
            + " می‌تواند کمک کند، اکثراً به شکل رایگان."
        ),
    },
    "research_question.asylum_claim": {
        "es": (
            "No hablo sobre los detalles de su solicitud de asilo. Un abogado o un "
            "representante acreditado por el DOJ puede ayudarle con eso."
        ),
        "en": (
            "I don't discuss the details of your asylum claim. A lawyer or a "
            "DOJ-accredited representative can help with that."
        ),
        "fa": (
            "من دربارهٔ جزئیات درخواست پناهندگی شما صحبت نمی‌کنم. "
            + _LEGAL_HELP_FA
            + " می‌تواند در این مورد کمک کند."
        ),
    },
    "research_question.untranslated": {
        "es": (
            "Encontré una respuesta en una fuente oficial, pero no pude traducirla. "
            "Puede leerla aquí:\n{sources}"
        ),
        "en": (
            "I found an answer in an official source but couldn't translate it. "
            "You can read it here:\n{sources}"
        ),
        "fa": (
            "در یک منبع رسمی جوابی پیدا کردم، اما نتوانستم آن را ترجمه کنم. "
            "می‌توانید آن را اینجا بخوانید:\n{sources}"
        ),
    },
    "research_question.failed": {
        "es": "No pude buscar la respuesta ahora. Pregúnteme de nuevo en un rato.",
        "en": "I couldn't look that up right now. Ask me again in a little while.",
        "fa": "حالا نتوانستم جواب را پیدا کنم. کمی بعد دوباره از من بپرسید.",
    },
    "letter.retake": {
        "es": (
            "No pude leer bien la foto. ¿Me puede enviar otra? Ponga la carta sobre "
            "una mesa con buena luz, con toda la página dentro de la foto y sin sombras."
        ),
        "en": (
            "I couldn't read the photo well. Could you send another one? Put the "
            "letter on a table in good light, with the whole page in the photo and "
            "no shadows."
        ),
        "fa": (
            "نتوانستم عکس را خوب بخوانم. می‌توانید یک عکس دیگر بفرستید؟ نامه را در "
            "روشنی خوب روی یک میز بگذارید، طوری که تمام صفحه در عکس باشد و سایه "
            "نداشته باشد."
        ),
    },
    "letter.retake_tip": {
        "es": "No pude leer bien la foto. {tip} ¿Me puede enviar otra?",
        "en": "I couldn't read the photo well. {tip} Could you send another one?",
        "fa": "نتوانستم عکس را خوب بخوانم. {tip} می‌توانید یک عکس دیگر بفرستید؟",
    },
    # R2 (Goal 6.2).
    "verification.verified": _VERIFIED,
    "verification.verified_no_call": {
        "es": (
            "Revisé su carta con la información oficial de uscis.gov: es auténtica. ✅ "
            "Por ahora no hace falta llamar a USCIS. Escríbame si tiene preguntas."
        ),
        "en": (
            "I checked your letter against official information on uscis.gov: it's "
            "genuine. ✅ There's no need to call USCIS for now. Write to me if you "
            "have questions."
        ),
        "fa": (
            "نامهٔ شما را با معلومات رسمی ویب سایت uscis.gov بررسی کردم: نامه اصلی "
            "است. ✅ فعلاً ضرورت به تماس با ادارهٔ USCIS نیست. اگر سوالی دارید، "
            "برایم بنویسید."
        ),
    },
    # Plan.md → Failure rules: a letter that looks like a scam. Never offers a call.
    "verification.suspicious": {
        "es": (
            "⚠️ Cuidado: esta carta tiene señales de fraude:\n{red_flags}\n"
            "No llame a los números de la carta, no pague nada y no dé sus datos. "
            "Escríbame si tiene preguntas."
        ),
        "en": (
            "⚠️ Careful: this letter has signs of a scam:\n{red_flags}\n"
            "Don't call the numbers on the letter, don't pay anything, and don't give "
            "out your details. Write to me if you have questions."
        ),
        "fa": (
            "⚠️ احتیاط: این نامه نشانه‌های کلاهبرداری دارد:\n{red_flags}\n"
            "به شماره‌های داخل نامه زنگ نزنید، هیچ پولی پرداخت نکنید و معلومات "
            "شخصی خود را به کسی ندهید. اگر سوالی دارید، برایم بنویسید."
        ),
    },
    "verification.suspicious_generic": {
        "es": (
            "⚠️ Cuidado: esta carta tiene señales de fraude. No llame a los números "
            "de la carta, no pague nada y no dé sus datos. Escríbame si tiene preguntas."
        ),
        "en": (
            "⚠️ Careful: this letter has signs of a scam. Don't call the numbers on "
            "the letter, don't pay anything, and don't give out your details. Write "
            "to me if you have questions."
        ),
        "fa": (
            "⚠️ احتیاط: این نامه نشانه‌های کلاهبرداری دارد. به شماره‌های داخل نامه "
            "زنگ نزنید، هیچ پولی پرداخت نکنید و معلومات شخصی خود را به کسی ندهید. "
            "اگر سوالی دارید، برایم بنویسید."
        ),
    },
    # Plan.md → Failure rules: verification unknown. No call offer, and a gentle
    # caution; it ends the explanation, or follows it alone (C45).
    "verification.unknown": {
        "es": (
            "No pude confirmar que esta carta de verdad venga de USCIS, así que "
            "todavía no le ofrezco llamar. Por precaución, no pague nada ni llame a "
            "ningún número de la carta. Puede revisar su caso en uscis.gov."
        ),
        "en": (
            "I couldn't confirm that this letter really comes from USCIS, so I won't "
            "offer to call yet. To be safe, please don't pay anything or call any "
            "number on it. You can check your case at uscis.gov."
        ),
        "fa": (
            "نتوانستم تأیید کنم که این نامه واقعاً از طرف ادارهٔ USCIS است، به همین "
            "خاطر هنوز پیشنهاد تماس نمی‌کنم. برای احتیاط، لطفاً هیچ پولی پرداخت "
            "نکنید و به هیچ شماره‌ای در نامه زنگ نزنید. می‌توانید دوسیهٔ خود را در "
            "ویب سایت uscis.gov بررسی کنید."
        ),
    },
    # Consent (Goal 6.3, C21). A YES covers one call; every call asks again.
    "consent.request": {lang: _WANT_CALL[lang] + _CALL_ASK[lang] for lang in _CALL_ASK},
    "consent.request_generic": {
        lang: _WANT_CALL_GENERIC[lang] + _CALL_ASK[lang] for lang in _CALL_ASK
    },
    # The verdict and the consent request in one message, so the user has one thing
    # to answer (conversation.py).
    "verification.verified_call": {
        lang: _VERIFIED[lang] + "\n" + _WANT_CALL[lang] + _CALL_ASK[lang]
        for lang in _CALL_ASK
    },
    "verification.verified_call_generic": {
        lang: _VERIFIED[lang] + "\n" + _WANT_CALL_GENERIC[lang] + _CALL_ASK[lang]
        for lang in _CALL_ASK
    },
    "consent.reprompt": {
        "es": "Por favor responda 1 si quiere que llame a USCIS, o 2 si no.",
        "en": "Please reply 1 if you'd like me to call USCIS, or 2 if not.",
        "fa": (
            "لطفاً اگر می‌خواهید با ادارهٔ USCIS تماس بگیرم، ۱ را بفرستید، و اگر نه، ۲ را."
        ),
    },
    # Says we're calling, so no call.dialing follows it (pacing: one message).
    "consent.given": {
        "es": "Gracias. Estoy llamando a USCIS ahora; le aviso cuando conteste una persona.",
        "en": "Thank you. I'm calling USCIS now and will let you know when a person answers.",
        "fa": (
            "تشکر. حالا با ادارهٔ USCIS تماس می‌گیرم و وقتی یک شخص جواب داد، به شما "
            "خبر می‌دهم."
        ),
    },
    "consent.declined": {
        "es": "De acuerdo, no voy a llamar. Si cambia de opinión, escríbame.",
        "en": "All right, I won't call. If you change your mind, write to me.",
        "fa": "خوب، تماس نمی‌گیرم. اگر نظر شما تغییر کرد، برایم بنویسید.",
    },
    "consent.unavailable": {
        "es": (
            "Lo siento, no puedo hacer esa llamada ahora. Escríbame si quiere que "
            "lo intente más tarde."
        ),
        "en": "Sorry, I can't make that call right now. Write to me if you'd like me to try later.",
        "fa": (
            "معذرت می‌خواهم، حالا نمی‌توانم این تماس را بگیرم. اگر می‌خواهید بعداً "
            "دوباره کوشش کنم، برایم بنویسید."
        ),
    },
    # Post-call summary (Goal 6.4). The next steps are translated free text.
    "summary.reference": {
        "es": "Número de referencia de la llamada: {reference}",
        "en": "Reference number for the call: {reference}",
        "fa": "شمارهٔ مرجع این تماس: {reference}",
    },
    "summary.deadlines": {
        "es": "📅 Fechas importantes: {dates}",
        "en": "📅 Important dates: {dates}",
        "fa": "📅 تاریخ‌های مهم: {dates}",
    },
    "summary.unavailable": {
        "es": (
            "La llamada con USCIS terminó. No pude escribirle el resumen ahora; "
            "escríbame y se lo explico."
        ),
        "en": (
            "The call with USCIS is over. I couldn't write up the summary just now; "
            "write to me and I'll explain it."
        ),
        "fa": (
            "تماس با ادارهٔ USCIS تمام شد. حالا نتوانستم خلاصهٔ آن را بنویسم؛ "
            "برایم بنویسید تا برایتان توضیح بدهم."
        ),
    },
    # Plan.md → Failure rules: hold exceeded max. A retry asks for consent again (C21).
    "summary.call_failed": {
        "es": (
            "No pude completar la llamada con USCIS: la espera fue demasiado larga "
            "o la llamada se cortó."
        ),
        "en": (
            "I couldn't complete the call with USCIS: the wait was too long or the "
            "call dropped."
        ),
        "fa": (
            "نتوانستم تماس با ادارهٔ USCIS را تمام کنم: انتظار خیلی طولانی شد "
            "یا تماس قطع شد."
        ),
    },
    "summary.cancelled": {
        "es": (
            "Terminé la llamada con USCIS, como me pidió. Escríbame cuando quiera "
            "que vuelva a llamar."
        ),
        "en": (
            "I ended the call with USCIS, as you asked. Write to me whenever you'd "
            "like me to call again."
        ),
        "fa": (
            "طوری که خواسته بودید، تماس با ادارهٔ USCIS را قطع کردم. هر وقت "
            "خواستید دوباره تماس بگیرم، برایم بنویسید."
        ),
    },
    "summary.unreachable_followup": {
        "es": (
            "Si quiere, puedo llamar otra vez a USCIS y avisarle cuando conteste "
            "una persona."
        ),
        "en": "If you'd like, I can call USCIS again and let you know when a person answers.",
        "fa": (
            "اگر بخواهید، می‌توانم دوباره با ادارهٔ USCIS تماس بگیرم و وقتی یک شخص "
            "جواب داد، به شما خبر بدهم."
        ),
    },
    # C22: suggest closing; the user decides (the turn's close_case tool).
    "summary.suggest_close": {
        "es": (
            "Parece que esta carta ya está resuelta. Si ya no necesita ayuda con "
            "ella, escríbame «cerrar» y la cierro."
        ),
        "en": (
            "It looks like this letter is taken care of. If you don't need more help "
            'with it, write "close" and I\'ll close it.'
        ),
        "fa": (
            "معلوم می‌شود که کار این نامه تمام شده است. اگر دیگر در مورد آن به کمک "
            "ضرورت ندارید، «بستن» بنویسید تا آن را ببندم."
        ),
    },
    # Call status (P2). The orchestrator picks which call events become these (C36).
    # Exactly the five in USER_MESSAGING_EVENTS; after the call, the user gets the
    # post-call summary instead of a "call ended" message.
    "call.dialing": {
        "es": "Estoy llamando a USCIS ahora.",
        "en": "Calling USCIS now.",
        "fa": "حالا با ادارهٔ USCIS تماس می‌گیرم.",
    },
    "call.on_hold": {
        "es": "Sigo en espera con USCIS. Le aviso cuando conteste una persona.",
        "en": "Still on hold with USCIS. I'll let you know when a person answers.",
        "fa": (
            "هنوز پشت خط ادارهٔ USCIS منتظر هستم. وقتی یک شخص جواب داد، "
            "به شما خبر می‌دهم."
        ),
    },
    "call.human_detected": {
        "es": "Contestó una persona. Le estoy llamando ahora; por favor conteste.",
        "en": "Someone picked up. I'm calling you now; please answer.",
        "fa": "یک شخص جواب داد. حالا به شما زنگ می‌زنم؛ لطفاً تیلفون را جواب بدهید.",
    },
    # Only for a second ring: the first is covered by call.human_detected.
    "call.user_dialed": {
        "es": (
            "USCIS sigue esperándole en la línea. Le estoy llamando otra vez; "
            "por favor conteste."
        ),
        "en": "USCIS is still waiting for you. I'm calling you again; please answer.",
        "fa": (
            "ادارهٔ USCIS هنوز پشت خط منتظر شماست. دوباره به شما زنگ می‌زنم؛ "
            "لطفاً تیلفون را جواب بدهید."
        ),
    },
    "call.user_unreachable": {
        "es": (
            "No pude comunicarme con usted, así que le dije a USCIS que usted "
            "volverá a llamar y terminé la llamada."
        ),
        "en": (
            "I couldn't reach you, so I told USCIS you'd call back and ended the call."
        ),
        "fa": (
            "نتوانستم با شما تماس بگیرم، به همین خاطر به ادارهٔ USCIS گفتم که خود "
            "شما دوباره زنگ می‌زنید و تماس را ختم کردم."
        ),
    },
    # C15: facts the memory writer is holding until the user says it's OK. {facts}
    # is a translated bullet list.
    "memory.ask_save": {
        "es": (
            "¿Puedo guardar esto, para no tener que preguntárselo otra vez?\n"
            "{facts}\n"
            "Solo lo uso para ayudarle, y puede borrarlo cuando quiera.\n"
            "1 Sí, guárdelo\n2 No, no lo guarde"
        ),
        "en": (
            "May I remember this, so I don't have to ask you again?\n"
            "{facts}\n"
            "I only use it to help you, and you can delete it any time.\n"
            "1 Yes, save it\n2 No, don't save it"
        ),
        "fa": (
            "اجازه می‌دهید این را نگه دارم، تا دوباره از شما نپرسم؟\n"
            "{facts}\n"
            "فقط برای کمک به شما از آن استفاده می‌کنم، و هر وقت بخواهید، "
            "می‌توانید آن را پاک کنید.\n"
            "۱ بلی، نگه دارید\n۲ نخیر، نگه ندارید"
        ),
    },
    "memory.saved": {
        "es": "Listo, lo guardé.",
        "en": "Done, I saved it.",
        "fa": "خوب، نگه داشتم.",
    },
    "memory.not_saved": {
        "es": "De acuerdo, no lo guardé.",
        "en": "All right, I didn't save it.",
        "fa": "خوب، نگه نداشتم.",
    },
}

# A failed call's summary and the new consent request (C21) in one message.
TEMPLATES["summary.call_failed_retry"] = {
    lang: TEMPLATES["summary.call_failed"][lang]
    + "\n"
    + _WANT_CALL[lang]
    + _CALL_ASK[lang]
    for lang in LANGUAGES
}
TEMPLATES["summary.call_failed_retry_generic"] = {
    lang: TEMPLATES["summary.call_failed"][lang]
    + "\n"
    + _WANT_CALL_GENERIC[lang]
    + _CALL_ASK[lang]
    for lang in LANGUAGES
}


def render(template_id: str, language: LanguageCode | None, **values: object) -> str:
    """The template in `language`, ready to send. With no language yet (before the
    user picks one), every supported language, one after the other."""
    texts = TEMPLATES[template_id]
    if language is None:
        # A text shared by several languages (the menu) goes out once, as written.
        first_language: dict[str, LanguageCode] = {}
        for lang in LANGUAGES:
            first_language.setdefault(texts[lang], lang)
        return "\n\n".join(
            _render(text, lang, values) for text, lang in first_language.items()
        )
    return _render(texts[language], language, values)


def _render(text: str, language: LanguageCode, values: dict[str, object]) -> str:
    """Numbers in the language's digits; direction isolates for right-to-left."""
    local = {
        name: local_digits(str(value), language) if isinstance(value, int) else value
        for name, value in values.items()
    }
    return for_display(text.format(**local), language)
