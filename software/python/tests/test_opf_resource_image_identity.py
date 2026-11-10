"""Host-only OFE-1A: Programming Resource Set vs Job Firmware Asset identity.

No PPU, Bootstrap, FPGA, DUT or real Flash. The staged Active Set built here
is a synthetic B3-receipt fixture from canonical Bundle bytes, not live B3
proof. These identities are informational: every test that touches the
execution path proves the Bundle archive SHA256 is still the only authority.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from plasma_opf import bundle_v3
from plasma_opf.bundle_v3 import BundleBuildError
from plasma_web.gateway_base import PlasmaWebHandler

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppu_asset_set as assets  # noqa: E402
import ppu_unified_deployment  # noqa: E402
from test_bundle_programming_workflow import (  # noqa: E402
    ALIAS, FakeCoordinator, FakeGateway, image, make, plan_body, run_once,
)
from plasma_manager.programming import CONFIRM_TOKEN  # noqa: E402

ROUTES = ROOT / "data/opf/programming-routes"
FW_A = bytes(range(256)) * 4
FW_B = bytes(reversed(range(256))) * 4 + b"\x01"


def route():
    return bundle_v3.load_route(ROUTES / "z2-site2-stm32f103c8t6.json")


def route_payload():
    return json.loads((ROUTES / "z2-site2-stm32f103c8t6.json").read_text())


def resource():
    return bundle_v3.resource_set_descriptor(route())


def zip_members(archive: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        return {name: bundle.read(name) for name in bundle.namelist()}


# ------------------------------------------------------------------ positive
def test_same_resources_different_firmware_same_resource_identity():
    a = bundle_v3.build_user_image_bundle(route(), FW_A, filename="a.bin")
    b = bundle_v3.build_user_image_bundle(route(), FW_B, filename="other-name.bin")
    assert a.archive_sha256 != b.archive_sha256  # Bundle identity still couples them
    assert a.resource_set_sha256 == b.resource_set_sha256
    assert a.image_asset_sha256 != b.image_asset_sha256
    # Identity derived from the actual archive bytes agrees with the writer.
    for built, payload in ((a, FW_A), (b, FW_B)):
        res, fw = bundle_v3.identity_from_archive(built.archive)
        assert bundle_v3.resource_set_sha256(res) == built.resource_set_sha256
        assert bundle_v3.image_asset_sha256(fw) == built.image_asset_sha256
        assert fw["sha256"] == hashlib.sha256(payload).hexdigest()
        assert fw["size"] == len(payload) and fw["load_address"] == 0x08000000


def test_firmware_filename_and_package_naming_do_not_affect_identities():
    one = bundle_v3.build_image_bundle(route(), FW_A, image_filename="x.bin",
                                       asset_package_id="fw-one", bundle_name="bundle-one")
    two = bundle_v3.build_image_bundle(route(), FW_A, image_filename="y.bin",
                                       asset_package_id="fw-two", bundle_name="bundle-two",
                                       version="9.9.9")
    assert one.archive_sha256 != two.archive_sha256
    assert one.resource_set_sha256 == two.resource_set_sha256
    assert one.image_asset_sha256 == two.image_asset_sha256


def test_identity_is_deterministic_and_canonical():
    first = [bundle_v3.resource_set_sha256(resource()) for _ in range(3)]
    assert len(set(first)) == 1
    shuffled = json.loads(json.dumps(resource()))
    shuffled = dict(reversed(list(shuffled.items())))
    assert bundle_v3.resource_set_sha256(shuffled) == first[0]
    fw = [bundle_v3.image_asset_sha256(bundle_v3.image_asset_descriptor(resource(), FW_A))
          for _ in range(3)]
    assert len(set(fw)) == 1
    descriptor = resource()
    assert descriptor["fpga_package"] is None
    assert [p["kind"] for p in descriptor["packages"]] == ["platform-provider", "programming-profile"]
    assert descriptor["abi"] == {"driver_abi": "plasma_swd:5", "transport": "fpga"}


def test_bundle_v3_wire_and_writer_bytes_unchanged():
    built = bundle_v3.build_image_bundle(
        route(), image(), image_filename="plasma-blue-pill-cdc.bin",
        asset_package_id="bluepill-cdc-fw-v01", bundle_name="bluepill-site2-fw-v01")
    assert built.archive_sha256 == "71e9a044c7f45d0f6e608c2727961f6ada220b483225bd20b928bf06f289946a"
    manifest = json.loads(zip_members(built.archive)["manifest.json"])
    assert manifest["schema"] == "plasma.ppu.bundle.v3"
    assert "resource_set_sha256" not in json.dumps(manifest)  # no wire-schema change
    assert built.summary()["identity_authority"] == "archive_sha256"


@pytest.mark.parametrize("mutate", [
    lambda r: r["provider"]["options"]["options"].update(extra={"type": "string"}),
    lambda r: r["provider"].update(version="1.0.1"),
    lambda r: r["profile"].update(version="1.0.1"),
    lambda r: r["profile"]["capabilities"].update(driver_abi="plasma_swd:6"),
    lambda r: r["profile"]["capabilities"].update(sites=[2, 3]),
    lambda r: r["profile"]["capabilities"].update(max_image_bytes=32768),
    lambda r: r["profile"]["flash_profile"].update(target_config="target/other.cfg"),
    lambda r: r["profile"]["flash_profile"].update(erase_granularity=2048),
    lambda r: r["target"].update(board="pynq-z1"),
    lambda r: r["target"].update(fpga_part="xc7z010clg400-1"),
])
def test_any_resource_change_changes_resource_identity(mutate):
    baseline = bundle_v3.resource_set_sha256(resource())
    payload = route_payload()
    mutate(payload)
    changed = bundle_v3.resource_set_descriptor(bundle_v3.parse_route(payload))
    assert bundle_v3.resource_set_sha256(changed) != baseline


def test_fpga_and_dependency_changes_change_resource_identity():
    base = resource()
    fpga = copy.deepcopy(base)
    fpga["packages"].append({"id": "fpga-a", "kind": "fpga-image", "version": "1.0.0",
                             "requires": [], "files": [{
                                 "path": "payload/packages/fpga-a/data/top.bit", "size": 4,
                                 "sha256": "1" * 64, "executable": False}]})
    fpga["fpga_package"] = "fpga-a"
    other = copy.deepcopy(fpga)
    other["packages"][-1]["files"][0]["sha256"] = "2" * 64
    shas = {bundle_v3.resource_set_sha256(d) for d in (base, fpga, other)}
    assert len(shas) == 3
    dep = copy.deepcopy(fpga)
    dep["packages"][-1]["requires"] = [base["packages"][0]["id"]]
    assert bundle_v3.resource_set_sha256(dep) not in shas


def test_job_binding_is_exact_and_verifiable():
    res = resource()
    fw = bundle_v3.image_asset_descriptor(res, FW_A)
    binding = bundle_v3.job_image_binding(res, fw, ppu_id="z2-hil", site_id=2,
                                          operation="flash_cycle")
    assert binding["resource_set_sha256"] == bundle_v3.resource_set_sha256(res)
    assert binding["image_asset_sha256"] == bundle_v3.image_asset_sha256(fw)
    assert binding["profile"] == "stm32f103c8t6-site2" and binding["icpn"] == "STM32F103C8T6"
    assert binding["operation"] == "flash_cycle"
    assert binding["range"] == {"address": 0x08000000, "length": len(FW_A)}
    digest = bundle_v3.verify_job_binding(binding, res, fw, ppu_id="z2-hil", site_id=2,
                                          operation="flash_cycle")
    assert len(digest) == 64
    fw_b = bundle_v3.image_asset_descriptor(res, FW_B)
    for kwargs, fw_x in (({"ppu_id": "other-ppu", "site_id": 2, "operation": "flash_cycle"}, fw),
                         ({"ppu_id": "z2-hil", "site_id": 2, "operation": "flash_cycle"}, fw_b)):
        with pytest.raises(BundleBuildError, match="JOB_BINDING_MISMATCH"):
            bundle_v3.verify_job_binding(binding, res, fw_x, **kwargs)


def test_staged_active_set_reproduces_resource_identity(tmp_path):
    built = bundle_v3.build_user_image_bundle(route(), FW_A, filename="a.bin")
    product, stage = stage_active(tmp_path, built)
    manifest = json.loads((stage / "manifest.json").read_bytes())
    sha = bundle_v3.verify_resource_set(resource(), manifest,
                                        lambda path: (stage / path).read_bytes())
    assert sha == built.resource_set_sha256


# ------------------------------------------------------------------ negative
def tampered_archive(built, path_suffix: str, new: bytes, *, fix_manifest: bool) -> bytes:
    members = zip_members(built.archive)
    manifest = json.loads(members["manifest.json"])
    (path,) = [p for p in members if p.endswith(path_suffix)]
    members[path] = new
    if fix_manifest:
        for package in manifest["packages"]:
            for entry in package["files"]:
                if entry["path"] == path:
                    entry.update(size=len(new), sha256=hashlib.sha256(new).hexdigest())
    members["manifest.json"] = bundle_v3.canonical_json(manifest)
    return bundle_v3.canonical_zip(members)


@pytest.mark.parametrize("suffix, mutate", [
    ("plasma-provider-options.json", lambda o: o["options"].update(x=1)),
    ("plasma-provider.json", lambda o: o.update(driver_abi="plasma_swd:6")),
    ("plasma-provider.json", lambda o: o.update(sites=[1, 2])),
    ("plasma-flash-profile.json", lambda o: o.update(flash_base=0)),
])
def test_provider_profile_driver_or_constraint_substitution_is_resource_mismatch(suffix, mutate):
    built = bundle_v3.build_user_image_bundle(route(), FW_A)
    member = json.loads([v for k, v in zip_members(built.archive).items() if k.endswith(suffix)][0])
    mutate(member)
    # Consistent manifest (attacker recomputed hashes): identity differs -> mismatch.
    forged = tampered_archive(built, suffix, bundle_v3.canonical_json(member), fix_manifest=True)
    res, _fw = bundle_v3.identity_from_archive(forged)
    assert bundle_v3.resource_set_sha256(res) != built.resource_set_sha256
    with zipfile.ZipFile(io.BytesIO(forged)) as z:
        manifest = json.loads(z.read("manifest.json"))
        with pytest.raises(BundleBuildError, match="RESOURCE_SET_MISMATCH"):
            bundle_v3.verify_resource_set(resource(), manifest, z.read)
    # Bytes swapped without updating the manifest SHA -> file mismatch.
    swapped = tampered_archive(built, suffix, bundle_v3.canonical_json(member), fix_manifest=False)
    with pytest.raises(BundleBuildError, match="BUNDLE_FILE_MISMATCH"):
        bundle_v3.identity_from_archive(swapped)


def test_non_canonical_resource_bytes_fail_closed():
    built = bundle_v3.build_user_image_bundle(route(), FW_A)
    raw = [v for k, v in zip_members(built.archive).items()
           if k.endswith("plasma-provider.json")][0]
    pretty = json.dumps(json.loads(raw), indent=2).encode()
    forged = tampered_archive(built, "plasma-provider.json", pretty, fix_manifest=True)
    with pytest.raises(BundleBuildError, match="BUNDLE_RESOURCE_NOT_CANONICAL"):
        bundle_v3.identity_from_archive(forged)


def test_firmware_substitution_in_archive_is_detected():
    built = bundle_v3.build_user_image_bundle(route(), FW_A)
    with pytest.raises(BundleBuildError, match="BUNDLE_FILE_MISMATCH"):
        bundle_v3.identity_from_archive(tampered_archive(built, ".bin", FW_B, fix_manifest=False))


@pytest.mark.parametrize("change, code", [
    ({"sha256": "0" * 64}, "IMAGE_ASSET_SHA256_MISMATCH"),
    ({"size": len(FW_A) + 1}, "IMAGE_ASSET_SIZE_MISMATCH"),
    ({"load_address": 0x08000000 + 512}, "IMAGE_ASSET_ADDRESS_INVALID"),
    ({"load_address": 0x08000000 - 1024}, "IMAGE_ASSET_ADDRESS_INVALID"),
    ({"load_address": 0x08000000 + 65536}, "IMAGE_ASSET_ADDRESS_INVALID"),
    ({"icpn": "STM32F103CBT6"}, "IMAGE_ASSET_TARGET_MISMATCH"),
    ({"format": "intel_hex"}, "IMAGE_ASSET_FORMAT_UNSUPPORTED"),
    ({"size": True}, "IMAGE_ASSET_FIELDS_INVALID"),
    ({"extra": 1}, "IMAGE_ASSET_FIELDS_INVALID"),
])
def test_firmware_asset_mismatch_fails_closed(change, code):
    res = resource()
    descriptor = {**bundle_v3.image_asset_descriptor(res, FW_A), **change}
    with pytest.raises(BundleBuildError, match=code):
        bundle_v3.verify_image_asset(descriptor, FW_A, res)


def test_firmware_exceeding_profile_is_refused():
    with pytest.raises(BundleBuildError, match="IMAGE_ASSET_EXCEEDS_PROFILE_MAX_IMAGE"):
        bundle_v3.image_asset_descriptor(resource(), b"\xff" * (65536 + 1))
    with pytest.raises(BundleBuildError, match="IMAGE_ASSET_EMPTY"):
        bundle_v3.image_asset_descriptor(resource(), b"")


def _mut(fn):
    d = resource()
    fn(d)
    return d


PROVIDER_ID = "openocd-platform-reference"


@pytest.mark.parametrize("descriptor, code", [
    (_mut(lambda d: d["packages"][1].update(requires=[])), "RESOURCE_DEPENDENCY_MISSING"),
    (_mut(lambda d: d["packages"][1].update(requires=["missing-pkg"])), "RESOURCE_DEPENDENCY_MISSING"),
    (_mut(lambda d: d["packages"].reverse()), "RESOURCE_DEPENDENCY_MISSING"),
    (_mut(lambda d: d["packages"].append(copy.deepcopy(d["packages"][0]))), "RESOURCE_PACKAGE_CONFLICT"),
    (_mut(lambda d: d["packages"][1]["files"].append(copy.deepcopy(d["packages"][1]["files"][0]))),
     "RESOURCE_PACKAGE_CONFLICT"),
    (_mut(lambda d: d["packages"].pop(0)), "RESOURCE_PACKAGES_INVALID"),
    (_mut(lambda d: d["packages"][0].update(kind="firmware-asset")), "RESOURCE_PACKAGE_INVALID"),
    (_mut(lambda d: d["packages"][0]["files"][0].update(sha256="ABC")), "RESOURCE_FILE_DESCRIPTOR_INVALID"),
    (_mut(lambda d: d["packages"][0]["files"][0].update(path="payload/packages/x/../y")),
     "RESOURCE_FILE_DESCRIPTOR_INVALID"),
    (_mut(lambda d: d["packages"][0].update(version="v 1")), "RESOURCE_PACKAGE_INVALID"),
    (_mut(lambda d: d.update(fpga_package="nonexistent")), "RESOURCE_FPGA_PACKAGE_INVALID"),
    (_mut(lambda d: d["abi"].update(transport="usb")), "RESOURCE_ABI_INVALID"),
    (_mut(lambda d: d["abi"].pop("driver_abi")), "RESOURCE_ABI_INVALID"),
    (_mut(lambda d: d["target"].update(board="../x")), "RESOURCE_TARGET_INVALID"),
    (_mut(lambda d: d["constraints"].update(sites=[3, 2])), "RESOURCE_CONSTRAINTS_INVALID"),
    (_mut(lambda d: d["constraints"].update(flash_size=65537)), "RESOURCE_CONSTRAINTS_INVALID"),
    (_mut(lambda d: d["constraints"].update(max_image_bytes=True)), "RESOURCE_CONSTRAINTS_INVALID"),
    (_mut(lambda d: d.update(image_package_kind="platform-provider")), "RESOURCE_IMAGE_KIND_INVALID"),
    (_mut(lambda d: d.update(schema="plasma.opf.programming-resource-set.v2")),
     "RESOURCE_SET_SCHEMA_UNSUPPORTED"),
    (_mut(lambda d: d.pop("constraints")), "RESOURCE_SET_FIELDS_INVALID"),
    (_mut(lambda d: d.update(archive_sha256="0" * 64)), "RESOURCE_SET_FIELDS_INVALID"),
    ([], "RESOURCE_SET_FIELDS_INVALID"),
])
def test_invalid_or_incomplete_resource_descriptor_fails_closed(descriptor, code):
    with pytest.raises(BundleBuildError, match=code):
        bundle_v3.resource_set_sha256(descriptor)


@pytest.mark.parametrize("kwargs, code", [
    ({"ppu_id": "z2-hil", "site_id": 1}, "JOB_BINDING_SITE_NOT_IN_PROFILE"),
    ({"ppu_id": "z2-hil", "site_id": True}, "JOB_BINDING_SITE_NOT_IN_PROFILE"),
    ({"ppu_id": "", "site_id": 2}, "JOB_BINDING_PPU_INVALID"),
    ({"ppu_id": "../z2", "site_id": 2}, "JOB_BINDING_PPU_INVALID"),
])
def test_job_binding_refuses_wrong_site_or_ppu(kwargs, code):
    res = resource()
    fw = bundle_v3.image_asset_descriptor(res, FW_A)
    with pytest.raises(BundleBuildError, match=code):
        bundle_v3.job_image_binding(res, fw, operation="flash_cycle", **kwargs)


def test_job_binding_refuses_firmware_for_other_target():
    res = resource()
    fw = {**bundle_v3.image_asset_descriptor(res, FW_A), "icpn": "STM32F103CBT6"}
    with pytest.raises(BundleBuildError, match="IMAGE_ASSET_TARGET_MISMATCH"):
        bundle_v3.job_image_binding(res, fw, ppu_id="z2-hil", site_id=2, operation="flash_cycle")


# ------------------------------------------- user-selected Operation (Gate 2)
BASE = 0x08000000
ALL_OPS = ["erase", "program", "verify", "read", "flash_cycle"]


def resource_with(operations):
    d = resource()
    d["constraints"]["operations"] = list(operations)
    return d


def bind(res, asset=None, **kw):
    return bundle_v3.job_image_binding(res, asset, ppu_id=kw.pop("ppu_id", "z2-hil"),
                                       site_id=kw.pop("site_id", 2), **kw)


def binding_sha(binding):
    return bundle_v3.sha256_hex(bundle_v3.canonical_json(binding))


def test_operation_vocabulary_matches_core_operation_enum():
    from plasma_core.enums import Operation
    assert set(bundle_v3.OPERATIONS) == {o.value for o in Operation} - {"status", "cancel"}
    assert bundle_v3.IMAGE_OPERATIONS == {"program", "verify", "flash_cycle"}


def test_operation_and_image_change_binding_identity():
    res = resource_with(ALL_OPS)
    fw_a = bundle_v3.image_asset_descriptor(res, FW_A)
    fw_b = bundle_v3.image_asset_descriptor(res, FW_B)
    shas = {binding_sha(bind(res, fw, operation=op))
            for op in ("program", "verify", "flash_cycle") for fw in (fw_a, fw_b)}
    assert len(shas) == 6
    # Resource identity is independent of which Operation a Job selects.
    assert bundle_v3.resource_set_sha256(res) != bundle_v3.resource_set_sha256(resource())
    assert all(bind(res, fw_a, operation=op)["resource_set_sha256"]
               == bundle_v3.resource_set_sha256(res) for op in ("program", "verify"))


def test_erase_and_read_need_no_image_and_range_changes_binding():
    res = resource_with(ALL_OPS)
    erase_all = bind(res, operation="erase", address=BASE, length=65536)
    erase_one = bind(res, operation="erase", address=BASE + 1024, length=1024)
    read_a = bind(res, operation="read", address=BASE, length=256)
    read_b = bind(res, operation="read", address=BASE + 1, length=256)
    read_c = bind(res, operation="read", address=BASE, length=257)
    assert erase_all["image_asset_sha256"] is None and read_a["image_asset_sha256"] is None
    assert erase_all["range"] == {"address": BASE, "length": 65536}
    assert len({binding_sha(b) for b in (erase_all, erase_one, read_a, read_b, read_c)}) == 5
    # Same range, different Operation: different identity.
    assert binding_sha(bind(res, operation="read", address=BASE, length=1024)) \
        != binding_sha(bind(res, operation="erase", address=BASE, length=1024))
    digest = bundle_v3.verify_job_binding(read_a, res, ppu_id="z2-hil", site_id=2,
                                          operation="read", address=BASE, length=256)
    assert digest == binding_sha(read_a)
    with pytest.raises(BundleBuildError, match="JOB_BINDING_MISMATCH"):
        bundle_v3.verify_job_binding(read_a, res, ppu_id="z2-hil", site_id=2,
                                     operation="read", address=BASE, length=255)


def test_image_operation_range_is_the_image_range():
    res = resource_with(ALL_OPS)
    fw = bundle_v3.image_asset_descriptor(res, FW_A, load_address=BASE + 2048)
    implicit = bind(res, fw, operation="program")
    explicit = bind(res, fw, operation="program", address=BASE + 2048, length=len(FW_A))
    assert implicit == explicit
    assert implicit["range"] == {"address": BASE + 2048, "length": len(FW_A)}
    at_base = bind(res, bundle_v3.image_asset_descriptor(res, FW_A), operation="program")
    assert binding_sha(at_base) != binding_sha(implicit)


def test_binding_mismatch_when_operation_differs():
    res = resource_with(ALL_OPS)
    fw = bundle_v3.image_asset_descriptor(res, FW_A)
    binding = bind(res, fw, operation="verify")
    with pytest.raises(BundleBuildError, match="JOB_BINDING_MISMATCH"):
        bundle_v3.verify_job_binding(binding, res, fw, ppu_id="z2-hil", site_id=2,
                                     operation="program")


@pytest.mark.parametrize("operation", ["status", "cancel", "write", "FLASH_CYCLE", "", None, 1])
def test_unknown_operation_is_refused(operation):
    res = resource_with(ALL_OPS)
    with pytest.raises(BundleBuildError, match="JOB_OPERATION_UNSUPPORTED"):
        bind(res, operation=operation, address=BASE, length=1024)


@pytest.mark.parametrize("operation", ["erase", "program", "verify", "read"])
def test_operation_not_declared_by_profile_is_refused(operation):
    # The committed Site 2 route declares only flash_cycle.
    res = resource()
    fw = bundle_v3.image_asset_descriptor(res, FW_A)
    asset = fw if operation in bundle_v3.IMAGE_OPERATIONS else None
    with pytest.raises(BundleBuildError, match="JOB_OPERATION_NOT_IN_PROFILE"):
        bind(res, asset, operation=operation, address=BASE, length=1024)


def test_flash_cycle_not_declared_is_refused():
    res = resource_with(["read"])
    fw = bundle_v3.image_asset_descriptor(res, FW_A)
    with pytest.raises(BundleBuildError, match="JOB_OPERATION_NOT_IN_PROFILE"):
        bind(res, fw, operation="flash_cycle")


@pytest.mark.parametrize("operation, use_image, address, length, code", [
    ("program", False, None, None, "JOB_IMAGE_ASSET_REQUIRED"),
    ("verify", False, None, None, "JOB_IMAGE_ASSET_REQUIRED"),
    ("flash_cycle", False, None, None, "JOB_IMAGE_ASSET_REQUIRED"),
    ("program", True, BASE + 1024, len(FW_A), "JOB_RANGE_MISMATCH"),
    ("verify", True, BASE, len(FW_A) + 1, "JOB_RANGE_MISMATCH"),
    ("flash_cycle", True, BASE, None, "JOB_RANGE_MISMATCH"),
    ("flash_cycle", True, BASE, True, "JOB_RANGE_MISMATCH"),
    ("erase", True, BASE, 1024, "JOB_IMAGE_ASSET_NOT_ALLOWED"),
    ("read", True, BASE, 1024, "JOB_IMAGE_ASSET_NOT_ALLOWED"),
    ("erase", False, None, None, "JOB_RANGE_REQUIRED"),
    ("read", False, BASE, None, "JOB_RANGE_REQUIRED"),
    ("read", False, True, 4, "JOB_RANGE_REQUIRED"),
    ("erase", False, BASE + 512, 1024, "JOB_RANGE_INVALID"),
    ("erase", False, BASE, 1000, "JOB_RANGE_INVALID"),
    ("erase", False, BASE, 65536 + 1024, "JOB_RANGE_INVALID"),
    ("read", False, BASE - 1, 16, "JOB_RANGE_INVALID"),
    ("read", False, BASE, 0, "JOB_RANGE_INVALID"),
    ("read", False, BASE + 65536 - 8, 16, "JOB_RANGE_INVALID"),
])
def test_operation_image_and_range_rules_fail_closed(operation, use_image, address, length, code):
    res = resource_with(ALL_OPS)
    fw = bundle_v3.image_asset_descriptor(res, FW_A) if use_image else None
    with pytest.raises(BundleBuildError, match=code):
        bind(res, fw, operation=operation, address=address, length=length)


@pytest.mark.parametrize("operations, ok", [
    (["read"], True),
    (["erase", "read"], True),
    (ALL_OPS, True),
    ([], False),
    (["flash_cycle", "flash_cycle"], False),
    (["flash_cycle", "status"], False),
    (["write"], False),
    ("flash_cycle", False),
])
def test_resource_operations_need_not_include_flash_cycle(operations, ok):
    descriptor = resource_with([]) if isinstance(operations, str) else resource_with(operations)
    if isinstance(operations, str):
        descriptor["constraints"]["operations"] = operations
    if ok:
        assert len(bundle_v3.resource_set_sha256(descriptor)) == 64
    else:
        with pytest.raises(BundleBuildError, match="RESOURCE_CONSTRAINTS_INVALID"):
            bundle_v3.resource_set_sha256(descriptor)


def test_executable_route_still_requires_flash_cycle():
    """Descriptor relaxation opens no execution: the Bundle-building Route keeps
    requiring flash_cycle, the only operation the C-3 Runtime route executes."""
    payload = route_payload()
    payload["profile"]["capabilities"]["operations"] = ["read"]
    with pytest.raises(BundleBuildError, match="ROUTE_CAPABILITIES_INVALID"):
        bundle_v3.parse_route(payload)
    payload["profile"]["capabilities"]["operations"] = ["flash_cycle", "bogus"]
    with pytest.raises(BundleBuildError, match="RESOURCE_CONSTRAINTS_INVALID"):
        bundle_v3.build_user_image_bundle(bundle_v3.parse_route(payload), FW_A)


@pytest.mark.parametrize("operation", ["erase", "program", "verify", "read"])
def test_gateway_bundle_reference_stays_flash_cycle_only(operation):
    """Runtime admission unchanged: the Bundle Asset reference is flash_cycle only."""
    body = {"site_id": 2, "operation": operation, "target": "STM32F103C8T6",
            "provider": PROVIDER_ID, "profile": "stm32f103c8t6-site2",
            "asset_set_sha256": "a" * 64, "asset_package_id": "img-0000000000000000",
            "bundle_asset_sha256": "c" * 64}
    handler = object.__new__(PlasmaWebHandler)
    with pytest.raises(ValueError):
        handler._job_request(body, client_id="plasma-web")


def test_bundle_with_extra_or_fpga_package_is_outside_contract():
    built = bundle_v3.build_user_image_bundle(route(), FW_A)
    members = zip_members(built.archive)
    manifest = json.loads(members["manifest.json"])
    manifest["packages"].append({"id": "fpga-x", "kind": "fpga-image", "version": "1",
                                 "requires": [], "files": []})
    with pytest.raises(BundleBuildError, match="BUNDLE_PACKAGE_SET_UNSUPPORTED"):
        bundle_v3.identity_from_manifest(manifest, lambda p: members[p])


# ---------------------------- no bypass of Active Set / B1-B3 / Job admission
def stage_active(tmp_path: Path, built) -> tuple[Path, Path]:
    """Synthetic structurally B3-verified staged Set from canonical Bundle bytes."""
    product = tmp_path / "product"
    stage = product / "assets/staged" / built.archive_sha256
    members = zip_members(built.archive)
    for name, blob in members.items():
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    manifest = json.loads(members["manifest.json"])
    (stage / "b3-install.json").write_bytes(bundle_v3.canonical_json({
        "schema": "plasma.ppu.b3-install.v1", "archive_sha256": built.archive_sha256,
        "manifest_sha256": hashlib.sha256(members["manifest.json"]).hexdigest(),
        "bundle_name": manifest["name"], "bundle_version": manifest["version"],
        "files_verified": len(members) - 1,
    }))
    (product / "assets/active.json").write_bytes(bundle_v3.canonical_json({
        "schema": assets.SCHEMA, "generation": 1, "asset_set_sha256": built.archive_sha256}))
    assert assets.read_active(product)["asset_set_sha256"] == built.archive_sha256
    return product, stage


def test_resource_identity_is_not_an_active_set_identity(tmp_path):
    a = bundle_v3.build_user_image_bundle(route(), FW_A, filename="a.bin")
    b = bundle_v3.build_user_image_bundle(route(), FW_B, filename="b.bin")
    product, _stage = stage_active(tmp_path, a)
    ok = assets.resolve_active_firmware(
        product, asset_set_sha256=a.archive_sha256, asset_package_id=a.asset_package_id,
        profile_package_id=a.profile_id, asset_sha256=a.image_sha256)
    assert ok["image"] == FW_A
    # Resource identity presented as the Active Set: refused.
    with pytest.raises(assets.AssetSetError, match="ACTIVE_SET_MISMATCH"):
        assets.resolve_active_firmware(
            product, asset_set_sha256=a.resource_set_sha256,
            asset_package_id=a.asset_package_id, profile_package_id=a.profile_id,
            asset_sha256=a.image_sha256)
    # Same Resource Set, different Firmware: not resolvable from A's Active Set.
    with pytest.raises(assets.AssetSetError):
        assets.resolve_active_firmware(
            product, asset_set_sha256=a.archive_sha256, asset_package_id=b.asset_package_id,
            profile_package_id=b.profile_id, asset_sha256=b.image_sha256)
    with pytest.raises(assets.AssetSetError, match="ACTIVE_SET_MISMATCH"):
        assets.resolve_active_firmware(
            product, asset_set_sha256=b.archive_sha256, asset_package_id=b.asset_package_id,
            profile_package_id=b.profile_id, asset_sha256=b.image_sha256)


@pytest.mark.parametrize("extra", [
    {"resource_set_sha256": "a" * 64},
    {"image_asset_sha256": "b" * 64},
    {"job_binding": {"schema": "plasma.opf.job-image-binding.v1"}},
])
def test_gateway_job_request_refuses_new_identity_fields(extra):
    body = {"site_id": 2, "operation": "flash_cycle", "target": "STM32F103C8T6",
            "provider": PROVIDER_ID, "profile": "stm32f103c8t6-site2",
            "asset_set_sha256": "a" * 64, "asset_package_id": "img-0000000000000000",
            "bundle_asset_sha256": "c" * 64, **extra}
    handler = object.__new__(PlasmaWebHandler)
    with pytest.raises(ValueError):
        handler._job_request(body, client_id="plasma-web")


def test_same_resources_new_firmware_reuses_ppu_verified_resources(tmp_path):
    """OFE-1B replaces the OFE-1A rule: equal PPU-derived Resources skip B1/B2/B3."""
    other = bundle_v3.build_user_image_bundle(route(), FW_B, filename="app.bin")
    current = bundle_v3.build_user_image_bundle(route(), image(), filename="app.bin")
    assert other.resource_set_sha256 == current.resource_set_sha256
    workflow, coord, gateway = make(
        tmp_path, coordinator=FakeCoordinator(active_sha=other.archive_sha256))
    planned, run = run_once(workflow)
    assert planned["activation_required"] is False
    assert planned["steps"][0] == "RESOURCE_REUSE"
    assert planned["resource"]["resource_set_sha256"] == other.resource_set_sha256
    assert run["outcome"] == "PASS"
    assert not {"B1_create", "B2", "B3"} & set(coord.calls)
    assert coord.active_sha == other.archive_sha256
    assert set(gateway.posts[0]) == {
        "site_id", "operation", "timeout_s", "target", "provider", "profile",
        "job_binding", "image_asset", "asset_base64"}


def test_active_set_reporting_resource_identity_is_not_trusted(tmp_path):
    """A Resource SHA presented as the Active Set is no PPU-verified identity."""
    current = bundle_v3.build_user_image_bundle(route(), image(), filename="app.bin")
    coord = FakeCoordinator(active_sha=current.resource_set_sha256)

    class PPU(FakeGateway):
        def _resources(self):
            # Real PPU: no staged Set under that SHA -> verify_staged fails.
            if self.coordinator.active_sha == current.resource_set_sha256:
                return {"state": "UNAVAILABLE", "reason": "ASSET_SET_NOT_STAGED"}
            return super()._resources()

    workflow, coord, _gateway = make(tmp_path, coordinator=coord,
                                     gateway=PPU(image=image(), coordinator=coord))
    planned = workflow.plan(ALIAS, plan_body())["plan"]
    assert planned["activation_required"] is True and planned["resource"]["reuse"] is False
    started = workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    run = workflow.run_status(ALIAS, started["run"]["run_id"])["run"]
    assert "B3" in coord.calls and run["outcome"] == "PASS"


def test_user_bundle_still_passes_host_only_b3_verifier(tmp_path):
    built = bundle_v3.build_user_image_bundle(route(), FW_B, filename="b.bin")
    path = tmp_path / "b.zip"
    path.write_bytes(built.archive)
    verified = ppu_unified_deployment.verify_host_only_bundle(
        path, expected_sha256=built.archive_sha256, target_profile=route().target)
    assert [p.kind for p in verified.packages] == [
        "platform-provider", "programming-profile", "firmware-asset"]
