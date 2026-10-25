#!/usr/bin/env python3
"""Host-only contract for the production generic Z2 FPGA Image Root path."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pl.hil import fpga_image_root as stage
from pl.hil.swd04 import one_shot


class FakePort:
    def __init__(self, release):
        self.release = release
        self.image = release.recovery_name
        self.boot = "host-only-boot-123456"
        self.writes = []
        self.fail = False

    def exclusive(self):
        return nullcontext()

    def report(self, port, release, image):
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
        one_shot.record_json(stage.CHILD, {"observed": {
            str(off): expected for off, expected, mask in self.release.identity_words}})


class GenericImageRootTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.folder = Path(td.name)
        self.release_data = json.loads(stage.RELEASE_FILE.read_text())
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(one_shot, "protected"))
        self.stack.enter_context(patch.object(stage, "RELEASE_FILE",
                                             self.folder / "approved.json"))
        self.write_manifest(self.release_data)
        self.release = stage.read_approved_release()
        self.port = FakePort(self.release)
        self.stack.enter_context(patch.object(stage, "STATE", self.folder / "state.json"))
        self.stack.enter_context(patch.object(stage, "CHILD", self.folder / "child.json"))
        self.stack.enter_context(patch.object(stage, "trusted_local"))
        self.stack.enter_context(patch.object(stage, "_state_file_trusted"))
        self.stack.enter_context(patch.object(stage.guard, "RootZ2TargetPort",
                                             return_value=self.port))
        self.stack.enter_context(patch.object(stage, "live_report",
                                             side_effect=self.port.report))
        self.stack.enter_context(patch.object(one_shot, "manager_write",
                                             side_effect=self.port.write))
        self.stack.enter_context(patch.object(one_shot, "run_child",
                                             side_effect=self.port.child))

    def write_manifest(self, source):
        if type(source) is str:
            self.folder.joinpath("approved.json").write_text(source)
        else:
            self.folder.joinpath("approved.json").write_text(json.dumps(source))

    def test_root_entry_does_not_name_any_single_image_handler(self):
        shell = (ROOT / "scripts/z2/plasma-path2-root-entry").read_text()
        self.assertIn('module="pl.hil.fpga_image_root"', shell)
        self.assertIn('pl/hil/fpga_image_guard.py', shell)
        self.assertIn('pl/hil/fpga_image_admission.py', shell)
        self.assertIn('pl/hil/approved-fpga-image.json', shell)
        self.assertIn('download|test|restore', shell)
        self.assertNotIn('path2_f1b', shell.lower())
        self.assertNotIn('f1b', shell.lower())

    def test_manifest_has_geometry_and_true_source_authority(self):
        image = self.release
        self.assertEqual(image.axi_bytes, 65536)
        self.assertEqual(image.site_bitmap, 1)
        self.assertEqual(len(image.identity_words), 3)
        self.assertEqual(image.expected_uio["maps"], [
            [image.owner_base, image.owner_bytes]])
        self.assertEqual(self.port.writes, [])

    def test_manifest_accepts_other_image_metadata_as_a_contract(self):
        """Simulate a *different source-pinned release*, never live admission."""
        alt = dict(self.release_data)
        alt.update(image_id="candidate-independent-ip",
                   firmware_name="reviewed-other-image.bin",
                   firmware_sha256="a" * 64, axi_base=0x40008000,
                   axi_bytes=4096, site_bitmap_offset=12, site_bitmap=8,
                   identity_words=[[0, 0x504C5357, 0xFFFFFFFF],
                                   [4, 0x10000, 0xFFFFFFFF],
                                   [12, 8, 0xFFFFFFFE]])
        self.write_manifest(alt)
        other = stage.read_approved_release()
        self.assertEqual(other.firmware_name, "reviewed-other-image.bin")
        self.assertEqual(other.axi_base, 0x40008000)
        self.assertEqual(other.identity_words[2][2], 0xFFFFFFFE)
        # Source hash/owner authorization are still enforced by Root Entry;
        # this mocked Host test does not grant this image permission on Z2.

    def test_bad_manifest_never_opens_manager(self):
        variants = (
            {"runtime_admitted": False},
            {"authorization": "SHA_ONLY"},
            {"firmware_name": "../untrusted.bin"},
            {"firmware_sha256": "0"},
            {"recovery_sha256": "0"},
            {"abi_version": 2},
            {"identity_words": [[0, 1, 0]]},
            {"axi_bytes": 0},
            {"owner_base": 0x50000000},
            {"site_bitmap_offset": 8},
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

    def test_state_binds_release_identity(self):
        stage.run("download")
        foreign = replace(self.release, image_id="different-image")
        with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                    "STATE_IMAGE_OR_IDENTITY_INVALID"):
            stage.read_state(foreign)
        self.assertEqual(self.port.writes, [self.release.firmware_name])


if __name__ == "__main__":
    unittest.main()
