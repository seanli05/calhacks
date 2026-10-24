"""The single fictional case the mock agency line knows about.

Keep these values in sync with the demo letter (a mock Form I-797C asylum
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

    @property
    def receipt_digits(self) -> str:
        return self.receipt_number[3:]


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
