from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from plasma_core.assets import ProgrammingAsset
from plasma_core.batch import BatchExecutionPolicy, BatchSiteState, BatchState, BatchTarget, normalize_batch_operations
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest, iso_now

from .batch_runtime import (
    BATCH_INFRASTRUCTURE_ERROR,
    BatchAssetSnapshot,
    BatchRecord,
    BatchRuntimeManager,
    BatchSiteRuntime,
    BatchTargetDeviceSnapshot,
    OperationAccumulator,
)
from .batch_state_store import BatchStateStore, StoredBatch, StoredBatchJob
from .engineering_targets import EngineeringPPUProvider
from .gateway_settings import GatewayCommunicationPolicy, GatewaySettingsController


BATCH_RECOVERY_ERROR = "BATCH_RECOVERY_ERROR"
BATCH_RECOVERY_JOB_UNKNOWN = "BATCH_RECOVERY_JOB_UNKNOWN"
BATCH_CHECKPOINT_INTERVAL_S = 0.1
_TERMINAL_JOB_STATES = {"success", "failed", "error", "cancelled", "timeout", "aborted"}


class _BatchRuntimeSuspended(BaseException):
    """Internal control-flow signal used to stop Gateway orchestration without cancelling PPU work."""


class _PersistingProvider:
    def __init__(self, provider: EngineeringPPUProvider, manager: "PersistentBatchRuntimeManager") -> None:
        self._provider = provider
        self._manager = manager

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    async def start_job(
        self,
        facility_id: str,
        ppu_id: str,
        request: JobRequest,
        *,
        session_id: str | None = None,
        asset_sha256: str | None = None,
    ) -> dict[str, Any]:
        batch_id = request.metadata.get("batch_id")
        tracked = isinstance(batch_id, str) and batch_id.startswith("batch-")
        if tracked:
            self._manager._record_job_intent(batch_id, facility_id, ppu_id, request)
        try:
            response = await self._provider.start_job(
                facility_id,
                ppu_id,
                request,
                session_id=session_id,
                asset_sha256=asset_sha256,
            )
        except Exception as exc:
            if tracked:
                self._manager._record_job_submission_error(batch_id, request.job_id, exc)
            raise
        if tracked:
            self._manager._record_job_accepted(batch_id, request.job_id, response)
        return response

    async def status(
        self,
        facility_id: str,
        ppu_id: str,
        *,
        site_id: int | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        response = await self._provider.status(
            facility_id,
            ppu_id,
            site_id=site_id,
            job_id=job_id,
        )
        if job_id is not None:
            self._manager._record_job_observation(job_id, response)
        return response

    async def cancel_job(self, facility_id: str, ppu_id: str, job_id: str) -> dict[str, Any]:
        response = await self._provider.cancel_job(facility_id, ppu_id, job_id)
        self._manager._record_job_observation(job_id, response)
        return response


class PersistentBatchRuntimeManager(BatchRuntimeManager):
    """BatchRuntimeManager with crash-safe local state and restart reconciliation.

    The durable boundary records immutable Batch input before orchestration,
    records each Job ID before sending it to a PPU, and checkpoints runtime
    state while execution progresses. Recovery never converts uncertainty into
    manufacturing SUCCESS/FAIL: accepted or ambiguous Job IDs are queried from
    the authoritative PPU before the Batch continues or terminates.
    """

    def __init__(
        self,
        provider: EngineeringPPUProvider,
        *,
        state_path: str | Path,
        terminal_retention_days: int = 30,
        poll_interval_s: float = 0.05,
        gateway_settings: GatewaySettingsController | None = None,
        retry_backoff_s: float = 1.0,
        checkpoint_interval_s: float = BATCH_CHECKPOINT_INTERVAL_S,
    ) -> None:
        self._state_store = BatchStateStore(
            state_path,
            terminal_retention_days=terminal_retention_days,
        )
        self._real_provider = provider
        self._creation_local = threading.local()
        self._job_batches: dict[str, str] = {}
        self._job_map_lock = threading.RLock()
        self._suspending = threading.Event()
        self._checkpoint_stop = threading.Event()
        self._checkpoint_interval_s = checkpoint_interval_s
        proxy = _PersistingProvider(provider, self)
        super().__init__(
            proxy,
            poll_interval_s=poll_interval_s,
            gateway_settings=gateway_settings,
            retry_backoff_s=retry_backoff_s,
        )
        self._restore_nonterminal_batches()
        self._checkpoint_thread = threading.Thread(
            target=self._checkpoint_main,
            name="plasma-batch-checkpoint",
            daemon=True,
        )
        self._checkpoint_thread.start()

    def _new_batch_id(self) -> str:
        pending = getattr(self._creation_local, "batch_id", None)
        if isinstance(pending, str) and pending:
            self._creation_local.batch_id = None
            return pending
        return super()._new_batch_id()

    @staticmethod
    def _spec_from_create(
        *,
        targets: tuple[BatchTarget, ...],
        operations: list[str] | tuple[str, ...],
        policy: BatchExecutionPolicy,
        gateway_policy: GatewayCommunicationPolicy,
        session_id: str | None,
        target_device: BatchTargetDeviceSnapshot | None,
        asset: ProgrammingAsset | None,
        read_offset: int,
        read_length: int,
    ) -> dict[str, Any]:
        return {
            "targets": [target.to_dict() for target in targets],
            "operations": [operation.value for operation in normalize_batch_operations(operations)],
            "execution_policy": policy.to_dict(),
            "gateway_settings": gateway_policy.to_dict(),
            "session_id": session_id,
            "target_device": target_device.to_dict() if target_device else None,
            "asset": (
                {
                    "name": asset.name,
                    "asset_type": asset.asset_type.value,
                    "asset_format": asset.asset_format.value,
                    "size_bytes": asset.size,
                    "sha256": asset.sha256,
                }
                if asset
                else None
            ),
            "read": {"offset": read_offset, "length": read_length},
        }

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
        batch_id = BatchRuntimeManager._new_batch_id()
        spec = self._spec_from_create(
            targets=targets,
            operations=operations,
            policy=policy,
            gateway_policy=self.gateway_settings.snapshot(),
            session_id=session_id,
            target_device=target_device,
            asset=asset,
            read_offset=read_offset,
            read_length=read_length,
        )
        self._state_store.prepare_batch(
            batch_id,
            spec=spec,
            asset_data=asset.data if asset is not None else None,
        )
        self._creation_local.batch_id = batch_id
        try:
            snapshot = super().create_batch(
                targets=targets,
                operations=operations,
                policy=policy,
                session_id=session_id,
                target_device=target_device,
                asset=asset,
                read_offset=read_offset,
                read_length=read_length,
            )
        except BaseException:
            self._state_store.discard_batch(batch_id)
            raise
        finally:
            self._creation_local.batch_id = None
        self._checkpoint_id(batch_id)
        return snapshot

    def cancel(self, batch_id: str) -> dict[str, Any]:
        snapshot = super().cancel(batch_id)
        self._checkpoint_id(batch_id)
        return snapshot

    def cancel_ppu(self, batch_id: str, facility_id: str, ppu_id: str) -> dict[str, Any]:
        snapshot = super().cancel_ppu(batch_id, facility_id, ppu_id)
        self._checkpoint_id(batch_id)
        return snapshot

    def _checkpoint_payload(self, batch: BatchRecord) -> dict[str, Any]:
        payload = batch.snapshot()
        with batch.lock:
            payload["_recovery"] = {
                "session_id": batch.session_id,
                "cancelled_ppus": sorted(batch.cancelled_ppus),
                "failed_ppus": sorted(batch.failed_ppus),
                "active_jobs": {
                    key: {"target": target.to_dict(), "job_id": job_id}
                    for key, (target, job_id) in batch.active_jobs.items()
                },
            }
        return payload

    def _checkpoint_id(self, batch_id: str) -> None:
        with self._lock:
            batch = self._batches.get(batch_id)
        if batch is not None:
            self._state_store.save_snapshot(batch_id, self._checkpoint_payload(batch))

    def _checkpoint_main(self) -> None:
        while not self._checkpoint_stop.wait(self._checkpoint_interval_s):
            with self._lock:
                batches = tuple(self._batches.values())
            for batch in batches:
                try:
                    self._state_store.save_snapshot(batch.batch_id, self._checkpoint_payload(batch))
                except Exception:
                    # Critical submission writes are synchronous and fail closed.
                    # Periodic checkpoints are best-effort because recovery can
                    # reconcile durable Job identities against the PPU.
                    continue

    def _record_job_intent(
        self,
        batch_id: str,
        facility_id: str,
        ppu_id: str,
        request: JobRequest,
    ) -> None:
        self._checkpoint_id(batch_id)
        site_key = f"{facility_id}::{ppu_id}::SITE{request.site_id}"
        round_index = request.metadata.get("batch_round", 0)
        if isinstance(round_index, bool) or not isinstance(round_index, int) or round_index < 1:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Batch Job is missing a valid batch_round")
        self._state_store.record_job_intent(
            batch_id=batch_id,
            site_key=site_key,
            job_id=request.job_id,
            facility_id=facility_id,
            ppu_id=ppu_id,
            site_id=request.site_id,
            operation=request.operation.value,
            round_index=round_index,
        )
        with self._job_map_lock:
            self._job_batches[request.job_id] = batch_id

    @staticmethod
    def _submission_is_ambiguous(exc: Exception) -> bool:
        if isinstance(exc, (TimeoutError, OSError, ConnectionError)):
            return True
        return isinstance(exc, PlasmaError) and exc.code in {
            ErrorCode.CONNECTION_TIMEOUT,
            ErrorCode.CONNECTION_FAILED,
        }

    def _record_job_submission_error(self, batch_id: str, job_id: str, exc: Exception) -> None:
        if not self._submission_is_ambiguous(exc):
            self._state_store.update_job(batch_id, job_id, phase="rejected")
        self._checkpoint_id(batch_id)

    def _record_job_accepted(self, batch_id: str, job_id: str, response: dict[str, Any]) -> None:
        job = response.get("job") if isinstance(response, dict) else None
        self._state_store.update_job(
            batch_id,
            job_id,
            phase="accepted",
            job=job if isinstance(job, dict) else None,
        )
        self._checkpoint_id(batch_id)

    def _record_job_observation(self, job_id: str, response: dict[str, Any]) -> None:
        with self._job_map_lock:
            batch_id = self._job_batches.get(job_id)
        if batch_id is None:
            return
        job = response.get("job") if isinstance(response, dict) else None
        if not isinstance(job, dict):
            return
        phase = "terminal" if str(job.get("state", "")) in _TERMINAL_JOB_STATES else "accepted"
        self._state_store.update_job(batch_id, job_id, phase=phase, job=job)
        self._checkpoint_id(batch_id)

    def _thread_main(self, batch: BatchRecord) -> None:
        loop = asyncio.new_event_loop()
        with batch.lock:
            batch.loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._execute(batch))
        except _BatchRuntimeSuspended:
            pass
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
            self._checkpoint_id(batch.batch_id)
            loop.close()

    async def _provider_request(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if self._suspending.is_set():
            raise _BatchRuntimeSuspended()
        return await super()._provider_request(*args, **kwargs)

    def close(self, timeout_s: float = 5.0) -> None:
        """Suspend Gateway orchestration without cancelling authoritative PPU Jobs."""
        self._suspending.set()
        self._checkpoint_stop.set()
        deadline = time.monotonic() + timeout_s
        with self._lock:
            batches = tuple(self._batches.values())
        for batch in batches:
            self._checkpoint_id(batch.batch_id)
        for batch in batches:
            thread = batch.thread
            if thread and thread.is_alive():
                thread.join(max(0.0, deadline - time.monotonic()))
        if self._checkpoint_thread.is_alive():
            self._checkpoint_thread.join(max(0.0, deadline - time.monotonic()))
        for batch in batches:
            self._checkpoint_id(batch.batch_id)
        self._state_store.close()

    @staticmethod
    def _restore_accumulator(raw: dict[str, Any]) -> OperationAccumulator:
        accumulator = OperationAccumulator()
        for name in (
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
            value = raw.get(name, 0)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                setattr(accumulator, name, value)
        return accumulator

    def _restore_site(
        self,
        target: BatchTarget,
        operations: tuple[Operation, ...],
        raw: dict[str, Any] | None,
    ) -> BatchSiteRuntime:
        operation_stats = {operation: OperationAccumulator() for operation in operations}
        if raw is None:
            return BatchSiteRuntime(target=target, operation_stats=operation_stats)
        raw_stats = raw.get("operation_statistics")
        if isinstance(raw_stats, dict):
            for operation in operations:
                candidate = raw_stats.get(operation.value)
                if isinstance(candidate, dict):
                    operation_stats[operation] = self._restore_accumulator(candidate)
        current_operation = raw.get("current_operation")
        return BatchSiteRuntime(
            target=target,
            state=BatchSiteState(str(raw.get("state", BatchSiteState.READY.value))),
            current_round=int(raw.get("current_round", 0) or 0),
            completed_rounds=int(raw.get("completed_rounds", 0) or 0),
            current_operation=Operation(str(current_operation)) if current_operation else None,
            current_job_id=str(raw["current_job_id"]) if raw.get("current_job_id") else None,
            progress_percent=float(raw.get("progress_percent", 0.0) or 0.0),
            total_attempts=int(raw.get("total_attempts", 0) or 0),
            retry_count=int(raw.get("retry_count", 0) or 0),
            final_failures=int(raw.get("final_failures", 0) or 0),
            faulted_round=int(raw["faulted_round"]) if raw.get("faulted_round") is not None else None,
            faulted_operation=(Operation(str(raw["faulted_operation"])) if raw.get("faulted_operation") else None),
            last_failure_source=(str(raw["last_failure_source"]) if raw.get("last_failure_source") else None),
            communication_state=str(raw.get("communication_state", "connected")),
            communication_attempt=int(raw.get("communication_attempt", 0) or 0),
            error=dict(raw["error"]) if isinstance(raw.get("error"), dict) else None,
            operation_stats=operation_stats,
        )

    @staticmethod
    def _target_device_from_spec(value: Any) -> BatchTargetDeviceSnapshot | None:
        if not isinstance(value, dict):
            return None
        return BatchTargetDeviceSnapshot(
            vendor=str(value["vendor"]),
            family=str(value["family"]),
            identifier=str(value["identifier"]),
            identifier_kind=str(value["identifier_kind"]),
            icpn=str(value["icpn"]) if value.get("icpn") is not None else None,
        )

    @staticmethod
    def _asset_snapshot_from_spec(value: Any) -> BatchAssetSnapshot | None:
        if not isinstance(value, dict):
            return None
        return BatchAssetSnapshot(
            name=str(value["name"]),
            asset_type=str(value["asset_type"]),
            asset_format=str(value["asset_format"]),
            size_bytes=int(value["size_bytes"]),
            sha256=str(value["sha256"]),
        )

    def _materialized_asset(self, stored: StoredBatch) -> ProgrammingAsset | None:
        raw = stored.spec.get("asset")
        if not isinstance(raw, dict):
            return None
        if stored.asset_data is None:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"Persisted Batch Asset bytes missing: {stored.batch_id}")
        return ProgrammingAsset.from_upload(
            name=str(raw["name"]),
            asset_type=str(raw["asset_type"]),
            asset_format=str(raw["asset_format"]),
            data=stored.asset_data,
            sha256=str(raw["sha256"]),
        )

    def _restore_record(self, stored: StoredBatch) -> BatchRecord:
        spec = stored.spec
        snapshot = stored.snapshot
        targets = tuple(
            BatchTarget(
                facility_id=str(raw["facility_id"]),
                ppu_id=str(raw["ppu_id"]),
                site_id=int(raw["site_id"]),
            )
            for raw in spec["targets"]
        )
        operations = normalize_batch_operations(tuple(str(value) for value in spec["operations"]))
        policy = BatchExecutionPolicy(**dict(spec["execution_policy"]))
        gateway_policy = GatewayCommunicationPolicy(**dict(spec["gateway_settings"]))
        site_payloads = {
            str(raw.get("key")): raw
            for raw in snapshot.get("sites", [])
            if isinstance(raw, dict) and raw.get("key")
        }
        sites = {
            target.key: self._restore_site(target, operations, site_payloads.get(target.key))
            for target in targets
        }
        recovery = snapshot.get("_recovery") if isinstance(snapshot.get("_recovery"), dict) else {}
        read = spec.get("read") if isinstance(spec.get("read"), dict) else {}
        state_value = str(snapshot.get("state", BatchState.QUEUED.value))
        batch = BatchRecord(
            batch_id=stored.batch_id,
            operations=operations,
            policy=policy,
            gateway_policy=gateway_policy,
            targets=targets,
            sites=sites,
            session_id=(str(spec["session_id"]) if spec.get("session_id") else None),
            target_device=self._target_device_from_spec(spec.get("target_device")),
            asset=self._asset_snapshot_from_spec(spec.get("asset")),
            read_offset=int(read.get("offset", 0)),
            read_length=int(read.get("length", 256)),
            state=BatchState(state_value),
            created_at=str(snapshot.get("created_at") or stored.updated_at),
            started_at=str(snapshot["started_at"]) if snapshot.get("started_at") else None,
            finished_at=None,
            stop_reason=str(snapshot["stop_reason"]) if snapshot.get("stop_reason") else None,
            error=dict(snapshot["error"]) if isinstance(snapshot.get("error"), dict) else None,
            cancel_requested=bool(snapshot.get("cancel_requested", False)),
            cancelled_ppus=set(str(value) for value in recovery.get("cancelled_ppus", [])),
            failed_ppus=set(str(value) for value in recovery.get("failed_ppus", [])),
        )
        return batch

    def _restore_nonterminal_batches(self) -> None:
        for stored in self._state_store.load_recoverable():
            try:
                batch = self._restore_record(stored)
                jobs = self._state_store.load_jobs(stored.batch_id)
                for job in jobs:
                    with self._job_map_lock:
                        self._job_batches[job.job_id] = stored.batch_id
                    if job.phase in {"submitting", "accepted"}:
                        target = batch.sites.get(job.site_key)
                        if target is not None:
                            target.current_job_id = job.job_id
                            batch.active_jobs[job.site_key] = (target.target, job.job_id)
                self._recache_asset(stored, batch)
                with self._lock:
                    self._batches[batch.batch_id] = batch
                thread = threading.Thread(
                    target=self._recovery_thread_main,
                    args=(batch, jobs),
                    name=f"plasma-recover-{batch.batch_id}",
                    daemon=True,
                )
                batch.thread = thread
                thread.start()
            except Exception as exc:
                # A corrupt/unloadable durable record remains durable for manual
                # diagnosis. It must not be silently converted into SUCCESS/FAIL.
                snapshot = dict(stored.snapshot)
                snapshot.update(
                    {
                        "batch_id": stored.batch_id,
                        "state": BatchState.ERROR.value,
                        "finished_at": iso_now(),
                        "stop_reason": "recovery_load_error",
                        "error": {
                            "error_code": BATCH_RECOVERY_ERROR,
                            "message": f"Batch recovery load failed: {type(exc).__name__}: {exc}",
                        },
                    }
                )
                self._state_store.save_snapshot(stored.batch_id, snapshot)

    def _recache_asset(self, stored: StoredBatch, batch: BatchRecord) -> None:
        asset = self._materialized_asset(stored)
        if asset is None:
            return
        if not batch.session_id:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Persisted Program/Verify Batch session_id is missing")
        for facility_id, ppu_id in sorted({(target.facility_id, target.ppu_id) for target in batch.targets}):
            self.provider.cache_asset(
                batch.session_id,
                facility_id,
                ppu_id,
                asset.name,
                asset.asset_type.value,
                asset.asset_format.value,
                asset.sha256,
                asset.data,
            )

    def _recovery_thread_main(self, batch: BatchRecord, jobs: list[StoredBatchJob]) -> None:
        loop = asyncio.new_event_loop()
        with batch.lock:
            batch.loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._recover_execute(batch, jobs))
        except _BatchRuntimeSuspended:
            pass
        except BaseException as exc:
            with batch.lock:
                batch.state = BatchState.ERROR
                batch.stop_reason = "recovery_exception"
                batch.error = {
                    "error_code": BATCH_RECOVERY_ERROR,
                    "message": f"Batch recovery failed: {type(exc).__name__}: {exc}",
                }
                batch.finished_at = iso_now()
        finally:
            with batch.lock:
                batch.loop = None
            self._checkpoint_id(batch.batch_id)
            loop.close()

    async def _recover_execute(self, batch: BatchRecord, jobs: list[StoredBatchJob]) -> None:
        jobs_by_site: dict[str, list[StoredBatchJob]] = defaultdict(list)
        for job in jobs:
            jobs_by_site[job.site_key].append(job)
        with batch.lock:
            if batch.started_at is None:
                batch.started_at = iso_now()
            if batch.cancel_requested or batch.state is BatchState.STOPPING:
                batch.state = BatchState.STOPPING
            else:
                batch.state = BatchState.RUNNING
        self._checkpoint_id(batch.batch_id)

        await asyncio.gather(
            *(
                self._recover_site(batch, batch.sites[target.key], jobs_by_site.get(target.key, []))
                for target in batch.targets
            )
        )

        with batch.lock:
            if batch.cancel_requested or batch.stop_reason == "operator_cancel":
                batch.state = BatchState.CANCELLED
            elif batch.stop_reason in {"failed_site_threshold", "runtime_exception", "recovery_exception"}:
                batch.state = BatchState.ERROR
            else:
                states = [site.state for site in batch.sites.values()]
                if states and all(state is BatchSiteState.SUCCESS for state in states):
                    batch.state = BatchState.SUCCESS
                elif states and all(state is BatchSiteState.CANCELLED for state in states):
                    batch.state = BatchState.CANCELLED
                elif any(state is BatchSiteState.ERROR for state in states):
                    batch.state = BatchState.PARTIAL if any(state is BatchSiteState.SUCCESS for state in states) else BatchState.ERROR
                else:
                    batch.state = BatchState.PARTIAL
            batch.finished_at = iso_now()
        self._checkpoint_id(batch.batch_id)

    async def _reconcile_job(
        self,
        batch: BatchRecord,
        site: BatchSiteRuntime,
        persisted: StoredBatchJob,
    ) -> dict[str, Any] | None:
        while True:
            try:
                response = await self._provider_request(
                    batch,
                    site,
                    "recovery_status",
                    lambda: self.provider.status(
                        persisted.facility_id,
                        persisted.ppu_id,
                        site_id=persisted.site_id,
                        job_id=persisted.job_id,
                    ),
                )
            except PlasmaError as exc:
                if exc.code is ErrorCode.JOB_NOT_FOUND and persisted.phase == "submitting":
                    self._state_store.update_job(batch.batch_id, persisted.job_id, phase="rejected")
                    with batch.lock:
                        batch.active_jobs.pop(site.target.key, None)
                        site.current_job_id = None
                    return None
                if exc.code is ErrorCode.JOB_NOT_FOUND:
                    with batch.lock:
                        site.state = BatchSiteState.ERROR
                        site.error = {
                            "error_code": BATCH_RECOVERY_JOB_UNKNOWN,
                            "message": f"PPU no longer reports accepted Job {persisted.job_id}",
                        }
                        batch.stop_reason = batch.stop_reason or "recovery_job_unknown"
                        batch.error = dict(site.error)
                    raise RuntimeError(site.error["message"]) from exc
                raise
            job = response.get("job") if isinstance(response, dict) else None
            if not isinstance(job, dict):
                raise RuntimeError("PPU recovery status is missing Job snapshot")
            with batch.lock:
                site.current_job_id = persisted.job_id
                site.progress_percent = float(job.get("progress_percent", site.progress_percent) or 0.0)
            if str(job.get("state", "")) in _TERMINAL_JOB_STATES:
                self._state_store.update_job(batch.batch_id, persisted.job_id, phase="terminal", job=job)
                with batch.lock:
                    batch.active_jobs.pop(site.target.key, None)
                return job
            await asyncio.sleep(self.poll_interval_s)

    async def _apply_terminal_job(
        self,
        batch: BatchRecord,
        site: BatchSiteRuntime,
        operation: Operation,
        round_index: int,
        job: dict[str, Any],
    ) -> bool:
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
            return True
        if state == "cancelled":
            disposition = self._stop_disposition(batch, site) or BatchSiteState.CANCELLED
            with batch.lock:
                site.state = disposition
            return False
        if state in {"error", "aborted"}:
            with batch.lock:
                site.state = BatchSiteState.ERROR
            await self._trip_infrastructure_error(batch, site, RuntimeError(site.error or state))
            return False
        if state in {"failed", "timeout"}:
            with batch.lock:
                site.state = BatchSiteState.FAULTED
                site.final_failures += 1
                site.faulted_round = round_index
                site.faulted_operation = operation
            await self._register_faulted_site(batch, site)
            return False
        with batch.lock:
            site.state = BatchSiteState.ERROR
            site.error = {
                "error_code": BATCH_RECOVERY_ERROR,
                "message": f"unexpected recovered Job state: {state!r}",
            }
        return False

    async def _recover_site(
        self,
        batch: BatchRecord,
        site: BatchSiteRuntime,
        jobs: list[StoredBatchJob],
    ) -> None:
        if site.state.terminal:
            return
        pending = [job for job in jobs if job.phase in {"submitting", "accepted"}]
        start_round = max(1, site.completed_rounds + 1)
        start_operation_index = 0

        if pending:
            persisted = pending[-1]
            operation = Operation(persisted.operation)
            round_index = persisted.round_index
            with batch.lock:
                site.state = BatchSiteState.RUNNING
                site.current_round = round_index
                site.current_operation = operation
            job = await self._reconcile_job(batch, site, persisted)
            if job is not None:
                if not await self._apply_terminal_job(batch, site, operation, round_index, job):
                    return
                operation_index = batch.operations.index(operation)
                if operation_index + 1 < len(batch.operations):
                    start_round = round_index
                    start_operation_index = operation_index + 1
                else:
                    with batch.lock:
                        site.completed_rounds = max(site.completed_rounds, round_index)
                    start_round = round_index + 1
                    start_operation_index = 0
            else:
                start_round = round_index
                start_operation_index = batch.operations.index(operation)
        elif site.current_operation is not None and site.current_round > site.completed_rounds:
            start_round = site.current_round
            start_operation_index = batch.operations.index(site.current_operation)

        if batch.cancel_requested or batch.stop_reason == "operator_cancel":
            with batch.lock:
                site.state = BatchSiteState.CANCELLED
                site.current_operation = None
                site.current_job_id = None
            return

        for round_index in range(start_round, batch.policy.repeat_count + 1):
            first_index = start_operation_index if round_index == start_round else 0
            with batch.lock:
                site.state = BatchSiteState.RUNNING
                site.current_round = round_index
            for operation_index in range(first_index, len(batch.operations)):
                operation = batch.operations[operation_index]
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
                self._checkpoint_id(batch.batch_id)
                try:
                    job = await self._execute_operation(batch, site, operation, round_index)
                except _BatchRuntimeSuspended:
                    raise
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
                if not await self._apply_terminal_job(batch, site, operation, round_index, job):
                    return
            with batch.lock:
                site.completed_rounds = round_index
                site.current_operation = None
                site.progress_percent = 100.0
            self._checkpoint_id(batch.batch_id)

        with batch.lock:
            site.state = BatchSiteState.SUCCESS
            site.current_job_id = None
            site.current_operation = None
            site.progress_percent = 100.0
        self._checkpoint_id(batch.batch_id)
