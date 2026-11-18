"""Per-Job stage timestamps (observation only) and event-loop offload.

Host-only. Timing never gates a Job: a failing sink is ignored, and Jobs
without a bound sink behave exactly as before.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from plasma_core import job_timing
from plasma_core.enums import JobState

from .test_mock_programming_operations import (
    IMAGE_A, SITE, mock_config, programming_request, started_manager,
)


def test_mark_without_a_bound_sink_is_a_no_op():
    job_timing.mark("anything", duration_ms=1.0)  # must not raise


def test_a_failing_sink_never_fails_the_caller():
    def broken(phase, **fields):
        raise OSError("log disk full")

    token = job_timing.bind(broken)
    try:
        with job_timing.span("step"):
            value = 7
    finally:
        job_timing.unbind(token)
    assert value == 7


def test_in_thread_records_duration_propagates_errors_and_frees_the_loop():
    records = []

    def blocking(seconds):
        time.sleep(seconds)
        return "done"

    def failing():
        raise ValueError("REFERENCE_DENIED")

    async def scenario():
        token = job_timing.bind(lambda phase, **f: records.append((phase, f)))
        try:
            ticks = 0

            async def ticker():
                nonlocal ticks
                while True:
                    ticks += 1
                    await asyncio.sleep(0.01)

            task = asyncio.create_task(ticker())
            assert await job_timing.in_thread("verify", blocking, 0.3) == "done"
            task.cancel()
            with pytest.raises(ValueError, match="REFERENCE_DENIED"):
                await job_timing.in_thread("denied", failing)
            return ticks
        finally:
            job_timing.unbind(token)

    ticks = asyncio.run(scenario())
    # The loop kept running while the blocking check was in a thread.
    assert ticks >= 10
    phases = dict(records)
    assert phases["verify"]["thread"] is True and phases["verify"]["duration_ms"] >= 250
    assert "denied" in phases


def _timing_events(log_root: Path, job_id: str) -> list[dict]:
    path = next(log_root.glob(f"*/SITE{SITE}/{job_id}.jsonl"))
    return [record for record in map(json.loads, path.read_text().splitlines())
            if record["event"] == "stage_timing"]


def test_job_log_records_admission_steps_and_queue_wait(tmp_path: Path):
    async def scenario():
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            request = programming_request(identity, ("erase", "program", "verify"), IMAGE_A)
            result = await manager.submit(request)
            assert result.state is JobState.SUCCESS, result.error
            return request.job_id
        finally:
            await manager.shutdown()

    job_id = asyncio.run(scenario())
    events = {record["phase"]: record for record in _timing_events(tmp_path / "log", job_id)}
    admission = events["job_admission"]
    for step in ("reserve_ms", "active_set_ms", "job_binding_ms", "route_admit_ms",
                 "write_state_ms"):
        assert type(admission[step]) is float and admission[step] >= 0
    assert events["queued"]["duration_ms"] >= 0
    assert all(type(record["t_ms"]) is float for record in events.values())
    server_log = next((tmp_path / "log").glob("*/server.log")).read_text()
    assert "admission_timing_ms=" in server_log


def test_timing_sink_is_scoped_to_its_job(tmp_path: Path):
    async def scenario():
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            first = programming_request(identity, ("erase", "program"), IMAGE_A)
            assert (await manager.submit(first)).state is JobState.SUCCESS
            second = programming_request(identity, ("verify",), IMAGE_A)
            assert (await manager.submit(second)).state is JobState.SUCCESS
            return first.job_id, second.job_id
        finally:
            await manager.shutdown()

    first, second = asyncio.run(scenario())
    assert job_timing._SINK.get() is None
    assert all(r["job_id"] == first for r in _timing_events(tmp_path / "log", first))
    assert all(r["job_id"] == second for r in _timing_events(tmp_path / "log", second))
