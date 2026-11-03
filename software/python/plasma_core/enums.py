from __future__ import annotations

from enum import StrEnum


class Operation(StrEnum):
    ERASE = "erase"
    PROGRAM = "program"
    VERIFY = "verify"
    READ = "read"
    # Complete Flash programming: Erase -> Program -> Verify -> full Readback
    # compare as one Job. PROGRAM stays write-only; the two never substitute.
    FLASH_CYCLE = "flash_cycle"
    STATUS = "status"
    CANCEL = "cancel"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    ABORTED = "aborted"

    @property
    def terminal(self) -> bool:
        return self in {
            JobState.SUCCESS,
            JobState.FAILED,
            JobState.ERROR,
            JobState.CANCELLED,
            JobState.TIMEOUT,
            JobState.ABORTED,
        }


class SiteState(StrEnum):
    DISABLED = "disabled"
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"
