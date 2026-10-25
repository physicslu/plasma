"""Single generic FPGA Stage with Z2 SWD Image Descriptor: host-only tests."""
from __future__ import annotations

from dataclasses import replace
import json
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

from pl.hil import fpga_configuration_policy as bp

SOURCE = "a" * 40  # synthetic future reviewed exact Git commit (NOT PR HEAD)
OLD_SOURCE = "b" * 40
BIT = b"test-only-bitstream"
HWH = b"test-only-handoff"
BIN = b"test-only-manager-binary"
BASE = b"test-only-original-base-image"
sha = lambda b: hashlib.sha256(b).hexdigest()
DESCRIPTOR_PATH = (Path(__file__).resolve().parents[1] /
                   "projects/z2-bluepill-rbb/image-descriptor.json")


def descriptor():
    """Synthetic locked images; real descriptor has no verified recovery."""
    return replace(
        bp.load_descriptor(DESCRIPTOR_PATH),
        image_build_source_sha=SOURCE,
        bit_sha256=sha(BIT), hwh_sha256=sha(HWH),
        bin_sha256=sha(BIN), recovery_sha256=sha(BASE))


def pinned():
    d = descriptor()
    return bp.ImageLock(d.project, d, SOURCE, SOURCE, SOURCE,
                        sha(BIT), sha(HWH), sha(BIN), sha(BASE))


def observed(lock=None, *, image="base"):
    lock = lock or pinned()
    d = lock.descriptor
    return bp.Observed(
        boot_id="boot-20261024-abcdef", board=d.board, manager="operating",
        active_image_sha256=(lock.recovery_sha256 if image == "base"
                             else lock.bin_sha256),
        candidate_sha256=lock.bin_sha256,
        recovery_sha256=lock.recovery_sha256,
        gp0_base=d.axi_base, gp0_size=d.axi_bytes, fclk_hz=d.fclk_hz,
        pin_map=d.pin_map, source_manifest_verified=True,
        exclusive_fpga_owner=True, consumers_quiesced=True,
        axi_isolation_proved=True, rollback_available=True,
        external_io_isolated=True, active_image_attested=True)


def downloaded(lock=None):
    lock = lock or pinned()
    plan = bp.prepare("download", lock, observed(lock), None)
    return bp.confirm(plan, lock, observed(lock, image="candidate"))[0]


MAGIC = descriptor().read_only_identity[0][1]
ABI = descriptor().read_only_identity[1][1]


def test_synthetic_download_test_restore_and_explicit_noop():
    lock = pinned()
    lock.check_bundle(bit=BIT, hwh=HWH, binary=BIN, original=BASE)
    state, receipt = bp.confirm(
        bp.prepare("download", lock, observed(lock), None),
        lock, observed(lock, image="candidate"))
    assert state.phase == "HELD"
    assert receipt["result"] == "SIMULATED_LOADED_AND_HELD"
    assert receipt["real_z2"] is False
    assert receipt["runtime_admitted"] is False
    assert receipt["hardware_authorized"] is False
    assert "PLASMA_PATH2_STAGE" not in receipt
    state, receipt = bp.confirm(
        bp.prepare("test", lock, observed(lock, image="candidate"), state),
        lock, observed(lock, image="candidate"),
        abi_reads=(MAGIC, ABI, 0x08), write_count=0)
    assert state.phase == "HELD" and receipt["result"] == "SIMULATED_IDENTITY_PASS"
    state, receipt = bp.confirm(
        bp.prepare("restore", lock, observed(lock, image="candidate"), state),
        lock, observed(lock))
    assert state.phase == "BASE"
    assert receipt["result"] == "SIMULATED_RESTORED_VERIFIED"
    state, receipt = bp.confirm(
        bp.prepare("restore", lock, observed(lock), state),
        lock, observed(lock))
    assert receipt["result"] == "SIMULATED_ALREADY_RESTORED"


@pytest.mark.parametrize("bad_lock,reason", [
    ({"project": "pl/projects/z2-fixed-unified-site1"}, "PROJECT_MISMATCH"),
    ({"reviewed_source_sha": "bad"}, "SOURCE_SHA_INVALID"),
    ({"reviewed_source_sha": OLD_SOURCE}, "EXECUTOR_SOURCE_PIN_MISMATCH"),
    ({"installed_source_sha": OLD_SOURCE}, "EXECUTOR_SOURCE_PIN_MISMATCH"),
    ({"image_build_source_sha": OLD_SOURCE}, "IMAGE_DESCRIPTOR_HASH_OR_SOURCE_MISMATCH"),
    ({"bit_sha256": "bad"}, "IMAGE_SHA_INVALID"),
    ({"hwh_sha256": "bad"}, "IMAGE_SHA_INVALID"),
    ({"bin_sha256": "bad"}, "IMAGE_SHA_INVALID"),
    ({"recovery_sha256": sha(BIN)}, "CANDIDATE_IS_RECOVERY"),
])
def test_manifest_and_image_source_fail_closed(bad_lock, reason):
    with pytest.raises(bp.StageDenied, match=reason):
        bp.prepare("download", replace(pinned(), **bad_lock), observed(), None)


@pytest.mark.parametrize("bad_blob", ["bit", "hwh", "binary", "original"])
def test_image_bundle_actual_bytes_must_match(bad_blob):
    images = {"bit": BIT, "hwh": HWH, "binary": BIN, "original": BASE}
    images[bad_blob] += b"tampered"
    with pytest.raises(bp.StageDenied, match="IMAGE_BUNDLE_HASH_MISMATCH"):
        pinned().check_bundle(**images)


@pytest.mark.parametrize("key,value,reason", [
    ("boot_id", "", "TARGET_BOOT_OR_BOARD_UNPROVEN"),
    ("board", "wrong-board", "TARGET_BOOT_OR_BOARD_UNPROVEN"),
    ("manager", "error", "TARGET_BOOT_OR_BOARD_UNPROVEN"),
    ("active_image_sha256", "c" * 64, "ORIGINAL_IMAGE_NOT_ATTESTED"),
    ("candidate_sha256", "d" * 64, "TARGET_IMAGE_IDENTITY_MISMATCH"),
    ("recovery_sha256", "d" * 64, "TARGET_IMAGE_IDENTITY_MISMATCH"),
    ("gp0_base", 0x40000000, "TARGET_GP0_CLOCK_OR_PIN_MISMATCH"),
    ("gp0_size", 0x10000, "TARGET_GP0_CLOCK_OR_PIN_MISMATCH"),
    ("fclk_hz", 10_000_000, "TARGET_GP0_CLOCK_OR_PIN_MISMATCH"),
    ("pin_map", (("swclk", "Y14"), ("swdio", "Y14")),
     "TARGET_GP0_CLOCK_OR_PIN_MISMATCH"),
    ("pin_map", (("swclk", "W14"), ("swdio", "W14")),
     "TARGET_GP0_CLOCK_OR_PIN_MISMATCH"),
    ("source_manifest_verified", False, "OWNER_ISOLATION_OR_RECOVERY_UNPROVEN"),
    ("exclusive_fpga_owner", False, "OWNER_ISOLATION_OR_RECOVERY_UNPROVEN"),
    ("consumers_quiesced", False, "OWNER_ISOLATION_OR_RECOVERY_UNPROVEN"),
    ("axi_isolation_proved", False, "OWNER_ISOLATION_OR_RECOVERY_UNPROVEN"),
    ("rollback_available", False, "OWNER_ISOLATION_OR_RECOVERY_UNPROVEN"),
    ("external_io_isolated", False, "OWNER_ISOLATION_OR_RECOVERY_UNPROVEN"),
    ("active_image_attested", False, "OWNER_ISOLATION_OR_RECOVERY_UNPROVEN"),
])
def test_all_preconditions_fail_closed(key, value, reason):
    with pytest.raises(bp.StageDenied, match=reason):
        bp.prepare("download", pinned(),
                   replace(observed(), **{key: value}), None)


@pytest.mark.parametrize("stage", ["test", "restore", "download-and-test",
                                   "flash", "", "DOWNLOAD"])
def test_no_implicit_load_and_no_unrecognized_stage(stage):
    with pytest.raises(bp.StageDenied, match=(
         "DOWNLOAD_REQUIRED" if stage in {"test", "restore"}
         else "STAGE_NOT_ALLOWLISTED")):
        bp.prepare(stage, pinned(), observed(), None)


@pytest.mark.parametrize("phase", ["UNKNOWN", "DOWNLOAD_IN_FLIGHT",
                                   "TEST_IN_FLIGHT", "RESTORE_IN_FLIGHT"])
def test_inflight_or_unknown_state_never_retries(phase):
    lock = pinned()
    state = replace(downloaded(), phase=phase)
    with pytest.raises(bp.StageDenied, match="STALE_BOOT_OR_IN_FLIGHT"):
        bp.prepare("restore", lock, observed(image="candidate"), state)


def test_boot_switch_does_not_preserve_authorization():
    state = downloaded()
    with pytest.raises(bp.StageDenied, match="STALE_BOOT"):
        bp.prepare("restore", pinned(), replace(observed(image="candidate"),
                   boot_id="next-boot-id-after-reset"), state)


def test_no_auto_download_from_held_and_no_test_without_held():
    state = downloaded()
    with pytest.raises(bp.StageDenied, match="DUPLICATE_DOWNLOAD"):
        bp.prepare("download", pinned(), observed(image="candidate"), state)
    base_state = bp.StageState(observed().boot_id, SOURCE, "BASE", pinned().recovery_sha256)
    with pytest.raises(bp.StageDenied, match="TEST_REQUIRES_HELD_IMAGE"):
        bp.prepare("test", pinned(), observed(), base_state)


@pytest.mark.parametrize("readbacks", [
    (), (MAGIC,), (MAGIC, ABI, 0x0),
    (MAGIC, ABI, 0x0C), (MAGIC, ABI + 1, 0x08),
    (0x1BA01477, ABI, 0x08), (MAGIC, ABI, -1),
    (MAGIC, ABI, 0x18),
])
def test_identity_and_swdio_hi_z_fail_closed(readbacks):
    lock = pinned()
    plan = bp.prepare("test", lock, observed(image="candidate"), downloaded())
    with pytest.raises(bp.StageDenied, match="IMAGE_READ_ONLY_IDENTITY"):
        bp.confirm(plan, lock, observed(image="candidate"), abi_reads=readbacks)


def test_test_readonly_and_download_never_accept_spurious_mmio_or_writes():
    lock = pinned()
    plan = bp.prepare("test", lock, observed(image="candidate"), downloaded())
    with pytest.raises(bp.StageDenied, match="UNEXPECTED_REGISTER_WRITE"):
        bp.confirm(plan, lock, observed(image="candidate"),
                   abi_reads=(MAGIC, ABI, 8), write_count=1)
    plan = bp.prepare("download", lock, observed(), None)
    with pytest.raises(bp.StageDenied, match="UNEXPECTED_MMIO_OBSERVATION"):
        bp.confirm(plan, lock, observed(image="candidate"),
                   abi_reads=(MAGIC, ABI, 8))


def test_post_download_image_and_boot_mismatch_never_qualifies():
    lock = pinned()
    plan = bp.prepare("download", lock, observed(), None)
    with pytest.raises(bp.StageDenied, match="STAGE_AFTER_IDENTITY"):
        bp.confirm(plan, lock, observed())
    with pytest.raises(bp.StageDenied, match="STAGE_AFTER_IDENTITY"):
        bp.confirm(plan, lock, replace(observed(image="candidate"),
                                      boot_id="another-boot-after-load"))


@pytest.mark.parametrize("modifications", [
    {"stage": "test"},
    {"action": "PLAN_RESTORED_NOOP"},
    {"expected_image_sha256": sha(BASE)},
    {"current": bp.StageState("another-boot", SOURCE, "BASE", sha(BASE))},
    {"current": bp.StageState("boot-20261024-abcdef", SOURCE,
                              "UNKNOWN", sha(BASE))},
])
def test_directly_forged_stage_plan_must_fail(modifications):
    lock = pinned()
    plan = bp.prepare("download", lock, observed(), None)
    with pytest.raises(bp.StageDenied, match="STAGE_PLAN_"):
        bp.confirm(replace(plan, **modifications),
                   lock, observed(image="candidate"))


def test_no_real_generic_stage_entrypoint_or_accidental_f1b_waiver():
    # Calling it as an installed root-entry module must fail before ANY action.
    script = Path(bp.__file__).resolve()
    # Existing protected Root Entry invokes reviewed stages as -m modules.
    result = subprocess.run(
        [sys.executable, "-m", "pl.hil.fpga_configuration_policy", "download"],
        cwd=script.parents[2], capture_output=True, text=True, timeout=8)
    assert result.returncode == 2
    assert "GENERIC_FPGA_CONFIGURATION_LIVE_BACKEND_NOT_IMPLEMENTED" in result.stderr
    assert "PLASMA_PATH2_STAGE=" not in result.stdout
    source = script.read_text()
    assert "path2_f1b_dev_risk" not in source
    assert "one_shot.manager_write(" not in source
    assert "os.system(" not in source
    assert "subprocess.Popen(" not in source


def test_real_historical_image_descriptor_is_not_runtime_admitted():
    historic = bp.load_descriptor(DESCRIPTOR_PATH)
    assert historic.image_build_source_sha == (
        "65555410f171e425e61d87ebd42dc4709755f389")
    assert historic.bit_sha256 == (
        "f2e59f31bacf6e8ab0ee9325a07125bc155647a261db3f84e67ba71bb0105891")
    assert historic.hwh_sha256 == (
        "84894ae5791a65ec16bd6146779faec4496d47833fd0ad294149d5c46571b510")
    assert historic.bin_sha256 == (
        "bfbd3d872caeff05a8f9daa0829b6292e5b5036c6c6b927d6c779e13fe9ec1a1")
    assert historic.recovery_sha256 is None
    assert historic.runtime_admitted is False
    assert historic.site_count == 1
    with pytest.raises(bp.StageDenied, match="RECOVERY_IMAGE_NOT_QUALIFIED"):
        bp.ImageLock(historic.project, historic,
                     historic.image_build_source_sha,
                     historic.image_build_source_sha,
                     historic.image_build_source_sha,
                     historic.bit_sha256, historic.hwh_sha256,
                     historic.bin_sha256, sha(BASE)).validate()


@pytest.mark.parametrize("field,value,reason", [
    ("site_count", 9, "IMAGE_DESCRIPTOR_IDENTITY_INVALID"),
    ("runtime_admitted", True, "IMAGE_DESCRIPTOR_PROVENANCE_INVALID"),
    ("external_io_timing", "QUALIFIED", "IMAGE_DESCRIPTOR_EXTERNAL_IO_UNQUALIFIED"),
    ("external_io_timing", "", "IMAGE_DESCRIPTOR_EXTERNAL_IO_UNQUALIFIED"),
    ("axi_base", 0x40008001, "IMAGE_DESCRIPTOR_AXI_INVALID"),
    ("axi_bytes", 0, "IMAGE_DESCRIPTOR_AXI_INVALID"),
    ("fclk_hz", 0, "IMAGE_DESCRIPTOR_AXI_INVALID"),
    ("pin_map", (("swclk", "W14"), ("swdio", "W14")),
     "IMAGE_DESCRIPTOR_PINS_INVALID"),
    ("read_only_identity", ((0, 0, 0),),
     "IMAGE_DESCRIPTOR_IDENTITY_INVALID"),
    ("read_only_identity", ((0, 1, 0xffffffff), (0, 2, 0xffffffff)),
     "IMAGE_DESCRIPTOR_IDENTITY_INVALID"),
    ("image_build_source_sha", "bad",
     "IMAGE_DESCRIPTOR_PROVENANCE_INVALID"),
])
def test_image_descriptor_does_not_accept_forged_geometry(field, value, reason):
    with pytest.raises(bp.StageDenied, match=reason):
        replace(descriptor(), **{field: value}).validate()


def test_descriptor_rejects_unknown_fields_and_malformed_json(tmp_path):
    raw = json.loads(DESCRIPTOR_PATH.read_text())
    raw["privileged_firmware_path"] = "/lib/firmware/unapproved.bin"
    with pytest.raises(bp.StageDenied, match="IMAGE_DESCRIPTOR_SCHEMA_INVALID"):
        bp.ImageDescriptor.from_mapping(raw)
    file = tmp_path / "descriptor.json"
    file.write_text("{broken")
    with pytest.raises(bp.StageDenied, match="IMAGE_DESCRIPTOR_FILE_INVALID"):
        bp.load_descriptor(file)


def test_new_executor_pin_does_not_promote_historical_recovery():
    historic = bp.load_descriptor(DESCRIPTOR_PATH)
    changed_sha = "c48c0a014ff9642242a9c107b5624ba97a387235"
    with pytest.raises(bp.StageDenied, match="RECOVERY_IMAGE_NOT_QUALIFIED"):
        bp.ImageLock(historic.project, historic, changed_sha, changed_sha,
                     historic.image_build_source_sha, historic.bit_sha256,
                     historic.hwh_sha256, historic.bin_sha256,
                     sha(BASE)).validate()

def test_generic_prepare_confirm_accepts_independent_image_build_provenance():
    lock = pinned()
    lock = replace(lock, descriptor=replace(
        lock.descriptor, image_build_source_sha=OLD_SOURCE),
        image_build_source_sha=OLD_SOURCE)
    lock.check_bundle(bit=BIT, hwh=HWH, binary=BIN, original=BASE)
    plan = bp.prepare("download", lock, observed(lock), None)
    state, receipt = bp.confirm(plan, lock, observed(lock, image="candidate"))
    assert state.phase == "HELD"
    assert receipt["runtime_admitted"] is False
    assert receipt["real_z2"] is False
