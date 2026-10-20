#!/usr/bin/env python3
"""Hosted-only F1 Build + Diagnostic v1 unit tests. No Vivado or SWPC access."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_fpga_build_diagnostics as diag
import plasma_vivado_host_build as build


class DiagnosticContracts(unittest.TestCase):
    def test_success_has_ordered_stages_digest_and_no_private_paths(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            session = diag.DiagnosticSession(
                execution_path="path2-cli", source_sha="a" * 40,
                evidence_dir=folder)
            session.check("license_environment_present", True)
            session.check("build_root_writable", True)
            log = folder / "vivado.log"
            log.write_bytes(b"mock timing report, PASS")
            session.artifact("vivado_stdout", log)
            for stage in diag.STAGES:
                session.enter(stage)
            session.complete()
            output = session.persist()
            receipt = json.loads(output.read_text())
            self.assertEqual(receipt["schema_version"], diag.SCHEMA)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual([s["stage"] for s in receipt["stages"]],
                             list(diag.STAGES))
            self.assertTrue(all(s["status"] == "PASS" for s in receipt["stages"]))
            self.assertEqual(receipt["artifacts"]["vivado_stdout"]["sha256"],
                             hashlib.sha256(log.read_bytes()).hexdigest())
            self.assertEqual(receipt["physical_load"], "NOT_RUN")
            self.assertEqual(receipt["m1"], "NO_GO")
            self.assertNotIn(str(folder), output.read_text())
            digest = (folder / "plasma-fpga-build-diagnostics.json.sha256").read_text()
            self.assertEqual(digest.split()[0], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_failure_preserves_first_exception_type_without_secret(self):
        with tempfile.TemporaryDirectory() as td:
            ses = diag.DiagnosticSession(
                execution_path="path3-codex", source_sha="b" * 40,
                evidence_dir=Path(td))
            ses.enter("PREFLIGHT")
            ses.enter("BOARD_PREPARE")
            exception = PermissionError(13, "License path /secret/license.lic TOKEN=XYZ")
            ses.fail(exception)
            ses.persist()
            receipt = json.loads((Path(td) / "plasma-fpga-build-diagnostics.json").read_text())
            self.assertEqual(receipt["status"], "FAIL")
            self.assertEqual(receipt["failed_stage"], "BOARD_PREPARE")
            self.assertEqual(receipt["exception_type"], "PermissionError")
            self.assertEqual(receipt["error_code"], "BUILD_UNCLASSIFIED_EXCEPTION")
            self.assertEqual(receipt["root_cause_status"], "UNKNOWN")
            self.assertNotIn("/secret/", json.dumps(receipt))
            self.assertNotIn("TOKEN=XYZ", json.dumps(receipt))
            self.assertEqual([s["status"] for s in receipt["stages"]], ["PASS", "FAIL"])

    def test_negative_stage_artifact_sha_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            ses = diag.DiagnosticSession(
                execution_path="path2-cli", source_sha="a" * 40,
                evidence_dir=folder)
            for bad in ("sudo", "DEVICE_POWER", ""):
                with self.assertRaises(ValueError):
                    ses.enter(bad)
            ses.enter("PREFLIGHT")
            with self.assertRaises(ValueError):
                ses.enter("PREFLIGHT")
            target = folder / "host.log"
            target.write_text("not from Vivado")
            link = folder / "symlink.log"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                ses.artifact("vivado_stderr", link)
            with self.assertRaises(ValueError):
                ses.artifact("arbitrary", target)
            with self.assertRaises(ValueError):
                ses.complete()
            ses.fail(build.BuildDenied("BUILD_OUTPUT_PERMISSION_DENIED"))
            ses.persist()
            self.assertEqual(ses.as_dict()["root_cause_status"], "CONFIRMED")
            report = folder / "plasma-fpga-build-diagnostics.json"
            report.unlink()
            report.symlink_to(target)
            with self.assertRaises(ValueError):
                ses.persist()

    def test_path3_requires_pinned_owner_runner_before_any_build(self):
        fixed = json.loads(
            (ROOT / "specs/engineering-dispatch/development-tasks-v1.json").read_text()
        )["tasks"]["fixed-site1-vivado-host-build"]
        task = dict(fixed, execution_path="path3-codex")
        approval = {
            "execution_capability": "vivado-host-build",
            "execution_path": "path3-codex",
            "task_id": "f1b-path3-codex-vivado-build",
            "pr_number": 1111,
            "pinned_sha": "b" * 40,
            "trusted_sha": "a" * 40,
        }
        env = {
            "GITHUB_REPOSITORY": "physicslu/plasma",
            "RUNNER_NAME": build.EXPECTED_RUNNER,
            "RUNNER_ENVIRONMENT": "self-hosted",
            "GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "a" * 40,
            "PLASMA_FPGA_PATH3_APPROVED": "1",
            "PLASMA_FPGA_PINNED_SHA": "b" * 40,
            "PLASMA_FPGA_PR_NUMBER": "1111",
        }
        plan = build.preflight(task, workspace=ROOT,
                               approval=approval, env=env,
                               execution_path="path3-codex")
        self.assertEqual(plan["source_sha"], "b" * 40)
        for field, value in (
            ("PLASMA_FPGA_PATH3_APPROVED", "0"),
            ("PLASMA_FPGA_PINNED_SHA", "c" * 40),
            ("PLASMA_FPGA_PR_NUMBER", "1"),
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("RUNNER_NAME", "github-hosted"),
            ("GITHUB_SHA", "c" * 40),
        ):
            with self.subTest(field=field), self.assertRaises(build.BuildDenied):
                build.preflight(task, workspace=ROOT, approval=approval,
                                env=env | {field: value},
                                execution_path="path3-codex")
        with self.assertRaises(build.BuildDenied):
            build.preflight(task, workspace=ROOT, approval=approval,
                            env=env, execution_path="path2-cli")
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"PLASMA_FPGA_PATH3_APPROVED": "0",
                                         "PLASMA_FPGA_PINNED_SHA": "",
                                         "PLASMA_FPGA_PR_NUMBER": ""}):
                result = build.main(["--path3-engineering-host-only",
                                     "--evidence-dir", td])
                self.assertEqual(result, 2)


    def test_reviewed_pr_driver_loads_sibling_diagnostic_library(self):
        """A pinned candidate PR must not borrow a different main version."""
        import shutil
        import plasma_development_dispatch as dev
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            scripts = workspace / "scripts"
            scripts.mkdir()
            driver = scripts / "plasma_vivado_host_build.py"
            library = scripts / "plasma_fpga_build_diagnostics.py"
            shutil.copyfile(ROOT / "scripts/plasma_vivado_host_build.py", driver)
            shutil.copyfile(ROOT / "scripts/plasma_fpga_build_diagnostics.py", library)
            reviewed = dev.reviewed_host_build_driver(
                workspace=workspace, approval={"pr_number": 1200})
            self.assertTrue(callable(reviewed.run))
            self.assertEqual(reviewed.diagnostics_type().SCHEMA if hasattr(
                reviewed.diagnostics_type(), "SCHEMA") else
                reviewed.diagnostics_type().__module__,
                "plasma_reviewed_fpga_diagnostics")
            library.unlink()
            with self.assertRaisesRegex(
                reviewed.BuildDenied, "BUILD_DIAGNOSTICS_LIBRARY_DENIED"
            ):
                reviewed.diagnostics_type()


class PipelineFailureEvidence(unittest.TestCase):
    """All executors below are stubs, even for license and Vivado regression."""

    def _pipeline(self, folder, *, executor, fail_output=False):
        evidence = folder / "evidence"
        evidence.mkdir()
        settings = folder / "settings64.sh"
        settings.write_text("# fake: never source")
        board = folder / "board"
        board.mkdir()
        builddir = folder / "pl" / "build" / "mock"
        builddir.mkdir(parents=True)
        sha = "b" * 40
        task = {"execution_path": "path2-cli", "capability": "vivado-host-build"}
        approval = {"pinned_sha": sha}
        plan = {"source_sha": sha, "board_sha": "e" * 40,
                "script": "/fake/build_bitstream.tcl",
                "verifier": "/fake/verify_hwh.py"}
        checked = [("e" * 40).encode(), b"", sha.encode()]
        def checked_command(*args, **kwargs):
            return checked.pop(0)
        with (
            patch.object(build, "preflight", return_value=plan),
            patch.object(build, "SETTINGS64", settings),
            patch.object(build, "resolve_board_repository", return_value=board),
            patch.object(build, "_run_checked", side_effect=checked_command),
            patch.object(build.os, "geteuid", return_value=1001),
            patch.object(build, "prepare_host_build_dir", side_effect=(
                build.BuildDenied("BUILD_OUTPUT_PERMISSION_DENIED")
                if fail_output else lambda workspace: builddir
            )),
            patch.dict(os.environ, {"XILINXD_LICENSE_FILE": "/private/license",
                                    "LM_LICENSE_FILE": ""}),
        ):
            with self.assertRaises(build.BuildDenied):
                build.run(task, workspace=folder, approval=approval,
                          evidence_dir=evidence, executor=executor)
        return json.loads((evidence / "plasma-fpga-build-diagnostics.json").read_text()), evidence

    def test_output_permission_is_confirmed_and_no_process_started(self):
        called = []
        result, evidence = self._pipeline(
            Path(tempfile.mkdtemp(prefix="plasma-diag-test-")),
            executor=lambda *args, **kwargs: called.append(args),
            fail_output=True,
        )
        self.assertFalse(called)
        self.assertEqual(result["failed_stage"], "OUTPUT_PREPARE")
        self.assertEqual(result["error_code"], "BUILD_OUTPUT_PERMISSION_DENIED")
        self.assertEqual(result["root_cause_status"], "CONFIRMED")
        self.assertEqual(result["checks"]["license_environment_present"], True)

    def test_vivado_failure_keeps_log_sha_and_license_without_leaking_secret(self):
        calls = []
        class Failure:
            returncode = 1
            stdout = b"mock Vivado failure"
            stderr = b"mock host failure"
        def fake_vivado(*args, **kwargs):
            calls.append((args, kwargs))
            return Failure()
        with tempfile.TemporaryDirectory() as td:
            result, _ = self._pipeline(Path(td), executor=fake_vivado)
        self.assertEqual(result["failed_stage"], "VIVADO_IMPLEMENTATION")
        self.assertEqual(result["error_code"], "BUILD_VIVADO_IMPLEMENTATION_FAILED")
        self.assertEqual(result["root_cause_status"], "UNKNOWN")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["env"]["XILINXD_LICENSE_FILE"], "/private/license")
        self.assertEqual(result["artifacts"]["vivado_stdout"]["sha256"],
                         hashlib.sha256(b"mock Vivado failure").hexdigest())
        self.assertNotIn("/private/license", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
