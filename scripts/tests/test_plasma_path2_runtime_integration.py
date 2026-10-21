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
                          ("z2-path2-testing", "path2-stage-contract"),
                           ("z2-path2-restore", "path2-stage-contract"),
                          ("z2-path2-full-hil", "path2-stage-contract")):
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
                 ("z2-path2-testing", "", False, False),
                  ("z2-path2-restore", "", False, False),
                 ("z2-path2-full-hil", "", False, False))
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
            ("z2-path2-restore", " --auto-download"),
            ("z2-path2-restore", " --auto-testing"),
            ("z2-path2-full-hil", " --auto-download"),
            ("z2-path2-full-hil", " --auto-testing"),
            ("z2-path2-build", " --auto-testing --auto-download"),
            ("z2-path2-build", " --auto-download --auto-download"),
            ("z2-path2-build", " --help"),
            ("z2-path2-build", " --auto-testing\\n"),
        ):
            with self.subTest(name=name, flags=flags):
                with self.assertRaises(dispatch.Denied):
                    dispatch.authorize(event(name, flags), context(), self.registry)
        for key, value in (("GITHUB_ACTOR", "attacker"),):
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
        for name in ("z2-path2-download", "z2-path2-testing",
                     "z2-path2-restore"):
            with self.subTest(name=name), self.assertRaisesRegex(
                    runtime.RuntimeDenied, "PATH2_TRUSTED_BRIDGE_NOT_INSTALLED"):
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

    def test_register_stage_uses_only_installed_fixed_bridge(self):
        class Response:
            def __init__(self, stage, payload):
                self.returncode = 0
                self.stdout = json.dumps(payload).encode()
                self.stderr = b""

        for name, stage, accepted in (
                ("z2-path2-download", "download", "LOADED_AND_HELD"),
                ("z2-path2-testing", "test", "IDENTITY_PASS"),
                ("z2-path2-restore", "restore", "RESTORED_VERIFIED")):
            args = []
            def fake_exec(command, **kwargs):
                args.append((command, kwargs))
                return Response(stage, {
                    "stage": stage, "source_sha": SHA,
                    "boot_id": "fake-test-boot-id", "real_z2": True,
                    "result": accepted})
            with self.subTest(name=name), patch.object(
                    runtime, "_trusted_root_bridge") as gate:
                out = runtime.registered_hardware_stage(
                    self.registry["tasks"][name], approval(name),
                    executor=fake_exec)
                gate.assert_called_once_with(runtime.ROOT_STAGE_BRIDGE)
                self.assertEqual(out["stage"], stage)
                self.assertEqual(out["result"], accepted)
                self.assertFalse(out["auto_next_stage"])
                self.assertEqual(args[0][0], [
                    str(runtime.ROOT_STAGE_BRIDGE), stage, SHA])
                self.assertEqual(args[0][1]["env"],
                                 {"PATH": "/usr/bin:/bin"})

    def test_uninstalled_bridge_and_fake_receipts_cannot_pass(self):
        task = self.registry["tasks"]["z2-path2-download"]
        with patch.object(runtime, "_trusted_root_bridge",
                          side_effect=runtime.RuntimeDenied(
                              "PATH2_TRUSTED_BRIDGE_NOT_INSTALLED")):
            with self.assertRaisesRegex(
                    runtime.RuntimeDenied,
                    "PATH2_TRUSTED_BRIDGE_NOT_INSTALLED"):
                runtime.registered_hardware_stage(
                    task, approval("z2-path2-download"),
                    executor=Mock(side_effect=AssertionError(
                        "must not reach executor")))
        with patch.object(runtime, "_trusted_root_bridge"):
            for fake in (
                    {"stage": "download", "source_sha": SHA,
                     "boot_id": "test-boot-long-id", "real_z2": False,
                     "result": "LOADED_AND_HELD"},
                    {"stage": "test", "source_sha": SHA,
                     "boot_id": "test-boot-long-id", "real_z2": True,
                     "result": "IDENTITY_PASS"},
                    {"stage": "download", "source_sha": "bad",
                     "boot_id": "test-boot-long-id", "real_z2": True,
                     "result": "LOADED_AND_HELD"}):
                result = Mock(returncode=0, stderr=b"",
                              stdout=json.dumps(fake).encode())
                with self.subTest(fake=fake), self.assertRaisesRegex(
                        runtime.RuntimeDenied,
                        "PATH2_BRIDGE_RECEIPT_NOT_REAL_Z2"):
                    runtime.registered_hardware_stage(
                        task, approval("z2-path2-download"),
                        executor=lambda *_args, **_kw: result)

    def test_full_hil_explicit_one_trigger_runs_three_real_stage_receipts(self):
        task = self.registry["tasks"]["z2-path2-full-hil"]
        called = []
        def fake_exec(command, **kwargs):
            called.append(command[1])
            stage = command[1]
            result = {
                "download": "LOADED_AND_HELD",
                "test": "IDENTITY_PASS",
                "restore": "RESTORED_VERIFIED",
            }[stage]
            return Mock(returncode=0, stderr=b"",
                        stdout=json.dumps({
                            "stage": stage, "source_sha": SHA,
                            "boot_id": "test-same-z2-boot",
                            "real_z2": True, "result": result,
                        }).encode())
        with patch.object(runtime, "_trusted_root_bridge"):
            output = runtime.full_hil_sequence(
                task, approval("z2-path2-full-hil"), executor=fake_exec)
        self.assertEqual(called, ["download", "test", "restore"])
        self.assertEqual([r["result"] for r in output["completed"]],
                         ["LOADED_AND_HELD", "IDENTITY_PASS",
                          "RESTORED_VERIFIED"])
        self.assertTrue(output["real_z2"])
        self.assertEqual(output["mode"], "full-hil")
        self.assertTrue(output["auto_next_stage"])
        self.assertEqual(output["build_stage"],
                         "REUSED_PREVIOUS_PINNED_IMAGE_NOT_REBUILT")

    def test_full_hil_failure_does_not_blindly_restore_or_continue(self):
        task = self.registry["tasks"]["z2-path2-full-hil"]
        calls = []
        def fake_exec(command, **_):
            calls.append(command[1])
            if command[1] == "test":
                return Mock(returncode=1, stdout=b"", stderr=b"test fail")
            return Mock(returncode=0, stderr=b"",
                        stdout=json.dumps({
                            "stage": command[1], "source_sha": SHA,
                            "boot_id": "test-same-z2-boot",
                            "real_z2": True, "result": "LOADED_AND_HELD",
                        }).encode())
        with patch.object(runtime, "_trusted_root_bridge"), \
             self.assertRaisesRegex(runtime.RuntimeDenied,
                                    "PATH2_BRIDGE_STAGE_FAILED_OR_UNKNOWN"):
            runtime.full_hil_sequence(
                task, approval("z2-path2-full-hil"), executor=fake_exec)
        self.assertEqual(calls, ["download", "test"])
        # Do not attempt an unsafe automatic Restore after failed MMIO.
        calls.clear()
        def rebooted_exec(command, **_):
            calls.append(command[1])
            return Mock(returncode=0, stderr=b"",
                        stdout=json.dumps({
                            "stage": command[1], "source_sha": SHA,
                            "boot_id": "first-boot-id" if command[1] == "download"
                            else "second-boot-id",
                            "real_z2": True,
                            "result": ("LOADED_AND_HELD" if
                                       command[1] == "download" else
                                       "IDENTITY_PASS"),
                        }).encode())
        with patch.object(runtime, "_trusted_root_bridge"), \
             self.assertRaisesRegex(runtime.RuntimeDenied,
                                    "PATH2_FULL_BOOT_OR_STAGE_CHANGED"):
            runtime.full_hil_sequence(
                task, approval("z2-path2-full-hil"),
                executor=rebooted_exec)
        self.assertEqual(calls, ["download", "test"])

    def test_full_hil_uninstalled_bridge_denies_first_stage(self):
        task = self.registry["tasks"]["z2-path2-full-hil"]
        with patch.object(runtime, "_trusted_root_bridge",
                          side_effect=runtime.RuntimeDenied(
                              "PATH2_TRUSTED_BRIDGE_NOT_INSTALLED")):
            with self.assertRaisesRegex(runtime.RuntimeDenied,
                                        "PATH2_TRUSTED_BRIDGE_NOT_INSTALLED"):
                runtime.full_hil_sequence(
                    task, approval("z2-path2-full-hil"),
                    executor=Mock(side_effect=AssertionError(
                        "should not run if bridge missing")))

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


    def test_both_paths_share_failure_boundary_and_never_continue(self):
        import subprocess
        work_sha = "d" * 64
        path3_task = {"execution_path": "path3-codex",
                      "capability": "codex-workspace",
                      "work_order_scope": "guarded-hardware",
                      "work_order_sha256": work_sha,
                      "hardware_stages": ["download", "test", "restore"]}
        path3_approval = approval("path3-work-order",
            execution_path="path3-codex",
            execution_capability="codex-guarded-hardware",
            work_order_sha256=work_sha)
        routes = [
            lambda executor: runtime.full_hil_sequence(
                self.registry["tasks"]["z2-path2-full-hil"],
                approval("z2-path2-full-hil"), executor=executor),
            lambda executor: runtime.path3_shared_hardware_stages(
                path3_task, path3_approval, executor=executor)]
        for route in routes:
            for failure in ("sigbus", "timeout", "receipt", "denied"):
                calls = []
                def executor(command, **kwargs):
                    calls.append(command[1])
                    if failure == "timeout":
                        raise subprocess.TimeoutExpired(command, 1)
                    if failure in ("sigbus", "denied"):
                        return Mock(returncode=-7 if failure == "sigbus" else 2,
                                    stdout=b"", stderr=b"")
                    return Mock(returncode=0, stdout=b'{"result":"PASS"}',
                                stderr=b"")
                with self.subTest(route=route, failure=failure), \
                     patch.object(runtime, "_trusted_root_bridge"), \
                     self.assertRaises(runtime.RuntimeDenied):
                    route(executor)
                self.assertEqual(calls, ["download"])
            executor = Mock()
            with patch.object(runtime, "_trusted_root_bridge",
                              side_effect=runtime.RuntimeDenied("ROOT_INTEGRITY_DENIED")), \
                 self.assertRaises(runtime.RuntimeDenied):
                route(executor)
            executor.assert_not_called()

    def test_shared_stage_contract_ignores_inert_flags(self):
        for name in ("z2-path2-download", "z2-path2-testing", "z2-path2-restore"):
            task = self.registry["tasks"][name]
            for flag in ("auto_download_after_build_success", "auto_test_after_download_success"):
                with self.subTest(name=name, flag=flag):
                    self.assertEqual(runtime.stage_contract(
                        task, approval(name, **{flag: True})), task["stage"])

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
