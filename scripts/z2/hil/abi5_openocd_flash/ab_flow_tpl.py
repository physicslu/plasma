"""Reviewed Z2 root-side Blue Pill ABI-v5 A/B HIL primitive.

The Path 2 SWPC controller replaces CONFIG_B64 before sending this file over
the existing enrolled SSH/sudo helper. No network, service, FPGA load, Root
Entry or runtime operation is performed here. Modes: status, backup, flash.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

CONFIG_B64 = "@CONFIG_B64@"
C = json.loads(base64.b64decode(CONFIG_B64))
FLASH_START = 0x08000000
FLASH_BYTES = 65536
ERASE_BYTES = 63488  # 62 x 1 KiB, preserve top two pages.
JOURNAL = Path("/var/lib/plasma-privileged/fpga-deployment-state.json")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def facts():
    journal = json.loads(JOURNAL.read_text())
    return {
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "manager": Path("/sys/class/fpga_manager/fpga0/state").read_text().strip(),
        "journal": {key: journal.get(key) for key in ("status", "image_id", "boot_id")},
        "journal_sha256": digest(JOURNAL),
        "openocd_pids": subprocess.run(["pgrep", "-x", "openocd"],
                                       capture_output=True, text=True, check=False).stdout.split(),
    }


def valid(pre):
    j = pre["journal"]
    binary = Path(C["openocd_dir"]) / "bin/openocd"
    firmware = Path(C["firmware"])
    base = (os.geteuid() == 0 and pre["manager"] == "operating"
            and not pre["openocd_pids"] and j.get("status") == "IMAGE"
            and j.get("boot_id") == pre["boot_id"]
            and j.get("image_id") == C["image_id"]
            and digest(binary) == C["openocd_sha256"]
            and C["site"] == 2 and C["speed_khz"] == 5000)
    return (base if C["mode"] == "status" else
            base and firmware.is_file() and firmware.stat().st_size == C["firmware_bytes"]
            and digest(firmware) == C["firmware_sha256"])


def part(name, command):
    return ["-c", "echo PLASMA_" + name + "_BEGIN=[clock milliseconds]",
            "-c", command,
            "-c", "echo PLASMA_" + name + "_END=[clock milliseconds]"]


def commands():
    args = ["-c", "adapter driver plasma_swd", "-c", "plasma_swd site 2",
            "-c", "transport select swd", "-c", "gdb port disabled",
            "-c", "tcl port disabled", "-c", "telnet port disabled",
            "-c", "source [find target/stm32f1x.cfg]",
            "-c", "adapter speed 5000", "-c", "init", "-c", "reset halt",
            "-c", "poll off", "-c", "flash probe 0"]
    if C["mode"] == "backup":
        args += part("BACKUP", "dump_image " + C["readback"] + " 0x08000000 65536")
        args += part("RESET", "reset run")
    else:
        args += part("ERASE", "flash erase_address 0x08000000 0xf800")
        args += part("WRITE", "flash write_image " + C["firmware"] + " 0x08000000 bin")
        args += part("VERIFY", "flash verify_image " + C["firmware"] + " 0x08000000 bin")
        args += part("READ", "dump_image " + C["readback"] + " 0x08000000 65536")
        args += part("RESET", "reset run")
    return args + ["-c", "shutdown"]


def run():
    out = {"mode": C["mode"], "attempt": C.get("attempt"),
           "version": C["version"], "firmware_sha256": C["firmware_sha256"],
           "started_unix": time.time(), "result": "FAIL"}
    pre = out["pre"] = facts()
    out["precheck"] = valid(pre)
    if not out["precheck"]:
        out["reason"] = "Z2_PREFLIGHT_MISMATCH"
        return out
    if C["mode"] == "status":
        out["result"] = "STATUS_PASS"
        return out
    rb = Path(C["readback"])
    if rb.exists():
        out["reason"] = "READBACK_ALREADY_EXISTS"
        return out
    binary = Path(C["openocd_dir"]) / "bin/openocd"
    script_dir = Path(C["openocd_dir"]) / "share/openocd/scripts"
    cmd = [str(binary), "-s", str(script_dir), "-d2"] + commands()
    started = time.monotonic()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True)
    try:
        log, _ = p.communicate(timeout=120)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        p.kill()  # only this exact child PID
        log, _ = p.communicate()
        rc = 124
    out["elapsed_s"] = round(time.monotonic() - started, 3)
    out["openocd_rc"] = rc
    log_path = Path(C["log"])
    with log_path.open("x", encoding="utf-8") as stream:
        stream.write(log)
    log_path.chmod(0o600)
    out["openocd_log_sha256"] = digest(log_path)
    out["log"] = str(log_path)
    out["clock_khz"] = [int(x) for x in re.findall(r"clock speed (\d+) kHz", log)]
    out["dpidr"] = re.findall(r"SWD DPIDR (0x[0-9a-fA-F]{8})", log)
    out["geometry_64k"] = "flash size = 64 KiB" in log
    out["device_id"] = re.findall(r"device id = (0x[0-9a-fA-F]+)", log)
    out["safe_off"] = "SAFE_OFF_MODE_OFF_VERIFIED" in log
    post = out["post"] = facts()
    out["journal_unchanged"] = post["journal_sha256"] == pre["journal_sha256"]
    out["readback_bytes"] = rb.stat().st_size if rb.is_file() else 0
    out["readback_sha256"] = digest(rb) if rb.is_file() else None
    common = (rc == 0 and out["geometry_64k"] and 5000 in out["clock_khz"]
              and "0x20036410" in [v.lower() for v in out["device_id"]]
              and out["dpidr"] and all(int(d, 16) == 0x1BA01477 for d in out["dpidr"])
              and out["safe_off"] and out["journal_unchanged"]
              and not post["openocd_pids"] and post["boot_id"] == pre["boot_id"])
    if C["mode"] == "backup":
        good = (common and out["readback_bytes"] == FLASH_BYTES
                and "PLASMA_BACKUP_END" in log and "PLASMA_RESET_END" in log)
        out["result"] = "BACKUP_PASS" if good else "FAIL"
    else:
        markers = all("PLASMA_" + n + "_END" in log for n in
                      ("ERASE", "WRITE", "VERIFY", "READ", "RESET"))
        baseline = Path(C["backup"]).read_bytes()
        expected = (Path(C["firmware"]).read_bytes()
                    + b"\xff" * (ERASE_BYTES - C["firmware_bytes"])
                    + baseline[ERASE_BYTES:])
        good = (common and markers and len(baseline) == FLASH_BYTES
                and out["readback_bytes"] == FLASH_BYTES
                and out["readback_sha256"] == hashlib.sha256(expected).hexdigest()
                and re.search(r"erased address 0x08000000 \(length 63488\)", log)
                and "wrote " + str(C["firmware_bytes"]) + " bytes" in log
                and "verified " + str(C["firmware_bytes"]) + " bytes" in log)
        out["result"] = "FLASH_PASS" if good else "FAIL"
    if out["result"] == "FAIL":
        out["reason"] = "OPENOCD_OR_READBACK_FAILURE"
    return out


try:
    result = run()
except Exception as exc:
    result = {"result": "FAIL", "reason": type(exc).__name__,
              "mode": C.get("mode"), "attempt": C.get("attempt")}
print("Z2JSON=" + json.dumps(result, sort_keys=True, separators=(",", ":")))
