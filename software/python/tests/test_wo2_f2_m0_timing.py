"""WO-2 F2 M0: host-only passive diagnostic behavior."""
import hashlib
import importlib.util
import json
from pathlib import Path

from plasma_manager.programming import _m0_timing as manager_timing
from plasma_server.site_manager import _m0_timing as ppu_timing


def _records(capsys):
    return [
        json.loads(line.removeprefix("PLASMA_M0 "))
        for line in capsys.readouterr().err.splitlines()
        if line.startswith("PLASMA_M0 ")
    ]


def test_m0_disabled_by_default(monkeypatch, capsys):
    monkeypatch.delenv("PLASMA_M0_TIMING", raising=False)
    manager_timing("manager_plan", batch_id="b")
    ppu_timing("ppu_enqueue", job_id="j")
    assert _records(capsys) == []


def test_m0_structured_local_duration_and_correlation(monkeypatch, capsys):
    monkeypatch.setenv("PLASMA_M0_TIMING", "1")
    manager_timing("manager_plan", batch_id="b", cycle_id="c",
                   site_id=1, duration_ms=12.5)
    ppu_timing("ppu_enqueue", job_id="j", site_id=1, duration_ms=8.5)
    records = _records(capsys)
    assert [r["event"] for r in records] == ["manager_plan", "ppu_enqueue"]
    assert records[0]["batch_id"] == "b" and records[0]["cycle_id"] == "c"
    assert records[1]["job_id"] == "j"
    assert all(type(r["monotonic_ns"]) is int and r["pid"] for r in records)


def test_m0_stderr_failure_never_blocks(monkeypatch):
    monkeypatch.setenv("PLASMA_M0_TIMING", "1")

    class BrokenOutput:
        def write(self, text):
            raise OSError("diagnostic failure")

    import sys
    monkeypatch.setattr(sys, "stderr", BrokenOutput())
    manager_timing("manager_plan", duration_ms=1)
    ppu_timing("ppu_enqueue", duration_ms=1)


def test_sha256_observation_preserves_digest(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("PLASMA_M0_TIMING", "1")
    script = Path(__file__).resolve().parents[3] / "scripts" / "ppu_asset_set.py"
    spec = importlib.util.spec_from_file_location("m0_asset_set", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = tmp_path / "example.bin"
    target.write_bytes(b"abc")
    assert module._digest(target) == hashlib.sha256(b"abc").hexdigest()
    records = _records(capsys)
    assert len(records) == 1 and records[0]["event"] == "ppu_asset_sha256"
    assert records[0]["bytes_hashed"] == 3 and records[0]["duration_ms"] >= 0


def test_admission_event_occurs_per_invocation(monkeypatch, capsys):
    import time
    from plasma_manager.programming_batch import ProgrammingBatchCoordinator
    monkeypatch.setenv("PLASMA_M0_TIMING", "1")
    coordinator = object.__new__(ProgrammingBatchCoordinator)
    coordinator.monotonic = time.monotonic
    coordinator._platform_block = lambda alias: None
    coordinator._site_block = lambda alias, site, **kw: None
    for _ in range(3):
        assert coordinator._admission_block("ppu", 1) is None
    events = _records(capsys)
    assert len(events) == 3
    assert all(x["event"] == "manager_admission" and x["site_id"] == 1
               and x["duration_ms"] >= 0 for x in events)


def test_disabled_admission_does_not_advance_fake_clock(monkeypatch, capsys):
    from plasma_manager.programming_batch import ProgrammingBatchCoordinator
    monkeypatch.delenv("PLASMA_M0_TIMING", raising=False)
    coordinator = object.__new__(ProgrammingBatchCoordinator)
    coordinator.monotonic = lambda: (_ for _ in ()).throw(AssertionError("clock advanced"))
    coordinator._platform_block = lambda alias: None
    coordinator._site_block = lambda alias, site, **kw: None
    assert coordinator._admission_block("ppu", 1) is None
    assert _records(capsys) == []


def test_site_status_records_resource_duration_without_changing_payload(monkeypatch, capsys):
    from types import SimpleNamespace
    import pytest
    from plasma_core.errors import PlasmaError
    from plasma_server.site_manager import SiteManager

    monkeypatch.setenv("PLASMA_M0_TIMING", "1")
    manager = object.__new__(SiteManager)
    manager._site_configs = {1: SimpleNamespace(enabled=True, interface="mock")}
    manager.workers = {}
    manager.ppu_snapshot = lambda: {"ppu_id": "ppu"}
    manager.active_resources_snapshot = lambda: {"state": "VERIFIED"}
    manager._latest_job_summary = lambda site: None
    result = manager.status(site_id=1)
    assert result["ppu"]["active_resources"] == {"state": "VERIFIED"}
    observations = _records(capsys)
    assert [event["event"] for event in observations] == [
        "ppu_site_resources", "ppu_site_status",
    ]
    assert observations[1]["duration_ms"] >= observations[0]["duration_ms"]
    with pytest.raises(PlasmaError):
        manager.status(site_id=2)  # No invented status for an invalid Site.


def test_m1_bootstrap_reads_have_duration_and_do_not_repeat(monkeypatch, capsys):
    import time
    import pytest
    from plasma_manager.programming import BundleProgrammingWorkflow

    workflow = object.__new__(BundleProgrammingWorkflow)
    workflow.monotonic = time.monotonic
    calls = []
    monkeypatch.setenv("PLASMA_M0_TIMING", "1")

    def read(alias):
        calls.append(alias)
        return {"state": "ACTIVE"}

    assert workflow._timed_bootstrap_read("z2", read, "assets") == {"state": "ACTIVE"}
    assert calls == ["z2"]
    record, = _records(capsys)
    assert record["event"] == "manager_bootstrap_read"
    assert record["operation"] == "assets" and record["ppu_alias"] == "z2"
    assert record["duration_ms"] >= 0

    def fail(alias):
        calls.append(alias)
        raise ValueError("Bootstrap unavailable")

    with pytest.raises(ValueError, match="Bootstrap unavailable"):
        workflow._timed_bootstrap_read("z2", fail, "status")
    record, = _records(capsys)
    assert record["event"] == "manager_bootstrap_read"
    assert record["operation"] == "status" and record["duration_ms"] >= 0
    assert calls == ["z2", "z2"]


def test_m1_readiness_2_gets_and_failure_remain_fail_closed(monkeypatch, capsys):
    import time
    import pytest
    from plasma_manager.programming import BundleProgrammingWorkflow, _StepFailure

    workflow = object.__new__(BundleProgrammingWorkflow)
    workflow.monotonic = time.monotonic
    paths = []
    health = {"ok": True, "execution": "ready"}
    status = {
        "ppu": {"ppu_id": "ppu", "execution": {"busy": False, "active_job_count": 0},
                "active_resources": {"state": "VERIFIED"}},
        "sites": [{"site_id": 1, "enabled": True, "state": "idle",
                   "current_job_id": None, "queued_jobs": 0, "interface": "mock"}],
    }

    def get(_client, path):
        paths.append(path)
        return health if path == "/api/health/ready" else status

    workflow._gateway_get = get
    monkeypatch.setenv("PLASMA_M0_TIMING", "1")
    ready = workflow._readiness(object(), 1, "mock")
    assert ready["ppu_id"] == "ppu" and ready["site_id"] == 1
    assert paths == ["/api/health/ready", "/api/status?site=1"]
    events = _records(capsys)
    assert [r["event"] for r in events] == [
        "manager_readiness_http", "manager_readiness_http", "manager_readiness"]
    assert [r["endpoint"] for r in events[:2]] == ["health_ready", "site_status"]
    assert all(r["duration_ms"] >= 0 for r in events)

    paths.clear()
    status["sites"][0]["state"] = "busy"
    with pytest.raises(_StepFailure, match="SITE_NOT_READY_OR_BUSY"):
        workflow._readiness(object(), 1, "mock")
    assert paths == ["/api/health/ready", "/api/status?site=1"]
    assert [r["event"] for r in _records(capsys)] == [
        "manager_readiness_http", "manager_readiness_http", "manager_readiness"]


def test_m1_observation_off_preserves_no_clock_reads(monkeypatch, capsys):
    from plasma_manager.programming import BundleProgrammingWorkflow

    workflow = object.__new__(BundleProgrammingWorkflow)
    workflow.monotonic = lambda: (_ for _ in ()).throw(AssertionError("clock advanced"))
    workflow._gateway_get = lambda _client, path: (
        {"ok": True, "execution": "ready"} if path == "/api/health/ready"
        else {"ppu": {"ppu_id": "ppu", "execution": {
            "busy": False, "active_job_count": 0}},
              "sites": [{"site_id": 1, "enabled": True, "state": "idle",
                         "current_job_id": None, "queued_jobs": 0, "interface": "mock"}]})
    monkeypatch.delenv("PLASMA_M0_TIMING", raising=False)
    assert workflow._timed_bootstrap_read("z2", lambda alias: {"alias": alias},
                                          "status") == {"alias": "z2"}
    assert workflow._readiness(object(), 1, "mock")["state"] == "idle"
    assert _records(capsys) == []


def test_m1_first_cycle_and_run_phases_carry_correlation(monkeypatch, capsys, tmp_path):
    from .test_programming_batch_repeat import Session

    monkeypatch.setenv("PLASMA_M0_TIMING", "1")
    session = Session(tmp_path, repeat=1)
    assert session.done()["outcome"] == "PASS"
    events = _records(capsys)
    initial = [r for r in events if r["event"] == "manager_initial_admission"]
    assert len(initial) == 1
    assert initial[0]["batch_id"] == session.batch_id
    assert initial[0]["cycle_id"] and initial[0]["site_id"] == 1
    assert initial[0]["platform_leader"] is True and initial[0]["duration_ms"] >= 0
    for name in ("manager_preflight", "manager_presubmit_readiness"):
        samples = [r for r in events if r["event"] == name]
        assert len(samples) == 1 and samples[0]["run_id"] and samples[0]["plan_id"]
        assert samples[0]["duration_ms"] >= 0
    assert any(r["event"] == "manager_bootstrap_read" for r in events)
