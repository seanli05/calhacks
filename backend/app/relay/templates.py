"""Pre-translated WhatsApp templates: `template_id -> {language: text}`.

Spanish uses formal usted. Every template must exist in every language in
LANGUAGES (a test checks). Placeholders use str.format: `{name}`.
"""

from app.contracts.common import LanguageCode

LANGUAGES: tuple[LanguageCode, ...] = ("es", "en")
"""Supported languages, in the order the language menu lists them."""

_MENU = (
    "Hola 👋 Hello\n"
    "¿En qué idioma prefiere que le escriba? / Which language would you like?\n"
    "1 Español\n"
    "2 English"
)

TEMPLATES: dict[str, dict[LanguageCode, str]] = {
    "language.confirm": {
        "es": "Parece que habla español. ¿Seguimos en español?\n1 Sí\n2 Otro idioma",
        "en": (
            "It looks like you're writing in English. Shall we continue in English?\n"
            "1 Yes\n2 Another language"
        ),
    },
    "language.menu": {"es": _MENU, "en": _MENU},
    "language.set": {
        "es": (
            "Perfecto, seguimos en español. Envíeme una foto de su carta, "
            "o escríbame su pregunta."
        ),
        "en": (
            "Great, we'll continue in English. Send me a photo of your letter, "
            "or write me your question."
        ),
    },
    "language.set_letter": {
        "es": (
            "Perfecto, seguimos en español. Recibí su carta. ¿Tiene más páginas? "
            "Envíelas ahora y las junto con la misma carta."
        ),
        "en": (
            "Great, we'll continue in English. I got your letter. Are there more "
            "pages? Send them now and I'll keep them with the same letter."
        ),
    },
    "letter.received": {
        "es": "Recibido. ¿Tiene más páginas? Envíelas ahora y las junto con la misma carta.",
        "en": "Got it. Are there more pages? Send them now and I'll keep them with the same letter.",
    },
    "letter.same_or_new": {
        "es": "¿Es otra página de la misma carta, o una carta nueva?\n1 Misma carta\n2 Carta nueva",
        "en": "Is this another page of the same letter, or a new letter?\n1 Same letter\n2 New letter",
    },
    "letter.pages_added": {
        "es": "Gracias, agregué la página a su carta.",
        "en": "Thanks, I added the page to your letter.",
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
    },
    # The orchestrator's turn failed (model or translation); never English instead.
    "orchestrator.unavailable": {
        "es": (
            "Lo siento, no pude responderle ahora. Por favor escríbame otra vez "
            "en unos minutos."
        ),
        "en": "Sorry, I couldn't answer just now. Please write to me again in a few minutes.",
    },
    "media.download_failed": {
        "es": "Lo siento, no pude descargar ese archivo. ¿Me lo puede enviar otra vez?",
        "en": "Sorry, I couldn't download that file. Could you send it again?",
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
    },
    "ask_user.reprompt": {
        "es": "Por favor responda solo con un número del 1 al {count}.",
        "en": "Please reply with just a number from 1 to {count}.",
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
    },
    # R1 (Goal 6.1). The explanation and checklist are translated free text; these
    # lines carry what must never be garbled, with dates formatted in code.
    "letter.appointment": {
        "es": "📅 Su entrevista: {date}, a las {time}. La dirección está en su carta.",
        "en": "📅 Your interview: {date}, at {time}. The address is on your letter.",
    },
    "letter.appointment_date": {
        "es": "📅 Su entrevista: {date}. Los detalles están en su carta.",
        "en": "📅 Your interview: {date}. The details are on your letter.",
    },
    "letter.deadline": {
        "es": "📅 Fecha límite: {date}.",
        "en": "📅 Deadline: {date}.",
    },
    "letter.checking": {
        "es": (
            "Ahora estoy verificando que la carta sea auténtica. "
            "Le escribo en unos minutos."
        ),
        "en": (
            "I'm now checking that this letter is legitimate. "
            "I'll write again in a few minutes."
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
    },
    "letter.reading_again": {
        "es": "Gracias. Ahora leo esa carta y le escribo en cuanto termine.",
        "en": "Thanks. I'm reading that letter now and will write as soon as I'm done.",
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
    },
    "research_question.failed": {
        "es": "No pude buscar la respuesta ahora. Pregúnteme de nuevo en un rato.",
        "en": "I couldn't look that up right now. Ask me again in a little while.",
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
    },
    "letter.retake_tip": {
        "es": "No pude leer bien la foto. {tip} ¿Me puede enviar otra?",
        "en": "I couldn't read the photo well. {tip} Could you send another one?",
    },
    # R2 (Goal 6.2).
    "verification.verified": {
        "es": "Revisé su carta con la información oficial de uscis.gov: es auténtica. ✅",
        "en": "I checked your letter against official information on uscis.gov: it's genuine. ✅",
    },
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
    },
    # Plan.md → Failure rules: verification unknown. No call offer; explain and ask.
    "verification.unknown": {
        "es": (
            "No pude confirmar si esta carta es auténtica, así que todavía no le "
            "ofrezco llamar a USCIS. Puedo explicarle lo que dice la carta, o usted "
            "puede revisar su caso en uscis.gov. ¿Qué prefiere?"
        ),
        "en": (
            "I couldn't confirm whether this letter is genuine, so I'm not offering "
            "to call USCIS yet. I can explain what the letter says, or you can check "
            "your case on uscis.gov. What would you like to do?"
        ),
    },
    # Consent (Goal 6.3, C21). A YES covers one call; every call asks again.
    "consent.request": {
        "es": (
            "¿Quiere que llame a USCIS por usted?\nPara qué: {goal}\n"
            "Yo espero en la línea. Cuando conteste una persona, le llamo a este "
            "número para que hable usted. No daré sus números de caso ni su fecha de "
            "nacimiento. Le pido permiso para cada llamada.\n"
            "1 Sí, llame\n2 No, gracias"
        ),
        "en": (
            "Would you like me to call USCIS for you?\nWhat for: {goal}\n"
            "I'll wait on the line. When a person answers, I'll call you at this "
            "number so you can talk to them. I won't give out your case numbers or "
            "your date of birth. I ask your permission for every call.\n"
            "1 Yes, call\n2 No, thanks"
        ),
    },
    "consent.request_generic": {
        "es": (
            "¿Quiere que llame a USCIS por usted sobre esta carta?\n"
            "Yo espero en la línea. Cuando conteste una persona, le llamo a este "
            "número para que hable usted. No daré sus números de caso ni su fecha de "
            "nacimiento. Le pido permiso para cada llamada.\n"
            "1 Sí, llame\n2 No, gracias"
        ),
        "en": (
            "Would you like me to call USCIS for you about this letter?\n"
            "I'll wait on the line. When a person answers, I'll call you at this "
            "number so you can talk to them. I won't give out your case numbers or "
            "your date of birth. I ask your permission for every call.\n"
            "1 Yes, call\n2 No, thanks"
        ),
    },
    "consent.reprompt": {
        "es": "Por favor responda 1 si quiere que llame a USCIS, o 2 si no.",
        "en": "Please reply 1 if you'd like me to call USCIS, or 2 if not.",
    },
    "consent.given": {
        "es": "Gracias. Preparo la llamada y le aviso cuando esté marcando.",
        "en": "Thank you. I'm setting up the call and will let you know when I'm dialing.",
    },
    "consent.declined": {
        "es": "De acuerdo, no voy a llamar. Si cambia de opinión, escríbame.",
        "en": "All right, I won't call. If you change your mind, write to me.",
    },
    "consent.unavailable": {
        "es": (
            "Lo siento, no puedo hacer esa llamada ahora. Escríbame si quiere que "
            "lo intente más tarde."
        ),
        "en": "Sorry, I can't make that call right now. Write to me if you'd like me to try later.",
    },
    # Post-call summary (Goal 6.4). The next steps are translated free text.
    "summary.reference": {
        "es": "Número de referencia de la llamada: {reference}",
        "en": "Reference number for the call: {reference}",
    },
    "summary.deadlines": {
        "es": "📅 Fechas importantes: {dates}",
        "en": "📅 Important dates: {dates}",
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
    },
    "summary.unreachable_followup": {
        "es": (
            "Si quiere, puedo llamar otra vez a USCIS y avisarle cuando conteste "
            "una persona."
        ),
        "en": "If you'd like, I can call USCIS again and let you know when a person answers.",
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
    },
    # Call status (P2). The orchestrator picks which call events become these (C36).
    # Exactly the four in USER_MESSAGING_EVENTS; after the call, the user gets the
    # post-call summary instead of a "call ended" message.
    "call.dialing": {
        "es": "Estoy llamando a USCIS ahora.",
        "en": "Calling USCIS now.",
    },
    "call.on_hold": {
        "es": "Sigo en espera con USCIS. Le aviso cuando conteste una persona.",
        "en": "Still on hold with USCIS. I'll let you know when a person answers.",
    },
    "call.human_detected": {
        "es": "Contestó una persona. Le estoy llamando ahora; por favor conteste.",
        "en": "Someone picked up. I'm calling you now; please answer.",
    },
    "call.user_unreachable": {
        "es": (
            "No pude comunicarme con usted, así que le dije a USCIS que usted "
            "volverá a llamar y terminé la llamada."
        ),
        "en": (
            "I couldn't reach you, so I told USCIS you'd call back and ended the call."
        ),
    },
}


def render(template_id: str, language: LanguageCode | None, **values: object) -> str:
    """The template in `language`. With no language yet (before the user picks one),
    every supported language, one after the other."""
    texts = TEMPLATES[template_id]
    if language is None:
        unique = dict.fromkeys(texts[lang] for lang in LANGUAGES)
        return "\n\n".join(text.format(**values) for text in unique)
    return texts[language].format(**values)
