"""Fake-/sys, fake-/proc tests. No hardware, SSH, MMIO or network."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from pl.tools.z2_kernel_dt_readonly import (
    InventoryRefused, _read, collect, main,
)

BOOT = "01234567-89ab-cdef-0123-456789abcdef"


@pytest.fixture
def fake(tmp_path: Path) -> dict:
    sysroot, procroot = tmp_path / "sys", tmp_path / "proc"
    sysroot.mkdir()
    procroot.mkdir()

    def place(root: Path, relative: str, raw: bytes) -> Path:
        p = root / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        return p

    place(procroot, "sys/kernel/random/boot_id", (BOOT + "\n").encode())
    place(procroot, "sys/kernel/osrelease", b"6.6.10-xilinx-fixture\n")
    place(procroot, "version", b"Linux version synthetic@private-host\n")
    plain = (b"CONFIG_FPGA_MGR_ZYNQ_FPGA=y\n"
             b"CONFIG_FPGA_BRIDGE=y\n"
             b"CONFIG_OF_FPGA_REGION=y\n"
             b"CONFIG_UIO_PDRV_GENIRQ=m\n"
             b"# CONFIG_FPGA_MGR_ZYNQ_AFI_FPGA is not set\n")
    compressed = gzip.compress(plain)
    place(procroot, "config.gz", compressed)
    place(sysroot, "firmware/devicetree/base/model", b"PYNQ-Z2 fixture\x00")
    place(sysroot, "firmware/devicetree/base/compatible",
          b"xlnx,zynq-7000\x00fixture,board\x00")
    place(sysroot, "firmware/fdt", b"\xd0\x0d\xfe\xed-fake-dtb-only")

    device = sysroot / "devices/soc0/axi/f8007000.devcfg"
    device.mkdir(parents=True)
    drivers = sysroot / "bus/platform/drivers/zynq_fpga_manager"
    drivers.mkdir(parents=True)
    (device / "driver").symlink_to(drivers, target_is_directory=True)
    place(sysroot, "devices/soc0/axi/f8007000.devcfg/of_node/compatible",
          b"xlnx,zynq-devcfg-1.0\x00")
    place(sysroot, "devices/soc0/axi/f8007000.devcfg/of_node/syscon",
          b"\x00\x00\x00\x01")
    mgr = sysroot / "class/fpga_manager/fpga0"
    mgr.mkdir(parents=True)
    place(sysroot, "class/fpga_manager/fpga0/state", b"operating\n")
    (mgr / "device").symlink_to(device, target_is_directory=True)

    regiondev = sysroot / "devices/platform/region-device"
    regiondev.mkdir(parents=True)
    rd = sysroot / "bus/platform/drivers/of-fpga-region"
    rd.mkdir(parents=True)
    (regiondev / "driver").symlink_to(rd, target_is_directory=True)
    place(sysroot, "devices/platform/region-device/of_node/fpga-mgr",
          b"\x00\x00\x00\x03")
    region = sysroot / "class/fpga_region/region0"
    region.mkdir(parents=True)
    (region / "device").symlink_to(regiondev, target_is_directory=True)
    (sysroot / "class/fpga_bridge").mkdir(parents=True)

    uio = sysroot / "class/uio/uio0"
    place(sysroot, "class/uio/uio0/name", b"fabric\n")
    for k, v in (("addr", "0x40000000"), ("size", "0x10000"),
                 ("offset", "0")):
        place(sysroot, "class/uio/uio0/maps/map0/" + k, v.encode())
    udev = sysroot / "devices/platform/fabric"
    udev.mkdir(parents=True)
    ud = sysroot / "bus/platform/drivers/uio_pdrv_genirq"
    ud.mkdir(parents=True)
    (udev / "driver").symlink_to(ud, target_is_directory=True)
    (uio / "device").symlink_to(udev, target_is_directory=True)
    return {"sys": sysroot, "proc": procroot, "compressed": compressed,
            "plain": plain, "tmp": tmp_path}


def test_snapshot_correctly_reads_only_relevant_safe_nodes(fake):
    report = collect(fake["sys"], fake["proc"])
    assert report["schema"] == "plasma-z2-kernel-dt-readonly-inventory-v1"
    assert report["boot_id_sha256"] == hashlib.sha256(BOOT.encode()).hexdigest()
    assert BOOT not in json.dumps(report)
    assert "private-host" not in json.dumps(report)
    assert report["kernel_release"] == "6.6.10-xilinx-fixture"
    assert report["kernel_config"]["compressed_sha256"] == hashlib.sha256(fake["compressed"]).hexdigest()
    assert report["kernel_config"]["plain_sha256"] == hashlib.sha256(fake["plain"]).hexdigest()
    assert report["kernel_config"]["flags"]["CONFIG_UIO_PDRV_GENIRQ"] == "m"
    assert report["kernel_config"]["flags"]["CONFIG_FPGA_MGR_ZYNQ_AFI_FPGA"] == "n"
    assert report["device_tree"]["model"] == "PYNQ-Z2 fixture"
    assert report["device_tree"]["compatible"] == ["xlnx,zynq-7000", "fixture,board"]
    assert report["device_tree"]["firmware_fdt_available"]
    assert report["device_tree"]["fdt_hash_is_complete_active_dt_attestation"] is False
    assert report["fpga_managers"][0]["driver"] == "zynq_fpga_manager"
    assert report["fpga_managers"][0]["compatible"] == ["xlnx,zynq-devcfg-1.0"]
    assert report["fpga_regions"][0]["driver"] == "of-fpga-region"
    assert report["fpga_regions"][0]["dt_fpga_bridges_property_sha256"] is None
    assert report["fpga_bridges"] == []
    assert report["fabric_uio"][0]["maps"][0] == {
        "index": "map0", "addr": "0x40000000",
        "size": "0x10000", "offset": "0",
    }
    assert report["source_commit_matching_running_binary"] == "UNRESOLVED"
    assert report["kernel_binary_identity"] == "UNRESOLVED"
    assert report["kernel_patchset_identity"] == "UNRESOLVED"
    assert report["source_kind"] == "CALLER_SUPPLIED_SYSROOT_PROCROOT_UNATTESTED"
    assert not report["reload_authorized"] and not report["hardware_ready"]
    assert report["m1_verdict"] == "NO_GO"


def test_collector_never_modifies_fixture_files(fake):
    files = [p for p in fake["tmp"].rglob("*") if p.is_file() and not p.is_symlink()]
    originals = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    before = {str(p.relative_to(fake["tmp"])) for p in fake["tmp"].rglob("*")}
    collect(fake["sys"], fake["proc"])
    after = {str(p.relative_to(fake["tmp"])) for p in fake["tmp"].rglob("*")}
    assert before == after
    assert originals == {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in files}


@pytest.mark.parametrize("relative", ["sys/kernel/random/boot_id",
                                      "sys/kernel/osrelease"])
def test_mandatory_boot_and_release_missing_fail_closed(fake, relative):
    (fake["proc"] / relative).unlink()
    with pytest.raises(InventoryRefused, match="Missing"):
        collect(fake["sys"], fake["proc"])


def test_invalid_boot_id_rejected(fake):
    (fake["proc"] / "sys/kernel/random/boot_id").write_text("fixture-not-uuid")
    with pytest.raises(InventoryRefused, match="boot ID"):
        collect(fake["sys"], fake["proc"])


def test_optional_kernel_config_unavailable_is_not_attested(fake):
    (fake["proc"] / "config.gz").unlink()
    report = collect(fake["sys"], fake["proc"])
    assert report["kernel_config"]["status"] == "UNAVAILABLE"
    assert report["kernel_config"]["plain_sha256"] is None
    assert report["m1_verdict"] == "NO_GO"


def test_missing_dt_and_bridge_is_unknown_not_absence_proof(fake):
    (fake["sys"] / "firmware/fdt").unlink()
    (fake["sys"] / "firmware/devicetree/base/model").unlink()
    (fake["sys"] / "class/fpga_bridge").rmdir()
    report = collect(fake["sys"], fake["proc"])
    assert not report["device_tree"]["firmware_fdt_available"]
    assert report["device_tree"]["model"] is None
    assert report["fpga_bridges"] is None
    assert report["m1_verdict"] == "NO_GO"


def test_registered_bridge_is_not_a_drain_receipt(fake):
    (fake["sys"] / "class/fpga_bridge/fpga_bridge0").mkdir()
    result = collect(fake["sys"], fake["proc"])
    assert result["fpga_bridges"] == ["fpga_bridge0"]
    assert result["dma_axi_quiescence_proven"] is False
    assert result["reload_authorized"] is False


def test_broken_config_gzip_fails_closed(fake):
    (fake["proc"] / "config.gz").write_bytes(b"not a gzip")
    with pytest.raises(InventoryRefused, match="Malformed"):
        collect(fake["sys"], fake["proc"])


def test_symlink_outside_root_rejected(fake):
    f = fake["proc"] / "config.gz"
    f.unlink()
    secret = fake["tmp"] / "private.txt"
    secret.write_text("should never read")
    f.symlink_to(secret)
    with pytest.raises(InventoryRefused, match="outside input root"):
        collect(fake["sys"], fake["proc"])


def test_sysfs_symlink_outside_root_rejected(fake):
    fake["sys"].joinpath("class/fpga_manager/fpga0/device").unlink()
    fake["sys"].joinpath("class/fpga_manager/fpga0/device").symlink_to(
        fake["proc"], target_is_directory=True)
    (fake["proc"] / "of_node").mkdir()
    (fake["proc"] / "of_node/compatible").write_bytes(b"unexpected\\x00")
    with pytest.raises(InventoryRefused, match="outside input root"):
        collect(fake["sys"], fake["proc"])


def test_oversized_fdt_rejected(fake):
    (fake["sys"] / "firmware/fdt").write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    with pytest.raises(InventoryRefused, match="too large"):
        collect(fake["sys"], fake["proc"])


def test_reject_path_traversal(fake):
    with pytest.raises(InventoryRefused, match="Forbidden"):
        _read(fake["sys"], "../proc/version")


def test_cli_sanitizes_blocker_without_raw_file_paths(fake, capsys):
    assert main(["--sysroot", str(fake["sys"]), "--procroot",
                 str(fake["proc"])]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["m1_verdict"] == "NO_GO"
    bad = fake["proc"] / "sys/kernel/random/boot_id"
    bad.unlink()
    assert main(["--sysroot", str(fake["sys"]), "--procroot",
                 str(fake["proc"])]) == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["result"] == "BLOCKED"
    assert blocked["reload_authorized"] is False
    assert str(fake["tmp"]) not in json.dumps(blocked)


def test_boot_is_sampled_twice_and_consistency_is_explicit(fake):
    report = collect(fake["sys"], fake["proc"])
    assert report["boot_and_kernel_two_sample_consistency"] == "MATCHED"
    assert report["collection_started_at_utc"] <= report["collected_at_utc"]


@pytest.mark.parametrize("attribute,replacement", [
    ("sys/kernel/random/boot_id", "ffffffff-ffff-ffff-ffff-ffffffffffff\\n"),
    ("sys/kernel/osrelease", "7.0-changed-kernel\\n"),
])
def test_reboot_or_kernel_change_mid_snapshot_fails_closed(
        fake, monkeypatch, attribute, replacement):
    import pl.tools.z2_kernel_dt_readonly as collector

    original = collector._read
    observations = {"count": 0}

    def double_read(root, relative, limit=collector.MAX_SYSFS):
        if root == fake["proc"] and relative == attribute:
            observations["count"] += 1
            if observations["count"] == 2:
                return replacement.encode()
        return original(root, relative, limit)

    monkeypatch.setattr(collector, "_read", double_read)
    with pytest.raises(InventoryRefused, match="changed during collection"):
        collect(fake["sys"], fake["proc"])
    assert observations["count"] == 2
