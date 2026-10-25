"""Mock USCIS phone line on Cartesia Line: phone tree -> hold -> live officer.

The phone agent dials this line in the demo. Three phases:
    IVR     deterministic phone tree (agency/ivr.py), keys or speech
    HOLD    timed announcements; caller audio is ignored so it can't cut hold short
    OFFICER an LLM plays the asylum officer who picks up

MOCK_AGENCY_MODE=quick skips IVR and HOLD: the officer picks up after a short
greeting, for testing live calls and the bridge. MOCK_AGENCY_MODE=short plays a
shorter IVR (one keypad menu, one open question) and a short hold.
"""

import asyncio
import secrets
from collections.abc import AsyncIterator
from enum import StrEnum

from agency import prompts
from agency.config import MockAgencySettings, Mode
from agency.ivr import IvrTurn, PhoneTree
from line.agent import TurnEnv
from line.events import (
    AgentEndCall,
    AgentSendText,
    AgentTurnEnded,
    AgentTurnStarted,
    AgentUpdateCall,
    CallEnded,
    CallStarted,
    InputEvent,
    OutputEvent,
    UserDtmfSent,
    UserTextSent,
    UserTurnEnded,
    UserTurnStarted,
)
from line.llm_agent import LlmAgent, LlmConfig, end_call
from line.voice_agent_app import AgentEnv, CallRequest, VoiceAgentApp
from loguru import logger

SILENCE_POLL_S = 0.25


class Phase(StrEnum):
    IVR = "ivr"
    HOLD = "hold"
    OFFICER = "officer"


class MockAgencyLine:
    def __init__(self, settings: MockAgencySettings, call_id: str) -> None:
        self.settings = settings
        self.call_id = call_id
        self.phase = Phase.IVR
        self.case = settings.case_record
        self.tree = PhoneTree(self.case, short=settings.mode is Mode.SHORT)
        self.officer: LlmAgent | None = None
        self.agent_speaking = False

    # --- harness filters --------------------------------------------------------

    def should_run(self, event: InputEvent) -> bool:
        """Which events start a new turn. Starting a turn cancels the current one."""
        self._track_agent_speech(event)
        if isinstance(event, (CallStarted, CallEnded)):
            return True
        if self.phase is Phase.IVR:
            if isinstance(event, UserTurnEnded) and self.agent_speaking:
                # Recorded prompts can't be talked over, like a real phone tree.
                # Speech that ends mid-prompt is echo, noise, or barge-in: drop it.
                logger.info(f"ignored_speech_during_prompt call_id={self.call_id}")
                return False
            return isinstance(event, (UserDtmfSent, UserTurnEnded))
        if self.phase is Phase.OFFICER:
            return isinstance(event, UserTurnEnded)
        return False

    def should_cancel(self, event: InputEvent) -> bool:
        """The officer stops when talked over; menu prompts and hold don't."""
        if not isinstance(event, UserTurnStarted):
            return False
        if self.phase is Phase.OFFICER:
            return True
        return self.phase is Phase.IVR and not self.agent_speaking

    def _track_agent_speech(self, event: InputEvent) -> None:
        """The harness reports when our TTS starts and stops playing."""
        if isinstance(event, AgentTurnStarted):
            self.agent_speaking = True
        elif isinstance(event, AgentTurnEnded):
            self.agent_speaking = False

    # --- turns ----------------------------------------------------------------

    async def process(
        self, env: TurnEnv, event: InputEvent
    ) -> AsyncIterator[OutputEvent]:
        if isinstance(event, CallEnded):
            logger.info(f"call_ended call_id={self.call_id} phase={self.phase}")
            if self.officer is not None:
                await self.officer.cleanup()
            return

        if self.phase is Phase.OFFICER and self.officer is not None:
            async for output in self.officer.process(env, event):
                yield output
            return

        if isinstance(event, CallStarted):
            yield AgentUpdateCall(voice_id=self.settings.ivr_voice_id)
            if self.settings.mode is Mode.QUICK:
                logger.info(f"quick_mode call_id={self.call_id}")
                yield AgentSendText(text=prompts.QUICK_GREETING, interruptible=False)
                async for output in self._officer_picks_up(prompts.QUICK_IVR_SUMMARY):
                    yield output
                return
            turn = self.tree.start()
        elif isinstance(event, UserDtmfSent):
            turn = self.tree.press(event.button)
        elif isinstance(event, UserTurnEnded):
            text = " ".join(
                item.content for item in event.content if isinstance(item, UserTextSent)
            ).strip()
            # Key presses also show up in turn content; they were handled as UserDtmfSent.
            turn = self.tree.hear(text) if text else IvrTurn()
        else:
            return

        logger.info(
            f"ivr call_id={self.call_id} event={event.type} node={self.tree.node}"
        )
        async for output in self._play(turn):
            yield output

    async def _play(self, turn: IvrTurn) -> AsyncIterator[OutputEvent]:
        """Speak a turn, then wait for input, hang up, or go on hold.

        Prompts are uninterruptible and always play to the end. A key press
        mid-prompt still starts a new turn, which cancels this one, but the
        prompt already sent finishes first. The no-input wait lives inside the
        turn, so any input cancels it before the timer fires.
        """
        while True:
            for line in turn.lines:
                yield AgentSendText(text=line, interruptible=False)
            if turn.hang_up:
                yield AgentEndCall()
                return
            if turn.transfer:
                async for output in self._hold_then_officer():
                    yield output
                return
            await self._wait_for_silence(self.settings.no_input_seconds)
            turn = self.tree.no_input()

    async def _wait_for_silence(self, seconds: float) -> None:
        """Sleep for `seconds` of time when the line itself isn't talking.

        Counting from when the prompt was sent would fire mid-prompt on the
        long menus.
        """
        waited = 0.0
        while waited < seconds:
            await asyncio.sleep(SILENCE_POLL_S)
            if not self.agent_speaking:
                waited += SILENCE_POLL_S

    async def _hold_then_officer(self) -> AsyncIterator[OutputEvent]:
        self.phase = Phase.HOLD
        hold_s = self.settings.call_hold_seconds
        logger.info(f"hold_started call_id={self.call_id} hold_s={hold_s}")
        minutes = max(2, round(hold_s / 60) + 3)
        yield AgentSendText(
            text=prompts.HOLD_START.format(minutes=minutes), interruptible=False
        )

        waited = 0.0
        announcement = 0
        while waited < hold_s:
            pause = min(self.settings.hold_announce_every_s, hold_s - waited)
            await asyncio.sleep(pause)
            waited += pause
            if waited < hold_s:
                text = prompts.HOLD_ANNOUNCEMENTS[
                    announcement % len(prompts.HOLD_ANNOUNCEMENTS)
                ]
                announcement += 1
                yield AgentSendText(text=text, interruptible=False)

        async for output in self._officer_picks_up(self.tree.info.summary()):
            yield output

    async def _officer_picks_up(self, ivr_summary: str) -> AsyncIterator[OutputEvent]:
        self.officer = self._build_officer(ivr_summary)
        yield AgentUpdateCall(voice_id=self.settings.officer_voice_id)
        self.phase = Phase.OFFICER
        logger.info(f"officer_joined call_id={self.call_id} info={ivr_summary!r}")
        yield AgentSendText(
            text=prompts.officer_intro(self.case, self.settings.officer_name)
        )

    def _build_officer(self, ivr_summary: str) -> LlmAgent:
        reference_number = f"SR{secrets.randbelow(10**6):06d}"
        return LlmAgent(
            model=self.settings.officer_model,
            api_key=self.settings.anthropic_api_key,
            tools=[end_call],
            config=LlmConfig(
                system_prompt=prompts.officer_system_prompt(
                    case=self.case,
                    officer=self.settings.officer_name,
                    reference_number=reference_number,
                    ivr_summary=ivr_summary,
                ),
                introduction="",
            ),
        )


async def get_agent(env: AgentEnv, call_request: CallRequest):
    line = MockAgencyLine(MockAgencySettings.from_env(), call_request.call_id)
    return line, line.should_run, line.should_cancel


app = VoiceAgentApp(get_agent=get_agent)

if __name__ == "__main__":
    # A bad env (e.g. an unknown MOCK_AGENCY_CASE) fails here, not on the first call.
    MockAgencySettings.from_env()
    app.run()
