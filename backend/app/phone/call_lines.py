"""The runner's fixed lines to a representative. Fixed text, never model output, so
rule 3 and C35 hold by review: the agent says it's automated and calls for the
applicant, and it never names anyone, gives an identifier, or mentions the case.
`JOIN_PROMPTS` and `LISTEN_PROMPTS` are the lines the applicant hears, in their own
language (rule 6)."""

from dataclasses import dataclass

from app.contracts.common import LanguageCode

INTRO = (
    "Hello, this is an automated assistant calling for an applicant. "
    "The applicant is joining the call now and will speak with you directly. "
    "One moment, please."
)
"""Said once, the moment a person is detected, while the applicant's phone rings."""

HOLDING = (
    "The applicant is joining now and will answer for themselves. One moment, please."
)
"""Said when the representative speaks while the applicant's phone rings, including
when they ask a question the agent must not answer."""

CALL_BACK = (
    "I'm sorry, the applicant can't join right now. "
    "The account holder will call back. Thank you, goodbye."
)
"""Failure rules → the user doesn't answer the bridged call."""

USER_ENDED = (
    "I'm sorry, the applicant has asked to end this call. "
    "They'll call back if they need to. Thank you, goodbye."
)
"""Said when the user asks over WhatsApp to hang up while a representative is on
the line and the applicant isn't yet (`human_detected`, `bridging`)."""


@dataclass(frozen=True)
class JoinPrompt:
    """What the applicant hears on picking up the bridged call, before they join.
    Spoken by Twilio's `<Say>`, so it needs Twilio's language tag and a voice that
    speaks it natively."""

    text: str
    say_language: str
    voice: str


JOIN_PROMPTS: dict[LanguageCode, JoinPrompt] = {
    "en": JoinPrompt(
        "Your call with the immigration office is ready. Press any key to join.",
        "en-US",
        "Polly.Joanna",
    ),
    "es": JoinPrompt(
        "Su llamada con la oficina de inmigración está lista. "
        "Presione cualquier tecla para unirse.",
        "es-US",
        "Polly.Lupe",
    ),
}
"""Keyed by the user's language (`CallJob.user_language`, from `users.language`:
the language they write to us in). The key press keeps the representative out of
voicemail, which Twilio reports as answered (spikes/bridge/README.md). Unused when
the line has no gate (`PHONE_JOIN_GATE=false`)."""

LISTEN_PROMPTS: dict[LanguageCode, JoinPrompt] = {
    "en": JoinPrompt(
        "Your call with the immigration office is in progress. "
        "Press any key to listen in. The office won't hear you.",
        "en-US",
        "Polly.Joanna",
    ),
    "es": JoinPrompt(
        "Su llamada con la oficina de inmigración está en curso. "
        "Presione cualquier tecla para escuchar. La oficina no podrá oírle.",
        "es-US",
        "Polly.Lupe",
    ),
}
"""What the user hears on picking up the listen-only leg (`listen_leg.py`), when they
asked to sit in. The key press keeps carrier voicemail from recording the call
(C29)."""

FALLBACK_LANGUAGE: LanguageCode = "en"


def join_prompt(language: LanguageCode) -> JoinPrompt:
    """The prompt in `language`, or English when there's none for it yet."""
    return JOIN_PROMPTS.get(language, JOIN_PROMPTS[FALLBACK_LANGUAGE])


def listen_prompt(language: LanguageCode) -> JoinPrompt:
    """The listen prompt in `language`, or English when there's none for it yet."""
    return LISTEN_PROMPTS.get(language, LISTEN_PROMPTS[FALLBACK_LANGUAGE])
