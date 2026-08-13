from __future__ import annotations

from enum import StrEnum


class Operation(StrEnum):
    ERASE = "erase"
    PROGRAM = "program"
    VERIFY = "verify"
    READ = "read"
    STATUS = "status"
    CANCEL = "cancel"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    ABORTED = "aborted"

    @property
    def terminal(self) -> bool:
        return self in {
            JobState.SUCCESS,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.TIMEOUT,
            JobState.ABORTED,
        }


class ChannelState(StrEnum):
    DISABLED = "disabled"
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"
