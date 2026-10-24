"""Fixed Spanish for the exact English strings the demo seed writes
(app/db/reset.py, app/db/seed_story.py). `common.localize` checks it before the
translation cache, so the seeded screens are Spanish on the first poll and read the
same in every recording. Other text goes through `translations.py`.
"""

SPANISH: dict[str, str] = {
    # Facts
    "Has two children on the asylum application": (
        "Tienes dos hijos en tu solicitud de asilo"
    ),
    "Lives in Los Angeles County": "Vives en el condado de Los Ángeles",
    "Prefers voice notes": "Prefieres mensajes de voz",
    # R1: explanation, what is asked, checklist
    "This is a notice from USCIS scheduling your asylum interview.": (
        "Es un aviso de USCIS con la cita para tu entrevista de asilo."
    ),
    "Attend asylum interview with dependents and a qualified interpreter": (
        "Ir a la entrevista de asilo con tus dependientes y un intérprete calificado"
    ),
    "All dependents listed on the I-589": (
        "Todos los dependientes de tu solicitud I-589"
    ),
    "A qualified interpreter if you are not fluent in English": (
        "Un intérprete calificado si no hablas inglés con fluidez"
    ),
    "ID for you and each dependent": "Identificación para ti y cada dependiente",
    # Brief: call goal and questions
    (
        "Confirm the asylum interview is still scheduled; ask what to do if the "
        "interpreter can't come"
    ): (
        "Confirmar que la entrevista sigue programada y preguntar qué hacer si el "
        "intérprete no puede ir"
    ),
    "Is the interview on November 12 at 8:30 AM still scheduled?": (
        "¿La entrevista del 12 de noviembre a las 8:30 AM sigue programada?"
    ),
    (
        "If the interpreter can't come, what should the applicant do before the "
        "interview?"
    ): (
        "Si el intérprete no puede ir, ¿qué debe hacer la persona antes de la "
        "entrevista?"
    ),
    # P3: report next steps
    "Your interview is still on November 12 at 8:30 AM": (
        "Tu entrevista sigue el 12 de noviembre a las 8:30 AM"
    ),
    "You must bring your own interpreter; USCIS doesn't provide one": (
        "Tienes que llevar tu propio intérprete; USCIS no lo da"
    ),
    "If your interpreter can't come, tell USCIS in writing before the appointment": (
        "Si tu intérprete no puede ir, avisa a USCIS por escrito antes de la cita"
    ),
}


def translate(en: str, lang: str) -> str | None:
    return SPANISH.get(en) if lang == "es" else None
