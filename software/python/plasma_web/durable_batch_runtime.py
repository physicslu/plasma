from __future__ import annotations

from collections import defaultdict
from typing import Any

from plasma_core.batch import BatchSiteState
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError

from .batch_runtime import BatchRecord, BatchSiteRuntime, OperationAccumulator
from .batch_state_store import StoredBatchJob
from .persistent_batch_runtime import PersistentBatchRuntimeManager


class DurableBatchRuntimeManager(PersistentBatchRuntimeManager):
    """Production recovery policy built on the persistent Batch substrate.

    Recovery reconstructs Site accounting/cursor from the durable Job ledger so
    a Job that reached terminal state immediately before a Gateway crash is not
    submitted again merely because the in-memory Site snapshot had not yet
    advanced. Retained terminal snapshots remain queryable after later Gateway
    restarts for the configured durable-history retention window.
    """

    @staticmethod
    def _public_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
        result = dict(snapshot)
        result.pop("_recovery", None)
        return result

    def _historical_snapshot(self, batch_id: str) -> dict[str, Any] | None:
        stored = self._state_store.load_batch(batch_id)
        if stored is None or not stored.snapshot:
            return None
        state = str(stored.snapshot.get("state", ""))
        if state not in {"success", "partial", "error", "cancelled"}:
            return None
        return self._public_snapshot(stored.snapshot)

    def get(self, batch_id: str) -> dict[str, Any]:
        try:
            return super().get(batch_id)
        except PlasmaError as exc:
            if exc.code is not ErrorCode.JOB_NOT_FOUND:
                raise
            historical = self._historical_snapshot(batch_id)
            if historical is None:
                raise
            return historical

    def cancel(self, batch_id: str) -> dict[str, Any]:
        try:
            return super().cancel(batch_id)
        except PlasmaError as exc:
            if exc.code is not ErrorCode.JOB_NOT_FOUND:
                raise
            historical = self._historical_snapshot(batch_id)
            if historical is None:
                raise
            return historical

    def cancel_ppu(self, batch_id: str, facility_id: str, ppu_id: str) -> dict[str, Any]:
        try:
            return super().cancel_ppu(batch_id, facility_id, ppu_id)
        except PlasmaError as exc:
            if exc.code is not ErrorCode.JOB_NOT_FOUND:
                raise
            historical = self._historical_snapshot(batch_id)
            if historical is None:
                raise
            site_matches = any(
                isinstance(site, dict)
                and site.get("facility_id") == facility_id
                and site.get("ppu_id") == ppu_id
                for site in historical.get("sites", [])
            )
            if not site_matches:
                raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PPU is not part of this Batch")
            return historical

    @staticmethod
    def _operation_index(batch: BatchRecord, operation: str) -> int:
        return batch.operations.index(Operation(operation))

    def _rebuild_site_from_ledger(
        self,
        batch: BatchRecord,
        site: BatchSiteRuntime,
        jobs: list[StoredBatchJob],
    ) -> None:
        stats = {operation: OperationAccumulator() for operation in batch.operations}
        total_attempts = 0
        retry_count = 0
        final_failures = 0
        terminal_by_step: dict[tuple[int, Operation], dict[str, Any]] = {}
        pending_steps: set[tuple[int, Operation]] = set()

        for persisted in jobs:
            operation = Operation(persisted.operation)
            step = (persisted.round_index, operation)
            if persisted.phase in {"submitting", "accepted"}:
                stats[operation].begin()
                pending_steps.add(step)
                continue
            if persisted.phase != "terminal" or not isinstance(persisted.job, dict):
                continue
            stats[operation].begin()
            stats[operation].record_job(persisted.job)
            terminal_by_step[step] = persisted.job
            result = persisted.job.get("result") if isinstance(persisted.job.get("result"), dict) else {}
            attempts = result.get("attempts")
            if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts <= 0:
                attempts = max(1, len(result.get("attempt_history", [])))
            total_attempts += attempts
            retry_count += max(0, attempts - 1)
            if str(persisted.job.get("state", "")) in {"failed", "timeout"}:
                final_failures += 1

        with batch.lock:
            site.operation_stats = stats
            site.total_attempts = total_attempts
            site.retry_count = retry_count
            site.final_failures = final_failures

        first_missing: tuple[int, int] | None = None
        completed_rounds = 0
        terminal_failure: tuple[int, Operation, dict[str, Any]] | None = None
        for round_index in range(1, batch.policy.repeat_count + 1):
            round_complete = True
            for operation_index, operation in enumerate(batch.operations):
                job = terminal_by_step.get((round_index, operation))
                if job is None:
                    round_complete = False
                    if first_missing is None:
                        first_missing = (round_index, operation_index)
                    break
                state = str(job.get("state", ""))
                if state != "success":
                    terminal_failure = (round_index, operation, job)
                    round_complete = False
                    break
            if terminal_failure is not None:
                break
            if round_complete:
                completed_rounds = round_index
                continue
            break

        with batch.lock:
            site.completed_rounds = completed_rounds

        if terminal_failure is not None:
            round_index, operation, job = terminal_failure
            state = str(job.get("state", ""))
            result = job.get("result") if isinstance(job.get("result"), dict) else {}
            error = result.get("error") if isinstance(result.get("error"), dict) else None
            with batch.lock:
                site.current_round = round_index
                site.current_operation = operation
                site.current_job_id = None
                site.progress_percent = float(job.get("progress_percent", 100.0) or 0.0)
                site.last_failure_source = str(error.get("failure_source")) if error and error.get("failure_source") else None
                site.error = dict(error) if error else None
                if state in {"failed", "timeout"}:
                    site.state = BatchSiteState.FAULTED
                    site.faulted_round = round_index
                    site.faulted_operation = operation
                elif state in {"error", "aborted"}:
                    site.state = BatchSiteState.ERROR
                elif state == "cancelled":
                    site.state = BatchSiteState.CANCELLED
            return

        if first_missing is None:
            with batch.lock:
                site.state = BatchSiteState.SUCCESS
                site.current_round = batch.policy.repeat_count
                site.current_operation = None
                site.current_job_id = None
                site.progress_percent = 100.0
            return

        round_index, operation_index = first_missing
        with batch.lock:
            if site.state.terminal and site.state is not BatchSiteState.SUCCESS:
                return
            site.state = BatchSiteState.RUNNING
            site.current_round = round_index
            site.current_operation = batch.operations[operation_index]
            if (round_index, batch.operations[operation_index]) not in pending_steps:
                site.current_job_id = None
                site.progress_percent = 0.0

    async def _recover_cancelled_site(
        self,
        batch: BatchRecord,
        site: BatchSiteRuntime,
        jobs: list[StoredBatchJob],
    ) -> None:
        pending = [job for job in jobs if job.phase in {"submitting", "accepted"}]
        for persisted in pending:
            try:
                await self._provider_request(
                    batch,
                    site,
                    "recovery_cancel",
                    lambda persisted=persisted: self.provider.cancel_job(
                        persisted.facility_id,
                        persisted.ppu_id,
                        persisted.job_id,
                    ),
                )
            except PlasmaError as exc:
                if exc.code is ErrorCode.JOB_NOT_FOUND and persisted.phase == "submitting":
                    self._state_store.update_job(batch.batch_id, persisted.job_id, phase="rejected")
                    continue
                raise
            terminal = await self._reconcile_job(batch, site, persisted)
            if terminal is not None:
                operation = Operation(persisted.operation)
                await self._apply_terminal_job(
                    batch,
                    site,
                    operation,
                    persisted.round_index,
                    terminal,
                )
        with batch.lock:
            site.state = BatchSiteState.CANCELLED
            site.current_operation = None
            site.current_job_id = None
        self._checkpoint_id(batch.batch_id)

    async def _recover_site(
        self,
        batch: BatchRecord,
        site: BatchSiteRuntime,
        jobs: list[StoredBatchJob],
    ) -> None:
        self._rebuild_site_from_ledger(batch, site, jobs)
        if batch.cancel_requested or batch.stop_reason == "operator_cancel":
            await self._recover_cancelled_site(batch, site, jobs)
            return
        if site.state.terminal:
            return
        await super()._recover_site(batch, site, jobs)
