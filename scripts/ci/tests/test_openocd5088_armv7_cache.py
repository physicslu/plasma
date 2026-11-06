#!/usr/bin/env python3
"""Host-only positive/negative contract tests for OpenOCD5088 ARMv7 build cache."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO / "scripts/ci/openocd5088-armv7-cache.py"
spec = importlib.util.spec_from_file_location("openocd5088_armv7_cache", MODULE_PATH)
cache = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(cache)
KEY = "a" * 64


class BuildKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in (cache.BUILD_RECIPE, cache.INJECTOR, cache.SELF):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        (self.root / cache.BUILD_RECIPE).write_text("toolchain epoch=1\nbuild recipe\n")
        (self.root / cache.INJECTOR).write_text("COPIES = ('adapter.c', 'adapter.h')\n")
        (self.root / cache.SELF).write_text("key implementation\n")
        folder = self.root / "software/native/swd"
        folder.mkdir(parents=True)
        (folder / "adapter.c").write_text("int adapter = 1;\n")
        (folder / "adapter.h").write_text("void adapter(void);\n")

    def test_document_template_admission_and_verify_only_changes_are_cache_hit(self):
        before = cache.build_key(self.root)
        for name in (
            "docs/runbook.md",
            "scripts/z2/hil/abi5_openocd_dpidr/deploy_tpl.py",
            "scripts/z2/plasma_swd_site_admission.py",
            "scripts/ci/verify-openocd5088-armv7.sh",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("repack or verify change; no C compilation\n")
        self.assertEqual(cache.build_key(self.root), before)

    def test_actual_build_input_invalidates_cache(self):
        original = cache.build_key(self.root)
        for name in (cache.BUILD_RECIPE, cache.INJECTOR, cache.SELF,
                     "software/native/swd/adapter.c", "software/native/swd/adapter.h"):
            path = self.root / name
            before = path.read_text()
            path.write_text(before + "\n# changed\n")
            self.assertNotEqual(cache.build_key(self.root), original, name)
            path.write_text(before)

    def test_missing_and_malformed_injector_inputs_fail_closed(self):
        (self.root / "software/native/swd/adapter.c").unlink()
        with self.assertRaises(ValueError):
            cache.build_key(self.root)
        (self.root / "software/native/swd/adapter.c").write_text("fixed\n")
        (self.root / cache.INJECTOR).write_text("COPIES = ('../escape.c',)\n")
        with self.assertRaises(ValueError):
            cache.build_key(self.root)


class CachedArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        binary = self.directory / "openocd"
        binary.write_bytes(b"\x7fELFdummy")
        binary.chmod(0o755)
        tcl = self.directory / "tcl/target"
        tcl.mkdir(parents=True)
        (tcl / "debug.cfg").write_text("adapter driver plasma_swd\n")

    def test_verified_cache_hit_and_expected_miss(self):
        with self.assertRaises(ValueError):
            cache.verify(self.directory, KEY)
        cache.seal(self.directory, KEY)
        cache.verify(self.directory, KEY)

    def test_wrong_key_corrupt_binary_or_tcl_must_fail(self):
        cache.seal(self.directory, KEY)
        with self.assertRaises(ValueError):
            cache.verify(self.directory, "b" * 64)
        binary = self.directory / "openocd"
        binary.write_bytes(binary.read_bytes() + b"X")
        with self.assertRaises(ValueError):
            cache.verify(self.directory, KEY)
        binary.write_bytes(b"\x7fELFdummy")
        (self.directory / "tcl/target/debug.cfg").write_text("tampered\n")
        with self.assertRaises(ValueError):
            cache.verify(self.directory, KEY)

    def test_missing_or_extra_payload_fails(self):
        cache.seal(self.directory, KEY)
        (self.directory / "unexpected.bin").write_text("wrong file\n")
        with self.assertRaises(ValueError):
            cache.verify(self.directory, KEY)

    def test_symlinked_file_fails(self):
        bad = self.directory / "tcl/target/escape.cfg"
        bad.symlink_to(self.directory / "openocd")
        with self.assertRaises(ValueError):
            cache.seal(self.directory, KEY)

    def test_nonexecutable_binary_fails(self):
        (self.directory / "openocd").chmod(0o644)
        with self.assertRaises(ValueError):
            cache.seal(self.directory, KEY)


class WorkflowContractTests(unittest.TestCase):
    def test_required_job_fresh_receipt_and_identical_artifact(self):
        wf = (REPO / ".github/workflows/swd-openocd5088-armv7-candidate.yml").read_text()
        self.assertIn("  armv7-source-locked-candidate:", wf)
        self.assertNotIn(
            'scripts/z2/plasma_swd_site_admission.py',
            wf.split("\npermissions:", 1)[0],
        )
        python_wf = (REPO / ".github/workflows/python-tests.yml").read_text()
        self.assertIn(
            'scripts/z2/plasma_swd_site_admission.py',
            python_wf.split("\nconcurrency:", 1)[0],
        )
        self.assertIn(
            "Deny Site admission and revocation without Root ownership", python_wf
        )
        self.assertIn("steps.build-cache.outputs.cache-hit != 'true'", wf)
        self.assertIn("github.event.pull_request.head.sha", wf)
        self.assertIn("actions/cache/restore@v4", wf)
        self.assertIn("actions/cache/save@v4", wf)
        self.assertIn("python3 scripts/ci/openocd5088-armv7-cache.py verify", wf)
        self.assertIn("bash scripts/ci/verify-openocd5088-armv7.sh", wf)
        self.assertIn('"plasma_source_sha": sys.argv[2]', wf)
        self.assertIn('candidate-evidence.json PROVENANCE.txt', wf)
        self.assertIn("name: plasma-openocd5088-armv7-candidate", wf)


if __name__ == "__main__":
    unittest.main()
