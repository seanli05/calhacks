import pytest
from agency import prompts
from agency.case_record import DEMO_CASE
from agency.ivr import MAX_NO_INPUT, Node, PhoneTree
from agency.speech import Topic, classify_reason, extract_receipt, spoken_digit


def tree_at(node: Node) -> PhoneTree:
    tree = PhoneTree(DEMO_CASE)
    tree.start()
    path = {
        Node.MAIN_MENU: [],
        Node.APPOINTMENT: ["2"],
        Node.RECEIPT: ["2", "2"],
    }[node]
    for key in path:
        tree.press(key)
    assert tree.node is node
    return tree


def press_all(tree: PhoneTree, keys: str):
    turn = None
    for key in keys:
        turn = tree.press(key)
    return turn


def test_greeting_goes_straight_to_english_main_menu():
    turn = PhoneTree(DEMO_CASE).start()
    assert turn.lines == [prompts.GREETING, prompts.MAIN_MENU]


def test_happy_path_by_keypad_reaches_transfer():
    tree = tree_at(Node.RECEIPT)
    turn = press_all(tree, DEMO_CASE.receipt_digits)
    assert tree.node is Node.REASON
    assert prompts.RECEIPT_FOUND in turn.lines

    tree.hear("I have a question about bringing an interpreter")
    assert tree.node is Node.ATTENDANCE

    turn = tree.press("1")
    assert turn.transfer
    assert tree.info.receipt_matched
    assert tree.info.topic is Topic.INTERPRETER
    assert tree.info.wants_reschedule is False


def test_spoken_receipt_needs_confirmation():
    tree = tree_at(Node.RECEIPT)
    turn = tree.hear("Z L A two six nine zero zero one two three four five")
    assert tree.node is Node.RECEIPT_CONFIRM
    assert "Z L A 2 6 9 0 0 1 2 3 4 5" in turn.lines[0]

    tree.hear("yes")
    assert tree.node is Node.REASON
    assert tree.info.receipt_number == DEMO_CASE.receipt_number


def test_saying_no_at_confirmation_asks_again():
    tree = tree_at(Node.RECEIPT)
    tree.hear("ZLA2690012345")
    tree.hear("no")
    assert tree.node is Node.RECEIPT


def test_wrong_receipt_retries_then_moves_on():
    tree = tree_at(Node.RECEIPT)
    for _ in range(2):
        turn = press_all(tree, "1111111111")
        assert tree.node is Node.RECEIPT
        assert prompts.RECEIPT_NOT_FOUND in turn.lines
    press_all(tree, "1111111111")
    assert tree.node is Node.REASON
    assert not tree.info.receipt_matched


def test_pound_submits_partial_keypad_entry():
    tree = tree_at(Node.RECEIPT)
    press_all(tree, "123")
    turn = tree.press("#")
    assert prompts.RECEIPT_NOT_FOUND in turn.lines


def test_reason_step_requires_speech():
    tree = tree_at(Node.RECEIPT)
    press_all(tree, DEMO_CASE.receipt_digits)
    turn = tree.press("1")
    assert tree.node is Node.REASON
    assert prompts.REASON_NEEDS_SPEECH in turn.lines


def test_reschedule_reason_skips_attendance_menu():
    tree = tree_at(Node.RECEIPT)
    press_all(tree, DEMO_CASE.receipt_digits)
    turn = tree.hear("I need to reschedule my interview")
    assert turn.transfer
    assert tree.info.wants_reschedule is True


def test_unclear_reason_reprompts_once_then_accepts():
    tree = tree_at(Node.RECEIPT)
    press_all(tree, DEMO_CASE.receipt_digits)
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
    assert tree.node is Node.RECEIPT


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
    "text",
    [
        "ZLA2690012345",
        "Z, L, A, 2, 6, 9, 0, 0, 1, 2, 3, 4, 5.",
        "My receipt number is zee el ay 269-001-2345",
        "Z L A two six nine oh oh one two three four five",
    ],
)
def test_extract_receipt(text):
    assert extract_receipt(text)[-10:] == DEMO_CASE.receipt_digits


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
