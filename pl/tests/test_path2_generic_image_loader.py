"""Host-only negative and ordering verification of generic Path 2 image core."""
from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

from pl.hil.path2_generic_image_loader import (
    ImageProfile, LoaderDenied, supervised_one_shot, verify_offline_bundle,
)

PIN = "a" * 40


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def valid_raw():
    return {
        "schema": "plasma.path2.fpga-image.v1",
        "profile_id": "z2-bluepill-swd-v1",
        "project": "pl/projects/z2-bluepill-rbb",
        "source_sha": PIN,
        "candidate_bit_sha256": sha(b"candidate-bit"),
        "candidate_hwh_sha256": sha(b"candidate-hwh"),
        "candidate_bin": "bluepill-swd.bin",
        "candidate_bin_sha256": sha(b"candidate-bin"),
        "recovery_hwh_sha256": sha(b"base-hwh"),
        "recovery_bin": "base.bin",
        "recovery_bin_sha256": sha(b"base-bin"),
    }


def verified(tmp_path: Path):
    raw = valid_raw()
    p = ImageProfile.from_protected_manifest(raw, approved_source_sha=PIN)
    artifact = tmp_path / "artifacts"
    firmware = tmp_path / "firmware"
    artifact.mkdir()
    firmware.mkdir()
    for dest, payload in (
        (artifact / "candidate.bit", b"candidate-bit"),
        (artifact / "candidate.hwh", b"candidate-hwh"),
        (artifact / "base.hwh", b"base-hwh"),
        (firmware / "bluepill-swd.bin", b"candidate-bin"),
        (firmware / "base.bin", b"base-bin"),
    ):
        dest.write_bytes(payload)
    kwargs = dict(artifact_dir=artifact, firmware_dir=firmware,
                  bit=artifact / "candidate.bit",
                  hwh=artifact / "candidate.hwh",
                  recovery_hwh=artifact / "base.hwh")
    return p, kwargs


@pytest.mark.parametrize("key,bad", [
    ("schema", "plasma.path2.fpga-image.v99"),
    ("source_sha", "b" * 40),
    ("project", "pl/projects/../../root"),
    ("profile_id", "../../run"),
    ("candidate_bin", "/lib/firmware/attack.bin"),
    ("candidate_bin", "../attack.bin"),
    ("recovery_bin", "candidate.bit"),
    ("candidate_bit_sha256", "bad"),
    ("recovery_bin_sha256", "bad"),
])
def test_manifest_fail_closed(key, bad):
    v = valid_raw()
    v[key] = bad
    with pytest.raises(LoaderDenied):
        ImageProfile.from_protected_manifest(v, approved_source_sha=PIN)


def test_schema_expansion_is_not_silent():
    v = valid_raw()
    v["allow_arbitrary_shell"] = True
    with pytest.raises(LoaderDenied, match="SCHEMA"):
        ImageProfile.from_protected_manifest(v, approved_source_sha=PIN)


def test_candidate_and_recovery_identity_must_be_distinct():
    v = valid_raw()
    v["candidate_bin"] = v["recovery_bin"]
    with pytest.raises(LoaderDenied, match="RECOVERY_CANNOT"):
        ImageProfile.from_protected_manifest(v, approved_source_sha=PIN)


def test_hash_and_symlink_rejected(tmp_path):
    profile, paths = verified(tmp_path)
    result = verify_offline_bundle(profile, **paths)
    assert result.candidate_bin_sha256 == valid_raw()["candidate_bin_sha256"]
    assert result.recovery_bin_sha256 == valid_raw()["recovery_bin_sha256"]
    assert result.candidate_bit_sha256 != result.recovery_bin_sha256
    (paths["artifact_dir"] / "candidate.bit").write_bytes(b"tampered")
    with pytest.raises(LoaderDenied, match="SHA256"):
        verify_offline_bundle(profile, **paths)
    (paths["artifact_dir"] / "candidate.bit").unlink()
    (paths["artifact_dir"] / "candidate.bit").symlink_to(paths["artifact_dir"] / "base.hwh")
    with pytest.raises(LoaderDenied, match="UNTRUSTED"):
        verify_offline_bundle(profile, **paths)


def test_missing_backend_never_attempts_hardware(tmp_path):
    _, paths = verified(tmp_path)
    bundle = verify_offline_bundle(
        ImageProfile.from_protected_manifest(valid_raw(), approved_source_sha=PIN),
        **paths)
    with pytest.raises(LoaderDenied, match="BACKEND_NOT_REGISTERED"):
        supervised_one_shot(bundle)


class FakeRootBackend:
    """Explicit fixture is NOT a root admission or actual hardware backend."""
    def __init__(self, fail=""):
        self.events = []
        self.fail = fail

    def step(self, name):
        self.events.append(name)
        if self.fail == name:
            raise RuntimeError(name)

    def preflight(self, bundle):
        self.step("preflight")

    def record_restore_intent(self, bundle):
        self.step("durable_intent")

    def load_candidate(self, bundle):
        self.step("load")

    def test_loaded(self, bundle):
        self.step("test")

    def restore_original(self, bundle):
        self.step("restore")

    def verify_restoration(self, bundle):
        self.step("verify_restored")


@pytest.mark.parametrize("fail,expected,overall", [
    ("", ["preflight", "durable_intent", "load", "test",
          "restore", "verify_restored"], "PASS_SEQUENCE"),
    ("load", ["preflight", "durable_intent", "load",
              "restore", "verify_restored"], "FAIL_OR_BLOCKED"),
    ("test", ["preflight", "durable_intent", "load", "test",
              "restore", "verify_restored"], "FAIL_OR_BLOCKED"),
    ("durable_intent", ["preflight", "durable_intent"], "FAIL_OR_BLOCKED"),
    ("restore", ["preflight", "durable_intent", "load", "test",
                 "restore"], "FAIL_OR_BLOCKED"),
])
def test_exact_stage_order_and_safe_failure(tmp_path, fail, expected, overall):
    profile, paths = verified(tmp_path)
    bundle = verify_offline_bundle(profile, **paths)
    backend = FakeRootBackend(fail=fail)
    result = supervised_one_shot(bundle, backend)
    assert backend.events == expected
    assert result["overall"] == overall
    if fail == "restore":
        assert result["restoration_verified"] == "FAIL_OR_UNKNOWN"
    if not fail:
        assert result["candidate_load"] == "PASS"
        assert result["restoration_verified"] == "PASS"


def test_empty_or_wrong_backend_fails_before_callbacks(tmp_path):
    profile, paths = verified(tmp_path)
    bundle = verify_offline_bundle(profile, **paths)
    with pytest.raises(LoaderDenied, match="BACKEND_NOT_REGISTERED"):
        supervised_one_shot(bundle, object())
