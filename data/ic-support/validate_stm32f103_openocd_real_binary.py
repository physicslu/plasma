#!/usr/bin/env python3
"""Software-only acceptance of the pinned OpenOCD STM32F103 backend.

This script executes the real Plasma-owned OpenOCD binary with OpenOCD's dummy
adapter and automatic initialization disabled. It parses the real STM32F1 target
script and instantiates the real stm32f1x Flash driver, but deliberately exits
before adapter initialization, target examination, or any hardware transaction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.json"
BASELINE_LOCK = ROOT / "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.lock.json"
BINDING = ROOT / "data/ic-support/bindings/stm32f103c-pilot-v0.json"
OPENOCD_RELEASE = ROOT / "release/openocd.json"

EXPECTED_ICPN = "STM32F103C8T6"
EXPECTED_INTERFACE_CONFIG = "interface/dummy.cfg"
EXPECTED_FLASH_DRIVER = "stm32f1x"
EXPECTED_FLASH_NAME = "stm32f1x.flash"
EXPECTED_TARGET_NAME = "stm32f1x.cpu"

Runner = Callable[..., subprocess.CompletedProcess[str]]


class OpenOCDSoftwareAcceptanceError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OpenOCDSoftwareAcceptanceError(f"cannot load {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OpenOCDSoftwareAcceptanceError(f"{path}: top level must be an object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise OpenOCDSoftwareAcceptanceError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _hex(value: object, *, field: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise OpenOCDSoftwareAcceptanceError(f"{field} must be a hexadecimal string")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise OpenOCDSoftwareAcceptanceError(f"{field} is not valid hexadecimal") from exc


def load_contract() -> dict[str, Any]:
    baseline_bytes = BASELINE.read_bytes()
    baseline = _load_json(BASELINE)
    lock = _load_json(BASELINE_LOCK)
    binding = _load_json(BINDING)
    release = _load_json(OPENOCD_RELEASE)

    baseline_sha = hashlib.sha256(baseline_bytes).hexdigest()
    if lock.get("canonical_file_sha256") != baseline_sha:
        raise OpenOCDSoftwareAcceptanceError("manufacturer baseline digest drift")
    if baseline.get("status") != "frozen_manufacturer_only":
        raise OpenOCDSoftwareAcceptanceError("manufacturer baseline is not frozen")
    if baseline.get("source_policy", {}).get("derivation_authority") != "manufacturer_official_only":
        raise OpenOCDSoftwareAcceptanceError("manufacturer-only derivation authority is required")
    if baseline.get("target", {}).get("icpn") != EXPECTED_ICPN:
        raise OpenOCDSoftwareAcceptanceError("unexpected manufacturer baseline target")

    flash = baseline["device_profile"]["memory_map"]["main_flash"]
    flash_start = _hex(flash.get("start"), field="main Flash start")
    flash_size = int(flash.get("size_bytes", 0))
    if flash_start != 0x08000000 or flash_size != 64 * 1024:
        raise OpenOCDSoftwareAcceptanceError(
            "exact STM32F103C8T6 manufacturer geometry must remain 0x08000000 + 64 KiB"
        )

    bindings = binding.get("bindings")
    if not isinstance(bindings, list):
        raise OpenOCDSoftwareAcceptanceError("STM32F103C pilot bindings are missing")
    exact = [
        row for row in bindings
        if isinstance(row, dict) and row.get("icpn") == EXPECTED_ICPN
    ]
    if len(exact) != 1:
        raise OpenOCDSoftwareAcceptanceError("exact STM32F103C8T6 binding must be unique")
    expected_catalog = exact[0].get("expected_catalog")
    if not isinstance(expected_catalog, dict):
        raise OpenOCDSoftwareAcceptanceError("exact STM32F103C8T6 catalog binding is malformed")
    if expected_catalog.get("flash_size") != "64 KiB":
        raise OpenOCDSoftwareAcceptanceError("catalog binding no longer preserves C8 64-KiB identity")
    target_config = expected_catalog.get("openocd_target_config")
    if target_config != "tcl/target/stm32f1x.cfg":
        raise OpenOCDSoftwareAcceptanceError("unexpected STM32F103C8T6 OpenOCD target config")

    version = release.get("version")
    source_commit = release.get("source_commit")
    runtime_id = release.get("runtime_id")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise OpenOCDSoftwareAcceptanceError("OpenOCD release version is invalid")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise OpenOCDSoftwareAcceptanceError("OpenOCD source commit is not a full SHA")
    if runtime_id != f"{version}-{source_commit[:12]}":
        raise OpenOCDSoftwareAcceptanceError("OpenOCD runtime identity is inconsistent")
    if release.get("hardware_runtime_ready") is not False:
        raise OpenOCDSoftwareAcceptanceError("OpenOCD release must remain hardware-runtime-disabled")

    return {
        "icpn": EXPECTED_ICPN,
        "baseline_id": baseline["baseline_id"],
        "baseline_sha256": baseline_sha,
        "flash_start": flash_start,
        "flash_size_bytes": flash_size,
        "interface_config": EXPECTED_INTERFACE_CONFIG,
        "target_config": target_config.removeprefix("tcl/"),
        "openocd_version": version,
        "openocd_source_commit": source_commit,
        "runtime_id": runtime_id,
        "hardware_runtime_ready": False,
    }


def build_openocd_argv(
    *,
    openocd: Path,
    scripts_root: Path,
    contract: dict[str, Any],
) -> list[str]:
    flash_size = int(contract["flash_size_bytes"])
    argv = [
        str(openocd),
        "-s",
        str(scripts_root),
        "-c",
        "noinit",
        "-f",
        str(contract["interface_config"]),
        "-c",
        "transport select jtag",
        "-c",
        f"set FLASH_SIZE 0x{flash_size:X}",
        "-f",
        str(contract["target_config"]),
        "-c",
        "set __plasma_banks [flash list]",
        "-c",
        'if {[llength $__plasma_banks] != 1} { error "PLASMA expected exactly one Flash bank" }',
        "-c",
        "array set __plasma_bank [lindex $__plasma_banks 0]",
        "-c",
        'echo "PLASMA_FLASH_NAME=$__plasma_bank(name)"',
        "-c",
        'echo "PLASMA_FLASH_DRIVER=$__plasma_bank(driver)"',
        "-c",
        'echo "PLASMA_FLASH_BASE=$__plasma_bank(base)"',
        "-c",
        'echo "PLASMA_FLASH_SIZE=$__plasma_bank(size)"',
        "-c",
        'echo "PLASMA_FLASH_TARGET=$__plasma_bank(target)"',
        "-c",
        'echo "PLASMA_CONFIG_ONLY_NOINIT=1"',
        "-c",
        "shutdown",
    ]
    validate_safe_argv(argv)
    return argv


def validate_safe_argv(argv: Sequence[str]) -> None:
    if not argv:
        raise OpenOCDSoftwareAcceptanceError("OpenOCD argv is empty")
    commands = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "-c"]
    files = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "-f"]
    if not commands or commands[0] != "noinit":
        raise OpenOCDSoftwareAcceptanceError("noinit must be the first OpenOCD command")
    if commands[-1] != "shutdown":
        raise OpenOCDSoftwareAcceptanceError("shutdown must terminate configuration parsing")
    if EXPECTED_INTERFACE_CONFIG not in files:
        raise OpenOCDSoftwareAcceptanceError("official OpenOCD dummy interface config is required")
    if any("board/" in value or "blue_pill" in value.lower() for value in files):
        raise OpenOCDSoftwareAcceptanceError("board-level OpenOCD configuration is forbidden")
    if not any(value.endswith("target/stm32f1x.cfg") for value in files):
        raise OpenOCDSoftwareAcceptanceError("STM32F1 target config is required")

    forbidden = (
        "init",
        "reset",
        "halt",
        "resume",
        "flash erase",
        "flash write",
        "flash verify",
        "program ",
        "dump_image",
        "load_image",
        "mww ",
        "mwh ",
        "mdw ",
        "mdh ",
    )
    for command in commands:
        normalized = command.strip().lower()
        if normalized == "noinit":
            continue
        if any(
            normalized == token
            or normalized.startswith(token)
            for token in forbidden
        ):
            raise OpenOCDSoftwareAcceptanceError(
                f"hardware-affecting OpenOCD command is forbidden: {command!r}"
            )


def _probe_runtime_layout(openocd: Path, scripts_root: Path, contract: dict[str, Any]) -> dict[str, str]:
    if not openocd.is_file():
        raise OpenOCDSoftwareAcceptanceError(f"OpenOCD binary is missing: {openocd}")
    if not scripts_root.is_dir():
        raise OpenOCDSoftwareAcceptanceError(f"OpenOCD scripts root is missing: {scripts_root}")

    dummy = scripts_root / contract["interface_config"]
    target = scripts_root / contract["target_config"]
    if not dummy.is_file():
        raise OpenOCDSoftwareAcceptanceError(f"OpenOCD dummy interface is missing: {dummy}")
    if not target.is_file():
        raise OpenOCDSoftwareAcceptanceError(f"STM32F1 target config is missing: {target}")

    dummy_lines = [
        line.strip()
        for line in dummy.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if dummy_lines != ["adapter driver dummy"]:
        raise OpenOCDSoftwareAcceptanceError(
            "OpenOCD dummy interface config no longer contains only the dummy adapter declaration"
        )

    target_text = target.read_text(encoding="utf-8")
    required_target_fragments = (
        "if { [info exists FLASH_SIZE] }",
        "flash bank $_FLASHNAME stm32f1x 0x08000000 $_FLASH_SIZE 0 0 $_TARGETNAME",
    )
    for fragment in required_target_fragments:
        if fragment not in target_text:
            raise OpenOCDSoftwareAcceptanceError(
                f"STM32F1 target config contract drift: missing {fragment!r}"
            )

    return {
        "binary_sha256": _sha256(openocd),
        "dummy_cfg_sha256": _sha256(dummy),
        "target_cfg_sha256": _sha256(target),
    }


def _run(
    argv: Sequence[str],
    *,
    runner: Runner,
    timeout_s: float,
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            list(argv),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OpenOCDSoftwareAcceptanceError(f"cannot execute OpenOCD: {exc}") from exc


def _require_version(
    openocd: Path,
    *,
    expected: str,
    runner: Runner,
    timeout_s: float,
) -> str:
    completed = _run([str(openocd), "--version"], runner=runner, timeout_s=timeout_s)
    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0:
        raise OpenOCDSoftwareAcceptanceError(
            f"OpenOCD version probe failed with code {completed.returncode}: {output[-2000:]}"
        )
    match = re.search(r"Open On-Chip Debugger\s+(\d+\.\d+\.\d+)", output)
    if match is None:
        raise OpenOCDSoftwareAcceptanceError("OpenOCD version banner is not recognized")
    if match.group(1) != expected:
        raise OpenOCDSoftwareAcceptanceError(
            f"OpenOCD version mismatch: expected {expected}, got {match.group(1)}"
        )
    return output.strip()


def _marker(output: str, name: str) -> str:
    match = re.search(rf"{re.escape(name)}=([^\r\n]+)", output)
    if match is None:
        raise OpenOCDSoftwareAcceptanceError(f"OpenOCD acceptance marker is missing: {name}")
    return match.group(1).strip().strip('"')


def validate_markers(output: str, contract: dict[str, Any]) -> dict[str, Any]:
    observed = {
        "flash_name": _marker(output, "PLASMA_FLASH_NAME"),
        "flash_driver": _marker(output, "PLASMA_FLASH_DRIVER"),
        "flash_base": int(_marker(output, "PLASMA_FLASH_BASE"), 0),
        "flash_size_bytes": int(_marker(output, "PLASMA_FLASH_SIZE"), 0),
        "flash_target": _marker(output, "PLASMA_FLASH_TARGET"),
        "config_only_noinit": _marker(output, "PLASMA_CONFIG_ONLY_NOINIT"),
    }
    expected = {
        "flash_name": EXPECTED_FLASH_NAME,
        "flash_driver": EXPECTED_FLASH_DRIVER,
        "flash_base": int(contract["flash_start"]),
        "flash_size_bytes": int(contract["flash_size_bytes"]),
        "flash_target": EXPECTED_TARGET_NAME,
        "config_only_noinit": "1",
    }
    if observed != expected:
        raise OpenOCDSoftwareAcceptanceError(
            f"real OpenOCD STM32F103 registration mismatch: expected={expected!r}, observed={observed!r}"
        )
    if observed["flash_size_bytes"] == 128 * 1024:
        raise OpenOCDSoftwareAcceptanceError(
            "real OpenOCD acceptance absorbed the Blue Pill 128-KiB board override"
        )
    return observed


def run_acceptance(
    *,
    openocd: Path,
    scripts_root: Path,
    runner: Runner = subprocess.run,
    timeout_s: float = 15.0,
) -> dict[str, Any]:
    if timeout_s <= 0:
        raise OpenOCDSoftwareAcceptanceError("timeout must be positive")

    contract = load_contract()
    layout = _probe_runtime_layout(openocd, scripts_root, contract)
    version_banner = _require_version(
        openocd,
        expected=str(contract["openocd_version"]),
        runner=runner,
        timeout_s=timeout_s,
    )
    argv = build_openocd_argv(openocd=openocd, scripts_root=scripts_root, contract=contract)
    completed = _run(argv, runner=runner, timeout_s=timeout_s)
    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0:
        raise OpenOCDSoftwareAcceptanceError(
            f"real OpenOCD configuration acceptance failed with code {completed.returncode}: "
            f"{output[-4000:]}"
        )
    observed = validate_markers(output, contract)

    return {
        "result": "PASS",
        "scope": "real_openocd_configuration_parse_only_noinit",
        "icpn": contract["icpn"],
        "manufacturer_baseline_id": contract["baseline_id"],
        "manufacturer_baseline_sha256": contract["baseline_sha256"],
        "openocd_version": contract["openocd_version"],
        "openocd_version_banner": version_banner,
        "openocd_source_commit": contract["openocd_source_commit"],
        "runtime_id": contract["runtime_id"],
        "binary_sha256": layout["binary_sha256"],
        "dummy_cfg_sha256": layout["dummy_cfg_sha256"],
        "target_cfg_sha256": layout["target_cfg_sha256"],
        "interface_config": contract["interface_config"],
        "target_config": contract["target_config"],
        "transport": "jtag",
        **observed,
        "automatic_init_disabled": True,
        "board_config_loaded": False,
        "adapter_initialization_requested": False,
        "target_examination_requested": False,
        "flash_operation_requested": False,
        "hardware_runtime_ready": False,
        "physical_programming_qualified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openocd", type=Path, required=True)
    parser.add_argument("--scripts-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-s", type=float, default=15.0)
    args = parser.parse_args()

    evidence = run_acceptance(
        openocd=args.openocd,
        scripts_root=args.scripts_root,
        timeout_s=args.timeout_s,
    )
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OpenOCDSoftwareAcceptanceError as exc:
        print(f"STM32F103 real-OpenOCD software acceptance FAIL: {exc}")
        raise SystemExit(1)
