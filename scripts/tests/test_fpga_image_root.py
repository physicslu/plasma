#!/usr/bin/env python3
"""Host-only contract for the production generic Z2 FPGA Image Root path."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pl.hil import fpga_image_root as stage
from pl.hil import fpga_image_guard as guard
from pl.hil import fpga_image_admission as admission


class FakePort:
    def __init__(self, release):
        self.release = release
        self.image = release.recovery_name
        self.boot = "host-only-boot-123456"
        self.writes = []
        self.fail = False

    def exclusive(self):
        return nullcontext()

    def inherited_reload_fence(self):
        # Host-only token: the real Root returns its held OS flock FD.
        return 123

    def report(self, port, release, image, *, previous_image=None,
               require_mmio=False):
        if image != self.image:
            raise stage.ImageDeploymentDenied("MANAGER_PROVENANCE_MISMATCH")
        return {"target_boot_id": self.boot, "image_id": release.image_id,
                "expected_manager_firmware": image}

    def write(self, filename):
        self.writes.append(filename)
        if self.fail:
            raise RuntimeError("INJECTED_FPGA_MANAGER_FAILURE")
        self.image = filename

    def child(self, argv, *, reload_fence_fd=None):
        assert reload_fence_fd == self.inherited_reload_fence()
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
        self.reservation = self.folder / "ppu-resource-reservation.json"
        self.stack.enter_context(patch.object(stage, "RUNTIME_RESERVATION", self.reservation))
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
        self.assertIn('module=pl.hil.fpga_image_root', shell)
        self.assertNotIn('verifier=/opt/plasma/bootstrap/ppu_privileged_source.py', shell)
        validator = (ROOT / "scripts/ppu_privileged_source.py").read_text()
        self.assertIn('pl/hil/fpga_image_guard.py', validator)
        self.assertIn('pl/hil/fpga_image_admission.py', validator)
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

    def test_no_operator_pl_change_while_a_batch_holds_the_ppu(self):
        """U11: download / test / restore refuse an ACTIVE Runtime Reservation."""
        self.assertEqual(stage.run("download")["result"], "LOADED_AND_HELD")
        writes = list(self.port.writes)
        self.reservation.write_text(json.dumps({"state": "ACTIVE", "owner_id": "batch-1"}))
        for verb in ("download", "test", "restore"):
            with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                        "RUNTIME_RESOURCE_RESERVATION_ACTIVE"):
                stage.run(verb)
        self.assertEqual(self.port.writes, writes)
        # A settled or isolated Reservation does not block operator recovery.
        for state in ("RECOVERY_REQUIRED", "RELEASED"):
            self.reservation.write_text(json.dumps({"state": state}))
            self.assertEqual(stage.run("test")["result"], "IDENTITY_PASS")

    def test_an_unreadable_runtime_reservation_fails_closed(self):
        self.assertEqual(stage.run("download")["result"], "LOADED_AND_HELD")
        for content in (b"not json", b"[]", b'{"state": 1}'):
            self.reservation.write_bytes(content)
            with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                        "RUNTIME_RESERVATION_UNREADABLE"):
                stage.run("test")
        # A link (e.g. to a device) is never followed.
        self.reservation.unlink()
        self.reservation.symlink_to("/dev/zero")
        with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                    "RUNTIME_RESERVATION_UNREADABLE"):
            stage.run("test")

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

    def test_post_load_report_failure_stays_unknown(self):
        original = self.port.report
        def failed_after(port, release, image, **kwargs):
            if image == release.firmware_name:
                raise stage.ImageDeploymentDenied("POST_LOAD_MANAGER_UNPROVEN")
            return original(port, release, image, **kwargs)
        with patch.object(stage, "live_report", side_effect=failed_after):
            with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                        "POST_LOAD_MANAGER_UNPROVEN"):
                stage.run("download")
        self.assertEqual(self.port.writes, [self.release.firmware_name])
        self.assertEqual(stage.read_state(self.release)["status"], "UNKNOWN")

    def test_identity_requires_mmio_admission_before_child(self):
        stage.run("download")
        original = self.port.report
        def deny_mmio(port, release, image, **kwargs):
            if kwargs.get("require_mmio"):
                raise admission.AdmissionDenied("UIO_PLATFORM_OWNER_MISMATCH")
            return original(port, release, image, **kwargs)
        with patch.object(stage, "live_report", side_effect=deny_mmio), \
                patch.object(guard, "run_child") as child:
            with self.assertRaisesRegex(admission.AdmissionDenied,
                                        "UIO_PLATFORM_OWNER_MISMATCH"):
                stage.run("test")
            child.assert_not_called()
        self.assertEqual(stage.read_state(self.release)["status"], "IMAGE")

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

    def test_live_admission_requires_global_owner_lock(self):
        from types import SimpleNamespace
        port = guard.RootZ2TargetPort(release=SimpleNamespace())
        with self.assertRaisesRegex(guard.TargetSafetyDenied,
                                    "FPGA_OWNER_LOCK_REQUIRED"):
            admission.collect_live(root_port=port, release=port.release,
                                   expected_firmware="candidate.bin",
                                   require_mmio=False)

    def test_missing_golden_and_bad_candidate_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            firmware = Path(td)
            (firmware / "candidate.bin").write_bytes(b"wrong candidate")
            with patch.object(guard, "FIRMWARE", firmware), \
                    patch.object(guard, "protected"):
                with self.assertRaisesRegex(guard.TargetSafetyDenied,
                                            "FIRMWARE_LOCATION_DENIED"):
                    guard.sha_file(firmware / "golden.bin", "a" * 64)
                with self.assertRaisesRegex(guard.TargetSafetyDenied,
                                            "FIRMWARE_BYTES_CHANGED"):
                    guard.sha_file(firmware / "candidate.bin", "a" * 64)

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



class GuardProcessCensusRegressionTests(unittest.TestCase):
    """Host-only races; fake /proc only; never touch Z2 or real MMIO."""

    def setUp(self):
        from types import SimpleNamespace
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.proc = Path(self.td.name)
        self.release = SimpleNamespace(owner_base=0x40000000,
                                       owner_bytes=0x10000)

    def pid(self, number, *, mapped=None):
        directory = self.proc / str(number)
        (directory / "fd").mkdir(parents=True)
        (directory / "maps").write_text(
            mapped or "00100000-00101000 r--p 00000000 00:00 0 [anon]\n")
        return directory

    def test_clean_scan_and_real_fd_conflict_are_distinct(self):
        active = self.pid(1000)
        result = {}
        self.assertEqual(guard.scan_proc_consumers(
            procroot=self.proc, release=self.release, diagnostic=result),
            (True, []))
        self.assertEqual(result["status"], "COMPLETE")
        (active / "fd/3").symlink_to("/dev/uio1")
        result = {}
        self.assertEqual(guard.scan_proc_consumers(
            procroot=self.proc, release=self.release, diagnostic=result),
            (True, ["1000"]))
        self.assertEqual(result["status"], "PROC_CONFLICT")

    def test_confirmed_pid_exit_restarts_full_scan(self):
        import shutil
        vanishing = self.pid(1000)
        self.pid(2000)
        original = Path.read_text
        calls = []
        def vanish_once(path, *args, **kwargs):
            if path == vanishing / "maps":
                calls.append("vanished")
                shutil.rmtree(vanishing)
                raise FileNotFoundError("synthetic terminated PID")
            return original(path, *args, **kwargs)
        detail = {}
        with patch.object(Path, "read_text", new=vanish_once):
            self.assertEqual(guard.scan_proc_consumers(
                procroot=self.proc, release=self.release, diagnostic=detail),
                (True, []))
        self.assertEqual(calls, ["vanished"])
        self.assertEqual(detail["status"], "COMPLETE")
        self.assertEqual(detail["rescans"], 1)
        self.assertEqual(detail["attempt"], 2)

    def test_existing_pid_with_missing_maps_fails_closed(self):
        (self.proc / "1000/fd").mkdir(parents=True)
        self.pid(2000)
        detail = {}
        self.assertEqual(guard.scan_proc_consumers(
            procroot=self.proc, release=self.release, diagnostic=detail),
            (False, ["1000"]))
        self.assertEqual(detail["attempt"], 1)
        self.assertEqual(detail["status"], "PROC_VISIBILITY_DENIED")

    def test_permission_denied_never_retries(self):
        active = self.pid(1000)
        original = Path.read_text
        def denied(path, *args, **kwargs):
            if path == active / "maps":
                raise PermissionError("synthetic proc permission error")
            return original(path, *args, **kwargs)
        detail = {}
        with patch.object(Path, "read_text", new=denied):
            result = guard.scan_proc_consumers(
                procroot=self.proc, release=self.release, diagnostic=detail)
        self.assertEqual(result, (False, ["1000"]))
        self.assertEqual(detail["status"], "PROC_VISIBILITY_DENIED")
        self.assertEqual(detail["attempt"], 1)

    def test_conflict_before_vanishing_process_cannot_be_skipped(self):
        import shutil
        owner = self.pid(1000)
        (owner / "fd/1").symlink_to("/dev/uio1")
        vanishing = self.pid(2000)
        original = Path.read_text
        def disappear(path, *args, **kwargs):
            if path == vanishing / "maps":
                shutil.rmtree(vanishing)
                raise FileNotFoundError("synthetic terminated PID")
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", new=disappear):
            detail = {}
            result = guard.scan_proc_consumers(
                procroot=self.proc, release=self.release, diagnostic=detail)
        self.assertEqual(result, (False, ["1000", "2000"]))
        self.assertEqual(detail["status"], "PROC_CONFLICT_AND_INCOMPLETE")
        self.assertEqual(detail["attempt"], 1)

    def test_missing_maps_with_inaccessible_pid_is_not_exit(self):
        active = self.pid(1000)
        original_read = Path.read_text
        original_stat = Path.stat

        def missing_maps(path, *args, **kwargs):
            if path == active / "maps":
                raise FileNotFoundError("inaccessible live PID maps")
            return original_read(path, *args, **kwargs)

        def hidden_pid(path, *args, **kwargs):
            if path == active:
                raise PermissionError("cannot establish PID disappearance")
            return original_stat(path, *args, **kwargs)

        detail = {}
        with patch.object(Path, "read_text", new=missing_maps), \
                patch.object(Path, "stat", new=hidden_pid):
            result = guard.scan_proc_consumers(
                procroot=self.proc, release=self.release,
                diagnostic=detail)
        self.assertEqual(result, (False, ["1000"]))
        self.assertEqual(detail["attempt"], 1)
        self.assertEqual(detail["status"], "PROC_VISIBILITY_DENIED")

    def test_three_successive_disappearing_pids_fail_closed(self):
        import shutil
        for pid in (1000, 2000, 3000, 9000):
            self.pid(pid)
        original = Path.read_text
        def disappear(path, *args, **kwargs):
            if path.parent.name in ("1000", "2000", "3000") and path.name == "maps":
                shutil.rmtree(path.parent)
                raise FileNotFoundError("synthetic terminated PID")
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", new=disappear):
            detail = {}
            result = guard.scan_proc_consumers(
                procroot=self.proc, release=self.release, diagnostic=detail)
        self.assertEqual(result, (False, ["3000"]))
        self.assertEqual(detail["status"], "VANISHED_PID_RESCAN_EXHAUSTED")
        self.assertEqual(detail["attempt"], 3)


class SiteAdmissionVanishedPidPolicyTests(unittest.TestCase):
    """2-Site HIL 2026-11-19: concurrent Sites exhausted the strict rescan.

    Site admission (``vanished_pids="skip"``) skips only a PID whose exit is
    confirmed; FPGA Manager download/test/restore keep ``"rescan"``. Fake
    /proc only; never touches Z2, real MMIO or a DUT.
    """

    SITE1 = 0x43C01000
    SITE2 = 0x43C02000

    def setUp(self):
        from types import SimpleNamespace
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.proc = Path(self.td.name)
        self.release = SimpleNamespace(
            owner_base=self.SITE1, owner_bytes=0x2000, site_bitmap=3,
            axi_base=self.SITE1, axi_bytes=0x2000)

    def pid(self, number, *, fds=(), maps="", start=1000):
        directory = self.proc / str(number)
        (directory / "fd").mkdir(parents=True)
        for index, target in enumerate(fds, start=3):
            (directory / f"fd/{index}").symlink_to(target)
        (directory / "maps").write_text(
            maps or "00100000-00101000 r--p 00000000 00:00 0 [anon]\n")
        self.restart(number, start)
        return directory

    def restart(self, number, start):
        fields = ["S"] + ["0"] * 18 + [str(start)] + ["0"] * 10
        (self.proc / str(number) / "stat").write_text(
            f"{number} (proc {number}) " + " ".join(fields) + "\n")

    @staticmethod
    def devmem(offset):
        return f"b6f00000-b6f01000 rw-s {offset:08x} 00:06 1029 /dev/mem\n"

    def scan(self, policy, cooperating=None):
        detail = {}
        result = guard.scan_proc_consumers(
            procroot=self.proc, release=self.release, diagnostic=detail,
            cooperating=cooperating, vanished_pids=policy)
        return result, detail

    def vanish_on_read(self, victims):
        import shutil
        original = Path.read_text
        def read(path, *args, **kwargs):
            if path.name == "maps" and path.parent.name in victims and path.parent.exists():
                shutil.rmtree(path.parent)
                raise FileNotFoundError("synthetic terminated PID")
            return original(path, *args, **kwargs)
        return patch.object(Path, "read_text", new=read)

    # -------------------------------------------------- confirmed exits
    def test_site_admission_skips_confirmed_exit_without_rescan(self):
        self.pid(1000)
        self.pid(2000)
        with self.vanish_on_read({"1000"}):
            result, detail = self.scan("skip")
        self.assertEqual(result, (True, []))
        self.assertEqual((detail["status"], detail["attempt"], detail["rescans"],
                          detail["vanished_skipped"]), ("COMPLETE", 1, 0, 1))

    def test_concurrent_churn_never_exhausts_site_admission_but_still_does_maintenance(self):
        """The repro: peer short-lived PIDs exit during every pass."""
        victims = {str(n) for n in range(1000, 1100)}
        for number in range(1000, 1100):
            self.pid(number)
        self.pid(9000)
        with self.vanish_on_read(victims):
            result, detail = self.scan("skip")
        self.assertEqual(result, (True, []))
        self.assertEqual(detail["vanished_skipped"], 100)
        for number in range(1000, 1004):
            self.pid(number)
        with self.vanish_on_read({"1000", "1001", "1002", "1003"}):
            result, detail = self.scan("rescan")
        self.assertFalse(result[0])
        self.assertEqual(detail["status"], "VANISHED_PID_RESCAN_EXHAUSTED")

    def test_exit_during_fd_phase_is_skipped(self):
        import shutil
        gone = self.pid(1000)
        self.pid(2000)
        original = Path.iterdir
        def iterdir(path):
            if path == gone / "fd":
                shutil.rmtree(gone)
                raise FileNotFoundError("synthetic terminated PID")
            return original(path)
        with patch.object(Path, "iterdir", new=iterdir):
            result, detail = self.scan("skip")
        self.assertEqual(result, (True, []))
        self.assertEqual(detail["vanished_skipped"], 1)

    def test_maintenance_default_policy_is_the_strict_rescan(self):
        self.pid(1000)
        with self.vanish_on_read({"1000"}):
            detail = {}
            result = guard.scan_proc_consumers(
                procroot=self.proc, release=self.release, diagnostic=detail)
        self.assertEqual(result, (False, []))  # nothing left; NO_PROCESS_OBSERVED
        self.assertEqual(detail["rescans"], 1)

    def test_unknown_policy_is_refused(self):
        with self.assertRaises(guard.TargetSafetyDenied):
            self.scan("ignore")

    # -------------------------------------------- still fail closed
    def test_live_but_unreadable_pid_still_fails_closed(self):
        active = self.pid(1000)
        original_read = Path.read_text
        def denied(path, *args, **kwargs):
            if path == active / "maps":
                raise PermissionError("LSM denied")
            return original_read(path, *args, **kwargs)
        with patch.object(Path, "read_text", new=denied):
            result, detail = self.scan("skip")
        self.assertEqual(result, (False, ["1000"]))
        self.assertEqual(detail["status"], "PROC_VISIBILITY_DENIED")

    def test_missing_maps_of_a_live_pid_is_not_an_exit(self):
        active = self.pid(1000)
        original_read = Path.read_text
        def missing(path, *args, **kwargs):
            if path == active / "maps":
                raise FileNotFoundError("maps hidden but PID alive")
            return original_read(path, *args, **kwargs)
        with patch.object(Path, "read_text", new=missing):
            result, detail = self.scan("skip")
        self.assertEqual(result, (False, ["1000"]))
        self.assertEqual(detail["status"], "PROC_VISIBILITY_DENIED")

    def test_real_fpga_owner_conflict_still_refused_even_with_exits(self):
        self.pid(1000, fds=("/dev/uio1",))
        self.pid(1500, fds=("/dev/xdevcfg",))
        self.pid(2000)
        with self.vanish_on_read({"2000"}):
            result, detail = self.scan("skip")
        self.assertEqual(result, (True, ["1000", "1500"]))
        self.assertEqual(detail["status"], "PROC_CONFLICT")
        self.assertEqual(detail["vanished_skipped"], 1)

    def test_uncooperative_devmem_owner_is_refused(self):
        # /dev/mem open without the Site lock / admission record: no exemption,
        # whether it only holds the fd or maps the PL window.
        self.pid(1000, fds=("/dev/mem",))
        self.pid(2000, maps=self.devmem(self.SITE2))
        result, _ = self.scan("skip", cooperating=lambda: {})
        self.assertEqual(result, (True, ["1000", "2000"]))

    def test_peer_site_owner_is_exempt_only_inside_its_own_page(self):
        self.pid(1000, fds=("/dev/mem",), maps=self.devmem(self.SITE2))
        result, _ = self.scan("skip", cooperating=lambda: {"1000": 2})
        self.assertEqual(result, (True, []))
        self.restart(1000, 1000)
        (self.proc / "1000/maps").write_text(self.devmem(self.SITE1))
        result, _ = self.scan("skip", cooperating=lambda: {"1000": 2})
        self.assertEqual(result, (True, ["1000"]))

    def test_inherited_devmem_fd_survives_its_exited_parent(self):
        # The parent exits mid-scan; the child listed with it inherited
        # /dev/mem and is NOT a proven Site owner, so it is still refused.
        self.pid(1000, fds=("/dev/mem",))
        self.pid(1001, fds=("/dev/mem",), maps=self.devmem(self.SITE1))
        with self.vanish_on_read({"1000"}):
            result, detail = self.scan("skip", cooperating=lambda: {})
        self.assertEqual(result, (True, ["1001"]))
        self.assertEqual(detail["vanished_skipped"], 1)

    # ------------------------------------------------------- PID reuse
    def test_pid_reused_mid_read_is_reexamined_and_conflict_refused(self):
        reused = self.pid(1000, start=111)
        original = Path.read_text
        state = {"swapped": False}
        def swap(path, *args, **kwargs):
            if path == reused / "maps" and not state["swapped"]:
                # The original exits; a new process takes PID 1000 holding /dev/uio1.
                state["swapped"] = True
                (reused / "fd/3").symlink_to("/dev/uio1")
                self.restart(1000, 222)
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", new=swap):
            for policy in ("skip", "rescan"):
                state["swapped"] = False
                (reused / "fd/3").unlink(missing_ok=True)
                self.restart(1000, 111)
                result, _ = self.scan(policy)
                self.assertEqual(result, (True, ["1000"]), policy)

    def test_pid_reused_twice_is_refused(self):
        reused = self.pid(1000, start=1)
        original = Path.read_text
        counter = iter(range(10, 100))
        def churn(path, *args, **kwargs):
            if path == reused / "maps":
                self.restart(1000, next(counter))
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", new=churn):
            result, detail = self.scan("skip")
        self.assertEqual(result, (False, ["1000"]))
        self.assertEqual(detail["status"], "PID_REUSED_DURING_SCAN")

    # ------------------------------------- ESRCH (2-Site HIL 2026-11-23)
    def esrch_on(self, victim, phase, *, after=None, error=ProcessLookupError):
        """Raise ``error`` when ``phase`` of PID ``victim`` is read.

        ``after(directory)`` runs first: remove the entry (confirmed exit),
        recreate it (PID reuse) or leave it (live / zombie task).
        """
        import contextlib
        directory = self.proc / str(victim)
        leaf = {"STAT": "stat", "MAPS": "maps", "FD": "fd"}[phase]
        target = directory / leaf
        original_read, original_iterdir = Path.read_text, Path.iterdir
        fired = []

        def fire():
            fired.append(phase)
            if after is not None:
                after(directory)
            raise error("synthetic procfs " + error.__name__)

        def read(path, *args, **kwargs):
            if path == target and not fired:
                fire()
            return original_read(path, *args, **kwargs)

        def iterdir(path):
            if path == target and not fired:
                fire()
            return original_iterdir(path)

        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(Path, "read_text", new=read))
        stack.enter_context(patch.object(Path, "iterdir", new=iterdir))
        return stack

    @staticmethod
    def remove(directory):
        import shutil
        shutil.rmtree(directory)

    def test_esrch_with_confirmed_exit_is_skipped_in_every_phase(self):
        for phase in ("STAT", "FD", "MAPS"):
            with self.subTest(phase=phase):
                self.pid(1000)
                self.pid(2000)
                with self.esrch_on(1000, phase, after=self.remove):
                    result, detail = self.scan("skip")
                self.assertEqual(result, (True, []))
                self.assertEqual((detail["status"], detail["attempt"], detail["rescans"],
                                  detail["vanished_skipped"], detail["observed"]),
                                 ("COMPLETE", 1, 0, 1, 1))
                self.remove(self.proc / "2000")

    def test_esrch_of_a_present_pid_fails_closed_in_every_phase(self):
        """A live or zombie task (entry still listed) is not a confirmed exit."""
        for phase in ("STAT", "FD", "MAPS"):
            with self.subTest(phase=phase):
                self.pid(1000)
                with self.esrch_on(1000, phase):
                    result, detail = self.scan("skip")
                self.assertEqual(result, (False, ["1000"]))
                self.assertEqual((detail["status"], detail["phase"], detail["error"]),
                                 ("PROC_VISIBILITY_DENIED", phase, "ProcessLookupError"))
                self.remove(self.proc / "1000")

    def test_esrch_then_pid_reused_fails_closed(self):
        def reuse(directory):
            self.remove(directory)
            self.pid(1000, start=4242)  # a new process already owns the PID
        self.pid(1000, start=7)
        with self.esrch_on(1000, "MAPS", after=reuse):
            result, detail = self.scan("skip")
        self.assertEqual(result, (False, ["1000"]))
        self.assertEqual(detail["status"], "PROC_VISIBILITY_DENIED")

    def test_esrch_with_unprovable_disappearance_fails_closed(self):
        """EACCES (or any error) on the confirming stat proves nothing."""
        self.pid(1000)
        original_stat = Path.stat
        def stat(path, *args, **kwargs):
            if path == self.proc / "1000":
                raise PermissionError("cannot establish PID disappearance")
            return original_stat(path, *args, **kwargs)
        with self.esrch_on(1000, "MAPS"), patch.object(Path, "stat", new=stat):
            result, detail = self.scan("skip")
        self.assertEqual(result, (False, ["1000"]))
        self.assertEqual(detail["status"], "PROC_VISIBILITY_DENIED")

    def test_eacces_is_never_an_exit_even_when_the_entry_is_gone(self):
        self.pid(1000)
        self.pid(2000)
        with self.esrch_on(1000, "MAPS", after=self.remove, error=PermissionError):
            result, detail = self.scan("skip")
        self.assertEqual(result, (False, ["1000"]))
        self.assertEqual((detail["status"], detail["error"]),
                         ("PROC_VISIBILITY_DENIED", "PermissionError"))

    def test_esrch_exit_under_maintenance_policy_rescans_and_stays_bounded(self):
        self.pid(1000)
        self.pid(2000)
        with self.esrch_on(1000, "MAPS", after=self.remove):
            result, detail = self.scan("rescan")
        self.assertEqual(result, (True, []))
        self.assertEqual((detail["status"], detail["rescans"], detail["attempt"]),
                         ("COMPLETE", 1, 2))
        # Every pass loses a PID to ESRCH: the bounded rescan is exhausted.
        import shutil
        original = Path.read_text
        victims = {"1000", "1001", "1002", "1003"}
        for number in (1000, 1001, 1002, 1003):
            self.pid(number)
        def read(path, *args, **kwargs):
            if path.name == "maps" and path.parent.name in victims and path.parent.exists():
                shutil.rmtree(path.parent)
                raise ProcessLookupError("synthetic reaped task")
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", new=read):
            result, detail = self.scan("rescan")
        self.assertFalse(result[0])
        self.assertEqual(detail["status"], "VANISHED_PID_RESCAN_EXHAUSTED")

    def test_conflict_is_still_refused_when_another_pid_exits_with_esrch(self):
        self.pid(1000, fds=("/dev/uio1",))
        self.pid(2000)
        with self.esrch_on(2000, "MAPS", after=self.remove):
            result, detail = self.scan("skip")
        self.assertEqual(result, (True, ["1000"]))
        self.assertEqual((detail["status"], detail["vanished_skipped"]), ("PROC_CONFLICT", 1))

    def test_stable_pid_identity_is_unchanged_behaviour(self):
        self.pid(1000, start=5)
        result, detail = self.scan("skip")
        self.assertEqual(result, (True, []))
        self.assertEqual(detail["observed"], 1)


class SiteAdmissionPolicyWiringTests(unittest.TestCase):
    """Only the Site owner asks for "skip"; the Root reload owner never does."""

    def port_facts(self, site):
        import threading
        port = guard.RootZ2TargetPort(release=object())
        port._locked, port._lock_owner_pid = True, os.getpid()
        port._lock_owner_thread = threading.get_ident()
        port._site = site
        if site is not None:
            port._site_session = ("boot", "session")
        with patch.object(guard, "read_live_z2_facts",
                          side_effect=lambda **kw: kw) as facts:
            port.current_facts()
        return facts.call_args.kwargs

    def test_site_admission_uses_skip(self):
        for site in (1, 2):
            kwargs = self.port_facts(site)
            self.assertEqual(kwargs["vanished_pids"], "skip")
            self.assertIsNotNone(kwargs["cooperating"])

    def test_reload_test_restore_owner_keeps_strict_rescan(self):
        kwargs = self.port_facts(None)
        self.assertEqual(kwargs["vanished_pids"], "rescan")
        self.assertIsNone(kwargs["cooperating"])

    def test_program_session_still_runs_no_census(self):
        import threading
        port = guard.RootZ2TargetPort(release=object())
        port._locked, port._lock_owner_pid = True, os.getpid()
        port._lock_owner_thread = threading.get_ident()
        with patch.object(guard, "read_live_z2_facts",
                          side_effect=lambda **kw: kw) as facts:
            port.runtime_program_facts()
        self.assertTrue(facts.call_args.kwargs["runtime_program_session"])
        self.assertNotIn("vanished_pids", facts.call_args.kwargs)


class RootLazyHwhParserImportTests(unittest.TestCase):
    """WO-2 F1: Site admission imports the Root modules on every Job; only
    HWH validation needs ElementTree. Each case runs in a FRESH interpreter
    with the Z2 admission flags (-I -B) so another test cannot preload xml.
    """

    REPO = Path(__file__).resolve().parents[2]
    RELEASE = "pl/hil/releases/swd-independent-d0add58c/plasma-image-manifest.json"
    HWH = "pl/tests/fixtures/swd-independent-d0add58c/system.hwh"

    def fresh(self, body):
        import subprocess
        code = ("import json, sys\n"
                f"sys.path.insert(0, {str(self.REPO)!r})\n" + body)
        done = subprocess.run([sys.executable, "-I", "-B", "-c", code],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_root_modules_import_without_elementtree(self):
        out = self.fresh(
            "from pl.hil import fpga_image_guard, fpga_image_admission, fpga_image_root\n"
            "print(json.dumps({'xml': 'xml.etree.ElementTree' in sys.modules,\n"
            "  'validate': callable(fpga_image_root.validate_hwh_bytes)}))\n")
        self.assertEqual(out, {"xml": False, "validate": True})

    def test_hwh_validation_unchanged_with_lazy_parser(self):
        out = self.fresh(f"""
from pathlib import Path
from pl.hil import fpga_image_root as root
release = root.parse_image_manifest_bytes(Path({str(self.REPO / self.RELEASE)!r}).read_bytes())
good = Path({str(self.REPO / self.HWH)!r}).read_bytes()
before = 'xml.etree.ElementTree' in sys.modules
root.validate_hwh_bytes(good, release)
after = 'xml.etree.ElementTree' in sys.modules
cases = {{
    'empty': b'', 'not_bytes': 'text', 'too_large': b'x' * 4_000_001,
    'malformed': b'<ROOT><MEMRANGE', 'bad_number': good.replace(b'0x43C01000', b'0xZZ', 1),
    'no_ranges': b'<hwh/>',
    'target': good.replace(b'DEVICE="7z020"', b'DEVICE="7z030"'),
    'identity': (b"<ROOT><SYSTEMINFO BOARD='pynq-z2' DEVICE='7z020' PACKAGE='clg400' "
                 b"SPEEDGRADE='-1'/><MEMRANGE MASTERBUSINTERFACE='M_AXI_GP0' "
                 b"BASEVALUE='0x43c01000' HIGHVALUE='0x43c01fff'/></ROOT>"),
}}
codes = {{}}
for name, raw in cases.items():
    try:
        root.validate_hwh_bytes(raw, release)
        codes[name] = 'ACCEPTED'
    except root.ImageDeploymentDenied as exc:
        codes[name] = str(exc)
print(json.dumps({{'before': before, 'after': after, 'codes': codes}}))
""")
        self.assertEqual((out["before"], out["after"]), (False, True))
        self.assertEqual(out["codes"], {
            "empty": "IMAGE_HWH_SIZE_DENIED",
            "not_bytes": "IMAGE_HWH_SIZE_DENIED",
            "too_large": "IMAGE_HWH_SIZE_DENIED",
            "malformed": "IMAGE_HWH_INVALID",
            "bad_number": "IMAGE_HWH_INVALID",
            "no_ranges": "IMAGE_HWH_RANGE_INVALID",
            "target": "IMAGE_HWH_TARGET_MISMATCH",
            "identity": "IMAGE_HWH_IDENTITY_RANGE_MISMATCH",
        })


class RootAdmissionFailureClassificationTests(unittest.TestCase):
    """An incomplete Root snapshot is not a known owner and never passes."""

    def facts(self):
        from types import SimpleNamespace
        release = SimpleNamespace(
            recovery_sha256=guard.GOLDEN_RECOVERY_SHA256,
            firmware_sha256="a" * 64,
            expected_uio={"uio": "uio1"},
            uio_name="uio1", firmware_name="candidate.bin",
            recovery_name=guard.GOLDEN_RECOVERY_NAME, site_bitmap=1, image_id="test")
        passive = {
            "observation_kind": "LIVE_ROOT_READ_ONLY", "root": True,
            "boot_id": "fixed-test-boot", "manager_state": "operating",
            "recovery_sha256": release.recovery_sha256,
            "candidate_sha256": release.firmware_sha256,
            "proc_complete": True, "proc_conflicts": [],
            "proc_scan_diagnostic": {"status": "COMPLETE"},
            "uio_overlaps": ["uio1"],
            "platform_overlaps": ["40000000.fabric"],
        }
        return release, passive

    def check(self, release, passive):
        from pl.hil import fpga_image_admission as admission
        return admission.check_exact(
            release=release, passive=passive, uio=release.expected_uio,
            original_manager_load="fpga_manager fpga0: writing candidate.bin to fpga0",
            expected_firmware=release.firmware_name)

    def test_complete_nonconflicting_facts_pass(self):
        release, facts = self.facts()
        self.assertEqual(self.check(release, facts)["image_id"], "test")

    def test_manager_load_ignores_stale_uio_index_but_mmio_does_not(self):
        release, facts = self.facts()
        facts["uio_overlaps"] = ["uio0"]
        report = admission.check_exact(
            release=release, passive=facts, uio=None,
            original_manager_load="fpga_manager fpga0: writing candidate.bin to fpga0",
            expected_firmware=release.firmware_name, require_mmio=False)
        self.assertIsNone(report["current_uio"])
        with self.assertRaisesRegex(ValueError, "BOUND_UIO_EXACT_FACTS_CHANGED"):
            admission.check_exact(
                release=release, passive=facts, uio={"uio": "uio0"},
                original_manager_load="fpga_manager fpga0: writing candidate.bin to fpga0",
                expected_firmware=release.firmware_name)

    def test_load_still_denies_missing_hash_census_owner_and_provenance(self):
        release, facts = self.facts()
        common = dict(release=release, uio=None,
                      original_manager_load="fpga_manager fpga0: writing candidate.bin to fpga0",
                      expected_firmware=release.firmware_name,
                      require_mmio=False)
        cases = (("recovery_sha256", "0" * 64, "INCOMPLETE_ROOT_OR_PROCESS_FACTS"),
                 ("candidate_sha256", "0" * 64, "INCOMPLETE_ROOT_OR_PROCESS_FACTS"),
                 ("proc_complete", False, "PROC_SCAN_INCOMPLETE"),
                 ("proc_conflicts", ["42"], "PROC_RESOURCE_OWNER_CONFLICT"),
                 ("uio_overlaps", ["uio0", "uio1"], "OTHER_BOUND_UIO_OR_MAPPING_DENIED"),
                 ("platform_overlaps", [], "BOUND_PLATFORM_EXCEPTION_NOT_ISOLATED"),
                 ("manager_state", "unknown", "INCOMPLETE_ROOT_OR_PROCESS_FACTS"),
                 ("boot_id", "", "INCOMPLETE_ROOT_OR_PROCESS_FACTS"))
        for field, value, code in cases:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, code):
                admission.check_exact(**dict(common, passive=facts | {field: value}))
        with self.assertRaisesRegex(ValueError, "MANAGER_LOAD_PROVENANCE_UNPROVEN"):
            admission.check_exact(**dict(common, passive=facts,
                                         original_manager_load="no load"))
        # Same code, now attributable: numeric PID/start time and fixed tokens.
        conflict = {"pid": "4242", "start_time": "913377", "device": "DEVMEM",
                    "reason": "OWNER_UNPROVEN", "stage": "LOCK", "revalidation": "STILL_HELD"}
        with self.assertRaisesRegex(
                ValueError, "^PROC_RESOURCE_OWNER_CONFLICT:4242:913377:DEVMEM:"
                            "OWNER_UNPROVEN:LOCK:STILL_HELD$"):
            admission.check_exact(**dict(common, passive=facts | {
                "proc_conflicts": ["4242"],
                "proc_scan_diagnostic": {"status": "PROC_CONFLICT", "conflict": conflict}}))

    def test_mmio_still_denies_wrong_aperture_or_owner(self):
        release, facts = self.facts()
        with self.assertRaisesRegex(ValueError, "BOUND_UIO_EXACT_FACTS_CHANGED"):
            admission.check_exact(
                release=release, passive=facts,
                uio={"uio": "uio1", "maps": [[0x43c00000, 65536]]},
                original_manager_load="fpga_manager fpga0: writing candidate.bin to fpga0",
                expected_firmware=release.firmware_name)
        facts["uio_overlaps"] = ["uio0"]
        with self.assertRaisesRegex(ValueError, "OTHER_BOUND_UIO_OR_MAPPING_DENIED"):
            self.check(release, facts)
        facts["uio_overlaps"] = ["uio1"]
        facts["platform_overlaps"] = ["43c00000.audio-codec-ctrl",
                                     "40000000.fabric"]
        with self.assertRaisesRegex(ValueError, "BOUND_PLATFORM_EXCEPTION_NOT_ISOLATED"):
            self.check(release, facts)

    def test_preload_collection_uses_locked_full_census_without_uio_read(self):
        release, facts = self.facts()
        facts["uio_overlaps"] = ["uio0"]
        class Port:
            def __init__(self):
                self.release = release
                self.full_scans = 0
            def _require_locked(self):
                return None
            def current_facts(self):
                self.full_scans += 1
                return facts
            def runtime_program_facts(self):
                raise AssertionError("program-session shortcut")
        port = Port()
        with tempfile.TemporaryDirectory() as td:
            proc = Path(td)
            boot = proc / "sys/kernel/random/boot_id"
            boot.parent.mkdir(parents=True)
            boot.write_text(facts["boot_id"])
            with patch.object(guard, "PROC", proc), \
                    patch.object(guard, "SYS", proc / "missing-sys"), \
                    patch.object(guard, "manager_last_load",
                                 return_value="fpga_manager fpga0: writing candidate.bin to fpga0"), \
                    patch.object(admission.os, "geteuid", return_value=0):
                report = admission.collect_live(
                    root_port=port, release=release,
                    expected_firmware=release.firmware_name,
                    require_mmio=False)
        self.assertEqual(port.full_scans, 1)
        self.assertIsNone(report["current_uio"])

    def test_preload_rejects_boot_change_after_census(self):
        release, facts = self.facts()
        class Port:
            def __init__(self):
                self.release = release
            def _require_locked(self):
                return None
            def current_facts(self):
                return facts
        with tempfile.TemporaryDirectory() as td:
            proc = Path(td)
            boot = proc / "sys/kernel/random/boot_id"
            boot.parent.mkdir(parents=True)
            boot.write_text("different-boot")
            with patch.object(guard, "PROC", proc), \
                    patch.object(guard, "manager_last_load",
                                 return_value="fpga_manager fpga0: writing candidate.bin to fpga0"), \
                    patch.object(admission.os, "geteuid", return_value=0):
                with self.assertRaisesRegex(ValueError,
                                            "BOOT_CHANGED_AFTER_RISK_SCAN"):
                    admission.collect_live(
                        root_port=Port(), release=release,
                        expected_firmware=release.firmware_name,
                        require_mmio=False)

    def test_mmio_collection_rejects_unproven_uio_owner(self):
        release, facts = self.facts()
        class Port:
            def __init__(self):
                self.release = release
            def _require_locked(self):
                return None
            def current_facts(self):
                return facts
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proc = root / "proc"
            boot = proc / "sys/kernel/random/boot_id"
            boot.parent.mkdir(parents=True)
            boot.write_text(facts["boot_id"])
            uio = root / "sys/class/uio/uio1"
            device = root / "sys/bus/platform/devices/43c00000.audio-codec-ctrl"
            device.mkdir(parents=True)
            (root / "uio_pdrv_genirq").touch()
            (device / "driver").symlink_to(root / "uio_pdrv_genirq")
            (device / "power").mkdir()
            (device / "power/runtime_status").write_text("active")
            (uio / "maps/map0").mkdir(parents=True)
            (uio / "device").symlink_to(device)
            (uio / "maps/map0/addr").write_text("0x40000000")
            (uio / "maps/map0/size").write_text("0x10000")
            (proc / "interrupts").write_text("1: 0 0 fabric\n")
            with patch.object(guard, "PROC", proc), \
                    patch.object(guard, "SYS", root / "sys"), \
                    patch.object(guard, "manager_last_load",
                                 return_value="fpga_manager fpga0: writing candidate.bin to fpga0"), \
                    patch.object(admission.os, "geteuid", return_value=0):
                with self.assertRaisesRegex(ValueError,
                                            "UIO_PLATFORM_OWNER_MISMATCH"):
                    admission.collect_live(
                        root_port=Port(), release=release,
                        expected_firmware=release.firmware_name)

    def test_incomplete_scan_reports_precise_kind_and_blocks(self):
        release, facts = self.facts()
        facts["proc_complete"] = False
        facts["proc_scan_diagnostic"] = {
            "status": "PROC_VISIBILITY_DENIED", "pid": "1234",
            "phase": "MAPS", "error": "PermissionError"}
        with self.assertRaisesRegex(ValueError,
                                    "PROC_SCAN_INCOMPLETE:PROC_VISIBILITY_DENIED:1234:MAPS:PermissionError"):
            self.check(release, facts)

    def test_owner_conflict_blocks_when_proc_snapshot_complete(self):
        release, facts = self.facts()
        facts["proc_conflicts"] = ["1234"]
        with self.assertRaisesRegex(ValueError, "PROC_RESOURCE_OWNER_CONFLICT"):
            self.check(release, facts)

    def test_other_root_integrity_failure_remains_fail_closed(self):
        release, facts = self.facts()
        facts["manager_state"] = "unknown"
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_ROOT_OR_PROCESS_FACTS"):
            self.check(release, facts)


class ProgramSessionProcScanSplitTests(unittest.TestCase):
    """Strict Manager census stays; program admission records NOT_RUN honestly."""

    def setUp(self):
        from types import SimpleNamespace
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.sys = self.work / "sys"
        self.proc = self.work / "proc"
        self.firmware = self.work / "firmware"
        self.firmware.mkdir()
        self.release = SimpleNamespace(
            firmware_name="candidate.bin", recovery_name=guard.GOLDEN_RECOVERY_NAME,
            firmware_sha256="a" * 64, recovery_sha256=guard.GOLDEN_RECOVERY_SHA256,
            soc_compatible="test,zynq", owner_base=0x40000000,
            owner_bytes=0x10000, uio_name="uio1",
            expected_uio={"uio": "uio1"},
            site_bitmap=1, image_id="test")
        boot = self.proc / "sys/kernel/random/boot_id"
        boot.parent.mkdir(parents=True)
        boot.write_text("test-boot-001")
        compatible = self.proc / "device-tree/compatible"
        compatible.parent.mkdir(parents=True)
        compatible.write_bytes(b"test,zynq\x00")
        state = self.sys / "class/fpga_manager/fpga0/state"
        state.parent.mkdir(parents=True)
        state.write_text("operating")

    def facts(self, *, runtime, scan, timing_ms=None):
        with patch.object(guard, "SYS", self.sys), \
                patch.object(guard, "PROC", self.proc), \
                patch.object(guard, "FIRMWARE", self.firmware), \
                patch.object(guard.os, "geteuid", return_value=0), \
                patch.object(guard, "sha_file", side_effect=lambda path, expected: expected), \
                patch.object(guard, "scan_kernel_owners",
                             return_value=(["uio1"], ["40000000.fabric"])), \
                patch.object(guard, "scan_proc_consumers", side_effect=scan):
            return guard.read_live_z2_facts(
                release=self.release, runtime_program_session=runtime,
                timing_ms=timing_ms)

    def test_admission_timing_preserves_process_conflict_evidence(self):
        timings = {}
        facts = self.facts(runtime=False,
                           scan=lambda **kw: (True, ["untrusted-owner"]),
                           timing_ms=timings)
        self.assertEqual(facts["proc_conflicts"], ["untrusted-owner"])
        self.assertEqual(set(timings),
                         {"image_hash", "kernel_owners", "process_census"})
        self.assertTrue(all(type(ms) is float and ms >= 0
                            for ms in timings.values()))

    def test_runtime_never_enumerates_all_proc_pids(self):
        def forbidden(**kwargs):
            raise AssertionError("runtime must not census all Linux processes")
        facts = self.facts(runtime=True, scan=forbidden)
        self.assertIsNone(facts["proc_complete"])
        self.assertIsNone(facts["proc_conflicts"])
        self.assertEqual(facts["proc_scan_diagnostic"],
                         {"status": "NOT_RUN_PROGRAM_SESSION"})
        self.assertEqual(facts["manager_state"], "operating")
        self.assertEqual(facts["uio_overlaps"], ["uio1"])

    def test_manager_still_requires_complete_process_visibility(self):
        diag = {}
        def scanner(**kwargs):
            kwargs["diagnostic"].update(status="PROC_VISIBILITY_DENIED",
                                        pid="1234", phase="MAPS",
                                        error="PermissionError")
            return False, ["1234"]
        facts = self.facts(runtime=False, scan=scanner)
        self.assertIs(facts["proc_complete"], False)
        self.assertEqual(facts["proc_conflicts"], ["1234"])
        self.assertEqual(facts["proc_scan_diagnostic"]["pid"], "1234")

    def test_manager_runtime_flag_does_not_forge_a_clean_scan(self):
        from pl.hil import fpga_image_admission as admission
        release = self.release
        facts = self.facts(runtime=True, scan=AssertionError("not called"))
        common = dict(
            release=release, passive=facts, uio=release.expected_uio,
            original_manager_load="fpga_manager fpga0: writing candidate.bin to fpga0",
            expected_firmware=release.firmware_name)
        self.assertEqual(admission.check_exact(
            **common, runtime_program_session=True)["image_id"], "test")
        with self.assertRaisesRegex(ValueError, "PROC_SCAN_INCOMPLETE"):
            admission.check_exact(**common)
        for field, value in (
                ("proc_complete", True),
                ("proc_conflicts", []),
                ("proc_scan_diagnostic", {"status": "COMPLETE"})):
            with self.subTest(field=field):
                malformed = dict(facts, **{field: value})
                with self.assertRaisesRegex(ValueError,
                                            "PROGRAM_SESSION_PROCESS_FACTS_INVALID"):
                    admission.check_exact(
                        **dict(common, passive=malformed),
                        runtime_program_session=True)

    def test_runtime_cannot_bypass_bad_image_or_manager_state(self):
        from pl.hil import fpga_image_admission as admission
        facts = self.facts(runtime=True, scan=AssertionError("not called"))
        common = dict(
            release=self.release, uio=self.release.expected_uio,
            original_manager_load="fpga_manager fpga0: writing candidate.bin to fpga0",
            expected_firmware=self.release.firmware_name,
            runtime_program_session=True)
        for change in ({"manager_state": "unknown"},
                       {"candidate_sha256": "c" * 64},
                       {"boot_id": ""}):
            with self.subTest(change=change), \
                    self.assertRaisesRegex(ValueError, "INCOMPLETE_ROOT_OR_PROCESS_FACTS"):
                admission.check_exact(
                    **dict(common, passive=dict(facts, **change)))
        with self.assertRaisesRegex(ValueError, "BOUND_UIO_EXACT_FACTS_CHANGED"):
            admission.check_exact(**dict(common, passive=facts,
                                         uio={"uio": "uio9"}))

    def test_bridge_uses_narrow_entry_and_scoped_fuser_under_lock(self):
        source = (ROOT / "scripts/bluepill-wordport-session.py").read_text()
        begin = source.index("with port.exclusive():")
        after = source[begin:]
        self.assertIn("root.live_program_session_report(port, release)", after)
        self.assertIn("['fuser', '-s', device]", after)
        self.assertLess(after.index("['fuser', '-s', device]"),
                        after.index("stack.enter_context(LinuxMMIO("))
        self.assertNotIn("root.live_report(port, release, release.firmware_name)", after)
        root_src = (ROOT / "pl/hil/fpga_image_root.py").read_text()
        start = root_src.index("def run(operation: str)")
        self.assertIn("live_report(port, release", root_src[start:])
        self.assertNotIn("live_program_session_report(", root_src[start:])



class RootStateAncestorTests(unittest.TestCase):
    """Root journal must not sit under a runtime-account-owned directory."""

    STATE = Path("/var/lib/plasma-privileged/fpga-deployment-state.json")

    def fake_lstat(self, table):
        import os as _os
        import stat as _stat

        def lstat(path):
            key = str(path)
            if key not in table:
                raise FileNotFoundError(key)
            uid, mode = table[key]
            return _os.stat_result((_stat.S_IFDIR | mode, 0, 0, 2, uid, uid,
                                    4096, 0, 0, 0))
        return lstat

    def chain(self, **overrides):
        table = {"/": (0, 0o755), "/var": (0, 0o755), "/var/lib": (0, 0o755),
                 "/var/lib/plasma-privileged": (0, 0o700)}
        table.update(overrides)
        return table

    def check(self, table):
        with patch.object(stage.os, "lstat", self.fake_lstat(table)):
            stage._state_dir_trusted(self.STATE)

    def test_production_state_is_dedicated_root_directory(self):
        self.assertEqual(stage.STATE, self.STATE)
        self.assertNotIn("/var/lib/plasma/", str(stage.STATE))
        native = (ROOT / "software/native/swd/"
                  "plasma_swd_openocd5088_ps_owner.c").read_text()
        self.assertIn(str(self.STATE), native)
        self.assertNotIn("/var/lib/plasma/privileged", native)

    def test_root_owned_private_chain_accepted(self):
        self.check(self.chain())

    def test_runtime_owned_grandparent_denied(self):
        # Z2 observed: /var/lib/plasma is uid 999 0755. Placing the journal
        # anywhere beneath it must fail closed even if the parent is root.
        state = Path("/var/lib/plasma/privileged/fpga-deployment-state.json")
        table = self.chain(**{"/var/lib/plasma": (999, 0o755),
                              "/var/lib/plasma/privileged": (0, 0o700)})
        with patch.object(stage.os, "lstat", self.fake_lstat(table)):
            with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                        "STATE_ANCESTOR_NOT_ROOT_PROTECTED"):
                stage._state_dir_trusted(state)

    def test_group_or_other_writable_ancestor_denied(self):
        for mode in (0o775, 0o757, 0o1777):
            with self.subTest(mode=oct(mode)):
                with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                            "STATE_ANCESTOR_NOT_ROOT_PROTECTED"):
                    self.check(self.chain(**{"/var/lib": (0, mode)}))

    def test_state_directory_must_be_private(self):
        with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                    "STATE_DIRECTORY_NOT_PRIVATE"):
            self.check(self.chain(**{"/var/lib/plasma-privileged": (0, 0o755)}))

    def test_missing_state_directory_fails_closed(self):
        table = self.chain()
        del table["/var/lib/plasma-privileged"]
        with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                    "STATE_DIRECTORY_NOT_PROVISIONED"):
            self.check(table)

    def test_missing_state_file_still_checks_directory_chain(self):
        table = self.chain(**{"/var/lib": (999, 0o755)})
        with patch.object(stage.os, "lstat", self.fake_lstat(table)), \
                patch.object(stage, "STATE", self.STATE):
            with self.assertRaisesRegex(stage.ImageDeploymentDenied,
                                        "STATE_ANCESTOR_NOT_ROOT_PROTECTED"):
                stage._state_file_trusted(require_file=False)


if __name__ == "__main__":
    unittest.main()
