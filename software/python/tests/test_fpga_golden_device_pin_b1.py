"""Stage B-1: the Golden recovery Image is a device fact, never a Manifest claim.

Host-only. No Z2, FPGA Manager, /lib/firmware or DUT access.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pl.hil import fpga_image_admission as admission
from pl.hil import fpga_image_guard as guard
from pl.hil import fpga_image_root as root

from .ppu_fpga_qualification_fixture import synthetic_image
from .test_ppu_bundle_v3_packages_contract import ROOT, load
from .test_ppu_fpga_static_qualification_gate1 import (
    _with_manifest, deny, fpga_bundle, contract_file, qualify,
)

GOLDEN = "c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c"
RELEASE = ROOT / "pl/hil/releases/swd-independent-bd976140/plasma-image-manifest.json"


def _manifest(**changes) -> bytes:
    data = json.loads(RELEASE.read_bytes())
    data.update(changes)
    return json.dumps(data, sort_keys=True).encode()


def test_device_golden_is_the_pynq_z2_factory_base_bin():
    assert guard.GOLDEN_RECOVERY_NAME == "base.bin"
    assert guard.GOLDEN_RECOVERY_SHA256 == GOLDEN


def test_every_shipped_manifest_restates_the_device_golden():
    shipped = [
        RELEASE,
        ROOT / "pl/tests/fixtures/swd-independent-bd976140/plasma-image-manifest.json",
        ROOT / "pl/projects/z2-bluepill-rbb/image-manifest.json",
        ROOT / "pl/hil/bluepill-swd-image-release.candidate.json",
    ]
    for path in shipped:
        data = json.loads(path.read_text())
        assert (data["recovery_name"], data["recovery_sha256"]) == ("base.bin", GOLDEN), path
    contracts = json.loads((ROOT / "scripts/ppu-fpga-image-contracts.json").read_text())
    assert all(c["recovery_name"] == "base.bin" for c in contracts["contracts"])
    assert root.parse_image_manifest_bytes(RELEASE.read_bytes()).recovery_sha256 == GOLDEN


@pytest.mark.parametrize("changes", [
    {"recovery_sha256": "d" * 64},                       # re-hashed Golden
    {"recovery_name": "user-golden.bin"},                 # renamed Golden
    {"recovery_name": "user-golden.bin", "recovery_sha256": "d" * 64},
])
def test_root_parser_rejects_manifest_that_redefines_recovery(changes):
    with pytest.raises(root.ImageDeploymentDenied, match="IMAGE_RECOVERY_NOT_DEVICE_GOLDEN"):
        root.parse_image_manifest_bytes(_manifest(**changes))


@pytest.mark.parametrize("field,value", [
    ("recovery_sha256", "d" * 64), ("recovery_name", "golden.bin"),
])
def test_image_manifest_object_cannot_carry_non_golden_recovery(field, value):
    good = root.parse_image_manifest_bytes(RELEASE.read_bytes())
    with pytest.raises(root.ImageDeploymentDenied, match="IMAGE_RECOVERY_NOT_DEVICE_GOLDEN"):
        dataclasses.replace(good, **{field: value})


def test_b2_static_qualification_denies_bundle_redefining_golden(tmp_path):
    # Even if the trusted contract pinned THAT Manifest's bytes, the Root
    # parser refuses a non-Golden recovery before any contract comparison.
    archive, digest, path = _with_manifest(tmp_path, {"recovery_sha256": "d" * 64})
    deny("FPGA_IMAGE_MANIFEST_DENIED:IMAGE_RECOVERY_NOT_DEVICE_GOLDEN",
         tmp_path, archive, digest, path)


def test_b2_static_qualification_passes_with_device_golden(tmp_path):
    files, entry = synthetic_image()
    archive, digest = fpga_bundle(tmp_path, files)
    result = qualify(tmp_path, archive, digest, contract_file(tmp_path, entry))
    assert result["result"] == "STATIC_QUALIFIED"


def test_live_facts_hash_device_golden_even_if_release_claims_otherwise(tmp_path):
    proc, sys_root, firmware = tmp_path / "proc", tmp_path / "sys", tmp_path / "fw"
    (proc / "sys/kernel/random").mkdir(parents=True)
    (proc / "sys/kernel/random/boot_id").write_text("boot-1")
    (proc / "device-tree").mkdir(parents=True)
    (proc / "device-tree/compatible").write_bytes(b"xlnx,zynq-7000\x00")
    (sys_root / "class/fpga_manager/fpga0").mkdir(parents=True)
    (sys_root / "class/fpga_manager/fpga0/state").write_text("operating")
    firmware.mkdir()
    # A forged (non-ImageManifest) release object claiming another Golden.
    forged = SimpleNamespace(
        firmware_name="candidate.bin", firmware_sha256="a" * 64,
        recovery_name="user-golden.bin", recovery_sha256="d" * 64,
        soc_compatible="xlnx,zynq-7000")
    calls = []
    with patch.object(guard, "PROC", proc), patch.object(guard, "SYS", sys_root), \
            patch.object(guard, "FIRMWARE", firmware), \
            patch.object(guard.os, "geteuid", return_value=0), \
            patch.object(guard, "sha_file",
                         side_effect=lambda p, e: calls.append((p.name, e)) or e), \
            patch.object(guard, "scan_kernel_owners", return_value=([], [])), \
            patch.object(guard, "scan_proc_consumers", return_value=(True, [])):
        facts = guard.read_live_z2_facts(release=forged)
    assert ("base.bin", GOLDEN) in calls
    assert all(name != "user-golden.bin" and expected != "d" * 64 for name, expected in calls)
    assert facts["recovery_sha256"] == GOLDEN


def test_admission_requires_observed_device_golden_not_release_claim():
    forged = SimpleNamespace(
        recovery_sha256="d" * 64, firmware_sha256="a" * 64, recovery_name="base.bin",
        firmware_name="candidate.bin", expected_uio={"uio": "uio1"}, uio_name="uio1",
        site_bitmap=1, image_id="host-only")
    passive = {"observation_kind": "LIVE_ROOT_READ_ONLY", "root": True,
               "boot_id": "b", "manager_state": "operating",
               "recovery_sha256": "d" * 64, "candidate_sha256": "a" * 64}
    with pytest.raises(admission.AdmissionDenied, match="INCOMPLETE_ROOT_OR_PROCESS_FACTS"):
        admission.check_exact(release=forged, passive=passive, uio={},
                              original_manager_load="", expected_firmware="candidate.bin")


@pytest.mark.parametrize("script", [
    "plasma_wordport_program.py", "plasma_native_wordport_v02.py",
])
def test_wordport_tools_pin_the_same_device_golden(script):
    module = load(f"golden_pin_{script.replace('.', '_')}", script)
    assert module.GOLDEN_RECOVERY == (guard.GOLDEN_RECOVERY_NAME, guard.GOLDEN_RECOVERY_SHA256)
    source = (ROOT / "scripts" / script).read_text()
    assert 'manifest["recovery_sha256"]' not in source
    assert 'manifest["recovery_name"]' not in source
