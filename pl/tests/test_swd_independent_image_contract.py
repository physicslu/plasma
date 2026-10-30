"""Host-only adversarial checks for the exact ab79b04e HWH/Manifest pair."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from unittest.mock import patch

from pl.hil import fpga_image_admission as admission
from pl.hil import fpga_image_root as root
from pl.hil import fpga_image_guard as guard
from pl.hil import swd_independent_image_contract as contract


FIXTURE = Path(__file__).parent / "fixtures/swd-independent-ab79b04e"


def test_exact_build_pair_and_site_addresses():
    result = contract.verify(FIXTURE / "system.hwh",
                             FIXTURE / "plasma-image-manifest.json")
    assert result["identity_addresses"] == [0x43C01000, 0x43C02000]
    assert result["linux_owner"] == "NOT_VERIFIED"


def test_missing_or_mutated_artifact_fails_closed(tmp_path):
    hwh = tmp_path / "system.hwh"
    hwh.write_bytes((FIXTURE / "system.hwh").read_bytes())
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes((FIXTURE / "plasma-image-manifest.json").read_bytes())
    hwh.write_bytes(hwh.read_bytes() + b"\n")
    with pytest.raises(contract.IndependentImageDenied, match="HWH_SHA_MISMATCH"):
        contract.verify(hwh, manifest)
    hwh.write_bytes((FIXTURE / "system.hwh").read_bytes())
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    with pytest.raises(contract.IndependentImageDenied, match="MANIFEST_SHA_MISMATCH"):
        contract.verify(hwh, manifest)
    manifest.write_bytes((FIXTURE / "plasma-image-manifest.json").read_bytes())
    fake_bin = tmp_path / "candidate.bin"
    fake_bin.write_bytes(b"not the admitted firmware")
    with pytest.raises(contract.IndependentImageDenied, match="BIN_SHA_MISMATCH"):
        contract.verify(hwh, manifest, firmware=fake_bin)


@pytest.mark.parametrize("change,denial", [
    ("no-site2", "HWH_SITE_COUNT_MISMATCH"),
    ("global-at-owner", "HWH_SITE_RANGE_MISMATCH"),
    ("wrong-gp0", "HWH_AXI_ROUTE_MISMATCH"),
    ("wrong-interconnect", "HWH_INTERCONNECT_MISMATCH"),
    ("wrong-clock", "HWH_SITE_CLOCK_RESET_MISMATCH"),
    ("wrong-reset", "HWH_SITE_CLOCK_RESET_MISMATCH"),
])
def test_hwh_topology_negative(tmp_path, monkeypatch, change, denial):
    tree = ET.parse(FIXTURE / "system.hwh")
    root_xml = tree.getroot()
    ranges = list(root_xml.iter("MEMRANGE"))
    if change == "no-site2":
        for parent in root_xml.iter():
            if ranges[1] in parent:
                parent.remove(ranges[1])
                break
    elif change == "global-at-owner":
        ranges[0].set("BASEVALUE", "0x43C00000")
        ranges[0].set("HIGHVALUE", "0x43C00FFF")
    elif change == "wrong-gp0":
        ranges[0].set("MASTERBUSINTERFACE", "M_AXI_GP1")
    else:
        modules = {m.get("INSTANCE"): m for m in root_xml.iter("MODULE")}
        if change == "wrong-interconnect":
            target = next(b for b in modules["swd_site1"].iter("BUSINTERFACE")
                          if b.get("NAME") == "S_AXI")
            target.set("BUSNAME", "unrelated")
        else:
            target = next(p for p in modules["swd_site1"].iter("PORT")
                          if p.get("NAME") == ("s_axi_aclk" if change == "wrong-clock"
                                               else "s_axi_aresetn"))
            target.set("SIGNAME", "unrelated")
    hwh = tmp_path / "changed.hwh"
    tree.write(hwh)
    monkeypatch.setattr(contract, "HWH_SHA", hashlib.sha256(hwh.read_bytes()).hexdigest())
    with pytest.raises(contract.IndependentImageDenied, match=denial):
        contract.verify(hwh, FIXTURE / "plasma-image-manifest.json")


@pytest.mark.parametrize("field,value,denial", [
    ("axi_base", 0x43C00000, "MANIFEST_AXI_BASE_MISMATCH"),
    ("axi_bytes", 4096, "MANIFEST_AXI_BASE_MISMATCH"),
    ("abi_version", 0x00040001, "MANIFEST_AXI_BASE_MISMATCH"),
    ("identity_words", [[0, 0x00050003, 0xFFFFFFFF],
                        [4096, 0x00050002, 0xFFFFFFFF]],
     "MANIFEST_IDENTITY_MISMATCH"),
    ("identity_words", [[0, 0x00050001, 0xFFFFFFFE],
                        [4096, 0x00050002, 0xFFFFFFFF]],
     "MANIFEST_IDENTITY_MISMATCH"),
])
def test_manifest_identity_negative(tmp_path, monkeypatch, field, value, denial):
    data = json.loads((FIXTURE / "plasma-image-manifest.json").read_text())
    data[field] = value
    manifest = tmp_path / "changed.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(contract, "MANIFEST_SHA",
                        hashlib.sha256(manifest.read_bytes()).hexdigest())
    with pytest.raises(contract.IndependentImageDenied, match=denial):
        contract.verify(FIXTURE / "system.hwh", manifest)


def test_root_identity_uses_axi_base_not_owner_base():
    class Image:
        axi_base = 0x43C01000
        owner_base = 0x43C00000
        identity_words = ((0, 0x00050001, 0xFFFFFFFF),
                          (4096, 0x00050002, 0xFFFFFFFF))
        abi_offset = 0
        abi_version = 0x00050001
        site_bitmap_offset = None
    reads = []
    def read32(address):
        reads.append(address)
        return {0x43C01000: 0x00050001, 0x43C02000: 0x00050002}[address]
    assert root.read_identity(read32, Image()) == {0: 0x00050001,
                                                   4096: 0x00050002}
    assert reads == [0x43C01000, 0x43C02000]


def test_platform_owner_admission_is_index_independent_and_fail_closed():
    class Release:
        recovery_sha256 = "b" * 64
        firmware_sha256 = "a" * 64
        expected_uio = {"platform_node": "43c01000.plasma-swd",
                        "driver": "uio_pdrv_genirq",
                        "maps": [[0x43C01000, 0x2000]], "runtime": "suspended"}
        uio_name = ""
        firmware_name = "candidate.bin"
        recovery_name = "base.bin"
        site_bitmap = 3
        image_id = "host-only"
    release = Release()
    facts = {"observation_kind": "LIVE_ROOT_READ_ONLY", "root": True,
             "boot_id": "host-only-boot", "manager_state": "operating",
             "recovery_sha256": release.recovery_sha256,
             "candidate_sha256": release.firmware_sha256,
             "proc_complete": True, "proc_conflicts": [],
             "proc_scan_diagnostic": {"status": "COMPLETE"},
             "platform_overlaps": ["43c01000.plasma-swd"],
             "uio_overlaps": ["uio0"]}
    def check(uio, passive=facts):
        return admission.check_exact(
            release=release, passive=passive, uio=uio,
            original_manager_load="fpga_manager fpga0: writing candidate.bin to fpga0",
            expected_firmware="candidate.bin")
    owner = dict(release.expected_uio, uio="uio0")
    assert check(owner)["target_boot_id"] == "host-only-boot"
    assert check(dict(owner, uio="uio7"), facts | {"uio_overlaps": ["uio7"]})
    for bad in (dict(owner, maps=[[0x40000000, 0x2000]]),
                dict(owner, maps=[[0x43C01000, 0x1000]]),
                dict(owner, platform_node="43c01000.audio-codec-ctrl"),
                dict(owner, driver="other")):
        with pytest.raises(admission.AdmissionDenied):
            check(bad)
    for bad in (facts | {"platform_overlaps": []},
                facts | {"platform_overlaps": ["43c01000.plasma-swd",
                                                 "43c00000.audio-codec-ctrl"]},
                facts | {"uio_overlaps": ["uio0", "uio1"]},
                facts | {"proc_conflicts": ["42"]},
                facts | {"recovery_sha256": "0" * 64},
                facts | {"candidate_sha256": "0" * 64},
                facts | {"boot_id": ""}):
        with pytest.raises(admission.AdmissionDenied):
            check(owner, bad)


def test_new_manifest_requires_explicit_platform_owner_not_uio_index(tmp_path):
    data = json.loads((FIXTURE / "plasma-image-manifest.json").read_text())
    data.pop("uio_name")
    data["owner_base"] = 0x43C01000
    data["owner_bytes"] = 0x2000
    data["expected_uio"] = {"platform_node": "43c01000.plasma-swd",
                            "driver": "uio_pdrv_genirq",
                            "maps": [[0x43C01000, 0x2000]],
                            "runtime": "suspended"}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    with patch.object(root, "MANIFEST_FILE", path), patch.object(guard, "protected"):
        image = root.read_image_manifest()
        assert image.uio_name == ""
        assert image.expected_uio["platform_node"] == "43c01000.plasma-swd"
        for bad in (dict(data, expected_uio=dict(data["expected_uio"],
                                                  platform_node="43c01000.audio-codec-ctrl")),
                    dict(data, expected_uio=dict(data["expected_uio"],
                                                  maps=[[0x40000000, 0x10000]])),
                    dict(data, uio_name="uio0")):
            path.write_text(json.dumps(bad))
            if bad["expected_uio"].get("platform_node") == "43c01000.audio-codec-ctrl":
                # A plausible but wrong owner must fail during live admission;
                # parser only validates manifest structure, not kernel truth.
                assert root.read_image_manifest().expected_uio["platform_node"].endswith(
                    "audio-codec-ctrl")
            else:
                with pytest.raises(root.ImageDeploymentDenied):
                    root.read_image_manifest()


def test_live_resolver_binds_platform_resource_regardless_of_uio_ordinal(tmp_path):
    class Release:
        expected_uio = {"platform_node": "43c01000.plasma-swd",
                        "driver": "uio_pdrv_genirq",
                        "maps": [[0x43C01000, 0x2000]], "runtime": "suspended"}
        uio_name = ""
        recovery_sha256 = "b" * 64
        firmware_sha256 = "a" * 64
        firmware_name = "candidate.bin"
        recovery_name = "base.bin"
        site_bitmap = 3
        image_id = "host-only"
    release = Release()
    facts = {"observation_kind": "LIVE_ROOT_READ_ONLY", "root": True,
             "boot_id": "host-only-boot", "manager_state": "operating",
             "recovery_sha256": release.recovery_sha256,
             "candidate_sha256": release.firmware_sha256,
             "proc_complete": True, "proc_conflicts": [],
             "proc_scan_diagnostic": {"status": "COMPLETE"},
             "platform_overlaps": ["43c01000.plasma-swd"],
             "uio_overlaps": ["uio7"]}
    class Port:
        def _require_locked(self):
            return None
        def current_facts(self):
            return facts
    port = Port()
    port.release = release
    sysroot = tmp_path / "sys"
    procroot = tmp_path / "proc"
    node = sysroot / "bus/platform/devices/43c01000.plasma-swd"
    node.mkdir(parents=True)
    (node / "power").mkdir()
    (node / "power/runtime_status").write_text("suspended")
    driver = sysroot / "bus/platform/drivers/uio_pdrv_genirq"
    driver.mkdir(parents=True)
    (node / "driver").symlink_to(driver)
    uio = sysroot / "class/uio/uio7"
    (uio / "maps/map0").mkdir(parents=True)
    (uio / "device").symlink_to(node)
    (uio / "maps/map0/addr").write_text("0x43C01000")
    (uio / "maps/map0/size").write_text("0x2000")
    boot = procroot / "sys/kernel/random/boot_id"
    boot.parent.mkdir(parents=True)
    boot.write_text(facts["boot_id"])
    with patch.object(guard, "SYS", sysroot), patch.object(guard, "PROC", procroot), \
         patch.object(guard, "manager_last_load",
                      return_value="fpga_manager fpga0: writing candidate.bin to fpga0"), \
         patch.object(admission.os, "geteuid", return_value=0):
        assert admission.collect_live(root_port=port, release=release,
                                      expected_firmware="candidate.bin")[
                                          "current_uio"]["uio"] == "uio7"
        (uio / "maps/map0/size").write_text("0x1000")
        with pytest.raises(admission.AdmissionDenied, match="BOUND_UIO_OWNER_FACTS_CHANGED"):
            admission.collect_live(root_port=port, release=release,
                                   expected_firmware="candidate.bin")
        (uio / "maps/map0/size").write_text("0x2000")
        other = sysroot / "class/uio/uio8"
        (other / "maps/map0").mkdir(parents=True)
        (other / "device").symlink_to(node)
        with pytest.raises(admission.AdmissionDenied, match="UIO_PLATFORM_OWNER_NOT_UNIQUE"):
            admission.collect_live(root_port=port, release=release,
                                   expected_firmware="candidate.bin")
