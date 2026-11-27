from __future__ import annotations

import asyncio
import importlib.util
import subprocess
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
from plasma_core.protocol import Frame, PROTOCOL_VERSION
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import PPUExecutionLease, SiteManager
from plasma_server.time_sync import ChronyTimeSync
from plasma_server.runtime_control import RuntimeControlServer
from plasma_web.runtime_activation import RuntimeActivationError, SiteRuntimeActivationController, desired_runtime_revision
from plasma_web.runtime_activation_helper import RuntimeActivationExecutor, RuntimeActivationHelperError
from tests.helpers import make_config


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


def _tracking(offset: float, *, leap: str = "Normal", dispersion: float = .001) -> str:
    direction = "fast" if offset >= 0 else "slow"
    return ("Reference ID    : 12345678 (time.example)\n"
            "Stratum         : 3\n"
            f"System time     : {abs(offset):.9f} seconds {direction} of NTP time\n"
            f"Root dispersion : {dispersion:.9f} seconds\n"
            f"Leap status     : {leap}\n")


@pytest.mark.parametrize("before,after,status,commands", [
    (.001, None, "SYNCED", ["tracking"]),
    (.250, .002, "CORRECTED", ["tracking", "makestep", "tracking"]),
    (.250, .240, "FAILED", ["tracking", "makestep", "tracking"]),
])
def test_chrony_immediate_step_requires_post_verification(before, after, status, commands):
    calls = []
    observations = iter([_tracking(before)] + ([_tracking(after)] if after is not None else []))
    def runner(args, **kwargs):
        calls.append(args[-1])
        assert args[:2] == ["chronyc", "-n"] and kwargs["timeout"] > 0
        return subprocess.CompletedProcess(args, 0,
                                           "" if args[-1] == "makestep" else next(observations), "")
    result = ChronyTimeSync(runner=runner).execute(ppu_id="ppu-a")
    assert result["status"] == status and calls == commands
    assert result["adjustment_performed"] is (after is not None)
    assert result["before_offset_ms"] == before * 1000
    if after is not None:
        assert result["after_offset_ms"] == after * 1000


@pytest.mark.parametrize("fault,status", [
    (FileNotFoundError(), "UNSUPPORTED"),
    (PermissionError(), "FAILED"),
    (subprocess.TimeoutExpired(["chronyc"], 1), "TIMEOUT"),
    (RuntimeError("failed"), "FAILED"),
])
def test_chrony_failures_are_warnings_without_host_clock_write(fault, status):
    def runner(*_args, **_kwargs):
        raise fault
    result = ChronyTimeSync(runner=runner).execute(ppu_id="ppu-a")
    assert result["status"] == status
    assert result["adjustment_performed"] is False
    assert result["before_offset_ms"] is None


@pytest.mark.parametrize("observation", [
    _tracking(.001, leap="Not synchronised"),
    _tracking(.001, dispersion=.2),
    _tracking(.001).replace("12345678", "00000000"),
])
def test_untrusted_chrony_source_never_steps(observation):
    calls = []
    def runner(args, **_kwargs):
        calls.append(args[-1])
        return subprocess.CompletedProcess(args, 0, observation, "")
    result = ChronyTimeSync(runner=runner).execute(ppu_id="ppu-a")
    assert result["status"] == "UNTRUSTED_SOURCE"
    assert calls == ["tracking"]


def test_time_sync_reuses_execution_lock_reservation_and_quiesce(tmp_path: Path):
    manager, _identity, expected = _m3_manager(tmp_path)
    calls = []
    manager._time_sync.execute = lambda **kwargs: calls.append(kwargs) or {
        "ppu_id": "ppu-a", "status": "SYNCED", "warning_code": None,
        "adjustment_performed": False}
    def sync(owner="batch-1", token=None):
        return manager.pre_start_time_sync(owner_id=owner, token=token,
                                           threshold_ms=100, budget_ms=1000)
    lease = manager.acquire_runtime_quiesce(2)
    assert sync()["status"] == "SKIPPED_BUSY"
    manager.release_runtime_quiesce(lease["token"])
    reservation = manager.resource_reservation("acquire", owner_id="batch-1",
                                               expected=expected)
    token = reservation["token"]
    assert sync("other", token)["status"] == "SKIPPED_BUSY"
    assert sync("batch-1", "wrong")["status"] == "SKIPPED_BUSY"
    assert sync("batch-1", token)["status"] == "SYNCED"
    manager._execution_lease = PPUExecutionLease("rest_client", "batch-1", {"job-1"})
    assert sync("batch-1", token)["status"] == "SKIPPED_BUSY"
    manager._execution_lease = None
    assert len(calls) == 1
    assert manager.resource_reservation("release", owner_id="batch-1",
                                        token=token)["state"] == "RELEASED"


def test_time_sync_holds_admission_lock_through_clock_operation(tmp_path: Path):
    manager = SiteManager(config(tmp_path))
    entered, release, acquired = threading.Event(), threading.Event(), threading.Event()
    def clock(**_kwargs):
        entered.set()
        assert release.wait(2)
        return {"status": "SYNCED", "warning_code": None,
                "adjustment_performed": False}
    manager._time_sync.execute = clock
    first = threading.Thread(target=lambda: manager.pre_start_time_sync(
        owner_id="run-1", token=None, threshold_ms=100, budget_ms=1000))
    second = threading.Thread(target=lambda: (manager.acquire_runtime_quiesce(2), acquired.set()))
    first.start()
    assert entered.wait(2)
    second.start()
    assert not acquired.wait(.02)
    release.set()
    first.join(2)
    second.join(2)
    assert acquired.is_set()


@pytest.mark.parametrize("worker", [
    None,
    {"sessions": [{"job_id": "external"}], "sealed_sites": [],
     "admission_record_sites": [], "not_ready": None},
    {"sessions": [], "sealed_sites": [1], "admission_record_sites": [], "not_ready": None},
    {"sessions": [], "sealed_sites": [], "admission_record_sites": [1], "not_ready": None},
])
def test_root_site_worker_ownership_prevents_clock_step(tmp_path: Path, worker):
    manager = SiteManager(config(tmp_path))
    manager._site_worker_status_reader = lambda: worker
    manager._time_sync.execute = lambda **_kwargs: pytest.fail("clock adjusted while Root unverified")
    result = manager.pre_start_time_sync(owner_id="run-1", token=None,
                                         threshold_ms=100, budget_ms=1000)
    assert result["status"] == "SKIPPED_BUSY"
    assert result["elapsed_ms"] > 0


def test_idle_root_site_worker_allows_bounded_clock_check(tmp_path: Path):
    manager = SiteManager(config(tmp_path))
    manager._site_worker_status_reader = lambda: {
        "sessions": [], "sealed_sites": [], "admission_record_sites": [],
        "not_ready": None}
    manager._time_sync.execute = lambda **_kwargs: {
        "status": "SYNCED", "warning_code": None, "adjustment_performed": False}
    assert manager.pre_start_time_sync(owner_id="run-1", token=None,
                                       threshold_ms=100, budget_ms=1000)["status"] == "SYNCED"


def test_time_sync_protocol_rejects_supplied_time_and_shell(tmp_path: Path):
    manager = SiteManager(config(tmp_path))
    calls = []
    manager._time_sync.execute = lambda **kwargs: calls.append(kwargs) or {
        "ppu_id": "ppu-a", "status": "SYNCED", "warning_code": None,
        "adjustment_performed": False}
    server = PlasmaServer(manager.config, manager)
    request = {"protocol_version": PROTOCOL_VERSION,
               "message_type": "pre_start_time_sync", "owner_id": "run-1",
               "token": None, "threshold_ms": 100, "budget_ms": 1000}
    async def scenario():
        for extra in ({"timestamp": "2026-01-01T00:00:00Z"},
                      {"command": "date -s now"}):
            with pytest.raises(PlasmaError) as denied:
                await server._dispatch(Frame(metadata={**request, **extra}), None)
            assert denied.value.code is ErrorCode.INVALID_ARGUMENT
        accepted = await server._dispatch(Frame(metadata=request), None)
        assert accepted.metadata["status"] == "SYNCED"
    asyncio.run(scenario())
    assert len(calls) == 1


# --- WO-2 F2 M3 Batch Resource Reservation (PPU authority) ---------------
# Real SiteManager + Mock ``operations[]`` Jobs (their evidence carries
# ``safe_off``). Hazard outcomes are injected as this PPU's own terminal Job
# results; TTL is expired by moving the monotonic deadline (no sleeps).

def _m3_manager(tmp_path: Path, sites=(1, 2), root: str = "out"):
    from plasma_server import mock_resources
    from .test_mock_programming_operations import mock_config
    cfg = mock_config(tmp_path, site_ids=sites)
    cfg.server.output_root = tmp_path / root
    manager = SiteManager(cfg)
    identity = mock_resources.install_mock_resources(manager)
    expected = {"ppu_id": manager.config.ppu.id,
                "asset_set_sha256": identity["asset_set_sha256"],
                "generation": identity["generation"],
                "resource_set_sha256": identity["resource_set_sha256"]}
    return manager, identity, expected


def _m3_job(identity, site, owner="batch-1", token=None):
    from dataclasses import replace
    from .test_mock_programming_operations import IMAGE_A, programming_request
    request = programming_request(identity, ("erase", "program", "verify"), IMAGE_A,
                                  site_id=site)
    metadata = {**request.metadata, "execution_owner_kind": "rest_client",
                "execution_owner_id": owner}
    if token is not None:
        metadata["resource_reservation_token"] = token
    return replace(request, metadata=metadata)


def _m3_safety(job_id, kind):
    denied = kind == "transport_denied"
    return {"schema": "plasma.ppu.site-safety.v1",
            "class": "PRE_HARDWARE_DENIED" if denied else "FAILED_SAFE_OFF_VERIFIED",
            "job_id": job_id, "session_id": "s" * 32, "site": 1, "operation": "programming",
            "stage": "run", "code": "ADMISSION_DENIED:X" if denied else "VERIFY",
            "hardware_touched": not denied, "safe_off": None if denied else True}


def _m3_outcome(manager, job_id, kind, *, active=False):
    """Record ``job_id`` as a reserved Job of this PPU with a given outcome."""
    from types import SimpleNamespace
    from plasma_core.enums import JobState
    from plasma_core.models import ErrorDetail, JobResult
    details, context, state, attempt = {}, None, JobState.FAILED, 1
    if kind == "pass_safe":
        details, state = {"programming": {"result": "PASS", "safe_off": True}}, JobState.SUCCESS
    elif kind == "pass_no_evidence":
        state = JobState.SUCCESS
    elif kind == "fail_safe":
        context = {"site_worker_result": {"result": "FAIL", "safe_off": True}}
    elif kind == "fail_safe_off_false":
        context = {"safe_off": False}
    elif kind in ("transport_denied", "operation_failed_safe", "site_sealed"):
        code = {"transport_denied": "TRANSPORT_DENIED:ADMISSION_DENIED:X",
                "operation_failed_safe": "OPERATION_FAILED_SAFE:VERIFY",
                "site_sealed": "OUTCOME_UNKNOWN_SITE_SEALED:X"}[kind]
        context = {"site_worker_code": code, "outcome_unknown": kind == "site_sealed",
                   "site_worker_stage": "run", "job_id": job_id, "site_id": 1,
                   "operation": "programming"}
        if kind != "site_sealed":
            # The Worker's structured statement (ppu_site_worker._safety).
            context["site_worker_safety"] = _m3_safety(job_id, kind)
    elif kind.startswith("safety_"):
        # Structured evidence that does NOT match this Job: never a proof.
        context = {"site_worker_code": "TRANSPORT_DENIED:ADMISSION_DENIED:X",
                   "outcome_unknown": False, "site_worker_stage": "run",
                   "job_id": job_id, "site_id": 1, "operation": "programming",
                   "site_worker_safety": _m3_safety(job_id, "transport_denied")}
        mutate = {"safety_code_only": lambda c: c.pop("site_worker_safety"),
                  "safety_other_job": lambda c: c["site_worker_safety"].update(job_id="job-other"),
                  "safety_other_site": lambda c: c["site_worker_safety"].update(site=2),
                  "safety_open_stage": lambda c: c.update(site_worker_stage="open"),
                  "safety_class_mismatch": lambda c: c["site_worker_safety"].update(
                      **{"class": "FAILED_SAFE_OFF_VERIFIED"}),
                  "safety_touched": lambda c: c["site_worker_safety"].update(hardware_touched=True),
                  "safety_unknown": lambda c: c.update(outcome_unknown=True)}[kind]
        mutate(context)
    elif kind == "outcome_unknown":
        context = {"site_worker_result": {"safe_off": True}, "outcome_unknown": True}
    elif kind == "cancelled_before_start":
        state, attempt = JobState.CANCELLED, 0
    error = (ErrorDetail(error_code="E", error_type="T", message="m", recoverable=False,
                         context=context) if context is not None else None)
    result = JobResult(job_id=job_id, site_id=1, operation=Operation.PROGRAMMING,
                       state=state, error=error, details=details)
    manager.registry._jobs[job_id] = SimpleNamespace(
        state=JobState.RUNNING if active else state,
        result=None if active else result, attempt=attempt)
    manager._reservation["job_ids"].add(job_id)
    if active:
        lease = manager._execution_lease or PPUExecutionLease("rest_client", "batch-1")
        lease.job_ids.add(job_id)
        manager._execution_lease = lease


def _m3_logged_reasons(manager) -> list[tuple[str, str]]:
    import re
    return re.findall(r"(ppu_resource_reservation_\w+) .*?reason='(\w+)'",
                      manager.server_log.path.read_text())


def _m3_b3_refused(manager) -> bool:
    try:
        lease = manager.acquire_asset_set_quiesce()
    except PlasmaError as exc:
        assert exc.code is ErrorCode.PPU_BUSY
        return True
    manager.release_runtime_quiesce(lease["token"])
    return False


def test_batch_reservation_spans_idle_cycles_and_releases_only_with_ppu_safe_off(tmp_path: Path) -> None:
    """P1-9 / P1-7 / P1-12: real Jobs, safe release, identity anomaly, recovery, re-acquire."""
    async def scenario() -> None:
        manager, identity, expected = _m3_manager(tmp_path)
        await manager.start()
        try:
            with pytest.raises(PlasmaError) as malformed:
                manager.resource_reservation("acquire", owner_id="batch-1",
                                             expected={**expected, "generation": True})
            assert malformed.value.code is ErrorCode.INVALID_ARGUMENT
            reservation = manager.resource_reservation("acquire", owner_id="batch-1",
                                                       expected=expected)
            token = reservation["token"]
            assert reservation["epoch"] and reservation["state"] == "ACTIVE"
            assert _m3_b3_refused(manager)  # no Job active: still reserved
            with pytest.raises(PlasmaError) as foreign:
                manager.enqueue(_m3_job(identity, 1, owner="batch-2"))
            assert foreign.value.code is ErrorCode.PPU_BUSY
            first = manager.enqueue(_m3_job(identity, 1, token=token))
            second = manager.enqueue(_m3_job(identity, 2, token=token))
            with pytest.raises(PlasmaError, match="active Jobs"):
                manager.resource_reservation("release", owner_id="batch-1", token=token)
            assert {(await first).state.value, (await second).state.value} == {"success"}
            assert _m3_b3_refused(manager)  # Batch idle between Cycles
            third = await manager.enqueue(_m3_job(identity, 1, token=token))  # same owner, next Cycle
            assert third.state.value == "success"
            assert manager.resource_reservation("check", owner_id="batch-1",
                                                token=token)["epoch"] == reservation["epoch"]
            assert manager.resource_reservation(
                "release", owner_id="batch-1", token=token)["state"] == "RELEASED"
            assert not (tmp_path / "out" / "ppu-resource-reservation.json").exists()
            assert not _m3_b3_refused(manager)

            # P1-7: identity anomaly under a Reservation isolates the PPU.
            second_res = manager.resource_reservation("acquire", owner_id="batch-1",
                                                      expected=expected)
            resolver = manager._active_resource_resolver
            manager._active_resource_resolver = lambda: {**resolver(), "generation": 9}
            with pytest.raises(PlasmaError) as drift:
                manager.resource_reservation("check", owner_id="batch-1",
                                             token=second_res["token"])
            assert drift.value.code is ErrorCode.PPU_BUSY
            snap = manager.resource_reservation_snapshot()
            assert (snap["state"], snap["reason"]) == (
                "RECOVERY_REQUIRED", "RESERVED_RESOURCE_IDENTITY_CHANGED")
            manager._active_resource_resolver = resolver
            assert _m3_b3_refused(manager)
            with pytest.raises(PlasmaError):
                manager.resource_reservation("acquire", owner_id="batch-3", expected=expected)
            with pytest.raises(PlasmaError):
                manager.enqueue(_m3_job(identity, 1, owner="batch-3"))
            with pytest.raises(PlasmaError, match="no matching"):
                manager.recover_resource_reservation("0" * 32)
            # P1-12: explicit recovery, then a new Batch reserves again.
            assert manager.recover_resource_reservation(snap["recovery_id"])["state"] == "NONE"
            assert manager.resource_reservation(
                "acquire", owner_id="batch-3", expected=expected)["state"] == "ACTIVE"
        finally:
            await manager.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("kind,proven", [
    ("pass_safe", True), ("fail_safe", True), ("transport_denied", True),
    ("operation_failed_safe", True), ("cancelled_before_start", True),
    ("pass_no_evidence", False), ("fail_safe_off_false", False),
    ("site_sealed", False), ("outcome_unknown", False),
    # A refusal code alone, or a statement about another Job / Site / stage,
    # with a mismatched class, or under an unknown outcome proves nothing.
    ("safety_code_only", False), ("safety_other_job", False), ("safety_other_site", False),
    ("safety_open_stage", False), ("safety_class_mismatch", False),
    ("safety_touched", False), ("safety_unknown", False),
])
def test_safe_off_proof_comes_only_from_this_ppu_job_result(tmp_path: Path, kind, proven) -> None:
    manager, _identity, expected = _m3_manager(tmp_path)
    manager.resource_reservation("acquire", owner_id="batch-1", expected=expected)
    _m3_outcome(manager, "job-x", kind)
    assert manager._job_safe_off_proven("job-x") is proven
    assert manager._job_safe_off_proven("job-unknown-to-this-ppu") is False


def test_ttl_expiry_with_an_active_job_keeps_every_exclusion(tmp_path: Path) -> None:
    """P1-4: TTL ends the owner's claim only; B3, Package Actions and Jobs stay refused."""
    manager, identity, expected = _m3_manager(tmp_path)
    token = manager.resource_reservation("acquire", owner_id="batch-1", expected=expected)["token"]
    _m3_outcome(manager, "job-run", "pass_safe", active=True)
    manager._reservation["deadline"] = time.monotonic() - 1
    assert manager.resource_reservation_snapshot()["state"] == "EXPIRED"
    assert _m3_b3_refused(manager)
    with pytest.raises(PlasmaError, match="EXPIRED"):
        manager.resource_reservation("check", owner_id="batch-1", token=token)
    with pytest.raises(PlasmaError, match="EXPIRED"):
        manager._reserve_execution_job(_m3_job(identity, 1, token=token))
    with pytest.raises(PlasmaError, match="EXPIRED"):
        manager.resource_reservation("acquire", owner_id="batch-2", expected=expected)
    manager._started = True
    with pytest.raises(PlasmaError, match="EXPIRED"):
        with manager.package_action_scope("a" * 32):
            pass
    # The Job ends with SAFE_OFF proven by its own result: expiry settles safely.
    _m3_outcome(manager, "job-run", "pass_safe")
    manager._release_execution_job("job-run")
    assert manager.resource_reservation_snapshot()["state"] == "NONE"
    assert _m3_logged_reasons(manager) == [
        ("ppu_resource_reservation_released", "RESERVATION_EXPIRED_SAFE_OFF_PROVEN")]
    assert not _m3_b3_refused(manager)


@pytest.mark.parametrize("kind", ["fail_safe_off_false", "outcome_unknown", "site_sealed",
                                  "pass_no_evidence"])
def test_ttl_expiry_or_manager_crash_without_safe_off_requires_recovery(tmp_path: Path, kind) -> None:
    """P1-5 / P1-2: the Manager stops renewing (crash); TTL is not SAFE_OFF evidence."""
    manager, _identity, expected = _m3_manager(tmp_path)
    manager.resource_reservation("acquire", owner_id="batch-1", expected=expected)
    _m3_outcome(manager, "job-safe", "pass_safe")
    _m3_outcome(manager, "job-bad", kind)
    manager._reservation["deadline"] = time.monotonic() - 1
    snap = manager.resource_reservation_snapshot()
    assert snap["state"] == "RECOVERY_REQUIRED"
    assert snap["reason"] == "RESERVATION_EXPIRED_SAFE_OFF_NOT_PROVEN"
    assert snap["unproven_job_ids"] == ["job-bad"]
    assert _m3_b3_refused(manager)
    # A restarted Manager (new Batch owner) cannot take the PPU either.
    with pytest.raises(PlasmaError, match="RECOVERY_REQUIRED"):
        manager.resource_reservation("acquire", owner_id="batch-after-crash", expected=expected)
    # Durable: a Runtime restart keeps the isolation (new epoch, same reason).
    restarted, _, _ = _m3_manager(tmp_path)
    again = restarted.resource_reservation_snapshot()
    assert again["state"] == "RECOVERY_REQUIRED" and again["epoch"] != snap["epoch"]
    assert again["reason"] == snap["reason"] and again["unproven_job_ids"] == ["job-bad"]
    assert _m3_b3_refused(restarted)
    restarted.recover_resource_reservation(again["recovery_id"])
    assert not _m3_b3_refused(restarted)


def test_outcome_unknown_release_is_refused_and_isolates(tmp_path: Path) -> None:
    """P1-6: an owner Release cannot claim safety the PPU cannot prove."""
    manager, _identity, expected = _m3_manager(tmp_path)
    token = manager.resource_reservation("acquire", owner_id="batch-1", expected=expected)["token"]
    _m3_outcome(manager, "job-ok", "pass_safe")
    _m3_outcome(manager, "job-unknown", "outcome_unknown")
    with pytest.raises(PlasmaError, match="recovery required"):
        manager.resource_reservation("release", owner_id="batch-1", token=token)
    snap = manager.resource_reservation_snapshot()
    assert (snap["state"], snap["reason"], snap["unproven_job_ids"]) == (
        "RECOVERY_REQUIRED", "RELEASE_SAFE_OFF_NOT_PROVEN", ["job-unknown"])
    assert _m3_b3_refused(manager)
    # Recovery is refused while anything executes; it never claims SAFE_OFF.
    manager._execution_lease = PPUExecutionLease("rest_client", "batch-1", {"job-late"})
    with pytest.raises(PlasmaError, match="execution is active"):
        manager.recover_resource_reservation(snap["recovery_id"])
    manager._execution_lease = None
    manager.recover_resource_reservation(snap["recovery_id"])
    assert not _m3_b3_refused(manager)


def test_partial_fail_cancel_and_denial_still_release_when_each_site_is_safe(tmp_path: Path) -> None:
    """P1-8: one Site FAIL (SAFE_OFF verified), one refused pre-I/O, one cancelled before start."""
    manager, _identity, expected = _m3_manager(tmp_path)
    token = manager.resource_reservation("acquire", owner_id="batch-1", expected=expected)["token"]
    for job, kind in (("j-pass", "pass_safe"), ("j-fail", "fail_safe"),
                      ("j-denied", "transport_denied"), ("j-cancel", "cancelled_before_start")):
        _m3_outcome(manager, job, kind)
    assert manager.resource_reservation("release", owner_id="batch-1",
                                        token=token)["state"] == "RELEASED"
    # The log states the proof outcome (HIL 2026-11-20 logged NOT_PROVEN here).
    assert _m3_logged_reasons(manager) == [
        ("ppu_resource_reservation_released", "RELEASE_SAFE_OFF_PROVEN")]
    assert not _m3_b3_refused(manager)


@pytest.mark.parametrize("content", ["active", "corrupt"])
def test_runtime_restart_never_forgets_a_reservation(tmp_path: Path, content) -> None:
    """P1-3: epoch fencing plus a durable record; restart -> RECOVERY_REQUIRED."""
    manager, _identity, expected = _m3_manager(tmp_path)
    old = manager.resource_reservation("acquire", owner_id="batch-1", expected=expected)
    if content == "corrupt":
        (tmp_path / "out" / "ppu-resource-reservation.json").write_text("{not json")
    restarted, _, _ = _m3_manager(tmp_path)
    snap = restarted.resource_reservation_snapshot()
    assert snap["state"] == "RECOVERY_REQUIRED" and snap["epoch"] != old["epoch"]
    assert snap["reason"] == ("RUNTIME_RESTARTED" if content == "active"
                              else "RESERVATION_STATE_UNREADABLE")
    with pytest.raises(PlasmaError):
        restarted.resource_reservation("check", owner_id="batch-1", token=old["token"])
    assert _m3_b3_refused(restarted)
    assert "token" not in (tmp_path / "out" / "ppu-resource-reservation.json").read_text()
    restarted.recover_resource_reservation(snap["recovery_id"])
    assert restarted.resource_reservation(
        "acquire", owner_id="batch-2", expected=expected)["state"] == "ACTIVE"


def test_multiple_ppus_hold_independent_reservations(tmp_path: Path) -> None:
    """P1-1: each PPU is its own authority; isolation of one never blocks another."""
    a, _ia, ea = _m3_manager(tmp_path, root="ppu-a")
    b, _ib, eb = _m3_manager(tmp_path, root="ppu-b")
    ta = a.resource_reservation("acquire", owner_id="batch-1", expected=ea)["token"]
    tb = b.resource_reservation("acquire", owner_id="batch-1", expected=eb)["token"]
    assert ta != tb
    with pytest.raises(PlasmaError):
        a.resource_reservation("check", owner_id="batch-1", token=tb)
    _m3_outcome(a, "a-unknown", "outcome_unknown")
    with pytest.raises(PlasmaError):
        a.resource_reservation("release", owner_id="batch-1", token=ta)
    assert b.resource_reservation("release", owner_id="batch-1", token=tb)["state"] == "RELEASED"
    assert _m3_b3_refused(a) and not _m3_b3_refused(b)
    assert b.resource_reservation("acquire", owner_id="batch-2", expected=eb)["state"] == "ACTIVE"


def test_eight_sites_share_one_reservation_without_a_barrier(tmp_path: Path) -> None:
    """P1-11: 8 Site Jobs of one Batch are all admitted at once under one token."""
    async def scenario() -> None:
        manager, identity, expected = _m3_manager(tmp_path, sites=tuple(range(1, 9)))
        await manager.start()
        try:
            token = manager.resource_reservation("acquire", owner_id="batch-1",
                                                 expected=expected)["token"]
            futures = [manager.enqueue(_m3_job(identity, site, token=token))
                       for site in range(1, 9)]
            assert manager.execution_lease_snapshot()["active_job_count"] == 8
            results = await asyncio.gather(*futures)
            assert {result.state.value for result in results} == {"success"}
            assert len(manager._reservation["job_ids"]) == 8
            assert manager.resource_reservation("release", owner_id="batch-1",
                                                token=token)["state"] == "RELEASED"
        finally:
            await manager.shutdown()

    asyncio.run(scenario())


def test_eight_sites_share_one_batch_reservation_without_cycle_barrier(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = SiteManager(make_config(
            tmp_path, enabled_sites=8, max_concurrent_jobs=8,
            site_options={site: {"mock": {"default_delay_s": 0.15}}
                          for site in range(1, 9)}))
        manager._resolve_active_resources = lambda: {
            "asset_set_sha256": "a" * 64, "generation": 1,
            "resource_set_sha256": "b" * 64}
        await manager.start()
        try:
            reservation = manager.resource_reservation(
                "acquire", owner_id="batch-8",
                expected={"ppu_id": manager.config.ppu.id,
                          "asset_set_sha256": "a" * 64, "generation": 1,
                          "resource_set_sha256": "b" * 64})
            futures = [manager.enqueue(JobRequest(
                site_id=site, operation=Operation.READ, job_id=f"batch-site-{site}",
                metadata={"execution_owner_kind": "rest_client",
                          "execution_owner_id": "batch-8",
                          "resource_reservation_token": reservation["token"]}))
                       for site in range(1, 9)]
            assert manager.execution_lease_snapshot()["active_job_count"] == 8
            await asyncio.gather(*futures)
            assert manager.resource_reservation_snapshot()["state"] == "ACTIVE"
        finally:
            await manager.shutdown()

    asyncio.run(scenario())


def test_p4_asset_pin_uses_configured_runtime_root_not_host_path(tmp_path):
    from plasma_server.package_actions import PackageActionRuntime

    manager = SiteManager(config(tmp_path))
    assert manager._active_asset_set_reader is None
    product_root = tmp_path / "different-ppu-root"
    PackageActionRuntime(
        manager,
        control_plane=Path(__file__).resolve().parents[3] / "scripts",
        product_root=product_root,
        state_root=tmp_path / "state",
        owner_credential=None,
        spawner=object(),
        python_executable=Path(sys.executable),
    )
    assert manager._active_asset_set_reader is not None
    assert manager._active_asset_set_reader()["state"] == "EMPTY"


def test_p4_job_pins_active_identity_inside_ppu_lease(tmp_path):
    async def scenario():
        active = {"state": "ACTIVE", "asset_set_sha256": "a" * 64,
                  "generation": 3, "ready": False}
        manager = SiteManager(config(tmp_path), active_asset_set_reader=lambda: active)
        await manager.start()
        try:
            original = manager._active_asset_set_reader
            def read():
                assert manager.execution_lease_snapshot()["busy"] is True
                with pytest.raises(PlasmaError) as error:
                    manager.acquire_asset_set_quiesce()
                assert error.value.code is ErrorCode.PPU_BUSY
                return original()
            manager._active_asset_set_reader = read
            request = JobRequest(site_id=1, operation=Operation.READ, job_id="p4-pinned")
            future = manager.enqueue(request)
            runtime = manager.registry.get(request.job_id)
            active["asset_set_sha256"] = "b" * 64
            assert runtime.snapshot()["active_asset_set"]["asset_set_sha256"] == "a" * 64
            # Duplicate admission cannot release the original Job's lease.
            with pytest.raises(PlasmaError) as error:
                manager.enqueue(request)
            assert error.value.code is ErrorCode.DUPLICATE_JOB
            assert manager.execution_lease_snapshot()["busy"] is True
            await future
            await asyncio.sleep(0)
            assert manager.execution_lease_snapshot()["busy"] is False
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_p4_asset_read_failure_releases_job_reservation(tmp_path):
    async def scenario():
        def corrupt():
            raise RuntimeError("ASSET_SET_CORRUPT")
        manager = SiteManager(config(tmp_path), active_asset_set_reader=corrupt)
        await manager.start()
        try:
            with pytest.raises(RuntimeError, match="ASSET_SET_CORRUPT"):
                manager.enqueue(JobRequest(site_id=1, operation=Operation.READ, job_id="p4-denied"))
            assert manager.execution_lease_snapshot()["busy"] is False
            assert manager.registry.all() == []
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_p4_ppu_fence_covers_other_site_queue_and_cancellation(tmp_path):
    async def scenario():
        cfg = config(tmp_path)
        cfg.sites.append(SiteConfig(id=2, enabled=True, interface="mock", target="STM32F103C8T6"))
        manager = SiteManager(cfg)
        await manager.start()
        # Occupy the concurrency slot: both admitted Jobs stay queued.
        await manager._semaphore.acquire()
        try:
            requests = [JobRequest(site_id=site, operation=Operation.READ, job_id=f"p4-site-{site}",
                                   metadata={"execution_owner_kind": "batch", "execution_owner_id": "p4"})
                        for site in (1, 2)]
            futures = [manager.enqueue(request) for request in requests]
            manager.cancel(requests[0].job_id)
            with pytest.raises(PlasmaError) as error:
                manager.acquire_asset_set_quiesce()
            assert error.value.code is ErrorCode.PPU_BUSY
            assert manager.execution_lease_snapshot()["active_job_count"] == 2
            manager._semaphore.release()
            await asyncio.gather(*futures)
            await asyncio.sleep(0)
            lease = manager.acquire_asset_set_quiesce()
            manager.release_runtime_quiesce(lease["token"])
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


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


def test_b3_held_lease_refused_while_recovery_required_until_socket_recovery(tmp_path: Path) -> None:
    """B3 exclusion end to end: the real Bootstrap helper B3 uses cannot take
    the Runtime quiesce over an isolated PPU; only the local recovery op clears it."""
    import json
    import socket

    async def scenario() -> None:
        manager, _identity, expected = _m3_manager(tmp_path)
        await manager.start()
        directory = tmp_path / "runtime-control"
        directory.mkdir(mode=0o700)
        socket_path = directory / "control.sock"
        control = RuntimeControlServer(manager, socket_path)
        await control.start()
        helper = _asset_helper()

        def b3_hold() -> str:
            try:
                with helper.held_runtime_asset_lease(socket_path):
                    return "GRANTED"
            except helper.AssetSetError as exc:
                return str(exc)

        def control_call(request: dict) -> dict:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(str(socket_path))
                sock.sendall((json.dumps(request) + "\n").encode())
                return json.loads(sock.makefile().readline())

        try:
            token = manager.resource_reservation("acquire", owner_id="batch-1",
                                                 expected=expected)["token"]
            assert await asyncio.to_thread(b3_hold) == "ASSET_SET_QUIESCE_NOT_GRANTED"
            _m3_outcome(manager, "job-unknown", "outcome_unknown")
            with pytest.raises(PlasmaError):
                manager.resource_reservation("release", owner_id="batch-1", token=token)
            recovery_id = manager.resource_reservation_snapshot()["recovery_id"]
            assert await asyncio.to_thread(b3_hold) == "ASSET_SET_QUIESCE_NOT_GRANTED"
            stale = await asyncio.to_thread(control_call, {
                "operation": "recover_resource_reservation", "recovery_id": "f" * 32})
            assert stale["ok"] is False
            extra = await asyncio.to_thread(control_call, {
                "operation": "recover_resource_reservation", "recovery_id": recovery_id,
                "force": True})
            assert extra["ok"] is False
            done = await asyncio.to_thread(control_call, {
                "operation": "recover_resource_reservation", "recovery_id": recovery_id})
            assert done["ok"] is True and done["result"]["state"] == "NONE"
            assert await asyncio.to_thread(b3_hold) == "GRANTED"
        finally:
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
        assert b3["stage"] == "bundle_staged_only"
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


def _standalone_deployment_module(tmp_path: Path):
    """Load ppu-bootstrap-deployment.py ALONE, as the Z2 PS kit ships it
    (its scripts/ directory has no sibling helper modules)."""
    import shutil

    kit_scripts = tmp_path / "kit-scripts"
    kit_scripts.mkdir()
    target = kit_scripts / "ppu-bootstrap-deployment.py"
    shutil.copyfile(Path(__file__).resolve().parents[3] / "scripts" / "ppu-bootstrap-deployment.py", target)
    spec = importlib.util.spec_from_file_location("plasma_kit_standalone_deployment", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_restart_quiesce_blocks_jobs_without_holding_a_connection(tmp_path: Path) -> None:
    """Runtime upgrade gate, run from a kit-shaped standalone deployment module
    against the real Runtime control socket.

    It must be refused while execution is active, must block new Jobs once
    granted, and must leave no open connection (Python >= 3.12.1
    Server.wait_closed() waits for open connections, which would stall the
    Runtime's graceful shutdown during the upgrade restart).
    """
    deployment = _standalone_deployment_module(tmp_path)

    async def scenario() -> None:
        manager = SiteManager(config(tmp_path))
        await manager.start()
        directory = tmp_path / "runtime-control"
        directory.mkdir(mode=0o700)
        socket_path = directory / "control.sock"
        control = RuntimeControlServer(manager, socket_path)
        await control.start()
        try:
            with manager._execution_lock:
                manager._execution_lease = PPUExecutionLease(
                    owner_kind="batch", owner_id="active-batch", job_ids={"job-running"},
                )
            with pytest.raises(deployment.DeploymentError, match="RUNTIME_RESTART_QUIESCE_NOT_GRANTED"):
                await asyncio.to_thread(deployment.quiesce_runtime_for_restart, socket_path)
            assert manager.runtime_quiesce_snapshot()["active"] is False
            with manager._execution_lock:
                manager._execution_lease = None

            granted = await asyncio.to_thread(deployment.quiesce_runtime_for_restart, socket_path)
            assert granted["ttl_s"] == deployment.RUNTIME_RESTART_QUIESCE_TTL_S
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


# --- U8: the Batch Reservation pins one loaded FPGA identity -------------------------

FPGA = {"status": "IMAGE", "image_id": "z2-independent-swd-v5-d0add58c",
        "session_id": "fpga-931d", "boot_id": "4cef-boot", "firmware_sha256": "0d" * 32,
        "journal_sha256": "ab" * 32}


def test_the_first_reserved_job_pins_the_fpga_identity_and_later_jobs_match_it(tmp_path: Path) -> None:
    manager, _identity, expected = _m3_manager(tmp_path)
    manager.resource_reservation("acquire", owner_id="batch-1", expected=expected)
    manager._reservation["job_ids"].update({"job-1", "job-2"})
    manager._guard_reserved_fpga_identity("job-1", dict(FPGA))
    snap = manager.resource_reservation_snapshot()
    assert snap["state"] == "ACTIVE" and snap["fpga_image_id"] == FPGA["image_id"]
    # Same image; the Root journal digest alone (not part of the identity) may differ.
    manager._guard_reserved_fpga_identity("job-2", {**FPGA, "journal_sha256": "cd" * 32})
    assert manager.resource_reservation_snapshot()["state"] == "ACTIVE"


@pytest.mark.parametrize("change", ["status", "image_id", "session_id", "boot_id", "firmware_sha256"])
def test_a_changed_fpga_image_under_a_reservation_isolates_the_ppu(tmp_path: Path, change) -> None:
    manager, _identity, expected = _m3_manager(tmp_path)
    manager.resource_reservation("acquire", owner_id="batch-1", expected=expected)
    manager._reservation["job_ids"].update({"job-1", "job-2"})
    manager._guard_reserved_fpga_identity("job-1", dict(FPGA))
    with pytest.raises(PlasmaError, match="reserved FPGA identity changed"):
        manager._guard_reserved_fpga_identity("job-2", {**FPGA, change: "other"})
    snap = manager.resource_reservation_snapshot()
    assert snap["state"] == "RECOVERY_REQUIRED" and snap["reason"] == "RESERVED_FPGA_IDENTITY_CHANGED"
    assert _m3_b3_refused(manager)


def test_an_unverifiable_identity_never_pins_and_a_job_outside_the_reservation_is_untouched(tmp_path: Path) -> None:
    manager, _identity, expected = _m3_manager(tmp_path)
    manager.resource_reservation("acquire", owner_id="batch-1", expected=expected)
    manager._reservation["job_ids"].add("job-1")
    with pytest.raises(PlasmaError, match="RESERVED_FPGA_IDENTITY_UNVERIFIABLE"):
        manager._guard_reserved_fpga_identity("job-1", {**FPGA, "image_id": None})
    assert "fpga_identity" not in manager._reservation
    # Not this Reservation's Job (or no Reservation at all): nothing to pin.
    manager._guard_reserved_fpga_identity("job-foreign", dict(FPGA))
    assert "fpga_identity" not in manager._reservation
