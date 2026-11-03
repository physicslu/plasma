#!/usr/bin/env python3
"""Path 2 source-pinned, read-only Z2 independent SWD ABI-v5 preflight.

Uses the EXISTING enrolled SSH/host-key helper and Bootstrap identity probe.
Does not open /dev/mem or /dev/uio, load PL, install source, touch SWD pins,
run OpenOCD, reset/power DUT, or infer permission from a covering UIO node.
Actual Root G1-G6 and electrical admission remain separate guarded operations.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")
DEVICE_ID = re.compile(r"ppu-device-[0-9a-f]{16,64}\Z")
PREFIX = "PLASMA_SWD5_READONLY_FACTS="

# Fixed, reviewed remote program. It uses only the standard library, reads
# sysfs/proc/firmware metadata, and emits a bounded allowlisted JSON receipt.
# It deliberately does not use arbitrary commands or touch AXI addresses.
REMOTE_READ_ONLY = r'''
import hashlib, json, os, re, subprocess
from pathlib import Path

S1, S2 = 0x43C01000, 0x43C02000
def overlap(base, size):
    return size > 0 and base < S2 + 0x1000 and base + size > S1
def file_text(path):
    try:
        return Path(path).read_text().strip()[:128]
    except (OSError, UnicodeError):
        return "UNAVAILABLE"
def firmware_sha(name):
    path = Path('/lib/firmware') / name
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_size > 16000000 or info.st_size <= 0:
            return "NOT_STAGED"
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1048576), b''):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return "NOT_STAGED"
def overlaps():
    found = []
    for item in sorted(Path('/sys/class/uio').glob('uio*')):
        if not re.fullmatch('uio[0-9]+', item.name):
            continue
        try:
            maps = []
            for entry in sorted((item / 'maps').glob('map*')):
                base = int((entry / 'addr').read_text().strip(), 0)
                size = int((entry / 'size').read_text().strip(), 0)
                maps.append([base, size])
            if not any(overlap(a, n) for a, n in maps):
                continue
            node = (item / 'device').resolve(strict=True)
            driver = (node / 'driver').resolve(strict=True).name
            found.append({'uio': item.name, 'platform_node': node.name,
                          'driver': driver, 'maps': maps,
                          'runtime': file_text(node / 'power/runtime_status')})
        except (OSError, ValueError):
            found.append({'uio': item.name, 'status': 'INCOMPLETE'})
    return found
def platform():
    found = []
    root = Path('/sys/bus/platform/devices')
    try:
        devices = sorted(root.iterdir())
    except OSError:
        return [{'status': 'INCOMPLETE'}]
    for node in devices:
        try:
            if not (node / 'driver').exists():
                continue
            address = re.match(r'^([0-9a-fA-F]+)\.', node.name)
            hit = bool(address and overlap(int(address.group(1), 16), 1))
            resource = node / 'resource'
            if resource.exists():
                for line in resource.read_text().splitlines():
                    lo, hi, flags = (int(x, 16) for x in line.split())
                    hit = hit or (bool(flags & 0x200) and overlap(lo, hi - lo + 1))
            if hit:
                found.append(node.name)
        except (OSError, ValueError):
            return [{'status': 'INCOMPLETE'}]
    return found
def last_firmware():
    try:
        lines = subprocess.run(['dmesg', '--color=never'], timeout=6,
                               capture_output=True, check=True, text=True).stdout
        found = re.findall(r'fpga_manager fpga0: writing ([A-Za-z0-9_.-]+) to ', lines)
        return found[-1] if found else 'UNAVAILABLE'
    except (OSError, subprocess.SubprocessError):
        return 'UNAVAILABLE'
result = {
    'schema': 'plasma.swd5.z2-readonly-facts.v1',
    'uid_root': os.geteuid() == 0,
    'board_compatible': b'xlnx,zynq-7000' in Path('/proc/device-tree/compatible').read_bytes().split(b'\0'),
    'boot_id_present': bool(re.fullmatch(r'[0-9a-f-]{36}',
                            file_text('/proc/sys/kernel/random/boot_id'))),
    'manager_state': file_text('/sys/class/fpga_manager/fpga0/state'),
    'manager_last_firmware': last_firmware(),
    'uio_overlaps': overlaps(), 'platform_overlaps': platform(),
    'candidate_sha256': firmware_sha('plasma-swd-independent-d0add58c.bin'),
    'golden_sha256': firmware_sha('base.bin'),
    'root_source_commit': file_text('/root/plasma-path2-approved/.plasma-path2-source-commit'),
    'native_python_present': Path('/opt/plasma/python/3.12.13/bin/python3').is_file(),
    'proc_consumer_census': 'NOT_RUN_ROOT_G5_REQUIRED',
    'axi_mmio': 'NOT_RUN', 'fpga_load': 'NOT_RUN', 'site_identity': 'NOT_RUN',
    'bluepill_dpidr': 'NOT_RUN', 'electrical_qualification': 'NOT_RUN',
}
print('PLASMA_SWD5_READONLY_FACTS=' + json.dumps(result, sort_keys=True, separators=(',', ':')))
'''


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("REVIEWED_HELPER_MISSING")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_only_preflight(*, host: str, device_id: str, source_sha: str,
                        common=None, ssh=None) -> dict:
    if not SOURCE_SHA.fullmatch(source_sha) or not DEVICE_ID.fullmatch(device_id):
        raise RuntimeError("WORK_ORDER_PIN_INVALID")
    if common is None:
        common = _module(ROOT / "scripts/ppu_path2_hardware_baseline.py",
                         "swd5_existing_hardware_baseline")
    common._private_ipv4(host)
    status = common.probe_status(host)
    if status.get("device_id_observed") != device_id:
        raise RuntimeError("ENROLLED_Z2_DEVICE_ID_MISMATCH")
    if ssh is None:
        ssh = _module(ROOT / "scripts/plasma_wordport_program.py",
                      "swd5_existing_pinned_z2_ssh")
    credentials, hosts = ssh.z2_login_credentials(Path.home())
    if credentials.get("ssh_host") != host:
        raise RuntimeError("ENROLLED_Z2_SSH_HOST_MISMATCH")
    rc, transcript = ssh.password_ssh_z2(
        ["python3", "-I", "-c", REMOTE_READ_ONLY],
        credentials, hosts, timeout=45)
    if rc != 0:
        raise RuntimeError("READ_ONLY_Z2_SSH_DENIED")
    # Never print or persist the transcript, even if parsing fails; it may
    # contain private environment or authentication material.
    matches = re.findall(r"PLASMA_SWD5_READONLY_FACTS=(\{[^\r\n]*\})", transcript)
    if len(matches) != 1 or len(matches[0]) > 16000:
        raise RuntimeError("READ_ONLY_Z2_RECEIPT_INVALID")
    try:
        facts = json.loads(matches[0])
    except ValueError:
        raise RuntimeError("READ_ONLY_Z2_RECEIPT_INVALID") from None
    required = {"schema", "uid_root", "board_compatible", "boot_id_present",
                "manager_state", "manager_last_firmware", "uio_overlaps",
                "platform_overlaps", "candidate_sha256", "golden_sha256",
                "root_source_commit", "native_python_present",
                "proc_consumer_census", "axi_mmio", "fpga_load",
                "site_identity", "bluepill_dpidr", "electrical_qualification"}
    if (type(facts) is not dict or set(facts) != required or
            facts["schema"] != "plasma.swd5.z2-readonly-facts.v1" or
            facts["uid_root"] is not True or
            facts["board_compatible"] is not True or
            facts["boot_id_present"] is not True or
            type(facts["uio_overlaps"]) is not list or
            type(facts["platform_overlaps"]) is not list or
            any(facts[x] != "NOT_RUN" for x in
                ("axi_mmio", "fpga_load", "site_identity",
                 "bluepill_dpidr", "electrical_qualification")) or
            facts["proc_consumer_census"] != "NOT_RUN_ROOT_G5_REQUIRED"):
        raise RuntimeError("READ_ONLY_Z2_RECEIPT_INVALID")
    return {"schema": "plasma.swd5.path2-preflight.v1",
            "source_sha": source_sha, "device_id": device_id,
            "status": "PASS_READ_ONLY_FACTS_ONLY",
            "owner_admission": "NOT_VERIFIED",
            "physical_identity": "NOT_RUN", "dpidr": "NOT_RUN",
            "facts": facts}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    try:
        actual = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True, check=True,
                                timeout=5).stdout.strip()
        if actual != args.source_sha:
            raise RuntimeError("EXACT_PR_HEAD_MISMATCH")
        report = read_only_preflight(host=args.host, device_id=args.device_id,
                                     source_sha=args.source_sha)
        exit_code = 0
    except Exception as exc:
        code = (str(exc) if isinstance(exc, RuntimeError) and str(exc) in {
            "EXACT_PR_HEAD_MISMATCH", "WORK_ORDER_PIN_INVALID",
            "ENROLLED_Z2_DEVICE_ID_MISMATCH", "ENROLLED_Z2_SSH_HOST_MISMATCH",
            "READ_ONLY_Z2_SSH_DENIED", "READ_ONLY_Z2_RECEIPT_INVALID",
            "REVIEWED_HELPER_MISSING"} else type(exc).__name__)
        report = {"schema": "plasma.swd5.path2-preflight.v1",
                  "status": "NOT_RUN", "reason": code,
                  "physical_identity": "NOT_RUN", "dpidr": "NOT_RUN"}
        exit_code = 69
    print("PLASMA_SWD5_PATH2_PREFLIGHT=" +
          json.dumps(report, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
