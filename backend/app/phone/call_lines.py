"""The runner's fixed lines to a representative. Fixed text, never model output, so
rule 3 and C35 hold by review: the agent says it's automated and calls for the
applicant, and it never names anyone, gives an identifier, or mentions the case."""

INTRO = (
    "Hello, this is an automated assistant calling for an applicant. "
    "The applicant is joining the call now and will speak with you directly. "
    "One moment, please."
)
"""Said once, the moment a person is detected, while the applicant's phone rings."""

HOLDING = (
    "The applicant is joining now and will answer for themselves. One moment, please."
)
"""Said when the representative speaks while the applicant's phone rings, including
when they ask a question the agent must not answer."""

CALL_BACK = (
    "I'm sorry, the applicant can't join right now. "
    "The account holder will call back. Thank you, goodbye."
)
"""Failure rules → the user doesn't answer the bridged call."""
