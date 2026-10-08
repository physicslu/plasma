from __future__ import annotations

import json
import platform
import time
from pathlib import Path
from typing import Any

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_interfaces.openocd_worker import OpenOCDWorker


OPENOCD_RUNTIME_EVIDENCE = Path("/opt/plasma/install/openocd-runtime.json")
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 30_000
EXECUTION_CAPABILITY = "openocd-control-plane-only"


def _request(body: dict[str, Any]) -> tuple[int, int]:
    allowed = {"site_id", "timeout_ms"}
    unknown = sorted(set(body) - allowed)
    missing = sorted(allowed - set(body))
    if unknown:
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            f"OpenOCD control-plane request contains unexpected fields: {', '.join(unknown)}",
        )
    if missing:
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            f"OpenOCD control-plane request is missing required fields: {', '.join(missing)}",
        )

    site_id = body["site_id"]
    timeout_ms = body["timeout_ms"]
    if isinstance(site_id, bool) or not isinstance(site_id, int) or site_id < 1:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "site_id must be a one-based positive integer")
    if (
        isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or timeout_ms < MIN_TIMEOUT_MS
        or timeout_ms > MAX_TIMEOUT_MS
    ):
        raise PlasmaError(
            ErrorCode.INVALID_ARGUMENT,
            f"timeout_ms must be between {MIN_TIMEOUT_MS} and {MAX_TIMEOUT_MS}",
        )
    return site_id, timeout_ms


def _validate_site(snapshot: dict[str, Any], site_id: int) -> None:
    sites = snapshot.get("sites")
    if not isinstance(sites, list):
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "canonical PPU status is missing Site topology",
        )
    known = {
        item.get("site_id")
        for item in sites
        if isinstance(item, dict)
        and isinstance(item.get("site_id"), int)
        and not isinstance(item.get("site_id"), bool)
    }
    if site_id not in known:
        raise PlasmaError(
            ErrorCode.SITE_INVALID,
            f"Site {site_id} is not present in canonical PPU topology",
            context={"site_id": site_id, "known_site_ids": sorted(known)},
        )


def _runtime_evidence(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlasmaError(
            ErrorCode.INTERFACE_NOT_CONFIGURED,
            "Plasma-owned OpenOCD runtime is not installed",
            recoverable=True,
            original_exception=exc,
            context={"evidence_path": str(path)},
        ) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "OpenOCD runtime install evidence is unreadable",
            original_exception=exc,
            context={"evidence_path": str(path)},
        ) from exc

    if not isinstance(payload, dict):
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "OpenOCD runtime install evidence must be an object")
    if payload.get("result") != "PASS" or payload.get("hardware_runtime_ready") is not False:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "OpenOCD runtime install evidence does not preserve the software-only boundary",
        )

    required = ("runtime_id", "openocd_version", "architecture", "binary", "scripts_root")
    for field in required:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"OpenOCD runtime install evidence is missing {field}",
            )

    binary = Path(payload["binary"])
    scripts_root = Path(payload["scripts_root"])
    if not binary.is_file():
        raise PlasmaError(
            ErrorCode.INTERFACE_NOT_CONFIGURED,
            "installed OpenOCD binary is missing",
            recoverable=True,
            context={"binary": str(binary)},
        )
    if not scripts_root.is_dir():
        raise PlasmaError(
            ErrorCode.INTERFACE_NOT_CONFIGURED,
            "installed OpenOCD scripts root is missing",
            recoverable=True,
            context={"scripts_root": str(scripts_root)},
        )
    return payload


async def execute_openocd_control_plane(
    body: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    evidence_path: Path = OPENOCD_RUNTIME_EVIDENCE,
) -> dict[str, Any]:
    """Run one safe, ephemeral OpenOCD control-plane probe on the PPU PS.

    The Browser cannot select a Tcl command. The diagnostic always uses the
    worker's fixed dummy-adapter startup and the safe Tcl `version` probe.
    This proves process/RPC/routing behavior only; it never touches SWD/JTAG,
    PL, target power/reset, target detection, or flash.
    """

    site_id, timeout_ms = _request(body)
    _validate_site(snapshot, site_id)
    runtime = _runtime_evidence(evidence_path)

    timeout_s = timeout_ms / 1000.0
    worker = OpenOCDWorker(
        site_id=site_id,
        executable=runtime["binary"],
        scripts_root=runtime["scripts_root"],
        startup_timeout_s=min(timeout_s, 5.0),
        command_timeout_s=timeout_s,
        stop_timeout_s=min(timeout_s, 2.0),
    )

    started_at = time.monotonic()
    generation = 0
    version = ""
    stopped = False
    try:
        status = await worker.start()
        generation = status.generation
        version = (await worker.command("version", timeout_s=timeout_s)).strip()
        if not version:
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                "OpenOCD Tcl RPC version probe returned an empty response",
                recoverable=True,
            )
    finally:
        await worker.stop()
        stopped = not worker.status().running

    latency_ms = round((time.monotonic() - started_at) * 1000, 3)
    if not stopped:
        raise PlasmaError(
            ErrorCode.INTERFACE_FAILURE,
            "OpenOCD diagnostic worker did not stop cleanly",
            recoverable=True,
            context={"site_id": site_id},
        )

    return {
        "ok": True,
        "result": "PASS",
        "site_id": site_id,
        "openocd_version": runtime["openocd_version"],
        "openocd_version_banner": version,
        "runtime_id": runtime["runtime_id"],
        "process_state": "stopped",
        "probe_process_state": "running",
        "tcl_rpc_state": "pass",
        "rpc_scope": "loopback",
        "architecture": runtime["architecture"],
        "host_architecture": platform.machine().lower(),
        "worker_generation": generation,
        "latency_ms": latency_ms,
        "execution_capability": EXECUTION_CAPABILITY,
        "hardware_runtime_ready": False,
        "not_claimed": [
            "SWD/JTAG",
            "FPGA PL",
            "target power/reset",
            "target detection",
            "flash programming",
            "real IC",
        ],
    }
