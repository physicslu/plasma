"""Host-only: Console-driven Bundle programming via Manager (fake PPU / fake Provider).

No real PPU, Bootstrap, FPGA or DUT. Fakes model the existing Manager Bootstrap
coordinator and the PPU Gateway REST contract closely enough to exercise every
decision the Manager workflow makes.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import ppu_unified_deployment  # noqa: E402

from plasma_manager.programming import (  # noqa: E402
    ACK_TOKEN,
    CONFIRM_TOKEN,
    BundleProgrammingWorkflow,
    ProgrammingError,
)
from plasma_manager.server import PPUOperationGate  # noqa: E402
from plasma_opf import bundle_v3  # noqa: E402

ROUTES = ROOT / "data/opf/programming-routes"
V01 = ROOT / "docs/evidence/bluepill-z2-flash-2026-10-27/firmware/plasma-blue-pill-cdc.bin"
ALIAS = "z2"
ICPN = "STM32F103C8T6"


class FakeCoordinator:
    def __init__(self, *, active_sha=None, paired=True, b3_final="succeeded",
                 b3_raises=False, status_raises_after_b3=False):
        self.active_sha = active_sha
        self.paired = paired
        self.b3_final = b3_final
        self.b3_raises = b3_raises
        self.status_raises_after_b3 = status_raises_after_b3
        self.calls: list[str] = []
        self.uploaded = bytearray()
        self.upload_sha = None
        self.deployment = None
        self.b3_body = None

    def status(self, alias):
        self.calls.append("status")
        if self.status_raises_after_b3 and self.b3_body is not None:
            raise TimeoutError("bootstrap status timed out")
        return {"ok": True, "pairing": {"paired": self.paired, "device_match": True},
                "bootstrap": {"runtime": {"state": "runtime_active"},
                              "deployment": self.deployment}}

    def assets(self, alias):
        self.calls.append("assets")
        if self.active_sha is None:
            return {"schema": "plasma.ppu.active-assets.v1", "state": "EMPTY",
                    "asset_set_sha256": None, "ready": False}
        return {"schema": "plasma.ppu.active-assets.v1", "state": "ACTIVE",
                "asset_set_sha256": self.active_sha, "ready": False}

    def create_upload(self, alias, body):
        self.calls.append("B1_create")
        self.upload_sha = body["sha256"]
        return 201, {"upload": {"upload_id": "a" * 32, "state": "open"}}

    def append_chunk(self, alias, upload_id, body):
        self.calls.append("B1_chunk")
        part = base64.b64decode(body["data_base64"])
        assert body["offset"] == len(self.uploaded)
        assert hashlib.sha256(part).hexdigest() == body["sha256"]
        self.uploaded.extend(part)
        return 200, {"upload": {"upload_id": upload_id, "received_bytes": len(self.uploaded)}}

    def commit_upload(self, alias, upload_id):
        self.calls.append("B1_commit")
        digest = hashlib.sha256(bytes(self.uploaded)).hexdigest()
        return 200, {"upload": {"upload_id": upload_id, "state": "committed", "sha256": digest}}

    def start_deployment(self, alias, body):
        if "mode" not in body:
            self.calls.append("B2")
            assert set(body) == {"kind", "upload_id", "archive_sha256"}
            return 202, {"deployment": {"transaction_id": "b" * 32, "state": "admitted"}}
        self.calls.append("B3")
        assert body["mode"] == "activate" and body["fpga_load"] is False
        assert body["admission_transaction_id"] == "b" * 32
        self.b3_body = body
        if self.b3_raises:
            raise TimeoutError("B3 response lost")
        tx = "c" * 32
        self.deployment = {"transaction_id": tx, "state": self.b3_final,
                           "result": {"result": "PASS"} if self.b3_final == "succeeded" else None}
        if self.b3_final == "succeeded":
            self.active_sha = body["archive_sha256"]
        return 202, {"deployment": {"transaction_id": tx, "state": "queued"}}


ROUTE_RESOURCE_SHA = bundle_v3.resource_set_sha256(bundle_v3.resource_set_descriptor(
    bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6.json")))


class FakeGateway:
    """PPU Gateway fake. ``coordinator`` is the PPU's Active Set; the fake PPU
    reports the Resource identity it would derive (``resource_for``) and echoes
    the Binding it accepted, as the OFE-1B SiteManager does."""

    def __init__(self, *, image: bytes, safe_off=True, readback_ok=True,
                 post_status=202, post_raises=False, busy=False, job_final="success",
                 status_target=ICPN, coordinator=None, resource_for=None,
                 resources_state=None, status_raises=False, echo=True, ppu_id="z2-hil"):
        self.image = image
        self.coordinator = coordinator
        self.resource_for = resource_for or (lambda _active: ROUTE_RESOURCE_SHA)
        self.resources_state = resources_state
        self.status_raises = status_raises
        self.echo = echo  # True, False (no echo) or a dict of tampered echo fields
        self.ppu_id = ppu_id
        self.safe_off = safe_off
        self.readback_ok = readback_ok
        self.post_status = post_status
        self.post_raises = post_raises
        self.busy = busy
        self.job_final = job_final
        self.status_target = status_target
        self.posts: list[dict] = []
        self.polls = 0

    def _resp(self, status, payload):
        return status, {"Content-Type": "application/json"}, json.dumps(payload).encode()

    def relay(self, method, path, *, headers, body, timeout_s, max_response_bytes):
        if method == "GET" and path == "/api/health/ready":
            return self._resp(200, {"ok": True, "execution": "ready"})
        if method == "GET" and path.startswith("/api/status?site="):
            if self.status_raises:
                raise TimeoutError("status read lost")
            return self._resp(200, {
                "ppu": {"ppu_id": self.ppu_id,
                        "execution": {"busy": self.busy, "active_job_count": 0},
                        "runtime_activation": {"active": False},
                        "active_resources": self._resources()},
                "sites": [{"site_id": int(path.rsplit("=", 1)[1]), "enabled": True,
                           "state": "idle", "current_job_id": None, "queued_jobs": 0,
                           "interface": "openocd", "target": self.status_target}]})
        if method == "POST" and path == "/api/jobs":
            self.posts.append(json.loads(body))
            if self.post_raises:
                raise TimeoutError("job POST response lost")
            return self._resp(self.post_status, {"ok": True, "job": {
                "job_id": "job-20261109-120000-0123abcd", "state": "queued"}})
        if method == "GET" and path.startswith("/api/status?job="):
            self.polls += 1
            post = self.posts[-1]
            sent = base64.b64decode(post["asset_base64"]) if "asset_base64" in post else self.image
            sha = hashlib.sha256(sent).hexdigest()
            state = "running" if self.polls == 1 else self.job_final
            binding = post["job_binding"]
            echo = None
            if self.echo:
                echo = {"job_binding_sha256": bundle_v3.sha256_hex(bundle_v3.canonical_json(binding)),
                        **{k: binding[k] for k in ("resource_set_sha256", "image_asset_sha256",
                                                   "operation", "range", "ppu_id", "site_id")},
                        "asset_set_sha256": self.coordinator.active_sha, "generation": 1}
                if isinstance(self.echo, dict):
                    echo.update(self.echo)
            return self._resp(200, {"job": {
                "job_id": "job-20261109-120000-0123abcd", "state": state, "site_id": 2,
                "operation": post["operation"], "stage": "verify", "progress_percent": 50,
                "job_binding": echo,
                "result": {"state": state, "image_sha256": sha, "image_size": len(sent),
                           "attempts": 1, "elapsed_ms": 10000, "error": None,
                           "details": {"flash_cycle": {
                               "result": "PASS" if state == "success" else "FAIL",
                               "readback_sha256": sha if self.readback_ok else "0" * 64,
                               "bytes_verified": len(self.image),
                               "safe_off": self.safe_off}}}}})
        raise AssertionError(f"unexpected Gateway call {method} {path}")

    def _resources(self):
        if self.resources_state is not None:
            return self.resources_state
        active = self.coordinator.active_sha if self.coordinator else None
        if active is None:
            return {"state": "UNAVAILABLE", "reason": "ASSET_SET_RESOURCE_NOT_ACTIVE"}
        return {"state": "VERIFIED", "asset_set_sha256": active, "generation": 1,
                "resource_set_sha256": self.resource_for(active)}


class FakeRegistry:
    def __init__(self, lifecycle="commissioned"):
        self.lifecycle = lifecycle

    def record_by_alias(self, alias):
        if alias != ALIAS:
            return None
        return SimpleNamespace(alias=ALIAS, endpoint="http://192.0.2.10:18080",
                               lifecycle=self.lifecycle)


def image() -> bytes:
    return V01.read_bytes()


def make(tmp_path, *, coordinator=None, gateway=None, registry=None, journal=True):
    coordinator = coordinator or FakeCoordinator()
    gateway = gateway or FakeGateway(image=image())
    if gateway.coordinator is None:
        gateway.coordinator = coordinator
    workflow = BundleProgrammingWorkflow(
        coordinator=coordinator, registry=registry or FakeRegistry(),
        gateway_client_factory=lambda endpoint, timeout: gateway,
        gate=PPUOperationGate(), request_timeout_s=5.0, routes_root=ROUTES,
        journal_path=(tmp_path / "runs.json") if journal else None,
        sleep=lambda _s: None, spawn=lambda target: target(), poll_interval_s=0.0)
    return workflow, coordinator, gateway


def plan_body(raw: bytes | None = None, site: int = 2, icpn: str = ICPN,
              operation: str = "flash_cycle"):
    raw = image() if raw is None else raw
    return {"icpn": icpn, "site_id": site, "operation": operation,
            "image_base64": base64.b64encode(raw).decode(), "image_filename": "app.bin"}


def run_once(workflow):
    planned = workflow.plan(ALIAS, plan_body())["plan"]
    started = workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    return planned, workflow.run_status(ALIAS, started["run"]["run_id"])["run"]


def test_shared_writer_reproduces_historical_bundle_a_bytes():
    route = bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6.json")
    built = bundle_v3.build_image_bundle(
        route, image(), image_filename="plasma-blue-pill-cdc.bin",
        asset_package_id="bluepill-cdc-fw-v01", bundle_name="bluepill-site2-fw-v01")
    assert built.archive_sha256 == "71e9a044c7f45d0f6e608c2727961f6ada220b483225bd20b928bf06f289946a"


def test_user_bundle_is_canonical_and_verifiable(tmp_path):
    route = bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6.json")
    built = bundle_v3.build_user_image_bundle(route, image(), filename="../evil name.bin")
    again = bundle_v3.build_user_image_bundle(route, image(), filename="../evil name.bin")
    assert built.archive == again.archive
    assert built.image_filename == "image.bin"
    path = tmp_path / "user.zip"
    path.write_bytes(built.archive)
    verified = ppu_unified_deployment.verify_host_only_bundle(
        path, expected_sha256=built.archive_sha256, target_profile=route.target)
    assert [p.kind for p in verified.packages] == [
        "platform-provider", "programming-profile", "firmware-asset"]


def test_success_with_activation_runs_b1_b2_b3_then_one_flash_cycle(tmp_path):
    workflow, coord, gateway = make(tmp_path)
    planned, run = run_once(workflow)
    assert planned["activation_required"] is True
    assert planned["catalog_gate"] == "NOT_USED"
    assert run["outcome"] == "PASS", run
    assert coord.calls.count("B2") == 1 and coord.calls.count("B3") == 1
    assert bytes(coord.uploaded) and coord.upload_sha == planned["bundle"]["archive_sha256"]
    assert len(gateway.posts) == 1 and run["job_submission_count"] == 1
    post = gateway.posts[0]
    assert post["operation"] == "flash_cycle" and post["site_id"] == 2
    # Job Image source: Binding + Image Asset; never the Bundle reference.
    assert not {"asset_set_sha256", "asset_package_id", "bundle_asset_sha256"} & set(post)
    assert post["job_binding"] == planned["job_binding"]
    assert post["image_asset"]["sha256"] == hashlib.sha256(image()).hexdigest()
    assert base64.b64decode(post["asset_base64"]) == image()
    receipt = run["receipt"]
    assert receipt["readback_sha256"] == receipt["expected_image_sha256"] \
        == receipt["observed_image_sha256"]
    assert receipt["bytes_verified"] == len(image()) and receipt["safe_off"] is True
    assert receipt["resource_reuse"] is False
    assert [s["step"] for s in run["steps"]] == [
        "PREFLIGHT", "B1_UPLOAD", "B2_ADMIT", "B3_SUBMIT", "B3_ACTIVATE",
        "FLASH_CYCLE_SUBMIT", "VERIFY_RECEIPT"]
    # journal is durable and holds no image/bundle bytes
    journal = (tmp_path / "runs.json").read_text()
    assert run["run_id"] in journal and base64.b64encode(image()[:64]).decode() not in journal


def test_already_active_skips_b1_b2_b3(tmp_path):
    route = bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6.json")
    sha = bundle_v3.build_user_image_bundle(route, image(), filename="app.bin").archive_sha256
    workflow, coord, gateway = make(tmp_path, coordinator=FakeCoordinator(active_sha=sha))
    planned, run = run_once(workflow)
    assert planned["activation_required"] is False
    assert run["outcome"] == "PASS"
    assert not {"B1_create", "B2", "B3"} & set(coord.calls)
    assert len(gateway.posts) == 1
    assert [s["step"] for s in run["steps"]] == [
        "PREFLIGHT", "RESOURCE_REUSE", "FLASH_CYCLE_SUBMIT", "VERIFY_RECEIPT"]


@pytest.mark.parametrize("body, code", [
    (plan_body(icpn="STM32F407VGT6"), "programming_route_not_found"),
    (plan_body(site=1), "programming_route_not_found"),
    (plan_body(raw=b"\x00" * (65536 + 1)), "bundle_incompatible"),
])
def test_incompatible_selection_never_touches_ppu(tmp_path, body, code):
    workflow, coord, gateway = make(tmp_path)
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, body)
    assert caught.value.code == code
    assert coord.calls == [] and gateway.posts == []


def test_missing_or_consumed_plan_is_bundle_missing(tmp_path):
    workflow, _coord, gateway = make(tmp_path)
    with pytest.raises(ProgrammingError) as caught:
        workflow.start(ALIAS, {"plan_id": "f" * 32, "confirm": CONFIRM_TOKEN})
    assert caught.value.code == "programming_plan_not_found"
    planned = workflow.plan(ALIAS, plan_body())["plan"]
    workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    with pytest.raises(ProgrammingError) as again:  # duplicate submit of the same plan
        workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    assert again.value.code == "programming_plan_not_found"
    assert len(gateway.posts) == 1


def test_duplicate_run_while_in_progress_is_rejected(tmp_path):
    pending: list = []
    workflow, _coord, gateway = make(tmp_path)
    workflow.spawn = pending.append  # hold the first run before it executes
    first = workflow.plan(ALIAS, plan_body())["plan"]
    second = workflow.plan(ALIAS, plan_body())["plan"]
    workflow.start(ALIAS, {"plan_id": first["plan_id"], "confirm": CONFIRM_TOKEN})
    with pytest.raises(ProgrammingError) as caught:
        workflow.start(ALIAS, {"plan_id": second["plan_id"], "confirm": CONFIRM_TOKEN})
    assert caught.value.code == "programming_run_in_progress"
    pending[0]()
    assert len(gateway.posts) == 1


def test_confirmation_is_mandatory(tmp_path):
    workflow, _coord, gateway = make(tmp_path)
    planned = workflow.plan(ALIAS, plan_body())["plan"]
    with pytest.raises(ProgrammingError) as caught:
        workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": "yes"})
    assert caught.value.code == "confirmation_required" and gateway.posts == []


def test_job_post_timeout_is_outcome_unknown_and_latches_without_retry(tmp_path):
    gateway = FakeGateway(image=image(), post_raises=True)
    workflow, _coord, _ = make(tmp_path, gateway=gateway)
    _planned, run = run_once(workflow)
    assert run["outcome"] == "OUTCOME_UNKNOWN"
    assert run["reason"] == "JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT"
    assert len(gateway.posts) == 1
    planned = workflow.plan(ALIAS, plan_body())["plan"]
    with pytest.raises(ProgrammingError) as caught:
        workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    assert caught.value.code == "programming_outcome_unknown_unresolved"
    assert len(gateway.posts) == 1
    workflow.acknowledge(ALIAS, run["run_id"], {"acknowledge": ACK_TOKEN})
    gateway.post_raises = False
    workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    assert len(gateway.posts) == 2  # only after explicit operator acknowledgement


def test_b3_outcome_unknown_never_submits_job(tmp_path):
    coord = FakeCoordinator(b3_raises=True)
    workflow, _c, gateway = make(tmp_path, coordinator=coord)
    _planned, run = run_once(workflow)
    assert run["outcome"] == "OUTCOME_UNKNOWN"
    assert run["reason"] == "B3_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT"
    assert coord.calls.count("B3") == 1 and gateway.posts == []


def test_b3_status_timeout_is_outcome_unknown(tmp_path):
    coord = FakeCoordinator(status_raises_after_b3=True)
    workflow, _c, gateway = make(tmp_path, coordinator=coord)
    _planned, run = run_once(workflow)
    assert run["outcome"] == "OUTCOME_UNKNOWN" and gateway.posts == []


def test_b3_failed_is_definitive_failure_without_job(tmp_path):
    coord = FakeCoordinator(b3_final="failed")
    workflow, _c, gateway = make(tmp_path, coordinator=coord)
    _planned, run = run_once(workflow)
    assert run["outcome"] == "FAIL" and run["reason"] == "B3_FAILED" and gateway.posts == []


def test_safe_off_failure_is_reported_as_distinct_fail(tmp_path):
    gateway = FakeGateway(image=image(), safe_off=False, job_final="failed")
    workflow, _c, _ = make(tmp_path, gateway=gateway)
    _planned, run = run_once(workflow)
    assert run["outcome"] == "FAIL" and run["reason"] == "SAFE_OFF_NOT_VERIFIED"
    assert run["receipt"]["safe_off"] is False and len(gateway.posts) == 1


def test_readback_mismatch_fails(tmp_path):
    gateway = FakeGateway(image=image(), readback_ok=False)
    workflow, _c, _ = make(tmp_path, gateway=gateway)
    _planned, run = run_once(workflow)
    assert run["outcome"] == "FAIL" and run["reason"] == "READBACK_SHA256_MISMATCH"


def test_job_rejected_by_ppu_is_definitive_fail(tmp_path):
    gateway = FakeGateway(image=image(), post_status=409)
    workflow, _c, _ = make(tmp_path, gateway=gateway)
    _planned, run = run_once(workflow)
    assert run["outcome"] == "FAIL" and run["reason"] == "JOB_SUBMISSION_REJECTED_HTTP_409"


def test_busy_site_blocks_before_any_write(tmp_path):
    gateway = FakeGateway(image=image(), busy=True)
    workflow, coord, _ = make(tmp_path, gateway=gateway)
    _planned, run = run_once(workflow)
    assert run["outcome"] == "FAIL" and run["reason"] == "SITE_NOT_READY_OR_BUSY"
    assert "B1_create" not in coord.calls and gateway.posts == []


@pytest.mark.parametrize("case, code", [
    ("unpaired", "bootstrap_pairing_required"),
    ("not_commissioned", "ppu_not_enabled"),
    ("unknown_alias", "ppu_not_found"),
])
def test_permission_denied(tmp_path, case, code):
    coord = FakeCoordinator(paired=case != "unpaired")
    registry = FakeRegistry(lifecycle="pending" if case == "not_commissioned" else "commissioned")
    workflow, _c, gateway = make(tmp_path, coordinator=coord, registry=registry)
    alias = "other" if case == "unknown_alias" else ALIAS
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(alias, plan_body())
    assert caught.value.code == code and gateway.posts == []


def test_manager_restart_mid_run_is_outcome_unknown_and_latched(tmp_path):
    pending: list = []
    workflow, coord, gateway = make(tmp_path)
    workflow.spawn = pending.append
    planned = workflow.plan(ALIAS, plan_body())["plan"]
    started = workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    restarted, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    run = restarted.run_status(ALIAS, started["run"]["run_id"])["run"]
    assert run["outcome"] == "OUTCOME_UNKNOWN" and run["reason"] == "MANAGER_RESTARTED_DURING_RUN"
    planned = restarted.plan(ALIAS, plan_body())["plan"]
    with pytest.raises(ProgrammingError) as caught:
        restarted.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    assert caught.value.code == "programming_outcome_unknown_unresolved"


def test_route_root_missing_is_explicit_unavailable(tmp_path):
    workflow, _c, _g = make(tmp_path)
    workflow.routes_root = tmp_path / "absent"
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, plan_body())
    assert caught.value.code == "programming_routes_unavailable"


# ----------------------------------------------------------------- OFE-1B Gate 1
def other_image() -> bytes:
    return image()[:-16] + b"OFE1B-FIRMWARE-B"


def plan_run(workflow, body):
    planned = workflow.plan(ALIAS, body)["plan"]
    started = workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    return planned, workflow.run_status(ALIAS, started["run"]["run_id"])["run"]


def test_same_resources_firmware_a_then_b_without_b1_b2_b3(tmp_path):
    workflow, coord, gateway = make(tmp_path)
    plan_a, run_a = plan_run(workflow, plan_body(image()))
    assert run_a["outcome"] == "PASS" and plan_a["activation_required"] is True
    b3_calls = coord.calls.count("B3")
    gateway.polls = 0
    plan_b, run_b = plan_run(workflow, plan_body(other_image()))
    assert run_b["outcome"] == "PASS", run_b
    # Firmware B: same Resource SHA, different Image SHA, no B1/B2/B3, no FPGA load.
    assert plan_b["activation_required"] is False and plan_b["resource"]["reuse"] is True
    assert coord.calls.count("B3") == b3_calls and coord.calls.count("B1_create") == 1
    assert plan_a["resource"]["resource_set_sha256"] == plan_b["resource"]["resource_set_sha256"]
    assert plan_a["image_asset"]["sha256"] != plan_b["image_asset"]["sha256"]
    assert plan_a["bundle"]["archive_sha256"] != plan_b["bundle"]["archive_sha256"]
    assert coord.active_sha == plan_a["bundle"]["archive_sha256"]  # Bundle A stays Active
    assert plan_b["fpga_load"] is False and len(gateway.posts) == 2
    assert base64.b64decode(gateway.posts[1]["asset_base64"]) == other_image()
    receipt = run_b["receipt"]
    assert receipt["resource_reuse"] is True
    assert receipt["expected_image_sha256"] == hashlib.sha256(other_image()).hexdigest()
    assert receipt["observed_job_binding_sha256"] == plan_b["job_binding_sha256"]
    assert receipt["observed_resource_set_sha256"] == plan_a["resource"]["resource_set_sha256"]


def test_different_ppu_resources_take_the_canonical_b1_b2_b3_path(tmp_path):
    coord = FakeCoordinator(active_sha="e" * 64)
    gateway = FakeGateway(image=image(), coordinator=coord,
                          resource_for=lambda active: "d" * 64 if active == "e" * 64
                          else ROUTE_RESOURCE_SHA)
    workflow, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    planned, run = plan_run(workflow, plan_body())
    assert planned["activation_required"] is True and planned["resource"]["reuse"] is False
    assert run["outcome"] == "PASS" and coord.calls.count("B3") == 1


def test_resources_unconfirmed_after_activation_never_submit(tmp_path):
    coord = FakeCoordinator()
    gateway = FakeGateway(image=image(), coordinator=coord, resource_for=lambda _a: "d" * 64)
    workflow, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    _planned, run = plan_run(workflow, plan_body())
    assert run["outcome"] == "FAIL" and run["reason"] == "RESOURCE_IDENTITY_NOT_CONFIRMED"
    assert gateway.posts == []


@pytest.mark.parametrize("gateway_kw, status, code", [
    ({"resources_state": {"state": "UNSUPPORTED"}}, 409, "ppu_runtime_resource_identity_unsupported"),
    ({"resources_state": {"state": "SOMETHING"}}, 409, "ppu_runtime_resource_identity_unsupported"),
    ({"status_raises": True}, 503, "ppu_resource_identity_unknown"),
    ({"resources_state": {"state": "VERIFIED", "asset_set_sha256": "f" * 64,
                          "generation": 1, "resource_set_sha256": ROUTE_RESOURCE_SHA}},
     409, "active_set_report_inconsistent"),
])
def test_unprovable_resource_identity_fails_closed_before_any_write(tmp_path, gateway_kw, status, code):
    coord = FakeCoordinator(active_sha="e" * 64)
    gateway = FakeGateway(image=image(), coordinator=coord, **gateway_kw)
    workflow, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, plan_body())
    assert (caught.value.status, caught.value.code) == (status, code)
    assert "B1_create" not in coord.calls and gateway.posts == []


def test_active_set_change_between_plan_and_run_fails_closed(tmp_path):
    route = bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6.json")
    sha = bundle_v3.build_user_image_bundle(route, image(), filename="app.bin").archive_sha256
    coord = FakeCoordinator(active_sha=sha)
    workflow, _c, gateway = make(tmp_path, coordinator=coord)
    planned = workflow.plan(ALIAS, plan_body(other_image()))["plan"]
    assert planned["activation_required"] is False
    coord.active_sha = "9" * 64  # generation advanced by another activation
    started = workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    run = workflow.run_status(ALIAS, started["run"]["run_id"])["run"]
    assert run["outcome"] == "FAIL" and run["reason"] == "ACTIVE_SET_CHANGED_SINCE_PLAN"
    assert gateway.posts == []


@pytest.mark.parametrize("change, status, code", [
    ({"operation": "blank_check"}, 400, "invalid_request"),
    ({"operation": "probe"}, 400, "invalid_request"),
    ({"operation": "status"}, 400, "invalid_request"),
    ({"operation": "erase"}, 400, "invalid_request"),  # erase never takes an Image
    ({"operation": "flash_cycle", "address": 0x08000000}, 400, "invalid_request"),
])
def test_operation_contract_is_validated_before_ppu(tmp_path, change, status, code):
    workflow, coord, gateway = make(tmp_path)
    body = {**plan_body(), **change}
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, body)
    assert (caught.value.status, caught.value.code) == (status, code)
    assert coord.calls == [] and gateway.posts == []


def test_operation_not_declared_by_profile_is_refused(tmp_path):
    workflow, coord, gateway = make(tmp_path)
    for op in ("program", "verify"):
        with pytest.raises(ProgrammingError) as caught:
            workflow.plan(ALIAS, plan_body(operation=op))
        assert caught.value.code == "operation_not_in_profile"
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, {"icpn": ICPN, "site_id": 2, "operation": "read",
                              "address": 0x08000000, "length": 256})
    assert caught.value.code == "operation_not_in_profile"
    assert coord.calls == [] and gateway.posts == []


def wide_routes(tmp_path) -> Path:
    """Route copy whose Profile also declares erase/program/verify/read (Host-only)."""
    root = tmp_path / "routes"
    root.mkdir()
    data = json.loads((ROUTES / "z2-site2-stm32f103c8t6.json").read_text())
    data["profile"]["capabilities"]["operations"] = [
        "flash_cycle", "erase", "program", "verify", "read"]
    (root / "z2-site2-stm32f103c8t6.json").write_text(json.dumps(data))
    return root


def wide_resource_sha(root: Path) -> str:
    route = bundle_v3.load_route(root / "z2-site2-stm32f103c8t6.json")
    return bundle_v3.resource_set_sha256(bundle_v3.resource_set_descriptor(route))


def test_user_operation_is_submitted_unchanged_and_unsupported_backend_fails(tmp_path):
    routes = wide_routes(tmp_path)
    coord = FakeCoordinator(active_sha="e" * 64)
    gateway = FakeGateway(image=image(), coordinator=coord, post_status=422,
                          resource_for=lambda _a: wide_resource_sha(routes))
    workflow, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    workflow.routes_root = routes
    planned, run = plan_run(workflow, plan_body(operation="program"))
    assert planned["operation"] == "program" and planned["steps"][-2] == "PROGRAM_JOB"
    # The Manager never rewrites the user's Operation into flash_cycle.
    assert gateway.posts[0]["operation"] == "program"
    assert gateway.posts[0]["job_binding"]["operation"] == "program"
    # PPU C-3 rejects it (OPERATION_UNSUPPORTED): definitive FAIL, no retry.
    assert run["outcome"] == "FAIL" and run["reason"] == "JOB_SUBMISSION_REJECTED_HTTP_422"
    assert len(gateway.posts) == 1


def test_non_flash_cycle_success_claim_is_not_a_pass(tmp_path):
    routes = wide_routes(tmp_path)
    coord = FakeCoordinator(active_sha="e" * 64)
    gateway = FakeGateway(image=image(), coordinator=coord,
                          resource_for=lambda _a: wide_resource_sha(routes))
    workflow, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    workflow.routes_root = routes
    _planned, run = plan_run(workflow, plan_body(operation="verify"))
    assert run["outcome"] == "FAIL" and run["reason"] == "OPERATION_RECEIPT_UNSUPPORTED"


@pytest.mark.parametrize("op, address, length, code", [
    ("erase", 0x08000000, 1024, None),
    ("read", 0x08000010, 7, None),
    ("erase", 0x08000010, 1024, "job_binding_invalid"),   # erase granularity
    ("erase", 0x08000000, 1000, "job_binding_invalid"),
    ("read", 0x08000000, 0x20000, "job_binding_invalid"),  # beyond flash
    ("read", 0, 16, "job_binding_invalid"),
])
def test_erase_read_ranges_follow_flash_geometry(tmp_path, op, address, length, code):
    routes = wide_routes(tmp_path)
    coord = FakeCoordinator(active_sha="e" * 64)
    gateway = FakeGateway(image=image(), coordinator=coord,
                          resource_for=lambda _a: wide_resource_sha(routes))
    workflow, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    workflow.routes_root = routes
    body = {"icpn": ICPN, "site_id": 2, "operation": op, "address": address, "length": length}
    if code is not None:
        with pytest.raises(ProgrammingError) as caught:
            workflow.plan(ALIAS, body)
        assert caught.value.code == code and gateway.posts == []
        return
    planned = workflow.plan(ALIAS, body)["plan"]
    assert planned["bundle"] is None and planned["image_asset"] is None
    assert planned["job_binding"]["range"] == {"address": address, "length": length}
    assert planned["job_binding"]["image_asset_sha256"] is None


def test_erase_without_active_matching_resources_needs_an_image_first(tmp_path):
    routes = wide_routes(tmp_path)
    workflow, coord, gateway = make(tmp_path)
    workflow.routes_root = routes
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, {"icpn": ICPN, "site_id": 2, "operation": "erase",
                              "address": 0x08000000, "length": 1024})
    assert caught.value.code == "resource_activation_requires_image"
    assert "B1_create" not in coord.calls and gateway.posts == []


@pytest.mark.parametrize("echo, reason", [
    (False, "JOB_BINDING_NOT_CONFIRMED"),
    ({"job_binding_sha256": "0" * 64}, "JOB_BINDING_NOT_CONFIRMED"),
    ({"resource_set_sha256": "d" * 64}, "JOB_BINDING_NOT_CONFIRMED"),
    ({"image_asset_sha256": "c" * 64}, "JOB_BINDING_NOT_CONFIRMED"),
    ({"ppu_id": "other-ppu"}, "JOB_BINDING_NOT_CONFIRMED"),
])
def test_http_success_without_matching_ppu_binding_echo_is_not_pass(tmp_path, echo, reason):
    gateway = FakeGateway(image=image(), echo=echo)
    workflow, _c, _g = make(tmp_path, gateway=gateway)
    _planned, run = run_once(workflow)
    assert run["outcome"] == "FAIL" and run["reason"] == reason


def test_receipt_keeps_expected_observed_and_readback_distinct(tmp_path):
    gateway = FakeGateway(image=image())
    workflow, _c, _g = make(tmp_path, gateway=gateway)
    planned, run = run_once(workflow)
    receipt = run["receipt"]
    assert receipt["schema"] == "plasma.manager.programming-receipt.v2"
    assert "image_sha256" not in receipt and "image_size" not in receipt
    assert receipt["expected_image_size"] == receipt["observed_image_size"] == len(image())
    assert receipt["expected_resource_set_sha256"] == planned["resource"]["resource_set_sha256"]
    assert receipt["expected_job_binding_sha256"] == planned["job_binding_sha256"]
    assert receipt["operation"] == "flash_cycle" and receipt["target"] == ICPN
    assert receipt["site_id"] == 2 and receipt["ppu_id"] == "z2-hil"


def test_observed_image_differs_from_expected_fails(tmp_path):
    gateway = FakeGateway(image=image())
    workflow, _c, _g = make(tmp_path, gateway=gateway)
    original = gateway.relay

    def tamper(method, path, **kw):
        status, headers, body = original(method, path, **kw)
        if path.startswith("/api/status?job="):
            data = json.loads(body)
            if "result" in data["job"]:
                data["job"]["result"]["image_sha256"] = "1" * 64
            body = json.dumps(data).encode()
        return status, headers, body
    gateway.relay = tamper
    _planned, run = run_once(workflow)
    assert run["outcome"] == "FAIL" and run["reason"] == "IMAGE_IDENTITY_MISMATCH"
    assert run["receipt"]["observed_image_sha256"] == "1" * 64
    assert run["receipt"]["expected_image_sha256"] == hashlib.sha256(image()).hexdigest()
