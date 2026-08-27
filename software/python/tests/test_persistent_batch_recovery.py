from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from plasma_core.batch import BatchExecutionPolicy, BatchTarget
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.batch_state_store import BatchStateStore
from plasma_web.persistent_batch_runtime import PersistentBatchRuntimeManager


class DurableProvider:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.start_calls: list[str] = []
        self.cancel_calls: list[str] = []
        self._lock = threading.RLock()

    def catalog(self):
        return {}

    def begin_session(self, previous_session_id=None):
        return {"session_id": "session"}

    def asset_cache_status(self, *args, **kwargs):
        return {"cache_hit": False}

    def cache_asset(self, *args, **kwargs):
        return {"ok": True}

    def job_timeout_s(self, facility_id, ppu_id):
        return 1.0

    async def start_job(self, facility_id, ppu_id, request, *, session_id=None, asset_sha256=None):
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

    async def status(self, facility_id, ppu_id, *, site_id=None, job_id=None):
        if job_id is None:
            return {"ok": True, "sites": []}
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise PlasmaError(ErrorCode.JOB_NOT_FOUND, f"Job not found: {job_id}")
            return {"ok": True, "job": dict(job)}

    async def cancel_job(self, facility_id, ppu_id, job_id):
        with self._lock:
            self.cancel_calls.append(job_id)
            job = self.jobs.get(job_id)
            if job is None:
                raise PlasmaError(ErrorCode.JOB_NOT_FOUND, f"Job not found: {job_id}")
            job.update(
                {
                    "state": "cancelled",
                    "progress_percent": job.get("progress_percent", 0.0),
                    "result": {
                        "state": "cancelled",
                        "attempts": 1,
                        "attempt_history": [],
                        "error": None,
                    },
                }
            )
            return {"ok": True, "job": dict(job)}

    def read_output_file(self, *args, **kwargs):
        return b""

    def complete(self, job_id: str, state: str = "success") -> None:
        with self._lock:
            job = self.jobs[job_id]
            job.update(
                {
                    "state": state,
                    "progress_percent": 100.0,
                    "result": {
                        "state": state,
                        "attempts": 1,
                        "attempt_history": [],
                        "error": None,
                    },
                }
            )


def wait_until(predicate, timeout_s: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true before timeout")


class BatchStateStoreTests(unittest.TestCase):
    def test_schema_is_versioned_and_prepared_batch_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BatchStateStore(Path(directory) / "batch-state.sqlite3")
            store.prepare_batch(
                "batch-test",
                spec={"targets": [], "operations": ["erase"]},
                asset_data=None,
            )
            recovered = store.load_recoverable()
            self.assertEqual([item.batch_id for item in recovered], ["batch-test"])
            self.assertEqual(recovered[0].spec["operations"], ["erase"])
            store.close()


class PersistentBatchRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp.name) / "batch-state.sqlite3"
        self.provider = DurableProvider()
        self.target = BatchTarget(facility_id="factory-a", ppu_id="ppu-01", site_id=1)

    def tearDown(self):
        self.temp.cleanup()

    def new_manager(self) -> PersistentBatchRuntimeManager:
        return PersistentBatchRuntimeManager(
            self.provider,
            state_path=self.state_path,
            poll_interval_s=0.01,
            retry_backoff_s=0.01,
            checkpoint_interval_s=0.01,
        )

    def test_restart_reconciles_existing_job_without_duplicate_submission(self):
        manager = self.new_manager()
        snapshot = manager.create_batch(
            targets=(self.target,),
            operations=["erase"],
            policy=BatchExecutionPolicy(),
        )
        batch_id = snapshot["batch_id"]
        wait_until(lambda: len(self.provider.start_calls) == 1)
        job_id = self.provider.start_calls[0]

        manager.close(timeout_s=1.0)
        self.assertEqual(self.provider.start_calls, [job_id])

        self.provider.complete(job_id)
        recovered = self.new_manager()
        wait_until(lambda: recovered.get(batch_id)["state"] == "success")
        final = recovered.get(batch_id)
        self.assertEqual(final["state"], "success")
        self.assertEqual(final["sites"][0]["completed_rounds"], 1)
        self.assertEqual(self.provider.start_calls, [job_id])
        recovered.close(timeout_s=1.0)

    def test_accepted_job_missing_after_restart_fails_closed(self):
        manager = self.new_manager()
        snapshot = manager.create_batch(
            targets=(self.target,),
            operations=["erase"],
            policy=BatchExecutionPolicy(),
        )
        batch_id = snapshot["batch_id"]
        wait_until(lambda: len(self.provider.start_calls) == 1)
        job_id = self.provider.start_calls[0]
        manager.close(timeout_s=1.0)

        with self.provider._lock:
            self.provider.jobs.pop(job_id)

        recovered = self.new_manager()
        wait_until(lambda: recovered.get(batch_id)["state"] == "error")
        final = recovered.get(batch_id)
        self.assertEqual(final["state"], "error")
        self.assertIn(final["stop_reason"], {"recovery_exception", "recovery_job_unknown"})
        self.assertEqual(self.provider.start_calls, [job_id])
        recovered.close(timeout_s=1.0)


if __name__ == "__main__":
    unittest.main()
