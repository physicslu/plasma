#!/usr/bin/env python3
"""Host-only contract for the production generic Z2 FPGA Image Root path."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pl.hil import fpga_image_root as stage
from pl.hil import fpga_image_guard as guard


class FakePort:
    def __init__(self, release):
        self.release = release
        self.image = release.recovery_name
        self.boot = "host-only-boot-123456"
        self.writes = []
        self.fail = False

    def exclusive(self):
        return nullcontext()

    def report(self, port, release, image, *, previous_image=None):
        if image != self.image:
            raise stage.ImageDeploymentDenied("MANAGER_PROVENANCE_MISMATCH")
        return {"target_boot_id": self.boot, "image_id": release.image_id,
                "expected_manager_firmware": image}

    def write(self, filename):
        self.writes.append(filename)
        if self.fail:
            raise RuntimeError("INJECTED_FPGA_MANAGER_FAILURE")
        self.image = filename

    def child(self, argv):
        assert argv[-3:] == ["pl.hil.fpga_image_root", "--identity-child"] or (
            argv[-3:] == ["-m", "pl.hil.fpga_image_root", "--identity-child"])
        guard.record_json(stage.CHILD, {"observed": {
            str(off): expected for off, expected, mask in self.release.identity_words}})


class GenericImageRootTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.folder = Path(td.name)
        self.release_data = json.loads((
            ROOT / "pl/projects/z2-bluepill-rbb/image-manifest.json").read_text())
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(guard, "protected"))
        self.stack.enter_context(patch.object(stage, "MANIFEST_FILE",
                                             self.folder / "plasma-image-manifest.json"))
        self.write_manifest(self.release_data)
        self.release = stage.read_image_manifest()
        self.port = FakePort(self.release)
        self.stack.enter_context(patch.object(stage, "STATE", self.folder / "state.json"))
        self.stack.enter_context(patch.object(stage, "CHILD", self.folder / "child.json"))
        self.stack.enter_context(patch.object(stage, "trusted_local"))
        self.stack.enter_context(patch.object(stage, "_state_file_trusted"))
        self.stack.enter_context(patch.object(stage.guard, "RootZ2TargetPort",
                                             return_value=self.port))
        self.stack.enter_context(patch.object(stage, "live_report",
                                             side_effect=self.port.report))
        self.stack.enter_context(patch.object(guard, "manager_write",
                                             side_effect=self.port.write))
        self.stack.enter_context(patch.object(guard, "run_child",
                                             side_effect=self.port.child))

    def write_manifest(self, source):
        if type(source) is str:
            self.folder.joinpath("plasma-image-manifest.json").write_text(source)
        else:
            self.folder.joinpath("plasma-image-manifest.json").write_text(json.dumps(source))

    def test_root_entry_does_not_name_any_single_image_handler(self):
        shell = (ROOT / "scripts/z2/plasma-path2-root-entry").read_text()
        self.assertIn('module="pl.hil.fpga_image_root"', shell)
        self.assertIn('pl/hil/fpga_image_guard.py', shell)
        self.assertIn('pl/hil/fpga_image_admission.py', shell)
        self.assertNotIn('pl/hil/approved-fpga-image.json', shell)
        self.assertIn("plasma-image-manifest.json", (ROOT / "pl/hil/fpga_image_root.py").read_text())
        self.assertIn('download|test|restore', shell)
        self.assertNotIn('path2_f1b', shell.lower())
        self.assertNotIn('f1b', shell.lower())
        for relative in ("pl/hil/fpga_image_root.py",
                         "pl/hil/fpga_image_guard.py",
                         "pl/hil/fpga_image_admission.py"):
            code = (ROOT / relative).read_text().lower()
            self.assertNotIn("path2_f1b", code)
            self.assertNotIn("from pl.hil import f1b", code)
            self.assertNotIn("f1-b", code)

    def test_runtime_closure_no_longer_depends_on_swd04(self):
        for relative in ("pl/hil/fpga_image_root.py",
                         "pl/hil/fpga_image_guard.py",
                         "pl/hil/fpga_image_admission.py",
                         "scripts/z2/plasma-path2-root-entry"):
            with self.subTest(relative=relative):
                content = (ROOT / relative).read_text()
                self.assertNotIn("pl.hil.swd04", content)
                self.assertNotIn("one_shot", content)
                self.assertNotIn("pl/hil/swd04", content)
        self.assertEqual(guard.GLOBAL_LOCK,
                         Path("/run/plasma-z2-swd05/supervisor.lock"))

    def test_swd_companion_manifest_has_no_release_authorization(self):
        """Provided BIN companion is not a source-code allowlist entry."""
        sample = json.loads((ROOT / "pl/projects/z2-bluepill-rbb/image-manifest.json").read_text())
        self.assertEqual(sample["schema"], "plasma.fpga.image.v1")
        self.assertNotIn("authorization", sample)
        self.assertNotIn("runtime_admitted", sample)
        self.assertEqual(sample["firmware_sha256"],
                         "bfbd3d872caeff05a8f9daa0829b6292e5b5036c6c6b927d6c779e13fe9ec1a1")
        self.assertEqual(sample["axi_base"], 0x40008000)
        self.assertEqual(sample["axi_bytes"], 4096)
        self.assertIsNone(sample["site_bitmap_offset"])
        self.assertEqual(sample["identity_words"],
                         [[0, 1346523991, 0xFFFFFFFF],
                          [4, 65536, 0xFFFFFFFF],
                          [12, 8, 0xFFFFFFFE]])
        other = stage.read_image_manifest()
        self.assertEqual(other.firmware_sha256, sample["firmware_sha256"])

    def test_direct_image_a_to_b_without_golden(self):
        self.assertEqual(stage.run("download")["result"], "LOADED_AND_HELD")
        different = dict(self.release_data)
        different.update(image_id="image-b", firmware_name="second-image.bin",
                         firmware_sha256="a" * 64)
        self.write_manifest(different)
        boot_path = self.folder / "sys/kernel/random/boot_id"
        boot_path.parent.mkdir(parents=True)
        boot_path.write_text(self.port.boot)
        self.stack.enter_context(patch.object(guard, "PROC", self.folder))
        with patch.object(guard, "sha_file") as prior_sha:
            result = stage.run("download")
            prior_sha.assert_not_called()
        self.assertEqual(result["result"], "LOADED_AND_HELD")
        self.assertEqual(self.port.writes,
                         [self.release.firmware_name, "second-image.bin"])
        new = stage.read_image_manifest()
        self.assertEqual(stage.read_state(new)["image_id"], "image-b")
        self.assertEqual(stage.read_state(new)["status"], "IMAGE")

    def test_direct_switch_requires_same_boot_without_golden(self):
        stage.run("download")
        different = dict(self.release_data)
        different.update(image_id="image-b", firmware_name="second-image.bin",
                         firmware_sha256="a" * 64)
        self.write_manifest(different)
        boot_path = self.folder / "sys/kernel/random/boot_id"
        boot_path.parent.mkdir(parents=True)
        boot_path.write_text("wrong-boot-123456")
        self.stack.enter_context(patch.object(guard, "PROC", self.folder))
        with patch.object(guard, "sha_file") as sha:
            with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                        "PREVIOUS_IMAGE_BOOT_CHANGED"):
                stage.run("download")
            sha.assert_not_called()
        self.assertEqual(self.port.writes, [self.release.firmware_name])

    def test_unknown_image_rejects_switch_without_recovery(self):
        self.port.fail = True
        with self.assertRaises(RuntimeError):
            stage.run("download")
        self.port.fail = False
        different = dict(self.release_data)
        different.update(image_id="image-b", firmware_name="second-image.bin",
                         firmware_sha256="a" * 64)
        self.write_manifest(different)
        with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                    "UNCERTAIN_PRIOR_OPERATION_MANUAL_RECOVERY"):
            stage.run("download")
        self.assertEqual(self.port.writes, [self.release.firmware_name])

    def test_manifest_legacy_approval_fields_rejected(self):
        for field, value in (("authorization", "SOURCE_PINNED_ROOT_APPROVAL"),
                             ("runtime_admitted", True)):
            with self.subTest(field=field):
                self.write_manifest(self.release_data | {field: value})
                with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                            "IMAGE_MANIFEST_SCHEMA_DENIED"):
                    stage.run("download")
                self.assertEqual(self.port.writes, [])


    def test_manifest_has_geometry_and_true_source_authority(self):
        image = self.release
        self.assertEqual(image.axi_bytes, 4096)
        self.assertEqual(image.site_bitmap, 1)
        self.assertEqual(len(image.identity_words), 3)
        self.assertEqual(image.expected_uio["maps"], [
            [image.owner_base, image.owner_bytes]])
        self.assertEqual(self.port.writes, [])

    def test_manifest_accepts_other_image_metadata_as_a_contract(self):
        """Independent Image metadata follows the same generic runtime parser."""
        alt = dict(self.release_data)
        alt.update(image_id="candidate-independent-ip",
                   firmware_name="reviewed-other-image.bin",
                   firmware_sha256="a" * 64, axi_base=0x40008000,
                   axi_bytes=4096, site_bitmap_offset=None, site_bitmap=1,
                   identity_words=[[0, 0x504C5357, 0xFFFFFFFF],
                                   [4, 0x10000, 0xFFFFFFFF],
                                   [12, 8, 0xFFFFFFFE]])
        self.write_manifest(alt)
        other = stage.read_image_manifest()
        self.assertEqual(other.firmware_name, "reviewed-other-image.bin")
        self.assertEqual(other.axi_base, 0x40008000)
        self.assertEqual(other.identity_words[2][2], 0xFFFFFFFE)
        self.assertIsNone(other.site_bitmap_offset)
        self.assertEqual(other.site_bitmap, 1)
        # Sample bit is not a hardware Site Bitmap register.
        actual = {other.axi_base + off: expected for off, expected, mask
                  in other.identity_words}
        actual[other.axi_base + 12] = 9
        self.assertEqual(stage.read_identity(lambda a: actual[a], other)[12], 9)
        # Source-code integrity is separate from this paired Image data.

    def test_bad_manifest_never_opens_manager(self):
        variants = (
            {"schema": "plasma.fpga.image-release.v2"},
            {"board_id": "wrong-board"},
            {"fpga_part": "wrong-part"},
            {"firmware_name": "../untrusted.bin"},
            {"firmware_sha256": "0"},
            {"recovery_sha256": "0"},
            {"abi_version": 2},
            {"identity_words": [[0, 1, 0]]},
            {"axi_bytes": 0},
            {"owner_base": 0x50000000},
            {"site_bitmap_offset": 8},
            {"site_bitmap_offset": 12},  # masked SAMPLE must not claim Site identity
            {"extra": True},
        )
        for change in variants:
            with self.subTest(change=change):
                self.write_manifest(self.release_data | change)
                with self.assertRaises(stage.ImageDeploymentDenied):
                    stage.run("download")
                self.assertEqual(self.port.writes, [])
        for raw in ('{', "[]", "", '{"schema":0,"schema":1}'):
            with self.subTest(raw=raw):
                self.write_manifest(raw)
                with self.assertRaises(stage.ImageDeploymentDenied):
                    stage.run("download")
                self.assertEqual(self.port.writes, [])

    def test_backend_read32_uses_released_axi_and_mask(self):
        image = self.release
        addresses = []
        values = {image.axi_base + off: expected
                  for off, expected, _ in image.identity_words}
        def read32(address):
            addresses.append(address)
            return values[address]
        actual = stage.read_identity(read32, image)
        self.assertEqual(len(actual), 3)
        self.assertEqual(addresses, [image.axi_base + off
                                    for off, _, _ in image.identity_words])
        values[image.axi_base + image.abi_offset] = 2
        with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                    "PL_IDENTITY_MISMATCH"):
            stage.read_identity(read32, image)

    def test_independent_download_test_restore_repeatable(self):
        self.assertEqual(stage.run("download")["result"], "LOADED_AND_HELD")
        self.assertEqual(stage.run("test")["result"], "IDENTITY_PASS")
        self.assertEqual(stage.run("restore")["result"], "RESTORED_VERIFIED")
        self.assertEqual(stage.run("restore")["result"], "ALREADY_RESTORED")
        self.assertEqual(self.port.writes, [
            self.release.firmware_name, self.release.recovery_name])
        self.assertEqual(stage.read_state(self.release)["status"], "RECOVERY")
        self.assertEqual(stage.run("download")["result"], "LOADED_AND_HELD")

    def test_identity_requires_manual_download_first(self):
        for verb in ("test", "restore"):
            with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                        "DOWNLOAD_REQUIRED_BEFORE"):
                stage.run(verb)
        self.assertEqual(self.port.writes, [])

    def test_failed_load_denies_uncontrolled_retry_or_restore(self):
        self.port.fail = True
        with self.assertRaises(RuntimeError):
            stage.run("download")
        self.assertEqual(stage.read_state(self.release)["status"], "UNKNOWN")
        self.port.fail = False
        for verb in ("download", "test", "restore"):
            with self.assertRaises(stage.ImageDeploymentDenied):
                stage.run(verb)
        self.assertEqual(len(self.port.writes), 1)

    def test_unknown_operation_rejected_before_manager(self):
        for command in ("erase", "program", "read", "full", "reset", ""):
            with self.assertRaises(stage.ImageDeploymentDenied):
                stage.run(command)
        self.assertEqual(self.port.writes, [])

    def test_no_switch_while_prior_image_is_held_for_test_or_restore(self):
        stage.run("download")
        other = dict(self.release_data)
        other.update(image_id="image-b", firmware_name="other.bin",
                     firmware_sha256="a" * 64)
        self.write_manifest(other)
        for operation in ("test", "restore"):
            with self.subTest(operation=operation), self.assertRaisesRegex(
                    stage.ImageDeploymentDenied,
                    "NEW_MANIFEST_DOWNLOAD_REQUIRED"):
                stage.run(operation)
        self.assertEqual(self.port.writes, [self.release.firmware_name])


class GenericGuardSafetyTests(unittest.TestCase):
    """Exercise the real common guard, without GenericImageRootTests mocks."""

    def test_runtime_child_path_matches_shared_owner(self):
        self.assertEqual(stage.CHILD,
                         guard.OWNER_DIR / "fpga-image-identity.json")

    def test_common_guard_rejects_unapproved_manager_name(self):
        for name in ("../unauthorized.bin", "/tmp/unauthorized.bin",
                     "image with spaces.bin", ""):
            with self.subTest(name=name), self.assertRaises(
                    guard.TargetSafetyDenied):
                guard.manager_write(name)

    def test_common_guard_supervisor_rejects_failed_child(self):
        class FailedChild:
            def wait(self, timeout):
                return 7
        with patch.object(guard.subprocess, "Popen", return_value=FailedChild()):
            with self.assertRaisesRegex(guard.TargetSafetyDenied,
                                        "MMIO child failed"):
                guard.run_child(["true"])

    def test_common_guard_load_record_must_be_observed(self):
        from subprocess import CompletedProcess
        with patch.object(guard.subprocess, "run",
                          return_value=CompletedProcess([], 0, "no FPGA load")):
            with self.assertRaisesRegex(guard.TargetSafetyDenied,
                                        "No current-boot FPGA Manager"):
                guard.manager_last_load()




if __name__ == "__main__":
    unittest.main()
