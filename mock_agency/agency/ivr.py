"""The phone tree as a pure state machine, with no Line SDK imports.

The Line adapter in main.py feeds it key presses, transcripts, and no-input
timeouts, and plays back the returned IvrTurn. Keeping it pure lets us test
every path without a call.

Tree:
    LANGUAGE        closed  1 English, 2 Spanish (unavailable, falls through)
    MAIN_MENU       closed  1 status, 2 interview notice, 3 address, 4 work permit
    APPOINTMENT     closed  1 biometrics, 2 asylum interview, 3 naturalization
    RECEIPT         open    say the receipt number, or key its 10 digits + #
    RECEIPT_CONFIRM closed  yes/1 or no/2
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
    extract_receipt,
    spell_out,
    spoken_digit,
    yes_or_no,
)
from pydantic import BaseModel, Field

MAX_NO_INPUT = 3
MAX_RECEIPT_ATTEMPTS = 3
MAX_REASON_ATTEMPTS = 2
RECEIPT_KEYPAD_DIGITS = 10


class Node(StrEnum):
    LANGUAGE = "language"
    MAIN_MENU = "main_menu"
    APPOINTMENT = "appointment"
    RECEIPT = "receipt"
    RECEIPT_CONFIRM = "receipt_confirm"
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

    receipt_number: str | None = None
    receipt_matched: bool = False
    reason_said: str | None = None
    topic: Topic | None = None
    wants_reschedule: bool | None = None

    def summary(self) -> str:
        receipt = self.receipt_number or "not given"
        matched = "matches the case record" if self.receipt_matched else "not matched"
        attendance = {
            True: "needs a new interview date",
            False: "plans to attend as scheduled",
            None: "not asked",
        }[self.wants_reschedule]
        return (
            f"- Receipt number entered: {receipt} ({matched})\n"
            f'- Reason for calling, in their words: "{self.reason_said or "not given"}"\n'
            f"- Topic: {self.topic or 'unknown'}\n"
            f"- Attendance: {attendance}"
        )


class PhoneTree:
    def __init__(self, case: MockCase) -> None:
        self.case = case
        self.node = Node.LANGUAGE
        self.info = CallerInfo()
        self._no_input_count = 0
        self._receipt_attempts = 0
        self._reason_attempts = 0
        self._keypad_buffer = ""
        self._pending_receipt: str | None = None

    # --- inputs -------------------------------------------------------------

    def start(self) -> IvrTurn:
        return IvrTurn(lines=[prompts.GREETING, prompts.LANGUAGE_MENU])

    def press(self, key: str) -> IvrTurn:
        """Handle one DTMF key press."""
        self._no_input_count = 0
        if self.node is Node.RECEIPT:
            return self._receipt_key(key)
        if self.node is Node.REASON:
            return IvrTurn(lines=[prompts.REASON_NEEDS_SPEECH, prompts.REASON_PROMPT])
        return self._choose(key)

    def hear(self, text: str) -> IvrTurn:
        """Handle one finished spoken turn."""
        self._no_input_count = 0
        if self.node is Node.RECEIPT:
            return self._receipt_spoken(text)
        if self.node is Node.REASON:
            return self._reason(text)
        if self.node is Node.RECEIPT_CONFIRM:
            answer = yes_or_no(text)
            if answer is not None:
                return self._choose("1" if answer else "2")
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
            case Node.LANGUAGE, "1":
                return self._go(Node.MAIN_MENU)
            case Node.LANGUAGE, "2":
                return self._go(Node.MAIN_MENU, before=[prompts.SPANISH_UNAVAILABLE])

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
                return self._go(Node.RECEIPT)
            case Node.APPOINTMENT, "*":
                return self._go(Node.MAIN_MENU)

            case Node.RECEIPT_CONFIRM, "1":
                return self._accept_receipt()
            case Node.RECEIPT_CONFIRM, "2":
                self._pending_receipt = None
                return self._go(Node.RECEIPT)

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
            Node.LANGUAGE: [("english", "1"), ("español", "2"), ("spanish", "2")],
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

    # --- open-ended: receipt number ---------------------------------------------

    def _receipt_key(self, key: str) -> IvrTurn:
        if key.isdigit():
            self._keypad_buffer += key
            if len(self._keypad_buffer) < RECEIPT_KEYPAD_DIGITS:
                return IvrTurn()
        elif key != "#":
            return IvrTurn()
        entered, self._keypad_buffer = self._keypad_buffer, ""
        if not entered:
            return IvrTurn(lines=[prompts.RECEIPT_NOT_HEARD, prompts.RECEIPT_PROMPT])
        return self._check_receipt(entered)

    def _receipt_spoken(self, text: str) -> IvrTurn:
        if asks_for_human(text) and extract_receipt(text) is None:
            return IvrTurn(lines=[prompts.HUMAN_NOT_YET, prompts.RECEIPT_PROMPT])
        receipt = extract_receipt(text)
        if receipt is None:
            return self._receipt_retry(prompts.RECEIPT_NOT_HEARD)
        self._pending_receipt = receipt
        self.node = Node.RECEIPT_CONFIRM
        return IvrTurn(
            lines=[prompts.RECEIPT_CONFIRM.format(spelled=spell_out(receipt))]
        )

    def _accept_receipt(self) -> IvrTurn:
        receipt, self._pending_receipt = self._pending_receipt or "", None
        return self._check_receipt(receipt)

    def _check_receipt(self, receipt: str) -> IvrTurn:
        """Match on the 10 digits; STT mishears letters far more often than digits."""
        self.info.receipt_number = receipt
        if receipt[-RECEIPT_KEYPAD_DIGITS:] == self.case.receipt_digits:
            self.info.receipt_number = self.case.receipt_number
            self.info.receipt_matched = True
            return self._go(Node.REASON, before=[prompts.RECEIPT_FOUND])
        return self._receipt_retry(prompts.RECEIPT_NOT_FOUND)

    def _receipt_retry(self, problem: str) -> IvrTurn:
        self._receipt_attempts += 1
        if self._receipt_attempts >= MAX_RECEIPT_ATTEMPTS:
            return self._go(Node.REASON, before=[problem, prompts.RECEIPT_GIVE_UP])
        return self._go(Node.RECEIPT, before=[problem])

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
            Node.LANGUAGE: prompts.LANGUAGE_MENU,
            Node.MAIN_MENU: prompts.MAIN_MENU,
            Node.APPOINTMENT: prompts.APPOINTMENT_MENU,
            Node.RECEIPT: prompts.RECEIPT_PROMPT,
            Node.RECEIPT_CONFIRM: prompts.RECEIPT_CONFIRM.format(
                spelled=spell_out(self._pending_receipt or "")
            ),
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
