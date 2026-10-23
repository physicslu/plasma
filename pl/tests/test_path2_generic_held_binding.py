"""Host-only generic Profile → current Held Provider ABI boundary."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import pytest

from pl.hil.path2_generic_image_loader import (
    ImageProfile, LoaderDenied, verify_offline_bundle,
)
from pl.hil.path2_generic_held_binding import (
    validate_held_binding, require_existing_f1b_identity_test,
    root_port_not_registered,
)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sample(tmp_path: Path, *, profile_id="z2-bluepill-swd-v1",
           project="pl/projects/z2-bluepill-rbb"):
    artifacts = tmp_path / "artifacts"
    firmware = tmp_path / "firmware"
    artifacts.mkdir(); firmware.mkdir()
    values = {
        "bit": b"real-bit-fixture",
        "hwh": b"real-hwh-fixture",
        "bin": b"real-firmware-fixture",
        "recovery_hwh": b"original-hwh-fixture",
        "recovery_bin": b"original-firmware-fixture",
    }
    for name, loc in (
        ("bit", artifacts / "candidate.bit"),
        ("hwh", artifacts / "candidate.hwh"),
        ("bin", firmware / "candidate.bin"),
        ("recovery_hwh", artifacts / "base.hwh"),
        ("recovery_bin", firmware / "base.bin"),
    ):
        loc.write_bytes(values[name])
    raw = {
        "schema": "plasma.path2.fpga-image.v1",
        "profile_id": profile_id, "project": project,
        "source_sha": "a" * 40,
        "candidate_bit_sha256": digest(values["bit"]),
        "candidate_hwh_sha256": digest(values["hwh"]),
        "candidate_bin": "candidate.bin",
        "candidate_bin_sha256": digest(values["bin"]),
        "recovery_hwh_sha256": digest(values["recovery_hwh"]),
        "recovery_bin": "base.bin",
        "recovery_bin_sha256": digest(values["recovery_bin"]),
    }
    p = ImageProfile.from_protected_manifest(
        raw, approved_source_sha="a" * 40)
    bundle = verify_offline_bundle(
        p, artifact_dir=artifacts, firmware_dir=firmware,
        bit=artifacts / "candidate.bit",
        hwh=artifacts / "candidate.hwh",
        recovery_hwh=artifacts / "base.hwh")
    intent = {
        "lease_id": "lease-123", "target_id": "pynq-z2",
        "profile_id": p.profile_id, "source_sha": p.source_sha,
        "artifact_sha256": bundle.candidate_bin_sha256,
        "recovery_sha256": bundle.recovery_bin_sha256,
        "boot_id": "actual-boot-only-in-real-backend",
        "owner_id": "owner-z2", "restore_intent_sha256": "1" * 64,
        "services_sha256": "2" * 64, "uio_sha256": "3" * 64,
        "lease_seconds": 100,
    }
    provenance = {
        "source_sha": p.source_sha,
        "bit_sha256": bundle.candidate_bit_sha256,
        "hwh_sha256": bundle.candidate_hwh_sha256,
        "bin_sha256": bundle.candidate_bin_sha256,
        "build_qualification_sha256": "4" * 64,
        "bootgen_evidence_sha256": "5" * 64,
        "scope": "BYTE_EQUIVALENCE_ONLY",
        "physical_load": "NOT_RUN",
    }
    return bundle, intent, provenance


def test_generic_bind_is_inert_and_swd_test_rejected(tmp_path):
    bundle, intent, provenance = sample(tmp_path)
    binding = validate_held_binding(
        bundle, intent=intent, provenance=provenance, at=1000)
    assert binding.source_sha == "a" * 40
    assert binding.candidate_bin_sha256 == provenance["bin_sha256"]
    assert binding.test_route == "GENERIC_TEST_BACKEND_NOT_REGISTERED"
    assert binding.hardware_authorized is False
    with pytest.raises(LoaderDenied, match="GENERIC_SWD_TEST"):
        require_existing_f1b_identity_test(binding)
    with pytest.raises(LoaderDenied, match="ROOT_BACKEND_NOT_REGISTERED"):
        root_port_not_registered(binding)


@pytest.mark.parametrize("bucket,key,bad", [
    ("intent", "profile_id", "f1b-site1-v1"),
    ("intent", "source_sha", "b" * 40),
    ("intent", "artifact_sha256", "c" * 64),
    ("intent", "recovery_sha256", "c" * 64),
    ("intent", "owner_id", "../sudo"),
    ("intent", "lease_seconds", 901),
    ("prov", "source_sha", "b" * 40),
    ("prov", "scope", "REAL_FPGA_READY"),
    ("prov", "physical_load", "PASS"),
    ("prov", "bit_sha256", "c" * 64),
    ("prov", "hwh_sha256", "c" * 64),
    ("prov", "bin_sha256", "c" * 64),
    ("prov", "bootgen_evidence_sha256", "bad"),
])
def test_fail_closed_binding_mismatch(tmp_path, bucket, key, bad):
    bundle, intent, provenance = sample(tmp_path)
    item = intent if bucket == "intent" else provenance
    item[key] = bad
    with pytest.raises(LoaderDenied):
        validate_held_binding(
            bundle, intent=intent, provenance=provenance, at=1000)


def test_extra_fields_and_bad_clock_rejected(tmp_path):
    bundle, intent, provenance = sample(tmp_path)
    i = copy.deepcopy(intent); i["sudo"] = True
    with pytest.raises(LoaderDenied, match="FIELDS"):
        validate_held_binding(bundle, intent=i, provenance=provenance, at=1000)
    p = copy.deepcopy(provenance); p["root"] = True
    with pytest.raises(LoaderDenied, match="FIELDS"):
        validate_held_binding(bundle, intent=intent, provenance=p, at=1000)
    with pytest.raises(LoaderDenied, match="LEASE_SCHEMA"):
        validate_held_binding(bundle, intent=intent, provenance=provenance, at=0)


def test_f1b_identity_scope_separated(tmp_path):
    bundle, intent, provenance = sample(
        tmp_path, profile_id="f1b-site1-v1",
        project="pl/projects/z2-fixed-unified-site1")
    binding = validate_held_binding(
        bundle, intent=intent, provenance=provenance, at=1000)
    assert binding.test_route == "F1B_THREE_READS_ONLY"
    require_existing_f1b_identity_test(binding)
    with pytest.raises(LoaderDenied, match="ROOT_BACKEND_NOT_REGISTERED"):
        root_port_not_registered(binding)


def test_no_fake_target_access_during_admission(tmp_path, monkeypatch):
    bundle, intent, provenance = sample(tmp_path)
    import pl.hil.swd04.one_shot as hardware
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected physical device operation")
    monkeypatch.setattr(hardware, "manager_write", forbidden)
    validate_held_binding(bundle, intent=intent, provenance=provenance, at=1000)
