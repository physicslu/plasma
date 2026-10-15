"""SWD-04 fake-sysfs inventory tests; no host hardware access."""
from pathlib import Path

import pytest

from pl.hil.swd04.collect import collect, fclk0_from_summary
from pl.hil.swd04.contract import REQUIRED_SERVICES, SafetyError


def fake_z2(tmp_path):
    sysroot = tmp_path / "sys"
    dt = tmp_path / "devicetree"
    clock = tmp_path / "clk_summary"
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    write(sysroot / "class/fpga_manager/fpga0/state", "operating\n")
    write(dt / "model", "TUL PYNQ-Z2\x00")
    write(clock, "clock enable_cnt prepare_cnt protect_cnt rate accuracy phase\n"
                 "   fclk0 1 1 0 100000000 0 0\n")
    write(sysroot / "class/uio/uio17/name", "fabric\n")
    write(sysroot / "class/uio/uio17/maps/map0/addr", "0x40000000\n")
    write(sysroot / "class/uio/uio17/maps/map0/size", "0x00010000\n")
    write(sysroot / "class/uio/uio1/name", "audio-codec-ctrl\n")
    write(sysroot / "class/uio/uio1/maps/map0/addr", "0x43c00000\n")
    write(sysroot / "class/uio/uio1/maps/map0/size", "0x10000\n")
    metadata = tmp_path / "pynq-metadata.bin"
    metadata.write_bytes(b"fixture metadata")
    return sysroot, dt, clock, metadata


def test_read_only_inventory_fake_z2(tmp_path):
    sysroot, dt, clock, metadata = fake_z2(tmp_path)
    seen = []
    def service_status(name):
        seen.append(name)
        return "active"
    snap = collect(sysroot=sysroot, device_tree=dt, clock_summary=clock,
                   metadata_path=metadata, service_status=service_status, architecture="armv7l",
                   pynq_version="3.1.1")
    assert snap["fpga_manager_state"] == "operating"
    assert snap["fclk0_hz"] == 100000000
    assert len(snap["metadata_sha256"]) == 64
    assert snap["device_model_confirmed"] is True
    assert len(snap["uio"]) == 2
    assert next(x for x in snap["uio"] if x["name"] == "fabric")["address"] == "0x40000000"
    assert set(seen) == set(REQUIRED_SERVICES)
    assert snap["pl_consumer_exclusivity"] == "UNVERIFIED_REQUIRES_OPERATOR_ATTESTATION"


@pytest.mark.parametrize("fault", ["clock", "duplicate_clock", "uio_map", "missing_state"])
def test_inventory_fails_on_corrupt_observation(tmp_path, fault):
    sysroot, dt, clock = fake_z2(tmp_path)
    if fault == "clock":
        clock.write_text("empty")
    elif fault == "duplicate_clock":
        clock.write_text("fclk0 1 1 0 100000000\nfclk0 1 1 0 100000000")
    elif fault == "uio_map":
        (sysroot / "class/uio/uio17/maps/map1").mkdir()
    elif fault == "missing_state":
        (sysroot / "class/fpga_manager/fpga0/state").unlink()
    with pytest.raises((OSError, SafetyError)):
        collect(sysroot=sysroot, device_tree=dt, clock_summary=clock,
                metadata_path=metadata, service_status=lambda _: "active", architecture="armv7l",
                pynq_version="3.1.1")


@pytest.mark.parametrize("value", [
    "", "fclk0 1 1 0 not-a-number", "fclk0 1 1 0 100000000\nfclk0 1 1 0 0"
])
def test_no_ambiguous_fclk0(value):
    with pytest.raises(SafetyError):
        fclk0_from_summary(value)
