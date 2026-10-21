"""One-experiment Z2 F1-B bound-UIO Development risk gate (READ-ONLY).

This policy is *not* proof of AXI quiescence, a Production qualification, a
Root Provider, or a capability to write FPGA Manager. A caller-supplied JSON
claim is never authoritative. The reviewed Z2 root process must invoke
collect_live() while holding the shared FPGA configuration owner lock, and
must separately prove the privileged execution/restore route before writing.
"""
from __future__ import annotations

from pathlib import Path
import os
import re

from pl.hil import f1b
from pl.hil import path2_z2_target_guard as guard

WAIVER = "PLASMA_PATH2_F1B_SITE1_20261021_ONCE_BOUND_PASSIVE_UIO"
FIXED_UIO = {"uio": "uio1", "driver": "uio_pdrv_genirq",
             "maps": [[f1b.BASE, f1b.LENGTH]],
             "runtime": "suspended", "irq_counts": [0, 0]}
ALLOWED = ("SITE1_F1B_DEVELOPMENT_ONLY",)
NO_OP = "NO_FPGA_WRITE_AUTHORITY"


class BoundedRiskDenied(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise BoundedRiskDenied(reason)


def check_exact(*, passive: dict, uio: dict, approval: str,
                scope: str, original_manager_load: str,
                service_snapshot: dict) -> dict:
    """Pure constraints on fresh facts; result *never* grants hardware access.

    Scope is exactly one experiment; cannot waive unknown MMIO users, missing
    operator recovery, a changed boot, firmware or other bound drivers.
    """
    require(approval == WAIVER and scope in ALLOWED,
            "OWNER_DEV_RISK_SCOPE_DENIED")
    require(type(passive) is dict and
            passive.get("observation_kind") == "LIVE_ROOT_READ_ONLY" and
            passive.get("root") is True and
            type(passive.get("boot_id")) is str and
            bool(passive["boot_id"]) and
            passive.get("manager_state") == "operating" and
            passive.get("recovery_sha256") == f1b.BASE_SHA and
            passive.get("candidate_sha256") == f1b.BIN_SHA and
            passive.get("proc_complete") is True and
            passive.get("proc_conflicts") == [],
            "INCOMPLETE_ROOT_OR_PROCESS_FACTS")
    require(type(uio) is dict and uio == FIXED_UIO,
            "BOUND_UIO_EXACT_FACTS_CHANGED")
    require(passive.get("uio_overlaps") == ["uio1"],
            "OTHER_BOUND_UIO_OR_MAPPING_DENIED")
    require(type(passive.get("platform_overlaps")) is list and
            len(passive["platform_overlaps"]) == 1 and
            type(passive["platform_overlaps"][0]) is str and
            bool(re.fullmatch(r"[0-9a-fA-F]+\.[A-Za-z0-9_.-]+",
                              passive["platform_overlaps"][0])),
            "BOUND_PLATFORM_EXCEPTION_NOT_ISOLATED")
    require(type(original_manager_load) is str and
            ": writing base.bin to " in original_manager_load,
            "ORIGINAL_BOOT_LOAD_PROVENANCE_UNPROVEN")
    require(type(service_snapshot) is dict and bool(service_snapshot) and
            all(v == "active" for v in service_snapshot.values()),
            "ORIGINAL_SERVICE_RESTORE_BASELINE_MISSING")
    require(passive.get("axi_isolation_evidence") == "UNPROVEN" and
            passive.get("active_image_attestation") == "UNPROVEN",
            "RISKS_MUST_REMAIN_EXPLICIT")
    return {
        "development_exception": WAIVER,
        "site": 1,
        "source_sha": f1b.SOURCE,
        "bit_sha256": f1b.BIT_SHA,
        "bin_sha256": f1b.BIN_SHA,
        "recovery_sha256": f1b.BASE_SHA,
        "target_boot_id": passive["boot_id"],
        "current_uio": FIXED_UIO,
        "axi_isolation": "UNPROVEN_ACCEPTED_FOR_ONE_DEVELOPMENT_EXPERIMENT",
        "production_qualification": False,
        "provider": NO_OP,
        "must_have_root_restore_and_durable_intent_before_load": True,
        "manual_recovery_on_timeout_or_unknown": True,
    }


def collect_live(*, root_port, approval: str, scope: str) -> dict:
    """Only inside RootZ2TargetPort.exclusive(); no MMIO/FPGA writes."""
    root_port._require_locked()
    require(os.geteuid() == 0, "Z2_ROOT_REQUIRED")
    from pl.hil.swd04 import one_shot
    passive = guard.read_live_z2_facts(
        candidate=root_port.candidate, recovery=root_port.recovery)
    uio_root = guard.SYS / "class/uio/uio1"
    device = (uio_root / "device").resolve(strict=True)
    driver = (device / "driver").resolve(strict=True).name
    maps = [[int((p / "addr").read_text().strip(), 0),
             int((p / "size").read_text().strip(), 0)]
            for p in sorted((uio_root / "maps").glob("map*"))]
    irq = [line for line in (guard.PROC / "interrupts").read_text().splitlines()
           if line.split() and line.split()[-1] == "fabric"]
    require(len(irq) == 1, "FABRIC_IRQ_TOPOLOGY_CHANGED")
    counters = [int(v) for v in irq[0].split()[1:3]]
    require(len(counters) == 2, "FABRIC_IRQ_CPU_COUNT_CHANGED")
    uio = dict(uio=uio_root.name, driver=driver, maps=maps,
               runtime=(device / "power/runtime_status").read_text().strip(),
               irq_counts=counters)
    original = one_shot.manager_last_load()
    services = one_shot.service_snapshot()
    before = check_exact(passive=passive, uio=uio,
                         approval=approval, scope=scope,
                         original_manager_load=original,
                         service_snapshot=services)
    # Refresh boot after all reads; a transient scan must not qualify.
    require((guard.PROC / "sys/kernel/random/boot_id").read_text().strip()
            == before["target_boot_id"], "BOOT_CHANGED_AFTER_RISK_SCAN")
    return before
