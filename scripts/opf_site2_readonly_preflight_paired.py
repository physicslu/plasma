#!/usr/bin/env python3
"""Path 2: one-time Site 2 read-only preflight using the enrolled Z2 pairing.

No runtime installation, bundle mutation, FPGA reload, MMIO/SWD access,
OpenOCD launch or DUT flash. This is an engineering acceptance snapshot,
not an every-Job health inventory or proof of real hardware readiness.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
from pathlib import Path

import plasma_site2_path2_preflight as preflight
import plasma_wordport_program as enrolled

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SCHEMA = "plasma.site2.path2-readonly-summary.v1"


def run(source_sha: str, *, pair=enrolled, probe=preflight) -> dict:
    if type(source_sha) is not str or SHA40.fullmatch(source_sha) is None:
        raise ValueError("PINNED_SOURCE_INVALID")
    credentials, _known_hosts = pair.z2_login_credentials(Path.home())
    host = credentials.get("ssh_host")
    try:
        addr = ipaddress.ip_address(host)
    except (ValueError, TypeError) as exc:
        raise ValueError("ENROLLED_TARGET_INVALID") from exc
    if addr.version != 4 or not addr.is_private:
        raise ValueError("ENROLLED_TARGET_INVALID")
    observed = probe.run(host, source_sha, helper=pair)
    if observed.get("schema") != probe.SCHEMA or observed.get("source_sha") != source_sha:
        raise ValueError("PREFLIGHT_RECEIPT_INVALID")
    z2 = observed.get("z2")
    rest = observed.get("rest")
    if type(z2) is not dict or type(rest) is not dict:
        raise ValueError("PREFLIGHT_RECEIPT_INVALID")
    engine, fpga = z2.get("engine", {}), z2.get("fpga", {})
    return {
        "schema": SCHEMA, "result": "OBSERVED",
        "source_sha": source_sha, "readiness": observed.get("readiness"),
        "blockers": observed.get("blockers"),
        "engine_selection": engine.get("status"),
        "openocd_driver": engine.get("driver"),
        "openocd_abi": engine.get("abi"),
        "fpga_journal_status": fpga.get("status", "NOT_VERIFIED"),
        "fpga_same_boot": fpga.get("boot_match"),
        "fpga_manager_state": fpga.get("manager_state"),
        "site2_sealed": z2.get("site2_seal", {}).get("present"),
        "site2_admission_record": z2.get("site2_admission", {}).get("present"),
        "openocd_running": bool(z2.get("openocd_pids")),
        "rest_ready": rest.get("health_ready"),
        "site2_idle": rest.get("site2_idle"),
        "site2_enabled": rest.get("site2_enabled"),
        "hardware_site_lock": "NOT_VERIFIED",
        "provider_runtime_resolution": "NOT_RUN",
        "physical_swd": "NOT_RUN", "fpga_reload": "NOT_RUN",
        "dut_flash": "NOT_RUN",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    try:
        result = run(args.source_sha)
        code = 0
    except Exception as exc:
        code = 69
        reason = str(exc) if isinstance(exc, ValueError) and str(exc) in {
            "PINNED_SOURCE_INVALID", "ENROLLED_TARGET_INVALID",
            "PREFLIGHT_RECEIPT_INVALID",
        } else type(exc).__name__
        result = {"schema": SCHEMA, "result": "BLOCKED_OR_NOT_RUN",
                  "reason": reason, "dut_flash": "NOT_RUN",
                  "fpga_reload": "NOT_RUN", "physical_swd": "NOT_RUN"}
    print("PLASMA_SITE2_RUNTIME_PREFLIGHT=" + json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
