"""The fictional cases the mock agency line can know about, one per deploy.

Keep each case in sync with its demo letter (a mock Form I-797C asylum
interview notice). Everything here is made up; never put real case data here.
"""

from datetime import date

from pydantic import BaseModel


class MockCase(BaseModel):
    receipt_number: str
    a_number: str
    applicant_name: str
    applicant_dob: date
    case_type: str
    notice_date: date
    interview_date: date
    interview_time: str
    interview_office: str
    interview_address: str


DEMO_CASE = MockCase(
    receipt_number="ZLA2690012345",
    a_number="A212345678",
    applicant_name="Ana Morales",
    applicant_dob=date(1988, 3, 14),
    case_type="I-589, Application for Asylum and for Withholding of Removal",
    notice_date=date(2026, 10, 13),
    interview_date=date(2026, 11, 12),
    interview_time="8:30 AM",
    interview_office="Los Angeles Asylum Office",
    interview_address="1585 Corporate Drive, Tustin, California",
)
"""The default case. The backend's database seed and tests depend on it."""

SF_DEMO_CASE = DEMO_CASE.model_copy(
    update={
        "applicant_name": "Mariam Namuna",
        "receipt_number": "ZLA2690412873",
        "a_number": "A219555031",
        "notice_date": date(2026, 10, 19),
        "interview_date": date(2026, 11, 25),
        "interview_time": "8:30 AM",
        "interview_office": "San Francisco Asylum Office",
        "interview_address": (
            "75 Hawthorne Street, Suite 303S, San Francisco, California"
        ),
    }
)
"""The demo video's case: demo/letters/i797c_mariam_namuna.png.

The letter prints no date of birth, so applicant_dob stays DEMO_CASE's.
"""
