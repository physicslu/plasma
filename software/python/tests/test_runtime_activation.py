from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from plasma_core.config import PlasmaConfig, PPUConfig, ServerConfig, SiteConfig
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_server.site_manager import SiteManager
from plasma_web.runtime_activation import RuntimeActivationError, SiteRuntimeActivationController, desired_runtime_revision
from plasma_web.runtime_activation_helper import RuntimeActivationExecutor, RuntimeActivationHelperError


def config(tmp_path: Path) -> PlasmaConfig:
    return PlasmaConfig(
        ppu=PPUConfig(id="ppu-a", facility_id="lab", model="test", display_name="PPU A"),
        server=ServerConfig(
            host="127.0.0.1",
            port=9900,
            max_supported_sites=8,
            max_concurrent_jobs=1,
            max_queue_depth_per_site=16,
            output_root=tmp_path / "out",
            log_root=tmp_path / "log",
        ),
        sites=[SiteConfig(id=1, enabled=True, interface="mock", target="STM32F103C8T6")],
    )


def test_quiesce_gate_and_job_reservation_share_authoritative_lock(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = SiteManager(config(tmp_path))
        await manager.start()
        try:
            lease = manager.acquire_runtime_quiesce(2)
            assert lease["ppu_id"] == "ppu-a"
            request = JobRequest(site_id=1, operation=Operation.READ, job_id="job-quiesce-test")
            with pytest.raises(PlasmaError) as exc_info:
                manager.enqueue(request)
            assert exc_info.value.code is ErrorCode.PPU_BUSY
            manager.release_runtime_quiesce(lease["token"])
        finally:
            await manager.shutdown()

    asyncio.run(scenario())


def test_quiesce_is_bounded_and_expires(tmp_path: Path) -> None:
    manager = SiteManager(config(tmp_path))
    manager.acquire_runtime_quiesce(2)
    manager._runtime_quiesce._deadline_monotonic = time.monotonic() - 1
    assert manager.runtime_quiesce_snapshot()["active"] is False


def test_runtime_revision_is_order_independent() -> None:
    first = {"sites": [{"site_id": 2, "desired_revision": "sha256:" + "b" * 64}, {"site_id": 1, "desired_revision": "sha256:" + "a" * 64}]}
    second = {"sites": list(reversed(first["sites"]))}
    assert desired_runtime_revision(first) == desired_runtime_revision(second)


def test_activation_rejects_stale_revision_without_restart() -> None:
    configuration = {
        "source": "canonical_ppu_config",
        "runtime_apply_supported": True,
        "reconciliation": "restart_required",
        "sites": [{"site_id": 1, "desired_revision": "sha256:" + "a" * 64}],
    }
    calls: list[str] = []

    class Helper:
        def restart_server(self, **_: object) -> dict[str, object]:
            calls.append("restart")
            return {}

    controller = SiteRuntimeActivationController(
        Helper(),
        lambda: {"site_configuration": configuration},
        lambda: {"ppu": {"ppu_id": "ppu-a"}},
        lambda _: {"site_configuration": configuration},
    )
    with pytest.raises(RuntimeActivationError) as exc_info:
        controller.activate({"action": "activate", "expected_revision": "sha256:" + "f" * 64, "expected_ppu_id": "ppu-a"})
    assert "changed before runtime activation" in str(exc_info.value)
    assert calls == []


def test_activation_rejects_malformed_revision_before_restart() -> None:
    calls: list[str] = []

    class Helper:
        def restart_server(self, **_: object) -> dict[str, object]:
            calls.append("restart")
            return {}

    controller = SiteRuntimeActivationController(
        Helper(),
        lambda: {"site_configuration": {"reconciliation": "restart_required", "sites": []}},
        lambda: {"ppu": {"ppu_id": "ppu-a"}},
        lambda _: {"site_configuration": {"reconciliation": "in_sync", "sites": []}},
    )
    with pytest.raises(RuntimeActivationError) as exc_info:
        controller.activate({"action": "activate", "expected_revision": "sha256:abc", "expected_ppu_id": "ppu-a"})
    assert exc_info.value.http_status == 400
    assert calls == []


def test_activation_guard_covers_revision_check_restart_and_reconciliation() -> None:
    before = {
        "source": "canonical_ppu_config",
        "runtime_apply_supported": True,
        "reconciliation": "restart_required",
        "sites": [{"site_id": 1, "desired_revision": "sha256:" + "a" * 64}],
    }
    after = {**before, "reconciliation": "in_sync"}
    expected = desired_runtime_revision(before)
    guarded = False

    @contextmanager
    def guard():
        nonlocal guarded
        assert guarded is False
        guarded = True
        try:
            yield
        finally:
            guarded = False

    class Helper:
        def restart_server(self, **_: object) -> dict[str, object]:
            assert guarded is True
            return {"restarted_service": "plasma-server.service"}

    def desired_payload() -> dict[str, object]:
        assert guarded is True
        return {"site_configuration": before}

    def runtime_snapshot() -> dict[str, object]:
        assert guarded is True
        return {"ppu": {"ppu_id": "ppu-a"}}

    def reconcile(_: dict[str, object]) -> dict[str, object]:
        assert guarded is True
        return {"site_configuration": after}

    controller = SiteRuntimeActivationController(
        Helper(),
        desired_payload,
        runtime_snapshot,
        reconcile,
        activation_guard=guard,
    )
    result = controller.activate(
        {"action": "activate", "expected_revision": expected, "expected_ppu_id": "ppu-a"}
    )
    assert result["restarted"] is True
    assert result["state"] == "in_sync"
    assert guarded is False


def test_narrow_helper_does_not_accept_arbitrary_service(tmp_path: Path) -> None:
    executor = RuntimeActivationExecutor(tmp_path / "server.sock", restart_server=lambda: None)
    with pytest.raises(RuntimeActivationHelperError):
        executor.execute({
            "operation": "restart_server",
            "service": "ssh.service",
            "expected_ppu_id": "ppu-a",
            "quiesce_ttl_s": 20,
        })
