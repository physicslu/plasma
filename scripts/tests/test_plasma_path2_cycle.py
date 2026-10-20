#!/usr/bin/env python3
"""Hosted/offline Path 2 cycle tests. All callbacks are fakes; never touch hardware."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_path2_cycle as cycle
from pl.hil import f1b

SHA = "a" * 40


def approval():
    return {"task_id": cycle.TASK_ID, "execution_path": "path2-cli",
            "execution_capability": "z2-development-cycle",
            "pinned_sha": SHA, "trusted_sha": SHA, "pr_number": 0}


def build_receipt():
    return {"status": cycle.BUILD_PASS, "physical_load": "NOT_RUN",
            "z2_hil": "NOT_RUN"}


def hil_result():
    return {"preflight": "PASS", "candidate_load": "PASS",
            "hil01": "PASS", "hil02": "PASS", "restore": "PASS",
            "restoration_verified": "PASS", "overall": cycle.HIL_PASS}


class CycleContracts(unittest.TestCase):
    def run_case(self, *, build=build_receipt, transaction=None,
                 approved=False):
        with tempfile.TemporaryDirectory() as tmp:
            report = cycle.run_cycle(
                approval=approval(), build=build, evidence_dir=Path(tmp),
                transaction=transaction, live_hardware_approved=approved)
            on_disk = json.loads(
                (Path(tmp) / "plasma-path2-cycle.json").read_text())
            self.assertEqual(report, on_disk)
            return report

    def test_inert_without_live_adapter(self):
        called = []
        report = self.run_case(transaction=lambda: called.append("load"),
                               approved=False)
        self.assertEqual(called, [])
        self.assertEqual(report["stages"], {
            "BUILD": "PASS", "DOWNLOAD": "NOT_RUN",
            "TESTING": "NOT_RUN", "RESTORE": "NOT_RUN"})
        self.assertEqual(report["physical_execution"], "NOT_RUN")

    def test_inert_without_explicit_approved_flag(self):
        report = self.run_case(approved=True)
        self.assertEqual(report["failure"], "HARDWARE_BACKEND_NOT_AUTHORIZED")

    def test_build_failure_never_calls_hardware(self):
        called = []
        def fail():
            raise OSError("simulated failed compile")
        report = self.run_case(build=fail, approved=True,
                               transaction=lambda: called.append("unsafe"))
        self.assertFalse(called)
        self.assertEqual(report["stages"]["BUILD"], "FAIL")
        self.assertEqual(report["stages"]["DOWNLOAD"], "NOT_RUN")

    def test_unverified_build_never_calls_hardware(self):
        called = []
        report = self.run_case(build=lambda: {"status": "PASS"},
                               approved=True,
                               transaction=lambda: called.append("unsafe"))
        self.assertFalse(called)
        self.assertEqual(report["stages"]["BUILD"], "FAIL")

    def test_order_and_success_from_existing_transaction_contract(self):
        seen = []
        def fake_build():
            seen.append("build")
            return build_receipt()
        def fake_transaction():
            seen.append("transaction")
            return hil_result()
        report = self.run_case(build=fake_build, approved=True,
                               transaction=fake_transaction)
        self.assertEqual(seen, ["build", "transaction"])
        self.assertEqual(report["overall"], "PASS")
        self.assertTrue(all(v == "PASS" for v in report["stages"].values()))

    def test_load_failure_does_not_claim_test_pass(self):
        outcome = hil_result()
        outcome.update(candidate_load="NOT_RUN", hil01="NOT_RUN",
                       hil02="NOT_RUN", overall="FAIL_OR_BLOCKED")
        report = self.run_case(approved=True, transaction=lambda: outcome)
        self.assertNotEqual(report["overall"], "PASS")
        self.assertEqual(report["stages"]["TESTING"], "NOT_RUN")

    def test_restore_not_verified_cannot_pass(self):
        outcome = hil_result()
        outcome.update(restore="FAIL_OR_UNKNOWN",
                       restoration_verified="FAIL_OR_UNKNOWN",
                       overall="FAIL_OR_BLOCKED")
        report = self.run_case(approved=True, transaction=lambda: outcome)
        self.assertEqual(report["stages"]["RESTORE"], "UNKNOWN")
        self.assertEqual(report["overall"], "NO_GO")

    def test_sigbus_or_unreaped_child_does_not_retry(self):
        calls = []
        def crash():
            calls.append("load")
            raise RuntimeError("simulated SIGBUS")
        report = self.run_case(approved=True, transaction=crash)
        self.assertEqual(calls, ["load"])
        self.assertEqual(report["stages"]["RESTORE"], "UNKNOWN")
        self.assertEqual(report["failure"], "HIL_RESULT_UNKNOWN")

    def test_source_scope_and_report_reuse_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = approval()
            broken["pinned_sha"] = "b" * 40
            with self.assertRaisesRegex(ValueError, "CYCLE_SOURCE_DENIED"):
                cycle.run_cycle(approval=broken, build=build_receipt,
                                evidence_dir=Path(tmp))
            (Path(tmp) / "plasma-path2-cycle.json").write_text("old")
            with self.assertRaisesRegex(ValueError, "CYCLE_REPORT_ALREADY_EXISTS"):
                cycle.run_cycle(approval=approval(), build=build_receipt,
                                evidence_dir=Path(tmp))

    def test_f1b_transaction_delegates_to_existing_supervised_sequence(self):
        calls = []
        @contextmanager
        def fake_lock(_):
            calls.append("locked")
            yield
        def observe():
            calls.append("observe")
            return object(), "", []
        def intent():
            calls.append("intent")
        def load():
            calls.append("load")
        def identity():
            calls.append("identity")
        def restore():
            calls.append("restore")
        def verify():
            calls.append("verify_restore")
        with patch.object(f1b, "exclusive_session", fake_lock), \
             patch.object(f1b, "admit", lambda *args, **kwargs: None):
            receipt = cycle.f1b_transaction(
                lock_path=Path("/unused/offline"), observe=observe,
                record_intent=intent, load=load, identity=identity,
                restore=restore, verify_restore=verify)
        self.assertEqual(receipt["overall"], cycle.HIL_PASS)
        self.assertEqual(calls, ["locked", "observe", "intent", "load",
                                 "identity", "observe", "restore",
                                 "verify_restore"])

    def test_f1b_admission_fails_closed_without_real_evidence(self):
        evidence = f1b.AdmissionEvidence()
        with self.assertRaises(ValueError):
            f1b.admit(evidence, maps="", fds=[])
        self.assertEqual(f1b.checked_address(0x4000), 0x40004000)
        with self.assertRaises(ValueError):
            f1b.checked_address(0x4001)


if __name__ == "__main__":
    unittest.main()
