#!/usr/bin/env python3
"""Offline Gate 1 negative controls; do not operate devices or publish catalog state."""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
runner = ROOT / "scripts/ci/icpn_stm32_governance_shadow.py"
spec = importlib.util.spec_from_file_location("governance_shadow", runner)
shadow = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(shadow)


class ShadowContracts(unittest.TestCase):
    def test_baseline(self):
        shadow.self_test()

    def test_source_ownership(self):
        for key in shadow.TARGETS:
            self.assertEqual(shadow.affected([shadow.SOURCES[key]["file"]]), [key])
        self.assertEqual(shadow.affected(["software/web/unrelated.ts"]), [])
        self.assertEqual(shadow.affected(["data/device-catalog/production/icpn-v1-manifest.json"]), [])
        for path in shadow.SHARED:
            self.assertEqual(shadow.affected([path]), list(shadow.TARGETS))

    def test_shared_path_fanout(self):
        self.assertEqual(shadow.affected(["data/device-catalog/research/stm32-post-u5-frontier-selection.json"]),
                         ["post_u5", "h7_scope"])
        self.assertEqual(shadow.affected(["data/device-catalog/research/stm32h7-partitioned-scope-selection.json"]),
                         ["h7_scope", "h7rs_evidence"])
        self.assertEqual(shadow.affected(["data/device-catalog/research/stm32h7-partition-source.json"]),
                         ["h7_scope", "h7rs_evidence"])

    def test_recursive_evidence_glob(self):
        self.assertEqual(shadow.affected(["data/device-catalog/research/evidence/stm32h7rs-accessibility-live-2026-09-16/a/b.json"]),
                         ["h7rs_evidence"])

    def test_fail_closed_source_mutation(self):
        for target in shadow.TARGETS:
            original = (ROOT / shadow.SOURCES[target]["file"]).read_bytes()
            with self.assertRaisesRegex(ValueError, "pinned original"):
                shadow.validate_source(target, original + b"\n# unexpected drift\n")

    def test_fail_closed_shadow_trigger_mutation(self):
        body = (ROOT / shadow.SHADOW).read_text()
        needle = "'data/device-catalog/research/stm32-post-u5-frontier-selection.json'"
        self.assertEqual(body.count(needle), 2)
        with self.assertRaisesRegex(ValueError, "trigger union"):
            shadow.verify_shadow(body.replace(needle, "'data/device-catalog/production/manifest.json'", 1))
        with self.assertRaisesRegex(ValueError, "trigger union"):
            shadow.verify_shadow(body.replace(needle + "\n", "", 1))

    def test_fail_closed_runner_permissions_mutation(self):
        body = (ROOT / shadow.SHADOW).read_text()
        with self.assertRaisesRegex(ValueError, "runtime"):
            shadow.verify_shadow(body.replace("timeout-minutes: 10", "timeout-minutes: 12", 1))
        with self.assertRaisesRegex(ValueError, "runtime"):
            shadow.verify_shadow(body.replace("contents: read", "contents: write", 1))

    def test_invalid_git_revisions_and_event(self):
        with self.assertRaisesRegex(ValueError, "unsafe"):
            shadow.diff_paths("not-sha", "a" * 40, "pull_request")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            shadow.diff_paths("a" * 40, "bad-head", "push")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            shadow.diff_paths("a" * 40, "b" * 40, "workflow_dispatch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
