"""Host-only: one ``programming`` Job (ordered E/P/V operations list) and the
independent ``read`` Job through REST -> Runtime -> C-3 -> fake OpenOCD.

Real pieces: Gateway handler, SiteManager Job Binding admission with the REAL
Active Resource resolver over a canonical route-built Bundle, execution
router, OpenOCD interface, OPF reference executor, the C-3 Site Worker core
and the ABI-v5 adapter argv / evidence logic. Fake: root admission and the
OpenOCD process (Flash simulator). No Z2, FPGA, DUT or real OpenOCD is used;
a PASS here is not a hardware qualification of any operation.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from plasma_opf import bundle_v3

from .test_c3_rest_flash_cycle import Stack, TERMINAL, abi5_stub, run, short_tmp
from .test_ofe1b_resource_reuse_job_image import (
    C3_PROFILE, C3_PROVIDER, FW_A, FW_B, PPU_ID, ROUTE_PATH, job_body, submit,
)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import ppu_site_worker as worker  # noqa: E402

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="Linux AF_UNIX + SO_PEERCRED")
BASE = 0x08000000
ALL = ["flash_cycle", "erase", "program", "verify", "read"]
LEGAL = [["erase"], ["program"], ["verify"], ["erase", "program"], ["program", "verify"],
         ["erase", "program", "verify"]]


def ops_route(operations=ALL) -> bundle_v3.ProgrammingRoute:
    data = json.loads(ROUTE_PATH.read_text())
    data["provider"]["id"] = C3_PROVIDER
    data["profile"]["id"] = C3_PROFILE
    data["profile"]["capabilities"]["provider_package"] = C3_PROVIDER
    data["profile"]["capabilities"]["operations"] = list(operations)
    return bundle_v3.parse_route(data)


def ops_stack(folder, operations=ALL, **kw):
    """Active Set = canonical Bundle of a Route declaring ``operations``."""
    route = ops_route(operations)
    built = bundle_v3.build_user_image_bundle(route, FW_A)
    return (Stack(Path(folder), bundle_options={"programming_bundle": built},
                  in_process=kw.pop("in_process", True), **kw),
            bundle_v3.resource_set_descriptor(route))


def ops_body(resource, operations, image=None, *, address=None, length=None,
             load_address=None):
    asset = None if image is None else bundle_v3.image_asset_descriptor(
        resource, image, load_address=load_address)
    binding = bundle_v3.job_image_binding(
        resource, asset, ppu_id=PPU_ID, site_id=2, operation=bundle_v3.PROGRAMMING,
        operations=operations, address=address, length=length)
    kinds = {p["kind"]: p["id"] for p in resource["packages"]}
    body = {"site_id": 2, "operations": list(operations),
            "target": resource["constraints"]["icpn"],
            "provider": kinds["platform-provider"], "profile": kinds["programming-profile"],
            "job_binding": binding}
    if image is not None:
        body.update(image_asset=asset, asset_base64=base64.b64encode(image).decode())
    return body


def commands(argv):
    return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "-c"]


def actions(argv):
    return [c.split(" {")[0].split(" 0x")[0] for c in commands(argv)
            if c.startswith(("flash erase_address", "flash write_image",
                             "flash verify_image", "dump_image"))]


EXPECTED_ACTIONS = {
    ("erase",): ["flash erase_address", "dump_image"],
    ("program",): ["flash write_image"],
    ("verify",): ["dump_image"],
    ("erase", "program"): ["flash erase_address", "flash write_image"],
    ("program", "verify"): ["flash write_image", "dump_image"],
    ("erase", "program", "verify"): ["flash erase_address", "flash write_image", "dump_image"],
}


# ---------------------------------------------------------- operations contract

def test_operations_list_is_ordered_unique_and_erase_verify_is_refused():
    for legal in LEGAL:
        assert bundle_v3.normalize_operations(legal) == legal
        assert worker.parse_operations(legal) == tuple(legal)
    for bad, code in [([], "JOB_OPERATIONS_INVALID"),
                      (["program", "erase"], "JOB_OPERATIONS_INVALID"),
                      (["erase", "erase"], "JOB_OPERATIONS_INVALID"),
                      (["read"], "JOB_OPERATIONS_INVALID"),
                      (["flash_cycle"], "JOB_OPERATIONS_INVALID"),
                      ("erase", "JOB_OPERATIONS_INVALID"),
                      (["erase", "verify"], "JOB_OPERATIONS_ERASE_VERIFY_UNSUPPORTED")]:
        with pytest.raises(bundle_v3.BundleBuildError, match=code):
            bundle_v3.normalize_operations(bad)
        with pytest.raises(worker.SiteWorkerDenied):
            worker.parse_operations(bad)


def test_binding_identity_carries_the_list_and_legacy_binding_is_unchanged():
    resource = bundle_v3.resource_set_descriptor(ops_route())
    asset = bundle_v3.image_asset_descriptor(resource, FW_A)
    legacy = bundle_v3.job_image_binding(resource, asset, ppu_id=PPU_ID, site_id=2,
                                         operation="flash_cycle")
    assert "operations" not in legacy  # the legacy identity gained no field
    full = ops_body(resource, ["erase", "program", "verify"], FW_A)["job_binding"]
    assert full["operation"] == "programming"
    assert full["operations"] == ["erase", "program", "verify"]
    assert full["range"] == legacy["range"]
    shas = {bundle_v3.sha256_hex(bundle_v3.canonical_json(
        ops_body(resource, ops, FW_A if bundle_v3.operations_take_image(ops) else None,
                 **({} if bundle_v3.operations_take_image(ops)
                    else {"address": BASE, "length": 1024}))["job_binding"]))
        for ops in LEGAL}
    assert len(shas) == len(LEGAL)  # every list is its own Binding identity
    # Erase-only: explicit erase-aligned range, never an Image.
    for kwargs, code in [({"address": BASE + 1, "length": 1024}, "JOB_RANGE_INVALID"),
                         ({"address": BASE, "length": 100}, "JOB_RANGE_INVALID"),
                         ({"address": BASE, "length": 65536 + 1024}, "JOB_RANGE_INVALID"),
                         ({}, "JOB_RANGE_REQUIRED")]:
        with pytest.raises(bundle_v3.BundleBuildError, match=code):
            ops_body(resource, ["erase"], None, **kwargs)
    with pytest.raises(bundle_v3.BundleBuildError, match="JOB_IMAGE_ASSET_NOT_ALLOWED"):
        ops_body(resource, ["erase"], FW_A)
    with pytest.raises(bundle_v3.BundleBuildError, match="JOB_IMAGE_ASSET_REQUIRED"):
        ops_body(resource, ["program"], None, address=BASE, length=1024)
    narrow = bundle_v3.resource_set_descriptor(ops_route(["flash_cycle", "program"]))
    with pytest.raises(bundle_v3.BundleBuildError, match="JOB_OPERATION_NOT_IN_PROFILE"):
        ops_body(narrow, ["erase", "program"], FW_A)


# ------------------------------------------------- one Job for every legal list

@pytest.mark.parametrize("operations", LEGAL, ids=lambda ops: "+".join(ops))
def test_every_legal_list_is_one_job_one_session_one_receipt(operations):
    takes_image = bundle_v3.operations_take_image(operations)

    async def scenario():
        with short_tmp() as folder:
            stack, resource = ops_stack(folder)
            async with stack:
                stack.sim.nor = True
                before = bytes(range(1, 255)) * 9  # non-blank, not FW_A
                if operations[0] in ("program", "verify"):
                    # P-only needs an erased IC; V-only needs the Image present.
                    seed = b"\xff" * len(FW_A) if operations[0] == "program" else FW_A
                else:
                    seed = before[:2048]
                stack.sim.memory[:len(seed)] = seed
                neighbour = bytes(stack.sim.memory[2048:4096])
                body = (ops_body(resource, operations, FW_A) if takes_image
                        else ops_body(resource, operations, None, address=BASE, length=2048))
                status, job = await submit(stack, body)
                assert status == 202, job
                assert job["state"] == "success", json.dumps(job)
                # ONE Job, ONE Worker session, ONE OpenOCD run for the whole list.
                assert job["operation"] == "programming"
                assert job["job_binding"]["operations"] == operations
                assert len(stack.sim.argvs) == 1
                opened = [r for r in stack.worker_requests if r["op"] == "open_job_session"]
                ran = [r for r in stack.worker_requests if r["op"] == "run"]
                assert len(opened) == 1 and len(ran) == 1
                assert opened[0]["provider_route"]["operation"] == "programming"
                assert opened[0]["provider_route"]["operations"] == operations
                assert ran[0]["operation"] == "programming"
                # Only the listed steps ran, in the fixed order; never flash_cycle.
                assert actions(stack.sim.argvs[0]) == EXPECTED_ACTIONS[tuple(operations)]
                details = job["result"]["details"]
                assert details["operations"] == operations and "flash_cycle" not in details
                evidence = details["programming"]
                assert evidence["result"] == "PASS" and evidence["safe_off"] is True
                assert evidence["operations"] == operations
                assert set(evidence["steps"]) == set(operations)
                assert evidence["job_binding_sha256"] == job["job_binding"]["job_binding_sha256"]
                steps = evidence["steps"]
                memory = bytes(stack.sim.memory)
                if "erase" in operations:
                    assert (steps["erase"]["erase_address"], steps["erase"]["erase_length"]) \
                        == (BASE, 1024 if takes_image else 2048)
                if operations == ["erase"]:
                    assert steps["erase"]["blank_verified"] is True
                    assert memory[:2048] == b"\xff" * 2048
                    assert job["result"]["image_sha256"] is None
                if "program" in operations:
                    assert steps["program"] == {
                        "write_address": BASE, "bytes_written": len(FW_A),
                        "image_sha256": hashlib.sha256(FW_A).hexdigest()}
                    assert memory[:len(FW_A)] == FW_A
                if "verify" in operations:
                    assert steps["verify"] == {
                        "verify_address": BASE, "bytes_verified": len(FW_A),
                        "readback_sha256": hashlib.sha256(FW_A).hexdigest()}
                if operations == ["verify"]:
                    assert memory[:len(FW_A)] == FW_A  # Verify never writes
                assert memory[2048:4096] == neighbour  # nothing outside the Job range
                status_now = stack.core.handle(
                    {"protocol": worker.PROTOCOL, "op": "status"},
                    (os.getpid(), 0, 0), "control")["result"]
                assert status_now["session"] is None and status_now["sealed_sites"] == []
                assert not stack.images.exists() or list(stack.images.iterdir()) == []
    run(scenario())


def test_program_only_never_erases_and_fails_on_a_non_erased_ic():
    async def scenario():
        with short_tmp() as folder:
            stack, resource = ops_stack(folder)
            async with stack:
                stack.sim.nor = True
                stack.sim.memory[:len(FW_B)] = FW_B  # IC already holds other data
                before = bytes(stack.sim.memory)
                status, job = await submit(stack, ops_body(resource, ["program"], FW_A))
                assert status == 202 and job["state"] != "success", job
                assert "OPENOCD_PROGRAM_FAILED" in json.dumps(job)
                [argv] = stack.sim.argvs
                assert actions(argv) == ["flash write_image"]  # no implicit erase
                assert not any(" erase" in c for c in commands(argv))
                assert bytes(stack.sim.memory) == before
                assert job["result"]["attempts"] == 1  # never auto-retried
                assert stack.core._sealed == set()  # SAFE_OFF proven: a definite FAIL
    run(scenario())


def test_verify_only_mismatch_is_a_safe_failure_and_never_writes():
    async def scenario():
        with short_tmp() as folder:
            stack, resource = ops_stack(folder)
            async with stack:
                stack.sim.memory[:len(FW_B)] = FW_B
                before = bytes(stack.sim.memory)
                status, job = await submit(stack, ops_body(resource, ["verify"], FW_A))
                assert status == 202 and job["state"] != "success", job
                assert "VERIFY_MISMATCH" in json.dumps(job)
                assert actions(stack.sim.argvs[0]) == ["dump_image"]
                assert bytes(stack.sim.memory) == before
                assert stack.core._sealed == set()
    run(scenario())


def test_erase_then_program_at_a_non_base_binding_address():
    async def scenario():
        with short_tmp() as folder:
            stack, resource = ops_stack(folder)
            async with stack:
                stack.sim.nor = True
                stack.sim.memory[:0x800] = b"\x00" * 0x800
                body = ops_body(resource, ["erase", "program", "verify"], FW_B,
                                load_address=BASE + 0x400)
                status, job = await submit(stack, body)
                assert status == 202 and job["state"] == "success", json.dumps(job)
                steps = job["result"]["details"]["programming"]["steps"]
                assert steps["erase"] == {"erase_address": BASE + 0x400, "erase_length": 1024}
                assert steps["program"]["write_address"] == BASE + 0x400
                assert bytes(stack.sim.memory[:0x400]) == b"\x00" * 0x400  # page 0 untouched
                assert bytes(stack.sim.memory[0x400:0x400 + len(FW_B)]) == FW_B
    run(scenario())


@pytest.mark.parametrize("fault, code", [
    ("forged_erase_report", "ERASE_RANGE_NOT_OBSERVED"),
    ("readback_corrupt", "VERIFY_MISMATCH"),
    ("erase_fails", "OPENOCD_ERASE_FAILED"),
    ("write_fails", "OPENOCD_PROGRAM_FAILED"),
])
def test_full_list_never_passes_without_proof_of_every_step(fault, code):
    async def scenario():
        with short_tmp() as folder:
            stack, resource = ops_stack(folder)
            async with stack:
                if fault == "forged_erase_report":
                    stack.sim.erase_report = (BASE + 0x400, 1024)
                elif fault == "readback_corrupt":
                    stack.sim.corrupt = True
                else:
                    stack.sim.fail_at = fault.split("_")[0]
                status, job = await submit(
                    stack, ops_body(resource, ["erase", "program", "verify"], FW_A))
                assert status == 202 and job["state"] != "success", job
                assert code in json.dumps(job)
                assert len(stack.sim.argvs) == 1 and job["result"]["attempts"] == 1
    run(scenario())


def test_worker_seals_a_write_whose_step_evidence_is_not_the_bound_range(tmp_path):
    """An Adapter PASS that does not prove the bound Image range is UNKNOWN."""
    class Lying(type(abi5_stub())):
        operations = frozenset({"programming", "read"})

        def run(self, site, operation, *, deadline, cancel, image=None, flash_range=None,
                operations=None):
            return {"result": "PASS", "safe_off": True, "operations": list(operations),
                    "steps": {"erase": {"erase_address": BASE, "erase_length": 1024},
                              "program": {"write_address": BASE + 4, "bytes_written": 4}}}

    images = tmp_path / "images"
    images.mkdir()
    (images / "job-lie.bin").write_bytes(b"DATA")
    core = worker.SiteWorkerCore(Lying(), runtime_pid=os.getpid,
                                 lease_verifier=lambda j, k: True,
                                 seal_dir=tmp_path / "seals", image_root=images)
    peer = (os.getpid(), os.getuid(), os.getgid())

    def call(op, **fields):
        return core.handle({"protocol": worker.PROTOCOL, "op": op, **fields}, peer, "control")

    opened = call("open_job_session", job_id="job-lie", sites=[2], max_runtime_s=30,
                  profile=PROFILE, provider_route=route_wire(["erase", "program"]),
                  deadline_monotonic=time.monotonic() + 10)
    assert opened["ok"], opened
    session = opened["result"]["session_id"]
    assert call("bind_image", session_id=session, image_size=4, load_address=BASE,
                image_sha256=hashlib.sha256(b"DATA").hexdigest())["ok"]
    reply = call("run", session_id=session, site=2, operation="programming")
    assert reply == {"ok": False, "error": "OUTCOME_UNKNOWN_SITE_SEALED:PROGRAM_RANGE_NOT_VERIFIED"}
    assert core._sealed == {2}


# ------------------------------------------------------------- fail closed

PROFILE = {"icpn": "STM32F103C8T6", "target_config": "target/stm32f1x.cfg",
           "flash_base": BASE, "flash_size": 65536, "erase_granularity": 1024}


def route_wire(operations=None, operation="programming"):
    route = {"asset_set_sha256": "a" * 64, "provider_package": "p",
             "profile_package": "profile", "descriptor_sha256": "b" * 64,
             "options_schema_sha256": "c" * 64, "options_sha256": "d" * 64,
             "operation": operation, "site_id": 2, "transport": "fpga",
             "driver_abi": "plasma_swd:5", "fpga_package": None, "max_image_bytes": 65536}
    if operations is not None:
        route["operations"] = operations
    return route


def test_worker_session_pins_the_list_and_binds_only_what_it_needs(tmp_path):
    class Ops(type(abi5_stub())):
        operations = frozenset({"probe", "flash_cycle", "programming", "read"})

    core = worker.SiteWorkerCore(Ops(), runtime_pid=os.getpid,
                                 lease_verifier=lambda j, k: True,
                                 seal_dir=tmp_path / "seals", image_root=tmp_path)
    peer = (os.getpid(), os.getuid(), os.getgid())
    serial = iter(range(100))

    def call(op, **fields):
        return core.handle({"protocol": worker.PROTOCOL, "op": op, **fields}, peer, "control")

    def open_(route, **extra):
        return call("open_job_session", job_id=f"job-{next(serial)}", sites=[2],
                    max_runtime_s=30, provider_route=route,
                    deadline_monotonic=time.monotonic() + 10, **extra)

    # The list is part of the route; missing, misordered or E+V lists never open.
    for bad, code in [(route_wire(), "PROVIDER_ROUTE_INVALID"),
                      (route_wire(["program", "erase"]), "OPERATIONS_INVALID"),
                      (route_wire([]), "OPERATIONS_INVALID"),
                      (route_wire(["erase", "verify"]), "OPERATIONS_ERASE_VERIFY_UNSUPPORTED"),
                      (route_wire(["erase"], operation="flash_cycle"), "PROVIDER_ROUTE_INVALID"),
                      (route_wire(["erase"], operation="read"), "PROVIDER_ROUTE_INVALID")]:
        assert open_(bad, profile=PROFILE) == {"ok": False, "error": code}
    assert open_(route_wire(["erase"])) == {"ok": False, "error": "PROFILE_REQUIRED"}
    assert core._sessions == {} and core._site_owners == {}

    def session(route):
        opened = open_(route, profile=PROFILE)
        assert opened["ok"], opened
        return opened["result"]["session_id"]

    def close(sid):
        assert call("close_session", session_id=sid)["ok"]

    # erase-only: a range, never an Image; whole erase units inside the bank.
    sid = session(route_wire(["erase"]))
    assert call("bind_image", session_id=sid, image_sha256="0" * 64, image_size=4,
                load_address=BASE)["error"] == "OPERATION_TAKES_NO_IMAGE"
    assert call("run", session_id=sid, site=2,
                operation="programming")["error"] == "RANGE_NOT_BOUND"
    for address, length in [(BASE + 4, 1024), (BASE, 1000), (BASE + 65536, 1024),
                            (BASE, 65536 + 1024), (BASE - 1024, 1024), (BASE, 0)]:
        assert call("bind_range", session_id=sid, address=address,
                    length=length)["error"] == "FLASH_RANGE_INVALID"
    bound = call("bind_range", session_id=sid, address=BASE + 1024, length=2048)
    assert bound["ok"] and bound["result"]["operation"] == "erase"
    assert call("bind_range", session_id=sid, address=BASE,
                length=1024)["error"] == "RANGE_ALREADY_BOUND"
    # The session runs only its own route operation.
    assert call("run", session_id=sid, site=2,
                operation="flash_cycle")["error"] == "PROVIDER_ROUTE_MISMATCH"
    close(sid)
    # A list with program / verify takes the Image, never a bare range.
    sid = session(route_wire(["program", "verify"]))
    assert call("bind_range", session_id=sid, address=BASE,
                length=1024)["error"] == "OPERATION_TAKES_NO_RANGE"
    assert call("run", session_id=sid, site=2,
                operation="programming")["error"] == "IMAGE_NOT_BOUND"
    close(sid)
    # read: any in-bank range (no erase alignment), never outside the Profile.
    sid = session(route_wire(operation="read"))
    for address, length in [(BASE - 1, 16), (BASE + 65536 - 8, 16), (0x40000000, 16), (BASE, 0)]:
        assert call("bind_range", session_id=sid, address=address,
                    length=length)["error"] == "FLASH_RANGE_INVALID"
    bound = call("bind_range", session_id=sid, address=BASE + 3, length=17)
    assert bound["ok"] and bound["result"]["operation"] == "read"
    close(sid)
    # The legacy flash_cycle session is unchanged and takes no range.
    sid = session(route_wire(operation="flash_cycle"))
    assert call("bind_range", session_id=sid, address=BASE,
                length=1024)["error"] == "OPERATION_TAKES_NO_RANGE"
    close(sid)
    assert core._sealed == set()


@pytest.mark.parametrize("case", ["erase_verify", "not_in_profile", "list_tampered",
                                  "operation_and_operations", "no_binding",
                                  "image_on_erase_only"])
def test_gateway_and_runtime_refuse_before_any_hardware_session(case):
    async def scenario():
        with short_tmp() as folder:
            stack, resource = ops_stack(
                folder, ["flash_cycle", "program", "verify"] if case == "not_in_profile" else ALL)
            async with stack:
                body = ops_body(resource, ["program", "verify"], FW_A)
                if case == "erase_verify":
                    body["operations"] = ["erase", "verify"]
                    body["job_binding"] = {**body["job_binding"],
                                           "operations": ["erase", "verify"]}
                elif case == "not_in_profile":
                    wide = bundle_v3.resource_set_descriptor(ops_route())
                    body = ops_body(wide, ["erase", "program"], FW_A)
                elif case == "list_tampered":
                    body["operations"] = ["erase", "program", "verify"]
                elif case == "operation_and_operations":
                    body["operation"] = "flash_cycle"
                elif case == "no_binding":
                    body = {"site_id": 2, "operations": ["erase"]}
                elif case == "image_on_erase_only":
                    erase = ops_body(resource, ["erase"], None, address=BASE, length=1024)
                    body = {**erase, "image_asset": body["image_asset"],
                            "asset_base64": body["asset_base64"]}
                status, received = await stack.api("POST", "/api/jobs", body)
                assert status != 202, received
                assert stack.sim.argvs == [] and not stack.core._sessions
                assert stack.manager.execution_lease_snapshot()["busy"] is False
    run(scenario())


def test_active_profile_that_does_not_declare_a_step_fails_closed_at_execution():
    """Even if admission were fooled, the pinned Active Profile decides."""
    async def scenario():
        with short_tmp() as folder:
            stack, _narrow = ops_stack(folder, ["flash_cycle"])
            async with stack:
                wide = bundle_v3.resource_set_descriptor(ops_route())
                active = stack.manager._active_resource_resolver()
                stack.manager._active_resource_resolver = lambda: {
                    **active, "resource_set": wide,
                    "resource_set_sha256": bundle_v3.resource_set_sha256(wide)}
                for body in (ops_body(wide, ["erase", "program", "verify"], FW_A),
                             job_body(wide, None, operation="read", address=BASE, length=64)):
                    status, job = await submit(stack, body)
                    assert status == 202 and job["state"] != "success", job
                    assert "OPERATION_UNSUPPORTED" in json.dumps(job)
                assert stack.sim.argvs == [] and not stack.core._sessions
    run(scenario())


def test_legacy_flash_cycle_job_is_unchanged_next_to_the_new_model():
    async def scenario():
        with short_tmp() as folder:
            stack, resource = ops_stack(folder)
            async with stack:
                status, job = await submit(stack, job_body(resource, FW_A))
                assert status == 202 and job["state"] == "success", json.dumps(job)
                assert job["operation"] == "flash_cycle"
                assert "operations" not in job["job_binding"]
                assert job["result"]["details"]["flash_cycle"]["result"] == "PASS"
                assert actions(stack.sim.argvs[0]) == [
                    "flash erase_address", "flash write_image", "flash verify_image",
                    "dump_image"]
                [opened] = [r for r in stack.worker_requests if r["op"] == "open_job_session"]
                assert "operations" not in opened["provider_route"]
    run(scenario())


# ------------------------------------------------------------------ read Job

def test_read_is_an_independent_job_with_a_verifiable_binary_output():
    async def scenario():
        with short_tmp() as folder:
            stack, resource = ops_stack(folder, in_process=False)
            async with stack:
                stack.sim.memory[:len(FW_B)] = FW_B
                before = bytes(stack.sim.memory)
                address, length = BASE + 5, 301  # no erase alignment needed
                status, job = await submit(
                    stack, job_body(resource, None, operation="read",
                                    address=address, length=length))
                assert status == 202 and job["state"] == "success", json.dumps(job)
                assert job["operation"] == "read" and job["job_binding"]["operation"] == "read"
                expected = before[5:5 + length]
                evidence = job["result"]["details"]["read"]
                assert evidence["result"] == "PASS" and evidence["safe_off"] is True
                assert (evidence["read_address"], evidence["read_length"],
                        evidence["bytes_read"]) == (address, length, length)
                assert evidence["sha256"] == hashlib.sha256(expected).hexdigest()
                assert "data" not in evidence and "data_base64" not in evidence
                [output] = job["result"]["output_files"]
                status, data = await stack.api(
                    "GET", f"/api/jobs/{job['job_id']}/files/{Path(output).name}")
                assert status == 200 and data == expected
                # Read never erases, writes or changes the IC.
                assert actions(stack.sim.argvs[0]) == ["dump_image"]
                assert bytes(stack.sim.memory) == before
    run(scenario())


@pytest.mark.parametrize("address, length", [
    (BASE - 16, 32), (BASE + 65536 - 8, 16), (0x40021000, 4), (BASE, 0), (BASE, 65537)])
def test_read_outside_the_profile_flash_range_is_never_bound(address, length):
    resource = bundle_v3.resource_set_descriptor(ops_route())
    with pytest.raises(bundle_v3.BundleBuildError, match="JOB_RANGE_INVALID"):
        job_body(resource, None, operation="read", address=address, length=length)


def test_read_result_that_does_not_match_its_sha256_is_a_safe_failure():
    async def scenario():
        with short_tmp() as folder:
            stack, resource = ops_stack(folder)
            async with stack:
                original = stack.adapter.run

                def tampered(site, operation, **kw):
                    result = dict(original(site, operation, **kw))
                    result["sha256"] = "0" * 64
                    return result

                stack.adapter.run = tampered
                status, job = await submit(
                    stack, job_body(resource, None, operation="read", address=BASE, length=64))
                assert status == 202 and job["state"] != "success", job
                assert "READ_RESULT_NOT_VERIFIED" in json.dumps(job)
                assert not job["result"].get("output_files")
                assert stack.core._sealed == set()  # a read cannot leave an unknown write
    run(scenario())


def test_read_is_refused_while_a_programming_job_owns_the_site():
    async def scenario():
        with short_tmp() as folder:
            stack, resource = ops_stack(folder)
            async with stack:
                gate = threading.Event()
                original = stack.sim.popen

                def slow(argv, **kw):
                    gate.wait(5)
                    return original(argv, **kw)

                stack.adapter._popen = slow
                status, first = await stack.api(
                    "POST", "/api/jobs", ops_body(resource, ["erase", "program", "verify"], FW_A))
                assert status == 202, first
                status, second = await stack.api(
                    "POST", "/api/jobs",
                    job_body(resource, None, operation="read", address=BASE, length=64))
                gate.set()
                job_id = first["job"]["job_id"]
                for _ in range(500):
                    _, result = await stack.api("GET", "/api/status?job=" + job_id)
                    if result["job"]["state"] in TERMINAL:
                        break
                    await asyncio.sleep(0.02)
                assert result["job"]["state"] == "success", json.dumps(result)
                assert status != 202, second  # the Site lease is not shared
                assert len(stack.sim.argvs) == 1
    run(scenario())
