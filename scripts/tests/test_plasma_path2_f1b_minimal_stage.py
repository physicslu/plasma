#!/usr/bin/env python3
"""Host-only repeatable F1-B stage tests. Fake device; never touch /dev/mem."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pl.hil import f1b
from pl.hil import path2_f1b_minimal_stage as stage
from pl.hil import path2_f1b_dev_risk as risk
from pl.hil.swd04 import one_shot

REAL_RUN_CHILD = one_shot.run_child
REAL_LIVE_REPORT = stage.live_report


class FakeTarget:
    def __init__(self):
        self.boot = "test-boot-very-long-id"
        self.image = "base.bin"
        self.writes = []
        self.reads = 0
        self.fail_load = False
        self.fail_restore = False
        self.fail_child = False

    def exclusive(self):
        return nullcontext()

    def report(self, port, expected):
        if expected != self.image:
            raise stage.LiveStageDenied("MANAGER_LAST_LOAD_CHANGED")
        return {"site": 1, "target_boot_id": self.boot,
                "expected_manager_firmware": expected,
                "axi_isolation": "UNPROVEN_ACCEPTED_FOR_ONE_DEVELOPMENT_EXPERIMENT",
                "development_exception": risk.WAIVER}

    def manager_write(self, image):
        self.writes.append(image)
        if image == stage.CANDIDATE.name and self.fail_load:
            raise RuntimeError("INJECTED_LOAD_ERROR")
        if image == "base.bin" and self.fail_restore:
            raise RuntimeError("INJECTED_RESTORE_ERROR")
        self.image = image

    def run_child(self, cmd):
        self.reads += 1
        if self.fail_child:
            raise RuntimeError("INJECTED_SIGBUS")
        assert cmd[1:] == ["-m", "pl.hil.path2_f1b_minimal_stage",
                            "--identity-child"]
        one_shot.record_json(stage.CHILD, {
            "observed": {str(k): v for k, v in f1b.IDENTITY.items()}})


class RepeatableStageTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.target = FakeTarget()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.t.name)
        self.stack.enter_context(patch.object(stage, "STATE", root / "state.json"))
        self.stack.enter_context(patch.object(stage, "CHILD", root / "child.json"))
        self.stack.enter_context(patch.object(stage, "trusted_local"))
        self.stack.enter_context(patch.object(stage, "_state_file_trusted"))
        self.stack.enter_context(patch.object(stage.guard, "RootZ2TargetPort",
                                              return_value=self.target))
        self.stack.enter_context(patch.object(stage, "live_report",
                                              side_effect=self.target.report))
        self.stack.enter_context(patch.object(one_shot, "manager_write",
                                              side_effect=self.target.manager_write))
        self.stack.enter_context(patch.object(one_shot, "run_child",
                                              side_effect=self.target.run_child))
        self.stack.enter_context(patch.object(one_shot, "protected"))

    def state(self):
        return stage.read_state()

    def test_source_owned_image_release_is_the_only_admitted_candidate(self):
        """Source-pinned release, not an AP-supplied image/module selector."""
        from dataclasses import replace
        release = stage.approved_image(stage.F1B_APPROVED_IMAGE)
        self.assertEqual(release.firmware_name, stage.CANDIDATE.name)
        self.assertEqual(release.recovery_name, "base.bin")
        self.assertEqual(release.firmware_sha256, f1b.BIN_SHA)
        self.assertEqual(release.recovery_sha256, f1b.BASE_SHA)
        self.assertEqual(release.abi_version, f1b.IDENTITY[4])
        for change in (
            {"image_id": "user-chosen-unreviewed"},
            {"firmware_name": "unreviewed.bin"},
            {"firmware_sha256": "0" * 64},
            {"recovery_sha256": "0" * 64},
            {"board_id": "different-board"},
            {"fpga_part": "another-fpga"},
            {"abi_version": 2},
            {"site_bitmap": 255},
            {"identity_words": ((0, 0),)},
        ):
            with self.subTest(change=change), self.assertRaisesRegex(
                    stage.LiveStageDenied, "IMAGE_RELEASE_NOT_ROOT_AUTHORIZED"):
                stage.approved_image(replace(release, **change))
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "IMAGE_RELEASE_NOT_ROOT_AUTHORIZED"):
            stage.approved_image({"image_id": release.image_id})
        self.assertEqual(self.target.writes, [])

    def test_ap_metadata_claim_is_comparison_not_image_authority(self):
        release = stage.F1B_APPROVED_IMAGE
        metadata = dict(board_id=release.board_id,
                        fpga_part=release.fpga_part,
                        abi_version=release.abi_version,
                        identity_words=dict(release.identity_words))
        stage.verify_image_metadata(release, **metadata)
        for changed in (
            {"board_id": "other-board"},
            {"fpga_part": "xc7z010clg400-1"},
            {"abi_version": 0},
            {"identity_words": {0: f1b.IDENTITY[0]}},
        ):
            with self.subTest(changed=changed), self.assertRaises(
                    stage.LiveStageDenied):
                stage.verify_image_metadata(release, **(metadata | changed))
        from dataclasses import replace
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "IMAGE_RELEASE_NOT_ROOT_AUTHORIZED"):
            stage.verify_image_metadata(
                replace(release, image_id="unreviewed"), **metadata)
        self.assertEqual(self.target.writes, [])

    def test_root_image_authorization_runs_before_hardware_manager(self):
        """Guard injected denial: no Root port or FPGA write may start."""
        with patch.object(stage, "approved_image",
                          side_effect=stage.LiveStageDenied(
                              "IMAGE_RELEASE_NOT_ROOT_AUTHORIZED")) as gate, \
             patch.object(stage.guard, "RootZ2TargetPort") as target_port, \
             patch.object(one_shot, "manager_write") as writer:
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "IMAGE_RELEASE_NOT_ROOT_AUTHORIZED"):
                stage.run("download")
            gate.assert_called_once()
            target_port.assert_not_called()
            writer.assert_not_called()
        self.assertFalse(stage.STATE.exists())

    def test_installed_source_pinned_release_matches_reviewed_f1b(self):
        record = stage.read_approved_release()
        self.assertEqual(record, stage.F1B_APPROVED_IMAGE)
        self.assertEqual(dict(record.identity_words), f1b.IDENTITY)
        self.assertEqual(self.target.writes, [])

    def test_source_release_rejects_invalid_or_forged_metadata(self):
        """A changed JSON file does not create another authorized Image."""
        original = json.loads(stage.RELEASE_FILE.read_text(encoding="utf-8"))
        variants = (
            {"image_id": "unreviewed-fpga-image"},
            {"board_id": "wrong-board"},
            {"soc_compatible": "malicious,ps"},
            {"fpga_part": "xc7z010clg400-1"},
            {"firmware_sha256": "0" * 64},
            {"recovery_sha256": "0" * 64},
            {"firmware_name": "../arbitrary.bin"},
            {"abi_version": 2},
            {"identity_words": [[0, 0], [4, 65536], [16384, 1]]},
            {"site_bitmap": 3},
            {"authorization": "SHA_ONLY"},
            {"schema": "unknown-schema"},
            {"unexpected": True},
        )
        with tempfile.TemporaryDirectory() as td:
            candidate = Path(td) / "image-release.json"
            for changed in variants:
                with self.subTest(change=changed):
                    candidate.write_text(json.dumps(original | changed))
                    with patch.object(stage, "RELEASE_FILE", candidate):
                        with self.assertRaises(stage.LiveStageDenied):
                            stage.read_approved_release()
            for malformed in (
                "",
                "{",
                "[]",
                "null",
                '{"schema":"old","schema":"new"}',
                '{"schema": NaN}',
            ):
                with self.subTest(malformed=malformed):
                    candidate.write_text(malformed)
                    with patch.object(stage, "RELEASE_FILE", candidate):
                        with self.assertRaises((stage.LiveStageDenied,
                                                ValueError)):
                            stage.read_approved_release()
            candidate.unlink()
            with patch.object(stage, "RELEASE_FILE", candidate):
                with self.assertRaises(stage.LiveStageDenied):
                    stage.read_approved_release()
        self.assertEqual(self.target.writes, [])

    def test_release_soc_expectation_and_observed_pl_abi_are_separate(self):
        """Host fixtures exercise checkers, not physical Board/IP attestation."""
        release = stage.read_approved_release()
        self.assertEqual(release.soc_compatible, "xlnx,zynq-7000")
        nul = bytes([0])
        stage.verify_live_ps_compatible(
            release, raw_compatible=b"test,pynq-z2" + nul +
                                    b"xlnx,zynq-7000" + nul)
        valid = dict(release.identity_words)
        stage.verify_observed_pl_identity(
            release, observed=valid, read32_count=3, write32_count=0)
        bad_compatibles = (
            b"xlnx,zynq-7000",  # missing required DT trailing NUL
            b"other,zynq-7000" + nul,
            b"xlnx,zynq-7000-extra" + nul,
            b"",
            "xlnx,zynq-7000",
        )
        for incompatible in bad_compatibles:
            with self.subTest(value=incompatible), self.assertRaisesRegex(
                    stage.LiveStageDenied, "IMAGE_PS_SOC_COMPATIBLE_MISMATCH"):
                stage.verify_live_ps_compatible(
                    release, raw_compatible=incompatible)
        for actual, reads, writes in (
            ({**valid, 4: 0}, 3, 0),
            ({**valid, 16384: 2}, 3, 0),
            ({0: valid[0], 4: valid[4]}, 2, 0),
            ({**valid, 0: -1}, 3, 0),
            (valid, 4, 0),
            (valid, 3, 1),
            (valid, True, 0),
        ):
            with self.subTest(actual=actual, reads=reads, writes=writes), \
                 self.assertRaises(stage.LiveStageDenied):
                stage.verify_observed_pl_identity(
                    release, observed=actual,
                    read32_count=reads, write32_count=writes)
        self.assertEqual(self.target.writes, [])

    def test_live_report_reads_real_kernel_compatible_bytes_not_ap_claim(self):
        """Root's live observation reads PS Device Tree via existing guard."""
        actual = REAL_LIVE_REPORT
        release = stage.read_approved_release()
        with tempfile.TemporaryDirectory() as td:
            proc = Path(td)
            compatible = proc / "device-tree" / "compatible"
            compatible.parent.mkdir()
            port = Mock()
            port.image_sha256.side_effect = lambda which: {
                "candidate": release.firmware_sha256,
                "recovery": release.recovery_sha256,
            }[which]
            fake_report = {
                "site": 1, "expected_manager_firmware": release.recovery_name
            }
            with patch.object(stage, "live_report", actual), \
                 patch.object(stage.guard, "PROC", proc), \
                 patch.object(stage.risk, "collect_live",
                              return_value=fake_report):
                compatible.write_bytes(b"unrelated,soc" + bytes([0]))
                with self.assertRaisesRegex(
                        stage.LiveStageDenied,
                        "IMAGE_PS_SOC_COMPATIBLE_MISMATCH"):
                    stage.live_report(port, release.recovery_name)
                compatible.write_bytes(b"xlnx,zynq-7000" + bytes([0]))
                self.assertEqual(
                    stage.live_report(port, release.recovery_name),
                    fake_report)
        self.assertEqual(self.target.writes, [])

    def test_independently_triggered_repeatable_full_lifecycle(self):
        first = stage.run("download")
        self.assertEqual(first["result"], "LOADED_AND_HELD")
        self.assertIs(first["auto_test"], False)
        self.assertEqual(self.target.writes, [stage.CANDIDATE.name])
        # A deliberate second Download in the same session is permitted.
        second = stage.run("download")
        self.assertEqual(second["download_count"], 2)
        self.assertEqual(first["lease_id"], second["lease_id"])
        self.assertEqual(self.target.writes.count(stage.CANDIDATE.name), 2)
        # Testing may run repeatedly; no automatic next-stage selection.
        self.assertEqual(stage.run("test")["result"], "IDENTITY_PASS")
        read2 = stage.run("test")
        self.assertEqual(read2["test_count"], 2)
        self.assertEqual(self.target.reads, 2)
        self.assertEqual(len(self.target.writes), 2)
        self.assertEqual(stage.run("restore")["result"], "RESTORED_VERIFIED")
        self.assertEqual(stage.run("restore")["result"], "ALREADY_RESTORED")
        self.assertEqual(self.target.writes.count("base.bin"), 1)
        third = stage.run("download")
        self.assertEqual(third["download_count"], 3)
        self.assertEqual(third["lease_id"], first["lease_id"])
        self.assertEqual(stage.run("test")["test_count"], 3)
        self.assertEqual(stage.run("restore")["restore_count"], 2)
        self.assertEqual(self.state()["status"], "BASE")

    def test_no_prior_load_denies_readonly_testing_and_restore(self):
        for command in ("test", "restore"):
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "DOWNLOAD_REQUIRED_BEFORE"):
                stage.run(command)
        self.assertEqual(self.target.writes, [])

    def test_restored_base_is_not_f1b_readiness(self):
        stage.run("download")
        stage.run("restore")
        before = stage.STATE.read_bytes()
        self.target.writes.clear()
        with patch.object(stage, "live_report") as inspect_live:
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "F1B_IMAGE_NOT_LOADED"):
                stage.run("test")
            inspect_live.assert_not_called()
        self.assertEqual(self.target.reads, 0)
        self.assertEqual(self.target.writes, [])
        self.assertEqual(stage.STATE.read_bytes(), before)
        self.assertEqual(self.state()["test_count"], 0)

    def test_inconsistent_f1b_image_denied_before_live_inspection(self):
        record = stage.init_state(self.target.report(self.target, "base.bin"))
        record["status"] = "F1B"
        stage.write_state(record)
        with patch.object(stage, "live_report") as inspect_live:
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "F1B_IMAGE_NOT_LOADED"):
                stage.run("test")
            inspect_live.assert_not_called()
        self.assertEqual(self.target.reads, 0)
        self.assertEqual(self.target.writes, [])

    def test_restore_after_download_without_testing_is_manual_and_valid(self):
        stage.run("download")
        out = stage.run("restore")
        self.assertEqual(out["result"], "RESTORED_VERIFIED")
        self.assertEqual(self.target.writes,
                         [stage.CANDIDATE.name, "base.bin"])

    def test_failed_download_sets_unknown_without_blind_retry(self):
        self.target.fail_load = True
        with self.assertRaisesRegex(RuntimeError, "INJECTED_LOAD"):
            stage.run("download")
        self.assertEqual(self.state()["status"], "UNKNOWN")
        self.target.fail_load = False
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "UNCERTAIN_PRIOR_OPERATION"):
            stage.run("download")
        self.assertEqual(len(self.target.writes), 1)

    def test_failed_test_blocks_restore_without_blind_reload(self):
        stage.run("download")
        self.target.fail_child = True
        with self.assertRaisesRegex(RuntimeError, "INJECTED_SIGBUS"):
            stage.run("test")
        self.assertEqual(self.state()["status"], "UNKNOWN")
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "UNCERTAIN_PRIOR_OPERATION"):
            stage.run("restore")
        self.assertEqual(self.target.writes, [stage.CANDIDATE.name])

    def test_native_supervisor_sigbus_and_unreaped_persist_stop(self):
        import subprocess
        for exits, reason in (([-7], "SIGBUS"),
                ([subprocess.TimeoutExpired("fake", 35)] * 3,
                 "UNREAPED_NO_RELOAD")):
            with self.subTest(reason=reason):
                if stage.STATE.exists():
                    stage.STATE.unlink()
                self.target.image = "base.bin"
                self.target.writes.clear()
                stage.run("download")
                proc = Mock(pid=123, wait=Mock(side_effect=exits))
                with patch.object(one_shot, "run_child", REAL_RUN_CHILD), \
                     patch.object(one_shot.subprocess, "Popen", return_value=proc), \
                     patch.object(one_shot.os, "killpg"), \
                     self.assertRaisesRegex(one_shot.c.SafetyError, reason):
                    stage.run("test")
                self.assertEqual(self.state()["status"], "UNKNOWN")
                for follow in ("download", "test", "restore"):
                    with self.assertRaisesRegex(stage.LiveStageDenied,
                                                "UNCERTAIN_PRIOR_OPERATION"):
                        stage.run(follow)
                self.assertEqual(self.target.writes, [stage.CANDIDATE.name])

    def test_restore_error_forbids_blind_repeat(self):
        stage.run("download")
        self.target.fail_restore = True
        with self.assertRaisesRegex(RuntimeError, "INJECTED_RESTORE"):
            stage.run("restore")
        self.assertEqual(self.state()["status"], "UNKNOWN")
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "UNCERTAIN_PRIOR_OPERATION"):
            stage.run("restore")
        self.assertEqual(self.target.writes.count("base.bin"), 1)

    def test_loaded_manager_and_boot_are_refreshed_each_trigger(self):
        stage.run("download")
        self.target.image = "base.bin"
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "MANAGER_LAST_LOAD_CHANGED"):
            stage.run("test")
        self.target.image = stage.CANDIDATE.name
        self.target.boot = "different-boot-long-id"
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "BOOT_CHANGED_MANUAL_REVIEW"):
            stage.run("test")
        self.assertEqual(self.target.reads, 0)

    def test_state_persists_across_restarts_and_is_not_one_use(self):
        first = stage.run("download")
        self.assertTrue(stage.STATE.exists())
        loaded = json.loads(stage.STATE.read_text())
        self.assertEqual(loaded["status"], "F1B")
        self.assertEqual(loaded["session_id"], first["lease_id"])
        self.assertEqual(stage.run("test")["test_count"], 1)
        self.assertEqual(stage.run("restore")["result"], "RESTORED_VERIFIED")
        self.assertEqual(stage.run("download")["download_count"], 2)
        self.assertEqual(first["lease_id"], self.state()["session_id"])

    def test_unfinished_operation_after_crash_is_unknown(self):
        stage.run("download")
        record = self.state()
        record["status"] = "RESTORE_IN_FLIGHT"
        stage.write_state(record)
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "UNCERTAIN_PRIOR_OPERATION"):
            stage.run("restore")
        self.assertEqual(self.target.writes, [stage.CANDIDATE.name])

    @patch.object(Path, "resolve", lambda path: path)
    def test_abnormal_arm_runtime_denied_before_hardware(self):
        stage.native_runtime_preflight(
            version=(3, 12, 13), machine="armv7l", endian="little",
            executable="/opt/plasma/python/3.12.13/bin/python3")
        for change in ({"version": (3, 11, 0)}, {"machine": "x86_64"},
                       {"endian": "big"}, {"executable": "/usr/bin/python3"}):
            args = {"version": (3, 12, 13), "machine": "armv7l",
                    "endian": "little",
                    "executable": "/opt/plasma/python/3.12.13/bin/python3"}
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "NATIVE_ARMV7_PYTHON_RUNTIME_REQUIRED"):
                stage.native_runtime_preflight(**(args | change))
        self.assertEqual(self.target.writes, [])

    def test_root_and_explicit_waiver_enforced(self):
        with patch.object(stage, "trusted_local", wraps=None) as gate:
            gate.side_effect = stage.LiveStageDenied("ROOT_REQUIRED")
            with self.assertRaisesRegex(stage.LiveStageDenied, "ROOT_REQUIRED"):
                stage.run("download")
        self.assertFalse(stage.STATE.exists())

    def test_no_arbitrary_stage_or_auto_chain_or_dispatch_registration(self):
        for stage_name in ("build", "download+test", "download;exit", ""):
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "STAGE_NOT_ALLOWLISTED"):
                stage.run(stage_name)
        self.assertFalse(stage.STATE.exists())
        source = (ROOT / "pl/hil/path2_f1b_minimal_stage.py").read_text()
        self.assertNotIn("paramiko", source)
        self.assertNotIn("auto_run", source)
        integration = (ROOT / "scripts/plasma_path2_runtime_integration.py").read_text()
        self.assertIn("def direct_root_operation(", integration)
        self.assertNotIn("def registered_hardware_stage(", integration)
        self.assertNotIn("def full_hil_sequence(", integration)


if __name__ == "__main__":
    unittest.main()
