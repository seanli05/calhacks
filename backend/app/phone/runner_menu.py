"""The call runner's menu and ask_user handlers (1b's actions on the line, C37).

Each menu utterance: 1c and 1b run in parallel, a decision is dropped if the line
left the menu or spoke again meanwhile, and the action goes out through the
executor. ask_user runs as a task while the line is still read: reprompts of the
asked prompt aren't decided again, the second one takes the default, and a new
prompt drops the question.

Every answer (a press, a say, starting ask_user, the applicant's choice) is held
until the line has been quiet `menu_quiet_s` after the turn closed, so the agent
never answers before hearing every option. Speech in the meantime pauses it; if
that speech adds text, a held decision is dropped and the menu so far is decided
again as a whole.
"""

import asyncio
import logging
from functools import partial
from typing import Any

from app.contracts import AskUserReply, AskUserRequest, EventType
from app.contracts.common import CallState
from app.db.ids import new_id
from app.phone import menu, phase
from app.phone.executor import sounds_like_reprompt
from app.phone.guard import BlockedIdentifier
from app.phone.menu import (
    AskUserAction,
    MenuAction,
    MenuTurn,
    PressAction,
    SayAction,
    WaitAction,
)
from app.phone.phase import PhaseReading
from app.phone.ports import LineClosed
from app.phone.runner_base import RunnerBase
from app.phone.runner_parts import AskDone, HeldAnswer, MenuGaveUp, OpenAsk

logger = logging.getLogger("app.phone.runner")

S = CallState


class MenuSteps(RunnerBase):
    """Menu handlers; `runner._CallRunner` adds the rest of the call."""

    async def _menu_heard(self, text: str, at_s: float, seq: int) -> None:
        if self.executor.observe(text):
            self.step.flags.append("keypad_mode")
        if self.held is not None:
            if not self.held.redo_on_heard and sounds_like_reprompt(
                text, self.held.heard
            ):
                # The menu is repeating itself: the applicant's choice still applies.
                self.step.flags.append("reprompt_while_held")
                return
            await self._drop_held()
        if self.ask is not None:
            await self._heard_while_asking(text, at_s, seq)
            return
        self.menu_buffer.append(text)
        await self._classify_and_decide(at_s, seq)

    async def _classify_and_decide(
        self, at_s: float, seq: int, reading: PhaseReading | None = None
    ) -> None:
        """1c and 1b in parallel; 1b's answer is dropped if the line left the menu
        or spoke again meanwhile. An answer is held until the line goes quiet."""
        heard = " ".join(self.menu_buffer)
        history = list(self.menu_history)

        async def decide() -> MenuAction:
            # The model call is made inside the task, so a task cancelled before it
            # starts (1c fired first) leaves no never-awaited coroutine behind.
            return await self._timed(
                "decide",
                menu.decide(
                    heard, self.brief, history, client=self.llm, call_id=self.call_id
                ),
            )

        deciding = asyncio.ensure_future(decide())
        try:
            if reading is None:
                reading = await self._classify(self.menu_buffer[-1], at_s)
                trigger = phase.to_trigger(S.MENU, reading)
                if trigger is not None:
                    await self._discard(deciding)
                    await self._log_menu_heard(reading)
                    await self._fire_reading(trigger, reading)
                    return
            action = await deciding
        except BaseException:
            await self._discard(deciding)
            raise

        self.step.action = action
        if action.fallback:
            self.step.flags.append("fallback")
        if self.heard_arrived > seq:
            self.step.flags.append("stale_dropped")
            await self._log_menu_heard(reading, action, stale=True)
            return
        if isinstance(action, WaitAction):
            await self._answer(action, heard, reading)
            return
        # Kept in `menu_buffer` until sent, so a menu that goes on is decided whole.
        self._hold(
            HeldAnswer(
                send=partial(self._answer, action, heard, reading),
                heard=heard,
                redo_on_heard=True,
                on_drop=partial(self._log_menu_heard, reading, action, stale=True),
            )
        )

    async def _answer(
        self, action: MenuAction, heard: str, reading: PhaseReading
    ) -> None:
        self.menu_buffer.clear()
        self.menu_history.append(MenuTurn(heard=heard, action=action))
        await self._log_menu_heard(reading, action)
        await self._act(action, heard)

    # Holding answers until every option has been heard

    def _hold(self, held: HeldAnswer) -> None:
        self.held = held
        self.step.flags.append("held")
        self.arm_held()

    def arm_held(self) -> None:
        """Send the held answer once the line has been quiet `menu_quiet_s`."""
        if self.held is None or self.line_speaking:
            return
        wait = self.quiet_since_s + self.config.menu_quiet_s - self.now_s()
        self.timers.start("menu_quiet", max(wait, 0.0))

    async def send_held(self) -> None:
        if self.held is None or self.line_speaking:
            self.step.flags.append("stale_timer")
            return
        held, self.held = self.held, None
        await held.send()

    def speech_started(self) -> None:
        """Pause the held answer. What the turn says decides its fate: more text
        redoes a decision (`_menu_heard`), a turn with none lets it go out."""
        self.timers.cancel("menu_quiet")

    async def _drop_held(self) -> None:
        held = self.forget_held()
        if held is not None and held.on_drop is not None:
            await held.on_drop()

    def forget_held(self) -> HeldAnswer | None:
        held, self.held = self.held, None
        self.timers.cancel("menu_quiet")
        if held is not None:
            self.step.flags.append("held_dropped")
        return held

    async def _heard_while_asking(self, text: str, at_s: float, seq: int) -> None:
        assert self.ask is not None
        reading = await self._classify(text, at_s)
        trigger = phase.to_trigger(S.MENU, reading)
        if trigger is not None:
            await self._log_menu_heard(reading)
            await self._fire_reading(trigger, reading)  # leaving the menu drops the ask
            return
        if sounds_like_reprompt(text, self.ask.heard):
            self.ask.reprompts += 1
            self.step.flags.append("reprompt_while_asking")
            await self._log_menu_heard(reading)
            if self.ask.reprompts >= self.config.ask_reprompts_before_default:
                # Menus hang up after a few no-inputs: take the safe default now.
                ask = self._drop_ask()
                self.step.flags.append("ask_default_early")
                await self._press_choice(ask, ask.action.default_option, "ask_default")
            return
        # The menu moved on; the question no longer applies.
        self._drop_ask()
        self.step.flags.append("ask_abandoned")
        self.menu_buffer = [text]
        await self._classify_and_decide(at_s, seq, reading)

    async def _act(self, action: MenuAction, heard: str) -> None:
        match action:
            case WaitAction():
                pass
            case AskUserAction():
                self._start_ask(action, heard)
            case SayAction(text=menu.ESCAPE_PHRASE):
                self.escapes += 1
                if self.escapes > self.config.escape_limit:
                    raise MenuGaveUp("asked for a person too many times")
                await self._send(action, heard, "model")
            case PressAction() | SayAction():
                await self._send(action, heard, "model")

    async def _send(
        self, action: PressAction | SayAction, prompt: str, source: str
    ) -> None:
        """One menu answer on the line, with C35's guard and a closed line handled
        here: neither stops the call."""
        try:
            if isinstance(action, PressAction):
                sent = await self.executor.press(action, prompt)
            else:
                sent = await self.executor.say(action)
        except BlockedIdentifier:
            self.step.flags.append("blocked")
            self.blocked_streak += 1
            if self.blocked_streak >= 2:
                self.blocked_streak = 0
                escape = SayAction(
                    kind="say",
                    text=menu.ESCAPE_PHRASE,
                    reason_en="Two blocked steps in a row; asking for a person",
                    fallback=True,
                )
                await self._send(escape, prompt, "fallback")
            return
        except LineClosed:
            self.step.flags.append("line_closed")
            return
        self.blocked_streak = 0
        self._sent(sent)
        if isinstance(action, PressAction):
            await self._log(
                EventType.CALL_MENU_CHOICE,
                f"Chose option {action.digits}",
                digit=action.digits,
                via=sent.via,
                source=source,
            )
        else:
            await self._log(
                EventType.CALL_MENU_CHOICE,
                "Answered the menu by voice",
                kind="say",
                via=sent.via,
                source=source,
                escape=action.text == menu.ESCAPE_PHRASE,
            )

    def _start_ask(self, action: AskUserAction, heard: str) -> None:
        request = menu.to_ask_user_request(
            action,
            call_id=self.call_id,
            question_id=new_id("question"),
            timeout_s=self.config.ask_timeout_s,
        )
        token = next(self._ask_seq)
        task = asyncio.create_task(self._ask_task(token, request))
        self.ask = OpenAsk(token, action, heard, len(self.menu_history) - 1, task)
        self.step.sent.append("asked the applicant")

    def _drop_ask(self) -> OpenAsk:
        """Stop waiting on the open question; cancelling lets the relay close it."""
        assert self.ask is not None
        ask, self.ask = self.ask, None
        ask.task.cancel()
        self._dropped.append(ask.task)
        return ask

    async def _ask_task(self, token: int, request: AskUserRequest) -> None:
        reply: AskUserReply | None
        try:
            reply = await self.deps.relay.ask_user(request)
        except Exception:
            logger.exception("ask_user failed; taking the default (%s)", self._ids())
            reply = None
        self.inbox.put_nowait(AskDone(token, reply, self.now_s()))

    async def _ask_done(self, item: AskDone) -> None:
        if self.ask is None or item.token != self.ask.token:
            self.step.flags.append("stale_answer")
            return
        ask, self.ask = self.ask, None
        options = len(ask.action.options)
        if item.reply is None:
            self.step.flags.append("ask_failed")
            choice = ask.action.default_option
        elif not 1 <= item.reply.choice <= options:
            self.step.flags.append("choice_out_of_range")
            choice = ask.action.default_option
        else:
            choice = item.reply.choice
        self.step.text = f"choice {choice}"
        await self._press_choice(ask, choice, "ask_user")

    async def _press_choice(self, ask: OpenAsk, choice: int, source: str) -> None:
        press = menu.press_for_choice(ask.action, choice)
        self.step.action = press
        self._hold(
            HeldAnswer(
                send=partial(self._send_choice, ask, press, source),
                heard=ask.heard,
                redo_on_heard=False,
            )
        )

    async def _send_choice(self, ask: OpenAsk, press: PressAction, source: str) -> None:
        self.menu_history[ask.turn_index] = MenuTurn(heard=ask.heard, action=press)
        self.menu_buffer.clear()
        await self._send(press, ask.heard, source)

    async def _log_menu_heard(
        self,
        reading: PhaseReading,
        action: MenuAction | None = None,
        *,
        stale: bool = False,
    ) -> None:
        data: dict[str, Any] = {
            "phase": reading.phase,
            "confidence": round(reading.confidence, 2),
            "source": reading.source,
            # Why, for the case view's activity: the reading names cues, and the
            # action's reason passed the menu guard (no refs, no digit runs).
            "reading_reason_en": reading.reason_en,
        }
        if action is not None:
            data["action"] = action.kind
            data["fallback"] = action.fallback
            data["reason_en"] = action.reason_en
        if stale:
            data["stale"] = True
        if self.ask is not None:
            data["asking"] = True
        await self._log(EventType.CALL_MENU_HEARD, "Heard the phone menu", **data)
