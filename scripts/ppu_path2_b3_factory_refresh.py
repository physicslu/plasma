#!/usr/bin/env python3
"""Minimal real Z2 B3 software refresh via EXISTING Factory Bootstrap Installer.

The existing, previously qualified Z2 factory/network/device/credential baseline
is preserved. This only deploys the exact reviewed PR's scripts, an exact
source/SHA factory B3 policy and restarts the existing Bootstrap unit.
No B1/B2 qualification rerun, B3 installation, service unit rewriting,
new credential, Runtime/FPGA/DUT operation, or second installer.

Invoke ONLY as an owner-approved, exact-PR-HEAD Path 2 operator-cli work order.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import pty
import re
import select
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import termios
import time
import tty
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
DEVICE_ID = re.compile(r"ppu-device-[0-9a-f]{16,64}\Z")
REMOTE_STAGING = re.compile(r"/tmp/plasma-b3-refresh-[0-9a-f]{12}-[A-Za-z0-9]{8}\Z")
FACTORY_SCRIPTS = (
    "ppu-bootstrap.py",
    "ppu-bootstrap-service.py",
    "ppu-bootstrap-deployment.py",
    "ppu-bootstrap-kit.py",
    "ppu_unified_deployment.py",
    "ppu-z2-installer.py",
    "ppu-z2-installer-core.py",
    "ppu-bootstrap-installer.py",
)
TARGET = {
    "platform": "linux-armv7",
    "board": "pynq-z2",
    "fpga_part": "xc7z020clg400-1",
}
# Explicit source manifest allowlist. Never execute an uploaded arbitrary script.
ALLOWED_FILES = frozenset(
    {"manifest.json", "SHA256SUMS", "artifacts/ppu-b3-smoke.zip"}
    | {f"scripts/{name}" for name in FACTORY_SCRIPTS}
    | {"scripts/ppu-b3-smoke-policy.json"}
)

# Small remote verifier; only writes under a newly created private staging dir.
# Actual privileged software updates remain in the original Factory Installer.
REMOTE_VERIFY_EXTRACT = """
import hashlib, json, os, pathlib, re, stat, sys, tarfile
archive, destination, sha, expected_digest = sys.argv[1:]
allowed = set(json.loads(sys.argv[5]))
root = pathlib.Path(destination)
if root.exists() or not re.fullmatch(r"/tmp/plasma-b3-refresh-[0-9a-f]{12}-[A-Za-z0-9]{8}/extracted",destination):
    raise SystemExit("B3_REMOTE_STAGE_DESTINATION_DENIED")
root.mkdir(mode=0o700)
files = set()
total = 0
with tarfile.open(archive, "r:gz") as data:
    for member in data.getmembers():
        if not member.isfile() or member.name not in allowed or member.name in files:
            raise SystemExit("B3_REMOTE_STAGE_MEMBER_DENIED")
        if member.size > 2000000:
            raise SystemExit("B3_REMOTE_STAGE_SIZE_DENIED")
        total += member.size
        if total > 4000000:
            raise SystemExit("B3_REMOTE_STAGE_TOTAL_SIZE_DENIED")
        files.add(member.name)
        path = root.joinpath(*member.name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        content = data.extractfile(member)
        if content is None:
            raise SystemExit("B3_REMOTE_STAGE_CONTENT_INVALID")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os,"O_NOFOLLOW",0)
        fd = os.open(path, flags, 0o600)
        with content, os.fdopen(fd,"wb") as out:
            while True:
                chunk = content.read(65536)
                if not chunk:
                    break
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
if files != allowed:
    raise SystemExit("B3_REMOTE_STAGE_INCOMPLETE")
checks = {}
for line in (root/"SHA256SUMS").read_text().splitlines():
    a = line.split("  ",1)
    if len(a)!=2 or not re.fullmatch("[0-9a-f]{64}",a[0]) or a[1] in checks:
        raise SystemExit("B3_SOURCE_SUMS_INVALID")
    checks[a[1]]=a[0]
if set(checks)!=allowed-{"SHA256SUMS"}:
    raise SystemExit("B3_SOURCE_SUMS_SET_DENIED")
for name,digest in checks.items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
        raise SystemExit("B3_SOURCE_SHA256_MISMATCH")
manifest=json.loads((root/"manifest.json").read_text())
policy=json.loads((root/"scripts/ppu-b3-smoke-policy.json").read_text())
if (manifest.get("source_commit")!=sha or
    policy.get("source_commit")!=sha or
    policy.get("target")!={"platform":"linux-armv7","board":"pynq-z2","fpga_part":"xc7z020clg400-1"} or
    policy.get("archive_sha256")!=expected_digest or
    hashlib.sha256((root/"artifacts/ppu-b3-smoke.zip").read_bytes()).hexdigest()!=expected_digest):
    raise SystemExit("B3_SOURCE_POLICY_PIN_MISMATCH")
(root/"scripts/ppu-b3-smoke-policy.json").chmod(0o600)
print("B3_REMOTE_VERIFIED_SHA256_PASS")
"""


def load(name: str, script: Path):
    spec = importlib.util.spec_from_file_location(name, script)
    if spec is None or spec.loader is None:
        raise RuntimeError("B3_SOURCE_MODULE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_source_tar(archive: Path, source_sha: str) -> tuple[str, str]:
    """Exact PR checkout supplies source; Builder supplies deterministic smoke."""
    if not SHA40.fullmatch(source_sha):
        raise RuntimeError("B3_SOURCE_SHA_INVALID")
    builder = load("ppu_b3_refresh_builder", ROOT / "scripts/ppu-bundle-v3-smoke.py")
    with tempfile.TemporaryDirectory(prefix="plasma-b3-refresh-build-") as temp:
        zip_path = Path(temp) / "ppu-b3-smoke.zip"
        bundle_digest = builder.make_bundle(zip_path, source_sha)
        policy = {
            "schema": "plasma.ppu.b3-factory-policy.v1",
            "bundle_name": "ppu-b3-smoke",
            "source_commit": source_sha,
            "archive_sha256": bundle_digest,
            "target": TARGET,
            "actions": ["install", "verify"],
        }
        contents = {
            "manifest.json": (json.dumps(
                {"schema": "plasma.ppu.b3-refresh.v1", "source_commit": source_sha},
                sort_keys=True,
            ) + "\n").encode(),
            "artifacts/ppu-b3-smoke.zip": zip_path.read_bytes(),
            "scripts/ppu-b3-smoke-policy.json": (
                json.dumps(policy, sort_keys=True) + "\n"
            ).encode(),
        }
        for name in FACTORY_SCRIPTS:
            script = ROOT / "scripts" / name
            if script.is_symlink() or not script.is_file():
                raise RuntimeError("B3_SOURCE_SCRIPT_UNTRUSTED")
            contents[f"scripts/{name}"] = script.read_bytes()
        if set(contents) != ALLOWED_FILES - {"SHA256SUMS"}:
            raise RuntimeError("B3_SOURCE_FILE_SET_MISMATCH")
        contents["SHA256SUMS"] = ("".join(
            f"{sha256(data)}  {name}\n" for name, data in sorted(contents.items())
        )).encode()
        archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "w:gz") as output:
            for name, data in sorted(contents.items()):
                info = tarfile.TarInfo(name)
                info.mode = 0o600 if name.endswith("-policy.json") else 0o644
                info.size = len(data)
                info.mtime = 0
                output.addfile(info, io.BytesIO(data))
        return sha256(archive.read_bytes()), bundle_digest


def password_scp(archive: Path, remote: str, credentials: dict, known_hosts: Path,
                 *, timeout: int = 70) -> None:
    """Single-file transport, existing enrolled password + exact pinned host key.

    This transfers a reviewed source archive to PRIVATE temp staging. It is
    not another Installer and never receives the Bootstrap bearer token.
    """
    import fcntl
    if not REMOTE_STAGING.fullmatch(remote):
        raise RuntimeError("B3_REMOTE_STAGE_PATH_INVALID")
    host = credentials["ssh_host"]
    if credentials["ssh_username"] != "xilinx" or host != "192.168.2.99":
        raise RuntimeError("B3_ENROLLED_SSH_IDENTITY_DENIED")
    argv = [
        "scp", "-O", "-F", "/dev/null",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "BatchMode=no",
        "-o", "NumberOfPasswordPrompts=1",
        "-o", "PreferredAuthentications=password,keyboard-interactive",
        "-o", "PubkeyAuthentication=no",
        "-o", "ConnectTimeout=8", "-o", "ConnectionAttempts=1",
        str(archive),
        f"xilinx@{host}:{remote}/factory.tar.gz",
    ]
    master, slave = pty.openpty()
    child = None
    sent = False
    output = bytearray()
    try:
        tty.setraw(slave, termios.TCSANOW)
        def controlling_tty():
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        child = subprocess.Popen(
            argv, stdin=slave, stdout=slave, stderr=slave,
            close_fds=True, preexec_fn=controlling_tty,
        )
        os.close(slave)
        slave = -1
        deadline = time.monotonic() + timeout
        while child.poll() is None or select.select([master], [], [], 0)[0]:
            if time.monotonic() > deadline:
                raise RuntimeError("B3_SCP_TRANSPORT_TIMEOUT")
            ready, _, _ = select.select([master], [], [], 0.2)
            if not ready:
                continue
            try:
                data = os.read(master, 8192)
            except OSError:
                break
            if not data:
                break
            output.extend(data)
            if len(output) > 32768:
                del output[:-32768]
            tail = output[-1024:].decode("utf-8", "replace")
            if (not sent
                    and re.search(r"(?i)(?:password|passphrase)[^\r\n]{0,90}:\s*$", tail)):
                os.write(master, credentials["ssh_password"].encode() + b"\n")
                sent = True
        if child.wait(timeout=5) != 0:
            raise RuntimeError("B3_SCP_TRANSPORT_FAILED")
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        os.close(master)
        if slave != -1:
            os.close(slave)


def remote(helper, credentials, known_hosts, command: list[str], *, timeout=90) -> str:
    rc, output = helper.password_ssh_z2(
        command, credentials, known_hosts, timeout=timeout
    )
    if rc != 0:
        # Never display private SSH output, credential prompts or command
        # payloads in GitHub Actions, even when remote execution fails.
        raise RuntimeError("B3_REMOTE_OPERATION_FAILED")
    return output


def run(host: str, device_id: str, sha: str) -> dict:
    evidence = {
        "schema": "plasma.ppu.b3-factory-refresh-path2.v1",
        "source_commit": sha, "expected_device_id": device_id,
        "result": "BLOCKED", "b3_factory_refresh": "NOT_RUN",
        "b1": "NOT_RUN", "b2": "NOT_RUN", "b3": "NOT_RUN",
        "fpga": "NOT_RUN", "dut": "NOT_RUN",
    }
    common = load("ppu_b3_refresh_common", ROOT / "scripts/ppu_path2_hardware_baseline.py")
    helper = load("ppu_b3_refresh_existing_ssh", ROOT / "scripts/plasma_wordport_program.py")
    common._private_ipv4(host)
    if common.probe_status(host).get("device_id_observed") != device_id:
        evidence["reason"] = "B3_PINNED_DEVICE_ID_MISMATCH"
        return evidence
    credentials, known_hosts = helper.z2_login_credentials(Path.home())
    if credentials["ssh_host"] != host or credentials["ssh_username"] != "xilinx":
        evidence["reason"] = "B3_ENROLLED_SSH_HOST_DENIED"
        return evidence
    token = common._existing_bootstrap_token_via_z2_ssh(host, helper=helper)
    client = common.DirectSSHAuthenticatedBootstrap(
        host, module=common._load_client(), token=token,
    )
    before = client.status()
    if (before.get("identity", {}).get("device_id") != device_id
            or before.get("bootstrap", {}).get("state") != "bootstrap_ready"):
        evidence["reason"] = "B3_BOOTSTRAP_NOT_READY"
        return evidence
    if (before.get("runtime", {}).get("state") == "recovery_required"
            or isinstance(before.get("deployment"), dict)
            and before["deployment"].get("state") in (
                "queued", "running", "recovery_required"
            )):
        evidence["reason"] = "B3_ACTIVE_OR_RECOVERY_DEPLOYMENT"
        return evidence
    with tempfile.TemporaryDirectory(prefix="plasma-b3-refresh-") as temp:
        archive = Path(temp) / "factory.tar.gz"
        archive_digest, bundle_digest = make_source_tar(archive, sha)
        evidence["bundle_sha256"] = bundle_digest
        evidence["transfer_sha256"] = archive_digest
        capabilities = before.get("capabilities", {})
        if (capabilities.get("bundle_v3_b3_install") is True
                and capabilities.get("bundle_v3_b3_source_commit") == sha
                and capabilities.get("bundle_v3_b3_archive_sha256") == bundle_digest):
            evidence["result"] = "PASS"
            evidence["b3_factory_refresh"] = "ALREADY_CURRENT"
            return evidence
        # Existing SSH is used only to carry the exact source into a unique
        # private temp dir. Existing Factory Installer performs the real update.
        stage = remote(helper, credentials, known_hosts, [
            "runuser", "-u", "xilinx", "--", "mktemp", "-d",
            f"/tmp/plasma-b3-refresh-{sha[:12]}-XXXXXXXX",
        ], timeout=30).strip()
        if not REMOTE_STAGING.fullmatch(stage):
            evidence["reason"] = "B3_REMOTE_STAGE_RESPONSE_INVALID"
            return evidence
        try:
            password_scp(archive, stage, credentials, known_hosts)
            digest_line = remote(helper, credentials, known_hosts, [
                "sha256sum", stage + "/factory.tar.gz",
            ], timeout=30)
            if not digest_line.strip().startswith(archive_digest + "  "):
                evidence["reason"] = "B3_REMOTE_ARCHIVE_SHA256_MISMATCH"
                return evidence
            extracted = stage + "/extracted"
            checked = remote(helper, credentials, known_hosts, [
                "python3", "-I", "-c", REMOTE_VERIFY_EXTRACT,
                stage + "/factory.tar.gz", extracted, sha, bundle_digest,
                json.dumps(sorted(ALLOWED_FILES), separators=(",", ":")),
            ], timeout=90)
            if "B3_REMOTE_VERIFIED_SHA256_PASS" not in checked:
                evidence["reason"] = "B3_REMOTE_STAGE_VERIFICATION_FAILED"
                return evidence
            evidence["source_staging"] = "SHA256_VERIFIED"
            refresh_result = remote(helper, credentials, known_hosts, [
                "python3", "-I",
                extracted + "/scripts/ppu-bootstrap-installer.py",
                "--source-root", extracted + "/scripts",
                "--host", host, "--port", "18081",
                "--refresh-only",
            ], timeout=120)
            if ('"operation": "refresh_only"' not in refresh_result
                    or '"result": "PASS"' not in refresh_result):
                evidence["reason"] = "B3_FACTORY_REFRESH_RECEIPT_INVALID"
                return evidence
            evidence["b3_factory_refresh"] = "SCRIPTS_UPDATED"
            remote(helper, credentials, known_hosts, [
                "systemctl", "restart", "plasma-bootstrap.service",
            ], timeout=55)
            evidence["b3_factory_refresh"] = "SERVICE_RESTARTED"
            # Bounded read-only verification; never rotate a token or update
            # the authoritative Z2 profile based on a remote Manifest.
            for _ in range(10):
                try:
                    now = client.status()
                except Exception:
                    time.sleep(1)
                    continue
                c = now.get("capabilities", {})
                if (now.get("identity", {}).get("device_id") == device_id
                        and now.get("bootstrap", {}).get("state") == "bootstrap_ready"
                        and c.get("bundle_v3_b3_install") is True
                        and c.get("bundle_v3_b3_source_commit") == sha
                        and c.get("bundle_v3_b3_archive_sha256") == bundle_digest):
                    evidence["result"] = "PASS"
                    evidence["b3_factory_refresh"] = "VERIFIED"
                    return evidence
                time.sleep(1)
            evidence["reason"] = "B3_REFRESH_STATUS_NOT_VERIFIED"
            return evidence
        finally:
            # A failed refresh retains its private staging/evidence for
            # recovery; no deletion or unapproved rollback of Z2 files.
            pass
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    result = {
        "schema": "plasma.ppu.b3-factory-refresh-path2.v1",
        "source_commit": args.source_sha,
        "expected_device_id": args.device_id,
        "result": "BLOCKED", "b3_factory_refresh": "NOT_RUN",
        "b1": "NOT_RUN", "b2": "NOT_RUN", "b3": "NOT_RUN",
        "fpga": "NOT_RUN", "dut": "NOT_RUN",
    }
    try:
        git = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if not SHA40.fullmatch(args.source_sha) or git != args.source_sha:
            raise RuntimeError("B3_EXACT_SOURCE_SHA_DENIED")
        if not DEVICE_ID.fullmatch(args.device_id):
            raise RuntimeError("B3_DEVICE_ID_DENIED")
        result = run(args.host, args.device_id, args.source_sha)
    except Exception as exc:
        result["reason"] = (
            str(exc) if type(exc) is RuntimeError and str(exc).startswith("B3_")
            else type(exc).__name__
        )
    print("PLASMA_PPU_B3_FACTORY_REFRESH_JSON=" + json.dumps(
        result, sort_keys=True, separators=(",", ":")
    ))
    return 0 if result.get("result") == "PASS" else 69


if __name__ == "__main__":
    raise SystemExit(main())
