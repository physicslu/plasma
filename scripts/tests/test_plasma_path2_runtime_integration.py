#!/usr/bin/env python3
"""Path 2 Runtime Integration Gate 1: GitHub-hosted Host-only contracts."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_development_dispatch as dispatch
import plasma_path2_runtime_integration as runtime
import plasma_path2_build_qualification as qualifier

REGISTRY = ROOT / "specs/engineering-dispatch/development-tasks-v1.json"
WORKFLOW = ROOT / ".github/workflows/plasma-engineering-runtime-dispatch.yml"
SHA = "a" * 40
BIT = "b" * 64
HWH = "c" * 64
EVIDENCE = "d" * 64


def approval(task_id="z2-path2-build", **changes):
    val = {"task_id": task_id, "execution_path": "path2-cli",
           "execution_capability": "vivado-host-build" if
           task_id == "z2-path2-build" else "path2-stage-contract",
           "pinned_sha": SHA, "trusted_sha": SHA, "pr_number": 0,
           "auto_download_after_build_success": False,
           "auto_test_after_download_success": False}
    val.update(changes)
    return val


def event(task_id, flags=""):
    return {"action": "created", "issue": {"number": 981},
            "comment": {"id": 12345, "user": {"login": "physicslu"},
                        "body": "/plasma-dispatch run " + task_id + flags + " 981"},
            "sender": {"login": "physicslu"},
            "repository": {"full_name": "physicslu/plasma"}}


def context():
    return {"GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_ACTOR": "physicslu",
            "GITHUB_REPOSITORY": "physicslu/plasma",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": SHA, "GITHUB_RUN_ATTEMPT": "1"}


class RouteContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY.read_text())

    def test_three_independent_task_identities(self):
        for name, cap in (("z2-path2-build", "vivado-host-build"),
                          ("z2-path2-download", "path2-stage-contract"),
                          ("z2-path2-testing", "path2-stage-contract")):
            self.assertEqual(dispatch.task_by_id(self.registry, name)["capability"], cap)
            result = dispatch.authorize(event(name), context(), self.registry)
            self.assertEqual(result["task_id"], name)
            self.assertFalse(result["auto_download_after_build_success"])
            self.assertFalse(result["auto_test_after_download_success"])

    def test_flags_are_owner_selected_and_independent(self):
        cases = (("z2-path2-build", "", False, False),
                 ("z2-path2-build", " --auto-download", True, False),
                 ("z2-path2-build", " --auto-testing", False, True),
                 ("z2-path2-build", " --auto-download --auto-testing", True, True),
                 ("z2-path2-download", "", False, False),
                 ("z2-path2-download", " --auto-testing", False, True),
                 ("z2-path2-testing", "", False, False))
        for name, flags, ad, at in cases:
            with self.subTest(name=name, flags=flags):
                p = dispatch.authorize(event(name, flags), context(), self.registry)
                self.assertEqual((p["auto_download_after_build_success"],
                                  p["auto_test_after_download_success"]), (ad, at))

    def test_untrusted_flags_and_changed_scope_denied(self):
        for name, flags in (
            ("nine-nine-path2", " --auto-download"),
            ("fixed-site1-vivado-host-build", " --auto-download"),
            ("z2-path2-download", " --auto-download"),
            ("z2-path2-testing", " --auto-testing"),
            ("z2-path2-build", " --auto-testing --auto-download"),
            ("z2-path2-build", " --auto-download --auto-download"),
            ("z2-path2-build", " --help"),
            ("z2-path2-build", " --auto-testing\\n"),
        ):
            with self.subTest(name=name, flags=flags):
                with self.assertRaises(dispatch.Denied):
                    dispatch.authorize(event(name, flags), context(), self.registry)
        for key, value in (("GITHUB_ACTOR", "attacker"),
                           ("GITHUB_RUN_ATTEMPT", "2")):
            ctx = context()
            ctx[key] = value
            with self.assertRaises(dispatch.Denied):
                dispatch.authorize(event("z2-path2-download"), ctx, self.registry)
        for key, value in (("stage", "build"),
                           ("project", "scripts/evil"),
                           ("capability", "z2-cpu-only"),
                           ("argv", ["python", "/dev/mem"])):
            reg = copy.deepcopy(self.registry)
            reg["tasks"]["z2-path2-download"][key] = value
            with self.assertRaises(dispatch.Denied):
                dispatch.task_by_id(reg, "z2-path2-download")

    def test_stage_never_uses_hardware_even_when_flagged(self):
        for name in ("z2-path2-download", "z2-path2-testing"):
            with self.subTest(name=name), self.assertRaisesRegex(
                    runtime.RuntimeDenied, "PATH2_LIVE_PROVIDER_NOT_REGISTERED"):
                runtime.disabled_hardware_stage(
                    self.registry["tasks"][name], approval(name))
        build = Mock()
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(
                    runtime.RuntimeDenied, "PATH2_LIVE_DOWNLOAD_PROVIDER_NOT_REGISTERED"):
                runtime.host_build(
                    self.registry["tasks"]["z2-path2-build"],
                    workspace=Path(td), approval=approval(
                        auto_download_after_build_success=True),
                    evidence_dir=Path(td), build_driver=build)
            build.assert_not_called()

    def test_host_build_receipt_is_qualified_once(self):
        build = Mock(return_value={
            "status": "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED",
            "execution_capability": "vivado-host-build",
            "physical_load": "NOT_RUN", "z2_hil": "NOT_RUN", "m1": "NO_GO",
            "source_sha": SHA, "bit_sha256": BIT, "hwh_sha256": HWH,
            "report_sha256": {"timing_summary.rpt": EVIDENCE},
        })
        decision = Mock(return_value={
            "decision": "APPROVED", "source_sha": SHA,
            "bit_sha256": BIT, "hwh_sha256": HWH,
            "qualification_evidence_sha256": EVIDENCE,
        })
        with tempfile.TemporaryDirectory() as td:
            result = runtime.host_build(
                self.registry["tasks"]["z2-path2-build"],
                workspace=Path(td), approval=approval(),
                evidence_dir=Path(td), build_driver=build,
                qualify=decision)
        self.assertEqual(result["completed"], ["build"])
        self.assertEqual(result["scope"], "ADAPTER_RECEIPTS_ONLY")
        self.assertEqual(result["receipts"]["build"]["artifact_sha256"], BIT)
        self.assertEqual(result["transitions"], [])
        build.assert_called_once()
        decision.assert_called_once()

    def test_no_pretext_from_hosted_ci_or_explicit_failure(self):
        driver = Mock()
        with tempfile.TemporaryDirectory() as td:
            no_qual = runtime.host_build
            with self.assertRaisesRegex(Exception, "VIVADO_BUILD_EVIDENCE_NOT_QUALIFIED"):
                no_qual(self.registry["tasks"]["z2-path2-build"],
                        workspace=Path(td), approval=approval(),
                        evidence_dir=Path(td),
                        build_driver=lambda _: {"status": "PASS"},
                        qualify=lambda _: {"decision": "APPROVED"})
            driver.assert_not_called()
        wf = WORKFLOW.read_text()
        self.assertIn("github.event_name == 'pull_request' || github.event_name == 'push'", wf)
        self.assertIn("runs-on: ubuntu-24.04", wf)
        self.assertIn("path2-stage-contract", wf)
        self.assertIn("github.run_attempt == 1", wf)
        self.assertIn("scripts/tests/test_plasma_path2_runtime_integration.py", wf)
        self.assertEqual(wf.count("runs-on: [self-hosted, linux, x64, plasma-codex]"), 2)


class BuildQualificationBytes(unittest.TestCase):
    def evidence(self, td):
        root = Path(td)
        build = root / "pl/build/fixed-f1-bounded"
        proj = build / "project"
        bit = proj / "z2_fixed_unified_site1.runs/impl_1/system_wrapper.bit"
        hwh = proj / "z2_fixed_unified_site1.gen/sources_1/bd/system/hw_handoff/system.hwh"
        bit.parent.mkdir(parents=True, exist_ok=True)
        hwh.parent.mkdir(parents=True, exist_ok=True)
        bit.write_bytes(b"bit valid source fixture")
        hwh.write_bytes(b"hwh valid source fixture")
        reports = {}
        for name in qualifier.REPORTS:
            path = build / "reports" / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(("REPORT " + name + " PASS").encode())
            reports[name] = qualifier.hashlib.sha256(path.read_bytes()).hexdigest()
        stdout = b"start\\n" + qualifier.MARKER + b"\\n"
        (build / "vivado-stdout.log").write_bytes(stdout)
        (build / "vivado-stderr.log").write_bytes(b"")
        raw = {"status": "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED",
               "source_sha": SHA, "execution_capability": "vivado-host-build",
               "physical_load": "NOT_RUN", "z2_hil": "NOT_RUN", "m1": "NO_GO",
               "build_dir": str(build),
               "bit_sha256": hashlib.sha256(bit.read_bytes()).hexdigest(),
               "hwh_sha256": hashlib.sha256(hwh.read_bytes()).hexdigest(),
               "report_sha256": reports,
               "vivado_stdout_sha256": hashlib.sha256(stdout).hexdigest(),
               "vivado_stderr_sha256": hashlib.sha256(b"").hexdigest(),
               "map": {"hardware_runtime_ready": False,
                       "regions": {"site2_8": "ABSENT"}}}
        return raw, bit, hwh, build

    def verified(self, raw):
        return {"bit_sha256": raw["bit_sha256"], "hwh_sha256": raw["hwh_sha256"],
                "report_sha256": raw["report_sha256"], "map": raw["map"]}

    def test_exact_files_pass_and_failed_provenance_denied(self):
        with tempfile.TemporaryDirectory() as td:
            raw, bit, hwh, build = self.evidence(td)
            with patch.object(qualifier, "_verify_hwh",
                              return_value=self.verified(raw)):
                decision = qualifier.qualify_host_build(
                    raw, workspace=Path(td), pinned_sha=SHA)
                self.assertEqual(decision["decision"], "APPROVED")
                self.assertEqual(decision["bit_sha256"], raw["bit_sha256"])
                self.assertEqual(len(decision["qualification_evidence_sha256"]), 64)
                for key, value in (
                    ("source_sha", "f" * 40),
                    ("physical_load", "PASS"),
                    ("bit_sha256", "0" * 64),
                    ("build_dir", "/tmp/not-approved"),
                ):
                    bad = dict(raw, **{key: value})
                    with self.subTest(key=key), self.assertRaises(qualifier.QualificationDenied):
                        qualifier.qualify_host_build(
                            bad, workspace=Path(td), pinned_sha=SHA)
                (build / "reports/drc.rpt").write_text("TAMPER")
                with self.assertRaisesRegex(
                        qualifier.QualificationDenied, "BUILD_REPORT_HASH_MISMATCH"):
                    qualifier.qualify_host_build(raw, workspace=Path(td), pinned_sha=SHA)

    def test_success_marker_is_not_a_fake_hardware_pass(self):
        with tempfile.TemporaryDirectory() as td:
            raw, bit, hwh, build = self.evidence(td)
            (build / "vivado-stdout.log").write_bytes(b"no success marker")
            raw["vivado_stdout_sha256"] = hashlib.sha256(b"no success marker").hexdigest()
            with patch.object(qualifier, "_verify_hwh",
                              return_value=self.verified(raw)):
                with self.assertRaisesRegex(
                        qualifier.QualificationDenied, "BUILD_VIVADO_LOG_DENIED"):
                    qualifier.qualify_host_build(raw, workspace=Path(td), pinned_sha=SHA)


if __name__ == "__main__":
    unittest.main()
