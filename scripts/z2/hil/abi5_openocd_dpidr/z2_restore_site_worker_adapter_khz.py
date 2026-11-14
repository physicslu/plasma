#!/usr/bin/env python3
"""Owner-authorized one-shot recovery of Site Worker SWD adapter speed.

Run only on enrolled Z2 as root via existing pinned SSH/sudo helper.
Uses native Runtime Job-admission gate. Never touches DUT or FPGA load.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

SELECTION = pathlib.Path("/etc/plasma/site-worker-engine.json")
ENGINE_CLI = pathlib.Path("/opt/plasma/bootstrap/ppu_site_engine.py")
EXPECTED_ENGINE = "0.12.0-5088db4c9154-plasma-swd-b8a7db670649-3f5d5feca058"
EXPECTED_SHA = "b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
EXPECTED_ADMISSION_SHA = "3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"

def fail(code):
    print(json.dumps({"result": "REFUSED", "reason": code}, sort_keys=True))
    return 1

def run():
    if not SELECTION.is_file() or SELECTION.is_symlink():
        return fail("SELECTION_UNTRUSTED")
    if not ENGINE_CLI.is_file() or ENGINE_CLI.is_symlink():
        return fail("ENGINE_CLI_UNTRUSTED")
    before_bytes = SELECTION.read_bytes()
    before = json.loads(before_bytes)
    runtime = pathlib.Path(before["openocd_root"]).name
    if (runtime != EXPECTED_ENGINE or before.get("schema") != "plasma.ppu.site-worker-engine.v1"
            or before.get("adapter_driver") != "plasma_swd" or before.get("driver_abi") != 5
            or before.get("openocd_sha256") != EXPECTED_SHA
            or before.get("admission_sha256") != EXPECTED_ADMISSION_SHA):
        return fail("ENGINE_IDENTITY_MISMATCH")
    if before.get("adapter_khz") not in (2000, 5000):
        return fail("UNEXPECTED_SELECTED_SPEED")
    if pathlib.Path("/run/plasma-z2-swd05/swd-site1-admission").exists():
        return fail("SITE1_ADMISSION_EXISTS")
    p = subprocess.run(["pgrep", "-x", "openocd"], capture_output=True, text=True, timeout=5)
    if p.returncode != 1:
        return fail("OPENOCD_ACTIVE_OR_UNKNOWN")
    s = subprocess.run(["systemctl", "is-active", "plasma-site-worker.service"],
                       capture_output=True, text=True, timeout=5)
    if s.returncode != 0 or s.stdout.strip() != "active":
        return fail("SITE_WORKER_NOT_ACTIVE")
    if before["adapter_khz"] == 5000:
        cmd = [sys.executable, "-I", "-B", str(ENGINE_CLI), "select", runtime,
               "--adapter-khz", "2000", "--restart"]
        changed = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        if changed.returncode != 0:
            return fail("NATIVE_SELECT_OR_RESTART_FAILED")
    after_bytes = SELECTION.read_bytes()
    after = json.loads(after_bytes)
    if (after.get("adapter_khz") != 2000 or
            {k:v for k,v in after.items() if k != "adapter_khz"} !=
            {k:v for k,v in before.items() if k != "adapter_khz"}):
        return fail("POST_SELECTION_MISMATCH")
    h = subprocess.run(["systemctl", "is-active", "plasma-site-worker.service"],
                       capture_output=True, text=True, timeout=5)
    if h.returncode != 0 or h.stdout.strip() != "active":
        return fail("POST_WORKER_UNHEALTHY")
    p2 = subprocess.run(["pgrep", "-x", "openocd"], capture_output=True, text=True, timeout=5)
    if p2.returncode != 1:
        return fail("POST_OPENOCD_NOT_IDLE")
    print(json.dumps({
        "result": "RESTORED_VERIFIED" if before["adapter_khz"] == 5000 else "ALREADY_2000_VERIFIED",
        "selected_adapter_khz_before": before["adapter_khz"],
        "selected_adapter_khz_after": after["adapter_khz"],
        "engine_runtime_id": runtime,
        "selection_sha256_before": hashlib.sha256(before_bytes).hexdigest(),
        "selection_sha256_after": hashlib.sha256(after_bytes).hexdigest(),
        "site_worker": "active", "openocd": "absent",
        "flash_operations": 0,
        "restart_performed": before["adapter_khz"] == 5000,
    }, sort_keys=True))
    return 0

try:
    sys.exit(run())
except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
    sys.exit(fail("RECOVERY_EXCEPTION_" + type(exc).__name__.upper()))
