from __future__ import annotations

import asyncio
import contextlib
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from plasma_core.config import SiteConfig
from plasma_core.enums import JobState, SiteState
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.job_logging import JobEventLogger, OutputManager
from plasma_core.models import ErrorDetail, ExecutionOutput, JobResult, iso_now
from plasma_handlers.base import BaseHandler

from .job_manager import JobRuntime


def _terminal_log_event(state: JobState) -> tuple[str, str]:
    """Return the structured log event and level for a terminal job state."""
    events = {
        JobState.SUCCESS: ("job_completed", "INFO"),
        JobState.CANCELLED: ("job_cancelled", "WARNING"),
        JobState.TIMEOUT: ("job_timeout", "ERROR"),
        JobState.ABORTED: ("job_aborted", "ERROR"),
        JobState.FAILED: ("job_failed", "ERROR"),
    }
    try:
        return events[state]
    except KeyError as exc:
        raise ValueError(f"job state is not terminal: {state.value}") from exc


class SiteWorker:
    """Execute queued jobs for one Programming Site inside a PPU."""

    def __init__(
        self,
        config: SiteConfig,
        handler: BaseHandler,
        output: OutputManager,
        log_root: Path,
        concurrency: asyncio.Semaphore,
        queue_depth: int,
    ) -> None:
        self.config = config
        self.handler = handler
        self.output = output
        self.log_root = log_root
        self.concurrency = concurrency
        self.queue: asyncio.Queue[JobRuntime | None] = asyncio.Queue(maxsize=queue_depth)
        self.state = SiteState.IDLE
        self.current: JobRuntime | None = None
        self._runner: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._runner is None:
            self._runner = asyncio.create_task(self._run(), name=f"plasma-SITE{self.config.id}")

    async def stop(self) -> None:
        if self._runner is None:
            return
        if self.current and self.current.active_task and not self.current.active_task.done():
            self.current.cancel_requested = True
            self.current.active_task.cancel()
        await self.queue.put(None)
        await self._runner
        self._runner = None
        self.state = SiteState.STOPPED

    def enqueue(self, runtime: JobRuntime) -> None:
        try:
            self.queue.put_nowait(runtime)
        except asyncio.QueueFull as exc:
            raise PlasmaError(
                ErrorCode.SITE_BUSY,
                f"SITE{self.config.id} queue is full",
                recoverable=True,
            ) from exc
        if self.state is SiteState.IDLE:
            self.state = SiteState.QUEUED

    def cancel(self, runtime: JobRuntime) -> None:
        if runtime.state.terminal:
            return
        runtime.cancel_requested = True
        runtime.cancel_event.set()
        if runtime.active_task and not runtime.active_task.done():
            runtime.active_task.cancel()

    @asynccontextmanager
    async def _concurrency_slot(self, runtime: JobRuntime):
        """Acquire the global slot while still allowing an immediate queued cancel."""
        acquire_task = asyncio.create_task(self.concurrency.acquire())
        cancel_task = asyncio.create_task(runtime.cancel_event.wait())
        acquired = False
        released = False
        try:
            await asyncio.wait({acquire_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
            if acquire_task.done() and not acquire_task.cancelled():
                acquire_task.result()
                acquired = True
            if runtime.cancel_requested:
                if not acquire_task.done():
                    acquire_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await acquire_task
                elif not acquired:
                    acquire_task.result()
                if acquired:
                    self.concurrency.release()
                    acquired = False
                    released = True
                yield False
                return
            if not acquired:
                await acquire_task
                acquired = True
            yield True
        finally:
            cancel_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cancel_task
            if not acquire_task.done():
                acquire_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await acquire_task
            elif (
                not acquired
                and not released
                and not acquire_task.cancelled()
                and acquire_task.exception() is None
            ):
                self.concurrency.release()
            if acquired:
                self.concurrency.release()

    async def _run(self) -> None:
        while True:
            runtime = await self.queue.get()
            if runtime is None:
                self.queue.task_done()
                break
            self.current = runtime
            try:
                try:
                    await self._process(runtime)
                except Exception as exc:
                    await self._emergency_failure(runtime, exc)
            finally:
                self.current = None
                self.state = SiteState.QUEUED if not self.queue.empty() else SiteState.IDLE
                self.queue.task_done()

    async def _emergency_failure(self, runtime: JobRuntime, failure: Exception) -> None:
        """Resolve the Job even if logging/output/plugin infrastructure fails."""
        request = runtime.request
        if isinstance(failure, PlasmaError):
            error = failure
        elif isinstance(failure, OSError):
            error = PlasmaError(
                ErrorCode.OUTPUT_WRITE_FAILED,
                "job infrastructure write failed",
                original_exception=failure,
            )
        else:
            error = PlasmaError(
                ErrorCode.INTERNAL_ERROR,
                "site worker failed outside the handler boundary",
                original_exception=failure,
            )
        with contextlib.suppress(Exception):
            await self.handler.interface.safe_shutdown()
        detail = ErrorDetail.from_exception(
            error,
            channel_id=request.channel_id,
            job_id=request.job_id,
            operation=request.operation,
        )
        result = JobResult(
            job_id=request.job_id,
            channel_id=request.channel_id,
            operation=request.operation,
            state=JobState.FAILED,
            created_at=runtime.created_at,
            started_at=runtime.started_at,
            finished_at=iso_now(),
            elapsed_ms=0,
            attempts=0,
            firmware_name=request.metadata.get("firmware_name"),
            firmware_size=len(request.firmware),
            firmware_sha256=request.firmware_sha256 if request.firmware else None,
            error=detail,
        )
        runtime.state = JobState.FAILED
        runtime.result = result
        with contextlib.suppress(Exception):
            self.output.write_state(request.job_id, self._state_payload(runtime, detail))
            self.output.write_result(result)
        if not runtime.future.done():
            runtime.future.set_result(result)

    def _state_payload(self, runtime: JobRuntime, error: ErrorDetail | None = None) -> dict[str, Any]:
        request = runtime.request
        return {
            "job_id": request.job_id,
            "site_id": request.site_id,
            # Retained in persisted job state while Plasma protocol v3.1 uses channel_id.
            "channel_id": request.channel_id,
            "operation": request.operation.value,
            "state": runtime.state.value,
            "created_at": runtime.created_at,
            "started_at": runtime.started_at,
            "updated_at": runtime.updated_at,
            "client_id": request.client_id,
            "target": request.target,
            "firmware_size": len(request.firmware),
            "firmware_sha256": request.firmware_sha256 if request.firmware else None,
            "stage": runtime.stage,
            "stage_state": runtime.stage_state,
            "stage_progress_percent": runtime.stage_progress_percent,
            "progress_percent": runtime.progress_percent,
            "bytes_done": runtime.bytes_done,
            "bytes_total": runtime.bytes_total,
            "attempt": runtime.attempt,
            "cancel_requested": runtime.cancel_requested,
            "error": error.to_dict() if error else None,
        }

    async def _process(self, runtime: JobRuntime) -> None:
        request = runtime.request
        logger = JobEventLogger(self.log_root, request.channel_id, request.job_id)
        if runtime.cancel_requested:
            await self._finish_cancelled(runtime, logger, started=False)
            return

        async with self._concurrency_slot(runtime) as acquired:
            if not acquired:
                await self._finish_cancelled(runtime, logger, started=False)
                return
            if runtime.cancel_requested:
                await self._finish_cancelled(runtime, logger, started=False)
                return
            runtime.state = JobState.RUNNING
            runtime.started_at = iso_now()
            runtime.updated_at = runtime.started_at
            self.state = SiteState.RUNNING
            self.output.write_state(request.job_id, self._state_payload(runtime))
            logger.event(
                "job_started",
                operation=request.operation.value,
                target=request.target,
                client_id=request.client_id,
                firmware_size=len(request.firmware),
                firmware_sha256=request.firmware_sha256 if request.firmware else None,
            )
            started_monotonic = time.monotonic()
            attempts = 0
            output = ExecutionOutput()
            final_error: PlasmaError | None = None
            cancelled = False

            async def stage_callback(name: str, event: str, fields: dict[str, Any]) -> None:
                level = "ERROR" if event == "failed" else "INFO"
                runtime.stage = name
                runtime.stage_state = event
                runtime.stage_progress_percent = float(
                    fields.get("stage_progress_percent", runtime.stage_progress_percent)
                )
                runtime.progress_percent = float(
                    fields.get("progress_percent", runtime.progress_percent)
                )
                if "bytes_done" in fields:
                    runtime.bytes_done = int(fields["bytes_done"])
                elif event == "started":
                    runtime.bytes_done = None
                if "bytes_total" in fields:
                    runtime.bytes_total = int(fields["bytes_total"])
                elif event == "started":
                    runtime.bytes_total = None
                runtime.updated_at = iso_now()
                self.output.write_state(request.job_id, self._state_payload(runtime))
                logger.event(f"stage_{event}", level=level, stage=name, **fields)

            while attempts <= request.max_retries:
                attempts += 1
                runtime.attempt = attempts
                runtime.updated_at = iso_now()
                logger.event("attempt_started", attempt=attempts)
                runtime.active_task = asyncio.create_task(
                    self.handler.execute(request, stage_callback),
                    name=f"{request.job_id}-attempt-{attempts}",
                )
                try:
                    output = await asyncio.wait_for(runtime.active_task, timeout=request.timeout_s)
                    final_error = None
                    break
                except TimeoutError as exc:
                    final_error = PlasmaError(
                        ErrorCode.OPERATION_TIMEOUT,
                        f"operation exceeded {request.timeout_s:.3f} seconds",
                        recoverable=True,
                        original_exception=exc,
                    )
                except asyncio.CancelledError:
                    cancelled = True
                    final_error = PlasmaError(
                        ErrorCode.OPERATION_CANCELLED,
                        "job was cancelled",
                        original_exception="asyncio.CancelledError",
                    )
                except PlasmaError as exc:
                    final_error = exc
                except Exception as exc:
                    final_error = PlasmaError(
                        ErrorCode.INTERNAL_ERROR,
                        "unexpected handler exception",
                        original_exception=exc,
                    )
                finally:
                    runtime.active_task = None

                if cancelled:
                    break
                if final_error and final_error.recoverable and attempts <= request.max_retries:
                    logger.event(
                        "job_retry",
                        level="WARNING",
                        attempt=attempts,
                        error_code=final_error.code.value,
                        message=final_error.message,
                        backoff_s=request.retry_backoff_s,
                    )
                    await self.handler.interface.safe_shutdown()
                    if request.retry_backoff_s > 0:
                        try:
                            await asyncio.wait_for(
                                runtime.cancel_event.wait(),
                                timeout=request.retry_backoff_s,
                            )
                        except TimeoutError:
                            pass
                    if runtime.cancel_requested:
                        cancelled = True
                        final_error = PlasmaError(
                            ErrorCode.OPERATION_CANCELLED,
                            "job was cancelled during retry backoff",
                        )
                        break
                    continue
                break

            elapsed_ms = round((time.monotonic() - started_monotonic) * 1000)
            shutdown_error: PlasmaError | None = None
            try:
                await self.handler.interface.safe_shutdown()
            except Exception as exc:
                logger.event("safe_shutdown_failed", level="ERROR", error=str(exc))
                shutdown_error = (
                    exc
                    if isinstance(exc, PlasmaError)
                    else PlasmaError(
                        ErrorCode.INTERFACE_FAILURE,
                        "interface safe shutdown failed",
                        original_exception=exc,
                        context={"phase": "safe_shutdown"},
                    )
                )

            if shutdown_error is not None:
                if final_error is not None:
                    shutdown_error.context.setdefault("prior_error_code", final_error.code.value)
                    shutdown_error.context.setdefault("prior_error_message", final_error.message)
                final_error = shutdown_error

            if shutdown_error is not None:
                state = JobState.FAILED
                runtime.stage_state = "failed"
            elif cancelled:
                state = JobState.CANCELLED
                runtime.stage_state = "cancelled"
            elif final_error and final_error.code is ErrorCode.OPERATION_TIMEOUT:
                state = JobState.TIMEOUT
                runtime.stage_state = "timeout"
            elif final_error:
                state = JobState.FAILED
                runtime.stage_state = "failed"
            else:
                state = JobState.SUCCESS
                runtime.stage_state = "completed"
                runtime.stage_progress_percent = 100.0
                runtime.progress_percent = 100.0

            error_detail = (
                ErrorDetail.from_exception(
                    final_error,
                    channel_id=request.channel_id,
                    job_id=request.job_id,
                    operation=request.operation,
                    retry_count=max(0, attempts - 1),
                )
                if final_error
                else None
            )

            result = JobResult(
                job_id=request.job_id,
                channel_id=request.channel_id,
                operation=request.operation,
                state=state,
                created_at=runtime.created_at,
                started_at=runtime.started_at,
                finished_at=iso_now(),
                elapsed_ms=elapsed_ms,
                attempts=attempts,
                firmware_name=request.metadata.get("firmware_name"),
                firmware_size=len(request.firmware),
                firmware_sha256=request.firmware_sha256 if request.firmware else None,
                error=error_detail,
                details=output.details,
            )

            if state is JobState.SUCCESS and output.read_sections:
                try:
                    paths = self.output.write_read_sections(
                        request.job_id,
                        request.channel_id,
                        output.read_sections,
                    )
                    result.output_files = [str(path) for path in paths]
                except PlasmaError as exc:
                    result.state = JobState.FAILED
                    result.error = ErrorDetail.from_exception(
                        exc,
                        channel_id=request.channel_id,
                        job_id=request.job_id,
                        operation=request.operation,
                    )

            runtime.state = result.state
            runtime.result = result
            runtime.updated_at = iso_now()
            self.output.write_state(request.job_id, self._state_payload(runtime, result.error))
            self.output.write_result(result)
            event, level = _terminal_log_event(result.state)
            logger.event(
                event,
                level=level,
                state=result.state.value,
                elapsed_ms=result.elapsed_ms,
                attempts=result.attempts,
                error_code=result.error.error_code if result.error else None,
                output_files=result.output_files,
            )
            if not runtime.future.done():
                runtime.future.set_result(result)

    async def _finish_cancelled(
        self,
        runtime: JobRuntime,
        logger: JobEventLogger,
        *,
        started: bool,
    ) -> None:
        request = runtime.request
        error = PlasmaError(ErrorCode.OPERATION_CANCELLED, "job was cancelled before execution")
        detail = ErrorDetail.from_exception(
            error,
            channel_id=request.channel_id,
            job_id=request.job_id,
            operation=request.operation,
        )
        result = JobResult(
            job_id=request.job_id,
            channel_id=request.channel_id,
            operation=request.operation,
            state=JobState.CANCELLED,
            created_at=runtime.created_at,
            started_at=runtime.started_at if started else None,
            finished_at=iso_now(),
            elapsed_ms=0,
            attempts=0,
            error=detail,
        )
        runtime.state = JobState.CANCELLED
        runtime.result = result
        runtime.stage_state = "cancelled"
        runtime.updated_at = iso_now()
        self.output.write_state(request.job_id, self._state_payload(runtime, detail))
        self.output.write_result(result)
        logger.event("job_cancelled", level="WARNING", state=result.state.value)
        if not runtime.future.done():
            runtime.future.set_result(result)


# Compatibility alias for code importing the pre-domain-rename worker type.
ChannelWorker = SiteWorker
