from __future__ import annotations

import hashlib
import threading
import time
import unittest
from typing import Any

from plasma_core.assets import ProgrammingAsset
from plasma_core.batch import BatchExecutionPolicy, BatchTarget
from plasma_core.errors import PlasmaError
from plasma_web.batch_runtime import BatchRuntimeManager


class FakeBatchProvider:
    def __init__(
        self,
        *,
        fail_sites: set[int] | None = None,
        error_sites: set[int] | None = None,
        status_delays: dict[int, float] | None = None,
    ) -> None:
        self.fail_sites = set(fail_sites or set())
        self.error_sites = set(error_sites or set())
        self.status_delays = dict(status_delays or {})
        self.jobs: dict[str, dict[str, Any]] = {}
        self.start_log: list[tuple[str, str, int, str, int, int]] = []
        self.cache_log: list[tuple[str, str, str, int]] = []
        self.cancel_log: list[tuple[str, str, str]] = []
        self._sequence = 0
        self._lock = threading.Lock()

    def catalog(self):
        return {"ok": True, "provider": "fake", "facilities": []}

    def begin_session(self, previous_session_id=None):
        return {"ok": True, "session": {"session_id": "1" * 32}}

    def asset_cache_status(self, *args, **kwargs):
        return {"ok": True, "programming_asset": {"cache_hit": False}}

    def cache_asset(
        self,
        session_id,
        facility_id,
        ppu_id,
        asset_name,
        asset_type,
        asset_format,
        asset_sha256,
        data,
    ):
        with self._lock:
            self.cache_log.append((facility_id, ppu_id, asset_sha256, id(data)))
        return {"ok": True, "programming_asset": {"cache_hit": True}}

    def job_timeout_s(self, facility_id, ppu_id):
        return 2.0

    async def start_job(
        self,
        facility_id,
        ppu_id,
        request,
        *,
        session_id=None,
        asset_sha256=None,
    ):
        with self._lock:
            self._sequence += 1
            job_id = f"fake-job-{self._sequence}"
            round_index = int(request.metadata.get("batch_round", 0))
            self.start_log.append(
                (
                    facility_id,
                    ppu_id,
                    request.site_id,
                    request.operation.value,
                    round_index,
                    request.max_retries,
                )
            )
            attempts = request.max_retries + 1
            if request.site_id in self.error_sites:
                state = "error"
                history = [
                    {
                        "attempt": 1,
                        "state": "error",
                        "error": {"failure_source": "infrastructure"},
                    }
                ]
                result = {
                    "state": state,
                    "attempts": 1,
                    "retry_exhausted": False,
                    "attempt_history": history,
                    "error": {
                        "error_code": "E5002",
                        "message": "fake infrastructure error",
                        "failure_source": "infrastructure",
                    },
                }
            elif request.site_id in self.fail_sites:
                state = "failed"
                history = [
                    {
                        "attempt": attempt,
                        "state": "failed",
                        "error": {"failure_source": "injected"},
                    }
                    for attempt in range(1, attempts + 1)
                ]
                result = {
                    "state": state,
                    "attempts": attempts,
                    "retry_exhausted": True,
                    "attempt_history": history,
                    "error": {
                        "error_code": "E6002",
                        "message": "fake program failure",
                        "failure_source": "injected",
                    },
                }
            else:
                state = "success"
                attempts = 1
                result = {
                    "state": state,
                    "attempts": attempts,
                    "retry_exhausted": False,
                    "attempt_history": [{"attempt": 1, "state": "success"}],
                    "error": None,
                }
            self.jobs[job_id] = {
                "job_id": job_id,
                "site_id": request.site_id,
                "operation": request.operation.value,
                "state": state,
                "progress_percent": 100.0,
                "result": result,
            }
        return {
            "ok": True,
            "job": {
                "job_id": job_id,
                "site_id": request.site_id,
                "operation": request.operation.value,
                "state": "queued",
            },
        }

    async def status(self, facility_id, ppu_id, *, site_id=None, job_id=None):
        if job_id is None:
            return {"ok": True, "sites": []}
        delay = self.status_delays.get(int(site_id or 0), 0.0)
        if delay:
            import asyncio

            await asyncio.sleep(delay)
        with self._lock:
            return {"ok": True, "job": dict(self.jobs[job_id])}

    async def cancel_job(self, facility_id, ppu_id, job_id):
        with self._lock:
            self.cancel_log.append((facility_id, ppu_id, job_id))
            job = self.jobs.get(job_id)
            if job is not None and job["state"] not in {"success", "failed", "error"}:
                job["state"] = "cancelled"
                job["result"] = {
                    "state": "cancelled",
                    "attempts": 1,
                    "retry_exhausted": False,
                    "attempt_history": [{"attempt": 1, "state": "cancelled"}],
                    "error": None,
                }
        return {"ok": True, "job": {"job_id": job_id, "cancel_requested": True}}

    def read_output_file(self, facility_id, ppu_id, job_id, filename):
        return b""


def make_asset(data: bytes = b"batch-image") -> ProgrammingAsset:
    digest = hashlib.sha256(data).hexdigest()
    return ProgrammingAsset.from_upload(
        name="batch.bin",
        asset_type="image",
        asset_format="binary",
        data=data,
        sha256=digest,
    )


class BatchRuntimeTests(unittest.TestCase):
    def wait_terminal(self, manager: BatchRuntimeManager, batch_id: str, timeout_s: float = 3.0):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            snapshot = manager.get(batch_id)
            if snapshot["state"] in {"success", "partial", "error", "cancelled"}:
                return snapshot
            time.sleep(0.01)
        self.fail(f"Batch {batch_id} did not reach a terminal state")

    def test_policy_rejects_invalid_values_and_threshold_above_site_count(self):
        with self.assertRaises(PlasmaError):
            BatchExecutionPolicy(repeat_count=0)
        with self.assertRaises(PlasmaError):
            BatchExecutionPolicy(site_retry_limit=-1)
        policy = BatchExecutionPolicy(failed_site_stop_threshold=3)
        with self.assertRaises(PlasmaError):
            policy.validate_target_count(2)

    def test_repeat_rounds_run_independently_and_aggregate_statistics(self):
        provider = FakeBatchProvider(status_delays={1: 0.03})
        manager = BatchRuntimeManager(provider, poll_interval_s=0.001)
        self.addCleanup(manager.close)
        targets = (
            BatchTarget("facility-1", "ppu-1", 1),
            BatchTarget("facility-1", "ppu-1", 2),
        )
        started = manager.create_batch(
            targets=targets,
            operations=["erase", "program", "verify"],
            policy=BatchExecutionPolicy(repeat_count=3, site_retry_limit=2),
            session_id="1" * 32,
            asset=make_asset(),
        )
        final = self.wait_terminal(manager, started["batch_id"])
        self.assertEqual(final["state"], "success")
        self.assertEqual(final["execution_policy"]["repeat_count"], 3)
        self.assertEqual(final["site_counts"]["success"], 2)
        self.assertTrue(all(site["completed_rounds"] == 3 for site in final["sites"]))
        self.assertEqual(final["operation_statistics"]["erase"]["logical_executions"], 6)
        self.assertEqual(final["operation_statistics"]["program"]["attempts"], 6)
        self.assertEqual(provider.cache_log[0][0:2], ("facility-1", "ppu-1"))
        self.assertEqual(len(provider.cache_log), 1)

        site1_round1_end_index = max(
            index
            for index, entry in enumerate(provider.start_log)
            if entry[2] == 1 and entry[4] == 1
        )
        site2_round2_start_index = next(
            index
            for index, entry in enumerate(provider.start_log)
            if entry[2] == 2 and entry[4] == 2
        )
        self.assertLess(site2_round2_start_index, site1_round1_end_index + 2)

    def test_retry_exhaustion_faults_site_and_threshold_stops_batch_with_error(self):
        provider = FakeBatchProvider(fail_sites={1}, status_delays={2: 0.05})
        manager = BatchRuntimeManager(provider, poll_interval_s=0.001)
        self.addCleanup(manager.close)
        started = manager.create_batch(
            targets=(
                BatchTarget("facility-1", "ppu-1", 1),
                BatchTarget("facility-1", "ppu-1", 2),
            ),
            operations=["program"],
            policy=BatchExecutionPolicy(
                repeat_count=5,
                site_retry_limit=2,
                failed_site_stop_threshold=1,
            ),
            session_id="1" * 32,
            asset=make_asset(),
        )
        final = self.wait_terminal(manager, started["batch_id"])
        by_site = {site["site_id"]: site for site in final["sites"]}
        self.assertEqual(final["state"], "error")
        self.assertEqual(final["stop_reason"], "failed_site_threshold")
        self.assertEqual(final["faulted_site_count"], 1)
        self.assertEqual(final["error"]["error_code"], "BATCH_SITE_FAILURE_THRESHOLD_EXCEEDED")
        self.assertEqual(by_site[1]["state"], "faulted")
        self.assertEqual(by_site[1]["total_attempts"], 3)
        self.assertEqual(by_site[1]["retry_count"], 2)
        self.assertEqual(by_site[1]["faulted_round"], 1)
        self.assertEqual(by_site[1]["faulted_operation"], "program")
        self.assertEqual(by_site[1]["last_failure_source"], "injected")
        self.assertIn(by_site[2]["state"], {"success", "stopped"})

    def test_infrastructure_error_is_not_counted_as_faulted_site(self):
        provider = FakeBatchProvider(error_sites={1}, status_delays={2: 0.05})
        manager = BatchRuntimeManager(provider, poll_interval_s=0.001)
        self.addCleanup(manager.close)
        started = manager.create_batch(
            targets=(
                BatchTarget("facility-1", "ppu-1", 1),
                BatchTarget("facility-1", "ppu-1", 2),
            ),
            operations=["erase"],
            policy=BatchExecutionPolicy(repeat_count=2, failed_site_stop_threshold=2),
        )
        final = self.wait_terminal(manager, started["batch_id"])
        by_site = {site["site_id"]: site for site in final["sites"]}
        self.assertEqual(final["state"], "error")
        self.assertEqual(final["stop_reason"], "infrastructure_error")
        self.assertEqual(final["faulted_site_count"], 0)
        self.assertEqual(by_site[1]["state"], "error")
        self.assertEqual(by_site[1]["last_failure_source"], "infrastructure")


if __name__ == "__main__":
    unittest.main()
