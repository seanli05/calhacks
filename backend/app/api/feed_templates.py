"""Pre-translated feed text for the event types on the demo screen (C23).

Each type has variants per language, most specific first. The feed uses the first
variant whose fields are all present, and the last variant of every type has no
fields, so an event with missing `data` still renders. Types not listed here show
their `summary_en`.

The `data` fields each template expects (emitters: please include them):

| Event type | `data` fields | Example |
|---|---|---|
| `verification.verified` | `source`: the official domain checked | `"uscis.gov"` |
| `consent.requested` | `agency`* | `"USCIS"` |
| `call.dialing` | `agency`* | `"USCIS"` |
| `call.menu_choice` | `digit`: the key pressed (Plan.md's example) | `"2"` |
| `call.ask_user_answered` | `choice`: the 1-based option picked | `1` |
| `call.ask_user_timeout` | `default_option`: the option taken | `1` |
| `call.on_hold` | `agency`* | `"USCIS"` |
| `call.human_detected` | `agency`* | `"USCIS"` |
| `call.user_joined` | `agency`* | `"USCIS"` |
| `call.ended` | `minutes`: whole minutes the call lasted | `6` |
| `memory.fact_saved` | `fact_id` (the text is looked up, never sent, C27) | `"fact_…"` |
| `memory.fact_superseded` | `fact_id`: the new fact | `"fact_…"` |
| `memory.fact_pending_consent` | `fact_id` | `"fact_…"` |
| `case.document_added` | `document_id` (marks the item deleted once it's gone) | `"doc_…"` |

\\* `agency` falls back to the case's issuer from R1 when the event doesn't carry it.
Every other listed type takes no fields. The four delete types already get theirs
from `app.db.deletes`.
"""

from string import Formatter

Variants = dict[str, list[str]]

HIDDEN: frozenset[str] = frozenset(
    {"research.search", "research.fetch", "research.check", "call.menu_heard"}
)
"""Step logs, many per check or call, for debugging, never in the feed: the deep
pass's lookups, and every menu prompt the phone agent hears (its choices still
show as `call.menu_choice`; the case view's headline says it's in the menu)."""

TEMPLATES: dict[str, Variants] = {
    "case.created": {
        "en": ["We received your letter"],
        "es": ["Recibimos tu carta"],
    },
    "case.document_added": {
        "en": ["We added a page to your letter"],
        "es": ["Agregamos una página a tu carta"],
    },
    "case.closed": {
        "en": ["We closed this case"],
        "es": ["Cerramos este caso"],
    },
    "research.fast_started": {
        "en": ["We're reading your letter"],
        "es": ["Estamos leyendo tu carta"],
    },
    "research.fast_done": {
        "en": ["We explained your letter"],
        "es": ["Te explicamos tu carta"],
    },
    "research.deep_started": {
        "en": ["We're checking that the letter is real"],
        "es": ["Estamos revisando que la carta sea real"],
    },
    "research.deep_done": {
        "en": ["We finished checking your letter"],
        "es": ["Terminamos de revisar tu carta"],
    },
    "research.fast_slow": {
        "en": ["Still reading your letter"],
        "es": ["Seguimos leyendo tu carta"],
    },
    "research.fast_failed": {
        "en": ["We couldn't finish reading your letter"],
        "es": ["No pudimos terminar de leer tu carta"],
    },
    "research.deep_failed": {
        "en": ["We couldn't finish checking your letter"],
        "es": ["No pudimos terminar de revisar tu carta"],
    },
    "research.needs_user_input": {
        "en": ["We need one answer from you"],
        "es": ["Necesitamos una respuesta tuya"],
    },
    "research.question_started": {
        "en": ["Looking up your question"],
        "es": ["Estamos buscando la respuesta a tu pregunta"],
    },
    "research.question_done": {
        "en": ["We found an answer to your question"],
        "es": ["Encontramos una respuesta a tu pregunta"],
    },
    "research.question_failed": {
        "en": ["We couldn't find an official answer"],
        "es": ["No encontramos una respuesta oficial"],
    },
    "verification.verified": {
        "en": [
            "We confirmed the letter is real ({source})",
            "We confirmed the letter is real",
        ],
        "es": [
            "Confirmamos que la carta es real ({source})",
            "Confirmamos que la carta es real",
        ],
    },
    "verification.suspicious": {
        "en": ["This letter may not be real. Don't call any number printed on it"],
        "es": [
            (
                "Es posible que esta carta no sea real. "
                "No llames a ningún número que aparezca en ella"
            )
        ],
    },
    "verification.unknown": {
        "en": ["We couldn't confirm whether the letter is real"],
        "es": ["No pudimos confirmar si la carta es real"],
    },
    "consent.requested": {
        "en": [
            "We asked if you want us to call {agency}",
            "We asked if you want us to make the call",
        ],
        "es": [
            "Te preguntamos si quieres que llamemos a {agency}",
            "Te preguntamos si quieres que hagamos la llamada",
        ],
    },
    "consent.given": {
        "en": ["You said yes to the call"],
        "es": ["Dijiste que sí a la llamada"],
    },
    "consent.declined": {
        "en": ["You said no to the call"],
        "es": ["Dijiste que no a la llamada"],
    },
    "call.dialing": {
        "en": [
            "We called the official {agency} number",
            "We called the official number",
        ],
        "es": ["Llamamos al número oficial de {agency}", "Llamamos al número oficial"],
    },
    "call.menu_heard": {
        "en": ["We heard the phone menu"],
        "es": ["Escuchamos el menú del teléfono"],
    },
    "call.menu_choice": {
        "en": ["We chose option {digit} in the menu", "We chose an option in the menu"],
        "es": ["Elegimos la opción {digit} del menú", "Elegimos una opción del menú"],
    },
    "call.ask_user": {
        "en": ["We sent you a question about the call"],
        "es": ["Te enviamos una pregunta sobre la llamada"],
    },
    "call.ask_user_answered": {
        "en": ["You chose option {choice}", "You answered our question"],
        "es": ["Elegiste la opción {choice}", "Respondiste nuestra pregunta"],
    },
    "call.ask_user_timeout": {
        "en": [
            "No answer in time, so we chose option {default_option}, the safest one",
            "No answer in time, so we chose the safest option",
        ],
        "es": [
            (
                "No hubo respuesta a tiempo, así que elegimos la opción "
                "{default_option}, la más segura"
            ),
            "No hubo respuesta a tiempo, así que elegimos la opción más segura",
        ],
    },
    "call.ask_user_late_reply": {
        "en": ["Your answer came after we had already chosen"],
        "es": ["Tu respuesta llegó después de que ya habíamos elegido"],
    },
    "call.on_hold": {
        "en": ["We're on hold with {agency}", "We're on hold"],
        "es": ["Estamos en espera con {agency}", "Estamos en espera"],
    },
    "call.human_detected": {
        "en": ["A person from {agency} answered", "A person answered"],
        "es": ["Contestó una persona de {agency}", "Contestó una persona"],
    },
    "call.user_dialed": {
        "en": ["We're calling you to connect you"],
        "es": ["Te llamamos para conectarte"],
    },
    "call.user_joined": {
        "en": ["We connected you with {agency}", "We connected you to the call"],
        "es": ["Te conectamos con {agency}", "Te conectamos a la llamada"],
    },
    "call.user_unreachable": {
        "en": ["We couldn't reach you by phone"],
        "es": ["No pudimos comunicarnos contigo por teléfono"],
    },
    "call.ended": {
        "en": ["The call ended after {minutes} minutes", "The call ended"],
        "es": ["La llamada terminó después de {minutes} minutos", "La llamada terminó"],
    },
    "memory.fact_saved": {
        "en": ["Saved: {fact}", "We saved a fact about you"],
        "es": ["Guardamos: {fact}", "Guardamos un dato sobre ti"],
    },
    "memory.fact_superseded": {
        "en": ["Updated: {fact}", "We updated a fact about you"],
        "es": ["Actualizamos: {fact}", "Actualizamos un dato sobre ti"],
    },
    "memory.fact_pending_consent": {
        "en": [
            "We'll ask you before saving: {fact}",
            "We'll ask you before saving a fact",
        ],
        "es": [
            "Te preguntaremos antes de guardar: {fact}",
            "Te preguntaremos antes de guardar un dato",
        ],
    },
    "fact.deleted": {
        "en": ["You deleted a fact"],
        "es": ["Borraste un dato"],
    },
    "document.deleted": {
        "en": ["You deleted the letter"],
        "es": ["Borraste la carta"],
    },
    "transcript.deleted": {
        "en": ["You deleted a call transcript"],
        "es": ["Borraste la transcripción de una llamada"],
    },
    "user.deleted_all": {
        "en": ["You deleted everything we knew about you"],
        "es": ["Borraste todo lo que sabíamos de ti"],
    },
}


def fields_of(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def fill(variants: list[str], values: dict[str, str]) -> str:
    """The first variant whose fields are all in `values`, filled in."""
    for template in variants:
        if fields_of(template) <= values.keys():
            return template.format(**values)
    raise ValueError(f"no variant fits {sorted(values)}: {variants}")


def render(
    event_type: str, lang: str, values: dict[str, str], values_en: dict[str, str]
) -> tuple[str, str] | None:
    """`(text in lang, English)`, or None when the type has no template. `values`
    fill the text in `lang`, `values_en` the English. A language without templates
    gets the English."""
    variants = TEMPLATES.get(event_type)
    if variants is None:
        return None
    en = fill(variants["en"], values_en)
    if lang not in variants:
        return en, en
    return fill(variants[lang], values), en
