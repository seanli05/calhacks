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
    "media.download_failed": {
        "es": "Lo siento, no pude descargar ese archivo. ¿Me lo puede enviar otra vez?",
        "en": "Sorry, I couldn't download that file. Could you send it again?",
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
