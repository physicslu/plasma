#!/usr/bin/env python3
"""Trusted-main, read-only SWPC Codex native-install inventory. Never launch Codex.

Called only by the fixed, owner-pinned Path 2 Work Order in the existing
development Dispatcher. No candidate code, arbitrary argv, model or hardware.
Public receipt contains category metadata and native SHA-256, never home paths.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import struct
import subprocess

NATIVE_VERSION = "0.162.1"
NODE_VERSION = "v22.23.2"
ARCH = "x86_64-unknown-linux-musl"
MAX_NATIVE_SIZE = 128 * 1024 * 1024
MAX_MANIFEST_SIZE = 65536
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class PreflightDenied(ValueError):
    """Only constant denial identifiers may enter a public receipt."""


def require(predicate, code):
    if not predicate:
        raise PreflightDenied(code)


def owned_path(root: Path, path: Path, *, kind: str):
    """Do not follow unexpected npm/node_modules links or writable parents."""
    require(path.is_relative_to(root), "NATIVE_PATH_OUTSIDE_HOME")
    here = root
    for name in path.relative_to(root).parts:
        here = here / name
        try:
            meta = here.lstat()
        except OSError:
            raise PreflightDenied("NATIVE_PATH_UNAVAILABLE") from None
        expect_dir = here != path or kind == "dir"
        require(stat.S_ISDIR(meta.st_mode) if expect_dir
                else stat.S_ISREG(meta.st_mode),
                "NATIVE_PATH_TYPE_DENIED")
        require(meta.st_uid in (0, os.geteuid()) and
                meta.st_mode & 0o022 == 0,
                "NATIVE_PATH_PERMISSIONS_DENIED")
    return path.stat()


def manifest(root, path, expected_name):
    info = owned_path(root, path, kind="file")
    require(info.st_size <= MAX_MANIFEST_SIZE, "NATIVE_MANIFEST_TOO_LARGE")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise PreflightDenied("NATIVE_MANIFEST_INVALID") from None
    require(type(data) is dict and data.get("name") == expected_name and
            data.get("version") == NATIVE_VERSION,
            "NATIVE_MANIFEST_ID_DENIED")
    return data


def native_elf_summary(data):
    require(len(data) >= 64 and data[:6] == b"\x7fELF\x02\x01",
            "NATIVE_ELF_FORMAT_DENIED")
    etype, machine = struct.unpack_from("<HH", data, 16)
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 54)
    require(etype in (2, 3) and machine == 62 and phentsize == 56 and
            1 <= phnum <= 128 and phoff + phentsize * phnum <= len(data),
            "NATIVE_ELF_FORMAT_DENIED")
    executable = False
    interp = False
    needed = 0
    for index in range(phnum):
        kind, flags, offset, _, _, file_size, _, _ = struct.unpack_from(
            "<IIQQQQQQ", data, phoff + index * phentsize)
        if kind == 1 and flags & 1:
            require(offset + file_size <= len(data), "NATIVE_ELF_FORMAT_DENIED")
            executable = True
        if kind == 3:
            interp = True
        if kind == 2:
            require(file_size % 16 == 0 and offset + file_size <= len(data),
                    "NATIVE_ELF_FORMAT_DENIED")
            for i in range(offset, offset + file_size, 16):
                tag = struct.unpack_from("<q", data, i)[0]
                if tag == 1:
                    needed += 1
                if tag == 0:
                    break
    require(executable, "NATIVE_ELF_NONEXECUTABLE")
    return {"elf_arch": "ELF64_LE_X86_64",
            "pt_interp": "PRESENT" if interp else "ABSENT",
            "dt_needed_count": needed}


def fixed_readonly_tool(program, argv):
    """No shell, no environment inheritance, no raw stderr or path output."""
    require(program in ("/usr/bin/file", "/usr/bin/readelf"),
            "NATIVE_TOOL_DENIED")
    if not Path(program).is_file():
        return None
    try:
        completed = subprocess.run(
            [program, *argv], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            check=False, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or len(completed.stdout) > 65536:
        return None
    return completed.stdout.decode("utf-8", errors="replace")


def inspect(*, home=None, which=shutil.which):
    """Return only bounded, non-personal diagnostic metadata."""
    home = Path(home if home is not None
                else pwd.getpwuid(os.geteuid()).pw_dir)
    require(home.is_absolute() and home.is_dir() and not home.is_symlink(),
            "NATIVE_HOME_DENIED")
    prefix = home / ".nvm" / "versions" / "node" / NODE_VERSION
    entry = prefix / "bin" / "codex"
    package = prefix / "lib" / "node_modules" / "@openai" / "codex"
    wrapper = package / "bin" / "codex.js"
    require(which("codex") == str(entry) and entry.is_symlink(),
            "NATIVE_ENTRY_DENIED")
    try:
        resolved = entry.resolve(strict=True)
    except (OSError, RuntimeError):
        raise PreflightDenied("NATIVE_ENTRY_DENIED") from None
    require(resolved == wrapper, "NATIVE_ENTRY_TARGET_DENIED")
    owned_path(home, wrapper, kind="file")
    metadata = manifest(home, package / "package.json", "@openai/codex")
    require(metadata.get("bin") == {"codex": "bin/codex.js"},
            "NATIVE_ENTRY_METADATA_DENIED")
    roots = (package / "node_modules" / "@openai" / "codex-linux-x64",
             package.parent / "codex-linux-x64",
             package)
    candidates = [(root, root / "vendor" / ARCH / "bin" / "codex")
                  for root in roots]
    candidates = [(root, path) for root, path in candidates
                  if path.exists() or path.is_symlink()]
    require(len(candidates) == 1, "NATIVE_LOCATION_AMBIGUOUS")
    root, binary = candidates[0]
    if root != package:
        manifest(home, root / "package.json", "@openai/codex-linux-x64")
    info = owned_path(home, binary, kind="file")
    require(info.st_size <= MAX_NATIVE_SIZE and info.st_size >= 120 and
            info.st_mode & 0o111,
            "NATIVE_EXECUTABLE_DENIED")
    try:
        data = binary.read_bytes()
    except OSError:
        raise PreflightDenied("NATIVE_READ_DENIED") from None
    require(len(data) == info.st_size, "NATIVE_SIZE_CHANGED")
    digest = hashlib.sha256(data).hexdigest()
    require(SHA256.fullmatch(digest) is not None, "NATIVE_DIGEST_DENIED")
    elf = native_elf_summary(data)
    file_result = fixed_readonly_tool("/usr/bin/file", ["-b", str(binary)])
    ph_result = fixed_readonly_tool("/usr/bin/readelf", ["-lW", str(binary)])
    dyn_result = fixed_readonly_tool("/usr/bin/readelf", ["-dW", str(binary)])
    file_status = ("UNAVAILABLE" if file_result is None else
                   "ELF_OBSERVED" if "ELF 64-bit" in file_result else "NOT_ELF")
    # Readelf output is only classified; never return its raw stdout.
    program_header_status = ("UNAVAILABLE" if ph_result is None else
                             "OBSERVED" if "Program Headers:" in ph_result
                             else "UNEXPECTED")
    dynamic_status = ("UNAVAILABLE" if dyn_result is None else
                      "NEEDED_PRESENT" if "(NEEDED)" in dyn_result else
                      "NO_NEEDED_OBSERVED")
    return {"schema": "plasma.codex.native_preflight.v1",
            "status": ("OBSERVED" if file_result is not None and
                       ph_result is not None and dyn_result is not None
                       else "INCOMPLETE"),
            "runner": "SWPC-plasma-codex",
            "model_session": "NOT_RUN",
            "hardware_access": "NOT_RUN",
            "install_layout": "FIXED_NVM_GLOBAL_NODE_V22",
            "entry_realpath": "EXPECTED_CODEX_JS_WRAPPER",
            "package": "@openai/codex",
            "package_version": NATIVE_VERSION,
            "platform_package": ("VENDORED" if root == package
                                 else "@openai/codex-linux-x64"),
            "native_path": "FIXED_PLATFORM_VENDOR_BINARY",
            "native_regular_file": True,
            "native_owner_is_runner_or_root": True,
            "native_group_other_writable": False,
            "native_mode": format(stat.S_IMODE(info.st_mode), "04o"),
            "native_size_bytes": info.st_size,
            "native_sha256": digest,
            **elf,
            "file_status": file_status,
            "readelf_program_headers": program_header_status,
            "readelf_dynamic": dynamic_status,
            "provenance": "NOT_INDEPENDENTLY_VERIFIED",
            "sha256_pin_authorized": False}
