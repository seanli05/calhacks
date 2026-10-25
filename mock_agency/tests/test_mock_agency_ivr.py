import pytest
from agency import prompts
from agency.case_record import DEMO_CASE
from agency.ivr import MAX_NO_INPUT, Node, PhoneTree
from agency.speech import Topic, classify_reason, spoken_digit


def tree_at(node: Node) -> PhoneTree:
    tree = PhoneTree(DEMO_CASE)
    tree.start()
    path = {
        Node.MAIN_MENU: [],
        Node.APPOINTMENT: ["2"],
        Node.REASON: ["2", "2"],
    }[node]
    for key in path:
        tree.press(key)
    assert tree.node is node
    return tree


def test_greeting_goes_straight_to_english_main_menu():
    turn = PhoneTree(DEMO_CASE).start()
    assert turn.lines == [prompts.GREETING, prompts.MAIN_MENU]


def test_happy_path_reaches_transfer_without_any_identifier():
    tree = tree_at(Node.APPOINTMENT)
    turn = tree.press("2")
    assert tree.node is Node.REASON
    assert turn.lines == [prompts.REASON_PROMPT]

    tree.hear("I have a question about bringing an interpreter")
    assert tree.node is Node.ATTENDANCE

    turn = tree.press("1")
    assert turn.transfer
    assert tree.info.topic is Topic.INTERPRETER
    assert tree.info.wants_reschedule is False


def test_no_prompt_asks_for_an_identifier():
    """C35: the phone agent never gives one, so the menu never asks."""
    said = " ".join(
        value
        for name, value in vars(prompts).items()
        if name.isupper() and isinstance(value, str)
    ).lower()
    for asked in ("your receipt number", "a-number", "date of birth"):
        assert asked not in said


def test_reason_step_requires_speech():
    tree = tree_at(Node.REASON)
    turn = tree.press("1")
    assert tree.node is Node.REASON
    assert prompts.REASON_NEEDS_SPEECH in turn.lines


def test_reschedule_reason_skips_attendance_menu():
    tree = tree_at(Node.REASON)
    turn = tree.hear("I need to reschedule my interview")
    assert turn.transfer
    assert tree.info.wants_reschedule is True


def test_unclear_reason_reprompts_once_then_accepts():
    tree = tree_at(Node.REASON)
    turn = tree.hear("um, hello?")
    assert tree.node is Node.REASON
    assert prompts.REASON_NOT_UNDERSTOOD in turn.lines
    tree.hear("it's complicated")
    assert tree.node is Node.ATTENDANCE
    assert tree.info.topic is Topic.OTHER


def test_menus_accept_spoken_numbers_and_option_names():
    tree = tree_at(Node.MAIN_MENU)
    tree.hear("press two")
    assert tree.node is Node.APPOINTMENT
    tree.hear("asylum interview")
    assert tree.node is Node.REASON


def test_wrong_branch_returns_to_main_menu():
    tree = tree_at(Node.MAIN_MENU)
    turn = tree.press("1")
    assert tree.node is Node.MAIN_MENU
    assert prompts.CASE_STATUS_INFO in turn.lines


def test_asking_for_a_human_does_not_skip_the_menu():
    tree = tree_at(Node.MAIN_MENU)
    turn = tree.hear("representative")
    assert tree.node is Node.MAIN_MENU
    assert prompts.HUMAN_NOT_YET in turn.lines
    turn = tree.press("0")
    assert prompts.HUMAN_NOT_YET in turn.lines


def test_invalid_key_repeats_prompt():
    tree = tree_at(Node.MAIN_MENU)
    turn = tree.press("7")
    assert turn.lines == [prompts.INVALID_OPTION, prompts.MAIN_MENU]


def test_silence_hangs_up_after_max_no_input():
    tree = tree_at(Node.MAIN_MENU)
    for _ in range(MAX_NO_INPUT - 1):
        assert not tree.no_input().hang_up
    assert tree.no_input().hang_up


def test_input_resets_no_input_count():
    tree = tree_at(Node.MAIN_MENU)
    for _ in range(MAX_NO_INPUT - 1):
        tree.no_input()
    tree.press("9")
    assert not tree.no_input().hang_up


@pytest.mark.parametrize(
    ("text", "digit"),
    [("two", "2"), ("Press 1.", "1"), ("one or two", None), ("I want to go", None)],
)
def test_spoken_digit(text, digit):
    assert spoken_digit(text) == digit


@pytest.mark.parametrize(
    ("text", "topic"),
    [
        ("I can't make it on that day, I need a new date", Topic.RESCHEDULE),
        ("Do I have to bring my own interpreter?", Topic.INTERPRETER),
        ("What documents should I bring", Topic.DOCUMENTS),
        ("Where is the interview?", Topic.DATE_AND_LOCATION),
        ("Can my lawyer join remotely", Topic.ATTORNEY),
        ("hello", None),
    ],
)
def test_classify_reason(text, topic):
    assert classify_reason(text) is topic


def test_short_tree_opens_on_the_appointment_menu_without_a_main_menu():
    tree = PhoneTree(DEMO_CASE, short=True)
    turn = tree.start()
    assert turn.lines == [prompts.GREETING, prompts.APPOINTMENT_OPTIONS]
    assert "star" not in prompts.APPOINTMENT_OPTIONS
    assert tree.node is Node.APPOINTMENT


def test_short_tree_goes_from_asylum_to_reason_to_transfer():
    tree = PhoneTree(DEMO_CASE, short=True)
    tree.start()
    assert tree.press("2").lines == [prompts.REASON_PROMPT]
    turn = tree.hear("I have a question about interpreters for my interview")
    assert turn.transfer
    assert turn.lines == [prompts.REASON_ACKS[Topic.INTERPRETER]]
    assert tree.info.topic is Topic.INTERPRETER


def test_short_tree_skips_attendance_even_for_a_non_reschedule_reason():
    tree = PhoneTree(DEMO_CASE, short=True)
    tree.start()
    tree.press("2")
    assert tree.hear("where is my interview").transfer
    assert tree.info.wants_reschedule is None


def test_short_tree_wrong_branch_returns_to_the_appointment_menu():
    tree = PhoneTree(DEMO_CASE, short=True)
    tree.start()
    turn = tree.press("1")
    assert turn.lines == [prompts.NOT_ASYLUM_INFO, prompts.APPOINTMENT_OPTIONS]
    assert tree.node is Node.APPOINTMENT
    assert tree.press("*").lines == [
        prompts.INVALID_OPTION,
        prompts.APPOINTMENT_OPTIONS,
    ]
