#!/usr/bin/env python3
"""Source-pinned Path 2 Blue Pill v0.1/v0.2, 5 MHz, Site 2 A/B test.

Each invocation performs at most 20 of the owner's 100 approved attempts.
No FPGA load, driver install, Runtime/Manager switch or automatic retry.
The existing enrolled SWPC -> Z2 SSH/sudo helper runs reviewed root-side
ABI-v5 OpenOCD code only. Use the trusted Issue #981 operator-cli dispatcher.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "scripts/z2/hil/abi5_openocd_flash/ab_flow_tpl.py"
CDC_PROBE = ROOT / "firmware/blue-pill-usb-cdc/host/cdc_probe.py"
EXPECTED = {
    "v0.1": {"bytes": 18768, "sha256": "8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d", "version": "0.1"},
    "v0.2": {"bytes": 62800, "sha256": "e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c", "version": "0.2"},
}
ERASE_BYTES = 63488
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")
DEVICE = re.compile(r"ppu-device-[a-f0-9]{16,64}\Z")
ENGINE_ROOT = "/opt/plasma/programming-engines/openocd/"
IMAGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,96}\Z")


class NotRun(Exception):
    def __init__(self, reason: str, exit_code: int = 69):
        self.exit_code = exit_code
        super().__init__(reason)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sequence(start: int, count: int) -> list[tuple[int, str]]:
    if not (0 <= start < 100 and 1 <= count <= 20 and start % 20 == 0
            and start + count <= 100 and count == 20):
        raise ValueError("BATCH_MUST_BE_20_AT_START_0_20_40_60_80")
    # 25 ABBA blocks: 50 attempts per firmware, thermal/time drift balanced.
    order = ("v0.1", "v0.2", "v0.2", "v0.1") * 25
    return [(i + 1, order[i]) for i in range(start, start + count)]


def firmware(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise NotRun("FIRMWARE_NOT_AVAILABLE:" + label)
    data = path.read_bytes()
    expected = EXPECTED[label]
    if len(data) != expected["bytes"] or sha(data) != expected["sha256"]:
        raise NotRun("FIRMWARE_SIZE_OR_SHA_MISMATCH:" + label, 77)
    return data


def build_v02_from_locked_source(cube_root: Path, arm_root: Path) -> bytes:
    """Host-only fallback; never modify source, install packages or use a DUT.

    The checked-in CMake contract rejects unpinned CubeF1 and dependency SHAs.
    The resulting BIN must additionally match the historical CI SHA exactly.
    """
    if (not shutil.which("cmake") or not shutil.which("ninja")
            or not (cube_root / "Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal.h").is_file()
            or not (arm_root / "usr/bin/arm-none-eabi-gcc").is_file()
            or not (arm_root / "usr/bin/arm-none-eabi-objdump").is_file()):
        raise NotRun("LOCKED_FIRMWARE_BUILD_DEPENDENCIES_MISSING")
    if cube_root.is_symlink() or arm_root.is_symlink():
        raise NotRun("LOCKED_BUILD_DEPENDENCY_SYMLINK_DENIED", 77)
    with tempfile.TemporaryDirectory(prefix="plasma-bluepill-ab-v02-") as folder:
        build = Path(folder) / "build"
        source = ROOT / "firmware/blue-pill-usb-cdc"
        commands = [
            ["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
             "-DCMAKE_TOOLCHAIN_FILE=" + str(source / "cmake/arm-none-eabi.cmake"),
             "-DARM_GCC_ROOT=" + str(arm_root),
             "-DSTM32CUBE_F1_ROOT=" + str(cube_root)],
            ["cmake", "--build", str(build)],
            [sys.executable, str(source / "host/check_artifacts.py"), str(build),
             str(arm_root / "usr/bin"), "--variant", "v0.2"],
        ]
        for stage, cmd in zip(("CONFIGURE", "BUILD", "CHECK_ARTIFACT"), commands):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True,
                                        timeout=240, check=False)
            except (OSError, subprocess.TimeoutExpired):
                raise NotRun("LOCKED_FIRMWARE_" + stage + "_UNAVAILABLE") from None
            if result.returncode != 0:
                observed = result.stdout + "\n" + result.stderr
                hint = ("SOURCE_REVISION_MISMATCH" if "dependency revision mismatch" in observed
                        else "MISSING_SOURCE_FILE" if "No such file or directory" in observed
                        else "CMAKE_OR_TOOLCHAIN_FAILURE")
                raise NotRun("LOCKED_FIRMWARE_" + stage + "_FAILED:" + hint)
        return firmware(build / "plasma-blue-pill-cdc-v0.2.bin", "v0.2")


def expected_region_sha(data: bytes) -> str:
    if len(data) > ERASE_BYTES:
        raise ValueError("FIRMWARE_EXCEEDS_APPROVED_ERASE_REGION")
    return sha(data + b"\xff" * (ERASE_BYTES - len(data)))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise NotRun("REVIEWED_HELPER_MISSING")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_args(args):
    if (not SHA40.fullmatch(args.source_sha) or not SHA64.fullmatch(args.openocd_sha)
            or not DEVICE.fullmatch(args.device_id) or not IMAGE_ID.fullmatch(args.image_id)):
        raise NotRun("SOURCE_OR_IDENTITY_ARGUMENT_INVALID", 77)
    if (not args.openocd_dir.startswith(ENGINE_ROOT)
            or not re.fullmatch(r"/[A-Za-z0-9_./-]+", args.openocd_dir)
            or ".." in Path(args.openocd_dir).parts
            or Path(args.openocd_dir).parent.as_posix() != ENGINE_ROOT.rstrip("/")):
        raise NotRun("OPENOCD_INSTALL_ROOT_INVALID", 77)
    if not (8 <= args.cdc_duration <= 30):
        raise NotRun("CDC_DURATION_OUT_OF_SCOPE", 77)
    if not (args.host == "192.168.2.99"):
        raise NotRun("UNEXPECTED_ENROLLED_Z2_HOST", 77)
    candidate = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
    if candidate != args.source_sha:
        raise NotRun("WORK_ORDER_SOURCE_SHA_MISMATCH", 77)
    sequence(args.start, args.count)


def make_remote(config: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count("@CONFIG_B64@") != 1:
        raise NotRun("REVIEWED_REMOTE_TEMPLATE_INVALID", 77)
    raw = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return template.replace("@CONFIG_B64@", base64.b64encode(raw).decode())


def remote_call(helper, creds, known_hosts, source: str, *, timeout=70) -> dict:
    try:
        rc, output = helper.password_ssh_z2(["python3", "-I", "-B", "-c", source],
                                             creds, known_hosts, timeout=timeout)
    except Exception:
        raise RuntimeError("Z2_OPERATION_OUTCOME_UNKNOWN") from None
    if rc != 0:
        raise RuntimeError("Z2_OPERATION_COMMAND_FAILED")
    rows = [line[7:] for line in output.splitlines() if line.startswith("Z2JSON=")]
    if len(rows) != 1 or len(rows[0]) > 20000:
        raise RuntimeError("Z2_OPERATION_RECEIPT_MISSING")
    try:
        result = json.loads(rows[0])
    except ValueError:
        raise RuntimeError("Z2_OPERATION_RECEIPT_INVALID") from None
    if not isinstance(result, dict):
        raise RuntimeError("Z2_OPERATION_RECEIPT_INVALID")
    return result


def remote_stage(helper, creds, known_hosts, code: str, *, timeout=90) -> None:
    # Stage responses are bounded, contain no credentials and have no stdout echo.
    try:
        rc, output = helper.password_ssh_z2(["python3", "-I", "-B", "-c", code],
                                             creds, known_hosts, timeout=timeout)
    except Exception:
        raise RuntimeError("Z2_STAGE_OUTCOME_UNKNOWN") from None
    if rc != 0 or "STAGE_OK" not in output:
        raise RuntimeError("Z2_STAGING_FAILED")


def stage_images(helper, creds, hosts, images: dict[str, bytes], token: str) -> dict[str, str]:
    if not re.fullmatch(r"[a-f0-9]{24}", token):
        raise ValueError("STAGE_TOKEN_INVALID")
    parent = "/root/.plasma-bluepill-ab"
    base = parent + "/" + token
    code = ("from pathlib import Path\nimport os\n"
            f"p=Path({parent!r});p.mkdir(mode=0o700,exist_ok=True);p.chmod(0o700)\n"
            f"d=Path({base!r});d.mkdir(mode=0o700,exist_ok=False)\nprint('STAGE_OK')")
    remote_stage(helper, creds, hosts, code)
    output = {}
    for version, data in images.items():
        path = base + "/fw-" + version.replace(".", "") + ".bin"
        for offset in range(0, len(data), 12000):
            chunk = base64.b64encode(data[offset:offset + 12000]).decode()
            code = ("import base64,os\nfrom pathlib import Path\n"
                    f"p=Path({path!r});offset={offset}\n"
                    "assert not p.is_symlink()\n"
                    "assert (p.stat().st_size if p.exists() else 0)==offset\n"
                    f"with p.open('ab') as f:f.write(base64.b64decode({chunk!r}))\n"
                    "os.chmod(p,0o600)\nprint('STAGE_OK')")
            remote_stage(helper, creds, hosts, code)
        code = ("import hashlib\nfrom pathlib import Path\n"
                f"p=Path({path!r})\n"
                f"assert p.stat().st_size=={len(data)}\n"
                f"assert hashlib.sha256(p.read_bytes()).hexdigest()=={sha(data)!r}\n"
                "print('STAGE_OK')")
        remote_stage(helper, creds, hosts, code)
        output[version] = path
    return output


def cdc_port() -> str:
    try:
        from serial.tools import list_ports
    except ImportError:
        raise NotRun("PY_SERIAL_NOT_INSTALLED") from None
    matches = [p.device for p in list_ports.comports()
               if p.vid == 0xCAFE and p.pid == 0x4001]
    if len(matches) != 1:
        raise NotRun("BLUE_PILL_CDC_NOT_UNIQUE_OR_MISSING")
    return matches[0]


def cdc_check(version: str, duration: int) -> dict:
    deadline = time.monotonic() + 6
    port = None
    while time.monotonic() < deadline:
        try:
            port = cdc_port()
            break
        except NotRun:
            time.sleep(0.3)
    if port is None:
        return {"result": "FAIL", "reason": "CDC_NOT_FOUND_AFTER_RESET"}
    cmd = [sys.executable, str(CDC_PROBE), "--port", port, "--version",
           EXPECTED[version]["version"], "--duration", str(duration)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=duration + 15, check=False)
    except subprocess.TimeoutExpired:
        return {"result": "FAIL", "reason": "CDC_PROBE_TIMEOUT"}
    return {"result": "PASS" if result.returncode == 0 and "PASS:" in result.stdout else "FAIL",
            "port": port, "probe_rc": result.returncode,
            "probe_tail": result.stdout[-400:] if result.returncode == 0 else
            (result.stdout + result.stderr)[-500:]}


def print_receipt(stage: str, value: dict):
    # The Path 2 executor saves stdout (<= 64 KiB) as a GitHub Actions artifact.
    print("PLASMA_AB=" + json.dumps({"stage": stage, **value},
                                    sort_keys=True, separators=(",", ":")), flush=True)


def execute(args) -> int:
    verify_args(args)
    planned = sequence(args.start, args.count)
    images = {"v0.1": firmware(Path(args.firmware_a), "v0.1"),
              "v0.2": None}
    if Path(args.firmware_b).is_file():
        images["v0.2"] = firmware(Path(args.firmware_b), "v0.2")
    elif args.build_b_if_missing:
        images["v0.2"] = build_v02_from_locked_source(
            Path(args.cube_root), Path(args.arm_gcc_root))
    else:
        raise NotRun("FIRMWARE_NOT_AVAILABLE:v0.2")
    print_receipt("SOURCE", {"source_sha": args.source_sha, "batch_start": args.start,
                             "count": args.count, "firmware": {
                                 k: {"sha256": sha(v), "bytes": len(v),
                                     "region_sha256": expected_region_sha(v)}
                                 for k, v in images.items()}})

    baseline = _load(ROOT / "scripts/ppu_path2_hardware_baseline.py", "ab_existing_baseline")
    try:
        baseline._private_ipv4(args.host)
        status = baseline.probe_status(args.host)
    except Exception:
        raise NotRun("Z2_BOOTSTRAP_IDENTITY_PROBE_UNAVAILABLE") from None
    if status.get("device_id_observed") != args.device_id:
        raise NotRun("Z2_DEVICE_ID_MISMATCH", 77)
    helper = _load(ROOT / "scripts/plasma_wordport_program.py", "ab_existing_pinned_ssh")
    try:
        creds, hosts = helper.z2_login_credentials(Path.home())
    except Exception:
        raise NotRun("Z2_ENROLLED_CREDENTIALS_UNAVAILABLE") from None
    if creds.get("ssh_host") != args.host:
        raise NotRun("Z2_ENROLLED_HOST_MISMATCH", 77)

    # CDC must be available before any Z2 filesystem mutation or MCU reset.
    port = cdc_port()
    owner = subprocess.run(["fuser", "-s", port], capture_output=True,
                           timeout=5, check=False)
    if owner.returncode != 1:
        raise NotRun("BLUE_PILL_SERIAL_OWNER_BUSY_OR_UNKNOWN")

    base = {"openocd_dir": args.openocd_dir, "openocd_sha256": args.openocd_sha,
            "image_id": args.image_id, "site": 2, "speed_khz": 5000}
    status_config = {**base, "mode": "status", "version": "v0.1", "attempt": args.start,
                     "firmware": "/root/.plasma-bluepill-ab/not-staged.bin",
                     "firmware_bytes": EXPECTED["v0.1"]["bytes"],
                     "firmware_sha256": EXPECTED["v0.1"]["sha256"]}
    initial = remote_call(helper, creds, hosts, make_remote(status_config), timeout=90)
    print_receipt("Z2_PREFLIGHT", {"result": initial.get("result"),
                                    "reason": initial.get("reason"),
                                    "boot_id": initial.get("pre", {}).get("boot_id"),
                                    "manager": initial.get("pre", {}).get("manager")})
    if initial.get("result") != "STATUS_PASS":
        return 1

    token = uuid.uuid4().hex[:24]
    paths = stage_images(helper, creds, hosts, images, token)
    home = "/root/.plasma-bluepill-ab/" + token
    def run_z2(mode, version, attempt):
        config = {**base, "mode": mode, "version": version, "attempt": attempt,
                  "firmware": paths[version], "firmware_sha256": EXPECTED[version]["sha256"],
                  "firmware_bytes": EXPECTED[version]["bytes"],
                  "backup": f"{home}/backup-{args.start:03d}.bin",
                  "readback": f"{home}/{mode}-{attempt:03d}.bin",
                  "log": f"{home}/{mode}-{attempt:03d}.openocd.log"}
        return remote_call(helper, creds, hosts, make_remote(config), timeout=180)

    backup = run_z2("backup", "v0.1", args.start)
    print_receipt("BACKUP", {k: backup.get(k) for k in
                             ("result", "reason", "openocd_rc", "readback_sha256",
                              "readback_bytes", "safe_off", "geometry_64k", "journal_unchanged")}
                  | {"z2_evidence_dir": home})
    if backup.get("result") != "BACKUP_PASS":
        return 1
    for index, version in planned:
        remote = run_z2("flash", version, index)
        print_receipt("FLASH", {"index": index, "version": version,
                                **{k: remote.get(k) for k in
                                   ("result", "reason", "elapsed_s", "openocd_rc",
                                    "readback_sha256", "readback_bytes", "clock_khz",
                                    "safe_off", "journal_unchanged", "openocd_log_sha256")}})
        if remote.get("result") != "FLASH_PASS":
            return 1  # no automatic retry or MCU reset after failed Flash
        cdc = cdc_check(version, args.cdc_duration)
        print_receipt("CDC", {"index": index, "version": version, **cdc})
        if cdc["result"] != "PASS":
            return 1
    print_receipt("COMPLETE", {"start": args.start, "count": args.count,
                               "passed": len(planned), "failed": 0,
                               "z2_evidence_dir": home})
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--openocd-dir", required=True)
    parser.add_argument("--openocd-sha", required=True)
    parser.add_argument("--firmware-a", required=True)
    parser.add_argument("--firmware-b", required=True)
    parser.add_argument("--build-b-if-missing", action="store_true")
    parser.add_argument("--cube-root", default="/tmp/plasma-stm32cubef1")
    parser.add_argument("--arm-gcc-root", default="/tmp/plasma-arm-toolchain")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--cdc-duration", type=int, default=12)
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except NotRun as exc:
        print_receipt("STOP", {"result": "NOT_RUN", "reason": str(exc)})
        return exc.exit_code
    except Exception as exc:
        print_receipt("STOP", {"result": "FAIL", "reason": type(exc).__name__})
        return 1


if __name__ == "__main__":
    sys.exit(main())
