from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from plasma_core.config import PlasmaConfig, PPUConfig, ServerConfig, SiteConfig
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_server.site_manager import PPUExecutionLease, SiteManager
from plasma_server.runtime_control import RuntimeControlServer
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


def _asset_helper():
    source = Path(__file__).resolve().parents[3] / "scripts" / "ppu_asset_set.py"
    spec = importlib.util.spec_from_file_location("plasma_asset_quiesce_runtime_gate1", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_asset_set_cross_process_held_lease_blocks_new_jobs_until_socket_eof(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = SiteManager(config(tmp_path))
        await manager.start()
        directory = tmp_path / "runtime-control"
        directory.mkdir(mode=0o700)
        socket_path = directory / "control.sock"
        control = RuntimeControlServer(manager, socket_path)
        await control.start()
        acquired = threading.Event()
        released = threading.Event()
        helper = _asset_helper()
        def installer_operation():
            with helper.held_runtime_asset_lease(socket_path) as lease:
                assert lease["ppu_id"] == "ppu-a"
                assert lease["active_job_count"] == 0
                acquired.set()
                assert released.wait(timeout=4)
        worker = None
        try:
            worker = asyncio.create_task(asyncio.to_thread(installer_operation))
            for _ in range(120):
                if acquired.is_set():
                    break
                await asyncio.sleep(0.01)
            assert acquired.is_set(), "Runtime must grant a held lease"
            request = JobRequest(site_id=1, operation=Operation.READ, job_id="asset-lock-1")
            with pytest.raises(PlasmaError) as error:
                manager.enqueue(request)
            assert error.value.code is ErrorCode.PPU_BUSY
            assert manager.runtime_quiesce_snapshot()["active"] is True
            # No TTL should expire while the owner holds its socket.
            assert manager.runtime_quiesce_snapshot()["ttl_remaining_s"] is None
            released.set()
            await asyncio.wait_for(worker, timeout=4)
            for _ in range(120):
                if not manager.runtime_quiesce_snapshot()["active"]:
                    break
                await asyncio.sleep(0.01)
            assert manager.runtime_quiesce_snapshot()["active"] is False
            assert manager.execution_lease_snapshot()["busy"] is False
        finally:
            released.set()
            if worker is not None:
                await worker
            await control.close()
            await manager.shutdown()
    asyncio.run(scenario())


def test_asset_set_runtime_socket_rejects_busy_ppu_then_does_not_leak_lease(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = SiteManager(config(tmp_path))
        await manager.start()
        directory = tmp_path / "runtime-control"
        directory.mkdir(mode=0o700)
        socket_path = directory / "control.sock"
        control = RuntimeControlServer(manager, socket_path)
        await control.start()
        helper = _asset_helper()
        try:
            with manager._execution_lock:
                manager._execution_lease = PPUExecutionLease(
                    owner_kind="batch", owner_id="active-batch",
                    job_ids={"job-queued", "job-cancelling"},
                )
            def try_client():
                with helper.held_runtime_asset_lease(socket_path):
                    pytest.fail("busy runtime must reject Asset Set switch")
            with pytest.raises(helper.AssetSetError, match="ASSET_SET_QUIESCE_NOT_GRANTED"):
                await asyncio.to_thread(try_client)
            assert manager.runtime_quiesce_snapshot()["active"] is False
            with manager._execution_lock:
                manager._execution_lease = None
            # Explicit restart quiesce and Asset Set hold are mutually exclusive.
            ttl = manager.acquire_runtime_quiesce(2)
            with pytest.raises(helper.AssetSetError, match="ASSET_SET_QUIESCE_NOT_GRANTED"):
                await asyncio.to_thread(try_client)
            manager.release_runtime_quiesce(ttl["token"])
            assert manager.runtime_quiesce_snapshot()["active"] is False
        finally:
            with manager._execution_lock:
                manager._execution_lease = None
            await control.close()
            await manager.shutdown()
    asyncio.run(scenario())


def test_p1_coordinator_integrates_real_runtime_socket_with_atomic_asset_set(tmp_path: Path) -> None:
    """Host-only end-to-end B3 staged Set -> real UDS lease -> Active identity."""
    from .test_ppu_b3_z2_install_gate1 import (
        b3_request, build_generic_assets, make_coordinator,
    )

    async def scenario() -> None:
        archive, sha = build_generic_assets(tmp_path / "asset-archive")
        coordinator = make_coordinator(tmp_path)
        b3 = coordinator.execute_bundle_v3_install(b3_request(archive, sha))
        assert b3["stage"] == "bundle_install_only"
        assert not (coordinator.paths.product_root / "assets/active.json").exists()
        manager = SiteManager(config(tmp_path / "runtime"))
        await manager.start()
        directory = tmp_path / "runtime-control"
        directory.mkdir(mode=0o700)
        socket_path = directory / "control.sock"
        control = RuntimeControlServer(manager, socket_path)
        await control.start()
        helper = _asset_helper()
        try:
            def activate():
                return coordinator.activate_staged_asset_set(
                    sha, quiescence_lease=lambda: helper.held_runtime_asset_lease(socket_path),
                )
            receipt = await asyncio.wait_for(asyncio.to_thread(activate), timeout=10)
            assert receipt["result"] == "PASS" and receipt["stage"] == "asset_set_active"
            assert receipt["asset_set_sha256"] == sha
            assert receipt["fpga"] == "NOT_RUN" and receipt["ready"] is False
            verified = helper.read_active(coordinator.paths.product_root)
            assert verified["state"] == "ACTIVE" and verified["asset_set_sha256"] == sha
            for _ in range(100):
                if not manager.runtime_quiesce_snapshot()["active"]:
                    break
                await asyncio.sleep(0.01)
            assert manager.runtime_quiesce_snapshot()["active"] is False
        finally:
            await control.close()
            await manager.shutdown()
    asyncio.run(scenario())


def test_runtime_restart_quiesce_blocks_jobs_without_holding_a_connection(tmp_path: Path) -> None:
    """Runtime upgrade gate: TTL quiesce via the real control socket.

    It must be refused while execution is active, must block new Jobs once
    granted, and must leave no open connection (Python >= 3.12.1
    Server.wait_closed() waits for open connections, which would stall the
    Runtime's graceful shutdown during the upgrade restart).
    """
    async def scenario() -> None:
        manager = SiteManager(config(tmp_path))
        await manager.start()
        directory = tmp_path / "runtime-control"
        directory.mkdir(mode=0o700)
        socket_path = directory / "control.sock"
        control = RuntimeControlServer(manager, socket_path)
        await control.start()
        helper = _asset_helper()
        try:
            with manager._execution_lock:
                manager._execution_lease = PPUExecutionLease(
                    owner_kind="batch", owner_id="active-batch", job_ids={"job-running"},
                )
            with pytest.raises(helper.AssetSetError, match="RUNTIME_RESTART_QUIESCE_NOT_GRANTED"):
                await asyncio.to_thread(helper.quiesce_runtime_for_restart, socket_path)
            assert manager.runtime_quiesce_snapshot()["active"] is False
            with manager._execution_lock:
                manager._execution_lease = None

            granted = await asyncio.to_thread(helper.quiesce_runtime_for_restart, socket_path)
            assert granted["ttl_s"] == helper.RUNTIME_RESTART_QUIESCE_TTL_S
            assert manager.runtime_quiesce_snapshot()["active"] is True
            with pytest.raises(PlasmaError) as error:
                manager.enqueue(JobRequest(site_id=1, operation=Operation.READ, job_id="upgrade-1"))
            assert error.value.code is ErrorCode.PPU_BUSY
            # No connection is left open: graceful close completes promptly.
            await asyncio.wait_for(control.close(), timeout=2)
        finally:
            await control.close()
            await manager.shutdown()
    asyncio.run(scenario())
