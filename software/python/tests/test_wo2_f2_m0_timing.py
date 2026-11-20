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
    coordinator._site_block = lambda alias, site: None
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
    coordinator._site_block = lambda alias, site: None
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
