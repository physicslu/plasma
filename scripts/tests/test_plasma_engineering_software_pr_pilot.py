#!/usr/bin/env python3
"""Synthetic security/contract tests. No real Codex, GitHub mutations or lab access."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_engineering_dispatch_v1 as core
import plasma_engineering_software_pr_pilot as pilot

FIXTURE = ROOT / "specs/engineering-dispatch/examples/software-pr-issue981-offline-pilot.json"
POLICY = ROOT / "specs/engineering-dispatch/capabilities-v1.json"
WORKFLOW = ROOT / ".github/workflows/plasma-engineering-software-pr-pilot-contract.yml"


class SoftwarePrPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.order = json.loads(FIXTURE.read_text())
        cls.policy = json.loads(POLICY.read_text())

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name) / "isolated"
        self.out = Path(self.t.name) / "artifacts"
        self.out.mkdir()

    def order_copy(self):
        return copy.deepcopy(self.order)

    def candidate(self):
        baseline = pilot.seed_fixture(self.root)
        pilot.fake_codex_write(self.root)
        return baseline

    def denied(self, expected, order=None, policy=None, base=None, exit_code=0,
               tests_success=True):
        with self.assertRaises(core.ContractDenied) as error:
            pilot.candidate_receipt(
                order or self.order, policy or self.policy, self.root,
                base if base is not None else pilot.sha256(pilot.BASE),
                exit_code, tests_success)
        self.assertEqual(str(error.exception), expected)

    def test_01_admit_remains_offline_hardware_free(self):
        plan = pilot.admit(self.order, self.policy)
        self.assertEqual(plan["executor"], "FAKE_CODEX_OFFLINE_ONLY")
        self.assertFalse(plan["owner_approval_verified"])
        self.assertFalse(plan["runtime_enabled"])
        self.assertEqual(plan["reviewed_main_sha"], self.order["reviewed_main_sha"])

    def test_02_fake_change_to_broker_candidate_passes(self):
        baseline = self.candidate()
        receipt, patch = pilot.candidate_receipt(
            self.order, self.policy, self.root, baseline, 0, True)
        self.assertEqual(receipt["status"], pilot.ACCEPTED)
        self.assertIn(b"-Status: PENDING", patch)
        self.assertIn(b"+Status: VERIFIED", patch)
        self.assertEqual(receipt["changed_files"], [pilot.TARGET])
        self.assertEqual(receipt["patch_sha256"], hashlib.sha256(patch).hexdigest())
        self.assertFalse(receipt["real_codex_executed"])
        self.assertFalse(receipt["github_pr_created"])
        self.assertFalse(receipt["publisher_enabled"])
        pilot.write_bundle(self.out, receipt, patch)
        sums = (self.out / "SHA256SUMS").read_text().splitlines()
        self.assertEqual(len(sums), 2)
        for line in sums:
            digest, file_name = line.split("  ")
            self.assertEqual(digest, hashlib.sha256((self.out / file_name).read_bytes()).hexdigest())

    def test_03_cli_simulated_fixture_writes_truthful_bundle(self):
        result = pilot.simulate(self.order, self.policy, self.out)
        self.assertEqual(result["work_order_sha256"], core.digest(self.order))
        self.assertFalse(result["credential_isolation_verified"])
        self.assertFalse(result["os_sandbox_isolation_verified"])
        self.assertFalse(result["github_claim_created"])
        self.assertEqual({p.name for p in self.out.iterdir()},
                         {"candidate-receipt.json", "candidate.patch", "SHA256SUMS"})

    def test_04_model_zero_exit_alone_is_insufficient(self):
        pilot.seed_fixture(self.root)
        self.denied("NO_CHANGE_REJECTED")

    def test_05_nonzero_model_exit_denied(self):
        self.candidate()
        self.denied("FAKE_MODEL_NONZERO", exit_code=1)

    def test_06_missing_trusted_tests_denied(self):
        self.candidate()
        self.denied("TRUSTED_TESTS_NOT_PASSED", tests_success=False)
        self.denied("TRUSTED_TESTS_NOT_PASSED", tests_success=1)

    def test_07_forged_baseline_sha_denied(self):
        self.candidate()
        self.denied("BASELINE_PROVENANCE_MISMATCH", base="0"*64)

    def test_08_unapproved_content_denied(self):
        self.candidate()
        (self.root / pilot.TARGET).write_text("Status: MALICIOUS\n")
        self.denied("UNREVIEWED_CONTENT_REJECTED")

    def test_09_extra_file_denied(self):
        self.candidate()
        (self.root / "unapproved.txt").write_text("bad")
        self.denied("WORKSPACE_UNAPPROVED_FILE")

    def test_10_extra_nested_directory_denied(self):
        self.candidate()
        (self.root / "secrets").mkdir()
        self.denied("WORKSPACE_UNEXPECTED_DIRECTORY")

    def test_11_symlink_file_denied(self):
        self.candidate()
        target = self.root / pilot.TARGET
        target.unlink()
        target.symlink_to(self.out / "secret")
        self.denied("WORKSPACE_SYMLINK_DENIED")

    def test_12_symlink_parent_denied(self):
        self.candidate()
        # Even unused linked directories are not accepted.
        (self.root / "alias").symlink_to(self.out, target_is_directory=True)
        self.denied("WORKSPACE_SYMLINK_DENIED")

    def test_13_binary_denied(self):
        self.candidate()
        (self.root / pilot.TARGET).write_bytes(b"\x00evil")
        self.denied("WORKSPACE_NON_TEXT_OR_OVERSIZED")

    def test_14_oversized_denied(self):
        self.candidate()
        (self.root / pilot.TARGET).write_bytes(b"x"*(pilot.MAX_BYTES+1))
        self.denied("WORKSPACE_FILE_TOO_LARGE")

    def test_15_no_swpc_or_hardware_permissions(self):
        for forbidden in ("usb", "z2", "fpga", "mmio", "dut", "hub-power", "host-root"):
            order = self.order_copy()
            order["scope"]["deny_resources"].remove(forbidden)
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(core.ContractDenied):
                    pilot.admit(order, self.policy)
        for capability in ("z2-readonly", "la2016-loopback", "z2-privileged"):
            order = self.order_copy()
            order["capability"] = capability
            with self.subTest(capability=capability):
                with self.assertRaises(core.ContractDenied):
                    pilot.admit(order, self.policy)

    def test_16_unapproved_path_and_traversal_denied(self):
        for path in ("docs/development", "../secrets", "/etc/passwd",
                     "docs/development/software-pr-pilot/RESULT.md/../../bad"):
            order = self.order_copy()
            order["scope"]["allow_repo_paths"] = [path]
            with self.subTest(path=path):
                with self.assertRaises(core.ContractDenied):
                    pilot.admit(order, self.policy)

    def test_17_policy_runtime_enable_denied(self):
        policy = copy.deepcopy(self.policy)
        policy["capabilities"]["software-pr"]["runtime_enabled"] = True
        with self.assertRaisesRegex(core.ContractDenied, "RUNTIME_DISPATCH_FORBIDDEN_GATE1A"):
            pilot.admit(self.order, policy)

    def test_18_unapproved_work_order_edited_denied(self):
        for key, value in (("issue_number", 982),
                           ("authorization_kind", "hardware-one-shot"),
                           ("entrypoint", "arbitrary-shell")):
            order = self.order_copy()
            order[key] = value
            with self.subTest(field=key):
                with self.assertRaises(core.ContractDenied):
                    pilot.admit(order, self.policy)

    def test_19_untrusted_bundle_target_denied(self):
        self.candidate()
        receipt, patch = pilot.candidate_receipt(
            self.order, self.policy, self.root,
            pilot.sha256(pilot.BASE), 0, True)
        (self.out / "already-there").write_text("old")
        with self.assertRaisesRegex(core.ContractDenied, "BUNDLE_DIRECTORY_UNSAFE_OR_NOT_EMPTY"):
            pilot.write_bundle(self.out, receipt, patch)

    def test_20_no_model_self_report_can_promote_acceptance(self):
        self.candidate()
        (self.root / pilot.TARGET).write_bytes(pilot.EXPECTED + b"Model says tests passed\n")
        self.denied("UNREVIEWED_CONTENT_REJECTED")

    def test_21_hosted_workflow_no_dispatch_or_privileged_runner(self):
        workflow = WORKFLOW.read_text()
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("python3 scripts/tests/test_plasma_engineering_software_pr_pilot.py", workflow)
        for forbidden in ("issue_comment:", "workflow_dispatch:", "schedule:",
                          "self-hosted", "plasma-codex", "contents: write",
                          "pull-requests: write", "secrets.", "sudo "):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, workflow)

    def test_22_fixed_schema_no_runtime_or_pr_publish(self):
        self.candidate()
        receipt, _ = pilot.candidate_receipt(
            self.order, self.policy, self.root, pilot.sha256(pilot.BASE), 0, True)
        self.assertEqual(receipt["schema_version"], pilot.SCHEMA)
        for field in ("real_codex_executed", "owner_approval_verified",
                      "hardware_access_verified", "os_sandbox_isolation_verified",
                      "credential_isolation_verified", "github_claim_created",
                      "github_pr_created", "publisher_enabled", "runtime_enabled"):
            self.assertIs(receipt[field], False, field)
        self.assertIs(receipt["gate2_merge_required"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
