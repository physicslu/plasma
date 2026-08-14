from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plasma_core.enums import JobState, Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_interfaces.mock import MockActivityTracker, MockInterface
from plasma_server.channel_manager import ChannelManager

from tests.helpers import make_config


class UnsafeShutdownMock(MockInterface):
    async def safe_shutdown(self) -> None:
        raise RuntimeError("simulated safe shutdown failure")


class ChannelManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.managers: list[ChannelManager] = []

    async def asyncTearDown(self) -> None:
        for manager in reversed(self.managers):
            await manager.shutdown()

    async def create_manager(self, **options: object) -> ChannelManager:
        manager = ChannelManager(make_config(self.root, **options))
        await manager.start()
        self.managers.append(manager)
        return manager

    async def test_dynamic_1_2_4_8_channel_status(self) -> None:
        for count in (1, 2, 4, 8):
            case_root = self.root / str(count)
            manager = ChannelManager(
                make_config(
                    case_root,
                    enabled_channels=count,
                    max_concurrent_jobs=count,
                )
            )
            await manager.start()
            status = manager.status()
            self.assertEqual(sum(item["enabled"] for item in status["channels"]), count)
            self.assertEqual(len(status["channels"]), 8)
            await manager.shutdown()

    async def test_eight_channels_execute_in_parallel(self) -> None:
        tracker = MockActivityTracker()
        config = make_config(
            self.root,
            enabled_channels=8,
            max_concurrent_jobs=8,
            channel_options={
                channel_id: {"mock": {"default_delay_s": 0.02}}
                for channel_id in range(8)
            },
        )
        manager = ChannelManager(config, mock_tracker=tracker)
        await manager.start()
        self.managers.append(manager)
        results = await asyncio.gather(
            *(
                manager.submit(
                    JobRequest(
                        channel_id=channel_id,
                        operation=Operation.PROGRAM,
                        firmware=bytes([channel_id]) * 32,
                    )
                )
                for channel_id in range(8)
            )
        )
        self.assertTrue(all(result.success for result in results))
        self.assertEqual(tracker.maximum, 8)

    async def test_global_concurrency_limit_is_enforced(self) -> None:
        tracker = MockActivityTracker()
        config = make_config(
            self.root,
            enabled_channels=8,
            max_concurrent_jobs=2,
            channel_options={
                channel_id: {"mock": {"default_delay_s": 0.01}}
                for channel_id in range(8)
            },
        )
        manager = ChannelManager(config, mock_tracker=tracker)
        await manager.start()
        self.managers.append(manager)
        await asyncio.gather(
            *(
                manager.submit(
                    JobRequest(channel_id=channel_id, operation=Operation.ERASE)
                )
                for channel_id in range(8)
            )
        )
        self.assertEqual(tracker.maximum, 2)

    async def test_failure_isolated_to_one_channel(self) -> None:
        manager = await self.create_manager(
            enabled_channels=2,
            channel_options={
                0: {
                    "mock": {
                        "failures": {"program": 1},
                        "failure_recoverable": False,
                        "default_delay_s": 0.01,
                    }
                },
                1: {"mock": {"default_delay_s": 0.01}},
            },
        )
        failed, succeeded = await asyncio.gather(
            manager.submit(JobRequest(channel_id=0, operation=Operation.PROGRAM, firmware=b"A" * 32)),
            manager.submit(JobRequest(channel_id=1, operation=Operation.PROGRAM, firmware=b"B" * 32)),
        )
        self.assertEqual(failed.state, JobState.FAILED)
        self.assertEqual(failed.error.error_code, ErrorCode.PROGRAM_FAILED.value)
        self.assertEqual(succeeded.state, JobState.SUCCESS)

    async def test_recoverable_failure_retries_and_succeeds(self) -> None:
        manager = await self.create_manager(
            enabled_channels=1,
            channel_options={0: {"mock": {"failures": {"program": 1}}}},
        )
        result = await manager.submit(
            JobRequest(
                channel_id=0,
                operation=Operation.PROGRAM,
                firmware=b"retry",
                max_retries=1,
            )
        )
        interface = manager.interfaces[0]
        self.assertIsInstance(interface, MockInterface)
        self.assertEqual(result.state, JobState.SUCCESS)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(interface.calls["program"], 2)

    async def test_timeout_has_structured_error(self) -> None:
        manager = await self.create_manager(
            enabled_channels=1,
            channel_options={0: {"mock": {"delays": {"erase": 0.2}}}},
        )
        result = await manager.submit(
            JobRequest(channel_id=0, operation=Operation.ERASE, timeout_s=0.02)
        )
        self.assertEqual(result.state, JobState.TIMEOUT)
        self.assertEqual(result.error.error_code, ErrorCode.OPERATION_TIMEOUT.value)
        jsonl_path = next((self.root / "logs").glob(f"*/CH0/{result.job_id}.jsonl"))
        events = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[-1]["event"], "job_timeout")
        self.assertEqual(events[-1]["level"], "ERROR")
        self.assertEqual(events[-1]["state"], JobState.TIMEOUT.value)

    async def test_running_job_can_be_cancelled(self) -> None:
        manager = await self.create_manager(
            enabled_channels=1,
            channel_options={0: {"mock": {"default_delay_s": 0.2}}},
        )
        request = JobRequest(channel_id=0, operation=Operation.ERASE)
        future = manager.enqueue(request)
        for _ in range(100):
            if manager.registry.get(request.job_id).state is JobState.RUNNING:
                break
            await asyncio.sleep(0.002)
        response = manager.cancel(request.job_id)
        result = await future
        self.assertTrue(response["accepted"])
        self.assertEqual(result.state, JobState.CANCELLED)
        self.assertEqual(result.error.error_code, ErrorCode.OPERATION_CANCELLED.value)
        jsonl_path = next((self.root / "logs").glob(f"*/CH0/{result.job_id}.jsonl"))
        events = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[-1]["event"], "job_cancelled")
        self.assertEqual(events[-1]["level"], "WARNING")
        self.assertEqual(events[-1]["state"], JobState.CANCELLED.value)

    async def test_job_waiting_for_global_slot_can_be_cancelled_immediately(self) -> None:
        manager = await self.create_manager(
            enabled_channels=2,
            max_concurrent_jobs=1,
            channel_options={
                0: {"mock": {"delays": {"erase": 0.5}}},
                1: {"mock": {"delays": {"erase": 0.5}}},
            },
        )
        first = JobRequest(channel_id=0, operation=Operation.ERASE, job_id="slot-holder")
        second = JobRequest(channel_id=1, operation=Operation.ERASE, job_id="slot-waiter")
        first_future = manager.enqueue(first)
        for _ in range(100):
            if manager.registry.get(first.job_id).state is JobState.RUNNING:
                break
            await asyncio.sleep(0.002)
        second_future = manager.enqueue(second)
        for _ in range(100):
            if manager.workers[1].current is not None:
                break
            await asyncio.sleep(0.002)
        manager.cancel(second.job_id)
        result = await asyncio.wait_for(asyncio.shield(second_future), timeout=0.15)
        self.assertEqual(result.state, JobState.CANCELLED)
        manager.cancel(first.job_id)
        await first_future

    async def test_safe_shutdown_failure_prevents_false_success(self) -> None:
        config = make_config(self.root, enabled_channels=1)
        manager = ChannelManager(config, interface_factory=lambda _channel: UnsafeShutdownMock())
        await manager.start()
        self.managers.append(manager)
        result = await manager.submit(
            JobRequest(channel_id=0, operation=Operation.ERASE, job_id="unsafe-shutdown")
        )
        self.assertEqual(result.state, JobState.FAILED)
        self.assertEqual(result.error.error_code, ErrorCode.INTERFACE_FAILURE.value)
        self.assertEqual(result.error.context["phase"], "safe_shutdown")

    async def test_manager_shutdown_cancels_running_and_queued_jobs(self) -> None:
        manager = await self.create_manager(
            enabled_channels=1,
            channel_options={0: {"mock": {"delays": {"erase": 0.2}}}},
        )
        running = JobRequest(channel_id=0, operation=Operation.ERASE, job_id="shutdown-running")
        queued = JobRequest(channel_id=0, operation=Operation.ERASE, job_id="shutdown-queued")
        running_future = manager.enqueue(running)
        queued_future = manager.enqueue(queued)
        for _ in range(100):
            if manager.registry.get(running.job_id).state is JobState.RUNNING:
                break
            await asyncio.sleep(0.002)
        await manager.shutdown()
        running_result, queued_result = await asyncio.gather(running_future, queued_future)
        self.assertEqual(running_result.state, JobState.CANCELLED)
        self.assertEqual(queued_result.state, JobState.CANCELLED)

    async def test_cancel_during_retry_backoff_prevents_next_attempt(self) -> None:
        manager = await self.create_manager(
            enabled_channels=1,
            channel_options={
                0: {
                    "mock": {"failures": {"program": 1}, "default_delay_s": 0.005},
                }
            },
        )
        request = JobRequest(
            channel_id=0,
            operation=Operation.PROGRAM,
            firmware=b"backoff-cancel",
            max_retries=1,
            retry_backoff_s=0.5,
        )
        future = manager.enqueue(request)
        interface = manager.interfaces[0]
        self.assertIsInstance(interface, MockInterface)
        runtime = manager.registry.get(request.job_id)
        for _ in range(200):
            if interface.calls["program"] == 1 and runtime.active_task is None:
                break
            await asyncio.sleep(0.005)
        else:
            self.fail("retry backoff was not reached")
        manager.cancel(request.job_id)
        result = await asyncio.wait_for(future, timeout=0.2)
        self.assertEqual(result.state, JobState.CANCELLED)
        self.assertEqual(interface.calls["program"], 1)

    async def test_disabled_and_unknown_channels_are_distinct(self) -> None:
        manager = await self.create_manager(enabled_channels=2)
        with self.assertRaises(PlasmaError) as disabled:
            manager.enqueue(JobRequest(channel_id=7, operation=Operation.ERASE))
        self.assertEqual(disabled.exception.code, ErrorCode.CHANNEL_DISABLED)
        with self.assertRaises(PlasmaError) as invalid:
            manager.enqueue(JobRequest(channel_id=9, operation=Operation.ERASE))
        self.assertEqual(invalid.exception.code, ErrorCode.CHANNEL_INVALID)

    async def test_duplicate_job_id_rejected(self) -> None:
        manager = await self.create_manager(enabled_channels=1)
        first = JobRequest(channel_id=0, operation=Operation.ERASE, job_id="fixed-job")
        await manager.submit(first)
        with self.assertRaises(PlasmaError) as duplicate:
            manager.enqueue(JobRequest(channel_id=0, operation=Operation.ERASE, job_id="fixed-job"))
        self.assertEqual(duplicate.exception.code, ErrorCode.DUPLICATE_JOB)

    async def test_path_like_job_id_is_rejected(self) -> None:
        with self.assertRaises(PlasmaError) as caught:
            JobRequest(channel_id=0, operation=Operation.ERASE, job_id="../escaped")
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_reserved_protocol_metadata_is_rejected(self) -> None:
        with self.assertRaises(PlasmaError) as caught:
            JobRequest(
                channel_id=0,
                operation=Operation.ERASE,
                metadata={"channel_id": 1},
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_read_section_filename_collision_is_rejected(self) -> None:
        manager = await self.create_manager(enabled_channels=1)
        result = await manager.submit(
            JobRequest(
                channel_id=0,
                operation=Operation.READ,
                map_data={
                    "sections": [
                        {"name": "config/a", "address": 0, "length": 1},
                        {"name": "config?a", "address": 1, "length": 1},
                    ]
                },
            )
        )
        self.assertEqual(result.state, JobState.FAILED)
        self.assertEqual(result.error.error_code, ErrorCode.INVALID_ARGUMENT.value)
        self.assertFalse(any((self.root / "output" / result.job_id).glob("read_*.bin")))

    async def test_program_then_read_writes_independent_binary_files(self) -> None:
        manager = await self.create_manager(enabled_channels=1)
        firmware = bytes(range(64))
        program = await manager.submit(
            JobRequest(channel_id=0, operation=Operation.PROGRAM, firmware=firmware)
        )
        self.assertTrue(program.success)
        read = await manager.submit(
            JobRequest(
                channel_id=0,
                operation=Operation.READ,
                map_data={
                    "sections": [
                        {"name": "section0", "address": 0, "length": 32},
                        {"name": "section1", "address": 32, "length": 32},
                    ]
                },
            )
        )
        self.assertEqual(read.state, JobState.SUCCESS)
        self.assertEqual(len(read.output_files), 2)
        self.assertEqual(Path(read.output_files[0]).read_bytes(), firmware[:32])
        self.assertEqual(Path(read.output_files[1]).read_bytes(), firmware[32:])
        self.assertNotEqual(Path(read.output_files[0]), Path(read.output_files[1]))

    async def test_verify_mismatch_is_reported(self) -> None:
        manager = await self.create_manager(enabled_channels=1)
        result = await manager.submit(
            JobRequest(channel_id=0, operation=Operation.VERIFY, firmware=b"not-erased")
        )
        self.assertEqual(result.state, JobState.FAILED)
        self.assertEqual(result.error.error_code, ErrorCode.VERIFY_FAILED.value)

    async def test_result_and_jsonl_logs_are_complete(self) -> None:
        manager = await self.create_manager(enabled_channels=1)
        result = await manager.submit(
            JobRequest(
                channel_id=0,
                operation=Operation.PROGRAM,
                firmware=b"logged",
                metadata={"firmware_name": "firmware.bin"},
            )
        )
        result_path = self.root / "output" / result.job_id / "result.json"
        saved = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["state"], "success")
        self.assertEqual(saved["firmware_name"], "firmware.bin")
        jsonl_path = next((self.root / "logs").glob(f"*/CH0/{result.job_id}.jsonl"))
        events = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
        event_names = {item["event"] for item in events}
        self.assertIn("job_started", event_names)
        self.assertIn("stage_completed", event_names)
        self.assertIn("job_completed", event_names)
        self.assertTrue(all(item["channel_id"] == 0 for item in events))

    async def test_restart_marks_incomplete_job_aborted(self) -> None:
        config = make_config(self.root, enabled_channels=1)
        manager = ChannelManager(config)
        manager.output.write_state(
            "orphan-job",
            {"job_id": "orphan-job", "channel_id": 0, "state": "running"},
        )
        recovered = await manager.start()
        self.managers.append(manager)
        self.assertEqual(recovered, ["orphan-job"])
        saved = json.loads(
            (self.root / "output" / "orphan-job" / "job_state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(saved["state"], "aborted")
        self.assertEqual(saved["error"]["error_code"], ErrorCode.JOB_ABORTED.value)

    async def test_full_channel_queue_is_rejected(self) -> None:
        manager = await self.create_manager(
            enabled_channels=1,
            queue_depth=1,
            channel_options={0: {"mock": {"default_delay_s": 0.2}}},
        )
        first = JobRequest(channel_id=0, operation=Operation.ERASE, job_id="queue-first")
        second = JobRequest(channel_id=0, operation=Operation.ERASE, job_id="queue-second")
        first_future = manager.enqueue(first)
        for _ in range(100):
            if manager.registry.get(first.job_id).state is JobState.RUNNING:
                break
            await asyncio.sleep(0.002)
        second_future = manager.enqueue(second)
        with self.assertRaises(PlasmaError) as busy:
            manager.enqueue(JobRequest(channel_id=0, operation=Operation.ERASE, job_id="queue-third"))
        self.assertEqual(busy.exception.code, ErrorCode.CHANNEL_BUSY)
        manager.cancel(first.job_id)
        manager.cancel(second.job_id)
        await asyncio.gather(first_future, second_future)

    async def test_log_write_failure_resolves_job_as_failed(self) -> None:
        manager = await self.create_manager(enabled_channels=1)
        with patch(
            "plasma_server.channel_worker.JobEventLogger.event",
            side_effect=OSError("simulated disk failure"),
        ):
            result = await manager.submit(
                JobRequest(channel_id=0, operation=Operation.ERASE, job_id="log-failure")
            )
        self.assertEqual(result.state, JobState.FAILED)
        self.assertEqual(result.error.error_code, ErrorCode.OUTPUT_WRITE_FAILED.value)
        follow_up = await manager.submit(
            JobRequest(channel_id=0, operation=Operation.ERASE, job_id="after-log-failure")
        )
        self.assertEqual(follow_up.state, JobState.SUCCESS)
