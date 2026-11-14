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
        # None: report the executed range truthfully; dict: override fields.
        self.flash_range: dict | None = None
        # programming / read Jobs: per-step evidence overrides and IC content.
        self.step_override: dict = {}
        self.drop_steps: tuple = ()
        self.read_data: bytes | None = None
        self.read_file_tamper = False
        self.downloads = 0
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
                "job_id": self._job_id(), "state": "queued"}})
        if method == "GET" and path.startswith("/api/status?job="):
            self.polls += 1
            post = self.posts[-1]
            sent = base64.b64decode(post["asset_base64"]) if "asset_base64" in post else self.image
            sha = hashlib.sha256(sent).hexdigest()
            # ``job_final`` may script one final state per submitted Job.
            final = (self.job_final if isinstance(self.job_final, str)
                     else self.job_final[min(len(self.posts), len(self.job_final)) - 1])
            state = "running" if self.polls == 1 else final
            binding = post["job_binding"]
            echo = None
            if self.echo:
                echo = {"job_binding_sha256": bundle_v3.sha256_hex(bundle_v3.canonical_json(binding)),
                        **{k: binding[k] for k in ("resource_set_sha256", "image_asset_sha256",
                                                   "operation", "range", "ppu_id", "site_id")},
                        **({"operations": binding["operations"]}
                           if "operations" in binding else {}),
                        "asset_set_sha256": self.coordinator.active_sha, "generation": 1}
                if isinstance(self.echo, dict):
                    echo.update(self.echo)
            # A programming Job is addressed by its operations list.
            kind = post.get("operation", "programming")
            result = "PASS" if state == "success" else "FAIL"
            has_image = "asset_base64" in post
            address, length = binding["range"]["address"], binding["range"]["length"]
            output_files = []
            if kind == "flash_cycle":
                evidence = {"result": result,
                            "readback_sha256": sha if self.readback_ok else "0" * 64,
                            "bytes_verified": len(self.image),
                            **self._executed_range(binding), "safe_off": self.safe_off}
            elif kind == "programming":
                operations = post["operations"]
                steps = {}
                if "erase" in operations:
                    steps["erase"] = {"erase_address": address,
                                      "erase_length": -(-length // 1024) * 1024}
                    if operations == ["erase"]:
                        steps["erase"].update(blank_verified=True, bytes_verified=length)
                if "program" in operations:
                    steps["program"] = {"write_address": address, "bytes_written": length,
                                        "image_sha256": sha}
                if "verify" in operations:
                    steps["verify"] = {"verify_address": address, "bytes_verified": length,
                                       "readback_sha256": sha if self.readback_ok else "0" * 64}
                for name, change in self.step_override.items():
                    steps[name] = {**steps.get(name, {}), **change}
                for name in self.drop_steps:
                    steps.pop(name, None)
                evidence = {"result": result, "operations": operations, "steps": steps,
                            "safe_off": self.safe_off}
            else:
                data = self._read_bytes(length)
                evidence = {"result": result, "read_address": address, "read_length": length,
                            "bytes_read": length, "sha256": hashlib.sha256(data).hexdigest(),
                            "safe_off": self.safe_off}
                if state == "success":
                    output_files = ["/var/lib/plasma/output/job/read_SITE2_flash.bin"]
            return self._resp(200, {"job": {
                "job_id": self._job_id(), "state": state,
                # The Site the Job was submitted for, not a fixed one: a Batch
                # walks several Sites of one PPU.
                "site_id": (self.posts[-1].get("site_id", 2) if self.posts else 2),
                "operation": kind, "stage": "verify", "progress_percent": 50,
                "job_binding": echo,
                "result": {"state": state, "image_sha256": sha if has_image else None,
                           "image_size": len(sent) if has_image else 0,
                           "attempts": 1, "elapsed_ms": 10000, "error": None,
                           "output_files": output_files,
                           "details": {kind: evidence}}}})
        if method == "GET" and path.endswith("/files/read_SITE2_flash.bin"):
            self.downloads += 1
            length = self.posts[-1]["job_binding"]["range"]["length"]
            data = self._read_bytes(length)
            if self.read_file_tamper:
                data = b"X" + data[1:]
            return 200, {"Content-Type": "application/octet-stream"}, data
        raise AssertionError(f"unexpected Gateway call {method} {path}")

    def _job_id(self):
        # Every submitted Job has its own identity.
        return "job-20261109-120000-%08x" % (0x0123abcd + len(self.posts) - 1)

    def _read_bytes(self, length):
        return (self.read_data if self.read_data is not None else bytes(range(256)) * 300)[:length]

    def _executed_range(self, binding):
        address, length = binding["range"]["address"], binding["range"]["length"]
        executed = {"load_address": address, "erase_address": address,
                    "erase_length": -(-length // 1024) * 1024, "write_address": address,
                    "verify_address": address, "readback_address": address}
        return executed if self.flash_range is None else {**executed, **self.flash_range}

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


@pytest.mark.parametrize("override", [
    {"erase_address": 0x08000400},           # executed somewhere else
    {"write_address": 0x08000400},
    {"readback_address": 0x08000400},
    {"erase_length": 4096},
    {"load_address": None, "erase_address": None, "erase_length": None,
     "write_address": None, "verify_address": None, "readback_address": None},  # no range
])
def test_ppu_pass_without_the_binding_flash_range_is_never_a_pass(tmp_path, override):
    route = bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6.json")
    sha = bundle_v3.build_user_image_bundle(route, image(), filename="app.bin").archive_sha256
    workflow, _coord, gateway = make(tmp_path, coordinator=FakeCoordinator(active_sha=sha))
    gateway.flash_range = override
    _planned, run = run_once(workflow)
    assert run["outcome"] == "FAIL" and run["reason"] == "FLASH_RANGE_MISMATCH"
    receipt = run["receipt"]
    assert receipt["expected_flash_range"]["write_address"] == 0x08000000
    assert receipt["observed_flash_range"] != receipt["expected_flash_range"]


def test_binding_echo_with_a_different_range_is_not_confirmed(tmp_path):
    route = bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6.json")
    sha = bundle_v3.build_user_image_bundle(route, image(), filename="app.bin").archive_sha256
    gateway = FakeGateway(image=image(),
                          echo={"range": {"address": 0x08000400, "length": len(image())}})
    workflow, _coord, gateway = make(tmp_path, coordinator=FakeCoordinator(active_sha=sha),
                                     gateway=gateway)
    _planned, run = run_once(workflow)
    assert run["outcome"] == "FAIL" and "JOB_BINDING_NOT_CONFIRMED" in json.dumps(run)


@pytest.mark.parametrize("body, code", [
    (plan_body(icpn="STM32F407VGT6"), "programming_route_not_found"),
    (plan_body(site=3), "programming_route_not_found"),
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


def legacy_only_routes(tmp_path) -> Path:
    """Only the legacy flash_cycle Route (as on a not-yet-updated deployment)."""
    root = tmp_path / "legacy-routes"
    root.mkdir()
    name = "z2-site2-stm32f103c8t6.json"
    (root / name).write_text((ROUTES / name).read_text())
    return root


OPS_ROUTE = bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6-operations.json")
OPS_RESOURCE_SHA = bundle_v3.resource_set_sha256(bundle_v3.resource_set_descriptor(OPS_ROUTE))
LEGAL_LISTS = [["erase"], ["program"], ["verify"], ["erase", "program"],
               ["program", "verify"], ["erase", "program", "verify"]]


def ops_body(operations, raw: bytes | None = None, **extra):
    if not bundle_v3.operations_take_image(operations):
        return {"icpn": ICPN, "site_id": 2, "operations": operations,
                "address": 0x08000000, "length": 2048, **extra}
    raw = image() if raw is None else raw
    return {"icpn": ICPN, "site_id": 2, "operations": operations,
            "image_base64": base64.b64encode(raw).decode(), "image_filename": "app.bin", **extra}


def ops_workflow(tmp_path, *, active=True, **gateway_kw):
    """The PPU already holds the operations Route's Resources (Resource Reuse)."""
    coord = FakeCoordinator(active_sha="e" * 64) if active else FakeCoordinator()
    gateway = FakeGateway(image=image(), coordinator=coord,
                          resource_for=lambda _a: OPS_RESOURCE_SHA, **gateway_kw)
    workflow, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    return workflow, coord, gateway


def test_committed_routes_keep_legacy_flash_cycle_separate_from_the_operations_route():
    legacy = bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6.json")
    assert legacy.capabilities["operations"] == ["flash_cycle"]  # legacy identity untouched
    assert OPS_ROUTE.capabilities["operations"] == ["erase", "program", "verify", "read"]
    assert OPS_RESOURCE_SHA != ROUTE_RESOURCE_SHA
    routes = bundle_v3.load_routes(ROUTES)
    pick = lambda ops: [r.route_id for r in bundle_v3.resolve_routes(  # noqa: E731
        routes, icpn=ICPN, site=2, operations=ops)]
    assert pick(["flash_cycle"]) == ["z2-site2-stm32f103c8t6"]
    for ops in LEGAL_LISTS + [["read"]]:
        assert pick(ops) == ["z2-site2-stm32f103c8t6-operations"]


def test_operation_not_declared_by_profile_is_refused(tmp_path):
    workflow, coord, gateway = make(tmp_path)
    workflow.routes_root = legacy_only_routes(tmp_path)
    for operations in (["program"], ["erase", "program", "verify"]):
        with pytest.raises(ProgrammingError) as caught:
            workflow.plan(ALIAS, ops_body(operations))
        assert caught.value.code == "operation_not_in_profile"
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, {"icpn": ICPN, "site_id": 2, "operation": "read",
                              "address": 0x08000000, "length": 256})
    assert caught.value.code == "operation_not_in_profile"
    assert coord.calls == [] and gateway.posts == []


@pytest.mark.parametrize("body, status", [
    ({"operations": []}, 400),
    ({"operations": ["program", "erase"]}, 400),
    ({"operations": ["erase", "erase"]}, 400),
    ({"operations": ["read"]}, 400),
    ({"operations": ["flash_cycle"]}, 400),
    ({"operations": "erase"}, 400),
    ({"operations": ["erase", "verify"]}, 422),          # no defined expected data
    ({"operations": ["program"], "operation": "flash_cycle"}, 400),
    ({"operation": "program"}, 400),                      # a step, never its own Job
    ({"operation": "verify"}, 400),
])
def test_operations_list_contract_is_validated_before_ppu(tmp_path, body, status):
    workflow, coord, gateway = ops_workflow(tmp_path)
    request = {**ops_body(["program"]), **body}
    if "operation" in body and "operations" not in body:
        del request["operations"]
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, request)
    assert caught.value.status == status
    assert caught.value.code == ("operations_invalid" if "operation" not in body
                                 else "invalid_request")
    assert coord.calls == [] and gateway.posts == []


@pytest.mark.parametrize("operations", LEGAL_LISTS, ids=lambda ops: "+".join(ops))
def test_every_legal_list_is_one_job_with_one_binding_and_one_receipt(tmp_path, operations):
    workflow, coord, gateway = ops_workflow(tmp_path)
    planned, run = plan_run(workflow, ops_body(operations))
    assert planned["operation"] == "programming" and planned["operations"] == operations
    assert planned["route"]["route_id"] == "z2-site2-stm32f103c8t6-operations"
    assert planned["steps"] == ["RESOURCE_REUSE", "PROGRAMMING_JOB", "VERIFY_RECEIPT"]
    # Exactly ONE Job: its list travels as ``operations``; never ``flash_cycle``.
    [post] = gateway.posts
    assert post["operations"] == operations and "operation" not in post
    assert post["job_binding"]["operation"] == "programming"
    assert post["job_binding"]["operations"] == operations
    assert ("asset_base64" in post) == bundle_v3.operations_take_image(operations)
    assert run["outcome"] == "PASS", run
    assert run["job_submission_count"] == 1 and run["auto_retry"] == "DISABLED"
    receipt = run["receipt"]
    assert receipt["schema"] == "plasma.manager.programming-receipt.v3"
    assert receipt["operation"] == "programming"
    assert receipt["operations"] == receipt["observed_operations"] == operations
    assert set(receipt["expected_steps"]) == set(operations)
    assert receipt["observed_steps"] == receipt["expected_steps"]
    assert receipt["expected_flash_range"] is None and receipt["read_output"] is None
    assert receipt["safe_off"] is True
    assert receipt["observed_job_binding_sha256"] == planned["job_binding_sha256"]
    if operations == ["erase"]:
        assert receipt["expected_image_sha256"] is None
        assert receipt["expected_steps"]["erase"] == {
            "erase_address": 0x08000000, "erase_length": 2048,
            "blank_verified": True, "bytes_verified": 2048}
    if "verify" in operations:
        assert receipt["readback_sha256"] == receipt["expected_image_sha256"]
    assert "B1_create" not in coord.calls


@pytest.mark.parametrize("fault, reason", [
    ({"step_override": {"program": {"write_address": 0x08000400}}}, "PROGRAM_EVIDENCE_MISMATCH"),
    ({"step_override": {"erase": {"erase_length": 65536}}}, "ERASE_EVIDENCE_MISMATCH"),
    ({"readback_ok": False}, "VERIFY_EVIDENCE_MISMATCH"),
    ({"drop_steps": ("verify",)}, "OPERATIONS_MISMATCH"),          # a listed step did not run
    ({"step_override": {"read": {"bytes_read": 1}}}, "OPERATIONS_MISMATCH"),  # an extra step
    ({"safe_off": False}, "SAFE_OFF_NOT_VERIFIED"),
    ({"job_final": "failed"}, "JOB_NOT_SUCCESS"),
    ({"echo": {"operations": ["program", "verify"]}}, "JOB_BINDING_NOT_CONFIRMED"),
])
def test_programming_success_claim_without_proof_of_every_step_is_not_a_pass(
        tmp_path, fault, reason):
    kwargs = {k: v for k, v in fault.items() if k not in ("step_override", "drop_steps")}
    workflow, _c, gateway = ops_workflow(tmp_path, **kwargs)
    gateway.step_override = fault.get("step_override", {})
    gateway.drop_steps = fault.get("drop_steps", ())
    _planned, run = plan_run(workflow, ops_body(["erase", "program", "verify"]))
    assert run["outcome"] == "FAIL" and run["reason"] == reason
    assert len(gateway.posts) == 1  # never resubmitted


def test_legacy_flash_cycle_request_still_uses_the_unchanged_legacy_route(tmp_path):
    workflow, _c, gateway = make(tmp_path)
    planned, run = run_once(workflow)
    assert planned["operation"] == "flash_cycle" and planned["operations"] is None
    assert planned["route"]["route_id"] == "z2-site2-stm32f103c8t6"
    assert planned["resource"]["resource_set_sha256"] == ROUTE_RESOURCE_SHA
    post = gateway.posts[0]
    assert post["operation"] == "flash_cycle" and "operations" not in post
    assert "operations" not in post["job_binding"]
    assert run["outcome"] == "PASS" and run["receipt"]["expected_steps"] is None


@pytest.mark.parametrize("op, address, length, code", [
    ("erase", 0x08000000, 1024, None),
    ("read", 0x08000010, 7, None),
    ("erase", 0x08000010, 1024, "job_binding_invalid"),   # erase granularity
    ("erase", 0x08000000, 1000, "job_binding_invalid"),
    ("read", 0x08000000, 0x20000, "job_binding_invalid"),  # beyond flash
    ("read", 0, 16, "job_binding_invalid"),
    ("read", 0x40021000, 4, "job_binding_invalid"),        # MMIO is never readable
])
def test_erase_read_ranges_follow_flash_geometry(tmp_path, op, address, length, code):
    workflow, _c, gateway = ops_workflow(tmp_path)
    selector = {"operations": ["erase"]} if op == "erase" else {"operation": "read"}
    body = {"icpn": ICPN, "site_id": 2, **selector, "address": address, "length": length}
    if code is not None:
        with pytest.raises(ProgrammingError) as caught:
            workflow.plan(ALIAS, body)
        assert caught.value.code == code and gateway.posts == []
        return
    planned = workflow.plan(ALIAS, body)["plan"]
    assert planned["bundle"] is None and planned["image_asset"] is None
    assert planned["source"] == "range"
    assert planned["job_binding"]["range"] == {"address": address, "length": length}
    assert planned["job_binding"]["image_asset_sha256"] is None


def test_erase_without_active_matching_resources_needs_an_image_first(tmp_path):
    workflow, coord, gateway = make(tmp_path)
    for body in (ops_body(["erase"]),
                 {"icpn": ICPN, "site_id": 2, "operation": "read",
                  "address": 0x08000000, "length": 64}):
        with pytest.raises(ProgrammingError) as caught:
            workflow.plan(ALIAS, body)
        assert caught.value.code == "resource_activation_requires_image"
    assert "B1_create" not in coord.calls and gateway.posts == []


# --------------------------------------------------------------- Read Memory

READ_BODY = {"icpn": ICPN, "site_id": 2, "operation": "read",
             "address": 0x08000010, "length": 777}


def test_read_is_an_independent_job_whose_output_the_manager_fetches_and_proves(tmp_path):
    workflow, coord, gateway = ops_workflow(tmp_path)
    planned, run = plan_run(workflow, READ_BODY)
    assert planned["operation"] == "read" and planned["operations"] is None
    assert planned["steps"] == ["RESOURCE_REUSE", "READ_JOB", "VERIFY_RECEIPT",
                                "FETCH_READ_OUTPUT"]
    [post] = gateway.posts
    assert post["operation"] == "read" and "operations" not in post
    assert "asset_base64" not in post and "image_asset" not in post
    assert run["outcome"] == "PASS", run
    expected = (bytes(range(256)) * 300)[:777]
    output = run["receipt"]["read_output"]
    assert output == {"address": 0x08000010, "bytes": 777,
                      "sha256": hashlib.sha256(expected).hexdigest(),
                      "filename": f"read-{ICPN}-0x08000010-777.bin", "available": True}
    assert run["receipt"]["expected_image_sha256"] is None
    data, meta = workflow.read_output(ALIAS, run["run_id"])
    assert data == expected and meta["sha256"] == output["sha256"]
    # Nothing was erased, programmed, activated or reloaded for a Read.
    assert "B1_create" not in coord.calls and gateway.downloads == 1
    # A restarted Manager still serves the journalled, re-hashed bytes.
    again, _c2, _g2 = ops_workflow(tmp_path)
    assert again.read_output(ALIAS, run["run_id"])[0] == expected
    with pytest.raises(ProgrammingError) as caught:
        workflow.read_output("other", run["run_id"])
    assert caught.value.status == 404


@pytest.mark.parametrize("fault, reason", [
    ({"read_file_tamper": True}, "READ_OUTPUT_INTEGRITY_MISMATCH"),
    ({"safe_off": False}, "SAFE_OFF_NOT_VERIFIED"),
    ({"job_final": "failed"}, "JOB_NOT_SUCCESS"),
])
def test_read_failure_or_unprovable_bytes_never_offers_a_download(tmp_path, fault, reason):
    tamper = fault.pop("read_file_tamper", False) if isinstance(fault, dict) else False
    workflow, _c, gateway = ops_workflow(tmp_path, **fault)
    gateway.read_file_tamper = tamper
    _planned, run = plan_run(workflow, READ_BODY)
    assert run["outcome"] == "FAIL" and run["reason"] == reason
    assert run["receipt"]["read_output"]["available"] is False
    with pytest.raises(ProgrammingError) as caught:
        workflow.read_output(ALIAS, run["run_id"])
    assert caught.value.code == "read_output_unavailable"
    assert len(gateway.posts) == 1


def test_read_unknown_outcome_latches_and_is_never_resubmitted(tmp_path):
    workflow, _c, gateway = ops_workflow(tmp_path, post_raises=True)
    _planned, run = plan_run(workflow, READ_BODY)
    assert run["outcome"] == "OUTCOME_UNKNOWN" and len(gateway.posts) == 1
    with pytest.raises(ProgrammingError) as caught:
        workflow.start(ALIAS, {"plan_id": workflow.plan(ALIAS, READ_BODY)["plan"]["plan_id"],
                               "confirm": CONFIRM_TOKEN})
    assert caught.value.code == "programming_outcome_unknown_unresolved"


def test_read_is_refused_while_a_programming_run_owns_the_ppu(tmp_path):
    workflow, _c, gateway = ops_workflow(tmp_path)
    pending = []
    workflow.spawn = pending.append  # the first run stays in progress
    first = workflow.plan(ALIAS, ops_body(["erase", "program", "verify"]))["plan"]
    workflow.start(ALIAS, {"plan_id": first["plan_id"], "confirm": CONFIRM_TOKEN})
    read = workflow.plan(ALIAS, READ_BODY)["plan"]
    with pytest.raises(ProgrammingError) as caught:
        workflow.start(ALIAS, {"plan_id": read["plan_id"], "confirm": CONFIRM_TOKEN})
    assert caught.value.code == "programming_run_in_progress" and gateway.posts == []


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
    assert receipt["schema"] == "plasma.manager.programming-receipt.v3"
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


# ---------------------------------------------------------------- Bundle source
# Unified Programming Integration (2026-11-11): the user supplies their own
# canonical Bundle v3. Host-only; fake PPU / fake Provider.

def _route():
    return bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6.json")


def user_bundle(raw: bytes | None = None, *, route=None, version: str = "2.3.0"):
    return bundle_v3.build_image_bundle(
        route or _route(), image() if raw is None else raw,
        image_filename="customer-app.bin", asset_package_id="customer-fw",
        bundle_name="customer-release", version=version)


def bundle_body(archive: bytes, *, site: int = 2, icpn: str = ICPN,
                operation: str = "flash_cycle", **extra):
    return {"icpn": icpn, "site_id": site, "operation": operation,
            "bundle_base64": base64.b64encode(archive).decode(), **extra}


def _variant_route(**flash):
    data = json.loads((ROUTES / "z2-site2-stm32f103c8t6.json").read_text())
    target = flash.pop("target", None)
    if target:
        data["target"].update(target)
    data["profile"]["flash_profile"].update(flash)
    return bundle_v3.parse_route(data)


def _rezip(archive: bytes, mutate) -> bytes:
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        contents = {name: source.read(name) for name in source.namelist()}
    mutate(contents)
    return bundle_v3.canonical_zip(contents)


def test_bundle_source_cache_miss_admits_the_users_exact_archive(tmp_path):
    workflow, coord, gateway = make(tmp_path)
    built = user_bundle()
    planned, run = plan_run(workflow, bundle_body(built.archive))
    assert planned["source"] == "bundle" and planned["activation_required"] is True
    assert planned["bundle"]["archive_sha256"] == built.archive_sha256
    assert planned["bundle"]["bundle_name"] == "customer-release"
    assert planned["steps"][:3] == ["B1_UPLOAD", "B2_ADMIT", "B3_ACTIVATE"]
    assert run["outcome"] == "PASS", run
    # B1 carried the user's own bytes; B3 activated exactly that identity.
    assert bytes(coord.uploaded) == built.archive and coord.active_sha == built.archive_sha256
    assert coord.b3_body["fpga_load"] is False
    assert len(gateway.posts) == 1 and run["job_submission_count"] == 1
    post = gateway.posts[0]
    assert base64.b64decode(post["asset_base64"]) == image()
    assert post["job_binding"] == planned["job_binding"]
    assert not {"bundle_base64", "asset_set_sha256"} & set(post)
    receipt = run["receipt"]
    assert receipt["resource_reuse"] is False and receipt["safe_off"] is True
    assert receipt["readback_sha256"] == hashlib.sha256(image()).hexdigest()


def test_bundle_source_reuses_ppu_verified_resources_without_b1_b2_b3(tmp_path):
    workflow, coord, gateway = make(tmp_path)
    _plan_a, run_a = plan_run(workflow, plan_body(image()))  # Firmware source activates
    assert run_a["outcome"] == "PASS"
    active, calls = coord.active_sha, list(coord.calls)
    gateway.polls = 0
    built = user_bundle(other_image())
    planned, run = plan_run(workflow, bundle_body(built.archive))
    assert planned["source"] == "bundle"
    assert planned["resource"]["reuse"] is True and planned["activation_required"] is False
    assert planned["steps"][0] == "RESOURCE_REUSE"
    assert run["outcome"] == "PASS", run
    assert coord.active_sha == active  # the Active Set is untouched
    assert not {"B1_create", "B2", "B3"} & set(coord.calls[len(calls):])
    assert base64.b64decode(gateway.posts[-1]["asset_base64"]) == other_image()
    assert run["receipt"]["resource_reuse"] is True
    assert run["receipt"]["observed_job_binding_sha256"] == planned["job_binding_sha256"]


def test_firmware_and_bundle_sources_share_one_resource_and_binding_identity(tmp_path):
    workflow, _coord, _gateway = make(tmp_path)
    firmware = workflow.plan(ALIAS, plan_body(image()))["plan"]
    bundle = workflow.plan(ALIAS, bundle_body(user_bundle().archive))["plan"]
    assert firmware["source"] == "image" and bundle["source"] == "bundle"
    for key in ("resource", "image_asset", "job_binding", "job_binding_sha256", "route"):
        assert firmware[key] == bundle[key], key
    assert firmware["bundle"]["archive_sha256"] != bundle["bundle"]["archive_sha256"]


def _two_images(contents):
    manifest = json.loads(contents["manifest.json"])
    extra = json.loads(json.dumps(manifest["packages"][-1]))
    extra["id"] = "second-fw"
    path = "payload/packages/second-fw/data/second.bin"
    extra["files"][0]["path"] = path
    contents[path] = contents[manifest["packages"][-1]["files"][0]["path"]]
    manifest["packages"].append(extra)
    contents["manifest.json"] = bundle_v3.canonical_json(manifest)


def _fpga_package(contents):
    manifest = json.loads(contents["manifest.json"])
    path = "payload/packages/pl-image/data/design.bit"
    contents[path] = b"\x00" * 16
    manifest["packages"].append({
        "id": "pl-image", "kind": "fpga-image", "version": "1.0.0", "requires": [],
        "files": [{"path": path, "size": 16, "executable": False,
                   "sha256": hashlib.sha256(contents[path]).hexdigest()}]})
    contents["manifest.json"] = bundle_v3.canonical_json(manifest)


def _tamper_image(contents):
    path = next(p for p in contents if p.endswith("customer-app.bin"))
    contents[path] = contents[path][:-1] + bytes([contents[path][-1] ^ 0xFF])


@pytest.mark.parametrize("make_archive, status, code, reason", [
    (lambda: b"not a zip archive", 422, "bundle_incompatible", "BUNDLE_ARCHIVE_INVALID"),
    (lambda: user_bundle(route=_variant_route(target={"board": "other-board"})).archive,
     422, "bundle_incompatible", "BUNDLE_TARGET_MISMATCH"),
    # A Bundle may not bring its own flash geometry / Provider configuration.
    (lambda: user_bundle(route=_variant_route(flash_size=131072)).archive,
     422, "bundle_resource_not_qualified", "BUNDLE_RESOURCE_NOT_ROUTE"),
    (lambda: user_bundle(route=_variant_route(target_config="target/stm32f4x.cfg")).archive,
     422, "bundle_resource_not_qualified", "BUNDLE_RESOURCE_NOT_ROUTE"),
    (lambda: _rezip(user_bundle().archive, lambda c: c.update({"payload/extra.sh": b"#!/bin/sh\n"})),
     422, "bundle_incompatible", "BUNDLE_NOT_CANONICAL"),
    (lambda: _rezip(user_bundle().archive, _tamper_image),
     422, "bundle_incompatible", "BUNDLE_FILE_MISMATCH"),
    # Several Images need an explicit choice this contract version cannot express.
    (lambda: _rezip(user_bundle().archive, _two_images),
     422, "bundle_incompatible", "BUNDLE_PACKAGE_SET_UNSUPPORTED"),
    # FPGA reload has no qualified Bundle-source execution path: fail closed.
    (lambda: _rezip(user_bundle().archive, _fpga_package),
     422, "bundle_incompatible", "BUNDLE_PACKAGE_SET_UNSUPPORTED"),
    (lambda: b"\x00" * (bundle_v3.MAX_BUNDLE_ARCHIVE_BYTES + 1),
     413, "bundle_too_large", None),
])
def test_incompatible_bundle_fails_closed_before_any_ppu_contact(
        tmp_path, make_archive, status, code, reason):
    workflow, coord, gateway = make(tmp_path)
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, bundle_body(make_archive()))
    assert (caught.value.status, caught.value.code) == (status, code)
    if reason is not None:
        assert caught.value.message == reason
    assert coord.calls == [] and gateway.posts == [] and workflow._plans == {}


def test_bundle_for_another_ic_or_site_is_refused(tmp_path):
    workflow, coord, gateway = make(tmp_path)
    archive = user_bundle().archive
    for body, code in (
            (bundle_body(archive, icpn="STM32F407VGT6"), "programming_route_not_found"),
            (bundle_body(archive, site=3), "programming_route_not_found")):
        with pytest.raises(ProgrammingError) as caught:
            workflow.plan(ALIAS, body)
        assert caught.value.code == code
    assert coord.calls == [] and gateway.posts == []


@pytest.mark.parametrize("body", [
    lambda a: {**bundle_body(a), "image_base64": base64.b64encode(image()).decode()},
    lambda a: bundle_body(a, image_filename="app.bin"),
    lambda a: bundle_body(a, address=0x08000000, length=1024),
    lambda a: {**bundle_body(a, operation="erase"), "address": 0x08000000, "length": 1024},
    lambda a: {**bundle_body(a), "bundle_base64": "not base64!"},
    lambda a: {**bundle_body(a), "bundle_base64": ""},
])
def test_bundle_source_request_shape_is_strict(tmp_path, body):
    workflow, coord, gateway = make(tmp_path)
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, body(user_bundle().archive))
    assert caught.value.status == 400
    assert coord.calls == [] and gateway.posts == []


def test_bundle_source_must_carry_the_resources_of_the_route_that_declares_its_operations(tmp_path):
    """A Bundle built for the legacy flash_cycle Route cannot run an operations
    list: its Profile does not declare those operations (fail closed)."""
    workflow, coord, gateway = make(tmp_path)
    body = bundle_body(user_bundle().archive)
    del body["operation"]
    with pytest.raises(ProgrammingError) as caught:
        workflow.plan(ALIAS, {**body, "operations": ["erase", "program", "verify"]})
    assert caught.value.code == "bundle_resource_not_qualified"
    assert coord.calls == [] and gateway.posts == []
    # The same list with a Bundle of the operations Route is admitted.
    own = user_bundle(route=OPS_ROUTE)
    admitted = bundle_body(own.archive)
    del admitted["operation"]
    planned = workflow.plan(
        ALIAS, {**admitted, "operations": ["erase", "program", "verify"]})["plan"]
    assert planned["source"] == "bundle" and planned["operations"] == ["erase", "program", "verify"]
    assert planned["bundle"]["archive_sha256"] == own.archive_sha256


def test_bundle_source_plan_is_single_use_and_never_resubmits_after_unknown(tmp_path):
    workflow, _coord, gateway = make(
        tmp_path, gateway=FakeGateway(image=image(), post_raises=True))
    planned = workflow.plan(ALIAS, bundle_body(user_bundle().archive))["plan"]
    start = {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN}
    run = workflow.run_status(ALIAS, workflow.start(ALIAS, start)["run"]["run_id"])["run"]
    assert run["outcome"] == "OUTCOME_UNKNOWN" and run["job_submission_count"] == 1
    assert run["auto_retry"] == "DISABLED" and len(gateway.posts) == 1
    with pytest.raises(ProgrammingError) as consumed:
        workflow.start(ALIAS, start)
    assert consumed.value.code == "programming_plan_not_found"
    again = workflow.plan(ALIAS, bundle_body(user_bundle().archive))["plan"]
    with pytest.raises(ProgrammingError) as latched:
        workflow.start(ALIAS, {"plan_id": again["plan_id"], "confirm": CONFIRM_TOKEN})
    assert latched.value.code == "programming_outcome_unknown_unresolved"
    assert len(gateway.posts) == 1


def test_user_bundle_passes_the_host_only_ppu_bundle_verifier(tmp_path):
    route = _route()
    built, raw = bundle_v3.route_bundle_from_archive(route, user_bundle().archive)
    assert raw == image() and built.archive == user_bundle().archive
    path = tmp_path / "customer.zip"
    path.write_bytes(built.archive)
    verified = ppu_unified_deployment.verify_host_only_bundle(
        path, expected_sha256=built.archive_sha256, target_profile=route.target)
    assert [p.kind for p in verified.packages] == [
        "platform-provider", "programming-profile", "firmware-asset"]
