"""Project-agnostic Path 2 FPGA image loader *core* (no active root route).

The trusted, root-owned executor must establish B1/B2/B3 authorization,
source tree authenticity, live target ownership, bus quiescence and physical
recovery BEFORE injecting a backend. A profile JSON, this core, or a
GitHub-hosted test never authorizes /sys/class/fpga_manager writes.

This reuses the existing one-shot recovery sequencing; it deliberately
does NOT pretend to be the separately-held Download/Test/Restore backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import re
from typing import Protocol

from pl.hil.swd04 import one_shot

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
PROJECT = re.compile(r"pl/projects/[a-z0-9][a-z0-9-]{2,69}\Z")
BASENAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\Z")
REQUIRED = frozenset((
    "schema", "profile_id", "project", "source_sha",
    "candidate_bit_sha256", "candidate_hwh_sha256",
    "candidate_bin", "candidate_bin_sha256",
    "recovery_hwh_sha256", "recovery_bin", "recovery_bin_sha256",
))


class LoaderDenied(ValueError):
    """Missing or stale protected qualification; no hardware admission."""


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise LoaderDenied(reason)


@dataclass(frozen=True)
class ImageProfile:
    """Exact immutable image contract, NOT a grant of root/FPGA authority."""
    profile_id: str
    project: str
    source_sha: str
    candidate_bit_sha256: str
    candidate_hwh_sha256: str
    candidate_bin: str
    candidate_bin_sha256: str
    recovery_hwh_sha256: str
    recovery_bin: str
    recovery_bin_sha256: str

    @classmethod
    def from_protected_manifest(cls, manifest: object,
                                *, approved_source_sha: str) -> ImageProfile:
        need(type(manifest) is dict and set(manifest) == REQUIRED,
             "IMAGE_MANIFEST_SCHEMA_DENIED")
        assert isinstance(manifest, dict)
        need(manifest["schema"] == "plasma.path2.fpga-image.v1",
             "IMAGE_MANIFEST_VERSION_DENIED")
        for name in REQUIRED - {"schema"}:
            need(type(manifest[name]) is str, "IMAGE_MANIFEST_FIELD_TYPE_DENIED")
        need(type(approved_source_sha) is str and
             SHA40.fullmatch(approved_source_sha) is not None and
             manifest["source_sha"] == approved_source_sha,
             "IMAGE_SOURCE_NOT_APPROVED")
        need(re.fullmatch(r"[a-z][a-z0-9-]{2,63}", manifest["profile_id"]) is not None,
             "IMAGE_PROFILE_ID_DENIED")
        need(PROJECT.fullmatch(manifest["project"]) is not None,
             "IMAGE_PROJECT_DENIED")
        for key in (
            "candidate_bit_sha256", "candidate_hwh_sha256",
            "candidate_bin_sha256", "recovery_hwh_sha256",
            "recovery_bin_sha256",
        ):
            need(SHA256.fullmatch(manifest[key]) is not None,
                 "IMAGE_DIGEST_DENIED")
        for key in ("candidate_bin", "recovery_bin"):
            filename = manifest[key]
            need(BASENAME.fullmatch(filename) is not None and
                 filename not in (".", "..") and filename.endswith(".bin"),
                 "IMAGE_FIRMWARE_BASENAME_DENIED")
        need(manifest["candidate_bin"] != manifest["recovery_bin"] and
             manifest["candidate_bin_sha256"] != manifest["recovery_bin_sha256"],
             "IMAGE_RECOVERY_CANNOT_EQUAL_CANDIDATE")
        return cls(**{name: manifest[name] for name in REQUIRED if name != "schema"})


def sha256_regular_file(path: Path, *, exact_parent: Path,
                        expected: str) -> str:
    """Offline integrity only; a trusted target must also verify root ownership."""
    need(path.is_absolute() and not path.is_symlink() and
         path.parent == exact_parent and exact_parent.is_dir() and
         not exact_parent.is_symlink(), "IMAGE_PATH_UNTRUSTED")
    need(path.is_file(), "IMAGE_FILE_MISSING")
    length = path.stat().st_size
    need(0 < length <= 16_000_000, "IMAGE_FILE_SIZE_DENIED")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    need(digest.hexdigest() == expected, "IMAGE_SHA256_MISMATCH")
    return digest.hexdigest()


@dataclass(frozen=True)
class VerifiedBundle:
    """Offline hashes only, not a Z2 firmware-manager or root receipt."""
    profile: ImageProfile
    candidate_bit_sha256: str
    candidate_hwh_sha256: str
    candidate_bin_sha256: str
    recovery_hwh_sha256: str
    recovery_bin_sha256: str


def verify_offline_bundle(profile: ImageProfile, *, artifact_dir: Path,
                          firmware_dir: Path, bit: Path, hwh: Path,
                          recovery_hwh: Path) -> VerifiedBundle:
    """Verify byte-for-byte image and recovery identity; no device effects."""
    need(type(profile) is ImageProfile, "IMAGE_PROFILE_NOT_VERIFIED")
    need(artifact_dir.is_absolute() and firmware_dir.is_absolute() and
         artifact_dir != firmware_dir, "IMAGE_STORAGE_ROOT_DENIED")
    for path in (bit, hwh, recovery_hwh):
        need(path.name not in (".", ".."), "IMAGE_PATH_UNTRUSTED")
    return VerifiedBundle(
        profile=profile,
        candidate_bit_sha256=sha256_regular_file(
            bit, exact_parent=artifact_dir, expected=profile.candidate_bit_sha256),
        candidate_hwh_sha256=sha256_regular_file(
            hwh, exact_parent=artifact_dir, expected=profile.candidate_hwh_sha256),
        candidate_bin_sha256=sha256_regular_file(
            firmware_dir / profile.candidate_bin, exact_parent=firmware_dir,
            expected=profile.candidate_bin_sha256),
        recovery_hwh_sha256=sha256_regular_file(
            recovery_hwh, exact_parent=artifact_dir, expected=profile.recovery_hwh_sha256),
        recovery_bin_sha256=sha256_regular_file(
            firmware_dir / profile.recovery_bin, exact_parent=firmware_dir,
            expected=profile.recovery_bin_sha256),
    )


class TrustedRootBackend(Protocol):
    """Provided ONLY by the separately reviewed installed root executor.

    It must enforce the shared FPGA lock, current-boot/owner/clock checks,
    durable fsynced recovery intent before FPGA Manager writes, bounded
    child tests, and fail-closed restoration under the same live authority.
    """
    def preflight(self, bundle: VerifiedBundle) -> None: ...
    def record_restore_intent(self, bundle: VerifiedBundle) -> None: ...
    def load_candidate(self, bundle: VerifiedBundle) -> None: ...
    def test_loaded(self, bundle: VerifiedBundle) -> None: ...
    def restore_original(self, bundle: VerifiedBundle) -> None: ...
    def verify_restoration(self, bundle: VerifiedBundle) -> None: ...


def supervised_one_shot(bundle: VerifiedBundle,
                        backend: TrustedRootBackend | None = None) -> dict[str, str]:
    """Reuse existing trusted-order one-shot algorithm with injected backend.

    Defaults closed. This does not register an SSH/Root/Dispatcher stage.
    If a privileged backend is installed, its preflight and restore callbacks
    are responsible for physical quiescence and independent restore safety.
    """
    need(type(bundle) is VerifiedBundle, "IMAGE_BUNDLE_REQUIRED")
    required = (
        "preflight", "record_restore_intent", "load_candidate",
        "test_loaded", "restore_original", "verify_restoration",
    )
    need(backend is not None and
         all(callable(getattr(backend, name, None)) for name in required),
         "TRUSTED_Z2_ROOT_BACKEND_NOT_REGISTERED")

    def preflight() -> None:
        assert backend is not None
        backend.preflight(bundle)
        # Set durable RESTORE_REQUIRED before ANY candidate FPGA write.
        backend.record_restore_intent(bundle)

    def test_callback(state: dict[str, str]) -> None:
        assert backend is not None
        backend.test_loaded(bundle)
        state["test"] = "PASS"

    assert backend is not None
    result = one_shot.run_sequence(
        preflight=preflight,
        load_candidate=lambda: backend.load_candidate(bundle),
        test_callback=test_callback,
        test_stages=("test",),
        restore=lambda: backend.restore_original(bundle),
        verify_restoration=lambda: backend.verify_restoration(bundle),
    )
    # Reconfiguration may have occurred. An unverified restore is not merely
    # a routine NO_GO; require trusted manual state inspection, never retry.
    if (result["preflight"] == "PASS" and
            result["restoration_verified"] != "PASS"):
        result["overall"] = "UNKNOWN_MANUAL_RECOVERY_REQUIRED"
    return result
