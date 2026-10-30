"""Source-bound prototype Z2 image admission; no independent write authority.

Only existing, observed platform conditions are checked. A paired Manifest
contains the expected UIO mapping; no runtime input can waive
unknown FPGA/AXI or recovery states.
"""
from __future__ import annotations

import os
import re

from pl.hil import fpga_image_guard as guard


class AdmissionDenied(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise AdmissionDenied(code)


def check_exact(*, release, passive: dict, uio: dict,
                original_manager_load: str, expected_firmware: str,
                previous_firmware: str | None = None,
                runtime_program_session: bool = False,
                require_mmio: bool = True) -> dict:
    need(type(passive) is dict and
         passive.get("observation_kind") == "LIVE_ROOT_READ_ONLY" and
         passive.get("root") is True and bool(passive.get("boot_id")) and
         passive.get("manager_state") == "operating" and
         passive.get("recovery_sha256") == release.recovery_sha256 and
         passive.get("candidate_sha256") == release.firmware_sha256,
         "INCOMPLETE_ROOT_OR_PROCESS_FACTS")
    need(type(runtime_program_session) is bool, "INVALID_PROCESS_SCAN_POLICY")
    need(type(require_mmio) is bool and
         (require_mmio or not runtime_program_session),
         "INVALID_MMIO_ADMISSION_POLICY")
    scan = passive.get("proc_scan_diagnostic")
    if runtime_program_session:
        # This is NOT a no-conflict measurement. In particular a forged
        # proc_complete=True must not be mistaken for a runtime exemption.
        need(passive.get("proc_complete") is None and
             passive.get("proc_conflicts") is None and
             scan == {"status": "NOT_RUN_PROGRAM_SESSION"},
             "PROGRAM_SESSION_PROCESS_FACTS_INVALID")
    else:
        scan = scan if type(scan) is dict else {}
        # No free-form command lines or environment values; only the root census
        # status, numeric PID, FD/MAPS phase and exception type are reported.
        detail = ":".join(str(scan.get(key, "UNKNOWN"))[:40]
                          for key in ("status", "pid", "phase", "error"))
        need(passive.get("proc_complete") is True,
             "PROC_SCAN_INCOMPLETE:" + detail)
        need(passive.get("proc_conflicts") == [],
             "PROC_RESOURCE_OWNER_CONFLICT")
    if require_mmio:
        owner = release.expected_uio
        if "platform_node" in owner:
            need(type(uio) is dict and
                 set(uio) == {"uio", "platform_node", "driver", "maps",
                              "runtime"} and
                 {k: uio[k] for k in owner} == owner and
                 type(uio["uio"]) is str and
                 re.fullmatch(r"uio[0-9]+", uio["uio"]) is not None,
                 "BOUND_UIO_OWNER_FACTS_CHANGED")
            need(passive.get("uio_overlaps") == [uio["uio"]],
                 "OTHER_BOUND_UIO_OR_MAPPING_DENIED")
            need(passive.get("platform_overlaps") == [owner["platform_node"]],
                 "UIO_PLATFORM_OWNER_MISMATCH")
        else:
            need(type(uio) is dict and uio == owner,
                 "BOUND_UIO_EXACT_FACTS_CHANGED")
            need(passive.get("uio_overlaps") == [release.uio_name],
                 "OTHER_BOUND_UIO_OR_MAPPING_DENIED")
    else:
        # An ordinal change is irrelevant to Manager load; competing bound
        # mappings of the same physical owner are still a resource conflict.
        overlaps = passive.get("uio_overlaps")
        need(type(overlaps) is list and len(overlaps) <= 1 and
             all(type(name) is str and
                 re.fullmatch(r"uio[0-9]+", name) for name in overlaps),
             "OTHER_BOUND_UIO_OR_MAPPING_DENIED")
    need(type(passive.get("platform_overlaps")) is list and
         len(passive["platform_overlaps"]) == 1 and
         bool(re.fullmatch(r"[0-9a-fA-F]+\.[A-Za-z0-9_.-]+",
                           passive["platform_overlaps"][0])),
         "BOUND_PLATFORM_EXCEPTION_NOT_ISOLATED")
    need(expected_firmware in (release.recovery_name, release.firmware_name) or
         (previous_firmware is not None and expected_firmware == previous_firmware),
         "MANAGER_FIRMWARE_NOT_ALLOWLISTED")
    need(type(original_manager_load) is str and
         ": writing " + expected_firmware + " to " in original_manager_load,
         "MANAGER_LOAD_PROVENANCE_UNPROVEN")
    return {
        "site": release.site_bitmap,
        "target_boot_id": passive["boot_id"],
        "image_id": release.image_id,
        "bin_sha256": release.firmware_sha256,
        "recovery_sha256": release.recovery_sha256,
        "current_uio": uio if require_mmio else None,
        "axi_isolation": "UNPROVEN_ACCEPTED_FOR_SOURCE_BOUND_DEVELOPMENT",
        "production_qualification": False,
        "manual_recovery_on_timeout_or_unknown": True,
        "expected_manager_firmware": expected_firmware,
    }


def collect_live(*, root_port: guard.RootZ2TargetPort, release,
                 expected_firmware: str, previous_firmware: str | None = None,
                 runtime_program_session: bool = False,
                 require_mmio: bool = True) -> dict:
    root_port._require_locked()
    need(os.geteuid() == 0, "Z2_ROOT_REQUIRED")
    need(root_port.release == release, "ROOT_RELEASE_BINDING_CHANGED")
    need(type(runtime_program_session) is bool, "INVALID_PROCESS_SCAN_POLICY")
    need(type(require_mmio) is bool and
         (require_mmio or not runtime_program_session),
         "INVALID_MMIO_ADMISSION_POLICY")
    passive = (root_port.runtime_program_facts() if runtime_program_session
               else root_port.current_facts())
    uio = None
    if require_mmio:
        owner = release.expected_uio
        if "platform_node" in owner:
            matches = []
            for item in sorted((guard.SYS / "class/uio").glob("uio*")):
                if not re.fullmatch(r"uio[0-9]+", item.name):
                    continue
                try:
                    node = (item / "device").resolve(strict=True)
                except (FileNotFoundError, OSError):
                    continue
                need(node.parent == (guard.SYS / "bus/platform/devices").resolve(),
                     "UIO_NOT_PLATFORM_DEVICE")
                if node.name == owner["platform_node"]:
                    matches.append(item)
            need(len(matches) == 1, "UIO_PLATFORM_OWNER_NOT_UNIQUE")
            uio_root = matches[0]
        else:
            uio_root = guard.SYS / "class/uio" / release.uio_name
        device = (uio_root / "device").resolve(strict=True)
        driver = (device / "driver").resolve(strict=True).name
        maps = [[int((p / "addr").read_text().strip(), 0),
                 int((p / "size").read_text().strip(), 0)]
                for p in sorted((uio_root / "maps").glob("map*"))]
        uio = dict(uio=uio_root.name, driver=driver, maps=maps,
                   runtime=(device / "power/runtime_status").read_text().strip())
        if "platform_node" in owner:
            uio["platform_node"] = device.name
        else:
            irq = [line for line in (guard.PROC / "interrupts").read_text().splitlines()
                   if line.split() and line.split()[-1] == "fabric"]
            need(len(irq) == 1, "FABRIC_IRQ_TOPOLOGY_CHANGED")
            counters = [int(x) for x in irq[0].split()[1:3]]
            need(len(counters) == 2, "FABRIC_IRQ_CPU_COUNT_CHANGED")
            uio["irq_counts"] = counters
        need(passive["platform_overlaps"] == [device.name],
             "UIO_PLATFORM_OWNER_MISMATCH")
    report = check_exact(
        release=release, passive=passive, uio=uio,
        original_manager_load=guard.manager_last_load(),
        expected_firmware=expected_firmware,
        previous_firmware=previous_firmware,
        runtime_program_session=runtime_program_session,
        require_mmio=require_mmio)
    need((guard.PROC / "sys/kernel/random/boot_id").read_text().strip()
         == report["target_boot_id"], "BOOT_CHANGED_AFTER_RISK_SCAN")
    return report
