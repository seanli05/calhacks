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
