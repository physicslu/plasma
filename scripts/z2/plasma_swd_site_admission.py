"""Root-only ABI-v5 Site admission record for PS-local OpenOCD ``plasma_swd``.

Runs on Z2 as root with the native ARMv7 Python 3.12.13. It grants nothing by
itself: it re-runs the *protected, source-pinned* Root G5 live admission
(``pl.hil.fpga_image_root.live_report`` with ``require_mmio=True``) while
holding the Root reload fence, and only then writes a short-lived,
root-private ``key=value`` record for the Runtime Site adapter. The OpenOCD
``plasma_swd`` adapter itself does not read it (it only holds the Site lock
and checks that PL holds a loaded Image).

It never loads FPGA, never writes the Root journal, never maps MMIO and never
touches the DUT. DUT voltage is neither measured nor attested here.

``axi_isolation_proven=1`` means the protected Root admission accepted the
current AXI policy (``UNPROVEN_ACCEPTED_FOR_SOURCE_BOUND_DEVELOPMENT``); the
exact policy string is emitted in the receipt and is NOT a production proof.

usage: plasma_swd_site_admission.py admit <site> | revoke <site>
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path

PROTECTED_ROOT = Path("/opt/plasma/privileged/fpga-root")
RECORD_DIR = Path("/run/plasma-z2-swd05")
RECORD_TTL_S = 300
SCHEMA = "plasma.swd.ps-admission.v3"
AXI_POLICY = "UNPROVEN_ACCEPTED_FOR_SOURCE_BOUND_DEVELOPMENT"


class SiteAdmissionDenied(RuntimeError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SiteAdmissionDenied(code)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_root_file(path: Path) -> os.stat_result:
    st = os.lstat(path)
    need(path.is_absolute() and not path.is_symlink() and
         (st.st_mode & 0o170000) == 0o100000 and st.st_uid == 0 and
         st.st_mode & 0o077 == 0, "FILE_NOT_ROOT_PRIVATE:" + path.name)
    return st


def verify_protected_tree(root: Path = PROTECTED_ROOT) -> str:
    """Check fixed, Linux-root-owned installed sources, without runtime rehash.

    File SHA256 qualification belongs to the install-time provisioner.
    SWD retains code-manifest stat identity and hardware owner locks.
    """
    need(root.is_absolute() and ".." not in root.parts,
         "PRIVILEGED_CODE_ROOT_INVALID")
    def require_owned(path: Path, directory: bool) -> os.stat_result:
        info = path.lstat()
        need((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
             and info.st_uid == 0 and info.st_mode & 0o022 == 0,
             "PRIVILEGED_CODE_SOURCE_UNTRUSTED")
        return info

    for directory in (*reversed(root.parents), root):
        require_owned(directory, True)
    for relative in ("pl/hil/fpga_image_root.py", "pl/hil/fpga_image_guard.py",
                     "pl/hil/fpga_image_admission.py",
                     "software/python/plasma_interfaces/linux_mmio.py"):
        current = root
        for part in Path(relative).parts[:-1]:
            current = current / part
            require_owned(current, True)
        require_owned(root / relative, False)
    private = root / ".plasma-privileged-code.json"
    info = _private_root_file(private)
    need(0 < info.st_size <= 16384, "PRIVILEGED_CODE_MANIFEST_INVALID")
    return hashlib.sha256(private.read_bytes()).hexdigest()


def render_record(fields: dict) -> str:
    order = (
        "schema", "site_id", "boot_id", "trusted_code_sha256",
        "image_manifest_sha256", "loaded_image_sha256", "image_id",
        "root_image_session_id", "abi_version", "site_bitmap",
        "trusted_code_verified", "manager_operating", "active_image_attested",
        "axi_isolation_proven", "owner_scan_complete",
        "recovery_available", "journal_dev", "journal_ino", "journal_size",
        "journal_mtime_ns", "record_expires_epoch",
        "code_manifest_dev", "code_manifest_ino", "code_manifest_size",
        "code_manifest_mtime_ns")
    need(set(fields) == set(order), "RECORD_FIELDS_INCOMPLETE")
    out = []
    for key in order:
        value = str(fields[key])
        need("\n" not in value and "=" not in value and value != "",
             "RECORD_VALUE_INVALID:" + key)
        out.append(f"{key}={value}\n")
    return "".join(out)


def _write_private(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, text.encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def guard_images() -> dict:
    """Reviewed devmem Image table from the root-owned protected tree."""
    from pl.hil import fpga_image_admission as admission  # noqa: E402
    need(Path(admission.__file__).resolve() ==
         PROTECTED_ROOT / "pl/hil/fpga_image_admission.py",
         "ADMISSION_MODULE_NOT_PROTECTED")
    return admission.DEVMEM_INDEPENDENT_IMAGES


def admit(site: int) -> dict:
    need(site in (1, 2), "SITE_INVALID")
    need(os.geteuid() == 0, "ROOT_REQUIRED")
    code_sha256 = verify_protected_tree()
    source_info = _private_root_file(PROTECTED_ROOT / ".plasma-privileged-code.json")
    sys.path.insert(0, str(PROTECTED_ROOT))
    from pl.hil import fpga_image_guard as guard  # noqa: E402 (protected tree)
    from pl.hil import fpga_image_root as root  # noqa: E402
    need(Path(root.__file__).resolve() ==
         PROTECTED_ROOT / "pl/hil/fpga_image_root.py", "ROOT_MODULE_NOT_PROTECTED")
    root.trusted_local()
    release = root.read_image_manifest()
    need(guard_images().get(release.image_id) == release.firmware_sha256 and
         release.abi_version == 0x00050001 and release.site_bitmap == 3 and
         release.axi_base == 0x43C01000 and release.axi_bytes == 0x2000,
         "RELEASE_NOT_ABI5_INDEPENDENT")
    port = guard.RootZ2TargetPort(release=release)
    now = time.time()
    with port.exclusive():
        state = root.read_state(release)
        need(state is not None and state["status"] == "IMAGE" and
             state["image"] == release.firmware_name and
             state["manifest_sha256"] == root.manifest_sha256() and
             state["firmware_sha256"] == release.firmware_sha256,
             "ROOT_JOURNAL_NOT_HELD_IMAGE")
        # The protected Root journal has already proved the same-boot Image.
        # Runtime admission checks live hardware; dmesg history is not durable.
        report = root.live_site_admission_report(port, release)
        need(report["target_boot_id"] == state["boot_id"],
             "BOOT_CHANGED_MANUAL_REVIEW")
        need(report["mmio_backend"] == "devmem" and
             report["axi_isolation"] == AXI_POLICY and
             report["bin_sha256"] == release.firmware_sha256,
             "ROOT_REPORT_NOT_DEVMEM_ADMITTED")
        js = _private_root_file(root.STATE)
        record = render_record({
            "schema": SCHEMA, "site_id": site,
            "boot_id": state["boot_id"], "trusted_code_sha256": code_sha256,
            "image_manifest_sha256": state["manifest_sha256"],
            "loaded_image_sha256": state["firmware_sha256"],
            "image_id": state["image_id"],
            "root_image_session_id": state["session_id"],
            "abi_version": 5, "site_bitmap": release.site_bitmap,
            "trusted_code_verified": 1, "manager_operating": 1,
            "active_image_attested": 1, "axi_isolation_proven": 1,
            "owner_scan_complete": 1,
            "recovery_available": 1,
            "journal_dev": js.st_dev, "journal_ino": js.st_ino,
            "journal_size": js.st_size, "journal_mtime_ns": js.st_mtime_ns,
            "record_expires_epoch": int(now) + RECORD_TTL_S,
            "code_manifest_dev": source_info.st_dev,
            "code_manifest_ino": source_info.st_ino,
            "code_manifest_size": source_info.st_size,
            "code_manifest_mtime_ns": source_info.st_mtime_ns,
        })
        guard.protected(RECORD_DIR, file=False)
        target = RECORD_DIR / f"swd-site{site}-admission"
        _write_private(target, record)
    return {
        "result": "SITE_ADMISSION_RECORD_ISSUED", "site_id": site,
        "record": str(target),
        "record_sha256": hashlib.sha256(record.encode()).hexdigest(),
        "boot_id": state["boot_id"], "trusted_code_sha256": code_sha256,
        "root_image_session_id": state["session_id"],
        "image_id": state["image_id"],
        "axi_isolation_policy": report["axi_isolation"],
        "production_qualification": report["production_qualification"],
        "voltage_source": "NOT_MEASURED",
        "record_expires_epoch": int(now) + RECORD_TTL_S,
    }


def revoke(site: int) -> dict:
    need(site in (1, 2) and os.geteuid() == 0, "REVOKE_DENIED")
    target = RECORD_DIR / f"swd-site{site}-admission"
    existed = target.exists()
    if existed:
        _private_root_file(target)
        target.unlink()
    return {"result": "SITE_ADMISSION_RECORD_REVOKED", "site_id": site,
            "existed": existed}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("admit", "revoke") or argv[1] not in ("1", "2"):
        print("usage: plasma_swd_site_admission.py admit|revoke 1|2", file=sys.stderr)
        return 2
    try:
        result = (admit if argv[0] == "admit" else revoke)(int(argv[1]))
    except Exception as exc:  # report a stable denial code only
        print("PLASMA_SWD_SITE_ADMISSION=" + json.dumps(
            {"result": "DENIED", "error": type(exc).__name__,
             "code": str(exc)[:160]}, sort_keys=True))
        return 1
    print("PLASMA_SWD_SITE_ADMISSION=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
