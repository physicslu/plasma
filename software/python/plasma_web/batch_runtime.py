from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from plasma_core.assets import ProgrammingAsset
from plasma_core.batch import (
    BatchExecutionPolicy,
    BatchSiteState,
    BatchState,
    BatchTarget,
    normalize_batch_operations,
)
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest, iso_now

from .engineering_targets import EngineeringPPUProvider
from .gateway_settings import GatewayCommunicationPolicy, GatewaySettingsController


BATCH_POLL_INTERVAL_S = 0.05
BATCH_SITE_FAILURE_THRESHOLD_ERROR = "BATCH_SITE_FAILURE_THRESHOLD_EXCEEDED"
BATCH_INFRASTRUCTURE_ERROR = "BATCH_INFRASTRUCTURE_ERROR"


@dataclass(frozen=True, slots=True)
class BatchTargetDeviceSnapshot:
    vendor: str
    family: str
    identifier: str
    identifier_kind: str
    icpn: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "family": self.family,
            "identifier": self.identifier,
            "identifier_kind": self.identifier_kind,
            "icpn": self.icpn,
        }


@dataclass(frozen=True, slots=True)
class BatchAssetSnapshot:
    name: str
    asset_type: str
    asset_format: str
    size_bytes: int
    sha256: str

    @classmethod
    def from_asset(cls, asset: ProgrammingAsset) -> "BatchAssetSnapshot":
        return cls(
            name=asset.name,
            asset_type=asset.asset_type.value,
            asset_format=asset.asset_format.value,
            size_bytes=asset.size,
            sha256=asset.sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "asset_type": self.asset_type,
            "asset_format": self.asset_format,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(slots=True)
class OperationAccumulator:
    logical_executions: int = 0
    attempts: int = 0
    retries: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    error_executions: int = 0
    cancelled_executions: int = 0
    failed_attempts: int = 0
    error_attempts: int = 0
    cancelled_attempts: int = 0

    def begin(self) -> None:
        self.logical_executions += 1

    def record_submission_error(self) -> None:
        self.error_executions += 1
        self.error_attempts += 1
        self.attempts += 1

    def record_job(self, job: dict[str, Any]) -> None:
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        history = result.get("attempt_history") if isinstance(result.get("attempt_history"), list) else []
        attempts = result.get("attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
            attempts = len(history)
        if attempts <= 0:
            attempts = max(1, len(history))
        self.attempts += attempts
        self.retries += max(0, attempts - 1)

        for item in history:
            if not isinstance(item, dict):
                continue
            state = str(item.get("state", ""))
            if state in {"failed", "timeout"}:
                self.failed_attempts += 1
            elif state in {"error", "aborted"}:
                self.error_attempts += 1
            elif state == "cancelled":
                self.cancelled_attempts += 1

        state = str(job.get("state", ""))
        if state == "success":
            self.successful_executions += 1
        elif state in {"failed", "timeout"}:
            self.failed_executions += 1
        elif state in {"error", "aborted"}:
            self.error_executions += 1
        elif state == "cancelled":
            self.cancelled_executions += 1

    def to_dict(self) -> dict[str, int | float]:
        attempt_failures = self.failed_attempts + self.error_attempts
        return {
            "logical_executions": self.logical_executions,
            "attempts": self.attempts,
            "retries": self.retries,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "error_executions": self.error_executions,
            "cancelled_executions": self.cancelled_executions,
            "failed_attempts": self.failed_attempts,
            "error_attempts": self.error_attempts,
            "cancelled_attempts": self.cancelled_attempts,
            "attempt_failure_rate": round(attempt_failures / self.attempts, 6) if self.attempts else 0.0,
        }


@dataclass(slots=True)
class BatchSiteRuntime:
    target: BatchTarget
    state: BatchSiteState = BatchSiteState.READY
    current_round: int = 0
    completed_rounds: int = 0
    current_operation: Operation | None = None
    current_job_id: str | None = None
    progress_percent: float = 0.0
    total_attempts: int = 0
    retry_count: int = 0
    final_failures: int = 0
    faulted_round: int | None = None
    faulted_operation: Operation | None = None
    last_failure_source: str | None = None
    communication_state: str = "connected"
    communication_attempt: int = 0
    error: dict[str, Any] | None = None
    operation_stats: dict[Operation, OperationAccumulator] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.target.to_dict(),
            "key": self.target.key,
            "state": self.state.value,
            "current_round": self.current_round,
            "completed_rounds": self.completed_rounds,
            "current_operation": self.current_operation.value if self.current_operation else None,
            "current_job_id": self.current_job_id,
            "progress_percent": round(self.progress_percent, 1),
            "total_attempts": self.total_attempts,
            "retry_count": self.retry_count,
            "final_failures": self.final_failures,
            "faulted_round": self.faulted_round,
            "faulted_operation": self.faulted_operation.value if self.faulted_operation else None,
            "last_failure_source": self.last_failure_source,
            "communication_state": self.communication_state,
            "communication_attempt": self.communication_attempt,
            "error": dict(self.error) if self.error else None,
            "operation_statistics": {
                operation.value: statistics.to_dict()
                for operation, statistics in self.operation_stats.items()
            },
        }


@dataclass(slots=True)
class BatchRecord:
    batch_id: str
    operations: tuple[Operation, ...]
    policy: BatchExecutionPolicy
    gateway_policy: GatewayCommunicationPolicy
    targets: tuple[BatchTarget, ...]
    sites: dict[str, BatchSiteRuntime]
    session_id: str | None
    target_device: BatchTargetDeviceSnapshot | None
    asset: BatchAssetSnapshot | None
    read_offset: int
    read_length: int
    state: BatchState = BatchState.QUEUED
    created_at: str = field(default_factory=iso_now)
    started_at: str | None = None
    finished_at: str | None = None
    stop_reason: str | None = None
    error: dict[str, Any] | None = None
    cancel_requested: bool = False
    cancelled_ppus: set[str] = field(default_factory=set)
    failed_ppus: set[str] = field(default_factory=set)
    active_jobs: dict[str, tuple[BatchTarget, str]] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    loop: asyncio.AbstractEventLoop | None = field(default=None, repr=False)
    thread: threading.Thread | None = field(default=None, repr=False)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            site_payloads = [self.sites[target.key].to_dict() for target in self.targets]
            counts = {
                state.value: sum(1 for site in self.sites.values() if site.state is state)
                for state in BatchSiteState
            }
            aggregate: dict[str, OperationAccumulator] = {
                operation.value: OperationAccumulator() for operation in self.operations
            }
            for site in self.sites.values():
                for operation, source in site.operation_stats.items():
                    target = aggregate[operation.value]
                    for field_name in (
                        "logical_executions",
                        "attempts",
                        "retries",
                        "successful_executions",
                        "failed_executions",
                        "error_executions",
                        "cancelled_executions",
                        "failed_attempts",
                        "error_attempts",
                        "cancelled_attempts",
                    ):
                        setattr(target, field_name, getattr(target, field_name) + getattr(source, field_name))
            return {
                "batch_id": self.batch_id,
                "state": self.state.value,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "operations": [operation.value for operation in self.operations],
                "execution_policy": self.policy.to_dict(),
                "gateway_settings": self.gateway_policy.to_dict(),
                "target_device": self.target_device.to_dict() if self.target_device else None,
                "asset": self.asset.to_dict() if self.asset else None,
                "read": {"offset": self.read_offset, "length": self.read_length},
                "cancel_requested": self.cancel_requested,
                "stop_reason": self.stop_reason,
                "error": dict(self.error) if self.error else None,
                "faulted_site_count": counts[BatchSiteState.FAULTED.value],
                "site_counts": counts,
                "operation_statistics": {
                    operation: statistics.to_dict()
                    for operation, statistics in aggregate.items()
                },
                "sites": site_payloads,
            }


class BatchRuntimeManager:
    """Server-side Batch orchestration across Facility/PPU/Site targets.

    The browser submits one immutable Batch snapshot. Site pipelines run
    independently: there is no round barrier across Sites or PPUs. Each Site
    completes E/P/V/R for one round and immediately advances to its next round.
    """

    def __init__(
        self,
        provider: EngineeringPPUProvider,
        *,
        poll_interval_s: float = BATCH_POLL_INTERVAL_S,
        gateway_settings: GatewaySettingsController | None = None,
        retry_backoff_s: float = 1.0,
    ) -> None:
        self.provider = provider
        self.poll_interval_s = poll_interval_s
        self.gateway_settings = gateway_settings or GatewaySettingsController()
        self.retry_backoff_s = retry_backoff_s
        self._batches: dict[str, BatchRecord] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _new_batch_id() -> str:
        return f"batch-{uuid.uuid4().hex}"

    def create_batch(
        self,
        *,
        targets: tuple[BatchTarget, ...],
        operations: list[str] | tuple[str, ...],
        policy: BatchExecutionPolicy,
        session_id: str | None = None,
        target_device: BatchTargetDeviceSnapshot | None = None,
        asset: ProgrammingAsset | None = None,
        read_offset: int = 0,
        read_length: int = 256,
    ) -> dict[str, Any]:
        if not targets:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch requires at least one Site")
        if len({target.key for target in targets}) != len(targets):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch targets must be unique")
        policy.validate_target_count(len(targets))
        ordered_operations = normalize_batch_operations(operations)
        requires_asset = any(operation in {Operation.PROGRAM, Operation.VERIFY} for operation in ordered_operations)
        if requires_asset and asset is None:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Program/Verify Batch requires one Programming Asset")
        if asset is not None and not requires_asset:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "Programming Asset is only valid when Batch includes Program or Verify",
            )
        if requires_asset and (not isinstance(session_id, str) or not session_id):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Program/Verify Batch requires an Engineering session_id")
        if (
            isinstance(read_offset, bool)
            or not isinstance(read_offset, int)
            or read_offset < 0
            or isinstance(read_length, bool)
            or not isinstance(read_length, int)
            or read_length <= 0
        ):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch Read offset/length is invalid")

        if asset is not None:
            assert session_id is not None
            for facility_id, ppu_id in sorted({(target.facility_id, target.ppu_id) for target in targets}):
                self.provider.cache_asset(
                    session_id,
                    facility_id,
                    ppu_id,
                    asset.name,
                    asset.asset_type.value,
                    asset.asset_format.value,
                    asset.sha256,
                    asset.data,
                )

        batch_id = self._new_batch_id()
        site_runtimes = {
            target.key: BatchSiteRuntime(
                target=target,
                operation_stats={operation: OperationAccumulator() for operation in ordered_operations},
            )
            for target in targets
        }
        batch = BatchRecord(
            batch_id=batch_id,
            operations=ordered_operations,
            policy=policy,
            gateway_policy=self.gateway_settings.snapshot(),
            targets=targets,
            sites=site_runtimes,
            session_id=session_id,
            target_device=target_device,
            asset=BatchAssetSnapshot.from_asset(asset) if asset else None,
            read_offset=read_offset,
            read_length=read_length,
        )
        with self._lock:
            self._batches[batch_id] = batch
        thread = threading.Thread(
            target=self._thread_main,
            args=(batch,),
            name=f"plasma-{batch_id}",
            daemon=True,
        )
        batch.thread = thread
        thread.start()
        return batch.snapshot()

    def get(self, batch_id: str) -> dict[str, Any]:
        return self._get_record(batch_id).snapshot()

    def _get_record(self, batch_id: str) -> BatchRecord:
        if not isinstance(batch_id, str) or not batch_id.startswith("batch-"):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid Batch ID")
        with self._lock:
            batch = self._batches.get(batch_id)
        if batch is None:
            raise PlasmaError(ErrorCode.JOB_NOT_FOUND, f"Batch not found: {batch_id}")
        return batch

    def cancel(self, batch_id: str) -> dict[str, Any]:
        batch = self._get_record(batch_id)
        with batch.lock:
            if batch.state.terminal:
                return batch.snapshot()
            batch.cancel_requested = True
            batch.stop_reason = "operator_cancel"
            batch.state = BatchState.STOPPING
            loop = batch.loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._cancel_active_jobs(batch), loop)
        return batch.snapshot()

    def cancel_ppu(self, batch_id: str, facility_id: str, ppu_id: str) -> dict[str, Any]:
        batch = self._get_record(batch_id)
        ppu_key = f"{facility_id}::{ppu_id}"
        if ppu_key not in {target.ppu_key for target in batch.targets}:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PPU is not part of this Batch")
        with batch.lock:
            batch.cancelled_ppus.add(ppu_key)
            loop = batch.loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._cancel_active_jobs(batch, ppu_key=ppu_key), loop)
        return batch.snapshot()

    def close(self, timeout_s: float = 5.0) -> None:
        with self._lock:
            batches = list(self._batches.values())
        for batch in batches:
            if not batch.state.terminal:
                self.cancel(batch.batch_id)
        deadline = time.monotonic() + timeout_s
        for batch in batches:
            thread = batch.thread
            if thread and thread.is_alive():
                thread.join(max(0.0, deadline - time.monotonic()))

    def _thread_main(self, batch: BatchRecord) -> None:
        loop = asyncio.new_event_loop()
        with batch.lock:
            batch.loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._execute(batch))
        except BaseException as exc:
            with batch.lock:
                batch.state = BatchState.ERROR
                batch.stop_reason = batch.stop_reason or "runtime_exception"
                batch.error = {
                    "error_code": BATCH_INFRASTRUCTURE_ERROR,
                    "message": f"Batch runtime failed: {type(exc).__name__}: {exc}",
                }
                batch.finished_at = iso_now()
        finally:
            with batch.lock:
                batch.loop = None
            loop.close()

    async def _execute(self, batch: BatchRecord) -> None:
        with batch.lock:
            if batch.cancel_requested:
                batch.state = BatchState.CANCELLED
                batch.finished_at = iso_now()
                return
            batch.state = BatchState.RUNNING
            batch.started_at = iso_now()

        await asyncio.gather(*(self._run_site(batch, batch.sites[target.key]) for target in batch.targets))

        with batch.lock:
            if batch.stop_reason == "operator_cancel":
                batch.state = BatchState.CANCELLED
            elif batch.stop_reason in {"failed_site_threshold", "runtime_exception"}:
                batch.state = BatchState.ERROR
            else:
                states = [site.state for site in batch.sites.values()]
                if states and all(state is BatchSiteState.SUCCESS for state in states):
                    batch.state = BatchState.SUCCESS
                elif states and all(state is BatchSiteState.CANCELLED for state in states):
                    batch.state = BatchState.CANCELLED
                elif any(state is BatchSiteState.ERROR for state in states):
                    batch.state = (
                        BatchState.PARTIAL
                        if any(state is BatchSiteState.SUCCESS for state in states)
                        else BatchState.ERROR
                    )
                else:
                    batch.state = BatchState.PARTIAL
            batch.finished_at = iso_now()

    def _stop_disposition(self, batch: BatchRecord, site: BatchSiteRuntime) -> BatchSiteState | None:
        with batch.lock:
            if site.target.ppu_key in batch.cancelled_ppus:
                return BatchSiteState.CANCELLED
            if site.target.ppu_key in batch.failed_ppus:
                return BatchSiteState.STOPPED
            if batch.stop_reason == "operator_cancel" or batch.cancel_requested:
                return BatchSiteState.CANCELLED
            if batch.stop_reason in {"failed_site_threshold", "runtime_exception"}:
                return BatchSiteState.STOPPED
        return None

    async def _run_site(self, batch: BatchRecord, site: BatchSiteRuntime) -> None:
        for round_index in range(1, batch.policy.repeat_count + 1):
            disposition = self._stop_disposition(batch, site)
            if disposition is not None:
                with batch.lock:
                    site.state = disposition
                    site.current_operation = None
                    site.current_job_id = None
                return
            with batch.lock:
                site.state = BatchSiteState.RUNNING
                site.current_round = round_index
                site.progress_percent = 0.0

            for operation in batch.operations:
                disposition = self._stop_disposition(batch, site)
                if disposition is not None:
                    with batch.lock:
                        site.state = disposition
                        site.current_operation = None
                        site.current_job_id = None
                    return
                with batch.lock:
                    site.current_operation = operation
                    site.progress_percent = 0.0
                    site.operation_stats[operation].begin()

                try:
                    job = await self._execute_operation(batch, site, operation, round_index)
                except Exception as exc:
                    with batch.lock:
                        site.operation_stats[operation].record_submission_error()
                        site.total_attempts += 1
                        site.state = BatchSiteState.ERROR
                        site.last_failure_source = "infrastructure"
                        site.communication_state = "failed"
                        site.error = {
                            "error_code": BATCH_INFRASTRUCTURE_ERROR,
                            "message": f"{type(exc).__name__}: {exc}",
                        }
                    await self._trip_infrastructure_error(batch, site, exc)
                    return

                with batch.lock:
                    statistics = site.operation_stats[operation]
                    statistics.record_job(job)
                    result = job.get("result") if isinstance(job.get("result"), dict) else {}
                    attempts = result.get("attempts")
                    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts <= 0:
                        attempts = max(1, len(result.get("attempt_history", [])))
                    site.total_attempts += attempts
                    site.retry_count += max(0, attempts - 1)
                    site.progress_percent = float(job.get("progress_percent", 100.0) or 0.0)
                    site.current_job_id = None
                    state = str(job.get("state", ""))
                    error = result.get("error") if isinstance(result.get("error"), dict) else None
                    site.last_failure_source = str(error.get("failure_source")) if error and error.get("failure_source") else None
                    site.error = dict(error) if error else None

                if state == "success":
                    continue
                if state == "cancelled":
                    disposition = self._stop_disposition(batch, site) or BatchSiteState.CANCELLED
                    with batch.lock:
                        site.state = disposition
                    return
                if state in {"error", "aborted"}:
                    with batch.lock:
                        site.state = BatchSiteState.ERROR
                    await self._trip_infrastructure_error(batch, site, RuntimeError(site.error or state))
                    return
                if state in {"failed", "timeout"}:
                    with batch.lock:
                        site.state = BatchSiteState.FAULTED
                        site.final_failures += 1
                        site.faulted_round = round_index
                        site.faulted_operation = operation
                    await self._register_faulted_site(batch, site)
                    return

                with batch.lock:
                    site.state = BatchSiteState.ERROR
                    site.error = {
                        "error_code": BATCH_INFRASTRUCTURE_ERROR,
                        "message": f"unexpected terminal Job state: {state!r}",
                    }
                await self._trip_infrastructure_error(batch, site, RuntimeError(f"unexpected Job state {state!r}"))
                return

            with batch.lock:
                site.completed_rounds = round_index
                site.current_operation = None
                site.progress_percent = 100.0

        with batch.lock:
            site.state = BatchSiteState.SUCCESS
            site.current_job_id = None
            site.current_operation = None
            site.progress_percent = 100.0

    async def _execute_operation(
        self,
        batch: BatchRecord,
        site: BatchSiteRuntime,
        operation: Operation,
        round_index: int,
    ) -> dict[str, Any]:
        map_data: dict[str, Any] = {}
        if operation is Operation.READ:
            map_data = {
                "sections": [
                    {
                        "name": "flash",
                        "address": batch.read_offset,
                        "length": batch.read_length,
                    }
                ]
            }
        metadata: dict[str, Any] = {
            "batch_id": batch.batch_id,
            "batch_round": round_index,
        }
        if batch.target_device is not None:
            metadata["target_device"] = batch.target_device.to_dict()
        request = JobRequest(
            site_id=site.target.site_id,
            operation=operation,
            map_data=map_data,
            timeout_s=self.provider.job_timeout_s(site.target.facility_id, site.target.ppu_id),
            max_retries=batch.policy.site_retry_limit,
            retry_backoff_s=0.05,
            client_id="plasma-batch-runtime",
            metadata=metadata,
        )
        asset_sha256 = batch.asset.sha256 if batch.asset and operation in {Operation.PROGRAM, Operation.VERIFY} else None
        session_id = batch.session_id if asset_sha256 is not None else None
        accepted = await self._provider_request(
            batch,
            site,
            "start",
            lambda: self.provider.start_job(
                site.target.facility_id,
                site.target.ppu_id,
                request,
                session_id=session_id,
                asset_sha256=asset_sha256,
            ),
            retryable=False,
        )
        job = accepted.get("job") if isinstance(accepted, dict) else None
        if not isinstance(job, dict) or not isinstance(job.get("job_id"), str):
            raise RuntimeError("PPU provider did not return an accepted Job identity")
        job_id = str(job["job_id"])
        with batch.lock:
            site.current_job_id = job_id
            batch.active_jobs[site.target.key] = (site.target, job_id)

        terminal_states = {"success", "failed", "error", "cancelled", "timeout", "aborted"}
        observed_terminal = False
        try:
            while True:
                response = await self._provider_request(
                    batch,
                    site,
                    "status",
                    lambda: self.provider.status(
                        site.target.facility_id,
                        site.target.ppu_id,
                        site_id=site.target.site_id,
                        job_id=job_id,
                    ),
                )
                current = response.get("job") if isinstance(response, dict) else None
                if not isinstance(current, dict):
                    raise RuntimeError("PPU provider Job status is missing")
                with batch.lock:
                    site.progress_percent = float(current.get("progress_percent", site.progress_percent) or 0.0)
                if str(current.get("state", "")) in terminal_states:
                    observed_terminal = True
                    return current
                await asyncio.sleep(self.poll_interval_s)
        finally:
            if observed_terminal:
                with batch.lock:
                    batch.active_jobs.pop(site.target.key, None)

    async def _provider_request(
        self,
        batch: BatchRecord,
        site: BatchSiteRuntime,
        action: str,
        operation: Callable[[], Awaitable[dict[str, Any]]],
        *,
        retryable: bool = True,
    ) -> dict[str, Any]:
        retries = batch.gateway_policy.ppu_retry_count if retryable else 0
        for attempt in range(retries + 1):
            try:
                response = await asyncio.wait_for(
                    operation(),
                    timeout=batch.gateway_policy.request_timeout_s,
                )
            except Exception as exc:
                transient = isinstance(exc, (TimeoutError, OSError, ConnectionError)) or (
                    isinstance(exc, PlasmaError)
                    and exc.code in {ErrorCode.CONNECTION_TIMEOUT, ErrorCode.CONNECTION_FAILED}
                )
                if not transient or attempt >= retries:
                    raise
                with batch.lock:
                    site.communication_state = "reconnecting"
                    site.communication_attempt = attempt + 1
                    site.error = {
                        "error_code": BATCH_INFRASTRUCTURE_ERROR,
                        "message": (
                            f"PPU {action} retry {attempt + 1}/{retries}: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    }
                await asyncio.sleep(self.retry_backoff_s * min(2 ** attempt, 4))
                continue
            with batch.lock:
                if site.state is not BatchSiteState.ERROR:
                    site.communication_state = "connected"
                    site.communication_attempt = 0
                    site.error = None
            return response
        raise RuntimeError("PPU provider request retry loop terminated unexpectedly")

    async def _register_faulted_site(self, batch: BatchRecord, site: BatchSiteRuntime) -> None:
        with batch.lock:
            faulted_count = sum(1 for candidate in batch.sites.values() if candidate.state is BatchSiteState.FAULTED)
            threshold = batch.policy.failed_site_stop_threshold
            should_trip = (
                threshold is not None
                and faulted_count >= threshold
                and batch.stop_reason is None
            )
            if should_trip:
                batch.stop_reason = "failed_site_threshold"
                batch.state = BatchState.STOPPING
                batch.error = {
                    "error_code": BATCH_SITE_FAILURE_THRESHOLD_ERROR,
                    "message": (
                        f"FAULTED Site threshold reached: {faulted_count} >= {threshold}"
                    ),
                    "faulted_site_count": faulted_count,
                    "threshold": threshold,
                    "trigger_site": site.target.to_dict(),
                }
        if should_trip:
            await self._cancel_active_jobs(batch)

    async def _trip_infrastructure_error(
        self,
        batch: BatchRecord,
        site: BatchSiteRuntime,
        failure: Exception,
    ) -> None:
        with batch.lock:
            ppu_key = site.target.ppu_key
            if ppu_key not in batch.failed_ppus:
                batch.failed_ppus.add(ppu_key)
                batch.stop_reason = batch.stop_reason or "infrastructure_error"
                batch.error = {
                    "error_code": BATCH_INFRASTRUCTURE_ERROR,
                    "message": str(failure),
                    "trigger_site": site.target.to_dict(),
                    "failed_ppus": sorted(batch.failed_ppus),
                }
                should_cancel = True
            else:
                should_cancel = False
        if should_cancel:
            await self._cancel_active_jobs(batch, ppu_key=ppu_key)

    async def _cancel_active_jobs(self, batch: BatchRecord, *, ppu_key: str | None = None) -> None:
        with batch.lock:
            active = [
                (target, job_id)
                for target, job_id in batch.active_jobs.values()
                if ppu_key is None or target.ppu_key == ppu_key
            ]
        if not active:
            return
        async def cancel_one(target: BatchTarget, job_id: str) -> None:
            site = batch.sites[target.key]
            try:
                await self._provider_request(
                    batch,
                    site,
                    "cancel",
                    lambda: self.provider.cancel_job(target.facility_id, target.ppu_id, job_id),
                )
            finally:
                with batch.lock:
                    batch.active_jobs.pop(target.key, None)

        await asyncio.gather(*(cancel_one(target, job_id) for target, job_id in active), return_exceptions=True)
