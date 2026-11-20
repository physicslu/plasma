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
