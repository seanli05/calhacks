"""Mock USCIS phone line on Cartesia Line: phone tree -> hold -> live officer.

The phone agent dials this line in the demo. Three phases:
    IVR     deterministic phone tree (agency/ivr.py), keys or speech
    HOLD    timed announcements; caller audio is ignored so it can't cut hold short
    OFFICER an LLM plays the asylum officer who picks up
"""

import asyncio
import secrets
from collections.abc import AsyncIterator
from enum import StrEnum

from agency import prompts
from agency.case_record import DEMO_CASE
from agency.config import MockAgencySettings
from agency.ivr import IvrTurn, PhoneTree
from line.agent import TurnEnv
from line.events import (
    AgentEndCall,
    AgentSendText,
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


class Phase(StrEnum):
    IVR = "ivr"
    HOLD = "hold"
    OFFICER = "officer"


class MockAgencyLine:
    def __init__(self, settings: MockAgencySettings, call_id: str) -> None:
        self.settings = settings
        self.call_id = call_id
        self.phase = Phase.IVR
        self.tree = PhoneTree(DEMO_CASE)
        self.officer: LlmAgent | None = None

    # --- harness filters --------------------------------------------------------

    def should_run(self, event: InputEvent) -> bool:
        """Which events start a new turn. Starting a turn cancels the current one."""
        if isinstance(event, (CallStarted, CallEnded)):
            return True
        if self.phase is Phase.IVR:
            return isinstance(event, (UserDtmfSent, UserTurnEnded))
        if self.phase is Phase.OFFICER:
            return isinstance(event, UserTurnEnded)
        return False

    def should_cancel(self, event: InputEvent) -> bool:
        return self.phase is not Phase.HOLD and isinstance(event, UserTurnStarted)

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
            if self.settings.ivr_voice_id:
                yield AgentUpdateCall(voice_id=self.settings.ivr_voice_id)
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

        The no-input wait lives inside the turn: any key press or speech starts a
        new turn, which cancels this one before the timer fires.
        """
        while True:
            for line in turn.lines:
                yield AgentSendText(text=line)
            if turn.hang_up:
                yield AgentEndCall()
                return
            if turn.transfer:
                async for output in self._hold_then_officer():
                    yield output
                return
            await asyncio.sleep(self.settings.no_input_seconds)
            turn = self.tree.no_input()

    async def _hold_then_officer(self) -> AsyncIterator[OutputEvent]:
        self.phase = Phase.HOLD
        logger.info(
            f"hold_started call_id={self.call_id} hold_s={self.settings.hold_seconds}"
        )
        minutes = max(2, round(self.settings.hold_seconds / 60) + 3)
        yield AgentSendText(
            text=prompts.HOLD_START.format(minutes=minutes), interruptible=False
        )

        waited = 0.0
        announcement = 0
        while waited < self.settings.hold_seconds:
            pause = min(
                self.settings.hold_announce_every_s, self.settings.hold_seconds - waited
            )
            await asyncio.sleep(pause)
            waited += pause
            if waited < self.settings.hold_seconds:
                text = prompts.HOLD_ANNOUNCEMENTS[
                    announcement % len(prompts.HOLD_ANNOUNCEMENTS)
                ]
                announcement += 1
                yield AgentSendText(text=text, interruptible=False)

        self.officer = self._build_officer()
        if self.settings.officer_voice_id:
            yield AgentUpdateCall(voice_id=self.settings.officer_voice_id)
        self.phase = Phase.OFFICER
        logger.info(f"officer_joined call_id={self.call_id} info={self.tree.info}")
        yield AgentSendText(
            text=prompts.OFFICER_INTRO.format(officer=self.settings.officer_name)
        )

    def _build_officer(self) -> LlmAgent:
        reference_number = f"SR{secrets.randbelow(10**6):06d}"
        return LlmAgent(
            model=self.settings.officer_model,
            api_key=self.settings.anthropic_api_key,
            tools=[end_call],
            config=LlmConfig(
                system_prompt=prompts.officer_system_prompt(
                    case=DEMO_CASE,
                    officer=self.settings.officer_name,
                    reference_number=reference_number,
                    ivr_summary=self.tree.info.summary(),
                ),
                introduction="",
            ),
        )


async def get_agent(env: AgentEnv, call_request: CallRequest):
    line = MockAgencyLine(MockAgencySettings.from_env(), call_request.call_id)
    return line, line.should_run, line.should_cancel


app = VoiceAgentApp(get_agent=get_agent)

if __name__ == "__main__":
    app.run()
