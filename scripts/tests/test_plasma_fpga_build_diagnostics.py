#!/usr/bin/env python3
"""Hosted-only Build Diagnostic v1 and generic host-build unit tests. No Vivado or SWPC access."""
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

    def test_retired_f1b_path3_build_route_is_absent(self):
        """Only the dynamic Path 2 Work Order may reach the host build engine."""
        for name in ("main", "preflight", "_run_pipeline", "diagnostics_type",
                     "license_snapshot"):
            self.assertFalse(hasattr(build, name), name)
        for execution_path, approval in (
                ("path3-codex", {"task_id": "f1b-path3-codex-vivado-build"}),
                ("path3-codex", {"task_id": "path2-work-order"}),
                ("path2-cli", {"task_id": "f1b-path3-codex-vivado-build"})):
            with self.subTest(path=execution_path, approval=approval):
                with patch.object(build, "run_generic") as generic:
                    with self.assertRaisesRegex(build.BuildDenied,
                                                "BUILD_LEGACY_PATH_RETIRED"):
                        build.run({}, workspace=ROOT, approval=approval,
                                  execution_path=execution_path)
                    generic.assert_not_called()

    def test_reviewed_pr_driver_loads_candidate_generic_engine(self):
        """A pinned candidate PR driver is loaded from the candidate tree."""
        import shutil
        import plasma_development_dispatch as dev
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            scripts = workspace / "scripts"
            scripts.mkdir()
            driver = scripts / "plasma_vivado_host_build.py"
            shutil.copyfile(ROOT / "scripts/plasma_vivado_host_build.py", driver)
            reviewed = dev.reviewed_host_build_driver(
                workspace=workspace, approval={"pr_number": 1200})
            self.assertTrue(callable(reviewed.run))
            self.assertTrue(callable(reviewed.run_generic))
            self.assertEqual(reviewed.__name__,
                             "plasma_reviewed_candidate_vivado_host_build")


class HostBuildOutputPathContracts(unittest.TestCase):
    """Offline contract: candidate-relative Runner checkout must not duplicate paths."""

    def test_relative_candidate_workspace_uses_absolute_build_dir(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            workspace = parent / "candidate"
            build_root = workspace / "pl" / "build"
            build_root.mkdir(parents=True)
            previous_cwd = Path.cwd()
            try:
                os.chdir(parent)
                result = build.prepare_host_build_dir(Path("candidate"))
                self.assertTrue(result.is_absolute())
                self.assertEqual(result.parent, build_root)
                self.assertTrue((result / "reports").is_dir())
                self.assertTrue(result.is_relative_to(workspace))
                # Same path from Vivado's actual cwd=workspace, no candidate/candidate.
                self.assertEqual(Path(str(result)).resolve(strict=True), result)
            finally:
                os.chdir(previous_cwd)

    def test_absolute_candidate_workspace_and_symlink_output_guard(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            workspace = parent / "candidate"
            build_root = workspace / "pl" / "build"
            build_root.mkdir(parents=True)
            result = build.prepare_host_build_dir(workspace)
            self.assertTrue(result.is_absolute())
            self.assertEqual(result.parent, build_root)
            self.assertTrue((result / "reports").is_dir())
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            workspace = parent / "candidate"
            (workspace / "pl").mkdir(parents=True)
            external = parent / "external-build"
            external.mkdir()
            (workspace / "pl" / "build").symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(
                build.BuildDenied, "BUILD_OUTPUT_ROOT_MISSING"
            ):
                build.prepare_host_build_dir(workspace)




class LicenseDiscoveryContracts(unittest.TestCase):
    """Host-only filesystem fixtures; never touch real Xilinx installs."""

    def fixture(self, root: Path):
        installed = root / "installed"
        tool = installed / "2026.1" / "Vivado"
        tool.mkdir(parents=True)
        settings = tool / "settings64.sh"
        settings.write_text("# metadata-only fixture")
        return installed, settings

    def fixed_license(self, installed: Path, data: bytes = b"FIXTURE ONLY"):
        parent = installed / "xic"
        parent.mkdir()
        target = parent / "Xilinx.lic"
        target.write_bytes(data)
        return target

    def test_fixed_location_without_environment_is_read_only_and_never_scans(self):
        with tempfile.TemporaryDirectory() as td:
            installed, settings = self.fixture(Path(td))
            fixed = self.fixed_license(installed)
            decoy = installed / "licenses" / "vivado" / "Xilinx.lic"
            decoy.parent.mkdir(parents=True)
            decoy.write_bytes(b"decoy, never selected")
            before = fixed.read_bytes()
            with patch.object(build.os, "walk",
                              side_effect=AssertionError("recursive scan forbidden")) as scan:
                resolved = build.discover_vivado_license(env={}, settings=settings)
                scan.assert_not_called()
            self.assertEqual(resolved, {"XILINXD_LICENSE_FILE": str(fixed)})
            self.assertEqual(fixed.read_bytes(), before)

    def test_explicit_pinned_source_and_duplicate_environment_keys(self):
        with tempfile.TemporaryDirectory() as td:
            installed, settings = self.fixture(Path(td))
            fixed = self.fixed_license(installed)
            for env in (
                {"XILINXD_LICENSE_FILE": str(fixed)},
                {"LM_LICENSE_FILE": str(fixed)},
                {"XILINXD_LICENSE_FILE": str(fixed),
                 "LM_LICENSE_FILE": str(fixed)},
            ):
                with self.subTest(env_keys=tuple(env)):
                    self.assertEqual(
                        build.discover_vivado_license(env=env, settings=settings),
                        {"XILINXD_LICENSE_FILE": str(fixed)})

    def test_missing_alt_sources_conflict_and_unreadable_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            installed, settings = self.fixture(Path(td))
            with self.assertRaisesRegex(
                build.BuildDenied, "BUILD_LICENSE_NOT_FOUND"
            ):
                build.discover_vivado_license(env={}, settings=settings)
            fixed = self.fixed_license(installed)
            alternate = installed / "Xilinx.lic"
            alternate.write_bytes(b"alternate")
            with self.assertRaisesRegex(
                build.BuildDenied, "BUILD_LICENSE_SOURCE_DENIED"
            ):
                build.discover_vivado_license(
                    env={"XILINXD_LICENSE_FILE": str(alternate)}, settings=settings)
            with self.assertRaisesRegex(
                build.BuildDenied, "BUILD_LICENSE_SOURCE_AMBIGUOUS"
            ):
                build.discover_vivado_license(
                    env={"XILINXD_LICENSE_FILE": str(fixed),
                         "LM_LICENSE_FILE": str(alternate)}, settings=settings)
            with patch.object(build.os, "access", return_value=False):
                with self.assertRaisesRegex(
                    build.BuildDenied, "BUILD_LICENSE_FILE_UNREADABLE"
                ):
                    build.discover_vivado_license(env={}, settings=settings)

    def test_reject_symlinks_untrusted_tokens_and_file_size(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            installed, settings = self.fixture(root)
            outside = root / "secrets" / "Xilinx.lic"
            outside.parent.mkdir()
            outside.write_bytes(b"synthetic secret, do not inspect")
            fixed = installed / "xic" / "Xilinx.lic"
            fixed.parent.mkdir()
            fixed.symlink_to(outside)
            with self.assertRaisesRegex(
                build.BuildDenied, "BUILD_LICENSE_SOURCE_DENIED"
            ):
                build.discover_vivado_license(env={}, settings=settings)
            for value in (str(outside), "27000@server", "Xilinx.lic",
                          "/etc/passwd", "/dev/mem", str(fixed) + "\n"):
                with self.subTest(value_type="untrusted"), self.assertRaisesRegex(
                    build.BuildDenied, "BUILD_LICENSE_SOURCE_DENIED"
                ):
                    build.discover_vivado_license(
                        env={"XILINXD_LICENSE_FILE": value}, settings=settings)
            fixed.unlink()
            for data in (b"", b"x" * (1024 * 1024 + 1)):
                fixed.write_bytes(data)
                with self.subTest(file_size=len(data)), self.assertRaisesRegex(
                    build.BuildDenied, "BUILD_LICENSE_FILE_INVALID"
                ):
                    build.discover_vivado_license(env={}, settings=settings)
                fixed.unlink()

    def test_symlinked_root_and_xic_parent_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            installed, settings = self.fixture(root)
            fake = root / "linked"
            fake.symlink_to(installed, target_is_directory=True)
            with self.assertRaisesRegex(
                build.BuildDenied, "BUILD_LICENSE_TOOL_ROOT_DENIED"
            ):
                build.discover_vivado_license(
                    env={}, settings=fake / "2026.1/Vivado/settings64.sh")
            external = root / "external-directory"
            external.mkdir()
            (external / "Xilinx.lic").write_bytes(b"test fixture")
            (installed / "xic").symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(
                build.BuildDenied, "BUILD_LICENSE_SOURCE_DENIED"
            ):
                build.discover_vivado_license(env={}, settings=settings)


if __name__ == "__main__":
    unittest.main()
