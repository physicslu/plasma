#!/usr/bin/env python3
"""HIL-A2 fixed CPU-only Cortex-A9 test; live admission is owned by the shared dispatcher.

No FPGA, MMIO, UIO, resets, UART, USB, DUT, hub power, or service operations.
Offline contract tests import this module and never open a socket or invoke SSH.
"""
from __future__ import annotations

import base64
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import pty
import re
import select
import shlex
import signal
import subprocess
import sys
import termios
import time
import tty

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/hil-a15-armv7-qemu.py"
SSH_HELPER = ROOT / "scripts/plasma-codex-z2-login.py"
ARTIFACT_SHA256 = "435e8a1e14b644396a5a14b52211bb50535176448442c08b4b55aed1a0463956"
ARTIFACT_RUN = 39192248348
ARTIFACT_ID = 12160282344
BINARY_NAME = "libplasma_mmio_barrier.so"
FUNCTION = "plasma_mmio_dmb_sy"
CALLS = 1000
MARKER = "PLASMA_HIL_A2_CPU_ONLY_JSON="
MAX_RESPONSE = 16384
TIMEOUT = 90

# Constant, reviewed remote program: no dynamic Python/Issue code is inserted.
# The only transported bytes are the source-verified, pinned shared library.
REMOTE_PROGRAM = r"""
import base64,ctypes,hashlib,json,os,platform,re,sys,tempfile
from pathlib import Path
expected="435e8a1e14b644396a5a14b52211bb50535176448442c08b4b55aed1a0463956"
data=base64.b64decode(sys.argv[1],validate=True)
assert hashlib.sha256(data).hexdigest()==expected, "ELF_SHA_MISMATCH"
assert os.geteuid()!=0, "REMOTE_ROOT_DENIED"
assert platform.system()=="Linux", "NOT_LINUX"
assert platform.machine().lower() in ("armv7l","armv7"), "NOT_ARMV7"
assert sys.byteorder=="little" and ctypes.sizeof(ctypes.c_void_p)==4, "ABI_DENIED"
cpu=Path("/proc/cpuinfo").read_text(errors="replace")[:16384].lower()
assert re.search(r"cpu part\s*:\s*0x0*c09\b",cpu), "NOT_CORTEX_A9"
compatible=Path("/proc/device-tree/compatible").read_bytes()[:1024]
assert b"xlnx,zynq-7000" in compatible, "NOT_ZYNQ7000"
with tempfile.TemporaryDirectory(prefix="plasma-a2-",dir="/tmp") as scratch:
    path=Path(scratch)/"libplasma_mmio_barrier.so"
    with path.open("xb") as handle:
        handle.write(data)
    path.chmod(0o600)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
    library=ctypes.CDLL(str(path),mode=ctypes.RTLD_LOCAL)
    barrier=getattr(library,"plasma_mmio_dmb_sy")
    barrier.argtypes=[]
    barrier.restype=None
    for _ in range(1000):
        barrier()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
result={"schema":"plasma.hil.a2.z2.cpu-only.v1","status":"PASS",
        "execution_target":"ENROLLED_REAL_Z2_CORTEX_A9","os":"Linux",
        "cpu":"Cortex-A9","cpu_part":"0xc09","machine":platform.machine().lower(),
        "pointer_bits":32,"byteorder":"little","device_tree_zynq7000":True,
        "board_identity_exact":"NOT_QUALIFIED",
        "library_sha256":expected,"function":"plasma_mmio_dmb_sy",
        "calls":1000,"library_load":"PASS","temporary_cleanup":"PASS",
        "mmio_uio":"NOT_RUN","fpga_reload":"NOT_RUN",
        "dut_programming":"NOT_RUN","hub_power":"NOT_RUN","m1":"NO_GO"}
print("PLASMA_HIL_A2_CPU_ONLY_JSON="+json.dumps(result,sort_keys=True))
"""


class Denied(ValueError):
    pass


def require(test: bool, code: str) -> None:
    if not test:
        raise Denied(code)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "DEPENDENCY_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_source(artifact_dir: Path) -> bytes:
    """Reuse the upstream seven-file A1 provenance and exact SHA/ELF checks."""
    source = load_module(SOURCE, "plasma_a15_pinned_verify")
    source.check_artifact(artifact_dir)
    binary = artifact_dir / BINARY_NAME
    require(binary.is_file() and not binary.is_symlink(), "A1_ELF_FILE_DENIED")
    data = binary.read_bytes()
    require(hashlib.sha256(data).hexdigest() == ARTIFACT_SHA256, "A1_SHA_DENIED")
    require(len(data) <= 65536, "A1_ELF_SIZE_DENIED")
    return data


def verify_cpu_report(result: object) -> dict:
    """Whitelisted on-board report; no QEMU receipt can pass this contract."""
    require(type(result) is dict, "A2_REPORT_TYPE_DENIED")
    expected = {
        "schema": "plasma.hil.a2.z2.cpu-only.v1",
        "status": "PASS",
        "execution_target": "ENROLLED_REAL_Z2_CORTEX_A9",
        "os": "Linux", "cpu": "Cortex-A9", "cpu_part": "0xc09",
        "pointer_bits": 32, "byteorder": "little",
        "device_tree_zynq7000": True,
        "board_identity_exact": "NOT_QUALIFIED",
        "library_sha256": ARTIFACT_SHA256, "function": FUNCTION,
        "calls": CALLS, "library_load": "PASS", "temporary_cleanup": "PASS",
        "mmio_uio": "NOT_RUN", "fpga_reload": "NOT_RUN",
        "dut_programming": "NOT_RUN", "hub_power": "NOT_RUN", "m1": "NO_GO",
    }
    require(set(result) == set(expected) | {"machine"}, "A2_REPORT_FIELDS_DENIED")
    for key, value in expected.items():
        require(type(result[key]) is type(value) and result[key] == value,
                "A2_REPORT_" + key.upper() + "_DENIED")
    require(result["machine"] in ("armv7", "armv7l"), "A2_MACHINE_DENIED")
    return result


def ssh_argv(host: str, known_hosts: Path, data: bytes) -> list[str]:
    require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,250}", host)),
            "SSH_HOST_DENIED")
    require(len(data) <= 65536 and
            hashlib.sha256(data).hexdigest() == ARTIFACT_SHA256,
            "A1_SHA_DENIED")
    # shell argument quoting is fixed and independent of GitHub event text
    command = ("python3 -c " + shlex.quote(REMOTE_PROGRAM) + " " +
               shlex.quote(base64.b64encode(data).decode("ascii")))
    return [
        "ssh", "-T", "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=" + str(known_hosts),
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "BatchMode=no", "-o", "NumberOfPasswordPrompts=1",
        "-o", "PreferredAuthentications=password,keyboard-interactive",
        "-o", "PubkeyAuthentication=no", "-o", "ConnectTimeout=8",
        "-o", "ConnectionAttempts=1", "--", "xilinx@" + host, command,
    ]


def bounded_ssh(argv: list[str], password: str) -> dict:
    """Run the one constant SSH command; never log stdout, password, or target."""
    require(type(password) is str and bool(password), "SSH_SECRET_DENIED")
    master, slave = pty.openpty()
    tty.setraw(slave, termios.TCSANOW)

    def controlling_tty():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

    process = None
    try:
        process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave,
                                   close_fds=True, preexec_fn=controlling_tty)
        os.close(slave)
        slave = -1
        response = bytearray()
        sent = False
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            ready = select.select([master], [], [], 0.2)[0]
            if ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                response.extend(chunk)
                require(len(response) <= MAX_RESPONSE, "SSH_RESPONSE_OVERSIZED")
                if not sent and re.search(
                    r"(?i)(?:password|passphrase)[^\r\n]{0,90}:\s*$",
                    response.decode("utf-8", "replace")[-300:],
                ):
                    os.write(master, password.encode() + b"\n")
                    sent = True
            if process.poll() is not None:
                while select.select([master], [], [], 0)[0]:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    response.extend(chunk)
                    require(len(response) <= MAX_RESPONSE, "SSH_RESPONSE_OVERSIZED")
                break
        else:
            raise Denied("SSH_OR_REMOTE_TIMEOUT")
        require(process.wait(timeout=3) == 0, "SSH_OR_REMOTE_FAILED")
        lines = response.decode("utf-8", "replace").splitlines()
        matches = [line[len(MARKER):] for line in lines if line.startswith(MARKER)]
        require(len(matches) == 1, "SSH_A2_MARKER_DENIED")
        require(len(matches[0]) <= 4096, "SSH_A2_REPORT_OVERSIZED")
        return verify_cpu_report(json.loads(matches[0]))
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        if slave >= 0:
            os.close(slave)
        os.close(master)


def live_gate(work_order: dict, *, approval: dict | None = None,
              env=os.environ) -> None:
    """Fail closed unless the hosted CAS receipt matches this exact Issue event."""
    import plasma_engineering_dispatch_v1 as contracts
    require(work_order["authorization_kind"] == "hardware-one-shot" and
            work_order["capability"] == "z2-cpu-only" and
            work_order["entrypoint"] == "z2-cpu-only" and
            work_order["work_order_id"] == "hil-a2-cpu-only",
            "A2_WORK_ORDER_SCOPE_DENIED")
    require(type(approval) is dict and
            approval.get("task_id") == "hil-a2-cpu-only" and
            approval.get("execution_path") == "path2-cli" and
            approval.get("issue_number") == 981 and
            type(approval.get("comment_id")) is int and
            approval["comment_id"] > 0 and
            type(approval.get("pinned_sha")) is str and
            bool(re.fullmatch(r"[0-9a-f]{40}", approval["pinned_sha"])),
            "A2_APPROVAL_RECEIPT_INVALID")
    digest = contracts.digest(work_order)
    claim = (f"refs/heads/plasma-engineering-claims/981/"
             f"a2-{approval['comment_id']}-{digest[:16]}-r1")
    require(approval.get("work_order_sha256") == digest and
            approval.get("claim_ref") == claim,
            "A2_CLAIM_BINDING_DENIED")
    require(env.get("PLASMA_HIL_A2_CLAIM_REF") == claim and
            env.get("PLASMA_HIL_A2_WORK_ORDER_SHA256") == digest and
            env.get("GITHUB_RUN_ATTEMPT") == "1" and
            env.get("GITHUB_EVENT_NAME") == "issue_comment" and
            env.get("GITHUB_REF") == "refs/heads/main" and
            env.get("RUNNER_NAME") == "SWPC-plasma-codex" and
            env.get("RUNNER_ENVIRONMENT") == "self-hosted" and
            env.get("GITHUB_REPOSITORY") == "physicslu/plasma" and
            env.get("GITHUB_SHA") == approval["pinned_sha"] and
            os.geteuid() != 0,
            "A2_LIVE_GATE_DENIED")


def run_once(work_order: dict, artifact_dir: Path, *, approval: dict) -> dict:
    live_gate(work_order, approval=approval)
    login = load_module(SSH_HELPER, "plasma_z2_known_host_login")
    login.expect_worker()
    binary = verify_source(artifact_dir)
    enrolled = login.creds()  # root-owned? No: nonroot 0600 worker credential.
    result = bounded_ssh(
        ssh_argv(enrolled["ssh_host"], login.KNOWN_HOSTS, binary),
        enrolled["ssh_password"],
    )
    return {
        **result,
        "execution_path": "path2-cli",
        "capability": "z2-cpu-only",
        "source_run_id": ARTIFACT_RUN,
        "source_artifact_id": ARTIFACT_ID,
        "artifact_sha256_verified": True,
        "runner": "SWPC-plasma-codex",
        "github_run_id": os.environ["GITHUB_RUN_ID"],
        "reviewed_main_sha": approval["pinned_sha"],
        "work_order_sha256": approval["work_order_sha256"],
        "claim_ref": approval["claim_ref"],
        "comment_id": approval["comment_id"],
        "ssh_host_verified": True,
        "exit_code": 0,
    }


if __name__ == "__main__":
    # Prevent direct ad-hoc execution: only callable through reviewed dispatcher.
    raise SystemExit("HIL-A2 is a gated shared-dispatcher module, not a CLI entry point")
