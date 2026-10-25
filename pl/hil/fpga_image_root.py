"""Trusted FPGA Image Deployment: source-approved download, identity, restore.

No protocol/IP-specific handler, runtime Project/Profile selector or Flash write.
Production operations retain the existing two-argument protected Root Entry.
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
import uuid

from pl.hil import fpga_image_guard as guard
from pl.hil import fpga_image_admission as admission
from pl.hil.swd04 import one_shot

ROOT = Path(__file__).resolve().parents[2]
RELEASE_FILE = ROOT / "pl/hil/approved-fpga-image.json"
STATE = ROOT / ".plasma-fpga-image-deployment-state.json"
CHILD = one_shot.OWNER_DIR / "fpga-image-identity.json"
SCHEMA = "plasma.fpga.image-deployment.v1"
STATUS = ("RECOVERY", "IMAGE", "DOWNLOAD_IN_FLIGHT", "TEST_IN_FLIGHT",
          "RESTORE_IN_FLIGHT", "UNKNOWN")


class ImageDeploymentDenied(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ImageDeploymentDenied(code)


@dataclass(frozen=True)
class ApprovedImage:
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
    site_bitmap_offset: int
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


def read_approved_release() -> ApprovedImage:
    """Release is protected by exact Root commit pin and full SHA256 manifest.

    JSON merely describes the publisher-approved release; it cannot authorize
    itself or override the protected source closure.
    """
    one_shot.protected(RELEASE_FILE)
    need(RELEASE_FILE.is_file() and 0 < RELEASE_FILE.stat().st_size <= 8192,
         "IMAGE_RELEASE_FILE_DENIED")
    try:
        data = json.loads(RELEASE_FILE.read_text(encoding="utf-8"),
                          object_pairs_hook=_pairs,
                          parse_constant=lambda _: need(False, "IMAGE_RELEASE_NONFINITE"))
    except (UnicodeError, json.JSONDecodeError) as e:
        raise ImageDeploymentDenied("IMAGE_RELEASE_JSON_DENIED") from e
    fields = {"schema", "authorization", "runtime_admitted", "image_id",
              "board_id", "fpga_part", "soc_compatible", "firmware_name",
              "firmware_sha256", "recovery_name", "recovery_sha256",
              "abi_version", "abi_offset", "identity_words", "site_bitmap",
              "site_bitmap_offset", "axi_base", "axi_bytes", "owner_base",
              "owner_bytes", "uio_name", "expected_uio"}
    need(type(data) is dict and set(data) == fields and
         data["schema"] == "plasma.fpga.image-release.v2" and
         data["authorization"] == "SOURCE_PINNED_ROOT_APPROVAL" and
         data["runtime_admitted"] is True, "IMAGE_RELEASE_NOT_AUTHORIZED")
    for key in ("image_id", "board_id", "fpga_part", "soc_compatible", "uio_name"):
        need(type(data[key]) is str and 0 < len(data[key]) <= 128,
             "IMAGE_RELEASE_VALUE_DENIED")
    need(_basename(data["firmware_name"]) and _basename(data["recovery_name"]) and
         data["firmware_name"] != data["recovery_name"] and
         all(type(data[k]) is str and
             re.fullmatch(r"[a-f0-9]{64}", data[k]) is not None
             for k in ("firmware_sha256", "recovery_sha256")),
         "IMAGE_RELEASE_FIRMWARE_DENIED")
    for key in ("abi_version", "abi_offset", "site_bitmap", "site_bitmap_offset",
                "axi_base", "axi_bytes", "owner_base", "owner_bytes"):
        need(type(data[key]) is int and 0 <= data[key] <= 0xFFFFFFFF,
             "IMAGE_RELEASE_INTEGER_DENIED")
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
         data["site_bitmap_offset"] in offsets and
         next(w for w in words if w[0] == data["abi_offset"])[1] ==
         data["abi_version"] and
         next(w for w in words if w[0] == data["site_bitmap_offset"])[1] ==
         data["site_bitmap"], "IMAGE_RELEASE_ABI_DENIED")
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
    return ApprovedImage(
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


def read_identity(read32, release: ApprovedImage) -> dict[int, int]:
    observed = {}
    for offset, expected, mask in release.identity_words:
        value = read32(release.axi_base + offset)
        need(type(value) is int and 0 <= value <= 0xFFFFFFFF and
             value & mask == expected & mask, "PL_IDENTITY_MISMATCH")
        observed[offset] = value
    need(observed[release.abi_offset] == release.abi_version and
         observed[release.site_bitmap_offset] == release.site_bitmap,
         "PL_ABI_OR_SITE_MISMATCH")
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
    for path in (ROOT, Path(__file__).resolve(), RELEASE_FILE,
                 ROOT / "pl/hil/fpga_image_guard.py",
                 ROOT / "pl/hil/fpga_image_admission.py",
                 ROOT / "software/python/plasma_interfaces/linux_mmio.py"):
        one_shot.protected(path, file=path != ROOT)
    one_shot.OWNER_DIR.mkdir(mode=0o700, exist_ok=True)
    one_shot.protected(one_shot.OWNER_DIR, file=False)


def _state_file_trusted() -> None:
    one_shot.protected(STATE)
    need(STATE.stat().st_mode & 0o077 == 0 and STATE.stat().st_size <= 4096,
         "STATE_FILE_NOT_PRIVATE")


def read_state(release: ApprovedImage) -> dict | None:
    if not STATE.exists():
        need(not STATE.is_symlink(), "STATE_SYMLINK_DENIED")
        return None
    _state_file_trusted()
    data = json.loads(STATE.read_text())
    need(type(data) is dict and set(data) == {
        "schema", "session_id", "boot_id", "status", "image", "image_id",
        "download_count", "test_count", "restore_count",
        "evidence_sha256", "last_error"}, "STATE_SCHEMA_INVALID")
    need(data["schema"] == SCHEMA and
         data["image_id"] == release.image_id and
         data["status"] in STATUS and
         data["image"] in (release.recovery_name, release.firmware_name) and
         type(data["session_id"]) is str and len(data["session_id"]) >= 8 and
         type(data["boot_id"]) is str and len(data["boot_id"]) >= 8 and
         all(type(data[k]) is int and data[k] >= 0 for k in
             ("download_count", "test_count", "restore_count")),
         "STATE_IMAGE_OR_IDENTITY_INVALID")
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


def live_report(port: guard.RootZ2TargetPort, release: ApprovedImage,
                image: str) -> dict:
    need(image in (release.recovery_name, release.firmware_name),
         "IMAGE_NOT_SOURCE_PINNED")
    report = admission.collect_live(root_port=port, release=release,
                                    expected_firmware=image)
    need(report["expected_manager_firmware"] == image and
         port.image_sha256("candidate") == release.firmware_sha256 and
         port.image_sha256("recovery") == release.recovery_sha256,
         "CURRENT_IMAGE_OR_RECOVERY_CHANGED")
    return report


def _initial_state(report: dict, release: ApprovedImage) -> dict:
    return {"schema": SCHEMA, "session_id": "fpga-" + uuid.uuid4().hex,
            "boot_id": report["target_boot_id"], "status": "RECOVERY",
            "image": release.recovery_name, "image_id": release.image_id,
            "download_count": 0, "test_count": 0, "restore_count": 0,
            "evidence_sha256": _digest(report), "last_error": ""}


def _confirm_current(port, release: ApprovedImage, record: dict | None,
                     operation: str) -> tuple[dict, dict]:
    if record is not None:
        need(record["status"] in ("RECOVERY", "IMAGE"),
             "UNCERTAIN_PRIOR_OPERATION_MANUAL_RECOVERY")
        if operation == "test":
            need(record["status"] == "IMAGE" and
                 record["image"] == release.firmware_name,
                 "APPROVED_IMAGE_NOT_LOADED")
        expected = record["image"]
    else:
        need(operation == "download", "DOWNLOAD_REQUIRED_BEFORE_TEST_OR_RESTORE")
        expected = release.recovery_name
    report = live_report(port, release, expected)
    if record is None:
        record = _initial_state(report, release)
    else:
        need(record["boot_id"] == report["target_boot_id"],
             "BOOT_CHANGED_MANUAL_REVIEW")
    return record, report


def run(operation: str) -> dict:
    need(operation in ("download", "test", "restore"), "OPERATION_NOT_ALLOWLISTED")
    trusted_local()
    release = read_approved_release()
    port = guard.RootZ2TargetPort(release=release)
    with port.exclusive():
        record, current = _confirm_current(port, release,
                                           read_state(release), operation)
        if operation == "download":
            record.update(status="DOWNLOAD_IN_FLIGHT", last_error="")
            write_state(record)
            try:
                one_shot.manager_write(release.firmware_name)
                after = live_report(port, release, release.firmware_name)
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
                one_shot.protected(CHILD)
                CHILD.unlink()
            record.update(status="TEST_IN_FLIGHT", last_error="")
            write_state(record)
            try:
                one_shot.run_child([sys.executable, "-m",
                                    "pl.hil.fpga_image_root", "--identity-child"])
                result = json.loads(CHILD.read_text())
                need(type(result) is dict and
                     result == {"observed": {str(k): v for k, v in
                                             sorted(_expected_identity(release).items())}},
                     "IDENTITY_CHILD_RECEIPT_DENIED")
                after = live_report(port, release, release.firmware_name)
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
            one_shot.manager_write(release.recovery_name)
            after = live_report(port, release, release.recovery_name)
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


def _expected_identity(release: ApprovedImage) -> dict[int, int]:
    return {offset: expected for offset, expected, mask in release.identity_words}


def identity_child() -> int:
    trusted_local()
    release = read_approved_release()
    state = read_state(release)
    need(state is not None and state["status"] == "TEST_IN_FLIGHT" and
         state["image"] == release.firmware_name and not CHILD.exists(),
         "IDENTITY_CHILD_NOT_CLAIMED")
    need(state["boot_id"] ==
         (guard.PROC / "sys/kernel/random/boot_id").read_text().strip() and
         ": writing " + release.firmware_name + " to " in
         one_shot.manager_last_load(), "IDENTITY_IMAGE_NOT_CURRENT")
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
    one_shot.record_json(CHILD, {"observed": observed})
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
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
