from __future__ import annotations

from .enums import JobState
from .errors import ErrorCode, PlasmaError


INFRASTRUCTURE_ERROR_CODES = frozenset(
    {
        ErrorCode.CONNECTION_FAILED,
        ErrorCode.CONNECTION_TIMEOUT,
        ErrorCode.INTERFACE_FAILURE,
        ErrorCode.INTERFACE_NOT_CONFIGURED,
        ErrorCode.OUTPUT_WRITE_FAILED,
        ErrorCode.INTERNAL_ERROR,
        ErrorCode.JOB_ABORTED,
    }
)

OPERATION_FAILURE_CODES = frozenset(
    {
        ErrorCode.ERASE_FAILED,
        ErrorCode.PROGRAM_FAILED,
        ErrorCode.VERIFY_FAILED,
        ErrorCode.READ_FAILED,
        ErrorCode.OPERATION_TIMEOUT,
    }
)


def failure_source(error: PlasmaError) -> str:
    """Return the stable failure-origin taxonomy used by Batch statistics.

    Interfaces may provide a more precise source in ``error.context``. The
    fallback classification intentionally avoids guessing physical root cause:
    operation failures stay ``operation`` unless the producer explicitly marks
    them as ``injected`` or ``mismatch``.
    """

    explicit = error.context.get("failure_source")
    if isinstance(explicit, str) and explicit:
        return explicit
    if error.code is ErrorCode.OPERATION_CANCELLED:
        return "cancelled"
    if error.code in INFRASTRUCTURE_ERROR_CODES:
        return "infrastructure"
    return "operation"


def terminal_state_for_error(error: PlasmaError) -> JobState:
    """Map an execution error to a truthful terminal Job state.

    Existing TIMEOUT remains a dedicated terminal state for compatibility.
    Infrastructure faults become ERROR instead of being misreported as target
    programming failures. Operation-level failures remain FAILED.
    """

    if error.code is ErrorCode.OPERATION_CANCELLED:
        return JobState.CANCELLED
    if error.code is ErrorCode.OPERATION_TIMEOUT:
        return JobState.TIMEOUT
    if error.code in INFRASTRUCTURE_ERROR_CODES:
        return JobState.ERROR
    return JobState.FAILED
