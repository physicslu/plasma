"""Generic Path 2 root-side preflight: real API, offline mocked sysfs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pl.hil.path2_generic_image_loader import (
    ImageProfile, LoaderDenied, VerifiedBundle,
)
from pl.hil.path2_generic_root_preflight import (
    collect_root_preflight, hardware_profile, verify_gp0_hwh_apertures,
)
from pl.hil.swd04 import one_shot


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sample(tmp_path: Path):
    raw = {
        "schema": "plasma.path2.fpga-image.v1",
        "profile_id": "z2-bluepill-swd-v1",
        "project": "pl/projects/z2-bluepill-rbb",
        "source_sha": "a" * 40,
        "candidate_bit_sha256": sha(b"bit"),
        "candidate_hwh_sha256": sha(b"hwh"),
        "candidate_bin": "candidate.bin",
        "candidate_bin_sha256": sha(b"candidate"),
        "recovery_hwh_sha256": sha(b"base.hwh"),
        "recovery_bin": "base.bin",
        "recovery_bin_sha256": sha(b"base"),
    }
    p = ImageProfile.from_protected_manifest(raw,
                                             approved_source_sha="a" * 40)
    bundle = VerifiedBundle(
        p, p.candidate_bit_sha256, p.candidate_hwh_sha256,
        p.candidate_bin_sha256, p.recovery_hwh_sha256,
        p.recovery_bin_sha256)
    manifest = tmp_path / "approved.json"
    manifest.write_text(json.dumps(raw))
    (tmp_path / "candidate.hwh").write_text(
        '<HWH><MEMRANGE MASTERBUSINTERFACE="M_AXI_GP0" '
        'INSTANCE="swd_0" BASEVALUE="0x40008000" '
        'HIGHVALUE="0x40008FFF"/></HWH>')
    inputs = one_shot.Inputs(
        tmp_path / "candidate.bit",
        tmp_path / "candidate.hwh",
        manifest,
        tmp_path / "candidate.bin",
        tmp_path / "base.bin",
        tmp_path / "base.hwh",
        tmp_path / "evidence",
    )
    return bundle, inputs, raw


def test_hardware_profile_is_native_and_inert(tmp_path):
    b, _, _ = sample(tmp_path)
    p = hardware_profile(b, trusted_apertures=(("swd_0", 0x40008000, 4096),))
    assert p.apertures == (("swd_0", 0x40008000, 4096),)
    assert p.bin_sha256 == b.candidate_bin_sha256
    assert p.recovery_sha256 == b.recovery_bin_sha256
    assert p.identity_words == ()
    assert p.abis == ()


@pytest.mark.parametrize("apertures", [
    (), (("swd", 0x40008001, 4096),),
    (("swd", 0x40008000, 0),),
    (("swd", 0x40008000, 2048),),
    (("swd", 0x90000000, 4096),),
    (("swd_0", 0x40008000, 4096), ("alias", 0x40008000, 4096)),
    (("swd", 0x40008000, True),),
    (("swd", 0x40008000, 4096, "unexpected"),),
    (("../escape", 0x40008000, 4096),),
    (("swd_0", 0x40008000, 4096),) * 9,
])
def test_invalid_apertures_rejected(tmp_path, apertures):
    b, _, _ = sample(tmp_path)
    with pytest.raises(LoaderDenied, match="ROOT_APERTURE"):
        hardware_profile(b, trusted_apertures=apertures)


def test_root_preflight_reuses_existing_native_guards_no_write(tmp_path):
    bundle, inputs, _ = sample(tmp_path)
    order = []
    def log(name):
        order.append(name)

    original = Path.read_text
    def read_text(self, *args, **kwargs):
        if str(self) == "/proc/sys/kernel/random/boot_id":
            return "test-boot-id\n"
        return original(self, *args, **kwargs)

    original_bytes = Path.read_bytes
    def read_bytes(self):
        if str(self) == "/proc/device-tree/compatible":
            return b"xlnx,zynq-7000\0"
        return original_bytes(self)

    with patch.object(one_shot, "verify_inputs", side_effect=lambda *a, **k: log("verify")), \
         patch.object(one_shot, "protected", side_effect=lambda *a, **k: log("protected")), \
         patch.object(one_shot, "clock_and_owner", side_effect=lambda *a, **k: log("clock_ownership")), \
         patch.object(one_shot, "service_snapshot", side_effect=lambda: (log("services") or {"plasma": "active"})), \
         patch.object(one_shot, "manager_last_load", side_effect=lambda: (log("manager_log") or
                      "fpga_manager fpga0: writing base.bin to fpga0")), \
         patch.object(one_shot, "manager_write", side_effect=AssertionError("hardware touched")), \
         patch.object(Path, "read_text", read_text), \
         patch.object(Path, "read_bytes", read_bytes):
        result = collect_root_preflight(
            bundle, inputs, approved_source_sha="a" * 40,
            trusted_apertures=(("swd_0", 0x40008000, 4096),))
    assert order == ["verify", "protected", "clock_ownership", "services", "manager_log"]
    assert result["status"] == "NO_GO"
    assert result["hardware_write_authorized"] is False
    assert result["physical_swd"] == "NOT_RUN"
    assert result["current_image"] == "MANAGER_LOG_ONLY_NOT_ATTESTED"
    assert result["boot_id"] == "test-boot-id"


def test_wrong_source_blocked_before_native_guards(tmp_path):
    b, inputs, _ = sample(tmp_path)
    with patch.object(one_shot, "verify_inputs") as guard:
        with pytest.raises(LoaderDenied, match="ROOT_APPROVED_SOURCE"):
            collect_root_preflight(
                b, inputs, approved_source_sha="b" * 40,
                trusted_apertures=(("swd_0", 0x40008000, 4096),))
        guard.assert_not_called()


def test_manifest_tamper_rejected_before_any_hardware_observation(tmp_path):
    bundle, inputs, raw = sample(tmp_path)
    raw["candidate_bin_sha256"] = "b" * 64
    inputs.manifest.write_text(json.dumps(raw))
    with patch.object(one_shot, "verify_inputs"), \
         patch.object(one_shot, "protected"), \
         patch.object(one_shot, "clock_and_owner") as clk, \
         patch.object(one_shot, "manager_write") as write:
        with pytest.raises(LoaderDenied, match="ROOT_INSTALLED_MANIFEST"):
            collect_root_preflight(
                bundle, inputs, approved_source_sha="a" * 40,
                trusted_apertures=(("swd_0", 0x40008000, 4096),))
        clk.assert_not_called()
        write.assert_not_called()


def test_root_preflight_existing_native_guard_fail_closed(tmp_path):
    b, inputs, _ = sample(tmp_path)
    with patch.object(one_shot, "verify_inputs", side_effect=ValueError("NOT_ARMV7")), \
         patch.object(one_shot, "clock_and_owner") as clk, \
         patch.object(one_shot, "manager_write") as write:
        with pytest.raises(ValueError, match="NOT_ARMV7"):
            collect_root_preflight(
                b, inputs, approved_source_sha="a" * 40,
                trusted_apertures=(("swd_0", 0x40008000, 4096),))
        clk.assert_not_called()
        write.assert_not_called()


@pytest.mark.parametrize("fragment,apertures", [
    ('<HWH/>', (("swd_0", 0x40008000, 4096),)),
    ('<HWH><MEMRANGE MASTERBUSINTERFACE="S_AXI_HP0" INSTANCE="swd_0" '
     'BASEVALUE="0x40008000" HIGHVALUE="0x40008FFF"/></HWH>',
     (("swd_0", 0x40008000, 4096),)),
    ('<HWH><MEMRANGE MASTERBUSINTERFACE="M_AXI_GP0" INSTANCE="swd_0" '
     'BASEVALUE="0x40008000" HIGHVALUE="0x40009FFF"/></HWH>',
     (("swd_0", 0x40008000, 4096),)),
    ('<HWH><MEMRANGE MASTERBUSINTERFACE="M_AXI_GP0" INSTANCE="swd_0" '
     'BASEVALUE="0x40008000" HIGHVALUE="0x40008FFF"/></HWH>',
     (("other_0", 0x40008000, 4096),)),
    ('<HWH><MEMRANGE MASTERBUSINTERFACE="M_AXI_GP0" INSTANCE="swd_0" '
     'BASEVALUE="bogus" HIGHVALUE="0x40008FFF"/></HWH>',
     (("swd_0", 0x40008000, 4096),)),
])
def test_hwh_mismatch_and_unsupported_bus_fail_closed(tmp_path, fragment, apertures):
    hwh = tmp_path / "candidate.hwh"
    hwh.write_text(fragment)
    with pytest.raises(LoaderDenied, match="HWH"):
        verify_gp0_hwh_apertures(hwh, apertures)


def test_hwh_exact_map_success(tmp_path):
    hwh = tmp_path / "candidate.hwh"
    hwh.write_text('<HWH><MEMRANGE MASTERBUSINTERFACE="M_AXI_GP0" '
                   'INSTANCE="swd_0" BASEVALUE="0x40008000" '
                   'HIGHVALUE="0x40008FFF"/></HWH>')
    assert verify_gp0_hwh_apertures(
        hwh, (("swd_0", 0x40008000, 4096),)) is None
