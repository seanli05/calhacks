"""Suggestion card text per language. `{days}` and `{item}` are filled in by
`app.api.suggestions`; a language missing here falls back to English."""

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
        "countdown_title_interview": "Tu entrevista es en {days} días",
        "countdown_title_interview_1": "Tu entrevista es mañana",
        "countdown_title_appointment": "Tu cita es en {days} días",
        "countdown_title_appointment_1": "Tu cita es mañana",
        "countdown_detail": "Repasa qué llevar",
        "countdown_action": "Preparar",
        "countdown_prefill_interview": "¿Qué tengo que llevar a mi entrevista?",
        "countdown_prefill_appointment": "¿Qué tengo que llevar a mi cita?",
        "glossary_title": "Palabras clave en inglés",
        "glossary_action": "Practicar",
        "glossary_prefill": "Quiero practicar las palabras en inglés para mi entrevista",
        "checklist_title": "No olvides: {item}",
        "checklist_detail": "Te ayudamos",
        "checklist_action": "Preguntar",
        "checklist_prefill": "¿Cómo consigo {item}?",
    },
}
