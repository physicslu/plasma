"""Generic FPGA maintenance policy: multiple projects, no IC-specific load."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

from pl.hil import fpga_configuration_policy as cfg

SOURCE = "a" * 40
RECOVERY = b"test-recovery"
BIT = b"test-bit"
HWH = b"test-hwh"
BIN = b"test-bin"
sha = lambda value: hashlib.sha256(value).hexdigest()


@pytest.mark.parametrize("project", [
    "pl/projects/z2-bluepill-rbb",
    "pl/projects/z2-fixed-universal",
    "pl/projects/z2-swd-validation",
])
def test_same_generic_lock_for_independent_hardware_projects(project):
    cfg.validate_source_lock(
        project=project, expected_project=project,
        reviewed_sha=SOURCE, installed_sha=SOURCE, build_sha=SOURCE,
        bit_sha=sha(BIT), hwh_sha=sha(HWH), bin_sha=sha(BIN),
        original_sha=sha(RECOVERY))


def test_exact_source_hashes_and_recovery_are_independent_of_ic():
    cfg.validate_bundle(
        bit=BIT, hwh=HWH, binary=BIN, original=RECOVERY,
        bit_sha=sha(BIT), hwh_sha=sha(HWH),
        bin_sha=sha(BIN), original_sha=sha(RECOVERY))
    with pytest.raises(cfg.StageDenied, match="IMAGE_BUNDLE_HASH_MISMATCH"):
        cfg.validate_bundle(
            bit=BIT, hwh=HWH, binary=BIN, original=RECOVERY + b"bad",
            bit_sha=sha(BIT), hwh_sha=sha(HWH),
            bin_sha=sha(BIN), original_sha=sha(RECOVERY))


@pytest.mark.parametrize("reviewed,installed,build,reason", [
    (SOURCE, SOURCE, "b" * 40, "IMAGE_SOURCE_REBUILD_REQUIRED"),
    (SOURCE, "b" * 40, SOURCE, "IMAGE_SOURCE_REBUILD_REQUIRED"),
    ("b" * 40, SOURCE, SOURCE, "IMAGE_SOURCE_REBUILD_REQUIRED"),
    ("z" * 40, SOURCE, SOURCE, "SOURCE_SHA_INVALID"),
    (SOURCE, "0" * 40, SOURCE, "SOURCE_SHA_INVALID"),
])
def test_reject_stale_or_invalid_image_source(reviewed, installed, build, reason):
    with pytest.raises(cfg.StageDenied, match=reason):
        cfg.validate_source_lock(
            project="pl/projects/z2-fixed-universal",
            expected_project="pl/projects/z2-fixed-universal",
            reviewed_sha=reviewed, installed_sha=installed, build_sha=build,
            bit_sha=sha(BIT), hwh_sha=sha(HWH), bin_sha=sha(BIN),
            original_sha=sha(RECOVERY))


@pytest.mark.parametrize("stage,phase,action", [
    ("download", "BASE", "PLAN_DOWNLOAD"),
    ("test", "HELD", "PLAN_READ_ONLY_ABI"),
    ("restore", "HELD", "PLAN_RESTORE"),
    ("restore", "BASE", "PLAN_RESTORED_NOOP"),
])
def test_stage_transitions_are_ic_agnostic(stage, phase, action):
    assert cfg.choose_stage(stage, phase) == action
    cfg.validate_stage_plan(
        stage=stage, phase=phase, action=action,
        expected_image_sha=(sha(BIN) if action in (
            "PLAN_DOWNLOAD", "PLAN_READ_ONLY_ABI") else sha(RECOVERY)),
        candidate_sha=sha(BIN), original_sha=sha(RECOVERY))


@pytest.mark.parametrize("stage", [
    "probe", "erase", "program", "read", "verify", "flash", "job",
    "select-ic", "select-provider", "switch-interface", "download-and-test",
])
def test_programming_jobs_never_become_fpga_image_reload(stage):
    with pytest.raises(cfg.StageDenied, match="STAGE_NOT_ALLOWLISTED"):
        cfg.choose_stage(stage, "BASE")


@pytest.mark.parametrize("stage,phase,reason", [
    ("download", "HELD", "DUPLICATE_DOWNLOAD_DENIED"),
    ("test", "BASE", "TEST_REQUIRES_HELD_IMAGE"),
    ("restore", "UNKNOWN", "STALE_BOOT_OR_IN_FLIGHT_MANUAL_RECOVERY"),
    ("restore", "DOWNLOAD_IN_FLIGHT",
     "STALE_BOOT_OR_IN_FLIGHT_MANUAL_RECOVERY"),
])
def test_invalid_configuration_transition_fails_closed(stage, phase, reason):
    with pytest.raises(cfg.StageDenied, match=reason):
        cfg.choose_stage(stage, phase)


@pytest.mark.parametrize("action,expected", [
    ("PLAN_RESTORE", "candidate"),
    ("PLAN_DOWNLOAD", "original"),
    ("PLAN_RESTORED_NOOP", "candidate"),
    ("PLAN_READ_ONLY_ABI", "original"),
])
def test_forged_stage_action_or_hash_fails(action, expected):
    with pytest.raises(cfg.StageDenied, match="STAGE_PLAN_TAMPERED"):
        cfg.validate_stage_plan(
            stage="download", phase="BASE", action=action,
            expected_image_sha=(sha(BIN) if expected == "candidate"
                                else sha(RECOVERY)),
            candidate_sha=sha(BIN), original_sha=sha(RECOVERY))


def test_generic_module_has_no_privileged_live_entrypoint():
    script = Path(cfg.__file__)
    p = subprocess.run([sys.executable, str(script), "download"],
                       capture_output=True, text=True, timeout=8)
    assert p.returncode == 2
    assert "GENERIC_FPGA_CONFIGURATION_LIVE_BACKEND_NOT_IMPLEMENTED" in p.stderr
    assert "PLASMA_PATH2_STAGE=" not in p.stdout

# Additive candidate contract: deliberately no candidate Git SHA/executor SHA.
def candidate_args():
    hardware = cfg.CandidateHardware(
        board="pynq-z2", fpga_part="xc7z020clg400-1", abi="swd-gpio-v1",
        axi_base=0x40008000, axi_bytes=4096, fclk_hz=100_000_000,
        site_count=1, pin_map=(("swclk", "W14"), ("swdio", "Y14")))
    return dict(image=BIN, image_sha256=sha(BIN), descriptor=hardware,
                measured=hardware, recovery=RECOVERY,
                recovery_sha256=sha(RECOVERY), exclusive_owner=True,
                consumers_quiesced=True, axi_isolated=True,
                external_io_isolated=True, all_sites_idle=True,
                admission_locked=True)


def test_candidate_integrity_without_image_source_provenance():
    assert cfg.validate_candidate(**candidate_args()) is None


@pytest.mark.parametrize("field", [
    "exclusive_owner", "consumers_quiesced", "axi_isolated",
    "external_io_isolated", "all_sites_idle", "admission_locked"])
@pytest.mark.parametrize("value", [False, None, 1, "true"])
def test_candidate_requires_each_real_owner_input(field, value):
    args = candidate_args()
    args[field] = value
    with pytest.raises(cfg.StageDenied):
        cfg.validate_candidate(**args)


@pytest.mark.parametrize("field,value", [
    ("board", "other-board"), ("fpga_part", "xc7z010clg400-1"),
    ("abi", "incompatible-v2"), ("axi_base", 0x40000000),
    ("axi_bytes", 8192), ("fclk_hz", 10_000_000), ("site_count", 2),
    ("pin_map", (("swclk", "Y14"), ("swdio", "W14")))])
def test_candidate_checks_measured_descriptor_compatibility(field, value):
    from dataclasses import replace
    args = candidate_args()
    args["measured"] = replace(args["measured"], **{field: value})
    with pytest.raises(cfg.StageDenied, match="CANDIDATE_HARDWARE_MISMATCH"):
        cfg.validate_candidate(**args)


@pytest.mark.parametrize("field,value", [
    ("image", b"tampered"), ("recovery", b"tampered"),
    ("image", b""), ("recovery", b""),
    ("image_sha256", None), ("image_sha256", "0" * 64),
    ("recovery_sha256", None), ("descriptor", None), ("measured", None)])
def test_candidate_fails_closed_on_missing_or_bad_bytes(field, value):
    args = candidate_args()
    args[field] = value
    with pytest.raises(cfg.StageDenied):
        cfg.validate_candidate(**args)


def test_candidate_rejects_recovery_as_candidate():
    args = candidate_args()
    args.update(image=RECOVERY, image_sha256=sha(RECOVERY))
    with pytest.raises(cfg.StageDenied, match="CANDIDATE_IS_RECOVERY"):
        cfg.validate_candidate(**args)


@pytest.mark.parametrize("field,value", [
    ("board", None), ("fpga_part", ""), ("abi", True),
    ("axi_base", True), ("axi_base", 0x40008001),
    ("axi_bytes", 0), ("fclk_hz", True), ("site_count", 0),
    ("pin_map", ()), ("pin_map", (["swclk", "W14"],)),
    ("pin_map", (("swclk", "W14"), ("swdio", "W14"))),
    ("pin_map", (("swclk", "W14"), ("swclk", "Y14"))),
])
def test_candidate_malformed_descriptor_denied(field, value):
    from dataclasses import replace
    args = candidate_args()
    args["descriptor"] = replace(args["descriptor"], **{field: value})
    with pytest.raises(cfg.StageDenied):
        cfg.validate_candidate(**args)
