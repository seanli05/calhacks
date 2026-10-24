"""Hand-written phone trees for the call simulator.

Written from how US agency and large-organization lines generally behave, never
from `mock_agency/` (CLAUDE.md → the mock agency is a test target). They differ on
purpose: wording, structure, key numbers, speech vs. keypad, hold style, and how
the representative answers. `heldout_consular` is held out: run it to see how the
agent does on a line it was never shaped against, and don't tune anything to it.

Every number, name, and agency here is made up.
"""

from app.phone.sim_line import Goodbye, Hold, Menu, Rep, Tree

SIM_BRIEF = {
    "brief_id": "brief_sim",
    "case_id": "case_sim",
    "call_goal_en": (
        "Confirm the applicant's asylum interview is still scheduled, and ask what "
        "to do if their interpreter can't come"
    ),
    "expected_menu_path": [
        "Choose English if a language is offered",
        "Go toward interviews, appointments, or an existing case",
        "If an identifier is requested, don't give it; take the path without it",
        "Ask for a representative when the menu offers one",
    ],
    "must_not_do": [
        "Never give the A-Number, receipt number, or date of birth",
        "Never discuss the asylum claim",
    ],
}

SPEECH_FEDERAL = Tree(
    name="speech_federal",
    about="Conversational speech menu, language pick, two-stage hold, chatty rep",
    start="language",
    nodes={
        "language": Menu(
            prompt=(
                (
                    "Thank you for calling the Federal Immigration Information Line. "
                    "Calls may be monitored for quality."
                ),
                "For English, press 1. Para español, oprima el dos.",
            ),
            keys={"1": "reason", "2": "spanish"},
            words={"english": "reason", "espanol": "spanish"},
            on_fail="reason",
        ),
        "spanish": Goodbye("Por favor, llame de nuevo más tarde. Adiós."),
        "reason": Menu(
            prompt=(
                (
                    "Briefly tell me why you're calling. For example, you can say "
                    "'case status', 'change of address', or 'appointments and interviews'."
                ),
            ),
            words={
                "appointment": "appointments",
                "interview": "appointments",
                "status": "status_info",
                "address": "address_info",
                "representative": "agent_first",
                "agent": "agent_first",
                "person": "agent_first",
            },
            no_match=(
                "Sorry, I didn't get that. You can say things like 'case status' "
                "or 'appointments'."
            ),
            on_fail="unable",
        ),
        "agent_first": Menu(
            prompt=(
                (
                    "I can get you to someone. First, tell me what it's about. Say "
                    "'case status', 'appointments and interviews', or 'something else'."
                ),
            ),
            words={
                "appointment": "appointments",
                "interview": "appointments",
                "status": "status_info",
                "else": "queue",
            },
            on_fail="queue",
        ),
        "appointments": Menu(
            prompt=(
                "Appointments and interviews.",
                "If you need to reschedule a fingerprint appointment, press 1.",
                (
                    "If you have a question about an interview that's already "
                    "scheduled, press 2."
                ),
                "To hear these options again, press 9.",
            ),
            keys={"1": "prints_info", "2": "queue", "9": "appointments"},
            words={"fingerprint": "prints_info", "interview": "queue"},
        ),
        "prints_info": Goodbye(
            "To reschedule a fingerprint appointment, please visit our website. Goodbye."
        ),
        "status_info": Goodbye(
            "You can check your case status online at any time. Goodbye."
        ),
        "address_info": Goodbye("You can change your address online. Goodbye."),
        "unable": Goodbye(
            "We're unable to process your request right now. Please call again later."
        ),
        "goodbye": Goodbye("Thank you for calling. Goodbye."),
        "queue": Hold(
            messages=(
                (
                    "Please hold while I connect you with a representative. Your "
                    "estimated wait time is less than five minutes."
                ),
                (
                    "All representatives are still helping other callers. Please stay "
                    "on the line; your call will be answered in the order received."
                ),
            ),
        ),
        "rep": Rep(
            greeting=(
                "Thank you for holding. My name is Officer Patel. How can I help "
                "you today?"
            ),
            replies=("Okay, sure, I can wait for them.",),
            nudges=("Hello? Are you still there?", "I'm here whenever they're ready."),
            talk=(
                "Hi there, go ahead, how can I help?",
                "I see the interview is still on the calendar for that date.",
                "Is there anything else? Alright, have a good day.",
            ),
        ),
    },
)

KEYPAD_STATE = Tree(
    name="keypad_state",
    about="Touch-tone only (deaf to speech), changed-options notice, queue position",
    start="main",
    nodes={
        "main": Menu(
            prompt=(
                "You have reached the State Department of Human Services.",
                "Please listen carefully, as our menu options have changed.",
                (
                    "For benefit applications, press 3. For appointments and "
                    "interviews, press 5. For all other questions, press 7. To repeat "
                    "this menu, press 9."
                ),
            ),
            keys={"3": "benefits", "5": "appointments", "7": "other", "9": "main"},
            speech=False,
            no_input="We did not receive your selection.",
            no_match="That is not a valid selection.",
            on_fail="disconnect",
        ),
        "appointments": Menu(
            prompt=(
                (
                    "Appointments and interviews. To confirm or ask about a scheduled "
                    "interview, press 1. To cancel an appointment, press 2. To return "
                    "to the main menu, press the star key."
                ),
            ),
            keys={"1": "queue", "2": "cancel_info", "*": "main"},
            speech=False,
            no_input="We did not receive your selection.",
            no_match="That is not a valid selection.",
            on_fail="disconnect",
        ),
        "other": Menu(
            prompt=(
                (
                    "To speak with a caseworker, press 0. To return to the main menu, "
                    "press star."
                ),
            ),
            keys={"0": "queue", "*": "main"},
            speech=False,
            on_fail="disconnect",
        ),
        "benefits": Goodbye(
            "Applications are accepted online or at your local office. Goodbye."
        ),
        "cancel_info": Goodbye("Your request has been noted. Goodbye."),
        "disconnect": Goodbye(
            "We're sorry, we did not receive a valid response. Goodbye."
        ),
        "goodbye": Goodbye("Goodbye."),
        "queue": Hold(
            messages=(
                "You are caller number three. Please continue to hold.",
                "You are caller number one. A caseworker will be with you shortly.",
            ),
        ),
        "rep": Rep(
            greeting="Human Services, this is Dana speaking. Who am I speaking with?",
            replies=("Oh, okay. I'll wait.",),
            talk=(
                "Hi, what can I do for you today?",
                "Alright, let me pull that up.",
                "Okay, you're all set. Bye now.",
            ),
        ),
    },
)

IDENTIFIER_FIRST = Tree(
    name="identifier_first",
    about="Asks for a receipt number up front; close topics; rep asks for an ID",
    start="intro",
    answers=(2,),
    nodes={
        "intro": Menu(
            prompt=(
                "Welcome to the Asylum Office information line.",
                (
                    "If you have your thirteen-character receipt number, please say or "
                    "enter it now. If you don't have it, say 'I don't have it', or press "
                    "the star key."
                ),
            ),
            keys={"*": "topics"},
            words={"don't have": "topics", "do not have": "topics"},
            no_match="Sorry, that doesn't look like a valid receipt number.",
            on_fail="topics",
        ),
        "topics": Menu(
            prompt=(
                "Please choose from the following.",
                "For questions about a pending asylum application, press 4.",
                "For interview scheduling and interview notices, press 6.",
                "For fingerprint appointments, press 8.",
            ),
            keys={"4": "queue", "6": "queue", "8": "prints"},
            words={"pending": "queue", "interview": "queue", "fingerprint": "prints"},
        ),
        "prints": Goodbye("Fingerprint appointments are handled online. Goodbye."),
        "goodbye": Goodbye("Thank you for calling. Goodbye."),
        "queue": Hold(
            messages=("Your call is important to us. Please remain on the line.",),
        ),
        "rep": Rep(
            greeting=(
                "Asylum office, this is Jordan. Can I start with the applicant's "
                "receipt number?"
            ),
            replies=("Okay.",),
            nudges=(
                "Hello? I'll need the receipt number to look anything up.",
                "Are you still with me?",
            ),
            user_answer_s=9.0,
            talk=(
                "Hi, I'm here. Can you read me the receipt number?",
                "Thanks. The interview is still scheduled.",
                "Okay, take care.",
            ),
        ),
    },
)

TRANSFER_UNREACHABLE = Tree(
    name="transfer_unreachable",
    about="Speech menu, hold, transfer into a second menu, hold; user doesn't answer",
    start="main",
    nodes={
        "main": Menu(
            prompt=(
                "Thank you for calling Visa and Immigration Customer Service.",
                (
                    "Say 'status' for the status of an application, 'appointments' for "
                    "appointment questions, or 'representative' to speak with someone."
                ),
            ),
            keys={"1": "status_info", "2": "transfer", "0": "transfer"},
            words={
                "status": "status_info",
                "appointment": "transfer",
                "representative": "transfer",
                "agent": "transfer",
            },
        ),
        "status_info": Goodbye("Status information is available online. Goodbye."),
        "goodbye": Goodbye("Goodbye."),
        "transfer": Hold(
            messages=("Please hold while we transfer your call.",), then="scheduling"
        ),
        "scheduling": Menu(
            prompt=(
                "You've reached the scheduling unit.",
                (
                    "For a new appointment, press 1. For an existing appointment or "
                    "interview, press 2."
                ),
            ),
            keys={"1": "new_appointment", "2": "queue"},
            words={"existing": "queue", "interview": "queue", "new": "new_appointment"},
        ),
        "new_appointment": Goodbye("New appointments are booked online. Goodbye."),
        "queue": Hold(
            messages=(
                (
                    "Thank you for waiting. The next available representative will be "
                    "with you shortly."
                ),
            ),
        ),
        "rep": Rep(
            greeting="Scheduling, this is Sam. What can I help you with?",
            replies=("Sure, no problem.", "Okay."),
            nudges=("Hello?", "Are they still coming?"),
            user_answers=False,
            ring_timeout_s=15.0,
        ),
    },
)

HELDOUT_CONSULAR = Tree(
    name="heldout_consular",
    about="HELD OUT. Named virtual assistant, yes/no confirm, rep gives a badge number",
    start="assistant",
    held_out=True,
    nodes={
        "assistant": Menu(
            prompt=(
                (
                    "Hi, I'm Ava, the virtual assistant for the Consular Services "
                    "Center. I can answer questions or connect you to an agent. What can "
                    "I help you with today?"
                ),
            ),
            words={
                "interview": "confirm",
                "appointment": "confirm",
                "agent": "agent_reason",
                "representative": "agent_reason",
                "person": "agent_reason",
            },
            no_match="Sorry, I'm still learning. Could you say that another way?",
            on_fail="agent_reason",
        ),
        "agent_reason": Menu(
            prompt=(
                (
                    "Sure, I can get you to an agent. So I can route your call, briefly "
                    "tell me what it's about."
                ),
            ),
            words={
                "interview": "confirm",
                "appointment": "confirm",
                "schedul": "confirm",
            },
            on_fail="queue",
        ),
        "confirm": Menu(
            prompt=(
                (
                    "Got it, you have a question about an interview appointment. Is that "
                    "right? Please say yes or no."
                ),
            ),
            keys={"1": "queue", "2": "assistant"},
            words={
                "yes": "queue",
                "yeah": "queue",
                "correct": "queue",
                "no": "assistant",
            },
        ),
        "goodbye": Goodbye("Thanks for calling. Goodbye."),
        "queue": Hold(
            messages=(
                "The current wait time is approximately four minutes.",
                "While you wait, many questions can be answered on our website.",
            ),
        ),
        "rep": Rep(
            greeting=(
                "Good afternoon, consular services, my name is Lee, badge number "
                "4471. Who do I have the pleasure of speaking with?"
            ),
            replies=("Oh, okay. Sure, I'll hold for them.",),
            talk=("Hello, how can I help you?", "Alright, I've noted that. Goodbye."),
        ),
    },
)

TREES = {
    tree.name: tree
    for tree in (
        SPEECH_FEDERAL,
        KEYPAD_STATE,
        IDENTIFIER_FIRST,
        TRANSFER_UNREACHABLE,
        HELDOUT_CONSULAR,
    )
}
