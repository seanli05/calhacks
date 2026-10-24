"""Plays a text phone tree on a `FakeTelephony`, for the call simulator (1e).

A tree is plain data (`sim_trees.py`); `PhoneTree` runs it as the line's
`responder`, reacting the way phone lines generally do: menus reprompt on silence
or a wrong answer and give up after a few tries, keypad-only menus can't hear
speech, hold plays music between messages, and a representative greets, answers
what the agent says, nudges when nobody talks, and hangs up if nobody's there.
Times are real seconds, kept short; speech takes as long as its words.
"""

import asyncio
import re
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field

from app.phone.clock import with_timeout
from app.phone.fakes import (
    Action,
    ConnectedUser,
    Dialed,
    FakeTelephony,
    HungUp,
    PressedKeys,
    RangUser,
    Said,
    Step,
)
from app.phone.guard import spoken_digits
from app.phone.line import (
    AgencyAnswered,
    AgencyHungUp,
    Heard,
    LineEvent,
    NonSpeech,
    SpeechStarted,
    UserAnswered,
    UserUnreachable,
)
from app.phone.ports import Clock

WORDS_PER_S = 2.8
PAUSE_BETWEEN_LINES_S = 0.6
"""The breath between a prompt's sentences: shorter than the quiet the runner waits
for, as on real lines, so a menu read in pieces is still answered whole."""


@dataclass(frozen=True)
class Menu:
    prompt: tuple[str, ...]
    """Spoken as separate utterances, the way speech-to-text splits a long menu."""
    keys: Mapping[str, str] = field(default_factory=dict)
    """Key → next node."""
    words: Mapping[str, str] = field(default_factory=dict)
    """Spoken phrase (lowercase, matched anywhere) → next node. Speech menus only."""
    speech: bool = True
    """False: a keypad-only menu, deaf to anything said."""
    no_input: str = "Sorry, I didn't hear a response."
    no_match: str = "Sorry, I didn't understand."
    wait_s: float = 6.0
    retries: int = 2
    on_fail: str = "goodbye"


@dataclass(frozen=True)
class Hold:
    messages: tuple[str, ...]
    """Played between stretches of music."""
    music_s: float = 6.0
    then: str = "rep"


@dataclass(frozen=True)
class Rep:
    greeting: str
    replies: tuple[str, ...] = ()
    """What the rep says back to the agent's lines, in order."""
    nudges: tuple[str, ...] = ("Hello? Is anyone there?",)
    nudge_s: float = 7.0
    give_up: str = "I'm not hearing anyone, so I'm going to disconnect. Goodbye."
    user_answers: bool = True
    user_answer_s: float = 6.0
    ring_timeout_s: float = 15.0
    talk: tuple[str, ...] = ()
    """The rep's side of the conversation once the applicant is on."""
    talk_gap_s: float = 4.0


@dataclass(frozen=True)
class Goodbye:
    message: str


type Node = Menu | Hold | Rep | Goodbye


@dataclass(frozen=True)
class Tree:
    name: str
    about: str
    start: str
    nodes: Mapping[str, Node]
    answers: tuple[int, ...] = ()
    """Scripted replies to ask_user, in order; after that, no reply (the default)."""
    ring_s: float = 2.0
    held_out: bool = False
    """Never tuned against: run it, read it, don't fix the agent to fit it."""


def speech_s(text: str) -> float:
    return max(0.8, len(text.split()) / WORDS_PER_S)


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9' ]", " ", text.lower()).split())


class PhoneTree:
    """A `Tree` running on one line. Call `attach` with the line before dialing."""

    def __init__(self, tree: Tree, clock: Clock) -> None:
        self.tree = tree
        self._clock = clock
        self._line: FakeTelephony | None = None
        self._flow: asyncio.Task[None] | None = None
        self._user_leg: asyncio.Task[None] | None = None
        self._node: Node | None = None
        self._tries_left = 0
        self._agent_lines: asyncio.Queue[str] = asyncio.Queue()
        self.visited: list[str] = []

    def attach(self, line: FakeTelephony) -> None:
        self._line = line

    def __call__(self, action: Action) -> list[Step]:
        match action:
            case Dialed():
                self._start(self._drive(self._answer()))
            case Said(text=text):
                self._on_said(text)
            case PressedKeys(digits=digits):
                self._on_keys(digits)
            case RangUser():
                self._user_leg = asyncio.create_task(self._ring_user())
            case ConnectedUser():
                self._start(self._talk())
            case HungUp():
                for task in (self._flow, self._user_leg):
                    if task is not None:
                        task.cancel()
        return []

    # Reacting to the agent

    def _on_said(self, text: str) -> None:
        match self._node:
            case Menu(speech=True) as menu:
                target = self._route_speech(menu, text)
                self._route(menu, target)
            case Rep():
                self._agent_lines.put_nowait(text)

    def _on_keys(self, digits: str) -> None:
        if isinstance(self._node, Menu):
            menu = self._node
            self._route(menu, menu.keys.get(digits) or menu.keys.get(digits[:1]))

    def _route(self, menu: Menu, target: str | None) -> None:
        if target is not None:
            self._start(self._drive(self._go(target)))
            return
        self._tries_left -= 1
        if self._tries_left < 0:
            self._start(self._drive(self._go(menu.on_fail)))
        else:
            self._start(self._drive(self._menu(menu, (menu.no_match,))))

    @staticmethod
    def _route_speech(menu: Menu, text: str) -> str | None:
        said = _normalize(text)
        for phrase, target in menu.words.items():
            if phrase in said:
                return target
        digits = spoken_digits(said)
        if digits and digits in menu.keys:
            return menu.keys[digits]
        for word, key in (("star", "*"), ("pound", "#")):
            if word in said.split() and key in menu.keys:
                return menu.keys[key]
        return None

    # The line's side

    def _start(self, flow: Awaitable[None]) -> None:
        if self._flow is not None:
            self._flow.cancel()
        self._flow = asyncio.ensure_future(flow)

    async def _drive(self, first: Awaitable[str | None]) -> None:
        name = await first
        while name is not None:
            name = await self._go(name)

    async def _answer(self) -> str:
        await self._clock.sleep(self.tree.ring_s)
        self._push(AgencyAnswered())
        return self.tree.start

    async def _go(self, name: str) -> str | None:
        node = self.tree.nodes[name]
        self._node = node
        self.visited.append(name)
        match node:
            case Menu():
                self._tries_left = node.retries
                return await self._menu(node, ())
            case Hold():
                return await self._hold(node)
            case Rep():
                return await self._rep(node)
            case Goodbye():
                await self._speak((node.message,))
                self._push(AgencyHungUp())
                return None

    async def _menu(self, menu: Menu, opener: tuple[str, ...]) -> str:
        await self._speak((*opener, *menu.prompt))
        while self._tries_left > 0:
            await self._clock.sleep(menu.wait_s)
            self._tries_left -= 1
            await self._speak((menu.no_input, *menu.prompt))
        await self._clock.sleep(menu.wait_s)
        return menu.on_fail

    async def _hold(self, hold: Hold) -> str:
        for message in hold.messages:
            await self._music(hold.music_s)
            await self._speak((message,))
        await self._music(hold.music_s)
        return hold.then

    async def _rep(self, rep: Rep) -> None:
        while not self._agent_lines.empty():
            self._agent_lines.get_nowait()  # menu answers, said before the rep came on
        await self._speak((rep.greeting,))
        replies = iter(rep.replies)
        nudges = iter(rep.nudges)
        while True:
            said = await self._agent_line(rep.nudge_s)
            if said is not None:
                await self._clock.sleep(speech_s(said))
                reply = next(replies, None)
                if reply is not None:
                    await self._speak((reply,))
                continue
            nudge = next(nudges, None)
            if nudge is None:
                await self._speak((rep.give_up,))
                self._push(AgencyHungUp())
                return
            await self._speak((nudge,))

    async def _ring_user(self) -> None:
        rep = self._node if isinstance(self._node, Rep) else Rep(greeting="")
        if rep.user_answers:
            await self._clock.sleep(rep.user_answer_s)
            self._push(UserAnswered())
        else:
            await self._clock.sleep(rep.ring_timeout_s)
            self._push(UserUnreachable(reason="no_answer"))

    async def _talk(self) -> None:
        rep = self._node if isinstance(self._node, Rep) else Rep(greeting="")
        for line in rep.talk:
            await self._clock.sleep(rep.talk_gap_s)
            await self._speak((line,))
        await self._clock.sleep(rep.talk_gap_s)
        self._push(AgencyHungUp())

    async def _agent_line(self, timeout_s: float) -> str | None:
        try:
            return await with_timeout(self._clock, self._agent_lines.get(), timeout_s)
        except TimeoutError:
            return None

    async def _speak(self, lines: tuple[str, ...]) -> None:
        for i, line in enumerate(lines):
            if i:
                await self._clock.sleep(PAUSE_BETWEEN_LINES_S)
            self._push(SpeechStarted())
            await self._clock.sleep(speech_s(line))
            self._push(Heard(text=line))

    async def _music(self, seconds: float) -> None:
        await self._clock.sleep(seconds)
        self._push(NonSpeech(sound="music", seconds=seconds))

    def _push(self, event: LineEvent) -> None:
        if self._line is None:
            raise RuntimeError("attach the line before dialing")
        self._line.push(event)
