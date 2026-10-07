from __future__ import annotations

import asyncio
import os
import socket
from pathlib import Path

import pytest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_interfaces.openocd_worker import OpenOCDWorker


OPENOCD = os.environ.get("PLASMA_TEST_OPENOCD")
SCRIPTS = os.environ.get("PLASMA_TEST_OPENOCD_SCRIPTS")

pytestmark = pytest.mark.skipif(
    not OPENOCD or not SCRIPTS,
    reason="real OpenOCD runtime paths are not provided",
)


def _worker(site_id: int, **kwargs) -> OpenOCDWorker:
    assert OPENOCD and SCRIPTS
    options = {
        "startup_timeout_s": 5,
        "command_timeout_s": 2,
        **kwargs,
    }
    return OpenOCDWorker(
        site_id=site_id,
        executable=Path(OPENOCD),
        scripts_root=Path(SCRIPTS),
        **options,
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.mark.asyncio
async def test_real_openocd_rpc_timeout_crash_and_restart() -> None:
    worker = _worker(1)
    try:
        first = await worker.start()
        version = await worker.command("version")
        assert "Open On-Chip Debugger" in version

        invalid = await worker.command("plasma_command_that_does_not_exist")
        assert invalid.strip()
        assert "Open On-Chip Debugger" in await worker.command("version")

        with pytest.raises(PlasmaError) as timeout:
            await worker.command("sleep 1000", timeout_s=0.05)
        assert timeout.value.code == ErrorCode.OPERATION_TIMEOUT
        assert timeout.value.context["worker_recovery"].startswith("restarted:")
        assert worker.generation == first.generation + 1
        assert "Open On-Chip Debugger" in await worker.command("version")

        process = worker._process
        assert process is not None
        process.kill()
        await process.wait()
        with pytest.raises(PlasmaError) as crash:
            await worker.command("version")
        assert crash.value.code == ErrorCode.INTERFACE_FAILURE
        assert crash.value.context["worker_recovery"].startswith("restarted:")
        assert "Open On-Chip Debugger" in await worker.command("version")
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_real_openocd_port_collision_is_retried() -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen(1)
    occupied_port = int(occupied.getsockname()[1])
    fallback_port = _free_port()
    ports = iter((occupied_port, fallback_port))
    worker = _worker(
        2,
        port_allocator=lambda: next(ports),
        startup_timeout_s=1,
        max_start_attempts=2,
    )
    try:
        status = await worker.start()
        assert status.rpc_port == fallback_port
        assert "Open On-Chip Debugger" in await worker.command("version")
    finally:
        occupied.close()
        await worker.stop()


@pytest.mark.asyncio
async def test_real_openocd_eight_workers_isolate_one_site_failure() -> None:
    workers = [_worker(site_id) for site_id in range(1, 9)]
    try:
        statuses = await asyncio.gather(*(worker.start() for worker in workers))
        assert len({status.rpc_port for status in statuses}) == 8
        responses = await asyncio.gather(*(worker.command("version") for worker in workers))
        assert all("Open On-Chip Debugger" in response for response in responses)

        await workers[4].kill()
        remaining = await asyncio.gather(
            *(worker.command("version") for index, worker in enumerate(workers) if index != 4)
        )
        assert len(remaining) == 7
        assert all("Open On-Chip Debugger" in response for response in remaining)

        await workers[4].start()
        assert "Open On-Chip Debugger" in await workers[4].command("version")
    finally:
        await asyncio.gather(*(worker.stop() for worker in workers), return_exceptions=True)
