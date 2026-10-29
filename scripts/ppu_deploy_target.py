"""Bounded Z2-side engineering-module installer, invoked by ppu-deploy.

This is transferred as reviewed Python source in an SSH command, not installed
as a privileged daemon.  No OpenOCD/FPGA/Flash operation is performed here.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path("/home/xilinx/plasma-swd-performance-20261029")
OPENOCD = Path("/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154/bin/openocd")
OPENOCD_CFG = Path("/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154/share/openocd/scripts/target/stm32f1x.cfg")
NATIVE_BRIDGE = ROOT / "libplasma_wordport_armv7.so"
NATIVE_BRIDGE_SHA = "66261cef851c9777469b393b7539c5b0f8c2b039a032f1a5b4cbf9e93460e447"
ALLOWED = frozenset({
    "scripts/plasma_wordport_program.py",
    "scripts/bluepill-wordport-session.py",
    "software/python/plasma_interfaces/native_bluepill_word_port.py",
    "software/python/plasma_interfaces/wordport_stage_monitor.py",
    "software/python/plasma_interfaces/bluepill_remote_bitbang.py",
})
OPERATORS = frozenset({"openocd", "plasma_wordport_program.py", "bluepill-wordport-session.py"})
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
HEX32 = re.compile(r"[a-f0-9]{32}\Z")
SWPC_ALLOWED = frozenset({"scripts/plasma_wordport_program.py", "scripts/plasma_ab_burn_in.py"})


class DeploymentError(Exception):
    pass


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def atomic_bytes(destination: Path, payload: bytes, mode: int = 0o644) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or any(p.is_symlink() for p in destination.parents):
        raise DeploymentError("SYMLINK_TARGET_DENIED")
    handle, name = tempfile.mkstemp(prefix=".ppu-deploy-", dir=destination.parent)
    try:
        os.fchmod(handle, mode)
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def active_hardware_owner() -> bool:
    """A conservative stop condition, not a substitute for Root Guard."""
    for device in ("/dev/mem", "/dev/uio1"):
        try:
            result = subprocess.run(["fuser", "-s", device], timeout=5,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            return True
        if result.returncode != 1:
            return True
    for item in Path("/proc").iterdir():
        if not item.name.isdecimal() or int(item.name) == os.getpid():
            continue
        try:
            args = (item / "cmdline").read_bytes().split(b"\0")
        except (OSError, PermissionError):
            continue
        # Python -I/-B wrapper flags may precede the actual script argument.
        if any(Path(arg.decode("utf-8", "replace")).name in OPERATORS for arg in args[:6] if arg):
            return True
    return False


class Target:
    def __init__(self, root: Path = ROOT, *, enforce_host: bool = True):
        self.root = root
        self.state = root / ".ppu-deploy"
        self.enforce_host = enforce_host

    def _require_safe(self) -> None:
        if not self.root.is_dir() or self.root.is_symlink():
            raise DeploymentError("REVIEWED_Z2_BUNDLE_MISSING")
        if self.state.is_symlink() or (self.state / "transactions").is_symlink():
            raise DeploymentError("DEPLOYMENT_STATE_SYMLINK_DENIED")
        if self.enforce_host:
            if os.geteuid() != 0:
                raise DeploymentError("Z2_ROOT_REQUIRED")
            if not OPENOCD.is_file() or not os.access(OPENOCD, os.X_OK) or not OPENOCD_CFG.is_file():
                raise DeploymentError("PINNED_OPENOCD_INTEGRATION_MISSING")
            if not NATIVE_BRIDGE.is_file() or digest(NATIVE_BRIDGE.read_bytes()) != NATIVE_BRIDGE_SHA:
                raise DeploymentError("PINNED_NATIVE_WORDPORT_BRIDGE_MISSING_OR_MISMATCH")
            if active_hardware_owner():
                raise DeploymentError("HARDWARE_OWNER_BUSY_OR_UNKNOWN")

    def _path(self, relative: str) -> Path:
        if relative not in ALLOWED:
            raise DeploymentError("UNAPPROVED_DEPLOYMENT_PATH")
        dest = self.root / relative
        if dest.is_symlink() or any(p.is_symlink() for p in dest.parents if p != Path("/")):
            raise DeploymentError("SYMLINK_TARGET_DENIED")
        return dest

    def current(self) -> dict | None:
        path = self.state / "current.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text())
        if (not isinstance(data, dict) or data.get("schema") != "plasma.ppu.deploy.v1" or
                not isinstance(data.get("bundle_sha256"), str) or
                not HEX64.fullmatch(data["bundle_sha256"]) or
                not isinstance(data.get("_transaction"), str) or
                not HEX32.fullmatch(data["_transaction"])):
            raise DeploymentError("DEPLOYMENT_STATE_INVALID")
        return data

    def verify(self, manifest: dict) -> dict:
        files = manifest.get("z2_files")
        swpc = manifest.get("swpc_files")
        if (manifest.get("schema") != "plasma.ppu.deploy.v1" or
                manifest.get("module") not in ("wordport", "openocd-integration", "abtest") or
                not isinstance(manifest.get("source_commit"), str) or
                not HEX40.fullmatch(manifest["source_commit"]) or
                not isinstance(files, dict) or set(files) != ALLOWED or
                not isinstance(swpc, dict) or not swpc or set(swpc) - SWPC_ALLOWED or
                any(not isinstance(value, str) or not HEX64.fullmatch(value)
                    for value in swpc.values()) or
                not isinstance(manifest.get("target_helper_sha256"), str) or
                not HEX64.fullmatch(manifest["target_helper_sha256"]) or
                not isinstance(manifest.get("bundle_sha256"), str) or
                not HEX64.fullmatch(manifest["bundle_sha256"])):
            raise DeploymentError("INVALID_MODULE_MANIFEST")
        unhashed = {key: value for key, value in manifest.items()
                    if key not in ("bundle_sha256", "_transaction")}
        if digest(json.dumps(unhashed, sort_keys=True).encode()) != manifest["bundle_sha256"]:
            raise DeploymentError("BUNDLE_MANIFEST_SHA_MISMATCH")
        for relative, expected in files.items():
            path = self._path(relative)
            if (not isinstance(expected, str) or not HEX64.fullmatch(expected) or
                    not path.is_file() or digest(path.read_bytes()) != expected):
                raise DeploymentError("Z2_FILE_SHA_MISMATCH:" + relative)
        return {"result": "PASS", "module": manifest["module"],
                "source_commit": manifest["source_commit"], "verified_files": len(files)}

    def _unpack(self, archive: bytes) -> tuple[dict, dict[str, bytes]]:
        if len(archive) > 2_000_000:
            raise DeploymentError("PACKAGE_TOO_LARGE")
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            names = package.namelist()
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise DeploymentError("PACKAGE_DUPLICATE_OR_MISSING_MANIFEST")
            manifest = json.loads(package.read("manifest.json"))
            if not isinstance(manifest, dict):
                raise DeploymentError("INVALID_MODULE_MANIFEST")
            files = manifest.get("z2_files", {})
            if (not isinstance(files, dict) or not files or set(files) - ALLOWED or
                    set(names) != set(files) | {"manifest.json"}):
                raise DeploymentError("PACKAGE_FILE_SET_MISMATCH")
            if any(package.getinfo(name).file_size > 500_000 for name in names):
                raise DeploymentError("PACKAGE_ENTRY_TOO_LARGE")
            payloads = {}
            for relative, expected in files.items():
                info = package.getinfo(relative)
                if info.file_size > 500_000:
                    raise DeploymentError("PACKAGE_FILE_TOO_LARGE")
                data = package.read(relative)
                if digest(data) != expected:
                    raise DeploymentError("PACKAGE_SHA_MISMATCH:" + relative)
                payloads[relative] = data
            return manifest, payloads

    def deploy(self, archive: bytes) -> dict:
        self._require_safe()
        manifest, payloads = self._unpack(archive)
        previous = self.current()
        if previous is not None:
            self.verify(previous)
        if previous is not None and previous.get("bundle_sha256") == manifest.get("bundle_sha256"):
            self.verify(manifest)
            return {"result": "PASS", "mode": "NO_CHANGE", "source_commit": manifest["source_commit"]}
        version = manifest.get("bundle_sha256")
        if not isinstance(version, str) or not HEX64.fullmatch(version):
            raise DeploymentError("INVALID_BUNDLE_ID")
        transaction = secrets.token_hex(16)
        backup = self.state / "transactions" / transaction
        if backup.exists():
            raise DeploymentError("TRANSACTION_NONCE_COLLISION")
        for relative in payloads:
            self._path(relative)
        backup.mkdir(parents=True, mode=0o700)
        originals = {}
        for relative in payloads:
            path = self._path(relative)
            originals[relative] = (digest(path.read_bytes()) if path.is_file() else None)
            if path.is_file():
                atomic_bytes(backup / relative, path.read_bytes(), 0o600)
        atomic_bytes(backup / "previous.json", json.dumps(previous).encode(), 0o600)
        atomic_bytes(backup / "originals.json", json.dumps(originals).encode(), 0o600)
        try:
            for relative, data in payloads.items():
                atomic_bytes(self._path(relative), data)
            self.verify(manifest)
            atomic_bytes(self.state / "current.json", json.dumps({
                **manifest, "schema": "plasma.ppu.deploy.v1", "_transaction": transaction,
            }, sort_keys=True).encode(), 0o600)
        except Exception:
            self._restore(backup, originals)
            raise
        return {"result": "PASS", "mode": "ACTIVATED", "source_commit": manifest["source_commit"],
                "previous_commit": previous.get("source_commit") if previous else None}

    def _restore(self, backup: Path, originals: dict) -> None:
        for relative, expected in originals.items():
            dest = self._path(relative)
            if expected is None:
                if dest.exists():
                    dest.unlink()
            else:
                source = backup / relative
                if not source.is_file() or digest(source.read_bytes()) != expected:
                    raise DeploymentError("BACKUP_INTEGRITY_FAIL:" + relative)
                atomic_bytes(dest, source.read_bytes())

    def rollback(self) -> dict:
        self._require_safe()
        active = self.current()
        if not active:
            raise DeploymentError("NO_DEPLOYED_VERSION")
        backup = self.state / "transactions" / active["_transaction"]
        originals = json.loads((backup / "originals.json").read_text())
        self.verify(active)
        self._restore(backup, originals)
        previous = json.loads((backup / "previous.json").read_text())
        if previous is None:
            (self.state / "current.json").unlink()
        else:
            atomic_bytes(self.state / "current.json", json.dumps(previous, sort_keys=True).encode(), 0o600)
        return {"result": "PASS", "mode": "ROLLED_BACK",
                "source_commit": previous.get("source_commit") if previous else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "verify", "deploy", "rollback"))
    parser.add_argument("--payload", default="")
    arguments = parser.parse_args(argv)
    try:
        target = Target()
        if arguments.action == "status":
            result = {"result": "PASS", "current": target.current()}
        elif arguments.action == "rollback":
            result = target.rollback()
        elif arguments.action == "deploy":
            result = target.deploy(base64.b64decode(arguments.payload, validate=True))
        else:
            manifest = json.loads(base64.b64decode(arguments.payload, validate=True))
            result = target.verify(manifest)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (DeploymentError, ValueError, OSError, KeyError, json.JSONDecodeError,
            zipfile.BadZipFile) as exc:
        print(json.dumps({"result": "NOT_RUN", "reason": str(exc)[:250]}))
        return 77


if __name__ == "__main__":
    sys.exit(main())
