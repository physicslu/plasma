#!/usr/bin/env python3
"""Hosted-only generic Vivado host-build contracts. No Vivado or SWPC access."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_vivado_host_build as build


class HostBuildRouteContracts(unittest.TestCase):
    def test_retired_f1b_path3_build_route_is_absent(self):
        """Only the dynamic Path 2 Work Order may reach the host build engine."""
        for name in ("main", "preflight", "_run_pipeline", "diagnostics_type",
                     "license_snapshot"):
            self.assertFalse(hasattr(build, name), name)
        self.assertFalse((ROOT / "scripts/plasma_fpga_build_diagnostics.py").exists())
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
