"""Suggestion card text per language. `{days}` and `{item}` are filled in by
`app.api.suggestions`; a language missing here goes through the translation cache.
Prefills are what the user sends on WhatsApp, so they speak as the user."""

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "countdown_title_interview": "Your interview is in {days} days",
        "countdown_title_interview_1": "Your interview is tomorrow",
        "countdown_title_appointment": "Your appointment is in {days} days",
        "countdown_title_appointment_1": "Your appointment is tomorrow",
        "countdown_detail": "Review what to bring",
        "countdown_action": "Prepare",
        "countdown_prefill_interview": "What do I need to bring to my interview?",
        "countdown_prefill_appointment": "What do I need to bring to my appointment?",
        "glossary_title": "Key English words",
        "glossary_action": "Practice",
        "glossary_prefill": "I want to practice the English words for my interview",
        "checklist_title": "Don't forget: {item}",
        "checklist_detail": "We can help",
        "checklist_action": "Ask",
        "checklist_prefill": "How do I get {item}?",
    },
    "es": {
        "countdown_title_interview": "Su entrevista es en {days} días",
        "countdown_title_interview_1": "Su entrevista es mañana",
        "countdown_title_appointment": "Su cita es en {days} días",
        "countdown_title_appointment_1": "Su cita es mañana",
        "countdown_detail": "Repase qué llevar",
        "countdown_action": "Preparar",
        "countdown_prefill_interview": "¿Qué tengo que llevar a mi entrevista?",
        "countdown_prefill_appointment": "¿Qué tengo que llevar a mi cita?",
        "glossary_title": "Palabras clave en inglés",
        "glossary_action": "Practicar",
        "glossary_prefill": "Quiero practicar las palabras en inglés para mi entrevista",
        "checklist_title": "No olvide: {item}",
        "checklist_detail": "Le ayudamos",
        "checklist_action": "Preguntar",
        "checklist_prefill": "¿Cómo consigo {item}?",
    },
    "fa": {
        "countdown_title_interview": "مصاحبهٔ شما {days} روز بعد است",
        "countdown_title_interview_1": "مصاحبهٔ شما فردا است",
        "countdown_title_appointment": "وقت ملاقات شما {days} روز بعد است",
        "countdown_title_appointment_1": "وقت ملاقات شما فردا است",
        "countdown_detail": "ببینید چه چیزهایی را باید با خود بیاورید",
        "countdown_action": "آماده شوید",
        "countdown_prefill_interview": "برای مصاحبه چه چیزهایی را باید با خود بیاورم؟",
        "countdown_prefill_appointment": (
            "برای وقت ملاقات چه چیزهایی را باید با خود بیاورم؟"
        ),
        "glossary_title": "کلمه‌های مهم انگلیسی",
        "glossary_action": "تمرین",
        "glossary_prefill": "می‌خواهم کلمه‌های انگلیسی مصاحبهٔ خود را تمرین کنم",
        "checklist_title": "فراموش نکنید: {item}",
        "checklist_detail": "ما کمک می‌کنیم",
        "checklist_action": "بپرسید",
        "checklist_prefill": "{item} را چطور پیدا کنم؟",
    },
}
