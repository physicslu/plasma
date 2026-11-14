"""Host-only OFE-1B Gate 1: PPU Resource identity + independent Job Image.

* ``ppu_asset_set.read_active_resource_identity`` over a synthetic B3-verified
  staged tree of canonical Bundle v3 bytes (no ZIP install, no Root).
* Gateway Job Image source validation (``PlasmaWebHandler._job_request``).
* SiteManager Job Binding admission through the existing REST -> Runtime ->
  C-3 fake OpenOCD stack (injected Resource resolver; real resolver above).

No SWPC, Z2, PL, DUT, network device or real OpenOCD is accessed. Host-only
PASS is not evidence of Resource reuse on hardware.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from plasma_core.enums import Operation
from plasma_core.errors import PlasmaError
from plasma_opf import bundle_v3
from plasma_web.gateway_base import PlasmaWebHandler

from .test_c3_rest_flash_cycle import Stack, TERMINAL, run, short_tmp

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import ppu_asset_set as assets  # noqa: E402

ROUTE_PATH = ROOT / "data/opf/programming-routes/z2-site2-stm32f103c8t6.json"
FW_A = bytes(range(256)) * 4
FW_B = bytes(reversed(range(256))) * 3 + b"OFE-1B"


def route(**caps) -> bundle_v3.ProgrammingRoute:
    data = json.loads(ROUTE_PATH.read_text())
    data["profile"]["capabilities"].update(caps)
    return bundle_v3.parse_route(data)


# ------------------------------------------------------------ PPU Resource identity
def stage_bundle(product: Path, built: bundle_v3.ProgrammingBundle, *, generation=1,
                 activate=True) -> str:
    """Write canonical Bundle bytes as a B3-verified staged Set (synthetic receipt)."""
    stage = product / "assets/staged" / built.archive_sha256
    with zipfile.ZipFile(io.BytesIO(built.archive)) as archive:
        names = [n for n in archive.namelist() if not n.endswith("/")]
        for name in names:
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name))
    manifest_raw = (stage / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    (stage / "b3-install.json").write_text(json.dumps({
        "schema": "plasma.ppu.b3-install.v1", "archive_sha256": built.archive_sha256,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "bundle_name": manifest["name"], "bundle_version": manifest["version"],
        "files_verified": len(names) - 1}))
    if activate:
        (product / "assets/active.json").write_text(json.dumps({
            "schema": assets.SCHEMA, "generation": generation,
            "asset_set_sha256": built.archive_sha256}))
    return built.archive_sha256


def test_ppu_derives_same_resource_for_firmware_a_and_b(tmp_path):
    r = route()
    bundle_a = bundle_v3.build_user_image_bundle(r, FW_A)
    bundle_b = bundle_v3.build_user_image_bundle(r, FW_B)
    product_a, product_b = tmp_path / "a", tmp_path / "b"
    stage_bundle(product_a, bundle_a)
    stage_bundle(product_b, bundle_b, generation=7)
    a = assets.read_active_resource_identity(product_a)
    b = assets.read_active_resource_identity(product_b)
    assert a["state"] == b["state"] == "VERIFIED"
    assert bundle_a.archive_sha256 != bundle_b.archive_sha256
    assert a["resource_set_sha256"] == b["resource_set_sha256"] == bundle_a.resource_set_sha256
    assert (a["asset_set_sha256"], a["generation"]) == (bundle_a.archive_sha256, 1)
    assert (b["asset_set_sha256"], b["generation"]) == (bundle_b.archive_sha256, 7)
    assert a["resource_set"] == bundle_v3.resource_set_descriptor(r)


@pytest.mark.parametrize("caps", [
    {"driver_abi": "plasma_swd:6"},
    {"max_image_bytes": 32768},
    {"operations": ["flash_cycle", "erase"]},
])
def test_different_profile_or_driver_abi_is_a_different_resource(tmp_path, caps):
    base = bundle_v3.build_user_image_bundle(route(), FW_A)
    other = bundle_v3.build_user_image_bundle(route(**caps), FW_A)
    stage_bundle(tmp_path, other)
    derived = assets.read_active_resource_identity(tmp_path)
    assert derived["resource_set_sha256"] == other.resource_set_sha256
    assert derived["resource_set_sha256"] != base.resource_set_sha256


def test_empty_active_set_has_no_resource_identity(tmp_path):
    (tmp_path / "assets").mkdir()
    with pytest.raises(assets.AssetSetError, match="RESOURCE_NOT_ACTIVE"):
        assets.read_active_resource_identity(tmp_path)


def test_tampered_provider_file_fails_before_identity(tmp_path):
    built = bundle_v3.build_user_image_bundle(route(), FW_A)
    digest = stage_bundle(tmp_path, built)
    options = (tmp_path / "assets/staged" / digest / "payload/packages"
               / "openocd-platform-reference/data/plasma-provider-options.json")
    options.write_bytes(options.read_bytes().replace(b"object", b"objeKt"))
    with pytest.raises(assets.AssetSetError):
        assets.read_active_resource_identity(tmp_path)


def test_non_canonical_or_mixed_set_fails_closed(tmp_path):
    from .test_ppu_bundle_firmware_job_gate1 import active_set
    product, _ = active_set(tmp_path)  # hand-built Provider/Profile, not writer output
    assert assets.read_active(product)["state"] == "ACTIVE"
    with pytest.raises(assets.AssetSetError, match="RESOURCE_IDENTITY_INVALID"):
        assets.read_active_resource_identity(product)


def test_generation_change_during_derivation_fails_closed(tmp_path, monkeypatch):
    built = bundle_v3.build_user_image_bundle(route(), FW_A)
    stage_bundle(tmp_path, built)
    original = assets.read_active
    calls = []

    def drifting(product_root):
        result = original(product_root)
        calls.append(1)
        if len(calls) > 1:
            result = {**result, "generation": result["generation"] + 1}
        return result

    monkeypatch.setattr(assets, "read_active", drifting)
    with pytest.raises(assets.AssetSetError, match="ACTIVE_SET_CHANGED"):
        assets.read_active_resource_identity(tmp_path)


# ------------------------------------------------------------- Gateway Job Image
PPU_ID = "local-ppu"


def binding_for(resource, image: bytes | None, *, operation="flash_cycle", site=2,
                ppu_id=PPU_ID, address=None, length=None, load_address=None):
    asset = None if image is None else bundle_v3.image_asset_descriptor(
        resource, image, load_address=load_address)
    binding = bundle_v3.job_image_binding(resource, asset, ppu_id=ppu_id, site_id=site,
                                          operation=operation, address=address, length=length)
    return asset, binding


def job_body(resource, image: bytes | None, *, operation="flash_cycle", **kw):
    asset, binding = binding_for(resource, image, operation=operation, **kw)
    kinds = {p["kind"]: p["id"] for p in resource["packages"]}
    body = {"site_id": kw.get("site", 2), "operation": operation,
            "target": resource["constraints"]["icpn"],
            "provider": kinds["platform-provider"], "profile": kinds["programming-profile"],
            "job_binding": binding}
    if image is not None:
        body.update(image_asset=asset, asset_base64=base64.b64encode(image).decode())
    return body


def gateway_request(body):
    return object.__new__(PlasmaWebHandler)._job_request(body, client_id="plasma-web")


WIDE = bundle_v3.resource_set_descriptor(route(
    operations=["flash_cycle", "erase", "program", "verify", "read"]))


def test_gateway_accepts_exclusive_job_image_source():
    request = gateway_request(job_body(WIDE, FW_A))
    assert request.operation is Operation.FLASH_CYCLE and request.image == FW_A
    assert request.max_retries == 0 and request.image_ref is None
    assert request.metadata["job_binding"]["operation"] == "flash_cycle"
    assert request.metadata["job_image_asset"]["sha256"] == hashlib.sha256(FW_A).hexdigest()
    assert not {"bundle_asset_set_sha256", "bundle_asset_sha256"} & set(request.metadata)


def test_gateway_read_and_erase_take_range_from_binding_without_image():
    read = gateway_request(job_body(WIDE, None, operation="read",
                                    address=0x08000100, length=64))
    assert read.operation is Operation.READ and read.image == b""
    assert read.map_data == {"sections": [{"name": "flash", "address": 0x08000100,
                                           "length": 64}]}
    erase = gateway_request(job_body(WIDE, None, operation="erase",
                                     address=0x08000000, length=2048))
    assert erase.operation is Operation.ERASE and "job_image_asset" not in erase.metadata


def _tamper(body, path, value):
    body = copy.deepcopy(body)
    target = body
    for key in path[:-1]:
        target = target[key]
    if value is KeyError:
        target.pop(path[-1])
    else:
        target[path[-1]] = value
    return body


@pytest.mark.parametrize("path, value", [
    (("image_asset", "sha256"), "0" * 64),                          # SHA mismatch
    (("image_asset", "size"), len(FW_A) + 1),                       # size mismatch
    (("image_asset", "format"), "intel_hex"),                       # format unsupported
    (("asset_base64",), base64.b64encode(FW_B).decode()),           # payload differs
    (("asset_base64",), "%%%"),
    (("job_binding", "operation"), "program"),                      # Operation mismatch
    (("operation",), "program"),
    (("job_binding", "site_id"), 1),
    (("job_binding", "icpn"), "STM32F103CBT6"),                     # Target mismatch
    (("target",), "STM32F103CBT6"),
    (("profile",), "other-profile"),
    (("job_binding", "image_asset_sha256"), "1" * 64),
    (("image_asset",), KeyError),
    (("job_binding",), KeyError),
    (("asset_set_sha256",), "a" * 64),                              # mixed with Bundle ref
    (("asset_name",), "fw.bin"),                                    # mixed with legacy inline
    (("offset",), 0),                                               # range only from Binding
])
def test_gateway_refuses_inconsistent_job_image(path, value):
    with pytest.raises((ValueError, PlasmaError)):
        gateway_request(_tamper(job_body(WIDE, FW_A), path, value))


def test_gateway_refuses_image_on_read_and_unapproved_operations():
    body = job_body(WIDE, None, operation="read", address=0x08000000, length=16)
    with pytest.raises(ValueError):
        gateway_request({**body, "asset_base64": base64.b64encode(FW_A).decode()})
    for op in ("blank_check", "probe"):
        with pytest.raises(ValueError):
            gateway_request({**job_body(WIDE, FW_A), "operation": op})


# ----------------------------------------------- SiteManager admission (REST -> C-3)
C3_PROVIDER = "openocd-reference"
C3_PROFILE = "stm32f103-c8"


def stack_resource(**caps) -> dict:
    data = json.loads(ROUTE_PATH.read_text())
    data["provider"]["id"] = C3_PROVIDER
    data["profile"]["id"] = C3_PROFILE
    data["profile"]["capabilities"]["provider_package"] = C3_PROVIDER
    data["profile"]["capabilities"].update(caps)
    return bundle_v3.resource_set_descriptor(bundle_v3.parse_route(data))


def install_resolver(stack, resource, *, generation_delta=0, calls=None):
    active = assets.read_active(stack.opf["product_root"])

    def resolver():
        if calls is not None:
            calls.append(1)
        return {"schema": assets.RESOURCES_SCHEMA, "state": "VERIFIED",
                "asset_set_sha256": active["asset_set_sha256"],
                "generation": active["generation"] + generation_delta,
                "resource_set": resource,
                "resource_set_sha256": bundle_v3.resource_set_sha256(resource)}

    stack.manager._active_resource_resolver = resolver
    return active


async def submit(stack, body):
    status, received = await stack.api("POST", "/api/jobs", body)
    if status != 202:
        return status, received
    job_id = received["job"]["job_id"]
    for _ in range(500):
        _, result = await stack.api("GET", "/api/status?job=" + job_id)
        if result["job"]["state"] in TERMINAL:
            return status, result["job"]
        await asyncio.sleep(0.02)
    raise AssertionError("Host-only C3 Job not terminal")


def test_firmware_a_then_b_reuse_same_active_resources_on_c3():
    async def scenario():
        with short_tmp() as folder:
            async with Stack(Path(folder), in_process=True) as stack:
                resource = stack_resource()
                calls = []
                active = install_resolver(stack, resource, calls=calls)
                # Same Active Set + same Resources, two different Images.
                for firmware in (FW_A, FW_B):
                    body = job_body(resource, firmware)
                    status, job = await submit(stack, body)
                    assert status == 202, job
                    assert job["state"] == "success", json.dumps(job)
                    cycle = job["result"]["details"]["flash_cycle"]
                    assert cycle["result"] == "PASS" and cycle["safe_off"] is True
                    assert cycle["readback_sha256"] == hashlib.sha256(firmware).hexdigest()
                    assert job["result"]["image_sha256"] == hashlib.sha256(firmware).hexdigest()
                    echo = job["job_binding"]
                    assert echo["job_binding_sha256"] == bundle_v3.sha256_hex(
                        bundle_v3.canonical_json(body["job_binding"]))
                    assert echo["resource_set_sha256"] == bundle_v3.resource_set_sha256(resource)
                    assert echo["asset_set_sha256"] == active["asset_set_sha256"]
                    assert echo["generation"] == active["generation"]
                    assert bytes(stack.sim.memory[:len(firmware)]) == firmware
                assert len(stack.sim.argvs) == 2 and len(calls) == 2
                # Active Set unchanged: no activation, no FPGA reload.
                assert assets.read_active(stack.opf["product_root"]) == active
                status, ppu = await stack.api("GET", "/api/status?site=2")
                report = ppu["ppu"]["active_resources"]
                assert report["state"] == "VERIFIED"
                assert report["resource_set_sha256"] == bundle_v3.resource_set_sha256(resource)
                _, unscoped = await stack.api("GET", "/api/status")
                assert "active_resources" not in unscoped["ppu"]
    run(scenario())


def _denied(stack, body, expect):
    async def go():
        status, received = await stack.api("POST", "/api/jobs", body)
        assert status != 202, received
        assert expect in json.dumps(received), received
        assert stack.sim.argvs == []
    return go()


@pytest.mark.parametrize("case, expect", [
    ("wrong_ppu", "JOB_BINDING_MISMATCH"),
    ("foreign_profile", "JOB_BINDING_MISMATCH"),     # Manager claims other Resources
    ("foreign_driver_abi", "JOB_BINDING_MISMATCH"),
    ("generation_moved", "JOB_RESOURCE_ACTIVE_SET_CHANGED"),
    ("provider_mismatch", "JOB_RESOURCE_PACKAGE_MISMATCH"),
    ("not_wired", "JOB_RESOURCE_IDENTITY_NOT_WIRED"),
    ("resolver_fails", "JOB_RESOURCE_IDENTITY_UNAVAILABLE"),
    # A single erase / program is never a Job of its own on C-3: they are
    # steps of one ``programming`` Job (tests/test_c3_programming_operations.py).
    ("erase_backend", "separate erase Job is not offered"),
    ("program_backend", "separate program Job is not offered"),
    ("not_in_profile", "JOB_OPERATION_NOT_IN_PROFILE"),
    ("fpga_reload_lock", "quiesced"),
])
def test_unsafe_or_unproven_job_binding_never_opens_c3(case, expect):
    async def scenario():
        with short_tmp() as folder:
            async with Stack(Path(folder), in_process=True) as stack:
                wide = stack_resource(operations=["flash_cycle", "erase", "program", "read"])
                resource = wide if case.endswith("_backend") else stack_resource()
                install_resolver(stack, resource,
                                 generation_delta=1 if case == "generation_moved" else 0)
                body = job_body(resource, FW_A)
                if case == "wrong_ppu":
                    body = job_body(resource, FW_A, ppu_id="other-ppu")
                elif case == "foreign_profile":
                    body = job_body(stack_resource(max_image_bytes=32768), FW_A)
                elif case == "foreign_driver_abi":
                    body = job_body(stack_resource(driver_abi="plasma_swd:6"), FW_A)
                elif case == "provider_mismatch":
                    body["provider"] = "openocd-platform-reference"
                elif case == "not_wired":
                    stack.manager._active_resource_resolver = None
                elif case == "resolver_fails":
                    def fail():
                        raise assets.AssetSetError("ASSET_SET_RESOURCE_IDENTITY_INVALID:X")
                    stack.manager._active_resource_resolver = fail
                elif case == "erase_backend":
                    body = job_body(resource, None, operation="erase",
                                    address=0x08000000, length=1024)
                elif case == "program_backend":
                    body = job_body(resource, FW_A, operation="program")
                elif case == "not_in_profile":
                    body = job_body(wide, None, operation="erase",
                                    address=0x08000000, length=1024)
                elif case == "fpga_reload_lock":
                    stack.manager.acquire_asset_set_quiesce()
                await _denied(stack, body, expect)
                assert stack.manager.execution_lease_snapshot()["busy"] is False \
                    or case == "fpga_reload_lock"
    run(scenario())


# --------------------------- Job Binding address end to end (OFE-1B PR-A, Gate 1 B)
SECOND_PAGE = 0x08000400
FLASH_RANGE_FIELDS = ("load_address", "erase_address", "erase_length",
                      "write_address", "verify_address", "readback_address")


def c3_route() -> bundle_v3.ProgrammingRoute:
    data = json.loads(ROUTE_PATH.read_text())
    data["provider"]["id"] = C3_PROVIDER
    data["profile"]["id"] = C3_PROFILE
    data["profile"]["capabilities"]["provider_package"] = C3_PROVIDER
    return bundle_v3.parse_route(data)


def route_stack(folder):
    """C-3 stack whose Active Set is a canonical route-built Bundle (FW_A), so
    the Runtime uses the REAL ``read_active_resource_identity`` resolver."""
    built = bundle_v3.build_user_image_bundle(c3_route(), FW_A)
    return Stack(Path(folder), in_process=True,
                 bundle_options={"programming_bundle": built}), built


def test_real_resolver_reuses_resources_and_writes_firmware_b_at_its_binding_address():
    async def scenario():
        with short_tmp() as folder:
            stack, built = route_stack(folder)
            async with stack:
                resource = bundle_v3.resource_set_descriptor(c3_route())
                assert stack.manager._active_resource_resolver is not None
                status, ppu = await stack.api("GET", "/api/status?site=2")
                report = ppu["ppu"]["active_resources"]
                assert report["state"] == "VERIFIED", report
                assert report["resource_set_sha256"] == built.resource_set_sha256 \
                    == bundle_v3.resource_set_sha256(resource)
                # A at flash_base, then B (same Resources) at the next page.
                for firmware, address in ((FW_A, 0x08000000), (FW_B, SECOND_PAGE)):
                    body = job_body(resource, firmware, load_address=address)
                    assert body["job_binding"]["range"] == {"address": address,
                                                            "length": len(firmware)}
                    status, job = await submit(stack, body)
                    assert status == 202, job
                    assert job["state"] == "success", json.dumps(job)
                    cycle = job["result"]["details"]["flash_cycle"]
                    erase_length = -(-len(firmware) // 1024) * 1024
                    assert {k: cycle[k] for k in FLASH_RANGE_FIELDS} == {
                        "load_address": address, "erase_address": address,
                        "erase_length": erase_length, "write_address": address,
                        "verify_address": address, "readback_address": address}
                    assert cycle["job_binding_sha256"] == job["job_binding"]["job_binding_sha256"]
                    commands = [a for a in stack.sim.argvs[-1] if a.startswith(
                        ("flash erase_address", "flash write_image", "flash verify_image",
                         "dump_image"))]
                    assert commands[0] == f"flash erase_address 0x{address:08x} 0x{erase_length:08x}"
                    assert all(f" 0x{address:08x} " in c for c in commands[1:])
                # B landed on page 1 and page 0 still holds A: flash_base was not reused.
                assert bytes(stack.sim.memory[:len(FW_A)]) == FW_A
                assert bytes(stack.sim.memory[0x400:0x400 + len(FW_B)]) == FW_B
                assert len(stack.sim.argvs) == 2
                assert assets.read_active(stack.opf["product_root"])["asset_set_sha256"] \
                    == built.archive_sha256
    run(scenario())


@pytest.mark.parametrize("fault", ["forged_erase_report", "write_lands_elsewhere",
                                   "readback_corrupt"])
def test_non_base_job_never_passes_unless_the_executed_range_is_proven(fault):
    async def scenario():
        with short_tmp() as folder:
            stack, _built = route_stack(folder)
            async with stack:
                resource = bundle_v3.resource_set_descriptor(c3_route())
                if fault == "forged_erase_report":
                    stack.sim.erase_report = (0x08000000, 1024)  # OpenOCD erased page 0
                elif fault == "write_lands_elsewhere":
                    stack.sim.write_skew = 0x400
                else:
                    stack.sim.corrupt = True
                status, job = await submit(
                    stack, job_body(resource, FW_B, load_address=SECOND_PAGE))
                assert status == 202, job
                assert job["state"] != "success", json.dumps(job)
                text = json.dumps(job)
                expect = {"forged_erase_report": "FLASH_RANGE_NOT_OBSERVED",
                          "write_lands_elsewhere": "OPENOCD_FLASH_FAILED",
                          "readback_corrupt": "READBACK_MISMATCH"}[fault]
                assert expect in text, text
    run(scenario())


def test_binding_window_outside_the_bank_is_refused_before_c3():
    async def scenario():
        with short_tmp() as folder:
            stack, _built = route_stack(folder)
            async with stack:
                resource = bundle_v3.resource_set_descriptor(c3_route())
                # Internally consistent forgery: Image bytes fit the last page's
                # start, but the rounded erase window (2 pages) crosses the end.
                image = FW_A + b"!"
                last = 0x08000000 + 0x10000 - 1024
                asset = {"schema": bundle_v3.IMAGE_ASSET_SCHEMA, "format": "binary",
                         "sha256": hashlib.sha256(image).hexdigest(), "size": len(image),
                         "load_address": last, "icpn": resource["constraints"]["icpn"]}
                forged = job_body(resource, image)
                forged["image_asset"] = asset
                forged["job_binding"]["image_asset_sha256"] = bundle_v3.image_asset_sha256(asset)
                forged["job_binding"]["range"] = {"address": last, "length": len(image)}
                status, received = await stack.api("POST", "/api/jobs", forged)
                assert status != 202, received
                assert "IMAGE_ASSET_ADDRESS_INVALID" in json.dumps(received), received
                assert stack.sim.argvs == []
    run(scenario())


def test_busy_site_and_running_job_block_a_second_binding_job():
    async def scenario():
        with short_tmp() as folder:
            async with Stack(Path(folder), in_process=True) as stack:
                resource = stack_resource()
                install_resolver(stack, resource)
                # Activation (FPGA reload) cannot start while a Job holds the lease.
                status, received = await stack.api("POST", "/api/jobs", job_body(resource, FW_A))
                assert status == 202, received
                with pytest.raises(Exception) as caught:
                    stack.manager.acquire_asset_set_quiesce()
                assert "PPU execution active" in str(caught.value)
                job_id = received["job"]["job_id"]
                for _ in range(500):
                    _, result = await stack.api("GET", "/api/status?job=" + job_id)
                    if result["job"]["state"] in TERMINAL:
                        break
                    await asyncio.sleep(0.02)
                assert result["job"]["state"] == "success"
                assert len(stack.sim.argvs) == 1  # exactly one submission, no auto retry
    run(scenario())
