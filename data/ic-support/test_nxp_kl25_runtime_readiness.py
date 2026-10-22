"""Host-only KL25 real OpenOCD readiness acceptance: deterministic negative gates."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "data/ic-support/validate_nxp_kl25_runtime_readiness.py"
SPEC = importlib.util.spec_from_file_location("kl25_runtime_readiness", SCRIPT)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


class Kl25RuntimeReadinessTests(unittest.TestCase):
    def setUp(self):
        self.context = tempfile.TemporaryDirectory()
        self.addCleanup(self.context.cleanup)
        self.root = Path(self.context.name)
        self.binary = self.root / "bin" / "openocd"
        self.binary.parent.mkdir()
        header = bytearray(64)
        header[:4] = b"\x7fELF"
        header[4] = 2
        header[5] = 1
        struct.pack_into("<H", header, 18, 62)
        self.binary.write_bytes(header)
        self.scripts = self.root / "scripts"
        blobs = {}
        for rel in M.SCRIPT_PATHS:
            value = ("# host fixture: " + rel + "\n").encode("utf-8")
            file = self.scripts / rel.removeprefix("tcl/")
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(value)
            blobs[rel] = {"git_blob": M.git_blob_sha1(value), "bytes": len(value)}
        blobs["src/flash/nor/kinetis.c"] = {
            "git_blob": "7137b4aa078719af31122f8276494f006589e8ab"
        }
        audit = {
            "review_boundary": "SOURCE_ONLY_NO_EXECUTION",
            "exact": {
                "manufacturer": "NXP", "icpn": M.EXPECTED_ICPN,
                "other_kl25_variants_inherited": 0,
            },
            "provider": {"source_commit": M.EXPECTED_COMMIT},
            "result": {
                "programming_qualification_state": "CANDIDATE",
                "catalog_level": 1, "execution_authorized": False,
                "supported_exact_icpn_count_new": 0,
            },
            "source_files": blobs,
        }
        release = {
            "engine": "openocd", "version": "0.12.0",
            "source_commit": M.EXPECTED_COMMIT,
            "runtime_id": M.EXPECTED_RUNTIME,
        }
        self.audit = self.root / "source-review.json"
        self.release = self.root / "openocd.json"
        self.receipt = self.root / "install.json"
        self.audit.write_text(json.dumps(audit), encoding="utf-8")
        self.release.write_text(json.dumps(release), encoding="utf-8")
        receipt = {
            "result": "PASS", "evidence_level": "openocd-runtime-local-install",
            "openocd_version": "0.12.0",
            "source_commit": M.EXPECTED_COMMIT,
            "runtime_id": M.EXPECTED_RUNTIME,
            "hardware_runtime_ready": False,
            "starts_openocd_service": False,
            "binary": str(self.binary),
            "scripts_root": str(self.scripts),
            "architecture": "x86_64",
            "artifact_sha256": "a" * 64,
            "payload_sha256": "b" * 64,
        }
        self.receipt.write_text(json.dumps(receipt), encoding="utf-8")
        self.audit_patch = patch.object(M, "SOURCE_REVIEW", self.audit)
        self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)
        self.release_patch = patch.object(M, "OPENOCD_RELEASE", self.release)
        self.release_patch.start()
        self.addCleanup(self.release_patch.stop)

    def mutate(self, file: Path, fn):
        data = json.loads(file.read_text(encoding="utf-8"))
        fn(data)
        file.write_text(json.dumps(data), encoding="utf-8")

    def fake_runner(self, args, **kwargs):
        self.assertFalse(kwargs.get("shell", False))
        self.assertTrue(kwargs.get("capture_output"))
        if args[-1] == "--version":
            return subprocess.CompletedProcess(args, 0, "Open On-Chip Debugger 0.12.0\n", "")
        M.validate_argv(args, self.binary, self.scripts)
        return subprocess.CompletedProcess(
            args, 0, "PLASMA_KL25_NOINIT_CONFIG_ONLY=1\n", "")

    def accept(self):
        return M.run_acceptance(self.binary, self.scripts, self.receipt,
                                runner=self.fake_runner)

    def test_installed_artifact_host_only_attestation_does_not_promote(self):
        data = self.accept()
        self.assertEqual(data["evidence_boundary"], "HOST_ONLY_NOINIT")
        self.assertEqual(data["host_parser"], "PASS")
        self.assertEqual(data["parser_transport"], "jtag")
        self.assertFalse(data["swd_session_qualified"])
        self.assertFalse(data["real_silicon_observed"])
        self.assertEqual(data["source_binary_sha256"], M.sha256_file(self.binary))
        self.assertEqual(data["runtime_provenance"]["architecture"], "x86_64")
        self.assertEqual(data["runtime_provenance"]["artifact_sha256"], "a" * 64)
        self.assertEqual(data["qualification"]["admission"], "BLOCKED")
        self.assertEqual(set(data["operations"].values()), {"UNKNOWN"})
        self.assertFalse(data["job_selectable"])
        self.assertFalse(data["execution_authorized"])
        self.assertFalse(data["installed_runtime_attested"])
        self.assertFalse(data["hardware_runtime_ready"])

    def test_pinned_source_blob_mismatch_fails_closed(self):
        target = self.scripts / "target/klx.cfg"
        target.write_text("# replaced Tcl\n", encoding="utf-8")
        with self.assertRaisesRegex(M.Kl25ReadinessError, "Git blob mismatch"):
            self.accept()

    def test_runtime_source_and_binary_architecture_drift(self):
        self.mutate(self.receipt, lambda x: x.update(source_commit="0" * 40))
        with self.assertRaisesRegex(M.Kl25ReadinessError, "receipt"):
            self.accept()
        self.mutate(self.receipt, lambda x: x.update(source_commit=M.EXPECTED_COMMIT,
                                                     architecture="armv7l"))
        with self.assertRaisesRegex(M.Kl25ReadinessError, "architecture"):
            self.accept()

    def test_forged_installed_hardware_ready_is_rejected(self):
        self.mutate(self.receipt, lambda x: x.update(hardware_runtime_ready=True))
        with self.assertRaisesRegex(M.Kl25ReadinessError, "receipt"):
            self.accept()

    def test_unqualified_evidence_cannot_be_injected_as_supported(self):
        proof = self.accept()
        cases = [
            lambda x: x.update(software_state="SUPPORTED", catalog_level=2,
                               job_selectable=True),
            lambda x: x.update(execution_authorized=True),
            lambda x: x.update(installed_runtime_attested=True),
            lambda x: x.update(swd_session_qualified=True),
            lambda x: x.update(real_silicon_observed=True),
            lambda x: x["operations"].update(PROGRAM="SUPPORTED"),
            lambda x: x.update(missing_gates=[]),
        ]
        for mutate in cases:
            altered = json.loads(json.dumps(proof))
            mutate(altered)
            with self.subTest(mutate=mutate.__code__.co_firstlineno):
                with self.assertRaises(M.Kl25ReadinessError):
                    M.qualification_boundary_claim(altered)

    def test_parser_refuses_any_other_argv(self):
        safe = M.build_safe_argv(self.binary, self.scripts)
        self.assertEqual(safe[3:5], ["-c", "noinit"])
        for bad in (
            safe[:-2] + ["-c", "init", "-c", "shutdown"],
            safe[:-2] + ["-c", "flash erase_address 0 0x400", "-c", "shutdown"],
            [x.replace("jtag", "swd") for x in safe],
        ):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(M.Kl25ReadinessError, "unapproved"):
                    M.validate_argv(bad, self.binary, self.scripts)

    def test_binary_version_probe_must_report_pinned_version(self):
        def bad_runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, "Open On-Chip Debugger 0.13.0\n", "")
        with self.assertRaisesRegex(M.Kl25ReadinessError, "version differs"):
            M.run_acceptance(self.binary, self.scripts, self.receipt,
                             runner=bad_runner)


if __name__ == "__main__":
    unittest.main()
