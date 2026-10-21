"""One Z2 Site1 F1-B development experiment; three explicit local triggers.

Target-only root-owned command. This is NOT a Github-hosted HIL runner and
not an automatically registered Dispatcher provider. Fixed firmware hashes,
shared FPGA flock, fsynced lease before FPGA writes, isolated read-only child,
and one checked restore. The owner accepts AXI UNPROVEN risk *only* for this
exact single experiment. Never auto-run a subsequent stage.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

from pl.hil import f1b, path2_f1b_dev_risk as risk
from pl.hil import path2_z2_target_guard as guard
from pl.hil.swd04 import one_shot
from scripts import plasma_path2_persistent_lease as lease

ROOT = Path(__file__).resolve().parents[2]
LEDGER = one_shot.OWNER_DIR / "path2-f1b-site1.json"
CANDIDATE = guard.FIRMWARE / "plasma-f1b-owner-20261020-once.bin"
RECOVERY = guard.FIRMWARE / "base.bin"
CHILD = one_shot.OWNER_DIR / "path2-f1b-identity.json"
LEASE_ID = "z2-f1b-site1-once"
TARGET_ID = "z2-site1"
OWNER_ID = "root-z2-f1b"
SCOPE = risk.ALLOWED[0]


class LiveStageDenied(ValueError):
    pass


def need(value: bool, reason: str) -> None:
    if not value:
        raise LiveStageDenied(reason)


def digest(data: object) -> str:
    """Evidence binding, *not* cryptographic attestation of live PL bits."""
    return hashlib.sha256(json.dumps(data, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def native_runtime_preflight(*, version=None, machine=None,
                             endian=None, executable=None) -> None:
    """Fast first-principles ABI check before *any* FPGA Manager write."""
    actual_version = tuple(sys.version_info[:3]) if version is None else tuple(version)
    actual_machine = platform.machine() if machine is None else machine
    actual_endian = sys.byteorder if endian is None else endian
    actual_exe = sys.executable if executable is None else executable
    need(actual_version == (3, 12, 13) and actual_machine == "armv7l"
         and actual_endian == "little"
         and Path(actual_exe).resolve().is_relative_to(
             "/opt/plasma/python/3.12.13"),
         "NATIVE_ARMV7_PYTHON_RUNTIME_REQUIRED")


def trusted_local() -> None:
    need(os.geteuid() == 0, "ROOT_REQUIRED")
    need(os.environ.get("PLASMA_DEV_RISK_ACK") == risk.WAIVER,
         "EXPLICIT_SINGLE_EXPERIMENT_RISK_ACK_REQUIRED")
    native_runtime_preflight()
    # Never run an unreviewed PR checkout as root: code deployment and route
    # ownership are independent obligations of the hardware operator.
    for p in (ROOT, Path(__file__).resolve(),
              ROOT / "pl/hil/path2_f1b_dev_risk.py",
              ROOT / "pl/hil/path2_z2_target_guard.py",
              ROOT / "scripts/plasma_path2_persistent_lease.py"):
        one_shot.protected(p, file=p != ROOT)
    one_shot.protected(one_shot.OWNER_DIR, file=False)


def snapshot(port: guard.RootZ2TargetPort, *, image: str) -> dict:
    need(image in ("base.bin", CANDIDATE.name), "IMAGE_NOT_PINNED")
    actual = risk.collect_live(root_port=port, approval=risk.WAIVER,
                               scope=SCOPE, expected_firmware=image)
    need(actual["target_boot_id"] and actual["site"] == 1,
         "TARGET_OR_BOOT_NOT_ESTABLISHED")
    return actual


def observation(now: int, record: dict, *, image: str, report: dict) -> dict:
    """Manager log + immutable bytes; accepted Dev risk, NOT FPGA bit proof."""
    need(record["boot_id"] == report["target_boot_id"],
         "TARGET_BOOT_CHANGED")
    need(image == report["expected_manager_firmware"],
         "CURRENT_MANAGER_LOAD_MISMATCH")
    return dict(observed_at=now, target_id=record["target_id"],
                boot_id=record["boot_id"],
                image_sha256=(f1b.BASE_SHA if image == "base.bin" else f1b.BIN_SHA),
                manager_state="operating",
                owner_evidence_sha256=digest(report),
                axi_admission="SEPARATELY_AUTHORIZED")


def risk_report(port, image: str) -> dict:
    report = snapshot(port, image=image)
    need(port.image_sha256("candidate") == f1b.BIN_SHA and
         port.image_sha256("recovery") == f1b.BASE_SHA,
         "FIRMWARE_BYTES_CHANGED")
    return report


def intent_for(report: dict, now: int) -> dict:
    keys = ("target_boot_id", "source_sha", "bin_sha256", "recovery_sha256",
            "current_uio", "development_exception")
    restore_claim = digest({k: report[k] for k in keys} | {"created_at": now})
    return dict(lease_id=LEASE_ID, target_id=TARGET_ID,
                profile_id="f1b-site1-v1", source_sha=f1b.SOURCE,
                artifact_sha256=f1b.BIN_SHA, recovery_sha256=f1b.BASE_SHA,
                boot_id=report["target_boot_id"], owner_id=OWNER_ID,
                restore_intent_sha256=restore_claim,
                services_sha256=digest(one_shot.service_snapshot()),
                uio_sha256=digest(one_shot.uio_snapshot()),
                lease_seconds=900)


def mark_unknown(store: lease.LeaseLedger, *, reason: str) -> None:
    if not store.path.exists():
        return
    previous = store.snapshot()
    if previous["status"] not in ("RESTORED_VERIFIED",
                                   "UNKNOWN_MANUAL_RECOVERY"):
        store.advance("mark_unknown", max(int(time.time()),
                      previous["last_seen"]), expected_revision=previous["revision"],
                      evidence={"reason": reason})


def run(stage: str) -> dict:
    need(stage in ("download", "test", "restore"), "STAGE_NOT_ALLOWLISTED")
    trusted_local()
    port = guard.RootZ2TargetPort(candidate=CANDIDATE,
                                  recovery=RECOVERY, ledger=LEDGER)
    store = lease.LeaseLedger(LEDGER)
    with port.exclusive():
        if stage == "download":
            need(not LEDGER.exists() and not LEDGER.is_symlink(),
                 "SINGLE_EXPERIMENT_ALREADY_CLAIMED")
            report = risk_report(port, "base.bin")
            at = port.now()
            intent = intent_for(report, at)
            created = store.initialize(intent, at)  # fsync before hardware
            try:
                claimed = store.advance(
                    "claim_load", at, expected_revision=created["revision"],
                    facts=observation(at, created, image="base.bin", report=report))
                # A command that may touch FPGA happens only after durable claim.
                one_shot.manager_write(CANDIDATE.name)
                report2 = risk_report(port, CANDIDATE.name)
                at2 = port.now()
                load_receipt = digest({"image": f1b.BIN_SHA,
                                       "observed": report2, "lease": LEASE_ID})
                confirmed = store.advance(
                    "confirm_load", at2, expected_revision=claimed["revision"],
                    facts=observation(at2, claimed, image=CANDIDATE.name,
                                      report=report2),
                    evidence={"lease_id": LEASE_ID,
                              "load_evidence_sha256": load_receipt,
                              "restore_intent_sha256": intent["restore_intent_sha256"]})
            except BaseException:
                mark_unknown(store, reason="DOWNLOAD_UNKNOWN_MANUAL_RECOVERY")
                raise
            return {"stage": "download", "result": "LOADED_AND_HELD",
                    "lease_id": LEASE_ID, "revision": confirmed["revision"],
                    "axi_isolation": "UNPROVEN_ACCEPTED_DEV_RISK",
                    "auto_test": False}

        record = store.snapshot()
        need(record["status"] == "LOADED_AND_HELD" and
             record["lease_id"] == LEASE_ID and
             record["artifact_sha256"] == f1b.BIN_SHA and
             record["recovery_sha256"] == f1b.BASE_SHA and
             record["load_attempts"] == 1 and record["restore_attempts"] == 0,
             "HELD_LEASE_OR_ATTEMPTS_CHANGED")
        at = port.now()
        need(at < record["lease_deadline"] and at >= record["last_seen"],
             "LEASE_EXPIRED_MANUAL_REVIEW")
        report = risk_report(port, CANDIDATE.name)
        current = observation(at, record, image=CANDIDATE.name, report=report)
        if stage == "test":
            need(record["test_attempts"] == 0 and not CHILD.exists(),
                 "SECOND_IDENTITY_TEST_DENIED")
            claimed = store.advance("claim_test", at,
                                    facts=current,
                                    expected_revision=record["revision"])
            try:
                # Child may SIGBUS or stall: supervisor must reap before
                # allowing any subsequent FPGA Manager write.
                one_shot.run_child([sys.executable, "-m",
                                    "pl.hil.path2_f1b_minimal_stage",
                                    "--identity-child"])
                data = json.loads(CHILD.read_text())
                need(data == {"observed": {str(k): v for k, v in
                                          f1b.IDENTITY.items()}},
                     "THREE_READ_IDENTITY_MISMATCH")
                report2 = risk_report(port, CANDIDATE.name)
                at2 = port.now()
                receipt = digest({"readback": data, "lease": LEASE_ID})
                completed = store.advance(
                    "confirm_test", at2, expected_revision=claimed["revision"],
                    facts=observation(at2, claimed, image=CANDIDATE.name,
                                      report=report2),
                    evidence={"lease_id": LEASE_ID,
                              "load_evidence_sha256": record["load_evidence_sha256"],
                              "test_evidence_sha256": receipt,
                              "observed": data["observed"], "read32": 3,
                              "write32": 0, "native_readonly": True})
            except BaseException:
                mark_unknown(store, reason="TEST_UNKNOWN_MANUAL_RECOVERY")
                raise
            return {"stage": "test", "result": "IDENTITY_PASS",
                    "read32_count": 3, "write32_count": 0,
                    "lease_id": LEASE_ID, "revision": completed["revision"],
                    "auto_restore": False}

        # Restore only after one verified native three-read Test; a failed
        # child, SIGBUS, unreaped process or expired lease forbids blind reload.
        need(record["test_attempts"] == 1 and
             lease.digest(record["test_evidence_sha256"]),
             "TEST_NOT_VERIFIED_RESTORE_DENIED")
        need(digest(one_shot.service_snapshot()) == record["services_sha256"]
             and digest(one_shot.uio_snapshot()) == record["uio_sha256"],
             "RESTORE_BASELINE_CHANGED")
        claim = store.advance("claim_restore", at,
                              facts=current, expected_revision=record["revision"])
        try:
            one_shot.manager_write(RECOVERY.name)
            restored = risk_report(port, "base.bin")
            need(digest(one_shot.service_snapshot()) == record["services_sha256"]
                 and digest(one_shot.uio_snapshot()) == record["uio_sha256"],
                 "RESTORE_ENVIRONMENT_CHANGED")
            at2 = port.now()
            evidence = digest({"image": f1b.BASE_SHA,
                               "observed": restored, "lease": LEASE_ID})
            done = store.advance(
                "confirm_restore", at2, expected_revision=claim["revision"],
                facts=observation(at2, claim, image="base.bin",
                                  report=restored),
                evidence={"lease_id": LEASE_ID,
                          "restore_evidence_sha256": evidence,
                          "services_sha256": record["services_sha256"],
                          "uio_sha256": record["uio_sha256"]})
        except BaseException:
            mark_unknown(store, reason="RESTORE_UNKNOWN_MANUAL_RECOVERY")
            raise
        return {"stage": "restore", "result": "RESTORED_VERIFIED",
                "lease_id": LEASE_ID, "revision": done["revision"]}


def child_main() -> int:
    # Never permit the standalone child to authorize its own FPGA write.
    trusted_local()
    record = lease.LeaseLedger(LEDGER).snapshot()
    need(record["status"] == "TEST_IN_FLIGHT" and
         record["test_attempts"] == 1 and not CHILD.exists(),
         "IDENTITY_CHILD_NOT_CLAIMED")
    need(record["boot_id"] ==
         (guard.PROC / "sys/kernel/random/boot_id").read_text().strip() and
         ": writing " + CANDIDATE.name + " to " in
         one_shot.manager_last_load(), "IDENTITY_IMAGE_NOT_CURRENT")
    # Match the earlier real Z2 one-shot backend: import the reviewed MMIO
    # module by fixed path, without depending on a PYNQ/package installation.
    import importlib.util
    # Reuse the already checked root runtime; no alternate package import.
    native_runtime_preflight()
    reviewed = ROOT / "software/python/plasma_interfaces/linux_mmio.py"
    one_shot.protected(reviewed)
    spec = importlib.util.spec_from_file_location("f1b_path2_native_mmio",
                                                  reviewed)
    need(spec is not None and spec.loader is not None,
         "NATIVE_MMIO_DRIVER_NOT_INSTALLED")
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver
    spec.loader.exec_module(driver)
    aperture = driver.MMIOAperture(f1b.BASE, frozenset(f1b.IDENTITY),
                                   frozenset(), f1b.LENGTH)
    with driver.LinuxMMIO((aperture,), readonly=True) as mmio:
        observed = f1b.read_identity(mmio.read32)
        need(mmio.stats().read32 == 3 and mmio.stats().write32 == 0,
             "NATIVE_MMIO_ACCESS_COUNT_CHANGED")
    one_shot.record_json(CHILD, {"observed": observed})
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    need(len(args) == 1, "ONE_FIXED_STAGE_ARGUMENT_REQUIRED")
    if args[0] == "--identity-child":
        return child_main()
    result = run(args[0])
    print("PLASMA_F1B_PATH2_DEV=" + json.dumps(
        result, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
