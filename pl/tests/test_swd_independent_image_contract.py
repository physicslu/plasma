"""Host-only adversarial checks for the exact ab79b04e HWH/Manifest pair."""
from __future__ import annotations

import hashlib
import json
import fcntl
import os
from pathlib import Path
import sys
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


def test_explicit_devmem_engineering_owner_is_not_inferred_from_covering_uio(tmp_path):
    """Only a source-pinned ABI-v5 Manifest and live owner facts admit MMIO."""
    data = json.loads((FIXTURE / "plasma-image-manifest.json").read_text())
    data.pop("uio_name")  # The historical uio1 assumption is false on Z2.
    data["expected_uio"] = {
        "backend": "devmem",
        "platform_node": "43c00000.audio-codec-ctrl",
        "driver": "uio_pdrv_genirq",
        "maps": [[0x43C00000, 0x10000]],
        "runtime": "suspended",
    }
    manifest = tmp_path / "candidate-owner.json"
    manifest.write_text(json.dumps(data))
    with patch.object(root, "MANIFEST_FILE", manifest), patch.object(guard, "protected"):
        release = root.read_image_manifest()
        assert release.uio_name == ""
        assert release.expected_uio["backend"] == "devmem"
        for field, changed in (
            ("firmware_sha256", "0" * 64),
            ("abi_version", 0x00040001),
            ("axi_base", 0x43C00000),
            ("identity_words", [[0, 0x00050001, 0xFFFFFFFF],
                                [4096, 0x00050003, 0xFFFFFFFF]]),
        ):
            manifest.write_text(json.dumps(data | {field: changed}))
            with pytest.raises(root.ImageDeploymentDenied):
                root.read_image_manifest()
        manifest.write_text(json.dumps(data))
        for owner_change in (
            {"backend": "uio"}, {"runtime": "active"},
            {"driver": "other_driver"},
        ):
            manifest.write_text(json.dumps(data | {"expected_uio":
                                      data["expected_uio"] | owner_change}))
            with pytest.raises(root.ImageDeploymentDenied):
                root.read_image_manifest()

    facts = {"observation_kind": "LIVE_ROOT_READ_ONLY", "root": True,
             "boot_id": "observed-boot", "manager_state": "operating",
             "recovery_sha256": release.recovery_sha256,
             "candidate_sha256": release.firmware_sha256,
             "proc_complete": True, "proc_conflicts": [],
             "proc_scan_diagnostic": {"status": "COMPLETE"},
             "platform_overlaps": ["43c00000.audio-codec-ctrl"],
             "uio_overlaps": ["uio0"]}
    kernel = {"uio": "uio0", "platform_node": "43c00000.audio-codec-ctrl",
              "driver": "uio_pdrv_genirq", "maps": [[0x43C00000, 0x10000]],
              "runtime": "suspended"}
    def admit(passive=facts, observed=kernel):
        return admission.check_exact(
            release=release, passive=passive, uio=observed,
            original_manager_load=("fpga_manager fpga0: writing " +
                                   release.firmware_name + " to fpga0"),
            expected_firmware=release.firmware_name)
    assert admit()["mmio_backend"] == "devmem"
    for bad in (facts | {"proc_conflicts": ["321"]},
                facts | {"uio_overlaps": ["uio1"]},
                facts | {"platform_overlaps": ["43c00000.audio-codec-ctrl",
                                               "43c01000.other"]},
                facts | {"manager_state": "unknown"}):
        with pytest.raises(admission.AdmissionDenied):
            admit(passive=bad)
    for bad in (kernel | {"uio": "uio1"},
                kernel | {"driver": "audio_codec_driver"},
                kernel | {"maps": [[0x43C00000, 0x2000]]}):
        with pytest.raises(admission.AdmissionDenied):
            admit(observed=bad)


def test_identity_child_requires_inherited_parent_fence(monkeypatch):
    monkeypatch.delenv("PLASMA_ROOT_RELOAD_FENCE_FD", raising=False)
    with patch.object(root, "trusted_local"):
        with pytest.raises(root.ImageDeploymentDenied,
                           match="IDENTITY_CHILD_RELOAD_FENCE_REQUIRED"):
            root.identity_child()


def test_root_identity_child_subprocess_inherits_only_reviewed_fence(tmp_path,
                                                                    monkeypatch):
    path = tmp_path / "synthetic-fence"
    path.touch()
    fd = os.open(path, os.O_RDONLY)
    monkeypatch.setenv("PLASMA_ROOT_RELOAD_FENCE_FD", "untrusted-override")
    try:
        with patch.object(guard.subprocess, "Popen") as run:
            run.return_value.wait.return_value = 0
            guard.run_child(["fake-python", "--identity-child"],
                            reload_fence_fd=fd)
            kwargs = run.call_args.kwargs
            assert kwargs["pass_fds"] == (fd,)
            assert kwargs["env"]["PLASMA_ROOT_RELOAD_FENCE_FD"] == str(fd)
        with patch.object(guard.subprocess, "Popen") as run:
            run.return_value.wait.return_value = 0
            guard.run_child(["fake-python"])
            kwargs = run.call_args.kwargs
            assert kwargs["pass_fds"] == ()
            assert "PLASMA_ROOT_RELOAD_FENCE_FD" not in kwargs["env"]
    finally:
        os.close(fd)


def test_root_child_exec_keeps_shared_exclusive_flock(tmp_path):
    """Real subprocess inheritance, no /dev/mem or physical FPGA involved."""
    lock = tmp_path / "root-fence"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    competitor = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code = ("import fcntl, os; "
                "fd=int(os.environ['PLASMA_ROOT_RELOAD_FENCE_FD']); "
                "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); "
                "assert os.fstat(fd).st_ino > 0")
        guard.run_child([sys.executable, "-c", code], reload_fence_fd=fd)
        with pytest.raises(BlockingIOError):
            fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(competitor)
        os.close(fd)
