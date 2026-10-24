"""What happens on the phone line, as the runner sees it (`Telephony.events()`).

Transport-agnostic: the 1e simulator makes these from text scripts, and Phase 2
makes them from Twilio status callbacks and the Pipecat stream (speech-to-text,
voice activity). Each maps onto a `state.Trigger`, or feeds the menu decider and
the phase classifier.

Turns: speech from the agency comes as one `SpeechStarted`, then exactly one event
that closes the turn: `Heard` with the text, or `NonSpeech` if it produced none
(music, noise). A line may skip `SpeechStarted` (the text fakes do); the runner
then learns of the turn only when it closes.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _LineEvent(BaseModel):
    model_config = ConfigDict(frozen=True)


class AgencyAnswered(_LineEvent):
    kind: Literal["agency_answered"] = "agency_answered"


class AgencyUnreachable(_LineEvent):
    """The agency call never connected."""

    kind: Literal["agency_unreachable"] = "agency_unreachable"
    reason: Literal["busy", "no_answer", "failed"]


class AgencyHungUp(_LineEvent):
    kind: Literal["agency_hung_up"] = "agency_hung_up"


class SpeechStarted(_LineEvent):
    """The agency side started talking (voice activity). The runner holds any menu
    answer until the turn closes and the line has been quiet a while, so it never
    answers before hearing every option."""

    kind: Literal["speech_started"] = "speech_started"


class Heard(_LineEvent):
    """One finished stretch of speech from the agency side, as text."""

    kind: Literal["heard"] = "heard"
    text: str


class NonSpeech(_LineEvent):
    """A stretch with no speech: hold music or silence."""

    kind: Literal["non_speech"] = "non_speech"
    sound: Literal["music", "silence"]
    seconds: float = Field(gt=0)


class UserAnswered(_LineEvent):
    kind: Literal["user_answered"] = "user_answered"


class UserUnreachable(_LineEvent):
    """The user's phone didn't pick up (Twilio's ring timeout), or rejected it, or
    something picked up but pressed no key to join (`no_key_press`): usually the
    carrier's voicemail, which Twilio reports as answered."""

    kind: Literal["user_unreachable"] = "user_unreachable"
    reason: Literal["busy", "no_answer", "failed", "no_key_press"]


class UserLeft(_LineEvent):
    """The user hung up after joining the conference."""

    kind: Literal["user_left"] = "user_left"


class Overheard(_LineEvent):
    """One finished utterance after the bridge, from a listen-only fork of one leg.
    For the transcript only: the agent is silent once the applicant is on, so this
    never feeds the classifier or the menu."""

    kind: Literal["overheard"] = "overheard"
    speaker: Literal["agency", "user"]
    text: str


LineEvent = Annotated[
    AgencyAnswered
    | AgencyUnreachable
    | AgencyHungUp
    | SpeechStarted
    | Heard
    | NonSpeech
    | UserAnswered
    | UserUnreachable
    | UserLeft
    | Overheard,
    Field(discriminator="kind"),
]
