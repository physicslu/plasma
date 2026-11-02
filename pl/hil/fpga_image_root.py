"""FPGA Image + companion Manifest: hash-matched download, identity, restore.

No protocol/IP-specific handler, runtime Project/Profile selector or Flash write.
download/test/restore keep the two-argument protected Root Entry; B3
``bundle-load <pin> <asset_set_sha256>`` adds only the installed Set SHA-256.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile
import uuid

from pl.hil import fpga_image_guard as guard
from pl.hil import fpga_image_admission as admission

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_FILE = guard.FIRMWARE / "plasma-image-manifest.json"
STATE = ROOT / ".plasma-fpga-image-deployment-state.json"
CHILD = guard.OWNER_DIR / "fpga-image-identity.json"
SCHEMA = "plasma.fpga.image-deployment.v3"
LEGACY_SCHEMA = "plasma.fpga.image-deployment.v1"
STATUS = ("RECOVERY", "IMAGE", "DOWNLOAD_IN_FLIGHT", "TEST_IN_FLIGHT",
          "RESTORE_IN_FLIGHT", "UNKNOWN")


class ImageDeploymentDenied(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ImageDeploymentDenied(code)


@dataclass(frozen=True)
class ImageManifest:
    image_id: str
    board_id: str
    fpga_part: str
    soc_compatible: str
    firmware_name: str
    firmware_sha256: str
    recovery_name: str
    recovery_sha256: str
    abi_version: int
    identity_words: tuple[tuple[int, int, int], ...]
    abi_offset: int
    site_bitmap: int
    site_bitmap_offset: int | None
    axi_base: int
    axi_bytes: int
    owner_base: int
    owner_bytes: int
    uio_name: str
    expected_uio: dict


def _pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, "IMAGE_RELEASE_DUPLICATE_FIELD")
        result[key] = value
    return result


def _basename(name: object) -> bool:
    return type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name) is not None


def manifest_sha256() -> str:
    """Fingerprint the runtime Manifest independently from executable code."""
    guard.protected(MANIFEST_FILE)
    need(MANIFEST_FILE.is_file() and 0 < MANIFEST_FILE.stat().st_size <= 8192,
         "IMAGE_MANIFEST_FILE_DENIED")
    return hashlib.sha256(MANIFEST_FILE.read_bytes()).hexdigest()


def read_image_manifest() -> ImageManifest:
    """Parse the root-owned paired Manifest used by the live Root Loader."""
    guard.protected(MANIFEST_FILE)
    need(MANIFEST_FILE.is_file() and 0 < MANIFEST_FILE.stat().st_size <= 8192,
         "IMAGE_MANIFEST_FILE_DENIED")
    return parse_image_manifest_bytes(MANIFEST_FILE.read_bytes())


def parse_image_manifest_bytes(raw: bytes) -> ImageManifest:
    """One shared, full Root schema/ABI parser; no filesystem/hardware effects.

    The canonical Root Loader still independently enforces ownership of
    MANIFEST_FILE, the live FPGA Manager, Runtime and Golden Recovery.
    This pure parser is reusable by the future Bundle Asset Handoff.
    """
    need(type(raw) is bytes and 0 < len(raw) <= 8192,
         "IMAGE_MANIFEST_FILE_DENIED")
    try:
        data = json.loads(raw.decode("utf-8"),
                          object_pairs_hook=_pairs,
                          parse_constant=lambda _: need(False, "IMAGE_MANIFEST_NONFINITE"))
    except (UnicodeError, json.JSONDecodeError) as e:
        raise ImageDeploymentDenied("IMAGE_MANIFEST_JSON_DENIED") from e
    fields = {"schema", "image_id", "board_id", "fpga_part",
              "soc_compatible", "firmware_name", "firmware_sha256",
              "recovery_name", "recovery_sha256", "abi_version",
              "abi_offset", "identity_words", "site_bitmap",
              "site_bitmap_offset", "axi_base", "axi_bytes", "owner_base",
              "owner_bytes", "uio_name", "expected_uio"}
    need(type(data) is dict and set(data) == fields and
         data["schema"] == "plasma.fpga.image.v1",
         "IMAGE_MANIFEST_SCHEMA_DENIED")
    # This is the Z2 prototype Root. Manifest claims cannot change its board.
    need(data["board_id"] == "pynq-z2" and
         data["fpga_part"] == "xc7z020clg400-1",
         "IMAGE_BOARD_PART_MISMATCH")
    for key in ("image_id", "board_id", "fpga_part", "soc_compatible", "uio_name"):
        need(type(data[key]) is str and 0 < len(data[key]) <= 128,
             "IMAGE_RELEASE_VALUE_DENIED")
    need(_basename(data["firmware_name"]) and _basename(data["recovery_name"]) and
         data["firmware_name"] != data["recovery_name"] and
         all(type(data[k]) is str and
             re.fullmatch(r"[a-f0-9]{64}", data[k]) is not None
             for k in ("firmware_sha256", "recovery_sha256")),
         "IMAGE_RELEASE_FIRMWARE_DENIED")
    for key in ("abi_version", "abi_offset", "site_bitmap",
                "axi_base", "axi_bytes", "owner_base", "owner_bytes"):
        need(type(data[key]) is int and 0 <= data[key] <= 0xFFFFFFFF,
             "IMAGE_RELEASE_INTEGER_DENIED")
    need(data["site_bitmap_offset"] is None or
         (type(data["site_bitmap_offset"]) is int and
          0 <= data["site_bitmap_offset"] <= 0xFFFFFFFF),
         "IMAGE_RELEASE_SITE_OFFSET_DENIED")
    need(data["axi_bytes"] >= 16 and data["axi_bytes"] <= 0x100000 and
         data["owner_bytes"] >= data["axi_bytes"] and
         data["owner_bytes"] <= 0x100000 and
         data["axi_base"] % 4096 == 0 and data["owner_base"] % 4096 == 0 and
         data["owner_base"] <= data["axi_base"] and
         data["axi_base"] + data["axi_bytes"] <=
         data["owner_base"] + data["owner_bytes"] <= 0x100000000 and
         data["site_bitmap"] > 0, "IMAGE_RELEASE_APERTURE_DENIED")
    words = data["identity_words"]
    need(type(words) is list and 2 <= len(words) <= 16 and
         all(type(w) is list and len(w) == 3 and
             all(type(n) is int and 0 <= n <= 0xFFFFFFFF for n in w) and
             w[0] % 4 == 0 and w[0] + 4 <= data["axi_bytes"] and w[2] > 0
             for w in words), "IMAGE_RELEASE_IDENTITY_DENIED")
    offsets = [w[0] for w in words]
    need(len(offsets) == len(set(offsets)) and
         data["abi_offset"] in offsets and
         next(w for w in words if w[0] == data["abi_offset"])[1] ==
         data["abi_version"], "IMAGE_RELEASE_ABI_DENIED")
    # Some legitimate FPGA IPs expose only ABI/Identity, not a Site-bitmap
    # register. Never mislabel a dynamic SAMPLE bit as hardware Site proof.
    if data["site_bitmap_offset"] is not None:
        need(data["site_bitmap_offset"] in offsets and
             any(w[0] == data["site_bitmap_offset"] and
                 w[1] == data["site_bitmap"] and w[2] == 0xFFFFFFFF
                 for w in words), "IMAGE_RELEASE_SITE_IDENTITY_DENIED")
    uio = data["expected_uio"]
    need(type(uio) is dict and set(uio) ==
         {"uio", "driver", "maps", "runtime", "irq_counts"} and
         uio["uio"] == data["uio_name"] and
         type(uio["driver"]) is str and
         type(uio["runtime"]) is str and
         uio["maps"] == [[data["owner_base"], data["owner_bytes"]]] and
         type(uio["irq_counts"]) is list and
         len(uio["irq_counts"]) == 2 and
         all(type(n) is int and 0 <= n <= 0xFFFFFFFF
             for n in uio["irq_counts"]), "IMAGE_RELEASE_UIO_DENIED")
    return ImageManifest(
        image_id=data["image_id"], board_id=data["board_id"],
        fpga_part=data["fpga_part"], soc_compatible=data["soc_compatible"],
        firmware_name=data["firmware_name"],
        firmware_sha256=data["firmware_sha256"],
        recovery_name=data["recovery_name"],
        recovery_sha256=data["recovery_sha256"],
        abi_version=data["abi_version"],
        identity_words=tuple(tuple(w) for w in words),
        abi_offset=data["abi_offset"], site_bitmap=data["site_bitmap"],
        site_bitmap_offset=data["site_bitmap_offset"],
        axi_base=data["axi_base"], axi_bytes=data["axi_bytes"],
        owner_base=data["owner_base"], owner_bytes=data["owner_bytes"],
        uio_name=data["uio_name"], expected_uio=uio)


def validate_bundle_fpga_handoff(
    handoff: dict, *,
    expected_active_set_sha256: str,
    manifest_bytes: bytes,
    bin_bytes: bytes,
    hwh_bytes: bytes,
) -> dict:
    """Host-only Root compatibility verification of a PPU-selected Asset.

    Reuses the exact production Root Image Manifest parser (including
    Identity, AXI/ABI and UIO geometry), but grants *no* privilege and does
    not modify /lib/firmware, invoke FPGA Manager or access DUT.

    This check is an additional input/format gate, NOT proof of an
    authorized Controller request, signed publisher, live hardware,
    Root source pin or Golden Recovery. Later privileged installation
    must revalidate from the immutable Active Set under exclusive locks.
    """
    need(type(expected_active_set_sha256) is str and
         re.fullmatch(r"[0-9a-f]{64}", expected_active_set_sha256) is not None,
         "ROOT_HANDOFF_ACTIVE_IDENTITY_INVALID")
    need(type(handoff) is dict and
         handoff.get("schema") == "plasma.ppu.fpga-asset-handoff.v1" and
         handoff.get("status") == "VERIFIED_NOT_LOADED" and
         handoff.get("asset_set_sha256") == expected_active_set_sha256 and
         handoff.get("ready") is False and
         handoff.get("fpga_install") == "NOT_RUN" and
         handoff.get("fpga_load") == "NOT_RUN" and
         handoff.get("root_hardware_validation") == "NOT_RUN",
         "ROOT_HANDOFF_NOT_BOUND_TO_ACTIVE_SET")
    selected = handoff.get("fpga_image")
    # A Programming Profile is optional: an FPGA-only Bundle is valid.
    profile = handoff.get("programming_profile")
    need(type(selected) is dict and (profile is None or type(profile) is dict),
         "ROOT_HANDOFF_SELECTION_MISSING")
    image_id = selected.get("image_id")
    package_id = selected.get("package_id")
    package_version = selected.get("package_version")
    names = [image_id, package_id, package_version]
    if profile is not None:
        names += [profile.get("package_id"), profile.get("package_version")]
    need(all(type(item) is str and
             re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", item) is not None
             for item in names),
         "ROOT_HANDOFF_SELECTION_INVALID")
    need(profile is None or
         (type(profile.get("package_identity_sha256")) is str and
          re.fullmatch(r"[0-9a-f]{64}",
                       profile["package_identity_sha256"]) is not None),
         "ROOT_HANDOFF_PROFILE_IDENTITY_INVALID")
    need(type(bin_bytes) is bytes and 0 < len(bin_bytes) <= 16_000_000 and
         type(hwh_bytes) is bytes and 0 < len(hwh_bytes) <= 4_000_000,
         "ROOT_HANDOFF_IMAGE_SIZE_INVALID")
    manifest = parse_image_manifest_bytes(manifest_bytes)
    prefix = "payload/packages/" + package_id + "/fpga/"
    names = {
        "bin": selected.get("bin_relative_path"),
        "hwh": selected.get("hwh_relative_path"),
        "manifest": selected.get("manifest_relative_path"),
    }
    need(all(type(name) is str and
             name.startswith(prefix) and
             re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name[len(prefix):]) is not None
             for name in names.values()),
         "ROOT_HANDOFF_RELATIVE_PATH_INVALID")
    need(names["bin"] == prefix + manifest.firmware_name and
         names["bin"].endswith(".bin") and
         names["hwh"].endswith(".hwh") and
         names["manifest"].endswith(".json") and
         len(set(names.values())) == 3,
         "ROOT_HANDOFF_FILE_ROLE_INVALID")
    checks = (
        ("bin_sha256", bin_bytes, manifest.firmware_sha256),
        ("hwh_sha256", hwh_bytes, None),
        ("manifest_sha256", manifest_bytes, None),
    )
    for field, data, paired in checks:
        expected = selected.get(field)
        need(type(expected) is str and
             re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
             "ROOT_HANDOFF_HASH_INVALID")
        actual = hashlib.sha256(data).hexdigest()
        need(actual == expected and (paired is None or actual == paired),
             "ROOT_HANDOFF_HASH_MISMATCH")
    need(manifest.image_id == image_id and
         selected.get("board_id") == manifest.board_id and
         selected.get("fpga_part") == manifest.fpga_part and
         selected.get("abi_version_claim") == manifest.abi_version and
         manifest.recovery_name == "base.bin",
         "ROOT_HANDOFF_IMAGE_IDENTITY_MISMATCH")
    # Golden is not part of the incoming Bundle; Root must independently
    # prove its SHA and current-boot manager/ownership state before load.
    return {
        "schema": "plasma.ppu.fpga-root-handoff-preflight.v1",
        "result": "ROOT_FORMAT_VERIFIED_NOT_INSTALLED",
        "asset_set_sha256": expected_active_set_sha256,
        "fpga_image_id": manifest.image_id,
        "fpga_bin_name": manifest.firmware_name,
        "fpga_bin_sha256": manifest.firmware_sha256,
        "fpga_hwh_sha256": selected["hwh_sha256"],
        "fpga_manifest_sha256": selected["manifest_sha256"],
        "programming_profile_identity_sha256":
            None if profile is None else profile["package_identity_sha256"],
        "board_id": manifest.board_id,
        "fpga_part": manifest.fpga_part,
        "abi_version": manifest.abi_version,
        "golden_recovery": "NOT_VERIFIED",
        "root_source_pin": "NOT_VERIFIED",
        "hardware_ownership": "NOT_VERIFIED",
        "fpga_installed": False,
        "fpga_loaded": False,
        "dut": "NOT_RUN",
        "ready": False,
    }


def stage_bundle_fpga_files_only(
    handoff: dict, *,
    expected_active_set_sha256: str,
    manifest_bytes: bytes,
    bin_bytes: bytes,
    hwh_bytes: bytes,
) -> dict:
    """Privileged *files-only* staging via the EXISTING protected Root owner.

    This is an internal primitive, deliberately NOT an allowed Root Entry
    command. Its caller must later provide independent Controller and
    Runtime authorization for any configuration or manifest activation.
    Staged companions never replace the active Root Image Manifest.
    """
    preflight = validate_bundle_fpga_handoff(
        handoff, expected_active_set_sha256=expected_active_set_sha256,
        manifest_bytes=manifest_bytes, bin_bytes=bin_bytes, hwh_bytes=hwh_bytes,
    )
    trusted_local()
    release = parse_image_manifest_bytes(manifest_bytes)
    port = guard.RootZ2TargetPort(release=release)
    with port.exclusive():
        _stage_files_locked(release, manifest_bytes=manifest_bytes,
                            bin_bytes=bin_bytes, hwh_bytes=hwh_bytes)
    return _staged_receipt(preflight, release)


def _stage_files_locked(release: ImageManifest, *, manifest_bytes: bytes,
                        bin_bytes: bytes, hwh_bytes: bytes) -> None:
    """Files-only staging; the caller holds the exclusive FPGA owner lock."""
    guard.protected(guard.FIRMWARE, file=False)
    # The name comes only from the Root-validated basename, not from a
    # Console-provided path. Each individual file is installed no-overwrite.
    files = (
        (release.firmware_name, bin_bytes),
        (release.firmware_name + ".hwh", hwh_bytes),
        (release.firmware_name + ".manifest.json", manifest_bytes),
    )
    # Golden is separate from any Asset Set and cannot be replaced by it.
    guard.sha_file(
        guard.FIRMWARE / release.recovery_name,
        release.recovery_sha256,
    )
    # Recheck the intended bytes and ensure no filename can escape Root
    # firmware storage even if an API consumer supplies malformed input.
    for name, raw in files:
        need(_basename(name) and name != release.recovery_name and
             name != MANIFEST_FILE.name and
             (guard.FIRMWARE / name).parent == guard.FIRMWARE,
             "ROOT_HANDOFF_FIRMWARE_FILENAME_DENIED")
        target = guard.FIRMWARE / name
        expected_sha = hashlib.sha256(raw).hexdigest()
        if target.is_symlink():
            raise ImageDeploymentDenied("ROOT_HANDOFF_EXISTING_SYMLINK")
        if target.exists():
            guard.protected(target)
            need(target.is_file() and target.stat().st_size == len(raw),
                 "ROOT_HANDOFF_EXISTING_FILE_CONFLICT")
            with target.open("rb") as source:
                observed_sha = hashlib.sha256(source.read()).hexdigest()
            need(observed_sha == expected_sha,
                 "ROOT_HANDOFF_EXISTING_FILE_CONFLICT")
            continue
        fd, temp_name = tempfile.mkstemp(
            prefix=".plasma-fpga-asset.", dir=guard.FIRMWARE
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as destination:
                destination.write(raw)
                destination.flush()
                os.fsync(destination.fileno())
            temp.chmod(0o600)
            # link() fails if target exists; do not use os.replace()
            # because it would silently overwrite a potentially
            # held firmware file under the same logical name.
            os.link(temp, target, follow_symlinks=False)
        except FileExistsError as exc:
            raise ImageDeploymentDenied(
                "ROOT_HANDOFF_FIRMWARE_NAME_COLLISION"
            ) from exc
        finally:
            if temp.exists():
                temp.unlink()
    folder = os.open(
        guard.FIRMWARE, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(folder)
    finally:
        os.close(folder)
    # Rehash all installed files; the canonical Root Image Manifest
    # remains untouched until an independently approved configuration.
    for name, data in files:
        target = guard.FIRMWARE / name
        guard.protected(target)
        with target.open("rb") as source:
            digest = hashlib.sha256(source.read()).hexdigest()
        need(digest == hashlib.sha256(data).hexdigest(),
             "ROOT_HANDOFF_STAGED_FILE_CHANGED")


def _staged_receipt(preflight: dict, release: ImageManifest) -> dict:
    return {
        **preflight,
        "result": "ROOT_FILES_STAGED_NOT_ACTIVATED",
        "firmware_files_staged": True,
        "fpga_installed": False,
        "fpga_loaded": False,
        "golden_recovery": "SHA_VERIFIED",
        "root_hardware_activation": "NOT_RUN",
        "ready": False,
        "firmware_name": release.firmware_name,
        "manifest_companion_name": release.firmware_name + ".manifest.json",
        "hwh_companion_name": release.firmware_name + ".hwh",
    }


def read_identity(read32, release: ImageManifest) -> dict[int, int]:
    observed = {}
    for offset, expected, mask in release.identity_words:
        value = read32(release.axi_base + offset)
        need(type(value) is int and 0 <= value <= 0xFFFFFFFF and
             value & mask == expected & mask, "PL_IDENTITY_MISMATCH")
        observed[offset] = value
    need(observed[release.abi_offset] == release.abi_version,
         "PL_ABI_MISMATCH")
    if release.site_bitmap_offset is not None:
        need(observed[release.site_bitmap_offset] == release.site_bitmap,
             "PL_SITE_BITMAP_MISMATCH")
    return observed


def native_runtime_preflight(*, version=None, machine=None,
                             endian=None, executable=None) -> None:
    version = tuple(sys.version_info[:3]) if version is None else tuple(version)
    machine = platform.machine() if machine is None else machine
    endian = sys.byteorder if endian is None else endian
    executable = sys.executable if executable is None else executable
    need(version == (3, 12, 13) and machine == "armv7l" and endian == "little"
         and Path(executable).resolve().is_relative_to("/opt/plasma/python/3.12.13"),
         "NATIVE_ARMV7_PYTHON_RUNTIME_REQUIRED")


def trusted_local() -> None:
    need(os.geteuid() == 0, "ROOT_REQUIRED")
    native_runtime_preflight()
    for path in (ROOT, Path(__file__).resolve(),
                 ROOT / "pl/hil/fpga_image_guard.py",
                 ROOT / "pl/hil/fpga_image_admission.py",
                 ROOT / "software/python/plasma_interfaces/linux_mmio.py"):
        guard.protected(path, file=path != ROOT)
    guard.OWNER_DIR.mkdir(mode=0o700, exist_ok=True)
    guard.protected(guard.OWNER_DIR, file=False)


def _state_file_trusted() -> None:
    guard.protected(STATE)
    need(STATE.stat().st_mode & 0o077 == 0 and STATE.stat().st_size <= 4096,
         "STATE_FILE_NOT_PRIVATE")


def read_state(release: ImageManifest) -> dict | None:
    if not STATE.exists():
        need(not STATE.is_symlink(), "STATE_SYMLINK_DENIED")
        return None
    _state_file_trusted()
    data = json.loads(STATE.read_text())
    fields = {"schema", "session_id", "boot_id", "status", "image", "image_id",
              "download_count", "test_count", "restore_count",
              "evidence_sha256", "last_error"}
    new_fields = fields | {"manifest_sha256", "firmware_sha256"}
    need(type(data) is dict and
         (set(data) == new_fields and data.get("schema") == SCHEMA or
          set(data) == fields and data.get("schema") == LEGACY_SCHEMA),
         "STATE_SCHEMA_INVALID")
    need(data["status"] in STATUS and
         type(data["session_id"]) is str and len(data["session_id"]) >= 8 and
         type(data["boot_id"]) is str and len(data["boot_id"]) >= 8 and
         type(data["image_id"]) is str and bool(data["image_id"]) and
         _basename(data["image"]) and
         all(type(data[k]) is int and data[k] >= 0 for k in
             ("download_count", "test_count", "restore_count")),
         "STATE_IMAGE_OR_IDENTITY_INVALID")
    if data["schema"] == SCHEMA:
        need(all(type(data[k]) is str and
                 re.fullmatch(r"[a-f0-9]{64}", data[k]) is not None
                 for k in ("manifest_sha256", "firmware_sha256")),
             "STATE_MANIFEST_HASH_INVALID")
    else:
        # v1 state may be retired only from a known-Golden checkpoint.
        need(data["status"] == "RECOVERY", "LEGACY_ACTIVE_IMAGE_DENIED")
    if data["status"] == "RECOVERY":
        need(data["image"] == release.recovery_name, "STATE_RECOVERY_MISMATCH")
    return data

def write_state(data: dict) -> None:
    raw = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
    need(len(raw) <= 4096, "STATE_TOO_LARGE")
    if STATE.exists():
        _state_file_trusted()
    temp = STATE.with_name(STATE.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            n = os.write(fd, raw[offset:])
            need(n > 0, "STATE_WRITE_INCOMPLETE")
            offset += n
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp, STATE)
    directory = os.open(STATE.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _digest(data: object) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def live_report(port: guard.RootZ2TargetPort, release: ImageManifest,
                image: str, *, previous_image: str | None = None,
                require_mmio: bool = True) -> dict:
    need(image in (release.recovery_name, release.firmware_name) or
         (previous_image is not None and image == previous_image),
         "IMAGE_NOT_IN_MANIFEST")
    report = admission.collect_live(root_port=port, release=release,
                                    expected_firmware=image,
                                    previous_firmware=previous_image,
                                    require_mmio=require_mmio)
    need(report["expected_manager_firmware"] == image and
         port.image_sha256("candidate") == release.firmware_sha256 and
         port.image_sha256("recovery") == release.recovery_sha256,
         "CURRENT_IMAGE_OR_RECOVERY_CHANGED")
    return report


def live_program_session_report(port: guard.RootZ2TargetPort,
                                release: ImageManifest) -> dict:
    """Read-only Bridge admission; no whole-system process census.

    Explicitly NOT callable by FPGA Manager download/test/restore. The
    Bridge has already checked its owner lock, current image checkpoint,
    protected source pin and targeted MMIO-owner preflight.
    """
    report = admission.collect_live(
        root_port=port, release=release,
        expected_firmware=release.firmware_name,
        runtime_program_session=True)
    need(report["expected_manager_firmware"] == release.firmware_name and
         port.image_sha256("candidate") == release.firmware_sha256 and
         port.image_sha256("recovery") == release.recovery_sha256,
         "CURRENT_IMAGE_OR_RECOVERY_CHANGED")
    return report


def _initial_state(report: dict, release: ImageManifest) -> dict:
    return {"schema": SCHEMA, "session_id": "fpga-" + uuid.uuid4().hex,
            "boot_id": report["target_boot_id"], "status": "RECOVERY",
            "image": release.recovery_name, "image_id": release.image_id,
            "manifest_sha256": manifest_sha256(),
            "firmware_sha256": release.firmware_sha256,
            "download_count": 0, "test_count": 0, "restore_count": 0,
            "evidence_sha256": _digest(report), "last_error": ""}


def _confirm_current(port, release: ImageManifest, record: dict | None,
                     operation: str) -> tuple[dict, dict]:
    current_manifest = manifest_sha256()
    different = (record is not None and
                 (record.get("manifest_sha256") != current_manifest or
                  record["image_id"] != release.image_id or
                  record.get("firmware_sha256") != release.firmware_sha256))
    if record is not None:
        need(record["status"] in ("RECOVERY", "IMAGE"),
             "UNCERTAIN_PRIOR_OPERATION_MANUAL_RECOVERY")
        if different:
            need(operation == "download", "NEW_MANIFEST_DOWNLOAD_REQUIRED")
        if operation == "test":
            need(record["status"] == "IMAGE" and
                 record["image"] == release.firmware_name,
                 "IMAGE_NOT_LOADED")
        expected = record["image"]
    else:
        need(operation == "download", "DOWNLOAD_REQUIRED_BEFORE_TEST_OR_RESTORE")
        expected = release.recovery_name
    if different and record["status"] == "IMAGE":
        # Direct Image A -> B transition, with no intermediate Golden reload.
        # Before overwriting PL, verify that A is still the current image,
        # its root-owned BIN matches the recorded digest, and owner/boot
        # evidence remains valid. Never accept UNKNOWN or stale in-flight state.
        need(record["schema"] == SCHEMA and
             record["boot_id"] ==
             (guard.PROC / "sys/kernel/random/boot_id").read_text().strip(),
             "PREVIOUS_IMAGE_BOOT_CHANGED")
        need(record["image"] not in (release.recovery_name, release.firmware_name),
             "PREVIOUS_IMAGE_AMBIGUOUS")
        # Previous firmware bytes need not remain on disk after Image A was
        # loaded. The protected journal + current-boot Manager record anchor
        # the held Image; only the incoming B BIN and Golden are rehashed.
        report = live_report(port, release, expected,
                             previous_image=expected,
                             require_mmio=operation == "test")
    else:
        report = live_report(port, release, expected,
                             require_mmio=operation == "test")
    if record is None or different:
        fresh = _initial_state(report, release)
        if record is not None and record["status"] == "IMAGE":
            # Represent the old held Image until the new Download begins;
            # any interrupted transition is persisted as in-flight/UNKNOWN.
            fresh["status"] = "IMAGE"
            fresh["image"] = expected
        record = fresh
    else:
        need(record["boot_id"] == report["target_boot_id"],
             "BOOT_CHANGED_MANUAL_REVIEW")
    need(record["manifest_sha256"] == current_manifest,
         "MANIFEST_CHANGED_IN_FLIGHT")
    return record, report

def run(operation: str) -> dict:
    need(operation in ("download", "test", "restore"), "OPERATION_NOT_ALLOWLISTED")
    trusted_local()
    release = read_image_manifest()
    port = guard.RootZ2TargetPort(release=release)
    with port.exclusive():
        return _run_locked(operation, port, release)


def _run_locked(operation: str, port: guard.RootZ2TargetPort,
                release: ImageManifest) -> dict:
    """download/test/restore; the caller holds the exclusive owner lock."""
    record, current = _confirm_current(port, release,
                                       read_state(release), operation)
    if operation == "download":
        record.update(status="DOWNLOAD_IN_FLIGHT", last_error="")
        write_state(record)
        try:
            need(manifest_sha256() == record["manifest_sha256"],
                 "MANIFEST_CHANGED_IN_FLIGHT")
            guard.manager_write(release.firmware_name)
            after = live_report(port, release, release.firmware_name,
                                require_mmio=False)
            record.update(status="IMAGE", image=release.firmware_name,
                          download_count=record["download_count"] + 1,
                          evidence_sha256=_digest(after))
            write_state(record)
        except BaseException as exc:
            record.update(status="UNKNOWN", last_error=type(exc).__name__)
            write_state(record)
            raise
        return {"stage": operation, "result": "LOADED_AND_HELD",
                "download_count": record["download_count"],
                "lease_id": record["session_id"], "boot_id": record["boot_id"],
                "auto_test": False}
    if operation == "test":
        if CHILD.exists():
            guard.protected(CHILD)
            CHILD.unlink()
        record.update(status="TEST_IN_FLIGHT", last_error="")
        write_state(record)
        try:
            need(manifest_sha256() == record["manifest_sha256"],
                 "MANIFEST_CHANGED_IN_FLIGHT")
            guard.run_child([sys.executable, "-m",
                                "pl.hil.fpga_image_root", "--identity-child"])
            result = json.loads(CHILD.read_text())
            need(type(result) is dict and
                 set(result) == {"observed"} and
                 type(result["observed"]) is dict and
                 set(result["observed"]) ==
                 {str(offset) for offset, _, _ in release.identity_words},
                 "IDENTITY_CHILD_RECEIPT_DENIED")
            for offset, expected, mask in release.identity_words:
                value = result["observed"][str(offset)]
                need(type(value) is int and 0 <= value <= 0xFFFFFFFF and
                     value & mask == expected & mask,
                     "IDENTITY_CHILD_VALUE_MISMATCH")
            need(result["observed"][str(release.abi_offset)] ==
                 release.abi_version, "IDENTITY_CHILD_ABI_MISMATCH")
            if release.site_bitmap_offset is not None:
                need(result["observed"][str(release.site_bitmap_offset)] ==
                     release.site_bitmap, "IDENTITY_CHILD_SITE_MISMATCH")
            need(manifest_sha256() == record["manifest_sha256"],
                 "MANIFEST_CHANGED_IN_FLIGHT")
            after = live_report(port, release, release.firmware_name,
                                require_mmio=True)
            record.update(status="IMAGE", test_count=record["test_count"] + 1,
                          evidence_sha256=_digest({"target": after,
                                                   "identity": result}))
            write_state(record)
        except BaseException as exc:
            record.update(status="UNKNOWN", last_error=type(exc).__name__)
            write_state(record)
            raise
        return {"stage": operation, "result": "IDENTITY_PASS",
                "test_count": record["test_count"],
                "read32_count": len(release.identity_words),
                "write32_count": 0, "lease_id": record["session_id"],
                "boot_id": record["boot_id"], "auto_restore": False}
    if record["status"] == "RECOVERY":
        return {"stage": operation, "result": "ALREADY_RESTORED",
                "restore_count": record["restore_count"],
                "lease_id": record["session_id"], "boot_id": record["boot_id"]}
    record.update(status="RESTORE_IN_FLIGHT", last_error="")
    write_state(record)
    try:
        need(manifest_sha256() == record["manifest_sha256"],
             "MANIFEST_CHANGED_IN_FLIGHT")
        guard.manager_write(release.recovery_name)
        after = live_report(port, release, release.recovery_name,
                            require_mmio=False)
        record.update(status="RECOVERY", image=release.recovery_name,
                      restore_count=record["restore_count"] + 1,
                      evidence_sha256=_digest(after))
        write_state(record)
    except BaseException as exc:
        record.update(status="UNKNOWN", last_error=type(exc).__name__)
        write_state(record)
        raise
    return {"stage": operation, "result": "RESTORED_VERIFIED",
            "restore_count": record["restore_count"],
            "lease_id": record["session_id"], "boot_id": record["boot_id"]}


STAGED_ASSET_SETS = Path("/opt/plasma/assets/staged")
STAGED_OWNER_UID = 0
MANIFEST_PREVIOUS = guard.FIRMWARE / "plasma-image-manifest.json.previous"
BUNDLE_LOAD_OUTCOMES = ("fpga_loaded", "fpga_load_denied",
                        "recovery_required", "fpga_identity_failed")


class BundleLoadOutcome(RuntimeError):
    """Classified bundle-load failure: whether the PL may have been written."""

    def __init__(self, outcome: str, code: str) -> None:
        super().__init__(code)
        self.outcome = outcome
        self.code = code


def _failure_code(exc: BaseException) -> str:
    text = str(exc)
    if re.fullmatch(r"[A-Z0-9_]{3,96}", text):
        return text
    return type(exc).__name__


def _read_staged_bytes(path: Path, max_bytes: int) -> bytes:
    """Root-owned regular file read once; the returned bytes are what is used."""
    guard.protected(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        need(info.st_uid == STAGED_OWNER_UID and info.st_mode & 0o022 == 0 and
             0 < info.st_size <= max_bytes, "BUNDLE_STAGED_FILE_UNTRUSTED")
        raw = stream.read(max_bytes + 1)
    need(0 < len(raw) <= max_bytes, "BUNDLE_STAGED_FILE_UNTRUSTED")
    return raw


def _staged_json(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: need(False, "BUNDLE_JSON_NONFINITE"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ImageDeploymentDenied("BUNDLE_STAGED_JSON_DENIED") from exc
    need(type(value) is dict, "BUNDLE_STAGED_JSON_DENIED")
    return value


def read_staged_fpga_handoff(asset_set_sha256: str, *,
                             staged_root: Path | None = None
                             ) -> tuple[dict, bytes, bytes, bytes]:
    """Root re-derivation of the FPGA handoff from an immutable B3 Set.

    The caller supplies only the Set SHA-256. Root locates the Set itself,
    requires a root-owned non-writable tree, binds b3-install.json to the
    exact manifest.json bytes and rehashes each FPGA file it will use.
    """
    need(type(asset_set_sha256) is str and
         re.fullmatch(r"[0-9a-f]{64}", asset_set_sha256) is not None,
         "BUNDLE_ASSET_SET_SHA_INVALID")
    base = STAGED_ASSET_SETS if staged_root is None else staged_root
    target = base / asset_set_sha256
    guard.protected(base, file=False)
    guard.protected(target, file=False)
    manifest_raw = _read_staged_bytes(target / "manifest.json", 1_048_576)
    receipt = _staged_json(_read_staged_bytes(target / "b3-install.json", 65536))
    manifest = _staged_json(manifest_raw)
    need(receipt.get("schema") == "plasma.ppu.b3-install.v1" and
         receipt.get("archive_sha256") == asset_set_sha256 and
         receipt.get("manifest_sha256") ==
         hashlib.sha256(manifest_raw).hexdigest() and
         manifest.get("schema") == "plasma.ppu.bundle.v3" and
         type(manifest.get("target")) is dict and
         manifest["target"].get("board") == "pynq-z2" and
         manifest["target"].get("fpga_part") == "xc7z020clg400-1" and
         type(manifest.get("packages")) is list and
         1 <= len(manifest["packages"]) <= 32,
         "BUNDLE_STAGED_SET_INVALID")
    packages = manifest["packages"]
    need(all(type(item) is dict for item in packages), "BUNDLE_STAGED_SET_INVALID")
    fpga = [item for item in packages if item.get("kind") == "fpga-image"]
    profiles = [item for item in packages if item.get("kind") == "programming-profile"]
    need(len(fpga) == 1, "BUNDLE_FPGA_IMAGE_PACKAGE_NOT_UNIQUE")
    need(len(profiles) <= 1, "BUNDLE_PROGRAMMING_PROFILE_NOT_UNIQUE")
    fpga = fpga[0]
    need(type(fpga.get("id")) is str and _basename(fpga["id"]) and
         type(fpga.get("version")) is str and _basename(fpga["version"]) and
         type(fpga.get("files")) is list, "BUNDLE_FPGA_IMAGE_PACKAGE_INVALID")

    def load(entry: dict) -> bytes:
        name = entry.get("path")
        need(type(name) is str and
             name.startswith("payload/packages/" + fpga["id"] + "/fpga/") and
             _basename(name.rsplit("/", 1)[1]) and
             type(entry.get("sha256")) is str and
             re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is not None and
             type(entry.get("size")) is int,
             "BUNDLE_FPGA_FILE_DESCRIPTOR_INVALID")
        path = target / name
        parent = target
        for part in Path(name).parts[:-1]:
            parent = parent / part
            guard.protected(parent, file=False)
        raw = _read_staged_bytes(path, 16_000_000)
        need(len(raw) == entry["size"] and
             hashlib.sha256(raw).hexdigest() == entry["sha256"],
             "BUNDLE_FPGA_FILE_CHANGED")
        return raw

    entries = [item for item in fpga["files"] if type(item) is dict]
    need(len(entries) == len(fpga["files"]), "BUNDLE_FPGA_FILE_DESCRIPTOR_INVALID")
    binaries = [e for e in entries if str(e.get("path", "")).endswith(".bin")]
    hwhs = [e for e in entries if str(e.get("path", "")).endswith(".hwh")]
    need(len(binaries) == 1 and len(hwhs) == 1 and
         not any(str(e.get("path", "")).endswith(".bit") for e in entries),
         "BUNDLE_FPGA_REQUIRES_PREBUILT_BIN_AND_HWH")
    candidates = []
    for entry in entries:
        if str(entry.get("path", "")).endswith(".json"):
            raw = load(entry)
            if _staged_json(raw).get("schema") == "plasma.fpga.image.v1":
                candidates.append((entry, raw))
    need(len(candidates) == 1, "BUNDLE_FPGA_MANIFEST_NOT_UNIQUE")
    manifest_entry, manifest_bytes = candidates[0]
    bin_bytes = load(binaries[0])
    hwh_bytes = load(hwhs[0])
    paired = parse_image_manifest_bytes(manifest_bytes)
    profile = None
    if profiles:
        item = profiles[0]
        need(type(item.get("files")) is list and
             all(type(f) is dict for f in item["files"]),
             "BUNDLE_PROGRAMMING_PROFILE_INVALID")
        descriptor = {
            "id": item.get("id"), "kind": item.get("kind"),
            "version": item.get("version"), "requires": item.get("requires"),
            "files": sorted(({
                "path": f.get("path"), "sha256": f.get("sha256"),
                "size": f.get("size"), "executable": f.get("executable"),
            } for f in item["files"]), key=lambda f: str(f["path"])),
        }
        profile = {
            "package_id": item.get("id"),
            "package_version": item.get("version"),
            "package_identity_sha256": hashlib.sha256(json.dumps(
                descriptor, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
    handoff = {
        "schema": "plasma.ppu.fpga-asset-handoff.v1",
        "status": "VERIFIED_NOT_LOADED",
        "asset_set_sha256": asset_set_sha256,
        "fpga_image": {
            "package_id": fpga["id"],
            "package_version": fpga["version"],
            "image_id": paired.image_id,
            "bin_relative_path": binaries[0]["path"],
            "bin_sha256": binaries[0]["sha256"],
            "hwh_relative_path": hwhs[0]["path"],
            "hwh_sha256": hwhs[0]["sha256"],
            "manifest_relative_path": manifest_entry["path"],
            "manifest_sha256": manifest_entry["sha256"],
            "board_id": manifest["target"]["board"],
            "fpga_part": manifest["target"]["fpga_part"],
            "abi_version_claim": paired.abi_version,
        },
        "programming_profile": profile,
        "root_hardware_validation": "NOT_RUN",
        "fpga_install": "NOT_RUN",
        "fpga_load": "NOT_RUN",
        "dut": "NOT_RUN",
        "ready": False,
    }
    return handoff, manifest_bytes, bin_bytes, hwh_bytes


def _write_firmware_file(path: Path, raw: bytes) -> None:
    """Atomic replace of a Root-owned metadata file in /lib/firmware."""
    fd, temp_name = tempfile.mkstemp(prefix=".plasma-manifest.", dir=guard.FIRMWARE)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as destination:
            destination.write(raw)
            destination.flush()
            os.fsync(destination.fileno())
        temp.chmod(0o644)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    folder = os.open(guard.FIRMWARE, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def _promote_manifest(manifest_bytes: bytes) -> bytes | None:
    """Make the Bundle companion the active Root Image Manifest.

    Returns the previous bytes when the Manifest changed (kept on disk as
    MANIFEST_PREVIOUS), or None when it was already identical.
    """
    previous = None
    if MANIFEST_FILE.exists() or MANIFEST_FILE.is_symlink():
        guard.protected(MANIFEST_FILE)
        previous = MANIFEST_FILE.read_bytes()
        if previous == manifest_bytes:
            return None
        if MANIFEST_PREVIOUS.exists() or MANIFEST_PREVIOUS.is_symlink():
            guard.protected(MANIFEST_PREVIOUS)
        _write_firmware_file(MANIFEST_PREVIOUS, previous)
    _write_firmware_file(MANIFEST_FILE, manifest_bytes)
    need(MANIFEST_FILE.read_bytes() == manifest_bytes, "MANIFEST_PROMOTION_FAILED")
    return previous if previous is not None else b""


def _undo_promotion(previous: bytes | None) -> None:
    if previous is None:
        return
    if previous == b"":
        MANIFEST_FILE.unlink()
    else:
        _write_firmware_file(MANIFEST_FILE, previous)


def bundle_load(asset_set_sha256: str) -> dict:
    """B3 FPGA load of an installed Set: stage, promote, download, Identity.

    Only the Set SHA-256 crosses the privilege boundary. Every denial up to
    the first PL write leaves the FPGA and the active Root Manifest unchanged.
    """
    try:
        trusted_local()
        handoff, manifest_bytes, bin_bytes, hwh_bytes = \
            read_staged_fpga_handoff(asset_set_sha256)
        preflight = validate_bundle_fpga_handoff(
            handoff, expected_active_set_sha256=asset_set_sha256,
            manifest_bytes=manifest_bytes, bin_bytes=bin_bytes,
            hwh_bytes=hwh_bytes)
        release = parse_image_manifest_bytes(manifest_bytes)
        port = guard.RootZ2TargetPort(release=release)
    except BaseException as exc:
        raise BundleLoadOutcome("fpga_load_denied", _failure_code(exc)) from exc
    with port.exclusive():
        try:
            _stage_files_locked(release, manifest_bytes=manifest_bytes,
                                bin_bytes=bin_bytes, hwh_bytes=hwh_bytes)
            previous = _promote_manifest(manifest_bytes)
            try:
                # Full read-only admission (boot, Golden, FPGA Manager,
                # /proc /dev/mem /dev/uio* census) before any PL write.
                _confirm_current(port, release, read_state(release), "download")
            except BaseException:
                _undo_promotion(previous)
                raise
        except BaseException as exc:
            raise BundleLoadOutcome("fpga_load_denied", _failure_code(exc)) from exc
        try:
            download = _run_locked("download", port, release)
        except BaseException as exc:
            raise BundleLoadOutcome("recovery_required", _failure_code(exc)) from exc
        try:
            test = _run_locked("test", port, release)
        except BaseException as exc:
            raise BundleLoadOutcome("fpga_identity_failed", _failure_code(exc)) from exc
    return {
        "stage": "bundle-load", "result": "fpga_loaded",
        "asset_set_sha256": asset_set_sha256,
        "fpga_image_id": release.image_id,
        "fpga_bin_sha256": release.firmware_sha256,
        "fpga_manifest_sha256": preflight["fpga_manifest_sha256"],
        "manifest_promoted": previous is not None,
        "download_count": download["download_count"],
        "test_count": test["test_count"],
        "identity": test["result"],
        "lease_id": test["lease_id"], "boot_id": test["boot_id"],
        "auto_restore": False, "dut": "NOT_RUN",
    }


def _expected_identity(release: ImageManifest) -> dict[int, int]:
    return {offset: expected for offset, expected, mask in release.identity_words}


def identity_child() -> int:
    trusted_local()
    release = read_image_manifest()
    state = read_state(release)
    need(state is not None and state["status"] == "TEST_IN_FLIGHT" and
         state["image"] == release.firmware_name and
         state["manifest_sha256"] == manifest_sha256() and not CHILD.exists(),
         "IDENTITY_CHILD_NOT_CLAIMED")
    need(state["boot_id"] ==
         (guard.PROC / "sys/kernel/random/boot_id").read_text().strip() and
         ": writing " + release.firmware_name + " to " in
         guard.manager_last_load(), "IDENTITY_IMAGE_NOT_CURRENT")
    reviewed = ROOT / "software/python/plasma_interfaces/linux_mmio.py"
    spec = importlib.util.spec_from_file_location("fpga_image_native_mmio", reviewed)
    need(spec is not None and spec.loader is not None,
         "NATIVE_MMIO_DRIVER_NOT_INSTALLED")
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver
    spec.loader.exec_module(driver)
    offsets = frozenset(_expected_identity(release))
    aperture = driver.MMIOAperture(
        release.axi_base, offsets, frozenset(), release.axi_bytes)
    with driver.LinuxMMIO((aperture,), readonly=True) as mmio:
        observed = read_identity(mmio.read32, release)
        stats = mmio.stats()
        need(stats.read32 == len(release.identity_words) and stats.write32 == 0,
             "NATIVE_MMIO_ACCESS_COUNT_CHANGED")
    guard.record_json(CHILD, {"observed": observed})
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == "bundle-load":
        try:
            result = bundle_load(argv[1])
        except BundleLoadOutcome as exc:
            result = {"stage": "bundle-load", "result": exc.outcome,
                      "code": exc.code, "asset_set_sha256": argv[1]
                      if re.fullmatch(r"[0-9a-f]{64}", argv[1]) else None}
            print("PLASMA_BUNDLE_LOAD=" + json.dumps(
                result, sort_keys=True, separators=(",", ":")), flush=True)
            return 3
        print("PLASMA_BUNDLE_LOAD=" + json.dumps(
            result, sort_keys=True, separators=(",", ":")), flush=True)
        return 0
    need(len(argv) == 1, "ONE_OPERATION_REQUIRED")
    if argv[0] == "--identity-child":
        return identity_child()
    result = run(argv[0])
    # Compatibility with the already-merged direct Path 2 receipt schema:
    # not a runtime project selector and does not grant any hardware access.
    result["project"] = "pl/projects/z2-fixed-unified-site1"
    print("PLASMA_PATH2_STAGE=" + json.dumps(
        result, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
