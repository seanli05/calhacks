"""What happens on the phone line, as the runner sees it (`Telephony.events()`).

Transport-agnostic: the 1e simulator makes these from text scripts, and Phase 2
makes them from Twilio status callbacks and the Pipecat stream (speech-to-text,
voice activity). Each maps onto a `state.Trigger`, or feeds the menu decider and
the phase classifier. `Heard` and `NonSpeech` are provisional until the phase
classifier (1c) settles its input.
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
    """The user's phone didn't pick up (Twilio's ring timeout), or rejected it."""

    kind: Literal["user_unreachable"] = "user_unreachable"
    reason: Literal["busy", "no_answer", "failed"]


class UserLeft(_LineEvent):
    """The user hung up after joining the conference."""

    kind: Literal["user_left"] = "user_left"


LineEvent = Annotated[
    AgencyAnswered
    | AgencyUnreachable
    | AgencyHungUp
    | Heard
    | NonSpeech
    | UserAnswered
    | UserUnreachable
    | UserLeft,
    Field(discriminator="kind"),
]
