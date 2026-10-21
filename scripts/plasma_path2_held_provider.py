"""Path 2 held FPGA Provider transaction core; NO live transport registration.

All side-effect functions are supplied by a separately reviewed, privileged
Z2 target-side Configuration Owner. Imported alone this module does not SSH,
open /dev/mem, invoke FPGA Manager, start a worker, or touch a DUT.

An injected Host-only fake can exercise transitions, but that is NOT hardware
qualification. An unverified JSON flag cannot prove AXI isolation.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol
import re

import plasma_path2_persistent_lease as lease

HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class ProviderDenied(ValueError):
    pass


def need(test: bool, reason: str) -> None:
    if not test:
        raise ProviderDenied(reason)


class TargetPort(Protocol):
    """A *future* reviewed root-owned Z2 implementation; none is registered."""

    def exclusive(self) -> AbstractContextManager: ...
    def now(self) -> int: ...
    def qualification(self, stage: str) -> dict: ...
    def observation(self, observed_at: int) -> dict: ...
    def image_sha256(self, which: str) -> str: ...
    def load_candidate_once(self, bin_sha256: str) -> dict: ...
    def read_f1b_identity_child(self) -> dict: ...
    def restore_original_once(self, recovery_sha256: str) -> dict: ...


QUALIFICATION_FIELDS = {
    "root_route", "target_global_lock", "target_owner_persistent",
    "independent_image_provenance", "bootgen_execution_verified",
    "protected_original_recovery", "complete_proc_visibility",
    "kernel_driver_excluded", "hardware_owner_excluded",
    "axi_idle_isolated", "worker_reaped", "restore_route_verified",
    "trusted_target_clock", "target_id", "boot_id", "owner_id",
    "restore_intent_sha256", "bit_sha256", "bin_sha256",
    "bootgen_evidence_sha256",
}
REQUIRED_BOOLEANS = QUALIFICATION_FIELDS - {
    "target_id", "boot_id", "owner_id", "restore_intent_sha256",
    "bit_sha256", "bin_sha256", "bootgen_evidence_sha256"}


def _admit(port: TargetPort, stage: str, record: dict) -> None:
    """Policy observation must be independently verified by a target owner.

    Even exact booleans are not standalone proof: the unregistered target
    implementation must establish truth from kernel/FPGA/device facts.
    """
    need(stage in ("download", "test", "restore"), "STAGE_DENIED")
    p = port.qualification(stage)
    need(type(p) is dict and set(p) == QUALIFICATION_FIELDS and
         all(p.get(k) is True for k in REQUIRED_BOOLEANS),
         "TARGET_HARDWARE_ISOLATION_UNPROVEN")
    for k in ("target_id", "boot_id", "owner_id", "restore_intent_sha256"):
        need(p[k] == record[k], "TARGET_OWNER_OR_RECOVERY_CHANGED")
    need(type(p["bit_sha256"]) is str and
         HEX64.fullmatch(p["bit_sha256"]) is not None and
         p["bit_sha256"] != record["artifact_sha256"] and
         p["bin_sha256"] == record["artifact_sha256"] and
         type(p["bootgen_evidence_sha256"]) is str and
         HEX64.fullmatch(p["bootgen_evidence_sha256"]) is not None,
         "TARGET_BIT_BIN_PROVENANCE_DENIED")
    return p


def _observe(port: TargetPort, record: dict, bin_hash: str) -> tuple[int, dict]:
    now = port.now()
    lease.tick(now)
    facts = port.observation(now)
    lease.observation(facts, record, now, bin_hash)
    return now, facts


def _incident(store: lease.LeaseLedger, reason: str, now: int) -> None:
    """Best effort persist UNKNOWN; never attempt an automatic reload."""
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,79}", reason):
        reason = "UNEXPECTED_TARGET_EXCEPTION"
    previous = store.snapshot()
    if previous["status"] not in ("UNKNOWN_MANUAL_RECOVERY", "RESTORED_VERIFIED"):
        store.advance("mark_unknown", max(now, previous["last_seen"]),
                      evidence={"reason": reason},
                      expected_revision=previous["revision"])


def download_held(*, store: lease.LeaseLedger, port: TargetPort,
                  intent: dict, provenance: dict) -> dict:
    """One load only; the durable intent and claim precede FPGA writes."""
    need(type(provenance) is dict and
         set(provenance) == {
             "source_sha", "bit_sha256", "hwh_sha256", "bin_sha256",
             "build_qualification_sha256", "bootgen_evidence_sha256",
             "scope", "physical_load"} and
         provenance.get("scope") == "BYTE_EQUIVALENCE_ONLY" and
         provenance.get("physical_load") == "NOT_RUN" and
         provenance.get("source_sha") == intent.get("source_sha") and
         provenance.get("bin_sha256") == intent.get("artifact_sha256") and
         HEX64.fullmatch(provenance.get("bit_sha256", "")) is not None and
         HEX64.fullmatch(provenance.get("hwh_sha256", "")) is not None and
         HEX64.fullmatch(provenance.get("build_qualification_sha256", "")) is not None and
         HEX64.fullmatch(provenance.get("bootgen_evidence_sha256", "")) is not None and
         provenance["bit_sha256"] != provenance["bin_sha256"],
         "BIT_BIN_SOURCE_BINDING_DENIED")
    with port.exclusive():
        # No other record can be overwritten. A previous unknown/expired
        # session always requires separately reviewed manual reconciliation.
        need(not store.path.exists(), "PRIOR_HARDWARE_LEASE_REQUIRES_REVIEW")
        template = lease.create_record(intent, port.now())
        target_claim = _admit(port, "download", template)
        need(target_claim["bit_sha256"] == provenance["bit_sha256"] and
             target_claim["bootgen_evidence_sha256"] ==
             provenance["bootgen_evidence_sha256"],
             "BOOTGEN_OR_BIT_TARGET_BINDING_DENIED")
        need(port.image_sha256("recovery") == intent["recovery_sha256"] and
             port.image_sha256("candidate") == intent["artifact_sha256"],
             "CANDIDATE_OR_RECOVERY_BYTES_CHANGED")
        at, original = _observe(port, template, intent["recovery_sha256"])
        record = store.initialize(intent, at)
        claim = store.advance("claim_load", at, facts=original,
                              expected_revision=record["revision"])
        try:
            execution = port.load_candidate_once(intent["artifact_sha256"])
            need(type(execution) is dict and
                 set(execution) == {"load_evidence_sha256", "restore_intent_sha256"}
                 and HEX64.fullmatch(execution["load_evidence_sha256"]) is not None
                 and execution["restore_intent_sha256"] ==
                 intent["restore_intent_sha256"], "LOAD_RECEIPT_INVALID")
            _admit(port, "download", claim)
            at2, candidate = _observe(port, claim, intent["artifact_sha256"])
            confirmed = store.advance(
                "confirm_load", at2, facts=candidate,
                evidence={"lease_id": intent["lease_id"],
                          "load_evidence_sha256": execution["load_evidence_sha256"],
                          "restore_intent_sha256": intent["restore_intent_sha256"]},
                expected_revision=claim["revision"])
        except BaseException:
            _incident(store, "LOAD_UNCERTAIN_REQUIRES_MANUAL_RECOVERY", at)
            raise
        need(confirmed["status"] == "LOADED_AND_HELD",
             "HELD_IMAGE_NOT_ESTABLISHED")
        # Existing F1-B Adapter requires BIT identity; ledger pins BIN identity.
        return {
            "result": "LOADED", "source_sha": intent["source_sha"],
            "profile_id": intent["profile_id"], "target_id": intent["target_id"],
            "artifact_sha256": provenance["bit_sha256"],
            "lease_id": intent["lease_id"], "boot_id": intent["boot_id"],
            "load_evidence_sha256": execution["load_evidence_sha256"],
            "restore_intent_sha256": intent["restore_intent_sha256"],
            "manager_state": "operating", "image_state": "LOADED_AND_HELD",
        }


def testing_held(*, store: lease.LeaseLedger, port: TargetPort,
                 request: dict, bit_sha256: str) -> dict:
    """Independent Trigger: *fresh* actual target facts are mandatory."""
    with port.exclusive():
        record = store.snapshot()
        trusted_claim = _admit(port, "test", record)
        need(type(bit_sha256) is str and
             HEX64.fullmatch(bit_sha256) is not None and
             bit_sha256 == trusted_claim["bit_sha256"],
             "TEST_BIT_BIN_IDENTITY_DENIED")
        at, facts = _observe(port, record, record["artifact_sha256"])
        lease.require_testing(record, request, facts, at)
        claim = store.advance("claim_test", at, facts=facts,
                              expected_revision=record["revision"])
        try:
            test = port.read_f1b_identity_child()
            need(type(test) is dict and set(test) == {
                    "observed", "read32", "write32", "native_readonly",
                    "worker_reaped", "timed_out", "returncode", "evidence_sha256"}
                 and test["worker_reaped"] is True and
                 test["timed_out"] is False and
                 type(test["returncode"]) is int and test["returncode"] == 0,
                 "NATIVE_CHILD_NOT_REAPED_OR_FAILED")
            lease.test_evidence({
                "lease_id": record["lease_id"],
                "load_evidence_sha256": record["load_evidence_sha256"],
                "test_evidence_sha256": test["evidence_sha256"],
                "observed": test["observed"], "read32": test["read32"],
                "write32": test["write32"],
                "native_readonly": test["native_readonly"]}, record)
            _admit(port, "test", claim)
            at2, confirmed_facts = _observe(
                port, claim, record["artifact_sha256"])
            complete = store.advance("confirm_test", at2,
                facts=confirmed_facts, evidence={
                    "lease_id": record["lease_id"],
                    "load_evidence_sha256": record["load_evidence_sha256"],
                    "test_evidence_sha256": test["evidence_sha256"],
                    "observed": test["observed"], "read32": test["read32"],
                    "write32": test["write32"],
                    "native_readonly": test["native_readonly"]},
                expected_revision=claim["revision"])
        except BaseException:
            _incident(store, "TEST_UNCERTAIN_REQUIRES_MANUAL_RECOVERY", at)
            raise
        need(complete["status"] == "LOADED_AND_HELD", "TEST_LEASE_NOT_HELD")
        # Existing F1-B adapter's live callback returns integer offsets.
        return {
            "result": "IDENTITY_PASS", "source_sha": record["source_sha"],
            "profile_id": record["profile_id"], "target_id": record["target_id"],
            "artifact_sha256": bit_sha256,
            "lease_id": record["lease_id"],
            "load_evidence_sha256": record["load_evidence_sha256"],
            "test_evidence_sha256": test["evidence_sha256"],
            "observed": {int(k): v for k, v in test["observed"].items()},
            "read32_count": test["read32"], "write32_count": test["write32"],
            "native_readonly": True, "image_state": "LOADED_AND_HELD",
        }


def restore_guarded(*, store: lease.LeaseLedger, port: TargetPort) -> dict:
    """One separate Restore Trigger; never unconditional finally-restore."""
    with port.exclusive():
        record = store.snapshot()
        _admit(port, "restore", record)
        need(port.image_sha256("recovery") == record["recovery_sha256"],
             "ORIGINAL_RECOVERY_BYTES_CHANGED")
        at, current = _observe(port, record, record["artifact_sha256"])
        claim = store.advance("claim_restore", at, facts=current,
                              expected_revision=record["revision"])
        try:
            done = port.restore_original_once(record["recovery_sha256"])
            need(type(done) is dict and set(done) == {
                    "restore_evidence_sha256", "services_sha256", "uio_sha256"}
                 and HEX64.fullmatch(done["restore_evidence_sha256"]) is not None
                 and done["services_sha256"] == record["services_sha256"] and
                 done["uio_sha256"] == record["uio_sha256"],
                 "RESTORE_EVIDENCE_INVALID")
            _admit(port, "restore", claim)
            at2, original = _observe(port, claim, record["recovery_sha256"])
            restored = store.advance("confirm_restore", at2,
                facts=original, evidence={
                    "lease_id": record["lease_id"],
                    "restore_evidence_sha256": done["restore_evidence_sha256"],
                    "services_sha256": done["services_sha256"],
                    "uio_sha256": done["uio_sha256"]},
                expected_revision=claim["revision"])
        except BaseException:
            _incident(store, "RESTORE_UNCERTAIN_REQUIRES_MANUAL_RECOVERY", at)
            raise
        need(restored["status"] == "RESTORED_VERIFIED",
             "RESTORE_VERIFICATION_FAILED")
        return {"result": "RESTORED_VERIFIED", "lease_id": record["lease_id"],
                "evidence_sha256": done["restore_evidence_sha256"],
                "firmware_sha256": record["recovery_sha256"]}


def bind_injected_stage_callbacks(*, store: lease.LeaseLedger,
                                  port: TargetPort, intent: dict,
                                  provenance: dict) -> dict:
    """Reuse the existing F1-B Adapter's Download/Testing callback ABI.

    Returns *inert until separately invoked* callables, never registers them
    in the trusted Dispatcher. The caller must supply a reviewed TargetPort;
    user-provided receipts cannot become authority to load hardware.
    """
    def held_download(ctx: dict) -> dict:
        need(type(ctx) is dict and
             ctx.get("stage") == "download" and
             ctx.get("source_sha") == intent["source_sha"] and
             ctx.get("profile_id") == intent["profile_id"] and
             ctx.get("target_id") == intent["target_id"] and
             type(ctx.get("build_receipt")) is dict and
             ctx["build_receipt"].get("status") == "PASS" and
             ctx["build_receipt"].get("stage") == "build" and
             ctx["build_receipt"].get("artifact_sha256") ==
             provenance["bit_sha256"] and
             ctx["build_receipt"].get("evidence_sha256") ==
             provenance["build_qualification_sha256"],
             "UNTRUSTED_BUILD_TO_DOWNLOAD")
        return download_held(store=store, port=port, intent=intent,
                             provenance=provenance)

    def identity_test(ctx: dict) -> dict:
        need(type(ctx) is dict and ctx.get("stage") == "test" and
             ctx.get("source_sha") == intent["source_sha"] and
             ctx.get("profile_id") == intent["profile_id"] and
             ctx.get("target_id") == intent["target_id"] and
             type(ctx.get("load_receipt")) is dict,
             "UNTRUSTED_LOAD_TO_TEST")
        raw = ctx["load_receipt"]
        need(raw.get("artifact_sha256") == provenance["bit_sha256"],
             "LOAD_BIT_IDENTITY_MISMATCH")
        request = {
            "lease_id": raw.get("lease_id"),
            "source_sha": ctx["source_sha"],
            "profile_id": ctx["profile_id"],
            "target_id": ctx["target_id"],
            "artifact_sha256": provenance["bin_sha256"],
            "load_evidence_sha256": raw.get("load_evidence_sha256"),
        }
        return testing_held(store=store, port=port, request=request,
                            bit_sha256=provenance["bit_sha256"])

    return {"held_download": held_download, "identity_test": identity_test}
