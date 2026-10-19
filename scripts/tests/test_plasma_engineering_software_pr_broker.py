#!/usr/bin/env python3
"""Token-free trusted-publisher *simulation* tests for Issue #981."""
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
import plasma_engineering_software_pr_broker as broker

FIXTURE = ROOT / "specs/engineering-dispatch/examples/software-pr-issue981-offline-pilot.json"
POLICY = ROOT / "specs/engineering-dispatch/capabilities-v1.json"
WF = ROOT / ".github/workflows/plasma-engineering-software-pr-pilot-contract.yml"


class BrokerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.order = json.loads(FIXTURE.read_text())
        cls.policy = json.loads(POLICY.read_text())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.artifacts = Path(self.temp.name) / "artifacts"
        self.artifacts.mkdir()
        self.receipt = pilot.simulate(self.order, self.policy, self.artifacts)
        self.patch = (self.artifacts / "candidate.patch").read_bytes()

    def verify(self, receipt=None, patch=None, order=None):
        return broker.verify_handoff(order if order is not None else self.order,
                                     self.policy,
                                     receipt if receipt is not None else self.receipt,
                                     patch if patch is not None else self.patch)

    def test_valid_receipt_constructs_inert_proposal(self):
        proposal = self.verify()
        self.assertEqual(proposal["files"], [pilot.TARGET])
        self.assertEqual(proposal["base"], "main")
        self.assertEqual(proposal["reviewed_main_sha"], self.order["reviewed_main_sha"])
        self.assertFalse(proposal["publication_enabled"])
        self.assertFalse(proposal["github_write_credential_present"])

    def test_in_memory_fake_branch_and_pr_once(self):
        proposal = self.verify()
        fake = broker.MockPublisher()
        result = fake.publish(proposal)
        self.assertEqual(result["status"], "MOCK_PR_CREATED_IN_MEMORY_ONLY")
        self.assertEqual(result["mock_pr_count"], 1)
        self.assertEqual(len(fake.branches), 1)
        self.assertEqual(len(fake.prs), 1)
        self.assertFalse(result["github_pr_created"])
        with self.assertRaisesRegex(core.ContractDenied, "MOCK_PUBLISHER_REPLAY_DENIED"):
            fake.publish(proposal)

    def test_mock_receipt_artifact_no_live_pr(self):
        result = broker.publish_bundle(self.order, self.policy, self.artifacts)
        self.assertEqual(result["mock_receipt"]["mock_pr_count"], 1)
        self.assertFalse(result["github_pr_created"])
        self.assertTrue((self.artifacts / "mock-publisher-receipt.json").is_file())
        with self.assertRaises(FileExistsError):
            broker.publish_bundle(self.order, self.policy, self.artifacts)

    def test_patch_mutation_denied(self):
        with self.assertRaisesRegex(core.ContractDenied, "BROKER_PATCH_MISMATCH"):
            self.verify(patch=self.patch + b"payload")

    def test_sha256_forgery_denied(self):
        bad = dict(self.receipt, patch_sha256="0"*64)
        with self.assertRaisesRegex(core.ContractDenied, "BROKER_PATCH_MISMATCH"):
            self.verify(receipt=bad)

    def test_work_order_mutation_denied(self):
        order = copy.deepcopy(self.order)
        order["objective"] += " changed!"
        with self.assertRaisesRegex(core.ContractDenied, "BROKER_CANDIDATE_PROVENANCE_DENIED"):
            self.verify(order=order)

    def test_additional_file_in_receipt_denied(self):
        bad = dict(self.receipt, changed_files=[pilot.TARGET, "scripts/hack.sh"])
        with self.assertRaisesRegex(core.ContractDenied, "BROKER_CANDIDATE_PROVENANCE_DENIED"):
            self.verify(receipt=bad)

    def test_extra_receipt_property_denied(self):
        bad = dict(self.receipt, root_token="secret")
        with self.assertRaisesRegex(core.ContractDenied, "BROKER_RECEIPT_FIELDS_DENIED"):
            self.verify(receipt=bad)

    def test_false_attestation_denied(self):
        for name in ("real_codex_executed", "owner_approval_verified",
                     "hardware_access_verified", "os_sandbox_isolation_verified",
                     "credential_isolation_verified", "github_claim_created",
                     "github_pr_created", "publisher_enabled", "runtime_enabled"):
            bad = dict(self.receipt)
            bad[name] = True
            with self.subTest(name=name):
                with self.assertRaisesRegex(core.ContractDenied, "BROKER_PRIVILEGE_ESCALATION_DENIED"):
                    self.verify(receipt=bad)

    def test_missing_actual_tests_denied(self):
        bad = dict(self.receipt, trusted_fixture_test="SKIPPED")
        with self.assertRaisesRegex(core.ContractDenied, "BROKER_CANDIDATE_PROVENANCE_DENIED"):
            self.verify(receipt=bad)

    def test_no_credential_or_actual_github_api(self):
        text = (ROOT / "scripts/plasma_engineering_software_pr_broker.py").read_text()
        self.assertNotIn("urllib.request", text)
        self.assertNotIn("subprocess.run", text)
        self.assertNotIn("GITHUB_TOKEN", text)
        workflow = WF.read_text()
        self.assertIn("python3 scripts/tests/test_plasma_engineering_software_pr_broker.py", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("issue_comment:", workflow)

    def test_mock_publisher_forged_capability_rejected(self):
        proposed = self.verify()
        for field, value in (("publication_enabled", True),
                             ("github_write_credential_present", True),
                             ("actual_github_pr_created", True),
                             ("files", ["AGENTS.md"]),
                             ("base", "production"),
                             ("head", "main")):
            bad = dict(proposed)
            bad[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(core.ContractDenied, "MOCK_PUBLISHER_SCOPE_DENIED"):
                    broker.MockPublisher().publish(bad)

    def test_candidate_artifact_tamper_on_disk_denied(self):
        (self.artifacts / "candidate.patch").write_bytes(self.patch + b"rogue")
        with self.assertRaisesRegex(core.ContractDenied, "BROKER_PATCH_MISMATCH"):
            broker.publish_bundle(self.order, self.policy, self.artifacts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
