from __future__ import annotations

import tempfile
import threading
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plasma_core.batch import BatchExecutionPolicy, BatchTarget
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.batch_runtime import BatchRuntimeManager
from plasma_web.durable_batch_runtime import DurableBatchRuntimeManager
from plasma_web.persistent_batch_runtime import PersistentBatchRuntimeManager
from plasma_web.persistent_mock_batch_runtime import PersistentMockAwareBatchRuntimeManager


class ContractProvider:
    """Small authoritative PPU double shared by the Batch runtime contract suite."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.jobs: dict[str, dict[str, Any]] = {}
        self.start_calls: list[str] = []
        self.cancel_calls: list[str] = []
        self._batch_contexts: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def catalog(self) -> dict[str, Any]:
        return {}

    def begin_session(self, previous_session_id=None) -> dict[str, str]:
        return {"session_id": "contract-session"}

    def asset_cache_status(self, *args, **kwargs) -> dict[str, bool]:
        return {"cache_hit": False}

    def cache_asset(self, *args, **kwargs) -> dict[str, bool]:
        return {"ok": True}

    def job_timeout_s(self, facility_id: str, ppu_id: str) -> float:
        return 1.0

    async def start_job(
        self,
        facility_id: str,
        ppu_id: str,
        request,
        *,
        session_id=None,
        asset_sha256=None,
    ) -> dict[str, Any]:
        with self._lock:
            self.start_calls.append(request.job_id)
            job = {
                "job_id": request.job_id,
                "site_id": request.site_id,
                "operation": request.operation.value,
                "state": "running",
                "progress_percent": 10.0,
                "result": None,
            }
            self.jobs[request.job_id] = job
            return {"ok": True, "job": dict(job)}

    async def status(
        self,
        facility_id: str,
        ppu_id: str,
        *,
        site_id: int | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        if job_id is None:
            return {"ok": True, "sites": []}
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise PlasmaError(ErrorCode.JOB_NOT_FOUND, f"Job not found: {job_id}")
            return {"ok": True, "job": dict(job)}

    async def cancel_job(self, facility_id: str, ppu_id: str, job_id: str) -> dict[str, Any]:
        with self._lock:
            self.cancel_calls.append(job_id)
            job = self.jobs.get(job_id)
            if job is None:
                raise PlasmaError(ErrorCode.JOB_NOT_FOUND, f"Job not found: {job_id}")
            job.update(
                {
                    "state": "cancelled",
                    "result": {
                        "state": "cancelled",
                        "attempts": 1,
                        "attempt_history": [],
                        "error": None,
                    },
                }
            )
            return {"ok": True, "job": dict(job)}

    def read_output_file(self, *args, **kwargs) -> bytes:
        return b""

    def complete(self, job_id: str, *, state: str = "success") -> None:
        error = None
        if state in {"error", "aborted"}:
            error = {
                "error_code": ErrorCode.INTERFACE_FAILURE.value,
                "error_type": "INTERFACE_FAILURE",
                "message": "injected infrastructure terminal state",
                "recoverable": False,
                "failure_source": "infrastructure",
            }
        with self._lock:
            self.jobs[job_id].update(
                {
                    "state": state,
                    "progress_percent": 100.0,
                    "result": {
                        "state": state,
                        "attempts": 1,
                        "attempt_history": [],
                        "error": error,
                    },
                }
            )

    # PersistentMockAwareBatchRuntimeManager deliberately adds only Mock
    # process-lifetime context semantics; the core Batch contract remains the
    # same. These methods model that provider extension without starting PPUs.
    def freeze_batch_context(self, batch_id: str) -> dict[str, Any]:
        context = {"batch_id": batch_id, "profile": "contract"}
        self._batch_contexts[batch_id] = context
        return dict(context)

    def batch_context(self, batch_id: str) -> dict[str, Any] | None:
        context = self._batch_contexts.get(batch_id)
        return dict(context) if context is not None else None

    def release_batch_context(self, batch_id: str) -> None:
        self._batch_contexts.pop(batch_id, None)


@dataclass(frozen=True)
class RuntimeCase:
    name: str
    manager_type: type[BatchRuntimeManager]
    persistent: bool = False
    mock_process_coupled: bool = False


RUNTIME_CASES = (
    RuntimeCase("memory", BatchRuntimeManager),
    RuntimeCase("persistent", PersistentBatchRuntimeManager, persistent=True),
    RuntimeCase("durable", DurableBatchRuntimeManager, persistent=True),
    RuntimeCase(
        "persistent-mock-aware",
        PersistentMockAwareBatchRuntimeManager,
        persistent=True,
        mock_process_coupled=True,
    ),
)


def wait_until(predicate, timeout_s: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true before timeout")


class BatchRuntimeContractTests(unittest.TestCase):
    """Conformance contract for the layered Batch runtime family.

    The subclasses add persistence/recovery policy; they are not independent
    manufacturing engines. Every layer must preserve the public create/get/
    cancel/terminal semantics exercised here.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.target = BatchTarget(facility_id="factory-a", ppu_id="ppu-01", site_id=1)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def new_manager(
        self,
        case: RuntimeCase,
        provider: ContractProvider,
        *,
        state_path: Path | None = None,
    ) -> BatchRuntimeManager:
        common: dict[str, Any] = {
            "poll_interval_s": 0.01,
            "retry_backoff_s": 0.01,
        }
        if case.persistent:
            common.update(
                {
                    "state_path": state_path or self.root / f"{case.name}.sqlite3",
                    "checkpoint_interval_s": 0.01,
                }
            )
        return case.manager_type(provider, **common)

    def create_erase(self, manager: BatchRuntimeManager) -> dict[str, Any]:
        return manager.create_batch(
            targets=(self.target,),
            operations=["erase"],
            policy=BatchExecutionPolicy(),
        )

    def test_common_create_get_terminal_and_idempotent_cancel_contract(self) -> None:
        for case in RUNTIME_CASES:
            with self.subTest(runtime=case.name):
                provider = ContractProvider(self.root / case.name)
                manager = self.new_manager(case, provider)
                try:
                    created = self.create_erase(manager)
                    batch_id = created["batch_id"]
                    self.assertTrue(batch_id.startswith("batch-"))
                    self.assertEqual(created["operations"], ["erase"])
                    self.assertEqual(len(created["sites"]), 1)

                    wait_until(lambda: len(provider.start_calls) == 1)
                    observed = manager.get(batch_id)
                    self.assertEqual(observed["batch_id"], batch_id)
                    self.assertIn(observed["state"], {"queued", "running"})

                    job_id = provider.start_calls[0]
                    provider.complete(job_id)
                    wait_until(lambda: manager.get(batch_id)["state"] == "success")

                    final = manager.get(batch_id)
                    self.assertEqual(final["state"], "success")
                    self.assertEqual(final["sites"][0]["state"], "success")
                    self.assertEqual(final["sites"][0]["completed_rounds"], 1)
                    self.assertEqual(manager.cancel(batch_id)["state"], "success")
                    self.assertEqual(provider.cancel_calls, [])
                finally:
                    manager.close(timeout_s=1.0)

    def test_common_operator_cancel_contract(self) -> None:
        for case in RUNTIME_CASES:
            with self.subTest(runtime=case.name):
                provider = ContractProvider(self.root / f"cancel-{case.name}")
                manager = self.new_manager(
                    case,
                    provider,
                    state_path=self.root / f"cancel-{case.name}.sqlite3",
                )
                try:
                    batch_id = self.create_erase(manager)["batch_id"]
                    wait_until(lambda: len(provider.start_calls) == 1)
                    cancelled = manager.cancel(batch_id)
                    self.assertTrue(cancelled["cancel_requested"])
                    self.assertEqual(cancelled["stop_reason"], "operator_cancel")
                    wait_until(lambda: manager.get(batch_id)["state"] == "cancelled")
                    final = manager.get(batch_id)
                    self.assertEqual(final["state"], "cancelled")
                    self.assertGreaterEqual(len(provider.cancel_calls), 1)
                finally:
                    manager.close(timeout_s=1.0)

    def test_common_unknown_batch_contract(self) -> None:
        for case in RUNTIME_CASES:
            with self.subTest(runtime=case.name):
                provider = ContractProvider(self.root / f"unknown-{case.name}")
                manager = self.new_manager(
                    case,
                    provider,
                    state_path=self.root / f"unknown-{case.name}.sqlite3",
                )
                try:
                    with self.assertRaises(PlasmaError) as caught:
                        manager.get("batch-does-not-exist")
                    self.assertEqual(caught.exception.code, ErrorCode.JOB_NOT_FOUND)
                finally:
                    manager.close(timeout_s=1.0)

    def test_independent_provider_recovery_reconciles_without_duplicate_submission(self) -> None:
        for case in RUNTIME_CASES:
            if not case.persistent or case.mock_process_coupled:
                continue
            with self.subTest(runtime=case.name):
                provider = ContractProvider(self.root / f"recover-{case.name}")
                state_path = self.root / f"recover-{case.name}.sqlite3"
                first = self.new_manager(case, provider, state_path=state_path)
                batch_id = self.create_erase(first)["batch_id"]
                wait_until(lambda: len(provider.start_calls) == 1)
                job_id = provider.start_calls[0]
                first.close(timeout_s=1.0)

                provider.complete(job_id)
                recovered = self.new_manager(case, provider, state_path=state_path)
                try:
                    wait_until(lambda: recovered.get(batch_id)["state"] == "success")
                    self.assertEqual(provider.start_calls, [job_id])
                    self.assertEqual(recovered.get(batch_id)["sites"][0]["completed_rounds"], 1)
                finally:
                    recovered.close(timeout_s=1.0)

    def test_process_coupled_mock_recovery_fails_closed_without_resubmission(self) -> None:
        case = next(item for item in RUNTIME_CASES if item.mock_process_coupled)
        provider = ContractProvider(self.root / "mock-recovery")
        state_path = self.root / "mock-recovery.sqlite3"
        first = self.new_manager(case, provider, state_path=state_path)
        batch_id = self.create_erase(first)["batch_id"]
        wait_until(lambda: len(provider.start_calls) == 1)
        job_id = provider.start_calls[0]
        first.close(timeout_s=1.0)

        recovered = self.new_manager(case, provider, state_path=state_path)
        try:
            final = recovered.get(batch_id)
            self.assertEqual(final["state"], "error")
            self.assertEqual(final["stop_reason"], "mock_ppu_restart")
            self.assertEqual(provider.start_calls, [job_id])
        finally:
            recovered.close(timeout_s=1.0)


if __name__ == "__main__":
    unittest.main()
