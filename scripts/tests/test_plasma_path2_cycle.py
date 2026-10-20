#!/usr/bin/env python3
"""GitHub-hosted tests: independent Path 2 triggers; no device access."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_path2_cycle as cycle
import plasma_development_dispatch as dispatch

SHA = "a" * 40
REGISTRY = ROOT / "specs/engineering-dispatch/development-tasks-v1.json"


def approval(task_id):
    return {"task_id": task_id, "execution_path": "path2-cli",
            "execution_capability": cycle.CAPABILITIES[cycle.STAGE_TASKS[task_id]],
            "pinned_sha": SHA, "trusted_sha": SHA, "pr_number": 0}


def built():
    return {"status": cycle.BUILD_PASS, "source_sha": SHA,
            "physical_load": "NOT_RUN", "z2_hil": "NOT_RUN",
            "bit_sha256": "b" * 64, "hwh_sha256": "c" * 64}


def loaded():
    return {"stage": "DOWNLOAD", "source_sha": SHA, "outcome": "PASS",
            "session_id": "offline-fixture", "boot_id": "test-boot",
            "restore_lease_active": True, "candidate_image_verified": True}


class IndependentTriggerContracts(unittest.TestCase):
    def test_registry_and_owner_admission(self):
        reg = json.loads(REGISTRY.read_text())
        for task_id, stage in (("z2-path2-download", "DOWNLOAD"),
                               ("z2-path2-testing", "TESTING")):
            self.assertEqual(dispatch.task_by_id(reg, task_id)["stage"], stage)
            event = {"action": "created", "issue": {"number": 981},
                     "comment": {"id": 123, "user": {"login": "physicslu"},
                                 "body": "/plasma-dispatch run " + task_id + " 981"},
                     "sender": {"login": "physicslu"},
                     "repository": {"full_name": "physicslu/plasma"}}
            ctx = {"GITHUB_EVENT_NAME": "issue_comment",
                   "GITHUB_ACTOR": "physicslu",
                   "GITHUB_REPOSITORY": "physicslu/plasma",
                   "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": SHA,
                   "GITHUB_RUN_ATTEMPT": "1"}
            self.assertEqual(dispatch.authorize(event, ctx, reg)["execution_capability"],
                             "z2-development-cycle")
            with self.assertRaises(dispatch.Denied):
                dispatch.authorize(event, dict(ctx, GITHUB_RUN_ATTEMPT="2"), reg)
            with self.assertRaises(dispatch.Denied):
                dispatch.authorize(event, dict(ctx, GITHUB_ACTOR="intruder"), reg)

    def test_reject_arbitrary_stage(self):
        reg = json.loads(REGISTRY.read_text())
        for field, value in (("stage", "BUILD"),
                             ("project", "pl/projects/bad"),
                             ("script", "scripts/evil.py")):
            bad = copy.deepcopy(reg)
            bad["tasks"]["z2-path2-download"][field] = value
            with self.subTest(field=field), self.assertRaises(dispatch.Denied):
                dispatch.task_by_id(bad, "z2-path2-download")

    def test_build_trigger_does_not_download_or_test(self):
        download, testing = Mock(), Mock()
        with tempfile.TemporaryDirectory() as tmp:
            report = cycle.run_stage(
                task_id="fixed-site1-vivado-host-build",
                approval=approval("fixed-site1-vivado-host-build"),
                evidence_dir=Path(tmp), build=built,
                download=download, testing=testing)
            self.assertEqual(report["stage"], "BUILD")
            self.assertEqual(report["outcome"], "PASS")
            self.assertFalse(report["next_stage_triggered"])
            self.assertEqual(report["physical_execution"], "NOT_RUN")
            self.assertEqual(json.loads(
                (Path(tmp) / "plasma-path2-build.json").read_text()), report)
            download.assert_not_called()
            testing.assert_not_called()

    def test_download_trigger_stops_without_backend(self):
        testing = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(cycle.StageDenied, "STAGE_LIVE_DOWNLOAD_BACKEND_UNAVAILABLE"):
                cycle.run_stage(task_id="z2-path2-download",
                                approval=approval("z2-path2-download"),
                                evidence_dir=Path(tmp), previous=built())
            report = cycle.run_stage(
                task_id="z2-path2-download",
                approval=approval("z2-path2-download"),
                evidence_dir=Path(tmp), previous=built(),
                hardware_authorized=True, download=loaded, testing=testing)
            self.assertEqual(report["stage"], "DOWNLOAD")
            self.assertFalse(report["next_stage_triggered"])
            testing.assert_not_called()

    def test_testing_trigger_stops_and_requires_verified_restore(self):
        build, download = Mock(), Mock()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(cycle.StageDenied, "STAGE_LIVE_TEST_BACKEND_UNAVAILABLE"):
                cycle.run_stage(task_id="z2-path2-testing",
                                approval=approval("z2-path2-testing"),
                                evidence_dir=Path(tmp), previous=loaded())
            report = cycle.run_stage(
                task_id="z2-path2-testing",
                approval=approval("z2-path2-testing"),
                evidence_dir=Path(tmp), previous=loaded(),
                hardware_authorized=True,
                testing=lambda: {"identity": "PASS", "restore": "PASS",
                                 "restoration_verified": "PASS"},
                build=build, download=download)
            self.assertEqual(report["stage"], "TESTING")
            self.assertTrue(report["restoration_verified"])
            self.assertFalse(report["next_stage_triggered"])
            build.assert_not_called()
            download.assert_not_called()

    def test_tampered_receipts_and_failed_restore_are_denied(self):
        action = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(cycle.StageDenied, "STAGE_BUILD_EVIDENCE_DENIED"):
                cycle.run_stage(
                    task_id="z2-path2-download", approval=approval("z2-path2-download"),
                    evidence_dir=Path(tmp), previous=dict(built(), source_sha="f" * 40),
                    hardware_authorized=True, download=action)
            with self.assertRaisesRegex(cycle.StageDenied, "STAGE_DOWNLOAD_EVIDENCE_DENIED"):
                cycle.run_stage(
                    task_id="z2-path2-testing", approval=approval("z2-path2-testing"),
                    evidence_dir=Path(tmp),
                    previous=dict(loaded(), restore_lease_active=False),
                    hardware_authorized=True, testing=action)
            with self.assertRaisesRegex(cycle.StageDenied, "STAGE_TEST_OR_RESTORE_UNKNOWN"):
                cycle.run_stage(
                    task_id="z2-path2-testing", approval=approval("z2-path2-testing"),
                    evidence_dir=Path(tmp), previous=loaded(),
                    hardware_authorized=True, testing=lambda: {
                        "identity": "PASS", "restore": "FAIL",
                        "restoration_verified": "UNKNOWN"})
            action.assert_not_called()
            self.assertFalse((Path(tmp) / "plasma-path2-testing.json").exists())

    def test_build_autodownload_optional_only(self):
        events = []
        def stub_build():
            events.append("BUILD")
            return built()
        def stub_download():
            events.append("DOWNLOAD")
            return loaded()
        test = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            auth = dict(approval("fixed-site1-vivado-host-build"),
                        auto_download=True, auto_testing=False)
            result = cycle.run_stage(
                task_id="fixed-site1-vivado-host-build", approval=auth,
                evidence_dir=Path(tmp), build=stub_build,
                download=stub_download, testing=test,
                hardware_authorized=True)
            self.assertEqual(events, ["BUILD", "DOWNLOAD"])
            self.assertTrue(result["next_stage_triggered"])
            self.assertEqual(result["completed_stages"],
                             {"BUILD": "PASS", "DOWNLOAD": "PASS"})
            test.assert_not_called()

    def test_download_autotesting_optional_only(self):
        events = []
        def stub_download():
            events.append("DOWNLOAD")
            return loaded()
        def stub_test():
            events.append("TESTING")
            return {"identity": "PASS", "restore": "PASS",
                    "restoration_verified": "PASS"}
        with tempfile.TemporaryDirectory() as tmp:
            auth = dict(approval("z2-path2-download"), auto_testing=True)
            result = cycle.run_stage(
                task_id="z2-path2-download", approval=auth,
                evidence_dir=Path(tmp), previous=built(),
                download=stub_download, testing=stub_test,
                hardware_authorized=True)
            self.assertEqual(events, ["DOWNLOAD", "TESTING"])
            self.assertEqual(result["completed_stages"],
                             {"DOWNLOAD": "PASS", "TESTING": "PASS"})
            self.assertTrue(result["next_stage_triggered"])

    def test_build_both_optional_transitions(self):
        events = []
        def make(stage, result):
            def callback():
                events.append(stage)
                return result
            return callback
        with tempfile.TemporaryDirectory() as tmp:
            auth = dict(approval("fixed-site1-vivado-host-build"),
                        auto_download=True, auto_testing=True)
            result = cycle.run_stage(
                task_id="fixed-site1-vivado-host-build", approval=auth,
                evidence_dir=Path(tmp), build=make("BUILD", built()),
                download=make("DOWNLOAD", loaded()),
                testing=make("TESTING",
                             {"identity": "PASS", "restore": "PASS",
                              "restoration_verified": "PASS"}),
                hardware_authorized=True)
            self.assertEqual(events, ["BUILD", "DOWNLOAD", "TESTING"])
            self.assertEqual(result["outcome"], "PASS")
            self.assertTrue(result["restoration_verified"])

    def test_opt_ins_cannot_skip_download_or_bypass_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            action = Mock()
            bad = dict(approval("fixed-site1-vivado-host-build"),
                       auto_testing=True)
            with self.assertRaisesRegex(cycle.StageDenied,
                                        "STAGE_OPTION_SCOPE_DENIED"):
                cycle.run_stage(task_id="fixed-site1-vivado-host-build",
                                approval=bad, evidence_dir=Path(tmp),
                                build=action, testing=action,
                                hardware_authorized=True)
            auth = dict(approval("fixed-site1-vivado-host-build"),
                        auto_download=True, auto_testing=True)
            with self.assertRaisesRegex(cycle.StageDenied,
                                        "STAGE_LIVE_DOWNLOAD_BACKEND_UNAVAILABLE"):
                cycle.run_stage(
                    task_id="fixed-site1-vivado-host-build", approval=auth,
                    evidence_dir=Path(tmp), build=action, download=action,
                    testing=action, hardware_authorized=False)
            action.assert_not_called()

    def test_authorize_selected_flags_only_for_named_triggers(self):
        reg = json.loads(REGISTRY.read_text())
        ctx = {"GITHUB_EVENT_NAME": "issue_comment",
               "GITHUB_ACTOR": "physicslu",
               "GITHUB_REPOSITORY": "physicslu/plasma",
               "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": SHA,
               "GITHUB_RUN_ATTEMPT": "1"}
        def issue(cmd):
            return {"action": "created", "issue": {"number": 981},
                    "comment": {"id": 123, "user": {"login": "physicslu"},
                                "body": cmd}, "sender": {"login": "physicslu"},
                    "repository": {"full_name": "physicslu/plasma"}}
        cases = [
            ("fixed-site1-vivado-host-build --auto-download", True, False),
            ("fixed-site1-vivado-host-build --auto-download --auto-testing",
             True, True),
            ("z2-path2-download --auto-testing", False, True),
            ("z2-path2-download", False, False)]
        for name, expected_dl, expected_test in cases:
            command = "/plasma-dispatch run " + name + " 981"
            with self.subTest(command=command):
                result = dispatch.authorize(issue(command), ctx, reg)
                self.assertIs(result["auto_download"], expected_dl)
                self.assertIs(result["auto_testing"], expected_test)
        for name in [
                "fixed-site1-vivado-host-build --auto-testing",
                "z2-path2-download --auto-download",
                "z2-path2-testing --auto-testing",
                "nine-nine-path2 --auto-download",
                "fixed-site1-vivado-host-build --auto-download --auto-download",
                "fixed-site1-vivado-host-build --auto-testing --auto-download"]:
            command = "/plasma-dispatch run " + name + " 981"
            with self.subTest(invalid=command), self.assertRaises(
                    dispatch.Denied):
                dispatch.authorize(issue(command), ctx, reg)

    def test_cross_stage_approval_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(cycle.StageDenied, "STAGE_APPROVAL_DENIED"):
                cycle.run_stage(task_id="z2-path2-download",
                                approval=approval("z2-path2-testing"),
                                evidence_dir=Path(tmp))


if __name__ == "__main__":
    unittest.main()
