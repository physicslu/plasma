"""PYNQ-Z2 Site1 F1-B minimal Development HIL: independent repeatable stages.

No auto-chaining. The root-owned target implementation must be separately
reviewed and installed before any physical execution. Only the fixed, known
F1-B candidate and original base.bin are allowed. AXI isolation remains
UNPROVEN under the explicitly accepted Development-only UIO exception.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import time
import uuid

from pl.hil import f1b
from pl.hil import path2_f1b_dev_risk as risk
from pl.hil import path2_z2_target_guard as guard
from pl.hil.swd04 import one_shot

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".plasma-f1b-site1-development-state.json"
CHILD = one_shot.OWNER_DIR / "path2-f1b-identity.json"
CANDIDATE = guard.FIRMWARE / "plasma-f1b-owner-20261020-once.bin"
RECOVERY = guard.FIRMWARE / "base.bin"
RELEASE_FILE = ROOT / "pl/hil/approved-fpga-image.json"
SCHEMA = "plasma.f1b.site1.development.v2"
STATUS = ("BASE", "F1B", "DOWNLOAD_IN_FLIGHT", "TEST_IN_FLIGHT",
          "RESTORE_IN_FLIGHT", "UNKNOWN")


class LiveStageDenied(ValueError):
    pass


def need(test: bool, reason: str) -> None:
    if not test:
        raise LiveStageDenied(reason)


# This record is compiled into the reviewed root-owned source closure. It is
# release authorization, not a runtime Project/Profile or a caller JSON claim.
@dataclass(frozen=True)
class ApprovedImage:
    image_id: str
    board_id: str
    fpga_part: str
    firmware_name: str
    firmware_sha256: str
    recovery_name: str
    recovery_sha256: str
    abi_version: int
    identity_words: tuple[tuple[int, int], ...]
    site_bitmap: int


F1B_APPROVED_IMAGE = ApprovedImage(
    image_id="f1b-site1-20261020",
    board_id="pynq-z2",
    fpga_part="xc7z020clg400-1",
    firmware_name=CANDIDATE.name,
    firmware_sha256=f1b.BIN_SHA,
    recovery_name=RECOVERY.name,
    recovery_sha256=f1b.BASE_SHA,
    abi_version=f1b.IDENTITY[0x0004],
    identity_words=tuple(sorted(f1b.IDENTITY.items())),
    site_bitmap=1,
)
AUTHORIZED_IMAGES = (F1B_APPROVED_IMAGE,)


def approved_image(image: object) -> ApprovedImage:
    """Only source-approved images, never arbitrary caller-provided manifests."""
    need(type(image) is ApprovedImage and image in AUTHORIZED_IMAGES,
         "IMAGE_RELEASE_NOT_ROOT_AUTHORIZED")
    need(image.board_id == "pynq-z2" and
         image.fpga_part == "xc7z020clg400-1" and
         image.firmware_name == CANDIDATE.name and
         image.recovery_name == RECOVERY.name and
         image.firmware_sha256 == f1b.BIN_SHA and
         image.recovery_sha256 == f1b.BASE_SHA and
         image.abi_version == f1b.IDENTITY[0x0004] and
         image.identity_words == tuple(sorted(f1b.IDENTITY.items())) and
         image.site_bitmap == 1,
         "IMAGE_RELEASE_SOURCE_LOCK_MISMATCH")
    return image


def _release_pairs(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate keys rather than silently overriding AP policy."""
    out = {}
    for key, value in pairs:
        need(key not in out, "IMAGE_RELEASE_DUPLICATE_FIELD")
        out[key] = value
    return out


def read_approved_release() -> ApprovedImage:
    """Read the reviewed, Root-owned + complete-source-SHA-pinned release.

    This file is included in the SSH source bundle and its SHA256 manifest.
    The existing Root Entry validates the full manifest and exact source Git
    pin before calling this code. No caller can choose a file or Python IP.
    """
    one_shot.protected(RELEASE_FILE)
    need(RELEASE_FILE.is_file() and 0 < RELEASE_FILE.stat().st_size <= 4096,
         "IMAGE_RELEASE_FILE_DENIED")
    try:
        raw = json.loads(RELEASE_FILE.read_text(encoding="utf-8"),
                         object_pairs_hook=_release_pairs,
                         parse_constant=lambda _: need(False,
                             "IMAGE_RELEASE_NONFINITE_NUMBER_DENIED"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveStageDenied("IMAGE_RELEASE_JSON_DENIED") from exc
    fields = {"schema", "authorization", "image_id", "board_id",
              "fpga_part", "firmware_name", "firmware_sha256",
              "recovery_name", "recovery_sha256", "abi_version",
              "identity_words", "site_bitmap"}
    need(type(raw) is dict and set(raw) == fields and
         raw["schema"] == "plasma.fpga.image-release.v1" and
         raw["authorization"] == "SOURCE_PINNED_ROOT_APPROVAL",
         "IMAGE_RELEASE_SCHEMA_DENIED")
    names = ("image_id", "board_id", "fpga_part", "firmware_name",
             "firmware_sha256", "recovery_name", "recovery_sha256")
    need(all(type(raw[n]) is str and bool(raw[n]) for n in names) and
         type(raw["abi_version"]) is int and
         type(raw["site_bitmap"]) is int and
         type(raw["identity_words"]) is list and
         len(raw["identity_words"]) == 3 and
         all(type(pair) is list and len(pair) == 2 and
             all(type(word) is int and 0 <= word <= 0xFFFFFFFF
                 for word in pair)
             for pair in raw["identity_words"]),
         "IMAGE_RELEASE_VALUE_DENIED")
    image = ApprovedImage(
        image_id=raw["image_id"],
        board_id=raw["board_id"],
        fpga_part=raw["fpga_part"],
        firmware_name=raw["firmware_name"],
        firmware_sha256=raw["firmware_sha256"],
        recovery_name=raw["recovery_name"],
        recovery_sha256=raw["recovery_sha256"],
        abi_version=raw["abi_version"],
        identity_words=tuple(tuple(pair) for pair in raw["identity_words"]),
        site_bitmap=raw["site_bitmap"],
    )
    return approved_image(image)


def verify_image_metadata(image: ApprovedImage, *, board_id: str,
                          fpga_part: str, abi_version: int,
                          identity_words: dict[int, int]) -> None:
    """Pure comparison, not independent PS/PL attestation.

    A qualified provider must collect authentic live board and PL facts
    before this can be used to admit any future non-F1-B release.
    """
    image = approved_image(image)
    need(type(board_id) is str and board_id == image.board_id and
         type(fpga_part) is str and fpga_part == image.fpga_part,
         "IMAGE_BOARD_OR_FPGA_PART_MISMATCH")
    need(type(abi_version) is int and abi_version == image.abi_version and
         type(identity_words) is dict and
         identity_words == dict(image.identity_words),
         "IMAGE_ABI_OR_IDENTITY_MISMATCH")


def digest(data: object) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def native_runtime_preflight(*, version=None, machine=None,
                             endian=None, executable=None) -> None:
    version = tuple(sys.version_info[:3]) if version is None else tuple(version)
    machine = platform.machine() if machine is None else machine
    endian = sys.byteorder if endian is None else endian
    executable = sys.executable if executable is None else executable
    need(version == (3, 12, 13) and machine == "armv7l" and endian == "little"
         and Path(executable).resolve().is_relative_to(
             "/opt/plasma/python/3.12.13"),
         "NATIVE_ARMV7_PYTHON_RUNTIME_REQUIRED")


def trusted_local() -> None:
    need(os.geteuid() == 0, "ROOT_REQUIRED")
    # The protected installed root entry already pins the explicit
    # owner-reviewed risk scope; an environment literal adds no authority.
    native_runtime_preflight()
    for path in (ROOT, Path(__file__).resolve(),
                 ROOT / "pl/hil/path2_f1b_dev_risk.py",
                 ROOT / "pl/hil/path2_z2_target_guard.py",
                 ROOT / "software/python/plasma_interfaces/linux_mmio.py"):
        one_shot.protected(path, file=path != ROOT)
    one_shot.OWNER_DIR.mkdir(mode=0o700, exist_ok=True)
    one_shot.protected(one_shot.OWNER_DIR, file=False)


def _state_file_trusted() -> None:
    one_shot.protected(STATE)
    need(STATE.stat().st_mode & 0o077 == 0 and STATE.stat().st_size <= 4096,
         "STATE_FILE_NOT_PRIVATE")


def read_state() -> dict | None:
    if not STATE.exists():
        need(not STATE.is_symlink(), "STATE_SYMLINK_DENIED")
        return None
    _state_file_trusted()
    raw = json.loads(STATE.read_text())
    need(type(raw) is dict and set(raw) == {
         "schema", "session_id", "boot_id", "status", "image",
         "download_count", "test_count", "restore_count",
         "evidence_sha256", "last_error"},
         "STATE_SCHEMA_INVALID")
    need(raw["schema"] == SCHEMA and raw["status"] in STATUS and
         raw["image"] in ("base.bin", CANDIDATE.name) and
         type(raw["session_id"]) is str and len(raw["session_id"]) >= 8 and
         type(raw["boot_id"]) is str and len(raw["boot_id"]) >= 8 and
         all(type(raw[k]) is int and raw[k] >= 0 for k in (
             "download_count", "test_count", "restore_count")),
         "STATE_IDENTITY_INVALID")
    return raw


def write_state(record: dict) -> None:
    """Atomic fsync checkpoint before any Manager write or MMIO child."""
    content = (json.dumps(record, sort_keys=True, separators=(",", ":"))
               + "\n").encode()
    need(len(content) <= 4096, "STATE_TOO_LARGE")
    if STATE.exists():
        _state_file_trusted()
    temp = STATE.with_name(STATE.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(content):
            n = os.write(fd, content[offset:])
            need(n > 0, "STATE_WRITE_INCOMPLETE")
            offset += n
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp, STATE)
    directory = os.open(STATE.parent, os.O_RDONLY | os.O_DIRECTORY |
                        os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def live_report(port: guard.RootZ2TargetPort, image: str) -> dict:
    release = read_approved_release()
    need(image in (release.recovery_name, release.firmware_name),
         "IMAGE_NOT_PINNED")
    report = risk.collect_live(root_port=port, approval=risk.WAIVER,
                               scope=risk.ALLOWED[0],
                               expected_firmware=image)
    need(report["site"] == 1 and report["expected_manager_firmware"] == image
         and port.image_sha256("candidate") == release.firmware_sha256
         and port.image_sha256("recovery") == release.recovery_sha256,
         "CURRENT_IMAGE_OR_RECOVERY_CHANGED")
    return report


def init_state(report: dict) -> dict:
    return {"schema": SCHEMA, "session_id": "site1-" + uuid.uuid4().hex,
            "boot_id": report["target_boot_id"], "status": "BASE",
            "image": "base.bin", "download_count": 0,
            "test_count": 0, "restore_count": 0,
            "evidence_sha256": digest(report), "last_error": ""}


def confirm_current(port, record: dict | None, stage: str) -> tuple[dict, dict]:
    # Every independent trigger rechecks current target facts. The state
    # document is evidence/history, not authority to trust a stale image.
    if record is not None:
        need(record["status"] in ("BASE", "F1B"),
             "UNCERTAIN_PRIOR_OPERATION_MANUAL_RECOVERY")
        # Restoring base.bin proves recovery only. Reject a known missing
        # F1-B before collecting live facts or starting the MMIO child; a
        # test-only Work Order must never implicitly Download the candidate.
        if stage == "test":
            need(record["status"] == "F1B" and
                 record["image"] == CANDIDATE.name, "F1B_IMAGE_NOT_LOADED")
        expected = record["image"]
    else:
        need(stage == "download", "DOWNLOAD_REQUIRED_BEFORE_TEST_OR_RESTORE")
        expected = "base.bin"
    report = live_report(port, expected)
    if record is None:
        record = init_state(report)
    else:
        need(record["boot_id"] == report["target_boot_id"],
             "BOOT_CHANGED_MANUAL_REVIEW")
    return record, report


def run(stage: str) -> dict:
    need(stage in ("download", "test", "restore"), "STAGE_NOT_ALLOWLISTED")
    trusted_local()
    release = read_approved_release()
    # The shared FPGA owner serializes all cooperating configuration users.
    port = guard.RootZ2TargetPort(candidate=CANDIDATE, recovery=RECOVERY,
                                  ledger=one_shot.OWNER_DIR / "path2-f1b-site1.json")
    with port.exclusive():
        record, current = confirm_current(port, read_state(), stage)
        if stage == "download":
            # Both BASE->F1B and F1B->F1B are operator-triggerable.
            record.update(status="DOWNLOAD_IN_FLIGHT", last_error="")
            write_state(record)  # persists recovery obligation first
            try:
                one_shot.manager_write(release.firmware_name)
                after = live_report(port, CANDIDATE.name)
                record.update(status="F1B", image=CANDIDATE.name,
                              download_count=record["download_count"] + 1,
                              evidence_sha256=digest(after))
                write_state(record)
            except BaseException as exc:
                record.update(status="UNKNOWN", last_error=type(exc).__name__)
                write_state(record)
                raise
            return {"stage": stage, "result": "LOADED_AND_HELD",
                    "download_count": record["download_count"],
                    "lease_id": record["session_id"],
                    "boot_id": record["boot_id"],
                    "auto_test": False}
        if stage == "test":
            if CHILD.exists():
                one_shot.protected(CHILD)
                CHILD.unlink()
            record.update(status="TEST_IN_FLIGHT", last_error="")
            write_state(record)
            try:
                one_shot.run_child([sys.executable, "-m",
                                    "pl.hil.path2_f1b_minimal_stage",
                                    "--identity-child"])
                result = json.loads(CHILD.read_text())
                need(result == {"observed": {str(k): v for k, v in
                                             f1b.IDENTITY.items()}},
                     "THREE_READ_IDENTITY_MISMATCH")
                after = live_report(port, CANDIDATE.name)
                record.update(status="F1B", test_count=record["test_count"] + 1,
                              evidence_sha256=digest({"target": after,
                                                      "identity": result}))
                write_state(record)
            except BaseException as exc:
                record.update(status="UNKNOWN", last_error=type(exc).__name__)
                write_state(record)
                raise
            return {"stage": stage, "result": "IDENTITY_PASS",
                    "test_count": record["test_count"],
                    "read32_count": 3, "write32_count": 0,
                    "lease_id": record["session_id"],
                    "boot_id": record["boot_id"], "auto_restore": False}
        if record["status"] == "BASE":
            # Verified no-op is a valid repeatable Restore.
            return {"stage": stage, "result": "ALREADY_RESTORED",
                    "restore_count": record["restore_count"],
                    "lease_id": record["session_id"], "boot_id": record["boot_id"]}
        record.update(status="RESTORE_IN_FLIGHT", last_error="")
        write_state(record)
        try:
            one_shot.manager_write(release.recovery_name)
            after = live_report(port, "base.bin")
            record.update(status="BASE", image="base.bin",
                          restore_count=record["restore_count"] + 1,
                          evidence_sha256=digest(after))
            write_state(record)
        except BaseException as exc:
            record.update(status="UNKNOWN", last_error=type(exc).__name__)
            write_state(record)
            raise
        return {"stage": stage, "result": "RESTORED_VERIFIED",
                "restore_count": record["restore_count"],
                "lease_id": record["session_id"], "boot_id": record["boot_id"]}


def child_main() -> int:
    # Read-only native subprocess: does not acquire the parent FPGA lock and
    # cannot invoke an FPGA Manager writer.
    trusted_local()
    release = read_approved_release()
    state = read_state()
    need(state is not None and state["status"] == "TEST_IN_FLIGHT" and
         state["image"] == CANDIDATE.name and not CHILD.exists(),
         "IDENTITY_CHILD_NOT_CLAIMED")
    need(state["boot_id"] ==
         (guard.PROC / "sys/kernel/random/boot_id").read_text().strip()
         and ": writing " + CANDIDATE.name + " to " in
         one_shot.manager_last_load(), "IDENTITY_IMAGE_NOT_CURRENT")
    reviewed = ROOT / "software/python/plasma_interfaces/linux_mmio.py"
    spec = importlib.util.spec_from_file_location("f1b_path2_native_mmio",
                                                  reviewed)
    need(spec is not None and spec.loader is not None,
         "NATIVE_MMIO_DRIVER_NOT_INSTALLED")
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver
    spec.loader.exec_module(driver)
    aperture = driver.MMIOAperture(f1b.BASE, frozenset(dict(release.identity_words)),
                                   frozenset(), f1b.LENGTH)
    with driver.LinuxMMIO((aperture,), readonly=True) as mmio:
        observed = f1b.read_identity(mmio.read32)
        need(observed == dict(release.identity_words),
             "IMAGE_IDENTITY_NOT_APPROVED")
        need(mmio.stats().read32 == len(release.identity_words) == 3 and
             mmio.stats().write32 == 0,
             "NATIVE_MMIO_ACCESS_COUNT_CHANGED")
    one_shot.record_json(CHILD, {"observed": observed})
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    need(len(argv) == 1, "ONE_FIXED_STAGE_ARGUMENT_REQUIRED")
    if argv[0] == "--identity-child":
        return child_main()
    result = run(argv[0])
    result["project"] = "pl/projects/z2-fixed-unified-site1"
    result["profile_id"] = "f1b-site1-v1"
    print("PLASMA_PATH2_STAGE=" + json.dumps(
          result, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
