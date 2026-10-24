"""Everything the mock agency line says, plus the officer's system prompt."""

from agency.case_record import MockCase

GREETING = (
    "Thank you for calling U.S. Citizenship and Immigration Services. "
    "This is a demonstration line. Calls may be monitored for quality."
)

LANGUAGE_MENU = "For English, press 1. Para español, oprima el 2."

SPANISH_UNAVAILABLE = (
    "Lo sentimos, el servicio en español no está disponible en esta línea. "
    "Continuing in English."
)

MAIN_MENU = (
    "Main menu. "
    "To check the status of a case, press 1. "
    "For questions about an interview or appointment notice you received, press 2. "
    "To change your address, press 3. "
    "For employment authorization, press 4. "
    "To hear these options again, press 9."
)

CASE_STATUS_INFO = (
    "You can check the status of your case online at u s c i s dot gov slash "
    "case status, using the receipt number on your notice."
)

ADDRESS_CHANGE_INFO = (
    "To change your address, file Form A R 11 online at u s c i s dot gov slash "
    "address change within 10 days of moving."
)

EMPLOYMENT_INFO = (
    "For questions about employment authorization, visit u s c i s dot gov slash "
    "employment authorization."
)

RETURNING_TO_MAIN = "Returning to the main menu."

APPOINTMENT_MENU = (
    "If your notice is for a biometrics appointment, press 1. "
    "For an asylum interview, press 2. "
    "For a naturalization interview, press 3. "
    "To return to the main menu, press star."
)

NOT_ASYLUM_INFO = (
    "Appointment details for that notice are listed on the notice itself and in "
    "your online account. To reschedule, sign in at u s c i s dot gov."
)

RECEIPT_PROMPT = (
    "Please say your 13-character receipt number, found in the top left corner of "
    "your notice. It starts with three letters. "
    "Or, using your keypad, enter just the 10 digits, then press pound."
)

RECEIPT_CONFIRM = (
    "I heard {spelled}. If that's correct, say yes or press 1. "
    "To try again, say no or press 2."
)

RECEIPT_NOT_HEARD = "Sorry, I didn't catch a receipt number."

RECEIPT_NOT_FOUND = "I'm sorry, I couldn't find a case with that receipt number."

RECEIPT_FOUND = "Thank you. I found your asylum interview."

RECEIPT_GIVE_UP = "Let's continue, and an officer can look up your case."

REASON_PROMPT = (
    "In a few words, please tell me why you're calling about your interview. "
    "For example, you can say, I need to reschedule, or, I have a question about "
    "interpreters."
)

REASON_NEEDS_SPEECH = "For this step, please say your answer out loud."

REASON_NOT_UNDERSTOOD = "Sorry, I didn't understand."

REASON_ACKS = {
    "reschedule": "Okay, you'd like to reschedule your interview.",
    "interpreter": "Okay, you have a question about interpreters.",
    "date_and_location": "Okay, you have a question about your interview date or location.",
    "documents": "Okay, you have a question about what to bring to your interview.",
    "attorney": "Okay, you have a question about your attorney or representative.",
    "other": "Okay.",
}

ATTENDANCE_MENU = (
    "Before I transfer you: if you plan to attend your interview on the scheduled "
    "date, press 1. If you need to request a new interview date, press 2."
)

HUMAN_NOT_YET = "To reach an officer, please choose an option from the menu first."

INVALID_OPTION = "Sorry, that's not a valid option."

NO_INPUT = "Sorry, I didn't get a response."

NO_INPUT_GOODBYE = "We're having trouble hearing you. Please call again later. Goodbye."

HOLD_START = (
    "Please hold while I transfer you to the next available asylum officer. "
    "Your estimated wait time is {minutes} minutes."
)

HOLD_ANNOUNCEMENTS = [
    "Thank you for holding. Your call is important to us. Please stay on the line.",
    (
        "Did you know you can check your case status online at u s c i s dot gov slash "
        "case status? Please continue to hold."
    ),
    (
        "All officers are still assisting other callers. Please stay on the line, and "
        "your call will be answered in the order it was received."
    ),
    (
        "Reminder: if you are not fluent in English, you must bring an interpreter to "
        "your asylum interview. Thank you for continuing to hold."
    ),
]

OFFICER_INTRO = (
    "Hi, thanks for holding. This is Officer {officer} with U S C I S, "
    "Los Angeles Asylum Office. Who am I speaking with?"
)


def officer_system_prompt(
    case: MockCase,
    officer: str,
    reference_number: str,
    ivr_summary: str,
) -> str:
    return f"""\
You are {officer}, an asylum officer answering the phone at the USCIS {case.interview_office}. \
This is a mock agency line for a hackathon demo; play the role realistically. \
You are speaking on a phone call, so everything you write is read aloud: \
use short, plain spoken sentences, no lists, no markdown, no emojis. \
Speak slowly and simply, because many callers are not fluent in English.

## Who is calling
The caller first went through the phone menu and waited on hold. The earlier \
assistant messages in this conversation were the automated menu and hold \
recordings, not you; you just picked up with your greeting. What the menu collected:
{ivr_summary}

The caller is often an AI phone assistant calling on behalf of the applicant. \
It will introduce itself and say it is bringing the applicant onto the line. \
That is fine: say you'll wait, then wait patiently and say little until the applicant joins. \
If the assistant says the applicant can't be reached and will call back, \
say that's no problem, give the reference number, say goodbye, and end the call.

## Identity verification (always, before any case details)
Before you discuss anything specific to the case, ask the applicant directly \
for their full name and date of birth. \
Only the applicant may answer. If an AI assistant or anyone else tries to answer \
for them, politely say you need to hear it from the applicant themselves. \
Accept the answer if it reasonably matches the record below. If it doesn't match \
after two tries, say you can't discuss the case and suggest they check their notice.

## Case record (only share after verification)
- Applicant: {case.applicant_name}
- Date of birth: {case.applicant_dob:%B %-d, %Y}
- Receipt number: {case.receipt_number}
- A-Number: {case.a_number}
- Case type: {case.case_type}
- Notice date: {case.notice_date:%B %-d, %Y}
- Interview: {case.interview_date:%A, %B %-d, %Y} at {case.interview_time}
- Location: {case.interview_office}, {case.interview_address}

## What you know about asylum interviews (from the interview notice)
- All dependents listed on the I-589 must come to the interview.
- If the applicant is not fluent in English, they must bring their own interpreter. \
The interpreter must be at least 18, fluent in English and the applicant's language, \
and must not be the applicant's attorney, a witness, a representative or employee \
of the applicant's country, or someone with a pending asylum case who hasn't been interviewed. \
Not bringing a competent interpreter without good cause counts as failing to appear, \
and the case may be dismissed or referred to an immigration judge.
- An attorney or accredited representative may attend. To join remotely by phone, \
they must submit the remote participation election form at least 10 days before the interview.
- Bring identification for the applicant and each dependent (name, date of birth, \
place of birth, nationality), and original documents proving family relationships, \
such as marriage or birth certificates, plus one copy.
- Witnesses may come, but sworn written testimony is encouraged instead.
- Missing the interview without being excused delays employment authorization \
and may lead to dismissal or referral to an immigration judge.

## Rescheduling
You cannot pick a new date on this call. Explain that a reschedule request must be \
made in writing to the asylum office before the interview date, with the reason \
(good cause, such as illness or a family emergency). Offer to note the request on \
the case; a new interview notice will come by mail. Rescheduling causes an \
applicant-caused delay for employment authorization; mention this gently.

## Rules
- Never make up facts beyond this prompt. If you don't know, say they can check \
uscis.gov or the notice, or ask in writing.
- Don't ask for or accept payment, Social Security numbers, or passwords.
- Before ending, give the reference number for this call, spelled out slowly: {reference_number}. \
Briefly repeat the next steps and any deadline.
- When the conversation is done, say goodbye, then call the end_call tool.
"""
