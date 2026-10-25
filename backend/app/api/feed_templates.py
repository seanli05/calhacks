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

from app.api.common import localize
from app.translation.script import local_digits

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
        "es": ["Recibimos su carta"],
        "fa": ["نامهٔ شما را گرفتیم"],
    },
    "case.document_added": {
        "en": ["We added a page to your letter"],
        "es": ["Agregamos una página a su carta"],
        "fa": ["یک صفحه به نامهٔ شما اضافه کردیم"],
    },
    "case.closed": {
        "en": ["We closed this case"],
        "es": ["Cerramos este caso"],
        "fa": ["این دوسیه را بستیم"],
    },
    "research.fast_started": {
        "en": ["We're reading your letter"],
        "es": ["Estamos leyendo su carta"],
        "fa": ["نامهٔ شما را می‌خوانیم"],
    },
    "research.fast_done": {
        "en": ["We explained your letter"],
        "es": ["Le explicamos su carta"],
        "fa": ["نامهٔ شما را توضیح دادیم"],
    },
    "research.deep_started": {
        "en": ["We're checking that the letter is real"],
        "es": ["Estamos revisando que la carta sea real"],
        "fa": ["بررسی می‌کنیم که نامه اصلی است"],
    },
    "research.deep_done": {
        "en": ["We finished checking your letter"],
        "es": ["Terminamos de revisar su carta"],
        "fa": ["بررسی نامهٔ شما تمام شد"],
    },
    "research.fast_slow": {
        "en": ["Still reading your letter"],
        "es": ["Seguimos leyendo su carta"],
        "fa": ["هنوز نامهٔ شما را می‌خوانیم"],
    },
    "research.fast_failed": {
        "en": ["We couldn't finish reading your letter"],
        "es": ["No pudimos terminar de leer su carta"],
        "fa": ["نتوانستیم خواندن نامهٔ شما را تمام کنیم"],
    },
    "research.deep_failed": {
        "en": ["We couldn't finish checking your letter"],
        "es": ["No pudimos terminar de revisar su carta"],
        "fa": ["نتوانستیم بررسی نامهٔ شما را تمام کنیم"],
    },
    "research.needs_user_input": {
        "en": ["We need one answer from you"],
        "es": ["Necesitamos una respuesta suya"],
        "fa": ["به یک جواب از شما ضرورت داریم"],
    },
    "research.question_started": {
        "en": ["Looking up your question"],
        "es": ["Estamos buscando la respuesta a su pregunta"],
        "fa": ["جواب سوال شما را جستجو می‌کنیم"],
    },
    "research.question_done": {
        "en": ["We found an answer to your question"],
        "es": ["Encontramos una respuesta a su pregunta"],
        "fa": ["برای سوال شما جوابی پیدا کردیم"],
    },
    "research.question_failed": {
        "en": ["We couldn't find an official answer"],
        "es": ["No encontramos una respuesta oficial"],
        "fa": ["جواب رسمی پیدا نکردیم"],
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
        "fa": [
            "تأیید کردیم که نامه اصلی است ({source})",
            "تأیید کردیم که نامه اصلی است",
        ],
    },
    "verification.suspicious": {
        "en": ["This letter may not be real. Don't call any number printed on it"],
        "es": [
            (
                "Es posible que esta carta no sea real. "
                "No llame a ningún número que aparezca en ella"
            )
        ],
        "fa": ["شاید این نامه اصلی نباشد. به هیچ شماره‌ای که روی آن است زنگ نزنید"],
    },
    "verification.unknown": {
        "en": ["We couldn't confirm whether the letter is real"],
        "es": ["No pudimos confirmar si la carta es real"],
        "fa": ["نتوانستیم تأیید کنیم که نامه اصلی است"],
    },
    "consent.requested": {
        "en": [
            "We asked if you want us to call {agency}",
            "We asked if you want us to make the call",
        ],
        "es": [
            "Le preguntamos si quiere que llamemos a {agency}",
            "Le preguntamos si quiere que hagamos la llamada",
        ],
        "fa": [
            "پرسیدیم که آیا می‌خواهید با ادارهٔ {agency} تماس بگیریم",
            "پرسیدیم که آیا می‌خواهید از طرف شما تماس بگیریم",
        ],
    },
    "consent.given": {
        "en": ["You said yes to the call"],
        "es": ["Usted dijo que sí a la llamada"],
        "fa": ["شما برای تماس «بلی» گفتید"],
    },
    "consent.declined": {
        "en": ["You said no to the call"],
        "es": ["Usted dijo que no a la llamada"],
        "fa": ["شما برای تماس «نخیر» گفتید"],
    },
    "call.dialing": {
        "en": [
            "We called the official {agency} number",
            "We called the official number",
        ],
        "es": ["Llamamos al número oficial de {agency}", "Llamamos al número oficial"],
        "fa": ["به شمارهٔ رسمی ادارهٔ {agency} زنگ زدیم", "به شمارهٔ رسمی زنگ زدیم"],
    },
    "call.menu_heard": {
        "en": ["We heard the phone menu"],
        "es": ["Escuchamos el menú del teléfono"],
        "fa": ["گزینه‌های سیستم تیلفونی را شنیدیم"],
    },
    "call.menu_choice": {
        "en": ["We chose option {digit} in the menu", "We chose an option in the menu"],
        "es": ["Elegimos la opción {digit} del menú", "Elegimos una opción del menú"],
        "fa": [
            "در سیستم تیلفونی گزینهٔ {digit} را انتخاب کردیم",
            "در سیستم تیلفونی یک گزینه را انتخاب کردیم",
        ],
    },
    "call.ask_user": {
        "en": ["We sent you a question about the call"],
        "es": ["Le enviamos una pregunta sobre la llamada"],
        "fa": ["دربارهٔ تماس یک سوال برای شما فرستادیم"],
    },
    "call.ask_user_answered": {
        "en": ["You chose option {choice}", "You answered our question"],
        "es": ["Usted eligió la opción {choice}", "Usted respondió nuestra pregunta"],
        "fa": ["شما گزینهٔ {choice} را انتخاب کردید", "شما به سوال ما جواب دادید"],
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
        "fa": [
            (
                "به وقت جوابی نرسید، به همین خاطر گزینهٔ {default_option} را "
                "انتخاب کردیم، که مطمئن‌ترین گزینه است"
            ),
            "به وقت جوابی نرسید، به همین خاطر مطمئن‌ترین گزینه را انتخاب کردیم",
        ],
    },
    "call.ask_user_late_reply": {
        "en": ["Your answer came after we had already chosen"],
        "es": ["Su respuesta llegó después de que ya habíamos elegido"],
        "fa": ["جواب شما بعد از آن رسید که ما انتخاب کرده بودیم"],
    },
    "call.on_hold": {
        "en": ["We're on hold with {agency}", "We're on hold"],
        "es": ["Estamos en espera con {agency}", "Estamos en espera"],
        "fa": ["پشت خط ادارهٔ {agency} منتظر هستیم", "پشت خط منتظر هستیم"],
    },
    "call.human_detected": {
        "en": ["A person from {agency} answered", "A person answered"],
        "es": ["Contestó una persona de {agency}", "Contestó una persona"],
        "fa": ["یک شخص از ادارهٔ {agency} جواب داد", "یک شخص جواب داد"],
    },
    "call.user_dialed": {
        "en": ["We're calling you to connect you"],
        "es": ["Le llamamos para conectarle"],
        "fa": ["به شما زنگ می‌زنیم تا وصل شوید"],
    },
    "call.user_joined": {
        "en": ["We connected you with {agency}", "We connected you to the call"],
        "es": ["Le conectamos con {agency}", "Le conectamos a la llamada"],
        "fa": ["شما را با ادارهٔ {agency} وصل کردیم", "شما را به تماس وصل کردیم"],
    },
    "call.user_unreachable": {
        "en": ["We couldn't reach you by phone"],
        "es": ["No pudimos comunicarnos con usted por teléfono"],
        "fa": ["نتوانستیم با تیلفون شما تماس بگیریم"],
    },
    "call.ended": {
        "en": ["The call ended after {minutes} min", "The call ended"],
        "es": ["La llamada terminó después de {minutes} min", "La llamada terminó"],
        "fa": ["تماس بعد از {minutes} دقیقه ختم شد", "تماس ختم شد"],
    },
    "memory.fact_saved": {
        "en": ["Saved: {fact}", "We saved a fact about you"],
        "es": ["Guardamos: {fact}", "Guardamos un dato sobre usted"],
        "fa": ["نگه داشتیم: {fact}", "یک معلومات دربارهٔ شما را نگه داشتیم"],
    },
    "memory.fact_superseded": {
        "en": ["Updated: {fact}", "We updated a fact about you"],
        "es": ["Actualizamos: {fact}", "Actualizamos un dato sobre usted"],
        "fa": ["تازه کردیم: {fact}", "یک معلومات دربارهٔ شما را تازه کردیم"],
    },
    "memory.fact_pending_consent": {
        "en": [
            "We'll ask you before saving: {fact}",
            "We'll ask you before saving a fact",
        ],
        "es": [
            "Le preguntaremos antes de guardar: {fact}",
            "Le preguntaremos antes de guardar un dato",
        ],
        "fa": [
            "پیش از نگه داشتن از شما می‌پرسیم: {fact}",
            "پیش از نگه داشتن یک معلومات از شما می‌پرسیم",
        ],
    },
    "fact.deleted": {
        "en": ["You deleted a fact"],
        "es": ["Usted borró un dato"],
        "fa": ["شما یک معلومات را پاک کردید"],
    },
    "document.deleted": {
        "en": ["You deleted the letter"],
        "es": ["Usted borró la carta"],
        "fa": ["شما نامه را پاک کردید"],
    },
    "transcript.deleted": {
        "en": ["You deleted a call transcript"],
        "es": ["Usted borró la transcripción de una llamada"],
        "fa": ["شما متن یک تماس را پاک کردید"],
    },
    "user.deleted_all": {
        "en": ["You deleted everything we knew about you"],
        "es": ["Usted borró todo lo que sabíamos de usted"],
        "fa": ["شما همه چیزهایی را که دربارهٔ شما می‌دانستیم پاک کردید"],
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
    fill the text in `lang`, `values_en` the English; a bare number ("2", "6") is
    written in the language's digits. A language without templates gets the English
    through the translation cache, English until it lands."""
    variants = TEMPLATES.get(event_type)
    if variants is None:
        return None
    en = fill(variants["en"], values_en)
    if lang not in variants:
        return localize(en, lang).text, en
    local = {k: local_digits(v, lang) if v.isdigit() else v for k, v in values.items()}
    return fill(variants[lang], local), en
