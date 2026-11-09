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


class FakeGateway:
    def __init__(self, *, image: bytes, safe_off=True, readback_ok=True,
                 post_status=202, post_raises=False, busy=False, job_final="success",
                 status_target=ICPN):
        self.image = image
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
            return self._resp(200, {
                "ppu": {"ppu_id": "z2-hil", "execution": {"busy": self.busy, "active_job_count": 0},
                        "runtime_activation": {"active": False}},
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
            sha = hashlib.sha256(self.image).hexdigest()
            state = "running" if self.polls == 1 else self.job_final
            return self._resp(200, {"job": {
                "job_id": "job-20261109-120000-0123abcd", "state": state, "site_id": 2,
                "operation": "flash_cycle", "stage": "verify", "progress_percent": 50,
                "result": {"state": state, "image_sha256": sha, "image_size": len(self.image),
                           "attempts": 1, "elapsed_ms": 10000, "error": None,
                           "details": {"flash_cycle": {
                               "result": "PASS" if state == "success" else "FAIL",
                               "readback_sha256": sha if self.readback_ok else "0" * 64,
                               "bytes_verified": len(self.image),
                               "safe_off": self.safe_off}}}}})
        raise AssertionError(f"unexpected Gateway call {method} {path}")


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
    workflow = BundleProgrammingWorkflow(
        coordinator=coordinator, registry=registry or FakeRegistry(),
        gateway_client_factory=lambda endpoint, timeout: gateway,
        gate=PPUOperationGate(), request_timeout_s=5.0, routes_root=ROUTES,
        journal_path=(tmp_path / "runs.json") if journal else None,
        sleep=lambda _s: None, spawn=lambda target: target(), poll_interval_s=0.0)
    return workflow, coordinator, gateway


def plan_body(raw: bytes | None = None, site: int = 2, icpn: str = ICPN):
    raw = image() if raw is None else raw
    return {"icpn": icpn, "site_id": site, "image_base64": base64.b64encode(raw).decode(),
            "image_filename": "app.bin"}


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
    assert post["asset_set_sha256"] == planned["bundle"]["archive_sha256"]
    assert post["bundle_asset_sha256"] == hashlib.sha256(image()).hexdigest()
    assert "asset_base64" not in post  # image never travels in the Job request
    receipt = run["receipt"]
    assert receipt["readback_sha256"] == receipt["image_sha256"]
    assert receipt["bytes_verified"] == len(image()) and receipt["safe_off"] is True
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
