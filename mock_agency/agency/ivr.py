"""The phone tree as a pure state machine, with no Line SDK imports.

The Line adapter in main.py feeds it key presses, transcripts, and no-input
timeouts, and plays back the returned IvrTurn. Keeping it pure lets us test
every path without a call.

English only, like the line it mocks: no language menu and no interpreter option.
It never asks for an identifier (receipt number, A-Number, date of birth): the
phone agent may not give one (Plan.md C35), so only the officer asks, and the
applicant answers in their own voice once bridged.

Tree:
    MAIN_MENU      closed  1 status, 2 interview notice, 3 address, 4 work permit
    APPOINTMENT     closed  1 biometrics, 2 asylum interview, 3 naturalization
    REASON          open    say why you're calling (speech only)
    ATTENDANCE      closed  1 attending as scheduled, 2 needs a new date
    -> transfer to hold, then a live officer
"""

from enum import StrEnum

from agency import prompts
from agency.case_record import MockCase
from agency.speech import (
    Topic,
    asks_for_human,
    classify_reason,
    spoken_digit,
)
from pydantic import BaseModel, Field

MAX_NO_INPUT = 3
MAX_REASON_ATTEMPTS = 2


class Node(StrEnum):
    MAIN_MENU = "main_menu"
    APPOINTMENT = "appointment"
    REASON = "reason"
    ATTENDANCE = "attendance"
    TRANSFERRED = "transferred"
    HUNG_UP = "hung_up"


class IvrTurn(BaseModel):
    """What the line says next, and whether it then transfers or hangs up."""

    lines: list[str] = Field(default_factory=list)
    transfer: bool = False
    hang_up: bool = False


class CallerInfo(BaseModel):
    """What the menu collected, handed to the officer at transfer."""

    reason_said: str | None = None
    topic: Topic | None = None
    wants_reschedule: bool | None = None

    def summary(self) -> str:
        attendance = {
            True: "needs a new interview date",
            False: "plans to attend as scheduled",
            None: "not asked",
        }[self.wants_reschedule]
        return (
            f'- Reason for calling, in their words: "{self.reason_said or "not given"}"\n'
            f"- Topic: {self.topic or 'unknown'}\n"
            f"- Attendance: {attendance}"
        )


class PhoneTree:
    def __init__(self, case: MockCase) -> None:
        self.case = case
        self.node = Node.MAIN_MENU
        self.info = CallerInfo()
        self._no_input_count = 0
        self._reason_attempts = 0

    # --- inputs -------------------------------------------------------------

    def start(self) -> IvrTurn:
        return IvrTurn(lines=[prompts.GREETING, prompts.MAIN_MENU])

    def press(self, key: str) -> IvrTurn:
        """Handle one DTMF key press."""
        self._no_input_count = 0
        if self.node is Node.REASON:
            return IvrTurn(lines=[prompts.REASON_NEEDS_SPEECH, prompts.REASON_PROMPT])
        return self._choose(key)

    def hear(self, text: str) -> IvrTurn:
        """Handle one finished spoken turn."""
        self._no_input_count = 0
        if self.node is Node.REASON:
            return self._reason(text)
        if asks_for_human(text):
            return IvrTurn(lines=[prompts.HUMAN_NOT_YET, self._prompt()])
        digit = spoken_digit(text) or self._keyword_choice(text)
        if digit is None:
            return self._invalid()
        return self._choose(digit)

    def no_input(self) -> IvrTurn:
        """The caller said and pressed nothing for a while."""
        self._no_input_count += 1
        if self._no_input_count >= MAX_NO_INPUT:
            self.node = Node.HUNG_UP
            return IvrTurn(lines=[prompts.NO_INPUT_GOODBYE], hang_up=True)
        return IvrTurn(lines=[prompts.NO_INPUT, self._prompt()])

    @property
    def awaiting_input(self) -> bool:
        return self.node not in (Node.TRANSFERRED, Node.HUNG_UP)

    # --- closed menus ----------------------------------------------------------

    def _choose(self, key: str) -> IvrTurn:
        match self.node, key:
            case Node.MAIN_MENU, "1":
                return self._info_then_main(prompts.CASE_STATUS_INFO)
            case Node.MAIN_MENU, "2":
                return self._go(Node.APPOINTMENT)
            case Node.MAIN_MENU, "3":
                return self._info_then_main(prompts.ADDRESS_CHANGE_INFO)
            case Node.MAIN_MENU, "4":
                return self._info_then_main(prompts.EMPLOYMENT_INFO)
            case Node.MAIN_MENU, "9":
                return self._go(Node.MAIN_MENU)

            case Node.APPOINTMENT, "1" | "3":
                return self._info_then_main(prompts.NOT_ASYLUM_INFO)
            case Node.APPOINTMENT, "2":
                return self._go(Node.REASON)
            case Node.APPOINTMENT, "*":
                return self._go(Node.MAIN_MENU)

            case Node.ATTENDANCE, "1" | "2":
                self.info.wants_reschedule = key == "2"
                return self._transfer()

            case _, "0":
                return IvrTurn(lines=[prompts.HUMAN_NOT_YET, self._prompt()])
        return self._invalid()

    def _keyword_choice(self, text: str) -> str | None:
        """Let callers say the option name instead of the number."""
        lowered = text.lower()
        keywords: dict[Node, list[tuple[str, str]]] = {
            Node.MAIN_MENU: [
                ("status", "1"),
                ("interview", "2"),
                ("appointment", "2"),
                ("notice", "2"),
                ("address", "3"),
                ("employment", "4"),
                ("work permit", "4"),
                ("repeat", "9"),
            ],
            Node.APPOINTMENT: [
                ("biometric", "1"),
                ("asylum", "2"),
                ("naturalization", "3"),
                ("citizenship", "3"),
                ("main menu", "*"),
            ],
            Node.ATTENDANCE: [
                ("new date", "2"),
                ("new interview date", "2"),
                ("reschedul", "2"),
                ("attend", "1"),
                ("scheduled", "1"),
            ],
        }
        for keyword, key in keywords.get(self.node, []):
            if keyword in lowered:
                return key
        return None

    # --- open-ended: reason for calling -----------------------------------------

    def _reason(self, text: str) -> IvrTurn:
        topic = classify_reason(text)
        self._reason_attempts += 1
        if topic is None and self._reason_attempts < MAX_REASON_ATTEMPTS:
            return IvrTurn(lines=[prompts.REASON_NOT_UNDERSTOOD, prompts.REASON_PROMPT])
        topic = topic or Topic.OTHER
        self.info.reason_said = text.strip()
        self.info.topic = topic
        ack = prompts.REASON_ACKS[topic]
        if topic is Topic.RESCHEDULE:
            self.info.wants_reschedule = True
            return self._transfer(before=[ack])
        return self._go(Node.ATTENDANCE, before=[ack])

    # --- helpers --------------------------------------------------------------

    def _prompt(self) -> str:
        return {
            Node.MAIN_MENU: prompts.MAIN_MENU,
            Node.APPOINTMENT: prompts.APPOINTMENT_MENU,
            Node.REASON: prompts.REASON_PROMPT,
            Node.ATTENDANCE: prompts.ATTENDANCE_MENU,
        }[self.node]

    def _go(self, node: Node, before: list[str] | None = None) -> IvrTurn:
        self.node = node
        return IvrTurn(lines=[*(before or []), self._prompt()])

    def _info_then_main(self, info: str) -> IvrTurn:
        return self._go(Node.MAIN_MENU, before=[info, prompts.RETURNING_TO_MAIN])

    def _invalid(self) -> IvrTurn:
        return IvrTurn(lines=[prompts.INVALID_OPTION, self._prompt()])

    def _transfer(self, before: list[str] | None = None) -> IvrTurn:
        self.node = Node.TRANSFERRED
        return IvrTurn(lines=before or [], transfer=True)
