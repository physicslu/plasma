#!/usr/bin/env python3
"""Historical replay reproduces the frozen v1 sidecar without the Runtime compiler."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import stm32f103c_vendor_neutral_admission as v1
import stm32f103c_vendor_neutral_admission_historical_replay as replay

COMPILER_PATH = v1.CONTRACT["legacy_inputs"]["compiler"]["path"]


def _deny_working_tree_compiler(original):
    def guarded(relative: str) -> Path:
        if relative == COMPILER_PATH:
            raise AssertionError("replay read the working-tree Runtime compiler")
        return original(relative)
    return guarded


class HistoricalAdmissionReplayTests(unittest.TestCase):
    def test_replay_reproduces_original_v1_artifacts_and_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest = replay.build_sidecar(Path(temp) / "sidecar")
        self.assertEqual(manifest["files"], replay.EXPECTED_V1_FILES)
        self.assertEqual(manifest["release_digest"], replay.EXPECTED_V1_RELEASE_DIGEST)
        self.assertEqual(manifest["migration_base_commit"], v1.CONTRACT["migration_base_commit"])

    def test_replay_never_reads_working_tree_runtime_compiler(self) -> None:
        with patch.object(v1, "_repo_path", _deny_working_tree_compiler(v1._repo_path)):
            result = replay.validate()
            with tempfile.TemporaryDirectory() as temp:
                manifest = replay.build_sidecar(Path(temp) / "sidecar")
        self.assertEqual({r["status"] for r in result.values()}, {"VALID"})
        self.assertEqual(manifest["release_digest"], replay.EXPECTED_V1_RELEASE_DIGEST)

    def test_frozen_v1_generator_is_restored_after_replay(self) -> None:
        original = v1._repo_path
        replay.validate()
        self.assertIs(v1._repo_path, original)

    def test_retired_compiler_bytes_match_pinned_blob_at_fixed_commit(self) -> None:
        raw = replay.retired_compiler_bytes()
        self.assertEqual(replay._blob_id(raw), v1.CONTRACT["legacy_inputs"]["compiler"]["git_blob_sha1"])
        self.assertIn("class OpenOCDPlanCompiler:", raw.decode("utf-8"))

    def test_tampered_pin_commit_or_path_fails_closed(self) -> None:
        mutations = {
            "blob": ("legacy_inputs", "compiler", "git_blob_sha1", "0" * 40),
            "malformed_blob": ("legacy_inputs", "compiler", "git_blob_sha1", "not-a-blob"),
            "path": ("legacy_inputs", "compiler", "path", "software/python/plasma_interfaces/openocd.py"),
            "escape": ("legacy_inputs", "compiler", "path", "../outside.py"),
        }
        for name, (a, b, key, value) in mutations.items():
            with self.subTest(name=name):
                contract = copy.deepcopy(v1.CONTRACT)
                contract[a][b][key] = value
                with self.assertRaises(v1.MigrationError):
                    replay.retired_compiler_bytes(contract)
        for commit in ("0" * 40, "HEAD"):
            with self.subTest(commit=commit):
                contract = copy.deepcopy(v1.CONTRACT)
                contract["migration_base_commit"] = commit
                with self.assertRaises(v1.MigrationError):
                    replay.retired_compiler_bytes(contract)

    def test_digest_drift_against_original_v1_fails_closed(self) -> None:
        with patch.object(replay, "EXPECTED_V1_RELEASE_DIGEST", "0" * 64):
            with tempfile.TemporaryDirectory() as temp:
                with self.assertRaisesRegex(v1.MigrationError, "release digest"):
                    replay.build_sidecar(Path(temp) / "sidecar")


if __name__ == "__main__":
    unittest.main()
