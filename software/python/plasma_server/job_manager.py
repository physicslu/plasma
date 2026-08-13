from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from plasma_core.enums import JobState
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest, JobResult, iso_now


@dataclass(slots=True)
class JobRuntime:
    request: JobRequest
    future: asyncio.Future[JobResult]
    state: JobState = JobState.QUEUED
    created_at: str = ""
    started_at: str | None = None
    active_task: asyncio.Task[Any] | None = None
    cancel_requested: bool = False
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    result: JobResult | None = None
    stage: str | None = None
    stage_state: str | None = None
    stage_progress_percent: float = 0.0
    progress_percent: float = 0.0
    bytes_done: int | None = None
    bytes_total: int | None = None
    attempt: int = 0
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = iso_now()
        if not self.updated_at:
            self.updated_at = self.created_at

    def snapshot(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "job_id": self.request.job_id,
            "channel_id": self.request.channel_id,
            "operation": self.request.operation.value,
            "state": self.state.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "cancel_requested": self.cancel_requested,
            "stage": self.stage,
            "stage_state": self.stage_state,
            "stage_progress_percent": self.stage_progress_percent,
            "progress_percent": self.progress_percent,
            "bytes_done": self.bytes_done,
            "bytes_total": self.bytes_total,
            "attempt": self.attempt,
            "updated_at": self.updated_at,
        }
        if self.result:
            data["result"] = self.result.to_dict()
        return data


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRuntime] = {}

    def create(self, request: JobRequest) -> JobRuntime:
        if request.job_id in self._jobs:
            raise PlasmaError(ErrorCode.DUPLICATE_JOB, f"job already exists: {request.job_id}")
        future: asyncio.Future[JobResult] = asyncio.get_running_loop().create_future()
        runtime = JobRuntime(request=request, future=future)
        self._jobs[request.job_id] = runtime
        return runtime

    def get(self, job_id: str) -> JobRuntime:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise PlasmaError(ErrorCode.JOB_NOT_FOUND, f"job not found: {job_id}") from exc

    def all(self) -> list[JobRuntime]:
        return list(self._jobs.values())
