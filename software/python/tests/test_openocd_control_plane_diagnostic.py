from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web import openocd_control_plane as diagnostic


class FakeWorker:
    instances: list["FakeWorker"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.generation = 0
        self.running = False
        self.__class__.instances.append(self)

    async def start(self):
        self.generation += 1
        self.running = True
        return SimpleNamespace(
            generation=self.generation,
            pid=4321,
            rpc_port=45678,
            running=True,
        )

    async def command(self, command: str, *, timeout_s: float | None = None) -> str:
        assert command == "version"
        assert timeout_s is not None
        return "Open On-Chip Debugger 0.12.0"

    async def stop(self) -> None:
        self.running = False

    def status(self):
        return SimpleNamespace(running=self.running)


def _runtime(tmp_path: Path, *, hardware_runtime_ready: bool = False) -> Path:
    binary = tmp_path / "bin" / "openocd"
    binary.parent.mkdir()
    binary.write_text("fake\n", encoding="utf-8")
    binary.chmod(0o755)
    scripts = tmp_path / "share" / "openocd" / "scripts"
    scripts.mkdir(parents=True)
    evidence = {
        "result": "PASS",
        "runtime_id": "0.12.0-9ea7f3d647c8",
        "openocd_version": "0.12.0",
        "architecture": "armv7l",
        "binary": str(binary),
        "scripts_root": str(scripts),
        "hardware_runtime_ready": hardware_runtime_ready,
    }
    path = tmp_path / "openocd-runtime.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return path


def _snapshot() -> dict:
    return {
        "ok": True,
        "ppu": {"ppu_id": "ppu-a", "facility_id": "lab"},
        "sites": [{"site_id": 1}, {"site_id": 2}],
    }


@pytest.mark.asyncio
async def test_control_plane_probe_uses_fixed_version_command_and_stops_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeWorker.instances.clear()
    monkeypatch.setattr(diagnostic, "OpenOCDWorker", FakeWorker)

    result = await diagnostic.execute_openocd_control_plane(
        {"site_id": 2, "timeout_ms": 5000},
        _snapshot(),
        evidence_path=_runtime(tmp_path),
    )

    assert result["result"] == "PASS"
    assert result["site_id"] == 2
    assert result["openocd_version"] == "0.12.0"
    assert result["tcl_rpc_state"] == "pass"
    assert result["rpc_scope"] == "loopback"
    assert result["process_state"] == "stopped"
    assert result["probe_process_state"] == "running"
    assert result["execution_capability"] == "openocd-control-plane-only"
    assert result["hardware_runtime_ready"] is False
    assert FakeWorker.instances[-1].running is False
    assert FakeWorker.instances[-1].kwargs["site_id"] == 2


@pytest.mark.asyncio
async def test_control_plane_request_rejects_arbitrary_tcl_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diagnostic, "OpenOCDWorker", FakeWorker)
    with pytest.raises(PlasmaError) as caught:
        await diagnostic.execute_openocd_control_plane(
            {"site_id": 1, "timeout_ms": 5000, "command": "shutdown"},
            _snapshot(),
            evidence_path=_runtime(tmp_path),
        )
    assert caught.value.code == ErrorCode.INVALID_ARGUMENT
    assert "unexpected fields" in caught.value.message


@pytest.mark.asyncio
async def test_control_plane_request_rejects_unknown_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diagnostic, "OpenOCDWorker", FakeWorker)
    with pytest.raises(PlasmaError) as caught:
        await diagnostic.execute_openocd_control_plane(
            {"site_id": 8, "timeout_ms": 5000},
            _snapshot(),
            evidence_path=_runtime(tmp_path),
        )
    assert caught.value.code == ErrorCode.SITE_INVALID


@pytest.mark.asyncio
async def test_control_plane_requires_closed_hardware_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diagnostic, "OpenOCDWorker", FakeWorker)
    with pytest.raises(PlasmaError) as caught:
        await diagnostic.execute_openocd_control_plane(
            {"site_id": 1, "timeout_ms": 5000},
            _snapshot(),
            evidence_path=_runtime(tmp_path, hardware_runtime_ready=True),
        )
    assert caught.value.code == ErrorCode.CONFIG_INVALID
