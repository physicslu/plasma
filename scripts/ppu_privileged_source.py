#!/usr/bin/env python3
"""Verify the factory-provisioned, immutable privileged FPGA code closure.

Unlike the retired Path 2 Git-commit pin, this verifies the precise,
root-owned installed code bytes. It is a provenance/integrity gate, NOT
Bundle authority, FPGA hardware permission, or hardware qualification.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

CODE_ROOT = Path("/opt/plasma/privileged/fpga-root")
MANIFEST = ".plasma-privileged-code.json"
SCHEMA = "plasma.ppu.privileged-code.v1"
CODE_FILES = frozenset({
    "pl/hil/fpga_image_root.py",
    "pl/hil/fpga_image_guard.py",
    "pl/hil/fpga_image_admission.py",
    "software/python/plasma_interfaces/__init__.py",
    "software/python/plasma_interfaces/linux_mmio.py",
})
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class PrivilegedSourceDenied(RuntimeError):
    pass


def require(ok: bool, code: str) -> None:
    if not ok:
        raise PrivilegedSourceDenied(code)


def _trusted(path: Path, *, uid: int, directory: bool) -> None:
    st = path.lstat()
    require((stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode))
            and st.st_uid == uid and st.st_mode & 0o022 == 0
            and (directory or st.st_nlink == 1),
            "PRIVILEGED_CODE_OWNERSHIP_DENIED")


def _parent_chain(root: Path, uid: int) -> None:
    require(root.is_absolute() and ".." not in root.parts,
            "PRIVILEGED_CODE_ROOT_INVALID")
    for p in (*reversed(root.parents), root):
        _trusted(p, uid=uid, directory=True)


def verify_source(root: Path = CODE_ROOT, *, expected_uid: int = 0) -> dict:
    """Fail closed on substitutions, unchecked imports or writable ancestors.

    expected_uid override is for isolated Host-only test fixtures; production
    Root Entry always calls the CLI with expected_uid=0 and a fixed root.
    """
    _parent_chain(root, expected_uid)
    manifest_file = root / MANIFEST
    try:
        _trusted(manifest_file, uid=expected_uid, directory=False)
    except FileNotFoundError as exc:
        raise PrivilegedSourceDenied("PRIVILEGED_CODE_MANIFEST_MISSING") from exc
    try:
        raw = manifest_file.read_bytes()
        require(len(raw) <= 16384, "PRIVILEGED_CODE_MANIFEST_INVALID")
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise PrivilegedSourceDenied("PRIVILEGED_CODE_MANIFEST_INVALID") from exc
    require(type(data) is dict and set(data) == {"schema", "files"}
            and data["schema"] == SCHEMA and type(data["files"]) is dict
            and set(data["files"]) == CODE_FILES
            and all(type(v) is str and HEX64.fullmatch(v)
                    for v in data["files"].values()),
            "PRIVILEGED_CODE_MANIFEST_INVALID")

    # The whole installed Python import closure is pinned, not just the
    # entry module. No unlisted .py, .pyc, symlink, or special file is accepted.
    observed = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        _trusted(parent, uid=expected_uid, directory=True)
        for name in dirs:
            _trusted(parent / name, uid=expected_uid, directory=True)
        for name in files:
            src = parent / name
            _trusted(src, uid=expected_uid, directory=False)
            relative = src.relative_to(root).as_posix()
            require(relative in CODE_FILES or relative == MANIFEST,
                    "PRIVILEGED_CODE_EXTRA_FILE_DENIED")
            observed.add(relative)
            if relative == MANIFEST:
                continue
            require(hashlib.sha256(src.read_bytes()).hexdigest() ==
                    data["files"][relative],
                    "PRIVILEGED_CODE_HASH_MISMATCH")
    require(observed == CODE_FILES | {MANIFEST},
            "PRIVILEGED_CODE_INVENTORY_MISMATCH")
    return {
        "schema": SCHEMA, "status": "VERIFIED_NOT_EXECUTED",
        "code_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "code_files": len(CODE_FILES),
        "source_commit_pin": "RETIRED",
        "fpga_loaded": False,
    }


def main(argv: list[str]) -> int:
    # No user-provided path, UID, file, executable or package command.
    if argv:
        print("PRIVILEGED_CODE_ARGUMENT_DENIED", file=sys.stderr)
        return 2
    if os.geteuid() != 0:
        print("PRIVILEGED_CODE_ROOT_REQUIRED", file=sys.stderr)
        return 2
    try:
        receipt = verify_source()
    except (PrivilegedSourceDenied, OSError) as exc:
        print(type(exc).__name__ + ":" + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
