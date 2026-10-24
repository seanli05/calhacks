"""A case's stage, computed rather than stored (C17, C22).

`compute_stage` is pure so the rules are testable without a database;
`reads.case_progress` gathers its inputs.
"""

from enum import StrEnum

from app.contracts import CallState, FastResultStatus, JobStatus, VerificationStatus


class CaseStage(StrEnum):
    RECEIVED = "received"
    EXPLAINING = "explaining"
    NEEDS_BETTER_IMAGE = "needs_better_image"
    NEEDS_ANSWER = "needs_answer"
    CHECKING = "checking"
    SUSPICIOUS = "suspicious"
    UNKNOWN = "unknown"
    AWAITING_CONSENT = "awaiting_consent"
    CALLING = "calling"
    ON_HOLD = "on_hold"
    CONNECTED = "connected"
    CALL_ENDED = "call_ended"
    CLOSED = "closed"


_CALL_STAGES = {
    CallState.DIALING: CaseStage.CALLING,
    CallState.MENU: CaseStage.CALLING,
    CallState.HOLD: CaseStage.ON_HOLD,
    CallState.HUMAN_DETECTED: CaseStage.CONNECTED,
    CallState.BRIDGING: CaseStage.CONNECTED,
    CallState.CONNECTED: CaseStage.CONNECTED,
    # Wrap-up: the line is closed and the report is being written. From the user's
    # side the call is over, and it may never have reached a person.
    CallState.WRAP_UP: CaseStage.CALL_ENDED,
    CallState.ENDED: CaseStage.CALL_ENDED,
}

_VERDICT_STAGES = {
    VerificationStatus.VERIFIED: CaseStage.AWAITING_CONSENT,
    VerificationStatus.SUSPICIOUS: CaseStage.SUSPICIOUS,
    VerificationStatus.UNKNOWN: CaseStage.UNKNOWN,
}

_ACTIVE = {JobStatus.QUEUED, JobStatus.RUNNING}


def compute_stage(
    *,
    closed: bool,
    latest_call_state: CallState | None,
    latest_verification: VerificationStatus | None,
    fast_job: JobStatus | None,
    deep_job: JobStatus | None,
    fast_result: FastResultStatus | None,
) -> CaseStage:
    """Inputs are the latest of each (job status, call state, verdict) for the case.
    Later stages win: a call outranks the verdict, which outranks research."""
    if closed:
        return CaseStage.CLOSED
    if latest_call_state is not None:
        return _CALL_STAGES[CallState(latest_call_state)]
    if latest_verification in _VERDICT_STAGES:
        return _VERDICT_STAGES[VerificationStatus(latest_verification)]
    if fast_job in _ACTIVE:
        return CaseStage.EXPLAINING
    if fast_result == FastResultStatus.NEEDS_BETTER_IMAGE:
        return CaseStage.NEEDS_BETTER_IMAGE
    if fast_result == FastResultStatus.NEEDS_USER_INPUT:
        return CaseStage.NEEDS_ANSWER
    if (
        deep_job in _ACTIVE
        or latest_verification == VerificationStatus.PENDING
        or fast_result == FastResultStatus.OK
    ):
        return CaseStage.CHECKING
    return CaseStage.RECEIVED
